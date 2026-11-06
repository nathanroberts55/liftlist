# 0001 — Initial architecture

- **Status:** Accepted
- **Date:** 2026-11-05

## Context
Lift List is a single-user (multi-user capable), self-hosted, phone-first web app. The owner wants a simple frontend, Django with automatic migrations, Postgres in production, and deployment matching an existing project (`friendfitter`: Django, Postgres, Tailwind, DaisyUI, Docker, Kubernetes).

## Decision
- Django 5.2 LTS with server-rendered templates, HTMX for partial updates, and Alpine.js for small client state (rest timer, steppers, sheets).
- Tailwind CSS v4 standalone CLI plus DaisyUI 5 (no Node toolchain). Vendored JS: HTMX, Alpine, SortableJS, Chart.js.
- PostgreSQL in production via `DATABASE_URL`, and SQLite in development when it is unset.
- `pip` with pinned requirements files.
- Docker image on Docker Hub, deployed to Kubernetes (1 replica) behind a Cloudflare Tunnel. Migrations and seeding run in the container entrypoint.
- Business logic lives in per-app service modules with required unit tests.
- No push notifications, offline mode, or background workers in v1. The rest timer is client-side only.

## Alternatives considered
- **React SPA + Django REST Framework:** more interactive, but doubles the codebase and needs a Node build. Rejected for v1.
- **uv / Poetry:** rejected to match the owner's preference for pip.
- **Celery + Web Push** for rest-end notifications: rejected as too much infrastructure for v1. The owner accepts the timer pausing when the app is backgrounded.

## Consequences
- Rich client-side behavior (drag-and-drop, timer) must stay small and isolated in `static/js/`.
- Migrations at startup are safe only with 1 replica. Scaling out requires moving them to a Job.
