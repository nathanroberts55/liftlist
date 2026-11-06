# 0003 — M2 plan builder layout and safe schedule edits

- **Status:** Accepted
- **Date:** 2026-11-05

## Context

DESIGN §7.8 sketches an iPad weekly grid with cross-day drag-and-drop for the plan builder. AGENTS.md also requires a non-drag fallback for every drag interaction, and M2 is scoped to F-03/F-04 before the runner exists. Plan edits on an active plan must not rewrite history or resurrect past dates.

## Decision

- Ship the §7.7 list form at every width in M2. It is the guaranteed builder on a 375 px phone and a 768 px tablet.
- Add SortableJS reordering **within a day** on ≥ 768 px, with a `grip-vertical` handle. The ▲▼ buttons remain visible and work at every width, and the server validates that superset members stay consecutive.
- Do not build the full weekly grid or cross-day dragging in M2. Treat it as a later enhancement rather than a release blocker.
- When an active plan is edited, regenerate only `PENDING` Scheduled Workouts on or after today. `generate_schedule` takes `start_from`, so edits and open-ended extensions never backfill the past. Past rows and started/completed workouts are never touched.
- Block deleting a Plan Day that has past or completed Scheduled Workouts.

## Alternatives considered

- **Weekly grid first.** Rejected: it is the riskiest layout, has no non-drag equivalent for cross-day moves, and would delay scheduling.
- **Drag-only reordering.** Rejected by AGENTS.md and unusable on a phone.
- **Regenerate the whole schedule after edits.** Rejected: it would delete or duplicate historical occurrences and break links to future sessions.
- **Delete any future row on archive.** Rejected for M2 only insofar as rows have no Session yet; the implementation already excludes rows with a session so M3 can add the FK safely.

## Consequences

- The list form is the source of truth for tests and acceptance; SortableJS is a progressive enhancement.
- M3 must revisit `regenerate_future` and `archive_plan` when `ScheduledWorkout` gains a Session FK, preserving linked sessions instead of deleting rows.
- The weekly grid remains future work under M6 polish if it is still wanted.
