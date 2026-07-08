# Noma centralized environment config

Single source of truth for local dev environment variables. Secrets live in AWS Secrets Manager (`noma/env/staging`, `noma/env/production`); structure and non-secret defaults live here (versioned).

## Developer guide

**Start here:** [`docs/GUIA_DESENVOLVEDOR.md`](../docs/GUIA_DESENVOLVEDOR.md) — onboarding, daily scenarios, troubleshooting (PT-BR).

Technical reference (EN): [`docs/ENVIRONMENT_SETUP.md`](../docs/ENVIRONMENT_SETUP.md).

## Layout

- `env.catalog.yaml` — variable schema (consumers, required envs, routing flags)
- `mappings.yaml` — canonical backend keys → frontend env names
- `profiles/staging.yaml`, `profiles/production.yaml` — non-secret values per `env`
- `handler_overrides/*.yaml` — API/WebSocket routing per `handler`
- `local.override.yaml` — personal overrides (gitignored; copy from `local.override.yaml.example`)

## Usage

```powershell
# Windows
cd C:\Noma\system
.\run.ps1 noma console backend env:staging handler:local
```

```bash
# Linux / macOS
cd /path/to/system
./run_stack.sh noma console backend env:staging handler:local
```

```powershell
.\venv\Scripts\python.exe scripts\run.py --check    # catalog drift
.\venv\Scripts\python.exe scripts\run.py --verify   # scenario matrix
```

Each app opens in a separate terminal window by default; use `--same-terminal` for single-window mode.

With `handler:local`, `run` also starts the local WebSocket service (`extensions/wss`) automatically in a `noma-wss` window; if the `wss` repo or its `wss-venv` is missing, it warns and continues.

Generation is **only** triggered by `run` (via internal `envgen` module). There is no separate setup command.
