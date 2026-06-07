# Hybrid Trainer Data Schema

This document describes the data format used by the Hybrid Trainer app. The format is intentionally simple and exportable so you can do whatever you want with your data: analyze it in a spreadsheet, build your own tools, import it into another app, or feed it to a script that calculates fatigue scores.

## Current schema version: 16

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
  "notes": "Really not into it today",
  "importSource": ""
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
| `importSource` | string | Stable id of an external source this session was imported from, used to skip duplicates on re-import. Empty for hand-logged sessions. Added in v15. Format `<source>:<id>` — e.g. Hevy CSV import uses `hevy:<start_time>\|<title>`. |

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

Sets have a `type` field that determines the rest of the shape. Four types.

Any set may also carry an optional **`done`** boolean (added v16) — set `true` when the user ticks the per-set "done" checkbox in the Log form to mark that set complete. Absent/`false` on older sets and on sets never checked; backwards compatible (it's just an extra key in the `exercises` jsonb, no migration). A transient `_prefilled` marker is used in-memory while logging (it flags a set whose empty fields were auto-filled from the last session so they aren't re-filled after you clear them) and is stripped before a session is saved, so it never appears in stored data.

The four types:

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

Type-based as of v0.19.0 (schema v13), mirroring run types. `condType` selects the field set. Types and their fields:

- **`erg`** (Row/Bike/Ski) — `machine`, `distance`, `time`, `split` (/500m), `watts`, `cal`, `hr`, `rpe`, `notes`
- **`sled`** (Sled/Carry) — `movement`, `load`, `distance`, `rounds`, `time`, `rpe`, `notes`
- **`ruck`** — `load`, `distance`, `time`, `pace`, `elevation`, `hr`, `rpe`, `notes`
- **`metcon`** (Circuit/MetCon) — `format`, `duration`, `rounds`, `movements`, `rpe`, `notes`
- **`circuit`** (Hyrox/WOD, v0.20.0) — `format`, `totalTime`, `result`, `rpe`, `notes`, plus a `segments` array (see below)
- **`other`** (General) — `modality`, `total`, `rpe`, `splits`, `notes`

The `circuit` type adds a repeatable **`segments`** array, modeled on run `intervalSets`. Each entry is `{ label, target, result }` (all strings). Used for Hyrox races (8 runs + 8 stations) and CrossFit WODs (movement list). The array is only written once a segment is added — a blank form has no `segments` key, so it isn't flagged as having content. Switching away from `circuit` keeps the array in the JSON (hidden, not deleted), same as orphaned fields.

```json
{
  "condType": "circuit",
  "format": "Hyrox",
  "totalTime": "1:12:30",
  "result": "23rd OA",
  "rpe": "9",
  "segments": [
    { "label": "Run 1km", "target": "1000m", "result": "4:32" },
    { "label": "SkiErg", "target": "1000m", "result": "3:58" }
  ],
  "notes": ""
}
```

```json
{
  "condType": "erg",
  "machine": "Row",
  "distance": "5000m",
  "time": "20:00",
  "split": "2:00",
  "watts": "205",
  "hr": "155",
  "rpe": "7",
  "notes": ""
}
```

**Backwards compatibility:** pre-v0.19.0 conditioning sessions had no `condType` and used `modality`/`total`/`rpe`/`splits`. On display they map to the `other` type (whose fields are exactly those keys), so old data still shows. New sessions default to `erg`. Switching type preserves orphaned fields in the JSON (hidden, not deleted), same as run types. No DB migration (`cond_data` is jsonb). Conditioning *templates* still store `{modality, total}` targets and load as the `other` type.

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

**Circuit template** (Hyrox/WOD, added v0.21.0) — a `circuit` conditioning template that carries the segment skeleton. `segments` hold `label`/`target` with `result` left blank, so loading the template gives you the prescription to fill in:

```json
{
  "id": "...",
  "name": "Hyrox",
  "type": "conditioning",
  "exercises": [],
  "condData": {
    "condType": "circuit",
    "format": "Hyrox",
    "segments": [
      { "label": "Run 1km", "target": "1000m", "result": "" },
      { "label": "SkiErg", "target": "1000m", "result": "" }
    ]
  }
}
```

Built-in presets (Hyrox, Fran, Murph, Cindy) ship in code as `WORKOUT_PRESETS` — circuit templates surfaced in the "Browse starter templates" section so they work offline with no Supabase seeding. "Add" deep-copies one into your own templates. Saving a logged circuit session as a template (`saveCurrentAsTemplate`) keeps `format` + segment `label`/`target` and drops the `result` values.

**As of v0.22.0 the `+New template` builder is config-driven over `COND_TYPES`:** pick any conditioning type (erg/sled/ruck/metcon/circuit/other) and the builder renders that type's fields, plus a segment editor (label + target only) for `circuit`. `saveTemplateDraft` stores `condType` + whatever fields you filled (blank fields are dropped). `saveCurrentAsTemplate` likewise preserves the session's `condType` and field values. So a conditioning template can now carry any type, not just `{modality, total}`. Legacy templates with no `condType` still display as modality/target.

**As of v0.24.0 the run path of the builder is also config-driven, over `RUN_TYPES`:** pick any run type (easy/tempo/intervals/long/race) and the builder renders that type's fields, plus a reps×distance@goal+recovery interval-set editor for `intervals` (stored in `runData.intervalSets`). `saveTemplateDraft` stores `runType` + filled fields (blanks dropped); a run template may legitimately be type-only (no targets). So a run template now carries any type's targets, not just `{runType, distance, pace}`. Loading a run or conditioning template deep-copies its `runData`/`condData` so editing the session can't mutate the saved template's arrays. Still no schema change — `run_data`/`cond_data` are jsonb.

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

## Importing your own data (additive, app v0.27.0)

Two different imports exist, and they behave very differently:

- **"Restore from backup" (full backup, JSON)** — REPLACES all current data with the file's contents. Use this to restore a complete backup. Lives under **Settings → Data → Backup & restore** (alongside "Export all data").
- **Importing workouts (additive)** — ADDS workouts without touching what's already there. Surfaced via an **Import workouts** button in two places (**Settings → Data** and the **History tab**), which opens a chooser of sources (Hevy CSV, Garmin "coming soon", or "from notes/a photo/another app" = the AI paste flow). The paste flow accepts one [Session object](#session-object) or an array of them (a `{ "history": [...] }` or `{ "sessions": [...] }` wrapper is also accepted). All additive paths feed a reusable merge core (`mergeImportedSessions`) that any future source (a Garmin file parser, an AI reader, account merge) can call.

Rules the importer applies, so AI- or hand-authored JSON is forgiving:

- A single session loads into the in-progress slot on the **Log tab for review** before you save; multiple sessions merge straight into `history`.
- Batches **dedupe by `id`** — a session whose `id` already exists in your history is skipped. Sessions without an `id` get a fresh one (so they always import; re-pasting the same id-less JSON can double-import).
- Missing/invalid `type` defaults to `lifts`; missing `date` defaults to today; run sessions get `runType: "easy"` if absent.
- **All numbers are coerced to strings** (the app stores strings), so JSON with real numbers (e.g. `"reps": 10` vs `10`) both work.
- Unknown top-level keys are dropped. **Units are not converted** — values must already be in the user's display units (the "Copy AI prompt" button bakes the current units into the prompt for this reason).

This import does not change the data shape, so it is not tied to `SCHEMA_VERSION`.

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
| `import_source` | text | Nullable. Maps to local `importSource`; empty string → null. Added in v15. |
| `created_at` | timestamptz | Server-set on insert. |
| `updated_at` | timestamptz | Updated on every write. |

Indexes: `(user_id, date desc)`, `(user_id, type)`.

Migration to add the v15 column (run once in the Supabase SQL editor):

```sql
alter table sessions add column if not exists import_source text;
```

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

### `feedback` table (app v0.26.0)

Bug reports and feature requests submitted from inside the app (Settings → Feedback). NOT tied to `SCHEMA_VERSION` (it doesn't affect the export/session data shape — same as `starter_templates`). Insertable by anyone, including anonymous users; there is **no select policy**, so clients can't read it — reports are read in the Supabase dashboard.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid (PK) | `gen_random_uuid()` default. |
| `user_id` | uuid | Nullable. `auth.users(id)` `on delete set null`. Null for anonymous submissions. |
| `type` | text | `bug` or `feature`. |
| `message` | text | The report. Client caps input at 2000 chars. |
| `contact` | text | Optional email/name for a reply. |
| `app_version` | text | The app's `APP_VERSION` at submit time (e.g. `v0.26.0`). |
| `context` | jsonb | `{ signedIn, email, mode, screen, ua }` captured client-side. |
| `created_at` | timestamptz | Server-set. |

```sql
create table if not exists feedback (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete set null,
  type text not null check (type in ('bug','feature')),
  message text not null,
  contact text,
  app_version text,
  context jsonb,
  created_at timestamptz default now()
);
alter table feedback enable row level security;
-- Anyone (incl. anonymous) may submit; a signed-in user can only attribute to
-- themselves (or leave it null). No select policy => clients cannot read feedback.
create policy "anyone can submit feedback"
  on feedback for insert
  with check (user_id is null or auth.uid() = user_id);
```

### Row Level Security

The three per-user tables (`sessions`, `templates`, `user_settings`) have RLS enabled with a single policy each: `auth.uid() = user_id`. The anon/publishable key embedded in the client cannot read or write anyone else's rows. If you write your own tooling against the Supabase API, you'll need to sign in as the user you're querying for. `starter_templates` is public-readable (`select using (true)`); `feedback` is insert-only for clients (no select policy, so reports stay private).

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

- **v15** (current) — External data import. Adds a session-level `importSource` field (and an `import_source` text column on the `sessions` table — one-line migration, see the `sessions` table section) so the same imported workout isn't added twice on re-import. Format `<source>:<id>`. First consumer is the **Hevy CSV import** (app v0.25.0), which sets `hevy:<start_time>|<title>` and maps each Hevy workout to a `lifts` session (one exercise per `exercise_title`, so supersets split; each drop-set row becomes its own working set). Additive and backwards compatible — old sessions have no `importSource` (treated as empty); the DB column is nullable. The field is generic and reusable by future GPX/TCX/FIT/Strava imports. (The originally-planned first source was GPX/TCX; Hevy CSV shipped first because it maps cleanly to the existing lifts model with no new dependency.)
- **v14** — Added the `circuit` conditioning type (Hyrox/WOD): `format`, `totalTime`, `result`, `rpe`, `notes`, plus a repeatable `segments` array (`{label, target, result}` rows, modeled on run `intervalSets`). For segment-based events — Hyrox races and CrossFit WODs. Additive and backwards compatible — no DB migration (`cond_data` is jsonb). `segments` is only written once a row is added, so blank forms aren't flagged as having content. *App v0.21.0* added circuit *templates* on top of this (built-in Hyrox/WOD presets in `WORKOUT_PRESETS`, deep-copied on add/load) — same `condData` shape, no schema change. *App v0.22.0* made the `+New template` builder config-driven over `COND_TYPES`, so any conditioning type (with a segment editor for circuit) can be hand-built — still the same `condData` shape, no schema change. *App v0.23.0* aligned the `SCHEMA_VERSION` constant to 14 (it had been left at 13 when circuit shipped in v0.20.0) and fixed an in-progress-session data-loss bug — no shape change. *App v0.24.0* added the Finish & Save end-time flow, made run templates config-driven over `RUN_TYPES`, and added History-tab import/export — all no shape change.
- **v13** — Conditioning is now type-based (like run types). `condData` gained `condType` (`erg`/`sled`/`ruck`/`metcon`/`other`) and per-type fields. Pre-v13 conditioning sessions (`modality`/`total`/`rpe`/`splits`, no `condType`) map to the `other` type on display, so old data is preserved. Additive and backwards compatible — no DB migration (`cond_data` is jsonb).
- **v12** — Race runs gained `warmup` and `cooldown` (free text), tracked apart from the race effort. The race effort stays in `distance`/`time`/`pace` (relabeled "Race distance/time/pace" in the UI), so old race sessions, the Stats pace chart, and the pace sanity check are unaffected. Additive and backwards compatible — no DB migration (run_data is jsonb).
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
