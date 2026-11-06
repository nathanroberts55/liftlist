# 0002 — M0 scaffold and deployment

- **Status:** Accepted
- **Date:** 2026-11-05

## Context

M0 builds the first deployable slice of Lift List: Django settings, authentication, the app shell and theme, installable PWA metadata, `/healthz/`, Docker/compose, CI, and Kubernetes manifests.

Two constraints shaped the implementation:

1. `AGENTS.md` says to mirror the owner's existing project `nathanroberts55/friendfitter` for the Dockerfile, `k8s/`, and GitHub Actions. However, `friendfitter` installs Node.js, uses `django-tailwind`, builds CSS with `runserver`, and runs `runserver` in production. That conflicts with the hard rule against Node build tooling and with TECH_SPEC §10 (multi-stage Tailwind standalone build + gunicorn).
2. `TECH_SPEC.md` §2 named the Django project package `config/`, but the repository already contained a `liftlist/` package and `manage.py` pointed at `liftlist.settings`.

The Tailwind/DaisyUI assumptions in TECH_SPEC also drifted: DaisyUI 5.7.50 no longer publishes `daisyui.mjs` or `daisyui-theme.mjs`, so the documented `@plugin "../vendor/daisyui.mjs"` paths cannot work with the pinned release.

## Decision

- **Keep the `liftlist/` project package.** TECH_SPEC §2 and the gunicorn target were updated to `liftlist.wsgi`.
- **Follow TECH_SPEC §10 for the container.** The Dockerfile is multi-stage: a `debian:bookworm-slim` stage downloads a pinned Tailwind v4.3.4 standalone binary and builds `app.css --minify`; the runtime stage is `python:3.12-slim`, installs pinned requirements, runs `collectstatic`, runs as a non-root user, and starts `entrypoint.sh` (migrate → `ensure_superuser` → gunicorn).
- **Adopt friendfitter's deployment conventions** where they do not conflict: image `docker.io/nater55/liftlist`, namespace `liftlist`, secret `app-secrets`, ClusterIP service on port 8000, and Docker Hub publishing on `main` and `v*` tags.
- **Vendor the full DaisyUI 5.7.50 package** under `static/vendor/daisyui/` and load its plugin entry points directly:
  `@plugin "../vendor/daisyui/index.js"` and `@plugin "../vendor/daisyui/theme/index.js"`.
  This was verified against the standalone binary; no CDN and no Node are involved.
- **Defer `seed_exercises` to M1.** `entrypoint.sh` runs migrations and the optional superuser only. The exercises app does not exist in M0, so calling the command now would fail.
- **Keep `UserSettings` theme-only in M0.** Default rest time, timer sound, default tags, tag management, and password change remain part of F-11 in M4.
- **Make secure cookies configurable.** `DJANGO_SECURE_COOKIES` defaults to on when `DEBUG=0`. `docker compose` serves plain HTTP on localhost, so it sets the variable to `0`; Kubernetes keeps the secure default behind the Cloudflare Tunnel.

## Alternatives considered

- **Copy friendfitter's Dockerfile (Node + `django-tailwind` + `runserver`).** Rejected: violates the no-Node hard rule and the TECH_SPEC production server choice, and adds unused dependencies.
- **Rename the project package to `config/`.** Rejected: churn for no benefit; the existing scaffold and `manage.py` already used `liftlist/`.
- **Use the prebuilt `daisyui.css` instead of the JS plugin.** Rejected: it embeds its own utility output and bypasses Tailwind's content scanning and custom theme definitions.
- **Ship a stub `seed_exercises` command.** Rejected: dead code that hides M1 work; the ADR records the gap instead.

## Consequences

- Local development and tests use SQLite. Only `docker compose` and Kubernetes supply `DATABASE_URL` for Postgres.
- The CSS build is reproducible and pinned; updating Tailwind or DaisyUI requires updating the Dockerfile `TAILWIND_VERSION` argument and the vendored package together.
- The Docker image includes `seed/` even though M0 does not use it, so M1 only needs the management command and one entrypoint line.
- The `k8s/secret.example.yaml` is a template; real values are created with `kubectl` and never committed.
- TECH_SPEC now matches the implementation for the package name, Tailwind plugin paths, and the deferred seed step.
