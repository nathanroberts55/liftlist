# M5 — Workout summary + stats

Features: **F-08** (workout summary), **F-10** (stats).

## Checklist

- [x] `workouts/services/records.py`: on-demand PR engine (`prs_for_exercise`, `prs_set_in_session`) with the PRD F-10 rules
- [x] `workouts/services/summary.py`: `build_summary` covering duration, sets, tonnage, comparison, PRs, increase flags, muscles, difficulty, and adherence
- [x] Full F-08 summary partial shared by the post-finish runner view and History session detail
- [x] Comparison uses the previous completed session with the same Plan Day (scheduled) or same title (unscheduled)
- [x] Active-plan adherence counts and streak (MISSED resets the streak)
- [x] `apps/stats` with `top_set_series`, `top_set_chart`, `weekly_volume`, `record_table`, `recent_sessions`, `weighted_exercises`, and `exercise_with_history`
- [x] `/stats/` with Progress (`?tab=progress`), PRs (`?tab=prs`), and Volume (`?tab=volume`) tabs
- [x] `/stats/api/top-set/` and `/stats/api/volume/` JSON endpoints, login required and user scoped
- [x] Exercise detail shows the last 5 sessions, current PRs, and an all-time weight chart
- [x] Chart.js 4.4.7 vendored in `static/vendor/`; data rendered with `json_script`; colors read from CSS variables
- [x] Chart palette tokens in `static/src/input.css` for both themes
- [x] Accessible empty states and no-JS table/list fallbacks for every tab
- [x] Auth, user-isolation, aggregation, record, summary, and view tests
- [x] Docs (TECH_SPEC, README, CHANGELOG) and `docs/plans/m5-summary-stats.md`
- [x] `ruff check .`, `ruff format --check .`, `pytest`, `manage.py check`, migrations check
- [x] Rebuild Tailwind and verify at 375 px / 768 px

## Notes

- Tonnage counts DONE `WEIGHT_REPS` sets only (`weight × reps`).
- PRs are computed from current data on demand, never stored, so editing a past session immediately updates the summary, PR table, and charts.
- The stats page calls `scheduling.sync_statuses` before aggregating so adherence counts are current.
- History's calendar remains in `workouts/services/history.py`; Stats links to it instead of duplicating it.
