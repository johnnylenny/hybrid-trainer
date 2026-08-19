#!/usr/bin/env python3
"""
seed_tokens.py — the ONE credential login, done by a human on their own
machine, and the uploader for the shared Garmin token bundle.

    python3 sync/seed_tokens.py --upload

Run this on your own machine, never in CI. It does the single credential
login (with MFA prompt if your account uses it), caches the resulting tokens
in ~/.garminconnect, and with --upload writes that bundle to the cloud
`garmin_tokens` row — the ONE bundle the daily CI sync and your local pushes
both read and both write back to. After --upload there is nothing else to
update: no secret to re-pack, no second copy to keep in step. Full steps in
sync/SETUP.md.

Why the split exists: since March 2026 Garmin aggressively rate-limits
credential logins per account (429s, multi-day lockouts). One careful login
here, then roughly a year of token-only access from CI and local runs alike.
Why the SHARED bundle exists: two copies of a rotating credential kept
drifting apart and dying early — the full story is in sync/token_store.py.
"""

import argparse
import getpass
import os
import stat
import sys
from pathlib import Path

try:
    from garminconnect import (
        Garmin,
        GarminConnectAuthenticationError,
        GarminConnectConnectionError,
        GarminConnectTooManyRequestsError,
    )
except ImportError:
    sys.exit("Missing dependency. Run:  pip install -r sync/requirements.txt")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import token_store  # noqa: E402  (path set above so this works from any cwd)

TOKEN_DIR = token_store.TOKEN_DIR

UPLOAD_HINT = """
Nothing was uploaded. To share these tokens with the daily CI sync, rerun
with --upload:

    python3 sync/seed_tokens.py --upload

Without that, the cloud bundle keeps whatever it had, and CI keeps using it.
"""


def lock_down_token_dir():
    """Restrict token files to your user only (no-op on Windows)."""
    p = Path(TOKEN_DIR)
    if not p.exists() or os.name == "nt":
        return
    p.chmod(stat.S_IRWXU)  # 700
    for f in p.iterdir():
        try:
            f.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 600
        except OSError:
            pass


def upload(bundle):
    """Push the freshly-logged-in bundle to the shared cloud row. Signs in to
    Supabase as the app user, so RLS applies and the row is yours — same
    account and same anon key the sync uses, never the service key."""
    try:
        from supabase import create_client
    except ImportError:
        sys.exit("Missing dependency. Run:  pip install -r sync/requirements.txt")
    for var in ("SUPABASE_URL", "SUPABASE_ANON_KEY"):
        if not os.getenv(var):
            sys.exit(f"Missing required env var {var} — see sync/SETUP.md.")
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])
    try:
        auth = token_store.supabase_sign_in(sb, log=print)
        token_store.upload_bundle(sb, auth.user.id, bundle, log=print)
    except token_store.TokenStoreError as e:
        sys.exit(f"FATAL: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="One-time local Garmin login, and upload of the shared "
                    "token bundle.")
    parser.add_argument(
        "--upload", action="store_true",
        help="After logging in (or confirming the cached tokens still work), "
             "write the bundle to the cloud garmin_tokens row that CI and "
             "local runs share. This is what makes a re-seed take effect "
             "everywhere.")
    args = parser.parse_args()

    # If cached tokens already work, don't burn a credential login. Garmin
    # rate-limits those hard, and an --upload of still-valid tokens is a
    # perfectly good repair for a cloud row that got lost or clobbered.
    bundle = None
    try:
        client = Garmin()
        client.login(TOKEN_DIR)
        bundle = token_store.read_local_bundle()
        print(f"Cached tokens in {TOKEN_DIR} are already valid — no login needed.")
        print("(To force a fresh login anyway:  rm -rf ~/.garminconnect  and rerun.)")
    except Exception:
        pass  # no valid tokens; do the one credential login below

    if bundle is None:
        print("One-time Garmin login. Your password is used once and never stored;")
        print(f"only the resulting tokens are cached in {TOKEN_DIR}.")
        email = os.getenv("GARMIN_EMAIL") or input("Garmin email: ").strip()
        password = os.getenv("GARMIN_PASSWORD") or getpass.getpass("Garmin password (hidden): ")

        client = Garmin(
            email,
            password,
            prompt_mfa=lambda: input("MFA code (from email/app): ").strip(),
        )
        try:
            client.login(TOKEN_DIR)
        except GarminConnectAuthenticationError as e:
            sys.exit(f"Authentication failed — check email/password. Details: {e}")
        except GarminConnectTooManyRequestsError:
            sys.exit(
                "Garmin rate-limited the login (429). Wait at least an hour and try "
                "again. Do NOT retry in a loop — that extends the lockout."
            )
        except GarminConnectConnectionError as e:
            sys.exit(f"Could not reach Garmin. Check your connection. Details: {e}")

        lock_down_token_dir()
        print(f"\nLogged in. Tokens cached in {TOKEN_DIR}.")
        bundle = token_store.read_local_bundle()

    if not bundle:
        sys.exit(f"Logged in, but no token bundle appeared in {TOKEN_DIR}. "
                 f"Nothing to upload.")

    if args.upload:
        upload(bundle)
    else:
        print(UPLOAD_HINT)


if __name__ == "__main__":
    main()
