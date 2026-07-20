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

Trigger: local only, manually. `python3 sync/garmin_push.py --self-test`.
Never scheduled — a cron that writes to Garmin unattended is risk without
benefit (spec 1.3 / fence 5).

Phase 1 (this file, today): --self-test only. Uploads one hardcoded
2-exercise workout — cloned from the Phase 0 reference payload
(sync/testdata/reference_workout.json, Johnny's own hand-built "Chest Dat"
workout, fetched read-only via get_workout_by_id) — verifies it round-tripped
correctly (appears in get_workouts, exercise names intact), then deletes it.
One create, one delete, 0.5s delays between Garmin calls. Fail-loud: the
first sign of trouble is a clean non-zero exit with a clear message, never a
retry loop against a write endpoint (spec 1.7's fail-loud contract). The
delete only ever targets the workout ID *this run's own* upload_workout call
returned — never a hardcoded or externally-supplied ID — so a bug here
cannot reach any of Johnny's real workouts.

Phase 0 finding worth recording here (corrects spec 1.4's assumption): the
reference payload's weightUnit is NOT hardcoded to kilogram. Johnny's
hand-built workout round-tripped with weightUnit {"unitKey": "pound",
"unitId": 9, "factor": 453.59237} — Garmin accepts a full unit object, and
pound values round-trip (with ~0.001-0.002 lb float noise from an internal
kg round-trip — cosmetic, matches the 0.5kg display-rounding quirk in spec
1.2). So the mapper (Phase 2, not built yet) likely does NOT need to convert
the app's lb strings to kg at the payload boundary.

Phase 2 (the mapper: a real template + latest history -> a real workout,
scheduled to a date) is NOT built yet. Running this file today only proves
the write path and token scope; it does not push anything useful.
"""

import argparse
import os
import sys
import time

try:
    from garminconnect import Garmin
except ImportError:
    Garmin = None

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


def main():
    if Garmin is None:
        fail("Missing Python deps. Run: pip install -r sync/requirements.txt")

    parser = argparse.ArgumentParser(
        description="Hybrid Trainer -> Garmin Connect outbound workout push.")
    parser.add_argument(
        "--self-test", action="store_true",
        help="Phase 1 write-path proof: create one hardcoded 2-exercise "
             "workout, verify it round-tripped, delete it.")
    args = parser.parse_args()

    if not args.self_test:
        parser.error(
            "Phase 1 only supports --self-test today (spec 1.6). The mapper "
            "(Phase 2: a real template -> a real workout) isn't built yet.")

    client = garmin_login()
    self_test(client)


if __name__ == "__main__":
    main()
