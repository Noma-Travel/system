# Noma local development — environment setup

> **Developer guide (PT-BR):** see **[GUIA_DESENVOLVEDOR.md](./GUIA_DESENVOLVEDOR.md)** — onboarding, scenarios, troubleshooting, and migration from the old `.env` workflow.

Central configuration lives in [`config/`](../config/). The **`run`** command is the only entry point: it generates `.env` files and starts local processes.

## Prerequisites

- AWS CLI with profile `noma` (`aws sso login --profile noma`)
- IAM: `secretsmanager:GetSecretValue` on `noma/env/staging` and `noma/env/production`
- Python 3.12 venv in `system/venv` (`py -3.12 -m venv venv`; includes `truststore` for AWS SSL on Windows)
- Node.js for `NOMA` and `console`

Optional personal overrides: copy `config/local.override.yaml.example` → `config/local.override.yaml`.

## Invoke `run`

**Windows (no alias required):**

```powershell
cd C:\Noma\system
.\run.ps1 noma console backend env:staging handler:local
```

**Linux / macOS:**

```bash
cd /path/to/system
./run_stack.sh noma console backend env:staging handler:local
```

Each app opens in a **separate terminal window** by default. The orchestrator terminal stays open; press **Ctrl+C** there to stop all apps. Use `--same-terminal` to keep everything in one window.

**PowerShell alias** (profile or session):

```powershell
function run { python C:\Noma\system\scripts\run.py @args }
```

**Git Bash:**

```bash
alias run='python /c/Noma/system/scripts/run.py'
```

**Direct Python:**

```powershell
python C:\Noma\system\scripts\run.py noma env:staging handler:local
```

## Command grammar

```text
run <apps...> env:<staging|prod> [handler:<local|staging|prod>] [--same-terminal]
run --check
run --verify
```

| Token | Meaning |
|-------|---------|
| `noma`, `console`, `backend` | Which apps to start (any combination) |
| `env:staging` / `env:prod` | Cognito, secrets, tables, integrations |
| `handler:local` | API/WS → `127.0.0.1:5001` / local WS |
| `handler:staging` / `handler:prod` | API/WS → remote API Gateway |

**Default `handler`:** if `backend` is in apps → `local`; else same as `env`.

### Examples

```bash
run noma env:prod handler:local
run console backend env:staging handler:local
run noma console env:prod handler:prod
run backend env:staging
```

## What gets generated

| App | Files |
|-----|-------|
| `backend` | `system/env_config.py`, `system/env.development` |
| `console` | `console/.env.development` |
| `noma` | `NOMA/.env.local` |

Backend starts with `venv\Scripts\python.exe main.py`, `PYTHONPATH` for `renglo-api`, `renglo-lib`, and `extensions/backend/package`. Repos are discovered dynamically by git folder name (see GUIA for flexible layouts).

## Separate terminals

By default each app runs in its own window (`noma-backend`, `noma-console`, `noma-noma`). The `run` terminal supervises all processes; **Ctrl+C** there stops everything. Pass `--same-terminal` for single-window mode.

## Local WebSocket (WSS)

With `handler:local`, `run` automatically starts the dev WebSocket service (`extensions/wss/dev_ws_service.py`) at `ws://127.0.0.1:8080/ws` in its own window (`noma-wss`) — the same URL injected by `handler_overrides/local.yaml`. It is supervised like the other apps and stops on Ctrl+C.

Prerequisite (one time): clone the `wss` repo and create its venv (`python -m venv wss-venv` + `pip install -r requirements.txt`). If the repo or venv is missing, `run` logs a warning and continues without local WebSocket. With `handler:staging`/`handler:prod` the local WSS is not started (remote API Gateway is used).

## Validation & inspection

```bash
run --check                              # catalog vs code references
run --verify                             # scenario matrix (no processes)
python scripts/show_env_scenarios.py       # print resolved vars per scenario (secrets masked)
python scripts/audit_env_vars.py         # regenerate env.catalog.generated.yaml draft
```

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `run` not recognized | Use `.\run.ps1` or full `python scripts/run.py` path |
| Secrets / SSL errors | `aws sso login --profile noma`; set `$env:AWS_PROFILE = "noma"` |
| Edited `.env.local` reverted | Use `config/local.override.yaml` instead |
| Auth mismatch | Align `env:` (Cognito) with `handler:` (API target) |

## Publishing secrets (admin only)

**Developers do not need to publish secrets** if `noma/env/staging` and `noma/env/production` already exist in AWS Secrets Manager.

One-time or rotation (extracts from Zappa settings automatically):

```bash
python scripts/publish_env_secret.py staging --from-zappa
python scripts/publish_env_secret.py prod --from-zappa
```

Manual JSON (optional):

```bash
python scripts/publish_env_secret.py staging config/secrets/staging.json
```

Copy `config/secrets/staging.json.example` only when adding keys not present in Zappa.

## Adding a new variable

1. Add entry to `config/env.catalog.yaml`
2. Add non-secret default to `profiles/staging.yaml` / `profiles/production.yaml` if applicable
3. Add secret to AWS SM or document in publish script
4. If routing-related, mark `routing: true` and update `handler_overrides/` if needed
5. Run `run --check` and `run --verify`
