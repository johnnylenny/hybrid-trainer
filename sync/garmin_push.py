#!/usr/bin/env python3
"""
garmin_push.py — Hybrid Trainer -> Garmin Connect outbound workout push.

Companion to garmin_sync.py (which reads FROM Garmin). This one writes TO
Garmin Connect: create a structured strength workout so the FR965 can guide
a lift at the gym. Full design and phase gates: outputs/Garmin_Outbound_Spec.md.

HARD RULE — tokens only, never a credential login (same as garmin_sync.py):
  Garmin aggressively rate-limits password logins (429s, multi-day account
  lockouts). This script contains NO credential-login code path at all. It
  loads pre-seeded cached tokens from ~/.garminconnect and, if they are
  missing or expired, fails fast with re-seed instructions. Seeding happens
  locally, once, via sync/seed_tokens.py — see sync/SETUP.md.

Trigger: local only, manually. Never scheduled — a cron that writes to
Garmin unattended is risk without benefit (spec 1.3 / fence 5). Phase 2's
workflow_dispatch button is a deliberate follow-up release, gated on a week
of real local use (spec 1.6) — not built here.

Two modes:

  --self-test                        Phase 1 write-path proof (unchanged).
  --push --template NAME --date D    Phase 2: map a real template to a
                                      workout and push it for real.

Phase 1: uploads one hardcoded 2-exercise workout — cloned from the Phase 0
reference payload (sync/testdata/reference_workout.json, Johnny's own
hand-built "Chest Dat" workout, fetched read-only via get_workout_by_id) —
verifies it round-tripped correctly (appears in get_workouts, exercise names
intact), then deletes it. One create, one delete, 0.5s delays between Garmin
calls. The delete only ever targets the workout ID *this run's own*
upload_workout call returned — never a hardcoded or externally-supplied ID —
so a bug here cannot reach any of Johnny's real workouts.

Phase 0 finding this file relies on (corrects spec 1.4's assumption): the
reference payload's weightUnit is NOT hardcoded to kilogram. Johnny's
hand-built workout round-tripped with weightUnit {"unitKey": "pound",
"unitId": 9, "factor": 453.59237} — Garmin accepts a full unit object, and
pound values round-trip (with ~0.001-0.002 lb float noise from an internal
kg round-trip — cosmetic, matches the 0.5kg display-rounding quirk in spec
1.2). Phase 2 below only has a VERIFIED weightUnit object for pound; a
'kg'-unit account fails loud instead of guessing an unverified kilogram
object (see WEIGHT_UNIT_LB and its one call site below).

Phase 2 (the mapper): reads one named 'lifts' template plus Supabase session
history — the SAME two sources and the SAME auth (anon key +
HT_EMAIL/HT_PASSWORD, RLS intact) garmin_sync.py already uses, just read
instead of written — mirrors the app's own prefillExercisesFromLast() to
fill each set's weight/reps from the most recent matching session, maps
exercise names through a small hand-built table (EXERCISE_TAXONOMY below;
no fuzzy matching — spec 1.4), and pushes a flat one-step-per-set workout
(no rest steps, no repeat groups — the self-test's flat shape, proven in
Phase 1, kept deliberately simple rather than replicating Garmin Connect's
messier hand-built nesting). Every set that can't map cleanly (no prior
history, an unparseable weight/rep string, a myo-rep/drop set Garmin has no
structure for, an exercise name with no taxonomy entry) still uploads — as a
plain step with that one target omitted — and is named in a printed report;
nothing is ever silently dropped (spec 1.4/1.7). Re-running a push for the
same template+date deletes its own prior push first, then recreates (spec
1.2's stale-on-watch bug means an update-in-place can't be trusted) —
matched ONLY by this script's own deterministic workout name, never fuzzily
or by some other heuristic, so a re-push can never reach a workout it didn't
itself create this way.

FENCE: index.html never changes for this file, in any phase, and never
learns this script exists.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

try:
    from garminconnect import Garmin
except ImportError:
    Garmin = None
try:
    from supabase import create_client
except ImportError:
    create_client = None

TOKEN_DIR = os.path.expanduser(os.getenv("GARMIN_TOKEN_DIR", "~/.garminconnect"))
REQUEST_DELAY_SECONDS = 0.5  # pause between Garmin API calls (be polite; spec fence 5)

RESEED_HELP = """
How to fix (one-time, on your own machine — NEVER add Garmin credentials to CI):
  1. rm -rf ~/.garminconnect
  2. python3 sync/seed_tokens.py          # logs in once, prompts for MFA
Tokens last roughly a year. This script never attempts a password login —
Garmin rate-limits those hard (429s, multi-day lockouts)."""

SELF_TEST_NAME = "HT self-test (safe to delete)"


def log(msg):
    print(str(msg), flush=True)


def fail(msg):
    log("FATAL: " + str(msg))
    sys.exit(1)


def garmin_login():
    """Cached-token login ONLY — same pattern as garmin_sync.py's
    garmin_login(), duplicated here (not imported) so each sync/ CLI script
    stays a standalone entry point, same as garmin_sync.py + seed_tokens.py
    already are."""
    if not os.path.isdir(TOKEN_DIR) or not os.listdir(TOKEN_DIR):
        fail(f"No Garmin tokens found at {TOKEN_DIR}.{RESEED_HELP}")
    try:
        client = Garmin()  # constructed WITHOUT credentials, on purpose
        client.login(TOKEN_DIR)
        log("Garmin: logged in with cached tokens.")
        return client
    except Exception as e:
        fail(f"Garmin token login failed — tokens are likely expired or "
             f"corrupt ({type(e).__name__}: {e}).{RESEED_HELP}")


def self_test_workout_json():
    """Two exercises, both taxonomy names copied verbatim from Johnny's own
    hand-built reference workout (sync/testdata/reference_workout.json) so
    Phase 1 tests the write path itself, not a guessed taxonomy name."""

    def step(order, category, exercise_name, reps, weight_lb):
        return {
            "type": "ExecutableStepDTO",
            "stepOrder": order,
            "stepType": {"stepTypeId": 3, "stepTypeKey": "interval"},
            "category": category,
            "exerciseName": exercise_name,
            "endCondition": {"conditionTypeId": 10, "conditionTypeKey": "reps"},
            "endConditionValue": float(reps),
            "targetType": {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target"},
            "weightValue": float(weight_lb),
            "weightUnit": {"unitId": 9, "unitKey": "pound"},
        }

    return {
        "workoutName": SELF_TEST_NAME,
        "sportType": {"sportTypeId": 5, "sportTypeKey": "strength_training"},
        "workoutSegments": [{
            "segmentOrder": 1,
            "sportType": {"sportTypeId": 5, "sportTypeKey": "strength_training"},
            "workoutSteps": [
                step(1, "BENCH_PRESS", "BARBELL_BENCH_PRESS", 8, 135),
                step(2, "TRICEPS_EXTENSION", "TRICEPS_PRESSDOWN", 12, 60),
            ],
        }],
    }


def _exercise_names(workout):
    """Flatten every step's exerciseName out of a workout dict (one level of
    RepeatGroupDTO nesting handled, though the self-test payload doesn't use
    repeats — Phase 0's reference workout does, so this helper is written to
    survive reading either shape back)."""
    names = []
    for seg in workout.get("workoutSegments") or []:
        for step in seg.get("workoutSteps") or []:
            if step.get("type") == "RepeatGroupDTO":
                for inner in step.get("workoutSteps") or []:
                    if inner.get("exerciseName"):
                        names.append(inner["exerciseName"])
            elif step.get("exerciseName"):
                names.append(step["exerciseName"])
    return names


def self_test(client):
    """Phase 1 gate (spec 1.6): script exits 0; the workout appeared with
    its exercise names intact and was deleted; the cached tokens authorized
    the POST. Any failure is collected into `problems`, cleanup is attempted
    regardless, and exactly one fail() call reports everything — no retries
    anywhere in this function."""
    expected_names = sorted(["BARBELL_BENCH_PRESS", "TRICEPS_PRESSDOWN"])
    log(f"Self-test: uploading {SELF_TEST_NAME!r} ({len(expected_names)} exercises)...")

    try:
        created = client.upload_workout(self_test_workout_json())
    except Exception as e:
        fail(
            f"upload_workout failed ({type(e).__name__}: {e}). Nothing was "
            f"created, nothing to clean up. If this looks like an auth/"
            f"permission error, the cached tokens likely don't authorize "
            f"workout-service writes — STOP and reassess against spec 1.7's "
            f"risk table (outputs/Garmin_Outbound_Spec.md) before re-seeding. "
            f"Not retrying."
        )

    workout_id = created.get("workoutId") if isinstance(created, dict) else None
    if not workout_id:
        fail(
            f"upload_workout returned no workoutId — response: {created!r}. "
            f"Treating as a rejected/no-op write per spec 1.7. Nothing "
            f"confirmed created, so nothing to clean up. Not retrying."
        )
    log(f"Created workout id={workout_id}.")
    time.sleep(REQUEST_DELAY_SECONDS)

    problems = []

    try:
        listed = client.get_workouts(start=0, limit=100)
    except Exception as e:
        problems.append(f"get_workouts failed after create ({type(e).__name__}: {e})")
        listed = []
    time.sleep(REQUEST_DELAY_SECONDS)

    match = next((w for w in listed if w.get("workoutId") == workout_id), None)
    if match is None:
        problems.append(f"uploaded workout id={workout_id} not found in get_workouts()")
    else:
        log(f"Found id={workout_id} in get_workouts() (name={match.get('workoutName')!r}).")

    try:
        detail = client.get_workout_by_id(workout_id)
    except Exception as e:
        problems.append(f"get_workout_by_id failed ({type(e).__name__}: {e})")
        detail = {}
    time.sleep(REQUEST_DELAY_SECONDS)

    actual_names = sorted(_exercise_names(detail))
    if actual_names != expected_names:
        problems.append(
            f"exercise names did not round-trip intact: expected {expected_names}, "
            f"got {actual_names} (this is the known 'exerciseName silently "
            f"dropped' failure mode from spec 1.2/1.7)"
        )
    else:
        log(f"Exercise names round-tripped intact: {actual_names}.")

    # Cleanup: attempt regardless of the checks above ("self-cleaning where
    # possible" — spec 1.7's fail-loud contract). `workout_id` only ever
    # comes from THIS run's own upload_workout() response above, never a
    # hardcoded or externally-supplied value.
    deleted = False
    try:
        client.delete_workout(workout_id)
        time.sleep(REQUEST_DELAY_SECONDS)
        still_listed = client.get_workouts(start=0, limit=100)
        deleted = not any(w.get("workoutId") == workout_id for w in still_listed)
        if not deleted:
            problems.append(f"delete_workout did not raise, but id={workout_id} "
                             f"still appears in get_workouts() after deleting")
    except Exception as e:
        problems.append(
            f"delete_workout failed ({type(e).__name__}: {e}) — id={workout_id} "
            f"may still exist. DELETE IT MANUALLY in Garmin Connect "
            f"(Training > Workouts > {SELF_TEST_NAME!r})."
        )

    if problems:
        fail(
            "Self-test FAILED. Per spec 1.6/1.7: stop, do not retry, reassess "
            "against the risk table.\n  - " + "\n  - ".join(problems) +
            (f"\n  Cleanup: workout id={workout_id} WAS deleted."
             if deleted else
             f"\n  Cleanup: workout id={workout_id} may still exist — check Garmin Connect.")
        )

    log(f"Self-test PASSED: created id={workout_id}, verified exercise names "
        f"intact, deleted, and confirmed gone. Cached tokens authorize "
        f"workout-service writes (closes the token-scope UNKNOWN, spec 1.3).")


# ---------------------------------------------------------------------------
# PHASE 2 — the mapper: a real template + latest history -> a real workout.
# ---------------------------------------------------------------------------

class MapperError(Exception):
    """A hard, whole-push failure in mapping a template (spec 1.4's "exits
    non-zero only for hard failures" line). Per-set issues — an unparseable
    value, an unmapped name, a myo/drop set — are NOT this: those degrade to
    a plain step plus a report line, and the push still proceeds."""


WEIGHT_UNIT_LB = {"unitId": 9, "unitKey": "pound"}
# No verified Garmin kilogram weightUnit object exists — Phase 0 only
# round-tripped pound (Johnny's real account unit, sync/testdata/
# reference_workout.json). push() below refuses to guess one for a
# 'kg'-unit account rather than risk a silently wrong weight on the watch
# (spec 1.4/1.7's "wrong guidance is worse than none").

PUSH_NAME_PREFIX = "HT: "


def push_workout_name(template_name, target_date):
    """Deterministic per (template, date) name. This is the ONLY thing a
    re-push matches against to find and delete its own prior copy (spec
    1.2/1.6) — never a fuzzy match, never anything Johnny named by hand."""
    return f"{PUSH_NAME_PREFIX}{template_name} ({target_date})"


# Johnny's real exercise names (his saved templates' exercises[].name),
# hand-mapped once to Garmin's public taxonomy
# (connect.garmin.com/web-data/exercises/Exercises.json, fetched 2026-07-20)
# per spec 1.4 — NO fuzzy matching. Key is name.strip().lower(); value is
# (category, exerciseName), both taken verbatim from the taxonomy file (the
# same two fields the reference payload carries,
# sync/testdata/reference_workout.json). An exercise not in this table
# uploads as a generic step (reps target only, no name/animation on the
# watch) and gets a report line — add a row by hand once you know the right
# taxonomy name; don't guess a close-sounding one in here.
EXERCISE_TAXONOMY = {
    "pull-ups": ("PULL_UP", "PULL_UP"),
    "bent-over barbell row": ("ROW", "BENT_OVER_ROW_WITH_BARBELL"),
    "1-arm cable row": ("ROW", "SINGLE_ARM_CABLE_ROW"),
    "dumbbell curl": ("CURL", "DUMBBELL_BICEPS_CURL"),
    "face-pull (rings)": ("ROW", "FACE_PULL"),
    "horizontal cable row": ("ROW", "SEATED_CABLE_ROW"),
    "barbell bench press": ("BENCH_PRESS", "BARBELL_BENCH_PRESS"),
    "triceps cable pulley": ("TRICEPS_EXTENSION", "TRICEPS_PRESSDOWN"),
    "dumbbell lateral shoulder raise": ("LATERAL_RAISE", "DUMBBELL_LATERAL_RAISE"),
    "barbell squat": ("SQUAT", "BARBELL_BACK_SQUAT"),
    # "Wedge Squat" (LEGS template) deliberately left UNMAPPED — no taxonomy
    # equivalent for a slant-board squat variant. A real, live example of
    # the unmapped path (it's also a myo-rep set, so it exercises both).
}

GARMIN_STEP_TYPE_WARMUP = {"stepTypeId": 1, "stepTypeKey": "warmup"}
GARMIN_STEP_TYPE_WORKING = {"stepTypeId": 3, "stepTypeKey": "interval"}
GARMIN_END_COND_REPS = {"conditionTypeId": 10, "conditionTypeKey": "reps"}
GARMIN_END_COND_MANUAL = {"conditionTypeId": 1, "conditionTypeKey": "lap.button"}
GARMIN_NO_TARGET = {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target"}
MAX_WORKOUT_STEPS = 50  # Garmin's documented builder/API cap (spec 1.2)


def parse_number(raw):
    """Parse an app value string to a float at the payload boundary — the
    Python-side mirror of the app's sanctioned "parse at the moment of
    computation, never in storage" rule (spec 1.4/fence 3); app data itself
    is never touched. Returns None for blank, multi-value, or non-numeric
    strings ("", "115/110", "8-10", "AMRAP") rather than guessing at them."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def sort_sessions_like_app(sessions):
    """Newest-first: date desc, then start_time desc (blank sorts last) —
    the exact comparator index.html uses to keep state.history ordered, so
    find_last_exercise_data's "first match wins" mirrors the JS correctly."""
    return sorted(sessions, key=lambda s: (s.get("date") or "", s.get("start_time") or ""),
                  reverse=True)


def find_last_exercise_data(history, exercise_name):
    """Python mirror of index.html's findLastExerciseData: the first (i.e.
    most recent, given newest-first `history`) 'lifts' session with an
    exercise whose name matches case-insensitively. No trimming — matches
    the JS exactly, which is why EXERCISE_TAXONOMY keys are pre-stripped
    instead (a template exercise name is trusted as typed)."""
    if not exercise_name:
        return None
    name_lower = exercise_name.lower()
    for session in history:
        if session.get("type") != "lifts":
            continue
        for ex in session.get("exercises") or []:
            if (ex.get("name") or "").lower() == name_lower:
                return ex
    return None


def prefill_exercise_sets(template_exercise, history):
    """Python mirror of index.html's prefillExercisesFromLast: fill each of
    the template's skeleton sets ({'type': ...}, no weight/reps — lifts
    templates never store numbers, SCHEMA.md) from the SAME-INDEX set in the
    most recent matching history exercise, and ONLY when that set's type
    also matches at that index (positional, not "closest working set" —
    exactly what the app does). Returns (filled_sets, had_any_history_match)."""
    last = find_last_exercise_data(history, template_exercise.get("name") or "")
    last_sets = (last or {}).get("sets") or []
    filled = []
    for si, tset in enumerate(template_exercise.get("sets") or []):
        set_type = tset.get("type")
        h = last_sets[si] if si < len(last_sets) else None
        matched = bool(h and h.get("type") == set_type)
        merged = {"type": set_type, "_matched": matched}
        if matched:
            if set_type in ("warmup", "working"):
                merged["weight"] = h.get("weight") or ""
                merged["reps"] = h.get("reps") or ""
            elif set_type in ("myorep", "drop"):
                merged["sequence"] = h.get("sequence") or ""
        filled.append(merged)
    return filled, (last is not None)


def map_exercise_name(name, report):
    """Exact (normalized) lookup only — no fuzzy matching (spec 1.4). Logs
    an unmapped name to `report` and returns (None, None) so the caller
    still emits a usable (if generic) step."""
    hit = EXERCISE_TAXONOMY.get((name or "").strip().lower())
    if hit:
        return hit
    if name:
        report.append(
            f"{name}: no taxonomy mapping on file — uploaded as a generic "
            f"strength step (reps target only, no exercise name or "
            f"animation on the watch). Add it to EXERCISE_TAXONOMY in this "
            f"file once you know the right Garmin name (see "
            f"connect.garmin.com/web-data/exercises/Exercises.json).")
    return (None, None)


def build_set_step(order, label, category, garmin_name, set_type, weight_raw, reps_raw, report):
    """One warmup/working set -> one flat ExecutableStepDTO. Reps and weight
    are parsed and reported independently (spec 1.4's per-value rule): a set
    can have a real weight target and no reps target, or vice versa. No reps
    -> the step falls back to a manual/lap.button end condition (press the
    lap button to end it) instead of inventing a fake number."""
    reps = parse_number(reps_raw)
    if reps_raw and reps is None:
        report.append(f"{label}: reps target skipped, {reps_raw!r} is not a "
                       f"single number — set becomes manual (press the lap "
                       f"button to end it).")

    step = {
        "type": "ExecutableStepDTO",
        "stepOrder": order,
        "stepType": dict(GARMIN_STEP_TYPE_WARMUP if set_type == "warmup" else GARMIN_STEP_TYPE_WORKING),
        "category": category,
        "exerciseName": garmin_name,
        "endCondition": dict(GARMIN_END_COND_REPS if reps is not None else GARMIN_END_COND_MANUAL),
        "targetType": dict(GARMIN_NO_TARGET),
    }
    if reps is not None:
        step["endConditionValue"] = reps

    weight = parse_number(weight_raw)
    if weight_raw and weight is None:
        report.append(f"{label}: weight target skipped, {weight_raw!r} is not a single number.")
    if weight is not None:
        step["weightValue"] = weight
        step["weightUnit"] = dict(WEIGHT_UNIT_LB)
    return step


def build_myo_drop_step(order, label, category, garmin_name, set_type, sequence_raw, report):
    """Myo-rep/drop sets have no Garmin equivalent (spec 1.4) — always a
    plain manual-advance step, reps/weight always omitted, always reported
    (this is a permanent modeling gap, not a data-quality issue)."""
    report.append(
        f"{label}: {set_type} set has no Garmin structure to map to — "
        f"uploaded as a plain manual-advance step (no reps/weight target). "
        f"Sequence was {sequence_raw!r} — read it from your own notes at the gym.")
    return {
        "type": "ExecutableStepDTO",
        "stepOrder": order,
        "stepType": dict(GARMIN_STEP_TYPE_WORKING),
        "category": category,
        "exerciseName": garmin_name,
        "endCondition": dict(GARMIN_END_COND_MANUAL),
        "targetType": dict(GARMIN_NO_TARGET),
    }


def map_template_to_workout(template, history, target_date):
    """The mapper (spec 1.4/1.6): a lifts template + session history -> a
    flat-step Garmin strength workout dict ready for push_workout(). Caller
    (push(), below) must already have confirmed the account's weight unit is
    'lb' — every weight target here is tagged WEIGHT_UNIT_LB unconditionally.
    Returns (workout, report) — report is a list of str, one per set/
    exercise that didn't map cleanly; always non-fatal, never silently
    dropped (spec 1.4/1.7). Raises MapperError only for a hard, whole-push
    failure (nothing to push, or over Garmin's step limit)."""
    # Defensive, not redundant: find_last_exercise_data's correctness
    # depends entirely on newest-first order. fetch_lifts_history() already
    # sorts, but this function must not silently produce a wrong "latest"
    # set just because some future caller passes history in whatever order
    # its source returned it.
    history = sort_sessions_like_app(history)
    report = []
    steps = []
    order = 0
    for ex in template.get("exercises") or []:
        name = ex.get("name") or ""
        category, garmin_name = map_exercise_name(name, report)
        filled_sets, had_history = prefill_exercise_sets(ex, history)
        if not had_history:
            report.append(f"{name or '(unnamed exercise)'}: no prior 'lifts' "
                           f"session found — uploaded without weight/reps targets.")
        for si, s in enumerate(filled_sets):
            order += 1
            label = name or f"(unnamed exercise, step {order})"
            matched = s.pop("_matched", False)
            # Exercise has history, but not at THIS position (e.g. last time
            # had fewer/differently-typed sets) — report once per affected
            # set. Skip for myo/drop: build_myo_drop_step already reports
            # unconditionally, so a second line here would just be noise.
            if had_history and not matched and s["type"] not in ("myorep", "drop"):
                report.append(f"{label}: set {si + 1} ({s['type']}) has no "
                               f"matching set in the last session — uploaded "
                               f"without a target.")
            if s["type"] in ("myorep", "drop"):
                steps.append(build_myo_drop_step(order, label, category, garmin_name,
                                                  s["type"], s.get("sequence", ""), report))
            else:
                steps.append(build_set_step(order, label, category, garmin_name,
                                             s["type"], s.get("weight", ""), s.get("reps", ""), report))

    if not steps:
        raise MapperError(f"Template {template.get('name')!r} produced zero sets — nothing to push.")
    if len(steps) > MAX_WORKOUT_STEPS:
        raise MapperError(f"Mapped workout has {len(steps)} steps, over Garmin's "
                           f"{MAX_WORKOUT_STEPS}-step limit (spec 1.2). Split the template.")

    workout = {
        "workoutName": push_workout_name(template.get("name") or "", target_date),
        "sportType": {"sportTypeId": 5, "sportTypeKey": "strength_training"},
        "workoutSegments": [{
            "segmentOrder": 1,
            "sportType": {"sportTypeId": 5, "sportTypeKey": "strength_training"},
            "workoutSteps": steps,
        }],
    }
    return workout, report


def print_report(template_name, target_date, report):
    log("")
    log(f"--- Push report: {template_name!r} -> {target_date} ---")
    if not report:
        log("Every set mapped cleanly: exercise recognized, weight and reps parsed.")
    else:
        for line in report:
            log(f"  - {line}")
    log(f"--- end report ({len(report)} item(s)) ---")


def push_workout(client, workout, target_date):
    """Upload `workout` (workoutName already set) and schedule it to
    target_date. Re-push semantics (spec 1.2/1.6): any EXISTING workout with
    the exact same workoutName is deleted first, then this one is created —
    'delete and recreate', because Garmin doesn't reliably overwrite a stale
    on-watch copy in place (spec 1.2). Matches/deletes ONLY by that
    deterministic name, so it can never reach a workout it didn't itself
    create this way. Verifies exercise names round-tripped (catches the
    known silent-drop bug, spec 1.2/1.7) before scheduling. Returns the new
    workout_id. Never retries a write; any failure is fail() (non-zero exit)."""
    name = workout["workoutName"]

    try:
        existing = client.get_workouts(start=0, limit=100)
    except Exception as e:
        fail(f"get_workouts failed while checking for a prior push ({type(e).__name__}: {e}).")
    time.sleep(REQUEST_DELAY_SECONDS)

    prior_ids = [w.get("workoutId") for w in existing if w.get("workoutName") == name]
    for wid in prior_ids:
        log(f"Re-push: deleting this script's own prior workout id={wid} ({name!r}).")
        try:
            client.delete_workout(wid)
        except Exception as e:
            fail(f"delete_workout failed for prior push id={wid} ({type(e).__name__}: {e}). "
                 f"Not continuing — delete it manually in Garmin Connect, then retry.")
        time.sleep(REQUEST_DELAY_SECONDS)

    if prior_ids:
        try:
            still_there = client.get_workouts(start=0, limit=100)
        except Exception as e:
            fail(f"get_workouts failed while confirming the prior push was deleted "
                 f"({type(e).__name__}: {e}).")
        time.sleep(REQUEST_DELAY_SECONDS)
        leftover = [wid for wid in prior_ids if any(w.get("workoutId") == wid for w in still_there)]
        if leftover:
            fail(f"delete_workout did not raise, but {leftover} still appear in "
                 f"get_workouts() — refusing to upload a duplicate. Check Garmin "
                 f"Connect manually (Training > Workouts > {name!r}).")

    try:
        created = client.upload_workout(workout)
    except Exception as e:
        fail(f"upload_workout failed ({type(e).__name__}: {e}). Not retrying.")
    workout_id = created.get("workoutId") if isinstance(created, dict) else None
    if not workout_id:
        fail(f"upload_workout returned no workoutId — response: {created!r}.")
    log(f"Created workout id={workout_id} ({name!r}).")
    time.sleep(REQUEST_DELAY_SECONDS)

    try:
        detail = client.get_workout_by_id(workout_id)
    except Exception as e:
        fail(f"get_workout_by_id failed after upload ({type(e).__name__}: {e}). "
             f"Workout id={workout_id} was created — check it manually in Garmin Connect.")
    time.sleep(REQUEST_DELAY_SECONDS)
    expected_names = sorted(n for n in _exercise_names(workout) if n)
    actual_names = sorted(n for n in _exercise_names(detail) if n)
    if actual_names != expected_names:
        fail(f"Exercise names did not round-trip intact after upload (id={workout_id}): "
             f"expected {expected_names}, got {actual_names} — the known "
             f"'exerciseName silently dropped' failure mode (spec 1.2/1.7). The "
             f"workout exists but may guide wrong — check/delete it manually in "
             f"Garmin Connect before trusting it at the gym.")
    log(f"Exercise names round-tripped intact: {actual_names}.")

    try:
        client.schedule_workout(workout_id, target_date)
    except Exception as e:
        fail(f"schedule_workout failed ({type(e).__name__}: {e}). Workout id={workout_id} "
             f"was created but is NOT scheduled to {target_date} — schedule it manually "
             f"in Garmin Connect, or delete it (id above) and retry.")
    log(f"Scheduled id={workout_id} to {target_date}.")
    return workout_id


SESSION_PATH = os.path.expanduser(os.getenv("HT_SESSION_PATH", "~/.hybridtrainer_session.json"))
# Deliberately OUTSIDE the repo — same reasoning as TOKEN_DIR/~/.garminconnect
# above — so it can never be committed regardless of .gitignore content.
# Holds only a refresh token, never HT_PASSWORD itself, at file mode 600
# (owner read/write only).


def load_saved_session():
    if not os.path.isfile(SESSION_PATH):
        return None
    try:
        with open(SESSION_PATH) as f:
            return (json.load(f) or {}).get("refresh_token") or None
    except (OSError, ValueError):
        return None


def save_session(session):
    fd = os.open(SESSION_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump({"refresh_token": session.refresh_token}, f)
    os.chmod(SESSION_PATH, 0o600)  # belt-and-suspenders: os.open's mode only applies on CREATE


def supabase_sign_in(sb):
    """Sign in to Supabase, preferring a saved session over HT_EMAIL/
    HT_PASSWORD (spec doesn't require this — added because a human running
    --push over and over, unlike garmin_sync.py's one-shot-per-CI-run, was
    retyping a password every single time). Supabase refresh tokens rotate
    on use, so every successful sign-in (fresh OR refreshed) re-saves the
    latest one. Unlike Garmin, Supabase sign-in has no harsh rate-limit, so
    falling back to a fresh password sign-in when the saved session is dead
    is safe, not risky — it just quietly asks again instead of hard-failing."""
    refresh_token = load_saved_session()
    if refresh_token:
        try:
            auth = sb.auth.refresh_session(refresh_token)
            save_session(auth.session)
            log("Supabase: signed in from a saved session (no password needed).")
            return auth
        except Exception as e:
            log(f"Saved Supabase session expired or invalid ({type(e).__name__}: {e}) "
                f"— falling back to HT_EMAIL/HT_PASSWORD.")

    email, password = os.getenv("HT_EMAIL"), os.getenv("HT_PASSWORD")
    if not email or not password:
        fail("No saved Supabase session yet, and HT_EMAIL/HT_PASSWORD aren't set. "
             "Set them once (see sync/SETUP.md) — after that run, a session is "
             "saved and you won't need to set them again.")
    try:
        auth = sb.auth.sign_in_with_password({"email": email, "password": password})
    except Exception as e:
        fail(f"Supabase sign-in failed: {type(e).__name__}: {e}")
    save_session(auth.session)
    log("Supabase: signed in with HT_EMAIL/HT_PASSWORD, saved a session for next time.")
    return auth


def fetch_template(sb, user_id, template_name):
    try:
        res = sb.table("templates").select("id,name,type,exercises") \
            .eq("user_id", user_id).eq("type", "lifts").eq("name", template_name).execute()
    except Exception as e:
        fail(f"Could not read templates: {type(e).__name__}: {e}")
    rows = res.data or []
    if not rows:
        fail(f"No 'lifts' template named {template_name!r} for this account. Check "
             f"Templates in the app for the exact name (case-sensitive).")
    if len(rows) > 1:
        fail(f"{len(rows)} 'lifts' templates are named {template_name!r} — rename one "
             f"in the app so the name is unique, then retry.")
    return rows[0]


def fetch_lifts_history(sb, user_id):
    try:
        res = sb.table("sessions").select("date,start_time,type,exercises") \
            .eq("user_id", user_id).eq("type", "lifts").execute()
    except Exception as e:
        fail(f"Could not read session history: {type(e).__name__}: {e}")
    return sort_sessions_like_app(res.data or [])


def push(client, template_name, target_date):
    """Phase 2 entry point. Connects to Supabase with the SAME account
    garmin_sync.py uses (RLS intact — never the service key), reads one
    named template plus lifts history, maps it, and pushes it via
    push_workout(). Auth prefers a saved session over HT_EMAIL/HT_PASSWORD —
    see supabase_sign_in()."""
    for var in ("SUPABASE_URL", "SUPABASE_ANON_KEY"):
        if not os.getenv(var):
            fail(f"Missing required env var {var} — see sync/SETUP.md.")
    if create_client is None:
        fail("Missing Python deps. Run: pip install -r sync/requirements.txt")
    try:
        datetime.strptime(target_date, "%Y-%m-%d")
    except ValueError:
        fail(f"--date must be YYYY-MM-DD, got {target_date!r}.")

    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])
    auth = supabase_sign_in(sb)
    user_id = auth.user.id

    template = fetch_template(sb, user_id, template_name)
    history = fetch_lifts_history(sb, user_id)
    log(f"Template {template['name']!r}: {len(template.get('exercises') or [])} "
        f"exercise(s). History: {len(history)} past 'lifts' session(s).")

    settings_row = {}
    try:
        res = sb.table("user_settings").select("units").eq("user_id", user_id).execute()
        if res.data:
            settings_row = res.data[0]
    except Exception as e:
        log(f"warning: could not read user_settings ({e}); defaulting to lb")
    units_setting = settings_row.get("units") or "lb"
    if units_setting != "lb":
        fail(f"Account weight unit is {units_setting!r}. Phase 2 only has a VERIFIED "
             f"Garmin weightUnit object for pound (Phase 0's read-back only confirmed "
             f"lb — see this file's module docstring and spec 1.4/1.7's 'wrong "
             f"guidance is worse than none' rule). Not guessing a kilogram object. "
             f"Switch Settings > Units to lb to use this push, or verify+add kg "
             f"support first.")

    try:
        workout, report = map_template_to_workout(template, history, target_date)
    except MapperError as e:
        fail(str(e))
    steps = workout["workoutSegments"][0]["workoutSteps"]
    log(f"Mapped {len(steps)} step(s) from {len(template.get('exercises') or [])} exercise(s).")

    workout_id = push_workout(client, workout, target_date)
    print_report(template["name"], target_date, report)
    log(f"Push PASSED (id={workout_id}). Open Garmin Connect, or sync your watch, to "
        f"confirm {workout['workoutName']!r} lands on {target_date} — then check the "
        f"FR965 at the gym.")


def main():
    if Garmin is None:
        fail("Missing Python deps. Run: pip install -r sync/requirements.txt")

    parser = argparse.ArgumentParser(
        description="Hybrid Trainer -> Garmin Connect outbound workout push.")
    parser.add_argument(
        "--self-test", action="store_true",
        help="Phase 1 write-path proof: create one hardcoded 2-exercise "
             "workout, verify it round-tripped, delete it.")
    parser.add_argument(
        "--push", action="store_true",
        help="Phase 2: map a named lifts template + your latest history to "
             "a real workout, upload, and schedule it to --date. Writes to "
             "your real Garmin Connect account.")
    parser.add_argument(
        "--template", metavar="NAME",
        help="Exact name of a saved 'lifts' template (case-sensitive). Required with --push.")
    parser.add_argument(
        "--date", metavar="YYYY-MM-DD",
        help="Calendar date to schedule the workout to. Required with --push.")
    args = parser.parse_args()

    if args.self_test and args.push:
        parser.error("Pass only one of --self-test or --push.")
    if not args.self_test and not args.push:
        parser.error(
            "Pass --self-test (Phase 1 write-path proof) or --push --template "
            "NAME --date YYYY-MM-DD (Phase 2: push a real workout).")
    if args.push and not (args.template and args.date):
        parser.error("--push requires both --template and --date.")

    client = garmin_login()
    if args.self_test:
        self_test(client)
    else:
        push(client, args.template, args.date)


if __name__ == "__main__":
    main()
