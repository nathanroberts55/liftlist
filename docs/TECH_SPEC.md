# Lift List — Technical Specification

| Field | Value |
|---|---|
| Status | v1 |
| Related docs | [`PRD.md`](./PRD.md), [`DESIGN.md`](./DESIGN.md), [`../AGENTS.md`](../AGENTS.md) |

---

## 1. Stack

| Layer | Choice | Notes |
|---|---|---|
| Language | Python 3.12+ | |
| Framework | Django 5.2 LTS | Server-rendered templates; built-in auth and admin. |
| Database | PostgreSQL (prod), SQLite (local dev) | Selected via `DATABASE_URL`; SQLite when unset. |
| Interactivity | HTMX 2.x | Partial page updates; no SPA. |
| Small client state | Alpine.js 3.x | Rest timer, steppers, sheets, theme toggle. |
| Drag-and-drop | SortableJS | Plan builder and reorder sheet. |
| Charts | Chart.js 4.x | Stats and summary. |
| CSS | Tailwind CSS v4 (standalone CLI) + DaisyUI 5 | No Node.js required. Custom DaisyUI themes per DESIGN §2. |
| Icons | Lucide (inline SVG partials) | |
| App server | Gunicorn | |
| Static files | WhiteNoise | Compressed, hashed filenames. |
| Packaging | `pip` + `requirements.txt` / `requirements-dev.txt` | Pin exact versions. |
| Container | Docker (Dockerfile) → Docker Hub | |
| Runtime | Kubernetes on home Linux server | Postgres runs on the same Linux server (outside the cluster). |
| Ingress | Cloudflare Tunnel | TLS terminates at Cloudflare. |
| Tests / lint | pytest + pytest-django, Ruff (lint + format) | |

JS libraries are **vendored** into `static/vendor/` with pinned versions (no CDN at runtime).

## 2. Repository layout

```
liftlist/
├── AGENTS.md                 # Rules for AI coding agents (read first)
├── CHANGELOG.md
├── README.md                 # Quick start (dev, compose, deploy)
├── Dockerfile
├── docker-compose.yml        # App + Postgres, mirrors prod locally
├── .env.example
├── .dockerignore / .gitignore
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml            # Ruff + pytest config
├── manage.py
├── entrypoint.sh             # migrate → seed (M1+) → gunicorn
├── bin/                      # Dev-only scripts and the downloaded Tailwind binary
│   ├── generate_icons.py
│   └── make_icons.py
├── liftlist/                 # Django project
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── apps/
│   ├── accounts/             # UserSettings, login/logout, settings page
│   ├── exercises/            # MuscleGroup, Exercise, seed command
│   ├── plans/                # Plan, PlanDay, PlanItem, ScheduledWorkout, scheduling service
│   ├── workouts/             # Session, SessionExercise, SetLog, Tag, runner/progression/records/summary services
│   ├── stats/                # Stats views + aggregation services
│   └── core/                 # Base views (today, healthz), template tags, mixins
├── templates/
│   ├── base.html
│   ├── components/           # Reusable includes (button, stepper, badge, sheet…)
│   └── <app>/                # Full pages; partials prefixed with "_" (e.g., _set_form.html)
├── static/
│   ├── src/input.css         # Tailwind entry + DaisyUI themes
│   ├── css/app.css           # Build output (gitignored)
│   ├── js/                   # timer.js, sortable-init.js, charts.js, sound.js
│   ├── vendor/               # htmx, alpine, sortable, chart.js, daisyui 5 package
│   └── img/icons/            # PWA icons
├── seed/
│   └── exercises.json
├── k8s/
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── configmap.yaml
│   └── secret.example.yaml
├── .github/workflows/
│   ├── ci.yml                # Ruff + pytest on PRs and pushes
│   └── docker-publish.yml    # Build + push to Docker Hub on main/tags
├── tests/                    # pytest tests mirroring apps/
└── docs/
    ├── PRD.md
    ├── DESIGN.md
    ├── TECH_SPEC.md
    └── decisions/            # ADRs: NNNN-title.md
```

> **Deployment consistency:** The owner's existing project `nathanroberts55/friendfitter` (Django + PostgreSQL + Tailwind + DaisyUI) is the reference for the Dockerfile, k8s manifests, and GitHub Actions. Where this spec and friendfitter's deployment files differ in mechanics (image naming, secrets handling, workflow triggers), **follow friendfitter** and record the choice in an ADR.

## 3. Data model

All timestamps are timezone-aware (`USE_TZ=True`, `TIME_ZONE="America/New_York"`). "Today" = `django.utils.timezone.localdate()`.

Every user-owned table has `user` (FK → `auth.User`, `on_delete=CASCADE`), and **every queryset in views must filter by `request.user`**.

Common abstract base `TimeStamped`: `created_at` (auto_now_add), `updated_at` (auto_now).

### 3.1 Entity relationships

```
User ─1:1─ UserSettings
User ─1:N─ Tag
User ─1:N─ Exercise (custom; seeded exercises have user = NULL)
MuscleGroup ─1:N─ Exercise (primary)   MuscleGroup ─M:N─ Exercise (secondary)
User ─1:N─ Plan ─1:N─ PlanDay ─1:N─ PlanItem ─N:1─ Exercise
PlanDay ─M:N─ MuscleGroup (focus)
Plan ─1:N─ ScheduledWorkout ─N:1─ PlanDay
User ─1:N─ Session ─0..1:1─ ScheduledWorkout (via Session.scheduled_workout)
Session ─M:N─ Tag
Session ─1:N─ SessionExercise ─N:1─ Exercise ; SessionExercise ─N:0..1─ PlanItem
SessionExercise ─1:N─ SetLog
```

### 3.2 `accounts`

**UserSettings**

| Field | Type | Notes |
|---|---|---|
| user | OneToOne(User) | Created automatically via post_save signal. |
| theme | Char choices `DARK`/`LIGHT`/`SYSTEM` | Default `DARK`. |
| default_rest_seconds | PositiveSmallInt | Default 90. |
| timer_sound | Bool | Default True. |
| default_tags | M2M(Tag) | Pre-selected on new unscheduled sessions. |

### 3.3 `exercises`

**MuscleGroup** (seeded, read-only in UI)

| Field | Type | Notes |
|---|---|---|
| name | Char(40) unique | Chest, Back, Shoulders, Biceps, Triceps, Forearms, Quads, Hamstrings, Glutes, Calves, Core, Cardio |
| slug | Slug unique | |
| display_order | PositiveSmallInt | Ordering for UI and chart colors. |

**Exercise**

| Field | Type | Notes |
|---|---|---|
| user | FK(User) null | NULL = seeded/global. |
| name | Char(100) | |
| primary_muscle | FK(MuscleGroup, PROTECT) | |
| secondary_muscles | M2M(MuscleGroup) blank | |
| tracking_type | Char choices | `WEIGHT_REPS`, `BODYWEIGHT`, `TIMED`, `CARDIO`, `WEIGHT_DISTANCE` |
| notes | Text blank | |
| is_archived | Bool default False | |

- Constraints: `UniqueConstraint(Lower("name"), "user")` for custom exercises. Seeded names are unique where `user IS NULL`. The form also rejects custom names matching a seeded name (case-insensitive).
- Archiving a seeded exercise is per-user → **ExerciseArchive** table (`user`, `exercise`, unique together) so global rows are never mutated by one user. Custom exercises use `is_archived`.
- Manager helper: `Exercise.objects.visible_to(user)` = (seeded not archived by user) ∪ (user's custom not archived).

### 3.4 `plans`

**Plan**

| Field | Type | Notes |
|---|---|---|
| user | FK(User) | |
| name | Char(100) | |
| split_type | Char choices | `FULL_BODY`, `UPPER_LOWER`, `PPL`, `BODY_PART`, `CUSTOM` |
| start_date | Date | |
| length_weeks | PositiveSmallInt null | NULL = open-ended. |
| status | Char choices | `DRAFT`, `ACTIVE`, `ARCHIVED` |
| activated_at / archived_at | DateTime null | |

- Constraint: `UniqueConstraint(fields=["user"], condition=Q(status="ACTIVE"), name="one_active_plan_per_user")`. Postgres enforces this as a partial unique index; SQLite supports it too.

**PlanDay**

| Field | Type | Notes |
|---|---|---|
| plan | FK(Plan, CASCADE) | |
| name | Char(60) | e.g., "Day A – Lower" |
| weekday | PositiveSmallInt 0–6 | 0 = Monday (Python `date.weekday()`). |
| order | PositiveSmallInt | Display order. |
| focus_muscles | M2M(MuscleGroup) blank | Drives picker suggestions. |

- Constraint: unique (`plan`, `weekday`).

**PlanItem**

| Field | Type | Notes |
|---|---|---|
| plan_day | FK(PlanDay, CASCADE) | |
| exercise | FK(Exercise, PROTECT) | |
| order | PositiveSmallInt | |
| superset_group | Char(1) blank | "A", "B"… within a day. Blank = none. Members must be contiguous in `order`. |
| target_sets | PositiveSmallInt | Default 3. |
| rep_min / rep_max | PositiveSmallInt null | `WEIGHT_REPS`, `BODYWEIGHT`. Check `rep_min <= rep_max`. |
| target_seconds | PositiveInt null | `TIMED`, `CARDIO`. |
| target_distance_mi | Decimal(6,2) null | `CARDIO`, `WEIGHT_DISTANCE`. |
| rest_seconds | PositiveSmallInt | Default from UserSettings. |
| notes | Char(200) blank | |

**ScheduledWorkout**

| Field | Type | Notes |
|---|---|---|
| user | FK(User) | Denormalized for easy filtering. |
| plan | FK(Plan, CASCADE) | |
| plan_day | FK(PlanDay, CASCADE) | |
| scheduled_date | Date | |
| status | Char choices | `PENDING`, `COMPLETED`, `MISSED`, `MADE_UP` |
| marked_missed_manually | Bool default False | |

- Constraint: unique (`plan`, `plan_day`, `scheduled_date`). Index (`user`, `scheduled_date`).

### 3.5 `workouts`

**Tag**

| Field | Type | Notes |
|---|---|---|
| user | FK(User) | |
| name | Char(30) | Unique per user (case-insensitive). |
| color | Char(7) | Hex; picked from the chart palette. |

**Session**

| Field | Type | Notes |
|---|---|---|
| user | FK(User) | |
| kind | Char choices | `SCHEDULED`, `UNSCHEDULED` |
| scheduled_workout | OneToOne(ScheduledWorkout, SET_NULL) null | Set when kind = SCHEDULED. |
| plan_day | FK(PlanDay, SET_NULL) null | For "same Plan Day" comparisons. |
| title | Char(100) | Plan Day name, or user-entered. |
| performed_date | Date | Local date the workout happened. |
| status | Char choices | `IN_PROGRESS`, `COMPLETED` |
| started_at | DateTime null | Null for retro logs without a time. |
| completed_at | DateTime null | |
| duration_seconds | PositiveInt null | Retro logs only (otherwise derived). |
| is_retro_log | Bool default False | Logged after the fact (no runner). |
| tags | M2M(Tag) blank | |

- Constraint: `UniqueConstraint(fields=["user"], condition=Q(status="IN_PROGRESS"), name="one_in_progress_session_per_user")`.
- Discard = hard delete of an `IN_PROGRESS` session (cascades). The linked ScheduledWorkout status is then recomputed.

**SessionExercise** (snapshot of targets at start)

| Field | Type | Notes |
|---|---|---|
| session | FK(Session, CASCADE) | |
| exercise | FK(Exercise, PROTECT) | |
| plan_item | FK(PlanItem, SET_NULL) null | |
| order | PositiveSmallInt | Mutable during the workout (reorder). |
| superset_group | Char(1) blank | Copied from PlanItem. |
| target_sets | PositiveSmallInt | Incremented by "Add set". |
| planned_sets | PositiveSmallInt | Original target; never changes. Used for the increase flag and "x of y planned". |
| rep_min, rep_max, target_seconds, target_distance_mi, rest_seconds | as PlanItem | Snapshot. |
| status | Char choices | `PENDING`, `IN_PROGRESS`, `DONE`, `SKIPPED` |

**SetLog**

| Field | Type | Notes |
|---|---|---|
| session_exercise | FK(SessionExercise, CASCADE) | |
| set_number | PositiveSmallInt | 1-based. |
| status | Char choices | `DONE`, `SKIPPED` |
| weight_lb | Decimal(6,2) null | Weight or added weight. |
| reps | PositiveSmallInt null | |
| duration_seconds | PositiveInt null | |
| distance_mi | Decimal(6,2) null | |
| difficulty | PositiveSmallInt null | 1–10, check constraint. |
| is_extra | Bool | True if `set_number > planned_sets`. |
| client_id | UUID unique | Idempotency key generated in the form. Duplicate submit returns the existing row. |
| completed_at | DateTime | |

- Constraint: unique (`session_exercise`, `set_number`).
- Validation per tracking type (PRD §8.2) lives in one function `validate_set_fields(tracking_type, data)`, used by the runner and edit forms.

## 4. Domain services

Business logic lives in `apps/<app>/services/*.py` as plain functions. Views stay thin: parse input → call service → render. Every service listed here **must have unit tests**.

### 4.1 `plans/services/scheduling.py`

- `activate_plan(plan, today) -> None`: in one transaction, archive the current active plan, set status ACTIVE, then `generate_schedule`.
- `generate_schedule(plan, today, horizon_days=14, start_from=None) -> int`:
  - week 1 starts on the Monday of the week containing `start_date`; dates before `start_date` are skipped
  - `start_from` limits creation to that date or later (defaults to `start_date`)
  - fixed length: generate all weeks
  - open-ended: generate through `today + horizon_days`
  - idempotent via `get_or_create`
- `regenerate_future(plan, today)`: after plan edits, delete `PENDING` rows with `scheduled_date >= today` and no session, then call `generate_schedule` with `start_from=today` so edits never backfill the past.
- `archive_plan(plan, today)`: delete future `PENDING` rows without a session; status ARCHIVED.
- `sync_statuses(user, today)`: `PENDING` with `scheduled_date < today` → `MISSED`. Called by Today, History, and Stats views (cheap single UPDATE). Also extends the horizon for an open-ended active plan.
- `resolve_status_on_complete(scheduled_workout, performed_date)`: `COMPLETED` if dates match, else `MADE_UP`. On session delete or date edit, recompute: no completed session → `PENDING` if date ≥ today else `MISSED`.
- `week_number(plan, today) -> int`.

### 4.2 `workouts/services/runner.py`

- `start_scheduled_session(user, scheduled_workout) -> Session`: enforce a single in-progress session; snapshot PlanItems → SessionExercises (`planned_sets = target_sets`).
- `next_step(session) -> Step | None`: pure function over the session's exercises and logged sets. Returns `Step(session_exercise, set_number, is_superset, superset_label, round_number, total_rounds, rest_after_seconds)`. Algorithm:
  1. Walk SessionExercises by `order`, grouping contiguous items with the same non-blank `superset_group` into blocks.
  2. The first block with any exercise having remaining sets (`logged_count < target_sets` and status not SKIPPED) is current.
  3. Single-exercise block: next set of that exercise.
  4. Superset block: round `r` = min over active members of `logged_count + 1`; return the first member (in order) whose `logged_count + 1 == r`. Members that are complete are skipped.
  5. `rest_after_seconds` for the step = the exercise's `rest_seconds`, except inside a superset: 0 unless this step finishes the round, in which case use the last member's `rest_seconds`.
  6. If this is the final step of the session, rest = 0.
- `log_set(session, session_exercise, data, client_id) -> SetLog`: validate, idempotent on `client_id`, mark the exercise IN_PROGRESS/DONE.
- `skip_set`, `add_set` (`target_sets += 1` for this session only), `skip_exercise` (records remaining sets as SKIPPED), `add_exercise` (defaults to 3 sets, blank targets, and the user's default rest).
- `reorder(session, ordered_ids)`: completed or fully logged blocks are locked at the top; the remaining blocks move as units, and superset members stay consecutive.
- `jump_to(session, session_exercise)`: inserts the block directly after the last block that has been started (status `IN_PROGRESS`/`DONE`/`SKIPPED` or any logged set). The ▲▼ `move_exercise` helper is the non-drag fallback.
- `finish_session(session, now)`: records `SKIPPED` for every remaining planned set, marks an exercise `DONE` when it has at least one completed set and `SKIPPED` otherwise, sets status COMPLETED and `completed_at`, then calls `resolve_status_on_complete`.
- `discard_session(session, today)`: hard-deletes the in-progress session and recomputes the linked ScheduledWorkout status (`PENDING` or `MISSED`).

### 4.3 `workouts/services/sessions.py`

- `start_unscheduled_session(user, *, title, tag_ids=(), items) -> Session`: validates the title and at least one exercise, applies default tags when none are passed, snapshots each item into a `SessionExercise`, and creates an `IN_PROGRESS` unscheduled session. A second in-progress session is refused.
- `create_retro_session(user, *, title, performed_date, start_time=None, duration_seconds=None, tag_ids=(), items) -> Session`: records a completed `is_retro_log` session for today or a past date; future dates are rejected. `started_at`/`completed_at` are derived from the date, optional start time, and duration.
- `update_session_metadata(user, session, *, title, performed_date, tag_ids=())`: renames, re-dates, and re-tags a session, then calls `scheduling.recompute_status_after_session_change` when the performed date moves so the linked `ScheduledWorkout` becomes `COMPLETED`, `MADE_UP`, `PENDING`, or `MISSED` as appropriate.
- `delete_session(user, session, *, today=None)`: deletes a session and recomputes its linked `ScheduledWorkout` status.
- `add_manual_set(user, session, session_exercise, data) -> SetLog`: appends the next set number after the last existing set; a set beyond `target_sets` is flagged `is_extra`; marks the exercise `DONE`.
- `update_manual_set(user, set_log, data) -> SetLog` and `delete_manual_set(user, set_log)`: edit or remove a set from a completed session. Delete renumbers the remaining sets and recomputes the exercise status.
- Every function asserts the session, exercise, or set belongs to `user`.

### 4.4 `workouts/services/tags.py`

- `TAG_PALETTE`: the DESIGN chart palette (blue, cyan, amber, green, purple, pink, brown, gray).
- `list_tags(user)` returns tags annotated with `session_count`; `get_tag`, `create_tag`, `update_tag`, and `delete_tag` are user-scoped.
- `resolve_tags(user, tag_ids)` validates that every id belongs to the user before attaching tags to a session.
- `default_tags(user)` / `set_default_tags(user, tag_ids)` read and write `UserSettings.default_tags`.

### 4.5 `workouts/services/history.py`

- `list_sessions(user, *, tag=None, exclude_tag=None, plan=None)`: completed sessions, newest first, with tag and plan filters.
- `calendar_month(user, year, month, *, tag=None, exclude_tag=None, plan=None, today)`: a Monday-start month grid with per-day status dots (`COMPLETED`, `MISSED`, `MADE_UP`, `PENDING`, `UNSCHEDULED`) plus the entries for each day.
- `build_history(user, *, view, year, month, selected_day, tag, exclude_tag, plan, today)`: resolves the visible month, the selected day, its scheduled workouts and sessions, and the filter labels used by the template.
- A make-up session is dotted `MADE_UP` on its original scheduled date and `COMPLETED` on the date it was performed. Tag filters apply to sessions; when a tag filter is active, scheduled workouts are limited to those with a matching session.

### 4.6 `workouts/services/progression.py`

- `last_time(user, exercise, plan_day=None, *, exclude_session=None) -> SessionExercise | None`: the most recent COMPLETED session's SessionExercise for the exercise, preferring the same `plan_day`, excluding the current session.
- `prefill(user, session_exercise, set_number) -> dict`: rules in PRD F-07. Targets are the fallback when there is no history; the same set number is preferred, otherwise the last completed set's weight.
- `increase_flag(session_exercise) -> bool`: tracking type in (`WEIGHT_REPS`, `BODYWEIGHT`) and `rep_max` set; non-extra DONE sets count ≥ `planned_sets`; all non-extra DONE sets have `reps >= rep_max`.
- `flag_for_upcoming(user, exercise, plan_day) -> bool` = `increase_flag(last_time(...))`.
- `last_time_display(user, session_exercise) -> str`: compact `Last:` values per tracking type for the set screen.

### 4.7 `workouts/services/records.py`

- `prs_for_exercise(user, exercise)`: heaviest weight, plus the max reps per weight.
- `prs_set_in_session(session) -> list[PR]`: compare each DONE set with all DONE sets from sessions with an earlier `(performed_date, completed_at)` order. Rules in PRD F-10. Computed on demand, not stored.

### 4.8 `workouts/services/summary.py`

`build_summary(session) -> Summary` dataclass with all PRD F-08 fields. Tonnage counts DONE sets of type `WEIGHT_REPS` (weight × reps). Comparison session: the previous COMPLETED session with the same `plan_day` (scheduled) or same `title` (unscheduled).

### 4.9 `stats/services/aggregations.py`

- `top_set_series(user, exercise, since)`: per session date, the max weight (with its reps).
- `weekly_volume(user, weeks=8, metric="sets"|"tonnage", tag_include=None, tag_exclude=None)`: grouped by ISO week (Monday start) × primary muscle group. Use `TruncWeek` on `performed_date`.
- `adherence(plan)`: counts by status (excluding PENDING) plus the streak (PRD F-08).
- `calendar_month(user, year, month, tags=None)`: per-day status dots.

## 5. URLs and views

All views use `LoginRequiredMixin` / `@login_required` except login and healthz. HTMX endpoints return partials when `request.htmx` is set (use `django-htmx`), otherwise redirect to the full page.

| Method | Path | View | Notes |
|---|---|---|---|
| GET | `/` | today | Calls `sync_statuses`. |
| GET/POST | `/login/`, `/logout/` | Django auth | |
| GET | `/healthz/` | healthz | 200 + DB check. No auth. |
| GET/POST | `/settings/` | settings | Theme, rest, sound, default tags, tag management, and change-password link. |
| GET/POST | `/settings/password/` | change password | Django's password-change form with the app's input styling. |
| GET/POST | `/settings/tags/new/`, `/settings/tags/<id>/edit/`, `/settings/tags/<id>/delete/` | tag CRUD | Full-page POST/redirect flows so Settings always sees fresh tag and default-tag choices. Delete renders a confirmation page and posts `confirm=1`. |
| GET | `/library/` | exercise list | `?q=`, `?muscle=`, `?archived=1` |
| GET/POST | `/library/new/`, `/library/<id>/edit/` | exercise form | Seeded exercises are read-only. |
| GET | `/library/<id>/` | exercise detail | |
| POST | `/library/<id>/archive/`, `/library/<id>/restore/` | archive toggle | Seeded rows archive per user via `ExerciseArchive`; custom rows use `is_archived`. |
| GET | `/plans/` | plan list | Active, drafts, and archived groups. |
| GET/POST | `/plans/new/` | new plan | Creates a draft and redirects to the builder. |
| GET/POST | `/plans/<id>/` | plan builder | List form at every width (M2). Plan settings post to the same URL. |
| POST | `/plans/<id>/days/` | add day | |
| POST | `/plans/<id>/days/<day_id>/edit/`, `/delete/` | day edit/delete | Delete asks for confirmation; blocked when past or completed workouts exist. |
| POST | `/plans/<id>/days/<day_id>/reorder/` | reorder items | Accepts `ordered_ids`; validates that supersets stay contiguous. |
| POST | `/plans/<id>/days/<day_id>/superset/`, `/superset/clear/` | supersets | Groups consecutive items under a label A–Z. |
| GET/POST | `/plans/<id>/days/<day_id>/items/new/` | add item | Inline exercise creation posts a second form to the same URL. |
| POST | `/plans/<id>/items/<item_id>/edit/`, `/delete/`, `/move/` | item CRUD and ▲▼ | |
| POST | `/plans/<id>/activate/`, `/archive/`, `/duplicate/` | | Activate and archive ask for confirmation. |
| GET | `/plans/<id>/picker/?day=<id>&q=` | exercise picker partial | Focus-group-first sorting; HTMX partial. |
| POST | `/schedule/<id>/start/` | start scheduled session | Creates the session (or resumes the one in progress) and redirects to the runner. |
| POST | `/schedule/<id>/mark-missed/` | mark today's workout missed | |
| GET/POST | `/sessions/new/` | plan & start unscheduled | Title, tags, and exercise rows with targets. `add_row` re-renders the bound formset with one more row; Start creates an in-progress session and redirects to the runner. |
| GET/POST | `/sessions/log/` | retro log form | Title, date, optional start time/duration, tags, and exercise rows. Creates a completed `is_retro_log` session and redirects to its detail page for set entry. |
| GET | `/sessions/<id>/run/` | runner page | Renders the current step or completion card. `?panel=menu|reorder|jump|add` renders a sheet; HTMX returns only `#runner`. |
| POST | `/sessions/<id>/sets/` | log set | HTMX: rest overlay plus the next step, or the completion card. Plain POST: redirect with rest skipped. |
| POST | `/sessions/<id>/skip-set/`, `/add-set/`, `/skip-exercise/`, `/add-exercise/`, `/reorder/`, `/move-exercise/`, `/jump/<se_id>/` | runner actions | Each returns `#runner` for HTMX and redirects otherwise. |
| GET | `/sessions/<id>/picker/?q=` | exercise picker partial | HTMX search for the add-exercise sheet. |
| POST | `/sessions/<id>/finish/`, `/discard/` | | Finish returns the completion card (or redirects). Discard asks for a server-rendered confirmation page first. |
| GET | `/sessions/<id>/` | summary / detail | Shows the session's snapshot targets, tags, sets, and edit/delete actions. An in-progress session links to the runner instead of showing set forms. |
| GET/POST | `/sessions/<id>/edit/`, `/sessions/<id>/delete/` | session metadata editing | Edit changes title, performed date, and tags. Delete renders a confirmation page and posts `confirm=1`. |
| POST | `/sessions/<id>/sets/add/` | add a set | Full-page POST + redirect to the session detail; appends the next set number. |
| GET/POST | `/sets/<id>/edit/` | edit a set | HTMX targets `#set-<id>` for an inline row swap; a full-page GET and POST are always available. |
| GET | `/sets/<id>/row/` | set row partial | Cancels an inline edit by restoring the read-only row. |
| GET/POST | `/sets/<id>/delete/` | delete a set | Confirmation page; renumbers the remaining sets. |
| GET | `/history/` | calendar/list | `?view=calendar|list&month=YYYY-MM&day=YYYY-MM-DD&tag=&exclude_tag=&plan=`. Tag filters apply to sessions; a tag filter limits scheduled workouts to those with a matching session. |
| GET | `/stats/` | stats tabs | `?tab=progress|prs|volume` |
| GET | `/stats/api/…` | JSON for Chart.js | Small JSON views, login required. |
| GET | `/manifest.webmanifest` | manifest | |
| — | `/admin/` | Django admin | Register all models. |

## 6. Frontend conventions

- `base.html`:
  - sets `<html data-theme="liftlist-dark|liftlist-light">` server-side from UserSettings (`SYSTEM` → a tiny inline script picks by `prefers-color-scheme` before paint)
  - loads `app.css`, htmx, alpine, and the CSRF header config (`hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'` on `<body>`)
  - enables `hx-boost="true"` on `<body>` only for authenticated users; logout, delete, activate, archive, confirmation, and fragment-saving forms opt out with `hx-boost="false"`
  - loads SortableJS, `plan-reorder.js`, and `htmx-focus.js` once for authenticated pages
- **HTMX partial contract (ADR 0004):** high-frequency actions keep their POST + redirect fallback and add a `request.htmx` branch that returns a 200 partial. A partial contains:
  1. one root element whose `id` matches the swap target, and
  2. an out-of-band `#messages` region (`hx-swap-oob="true"`) so alerts appear without a reload.

  Swap targets:
  - `#day-items-<day_id>` for ▲▼ move, drag reorder, superset create, and superset clear. Only the items region is replaced, so the day header and an open “Edit day and focus” panel keep their state.
  - `#today-content` for “Mark as missed”, which can change the today card, catch-up list, and week strip together.
  - `#set-<set_id>` for editing a set from the session detail; `#library-list` for the library search form.

  **Gate fragment responses on `HX-Target`, not just `request.htmx`.** `hx-boost` makes ordinary navigation look like an HTMX request, so a view that returns a partial for every `request.htmx` would replace the whole page with a fragment. A view returns its partial only when `request.headers.get("HX-Target")` matches the intended container (for example `library-list` or `runner`); boosted page requests get the full template.

  Action buttons keep stable IDs (`move-up-<item_id>`, `move-down-<item_id>`, `superset-<day_id>`, `clear-superset-<day_id>-<group>`, `mark-missed`) so htmx restores focus after a swap. `hx-disabled-elt` disables the control in flight; `find button` covers move forms and `#superset-<day_id>` covers the superset button that lives outside its hidden form. Because disabling the pressed control moves focus to the document, `htmx-focus.js` remembers the active element's `id` on `htmx:beforeRequest` and restores it on `htmx:afterSettle`.
- **Full-page flows stay full-page.** Tag CRUD, history filters, the unscheduled/retro forms, and session deletion use ordinary POST/redirect responses even when HTMX is present, because they change data that the Settings or History page must re-read (tag choices, default-tag chips, calendar dots). Only the set row editor and library search add a fragment branch.
- `templates/components/messages.html` renders the `#messages` wrapper on every page. `messages_oob.html` renders the same block with `hx-swap-oob="true"` and is included only in partial responses, never in a full page.
- Partials are named `_name.html` and live beside their page template.
- Component includes live in `templates/components/` (`button.html`, `stepper.html`, `badge.html`, `sheet.html`, `status_dot.html`, `tag_chip.html`, `empty_state.html`).
- **Runner swap pattern (ADR 0005):** `#runner` is the single swap target. Runner POSTs use `hx-target="#runner" hx-swap="outerHTML"` and return `_runner_swap.html`, which contains `#runner` plus an out-of-band `#messages`. The fragment branches to a panel (`menu`, `reorder`, `jump`, `add`), the set screen, or the completion card. A plain POST redirects to `/sessions/<id>/run/`.
  - When `rest > 0` the fragment renders `_rest.html` over the next `_set_form.html`. The next form is already in the DOM but `inert`; when the countdown ends or Skip is tapped, Alpine hides the overlay, clears `inert`, focuses the first field, and beeps.
  - Without HTMX the view redirects with `rest_seconds=0`, so the rest overlay is never rendered and the next set form appears directly.
- **Timer** (`static/js/timer.js`, Alpine component):
  - `endAt = Date.now() + rest*1000`, ticks every 250 ms, displays `max(0, ceil((endAt − now)/1000))`
  - ±15 s adjusts `endAt`; Skip calls the same finish path immediately
  - counting from a fixed end time means a throttled background tab returns to the correct remaining time, or advances if the rest already elapsed
- **Sound** (`static/js/sound.js`): Web Audio API, two short 880 Hz beeps. Create/resume the `AudioContext` on the Submit tap (iOS requires a user gesture). The rest timer beeps on completion when `UserSettings.timer_sound` is on; the toggle in Settings controls it.
- **Validation errors:** `ValidationError` from a runner service adds a message and returns the same `#runner` fragment with `save_failed=True`, which renders a Retry save button and keeps the submitted values. A plain POST redirects and shows the message; the fields fall back to their pre-filled values. HTMX transport errors are left to the browser instead of a separate error card.
- **Idempotency:** `_set_form.html` renders a hidden `client_id` (`uuid4`) per step. A replayed submit returns the existing `SetLog` rather than creating a duplicate.
- **Drag-and-drop:** SortableJS on plan day columns and the runner reorder sheet. On `onEnd`, POST the ordered ids with HTMX. Provide ▲▼ buttons everywhere as the fallback. `plan-reorder.js` loads once for authenticated pages, initializes each `[data-sortable]` container once (`data-sortable-ready`), and re-initializes inside the swapped target on `htmx:afterSwap`.
- **Charts:** Chart.js initialized from `data-*` JSON or `/stats/api/` endpoints. Colors read from CSS variables so they follow the theme.
- **Tailwind:** `static/src/input.css` contains `@import "tailwindcss" source(none);`, `@plugin "../vendor/daisyui/index.js"`, and two `@plugin "../vendor/daisyui/theme/index.js" { … }` theme blocks using DESIGN §2 tokens. DaisyUI 5.7.50 no longer ships the `daisyui.mjs` / `daisyui-theme.mjs` files named in earlier drafts; the vendored package's JS entry points work with the standalone CLI (ADR 0002). Build:
  - dev: `tailwindcss -i static/src/input.css -o static/css/app.css --watch`
  - prod: same with `--minify` in the Docker build

  Windows dev uses `tailwindcss-windows-x64.exe`.

## 7. Configuration (environment variables)

| Variable | Dev default | Prod | Purpose |
|---|---|---|---|
| `DJANGO_SECRET_KEY` | insecure dev key | **required** | |
| `DJANGO_DEBUG` | `1` | `0` | |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | public hostname(s) | Comma-separated. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | — | `https://<public-host>` | Required behind Cloudflare. |
| `DATABASE_URL` | unset → SQLite `db.sqlite3` | `postgres://user:pass@host:5432/liftlist` | via `dj-database-url` |
| `DJANGO_SECURE_COOKIES` | `0` when `DEBUG=1` | `1` | Set `0` for plain-HTTP local stacks; compose does. |
| `DJANGO_SUPERUSER_USERNAME` / `_PASSWORD` / `_EMAIL` | optional | optional | If set, entrypoint creates the superuser if missing. |
| `TZ` / `TIME_ZONE` | `America/New_York` | same | |
| `GUNICORN_WORKERS` | — | `2` | |

Production settings when `DEBUG=0`:
- `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`
- `SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = True` (override with `DJANGO_SECURE_COOKIES=0` for plain-HTTP stacks)
- `SESSION_COOKIE_AGE = 60*60*24*30`
- WhiteNoise `CompressedManifestStaticFilesStorage`
- logging to stdout

## 8. Dependencies

`requirements.txt` (pin exact versions at scaffold time):
`Django~=5.2`, `psycopg[binary]`, `dj-database-url`, `gunicorn`, `whitenoise`, `django-htmx`.

`requirements-dev.txt`: `-r requirements.txt`, `pytest`, `pytest-django`, `ruff`, `freezegun` (date-dependent tests).

Adding any other dependency requires an ADR (see AGENTS.md).

## 9. Seed data

- `seed/exercises.json`: list of `{name, primary, secondary[], tracking_type}`.
- Muscle groups are created by a **data migration** in `exercises` (stable, required for FKs).
- `python manage.py seed_exercises`: idempotent upsert by name for `user IS NULL` rows. It never deletes and never overwrites user archives. Runs in `entrypoint.sh` after `migrate`.

## 10. Containers and deployment

### 10.1 Dockerfile (multi-stage)

1. **css stage:** `debian:bookworm-slim`. Download a pinned Tailwind v4 standalone binary, copy `static/` and `templates/` (Tailwind scans templates for classes), build `app.css --minify`.
2. **runtime stage:** `python:3.12-slim`.
   - Set `PYTHONDONTWRITEBYTECODE=1` and `PYTHONUNBUFFERED=1`.
   - `pip install --no-cache-dir -r requirements.txt`.
   - Copy the app and the built CSS.
   - Run `collectstatic --noinput --ignore "src/*" --ignore "vendor/daisyui/*"` (the Tailwind entry source and DaisyUI build package are not served assets).
   - Run as a non-root user, `EXPOSE 8000`, `ENTRYPOINT ["./entrypoint.sh"]`.

`entrypoint.sh`:
```sh
set -e
python manage.py migrate --noinput
# python manage.py seed_exercises   # enabled in M1, when the exercises app exists
python manage.py ensure_superuser   # no-op unless env vars set
exec gunicorn liftlist.wsgi:application --bind 0.0.0.0:8000 --workers ${GUNICORN_WORKERS:-2} --access-logfile -
```

### 10.2 Local

- **Fast dev (Windows 11, SQLite):**
  ```powershell
  python -m venv .venv
  .venv\Scripts\Activate.ps1
  pip install -r requirements-dev.txt
  python manage.py migrate
  # python manage.py seed_exercises   # available from M1
  python manage.py createsuperuser
  python manage.py runserver
  ```
  Run the Tailwind watcher in a second terminal.
- **Prod-like:** `docker compose up --build` runs `web` (built from the Dockerfile) and `db` (`postgres:16`, named volume). Every value has a working default; `.env` is optional. App on `http://localhost:8000`.

### 10.3 Kubernetes (prod)

- `Deployment`:
  - 1 replica, image `<dockerhub-user>/liftlist:<tag>`
  - env from `ConfigMap` (non-secret) and `Secret` (secret key, `DATABASE_URL`, superuser)
  - `readinessProbe` and `livenessProbe` on `GET /healthz/`
  - resources: requests 100m CPU / 192Mi, limits 500m / 512Mi
- `Service`: ClusterIP on port 8000, exposed via the Cloudflare tunnel per the friendfitter setup.
- Postgres on the host: a dedicated database `liftlist` and role `liftlist`. `DATABASE_URL` points to the host address reachable from the cluster.
- Migrations run at container start. With 1 replica this is safe. If replicas are ever > 1, move migrations to a k8s `Job` or initContainer (ADR required).

### 10.4 CI/CD (GitHub Actions)

- `ci.yml`: on PR and push → set up Python 3.12 → `pip install -r requirements-dev.txt` → `ruff check .` → `ruff format --check .` → `pytest`.
- `docker-publish.yml`: on push to `main` and on `v*` tags → build → push `:latest`, `:sha-<short>`, and `:vX.Y.Z` to Docker Hub (secrets `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`).
- Rollout: update the Deployment image tag (or `kubectl rollout restart` for `:latest`), matching friendfitter's process.

## 11. Backups (recommended, outside the app)

Not part of the v1 app. Recommended on the Linux host because Postgres runs there:

```cron
# Nightly at 3:15 — compressed dump, keep 14 days
15 3 * * * pg_dump -Fc -U liftlist liftlist > /backups/liftlist/liftlist-$(date +\%F).dump && find /backups/liftlist -name '*.dump' -mtime +14 -delete
```

Restore: `pg_restore -c -U liftlist -d liftlist <file>.dump`. A k8s `CronJob` is an alternative (future ADR).

## 12. Testing strategy

- **pytest-django**, tests in `tests/` mirroring `apps/`. Use simple factory functions in `tests/factories.py` (no extra library).
- **Required unit tests** (service layer):
  - scheduling: generation (fixed and open-ended, start mid-week), `sync_statuses`, made-up vs completed, regenerate after edit, archive
  - runner `next_step`: normal order, supersets (equal and unequal set counts), skip set/exercise, add set, reorder, jump, last-step rest = 0
  - progression: last-time preference (same plan day first), prefill fallbacks, increase flag (PRD AC cases, extra sets ignored, skipped sets block the flag)
  - records: heaviest weight, rep PR rules (first use of a weight is not a rep PR)
  - summary + aggregations: tonnage, weekly volume grouping, adherence, streak
  - set validation per tracking type, idempotent `client_id`
- **View tests:** auth required on every route, user data isolation (user B gets 404 on user A's objects), runner happy path via the test client.
- Use `freezegun` for any date logic. Never depend on the real current date.
- CI must pass before merge.

## 13. Security

- Login required everywhere except `/login/`, `/healthz/`, and `/manifest.webmanifest`. The admin login view is exempt by Django so `/admin/` can authenticate staff.
- All object lookups use `get_object_or_404(Model, pk=…, user=request.user)` (or through the parent chain).
- CSRF on all state-changing requests (HTMX header configured in base).
- No secrets in git. `.env` is gitignored, and `.env.example` documents the variables.
- Django admin is available at `/admin/` (superuser only).
