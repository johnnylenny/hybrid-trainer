# Hybrid Trainer

A minimal, single-file workout tracker for hybrid athletes (lifting + running + conditioning). Built as a learning project and a tool I actually use.

**Live app:** https://johnnylenny.github.io/hybrid-trainer/

## What it does

- Log lifting sessions with four set types: warmup, working, myo-rep, and drop set
- Log running sessions (distance, time, pace, HR, RPE)
- Log conditioning sessions (modality, total work, splits, RPE)
- Save exercise lists as reusable templates
- Auto-suggests exercise names you've used before
- Shows last session's numbers as grayed-out targets to beat
- Track bodyweight and session duration per workout
- Filter history by training phase (Hypertrophy, Strength, Peak, etc.)
- Export and import your data as JSON

## Status

v0.2 — rough prototype. Works, not polished. No accounts, no cloud sync.

## How to use it

1. Open the [live app](https://johnnylenny.github.io/hybrid-trainer/) on your phone or laptop
2. On iPhone: Share → Add to Home Screen for an app-like icon
3. On Android: Chrome menu → Add to Home screen
4. Log workouts. Save sessions as templates to reuse exercise lists.

## Important: how data is stored

All your data is saved in your browser's localStorage on the device you're using. That means:

- Your phone and your laptop each have separate data
- Clearing your browser data deletes everything
- Switching browsers means starting over
- Nobody else can see your data

**Back up regularly** by clicking the Export button. It gives you a JSON file you can Import later or move to another device.

## Known limitations

- No cloud sync between devices
- No accounts or login
- Myo-rep and drop-set sequences are free text, not parsed into structured data
- Autocomplete only suggests exercises you've previously logged
- Target-to-beat hints only work when set structure matches the previous session
- "Add to Home Screen" requires internet to first load the app

## Tech

Plain HTML, CSS, and JavaScript in one file. No frameworks, no build step, no dependencies. Hosted on GitHub Pages.

## Built with

[Claude](https://claude.ai) as coding partner. Beginner-friendly approach: every chunk of code is commented so I can actually read and understand what it does.

## License

MIT — see [LICENSE](LICENSE) file. Use it, fork it, modify it.
