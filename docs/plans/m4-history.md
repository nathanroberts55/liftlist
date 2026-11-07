# M4 — Unscheduled sessions, tags, history + editing

Features: **F-06** (unscheduled sessions and tags), **F-09** (history), **F-11** (settings additions).

## Checklist

- [x] `UserSettings.timer_sound` and `UserSettings.default_tags` with migration
- [x] Settings screen: timer sound toggle, default tag chips, tag management, change password
- [x] Tag services (list/create/update/delete/resolve/defaults) and tag CRUD screens
- [x] Tag chip and status-dot components + CSS tokens
- [x] `/sessions/new/` plan-and-start unscheduled session (formset, no-JS add row)
- [x] `/sessions/log/` retroactive session (date/time/duration + exercises)
- [x] Today entry points for both unscheduled flows
- [x] `/history/` calendar + list, tag include/exclude and plan filters, day detail
- [x] Session detail with editable sets, add/delete set, metadata edit, delete session
- [x] Scheduled status recalculation on performed-date change and session delete
- [x] Auth and user-isolation tests for every new route
- [x] No-JS fallbacks for forms, edits, and destructive confirmations
- [x] Docs (TECH_SPEC, README, CHANGELOG) + ADR for full-page tag CRUD/history editing
- [x] `ruff check .`, `ruff format --check .`, `pytest`, `manage.py check`, migrations check
- [x] Rebuild Tailwind and verify at 375 px / 768 px
