# M2 polish implementation plan — in-place actions and boosted navigation

- **Status:** Implemented (2026-11-06)
- **Date:** 2026-11-05
- **Scope:** Post-M2 UX polish for F-03 (plan builder) and F-04 (scheduling/Today)
- **Related:** PRD F-03/F-04; DESIGN §7.2, §7.7, §7.8, §8; TECH_SPEC §5, §6; ADR 0003
- **Follow-up:** ADR 0004, to be marked Accepted when this ships

## 1. Problem

M2 works, but most actions still submit a plain `<form method="post">`. The browser navigates away, paints a blank frame, and resets scroll even when the change is a one-row edit. This is most visible on:

- the ▲▼ move buttons on every Plan Item
- superset create and clear
- SortableJS drag reordering
- “Mark as missed” on Today

The confirmation pages are correct and must stay full-page. The fix is progressive enhancement: keep every form working without JavaScript, but make the high-frequency actions update in place.

## 2. Goals

1. No full navigation, blank frame, or scroll jump for high-frequency actions.
2. Updated markup and success/error messages appear without a reload.
3. SortableJS is re-initialized after a partial swap and never double-initialized.
4. Destructive actions still use server-rendered confirmation pages.
5. Navigation and non-destructive forms feel instant through `hx-boost`.
6. Keyboard focus and double-submit protection survive the swap.
7. No new dependencies, no schema changes, no service behavior changes.

## 3. Non-goals

- The M3 workout runner, sessions, history, or stats.
- A single-page app, client-side routing, or a new JavaScript framework.
- Changing scheduling, superset, or reorder rules.
- Editing past or completed history.
- Replacing server-rendered confirmation pages with dialogs.
- Any feature listed in PRD §4.

## 4. Behaviour matrix

| Interaction | Today | After | Fallback |
|---|---|---|---|
| Authenticated navigation links | Full page | `hx-boost` body swap, title and history updated | Normal link |
| Plan save, day add/edit, exercise add/edit, plan new, duplicate | Full page | Boosted full-page swap | Normal POST + redirect |
| Plan Item ▲▼ move | Full page | Partial swap of `#day-items-<day_id>` | POST + redirect to `#day-items-<day_id>` |
| Drag reorder | Full page | Same partial swap | POST + redirect to `#day-items-<day_id>` |
| Superset create / clear | Full page | Same partial swap | POST + redirect to `#day-items-<day_id>` |
| Today “Mark as missed” | Full page | Partial swap of `#today-content` | POST + redirect to Today |
| Delete Plan Item / Plan Day | Full page + confirm page | Unchanged | Unchanged |
| Activate / archive Plan | Full page + confirm page when needed | Unchanged | Unchanged |
| Login / logout | Full page | Unchanged | Unchanged |

“Partial swap” means one HTMX request, a 200 response, and no browser navigation.

## 5. Technical approach

### 5.1 HTMX detection

Use `request.htmx` from `django-htmx==1.29.0`, which is already installed and already has `django_htmx.middleware.HtmxMiddleware` in `MIDDLEWARE`. No dependency change is needed.

Each action view keeps its current service call. Only the response changes:

```python
if request.htmx:
    return render(request, "plans/_day_items_swap.html", context)
return redirect(f"{reverse('plan_detail', args=[plan.pk])}#day-items-{day.pk}")
```

The non-HTMX branch must remain exactly as it is today so the app still works without JavaScript.

### 5.2 Partial response contract

A partial response contains:

1. one root element matching the swap target, and
2. an out-of-band messages element.

For Plan Item actions, the root is `#day-items-<day_id>`. This is narrower than swapping the whole day card, so the day header and an open “Edit day and focus” panel keep their state. It also means the day’s exercise count does not need to be recalculated.

```html
<div id="day-items-{{ day.pk }}">…</div>
<div id="messages" hx-swap-oob="true">…</div>
```

For Today, the root is `#today-content`. It includes the today card, catch-up list, and week strip, because marking a workout missed changes all three.

### 5.3 Messages

- Extract the messages block from `base.html` into `templates/components/messages.html`.
- Always render the wrapper with `id="messages"`, even when there are no messages.
- Add `templates/components/messages_oob.html`, which renders the same content with `hx-swap-oob="true"`.
- Include the OOB partial only in HTMX responses. Do not include it in the full page, or the messages would render twice.

### 5.4 Selective `hx-boost`

Add `hx-boost="true"` to `<body>` only when `user.is_authenticated`.

Keep these as normal document navigations with `hx-boost="false"`:

- the logout form
- delete Plan Item
- delete Plan Day
- activate Plan
- archive Plan

Those actions either cross an auth boundary or can return a confirmation page. Keeping them unboosted avoids confirmation URLs entering the HTMX history cache.

Verified against the vendored htmx 2.0.11: hash-only links such as `#add-day` are not boosted, so the existing “Add your first day” link needs no change.

### 5.5 Focus and double submit

- Give action buttons stable IDs:
  - `move-up-<item_id>`, `move-down-<item_id>`
  - `superset-<day_id>`
  - `clear-superset-<day_id>-<group>`
  - `mark-missed`
- htmx 2.0.11 restores focus after a swap when the active element has an `id` and an element with the same `id` exists afterwards. Stable IDs give us focus retention without custom JavaScript.
- Add `hx-disabled-elt` so the clicked control disables while the request is in flight:
  - `hx-disabled-elt="find button"` on move forms and the Today form
  - `hx-disabled-elt="#superset-<day_id>"` on the hidden superset form, because its submit button lives outside the form
- If a move makes the focused button disabled (for example, moving the first item up), focus falls back to the document. That is acceptable.

### 5.6 SortableJS lifecycle

Move `sortable.min.js` and `plan-reorder.js` from `plans/detail.html` into `base.html`, loaded once for authenticated pages. They are cached, and `plan-reorder.js` does nothing when no `[data-sortable]` element exists. This avoids re-executing the vendor script on every boosted navigation to the plan builder.

Refactor `static/js/plan-reorder.js` to:

- initialize immediately when the document is already parsed, otherwise on `DOMContentLoaded`
- listen for `htmx:afterSwap` and initialize any new `[data-sortable]` elements inside the swapped target
- guard each container with `data-sortable-ready` so it is never initialized twice
- bind the `afterSwap` listener once per window

The ▲▼ buttons remain the non-drag fallback at every width. Drag remains a ≥768 px enhancement.

### 5.7 Redirect anchors

Where a full-page save still redirects, send the user back to the relevant block:

- add/edit Plan Item → `#day-items-<day_id>`
- add/edit Plan Day → `#day-<day_id>`
- delete Plan Item → `#day-items-<day_id>` (the empty state keeps the anchor valid)
- move, reorder, superset → existing `#day-items-<day_id>` anchors

The plan settings form and plan duplicate stay at the top of the page.

If the headless probe shows htmx does not scroll to a hash after a boosted redirect, add a small `htmx:afterSettle` handler that calls `scrollIntoView()` for `window.location.hash`. Do not add it pre-emptively.

## 6. Implementation checklist

### 6.1 Templates

- [ ] `templates/components/messages.html`: shared messages block, always with `id="messages"`.
- [ ] `templates/components/messages_oob.html`: same block with `hx-swap-oob="true"`.
- [ ] `templates/base.html`: include the messages component; add conditional `hx-boost`; add `hx-boost="false"` to logout; load SortableJS and `plan-reorder.js` for authenticated pages.
- [ ] `templates/plans/_day_items.html`: extract the items list, hidden superset/reorder forms, footer actions, and empty state from `detail.html`, wrapped in `#day-items-<day_id>`.
- [ ] `templates/plans/_day_items_swap.html`: include `_day_items.html` and `messages_oob.html`.
- [ ] `templates/plans/detail.html`: use `_day_items.html`; add HTMX attributes and stable IDs; add `hx-boost="false"` to destructive forms.
- [ ] `templates/core/_today_content.html`: extract the today card, catch-up section, and week strip; wrap in `#today-content`.
- [ ] `templates/core/_today_swap.html`: include `_today_content.html` and `messages_oob.html`.
- [ ] `templates/core/today.html`: use `_today_content.html`; add HTMX attributes and the `mark-missed` ID.

### 6.2 Views

- [ ] `apps/plans/views.py`
  - add a small helper that renders the day-items swap response
  - add `request.htmx` branches to `plan_item_move`, `plan_day_reorder`, `plan_day_superset`, `plan_day_superset_clear`
  - add a `request.htmx` branch to `scheduled_mark_missed`
  - capture the return values of `add_day` and `add_item` so redirects can include the correct anchor
  - add anchors to `plan_day_edit`, `plan_item_new`, `plan_item_edit`, and `plan_item_delete`
- [ ] `apps/core/views.py`: no change unless Today context extraction needs a helper; `build_today` remains the single source of truth.

### 6.3 JavaScript

- [ ] `static/js/plan-reorder.js`: immediate boot, `htmx:afterSwap` re-init, per-container guard, one listener per window.
- [ ] Remove the unused `data-reorder-url` attribute or use it in `submitOrder`; do not keep two sources of truth for the reorder URL.

### 6.4 Data and routes

- [ ] No model changes.
- [ ] No migrations.
- [ ] No URL changes.
- [ ] No service behavior changes.

## 7. Testing

### 7.1 Automated tests

Add to `tests/test_plan_views.py`:

- HTMX move returns 200, uses the day-items partial, and shows the new order.
- HTMX move at the top of the list returns 200 with an error message and leaves the order unchanged.
- Non-HTMX move still returns 302 to `#day-items-<day_id>`.
- HTMX reorder returns the partial with the new order.
- HTMX superset create returns the partial with the new group label.
- HTMX superset clear returns the partial without the group.
- HTMX partial responses contain `hx-swap-oob="true"` and `id="messages"`.
- A different user still gets 404 for every partial action.
- A non-HTMX request never receives a partial.

Add to `tests/test_today.py`:

- HTMX mark-missed returns 200, uses the Today content partial, and shows the workout under “Catch up”.
- Non-HTMX mark-missed still returns 302 to Today.
- A different user gets 404.

Add to `tests/test_shell.py`:

- authenticated pages contain `hx-boost="true"`
- the login page does not
- the logout form contains `hx-boost="false"`

### 7.2 Quality gates

```powershell
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m ruff format --check .
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe manage.py check
.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
```

### 7.3 Headless Chrome probe

Use the existing CDP probe pattern from `C:\Users\Owner\AppData\Local\Temp\opencode\m2shots\probe.mjs`.

For each in-place action:

1. set `window.__probe = { marker: "alive" }`
2. click the control
3. wait for the swap
4. assert `window.__probe.marker` is still `"alive"` (no new document)
5. assert the URL and `window.scrollY` are unchanged
6. assert the expected DOM changed and the success message appeared
7. assert `[data-sortable]` still has `data-sortable-ready`
8. assert there are no console errors

Run at 375 px (▲▼ and mark-missed) and 768 px (drag reorder). Also confirm:

- a delete still reaches a server-rendered confirmation page
- boosted navigation updates the title and URL
- browser Back restores the previous page
- the Today empty state, plan empty state, and validation-error pages still render

## 8. Documentation changes

Before merging:

- add an `## [Unreleased]` entry to `CHANGELOG.md`
- update TECH_SPEC §6 with the partial-response contract, OOB messages, selective boost, and the `#day-items-<id>` / `#today-content` swap targets
- update DESIGN §8 with in-place update and focus rules
- write `docs/decisions/0004-htmx-progressive-enhancement.md` and mark it Accepted
- update the README project layout to mention `docs/plans/`

## 9. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Boosted destructive form puts a confirmation URL in history | `hx-boost="false"` on delete, activate, archive, and logout |
| Sortable initialized twice after a swap | `data-sortable-ready` guard plus a single `afterSwap` listener |
| Messages consumed by the partial and never shown | Render `messages_oob.html` in the same response |
| Validation errors do not swap because the response is 4xx | Action views catch `ValidationError`, add a message, and return a 200 partial with canonical state |
| Focus lost after replacing the row | Stable button IDs; htmx restores focus by ID |
| Open “Edit day” panel closes on every row action | Swap `#day-items-<id>` instead of the whole day card |
| Sortable drag visually mutates the DOM before the server responds | Server response re-renders canonical order; on error it also re-renders the stored order |
| Hash redirect does not scroll under boost | Verify in the probe; add one small `afterSettle` scroll helper only if needed |
| Scripts not executed after boosted navigation | Load Sortable and the reorder initializer once from `base.html` |

## 10. Rollback

The change is additive. If a partial response misbehaves:

1. remove the `hx-*` attributes from the affected form; it falls back to the existing POST + redirect immediately
2. the view can keep its `request.htmx` branch or ignore it; non-HTMX behaviour is unchanged
3. no data migration or service rollback is required

## 11. Definition of done

- [ ] Every action in the behaviour matrix works with JavaScript disabled.
- [ ] High-frequency actions update in place without scroll or focus loss.
- [ ] Confirmation pages remain full-page server-rendered pages.
- [ ] Sortable works after any number of partial swaps and boosted navigations.
- [ ] 375 px and 768 px layouts still match DESIGN.
- [ ] `ruff check .`, `ruff format --check .`, and `pytest` pass.
- [ ] Headless probe passes with no console errors.
- [ ] Docker Compose with Postgres still boots and serves the app.
- [ ] CHANGELOG, TECH_SPEC, DESIGN, and ADR 0004 are updated.
