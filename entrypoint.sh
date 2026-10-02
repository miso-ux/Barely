#!/bin/sh
# Container entrypoint: apply migrations, seed demo data (idempotent), start the web server.
set -e

alembic upgrade head
python -m app.seed

# The app is expected to run behind a reverse proxy (Tailscale, nginx, Traefik...). Trusting the
# X-Forwarded-* headers makes request.url carry the public https scheme and host, which is what
# redirects and secure cookies need. Restrict FORWARDED_ALLOW_IPS to the proxy's address in
# production if the container port is reachable from elsewhere. Keep the value quoted: "*"
# would otherwise be expanded by the shell into a list of file names.
ALLOW_IPS="${FORWARDED_ALLOW_IPS:-*}"

if [ "$APP_ENV" = "development" ]; then
  exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload \
    --proxy-headers --forwarded-allow-ips "$ALLOW_IPS"
else
  exec uvicorn app.main:app --host 0.0.0.0 --port 8000 \
    --proxy-headers --forwarded-allow-ips "$ALLOW_IPS"
fi
