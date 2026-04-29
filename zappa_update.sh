#!/usr/bin/env bash
set -euo pipefail

# Zappa Deployment Script (Simplified)
# 
# Usage:
#   ./zappa_update.sh <stage> [update|deploy] [--clean]
#   ./zappa_update.sh noma_prod update
#   ./zappa_update.sh noma_prod update --clean  # Force clean wheelhouse
#
# What it does:
# 1. Captures your EXACT current environment (pip freeze)
# 2. Downloads wheels for all packages at exact versions (manylinux cp312 x86_64 for Lambda;
#    set ZAPPA_LAMBDA_WHEEL_PLATFORM=0 to use host wheels — not valid for Lambda Linux)
# 3. Creates clean deployment venv with those exact packages
# 4. Installs local packages from source
# 5. Deploys with Zappa
# 6. Restores your original environment
#
# Speed optimization:
# - Wheelhouse is kept between deploys (faster subsequent deploys)
# - Use --clean flag to force fresh download

STAGE="${1:-noma_prod}"
ACTION="${2:-update}"  # "deploy" for first-time; "update" otherwise
CLEAN_BUILD=false

# Check for --clean flag
for arg in "$@"; do
  if [[ "$arg" == "--clean" ]]; then
    CLEAN_BUILD=true
  fi
done

WHEELHOUSE=".wheelhouse"
FREEZE_FILE=".freeze.txt"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Absolute path: Git Bash + relative ".venv_deploy" can break -f/-x tests for Scripts/python.exe
DEPLOY_VENV="${SCRIPT_DIR}/.venv_deploy"

# Default: build for AWS Lambda (Linux x86_64, CPython 3.12). Required when running this script on
# Windows/macOS so pip downloads and installs manylinux wheels; set ZAPPA_LAMBDA_WHEEL_PLATFORM=0
# to use host wheels (broken on Lambda for native modules like pydantic_core).
LAMBDA_PIP_PLATFORM_FLAGS=()
if [[ "${ZAPPA_LAMBDA_WHEEL_PLATFORM:-1}" != "0" ]]; then
  LAMBDA_PIP_PLATFORM_FLAGS=(--platform manylinux2014_x86_64 --implementation cp --python-version 312 --abi cp312)
fi

# Track original environment
ORIG_VENV="${VIRTUAL_ENV:-}"
ORIG_PATH="$PATH"

# shellcheck disable=SC1091
source_venv() {
  local v="$1"
  if [[ -f "$v/Scripts/activate" ]]; then
    source "$v/Scripts/activate"
  elif [[ -f "$v/bin/activate" ]]; then
    source "$v/bin/activate"
  else
    echo "ERROR: No activate script in $v (expected Scripts/activate or bin/activate)" >&2
    return 1
  fi
}

# Cleanup function
cleanup() {
  echo ""
  echo "==> Cleaning up..."

  # Windows venv activate can strip MSYS paths; restore coreutils + mingw64 for bash/cygpath.
  export PATH="/mingw64/bin:/usr/bin:/bin:${PATH:-}"

  # If Step 13 failed after Step 12 moved .wheelhouse aside, put it back (next run needs it).
  if [[ -n "${WHEELHOUSE_TMP:-}" && -d "${WHEELHOUSE_TMP}/wheelhouse" ]] && [[ ! -d "$WHEELHOUSE" ]]; then
    echo "==> Restoring wheelhouse (deploy interrupted before normal restore)..."
    mv "${WHEELHOUSE_TMP}/wheelhouse" "$WHEELHOUSE"
    rmdir "${WHEELHOUSE_TMP}" 2>/dev/null || true
  fi
  
  # Deactivate deploy venv if active
  if [[ -n "${VIRTUAL_ENV:-}" ]]; then
    command -v deactivate >/dev/null 2>&1 && deactivate || true
  fi

  # Reactivate original venv
  if [[ -n "$ORIG_VENV" && -d "$ORIG_VENV" ]]; then
    echo "==> Restoring original venv: $ORIG_VENV"
    source_venv "$ORIG_VENV" || true
  else
    export PATH="$ORIG_PATH"
  fi

  # Remove deploy venv
  rm -rf "$DEPLOY_VENV"

  # Remove werkzeug vendored at project root for Zappa packaging (Step 8c)
  if [[ -f "$SCRIPT_DIR/.werkzeug_vendored_for_zappa" ]]; then
    rm -rf "$SCRIPT_DIR/werkzeug"
    rm -f "$SCRIPT_DIR/.werkzeug_vendored_for_zappa"
    echo "==> Removed temporary vendored werkzeug/ from project root"
  fi
  
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
  echo "  Linux/macOS: source venv/bin/activate" >&2
  echo "  Windows Git Bash: source venv/Scripts/activate" >&2
  exit 1
fi
echo "    Current venv: $VIRTUAL_ENV"

# Cursor / minimal hosts: a prior broken `source venv/Scripts/activate` can leave
# _OLD_VIRTUAL_PATH pointing at a Windows-only PATH; the next line in activate runs
# `cygpath` after `deactivate` restores that PATH — cygpath disappears. Fix PATH and
# re-source this venv once so _OLD_* matches a MSYS-safe PATH.
if [[ "${OSTYPE:-}" == "msys" || "${OSTYPE:-}" == "cygwin" ]] && [[ -n "${VIRTUAL_ENV:-}" ]]; then
  export PATH="/mingw64/bin:/usr/bin:/bin:${PATH:-}"
  unset _OLD_VIRTUAL_PATH _OLD_VIRTUAL_PYTHONHOME _OLD_VIRTUAL_PS1 2>/dev/null || true
  if [[ -f "${VIRTUAL_ENV}/Scripts/activate" ]]; then
    # shellcheck disable=SC1090
    source "${VIRTUAL_ENV}/Scripts/activate"
  elif [[ -f "${VIRTUAL_ENV}/bin/activate" ]]; then
    # shellcheck disable=SC1090
    source "${VIRTUAL_ENV}/bin/activate"
  fi
fi

# Prefer the active venv's interpreter (avoids Windows Store python3 / wrong PATH)
if [[ -x "$VIRTUAL_ENV/Scripts/python.exe" ]]; then
  PYTHON_BIN="$VIRTUAL_ENV/Scripts/python.exe"
elif [[ -x "$VIRTUAL_ENV/bin/python" ]]; then
  PYTHON_BIN="$VIRTUAL_ENV/bin/python"
else
  PYTHON_BIN="${PYTHON_BIN:-python}"
fi
echo "    Using Python: $PYTHON_BIN"

# CPython that must run `python -m venv` for the deploy tree. On Windows, if you create a venv
# using an *already-virtual* python.exe (the dev venv), the child venv is invalid: pyvenv.cfg
# chains to the parent and sys.prefix stays the parent venv, so all pip --target and imports hit
# the wrong site-packages. Resolve the real base install from the dev venv's pyvenv.cfg.
# shellcheck disable=SC2016
VENV_BASE_PYTHON="$("$PYTHON_BIN" -c 'import pathlib, sys; cfg = pathlib.Path(sys.prefix) / "pyvenv.cfg"
if not cfg.is_file():
    print(sys.executable)
    raise SystemExit(0)
for line in cfg.read_text(encoding="utf-8").splitlines():
    s = line.strip()
    if s.lower().startswith("executable") and "=" in s:
        print(s.split("=", 1)[1].strip())
        break
else:
    print(sys.executable)
' 2>/dev/null || true)"
if [[ -z "$VENV_BASE_PYTHON" || ! -e "$VENV_BASE_PYTHON" ]]; then
  VENV_BASE_PYTHON="$PYTHON_BIN"
fi
echo "    Base Python for new venvs (python -m venv): $VENV_BASE_PYTHON"

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

# Local ../ paths must always be installed from source: pip freeze strips git+ lines, and
# non-editable git installs would otherwise be missing from the deploy venv. Merge these even
# when the dev venv already has other editable installs (previously Step 3b ran only when
# EDITABLE_PATHS was empty, which dropped e.g. ../extensions/backend/package).
merge_local_paths_from_req() {
  local reqfile="$1"
  [[ -f "$reqfile" ]] || return 0
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%%#*}"
    line="$(echo "$line" | xargs)"
    [[ -z "$line" ]] && continue
    [[ "$line" =~ ^-r[[:space:]] ]] && continue
    if [[ "$line" =~ ^\.\./ ]] && [[ -d "$line" ]]; then
      local found=false
      for p in "${EDITABLE_PATHS[@]}"; do
        if [[ "$p" == "$line" ]]; then found=true; break; fi
      done
      if [[ "$found" == false ]]; then
        EDITABLE_PATHS+=("$line")
        echo "    Added (local path from $reqfile): $line"
      fi
    fi
  done < "$reqfile"
}

echo ""
echo "==> Step 3b: Resolving local package paths from requirements files"
merge_local_paths_from_req "requirements.txt"
merge_local_paths_from_req "requirements-noma-travel.txt"

# Step 4: Create wheelhouse directory
echo ""
echo "==> Step 4: Creating wheelhouse: $WHEELHOUSE"
rm -rf "$WHEELHOUSE"
mkdir -p "$WHEELHOUSE"

# Step 5: Download wheels for non-editable packages
# Lambda runs Linux x86_64 (see zappa_settings.json runtime). On Windows/macOS, a plain
# `pip download` pulls host-OS wheels; native modules (pydantic_core, cryptography, jiter, …)
# then fail at import with errors like ModuleNotFoundError for pydantic_core._pydantic_core.
echo ""
echo "==> Step 5: Downloading wheels for frozen packages"
if [[ -s "$FREEZE_FILE" ]]; then
  if [[ "${ZAPPA_LAMBDA_WHEEL_PLATFORM:-1}" == "0" ]]; then
    echo "    ZAPPA_LAMBDA_WHEEL_PLATFORM=0: downloading for host platform (not for Lambda Linux)"
    pip download -r "$FREEZE_FILE" -d "$WHEELHOUSE" --no-deps
  else
    echo "    Target: manylinux2014_x86_64 / cp312 (AWS Lambda python3.12)"
    pip download -r "$FREEZE_FILE" -d "$WHEELHOUSE" --no-deps "${LAMBDA_PIP_PLATFORM_FLAGS[@]}"
  fi
  echo "    Downloaded wheels to $WHEELHOUSE"
else
  echo "    No packages to download"
fi

# greenlet: some releases (e.g. 3.3.2) publish only win/mac wheels + Linux sdist — no manylinux .whl.
# pip cannot compile Linux greenlet on Windows; use a version that ships manylinux (gevent still supports it).
if [[ -s "$FREEZE_FILE" ]] && [[ "${ZAPPA_LAMBDA_WHEEL_PLATFORM:-1}" != "0" ]] && grep -q '^greenlet==' "$FREEZE_FILE"; then
  echo ""
  echo "==> Step 5b: Ensuring greenlet manylinux wheel (Lambda)"
  rm -f "$WHEELHOUSE"/greenlet-*
  pip download 'greenlet==3.2.5' -d "$WHEELHOUSE" --no-deps "${LAMBDA_PIP_PLATFORM_FLAGS[@]}" --only-binary=:all:
  # Align freeze line with the wheel we install (avoids pip install version mismatch)
  tmp_freeze="$(mktemp)"
  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" =~ ^greenlet== ]]; then
      echo "greenlet==3.2.5"
    else
      echo "$line"
    fi
  done < "$FREEZE_FILE" > "$tmp_freeze"
  mv "$tmp_freeze" "$FREEZE_FILE"
  echo "    Pinned greenlet==3.2.5 for Lambda (manylinux wheel)"
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
"$VENV_BASE_PYTHON" -m venv "$DEPLOY_VENV"
source_venv "$DEPLOY_VENV"
# Windows Scripts/activate drops MSYS paths; restore for basename/grep/mktemp/rm.
export PATH="/mingw64/bin:/usr/bin:/bin:${PATH:-}"
# Force the deploy venv to win over the still-on-PATH dev venv: on Git Bash, nested activate can
# leave venv/Scripts before .venv_deploy/Scripts, so `command -v python.exe` keeps using the dev venv
# and pip --target writes the wrong site-packages (Zappa zip missing werkzeug).
export PATH="${DEPLOY_VENV}/Scripts:${PATH}"

# Interpreter: always the deploy venv binary (never rely on PATH order for `python`).
if [[ -e "$DEPLOY_VENV/Scripts/python.exe" ]]; then
  DEPLOY_PYTHON="$DEPLOY_VENV/Scripts/python.exe"
elif [[ -e "$DEPLOY_VENV/bin/python" ]]; then
  DEPLOY_PYTHON="$DEPLOY_VENV/bin/python"
else
  echo "ERROR: No python under $DEPLOY_VENV (expected Scripts/python.exe or bin/python)" >&2
  exit 1
fi
if ! "$DEPLOY_PYTHON" -c "import sys" 2>/dev/null; then
  echo "ERROR: Not runnable: $DEPLOY_PYTHON" >&2
  exit 1
fi
if ! "$DEPLOY_PYTHON" -c "import os, sys; b=os.path.basename(os.path.normpath(sys.prefix)); assert b=='.venv_deploy', (b, sys.prefix, sys.executable)"; then
  echo "ERROR: $DEPLOY_PYTHON is not the deploy venv (sys.prefix should end in .venv_deploy). Got:" >&2
  "$DEPLOY_PYTHON" -c "import sys; print('sys.prefix', sys.prefix); print('sys.executable', sys.executable)" >&2
  exit 1
fi

# Upgrade pip in deploy venv
"$DEPLOY_PYTHON" -m pip install --upgrade pip setuptools wheel -q

# venv purelib (reliable on Windows; getsitepackages()[0] can point elsewhere)
DEPLOY_SITE="$("$DEPLOY_PYTHON" -c "import os, sysconfig; print(os.path.normpath(sysconfig.get_path('purelib')))")"
echo "    Deploy venv site-packages: $DEPLOY_SITE"

# Step 8: Install from wheelhouse
echo ""
echo "==> Step 8: Installing packages from wheelhouse"

# First install PyPI packages from freeze file using wheelhouse
if [[ -s "$FREEZE_FILE" ]]; then
  echo "    Installing from freeze file..."
  if [[ "${ZAPPA_LAMBDA_WHEEL_PLATFORM:-1}" == "0" ]]; then
    "$DEPLOY_PYTHON" -m pip install --no-index --find-links "$WHEELHOUSE" -r "$FREEZE_FILE"
  else
    # Windows/macOS pip only allows --platform with --target (or --dry-run). Install into this
    # venv's site-packages so the layout matches a normal environment for Zappa packaging.
    # --no-deps: required by pip when using --platform with a requirements file; freeze is flat.
    # --ignore-installed: without this, pip may skip packages already satisfied by the system Python
    # (those packages are not what Zappa zips from the venv).
    "$DEPLOY_PYTHON" -m pip install --no-index --find-links "$WHEELHOUSE" -r "$FREEZE_FILE" --no-deps \
      --ignore-installed "${LAMBDA_PIP_PLATFORM_FLAGS[@]}" --target "$DEPLOY_SITE"
  fi
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
      "$DEPLOY_PYTHON" -m pip install "$src" --no-deps
    fi
  done
  
  # Then install others
  for src in "${EDITABLE_PATHS[@]}"; do
    if [[ ! "$src" =~ renglo-lib ]]; then
      echo "      - $(basename "$src")"
      "$DEPLOY_PYTHON" -m pip install "$src" --no-deps
    fi
  done
fi

# Step 8b: Freeze + --target may install renglo-* from pip's cached wheel (stale vs your working tree).
# Always refresh renglo-lib / renglo-api from ../dev so Lambda gets the same code you edit locally.
echo ""
echo "==> Step 8b: Refresh renglo-lib and renglo-api from dev tree (no stale pip cache)"
_RENGLO_LIB="${SCRIPT_DIR}/../dev/renglo-lib"
_RENGLO_API="${SCRIPT_DIR}/../dev/renglo-api"
if [[ -d "$_RENGLO_LIB" ]]; then
  echo "    pip install --force-reinstall: $_RENGLO_LIB"
  "$DEPLOY_PYTHON" -m pip install --no-cache-dir --force-reinstall --no-deps "$_RENGLO_LIB"
else
  echo "    (skip) not found: $_RENGLO_LIB"
fi
if [[ -d "$_RENGLO_API" ]]; then
  echo "    pip install --force-reinstall: $_RENGLO_API"
  "$DEPLOY_PYTHON" -m pip install --no-cache-dir --force-reinstall --no-deps "$_RENGLO_API"
else
  echo "    (skip) not found: $_RENGLO_API"
fi

# Step 8c: Zappa's Windows+manylinux zip merge can omit pure-Python packages from site-packages
# even when they import in the deploy venv. Zappa's handler.py imports werkzeug before the app
# (see venv/Lib/site-packages/zappa/handler.py). Vendoring ensures /var/task/werkzeug exists in Lambda.
echo ""
echo "==> Step 8c: Vendoring werkzeug into project root for Zappa/Lambda zip"
if [[ -d "$DEPLOY_SITE/werkzeug" ]]; then
  rm -rf "$SCRIPT_DIR/werkzeug"
  cp -R "$DEPLOY_SITE/werkzeug" "$SCRIPT_DIR/werkzeug"
  : > "$SCRIPT_DIR/.werkzeug_vendored_for_zappa"
  echo "    Copied werkzeug/ from deploy venv to project root (removed in cleanup on exit)"
else
  echo "ERROR: werkzeug not found under deploy site-packages: $DEPLOY_SITE" >&2
  exit 1
fi

# Fail fast before Zappa packages a broken tree (Lambda imports werkzeug in handler).
# Do not import pydantic_core here: manylinux wheels place a Linux .so that Windows cannot load,
# but Zappa will package it correctly for Lambda.
if [[ "${ZAPPA_LAMBDA_WHEEL_PLATFORM:-1}" != "0" ]]; then
  echo "    Verifying imports (werkzeug)..."
  "$DEPLOY_PYTHON" -c "import werkzeug; print('    Import check OK')" || {
    echo "ERROR: werkzeug import failed in deploy venv. Fix wheelhouse / Step 8 before deploying." >&2
    exit 1
  }
fi

echo "    Installation complete"

# Step 9: Ensure Zappa is installed
echo ""
echo "==> Step 9: Ensuring Zappa is installed"
if ! "$DEPLOY_PYTHON" -m pip show zappa >/dev/null 2>&1; then
  echo "    Installing zappa..."
  "$DEPLOY_PYTHON" -m pip install zappa -q
else
  echo "    Zappa already installed"
fi

# Zappa entry point: `pip install --target` does not install console_scripts (no Scripts/zappa.exe).
# Use the CLI module (zappa has no top-level __main__).
ZAPPA_CLI=( "$DEPLOY_PYTHON" -m zappa.cli )

# Step 9b: Patch Zappa (Windows / pip): handler venv pip must capture stderr
echo ""
echo "==> Step 9b: Patching Zappa create_handler_venv subprocess (Windows-safe)"
if [[ -f "$SCRIPT_DIR/scripts/patch_zappa_handler_venv.py" ]]; then
  "$DEPLOY_PYTHON" "$SCRIPT_DIR/scripts/patch_zappa_handler_venv.py" || echo "    (patch skipped or failed — continuing)"
else
  echo "    No scripts/patch_zappa_handler_venv.py — skipping"
fi

# Step 10: Verify no editable installs
echo ""
echo "==> Step 10: Verifying no editable installs in deployment venv"
if "$DEPLOY_PYTHON" -m pip freeze | grep -q "^-e "; then
  echo "ERROR: Editable installs detected in deployment venv!" >&2
  "$DEPLOY_PYTHON" -m pip freeze | grep "^-e " >&2
  exit 1
else
  echo "    ✓ No editable installs (clean deployment venv)"
fi

# Step 11: Show what will be deployed
echo ""
echo "==> Step 11: Deployment environment summary"
echo "    Python: $($DEPLOY_PYTHON --version)"
echo "    Pip: $($DEPLOY_PYTHON -m pip --version)"
echo "    Zappa: $("${ZAPPA_CLI[@]}" --version 2>/dev/null | tail -n 1)"
echo "    Total packages: $($DEPLOY_PYTHON -m pip list | tail -n +3 | wc -l | tr -d ' ')"

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
  "${ZAPPA_CLI[@]}" deploy "$STAGE"
else
  "${ZAPPA_CLI[@]}" update "$STAGE"
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
echo "  source venv/Scripts/activate   # Windows Git Bash"
echo "  source venv/bin/activate       # Linux/macOS"
echo "  zappa tail $STAGE"
echo ""

