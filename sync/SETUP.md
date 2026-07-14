# Garmin auto-sync — setup

A GitHub Actions workflow (`.github/workflows/garmin-sync.yml`) runs daily at
09:00 UTC and inserts your last 3 days of Garmin activities into the app's
cloud `sessions` table. After the one-time setup below there are zero manual
steps — new activities just appear in the app (a fresh open pulls everything
from the cloud; on a phone, returning to a backgrounded app usually triggers
a fresh open too).

What syncs: runs (auto-typed easy/tempo/intervals/long), rowing (erg),
cycling and other cardio (conditioning). Strength activities are skipped —
you log lifts in the app. No health metrics (sleep, HRV, etc.).

## One-time setup

### 0. Install the Python deps locally

```bash
cd ~/Claude/Projects/hybrid-trainer
pip3 install -r sync/requirements.txt
```

### 1. Seed Garmin tokens (the only credential login, ever)

Garmin rate-limits password logins hard (429s, multi-day lockouts), so the
CI workflow never logs in with credentials — it reuses tokens you create
once, locally:

```bash
python3 sync/seed_tokens.py
```

It prompts for your Garmin email, password, and MFA code, then caches
tokens in `~/.garminconnect`. Your password is used once and never stored.

### 2. Pack the tokens into a GitHub secret

```bash
COPYFILE_DISABLE=1 tar czf - -C "$HOME" .garminconnect | base64 | pbcopy
```

That puts a base64 blob on your clipboard (nothing is printed on screen).
`COPYFILE_DISABLE=1` stops macOS from adding junk `._*` files to the tar.

If you're not on a Mac, drop `pbcopy` and copy the printed output instead:

```bash
tar czf - -C "$HOME" .garminconnect | base64
```

### 3. Create the GitHub secrets

GitHub repo → **Settings → Secrets and variables → Actions** → **New
repository secret**, five times:

| Secret | Value |
|---|---|
| `GARMIN_TOKENS` | paste the clipboard from step 2 |
| `SUPABASE_URL` | `https://rrrfmudypfhywiremudw.supabase.co` (same as in index.html) |
| `SUPABASE_ANON_KEY` | the anon/public key from index.html (it's public by design — RLS is the protection) |
| `HT_EMAIL` | the email you sign into Hybrid Trainer with |
| `HT_PASSWORD` | your Hybrid Trainer password |

Never add the Supabase **service role** key, and never add your Garmin
password. The sync signs in as *you*, so Row Level Security applies exactly
as it does in the app.

### 4. (Optional) Tempo detection

The app's easy-HR-ceiling setting lives only in your browser's localStorage
(deliberately not cloud-synced), so CI can't read it. To enable tempo
detection in the sync, set the same number as a repo **variable** (not a
secret): **Settings → Secrets and variables → Actions → Variables tab** →
name `EASY_HR_CEILING`, value e.g. `150`. Leave it unset and hot runs simply
classify as easy — same as the app with the setting blank.

## Running it

- **Manual run:** repo → **Actions** → **Garmin sync** → **Run workflow**.
- **Scheduled:** daily at 09:00 UTC automatically.
- **Verify:** the run is green; open the app (hard refresh on desktop:
  Cmd+Shift+R), History shows the new sessions with a "Garmin" badge.
  Run it again immediately: still green, log says `inserted=0`.

The run log shows one line per activity: inserted, skipped (already in
cloud), or skipped (strength). Anything already imported via the manual
TCX importer is recognized and skipped too — same `garmin:<timestamp>`
dedupe key.

## When tokens expire (~1 year) or the workflow fails with a token error

The failure message in the Actions log says exactly this, but for the
record:

```bash
rm -rf ~/.garminconnect
python3 sync/seed_tokens.py
COPYFILE_DISABLE=1 tar czf - -C "$HOME" .garminconnect | base64 | pbcopy
```

Then update the `GARMIN_TOKENS` secret with the new clipboard contents
(Settings → Secrets and variables → Actions → `GARMIN_TOKENS` → Update).

## Good to know

- **The workflow never retries a Garmin login.** Missing/expired tokens =
  immediate red run with the re-seed instructions above, zero login
  attempts against your Garmin account.
- **Failure artifact:** a failed run uploads `garmin-sync-debug-log`
  (dates, activity types, insert/skip decisions — no activity names, HR
  data, or secrets). Green runs upload nothing.
- **GitHub pauses cron on quiet repos:** after ~60 days without any repo
  activity, GitHub disables scheduled workflows and emails you first. Any
  push re-enables it, or hit the "Enable" button on the Actions page. You
  push regularly, so this likely never bites.
- **Unofficial API:** `garminconnect` is a reverse-engineered client.
  Garmin can break it any day; if that happens the workflow fails red and
  emails you, the app itself is untouched, and the manual TCX import keeps
  working as the fallback.
- **Dedupe is one-directional by design:** the sync always skips anything
  already in the cloud (including manual TCX imports). But if a run
  auto-synced first and you *then* manually import the same .tcx file, the
  app's single-file review path doesn't check import_source — saving it
  would duplicate. With auto-sync running you shouldn't need manual TCX
  imports anymore.
