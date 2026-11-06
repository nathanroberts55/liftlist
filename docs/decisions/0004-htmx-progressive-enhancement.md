# 0004 — HTMX progressive enhancement for plan and Today actions

- **Status:** Accepted
- **Date:** 2026-11-06

## Context

M2 worked, but high-frequency actions submitted plain forms. The browser navigated away, painted a blank frame, and reset scroll for one-row changes such as ▲▼ moves, superset create/clear, drag reordering, and “Mark as missed”. Destructive actions already used server-rendered confirmation pages, which must stay. AGENTS.md fixes the stack and requires every action to keep working without JavaScript, so the solution had to be an enhancement rather than a rewrite.

## Decision

- Keep every existing POST route and redirect fallback. Add `request.htmx` branches (from the already-installed `django-htmx`) that return a partial instead of a redirect.
- Use two swap targets:
  - `#day-items-<day_id>` for Plan Item move, reorder, superset create, and superset clear. Swapping only the items region preserves the day header and an open “Edit day and focus” panel.
  - `#today-content` for “Mark as missed”, because the card, catch-up list, and week strip can all change.
- Every partial returns one root element matching the target plus an out-of-band `#messages` element (`hx-swap-oob="true"`). The messages wrapper is always present in the full page and in partials, so alerts appear without a reload and can later be cleared.
- Enable `hx-boost="true"` on `<body>` only for authenticated users. Exclude the logout form, delete Plan Item, delete Plan Day, activate Plan, archive Plan, confirmation forms, and forms whose redirect carries a `#day-items-<id>` anchor.
- Give action controls stable IDs (`move-up-<item_id>`, `move-down-<item_id>`, `superset-<day_id>`, `clear-superset-<day_id>-<group>`, `mark-missed`) so htmx can restore focus after a swap. Add `hx-disabled-elt` so a control disables while its request is in flight, and add `htmx-focus.js` because disabling the pressed control moves focus to the document: it remembers the active element's `id` on `htmx:beforeRequest` and restores it on `htmx:afterSettle`.
- Load SortableJS and `plan-reorder.js` once from `base.html` for authenticated pages. The initializer runs immediately when the document is parsed, re-runs on `htmx:afterSwap`, guards each container with `data-sortable-ready`, and binds one listener per window.
- Keep ▲▼ buttons as the non-drag fallback at every width; drag remains a ≥768 px enhancement.

## Alternatives considered

- **Full single-page app or a client-side router.** Rejected: it adds a build/runtime stack that AGENTS.md forbids and duplicates server-rendered screens.
- **Swap the whole Plan Day card.** Rejected: it would close an open “Edit day” panel and reset unrelated state.
- **Return 4xx for validation errors and rely on htmx error handling.** Rejected: a 4xx response is not swapped by default, so the canonical order and inline message would not update. Views catch `ValidationError`, add a message, and return a 200 partial rendering stored state.
- **Boost every form.** Rejected: destructive forms would put confirmation URLs in the history cache, and boosted redirects drop URL fragments, breaking anchor scroll for add/edit forms.
- **Re-execute page scripts on every boosted navigation.** Rejected: it would double-initialize Sortable and add request churn. Loading once with an idempotent initializer is simpler.

## Consequences

- JavaScript-off behaviour is unchanged: forms still POST and redirect to the correct anchor.
- Partial responses must keep the root `id` and the OOB messages contract; new in-place actions should follow the same shape.
- Server-rendered confirmation pages remain full-page navigations.
- Focus retention depends on stable IDs surviving the swap. `htmx-focus.js` restores focus after `hx-disabled-elt` temporarily moves it to the document. If a moved control is disabled at an edge, focus falls back to the document, which is acceptable.
- M3 can reuse the swap and OOB message pattern for runner steps and set logging without new dependencies or routes.
