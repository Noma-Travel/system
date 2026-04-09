# NOMA Deployment Guide (Full Stack + Backend)

This guide defines the production-safe deployment flow for the NOMA stack, how to switch between local and deployed contexts, and how backend packaging with **`zappa_update.sh`** works. It replaces any separate “Zappa-only” deploy doc—use this file as the single reference.

---

## 1) Deployment sequence

Use this sequence:

1. Confirm production frontend domain is unchanged (`https://app.travelwithnoma.com`).
2. Confirm backend allowed frontend origin values include that domain.
3. Deploy backend (`zappa update` via `./zappa_update.sh`) with current production env.
4. Run post-deploy org initialization (tools/actions, blueprint, config publish).

---

## 2) Repositories included in backend deploy

Backend deployment installs from a **hybrid Noma-Travel set** in [`requirements-noma-travel.txt`](requirements-noma-travel.txt), referenced by [`requirements.txt`](requirements.txt). It uses Noma-Travel repos where available and temporary local workspace fallbacks for repos still being created in Noma-Travel.

For a full table of Git `origin` URLs across this workspace, see [`WORKSPACE_GITHUB_ORIGINS.md`](WORKSPACE_GITHUB_ORIGINS.md).

- `https://github.com/Noma-Travel/renglo-lib.git`
- `https://github.com/Noma-Travel/renglo-api.git`
- `https://github.com/Noma-Travel/backend.git` (handlers package lives under `package/`; pip uses `subdirectory=package`)
- `https://github.com/Noma-Travel/pes.git` (not created yet; `requirements-noma-travel.txt` still uses local `../extensions/pes/package` until migrated)
- `https://github.com/Noma-Travel/pes_noma.git`

Commonly used alongside console runtime:

- `https://github.com/Noma-Travel/wss.git` (`C:/Noma/extensions/wss`)
- `https://github.com/Noma-Travel/inca.git` (`C:/Noma/extensions/inca`)

### Mirror workflow (one-time per repo)

1. Create empty repositories under `Noma-Travel` on GitHub (if they do not exist).
2. From each local clone that currently tracks `renglo/*`, add `noma-travel` remote:  
   `git remote add noma-travel https://github.com/Noma-Travel/<repo>.git`
3. Push the branch you use for deploy (e.g. `main_noma` or `main`):  
   `git push noma-travel main_noma:main` (adjust names as needed).
4. Set `origin` to Noma-Travel and remove `renglo` remotes from your workspace clones to avoid accidental pushes upstream.

Run `pip install -r requirements.txt` before `./zappa_update.sh`. When `Noma-Travel/pes` exists, replace the local `pes` path in [`requirements-noma-travel.txt`](requirements-noma-travel.txt) with a git URL (and `subdirectory=package` like other handler packages).

---

## 3) Environment variables that control context

### Frontend (NOMA app)

Main variables (see `C:/Noma/NOMA/env.example`):

- `NEXT_PUBLIC_API_BASE_URL`
- `NEXT_PUBLIC_CHAT_WS`
- `NEXT_PUBLIC_PORTFOLIO_ID`
- `NEXT_PUBLIC_ORG_ID`
- `NEXT_PUBLIC_TOOL_ID`

Important behavior:

- If `NEXT_PUBLIC_PORTFOLIO_ID` and `NEXT_PUBLIC_ORG_ID` are set, first-login onboarding can be bypassed.
- For first-login onboarding tests, keep those IDs empty/unset.

### Console frontend

Main variables (see `C:/Noma/console/.env.development.TEMPLATE` and `.env.production.TEMPLATE`):

- `VITE_API_URL`
- `VITE_API_PROXY_TARGET` (used by dev proxy in `vite.config.ts` when needed)
- `VITE_WEBSOCKET_URL`
- `VITE_COGNITO_REGION`
- `VITE_COGNITO_USERPOOL_ID`
- `VITE_COGNITO_APP_CLIENT_ID`
- `VITE_EXTENSIONS`

### Backend (renglo-api / system)

Loaded from `zappa_settings.json` env vars in Lambda and/or env config files (`env.development`, `env.production`):

- `FE_BASE_URL`
- `APP_FE_BASE_URL`
- `ALLOW_DEV_ORIGINS`
- `COGNITO_REGION`
- `COGNITO_USERPOOL_ID`
- `COGNITO_APP_CLIENT_ID`
- `WEBSOCKET_CONNECTIONS`
- `DYNAMODB_*` tables, `S3_BUCKET_NAME`, etc.

CORS / allowed access in backend:

- In Lambda, allowed origins are built from `FE_BASE_URL` + `APP_FE_BASE_URL`.
- Optional local origins are added only when `ALLOW_DEV_ORIGINS=true`.

### `WEBSOCKET_CONNECTIONS` must match the chat WebSocket API id

`WEBSOCKET_CONNECTIONS` in `zappa_settings.json` is the **HTTPS** management endpoint for API Gateway WebSocket (Lambda uses it for `postToConnection` when pushing chat/realtime messages). It must use the **same** `execute-api` **ApiId** as the NOMA app’s `NEXT_PUBLIC_CHAT_WS` (which uses **wss**). If they differ, the browser can connect to one WebSocket API while the backend posts to another, and chat updates will not appear.

**Always confirm the ApiId in your AWS account** (ids are not portable across accounts):

```bash
aws apigatewayv2 get-apis --region us-east-1 --profile noma --query "Items[?ProtocolType=='WEBSOCKET'].[ApiId,Name,ApiEndpoint]" --output table
```

For the current Noma production stack (`noma_prod_websocket`), the WebSocket ApiId is **`3vdnaldxj0`** and the stage is **`production`**. Example pair:

- `NEXT_PUBLIC_CHAT_WS` = `wss://3vdnaldxj0.execute-api.us-east-1.amazonaws.com/production`
- `WEBSOCKET_CONNECTIONS` = `https://3vdnaldxj0.execute-api.us-east-1.amazonaws.com/production`

**`$connect` and JWT:** Full WebSocket setup (routes, `chat_message` → `POST …/_chat/message`, and `$connect` / `$disconnect` as **MOCK** integrations) is described in the launcher repo: `dev/launcher/ENVIRONMENT_README.md` §7 and `dev/launcher/scripts/create_websocket_api.py`. With MOCK `$connect`, API Gateway does **not** validate the `?auth=` query string at connect time; the Cognito JWT is validated when messages hit `/_chat/message` (`socket_auth_required` in `renglo-api`).

---

## 4) Context matrix (what to change for each scenario)

### A) Local frontend + local backend

- NOMA/Console frontend: set API URL to local backend (`http://127.0.0.1:5001` or local API port).
- Backend: run locally with `env.development`.
- Keep local testing origins enabled only in local mode.

### B) Local frontend + deployed backend

- Frontend (`NOMA` or `console`): set API URL to deployed API (`https://...execute-api.../noma_prod` or custom domain); set websocket URL to deployed websocket.
- Backend (`noma_prod`): `ALLOW_DEV_ORIGINS=true` temporarily, or your local origin will be blocked by CORS. Revert after testing.

### C) Deployed frontend + deployed backend (production path)

- Frontend: deploy and confirm final public URL.
- Backend: set `FE_BASE_URL` and `APP_FE_BASE_URL` to deployed frontend URL(s); set `ALLOW_DEV_ORIGINS=false` unless explicitly required; deploy with `./zappa_update.sh`.

---

## 5) How to switch context safely

1. Choose target mode (A/B/C above).
2. Update frontend env file values (`NOMA` and/or `console`).
3. Update backend env values (`zappa_settings.json` and/or `env.production` / `env.development` as applicable).
4. Restart frontend dev servers.
5. If backend env changed for Lambda, run backend deploy.
6. Validate: browser requests hit expected API host; websocket URL matches; backend CORS accepts expected frontend origin.

Never mix accounts/profiles while switching context. Use `--profile noma` and `us-east-1` consistently unless intentionally targeting another account/region.

---

## 6) Frontend deployment (when needed)

1. Deploy NOMA frontend to Amplify (`main` branch).
2. Confirm a new deployment job appears and succeeds.
3. Confirm deployed domain is `https://app.travelwithnoma.com`.
4. If webhook is green but no deployment job appears, trigger release manually:

```bash
aws amplify start-job --region us-east-1 --app-id d1f1y2ixvuy9lc --branch-name main --job-type RELEASE --profile noma
```

---

## 7) Backend deployment (Zappa / `noma_prod`)

**Canonical script:** [`zappa_update.sh`](zappa_update.sh) in `C:/Noma/system`. There is no separate `zappa_deploy.sh`.

### Preconditions

- `FE_BASE_URL` and `APP_FE_BASE_URL` are both `https://app.travelwithnoma.com` (for production).
- `ALLOW_DEV_ORIGINS` has the intended value for the target environment.

### Commands

From `C:/Noma/system`, with the **repo `venv` activated**:

```bash
pip install -r requirements.txt

# First-time API stage: deploy; routine updates: update
./zappa_update.sh noma_prod deploy    # rare — first Zappa deploy for this stage
./zappa_update.sh noma_prod update    # normal

# Fresh wheelhouse / troubleshooting / new machine
./zappa_update.sh noma_prod update --clean
```

- On **Windows**, run **`./zappa_update.sh` from Git Bash** (e.g. `"C:\Program Files\Git\bin\bash.exe"`) so bash, paths, and the script’s traps behave correctly.
- **PowerShell** can activate the venv (`.\venv\Scripts\Activate.ps1`) for `pip install`, but invoke the script from Git Bash as above.

### Step 11 sanity check

During the run, **Step 11** prints `Total packages`. Expect **many dozens** of packages (for example **~82**), not a handful. A tiny count usually means dependencies were not installed into **`.venv_deploy`**; Lambda may then return **502** (e.g. `No module named 'werkzeug'`).

### How Zappa is invoked

The script builds a temporary **`.venv_deploy`**, installs dependencies there (including **Flask/Werkzeug**), and runs Zappa as **`python -m zappa.cli`** (not `python -m zappa`). On Windows, `pip install` with `--target` does not create `Scripts/zappa.exe` in that layout; the **`zappa.cli`** module is the supported entry point.

### Post-deploy checks

- `zappa tail noma_prod` — or `python -m zappa.cli tail noma_prod` from the same venv if `zappa` is not on `PATH`.
- Health: `/ping` responds.
- No repeated **502**/**500** on important routes (e.g. `/auth/tree`, `/auth/user`, portfolio checks). **502** from API Gateway plus **`ImportModuleError`** / missing **`werkzeug`** in CloudWatch usually means a **bad Lambda zip** — fix packaging and redeploy; browser **CORS** errors on those calls often go away once Lambda returns **200**.
- For chat/tools: check CloudWatch for `No module named ...` and filesystem errors such as `Read-only file system`. In Lambda, only **`/tmp`** is writable.

After a successful backend deploy, you can reset test users and re-run full flows; new organizations can get NOMA and SCHD tools installed automatically on creation where that logic is enabled.

---

## 8) How `zappa_update.sh` matches your dev environment

The script (see comments at top of [`zappa_update.sh`](zappa_update.sh)) roughly:

1. **Freeze** — `pip freeze --exclude-editable` → `.freeze.txt` (exact versions for non-editables).
2. **Wheelhouse** — download wheels for that freeze (Linux manylinux wheels when building for Lambda from Windows/macOS).
3. **`.venv_deploy`** — fresh venv; install from wheelhouse into that venv’s `site-packages` (and local/editables from source in dependency order).
4. **Verify** — e.g. `werkzeug` import in the deploy venv before Zappa runs.
5. **Zappa** — `python -m zappa.cli update|deploy` packages that venv for Lambda.

Conceptual flow:

```
Dev venv (frozen)     Wheelhouse           .venv_deploy          Lambda zip
────────────────     ──────────           ────────────          ──────────
pip freeze      →    .wheelhouse/*.whl →  pip install    →     Zappa packages
editables       →    (built in script)    + locals           same tree
```

Why this works:

- Same **pinned** versions as dev; install for deploy is **offline** from the wheelhouse (no surprise upgrades).
- **No editable installs** left in the deployment venv (script verifies before upload).

**Speed:** `.wheelhouse/` is **kept** between runs; use `--clean` to wipe it and re-download everything (slower, useful after upgrades or when debugging).

**Artifacts** (managed by the script; you normally do not delete these by hand):

| Path | Role |
|------|------|
| `.freeze.txt` | Regenerated each run |
| `.wheelhouse/` | Cached wheels (**kept** between runs unless `--clean`) |
| `.venv_deploy/` | Temporary full deploy venv (**removed** after the script finishes) |

If Step 12 moves `.wheelhouse` aside and Step 13 fails, cleanup **restores** `.wheelhouse` so the next run does not lose wheels.

### When to use `--clean`

- After upgrading PyPI packages in dev.
- Troubleshooting bad or incomplete wheels.
- First deploy on a new machine.

### Backend packaging troubleshooting

| Issue | What to do |
|-------|------------|
| `ERROR: Not in a virtualenv` | `cd` to `system`, `source venv/bin/activate` (or Windows `Scripts\activate`), then re-run the script. |
| `Editable installs detected` in deployment venv | Should not happen; check script output and that you did not `pip install -e` into `.venv_deploy`. |
| Wrong package versions after dev upgrade | `pip install --upgrade <pkg>` in dev, then `./zappa_update.sh noma_prod update --clean`. |
| **502** / **ImportModuleError** / **werkzeug** | Re-run `./zappa_update.sh noma_prod update --clean`; confirm Step 11 **Total packages** is large. Check `zappa_settings.json` env and CloudWatch. |
| `No module named 'noma'` / `No module named 'noma.utilities...'` / `No module named 'noma.handlers.rextur'` | Confirm `requirements.txt` includes `../extensions/backend/package` (local fallback) and re-run deploy. Ensure `extensions/backend/package/pyproject.toml` uses package discovery for `noma*` (not only `["noma","noma.handlers"]`). |
| Tool returns empty/fallback answer but CloudWatch shows handler error | Read the **handler_call** log entry. If it shows filesystem writes failing (e.g. `Read-only file system: 'rextur_response.json'`), patch handler debug writes to `/tmp` or make them best-effort only. |
| Browser **CORS** on API calls | Often a **symptom** of 502/error responses without CORS headers; fix Lambda first, then re-check `FE_BASE_URL` / `APP_FE_BASE_URL` if needed. |

### Deployed artifact integrity check (recommended after packaging changes)

Use this when changing `requirements*`, `pyproject.toml`, or handler package structure:

1. Check deployed Lambda timestamp:
   ```bash
   aws lambda get-function-configuration --function-name noma-noma-prod --profile noma --region us-east-1 --query "LastModified"
   ```
2. Download deployed zip from `aws lambda get-function --query "Code.Location"`.
3. Inspect zip contents and verify critical modules exist (example):
   - `noma/handlers/agent_trips.py`
   - `noma/handlers/rextur/rextur_flight_parser.py`
   - `noma/utilities/common_utils.py`
   - `renglo/...`, `pes/...`, `pes_noma/...`
4. For native deps, confirm Linux binaries are present in zip (e.g. `pydantic_core/*.so`, `cryptography/.../_rust.abi3.so`).

This avoids false confidence from local imports on Windows/macOS and catches missing modules before user tests.

---

## 9) Mandatory post-deploy org initialization

After backend deploy, perform these in order:

1. Upload tools/actions through Console.
2. Upload blueprint:

```bash
python upload_blueprints.py noma-prod --aws-profile noma --aws-region us-east-1 --blueprint noma_config
```

Notes:

- Script path: `C:/Noma/extensions/backend/installer/upload_blueprints.py`.
- Environment name maps to DynamoDB `{env}_blueprints` (example: `noma-prod` → `noma-prod_blueprints`).
- Production frontend for backend CORS/env: `https://app.travelwithnoma.com`.
- **Console production API base** (`C:/Noma/console/.env.production`): `https://u8za3vvgbb.execute-api.us-east-1.amazonaws.com/noma_prod` — `VITE_API_URL` must match for deployed console builds.
- Console dev can use `VITE_API_URL=/api` with `VITE_API_PROXY_TARGET` pointing at that API base to avoid browser CORS during local dev.
- Production websocket in console `.env.production`: use the **wss** URL from API Gateway for your WebSocket ApiId (e.g. `wss://3vdnaldxj0.execute-api.us-east-1.amazonaws.com/production` — no trailing slash for NOMA). Align with Lambda `WEBSOCKET_CONNECTIONS` in `zappa_settings.json` if realtime breaks.
- AWS profile/region for CLI: `noma` / `us-east-1`.

3. Update config for new environment variables if needed (backend and/or blueprint).
4. Upload/publish updated config through Console.

---

## 10) End-to-end validation checklist

With a fresh user:

1. User can authenticate.
2. First-login flow prompts for portfolio/org creation when expected.
3. Portfolio/org are created successfully.
4. Tools/actions are present in org.
5. Console loads org tree without CORS/auth errors.
6. NOMA chat/API requests resolve portfolio/org context correctly.
7. Send a chat message and verify websocket streaming appears.
8. Execute at least one tool-heavy action (e.g. flight search) and confirm cards/UI payload render (not only assistant text fallback).
9. If a tool says "no results", confirm in CloudWatch whether tool output was truly empty vs handler error.

---

## 11) Recovery notes

- If frontend deploy does not trigger from webhook, use `start-job` manually with `--profile noma`.
- If the browser shows **CORS** errors after backend deploy, first confirm the API is not returning **502** (Lambda import/runtime failure); then re-check `FE_BASE_URL` / `APP_FE_BASE_URL` and redeploy backend if needed.
- If testing local frontend against deployed backend, temporarily enable `ALLOW_DEV_ORIGINS` and redeploy backend.
- If onboarding data looks stale after resets, refresh tree cache and rerun the post-deploy setup sequence.
- If chat connects but no answer arrives, inspect `/_chat/message` path in CloudWatch and confirm the handler in `core` executed successfully (not blocked by import/runtime errors).
- If plan/action executes but UI receives fallback text instead of cards, inspect the tool `handler_call` log result first; many "no results" responses are downstream of tool exceptions.

---

## Optional: pip-compile vs this workflow

| pip-compile | This repo’s approach |
|-------------|----------------------|
| Extra tool (`pip-tools`) | `pip` + `pip freeze` + wheelhouse only |
| Resolves dependencies each time | Uses **frozen** dev state |
| Lockfile with hashes | Exact wheels from freeze + local builds |

For day-to-day deploys, follow **§7** and **§8** above.
