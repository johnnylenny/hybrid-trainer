#!/usr/bin/env python3
"""
token_store.py — the ONE place the Garmin token bundle lives, plus the
Supabase sign-in helpers the sync/ scripts share.

THE PROBLEM THIS SOLVES (owner ruling 2026-08-19). The Garmin bundle is a
rotating credential: garth refreshes it and writes the new one back. Until
now it lived in two places that could not stay in step:

  * the GARMIN_TOKENS GitHub secret — a FROZEN snapshot. CI restored it every
    run and its refreshed tokens died with the runner, so the secret could
    only ever get staler, never heal.
  * ~/.garminconnect on the owner's Mac — which DID heal on every local run,
    and whose rotations silently orphaned the CI copy.

Two diverging copies of one rotating credential is the prime suspect for
bundles dying in weeks instead of the documented ~year (see
.claude/skills/_owner-runbook.md "Garmin token death watch"). So: ONE bundle,
in the cloud, in the `garmin_tokens` table (migration
_local/migrations/garmin-tokens.sql), read by every run and written back by
every run, CI and local alike.

Last-write-wins is accepted on purpose: a CI run and a local push overlapping
to the second is not a real risk here, and the loser simply re-reads a valid
bundle on its next run.

WHAT IS LOGGED: the bundle's age, who last wrote it, and how many times it
has actually rotated. NEVER the bundle contents — it grants persistent
account access, same as a password.

CREDENTIAL LOGIN STAYS LOCAL AND HUMAN-ONLY: nothing in this module logs in
to Garmin with a password. Only sync/seed_tokens.py does, only when a human
runs it. Garmin rate-limits password logins hard (429s, multi-day lockouts).

The local ~/.garminconnect file is still the WORKING copy during a run —
install_bundle() writes the cloud bundle there and garminconnect reads/
refreshes it exactly as before. persist_bundle() then reads that file back
and pushes whatever the library left in it. The library's behavior is
untouched; only where the bundle comes from and goes to has changed.
"""

import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path

TABLE = "garmin_tokens"
BUNDLE_FILE_NAME = "garmin_tokens.json"  # the filename garminconnect itself uses
TOKEN_DIR = os.path.expanduser(os.getenv("GARMIN_TOKEN_DIR", "~/.garminconnect"))

# The one sentence every auth failure ends with. The bundle is now
# self-maintaining, so a human only has to act on the ~yearly real expiry —
# and when that day comes this line must be enough on its own.
RESEED_LINE = "token bundle expired: run seed_tokens.py --upload"

RESEED_HELP = f"""
{RESEED_LINE}

On your own machine (never in CI — Garmin credentials must never be CI
secrets):

    python3 sync/seed_tokens.py --upload

That does the single credential login (password + MFA prompt), then writes
the fresh bundle to the cloud `garmin_tokens` row. Both the daily CI sync and
your local pushes read that row, so there is nothing else to update
afterwards — no secret to re-pack. Full walkthrough: sync/SETUP.md."""


class TokenStoreError(Exception):
    """Anything the caller should turn into its own classified failure."""


# ---------------------------------------------------------------------------
# The local working copy (~/.garminconnect/garmin_tokens.json)
# ---------------------------------------------------------------------------

def bundle_path(token_dir=None):
    return Path(token_dir or TOKEN_DIR).expanduser() / BUNDLE_FILE_NAME


def read_local_bundle(token_dir=None):
    """The bundle garminconnect currently has on disk, or None. Tolerant on
    purpose: a missing or half-written file is a normal state to handle, not
    an error to raise."""
    p = bundle_path(token_dir)
    try:
        data = json.loads(p.read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("di_token") else None


def write_local_bundle(bundle, token_dir=None):
    """Write the bundle where garminconnect expects it, at the same
    permissions the library itself uses (0700 dir, 0600 file) — this is a
    credential, and CI runners are shared hosts."""
    p = bundle_path(token_dir)
    p.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        p.parent.chmod(stat.S_IRWXU)  # mkdir's mode is umask-bound and a no-op if it existed
    except OSError:
        pass
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(p, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(bundle, f)
    try:
        p.chmod(0o600)  # enforce it even if the file pre-existed looser
    except OSError:
        pass


# ---------------------------------------------------------------------------
# The shared cloud bundle (`garmin_tokens` row)
# ---------------------------------------------------------------------------

def _parse_ts(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _age(value):
    """Human age of a timestamptz, e.g. '15d' / '4h' / '9m'. Returns '?' when
    the timestamp is missing or unparseable — never raises, because this is
    only ever used for a log line."""
    ts = _parse_ts(value)
    if ts is None:
        return "?"
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    secs = (datetime.now(timezone.utc) - ts).total_seconds()
    if secs < 0:
        return "0m"
    if secs >= 86400:
        return f"{int(secs // 86400)}d"
    if secs >= 3600:
        return f"{int(secs // 3600)}h"
    return f"{int(secs // 60)}m"


def age_line(row):
    """The evidence line. Bundle age, last write, who wrote it, how many real
    rotations — and never a byte of the bundle itself. If short deaths keep
    happening, THIS is the data the death watch has never had."""
    return (f"seeded {_age(row.get('seeded_at'))} ago, "
            f"last written {_age(row.get('updated_at'))} ago "
            f"by {row.get('updated_by') or '?'}, "
            f"{row.get('refresh_count') or 0} rotation(s) since seeding")


def fetch_row(sb, user_id):
    """The user's bundle row, or None. Raises TokenStoreError if the query
    itself fails — a read error must never be mistaken for 'no bundle yet'
    and quietly fall through to the local copy."""
    try:
        res = sb.table(TABLE).select(
            "bundle,seeded_at,updated_at,updated_by,refresh_count"
        ).eq("user_id", user_id).execute()
    except Exception as e:
        raise TokenStoreError(
            f"Could not read the {TABLE} row ({type(e).__name__}: {e}). If the "
            f"table does not exist yet, run _local/migrations/garmin-tokens.sql "
            f"in the Supabase SQL editor.") from e
    rows = res.data or []
    return rows[0] if rows else None


class BundleState:
    """What install_bundle() loaded, carried to persist_bundle() so it can
    tell a real rotation from an unchanged bundle."""

    def __init__(self, loaded, row, source):
        self.loaded = loaded    # the bundle dict as of the start of the run
        self.row = row          # the cloud row it came from, or None
        self.source = source    # 'cloud' | 'local-bootstrap'


def install_bundle(sb, user_id, *, log, token_dir=None):
    """Put the shared bundle on disk where garminconnect will find it, and
    say (without contents) how old it is. Call this BEFORE garmin login."""
    row = fetch_row(sb, user_id)
    bundle = (row or {}).get("bundle")
    if row and isinstance(bundle, dict) and bundle.get("di_token"):
        write_local_bundle(bundle, token_dir)
        log(f"Garmin tokens: loaded the shared cloud bundle ({age_line(row)}).")
        return BundleState(bundle, row, "cloud")

    # No usable row. The only legitimate time this happens is the bootstrap
    # window before the first `seed_tokens.py --upload`, so a local bundle is
    # adopted (and uploaded at the end of this run) rather than failing the
    # owner's machine. CI has no local bundle once GARMIN_TOKENS is retired,
    # so CI lands on the raise below, which is the intended CI behavior.
    local = read_local_bundle(token_dir)
    if local:
        log("Garmin tokens: no cloud bundle row yet — bootstrapping from the "
            "local ~/.garminconnect copy; it will be uploaded at the end of "
            "this run.")
        return BundleState(local, None, "local-bootstrap")

    raise TokenStoreError(
        f"No Garmin token bundle: the {TABLE} row is missing or empty and "
        f"there is no local bundle either.{RESEED_HELP}")


def persist_bundle(sb, user_id, state, *, actor, log, token_dir=None):
    """Write whatever garminconnect left on disk back to the shared row, at
    the END of every run. Returns (ok, rotated).

    Never raises: this runs in a finally block, where raising would mask the
    real failure. A failed write-back of a ROTATED bundle is still serious
    (that rotation is lost and the next run gets a dead token), so the caller
    escalates on (ok=False, rotated=True) — see garmin_sync.py."""
    current = read_local_bundle(token_dir)
    if not current:
        log("warning: no Garmin token file on disk at the end of the run — "
            "nothing to write back.")
        return True, False

    rotated = current != state.loaded
    row = state.row or {}
    payload = {
        "user_id": user_id,
        "bundle": current,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": actor,
        # Count only real content changes. `seeded_at` is deliberately absent:
        # on insert it defaults to now(), on update PostgREST leaves columns
        # it wasn't given alone — so only seed_tokens.py --upload resets it,
        # which is what makes it a true bundle age.
        "refresh_count": int(row.get("refresh_count") or 0) + (1 if rotated else 0),
    }
    try:
        sb.table(TABLE).upsert(payload, on_conflict="user_id").execute()
    except Exception as e:
        log(f"WARNING: could not write the Garmin bundle back to the cloud "
            f"({type(e).__name__}: {e}). "
            + ("A ROTATED bundle was lost — the next run will fail on expired "
               "tokens until this is fixed." if rotated
               else "The bundle did not change this run, so nothing was lost."))
        return False, rotated
    if rotated:
        log(f"Garmin tokens: rotated during this run; wrote the new bundle "
            f"back (rotation #{payload['refresh_count']} since seeding).")
    else:
        log("Garmin tokens: unchanged this run; refreshed the row's timestamp.")
    return True, rotated


def upload_bundle(sb, user_id, bundle, *, log, actor="seed"):
    """Seed path: replace the row with a freshly-logged-in bundle and restart
    the evidence counters. Only sync/seed_tokens.py calls this."""
    now = datetime.now(timezone.utc).isoformat()
    try:
        sb.table(TABLE).upsert({
            "user_id": user_id,
            "bundle": bundle,
            "seeded_at": now,     # a real credential login: age starts over
            "updated_at": now,
            "updated_by": actor,
            "refresh_count": 0,
        }, on_conflict="user_id").execute()
    except Exception as e:
        raise TokenStoreError(
            f"Could not write the {TABLE} row ({type(e).__name__}: {e}). If the "
            f"table does not exist yet, run _local/migrations/garmin-tokens.sql "
            f"in the Supabase SQL editor.") from e
    log("Uploaded the token bundle to the cloud. Both the daily CI sync and "
        "your local pushes will pick it up from there — nothing else to "
        "update.")


# ---------------------------------------------------------------------------
# Supabase sign-in (moved here from garmin_push.py so seed_tokens.py, the
# push and the sync all share ONE implementation)
# ---------------------------------------------------------------------------

SESSION_PATH = os.path.expanduser(os.getenv("HT_SESSION_PATH", "~/.hybridtrainer_session.json"))
# Deliberately OUTSIDE the repo — same reasoning as TOKEN_DIR/~/.garminconnect —
# so it can never be committed regardless of .gitignore content. Holds only a
# refresh token, never HT_PASSWORD itself, at file mode 600.


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
    os.chmod(SESSION_PATH, 0o600)  # os.open's mode only applies on CREATE


def supabase_sign_in(sb, *, log, allow_saved_session=True):
    """Sign in to Supabase as the app user (RLS intact — never the service
    key). Prefers a saved refresh token so a human running the push over and
    over isn't retyping a password; CI passes allow_saved_session=False and
    goes straight to its secrets. Supabase refresh tokens rotate on use, so
    every successful sign-in re-saves the latest one. Unlike Garmin, Supabase
    sign-in has no harsh rate limit, so falling back to a password sign-in
    when the saved session is dead is safe."""
    if allow_saved_session:
        refresh_token = load_saved_session()
        if refresh_token:
            try:
                auth = sb.auth.refresh_session(refresh_token)
                save_session(auth.session)
                log("Supabase: signed in from a saved session (no password needed).")
                return auth
            except Exception as e:
                log(f"Saved Supabase session expired or invalid "
                    f"({type(e).__name__}: {e}) — falling back to "
                    f"HT_EMAIL/HT_PASSWORD.")

    email, password = os.getenv("HT_EMAIL"), os.getenv("HT_PASSWORD")
    if not email or not password:
        raise TokenStoreError(
            "No usable Supabase session, and HT_EMAIL/HT_PASSWORD aren't set. "
            "Set them once (see sync/SETUP.md).")
    try:
        auth = sb.auth.sign_in_with_password({"email": email, "password": password})
    except Exception as e:
        raise TokenStoreError(f"Supabase sign-in failed: {type(e).__name__}: {e}") from e
    if allow_saved_session:
        save_session(auth.session)
        log("Supabase: signed in with HT_EMAIL/HT_PASSWORD, saved a session "
            "for next time.")
    else:
        log("Supabase: signed in.")
    return auth
