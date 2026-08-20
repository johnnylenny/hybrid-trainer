#!/usr/bin/env python3
"""
garmin_sync.py — daily Garmin Connect -> Hybrid Trainer cloud sync.

Runs in GitHub Actions (see .github/workflows/garmin-sync.yml). Fetches the
last FETCH_DAYS days of Garmin activities, maps each one to a Hybrid Trainer session
row (same shapes the webapp's TCX importer produces), and inserts the new
ones into the Supabase `sessions` table, signed in as the app user so RLS
applies normally.

HARD RULE — tokens only, never a credential login:
  Garmin aggressively rate-limits password logins (429s, multi-day account
  lockouts). This script contains NO credential-login code path at all. It
  loads the SHARED token bundle from the cloud `garmin_tokens` row, uses it,
  and writes the refreshed bundle back at the end of the run — the same
  bundle local runs use, so the two can no longer drift apart (that drift is
  what kept killing bundles early; the full story is in sync/token_store.py).
  If the bundle is missing or expired it fails fast, and the fix is one local
  command: python3 sync/seed_tokens.py --upload. Seeding is the only
  credential login, it is local and human-only, and it never happens in CI.

Dedupe: every inserted row carries import_source "garmin:<UTC ISO>", the
same format the webapp's TCX importer writes, so a run imported manually
from a .tcx file and the same run arriving via this sync collapse into one.
The skip-check normalizes both sides to seconds precision so formatting
differences (milliseconds, Z suffix) can't cause a duplicate.

Env vars (set as GitHub secrets / vars):
  SUPABASE_URL, SUPABASE_ANON_KEY  — the app's public Supabase config
  HT_EMAIL, HT_PASSWORD            — the app user's login (RLS stays intact).
                                     These now also gate the Garmin bundle:
                                     it is read from a row this user owns.
  EASY_HR_CEILING (optional)       — bpm; enables tempo-run detection. The
                                     app stores this setting locally only
                                     (not cloud-synced), so CI can't read it
                                     from the database. Blank = tempo off,
                                     hot runs classify as easy (same as the
                                     app with the setting blank).
"""

import os
import re
import sys
import time
import uuid
from datetime import date, datetime, timedelta, timezone

# Guarded imports so the pure mapping helpers below can be unit-tested
# without installing the network deps. main() checks and fails loudly.
try:
    from garminconnect import Garmin
except ImportError:
    Garmin = None
try:
    from supabase import create_client
except ImportError:
    create_client = None

# Shared with garmin_push.py, not re-typed: EXERCISE_TAXONOMY is the one table
# that teaches this repo both directions (app name -> Garmin, and here, Garmin
# -> app name). A hand-copied second table would be a silent drift risk, same
# reasoning garmin_pull_corpus.py already uses for importing classify_run_type
# from this file. garmin_push.py has no module-level network calls and guards
# its own garminconnect/supabase imports, so this import is safe even without
# those deps installed.
from garmin_push import EXERCISE_TAXONOMY, PUSH_NAME_PREFIX
GARMIN_EXERCISE_TO_APP_NAME = {v: k.title() for k, v in EXERCISE_TAXONOMY.items()}

# The shared Garmin token bundle + Supabase sign-in. Same standalone-entry-point
# reasoning as the import above: one implementation, imported, not re-typed.
import token_store

TOKEN_DIR = os.path.expanduser(os.getenv("GARMIN_TOKEN_DIR", "~/.garminconnect"))
REQUEST_DELAY_SECONDS = 0.5  # pause between Garmin API calls (be polite)
FETCH_DAYS = 14              # overlapping window; dedupe makes overlap harmless. Was 3
                             # until the 2026-07-21..31 token outage proved a broken
                             # week silently loses activities: a run older than the
                             # window when CI recovers is never fetched again. 14 lets
                             # an outage up to two weeks self-heal on the first green
                             # run (costs ~1 extra lap fetch per new run, nothing more).
LOG_PATH = os.getenv("SYNC_LOG_PATH", "sync_log.txt")

# Failure classes. Each gets a distinct exit code so garmin-sync.yml can print
# ONE redacted line naming the class — the next failure is then diagnosable
# without opening the log. Keep these in sync with the workflow's case block.
EXIT_CONFIG = 10         # a secret/var is missing, or deps aren't installed
EXIT_AUTH_GARMIN = 11    # cached Garmin tokens missing or rejected
EXIT_GARMIN_API = 12     # logged in, but a Garmin API call failed
EXIT_AUTH_SUPABASE = 13  # Supabase sign-in rejected
EXIT_DATA = 14           # per-activity mapping/insert errors
EXIT_TOKEN_WRITEBACK = 15  # the run rotated the Garmin bundle and could not save it
FAIL_CLASSES = {
    EXIT_CONFIG: "CONFIG",
    EXIT_AUTH_GARMIN: "AUTH-GARMIN",
    EXIT_GARMIN_API: "GARMIN-API",
    EXIT_AUTH_SUPABASE: "AUTH-SUPABASE",
    EXIT_DATA: "DATA",
    EXIT_TOKEN_WRITEBACK: "TOKEN-WRITEBACK",
}

# The Garmin token bundle is SHARED, not snapshotted (owner ruling
# 2026-08-19). It lives in one place — the cloud `garmin_tokens` row — and
# every run, CI and local alike, loads it at the start and writes the
# refreshed bundle back at the end. See sync/token_store.py for the full
# story of the two-diverging-copies bug this replaced, and
# _local/migrations/garmin-tokens.sql for the table.
#
# What that means for a red run: there is no secret to re-pack any more. An
# AUTH-GARMIN failure now means the bundle itself is genuinely dead, which
# should be the ~yearly real expiry — one local re-seed fixes it everywhere.
RESEED_HELP = token_store.RESEED_HELP

# Garmin activityType.typeKey -> Hybrid Trainer mapping
RUNNING_TYPES = {
    "running", "street_running", "track_running", "trail_running",
    "treadmill_running", "indoor_running", "virtual_run",
}
ROWING_TYPES = {"rowing", "indoor_rowing"}
CYCLING_TYPES = {
    "cycling", "road_biking", "mountain_biking", "gravel_cycling",
    "virtual_ride", "indoor_cycling", "cyclocross", "track_cycling",
}


def log(msg):
    """Print AND append to the debug log the workflow uploads on failure.
    Keep entries redacted: dates, activity types, decisions — never activity
    names, HR values, or anything from the secrets."""
    line = str(msg)
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


class SyncFailure(Exception):
    """Raised by fail() instead of exiting, so the pieces of this module can
    be called as an isolated stage from an orchestrator (sync/nightly_cycle.py)
    that must not let one failure kill the whole process. Carries the same
    FAIL_CLASSES code fail() always logged, so main() below can reproduce
    today's exact sys.exit(code) for standalone `python sync/garmin_sync.py`
    runs."""
    def __init__(self, msg, code):
        super().__init__(msg)
        self.code = code


def fail(msg, code=EXIT_CONFIG):
    """Log the failure CLASS on its own first line, then the detail, then
    raise SyncFailure(code). The class line is what the workflow echoes as a
    one-line annotation, so keep it short and free of anything sensitive."""
    log(f"FAIL-CLASS: {FAIL_CLASSES.get(code, 'UNKNOWN')}")
    log("FATAL: " + str(msg))
    raise SyncFailure(msg, code)


# ---------------------------------------------------------------------------
# Pure helpers — straight Python ports of the webapp's TCX-import functions
# (index.html: secondsToClock, metersToDisplay, paceFromMetersSeconds,
# classifyRunType, tcxActivityToSession). Keep behavior identical; the webapp
# is the reference implementation.
# ---------------------------------------------------------------------------

def _round_half_up(x):
    """JS Math.round: half rounds away from zero (values here are >= 0)."""
    return int(float(x) + 0.5)


def seconds_to_clock(total_seconds):
    s = max(0, _round_half_up(float(total_seconds or 0)))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h > 0 else f"{m}:{sec:02d}"


def meters_to_display(meters, unit):
    m = float(meters or 0)
    val = m / 1000 if unit == "km" else m / 1609.344
    return f"{val:.2f}"


def pace_from_meters_seconds(meters, seconds, unit):
    m = float(meters or 0)
    s = float(seconds or 0)
    if m <= 0 or s <= 0:
        return ""
    dist_units = m / 1000 if unit == "km" else m / 1609.344
    if dist_units <= 0:
        return ""
    return seconds_to_clock(s / dist_units)


# Same thresholds and priority order as the webapp: long and intervals win
# over tempo because they also run hot.
RUN_LONG_SECONDS = 75 * 60
RUN_LONG_METERS = 16000
INTERVAL_MIN_LAPS = 4
INTERVAL_PACE_RATIO = 1.5
TEMPO_MIN_SECONDS = 12 * 60


def classify_run_type(activity, easy_hr_ceiling=0):
    a = activity or {}
    secs = float(a.get("totalSeconds") or 0)
    meters = float(a.get("distanceMeters") or 0)
    if secs >= RUN_LONG_SECONDS or meters >= RUN_LONG_METERS:
        return "long"
    laps = a.get("laps") or []
    paces = []
    for l in laps:
        ld = float(l.get("distanceMeters") or 0)
        ls = float(l.get("totalSeconds") or 0)
        if ld > 0 and ls > 0:
            paces.append(ls / ld)
    if len(paces) >= INTERVAL_MIN_LAPS:
        mx, mn = max(paces), min(paces)
        if mn > 0 and mx / mn > INTERVAL_PACE_RATIO:
            return "intervals"
    try:
        ceiling = float(easy_hr_ceiling or 0)
    except (TypeError, ValueError):
        ceiling = 0
    if ceiling > 0:
        sec_above = 0.0
        for l in laps:
            if float(l.get("avgHr") or 0) > ceiling:
                sec_above += float(l.get("totalSeconds") or 0)
        if sec_above == 0 and float(a.get("avgHr") or 0) > ceiling:
            sec_above = secs
        if sec_above >= TEMPO_MIN_SECONDS:
            return "tempo"
    return "easy"


GARMIN_TS_RE = re.compile(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})")


def normalize_garmin_source(src):
    """'garmin:2026-07-12T11:03:22.000Z' and 'garmin:2026-07-12 11:03:22'
    both -> 'garmin:2026-07-12T11:03:22' so TCX-imported and auto-synced
    copies of the same activity always match."""
    m = GARMIN_TS_RE.search(src or "")
    return f"garmin:{m.group(1)}T{m.group(2)}" if m else (src or "")


def garmin_import_source(a):
    """Build the import_source in the exact format the TCX importer stores:
    the TCX <Id> is the UTC start time like 2026-07-12T11:03:22.000Z."""
    m = GARMIN_TS_RE.search((a.get("startTimeGMT") or "")[:19])
    if m:
        return f"garmin:{m.group(1)}T{m.group(2)}.000Z"
    return ""


def laps_from_splits(splits):
    """Garmin get_activity_splits payload -> the lap shape classifyRunType
    expects ({totalSeconds, distanceMeters, avgHr})."""
    out = []
    for l in (splits or {}).get("lapDTOs") or []:
        out.append({
            "totalSeconds": float(l.get("duration") or 0),
            "distanceMeters": float(l.get("distance") or 0),
            "avgHr": float(l.get("averageHR") or 0),
        })
    return out


def local_time_parts(start_time_local, duration_secs):
    """Garmin's startTimeLocal ('2026-07-12 07:03:22') is already the
    activity's LOCAL wall-clock time — use it directly, never derive the
    date from a UTC timestamp (the app's rule 12). Returns (date, start,
    end) as YYYY-MM-DD / HH:MM strings; end is '' when duration is 0,
    matching the TCX importer."""
    try:
        d = datetime.strptime((start_time_local or "")[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return "", "", ""
    secs = float(duration_secs or 0)
    end = ""
    if secs > 0:
        end = (d + timedelta(seconds=_round_half_up(secs))).strftime("%H:%M")
    return d.strftime("%Y-%m-%d"), d.strftime("%H:%M"), end


def activity_to_row(a, laps, *, unit, easy_hr_ceiling, default_phase,
                    user_id, import_source):
    """Map one Garmin activity summary (+ optional laps) to a `sessions`
    row exactly as the webapp's sessionToRow writes it: string values in
    display units, empty optionals as NULL, notes as ''. Returns None when
    the activity has no usable local start time."""
    type_key = ((a.get("activityType") or {}).get("typeKey") or "").lower()
    meters = float(a.get("distance") or 0)
    secs = float(a.get("duration") or 0)
    avg_hr = float(a.get("averageHR") or 0)
    calories = float(a.get("calories") or 0)

    d, start_t, end_t = local_time_parts(a.get("startTimeLocal"), secs)
    if not d:
        return None

    dist_str = meters_to_display(meters, unit) if meters > 0 else ""
    time_str = seconds_to_clock(secs) if secs > 0 else ""
    pace_str = pace_from_meters_seconds(meters, secs, unit)
    hr_str = str(_round_half_up(avg_hr)) if avg_hr else ""

    run_data, cond_data = {}, {}
    if type_key in RUNNING_TYPES:
        session_type = "run"
        run_type = classify_run_type(
            {"totalSeconds": secs, "distanceMeters": meters,
             "avgHr": avg_hr, "laps": laps},
            easy_hr_ceiling,
        )
        if run_type == "intervals":
            split_paces = ", ".join(filter(None, (
                pace_from_meters_seconds(l["distanceMeters"], l["totalSeconds"], unit)
                for l in laps
            )))
            run_data = {"runType": "intervals", "splits": split_paces,
                        "totalDistance": dist_str, "totalTime": time_str,
                        "notes": ""}
        elif run_type == "tempo":
            # No reliable WU/work/CD split from summary data — totals + HR,
            # user refines in the app (same tradeoff as the TCX importer).
            run_data = {"runType": "tempo", "distance": dist_str,
                        "time": time_str, "hr": hr_str, "notes": ""}
        else:
            run_data = {"runType": run_type, "distance": dist_str,
                        "time": time_str, "pace": pace_str, "hr": hr_str,
                        "notes": ""}
    elif type_key in ROWING_TYPES:
        session_type = "conditioning"
        split_500 = seconds_to_clock(secs / (meters / 500.0)) if meters > 0 and secs > 0 else ""
        cond_data = {"condType": "erg", "machine": "Row",
                     "distance": f"{_round_half_up(meters)}m" if meters > 0 else "",
                     "time": time_str, "split": split_500,
                     "cal": str(_round_half_up(calories)) if calories else "",
                     "hr": hr_str, "notes": ""}
    else:
        # Cycling and any other cardio -> conditioning "other", same shape
        # the TCX importer produces for non-running sports.
        session_type = "conditioning"
        if type_key in CYCLING_TYPES:
            modality = "Bike"
        else:
            modality = type_key.replace("_", " ").title() if type_key else "Other"
        bits = []
        if dist_str:
            bits.append(dist_str + " " + unit)
        if time_str:
            bits.append(time_str)
        cond_data = {"condType": "other", "modality": modality,
                     "total": " / ".join(bits),
                     "splits": f"Avg HR {hr_str}" if hr_str else "",
                     "notes": ""}

    return {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "date": d,
        "start_time": start_t or None,
        "end_time": end_t or None,
        "end_date": None,
        "bodyweight": None,
        "name": None,
        "phase": default_phase or None,
        "type": session_type,
        "exercises": [],
        "run_data": run_data,
        "cond_data": cond_data,
        "notes": "",
        "import_source": import_source,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Strength (lifts) mapping — a separate path from activity_to_row above.
# Exercises come from get_activity_exercise_sets, not the activity summary.
# Imported sessions are marked review-pending (cond_data.reviewPending)
# rather than trusted silently — see index.html's History badge and
# editHistorySession's clear-on-open.
# ---------------------------------------------------------------------------

GRAMS_PER_LB = 453.59237


def grams_to_lb(grams):
    """Garmin weight is in grams. None or 0 means 'not recorded' (the watch
    has no weight sensor for e.g. a dumbbell lateral raise), not literally
    zero pounds, so both map to ''. Rounds to the nearest 0.5 lb: a real gym
    increment, and it also cleans the few-hundredths-of-a-pound float noise
    Garmin's own internal round-trip introduces (observed directly on a real
    account: 20437g read back as 45.055..lb, not exactly 45)."""
    if grams is None:
        return ''
    g = float(grams)
    if g <= 0:
        return ''
    lb = g / GRAMS_PER_LB
    rounded = round(lb * 2) / 2
    return str(int(rounded)) if rounded == int(rounded) else f"{rounded:.1f}"


def map_garmin_exercise(category, name, notes):
    """(category, name) -> the app's exact exercise name, via the shared
    taxonomy. Exact lookup only, no fuzzy matching (same rule as the push
    direction, garmin_push.py's map_exercise_name). On a miss, falls back to
    a readable name built from Garmin's own name and appends a line to
    `notes` — never silently dropped."""
    hit = GARMIN_EXERCISE_TO_APP_NAME.get((category, name))
    if hit:
        return hit
    fallback = (name or category or 'Unknown exercise').replace('_', ' ').title()
    notes.append(
        f"{fallback}: no taxonomy mapping on file (Garmin category={category!r} "
        f"name={name!r}) — imported under this name. Add it to EXERCISE_TAXONOMY "
        f"in garmin_push.py once you know the right app-side name.")
    return fallback


def strip_pushed_workout_name(activity_name, target_date_str):
    """If this activity's name matches garmin_push.py's own deterministic
    push_workout_name() pattern ('HT: <template> (<date>)'), recover the
    template name for a far more reviewable session name. Returns '' for a
    freeform (non-pushed) strength activity — the caller then leaves the
    session unnamed, same as a hand-logged session with no name."""
    n = activity_name or ''
    suffix = f" ({target_date_str})"
    if n.startswith(PUSH_NAME_PREFIX) and n.endswith(suffix):
        return n[len(PUSH_NAME_PREFIX):-len(suffix)]
    return ''


def map_strength_activity_to_session(a, exercise_sets, *, user_id, default_phase,
                                      import_source):
    """One completed Garmin strength_training activity + its exercise-sets
    payload -> a 'lifts' session row, exactly like activity_to_row does for
    run/conditioning but from a different Garmin endpoint (exercise sets, not
    the activity summary). Returns (row, notes); row is None if there are no
    active sets to import. Never raises on an unmapped exercise or a missing
    weight — those degrade to a fallback value and a `notes` line, matching
    garmin_push.py's 'never silently drop' rule for the push direction.
    Consecutive ACTIVE sets sharing the same (category, name) group into one
    exercise; a non-adjacent repeat of the same exercise becomes a SEPARATE
    exercise entry — same superset handling the Hevy CSV importer already
    uses, not a special case invented here."""
    secs = float(a.get("duration") or 0)
    d, start_t, end_t = local_time_parts(a.get("startTimeLocal"), secs)
    if not d:
        return None, ["No usable local start time on this activity."]

    notes = []
    exercises = []  # list of {"name":..., "key":(cat,name), "sets":[...]}
    current = None
    for s in (exercise_sets.get("exerciseSets") or []):
        if s.get("setType") != "ACTIVE":
            continue
        ex_list = s.get("exercises") or []
        if not ex_list:
            continue
        top = ex_list[0]
        category, g_name = top.get("category") or '', top.get("name") or ''
        key = (category, g_name)
        if current is None or current["key"] != key:
            current = {"name": map_garmin_exercise(category, g_name, notes),
                       "key": key, "sets": []}
            exercises.append(current)
        reps = s.get("repetitionCount")
        current["sets"].append({
            "type": "working",
            "weight": grams_to_lb(s.get("weight")),
            "reps": str(int(reps)) if reps is not None else '',
            "rpe": "", "rir": "",
            "done": True,
        })

    if not exercises:
        notes.append("No active sets in this activity's exercise data — nothing to import.")
        return None, notes

    name = strip_pushed_workout_name(a.get("activityName"), d) or None

    return {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "date": d,
        "start_time": start_t or None,
        "end_time": end_t or None,
        "end_date": None,
        "bodyweight": None,
        "name": name,
        "phase": default_phase or None,
        "type": "lifts",
        "exercises": [{"name": e["name"], "sets": e["sets"], "notes": ""} for e in exercises],
        "run_data": {},
        "cond_data": {"reviewPending": True},
        "notes": "",
        "import_source": import_source,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }, notes


# ---------------------------------------------------------------------------
# Network steps
# ---------------------------------------------------------------------------

def supabase_login():
    """Sign in as the app user with the public anon key, so RLS applies
    exactly as it does in the browser. Never the service role key. This now
    runs FIRST, before Garmin: the Garmin bundle lives in the cloud, so we
    need a signed-in client to fetch it."""
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])
    try:
        # allow_saved_session=False: CI has its secrets and a runner has no
        # saved session to reuse anyway.
        auth = token_store.supabase_sign_in(sb, log=log, allow_saved_session=False)
    except token_store.TokenStoreError as e:
        fail(str(e), EXIT_AUTH_SUPABASE)
    return sb, auth.user.id


def garmin_login():
    """Cached-token login ONLY. There is deliberately no code path here that
    could submit credentials to Garmin. The bundle was written to TOKEN_DIR
    moments ago by token_store.install_bundle(), so a failure here means the
    SHARED bundle itself is dead — not that some copy drifted."""
    try:
        client = Garmin()  # constructed WITHOUT credentials, on purpose
        client.login(TOKEN_DIR)
        log("Garmin: logged in with the shared token bundle.")
        return client
    except Exception as e:
        fail(f"Garmin login failed with the shared cloud bundle "
             f"({type(e).__name__}: {e}) — {token_store.RESEED_LINE}."
             f"{RESEED_HELP}", EXIT_AUTH_GARMIN)


def sync_activities(sb, user_id, client):
    """The sync itself. Auth (Supabase, then the shared Garmin bundle) has
    already happened in main() — this only fetches, maps and inserts."""
    end = date.today()
    start = end - timedelta(days=FETCH_DAYS - 1)
    log(f"Fetching Garmin activities {start} .. {end}")
    try:
        activities = client.get_activities_by_date(start.isoformat(), end.isoformat()) or []
    except Exception as e:
        fail(f"Garmin activity fetch failed: {type(e).__name__}: {e}",
             EXIT_GARMIN_API)
    time.sleep(REQUEST_DELAY_SECONDS)
    log(f"Garmin returned {len(activities)} activities")

    # Units + default phase come from the app's cloud-synced settings so the
    # rows look exactly like ones logged in the app. (easyHrCeiling is
    # localStorage-only by design — that one arrives via EASY_HR_CEILING.)
    settings_row = {}
    try:
        res = sb.table("user_settings").select("distance_unit,default_phase,units") \
            .eq("user_id", user_id).execute()
        if res.data:
            settings_row = res.data[0]
    except Exception as e:
        log(f"warning: could not read user_settings ({e}); defaulting to mi/lb")
    unit = settings_row.get("distance_unit") or "mi"
    default_phase = settings_row.get("default_phase") or ""
    units_setting = settings_row.get("units") or "lb"
    easy_hr_ceiling = os.getenv("EASY_HR_CEILING") or ""

    # One query for every garmin-sourced row ever written (TCX imports AND
    # prior syncs). Hard-fail if it errors: inserting blind risks duplicates.
    try:
        res = sb.table("sessions").select("import_source") \
            .like("import_source", "garmin:%").execute()
        existing = {normalize_garmin_source(r["import_source"])
                    for r in (res.data or []) if r.get("import_source")}
    except Exception as e:
        fail(f"Could not read existing sessions for dedupe: {e}", EXIT_DATA)
    log(f"Cloud already has {len(existing)} garmin-sourced sessions")

    # Owner ruling 2026-08-18: the watch is the source of truth for lifts on
    # watch-guided days — never double-log. Any EXISTING 'lifts' session that
    # date (hand-logged or already synced) blocks a strength import for that
    # date, not just an exact import_source match. Same hard-fail philosophy
    # as the dedupe query above: inserting blind risks the exact duplicate
    # the owner ruled out.
    try:
        res = sb.table("sessions").select("date") \
            .eq("user_id", user_id).eq("type", "lifts").execute()
        lifts_dates = {r["date"] for r in (res.data or []) if r.get("date")}
    except Exception as e:
        fail(f"Could not read existing lifts sessions for the no-double-log "
             f"safety check: {e}", EXIT_DATA)

    inserted, already, skipped_existing_lifts = 0, 0, 0
    errors = []
    new_lifts = []  # {date, name} for each NEW lifts session inserted this
                     # run — name is the recovered template name (or None
                     # for an unrecognized/hand-done activity), consumed by
                     # sync/nightly_cycle.py's advance stage.
    for a in activities:
        type_key = ((a.get("activityType") or {}).get("typeKey") or "").lower()
        label = f"{(a.get('startTimeLocal') or '?')[:10]} {type_key or '?'}"

        src = garmin_import_source(a)
        if not src:
            log(f"ERROR: no UTC start timestamp, no stable dedupe key: {label}")
            errors.append(label)
            continue
        if normalize_garmin_source(src) in existing:
            log(f"skip (already in cloud): {label}")
            already += 1
            continue

        if type_key == "strength_training":
            if units_setting != "lb":
                log(f"ERROR: account weight unit is {units_setting!r}, not "
                    f"'lb' — strength import only has a verified gram->lb "
                    f"conversion (same precedent as garmin_push.py's weight "
                    f"push). Not guessing kg: {label}")
                errors.append(label)
                continue
            check_date, _, _ = local_time_parts(a.get("startTimeLocal"), a.get("duration"))
            if check_date and check_date in lifts_dates:
                log(f"skip (a 'lifts' session already exists for {check_date} "
                    f"— not double-logging over it): {label}")
                skipped_existing_lifts += 1
                continue
            try:
                sets_payload = client.get_activity_exercise_sets(a["activityId"])
            except Exception as e:
                log(f"ERROR: exercise-sets fetch failed for {label}: {e}")
                errors.append(label)
                continue
            time.sleep(REQUEST_DELAY_SECONDS)
            row, notes = map_strength_activity_to_session(
                a, sets_payload, user_id=user_id, default_phase=default_phase,
                import_source=src)
            if row is None:
                log(f"ERROR: unmappable strength activity: {label}"
                    + (f" ({notes[0]})" if notes else ""))
                errors.append(label)
                continue
            for n in notes:
                log(f"  note: {n}")
            try:
                sb.table("sessions").insert(row).execute()
                existing.add(normalize_garmin_source(src))
                lifts_dates.add(row["date"])
                inserted += 1
                new_lifts.append({"date": row["date"], "name": row["name"]})
                log(f"inserted: {label} -> lifts ({len(row['exercises'])} "
                    f"exercise(s), review-pending)")
            except Exception as e:
                log(f"ERROR: insert failed for {label}: {e}")
                errors.append(label)
            continue

        # Laps are only needed for the run classifier (intervals contrast,
        # tempo time-above-ceiling) — one extra call per NEW run only.
        laps = []
        if type_key in RUNNING_TYPES and a.get("activityId"):
            try:
                laps = laps_from_splits(client.get_activity_splits(a["activityId"]))
            except Exception as e:
                log(f"warning: lap fetch failed for {label} ({e}); "
                    f"classifying without laps")
            time.sleep(REQUEST_DELAY_SECONDS)

        row = activity_to_row(
            a, laps, unit=unit, easy_hr_ceiling=easy_hr_ceiling,
            default_phase=default_phase, user_id=user_id, import_source=src)
        if row is None:
            log(f"ERROR: unmappable (no local start time): {label}")
            errors.append(label)
            continue

        try:
            sb.table("sessions").insert(row).execute()
            existing.add(normalize_garmin_source(src))
            inserted += 1
            detail = row["run_data"].get("runType") if row["type"] == "run" \
                else row["cond_data"].get("condType")
            log(f"inserted: {label} -> {row['type']}/{detail}")
        except Exception as e:
            log(f"ERROR: insert failed for {label}: {e}")
            errors.append(label)

    log(f"Done. inserted={inserted} already_synced={already} "
        f"skipped_existing_lifts={skipped_existing_lifts} errors={len(errors)}")
    # Does NOT fail()/raise here even when errors is non-empty: a partial
    # success (some activities inserted fine, an unrelated one didn't map)
    # must still be usable by a caller that needs whatever DID succeed —
    # sync/nightly_cycle.py's advance stage needs new_lifts regardless of
    # whether an unrelated activity in the same batch errored. The decision
    # of whether a non-empty errors list should be a hard failure belongs to
    # the caller: _run() below still fails loud for the standalone CLI
    # (unchanged behavior), nightly_cycle.py's stage_import reports its own
    # STAGE-IMPORT: FAIL while still handing the partial results onward.

    # new_lifts is sorted oldest-first before returning: get_activities_by_date
    # returns newest-first (confirmed against the installed garminconnect
    # source — no sortorder is passed, and only that call auto-paginates;
    # order is not otherwise guaranteed), and a multi-day catch-up must be
    # walked in the order it actually happened at the gym.
    return {
        "inserted": inserted, "already": already,
        "skipped_existing_lifts": skipped_existing_lifts, "errors": errors,
        "new_lifts": sorted(new_lifts, key=lambda x: x["date"]),
    }


def main():
    # Thin wrapper: _run() raises SyncFailure on any fail() call (needed so
    # sync/nightly_cycle.py can import and call the pieces below as an
    # isolated stage without the process exiting on it). This converts that
    # back to the exact sys.exit(code) standalone `python sync/garmin_sync.py`
    # always did.
    try:
        _run()
    except SyncFailure as e:
        sys.exit(e.code)


def _run():
    if Garmin is None or create_client is None:
        fail("Missing Python deps. Run: pip install -r sync/requirements.txt",
             EXIT_CONFIG)
    for var in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "HT_EMAIL", "HT_PASSWORD"):
        if not os.getenv(var):
            fail(f"Missing required env var {var} (set it as a GitHub Actions "
                 f"secret — see sync/SETUP.md).", EXIT_CONFIG)

    # Order matters now: Supabase first, because the Garmin bundle lives in
    # the cloud. (Before 2026-08-19 Garmin came first and the bundle came
    # from the GARMIN_TOKENS secret — see token_store.py for why that had to
    # go.)
    sb, user_id = supabase_login()
    try:
        state = token_store.install_bundle(sb, user_id, log=log)
    except token_store.TokenStoreError as e:
        fail(str(e), EXIT_AUTH_GARMIN)

    actor = "ci" if os.getenv("GITHUB_ACTIONS") == "true" else "local"
    result = None
    try:
        result = sync_activities(sb, user_id, client=garmin_login())
    finally:
        # finally, not just the happy path: garth can rotate the bundle on the
        # very first call, so a run that dies halfway may still owe the shared
        # row a newer bundle. A raised SyncFailure still runs this — it
        # unwinds through finally exactly like the old sys.exit() did.
        wrote, rotated = token_store.persist_bundle(
            sb, user_id, state, actor=actor, log=log)

    # sync_activities() no longer fails loud on a non-empty errors list
    # itself (sync/nightly_cycle.py's import stage needs the partial result
    # even when some activities errored) — so the standalone CLI's own
    # "fail loud on any mapping/insert error" behavior is preserved here.
    if result and result["errors"]:
        fail(f"{len(result['errors'])} activities failed to map or insert.",
             EXIT_DATA)

    if not wrote and rotated:
        # The sync worked, but a rotated bundle never reached the cloud — the
        # next run would meet a dead token. Loud on purpose: this is exactly
        # the silent-loss class of bug the shared bundle exists to end.
        fail("The sync completed, but the rotated Garmin bundle could not be "
             "written back to the cloud (see the warning above). Re-run the "
             "workflow; if it keeps failing, re-seed with "
             f"{token_store.RESEED_LINE}.", EXIT_TOKEN_WRITEBACK)


if __name__ == "__main__":
    main()
