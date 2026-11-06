# Lift List

Self-hosted, mobile-first web app for planning workout splits, running workouts set by set, and tracking progress.

Built with Django 5.2, server-rendered templates, HTMX, Alpine.js, Tailwind CSS v4 (standalone CLI), and DaisyUI 5. No Node toolchain is required.

**Status:** M3 workout runner and progression — authentication, theme, installable PWA, `/healthz/`, the app shell, a seeded exercise library, the plan builder with scheduling and the Today screen, and the workout runner (set logging, supersets, rest timer, skip/add/reorder/jump, finish/discard, pre-fill from history, and the increase flag). History, summary, stats, and tags arrive in later milestones (see `docs/PRD.md` §12).

## Local development (SQLite)

Local development and tests use SQLite automatically. `DATABASE_URL` is only needed for Postgres (compose/Kubernetes).

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python manage.py migrate
python manage.py seed_exercises
python manage.py createsuperuser
python manage.py runserver
```

Open <http://127.0.0.1:8000>. There is no sign-up: log in with the superuser you just created.

Run the Tailwind watcher in a second terminal (the built CSS is not committed):

```powershell
.\bin\tailwindcss-windows-x64.exe -i static/src/input.css -o static/css/app.css --watch
```

The binary is not in version control. Download it from the
[Tailwind v4.3.4 release](https://github.com/tailwindlabs/tailwindcss/releases/tag/v4.3.4):

```powershell
New-Item -ItemType Directory -Force bin | Out-Null
Invoke-WebRequest `
  -Uri https://github.com/tailwindlabs/tailwindcss/releases/download/v4.3.4/tailwindcss-windows-x64.exe `
  -OutFile bin\tailwindcss-windows-x64.exe
```

On macOS or Linux, download `tailwindcss-macos-arm64` or `tailwindcss-linux-x64` instead.

## Tests and lint

```powershell
ruff check .
ruff format --check .
pytest
```

Tests and CI use SQLite. No database service is required.

## Prod-like local stack (Postgres)

```powershell
Copy-Item .env.example .env   # optional; compose has working defaults
docker compose up --build
```

Open <http://localhost:8000>. The stack runs the app image and `postgres:16` with a named volume. Migrations run on container start; set `DJANGO_SUPERUSER_USERNAME` and `DJANGO_SUPERUSER_PASSWORD` to have the entrypoint create a superuser.

## Deployment

- The image is built by `.github/workflows/docker-publish.yml` and pushed to `docker.io/nater55/liftlist`.
- Kubernetes manifests live in `k8s/` (namespace `liftlist`, secret `app-secrets`).
- Postgres runs on the host; set `DATABASE_URL` in the Secret.
- Ingress is provided by the existing Cloudflare Tunnel setup.

See `docs/TECH_SPEC.md` §10 for details.

## Project layout

```
liftlist/          Django project (settings, URLs, WSGI)
apps/core/         Today, health check, PWA manifest, nav
apps/accounts/     UserSettings, login/settings routes, ensure_superuser
apps/exercises/    MuscleGroup, Exercise, ExerciseArchive, library services/views
apps/plans/        Plan, PlanDay, PlanItem, ScheduledWorkout, builder/scheduling/Today services
apps/workouts/     Tag, Session, SessionExercise, SetLog, runner/progression services, runner views
templates/         base.html, components, page templates
static/src/        Tailwind entry (input.css)
static/vendor/     HTMX, Alpine, DaisyUI (pinned, vendored)
static/img/icons/  PWA icons
tests/             pytest suite
k8s/               Deployment, Service, ConfigMap, Secret example
seed/              Exercise seed data
docs/              PRD, design guide, technical spec, ADRs, implementation plans
```

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `DJANGO_SECRET_KEY` | insecure dev key | Set in production. |
| `DJANGO_DEBUG` | `1` | `0` in production. |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | empty | Required behind Cloudflare. |
| `DJANGO_SECURE_COOKIES` | on when `DEBUG=0` | Set `0` for plain-HTTP local stacks (compose does). |
| `DATABASE_URL` | unset → SQLite | Postgres in compose/Kubernetes. |
| `DJANGO_SUPERUSER_*` | empty | Optional first-run superuser. |
| `GUNICORN_WORKERS` | `2` | Container workers. |

Architecture decisions are recorded in `docs/decisions/`, starting with ADR 0002 for the M0 scaffold. Implementation plans live in `docs/plans/`.
