# TCMS Design System
Version: 1.0 — established during /plan-design-review on 2026-05-28

This document is the authoritative reference for all TCMS UI decisions.
Before implementing any new UI: check this file. Before running /plan-design-review: read this file.

---

## Context: Two Distinct UIs

TCMS has two user-facing interfaces with different design requirements:

| | Internal Tool | Live Client Portal |
|--|--|--|
| Users | QA leads, delivery heads (Shorthills) | Clients (non-technical stakeholders) |
| Device | Desktop (1024px+), keyboard-first | Mobile-first, occasional desktop |
| Density | Dense, data-forward | Sparse, prose-forward |
| Trust signal | Efficiency, speed, precision | Professionalism, clarity, completeness |
| Chrome | Sidebar nav, dark topbar, tabs | No sidebar, minimal nav, single-column |

Treat these as separate design systems that share tokens.

---

## Color Tokens

```css
:root {
  /* Backgrounds */
  --color-nav-bg: #1a1a2e;         /* Top nav + project switcher */
  --color-surface: #ffffff;         /* Cards, panels, main content */
  --color-bg: #f5f5f5;              /* Page background */
  --color-bg-subtle: #f9fafb;       /* Table header, alternating rows */

  /* Borders */
  --color-border: #e5e5e5;
  --color-border-subtle: #f0f0f0;

  /* Primary (purple) */
  --color-primary: #7c6af7;
  --color-primary-hover: #6a58e5;
  --color-primary-muted: #f5f0ff;   /* Active sidebar item bg */
  --color-primary-border: #c4b5fd;  /* AI banner border, input focus ring */

  /* Text */
  --color-text-primary: #1a1a2e;    /* 17:1 on white — headings, primary labels */
  --color-text-secondary: #555;     /* Body text */
  --color-text-tertiary: #888;      /* Captions, timestamps, metadata */
  --color-text-on-dark: #ffffff;    /* Text on nav-bg */
  --color-text-muted-on-dark: #aaa; /* Secondary text on nav-bg */

  /* Status */
  --color-success: #16a34a;
  --color-success-bg: #dcfce7;
  --color-danger: #dc2626;
  --color-danger-bg: #fee2e2;
  --color-warning: #ca8a04;
  --color-warning-bg: #fef9c3;
  --color-info: #1e40af;
  --color-info-bg: #dbeafe;

  /* Portal-specific (client-facing only) */
  --color-portal-bg: #ffffff;
  --color-portal-text: #111827;
  --color-portal-accent: #7c6af7;
  --color-portal-border: #e5e7eb;
}
```

**Contrast compliance:**
- `--color-primary` (#7c6af7) on white = 3.85:1 — FAILS WCAG AA at normal text sizes
- NEVER use `--color-primary` as text color on white background at < 18px
- Badge text using primary: always use `--color-primary` on `--color-primary-muted` (not white)
- All body text: `--color-text-secondary` (#555) on white = 7.4:1 — PASSES
- `--color-text-primary` (#1a1a2e) on white = ~17:1 — PASSES

---

## Typography

```css
/* Internal Tool */
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap');

:root {
  --font-sans: 'DM Sans', system-ui, sans-serif;
  --font-mono: 'IBM Plex Mono', monospace;

  /* Scale */
  --text-xs:   11px;   /* Uppercase labels, badge text */
  --text-sm:   12px;   /* Captions, metadata, table headers */
  --text-base: 13px;   /* Default body, table cells */
  --text-md:   15px;   /* Card titles, form labels */
  --text-lg:   18px;   /* Section headings */
  --text-xl:   20px;   /* Page titles */
  --text-2xl:  24px;   /* Dashboard stat numbers */
  --text-3xl:  32px;   /* Large numbers in client portal */

  /* Weights */
  --font-normal: 400;
  --font-medium: 500;
  --font-semibold: 600;
  --font-bold: 700;
}

/* Use IBM Plex Mono for: TC-IDs (TC-001), coverage percentages, numbers in stats */
.tc-id, .coverage-pct, .stat-number {
  font-family: var(--font-mono);
}
```

**Rules:**
- DO NOT use: Inter, Roboto, Arial, -apple-system, BlinkMacSystemFont, system-ui alone
- DM Sans: all UI text (nav, sidebar, forms, tables, buttons)
- IBM Plex Mono: TC-IDs, coverage %, all tabular numbers, API keys
- Line height: 1.5 for body, 1.2 for headings, 1.0 for monospace numbers

**Client Portal typography:**
- Same fonts, larger scale: base text at 16px (not 13px)
- More line height: 1.65 for body paragraphs
- Executive summary: 18px, 1.65 line-height, `--color-portal-text`

---

## Spacing Scale

```css
:root {
  --space-px: 1px;
  --space-1:  4px;
  --space-2:  8px;
  --space-3:  12px;
  --space-4:  16px;
  --space-5:  20px;
  --space-6:  24px;
  --space-8:  32px;
  --space-10: 40px;
  --space-12: 48px;
  --space-16: 64px;
}
```

Standard component padding: `var(--space-5)` (20px) for cards, `var(--space-6)` (24px) for page content area.

---

## Border Radius

```css
:root {
  --radius-sm:   4px;   /* Input fields, small chips */
  --radius-md:   6px;   /* Buttons, tags */
  --radius-lg:   10px;  /* Cards, modals, panels */
  --radius-full: 20px;  /* Badges, status pills */
}
```

Do NOT apply the same radius to every element. Badge gets `--radius-full`, card gets `--radius-lg`, button gets `--radius-md`.

---

## Shadows

```css
:root {
  --shadow-sm:  0 1px 3px rgba(0,0,0,0.06);      /* Card resting state */
  --shadow-md:  0 4px 12px rgba(0,0,0,0.08);     /* Dropdown, modal backdrop */
  --shadow-lg:  0 8px 24px rgba(0,0,0,0.12);     /* Drawer, popover */
  --shadow-focus: 0 0 0 3px rgba(124,106,247,0.15); /* Input/button focus ring */
}
```

---

## Components

### Buttons

```css
/* Primary */
.btn-primary {
  background: var(--color-primary);
  color: white;
  padding: var(--space-2) var(--space-4);  /* 8px 16px */
  border-radius: var(--radius-md);
  font-size: var(--text-base);
  font-weight: var(--font-medium);
  height: 36px;
  min-width: 44px; /* touch target */
}
.btn-primary:hover { background: var(--color-primary-hover); }
.btn-primary:focus { box-shadow: var(--shadow-focus); }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

/* Secondary */
.btn-secondary { background: white; border: 1px solid var(--color-border); color: var(--color-text-primary); }
/* Ghost */
.btn-ghost { background: none; border: 1px solid var(--color-primary); color: var(--color-primary); }
```

### Badges / Status Pills

```css
/* Always: text on tinted background. NEVER primary text on white. */
.badge { font-family: var(--font-mono); font-size: var(--text-xs); font-weight: var(--font-semibold); border-radius: var(--radius-full); padding: 2px 8px; }
.badge-pass    { background: var(--color-success-bg); color: var(--color-success); }
.badge-fail    { background: var(--color-danger-bg);  color: var(--color-danger); }
.badge-skip    { background: var(--color-warning-bg); color: var(--color-warning); }
.badge-draft   { background: #f3f4f6; color: #4b5563; }
.badge-active  { background: var(--color-info-bg); color: var(--color-info); }
.badge-attention { background: var(--color-warning-bg); color: var(--color-warning); }
```

### Form Inputs

```css
.form-input {
  font-family: var(--font-sans);
  font-size: var(--text-base);
  padding: var(--space-2) var(--space-3);   /* 8px 12px */
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  height: 36px;
  width: 100%;
}
.form-input:focus {
  border-color: var(--color-primary);
  box-shadow: var(--shadow-focus);
  outline: none;
}
.form-input:disabled { background: var(--color-bg); opacity: 0.6; }
```

### Progress Bar

```css
/* Coverage bar in project table */
.progress-bar { height: 6px; background: var(--color-border); border-radius: 3px; }
.progress-fill { height: 100%; background: var(--color-primary); border-radius: 3px; transition: width 0.3s ease; }
.progress-fill.warning { background: var(--color-warning); }  /* < 70% coverage */
.progress-fill.danger  { background: var(--color-danger); }   /* < 40% coverage */
```

### Sidebar Navigation

```css
/* Dashboard: sidebar shows project list */
/* Inside project: sidebar shows test case sections */
.sidebar { width: 220px; background: var(--color-surface); border-right: 1px solid var(--color-border); }
.sidebar-item { padding: var(--space-2) var(--space-5); font-size: var(--text-base); color: var(--color-text-secondary); border-left: 3px solid transparent; cursor: pointer; }
.sidebar-item:hover { background: var(--color-bg); }
.sidebar-item.active { border-left-color: var(--color-primary); color: var(--color-text-primary); font-weight: var(--font-semibold); background: var(--color-primary-muted); }
.sidebar-section-label { padding: var(--space-3) var(--space-5) var(--space-1); font-size: var(--text-xs); color: var(--color-text-tertiary); text-transform: uppercase; letter-spacing: 0.5px; }
```

---

## Interaction States Baseline

Every interactive element must have these states defined:

| State | Visual treatment |
|-------|-----------------|
| Default | Base styles above |
| Hover | Slightly darker bg or border |
| Focus | `box-shadow: var(--shadow-focus)` + `border-color: var(--color-primary)` |
| Active / Pressed | Scale(0.98) + slightly darker |
| Disabled | `opacity: 0.5` + `cursor: not-allowed` |
| Loading | Replace label with spinner, maintain dimensions |
| Error | `border-color: var(--color-danger)` + helper text below in danger color |
| Success | Brief green flash, then returns to default |

---

## AI Generate Animation

**Pattern: CSS stagger reveal (not true SSE)**

Backend returns all test cases in one response. Frontend reveals them sequentially:

```css
.tc-card { opacity: 0; transform: translateY(8px); animation: card-appear 0.25s ease forwards; }
.tc-card:nth-child(1) { animation-delay: 0ms; }
.tc-card:nth-child(2) { animation-delay: 150ms; }
.tc-card:nth-child(3) { animation-delay: 300ms; }
.tc-card:nth-child(4) { animation-delay: 450ms; }
.tc-card:nth-child(5) { animation-delay: 600ms; }

@keyframes card-appear {
  to { opacity: 1; transform: translateY(0); }
}
```

While waiting (before response): pulse animation on AI banner + "Generating X test cases..." label + disabled button.

---

## AI Criticism Drawer

- **Desktop:** Right overlay, 380px width, slides in from right edge of Test Editor. Does NOT push content. Dim overlay backdrop (rgba(0,0,0,0.25)).
- **Tablet < 1024px:** Full-width bottom sheet, 60vh max height, slides up.
- **Mobile < 768px:** Same as tablet.
- **Loading state:** 3 shimmer skeleton lines ("Finding edge cases...", "Checking step clarity...", "Reviewing expected results...")
- **Close:** `Escape` key or X button in drawer header. Focus returns to trigger button.

---

## Execution Runner Keyboard Shortcuts

| Key | Action | Conflict check |
|-----|--------|----------------|
| j | Next test case | Safe (no standard browser binding) |
| k | Previous test case | Safe |
| p | Mark PASS | Safe |
| f | Mark FAIL | Safe |
| s | Mark SKIP | Safe |
| b | Mark BLOCKED | Safe — browser uses Ctrl+B for bold |
| e | Open notes drawer | Safe |
| ? | Toggle shortcut help overlay | Safe |
| Escape | Close notes drawer / help overlay | Standard expected behavior |

Shortcuts DISABLED when:
- A text input has focus (notes field, search bar)
- Any modal is open

**Mobile:** Shortcuts not available. Touch alternatives:
- Swipe right on test case row → PASS (green flash)
- Swipe left → FAIL (red flash)
- Tap status button → opens pass/fail/skip/blocked picker
- Tap notes icon → opens notes sheet

---

## Dashboard: "Needs Attention" Logic

Fixed thresholds (hardcoded, not user-configurable):
- `coverage_pct < 70` → "Needs attention" (yellow badge)
- `days_since_last_run > 14` → "Needs attention" (yellow badge)
- Both: same badge

Projects meeting either condition float to the top of the project table.
All other projects sorted by last modified desc.

---

## Responsive Breakpoints

| Breakpoint | Layout | Sidebar |
|------------|--------|---------|
| ≥ 1024px (desktop) | Sidebar + main, full width | 220px, always visible |
| 768–1023px (tablet) | Sidebar + main | Collapsed to 48px icon strip, expands on click |
| < 768px (mobile) | Single column | Hidden. Bottom nav bar: Dashboard / Project / Settings |

Mobile top nav: logo + page title + user avatar. No project switcher in top nav on mobile (use bottom nav).

---

## Live Client Portal (Read-only, Public)

Complete separate design. Do not reuse internal tool components without modification.

**Layout:**
```
┌──────────────────────────────────────────────────┐
│  [Shorthills logo sm]              [QA Team name] │  header: white, border-bottom
├──────────────────────────────────────────────────┤
│  Project Name                                     │  h1, 28px, text-primary
│  Client Name · Sprint 3 · 2026-05-28             │  14px, text-tertiary
├──────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────┐ │
│  │ "Coverage improved 12% this sprint. All     │ │  executive summary card
│  │ P1 issues from last report are resolved."   │ │  18px, left border primary
│  └─────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────┤
│      94%          3          8                    │  3 large numbers
│     PASSED      FAILED     SKIPPED               │  monospace, centered
├──────────────────────────────────────────────────┤
│  [Test case table: Title | Priority | Status]     │  simplified, accordion steps
│  TC-001  Login happy path          HIGH  ✓ PASS  │
│  TC-002  Invalid password          HIGH  ✗ FAIL  │
│  ...                                              │
└──────────────────────────────────────────────────┘
│  Generated by TCMS · Shorthills.ai · Valid until  │  footer
│  2026-06-28                                       │
```

**Typography:** 16px base (vs 13px internal), DM Sans, 1.65 line-height
**Mobile:** Max width 800px, centered with 16px padding. Single column. Table scrolls horizontally.
**Print:** `@media print` — hide all interactive elements, expand all accordion rows, black/white safe.
**Error states:**
- 410 Gone: full-page "This report link has expired." (no sidebar, Shorthills logo, contact details)
- 404: same pattern
- 503: "Report temporarily unavailable. Try again in a few minutes."

---

## Template Modal

Three packs. Modal, not inline:
- Title: "Start with a template"
- 3 cards in a row: react-crud (34 cases), rest-api (28 cases), mobile (22 cases)
- Each card: name, case count, 3-line scrollable preview of sample titles
- Selected card: primary border + checkmark
- CTA: "Import [N] test cases" (disabled until selection)
- Conflict behavior: "This project already has X test cases. These templates will be added alongside them." (info banner in modal footer)

---

## Not in Scope (Design Deferred)

- **Dark mode:** Not in v1. Token system is dark-mode-ready (`color-scheme: light` in root).
- **Custom report branding:** Client portal uses Shorthills branding only. Per-client logo upload is v2.
- **JIRA/Linear integration UI:** Freetext `jira_ref` only in v1. No deep link styling.
- **Animation library:** No Framer Motion or GSAP. CSS animations only. Keeps bundle small.
- **Emoji/icons in nav:** No emoji. Icon library decision deferred — use text labels in MVP to avoid icon-in-circle slop.

---

## What Already Exists

From `docs/tcms-wireframe.html`:
- Dark nav `#1a1a2e` — keep, locked in as `--color-nav-bg`
- Purple accent `#7c6af7` — keep, locked in as `--color-primary`
- Sidebar left-border active state — keep, already in component spec above
- Table layout for projects — keep structure, update typography
- Client report gradient header — REPLACE with client portal spec above
- System fonts — REPLACED with DM Sans + IBM Plex Mono

---
_Last updated: 2026-05-28 by /plan-design-review_
