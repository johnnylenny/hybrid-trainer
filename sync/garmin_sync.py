#!/usr/bin/env python3
"""
garmin_sync.py — daily Garmin Connect -> Hybrid Trainer cloud sync.

Runs in GitHub Actions (see .github/workflows/garmin-sync.yml). Fetches the
last 3 days of Garmin activities, maps each one to a Hybrid Trainer session
row (same shapes the webapp's TCX importer produces), and inserts the new
ones into the Supabase `sessions` table, signed in as the app user so RLS
applies normally.

HARD RULE — tokens only, never a credential login:
  Garmin aggressively rate-limits password logins (429s, multi-day account
  lockouts). This script contains NO credential-login code path at all. It
  loads pre-seeded cached tokens from ~/.garminconnect and, if they are
  missing or expired, fails fast with re-seed instructions. Seeding happens
  locally, once, via sync/seed_tokens.py — see sync/SETUP.md.

Dedupe: every inserted row carries import_source "garmin:<UTC ISO>", the
same format the webapp's TCX importer writes, so a run imported manually
from a .tcx file and the same run arriving via this sync collapse into one.
The skip-check normalizes both sides to seconds precision so formatting
differences (milliseconds, Z suffix) can't cause a duplicate.

Env vars (set as GitHub secrets / vars):
  SUPABASE_URL, SUPABASE_ANON_KEY  — the app's public Supabase config
  HT_EMAIL, HT_PASSWORD            — the app user's login (RLS stays intact)
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

TOKEN_DIR = os.path.expanduser(os.getenv("GARMIN_TOKEN_DIR", "~/.garminconnect"))
REQUEST_DELAY_SECONDS = 0.5  # pause between Garmin API calls (be polite)
FETCH_DAYS = 3               # small overlapping window; dedupe makes overlap harmless
LOG_PATH = os.getenv("SYNC_LOG_PATH", "sync_log.txt")

RESEED_HELP = """
How to fix (one-time, on your own machine — NEVER add Garmin credentials to CI):
  1. rm -rf ~/.garminconnect
  2. python3 sync/seed_tokens.py          # logs in once, prompts for MFA
  3. COPYFILE_DISABLE=1 tar czf - -C "$HOME" .garminconnect | base64 | pbcopy
  4. Paste the clipboard into the GARMIN_TOKENS secret:
     GitHub repo -> Settings -> Secrets and variables -> Actions
Tokens last roughly a year. This script never attempts a password login —
Garmin rate-limits those hard (429s, multi-day lockouts)."""

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
SKIP_TYPES = {"strength_training"}  # lifts are logged in the app; no duplicates


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


def fail(msg):
    log("FATAL: " + str(msg))
    sys.exit(1)


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
# Network steps
# ---------------------------------------------------------------------------

def garmin_login():
    """Cached-token login ONLY. There is deliberately no code path here that
    could submit credentials to Garmin."""
    if not os.path.isdir(TOKEN_DIR) or not os.listdir(TOKEN_DIR):
        fail(f"No Garmin tokens found at {TOKEN_DIR}. The GARMIN_TOKENS "
             f"secret is missing, empty, or didn't decode.{RESEED_HELP}")
    try:
        client = Garmin()  # constructed WITHOUT credentials, on purpose
        client.login(TOKEN_DIR)
        log("Garmin: logged in with cached tokens.")
        return client
    except Exception as e:
        fail(f"Garmin token login failed — tokens are likely expired or "
             f"corrupt ({type(e).__name__}: {e}).{RESEED_HELP}")


def main():
    if Garmin is None or create_client is None:
        fail("Missing Python deps. Run: pip install -r sync/requirements.txt")
    for var in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "HT_EMAIL", "HT_PASSWORD"):
        if not os.getenv(var):
            fail(f"Missing required env var {var} (set it as a GitHub Actions "
                 f"secret — see sync/SETUP.md).")

    client = garmin_login()

    end = date.today()
    start = end - timedelta(days=FETCH_DAYS - 1)
    log(f"Fetching Garmin activities {start} .. {end}")
    try:
        activities = client.get_activities_by_date(start.isoformat(), end.isoformat()) or []
    except Exception as e:
        fail(f"Garmin activity fetch failed: {type(e).__name__}: {e}")
    time.sleep(REQUEST_DELAY_SECONDS)
    log(f"Garmin returned {len(activities)} activities")

    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])
    try:
        auth = sb.auth.sign_in_with_password({
            "email": os.environ["HT_EMAIL"],
            "password": os.environ["HT_PASSWORD"],
        })
    except Exception as e:
        fail(f"Supabase sign-in failed: {type(e).__name__}: {e}")
    user_id = auth.user.id
    log("Supabase: signed in.")

    # Units + default phase come from the app's cloud-synced settings so the
    # rows look exactly like ones logged in the app. (easyHrCeiling is
    # localStorage-only by design — that one arrives via EASY_HR_CEILING.)
    settings_row = {}
    try:
        res = sb.table("user_settings").select("distance_unit,default_phase") \
            .eq("user_id", user_id).execute()
        if res.data:
            settings_row = res.data[0]
    except Exception as e:
        log(f"warning: could not read user_settings ({e}); defaulting to mi")
    unit = settings_row.get("distance_unit") or "mi"
    default_phase = settings_row.get("default_phase") or ""
    easy_hr_ceiling = os.getenv("EASY_HR_CEILING") or ""

    # One query for every garmin-sourced row ever written (TCX imports AND
    # prior syncs). Hard-fail if it errors: inserting blind risks duplicates.
    try:
        res = sb.table("sessions").select("import_source") \
            .like("import_source", "garmin:%").execute()
        existing = {normalize_garmin_source(r["import_source"])
                    for r in (res.data or []) if r.get("import_source")}
    except Exception as e:
        fail(f"Could not read existing sessions for dedupe: {e}")
    log(f"Cloud already has {len(existing)} garmin-sourced sessions")

    inserted, already, skipped_strength = 0, 0, 0
    errors = []
    for a in activities:
        type_key = ((a.get("activityType") or {}).get("typeKey") or "").lower()
        label = f"{(a.get('startTimeLocal') or '?')[:10]} {type_key or '?'}"

        if type_key in SKIP_TYPES:
            log(f"skip (strength — logged in the app): {label}")
            skipped_strength += 1
            continue
        src = garmin_import_source(a)
        if not src:
            log(f"ERROR: no UTC start timestamp, no stable dedupe key: {label}")
            errors.append(label)
            continue
        if normalize_garmin_source(src) in existing:
            log(f"skip (already in cloud): {label}")
            already += 1
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
        f"skipped_strength={skipped_strength} errors={len(errors)}")
    if errors:
        # Non-zero exit -> the workflow goes red and uploads the log.
        # The next scheduled run retries the failed ones (dedupe skips the
        # rest), so a transient failure self-heals.
        sys.exit(1)


if __name__ == "__main__":
    main()
