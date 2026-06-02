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
- Shows last session's numbers as grayed-out targets to beat
- Optional RPE or RIR tracking (or off entirely)

**Running**
- Five run types with conditional fields: Easy/Z2, Tempo/Threshold, Intervals/Track, Long Run, Race
- Different types show different fields (e.g. intervals shows splits, races show result)
- Switching types preserves data, doesn't delete fields

**Conditioning**
- Free-form modality, total work, RPE, splits

**Stats**
- Five charts: bodyweight, per-exercise progression, estimated 1RM (Epley), run pace trend, weekly volume by type

**Sync across devices** (new in v0.10)
- Sign up with email and password, or use a magic link
- Sessions, templates, and settings sync between phone and laptop
- Local-only mode: continue without an account, keep all data on your device
- Sync indicator in the header tells you when changes are pushed to the cloud

**Profile** (new in v0.11)
- Display name and avatar picker (5 emoji presets)
- Shown in the header when signed in
- Stored in the cloud, syncs across devices

**Everywhere**
- Save exercise lists as reusable templates
- Edit any saved session (tap it in History)
- Sort and filter history by type, phase, name, and date range
- Format validation flags impossible values; warnings catch missing or inconsistent data before saving
- Cross-day session support for workouts that span midnight
- Settings: theme (light/dark/auto), 24h vs 12h, weight units (lb/kg), distance units (mi/km), intensity tracking
- Export and import your data as JSON (with schema versioning)
- Delete your cloud account from inside the app

## Status

v0.11 — daily-driver prototype with cloud sync and user profiles. Works on phone and laptop, signed in or local-only.

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

**Near-term:**
- Conditioning field cleanup (per-modality fields)
- Polish: retry logic for failed cloud writes, conflict resolution

**The reason this exists:**
- Combined lifting + cardio fatigue score (the differentiator no other app does for hybrid athletes)

**Long-term:**
- Sharing with friends (read-only access to selected sessions)
- Garmin import for runs
- Strava export for completed sessions
- Hub-style dashboard aggregating training load across modalities

## Known limitations

- No retry yet if a cloud write fails. The sync indicator turns red, but you'll need to edit and resave the affected session to push it again.
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
