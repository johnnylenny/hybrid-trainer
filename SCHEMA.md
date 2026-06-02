# Hybrid Trainer Data Schema

This document describes the data format used by the Hybrid Trainer app. The format is intentionally simple and exportable so you can do whatever you want with your data: analyze it in a spreadsheet, build your own tools, import it into another app, or feed it to a script that calculates fatigue scores.

## Current schema version: 12

Every exported JSON file includes a `schemaVersion` field so future versions of the app (or any downstream tools) can detect the format.

## Where data lives

The app has two storage layers depending on whether you're signed in.

**Local-only mode** (you chose "Continue without an account"):
- Everything lives in your browser's `localStorage`
- Two keys: `hybridTrainerV2` (sessions + templates + current session) and `hybridTrainerSettings`
- Data never leaves the device

**Cloud-sync mode** (signed in via Supabase auth):
- Source of truth is the Supabase database (Postgres)
- `localStorage` is still used as a fast local cache
- Writes go to localStorage instantly, then to Supabase in the background
- On sign-in, the cloud overwrites the local cache (or you're prompted to upload local data first)
- On sign-out, the local cache is wiped to avoid leaking data between accounts

The two layers use the same JS object shapes. The conversion to/from the Supabase row format is documented in the [Local ↔ Cloud mapping](#local--cloud-mapping) section below.

## Top-level export format

```json
{
  "schemaVersion": 9,
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
  "id": "a1b2c3d4-...",
  "date": "2026-04-13",
  "startTime": "18:41",
  "endTime": "20:21",
  "endDate": "",
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
| `id` | string (UUID) | Stable identifier for the session. Added in v8 to support cloud sync. Old sessions without an id get one assigned on first upload. |
| `date` | string (YYYY-MM-DD) | Date of the session. |
| `startTime` | string (HH:MM, 24h) | When the session started. Optional. |
| `endTime` | string (HH:MM, 24h) | When the session ended. Optional. |
| `endDate` | string (YYYY-MM-DD) | Only set if the session ended on a different day than it started (e.g. crossed midnight). Empty/absent means same day as `date`. Added in v7. |
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

**`tempo`** — Tempo / Threshold (work portion tracked separately as of v0.16)
- `warmup`, `tempoDistance`, `tempoTime`, `tempoPace`, `cooldown`, `distance` (total), `time` (total), `hr`, `notes`
- The tempo (work) segment is logged apart from the whole run, e.g. `warmup: "0.5 mi"`, `tempoTime: "20:00"`, `tempoPace: "8:30"`, `cooldown: "1 mi"`.
- Pre-v0.16 tempo runs used a flat `distance`/`time`/`pace`. Those old fields stay in the JSON (not destroyed); `pace` just no longer has its own input. The Stats pace chart reads `pace` and falls back to `tempoPace` for tempo runs.

**`intervals`** — Intervals / Track (repeatable sets as of v0.16)
- `intervalSets` (array), plus `splits`, `totalDistance`, `totalTime`, `notes`
- `intervalSets` is a list of blocks so you can log more than one distance/goal in a session. Each block: `{ reps, distance, goal, recovery }`, e.g. `[{"reps":"5","distance":"400m","goal":"1:30","recovery":"90s jog"},{"reps":"2","distance":"200m","goal":"0:45","recovery":""}]`.
- Pre-v0.16 intervals used a single `workout`/`targetPace`/`recovery` text triple. Old data is preserved but the new UI uses `intervalSets`.

**`long`** — Long Run
- `distance`, `time`, `pace`, `hr`, `rpe`, `fueling`, `notes`

**`race`** — Race (warm-up/cool-down tracked separately as of v0.16.1)
- `warmup`, `distance`, `time`, `pace`, `result`, `cooldown`, `notes`
- The race effort stays in `distance`/`time`/`pace` (now labeled "Race distance/time/pace" in the UI). `warmup` and `cooldown` are free text for the miles run around the race, e.g. `warmup: "1.5 mi easy"`, `cooldown: "1 mi jog"`.
- No RPE, no HR: result is the data
- Pre-v0.16.1 race runs only had `distance`/`time`/`pace`/`result`/`notes`. Those fields are unchanged, so old races display correctly with empty warm-up/cool-down. The Stats pace chart still reads `pace`.

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

A template is a reusable plan. As of schema v10 it has three flavors keyed off `type`: `lifts`, `run`, and `conditioning`. Only the payload for that type is populated.

**Lifts template** — an exercise list with set types but no logged values:

```json
{
  "id": "a1b2c3d4-...",
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

**Run template** — a run type plus optional target distance/pace (added v10):

```json
{
  "id": "...",
  "name": "Tempo 5k",
  "type": "run",
  "exercises": [],
  "runData": { "runType": "tempo", "distance": "5", "pace": "4:30" }
}
```

**Conditioning template** — a modality plus optional target work (added v10):

```json
{
  "id": "...",
  "name": "Row Intervals",
  "type": "conditioning",
  "exercises": [],
  "condData": { "modality": "Row", "total": "5x500m" }
}
```

Lifts templates store exercise names and set types only — never weights or reps. Run/conditioning templates store *target* values only; you fill the actual numbers each session. The `id` field was added in v8 alongside cloud sync; old templates without an id get one assigned on first upload. `runData`/`condData` are omitted (not sent to the cloud) for lifts templates, so lifts templates remain compatible with a `templates` table that predates the v10 `run_data`/`cond_data` columns.

## Settings object

```json
{
  "theme": "auto",
  "timeFormat": "24",
  "units": "lb",
  "distanceUnit": "mi",
  "intensity": "rpe",
  "defaultPhase": "",
  "displayName": "",
  "avatar": ""
}
```

| Field | Type | Values |
|---|---|---|
| `theme` | string | `auto`, `light`, `dark` |
| `timeFormat` | string | `24`, `12` |
| `units` | string | `lb`, `kg` (label only, not converted) |
| `distanceUnit` | string | `mi`, `km` (label only; pace pairs automatically) |
| `intensity` | string | `off`, `rpe`, `rir` |
| `defaultPhase` | string | Free text. |
| `displayName` | string | Free text shown in header instead of email. Empty = fall back to email. Added in v9. Only meaningful in cloud-sync mode. |
| `avatar` | string | One of: `lifter`, `runner`, `strong`, `fire`, `bolt`, or empty. Maps to an emoji in the UI. Added in v9. |

## Cloud database schema (Supabase)

When signed in, data lives in three Postgres tables. Row Level Security ensures each user can only read/write their own rows.

### `sessions` table

| Column | Type | Notes |
|---|---|---|
| `id` | uuid (PK) | Same value as the local `id` field. |
| `user_id` | uuid | FK to `auth.users(id)`. Cascade on delete. |
| `date` | date | YYYY-MM-DD. |
| `start_time` | text | Nullable. Local `startTime` → null if empty. |
| `end_time` | text | Nullable. Local `endTime` → null if empty. |
| `end_date` | date | Nullable. Local `endDate` → null if empty. |
| `bodyweight` | text | Nullable. Local `bodyweight` → null if empty. |
| `name` | text | Nullable. |
| `phase` | text | Nullable. |
| `type` | text | Constrained to `lifts`, `run`, `conditioning`. |
| `exercises` | jsonb | Same array as local `exercises`. |
| `run_data` | jsonb | Same object as local `runData`. |
| `cond_data` | jsonb | Same object as local `condData`. |
| `notes` | text | Defaults to empty string. |
| `created_at` | timestamptz | Server-set on insert. |
| `updated_at` | timestamptz | Updated on every write. |

Indexes: `(user_id, date desc)`, `(user_id, type)`.

### `templates` table

| Column | Type | Notes |
|---|---|---|
| `id` | uuid (PK) | Same value as the local `id` field. |
| `user_id` | uuid | FK to `auth.users(id)`. Cascade on delete. |
| `name` | text | |
| `type` | text | `lifts`, `run`, or `conditioning` (v10). |
| `exercises` | jsonb | Lifts exercise array. Empty for run/conditioning. |
| `run_data` | jsonb | Run template targets `{runType, distance, pace}`. Null for non-run. Added v10. |
| `cond_data` | jsonb | Conditioning template targets `{modality, total}`. Null for non-conditioning. Added v10. |
| `created_at`, `updated_at` | timestamptz | |

Index: `(user_id)`.

Migration to add the v10 columns (run once in the Supabase SQL editor):

```sql
alter table templates
  add column if not exists run_data jsonb,
  add column if not exists cond_data jsonb;
```

### `starter_templates` table (v10 / app v0.15)

A read-only library of preset templates anyone can browse and copy into their own templates. No `user_id` — it's shared, not per-user. RLS allows `select` for everyone (including anon); writes happen only in the Supabase dashboard.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid (PK) | `gen_random_uuid()` default. |
| `name` | text | |
| `type` | text | `lifts`, `run`, or `conditioning`. |
| `category` | text | Optional secondary label (e.g. "Push", "Threshold"). |
| `exercises` | jsonb | Lifts exercise array; empty for run/conditioning. |
| `run_data` | jsonb | `{runType, distance, pace}` for run presets. |
| `cond_data` | jsonb | `{modality, total}` for conditioning presets. |
| `sort_order` | int | Display order, ascending. |
| `created_at` | timestamptz | Server-set. |

```sql
create table if not exists starter_templates (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  type text not null check (type in ('lifts','run','conditioning')),
  category text,
  exercises jsonb default '[]'::jsonb,
  run_data jsonb,
  cond_data jsonb,
  sort_order int default 0,
  created_at timestamptz default now()
);
alter table starter_templates enable row level security;
create policy "starter_templates readable by anyone"
  on starter_templates for select using (true);
```

### `user_settings` table

One row per user. Primary key is `user_id` (not a separate id), so there's at most one settings row per account.

| Column | Type | Maps to local |
|---|---|---|
| `user_id` | uuid (PK) | — |
| `theme` | text | `theme` |
| `time_format` | text | `timeFormat` |
| `units` | text | `units` |
| `distance_unit` | text | `distanceUnit` |
| `intensity` | text | `intensity` |
| `default_phase` | text | `defaultPhase` |
| `display_name` | text | `displayName` (added in v9) |
| `avatar` | text | `avatar` (added in v9) |
| `updated_at` | timestamptz | — |

### Row Level Security

All three tables have RLS enabled with a single policy each: `auth.uid() = user_id`. The anon/publishable key embedded in the client cannot read or write anyone else's rows. If you write your own tooling against the Supabase API, you'll need to sign in as the user you're querying for.

## Local ↔ Cloud mapping

The local JS shape and the database row shape are not identical. The app has converter functions (`sessionToRow`, `rowToSession`, etc.) that translate between them. Key differences:

| Local (camelCase) | Cloud (snake_case) |
|---|---|
| `startTime` | `start_time` |
| `endTime` | `end_time` |
| `endDate` | `end_date` |
| `runData` | `run_data` |
| `condData` | `cond_data` |
| `timeFormat` | `time_format` |
| `distanceUnit` | `distance_unit` |
| `defaultPhase` | `default_phase` |

Other notes:
- Empty strings in local fields become `null` in the database (Postgres null is more meaningful than empty string).
- `null` from the database becomes `""` (empty string) in local objects, to match the rest of the app's "everything is a string" convention.
- The `user_id` field exists only in the database. Local objects don't carry it because the entire local store belongs to one user already.

## Conventions and gotchas

- **All numbers are stored as strings.** This is intentional. Free-text fields like "115" or "115.5" or "115/110" all coexist without coercion errors. If you want to compute on them, parse to number in your tool.
- **Units are not stored per-set.** The user's current units preference is global. If a user switches units mid-program, old numbers are NOT converted. Treat all numbers as "user's chosen unit at log time."
- **Empty strings are common.** Fields are present but blank rather than missing.
- **Sets always have `type`.** The other fields depend on the type.
- **Runs always have `runType` from v0.5 onward.** Old data is treated as `easy`.
- **Switching run types preserves orphan data.** If you log a tempo run with HR, then switch to intervals (which doesn't display HR), the HR value stays in the JSON. It's just hidden from the UI. This is intentional — no data loss from type changes.
- **History is ordered most recent first** (`history[0]` is the newest session).
- **The `currentSession` is the live in-progress session.** When the user saves, it gets pushed onto `history` and a new empty one takes its place. `currentSession` is NOT synced to the cloud; only saved sessions are.
- **Sessions and templates carry a UUID `id` from v8 onward.** Old data without an id gets one assigned on first upload to the cloud.

## Schema version history

- **v12** (current) — Race runs gained `warmup` and `cooldown` (free text), tracked apart from the race effort. The race effort stays in `distance`/`time`/`pace` (relabeled "Race distance/time/pace" in the UI), so old race sessions, the Stats pace chart, and the pace sanity check are unaffected. Additive and backwards compatible — no DB migration (run_data is jsonb).
- **v11** — Run session data shape extended. Tempo runs gained `warmup`, `tempoDistance`, `tempoTime`, `tempoPace`, `cooldown` (work portion tracked apart from totals). Interval runs gained an `intervalSets` array (`{reps, distance, goal, recovery}` blocks) replacing the single `workout`/`targetPace` triple in the UI. Additive and backwards compatible — old run fields are preserved, no DB migration (run_data is jsonb).
- **v10** — Templates gained `run` and `conditioning` types alongside `lifts`. Run templates carry `runData` `{runType, distance, pace}`; conditioning templates carry `condData` `{modality, total}`. Cloud `templates` table gained `run_data` and `cond_data` jsonb columns (migration required — see the `templates` table section). Backwards compatible: existing lifts templates are unchanged and don't send the new columns.
- **v9** — Added `displayName` and `avatar` fields to settings (and corresponding `display_name`, `avatar` columns to the cloud `user_settings` table). Both are optional; empty values fall back to email/no avatar. Backwards compatible: old exports/imports without these fields just leave them empty.
- **v8** — Added stable UUID `id` field to sessions and templates to support cloud sync. Added cloud database schema (Supabase tables: `sessions`, `templates`, `user_settings`) with Row Level Security. Local ↔ cloud field name mapping documented. Backwards compatible: old data without `id` gets one assigned on first cloud upload.
- **v7** — Added optional `endDate` field for sessions crossing midnight. Added `distanceUnit` setting (mi/km) affecting run field labels and pace. Added inline format validation (visual red-border only, never blocks saving) and pre-save warnings for missing or inconsistent data. Backwards compatible: sessions without `endDate` are treated as same-day.
- **v6** — Cleaned up phantom defaults: `runData` and `condData` are now only populated for sessions whose `type` matches. Added session-type-switch guard in the UI to warn before hiding data. Backwards compatible: old files with phantom defaults still import fine.
- **v5** — Added `runType` field to run sessions with five types (easy, tempo, intervals, long, race), each with their own field set. Backwards compatible with v4: old runs without `runType` are treated as easy.
- **v4** — Added `schemaVersion`, `exportedAt`, optional `rir` field on working sets, and `settings` to exports.
- **v3** (implicit, no version field) — Same as v2 visually but with the polished UI redesign.
- **v2** (implicit, no version field) — Introduced four set types (warmup, working, myorep, drop), session metadata (date, start/end time, bodyweight, name, phase), templates, history, run and conditioning session types.
- **v1** (implicit, deprecated) — Original phase/day rigid program structure. Files from v1 are not supported by import.
