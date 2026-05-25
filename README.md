# Hybrid Trainer

A workout tracker built for hybrid athletes who lift, run, and condition. The long-term goal is to track systemic fatigue across all three so you can train smarter, not just track sets and miles in separate apps that don't talk to each other.

**Live app:** https://johnnylenny.github.io/hybrid-trainer/

## Why this exists

- Lifting apps don't model how lifting affects running recovery
- Running apps (Garmin, Strava) undercount lifting effort
- Nothing aggregates both into a useful signal for hybrid training

Built as a learning project. Eventually intended to be a hub that pulls runs from Garmin, posts to Strava, and combines everything into one fatigue dashboard.

## What it does today

- Log lifting sessions with four set types: warmup, working, myo-rep, and drop set
- Log running sessions (distance, time, pace, HR, RPE)
- Log conditioning sessions (modality, total work, splits, RPE)
- Save exercise lists as reusable templates
- Auto-suggests exercise names you've used before
- Shows last session's numbers as grayed-out targets to beat
- Edit any saved session (tap it in History)
- Reorder sets and exercises with up/down arrows
- Warmups auto-sort before working sets
- Settings for theme (light/dark/auto), 24h vs 12h, units (lb/kg), and intensity tracking (RPE/RIR/off)
- Export and import your data as JSON (with schema versioning)

## Status

v0.4 — daily-driver prototype. Works on phone and laptop. No accounts, no cloud sync.

## How to use it

1. Open the [live app](https://johnnylenny.github.io/hybrid-trainer/) on your phone or laptop
2. On iPhone: Share → Add to Home Screen for an app-like icon
3. On Android: Chrome menu → Add to Home screen
4. Log workouts. Save sessions as templates to reuse exercise lists.
5. Tweak preferences in the Settings tab.

## Important: how data is stored

All your data is saved in your browser's localStorage on the device you're using. That means:

- Your phone and your laptop each have separate data
- Clearing your browser data deletes everything
- Switching browsers means starting over
- Nobody else can see your data

**Back up regularly** by tapping Export. It gives you a JSON file you can Import later or move to another device. See [SCHEMA.md](SCHEMA.md) for the data format.

## Roadmap

**Near-term (v0.5):**
- Run types with conditional fields (Easy / Tempo / Intervals / Long / Race)
- Session-level fatigue inputs (overall RPE, sleep quality, soreness)

**Mid-term:**
- Progression charts per exercise
- Volume and frequency analytics

**Long-term:**
- Garmin import for runs
- Strava export for completed sessions
- Combined lifting + cardio fatigue score
- Hub-style dashboard that aggregates training load across modalities

## Known limitations

- No cloud sync between devices
- No accounts or login
- Myo-rep and drop-set sequences are free text, not parsed into structured data
- Autocomplete only suggests exercises you've previously logged
- Unit setting is a label only; switching units does NOT convert old logs
- "Add to Home Screen" requires internet to first load the app

## Tech

Plain HTML, CSS, and JavaScript in one file. No frameworks, no build step, no dependencies. Hosted on GitHub Pages. Data lives in browser localStorage.

See [SCHEMA.md](SCHEMA.md) for the data format if you want to write scripts against your exported data or build something on top of it.

## Built with

[Claude](https://claude.ai) as coding partner. Every chunk of code is commented so the author (a coding beginner) can actually read and understand what it does.

## License

MIT — see [LICENSE](LICENSE) file. Use it, fork it, modify it.
