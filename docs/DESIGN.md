# Lift List — Design Guide

| Field | Value |
|---|---|
| Status | v1 |
| Related docs | [`PRD.md`](./PRD.md), [`TECH_SPEC.md`](./TECH_SPEC.md) |

---

## 1. Design principles

1. **Gym-first.** Large targets, few taps, readable at arm's length, one hand.
2. **One thing per screen during a workout.** The set entry screen shows only the current set.
3. **Minimal and neutral.** In the spirit of Strong and Apple Fitness: dark surfaces, clean type, one accent color. No gradients, no decorative imagery.
4. **Numbers are the hero.** Weights, reps, and timers use large tabular figures.
5. **Color means something.** Blue = action. Amber = attention (increase flag, PRs, made up). Green = done. Red = missed or destructive.

## 2. Color tokens

Implement as CSS custom properties and as two DaisyUI themes: `liftlist-dark` (default) and `liftlist-light`. Components must use tokens, never raw hex values.

| Token | Dark (default) | Light | Usage |
|---|---|---|---|
| `--ll-bg` | `#0B0D10` | `#F5F6F8` | Page background |
| `--ll-surface` | `#15181D` | `#FFFFFF` | Cards, sheets, tab bar |
| `--ll-surface-2` | `#1F242B` | `#EEF0F3` | Inputs, pressed states, nested cards |
| `--ll-border` | `#2A3038` | `#DDE1E6` | Dividers, card borders |
| `--ll-text` | `#F2F4F7` | `#0F1115` | Primary text |
| `--ll-text-muted` | `#9AA3AF` | `#5B6470` | Secondary text, labels, "Last time" |
| `--ll-primary` | `#2B7FFF` | `#0A6CFF` | Electric blue: primary buttons, active tab, links, focus ring |
| `--ll-primary-soft` | `#2B7FFF26` | `#0A6CFF1A` | Selected chips, highlight backgrounds |
| `--ll-on-primary` | `#FFFFFF` | `#FFFFFF` | Text on primary |
| `--ll-accent` | `#FF9F0A` | `#D97A00` | Amber: increase flag, PR badges, made-up |
| `--ll-success` | `#30D158` | `#1FA34A` | Completed |
| `--ll-danger` | `#FF453A` | `#E5383B` | Missed, delete, errors |
| `--ll-info` | `#64D2FF` | `#0091C2` | Unscheduled session dots, secondary chart series |

**Chart palette** (in order): primary, info, accent, success, `#BF5AF2`, `#FF375F`, `#AC8E68`, `#8E8E93`. Muscle-group colors are assigned from this palette in fixed order so a group is always the same color.

Contrast: all text/background pairs must meet WCAG AA (4.5:1 body text, 3:1 large text and icons).

## 3. Typography

- **Font:** system stack, with no web fonts to download:
  `-apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif`
- **Numbers:** `font-variant-numeric: tabular-nums` everywhere numbers appear.

| Style | Size / weight | Use |
|---|---|---|
| Display | 64 px / 700 | Rest timer |
| Number-lg | 32 px / 700 | Weight and reps inputs on set screen |
| H1 | 28 px / 700 | Screen titles |
| H2 | 20 px / 600 | Section titles, exercise name on set screen |
| Body | 16 px / 400 | Default. **All inputs ≥ 16 px** (prevents iOS zoom on focus). |
| Label | 14 px / 500 | Field labels, chips, tab labels |
| Caption | 13 px / 400 | Muted helper text, "Last time" line |

## 4. Spacing, shape, elevation

- 4 px spacing grid. Common steps: 4, 8, 12, 16, 24, 32.
- Screen padding: 16 px phone, 24 px iPad.
- Radius: cards 16 px, buttons and inputs 12 px, chips full pill.
- Elevation: no heavy shadows. In dark mode, separate layers with surface color and 1 px border. Bottom sheets may use a subtle shadow.
- Motion: 150–200 ms ease-out for sheets and screen swaps. Respect `prefers-reduced-motion` (no slide animations).

## 5. Layout and navigation

**Phone (< 768 px)**
- Top bar: screen title (left), gear icon → Settings (right).
- Bottom tab bar (fixed, safe-area aware), 5 tabs with icon and label: **Today · Plan · Library · History · Stats**.
- During a workout (Runner), the tab bar is hidden. The top bar shows **✕ Exit** (back to Today; the session stays in progress), the session title, and the ⋮ menu.

**iPad / desktop (≥ 768 px)**
- Left sidebar with the same 5 destinations and Settings at the bottom.
- Content max-width 1100 px. Runner screens are centered with max-width 480 px.

**Icons:** Lucide icons (inline SVG). Today = `calendar-check`, Plan = `clipboard-list`, Library = `library`, History = `history`, Stats = `chart-line`, Settings = `settings`.

## 6. Components

| Component | Spec |
|---|---|
| **Button: primary** | Full width on phone, 56 px tall, primary bg, 17 px / 600 label. One per screen. |
| **Button: secondary** | 48 px, surface-2 bg, text color. |
| **Button: ghost** | Text-only, primary color. For "+ Add set", "Skip set". |
| **Button: danger** | Danger text on surface; filled danger only inside confirm dialogs. |
| **Card** | Surface bg, 1 px border, 16 px radius, 16 px padding. |
| **Stepper input** | `[ − ] [ value ] [ + ]`. Value field 32 px bold, centered, `inputmode="decimal"` (weight) or `"numeric"` (reps). Buttons 48×48. Weight step 5 lb; reps step 1. |
| **Difficulty selector** | Label "How hard? (optional)". Two rows of five 48 px pill buttons (1–5, 6–10). Selected = primary bg. Tap again to clear. |
| **Exercise row** | Name (body 600), target on the right (`3 × 8–12`, muted). Optional badges below the name. Superset items show a 3 px primary bar on the left and a group label chip (`A`). |
| **Increase badge** | Amber pill: `⬆ Increase`. Use the `arrow-up` icon plus text, not color alone. |
| **PR badge** | Amber pill: `🏆 PR` (trophy icon). |
| **Status dot** | 8 px circle. Completed = success, missed = danger, made up = accent ring, pending = border ring, unscheduled = info. |
| **Tag chip** | Pill, tag color at 15% opacity bg and full-color text. |
| **Bottom sheet** | For the ⋮ menu, reorder, and exercise picker. Rounded top 20 px, drag handle, closes on backdrop tap. |
| **Toast / inline error** | Errors appear inline above the primary button: danger-tinted card with message and **Retry**. |
| **Empty state** | Icon, one-line message, one primary action (e.g., "No active plan · Create plan"). |
| **Confirm dialog** | For discard workout, archive plan, delete session, delete tag. Title, one sentence, Cancel + destructive action. |

## 7. Screens

ASCII sketches show layout and content. Exact spacing follows the tokens above.

### 7.1 Login

```
┌──────────────────────────────┐
│                              │
│          LIFT LIST           │
│                              │
│  Username                    │
│  [                        ]  │
│  Password                    │
│  [                        ]  │
│                              │
│  [         LOG IN         ]  │
└──────────────────────────────┘
```

### 7.2 Today

```
┌──────────────────────────────┐
│ Today                     ⚙  │
│ Mon, Nov 9 · Week 2 of 5     │
│ ┌──────────────────────────┐ │
│ │ ▶ Resume: Upper (3 of 5) │ │  ← only if a session is in progress
│ │   Finish · Discard       │ │
│ └──────────────────────────┘ │
│ ┌──────────────────────────┐ │
│ │ DAY A – LOWER            │ │
│ │ Squat          4 × 6–8   │ │
│ │ Leg Ext ⬆Increase 3×10–12│ │
│ │ ▌A Calf Raise  3 × 12–15 │ │
│ │ ▌A Hanging Leg Raise 3×12│ │
│ │ [    START WORKOUT    ]  │ │
│ │ Mark as missed           │ │
│ └──────────────────────────┘ │
│ CATCH UP                     │
│  🔴 Fri · Day D – Arms  Start│
│ THIS WEEK                    │
│  M🟢  T⚪  W⚪  Th⚪  F⚪      │
│ + Unscheduled session        │
├──────────────────────────────┤
│ Today Plan Library History Stats│
└──────────────────────────────┘
```

Other states:
- **No workout today:** "Rest day" card plus the Catch up and This week sections.
- **No active plan:** empty state with "Create plan".
- **Unscheduled session builder:** starts with a single exercise row; one exercise is a complete session, and **Add another exercise** appends a blank row.

### 7.3 Runner: set entry (`WEIGHT_REPS`)

```
┌──────────────────────────────┐
│ ✕   Day A – Lower         ⋮  │
│ Exercise 1 of 4              │
│ Squat               ⬆Increase│
│ Set 2 of 4 · Goal 6–8 reps   │
│ Last: 225×8 · 225×8 · 225×7  │
│                              │
│ Weight (lb)                  │
│  [ − ]     [  225  ]   [ + ] │
│ Reps                         │
│  [ − ]     [   8   ]   [ + ] │
│                              │
│ How hard? (optional)         │
│ (1)(2)(3)(4)(5)              │
│ (6)(7)(8)(9)(10)             │
│                              │
│ [          SUBMIT          ] │
│  + Add set        Skip set   │
│ ──────────────────────────── │
│ ✔ Set 1  225 × 8  · 7     ✎  │
└──────────────────────────────┘
```

Field variants:
- `BODYWEIGHT`: Reps stepper first, then "Added weight (lb)" (optional, starts at 0).
- `TIMED`: "Time (sec)" stepper (step 5) plus optional added weight.
- `CARDIO`: Duration `mm:ss` and/or distance (mi). Either one satisfies the set; distance accepts any decimal (e.g. `2.48`).
- `WEIGHT_DISTANCE`: weight plus optional distance.

Superset: the header shows `Superset A · Round 2 of 3`, and the next-up line shows the next exercise in the group.

### 7.4 Runner: rest timer

```
┌──────────────────────────────┐
│ ✕   Day A – Lower         ⋮  │
│                              │
│            REST              │
│            1:24              │
│   ▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░        │
│                              │
│  [ −15s ]  [ SKIP ]  [ +15s ]│
│                              │
│ Up next                      │
│ Squat · Set 3 of 4           │
│ 225 lb × 8 (pre-filled)      │
└──────────────────────────────┘
```

At 0:00: two short beeps (if enabled), a brief primary-color flash of the timer, then auto-transition to the set entry screen.

### 7.5 Runner: ⋮ menu and reorder sheet

```
┌──────────────────────────────┐        ┌──────────────────────────────┐
│ ───                          │        │ ───   Reorder exercises      │
│ Reorder exercises            │        │ ✔ Squat            (done)    │
│ Jump to exercise             │        │ ≡ Leg Extension              │
│ Add exercise                 │        │ ≡ ▌A Calf Raise              │
│ Skip this exercise           │        │ ≡ ▌A Hanging Leg Raise       │
│ Finish workout               │        │ [          DONE          ]   │
│ Discard workout   (red)      │        └──────────────────────────────┘
└──────────────────────────────┘
```

Superset groups move as one block. Each row also has ▲▼ buttons as a fallback to dragging.

### 7.6 Workout summary

```
┌──────────────────────────────┐
│ Workout complete          ✕  │
│ Day A – Lower · Mon Nov 9    │
│ ┌──────┐ ┌──────┐ ┌──────┐   │
│ │ 52m  │ │14/16 │ │ 6.4  │   │
│ │ time │ │ sets │ │ avg  │   │
│ └──────┘ └──────┘ └──────┘   │  ← avg difficulty
│ Volume 18,420 lb  ▲ 6% vs last│
│ 🏆 PRs                        │
│  Squat — 235 lb (new heaviest)│
│  Leg Ext — 14 reps @ 120 lb  │
│ ⬆ Ready to increase next time│
│  Leg Extension, Calf Raise   │
│ Muscles worked               │
│  Quads ████████ 7            │
│  Calves ████ 3               │
│  Core ███ 3                  │
│ Plan adherence               │
│  🟢 9 on time 🟠 1 made up 🔴 1│
│  Streak: 4 workouts          │
│ [   EDIT SETS   ] [  DONE  ] │
└──────────────────────────────┘
```

### 7.7 Plan list and plan builder (phone: list form)

```
┌──────────────────────────────┐   ┌──────────────────────────────┐
│ Plans                   + New│   │ ← Upper/Lower B3       Save  │
│ ACTIVE                       │   │ Upper/Lower · Start Nov 2    │
│ ┌──────────────────────────┐ │   │ Length: [5] weeks (optional) │
│ │ Upper/Lower Block 3      │ │   │                              │
│ │ Wk 2 of 5 · M T Th F     │ │   │ MON · Day A – Lower       ⋮  │
│ └──────────────────────────┘ │   │  Focus: Quads Hams Calves    │
│ DRAFTS                       │   │  1 Squat   4×6–8 · 120s ▲▼ ✎│
│  Block 4 (draft)             │   │  2 RDL     3×8–10 · 90s ▲▼ ✎│
│ ARCHIVED                     │   │  A Calf Raise 3×12–15   ▲▼ ✎│
│  Block 2 · ended Oct 26      │   │  A Leg Raise  3×12      ▲▼ ✎│
│  Block 1 · ended Sep 21      │   │  + Add exercise  ⊂Superset   │
└──────────────────────────────┘   │ + Add day                    │
                                   │ [ DUPLICATE ] [ ACTIVATE ]   │
                                   └──────────────────────────────┘
```

Item edit sheet fields: exercise, sets, rep min, rep max (or seconds/distance by tracking type), rest (sec), notes.

### 7.8 Plan builder (iPad: enhancement)

M2 ships the §7.7 list form at every width; it is the guaranteed layout and works on a 375 px phone and a 768 px tablet. On ≥ 768 px, items within a day can also be reordered by dragging (`grip-vertical` handle), while ▲▼ buttons remain the accessible fallback at all widths.

The weekly grid below is a later enhancement. It is not part of M2 and the app must never require it.

```
┌───────────┬───────────────────────────────────────────────────────────┐
│ LIBRARY   │ Upper/Lower Block 3          Start Nov 2 · 5 wks   Save   │
│ [search ] │ ┌─────────┬─────────┬─────────┬─────────┬─────────┬──────┐│
│ Focus:    │ │ MON     │ TUE     │ WED     │ THU     │ FRI     │ +Day ││
│ ☑Quads    │ │ Lower A │ Upper A │  rest   │ Lower B │ Upper B │      ││
│ ☑Hams     │ │ ≡Squat  │ ≡Bench  │         │ ≡Dead.  │ ≡OHP    │      ││
│ ☐Chest    │ │  4×6–8  │  4×6–8  │         │  3×5    │  3×8–10 │      ││
│ ─────     │ │ ≡RDL    │ ≡Row    │         │ ≡Lunge  │ ≡Pullup │      ││
│ ≡ Squat   │ │ ▌A Calf │ ≡Curl   │         │         │         │      ││
│ ≡ Leg Ext │ │ ▌A Leg R│         │         │         │         │      ││
│ ≡ RDL     │ │ + add   │ + add   │         │ + add   │ + add   │      ││
│ + New ex. │ └─────────┴─────────┴─────────┴─────────┴─────────┴──────┘│
└───────────┴───────────────────────────────────────────────────────────┘
```

- Drag from the library into a day column to add (opens the item sheet with defaults pre-filled).
- Drag within a column to reorder; drag between columns to move.
- Tap an item to edit.
- If drag-and-drop proves unreliable, this screen falls back to the §7.7 list form, which must always work.

### 7.9 Library

```
┌──────────────────────────────┐   ┌──────────────────────────────┐
│ Library               + New  │   │ ← Squat                      │
│ [ 🔍 Search exercises      ] │   │ Quads · Glutes · Weight×Reps │
│ [All][Chest][Back][Quads]…   │   │ Heaviest: 235 lb × 6 (Nov 9) │
│ CHEST                        │   │ [ chart: top set over time ] │
│  Bench Press      Weight×Reps│   │ RECENT                       │
│  Incline DB Press Weight×Reps│   │  Nov 9  235×6 · 225×8 · 225×8│
│  Push-up          Bodyweight │   │  Nov 2  225×8 · 225×8 · 225×7│
│ BACK                         │   │ [ ARCHIVE ] (custom: EDIT)   │
│  …                           │   └──────────────────────────────┘
└──────────────────────────────┘
```

### 7.10 History

```
┌──────────────────────────────┐
│ History        [Calendar|List]│
│ Tags: [All ▾]  Plan: [All ▾] │
│      November 2026     ‹  ›  │
│  M   T   W   T   F   S   S   │
│  2🟢 3🟢 4   5🔴 6🟢 7   8   │
│  9🟢 10🔵 11 12⚪ 13⚪ 14 15  │
│  …                           │
│ ── Tue Nov 10 ──             │
│  🔵 PT Session  [PT]       › │
└──────────────────────────────┘
```

Session detail / edit uses the Summary layout plus editable set rows: tap a set → inline steppers + Save; swipe or ✎ menu → Delete.

### 7.11 Stats

```
┌──────────────────────────────┐
│ Stats                        │
│ [Progress][PRs][Volume]      │
│ Exercise: [ Squat        ▾ ] │
│ Range: 3M 6M 1Y All          │
│ ┌──────────────────────────┐ │
│ │      line chart          │ │
│ └──────────────────────────┘ │
│ Volume tab: [Sets|Tonnage]   │
│ stacked bars by muscle, 8 wks│
│ Tags: exclude [PT ✕]         │
└──────────────────────────────┘
```

### 7.12 Settings

```
┌──────────────────────────────┐
│ ← Settings                   │
│ Theme   [Dark][Light][Device]│
│ Default rest     [ 90 ] sec  │
│ Timer sound           [ ON ] │
│ Default tags  [PT ✕] [+ add] │
│ TAGS                         │
│  ● PT              ✎  🗑     │
│  ● Cardio day      ✎  🗑     │
│  + New tag                   │
│ Change password            › │
│ Log out                      │
└──────────────────────────────┘
```

## 8. Interaction rules

- **Pre-filled values** are shown in normal text color (not placeholder gray) so they can be submitted as-is with one tap.
- **Submit** is disabled until required fields for the tracking type are valid.
- Steppers never go below 0. Weight accepts decimals (e.g., 2.5 lb plates).
- Destructive actions always confirm. Non-destructive actions never confirm.
- **In-place updates:** a one-row action (▲▼ move, superset create/clear, drag reorder) updates only that day's exercise list. The day header, focus chips, and an open “Edit day and focus” panel stay put. “Mark as missed” updates the today card, catch-up list, and week strip together. No full-page repaint, scroll jump, or blank frame.
- **Feedback:** success and error messages appear in the page's message region without a reload. Keep the action available if the request fails so it can be retried.
- **Focus and double submit:** the tapped control keeps keyboard focus after an in-place update when it still exists, and disables while its request is in flight. If a move disables the control at an edge, focus may return to the document.
- **Navigation:** authenticated links and non-destructive forms swap in place through `hx-boost`. Destructive actions, logout, and forms that return to a specific day block remain ordinary full-page navigations.
- After an inline edit saves, show a 1.5 s "Saved" check next to the row.
- Theme applies before first paint (set `data-theme` on `<html>` server-side from the user setting; "Match device" uses `prefers-color-scheme`).

## 9. Branding

- **Name:** Lift List.
- **Wordmark:** "LIFT LIST" in system font, 700 weight, letter-spacing 0.08em, text color, with the two "L"s in primary blue (optional).
- **App icon (placeholder until designed):** rounded-square primary-blue background with a white checklist mark and a small barbell. Sizes: 180 (apple-touch), 192, 512, and 512 maskable.
- `theme-color`: `#0B0D10` (dark) / `#F5F6F8` (light).

## 10. Accessibility checklist

- Every input has a visible `<label>`.
- Icon-only buttons have `aria-label`.
- The timer region uses `aria-live="polite"` and announces only at 10 s and 0 s.
- Never rely on color alone: status dots have text equivalents in lists and tooltips; badges include icon and text.
- Focus ring: 2 px primary outline, offset 2 px.
