#!/usr/bin/env python3
"""
seed_tokens.py — one-time LOCAL Garmin Connect login to create cached tokens.

Run this on your own machine, never in CI. It does the single credential
login (with MFA prompt if your account uses it) and caches the resulting
tokens in ~/.garminconnect. Those tokens — not your password — are what the
GitHub Actions sync uses, packed into the GARMIN_TOKENS secret. Full steps
in sync/SETUP.md.

Why this split exists: since March 2026 Garmin aggressively rate-limits
credential logins per account (429s, multi-day lockouts). One careful login
here, then roughly a year of token-only access from CI.
"""

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

TOKEN_DIR = os.path.expanduser("~/.garminconnect")

NEXT_STEPS = """
Next steps (see sync/SETUP.md for the full walkthrough):
  1. Pack the tokens for GitHub (copies straight to your clipboard):
       COPYFILE_DISABLE=1 tar czf - -C "$HOME" .garminconnect | base64 | pbcopy
  2. GitHub repo -> Settings -> Secrets and variables -> Actions ->
     New repository secret -> name it GARMIN_TOKENS, paste, save.
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


def main():
    # If cached tokens already work, don't burn a credential login.
    try:
        client = Garmin()
        client.login(TOKEN_DIR)
        print(f"Cached tokens in {TOKEN_DIR} are already valid — no login needed.")
        print("(To force a fresh login anyway:  rm -rf ~/.garminconnect  and rerun.)")
        print(NEXT_STEPS)
        return
    except Exception:
        pass  # no valid tokens; do the one credential login below

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
    print(NEXT_STEPS)


if __name__ == "__main__":
    main()
