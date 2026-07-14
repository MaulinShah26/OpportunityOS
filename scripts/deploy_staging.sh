#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-${ROOT_DIR}/.env.staging}"
COMPOSE_FILE="${ROOT_DIR}/docker-compose.staging.yml"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required." >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "The Docker Compose plugin is required." >&2
  exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  cp "${ROOT_DIR}/.env.staging.example" "${ENV_FILE}"
  chmod 600 "${ENV_FILE}"
  echo "Created ${ENV_FILE}. Replace POSTGRES_PASSWORD, then run this script again." >&2
  exit 1
fi

chmod 600 "${ENV_FILE}"

compose() {
  docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" "$@"
}

compose config >/dev/null
compose build --pull
compose up -d --remove-orphans

ENV_FILE="${ENV_FILE}" bash "${ROOT_DIR}/scripts/verify_staging.sh"
compose ps

echo
printf 'Staging is available only on the VM loopback interface.\n'
printf 'Open an SSH tunnel to port %s before browsing to /app.\n' "${STAGING_PORT:-8000}"
