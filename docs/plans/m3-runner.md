# M3 implementation plan — workout runner, rest timer, progression

- **Status:** Complete (2026-11-06)
- **Date:** 2026-11-06
- **Scope:** F-05 (Workout Runner) and F-07 (Progression), plus the Today entry points that M3 unblocks
- **Related:** PRD F-05/F-07/§8.2; DESIGN §7.3–7.5, §8; TECH_SPEC §3.5, §4.2–4.3, §5, §6; ADR 0005
- **Follow-up:** F-08 summary and F-06 unscheduled/tag UI stay in M4/M5. M3 ships a completion card, not the full summary.

## 1. Goal

Make the gym flow usable end to end:

1. Start a Scheduled Workout from Today, or resume the one session already in progress.
2. Log one set at a time with type-specific inputs, pre-filled from the last time.
3. Rotate supersets correctly and show a rest timer between rounds.
4. Skip sets/exercises, add sets/exercises, reorder, and jump ahead without touching the plan.
5. Finish or discard. Finishing updates the Scheduled Workout to `COMPLETED`/`MADE_UP`.
6. Show the increase flag on Today, the set screen, and the completion card.

## 2. Decisions

- **New app `apps.workouts`** owns `Tag`, `Session`, `SessionExercise`, and `SetLog`, exactly as TECH_SPEC §3.5 describes. `Tag` exists now because `Session.tags` is part of the model, but tag UI waits for F-06.
- **The runner is server-rendered state plus one swap target.** `GET /sessions/<id>/run/` renders `#runner`; every POST returns the same partial (`_runner_swap.html`) with out-of-band messages. Without HTMX the same POST redirects to the runner page.
- **The rest screen is server-rendered, with a JS countdown.** After an HTMX set submit, the response includes the rest duration for the step that was just completed. The rest overlay is rendered on top of the next set screen, which is already in the DOM but locked with `inert`. Alpine counts down from a fixed end time, then removes the overlay and focuses the next field. A plain POST (JavaScript off) redirects with `rest_seconds=0`, so the next set form appears directly and the rest overlay is never rendered.
- **Finishing early writes SKIPPED rows** for the remaining planned set numbers of every unfinished exercise. That keeps "planned vs completed" honest and makes the increase rule simple.
- **Discard is a hard delete** of an `IN_PROGRESS` session and recomputes the linked Scheduled Workout status. It keeps the server-rendered confirmation page.
- **Only one session can be in progress.** Enforced in the service and by a partial unique constraint.
- **Idempotency:** the set form carries a `client_id` UUID. A duplicate submit returns the existing `SetLog` instead of creating a second one.
- **No new dependency, no new service outside TECH_SPEC.** No Chart.js, no summary service yet.

## 3. Non-goals

- Unscheduled sessions (F-06) and tag management UI.
- The full workout summary, PRs, and stats (F-08/F-10).
- Editing completed sessions or sets (M4).
- Sound preference UI (F-11). M3 beeps by default; the setting arrives with the rest of F-11.
- Any PRD §4 non-goal.

## 4. Data model checklist (`apps.workouts`)

- [x] `Tag`: user, name (case-insensitive unique per user), color.
- [x] `Session`: user, kind, scheduled_workout (1:1, SET_NULL), plan_day (SET_NULL), title, performed_date, status, started_at, completed_at, duration_seconds, is_retro_log, tags.
  - [x] one `IN_PROGRESS` session per user.
- [x] `SessionExercise`: session, exercise (PROTECT), plan_item (SET_NULL), order, superset_group, target_sets, planned_sets, rep_min, rep_max, target_seconds, target_distance_mi, rest_seconds, status.
- [x] `SetLog`: session_exercise, set_number, status, weight_lb, reps, duration_seconds, distance_mi, difficulty (1–10 or null), is_extra, client_id (unique), completed_at.
  - [x] unique `(session_exercise, set_number)`.
- [x] Admin registrations and committed migration.
- [x] Add `apps.workouts` to `INSTALLED_APPS` and the URLconf.

## 5. Services checklist

### 5.1 `services/runner.py`

- [x] `start_scheduled_session(user, scheduled_workout)` with one-in-progress guard and target snapshot.
- [x] `next_step(session)` step engine per TECH_SPEC §4.2, including superset rotation and rest rules.
- [x] `log_set`, `skip_set`, `add_set`, `skip_exercise`, `add_exercise`.
- [x] `reorder`, `move_exercise`, `jump_to`.
- [x] `finish_session`, `discard_session`.
- [x] `validate_set_fields(tracking_type, data)` per PRD §8.2.
- [x] Pure helpers exposed for templates/tests: `remaining_sets`, `exercise_position`, `goal_label`.

### 5.2 `services/progression.py`

- [x] `last_time(user, exercise, plan_day=None, exclude_session=None)` with same-Plan-Day preference.
- [x] `prefill(user, session_exercise, set_number)`.
- [x] `increase_flag(session_exercise)` and `flag_for_upcoming(user, exercise, plan_day)`.
- [x] `last_time_display(user, session_exercise)` for the `Last:` line.

## 6. Views and URLs checklist

- [x] `POST /schedule/<id>/start/` → create session → runner.
- [x] `GET /sessions/<id>/run/` → runner page, optional `?panel=menu|reorder|jump|add&q=`.
- [x] `POST /sessions/<id>/sets/` → log set (HTMX rest response, redirect fallback).
- [x] `POST /sessions/<id>/skip-set/`, `/add-set/`, `/skip-exercise/`, `/add-exercise/`, `/reorder/`, `/move-exercise/`, `/jump/<se_id>/`.
- [x] `POST /sessions/<id>/finish/`, `/discard/`.
- [x] `GET /sessions/<id>/picker/` → exercise picker partial.
- [x] Every lookup uses `get_object_or_404(..., user=request.user)`; a different user gets 404.

## 7. Templates and JS checklist

- [x] `workouts/run.html`, `_runner_content.html`, `_runner_swap.html`, `_set_form.html`, `_rest.html`, `_menu.html`, `_reorder_sheet.html`, `_add_exercise.html`, `_jump_sheet.html`, `_finish.html`, `_set_row.html`.
- [x] Today: resume banner with Finish/Discard, Start Workout, catch-up Start, increase badges, remove M3 placeholders.
- [x] `static/js/timer.js`: fixed-end-time countdown, ±15 s, skip, focus next field, announce at 10 s and 0 s.
- [x] `static/js/sound.js`: two short Web Audio beeps, no asset.
- [x] Reuse `plan-reorder.js` for the runner reorder sheet, with ▲▼ fallback.
- [x] Add runner icons to `bin/generate_icons.py` and regenerate `_icon_data.py`.

## 8. Testing checklist

- [x] Model tests: defaults, constraints, one-in-progress, tag uniqueness, set-number uniqueness.
- [x] Runner service tests: snapshot, step engine (normal, superset, final rest), validation per tracking type, idempotent log, skip, add, reorder, jump, finish/discard status changes.
- [x] Progression tests: same-day preference and fallback, prefill rules, increase flag boundaries, display strings.
- [x] View tests: auth, start, resume banner, all runner actions, HTMX partials, duplicate submit, user isolation, finish/discard, completed runner.
- [x] Update Today tests for the new Start/Resume content.
- [x] `ruff check .`, `ruff format --check .`, `pytest`, `manage.py check`, `makemigrations --check --dry-run`.
- [x] Headless probe at 375 px and 768 px: start → log → rest → next → superset → reorder → finish, plus a no-JS POST fallback.

## 9. Docs

- [x] `CHANGELOG.md` under `## [Unreleased]`.
- [x] TECH_SPEC §3.5/§4.2–4.3/§5 if implementation details diverge.
- [x] ADR 0005: runner step engine, rest-timer strategy, and finish-early semantics.
- [x] README project layout if it lists apps.
