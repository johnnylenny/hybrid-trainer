# Skylime Design System

This is the design system for all apps, dashboards, and interfaces built by [your name/company]. Apply this system to every screen you build unless explicitly told otherwise. If a request conflicts with this system, flag the conflict before proceeding rather than silently picking one or the other.

## How to use this file

Reference this file at the start of every new project (paste it into CLAUDE.md, or link to it). If output starts drifting from these rules during a long session, the fix is to say "check Skylime" and Claude Code should re-read this file and correct course. This file defines WHAT the system is. It does not enforce itself — review your own output against it periodically.

---

## 1. Brand identity

Skylime pairs a confident, technical blue with a sharp lime accent. The blue carries trust and competence (this is software people rely on for real work). The lime is the personality color — used sparingly, it signals "this isn't another boring enterprise tool." Blue does the heavy lifting. Lime is seasoning, not the meal.

Tone: clean, confident, slightly understated. Not playful/cute. Not corporate/stiff. Closer to "modern fintech operations tool" than "consumer app" or "AI hype startup."

---

## 2. Color tokens

### Light mode (default for build/testing)

```css
--skylime-bg-primary: #F7F8F7;       /* page background */
--skylime-bg-surface: #FFFFFF;       /* card/component background */
--skylime-bg-surface-muted: #F1F2F0; /* subtle fills, hover states */

--skylime-text-primary: #141210;     /* headings, primary content */
--skylime-text-secondary: #6B6F6A;   /* labels, muted text, captions */
--skylime-text-tertiary: #9A9D97;    /* placeholders, disabled text */

--skylime-border-default: #E2E4E1;
--skylime-border-strong: #D5D8D4;

--skylime-blue: #1C80CD;             /* primary brand color, primary buttons, links */
--skylime-blue-hover: #176BAC;
--skylime-blue-subtle-bg: #E6F1FB;   /* badge/pill backgrounds */
--skylime-blue-subtle-text: #0C447C; /* text on blue-subtle-bg */

--skylime-lime: #CBF857;             /* secondary accent ONLY — see usage rules below */
--skylime-lime-text-on: #1A2306;     /* text/icon color when placed ON lime background */

--skylime-shadow-card: 0 2px 8px rgba(20, 18, 16, 0.10); /* the ONLY approved shadow value */
```

### Dark mode (tokens exist now, default flips to dark once app ships)

```css
--skylime-bg-primary: #0F1113;
--skylime-bg-surface: #1B1E22;
--skylime-bg-surface-muted: #22262A;

--skylime-text-primary: #F3F4F2;
--skylime-text-secondary: #8C9298;
--skylime-text-tertiary: #5C6066;

--skylime-border-default: #272B30;
--skylime-border-strong: #33383E;

--skylime-blue: #3D9FEB;             /* lighter than light-mode blue — full saturation glows on dark bg */
--skylime-blue-hover: #56A5E3;
--skylime-blue-subtle-bg: #173A57;
--skylime-blue-subtle-text: #85B7EB;

--skylime-lime: #A8C93D;             /* desaturated from light-mode lime — full brightness is unreadable/glowing on dark */
--skylime-lime-text-on: #10160A;

--skylime-shadow-card: 0 2px 8px rgba(0, 0, 0, 0.35);
```

**Rule: never reuse a light-mode hex value in dark mode or vice versa.** The blue and lime are deliberately different shades per mode. This is not optional — using light-mode lime (`#CBF857`) at full brightness on a dark background will look broken.

### Status colors — completely separate from brand colors

These are for success/warning/error states only (paid/pending/overdue badges, form validation, alerts). Never use Skylime blue or lime for status meaning, and never use these for brand/decorative purposes.

```css
/* Light mode */
--status-success-bg: #EAF3DE;   --status-success-text: #27500A;
--status-warning-bg: #FAEEDA;   --status-warning-text: #633806;
--status-error-bg:   #FCEBEB;   --status-error-text:   #791F1F;

/* Dark mode */
--status-success-bg: #1F3309;   --status-success-text: #97C459;
--status-warning-bg: #3D2E0A;   --status-warning-text: #EF9F27;
--status-error-bg:   #3D1414;   --status-error-text:   #F09595;
```

**Why this separation exists:** lime sits visually close to "success green" conventions. If brand lime and status-success ever shared a color family, badges and buttons would blur together and the brand accent would lose its meaning. Keep them in separate, named token groups always.

---

## 3. Typography

- **Body and UI text:** Plus Jakarta Sans (Google Fonts, free). Weights used: 400 (regular), 500 (medium). Do not use 600/700 — too heavy for this system.
- **Serif accent:** Fraunces (Google Fonts, free). **Restricted use only** — see rule below.

```css
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500&family=Fraunces:opsz,wght@9..144,400;9..144,500&display=swap');

--font-sans: 'Plus Jakarta Sans', system-ui, sans-serif;
--font-serif: 'Fraunces', Georgia, serif;
```

**Serif usage rule (strict):** Fraunces is used ONLY for two cases — large hero/stat numbers (e.g. a big "$48,200" metric, a landing page headline number) and standalone pull-quotes/testimonials. It is never used for body copy, navigation, buttons, form labels, table content, or regular headings. If you're unsure whether something qualifies, default to sans-serif.

### Type scale

```css
--text-xs: 12px;    /* captions, badges */
--text-sm: 13px;    /* labels, secondary text */
--text-base: 14px;  /* body, table content, form inputs */
--text-md: 16px;    /* default paragraph text on marketing pages */
--text-lg: 18px;    /* card titles, h3 */
--text-xl: 22px;    /* h2, stat numbers (sans) */
--text-2xl: 28px;   /* h1 on app screens */
--text-3xl: 40px;   /* marketing hero headline */
--text-hero-serif: 56px; /* Fraunces, big stat callouts / hero numbers only */

/* Weight: 400 default, 500 for headings and emphasis. Never 600+. */
```

---

## 4. Spacing scale

Use this scale exclusively — don't invent arbitrary px values mid-build.

```css
--space-1: 4px;
--space-2: 8px;
--space-3: 12px;
--space-4: 16px;
--space-5: 20px;
--space-6: 24px;
--space-8: 32px;
--space-10: 40px;
--space-12: 48px;
```

Card internal padding: `20px` (`--space-5`). Gap between cards in a grid: `12px` (`--space-3`). Section spacing on marketing pages: `48px`–`80px` between major sections.

---

## 5. Corner radius

```css
--radius-sm: 8px;    /* badges, small inline elements */
--radius-md: 14px;   /* cards, inputs, dropdowns */
--radius-full: 999px; /* buttons only */
```

Buttons are always fully rounded (pill shape). Cards and inputs use `--radius-md`. Badges/pills use `--radius-full` as well (badges read as small pills, consistent with buttons).

---

## 6. Components

### Buttons

Shape: always pill (`border-radius: 999px`).

**Primary button** (main action per screen, e.g. "Create invoice"):
```css
background: var(--skylime-blue);
color: #FFFFFF;
border: none;
padding: 10px 20px;
font-size: 14px;
font-weight: 500;
```
Hover: `background: var(--skylime-blue-hover)`.

**Secondary/accent button** (a genuinely secondary action you want to stand out — used sparingly, max one per screen alongside a primary button):
```css
background: var(--skylime-lime);
color: var(--skylime-lime-text-on);
border: none;
padding: 10px 20px;
font-size: 14px;
font-weight: 500;
```

**Outline button** (tertiary actions, cancel, "view more"):
```css
background: transparent;
color: var(--skylime-blue);
border: 1.5px solid var(--skylime-blue);
padding: 9px 20px;
```

**Rule:** never use lime for more than one button per screen. If lime starts appearing on every button, it stops being an accent and starts being wallpaper — defeats the purpose.

### Cards

Style: lifted (soft shadow), not bordered-only.
```css
background: var(--skylime-bg-surface);
border: 0.5px solid var(--skylime-border-default);
border-radius: var(--radius-md);
padding: 20px;
box-shadow: var(--skylime-shadow-card); /* use the exact value above — do not improvise shadow values */
```

### Tables

Style: bordered rows, no zebra striping.
```css
/* Row */
border-bottom: 0.5px solid var(--skylime-border-default);
padding: 10px 6px;
font-size: 14px;

/* Last row: no border-bottom */
```
Status values inside tables use status badges (see below), never plain colored text.

### Status badges

```css
background: var(--status-{success|warning|error}-bg);
color: var(--status-{success|warning|error}-text);
font-size: 11px;
padding: 3px 10px;
border-radius: 999px;
font-weight: 500;
```

### Inputs / selects

```css
background: var(--skylime-bg-surface);
border: 0.5px solid var(--skylime-border-strong);
border-radius: var(--radius-md);
padding: 9px 10px;
font-size: 14px;
color: var(--skylime-text-primary);
```
Focus state: `box-shadow: 0 0 0 3px var(--skylime-blue-subtle-bg); border-color: var(--skylime-blue);`

### Icons

Use Lucide (lucide-react for React projects, or the SVG/web font for plain HTML). Outline style only, never filled/solid icon variants. Default size 16–20px inline, 24px max for decorative use. Icons inherit text color from their context — don't hardcode icon colors separately from surrounding text.

---

## 7. What NOT to do (drift prevention)

- Don't use lime as a background fill for large areas (hero sections, page backgrounds). It's a small-surface accent only.
- Don't use lime or blue for status/semantic meaning (success, warning, error). Use the separate status token set.
- Don't use Fraunces (serif) outside of hero stat numbers and pull-quotes.
- Don't invent new shadow values. Use `--skylime-shadow-card` everywhere a shadow is needed.
- Don't mix button shapes. Every button in the system is a pill. If a design calls for a non-pill button, that's a sign to stop and check this file rather than improvise.
- Don't reuse light-mode hex values in dark mode. Each mode has its own tuned token set above.
- Don't use font weights above 500 anywhere.

---

## 8. Quick reference for prompting Claude Code

When starting a new project or component, a good opening instruction is:

> "Use the Skylime design system (paste SKYLIME.md or reference its path). Build in light mode first using the light-mode tokens, but define dark-mode tokens alongside so dark mode can be enabled later without a rebuild."

If output drifts (wrong button shape, wrong shadow, lime overused, serif misapplied), say: "This doesn't match Skylime — check section [X]" and reference the specific rule.
