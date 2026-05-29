Hybrid Trainer
A workout tracker built for hybrid athletes who lift, run, and condition. The long-term goal is to track systemic fatigue across all three so you can train smarter, not just track sets and miles in separate apps that don't talk to each other.
Live app: https://johnnylenny.github.io/hybrid-trainer/
Why this exists

Lifting apps don't model how lifting affects running recovery
Running apps (Garmin, Strava) undercount lifting effort
Nothing aggregates both into a useful signal for hybrid training

Built as a learning project. Eventually intended to be a hub that pulls runs from Garmin, posts to Strava, and combines everything into one fatigue dashboard.
What it does today
Lifting

Four set types: warmup, working, myo-rep, and drop set
Warmups auto-sort before working sets
Reorder sets and exercises with up/down arrows
Auto-suggests exercise names you've used before
Shows last session's numbers as grayed-out targets to beat
Optional RPE or RIR tracking (or off entirely)

Running

Five run types with conditional fields: Easy/Z2, Tempo/Threshold, Intervals/Track, Long Run, Race
Different types show different fields (e.g. intervals shows splits, races show result)
Switching types preserves data, doesn't delete fields

Conditioning

Free-form modality, total work, RPE, splits

Stats

Five charts: bodyweight, per-exercise progression, estimated 1RM (Epley), run pace trend, weekly volume by type

Everywhere

Save exercise lists as reusable templates
Edit any saved session (tap it in History)
Sort and filter history by type, phase, name, and date range
Format validation flags impossible values; warnings catch missing or inconsistent data before saving
Cross-day session support for workouts that span midnight
Settings: theme (light/dark/auto), 24h vs 12h, weight units (lb/kg), distance units (mi/km), intensity tracking
Export and import your data as JSON (with schema versioning)

Status
v0.8 — daily-driver prototype. Works on phone and laptop. No accounts, no cloud sync.
How to use it

Open the live app on your phone or laptop
On iPhone: Share → Add to Home Screen for an app-like icon
On Android: Chrome menu → Add to Home screen
Log workouts. Save sessions as templates to reuse exercise lists.
Check the Stats tab once you have a few sessions logged.

Important: how data is stored
All your data is saved in your browser's localStorage on the device you're using. That means:

Your phone and your laptop each have separate data
Clearing your browser data deletes everything
Switching browsers means starting over
Nobody else can see your data

Back up regularly by tapping Export. It gives you a JSON file you can Import later or move to another device. See SCHEMA.md for the data format.
Roadmap
Near-term:

Conditioning field cleanup (per-modality fields)
More mobile polish

The reason this exists:

Combined lifting + cardio fatigue score (the differentiator no other app does for hybrid athletes)

Long-term:

Backend sync (cross-device, shareable with friends)
Garmin import for runs
Strava export for completed sessions
Hub-style dashboard aggregating training load across modalities

Known limitations

No cloud sync between devices
No accounts or login
Myo-rep and drop-set sequences are free text, not parsed into structured data
Autocomplete only suggests exercises you've previously logged
Unit settings are labels only; switching units does NOT convert old logs
Stats tab requires an internet connection (loads Chart.js from a CDN)
"Add to Home Screen" requires internet to first load the app

Tech
Plain HTML, CSS, and JavaScript in one file. No build step. The only dependency is Chart.js, loaded from a CDN for the Stats tab. Hosted on GitHub Pages. Data lives in browser localStorage.
See SCHEMA.md for the data format if you want to write scripts against your exported data or build something on top of it.
Built with
Claude as coding partner. Every chunk of code is commented so the author (a coding beginner) can actually read and understand what it does.
License
MIT — see LICENSE file. Use it, fork it, modify it.
