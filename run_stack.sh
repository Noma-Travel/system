#!/bin/bash
# Noma dev launcher (Linux/Mac) — mirrors run.ps1 for Windows
# Usage: ./run_stack.sh noma console backend env:staging handler:local
set -e
SYSTEM_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$SYSTEM_ROOT/venv/bin/python"
if [ ! -f "$PYTHON" ]; then
    PYTHON="python3"
fi
exec "$PYTHON" "$SYSTEM_ROOT/scripts/run.py" "$@"
