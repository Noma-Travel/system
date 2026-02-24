#!/usr/bin/env bash
set -euo pipefail

# Zappa Deployment Script (Simplified)
# 
# Usage:
#   ./zappa_update.sh <stage> [update|deploy] [--clean]
#   ./zappa_update.sh renglo_0206 update
#   ./zappa_update.sh renglo_0206 update --clean  # Force clean wheelhouse
#
# What it does:
# 1. Captures your EXACT current environment (pip freeze)
# 2. Downloads wheels for all packages at exact versions
# 3. Creates clean deployment venv with those exact packages
# 4. Installs local packages from source
# 5. Deploys with Zappa
# 6. Restores your original environment
#
# Speed optimization:
# - Wheelhouse is kept between deploys (faster subsequent deploys)
# - Use --clean flag to force fresh download

# Validate required arguments
if [[ -z "${1:-}" ]]; then
  echo "ERROR: Stage name is required" >&2
  echo "" >&2
  echo "Usage: $0 <stage> [update|deploy] [--clean]" >&2
  echo "  <stage> - REQUIRED: Zappa stage name (must match a key in zappa_settings.json)" >&2
  exit 1
fi

STAGE="$1"
ACTION="${2:-update}"  # "deploy" for first-time; "update" otherwise
CLEAN_BUILD=false

# Check for --clean flag
for arg in "$@"; do
  if [[ "$arg" == "--clean" ]]; then
    CLEAN_BUILD=true
  fi
done

PYTHON_BIN="${PYTHON_BIN:-python3}"
WHEELHOUSE=".wheelhouse"
DEPLOY_VENV=".venv_deploy"
FREEZE_FILE=".freeze.txt"

# Track original environment
ORIG_VENV="${VIRTUAL_ENV:-}"
ORIG_PATH="$PATH"

# Cleanup function
cleanup() {
  echo ""
  echo "==> Cleaning up..."
  
  # Deactivate deploy venv if active
  if [[ -n "${VIRTUAL_ENV:-}" && "${VIRTUAL_ENV:-}" == "$(pwd)/$DEPLOY_VENV" ]]; then
    command -v deactivate >/dev/null 2>&1 && deactivate || true
  fi

  # Reactivate original venv
  if [[ -n "$ORIG_VENV" && -d "$ORIG_VENV" ]]; then
    echo "==> Restoring original venv: $ORIG_VENV"
    source "$ORIG_VENV/bin/activate" || true
  else
    export PATH="$ORIG_PATH"
  fi

  # Remove deploy venv
  rm -rf "$DEPLOY_VENV"
  
  # Keep wheelhouse by default for faster re-deploys
  # (Use --clean flag on next run to refresh it)
  
  echo "==> Cleanup complete"
  if [[ -d "$WHEELHOUSE" ]]; then
    echo "==> Wheelhouse preserved for faster subsequent deploys"
  fi
}
trap cleanup EXIT

echo "=========================================="
echo "Zappa Deployment Script"
echo "Stage: $STAGE"
echo "Action: $ACTION"
if [[ "$CLEAN_BUILD" == "true" ]]; then
  echo "Mode: CLEAN BUILD (fresh wheelhouse)"
else
  echo "Mode: INCREMENTAL (reuse wheelhouse)"
fi
echo "=========================================="
echo ""

# Step 0: Clean old artifacts
echo "==> Step 0: Preparing build environment"
rm -f "$FREEZE_FILE"  # Always regenerate freeze file
if [[ "$CLEAN_BUILD" == "true" ]]; then
  echo "    Removing old wheelhouse (clean build requested)..."
  rm -rf "$WHEELHOUSE"
elif [[ -d "$WHEELHOUSE" ]]; then
  echo "    Reusing existing wheelhouse (faster build)"
  echo "    Tip: Use --clean flag for fresh download"
fi
echo ""

# Step 1: Verify we're in a venv
echo "==> Step 1: Verify environment"
if [[ -z "${VIRTUAL_ENV:-}" ]]; then
  echo "ERROR: Not in a virtualenv. Please activate your dev venv first:" >&2
  echo "  source venv/bin/activate" >&2
  exit 1
fi
echo "    Current venv: $VIRTUAL_ENV"

# Step 2: Capture exact environment
echo "==> Step 2: Capturing current environment (exact versions)"
pip freeze --exclude-editable > "$FREEZE_FILE.tmp"

# Clean up any malformed lines (git references, local paths, etc.)
grep -v "^-e " "$FREEZE_FILE.tmp" | \
grep -v "\.git@" | \
grep -v "^file://" | \
grep -E "^[a-zA-Z0-9_-]+" > "$FREEZE_FILE" || touch "$FREEZE_FILE"

rm -f "$FREEZE_FILE.tmp"
echo "    Captured $(wc -l < "$FREEZE_FILE" | tr -d ' ') packages"

# Step 3: Detect editable installs (supports both old and new PEP 660 style)
echo ""
echo "==> Step 3: Detecting editable installs"
EDITABLE_PATHS=()
while IFS= read -r path; do
  if [[ -n "$path" ]]; then
    EDITABLE_PATHS+=("$path")
    echo "    Found: $path"
  fi
done < <(python - <<'PY'
import subprocess, json, sys

# Use pip list to find editable installs (works for both old and new style)
try:
    result = subprocess.run(
        [sys.executable, '-m', 'pip', 'list', '--format=json', '--editable'],
        capture_output=True,
        text=True,
        check=True
    )
    packages = json.loads(result.stdout)
    
    for pkg in packages:
        if 'editable_project_location' in pkg:
            print(pkg['editable_project_location'])
except Exception as e:
    # Fallback: try to find .egg-link files (old style)
    import site, glob, os
    paths = []
    try:
        paths += site.getsitepackages()
    except Exception:
        pass
    try:
        paths.append(site.getusersitepackages())
    except Exception:
        pass
    
    for p in paths:
        if not p or not os.path.isdir(p):
            continue
        for link in glob.glob(os.path.join(p, '*.egg-link')):
            try:
                with open(link, 'r') as f:
                    src = f.readline().strip()
                    if src and os.path.isdir(src):
                        print(src)
            except Exception:
                pass
PY
)

if [[ ${#EDITABLE_PATHS[@]} -eq 0 ]]; then
  echo "    No editable installs found"
fi

# Step 4: Create wheelhouse directory
echo ""
echo "==> Step 4: Creating wheelhouse: $WHEELHOUSE"
rm -rf "$WHEELHOUSE"
mkdir -p "$WHEELHOUSE"

# Step 5: Download wheels for non-editable packages
echo ""
echo "==> Step 5: Downloading wheels for frozen packages"
if [[ -s "$FREEZE_FILE" ]]; then
  pip download -r "$FREEZE_FILE" -d "$WHEELHOUSE" --no-deps
  echo "    Downloaded wheels to $WHEELHOUSE"
else
  echo "    No packages to download"
fi

# Step 6: Note editable installs (will be installed from source in deployment venv)
if [[ ${#EDITABLE_PATHS[@]} -gt 0 ]]; then
  echo ""
  echo "==> Step 6: Local packages detected (will install from source)"
  for src in "${EDITABLE_PATHS[@]}"; do
    echo "    - $src"
  done
else
  echo ""
  echo "==> Step 6: No editable installs found"
fi

echo ""
echo "==> Wheelhouse contents:"
ls -lh "$WHEELHOUSE" | tail -n +2 | awk '{print "    " $9 " (" $5 ")"}'

# Step 7: Create clean deployment venv
echo ""
echo "==> Step 7: Creating clean deployment venv"
deactivate 2>/dev/null || true
rm -rf "$DEPLOY_VENV"
$PYTHON_BIN -m venv "$DEPLOY_VENV"
source "$DEPLOY_VENV/bin/activate"

# Upgrade pip in deploy venv
python -m pip install --upgrade pip setuptools wheel -q

# Step 8: Install from wheelhouse
echo ""
echo "==> Step 8: Installing packages from wheelhouse"

# First install PyPI packages from freeze file using wheelhouse
if [[ -s "$FREEZE_FILE" ]]; then
  echo "    Installing from freeze file..."
  pip install --no-index --find-links "$WHEELHOUSE" -r "$FREEZE_FILE"
else
  echo "    No freeze file to install from"
fi

# Then install local packages directly from source (not as wheels)
if [[ ${#EDITABLE_PATHS[@]} -gt 0 ]]; then
  echo "    Installing local packages from source..."
  
  # Install in dependency order: renglo-lib first
  for src in "${EDITABLE_PATHS[@]}"; do
    if [[ "$src" =~ renglo-lib ]]; then
      echo "      - $(basename "$src")"
      pip install "$src" --no-deps
    fi
  done
  
  # Then install others
  for src in "${EDITABLE_PATHS[@]}"; do
    if [[ ! "$src" =~ renglo-lib ]]; then
      echo "      - $(basename "$src")"
      pip install "$src" --no-deps
    fi
  done
fi

echo "    Installation complete"

# Step 9: Ensure Zappa is installed
echo ""
echo "==> Step 9: Ensuring Zappa is installed"
if ! command -v zappa >/dev/null 2>&1; then
  echo "    Installing zappa..."
  pip install zappa -q
else
  echo "    Zappa already installed"
fi

# Step 10: Verify no editable installs
echo ""
echo "==> Step 10: Verifying no editable installs in deployment venv"
if pip freeze | grep -q "^-e "; then
  echo "ERROR: Editable installs detected in deployment venv!" >&2
  pip freeze | grep "^-e " >&2
  exit 1
else
  echo "    ✓ No editable installs (clean deployment venv)"
fi

# Step 11: Show what will be deployed
echo ""
echo "==> Step 11: Deployment environment summary"
echo "    Python: $(python --version)"
echo "    Pip: $(pip --version)"
echo "    Zappa: $(zappa --version 2>/dev/null || echo 'installed')"
echo "    Total packages: $(pip list | tail -n +3 | wc -l | tr -d ' ')"

# Step 12: Temporarily move wheelhouse out of the way before Zappa packages
echo ""
echo "==> Step 12: Preparing for Zappa packaging"
WHEELHOUSE_TMP=""
if [[ -d "$WHEELHOUSE" ]]; then
  WHEELHOUSE_TMP=$(mktemp -d)
  echo "    Temporarily moving wheelhouse out of packaging directory..."
  mv "$WHEELHOUSE" "$WHEELHOUSE_TMP/wheelhouse"
fi

# Step 13: Deploy with Zappa
echo ""
echo "=========================================="
echo "==> Step 13: Running Zappa $ACTION $STAGE"
echo "=========================================="
echo ""

if [[ "$ACTION" == "deploy" ]]; then
  zappa deploy "$STAGE"
else
  zappa update "$STAGE"
fi

# Restore wheelhouse after packaging (before cleanup)
if [[ -n "$WHEELHOUSE_TMP" && -d "$WHEELHOUSE_TMP/wheelhouse" ]]; then
  echo ""
  echo "==> Restoring wheelhouse..."
  mv "$WHEELHOUSE_TMP/wheelhouse" "$WHEELHOUSE"
  rmdir "$WHEELHOUSE_TMP" 2>/dev/null || true
fi

echo ""
echo "=========================================="
echo "==> Deployment complete!"
echo "=========================================="
echo ""
echo "To check logs:"
echo "  source venv/bin/activate"
echo "  zappa tail $STAGE"
echo ""

