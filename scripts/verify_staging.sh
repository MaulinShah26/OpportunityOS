#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-${ROOT_DIR}/.env.staging}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

PORT="${STAGING_PORT:-8000}"
BASE_URL="http://127.0.0.1:${PORT}"
ATTEMPTS="${VERIFY_ATTEMPTS:-30}"
DELAY="${VERIFY_DELAY_SECONDS:-2}"

for ((attempt = 1; attempt <= ATTEMPTS; attempt++)); do
  if curl --fail --silent --show-error "${BASE_URL}/health" >/tmp/opportunityos-health.json 2>/dev/null; then
    break
  fi

  if ((attempt == ATTEMPTS)); then
    echo "Staging health check failed after ${ATTEMPTS} attempts." >&2
    docker compose --env-file "${ENV_FILE}" -f "${ROOT_DIR}/docker-compose.staging.yml" logs --tail=200 >&2
    exit 1
  fi

  sleep "${DELAY}"
done

curl --fail --silent --show-error "${BASE_URL}/app/" | grep -q "OpportunityOS"

echo "Health endpoint: $(cat /tmp/opportunityos-health.json)"
echo "Web workspace: ${BASE_URL}/app/"
