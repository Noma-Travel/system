# NOMA Full Deployment Guide (Frontend + Backend + Post-Deploy Setup)

This guide defines the production-safe deployment flow for the NOMA stack and how to switch between local and deployed contexts during testing.

## 1) Deployment Sequence

Use this sequence:

1. Confirm production frontend domain is unchanged (`https://app.travelwithnoma.com`).
2. Confirm backend allowed frontend origin values include that domain.
3. Deploy backend (`zappa update`) with current production env.
4. Run post-deploy org initialization (tools/actions, blueprint, config publish).

## 2) Repositories Included In Backend Deploy

Backend deployment installs from **Noma-Travel** only ([`requirements-noma-travel.txt`](requirements-noma-travel.txt)), referenced by [`requirements.txt`](requirements.txt). For a full local workspace layout without git installs, use [`requirements-local.txt`](requirements-local.txt) instead.

- `https://github.com/Noma-Travel/renglo-lib.git`
- `https://github.com/Noma-Travel/renglo-api.git`
- `https://github.com/Noma-Travel/noma-handlers.git` (handlers package; path `extensions/noma/package` in local trees)
- `https://github.com/Noma-Travel/pes.git`
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

After mirrors exist, `pip install -r requirements.txt` in `system` resolves packages from Noma-Travel. Until then, use `pip install -r requirements-local.txt` before `./zappa_update.sh`.

## 3) Environment Variables That Control Context

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

### Backend (renglo-api/system)

Loaded from `zappa_settings.json` env vars in Lambda and/or env config files (`env.development`, `env.production`):

- `FE_BASE_URL`
- `APP_FE_BASE_URL`
- `ALLOW_DEV_ORIGINS`
- `COGNITO_REGION`
- `COGNITO_USERPOOL_ID`
- `COGNITO_APP_CLIENT_ID`
- `WEBSOCKET_CONNECTIONS`
- `DYNAMODB_*` tables, `S3_BUCKET_NAME`, etc.

CORS/allowed access in backend:

- In Lambda, allowed origins are built from `FE_BASE_URL` + `APP_FE_BASE_URL`.
- Optional local origins are added only when `ALLOW_DEV_ORIGINS=true`.

## 4) Context Matrix (What To Change For Each Scenario)

### A) Local frontend + Local backend

- NOMA/Console frontend:
  - set API URL to local backend (`http://127.0.0.1:5001` or local API port).
- Backend:
  - run locally with `env.development`.
- Keep local testing origins enabled only in local mode.

### B) Local frontend + Deployed backend

- Frontend (`NOMA` or `console`):
  - set API URL to deployed API (`https://...execute-api.../noma_prod` or custom domain).
  - set websocket URL to deployed websocket.
- Backend (`noma_prod`):
  - `ALLOW_DEV_ORIGINS=true` temporarily, or your local origin will be blocked by CORS.
  - keep this temporary and revert for production-hardening.

### C) Deployed frontend + Deployed backend (production path)

- Frontend:
  - deploy and confirm final public URL.
- Backend:
  - set `FE_BASE_URL` and `APP_FE_BASE_URL` to deployed frontend URL(s).
  - set `ALLOW_DEV_ORIGINS=false` unless explicitly required.
  - deploy with `zappa update`.

## 5) How To Switch Context Safely

1. Choose target mode (A/B/C above).
2. Update frontend env file values (`NOMA` and/or `console`).
3. Update backend env values (`zappa_settings.json` and/or `env.production`/`env.development` as applicable).
4. Restart frontend dev servers.
5. If backend env changed for Lambda, run backend deploy.
6. Validate active context:
   - browser network requests hit expected API host.
   - websocket connects to expected URL.
   - backend CORS accepts expected frontend origin.

Never mix accounts/profiles while switching context. Use `--profile noma` and `us-east-1` consistently unless intentionally targeting another account/region.

## 6) Frontend Deployment (When Needed)

1. Deploy NOMA frontend to Amplify (`main` branch).
2. Confirm a new deployment job appears and succeeds.
3. Confirm deployed domain is `https://app.travelwithnoma.com`.
4. If webhook is green but no deployment job appears, trigger release manually:

```bash
aws amplify start-job --region us-east-1 --app-id d1f1y2ixvuy9lc --branch-name main --job-type RELEASE --profile noma
```

## 7) Backend Deployment (Second)

Before deploying backend, confirm:

- `FE_BASE_URL` and `APP_FE_BASE_URL` are both `https://app.travelwithnoma.com`.
- `ALLOW_DEV_ORIGINS` has the intended value for the target environment.

Deploy from `C:/Noma/system`:

```bash
# activate venv first, then:
./zappa_update.sh noma_prod update
```

Post-deploy checks:

- `zappa tail noma_prod`
- API health endpoint (`/ping`) responds.
- No repeated `500` errors on key auth routes (`/_auth/tree`, `/_auth/user`, `/_auth/portfolios`).

## 8) Mandatory Post-Deploy Org Initialization

After backend deploy, perform these in order:

1. Upload tools/actions through Console.
2. Upload blueprint:

```bash
python upload_blueprints.py noma-prod --aws-profile noma --aws-region us-east-1 --blueprint noma_config
```

Notes:

- Script location is `C:/Noma/extensions/noma/installer/upload_blueprints.py`.
- Environment name maps to DynamoDB table `{env}_blueprints` (example: `noma-prod` → `noma-prod_blueprints`).
- Production frontend domain used by backend CORS/env: `https://app.travelwithnoma.com`.
- **Console production API base** (checked in `C:/Noma/console/.env.production`): `https://u8za3vvgbb.execute-api.us-east-1.amazonaws.com/noma_prod` — this is what `VITE_API_URL` must use for deployed console builds.
- Console dev can use `VITE_API_URL=/api` with `VITE_API_PROXY_TARGET` pointing at that same API base to avoid browser CORS during local dev.
- Production websocket in console `.env.production`: `wss://0y1ais8791.execute-api.us-east-1.amazonaws.com/production/`. Align with Lambda `WEBSOCKET_CONNECTIONS` in `zappa_settings.json` if realtime breaks.
- AWS profile/region for deploy commands: `noma` / `us-east-1`.

3. Update config to include new environment variables if needed (backend and/or blueprint config fields).
4. Upload/publish updated config through Console.

## 9) End-to-End Validation Checklist

Use a fresh user and verify:

1. User can authenticate.
2. First-login flow prompts for portfolio/org creation when expected.
3. Portfolio/org are created successfully.
4. Tools/actions are present in org.
5. Console can load org tree without CORS/auth errors.
6. NOMA chat/API requests resolve portfolio/org context correctly.

## 10) Recovery Notes

- If frontend deploy does not trigger from webhook, use `start-job` manually with `--profile noma`.
- If browser shows CORS errors after backend deploy, re-check `FE_BASE_URL` / `APP_FE_BASE_URL` and redeploy backend.
- If testing local frontend against deployed backend, temporarily enable `ALLOW_DEV_ORIGINS` and redeploy backend.
- If onboarding data looks stale after resets, refresh tree cache path and rerun post-deploy setup sequence.
