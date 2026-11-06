# 0005 — Runner step engine, rest overlay, and finish-early semantics

- **Status:** Accepted
- **Date:** 2026-11-06

## Context

M3 introduces the workout runner (F-05) and progression (F-07). The runner has to rotate supersets, pre-fill the next set from history, offer a rest timer, survive a page refresh, and keep working with JavaScript disabled. AGENTS.md fixes the stack (Django templates, HTMX, Alpine) and requires every action to have a POST-and-redirect fallback, so the timer could not be a client-only widget and the runner state could not live in JavaScript.

The planner already snapshots a Plan Day into `SessionExercise` rows at start. The runner therefore only needs to decide which snapshot row and set number come next, and where the rest screen fits between submits.

## Decision

- **One pure step engine.** `runner.next_step(session)` reads the ordered `SessionExercise` rows and their `SetLog` rows, groups contiguous rows that share a non-blank `superset_group` into blocks, and returns a `Step` (`session_exercise`, `set_number`, superset label/round, `rest_after_seconds`) or `None` when everything is logged. Views and templates never reimplement the rotation.
  - A single-exercise block returns that exercise's next set.
  - A superset block takes `round = min(next_set_number)` across active members and returns the first member in order whose next set is that round.
  - Rest is the exercise's `rest_seconds`, except inside a superset it is `0` until the step that finishes the round, which rests for the last member's duration. The final step of the session never rests.
- **The runner is a server-rendered `#runner` fragment.** `GET /sessions/<id>/run/` renders the full page or, with an HTMX request targeting `runner`, only `_runner_swap.html`. Every runner POST returns the same fragment and an out-of-band `#messages` region. Without HTMX the same POST redirects to the runner page, so refresh, back, and no-JS all converge on server state.
- **The rest screen is server-rendered on top of the next set form.** An HTMX set submit includes the just-finished step's `rest_after_seconds`. The response renders `_rest.html` over the next set form, which is already present in the DOM and marked `inert`. Alpine counts down from a fixed `endsAt`, then hides the overlay, unlocks the panel, and focuses the next input. ±15 s only moves `endsAt`; Skip reveals the next form immediately. No second request is needed.
- **JavaScript off skips rest rather than showing a broken overlay.** A plain POST redirects with `rest_seconds=0`, so the server renders the next set form directly and `_rest.html` is never emitted. Rest is an enhancement, not a prerequisite for logging the next set.
- **Finishing early is explicit.** `finish_session` writes `SKIPPED` `SetLog` rows for every remaining planned set number across unfinished exercises. An exercise becomes `DONE` if it has at least one completed set, otherwise `SKIPPED`. This keeps planned-versus-completed honest and lets the increase flag count only real work. The linked `ScheduledWorkout` is resolved to `COMPLETED` or `MADE_UP` from the performed date.
- **Discard is a hard delete.** An `IN_PROGRESS` session is deleted (cascading sets), and the linked `ScheduledWorkout` is recomputed to `PENDING` or `MISSED`. The confirmation page stays server-rendered as in M2.
- **One in-progress session per user.** Enforced in `start_scheduled_session` and by a partial unique constraint, so the Today resume banner always has at most one target.
- **Set submits are idempotent.** The form carries a `client_id` UUID; a replay returns the existing `SetLog` instead of creating a second one. Add-set changes `target_sets` for this session only and never the plan.
- **Reorder and jump use the same block model.** Completed or fully logged blocks are locked at the top; the remaining blocks move as units. Jump inserts a block directly after the last block that has been started (status `IN_PROGRESS`/`DONE`/`SKIPPED` or any logged set). ▲▼ buttons remain the non-drag fallback; SortableJS reuses `plan-reorder.js` at ≥768 px.
- **Progression reads history, never the plan.** `last_time` picks the most recent COMPLETED session for the exercise, prefers the same Plan Day, excludes the current session, and feeds pre-fill and the "Last:" line. The increase flag requires the planned number of non-extra completed sets and every one to reach `rep_max`; it is shown on Today, the set screen, and the completion card.

## Alternatives considered

- **Client-side runner state (JSON plus Alpine).** Rejected: it duplicates the domain model, breaks refresh/no-JS, and conflicts with the server-rendered stack.
- **A separate `/rest/` route or a timer-only page.** Rejected: an extra round-trip, extra URL, and a screen that can be refreshed into an invalid state. Rendering rest over the already-known next step is simpler and idempotent.
- **Hiding the next form with `x-show` instead of `inert`.** Rejected: the form must be visible and usable without JavaScript. `inert` keeps it out of the tab order and AT tree only while the overlay is up, then restores it in place.
- **Soft-deleting discarded sessions.** Rejected: a discarded workout should not appear in history or stats, and hard delete already matches the existing status-recompute helper.
- **Treating a fully skipped exercise as `DONE`.** Rejected: it would inflate completed counts and could trigger the increase flag on work that never happened.
- **Blocking finish until every set is logged.** Rejected: real workouts end early. Explicit `SKIPPED` rows preserve the audit trail without forcing the user to tap Skip on every remaining set.

## Consequences

- The step engine and rest rules are pure functions with unit tests; templates stay declarative.
- Every runner POST has one response shape (`#runner` plus OOB messages) and one no-JS fallback (redirect). New runner actions should follow that contract (ADR 0004).
- `SessionExercise` targets are a snapshot. Plan edits after a session starts do not change that session, and past sessions never read `PlanItem` for display.
- Rest is skipped entirely without JavaScript; this is documented in the M3 plan and covered by the no-JS HTTP probe.
- The completion card is intentionally smaller than the F-08 summary. The full summary, PRs, history editing, and stats remain later milestones.
