# Hybrid Trainer — Brand

The canonical reference for how Hybrid Trainer looks and sounds. If you're building something new (icon, marketing, a sibling app, the newsletter), start here.

---

## Name

**Hybrid Trainer** is the full product name. Use it in:
- Page titles, README headings, the app header
- Anywhere formal: app stores, official docs, legal

**Hybrid** is the short form. Use it in:
- The iOS PWA home-screen label (limited space)
- Casual references in copy
- The fitness-app branded shorthand once people know the product

Don't abbreviate to anything else (no "HT", no "HyTrain", etc).

---

## One-liner

> A workout tracker for hybrid athletes who lift, run, and condition — built to model the systemic fatigue no other app captures.

Use this when explaining what it is. Don't shorten to just "workout tracker" — the differentiator is the hybrid fatigue angle.

Variants for different contexts:

- **Shortest (for tagline / icon caption)**: "Lift. Run. Condition. Track all three."
- **For builders / technical audience**: "Open-source workout logger with cloud sync, designed around hybrid training patterns."
- **For athletes**: "Stop guessing how your lifting day affects your run pace tomorrow."

---

## Color palette

The brand color is **olive** — a tactical, military-influenced green that fits hybrid athlete culture (rucking, conditioning, GORUCK aesthetic) without being a clichéd fitness orange or generic startup blue.

### Primary

| Role | Hex | Use |
|---|---|---|
| **Accent** | `#65a30d` | Primary buttons, FAB, active tab indicator, highlights |
| **Accent hover** | `#4d7c0f` | Darker olive for hover/pressed states |
| **Accent subtle** | `#365314` | Backgrounds or borders where olive should whisper, not shout |

In dark mode, accent shifts brighter so it pops against the dark surface:
- `#84cc16` (dark mode accent)
- `#a3e635` (dark mode hover)

### Functional colors

| Role | Light | Dark | Use |
|---|---|---|---|
| **Success** | `#06b6d4` | `#22d3ee` | Sync indicator (synced), success messages, the run pace chart |
| **Info** | `#8b5cf6` | `#a78bfa` | Info messages, the 1RM chart |
| **Danger** | `#dc2626` | `#f87171` | Delete buttons, error messages, destructive confirmations |

The pattern: each functional color sits in a distinct slice of the color wheel from the brand color and from each other. Olive (green-yellow), cyan (green-blue), violet (purple), red. Maximum perceptual distance.

### Neutrals

| Role | Light | Dark |
|---|---|---|
| **Background** | `#fafafa` | `#0a0a0b` |
| **Surface** (cards) | `#ffffff` | `#131316` |
| **Surface 2** (subtle bg) | `#f4f4f5` | `#1c1c20` |
| **Border** | `#e4e4e7` | `#27272a` |
| **Text** | `#18181b` | `#fafafa` |
| **Text muted** | `#71717a` | `#a1a1aa` |
| **Text dim** | `#a1a1aa` | `#71717a` |

### Usage rules

- **One accent at a time.** A screen has at most one olive-highlighted element competing for attention. The FAB on Log, the active tab in nav, the primary button — never all three lit at once.
- **Functional colors are functional.** Cyan means success, violet means info, red means danger. Don't decorate with them.
- **Dark mode is the canonical mode.** Light mode works and is supported, but visual decisions should be made in dark first. Most users (Johnny included) keep their devices on auto-dark.
- **No gradients.** Solid colors only. Gradients don't fit the tactical-tool aesthetic.

---

## Typography

System fonts. No webfont loading.

```css
font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
```

Why: fast load, native feel on every platform, doesn't fight the OS, costs no kB.

### Monospace (for numbers)

```css
font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
```

Used for weights, reps, times, paces, anything where digits need to line up. Critical for the "tactical tool" feel — numbers in a workout log should look like numbers, not prose.

### Weights

- **400** — body text
- **600** — buttons, tab labels, emphasized fields, section headers
- **700** — h1, the app title

No light weights (300 or below). Hybrid Trainer is a tool, not a magazine.

---

## Voice

Direct. Practical. No fluff.

### Do

- **State things plainly.** "Sign in to sync workouts across devices."
- **Lead with the limit, then the instruction.** "Magic link emails take 1-2 minutes. Then click the link to sign in."
- **Be specific.** "Found 25 sessions on this device" not "Some data was detected."
- **Use the second person.** "Your data" not "the user's data."
- **Acknowledge tradeoffs honestly.** "Last write wins" is better than pretending there's perfect conflict resolution.

### Don't

- **No hype.** No "💪 CRUSH YOUR GOALS" anywhere, ever.
- **No motivational quotes.** This is a logger, not a coach.
- **No emoji in functional copy.** Emoji exist in avatars (intentional) and that's it.
- **No marketing-speak verbs.** Don't "unlock," "supercharge," or "level up" anything.
- **No exclamation points** in success messages or anywhere else. "Saved." not "Saved!"

### Examples

| Don't | Do |
|---|---|
| "Awesome! Your session was saved successfully!" | "Session saved." |
| "Oh no, something went wrong 😕" | "Couldn't reach your cloud account. Working in local mode for now." |
| "Crush your next workout! 🔥" | (Just don't say this. There is no copy in the app that says this.) |
| "Unlock cross-device sync" | "Sign in to sync." |
| "We found 25 sessions" | "Found 25 sessions on this device" |

---

## Logo / Icon guidelines

The app icon is the most visible piece of brand. It needs to:

- Read clearly at 60×60 (smallest iOS home-screen size)
- Look correct on dark and light home screen wallpapers
- Be immediately identifiable as Hybrid (not generic fitness)
- Not look like Strava, Hevy, Whoop, or Apple Fitness

### Recommended approaches

In rough order of effort vs payoff:

1. **Wordmark icon**: "HT" or "H" in olive on a dark background. Easiest to make. Reads as "tool." Risk: bland.
2. **Symbol + wordmark**: A simple barbell + run combo or a single chosen emoji on a dark olive-tinted background. Recognizable.
3. **Custom mark**: An abstract symbol representing the hybrid concept. Highest reward, highest effort. Defer until the brand is settled.

### Colors for the icon

- Primary background: `#0a0a0b` (dark background, matches the app)
- Primary mark: `#84cc16` (dark-mode accent, the brighter olive)
- Or invert: olive background, dark mark

Avoid: gradients, drop shadows, anything that "feels Web 2.0."

### Required sizes

- `icon-180.png` — 180×180, iOS home screen
- `icon-192.png` — 192×192, Android/Chrome PWA
- `icon-512.png` — 512×512, Android splash screen

Generated via realfavicongenerator.net or similar tools.

---

## Don'ts (overall)

- Don't add additional accent colors. The palette is complete.
- Don't introduce illustrations, mascots, or characters.
- Don't use stock photos anywhere.
- Don't add motivational copy, ever.
- Don't change the name without updating every reference (README, manifest, page title, etc.)

---

## When to update this doc

- New product surface (a sibling app, the newsletter, a marketing page)
- A new color is being considered (write it down before adding it to the app)
- Voice or naming changes
- Logo is finalized (replace the "in progress" guidance with the actual asset)

If you're updating it, also update `IDEAS.md` to reflect any new brand-aligned features that emerged from the conversation.
