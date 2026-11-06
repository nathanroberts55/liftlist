# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning: [SemVer](https://semver.org/).

## [Unreleased]

### Added
- Workout runner (F-05): `Tag`, `Session`, `SessionExercise`, and `SetLog` models; target snapshots at start; one in-progress session per user; and a server-rendered `#runner`. Logs one set at a time with type-specific fields for weight/reps, bodyweight, timed, cardio, and weight/distance, plus difficulty 1–10. Includes superset rotation with per-round rest, a rest timer with +15/−15/skip and an audible rest beep, skip/add set, skip/add exercise, reorder (drag + ▲▼), jump ahead, finish early with the remaining planned sets recorded as skipped, and discard behind a confirmation page.
- Progression (F-07): the `Last:` line, pre-fill from the same set number when available, same-Plan-Day preference, and the “Ready to increase” flag on Today, the set screen, and the completion card. The flag requires every planned set to reach the rep max.
- Today entry points: Start workout, Start catch-up for a missed workout, and a resume banner for the one session in progress.
- `apps/workouts` services (`runner.py`, `progression.py`), views, URLs, admin, migration, runner templates, `timer.js`, and runner icons.
- Runner, progression, view, model, user-isolation, HTMX-partial, and no-JS fallback tests, plus a headless 375/768 px runner probe.
- Plan builder (F-03): `Plan`, `PlanDay`, and `PlanItem` models with a single active plan per user, one day per weekday, and target constraints. List-form builder at every width with inline plan settings, day and item CRUD, an exercise picker sorted by focus muscles, ▲▼ reordering, and supersets (A–Z) that must stay consecutive.
- Scheduling (F-04): `ScheduledWorkout` generation for fixed-length and open-ended plans, activation that archives the current plan, plan duplication, archive cleanup of future pending rows, missed/made-up/completed status helpers, and manual "mark missed" for today.
- Today screen: active plan and week progress, today's workout with ordered target list, rest days, catch-up list, week strip, and a link into the plan builder.
- Per-user default rest (`UserSettings.default_rest_seconds`, default 90) in Settings, used as the initial value for new plan items.
- Drag-and-drop reordering within a day on tablet-and-up (SortableJS) with the ▲▼ buttons and list form as the always-available fallback.
- `apps/plans` services (`plans.py`, `scheduling.py`, `today.py`), forms, views, URLs, admin, migrations, SortableJS asset, and `plan-reorder.js`.
- Plan, scheduling, Today, form, model, and user-isolation tests; new plan/day/item fixtures.
- Project docs: PRD, Design Guide, Technical Spec, AGENTS.md, ADR 0001, exercise seed data.
- M0 scaffold: Django 5.2 project (`liftlist/`), env-driven settings, SQLite for local dev/tests, Postgres via `DATABASE_URL`.
- Authentication (F-01): Django login/logout, `LoginRequiredMiddleware`, 30-day sessions, optional `ensure_superuser` command.
- Per-user `UserSettings` with automatic creation, theme preferences (`Dark`, `Light`, `Match device`), settings page, and admin.
- App shell per DESIGN: phone top bar and five-tab bottom bar, tablet sidebar, login/Today/Settings screens, reusable button and empty-state components, inline Lucide icons.
- Tailwind v4.3.4 + DaisyUI 5.7.50 themes (`liftlist-dark`, `liftlist-light`) built with the standalone CLI; vendored HTMX 2.0.11 and Alpine 3.17.5.
- Installable PWA (F-12): manifest, 180/192/512/maskable icons, Apple touch icon and standalone metadata.
- `/healthz/` with a database check and 503 responses when the database is unreachable.
- Multi-stage Dockerfile (Tailwind build + gunicorn runtime), `entrypoint.sh`, compose stack with Postgres 16, and `.env.example`.
- Kubernetes manifests under `k8s/` and GitHub Actions workflows for CI and Docker Hub publishing.
- pytest suite covering healthz, auth redirects/login/logout, manifest/icons, settings auto-creation/update/isolation, theme resolution, and `ensure_superuser`.
- Exercise library (F-02): `MuscleGroup`, `Exercise`, and per-user `ExerciseArchive` models; `ExerciseQuerySet.visible_to` / `archived_for`; 12 seeded muscle groups via data migration.
- `seed_exercises` management command with a 96-exercise global library (`seed/exercises.json`); idempotent upsert that never deletes and never touches user archives. Runs automatically in `entrypoint.sh`.
- Library screens per DESIGN §7.9: grouped list with HTMX search (GET-form fallback), muscle-group filter chips, archived view, exercise detail, create/edit forms for custom exercises, and archive/restore actions. Seeded exercises are read-only and archive per user.
- Library services (`apps/exercises/services/library.py`) for listing, grouping, name validation, and create/update/archive/restore, with unit tests; model, form, view, user-isolation, and seed-command tests.

### Changed
- ADR 0005 records the runner step engine, the server-rendered rest overlay with its JavaScript-off redirect, and the finish-early and discard semantics.
- TECH_SPEC §4.2–4.3, §5, and §6: runner service signatures, routes, the `#runner` `outerHTML` swap, validation handling, and timer details now match M3.
- M2 polish: ▲▼ moves, drag reorder, and superset create/clear now swap only `#day-items-<day_id>`, and Today “Mark as missed” swaps `#today-content`, so the page no longer blanks or jumps. Partial responses carry out-of-band messages, action controls keep stable IDs, disable in flight, and restore keyboard focus after the swap, and SortableJS re-initializes after a swap without double-binding. Authenticated navigation and non-destructive forms use `hx-boost`; logout, delete, activate, archive, confirmation forms, and fragment-saving forms stay full-page. ADR 0004 records the partial-response contract.
- ADR 0003 records the M2 builder layout (list form everywhere, within-day drag on tablets) and the rule that active-plan edits only regenerate today-and-later pending workouts.
- TECH_SPEC: project package is `liftlist/` (not `config/`), Tailwind/DaisyUI plugin paths reflect the vendored 5.7.50 package, and the URL/seed sections describe the M1 library.
- TECH_SPEC §4.1/§5: `generate_schedule` accepts `start_from` so plan edits and open-ended extensions never backfill past dates; the M2 plan and schedule routes are documented.
- DESIGN §7.8: the M2 builder ships the §7.7 list form at every width, with SortableJS reordering on ≥768 px; the full iPad weekly grid remains a later enhancement, not a blocker.
- The app shell switches to the tablet sidebar at 768 px, matching DESIGN §5.
- Secure cookies are controlled by `DJANGO_SECURE_COOKIES` (default: on when `DEBUG=0`). The plain-HTTP compose stack sets it to `0` so login works locally.
- `python manage.py seed_exercises` is now part of local setup and container startup.

### Fixed
- Library navigation via the app shell no longer replaces the whole page with the exercise list fragment. The boosted page request now renders the full Library page with the top bar, bottom tab bar, and sidebar; the HTMX list fragment is returned only when the search form targets `#library-list`.

### Notes
- M0–M3 cover the scaffold, the exercise library, plan building and scheduling, and the workout runner with progression. History, summary, stats, and tags arrive in later milestones.
