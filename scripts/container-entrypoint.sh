#!/usr/bin/env sh
set -eu

: "${DATABASE_URL:?DATABASE_URL must be set}"

python - <<'PY'
import os
import sys
import time

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

url = os.environ["DATABASE_URL"]
attempts = int(os.getenv("DATABASE_WAIT_ATTEMPTS", "30"))
delay = float(os.getenv("DATABASE_WAIT_SECONDS", "2"))

for attempt in range(1, attempts + 1):
    try:
        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        engine.dispose()
        print("Database connection is ready.", flush=True)
        break
    except SQLAlchemyError as exc:
        if attempt == attempts:
            print(f"Database did not become ready: {exc}", file=sys.stderr, flush=True)
            raise
        print(
            f"Waiting for database ({attempt}/{attempts})...",
            flush=True,
        )
        time.sleep(delay)
PY

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    alembic upgrade head
fi

exec uvicorn opportunityos.api.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --workers "${WEB_CONCURRENCY:-1}" \
    --proxy-headers \
    --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}"
