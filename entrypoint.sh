#!/bin/sh
set -e

python manage.py migrate --noinput
python manage.py seed_exercises
python manage.py ensure_superuser

exec gunicorn liftlist.wsgi:application \
  --bind "0.0.0.0:8000" \
  --workers "${GUNICORN_WORKERS:-2}" \
  --access-logfile -
