# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning: [SemVer](https://semver.org/).

## [Unreleased]

### Added
- Distance units (F-13): every exercise has a default distance unit (miles, yards, or metres) that can be overridden per Plan Item, Session Exercise, and ad-hoc session exercise. The unit is snapshotted, so changing an exercise default never rewrites history. Distances are stored canonically in metres (4 dp), and `apps/exercises/services/units.py` handles conversion, input values, and labels. New migration converts existing mile values to metres.
- `DISTANCE` tracking type replaces `WEIGHT_DISTANCE`: a set needs a distance, steps, or both, weight is optional, and there is no duration field. Sled Push, Sled Pull, and Farmer's Carry are seeded as `DISTANCE` in yards. Steps reuse the reps field and are labelled “Steps (each way)”.
- Unit select with an “Exercise default” choice on the exercise form and on the plan-item and session-item forms, a unit-aware distance label on the runner and history set forms, and tests for conversions, unit snapshots, validation, and form overrides.
- Workout summary (F-08): the post-finish card and History session detail now show duration, completed vs planned sets (with extra/skipped counts), tonnage with a comparison against the previous completed session of the same Plan Day or title, PRs, “Ready to increase” exercises, sets per primary muscle group, average difficulty, and active-plan adherence with the current streak. The summary is derived on demand, so editing a past session updates it immediately.
- Stats (F-10): `/stats/` with Progress, PRs, and Volume tabs. Progress plots the top set per session date for an exercise across 3M/6M/1Y/All with full-set tooltips; PRs lists the heaviest set and expandable “most reps at each weight” records with search and muscle filters; Volume stacks weekly sets or tonnage by primary muscle group across the last 8 ISO weeks with a tag exclusion filter.
- Stats JSON endpoints (`/stats/api/top-set/`, `/stats/api/volume/`) for Chart.js, login required and scoped to the visible exercises and sessions of the logged-in user.
- Personal-record engine (`workouts/services/records.py`) shared by the summary, exercise detail, and stats PR table, implementing the PRD F-10 heaviest-weight and most-reps-at-weight rules.
- Exercise detail now shows the last five sessions, current PRs, and an all-time top-set chart, and links to the filtered PR table.
- Chart.js 4.4.7 vendored in `static/vendor/` (no runtime CDN), `static/js/charts.js` reading theme colors from CSS variables, and chart palette tokens for both themes.
- Record, summary, stats aggregation, stats view, auth, and user-isolation tests.
- Unscheduled sessions (F-06): `/sessions/new/` plans and starts a workout with a title, tags, and type-aware exercise targets. “Add another exercise” re-renders the bound form without JavaScript, and **Start workout** creates an in-progress unscheduled session in the runner. Today gains an “On your own” section with plan-and-start and retro-log entry points; plan-and-start is hidden while another workout is in progress.
- Retroactive logging (F-06): `/sessions/log/` records a completed past workout with title, date, optional start time and duration, tags, and exercises. Future dates are rejected; the detail page then accepts sets.
- Tags (F-06): user-scoped tag CRUD on Settings using the DESIGN chart palette, duplicate-name protection ignoring case, per-tag workout counts, default tags pre-selected on new sessions, and tag chips/status-dot components with theme-driven colors.
- History (F-09): `/history/` calendar and list views with a Monday-start month grid, completed/missed/made-up/pending/unscheduled dots, day detail, tag include/exclude filters, and plan filters. Filter state survives month navigation.
- History editing (F-09): session detail, title/date/tag editing, add/edit/delete sets with an HTMX row swap and full-page fallback, session deletion behind a confirmation page, and scheduled-workout status recalculation after a date change or deletion.
- Settings (F-11): timer sound toggle, default tag chips, tag management, and a styled change-password screen.
- Tests for tag services and CRUD, unscheduled and retro flows, session/set editing, status recalculation, history calendar/list/filters/day detail, HTMX partials, and user isolation across the new routes.
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
- PRD §6/§8.2/§9, DESIGN §7.5/§7.7, and TECH_SPEC §3–§4 now describe distance units, the `DISTANCE` tracking type, canonical metre storage, and the `units` service.
- Unscheduled-session builders (F-06) now start with one exercise row. A session may contain exactly one exercise, and blank extra rows are no longer browser-required, so **Log past workout** and **Plan & start now** both save a single-exercise session.
- M6 polish (in progress, Step 1): `components/empty_state.html` supports a compact nested variant and consistent actions; plan-day “no exercises” and workout exercise picker empty/no-match states are clearer, with a library link from the runner picker.
- M6 polish (Step 2, iPad/≥768px layouts): library muscle-filter scroll padding now matches `md:px-6` content padding to prevent horizontal bleed; unauthenticated/auth pages use consistent iPad horizontal padding; exercise detail actions lay out side by side on small/tablet widths; Today “On your own” actions use a two-column grid on `sm+` while preserving the in-progress state. Runner remains centered at 480px and phone layout is unchanged.
- M6 polish (Step 3, accessibility): Stats PR/volume filters and the runner exercise-picker search now use visible labels instead of screen-reader-only labels (DESIGN §10). Progress/volume/exercise charts include fallback text inside `canvas` elements alongside their `role="img"` labels. Focus-visible ring, status-dot text equivalents, timer `aria-live` announcements (10 seconds and rest end), and 44px/16px target/input sizing were verified across key screens.
- TECH_SPEC §4.7–4.9 and §5 now describe the records engine, summary dataclass, stats aggregations, chart endpoints, and the rule that Stats links to the History calendar instead of duplicating it.
- The Stats tab is a real destination instead of a placeholder, and the exercise detail page reuses the stats services for its records and chart.
- Deployment: added `k8s/ingress.yaml` (Traefik host rule, no TLS block because Cloudflare terminates TLS), made both probes send `Host: liftlist.naterobertstech.com` so Django's `ALLOWED_HOSTS` accepts the kubelet request, switched the single replica to `strategy: Recreate` to avoid concurrent migrations, and documented the gitignored `k8s/secrets.yaml` workflow alongside the committed `k8s/secret.example.yaml`.
- ADR 0006 records the M4 split: tag CRUD, history filters, session creation, and destructive confirmations use full-page POST/redirect flows, while only set editing adds an HTMX row swap. Fragment branches are gated on `HX-Target` so boosted navigation always receives a full page.
- TECH_SPEC §4.2–4.9, §5, and §6 now describe the unscheduled/retro/history/tag services, the new routes, the full-page flows, the `HX-Target` rule, and the timer-sound preference.
- Settings now treats default tags as first-class preferences, and History is a real destination instead of a placeholder.
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
- Distance entry (F-13): distance fields accept any decimal value, so a `2.48 mi` walk saves instead of failing browser step validation. `CARDIO` accepts a duration, a distance, or both, and the rest preview shows distance-only sets correctly.
- Library navigation via the app shell no longer replaces the whole page with the exercise list fragment. The boosted page request now renders the full Library page with the top bar, bottom tab bar, and sidebar; the HTMX list fragment is returned only when the search form targets `#library-list`.

### Notes
- M0–M5 cover the scaffold, the exercise library, plan building and scheduling, the workout runner with progression, unscheduled and retroactive sessions, tags, Settings additions, history with editing, the workout summary, and stats. Polish (empty states, iPad layouts, accessibility) is M6.
