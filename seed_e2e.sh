#!/usr/bin/env bash
# Seed canonical E2E trip scenarios into noma_travels (synthetic fixtures).
#
# Usage (from system/):
#   export NOMA_E2E_SEED_ALLOWED=1
#   export AWS_PROFILE=noma
#   ./seed_e2e.sh --portfolio <id> --org <id> --owner-email you@company.com --scenarios all
#
# Cleanup:
#   ./seed_e2e.sh --portfolio <id> --org <id> --cleanup --yes

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SEED_PY="${SCRIPT_DIR}/../extensions/backend/scripts/seed_e2e_trips.py"

if [[ ! -f "${SEED_PY}" ]]; then
  echo "ERROR: seed script not found at ${SEED_PY}" >&2
  exit 1
fi

export NOMA_E2E_SEED_ALLOWED="${NOMA_E2E_SEED_ALLOWED:-1}"

exec python "${SEED_PY}" "$@"
