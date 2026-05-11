#!/bin/sh
set -e

# Auto-detect Django WSGI module from /app/<project>/wsgi.py
if [ -z "$WSGI_MODULE" ]; then
    WSGI_PATH=$(find /app -maxdepth 2 -name wsgi.py -not -path "*/.venv/*" 2>/dev/null | head -n1)
    if [ -z "$WSGI_PATH" ]; then
        echo "ERROR: no wsgi.py found. Set WSGI_MODULE env var (e.g. 'myproject.wsgi')." >&2
        exit 1
    fi
    WSGI_MODULE=$(echo "$WSGI_PATH" | sed 's|^/app/||;s|\.py$||;s|/|.|g')
fi
echo "Using WSGI module: $WSGI_MODULE"

# Migrations on boot (set RUN_MIGRATIONS=0 to disable)
if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
    echo "Running migrations..."
    python manage.py migrate --noinput
fi

# Collectstatic on boot (off by default — usually better to do this at build time)
if [ "${RUN_COLLECTSTATIC:-0}" = "1" ]; then
    echo "Collecting static files..."
    python manage.py collectstatic --noinput
fi

exec gunicorn \
    --bind "0.0.0.0:${PORT:-8080}" \
    --workers "${GUNICORN_WORKERS:-2}" \
    --threads "${GUNICORN_THREADS:-2}" \
    --access-logfile - \
    --error-logfile - \
    --log-level "${LOG_LEVEL:-info}" \
    "$WSGI_MODULE"
