# syntax=docker/dockerfile:1

# --- CSS build stage ---------------------------------------------------------
# Builds static/css/app.css with the Tailwind standalone binary (no Node).
FROM debian:bookworm-slim AS css

ARG TAILWIND_VERSION=4.3.4
ARG TARGETARCH

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

RUN case "${TARGETARCH:-amd64}" in \
        amd64) tw_arch=x64 ;; \
        arm64) tw_arch=arm64 ;; \
        *) echo "Unsupported architecture: ${TARGETARCH}" >&2; exit 1 ;; \
    esac \
    && curl -fsSL -o /usr/local/bin/tailwindcss \
        "https://github.com/tailwindlabs/tailwindcss/releases/download/v${TAILWIND_VERSION}/tailwindcss-linux-${tw_arch}" \
    && chmod +x /usr/local/bin/tailwindcss

WORKDIR /app
COPY static ./static
COPY templates ./templates
COPY apps ./apps
RUN tailwindcss -i static/src/input.css -o static/css/app.css --minify

# --- Runtime stage -----------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_DEBUG=0

WORKDIR /app

RUN groupadd --system liftlist \
    && useradd --system --gid liftlist --home-dir /app liftlist

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY manage.py entrypoint.sh ./
COPY liftlist ./liftlist
COPY apps ./apps
COPY templates ./templates
COPY static ./static
COPY seed ./seed
COPY --from=css /app/static/css/app.css ./static/css/app.css

# `static/src` holds the Tailwind entry source; it is not a served asset and
# must not be post-processed by the manifest storage.
RUN chmod +x entrypoint.sh \
    && python manage.py collectstatic --noinput \
        --ignore "src/*" \
        --ignore "vendor/daisyui/*" \
    && chown -R liftlist:liftlist /app

USER liftlist

EXPOSE 8000
ENTRYPOINT ["./entrypoint.sh"]
