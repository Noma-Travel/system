#!/bin/bash
# Run the Tank from THIS checkout.
#
# Why this exists
# ---------------
# `noma`, `renglo` and `renglo_api` are pip-installed in EDITABLE mode pointing
# at a different working copy (…/_noma_/…). Without the PYTHONPATH pin below,
# `python main.py` from here still imports that other tree — silently, with no
# error — so nothing you edit in this checkout actually runs.
#
# The two trees have diverged: this one has `last_llm_usage` in
# renglo/agent/agent_utilities.py and `renglo_api/langfuse_tracing.py`; the
# other has neither. All three packages must be pinned together or you get a
# mix of old and new.
#
# Windows notes: PYTHONPATH is split on ';' by the Windows Python binary (not
# ':'), and it needs Windows-style paths, hence `pwd -W`.
#
# Verify what actually loaded:
#   ./run-pinned.sh --check
#
# The permanent fix is repointing the editable installs at this checkout; until
# then, use this instead of run.bat.

set -e

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Windows-style root. Written as an explicit if/else because
# `cd .. && pwd -W || cd .. && pwd` parses as `((a && b) || c) && d` — when
# `pwd -W` succeeds the trailing `&& pwd` STILL runs and ROOT ends up holding
# both paths on two lines, which silently produces a broken PYTHONPATH.
ROOT="$(cd "$HERE/.." && pwd -W 2>/dev/null)"
if [ -z "$ROOT" ]; then
  ROOT="$(cd "$HERE/.." && pwd)"
fi

PIN="$ROOT/extensions/backend/package;$ROOT/dev/renglo-lib;$ROOT/dev/renglo-api"
if [ -n "$PYTHONPATH" ]; then
  export PYTHONPATH="$PIN;$PYTHONPATH"
else
  export PYTHONPATH="$PIN"
fi

# pip and some metadata readers choke on the accented path ("Área de Trabalho")
# under the cp1252 default; UTF-8 mode makes that deterministic.
export PYTHONUTF8=1

export AWS_PROFILE=joao-noma
export AWS_DEFAULT_REGION=us-east-1

if [ "$1" = "--check" ]; then
  cd "$HERE"
  python -c "
import importlib.util, inspect, sys

# find_spec, not import: importing renglo_api registers Flask blueprints and
# needs live DynamoDB config, which is not what this check is about.
ok = True
for name in ('noma', 'renglo', 'renglo_api'):
    spec = importlib.util.find_spec(name)
    origin = (spec.origin if spec else '') or ''
    print(name.ljust(11), origin.split('Trabalho', 1)[-1] or 'NAO ENCONTRADO')
    if not spec or '_noma_' in origin:
        print('   ^^ FALHA: viria do checkout antigo')
        ok = False

import renglo.agent.agent_utilities as au
if 'last_llm_usage' not in inspect.getsource(au):
    print('FALHA: renglo sem last_llm_usage — o A/B nao mede token')
    ok = False

from noma.agent_computer.agent import AgentComputer
from noma.agent_computer.prompt import load_kit_doc
AgentComputer()
if not load_kit_doc().startswith('# NOMA.md'):
    print('FALHA: kit NOMA.md nao encontrado')
    ok = False

print()
print('agent_computer OK — pode subir o Tank' if ok else 'AMBIENTE INCONSISTENTE')
sys.exit(0 if ok else 1)
"
  exit $?
fi

cd "$HERE"
python main.py
