#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-${ROOT_DIR}/.env.staging}"
COMPOSE_FILE="${ROOT_DIR}/docker-compose.staging.yml"
BACKUP_DIR="${BACKUP_DIR:-${ROOT_DIR}/backups/staging}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

: "${POSTGRES_DB:?POSTGRES_DB must be set}"
: "${POSTGRES_USER:?POSTGRES_USER must be set}"

mkdir -p "${BACKUP_DIR}"
chmod 700 "${BACKUP_DIR}"

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_FILE="${BACKUP_DIR}/opportunityos-${TIMESTAMP}.dump"

docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" \
  exec -T postgres pg_dump \
  --username "${POSTGRES_USER}" \
  --dbname "${POSTGRES_DB}" \
  --format custom \
  --no-owner \
  --no-privileges >"${BACKUP_FILE}"

if [[ ! -s "${BACKUP_FILE}" ]]; then
  rm -f "${BACKUP_FILE}"
  echo "Backup failed or produced an empty file." >&2
  exit 1
fi

find "${BACKUP_DIR}" -type f -name 'opportunityos-*.dump' -mtime "+${RETENTION_DAYS}" -delete
chmod 600 "${BACKUP_FILE}"
echo "Created ${BACKUP_FILE}"
