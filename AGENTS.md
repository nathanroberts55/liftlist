# AGENTS.md — Instructions for AI coding agents (OpenCode)

Lift List is a self-hosted, mobile-first Django web app for planning workout splits, running workouts set by set with a rest timer, and tracking progress.

## Read before every task

1. `docs/PRD.md`: what to build. Feature IDs are F-01 to F-12, and the glossary is in §6.
2. `docs/DESIGN.md`: how it looks. Tokens, components, and screen sketches.
3. `docs/TECH_SPEC.md`: how it's built. Stack, data model, services, URLs, and deployment.
4. `docs/decisions/`: past architecture decisions (ADRs).

These docs are the source of truth. If a request conflicts with them, stop and ask, or update the docs in the same change with the user's approval.

## Hard rules

- **Stack is fixed:**
  - Django 5.2 with server-rendered templates
  - HTMX and Alpine.js
  - Tailwind v4 (standalone CLI) with DaisyUI 5
  - SortableJS and Chart.js
  - PostgreSQL in production, SQLite in development

  Do not add React, Node build tooling, DRF, Celery, Redis, or any new dependency without first writing an ADR in `docs/decisions/` and getting approval.
- **Dependencies:** use `pip` with pinned `requirements.txt` and `requirements-dev.txt`. Do not use Poetry, uv, or Pipenv.
- **Use the glossary terms** in code and UI: Plan, PlanDay, PlanItem, ScheduledWorkout, Session, SessionExercise, SetLog, Tag. Don't invent synonyms.
- **Business logic goes in services** (`apps/<app>/services/`). Views only parse input, call a service, and render. Do not put logic in templates or models' `save()`.
- **Scope every query to the user:** `filter(user=request.user)` or `get_object_or_404(..., user=request.user)`.
- **History is immutable to plan edits.** SessionExercise snapshots its targets. Never read PlanItem targets when displaying past sessions.
- **Don't add features from PRD §4 (Non-goals):**
  - push notifications
  - offline mode / service worker
  - e1RM
  - warm-up sets
  - automatic weight changes
  - import/export
  - sign-up
- **Styling:**
  - Use DESIGN.md tokens through the DaisyUI theme or CSS variables. No raw hex values in templates.
  - Inputs must be ≥ 16 px and tap targets ≥ 44 px.
  - Dark theme is the default.
- **Drag-and-drop must have a non-drag fallback** (▲▼ buttons).
- **Migrations:** always commit generated migrations. Never edit an applied migration; add a new one.
- **Dates:** use `timezone.localdate()` for "today". Tests use `freezegun`.

## Workflow

- **Branches:** `feat/<short-name>`, `fix/<short-name>`, `docs/<short-name>`, `chore/<short-name>`.
- **Commits:** Conventional Commits with a scope and feature ID when relevant.
  - `feat(runner): F-05 superset rotation in next_step`
  - `fix(scheduling): F-04 made-up status when date edited`
  - `docs(prd): clarify rep PR rule`
  - Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `ci`, `build`.
- **Build order:** follow the milestones in PRD §12 (M0 → M6). Don't start a milestone before the previous one passes CI.
- **When behavior changes:**
  - update the relevant doc in the same PR
  - add a line under `## [Unreleased]` in `CHANGELOG.md`
  - for architectural choices, add an ADR (`docs/decisions/NNNN-kebab-title.md`, using the template in `0000-template.md`)

## Definition of done

- [ ] Meets the PRD acceptance criteria for the feature ID(s).
- [ ] Matches the DESIGN.md sketch and components on a 375 px-wide phone and on an iPad (≥ 768 px).
- [ ] Service functions have unit tests. Auth and user-isolation view tests are added for new routes.
- [ ] `ruff check .`, `ruff format --check .`, and `pytest` pass.
- [ ] Docs and CHANGELOG are updated if behavior changed.
- [ ] Works with both SQLite (dev) and Postgres (`docker compose up --build`).

## Commands

```powershell
# Windows dev (SQLite)
python -m venv .venv; .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python manage.py migrate
python manage.py seed_exercises
python manage.py createsuperuser
python manage.py runserver

# Tailwind (second terminal)
.\bin\tailwindcss-windows-x64.exe -i static/src/input.css -o static/css/app.css --watch

# Quality
ruff check . ; ruff format . ; pytest

# Prod-like local (Postgres)
docker compose up --build
```

## Deployment reference

Production runs as a Docker image on Docker Hub, deployed to Kubernetes on a home Linux server, with Postgres on the host and ingress through a Cloudflare Tunnel.

Mirror the owner's existing repo **`nathanroberts55/friendfitter`** (Django + Postgres + Tailwind + DaisyUI) for:
- the Dockerfile structure
- `k8s/` manifests
- GitHub Actions workflows

If friendfitter's approach differs from TECH_SPEC §10, follow friendfitter and record it in an ADR.
