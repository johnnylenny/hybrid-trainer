# Garmin auto-sync — setup

A GitHub Actions workflow (`.github/workflows/garmin-sync.yml`) runs daily at
09:00 UTC and inserts your last 14 days of Garmin activities into the app's
cloud `sessions` table (the window overlaps on purpose; dedupe makes that
harmless, and it lets an outage self-heal on the first green run). After the one-time setup below there are zero manual
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

### 1. Seed Garmin tokens and upload them (the only credential login, ever)

Garmin rate-limits password logins hard (429s, multi-day lockouts), so the
CI workflow never logs in with credentials — it reuses tokens you create
once, locally:

```bash
python3 sync/seed_tokens.py --upload
```

It prompts for your Garmin email, password, and MFA code, caches the tokens
in `~/.garminconnect`, and then uploads that bundle to the cloud
`garmin_tokens` table. Your password is used once and never stored.

**That upload is the whole point.** The bundle in that row is the *only* copy
that matters: the daily CI sync reads it, your local pushes read it, and both
write the refreshed bundle back at the end of every run. There is no second
copy to keep in step and no secret to re-pack — a re-seed takes effect
everywhere the moment `--upload` finishes.

`--upload` needs `SUPABASE_URL` and `SUPABASE_ANON_KEY` in your shell (same
values as step 3 below), because the row is protected by RLS — it signs in as
you to write it.

> Requires the `garmin_tokens` table: run
> `_local/migrations/garmin-tokens.sql` in the Supabase SQL editor once.

### 2. Create the GitHub secrets

GitHub repo → **Settings → Secrets and variables → Actions** → **New
repository secret**, four times:

| Secret | Value |
|---|---|
| `SUPABASE_URL` | `https://rrrfmudypfhywiremudw.supabase.co` (same as in index.html) |
| `SUPABASE_ANON_KEY` | the anon/public key from index.html (it's public by design — RLS is the protection) |
| `HT_EMAIL` | the email you sign into Hybrid Trainer with |
| `HT_PASSWORD` | your Hybrid Trainer password |

Never add the Supabase **service role** key, and never add your Garmin
password. The sync signs in as *you*, so Row Level Security applies exactly
as it does in the app — and that same sign-in is what unlocks the Garmin
token row.

There is **no `GARMIN_TOKENS` secret** any more (retired 2026-08-19 — see
"Why the old secret had to go" below). If you still have one, delete it;
nothing reads it.

### 3. Local shell setup (for pushes and `--upload`)

The same four values, exported in your shell, let you run `sync/` scripts
locally:

```bash
export SUPABASE_URL=https://rrrfmudypfhywiremudw.supabase.co
export SUPABASE_ANON_KEY=...   # the anon key from index.html
export HT_EMAIL=...
export HT_PASSWORD=...
```

After the first successful run a Supabase session is cached in
`~/.hybridtrainer_session.json`, so `HT_EMAIL`/`HT_PASSWORD` stop being
needed on later local runs.

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

## Fixing a red run

Every failure prints ONE line naming the failure class, at the top of the run
page (Actions → the red run). Read that line first — it tells you which of
these five things broke, so you don't have to dig through the log:

| Class | What broke | What to do |
|---|---|---|
| `AUTH-GARMIN` | Garmin rejected the shared token bundle | Run `python3 sync/seed_tokens.py --upload` locally. One command, fixes CI and local together. |
| `AUTH-SUPABASE` | Supabase rejected the sign-in | Your app password changed: update the `HT_PASSWORD` secret. This also blocks the Garmin bundle, which lives behind the same sign-in. |
| `GARMIN-API` | Login worked, a Garmin call failed | Usually transient (rate limit or Garmin outage). Wait for tomorrow's run; dedupe stops doubles. |
| `TOKEN-WRITEBACK` | The sync worked, but a rotated bundle couldn't be saved back | Re-run the workflow. If it repeats, `seed_tokens.py --upload`. |
| `DATA` | Auth all fine, some activities didn't map | Download the debug-log artifact on the run page to see which dates. The next run retries them. |
| `CONFIG` / `INSTALL` | A secret/variable is missing, or `pip install` failed | Re-check the secrets table above; `INSTALL` means the pinned dep couldn't be fetched. |

### Why `AUTH-GARMIN` happens now, and why one command fixes it

The bundle is **shared**. Every run — the daily CI sync and every local
`sync/` script — reads it from the `garmin_tokens` row at the start and
writes the refreshed bundle back at the end. So a Garmin failure no longer
means "one copy drifted"; it means the bundle itself is dead, which should
only happen at the real ~yearly expiry.

The fix is one command on your own machine:

```bash
python3 sync/seed_tokens.py --upload
```

It first tries your cached tokens (no password, no MFA, no rate-limit risk)
and only asks for credentials if those are dead too. Either way it ends by
writing the bundle to the shared row, so CI is fixed at the same moment your
Mac is. Then **Actions → Garmin sync → Run workflow** to confirm green.

### Why the old secret had to go (retired 2026-08-19)

`GARMIN_TOKENS` was a **frozen snapshot**. `garth` refreshes tokens and writes
the new ones back to `~/.garminconnect`, so the local copy healed itself on
every local run — but CI restored the same snapshot every run and its
refreshed tokens died with the runner. Once the snapshot's refresh token
stopped being accepted, no future CI run could revive it; it failed
identically forever until the secret was re-packed by hand. Worse, the two
copies rotated independently, and a local run could silently orphan the CI
one.

That is the prime suspect for bundles dying in weeks instead of the
documented year (`.claude/skills/_owner-runbook.md`, "Garmin token death
watch"). Both consequences are gone now: there is one copy, and **a local
run's rotation is exactly what CI reads next**.

### The evidence trail (if bundles still die early)

Every run logs one line with the bundle's age and history — never its
contents:

```
Garmin tokens: loaded the shared cloud bundle (seeded 15d ago, last written
1d ago by ci, 4 rotation(s) since seeding).
```

and one at the end saying whether the bundle rotated this run. The row itself
keeps the same facts; read them any time in the SQL editor:

```sql
select seeded_at, updated_at, updated_by, refresh_count from garmin_tokens;
```

Never `select bundle` onto a shared screen — it is a credential. `seeded_at`
only moves on a real `--upload`, so `now() - seeded_at` is the bundle's true
age, and `refresh_count` says how hard it is being rotated. If a bundle dies
short again, those two numbers are the data the death watch has never had.

## Pushing a workout to Garmin (outbound, Phase 2)

The sync above only reads FROM Garmin. `sync/garmin_push.py` writes TO it:
pick one of your saved lifts templates, and it fills in your most recent
weights/reps for each exercise (the same thing the app's Log form does when
you load a template), uploads it as a structured strength workout, and
schedules it to a date — so it shows up on your Forerunner 965 and guides
you through the lift at the gym. Full design: `outputs/Garmin_Outbound_Spec.md`.

**Local only, on purpose.** Unlike the daily sync, this is never scheduled
and has no "Run workflow" button (yet) — you run it from your own terminal
when you want a workout on the watch. It's a real write to your real Garmin
account, so it stays a deliberate, manual action.

**One-time setup:** same as above (Python deps installed, tokens seeded and
uploaded). The push does NOT need its own token setup — it reads the same
shared `garmin_tokens` bundle the daily sync reads, and writes the refreshed
bundle back to it, so a push keeps CI's tokens alive instead of orphaning
them the way it used to.

**Before running it locally**, export these as real environment variables in
your terminal (a GitHub secret only exists inside GitHub's servers — running
locally means your own shell has to know them instead):

```bash
export SUPABASE_URL="https://rrrfmudypfhywiremudw.supabase.co"
export SUPABASE_ANON_KEY="the anon/public key from index.html"
export HT_EMAIL="the email you sign into Hybrid Trainer with"
export HT_PASSWORD="your Hybrid Trainer password"
```

`SUPABASE_URL`/`SUPABASE_ANON_KEY` are needed every run. **`HT_EMAIL`/
`HT_PASSWORD` are only needed the FIRST time** (or whenever your saved
session eventually goes stale) — a successful sign-in saves a session file
at `~/.hybridtrainer_session.json` (outside the repo, file permissions
600 — only your Mac user account can read it, and it holds a session token,
never your actual password) and every run after that reuses and refreshes
it automatically. If that saved session ever stops working, the script
quietly falls back to asking for `HT_EMAIL`/`HT_PASSWORD` again — no manual
re-seed step like Garmin's tokens need. Delete
`~/.hybridtrainer_session.json` any time to force a fresh sign-in (e.g. if
you change your Hybrid Trainer password). Never commit any of this.

**Run it:**

```bash
python3 sync/garmin_push.py --push --template "CHEST" --date 2026-07-22
```

`--template` must exactly match a saved lifts template's name (case
matters — check Templates in the app). `--date` is the calendar date
(YYYY-MM-DD) to schedule it to.

**Rests are built in.** Every set (warm-ups included, and the last set too)
is followed by a rest step that waits for a lap-button press — it never
auto-advances. That rest screen is also where the watch lets you adjust the
reps and weight it just logged, so take as long as you need.

**What you'll see:** a log line per step of the process (sign-in, template
found, workout mapped, uploaded, scheduled), then a **push report** listing
every set that couldn't be filled in cleanly — no weight/reps history yet
for that exercise, a logged value like "115/110" that isn't a single
number, or a myo-rep/drop set (Garmin's workout model has no such thing, so
it uploads as a plain step you advance by hand). Nothing is ever silently
dropped — if a set isn't in the report, it mapped cleanly.

**Running it again for the same template and date is safe.** It deletes its
own previous push for that exact template+date first, then creates a fresh
one — so you never end up with two workouts on the watch for the same day.
It only ever touches a workout it named itself this way; it can't reach
anything you built by hand in Garmin Connect.

**Weight unit:** only works today if your Hybrid Trainer Units setting
(Settings tab) is **lb**. A kg account fails loud with an explanation rather
than risk showing the wrong number on your wrist — see the spec if you
want to add verified kilogram support.

**New exercise names:** the script only knows Garmin's official name for
exercises it's been told about by hand (`EXERCISE_TAXONOMY` near the top of
`sync/garmin_push.py`). An exercise it doesn't recognize still uploads (as a
plain step with just the rep target — no name or animation on the watch)
and shows up in the report so you know to add it.

## When tokens expire (~1 year) or the workflow fails with a token error

The failure message in the Actions log says exactly this, but for the record:

```bash
python3 sync/seed_tokens.py --upload
```

That is the whole procedure. It reuses your cached tokens if they still work
and only does a credential login (password + MFA) if they don't, then writes
the bundle to the shared `garmin_tokens` row that CI and local runs both use.
Nothing to pack, nothing to paste, no secret to update.

If you want to force a completely fresh login first:

```bash
rm -rf ~/.garminconnect && python3 sync/seed_tokens.py --upload
```

## Good to know

- **The workflow never retries a Garmin login.** A missing or expired bundle
  = immediate red run with the one-command fix above, zero login attempts
  against your Garmin account.
- **One bundle, shared.** CI and local runs read the same `garmin_tokens` row
  and both write the refreshed bundle back. Last write wins, which is fine:
  the loser just reads a valid bundle on its next run. A local run no longer
  orphans CI — and unlike before, a local script working *does* now tell you
  something about CI, because it is the same bundle.
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
