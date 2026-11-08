# Lift List

Self-hosted, mobile-first web app for planning workout splits, running workouts set by set, and tracking progress.

Built with Django 5.2, server-rendered templates, HTMX, Alpine.js, Tailwind CSS v4 (standalone CLI), and DaisyUI 5. No Node toolchain is required.

**Status:** M5 summary and stats — authentication, theme, installable PWA, `/healthz/`, the app shell, a seeded exercise library, the plan builder with scheduling and the Today screen, the workout runner, unscheduled and retroactive sessions, tags, Settings additions, a calendar/list history with session and set editing, the full workout summary, and Progress/PRs/Volume stats. M6 polish remains (see `docs/PRD.md` §12).

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
- Kubernetes manifests live in `k8s/` (namespace `liftlist`, Service `liftlist`, Secret `app-secrets`).
- `k8s/ingress.yaml` routes `liftlist.naterobertstech.com` to the Service. The Cloudflare Tunnel points at Traefik on `http://localhost:80`; Cloudflare terminates TLS.
- Postgres runs on the host. `DATABASE_URL` is a standard libpq connection string, for example `postgres://ll_user:password@100.86.17.28:5432/liftlist`. Allow the pod CIDR in `pg_hba.conf`.
- Copy `k8s/secret.example.yaml` to `k8s/secrets.yaml`, rename the Secret to `app-secrets`, fill in the values, and apply it explicitly. `k8s/secrets.yaml` is gitignored.
- The probes send `Host: liftlist.naterobertstech.com` so Django's `ALLOWED_HOSTS` accepts the kubelet request; without it `/healthz/` returns 400.
- The single replica uses `strategy: Recreate` so a rollout never runs two `migrate` calls at once.

```bash
kubectl create namespace liftlist
cp k8s/secret.example.yaml k8s/secrets.yaml   # edit, rename to app-secrets, fill values
kubectl apply -f k8s/secrets.yaml
kubectl apply -f k8s/configmap.yaml -f k8s/service.yaml -f k8s/deployment.yaml -f k8s/ingress.yaml
```

See `k8s/README.md` and `docs/TECH_SPEC.md` §10 for details.

## Project layout

```
liftlist/          Django project (settings, URLs, WSGI)
apps/core/         Today, health check, PWA manifest, nav
apps/accounts/     UserSettings, login/settings routes, ensure_superuser
apps/exercises/    MuscleGroup, Exercise, ExerciseArchive, library services/views
apps/plans/        Plan, PlanDay, PlanItem, ScheduledWorkout, builder/scheduling/Today services
apps/stats/        Stats tabs, Chart.js JSON endpoints, and progress/volume aggregations
apps/workouts/     Tag, Session, SessionExercise, SetLog, runner/history/tag/summary/record services
templates/         base.html, components, page templates
static/src/        Tailwind entry (input.css)
static/vendor/     HTMX, Alpine, SortableJS, Chart.js, DaisyUI (pinned, vendored)
static/img/icons/  PWA icons
tests/             pytest suite
k8s/               Deployment, Service, ConfigMap, Ingress, Secret example (real secrets.yaml is gitignored)
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
