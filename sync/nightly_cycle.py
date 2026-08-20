#!/usr/bin/env python3
"""
nightly_cycle.py — the nightly training-cycle orchestrator: import, advance,
push, cleanup, in that order, each isolated from the others' failures.

Owner rulings, 2026-08-19 ("close the training cycle"):
  (a) an ordered QUEUE of lifts templates with a head pointer
      (user_settings.lift_queue: {templateIds:[...], headIndex:N}),
      auto-advancing when a watch import matches the head's template name.
  (b) this script's OWN past pushed workouts auto-delete from Garmin Connect
      so nothing builds up on the watch — they're regenerable from HT
      history. Hand-built workouts are structurally out of reach (matched by
      exact deterministic name pattern only, see garmin_push.PUSHED_WORKOUT_RE).
  (c) unreviewed imports still count as the freshest numbers for the mapper
      (the watch is source of truth) — already true, no code change needed:
      garmin_push.fetch_lifts_history() never reads cond_data.reviewPending,
      so a session sitting in the "Imported - review" state in the app is
      still fully visible to prefill/mapping here.
  (d) push nightly, so the watch has maximum background-sync time before
      the gym.

This is the "new decision" outputs/Garmin_Outbound_Spec.md fence 5 and
garmin_push.py's own docstring both said scheduled Garmin writes needed
before they could exist. See garmin_push.py's module docstring and the
spec's fence-5 amendment note for the full story; this file doesn't repeat it.

Four stages, run in order, each isolated (owner requirement 5): a failure in
one must not block the others, and the failure-class line must name the
stage. run_stage() below is the isolation boundary — every stage function
returns (ok, result) on every outcome it explicitly handles, including a
SKIP (empty queue, a name mismatch, a deleted template — normal outcomes,
not failures), and logs its own STAGE-<NAME> line for each. Only an
UNHANDLED exception falls through to run_stage's own generic catch.

Shared setup (Supabase sign-in, the Garmin token bundle, Garmin login) is NOT
stage-wrapped: if it fails, none of the 4 stages could do anything anyway, so
it keeps exactly the exit-code classification (10/11/13) garmin_sync.py and
garmin_push.py already use standalone. Only a failure inside the 4 stages
produces the new EXIT_STAGE_FAILURE code — the ORIGINAL failure detail
(which class, which stage) stays on that stage's own log line, so nothing is
lost; the new code just means "check the STAGE-* lines."

Nothing here forks garmin_sync.py's or garmin_push.py's actual import/
mapper/push logic — this file only orchestrates calls into both, plus the
queue read/advance/write logic that's genuinely new. garmin_push.log is
reassigned to this file's log() at import time so push's own narration (the
mapping report, workout ids, cleanup deletions) lands in the same
sync_log.txt the workflow uploads on failure — garmin_push.py's own log()
only prints, it never appends to a file.

FENCE (unchanged from garmin_push.py): index.html never changes for any of
this, in any phase, and never learns this script exists.
"""

import os
import sys
from datetime import date

try:
    from supabase import create_client
except ImportError:
    create_client = None

import garmin_sync
import garmin_push
import token_store

log = garmin_sync.log  # print + append to sync_log.txt, reused as-is
garmin_push.log = log  # so push()/cleanup's own narration lands there too

EXIT_STAGE_FAILURE = 16  # one or more of the 4 stages failed; see STAGE-* lines
FAIL_CLASSES = {**garmin_sync.FAIL_CLASSES, EXIT_STAGE_FAILURE: "STAGE-FAILURE"}


def fail(msg, code):
    """Same shape as garmin_sync.py/garmin_push.py's own fail(): log the
    class, log the detail, raise. Reuses garmin_sync.SyncFailure (rather
    than a third exception type) since main()'s outer catch already handles
    it and the two share the same FAIL_CLASSES code space here."""
    log(f"FAIL-CLASS: {FAIL_CLASSES.get(code, 'UNKNOWN')}")
    log("FATAL: " + str(msg))
    raise garmin_sync.SyncFailure(msg, code)


# ---------------------------------------------------------------------------
# Queue storage — user_settings.lift_queue (migration:
# _local/migrations/lift-queue.sql). Tolerant reads (a missing row/column
# defaults to an empty queue, not an error — "nothing configured yet" is
# normal); upsert writes (user_settings may not have a row yet for this
# user, and an UPDATE on a missing row would silently affect zero rows and
# drop the advance with no error — same defensive reasoning garmin_sync.py's
# own settings read already uses for this table).
# ---------------------------------------------------------------------------

def fetch_lift_queue(sb, user_id):
    try:
        res = sb.table("user_settings").select("lift_queue") \
            .eq("user_id", user_id).execute()
    except Exception as e:
        log(f"warning: could not read lift_queue ({type(e).__name__}: {e}); "
            f"treating as empty")
        return {"templateIds": [], "headIndex": 0}
    rows = res.data or []
    queue = (rows[0].get("lift_queue") if rows else None) or {}
    return {
        "templateIds": queue.get("templateIds") or [],
        "headIndex": queue.get("headIndex") or 0,
    }


def write_lift_queue(sb, user_id, queue):
    sb.table("user_settings").upsert(
        {"user_id": user_id, "lift_queue": queue},
        on_conflict="user_id",
    ).execute()


# ---------------------------------------------------------------------------
# Stage isolation
# ---------------------------------------------------------------------------

def run_stage(name, fn):
    """Call fn() as one isolated stage. fn() is expected to return (ok,
    result) and log its own STAGE-<name> line for every outcome it handles
    itself. An exception that escapes fn() is the safety net: caught here,
    logged as STAGE-<name>: FAIL, turned into (False, None) so the stage
    after this one still runs."""
    try:
        return fn()
    except Exception as e:
        log(f"STAGE-{name}: FAIL ({type(e).__name__}: {e})")
        return False, None


def stage_import(sb, user_id, client):
    """Unlike the other 3 stages, import can PARTIALLY succeed — some
    activities inserted fine while an unrelated one failed to map — and the
    advance stage still needs whatever new lifts sessions DID land even when
    this stage reports FAIL for the ones that didn't. So this does not raise
    on a non-empty errors list (unlike garmin_sync.py's own standalone
    caller, which still does, via garmin_sync._run() checking the same
    field) — it logs FAIL and returns the result anyway."""
    result = garmin_sync.sync_activities(sb, user_id, client)
    if result["errors"]:
        log(f"STAGE-IMPORT: FAIL ({len(result['errors'])} activities failed "
            f"to map or insert; inserted={result['inserted']} succeeded "
            f"anyway — see the DATA errors above)")
        return False, result
    log(f"STAGE-IMPORT: OK (inserted={result['inserted']} "
        f"already_synced={result['already']} "
        f"skipped_existing_lifts={result['skipped_existing_lifts']})")
    return True, result


def stage_advance(sb, user_id, new_lifts):
    """Walk new_lifts (already oldest-first from sync_activities) against
    the queue head, advancing on each name match and stopping — never
    erroring — at the first mismatch (owner requirement 2: on mismatch, do
    NOT advance, say so). Only ever moves headIndex, never edits
    templateIds, so a manual reorder in the app always wins."""
    queue = fetch_lift_queue(sb, user_id)
    template_ids = queue.get("templateIds") or []
    head_index = queue.get("headIndex") or 0

    if not template_ids:
        log("STAGE-ADVANCE: SKIP (queue is empty)")
        return True, {"advanced": 0, "queue": queue}
    if not new_lifts:
        log("STAGE-ADVANCE: SKIP (no new lifts session imported this run)")
        return True, {"advanced": 0, "queue": queue}

    advanced = 0
    stop_reason = None
    for session in new_lifts:
        idx = head_index % len(template_ids)
        head_row = garmin_push.fetch_template_by_id(sb, user_id, template_ids[idx])
        head_name = head_row["name"] if head_row else None
        did_name = session.get("name")
        if head_row is None:
            stop_reason = (f"queue head id={template_ids[idx]} no longer "
                            f"resolves to a template — not advancing")
            break
        if did_name and did_name == head_name:
            head_index = idx + 1
            advanced += 1
            log(f"advance: {session['date']} {did_name!r} matched the queue "
                f"head — moved to the next template")
        else:
            did_display = repr(did_name) if did_name else "(unrecognized/hand-done activity)"
            stop_reason = (f"{session['date']}: did {did_display}, queue "
                            f"expected {head_name!r} — not advancing")
            break

    queue["headIndex"] = head_index % len(template_ids)
    if advanced:
        write_lift_queue(sb, user_id, queue)
        msg = (f"STAGE-ADVANCE: OK (advanced {advanced} step(s), head is "
               f"now index {queue['headIndex']})")
        if stop_reason:
            msg += f"; stopped there: {stop_reason}"
        log(msg)
    else:
        log(f"STAGE-ADVANCE: SKIP ({stop_reason})")
    return True, {"advanced": advanced, "queue": queue, "stop_reason": stop_reason}


def stage_push(sb, user_id, client, queue, today_str):
    """Push the (possibly just-advanced) queue head's template for today.
    Reuses garmin_push.push() completely unchanged — the only new code is
    resolving the head's template id to a name first, since push() (like the
    manual --push CLI) is name-keyed."""
    template_ids = queue.get("templateIds") or []
    if not template_ids:
        log("STAGE-PUSH: SKIP (queue is empty)")
        return True, None
    idx = (queue.get("headIndex") or 0) % len(template_ids)
    head_row = garmin_push.fetch_template_by_id(sb, user_id, template_ids[idx])
    if head_row is None:
        log(f"STAGE-PUSH: SKIP (queue head id={template_ids[idx]} no longer "
            f"resolves to a template)")
        return True, None
    garmin_push.push(client, sb, user_id, head_row["name"], today_str)
    log(f"STAGE-PUSH: OK ({head_row['name']!r} -> {today_str})")
    return True, head_row["name"]


def stage_cleanup(client, today_str):
    """Best-effort: garmin_push.cleanup_stale_pushes() already keeps going
    on a per-item delete failure rather than aborting the sweep, so a FAIL
    here still means everything deletable got deleted."""
    result = garmin_push.cleanup_stale_pushes(client, today_str)
    if result["failed"]:
        log(f"STAGE-CLEANUP: FAIL ({len(result['failed'])} deletion(s) "
            f"failed, {len(result['deleted'])} succeeded anyway, "
            f"{result['kept']} not-yet-stale left in place)")
        return False, result
    log(f"STAGE-CLEANUP: OK (deleted {len(result['deleted'])}, "
        f"{result['kept']} not-yet-stale left in place)")
    return True, result


# ---------------------------------------------------------------------------
# Shared setup + orchestration
# ---------------------------------------------------------------------------

def supabase_login():
    """Like garmin_sync.py's own supabase_login(), but allow_saved_session
    defaults True (matching garmin_push.py's supabase_sign_in) rather than
    being hardcoded False. This script runs both in CI (no saved session —
    falls through to the same required HT_EMAIL/HT_PASSWORD secrets) and
    locally by a human testing changes, where reusing a saved session avoids
    retyping a password on every run."""
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])
    try:
        auth = token_store.supabase_sign_in(sb, log=log)
    except token_store.TokenStoreError as e:
        fail(str(e), garmin_sync.EXIT_AUTH_SUPABASE)
    return sb, auth.user.id


def main():
    try:
        _run()
    except garmin_sync.SyncFailure as e:
        sys.exit(e.code)
    except garmin_push.PushFailure:
        sys.exit(1)


def _run():
    if garmin_sync.Garmin is None or create_client is None:
        fail("Missing Python deps. Run: pip install -r sync/requirements.txt",
             garmin_sync.EXIT_CONFIG)
    # HT_EMAIL/HT_PASSWORD are NOT required upfront here (unlike
    # garmin_sync.py, which only ever runs unattended) — supabase_login()
    # below prefers a saved local session (matching garmin_push.py's own
    # pattern), and token_store.supabase_sign_in() already raises a clear
    # TokenStoreError if neither a saved session nor these are available. In
    # CI, where there's never a saved session, a missing secret still fails
    # fast, just classified AUTH-SUPABASE (13) instead of CONFIG (10).
    for var in ("SUPABASE_URL", "SUPABASE_ANON_KEY"):
        if not os.getenv(var):
            fail(f"Missing required env var {var} (set it as a GitHub Actions "
                 f"secret — see sync/SETUP.md).", garmin_sync.EXIT_CONFIG)

    today_str = date.today().isoformat()

    # Shared setup: NOT stage-wrapped. If this fails, none of the 4 stages
    # can do anything anyway (no signed-in client, no Garmin login), so it
    # keeps today's exact exit-code classification instead of the new
    # STAGE-FAILURE code.
    sb, user_id = supabase_login()
    try:
        state = token_store.install_bundle(sb, user_id, log=log)
    except token_store.TokenStoreError as e:
        fail(str(e), garmin_sync.EXIT_AUTH_GARMIN)

    actor = "ci" if os.getenv("GITHUB_ACTIONS") == "true" else "local"
    any_failed = False
    try:
        client = garmin_sync.garmin_login()

        import_ok, import_result = run_stage(
            "IMPORT", lambda: stage_import(sb, user_id, client))
        any_failed = any_failed or not import_ok
        new_lifts = (import_result or {}).get("new_lifts") or []

        advance_ok, advance_result = run_stage(
            "ADVANCE", lambda: stage_advance(sb, user_id, new_lifts))
        any_failed = any_failed or not advance_ok
        queue = (advance_result or {}).get("queue") or fetch_lift_queue(sb, user_id)

        push_ok, _ = run_stage(
            "PUSH", lambda: stage_push(sb, user_id, client, queue, today_str))
        any_failed = any_failed or not push_ok

        cleanup_ok, _ = run_stage(
            "CLEANUP", lambda: stage_cleanup(client, today_str))
        any_failed = any_failed or not cleanup_ok
    finally:
        # finally, not just the happy path: garth can rotate the bundle on
        # the very first Garmin call, so a run that dies partway may still
        # owe the shared row a newer bundle. Same pattern garmin_sync.py and
        # garmin_push.py already use.
        wrote, rotated = token_store.persist_bundle(
            sb, user_id, state, actor=actor, log=log)

    if not wrote and rotated:
        fail("The nightly cycle finished, but the rotated Garmin bundle "
             "could not be written back to the cloud (see the warning "
             "above). Re-run the workflow; if it keeps failing, re-seed "
             f"with {token_store.RESEED_LINE}.", garmin_sync.EXIT_TOKEN_WRITEBACK)

    if any_failed:
        fail("One or more stages failed — see the STAGE-* lines above for "
             "which and why.", EXIT_STAGE_FAILURE)

    log("Nightly cycle: all stages OK.")


if __name__ == "__main__":
    main()
