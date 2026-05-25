# Hybrid Trainer Data Schema

This document describes the data format used by the Hybrid Trainer app. The format is intentionally simple and exportable so you can do whatever you want with your data: analyze it in a spreadsheet, build your own tools, import it into another app, or feed it to a script that calculates fatigue scores.

## Current schema version: 5

Every exported JSON file includes a `schemaVersion` field so future versions of the app (or any downstream tools) can detect the format.

## Top-level export format

```json
{
  "schemaVersion": 5,
  "exportedAt": "2026-05-24T18:41:00.000Z",
  "settings": { ... },
  "templates": [ ... ],
  "history": [ ... ],
  "currentSession": { ... }
}
```

| Field | Type | Description |
|---|---|---|
| `schemaVersion` | number | Version of the data format. Increment on breaking changes. |
| `exportedAt` | ISO 8601 string | When the file was exported. |
| `settings` | object | User preferences (units, intensity tracking, theme, etc). |
| `templates` | array | Saved exercise lists for quick session reuse. |
| `history` | array | All saved sessions, most recent first. |
| `currentSession` | object | The in-progress session being edited. |

## Session object

A session represents one workout. There are three types: `lifts`, `run`, `conditioning`.

```json
{
  "date": "2026-04-13",
  "startTime": "18:41",
  "endTime": "20:21",
  "bodyweight": "205.25",
  "name": "BACK",
  "phase": "Hypertrophy",
  "type": "lifts",
  "exercises": [ ... ],
  "runData": {},
  "condData": {},
  "notes": "Really not into it today"
}
```

| Field | Type | Description |
|---|---|---|
| `date` | string (YYYY-MM-DD) | Date of the session. |
| `startTime` | string (HH:MM, 24h) | When the session started. Optional. |
| `endTime` | string (HH:MM, 24h) | When the session ended. Optional. |
| `bodyweight` | string | Stored as a string, not number. Unit is whatever the user had selected at log time. |
| `name` | string | Free-text name, e.g. "BACK", "LEGS", "Easy run". |
| `phase` | string | Training phase tag, e.g. "Hypertrophy", "Strength", "Peak". |
| `type` | string | One of `lifts`, `run`, `conditioning`. Determines which sub-object is used. |
| `exercises` | array | Used when `type === "lifts"`. Empty otherwise. |
| `runData` | object | Used when `type === "run"`. Empty otherwise. |
| `condData` | object | Used when `type === "conditioning"`. Empty otherwise. |
| `notes` | string | Free-text notes about the whole session. |

## Exercise object (lifts only)

```json
{
  "name": "BB Bent-over Row",
  "sets": [ ... ],
  "notes": "felt light, no belt"
}
```

| Field | Type | Description |
|---|---|---|
| `name` | string | Exercise name (e.g. "Back Squat", "DB Curl"). |
| `sets` | array | List of sets, in order. Warmups always sort to the top. |
| `notes` | string | Free-text exercise-level notes. |

## Set object

Sets have a `type` field that determines the rest of the shape. Four types:

### Warmup set
```json
{ "type": "warmup", "weight": "45", "reps": "10" }
```

### Working set
```json
{ "type": "working", "weight": "115", "reps": "10", "rpe": "7", "rir": "" }
```

Either `rpe` or `rir` may be populated depending on which the user has enabled in settings. Both fields always exist on working sets but one is typically empty.

### Myo-rep set
```json
{ "type": "myorep", "weight": "", "sequence": "15 × 14, 8, 3, 2" }
```

The `sequence` field is a free-text string. It's not parsed into structured data because myo-rep notation varies between users.

### Drop set
```json
{ "type": "drop", "sequence": "35x8, 25x7, 15x11" }
```

The `sequence` field is a free-text chain of weight × reps drops.

## Run data (when type === "run")

Run sessions have a `runType` field that determines which other fields are meaningful. All fields are strings (free text) and all are optional.

```json
{
  "runType": "easy",
  "distance": "5.2k",
  "time": "26:15",
  "pace": "5:02/km",
  "hr": "152",
  "rpe": "3",
  "notes": "Felt good, nasal breathing whole way"
}
```

### Run types and their fields

**`easy`** — Easy / Zone 2
- `distance`, `time`, `pace`, `hr`, `rpe`, `notes`

**`tempo`** — Tempo / Threshold
- `distance`, `time`, `pace`, `hr`, `notes`
- No RPE: the pace target is the effort target

**`intervals`** — Intervals / Track
- `workout` (e.g. "6x800m"), `targetPace`, `recovery`, `splits`, `totalDistance`, `totalTime`, `notes`
- No avg pace or HR: splits are the data

**`long`** — Long Run
- `distance`, `time`, `pace`, `hr`, `rpe`, `fueling`, `notes`

**`race`** — Race
- `distance`, `time`, `pace`, `result`, `notes`
- No RPE, no HR: result is the data

### Backwards compatibility

Old runs from before v0.5 don't have a `runType` field. The app treats those as `runType: "easy"` for display purposes. Data is not destroyed: switching run types preserves all fields, even ones the new type doesn't display.

## Conditioning data (when type === "conditioning")

```json
{
  "modality": "Rower",
  "total": "6x500m",
  "rpe": "8",
  "splits": "1:45, 1:47, 1:46, 1:48, 1:50, 1:52"
}
```

## Template object

A template is a saved exercise list with the structure stripped of actual logged values.

```json
{
  "name": "BACK",
  "type": "lifts",
  "exercises": [
    {
      "name": "Pull-up",
      "sets": [
        { "type": "warmup" },
        { "type": "working" },
        { "type": "working" }
      ],
      "notes": ""
    }
  ]
}
```

Templates only store exercise names and set types. They never store weights or reps.

## Settings object

```json
{
  "theme": "auto",
  "timeFormat": "24",
  "units": "lb",
  "intensity": "rpe",
  "defaultPhase": ""
}
```

| Field | Type | Values |
|---|---|---|
| `theme` | string | `auto`, `light`, `dark` |
| `timeFormat` | string | `24`, `12` |
| `units` | string | `lb`, `kg` (label only, not converted) |
| `intensity` | string | `off`, `rpe`, `rir` |
| `defaultPhase` | string | Free text. |

## Conventions and gotchas

- **All numbers are stored as strings.** This is intentional. Free-text fields like "115" or "115.5" or "115/110" all coexist without coercion errors. If you want to compute on them, parse to number in your tool.
- **Units are not stored per-set.** The user's current units preference is global. If a user switches units mid-program, old numbers are NOT converted. Treat all numbers as "user's chosen unit at log time."
- **Empty strings are common.** Fields are present but blank rather than missing.
- **Sets always have `type`.** The other fields depend on the type.
- **Runs always have `runType` from v0.5 onward.** Old data is treated as `easy`.
- **Switching run types preserves orphan data.** If you log a tempo run with HR, then switch to intervals (which doesn't display HR), the HR value stays in the JSON. It's just hidden from the UI. This is intentional — no data loss from type changes.
- **History is ordered most recent first** (`history[0]` is the newest session).
- **The `currentSession` is the live in-progress session.** When the user saves, it gets pushed onto `history` and a new empty one takes its place.

## Schema version history

- **v5** (current) — Added `runType` field to run sessions with five types (easy, tempo, intervals, long, race), each with their own field set. Backwards compatible with v4: old runs without `runType` are treated as easy.
- **v4** — Added `schemaVersion`, `exportedAt`, optional `rir` field on working sets, and `settings` to exports.
- **v3** (implicit, no version field) — Same as v2 visually but with the polished UI redesign.
- **v2** (implicit, no version field) — Introduced four set types (warmup, working, myorep, drop), session metadata (date, start/end time, bodyweight, name, phase), templates, history, run and conditioning session types.
- **v1** (implicit, deprecated) — Original phase/day rigid program structure. Files from v1 are not supported by import.
