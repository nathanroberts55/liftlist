# 0006 — Full-page tag CRUD and history editing

- **Status:** Accepted
- **Date:** 2026-11-06

## Context

M4 adds tags (F-06), history with editing (F-09), and the Settings additions (F-11). Tags are created and renamed on Settings, but the same tag list also drives the default-tag chips, the filters on History, and the tag picker on the unscheduled and retro session forms. Editing a set happens inside a dense session detail page where an inline swap genuinely helps. Tag CRUD and history filters have no such locality: after a change, the user expects the whole Settings or History screen to reflect the new tag names, colors, counts, and calendar dots.

The app shell also enables `hx-boost` on authenticated pages. With boosted navigation, every link click arrives as an HTMX request, so a view cannot treat `request.htmx` as “return a fragment”. The M3 library regression showed how easy it is to replace the shell with a list fragment.

## Decision

- **Tag CRUD is a full-page POST/redirect flow.** `/settings/tags/new/`, `/settings/tags/<id>/edit/`, and `/settings/tags/<id>/delete/` render normal pages and redirect back to Settings after a successful POST. Delete renders a confirmation page and requires `confirm=1`.
- **History filters, session creation, session deletion, and set add are full-page flows.** They redirect (or re-render the full form on validation errors) so the page always recomputes the calendar, filters, and tag counts from the database.
- **Only set editing is inline.** `/sets/<id>/edit/` returns the whole session detail page normally, and returns `_set_row.html` only when the request targets `#set-<id>`. A POST with the same target swaps the row; without HTMX it redirects to the session detail. `/sets/<id>/row/` restores the read-only row for the cancel action.
- **Every fragment branch is gated on `HX-Target`.** A view returns a partial only when `request.headers.get("HX-Target")` matches its intended container. Boosted navigation and ordinary requests always get the full page.
- **Destructive actions are server-rendered confirmations.** Sessions, sets, and tags have GET confirmation pages and POST with `confirm=1`; there is no hidden or one-click bypass.
- **History keeps make-up semantics visible.** A make-up session puts a `MADE_UP` dot on its original scheduled date and a `COMPLETED` dot on the date it was performed. Tag filters apply to sessions; when a tag filter is active, scheduled workouts are shown only if they have a matching session.

## Alternatives considered

- **HTMX tag CRUD partials.** Rejected: the Settings tag list, default-tag chips, and tag pickers would need out-of-band updates or a reload anyway, so a fragment adds complexity without a latency win.
- **Client-side filtering on History.** Rejected: it duplicates the service filter rules and breaks the no-JS fallback.
- **Partial responses for every `request.htmx` request.** Rejected: `hx-boost` makes navigation look like HTMX, which is exactly how the library shell regression happened.
- **Inline deletion of sets with a hidden POST.** Rejected: AGENTS.md requires destructive actions to confirm, and the confirmation page keeps the no-JS path honest.

## Consequences

- Tag and history changes always re-read the database, so counts, chips, and calendar dots cannot go stale.
- The set row swap keeps the one interaction that benefits from partial updates, while still providing full-page GET/POST fallbacks.
- New fragment endpoints must check `HX-Target`; the rule is covered by view tests for the library, runner, and set row.
- History editing can change a scheduled workout's status. Both the date-edit and delete paths call `scheduling.recompute_status_after_session_change`, so the calendar never shows a stale `COMPLETED` or `MISSED` state.
