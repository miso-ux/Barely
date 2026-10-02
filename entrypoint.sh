#!/bin/sh
# Container entrypoint: apply migrations, seed demo data (idempotent), start the web server.
set -e

alembic upgrade head
python -m app.seed

if [ "$APP_ENV" = "development" ]; then
  exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
else
  exec uvicorn app.main:app --host 0.0.0.0 --port 8000
fi
