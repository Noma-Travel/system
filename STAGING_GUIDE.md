# Staging Environment — Branch Policy and Setup

This document describes the **`staging` branch** strategy across the NOMA stack. Staging branches were created to mirror production (`main`) while allowing integration and UAT before production releases.

---

## Repositories with `staging` branch

| Repository | GitHub | Purpose |
|------------|--------|---------|
| `renglo-lib` | [Noma-Travel/renglo-lib](https://github.com/Noma-Travel/renglo-lib) | Lambda dependency (`@staging`) |
| `renglo-api` | [Noma-Travel/renglo-api](https://github.com/Noma-Travel/renglo-api) | Lambda dependency (`@staging`) |
| `system` | [Noma-Travel/system](https://github.com/Noma-Travel/system) | Zappa deploy orchestrator |
| `console` | [Noma-Travel/console](https://github.com/Noma-Travel/console) | Admin console frontend |
| `backend` | [Noma-Travel/backend](https://github.com/Noma-Travel/backend) | Handlers package (`@staging`) |
| `NOMA` | [Noma-Travel/Noma](https://github.com/Noma-Travel/Noma) | App frontend (Amplify `staging`) |
| `pes_noma` | [Noma-Travel/pes_noma](https://github.com/Noma-Travel/pes_noma) | Lambda dependency (`@staging`) |
| `wss` | [Noma-Travel/wss](https://github.com/Noma-Travel/wss) | WebSocket service |
| `schd` | [Noma-Travel/schd](https://github.com/Noma-Travel/schd) | Scheduler extension (`@staging`) |

**Initial state:** Each `staging` branch was created from the current `main` tip (same commit SHA). They will diverge as work lands on `staging` first.

---

## Branch workflow

```
feature/*  ──PR──►  staging  ──UAT/E2E──►  main
                      │                      │
                      ▼                      ▼
               staging deploy           production deploy
```

| Branch | Deploys to | Typical use |
|--------|------------|-------------|
| `staging` | Staging stack (`noma_staging`, staging Amplify URL, etc.) | Integration, UAT, E2E |
| `main` | Production (`noma_prod`, production Amplify URL) | Release after staging validation |

### Day-to-day

1. Open PRs targeting **`staging`** (not `main`) for new features.
2. After merge, staging CI/CD deploys automatically (once workflows from Step 3+ are in place).
3. Run UAT/E2E against staging URLs.
4. Promote to production by merging **`staging` → `main`** across affected repos (coordinated release).

### Keeping branches aligned

- Periodically merge `main` → `staging` if hotfixes land on production first.
- Before a production release, ensure `staging` has been validated and is ready to merge into `main`.

---

## Local checkout

```bash
git fetch origin
git checkout staging
git pull origin staging
```

---

## Branch protection (recommended — configure in GitHub)

Branch protection cannot be fully automated without org admin rights. Configure in **GitHub → Repository → Settings → Branches** for each repo above.

### `staging`

- Require a pull request before merging
- 1 approving review (optional for fast iteration teams)
- Do not allow force pushes
- Allow administrators to bypass (optional during bootstrap)

### `main`

- Require a pull request before merging
- 1–2 approving reviews
- Require branches to be up to date
- Do not allow force pushes
- Restrict who can push (release managers only, optional)

### NOMA-specific (after Step 1 CI)

On `develop` / `staging` / `main`, optionally require status checks:

- `build`
- `e2e-smoke`

---

## Deploy triggers (configured)

Pushes to `staging` or `main` in dependency repos dispatch deploys to the **system** repo.

| Source repo | `staging` push | `main` push |
|-------------|----------------|-------------|
| `backend` | `backend-staging-updated` → `deploy-staging.yml` | `backend-main-updated` → `deploy.yml` |
| `renglo-lib` | `renglo-lib-staging-updated` | `renglo-lib-main-updated` |
| `renglo-api` | `renglo-api-staging-updated` | `renglo-api-main-updated` |
| `pes_noma` | `pes-noma-staging-updated` | `pes-noma-main-updated` |
| `schd` | `schd-staging-updated` | `schd-main-updated` |
| `system` | direct `deploy-staging.yml` | direct `deploy.yml` |

- Staging installs from [`requirements.ci.staging.txt`](requirements.ci.staging.txt) (`@staging` git refs).
- Production installs from [`requirements.ci.txt`](requirements.ci.txt) (`@main` git refs).
- Concurrency groups `deploy-staging` and `deploy-production` queue overlapping runs.

### Required GitHub secrets

**`system` repo:** existing `AWS_*`, `GH_PAT`, `ZAPPA_SETTINGS` plus **`ZAPPA_SETTINGS_STAGING`** (staging Lambda config with `noma_staging` stage).

**Post-deploy org sync (step 7c — end of rollout):**

| Secret | Purpose |
|--------|---------|
| `DEPLOY_SYNC_ORGS` | Prod org(s) for `post_deploy` after `deploy.yml` |
| `STAGING_SYNC_ORGS` | Staging org(s) after seeding a test tenant in staging |

Format: `[{"portfolio":"<id>","org":"<id>"}]` — see [`DEPLOYMENT_GUIDE.md`](DEPLOYMENT_GUIDE.md) §9a.

**Each triggering repo** (`backend`, `renglo-lib`, `renglo-api`, `pes_noma`, `schd`): **`SYSTEM_REPO_PAT`** — fine-grained PAT with `contents:read` and permission to dispatch workflows on `Noma-Travel/system`.

## Infrastructure (provisioned 2026-06-08)

Launcher (`deploy_environment.py noma-staging`) created:

| Resource | Value |
|----------|-------|
| DynamoDB tables | `noma-staging_blueprints`, `_entities`, `_rel`, `_chat`, `_data` |
| Cognito User Pool | `us-east-1_vBbXLDESt` |
| Cognito App Client | `6rcfm5lsscs5ocnlu4ftukdbjr` |
| IAM role | `arn:aws:iam::158711196499:role/noma-staging_tt_role` |
| S3 bucket | `noma-staging-42067270` |
| System blueprints | 4 uploaded to `noma-staging_blueprints` |

**Still pending:** Zappa stage `noma_staging` (first deploy), `API_GATEWAY_ARN`, Amplify `staging` branch config, WebSocket staging URL.

See also [`DEPLOYMENT_GUIDE.md`](DEPLOYMENT_GUIDE.md) for production deploy flow.

---

## Verify staging branches exist

```bash
for repo in renglo-lib renglo-api system console backend Noma pes_noma wss schd; do
  echo -n "$repo: "
  git ls-remote --heads "https://github.com/Noma-Travel/${repo}.git" staging
done
```

---

## `ZAPPA_SETTINGS_STAGING` secret (Step 7b — do now)

**When:** After launcher (done) and before first staging deploy test. Template file: **`zappa_settings_staging.json`** (gitignored, filled locally).

**Action:** Copy the entire JSON from `zappa_settings_staging.json` into GitHub secret **`ZAPPA_SETTINGS_STAGING`** on `Noma-Travel/system` (Settings → Secrets and variables → Actions → New repository secret).

**Still empty until first deploy:**

| Field | Fill when |
|-------|-----------|
| `API_GATEWAY_ARN` | After first `deploy-staging.yml` run creates the staging API Gateway |
| `BASE_URL` / `DOC_BASE_URL` | Same — staging API URL from Zappa output |
| `WEBSOCKET_CONNECTIONS` | When `wss` staging is deployed (Step 8) |

Update `FE_BASE_URL` / `CORS_ALLOWED_ORIGINS` if your NOMA Amplify staging URL differs from `staging.d1uvu3pkmkr1l6.amplifyapp.com`.

## Minimum deploy triggers (system + backend)

Your required behavior is already configured:

| Commit to | Repo | What runs |
|-----------|------|-----------|
| `main` | **system** | `deploy.yml` → `noma_prod` |
| `staging` | **system** | `deploy-staging.yml` → `noma_staging` |
| `main` | **backend** | `deploy-trigger.yml` → dispatches **system** `deploy.yml` |
| `staging` | **backend** | `deploy-trigger-staging.yml` → dispatches **system** `deploy-staging.yml` |

Pushes to `main`/`staging` in **renglo-lib**, **renglo-api**, **pes_noma**, and **schd** also trigger the same system deploys (optional extra triggers). Concurrency groups prevent overlapping production or staging deploys from running at once.

```mermaid
sequenceDiagram
    participant Backend as backend repo
    participant System as system repo
    participant Lambda as AWS Lambda

    Note over Backend,Lambda: Production
    Backend->>System: push main OR repository_dispatch
    System->>Lambda: deploy.yml → noma_prod

    Note over Backend,Lambda: Staging
    Backend->>System: push staging OR repository_dispatch
    System->>Lambda: deploy-staging.yml → noma_staging
```

## Changelog

| Date | Action |
|------|--------|
| 2026-06-08 | Created `staging` branch on all 9 stack repos from `main` |
| 2026-06-08 | Added `deploy-staging.yml`, `requirements.ci.staging.txt`, and cross-repo dispatch triggers |
| 2026-06-08 | Added `zappa_settings_staging.json` template for `ZAPPA_SETTINGS_STAGING` secret |
| 2026-06-08 | Ran launcher `noma-staging`; DynamoDB, Cognito, IAM, S3, blueprints provisioned |
