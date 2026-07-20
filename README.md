# Hybrid Trainer

A workout tracker built for hybrid athletes who lift, run, and condition. The long-term goal is to track systemic fatigue across all three so you can train smarter, not just track sets and miles in separate apps that don't talk to each other.

**Live app:** https://johnnylenny.github.io/hybrid-trainer/

## Why this exists

- Lifting apps don't model how lifting affects running recovery
- Running apps (Garmin, Strava) undercount lifting effort
- Nothing aggregates both into a useful signal for hybrid training

Built as a learning project. Eventually intended to be a hub that pulls runs from Garmin, posts to Strava, and combines everything into one fatigue dashboard.

## What it does today

**Lifting**
- Four set types: warmup, working, myo-rep, and drop set
- Warmups auto-sort before working sets
- Reorder sets and exercises with up/down arrows
- Auto-suggests exercise names you've used before
- Pre-fills each set with what you did last time for that exercise, so you start from real numbers instead of a blank form (adjust them as needed)
- Check off each set with a "done" checkbox as you complete it
- Optional RPE or RIR tracking (or off entirely)

**Running**
- Five run types with conditional fields: Easy/Z2, Tempo/Threshold, Intervals/Track, Long Run, Race
- Tempo runs track the work portion on its own: warm-up, tempo distance/time/pace, cool-down, plus totals
- Race runs break out warm-up and cool-down from the race effort, so the pace reflects the race, not the easy miles around it
- Interval runs log multiple sets — reps x distance @ goal time + recovery (e.g. 5x400 @ 1:30, then 2x200 @ 0:45)
- Switching types preserves data, doesn't delete fields

**Conditioning**
- Type-based like runs: Erg (Row/Bike/Ski), Sled/Carry, Ruck, Circuit/MetCon, Hyrox/WOD, and Other/General, each with its own fields
- Hyrox/WOD uses a repeatable segment list (movement + target + result) for races and CrossFit benchmarks
- Switching type preserves data, doesn't delete fields

**Stats**
- Five charts: bodyweight, per-exercise progression, estimated 1RM (Epley), run pace trend, weekly volume by type
- Challenge view: a consistency grid. The "Friends overview" shows you and your friends for one activity type (add friends in Settings → Friends, by code or email). You can also start a **challenge** — a named, time-boxed group of up to 6, tracking any mix of lift/run/conditioning, where each member sets their own weekly goal; pick it from the grid's dropdown to see everyone's day-by-day or weekly consistency and post in a group comment thread, and finished challenges archive. A green dot just means a qualifying session happened — others only ever see your training *days*, never the weights, paces, notes, or bodyweight inside a session

**Sync across devices** (new in v0.10)
- Sign up with email and password, or use a magic link
- Sessions, templates, and settings sync between phone and laptop
- Local-only mode: continue without an account, keep all data on your device
- Sync indicator in the header tells you when changes are pushed to the cloud
- Failed cloud writes are queued and retried automatically (on a timer, when the network returns, or when you refocus the tab) — they survive a page reload, so a dropped write is never lost

**Profile** (new in v0.11)
- Display name and avatar picker (5 emoji presets)
- Shown in the header when signed in
- Stored in the cloud, syncs across devices

**Everywhere**
- Reusable templates for all three session types: lifts (exercise lists), run (any run type's fields, including a reps×distance@goal interval-set editor for intervals), and conditioning (any type's target fields, including a segment editor for Hyrox/WOD). Build them in the Templates tab, or save the current session as one. Built-in presets (Hyrox, Fran, Murph, Cindy) are one tap to add.
- Browse a starter-template library and add presets to your own templates with one tap
- Edit any saved session (tap it in History)
- Sort and filter history by type, phase, name, and date range
- Format validation flags impossible values; warnings catch missing or inconsistent data before saving
- Cross-day session support for workouts that span midnight
- Settings grouped into sections (Profile, Appearance, Units & tracking, Data, Danger zone): theme (light/dark/auto), 24h vs 12h, weight units (lb/kg), distance units (mi/km), intensity tracking
- In-app modals and toasts throughout — no native browser popups
- "Finish & Save" flow when ending a workout: set the end time to now (or a few minutes back with one tap), keep a time you already entered, or save with no end time at all — handy for logging old workouts
- Export and import your data as JSON (with schema versioning), from Settings or the History tab
- Import your Hevy history from a CSV export (Settings → Data) — each Hevy workout becomes a lifts session, supersets split into separate exercises, drop sets split into separate sets, and re-importing the same file skips duplicates
- Import a run or ride from a Garmin .TCX file (Settings → Data → Import workouts → From Garmin) — it reads distance, time, pace and heart rate, converts to your units, and guesses the run type (easy, tempo, intervals, long), then opens it on the Log tab to review before saving
- Automated daily Garmin sync (optional, for the cloud-synced account): a scheduled GitHub Actions workflow pulls the last few days of Garmin activities and inserts them as sessions — runs auto-typed the same way as the .TCX import, cycling and rowing as conditioning, strength skipped (you log lifts in the app), duplicates skipped. Sessions show a "Garmin" badge in History. Setup in [sync/SETUP.md](sync/SETUP.md)
- Send feedback (bug reports or feature requests) from inside the app (Settings → Feedback), signed in or not
- Import a single workout (or a batch) by pasting JSON (Settings → Data) — with a "Copy AI prompt" button so an AI can turn handwritten notes, a photo, or another app's export into the right format; one workout opens on the Log tab to review before saving
- Delete your cloud account from inside the app

## Status

v0.56.0 — daily-driver prototype with cloud sync (auto-retry on failed writes), user profiles, and a standard email signup that adopts any workouts you logged locally the first time you sign in. Multi-type templates (all run and conditioning types, with interval and segment editors) plus a starter library and built-in workout presets; detailed tempo/interval/race run logging; type-based conditioning including a Hyrox/WOD segment tracker; custom in-app modals; a Finish & Save end-time flow. Cardio from Garmin syncs automatically once a day, no import needed; you can also import lifting history from a Hevy CSV, a Garmin .TCX file by hand (reads distance/time/pace/HR, converts units, and guesses the run type, with heart-rate-based tempo detection), or any workout by pasting JSON (with an AI-prompt helper); plus an in-app feedback form. Lift logging pre-fills each set from your last session and lets you check sets off as done. You can add friends (by code or email) and start time-boxed challenge groups (up to 6, any mix of activities, each member's own weekly goal) with a group comment thread; the Stats grid shows everyone's training consistency side by side, and others see only which days you trained, never the session details. An in-progress workout survives closing and reopening the app. Works on phone and laptop, signed in or local-only.

## How to use it

1. Open the [live app](https://johnnylenny.github.io/hybrid-trainer/) on your phone or laptop
2. On iPhone: Share → Add to Home Screen for an app-like icon
3. On Android: Chrome menu → Add to Home screen
4. Either create an account (email + password) for cross-device sync, or click "Continue without an account" to stay local-only
5. Log workouts. Save sessions as templates to reuse exercise lists.
6. Check the Stats tab once you have a few sessions logged.

## Important: how data is stored

You choose between two modes the first time you open the app.

**Signed in (cloud sync)**
- Data lives in a Supabase database, scoped to your account
- localStorage on each device is a fast cache that gets overwritten on sign-in
- Same data across all signed-in devices
- Signing out wipes the local cache on that device (other devices unaffected)

**Local-only mode**
- Everything stays in your browser's localStorage on the device you're using
- Clearing browser data deletes everything
- Switching browsers means starting over

In either mode, **export your data regularly** as a backup. Settings → Export gives you a JSON file you can Import later or migrate elsewhere. See [SCHEMA.md](SCHEMA.md) for the data format.

## Roadmap

**Next up:**
- More cardio import formats, so you stop hand-entering pace/distance/HR. Garmin .TCX import ships since v0.39 (heart-rate-based run-type detection since v0.40), and v0.54 added a fully automated daily Garmin pull via GitHub Actions — file imports are now the manual fallback. GPX is the next file format, then .FIT (binary), then a Strava connection. Lifting import from Hevy shipped in v0.25.

**The reason this exists:**
- Combined lifting + cardio fatigue score (the differentiator no other app does for hybrid athletes)

**Long-term:**
- Conflict resolution for simultaneous edits on two devices
- Strava export for completed sessions
- Challenges with friends — friends, challenge groups, the per-challenge grid, and per-challenge comment threads all work now (named, time-boxed, up to 6 people, per-member goals)
- Hub-style dashboard aggregating training load across modalities

## Known limitations

- No conflict resolution: if you edit the same session on two devices simultaneously, last write wins.
- Myo-rep and drop-set sequences are free text, not parsed into structured data
- Autocomplete only suggests exercises you've previously logged
- Unit settings are labels only; switching units does NOT convert old logs
- Stats tab requires an internet connection (loads Chart.js from a CDN)
- Cloud sync requires an internet connection. The app still works offline if you've loaded it once, but new writes won't sync until you're back online.

## Tech

Plain HTML, CSS, and JavaScript in one file. No build step. Two CDN dependencies: Chart.js for the Stats tab, and Supabase JS client for cloud sync. Hosted on GitHub Pages. Data lives in browser localStorage and (for signed-in users) a Supabase Postgres database.

See [SCHEMA.md](SCHEMA.md) for both the local data format and the cloud database schema.

## Built with

[Claude](https://claude.ai) as coding partner. Every chunk of code is commented so the author (a coding beginner) can actually read and understand what it does.

## License

MIT — see [LICENSE](LICENSE) file. Use it, fork it, modify it.
