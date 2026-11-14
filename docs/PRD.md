# Lift List — Product Requirements Document (PRD)

| Field | Value |
|---|---|
| Product | Lift List |
| Owner | Nate Roberts |
| Status | v1 — Approved for build |
| Related docs | [`DESIGN.md`](./DESIGN.md), [`TECH_SPEC.md`](./TECH_SPEC.md), [`../AGENTS.md`](../AGENTS.md) |

---

## 1. Overview

Lift List is a self-hosted, mobile-first web app for planning weekly workout splits, running workouts set-by-set at the gym, and tracking progress over time. It replaces a workflow of writing workouts in a phone notes app.

It is a personal tool: one primary user, self-hosted on a home Linux server (Kubernetes), reached from outside the home through a Cloudflare tunnel.

## 2. Problem

Planning in a notes app works for writing a plan but fails at:

- Remembering what weight was used last time for each set.
- Knowing when an exercise is ready for a weight increase.
- Tracking missed workouts and adherence over a training block.
- Logging physical therapy (PT) and other unplanned sessions in the same place.
- Seeing progress (weights over time, PRs, volume per muscle group).

## 3. Goals

1. Build a training plan (split) in minutes, on iPad or phone.
2. At the gym, run a workout one set at a time with minimal taps and a rest timer between sets.
3. Always show what was done last time and pre-fill it.
4. Flag exercises where the top of the rep range was hit on every planned set.
5. Track scheduled, missed, made-up, and unscheduled (e.g., PT) workouts.
6. Show progress through simple charts and a history calendar.

## 4. Non-goals (v1)

- Social features, sharing, leaderboards.
- Native iOS/Android app (installable web app only).
- Offline mode / service worker sync.
- Push notifications. The rest timer runs only while the page is open.
- Estimated 1-rep max (e1RM) anywhere in the app.
- Warm-up set tracking.
- Automatic weight changes (the app flags; the user decides).
- Data import/export.
- Self-service sign-up.

## 5. User and context

- **Primary user:** One lifter (the owner). Multi-user is supported by the data model (every record is owned by a user), but there is no sign-up flow; accounts are created by an admin.
- **Devices:**
  - **iPhone at the gym** (primary). One hand, phone goes in pocket between sets, may switch apps.
  - **iPad at home** for planning.
- **Environment:** Public gyms. Equipment availability changes, so exercise order must be flexible.

## 6. Glossary

These terms are used consistently in all docs, code, and UI.

| Term | Definition |
|---|---|
| **Plan** | A named training split (e.g., "Upper/Lower Block 3"). Has an optional length in weeks. Only one plan can be **active** at a time; others are **draft** or **archived**. |
| **Plan Day** | A named day in a plan (e.g., "Day A – Lower") assigned to a weekday. |
| **Plan Item** | One exercise slot inside a Plan Day, with targets (sets, rep range, rest, etc.) and order. |
| **Superset** | Two or more Plan Items in the same day sharing a superset group. Sets rotate across all exercises in the group (A1 → B1 → C1 → A2 …). Rest happens after each full round. |
| **Scheduled Workout** | A dated occurrence of a Plan Day generated from the active plan (e.g., "Day A – Lower on Mon Nov 9"). |
| **Session** | An actual workout performed (or in progress). Either linked to a Scheduled Workout, or **unscheduled**. |
| **Unscheduled Session** | A session not generated from the plan, such as PT or an extra workout. Can be run live or logged after the fact. |
| **Session Exercise** | A snapshot of an exercise inside a Session, with its targets copied at start time so plan edits never change history. |
| **Set Log** | One recorded set: weight, reps, duration, distance, steps, difficulty (as applicable). |
| **Distance unit** | The unit a distance is shown in: miles (`MI`), yards (`YD`), or metres (`M`). Chosen per exercise and snapshotted onto Plan Items and Session Exercises. Stored canonically in metres. |
| **Working set** | Any logged set. (Warm-ups are not tracked in v1, so every logged set counts as a working set.) |
| **Missed** | A Scheduled Workout whose date passed without being completed on that date. |
| **Made up** | A Scheduled Workout completed on a later date. It still counts as **missed** for its original date. |
| **Increase flag** | A badge on an exercise meaning: last time, every planned set hit the top of the rep range. |
| **PR** | Personal record. v1 has two types: **heaviest weight** for an exercise, and **most reps at a given weight**. |
| **Volume** | Two measures: **sets** (count of completed working sets) and **tonnage** (Σ weight × reps). |
| **Difficulty** | Per-set rating from 1 (very easy) to 10 (max effort). Optional. |
| **Tag** | A user-defined label on Sessions (e.g., "PT") used for filtering. |
| **Tracking type** | How an exercise is measured. Controls which fields appear when logging a set. See §8.2. |

## 7. Feature list and IDs

Feature IDs are referenced in commits, PRs, tests, and docs (e.g., `feat(runner): F-05 superset rotation`).

| ID | Feature | v1 |
|---|---|---|
| F-01 | Authentication (username + password) | ✅ |
| F-02 | Exercise Library (muscle groups, seeded + custom exercises) | ✅ |
| F-03 | Plan Builder (plans, days, items, supersets) | ✅ |
| F-04 | Scheduling (scheduled workouts, missed, made-up) | ✅ |
| F-05 | Workout Runner (set-by-set flow, rest timer, reorder, add/skip) | ✅ |
| F-06 | Unscheduled Sessions + Tags (live or retroactive) | ✅ |
| F-07 | Progression (pre-fill, last-time display, increase flag) | ✅ |
| F-08 | Workout Summary | ✅ |
| F-09 | History (calendar, list, tag filter, edit past sessions) | ✅ |
| F-10 | Stats (weight over time, PRs, weekly volume by muscle group) | ✅ |
| F-11 | Settings (theme, default rest, timer sound, default tags, tag management) | ✅ |
| F-12 | Installable web app (home-screen icon, standalone display) | ✅ |
| F-13 | Distance entry and units (any decimal, mi/yd/m per exercise) | 🚧 |

## 8. Functional requirements

Each requirement has acceptance criteria (AC). "User" means the logged-in user. All data is scoped to that user.

### F-01 Authentication

- Use Django's built-in auth: username + password login page, logout.
- Every page except login and `/healthz/` requires login.
- Sessions persist (stay logged in on the phone for at least 30 days).
- No sign-up page. Users are created through `createsuperuser` or Django admin.

**AC**
- Visiting any page while logged out redirects to `/login/?next=…`.
- After login, the user lands on the requested page or Today.

### F-02 Exercise Library

#### 8.1 Muscle groups (fixed, seeded)

Chest, Back, Shoulders, Biceps, Triceps, Forearms, Quads, Hamstrings, Glutes, Calves, Core, Cardio.

#### 8.2 Tracking types

| Type | Set fields | Required | Example |
|---|---|---|---|
| `WEIGHT_REPS` | weight (lb), reps | both | Squat |
| `BODYWEIGHT` | reps, added weight (lb) | reps | Pull-up |
| `TIMED` | duration (sec), added weight (lb) | duration | Plank |
| `CARDIO` | duration (min:sec), distance (exercise unit) | duration or distance | Walk, Run |
| `DISTANCE` | distance (exercise unit), steps, weight (lb) | distance or steps | Sled push, Farmer's carry |

Every set may also have a difficulty rating (1–10, optional). Each exercise has a
default distance unit (miles, yards, or metres); `CARDIO` defaults to miles and
carries to their own unit by default.

#### Requirements

- The library ships with ~90 seeded common exercises (`seed/exercises.json`), each with a primary muscle group, optional secondary groups, and a tracking type.
- The user can add custom exercises: name, primary muscle group, optional secondary groups, tracking type, optional notes.
- The user can edit or archive custom exercises. Seeded exercises can be archived (hidden) but not deleted. Archived exercises stay in history.
- The library screen groups exercises by primary muscle group, with search.
- The exercise detail page shows the last 5 sessions, PRs, and a weight-over-time chart (reuses F-10).

**AC**
- Adding an exercise with a duplicate name (case-insensitive, per user, including seeded names) is rejected with a clear message.
- Seeding is idempotent: running it twice creates no duplicates.

### F-03 Plan Builder

- Create a plan with:
  - **name** (required)
  - **split type** (Full Body, Upper/Lower, Push/Pull/Legs, Body-Part Split, Custom)
  - **start date**
  - **length in weeks** (optional; blank means it repeats until changed or archived)
- Add Plan Days. Each has a name and a weekday. A weekday can have only one Plan Day per plan.
- For each Plan Day, the user may select **focus muscle groups** (e.g., Chest, Biceps, Calves). The exercise picker then shows exercises from those groups first, sorted by how often the user has done them, then alphabetically. Picking from any group, or creating a new exercise inline, is always possible.
- Plan Items have:
  - exercise and order
  - targets by tracking type:
    - `WEIGHT_REPS` / `BODYWEIGHT`: sets, rep min, rep max
    - `TIMED`: sets, target seconds
    - `CARDIO`: target duration and/or distance (1 set)
    - `DISTANCE`: sets, optional target distance
  - rest seconds (defaults to the user's default rest setting)
  - optional superset group
  - optional notes (cues)
- Supersets: the user selects 2+ consecutive items and taps **Superset**. Items share a group label (A, B, C…) and display grouped.
- Reorder items with drag-and-drop on iPad and desktop. A list form with up/down controls is always available as the fallback (required on phone).
- **Duplicate plan** copies days and items into a new draft (for starting the next block with changes).
- **Activate plan** makes it the single active plan (any currently active plan is archived after confirmation) and generates Scheduled Workouts (F-04).
- **Archive plan** ends it. Future pending Scheduled Workouts are deleted. History is kept.
- Editing an active plan updates future pending Scheduled Workouts (dated today or later with no session). Past and started workouts are untouched.

**AC**
- A user cannot have two active plans (enforced in the database).
- Editing an active plan never changes data in completed Sessions.

### F-04 Scheduling

- When a plan is activated, generate Scheduled Workouts for each Plan Day's weekday, starting from the plan start date:
  - **Fixed length:** generate for all weeks up front.
  - **Open-ended:** keep 14 days generated ahead of today (extend lazily when Today or History loads).
- Statuses:

| Status | Meaning |
|---|---|
| `PENDING` | Date is today or later and not completed. |
| `COMPLETED` | Completed on its scheduled date. |
| `MISSED` | Date has passed and it was not completed on that date. |
| `MADE_UP` | Completed on a later date. Counts as missed for adherence. |

- Past `PENDING` items become `MISSED` automatically (evaluated on page load; no background job required).
- The user can manually mark today's workout as missed (e.g., rest day due to injury).
- **Any** pending or missed (not made up) Scheduled Workout from the active plan can be started on any day. Doing Monday's workout on Wednesday:
  - Monday's workout becomes `MADE_UP`.
  - Wednesday's own workout stays `PENDING`; the user chooses what to do next.
- **Week number** shown on Today = weeks since plan start + 1 (e.g., "Week 2 of 5", or "Week 7" if open-ended).

**AC**
- If Mon is missed and Mon's workout is done on Wed: Mon shows "Missed · made up Wed"; Wed's workout is still pending; adherence counts Mon as missed.
- Completing a workout on its date sets `COMPLETED`.

### F-05 Workout Runner

The core gym flow. Phone-first and fast.

**Starting**
- From Today, tap **Start Workout** on a Scheduled Workout. This creates a Session (`IN_PROGRESS`) and copies all Plan Items into Session Exercises with their targets.
- Only one Session can be `IN_PROGRESS` at a time. If one exists, Today shows a **Resume** banner (with **Finish** and **Discard** options) instead of letting a second one start.
- There is no automatic resume. Reopening the app goes to Today, which shows the Resume banner.

**Set entry screen**
- Shows: exercise name, "Exercise X of Y", "Set N of M", target (e.g., "Goal 8–12 reps"), superset label if any, increase flag if any, and a **Last time** line (e.g., `Last: 185×12, 185×12, 185×11`).
- Input fields depend on tracking type (§8.2), pre-filled per F-07.
- Steppers (−/+) beside weight (5 lb step) and reps (1 step). Fields are also directly typeable.
- Difficulty selector 1–10 (optional; tap to select, tap again to clear).
- Buttons: **Submit** (primary), **+ Add set**, **Skip set**.
- Completed sets for the current exercise are listed below, each with an edit (✎) action.

**After Submit**
- The set saves to the server immediately.
- If the next step has a rest period (> 0 sec), the **rest timer** screen shows. It has −15s, +15s, and **Skip**, plus a preview of the next set. When it reaches 0, a short sound plays (if enabled) and the next set entry screen appears automatically.
- If rest is 0 or skipped, the next set entry screen appears immediately.
- The timer only needs to work while the page is open. Pausing when backgrounded is acceptable. It counts toward a fixed end time, so it is correct when the user returns.

**Order of steps**
- Normal exercises: all sets of exercise 1, then exercise 2, etc.
- Superset group: rotate one set per exercise in group order. Rest is applied after each full round, using the rest value of the last exercise in the group. If one exercise in the group has fewer sets, it drops out of the rotation once complete.

**Adjusting during a workout** (via the ⋮ menu on the set screen)
- **Reorder exercises:** opens a sheet listing remaining exercises. Drag to reorder (up/down buttons as fallback). Completed exercises are locked at the top.
- **Jump to exercise:** start any remaining exercise now.
- **Skip exercise:** marks it skipped; remaining planned sets are recorded as skipped.
- **Add exercise:** pick from the library (needed for unscheduled sessions and spur-of-the-moment changes).
- **Add set:** increases the session's set count for this exercise by one (not the plan).
- **Skip set:** records the set as skipped and moves on.

**Finishing**
- After the last set of the last exercise, show **Finish Workout** (also available any time from the ⋮ menu).
- Finishing sets the Session to `COMPLETED`, sets `completed_at`, updates the linked Scheduled Workout status (F-04), and opens the Summary (F-08).

**Errors**
- If saving a set fails (network or server), stay on the set entry screen, keep the typed values, show "Couldn't save — Retry". Retrying must not create duplicate sets (idempotency key per set).

**AC**
- Example: plan has Squat 3×8–12, Bench 3×8–12, Curl 3×10–12 with 90 s rest. Start → Squat set 1 → Submit → 90 s timer → Squat set 2 … → after Squat set 3, the next screen is Bench set 1.
- Superset A (Curl 3 sets, Pushdown 3 sets): order is Curl 1, Pushdown 1, rest, Curl 2, Pushdown 2, rest, Curl 3, Pushdown 3.
- Reordering puts the moved exercise next in line without changing the plan.

### F-06 Unscheduled Sessions and Tags

- From Today, **+ Unscheduled session** offers two options:
  1. **Plan & start now:** enter a title, pick tags, add exercises with targets → start the Runner (F-05).
  2. **Log past workout:** pick a date (and optional start time and duration), title, tags, then add exercises and enter sets in a simple form (no runner, no timer).
- Both builders start with **one exercise row**. A session may contain exactly one exercise; **Add another exercise** appends a blank row.
- Unscheduled sessions do not affect plan adherence.
- Tags:
  - User-defined (name, color).
  - Many-to-many with Sessions.
  - Can be added to any Session, scheduled or not.
  - Default tags from Settings are pre-selected for new unscheduled sessions.
- History and Stats can filter by tag (include or exclude), e.g., show only "PT", or hide "PT".

**AC**
- A retroactively logged PT session appears on the History calendar on its date with the PT tag, and is excluded from adherence.

### F-07 Progression

**Last time**
- "Last time" for an exercise = the most recent completed Session Exercise for the same exercise, preferring one from the same Plan Day and falling back to any session.

**Pre-fill**
- Weight: last time's weight for the same set number; if missing, last time's final set weight; if none, blank.
- Reps (or duration/distance): last time's value for the same set number; if none, the target rep max (or target duration/distance).

**Increase flag**
- Applies to `WEIGHT_REPS` and `BODYWEIGHT` exercises with a rep max.
- Set when, in the "last time" Session Exercise:
  - the number of completed (non-skipped) sets ≥ the planned set count, **and**
  - every planned set had reps ≥ rep max.
- Extra (added) sets are ignored for the flag.
- The flag shows on:
  - Today's exercise list
  - the set entry screen
  - the Summary of the session that earned it ("Ready to increase next time")
- The app never changes weights automatically.

**AC**
- Plan 3×8–12. Last time: 135×12, 135×12, 135×12 → flagged. Last time: 135×12, 135×12, 135×11 → not flagged.

### F-08 Workout Summary

Shown after finishing; also reachable from History.

| Item | Definition |
|---|---|
| Duration | `completed_at − started_at` (for retro logs: the entered duration, if any). |
| Sets | Completed sets vs planned (e.g., "14 of 16 · +1 extra · 2 skipped"). |
| Total volume | Tonnage for this session, with % change vs the last completed session of the same Plan Day (scheduled) or same title (unscheduled). |
| PRs hit | List of new PRs set this session (heaviest weight, most reps at a weight). |
| Ready to increase | Exercises that earned an increase flag this session. |
| Muscle groups worked | Sets per primary muscle group (chips or small horizontal bar chart). |
| Average difficulty | Mean of rated sets (hidden if none rated). |
| Adherence | For the active plan: completed on time / made up / missed, and current streak. |

**Streak** = consecutive Scheduled Workouts (in date order, up to today) that are `COMPLETED` or `MADE_UP`. A `MISSED` workout that was never made up resets it to 0.

### F-09 History

- **Calendar view (month):** each day shows dots:
  - 🟢 completed
  - 🔴 missed
  - 🟠 made up (on the original date; the make-up session shows on the day it was done)
  - 🔵 unscheduled session
  - ⚪ pending
- Tapping a day lists that day's Sessions and Scheduled Workouts.
- **List view:** reverse chronological Sessions, filterable by tag and by plan.
- **Session detail / edit:**
  - Edit any set (weight, reps, duration, distance, difficulty).
  - Add or delete sets.
  - Change performed date, title, and tags.
  - Delete the session (with confirmation).
  - Changing a scheduled session's date recalculates its Scheduled Workout status.
- PRs and stats are computed from current data, so edits are reflected automatically.

### F-10 Stats

1. **Weight over time (per exercise):**
   - Pick an exercise; line chart of top-set weight per session date.
   - Tooltip shows the full set list.
   - Ranges: 3 months, 6 months, 1 year, all.
2. **Personal records:**
   - Table per exercise: heaviest weight (with reps and date).
   - Expandable "most reps at weight" list.
   - Searchable, filterable by muscle group.
3. **Weekly volume by muscle group:**
   - Bar chart, last 8 ISO weeks (Mon–Sun).
   - Toggle **Sets** or **Tonnage**.
   - Counts the primary muscle group only.
   - Tag filter (e.g., exclude PT).
4. **Workout history calendar:** see F-09 (linked from Stats).

**PR rules**
- **Heaviest weight:** max weight across completed `WEIGHT_REPS` / `DISTANCE` sets (reps ≥ 1 where applicable). Distance PRs are deferred.
- **Most reps at weight:** for a given exact weight, the max reps. A new PR is set when reps exceed all previous sets at that exact weight. The first time a weight is used does **not** count as a rep PR. It counts as a heaviest-weight PR only if it is the heaviest ever.

### F-11 Settings

- Theme: Dark (default), Light, Match device.
- Default rest time (seconds; default 90).
- Timer sound on/off (default on).
- Default tags for new unscheduled sessions.
- Manage tags: create, rename, recolor, delete. Deleting a tag removes it from sessions; sessions are kept.
- Change password (Django built-in view).

### F-12 Installable web app

- Web app manifest, app icons, `apple-touch-icon`, `display: standalone`, theme color.
- "Add to Home Screen" on iOS/iPadOS opens full-screen with no browser bar.
- No service worker / offline caching in v1.

### F-13 Distance entry and units

- Distance targets and logged sets accept any decimal value (for example `2.48`); there is no fixed 0.1 increment.
- Each exercise has a default distance unit: miles (`MI`), yards (`YD`), or metres (`M`). Feet are not supported.
- The unit is chosen per exercise and can be overridden per Plan Item / Session Exercise. The chosen unit is snapshotted, so changing an exercise's default later never rewrites history.
- Distances are stored canonically in metres to four decimal places. `1 mi = 1609.344 m`, `1 yd = 0.9144 m`.
- `CARDIO` sets accept a duration, a distance, or both. At least one is required.
- `DISTANCE` sets accept a distance, steps, or both. Weight is optional. There is no duration field. Steps reuse the reps field and are labelled "Steps (each way)".
- Distance PRs and distance-over-time charts are out of scope for now.

**AC**
- A walk logged as `2.48 mi` saves and redisplays as `2.48 mi`.
- `15 yd` and `400 m` round-trip in their own units.
- A sled set entered as `15 yd` shows as `15 yd` in history, even after the exercise default changes.
- A `CARDIO` set with a distance and no duration saves.
- A `CARDIO` set with neither duration nor distance is rejected with a clear message.
- A `DISTANCE` set with steps and no distance saves; one with neither distance nor steps is rejected.

## 9. Non-functional requirements

| Area | Requirement |
|---|---|
| Performance | Set submit → next screen < 300 ms on the home network/tunnel under normal conditions. Pages < 1 s. |
| Mobile | Usable one-handed on a 375 px-wide screen. Tap targets ≥ 44 px. Inputs ≥ 16 px font (prevents iOS zoom). |
| Reliability | Each set persists on Submit. No data is held only in the browser. |
| Security | Login required. CSRF on all POSTs. Secrets via environment variables. HTTPS terminated by Cloudflare. |
| Data integrity | Completed history is immutable to plan edits (snapshot targets). DB constraints for single active plan and idempotent set submits. |
| Units | Pounds; distance in miles, yards, or metres (no feet). Canonical storage in metres. |
| Timezone | `America/New_York`. "Today" uses local date. |
| Accessibility | WCAG AA contrast in both themes. Labels on all inputs. Timer uses `aria-live`. |

## 10. v1 scope (definition of "usable at the gym")

Planning (F-02, F-03), Scheduling (F-04), Runner + rest timer (F-05), Editing (F-09), Data displays (F-08, F-10), plus F-01, F-06, F-07, F-11, F-12, and F-13.

## 11. Future (not v1)

- Push notification when rest ends (requires a background worker and Web Push).
- Offline mode (service worker with queued set sync).
- Warm-up sets.
- CSV export (e.g., share PT history with a therapist).
- Equipment tags on exercises.
- Plan templates library.
- Bodyweight tracking.
- Automated database backups as part of deployment (see TECH_SPEC §11).

## 12. Build milestones

Build in this order. Each milestone ends deployable and tested.

| # | Milestone | Features |
|---|---|---|
| M0 | Scaffold: Django project, settings, Docker, compose, CI, auth, base layout + theme, `/healthz/` | F-01, F-11 (theme only), F-12 |
| M1 | Exercise library + seed | F-02 |
| M2 | Plan builder (list form first, then drag-and-drop) + scheduling | F-03, F-04 |
| M3 | Workout runner + rest timer + progression | F-05, F-07 |
| M4 | Unscheduled sessions, tags, history + editing | F-06, F-09, F-11 |
| M5 | Summary + stats | F-08, F-10 |
| M6 | Polish: empty states, iPad layouts, accessibility pass | — |
