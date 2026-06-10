# NOMA CI/CD — End-to-End Flow

Reference diagram for developers: how code moves from Git branches to staging/production, and where tests and notifications run.

**Related docs:** [`STAGING_GUIDE.md`](STAGING_GUIDE.md) · [`DEPLOYMENT_GUIDE.md`](DEPLOYMENT_GUIDE.md) · [`NOMA/cypress/DEPLOY_CI.md`](../NOMA/cypress/DEPLOY_CI.md)

---

## Branch model

```mermaid
flowchart LR
  subgraph dev["Development"]
    FEAT["feature/* branches"]
  end
  subgraph integration["Integration / UAT"]
    STG["staging branch\n(9 stack repos)"]
  end
  subgraph release["Production"]
    MAIN["main branch"]
  end

  FEAT -->|"PR merge"| STG
  STG -->|"UAT + E2E green"| MAIN
  STG -->|"auto deploy"| STG_ENV["Staging AWS + Amplify"]
  MAIN -->|"auto deploy"| PROD_ENV["Production AWS + Amplify"]
```

| Branch | Backend Lambda | Frontend | pip/git refs |
|--------|----------------|----------|--------------|
| `staging` | `noma-noma-staging` | Amplify branch `staging` | `requirements.ci.staging.txt` → `@staging` |
| `main` | `noma-noma-prod` | Amplify branch `main` | `requirements.ci.txt` → `@main` |

---

## Full pipeline (all repos)

```mermaid
flowchart TB
  subgraph repos["GitHub repos (9-stack)"]
    R1["backend"]
    R2["system"]
    R3["renglo-lib / renglo-api"]
    R4["pes_noma / schd"]
    R5["NOMA (frontend)"]
  end

  subgraph triggers["What triggers a backend deploy"]
    T1["push to system/staging or system/main"]
    T2["push to backend/staging or backend/main"]
    T3["repository_dispatch from dependency repos"]
  end

  subgraph system_ci["Noma-Travel/system — GitHub Actions"]
    DS["deploy-staging.yml\n(or deploy.yml for prod)"]
    REUSE["deploy-backend-reusable.yml"]
    ZAPPA["zappa_update.sh → Lambda update"]
    PD["post-deploy-reusable.yml"]
    SYNC["Blueprints upload +\norg discovery +\ntool/action sync"]
    NOTIFY["notify-*-deploy-failure.yml\n(email + Slack #deployments)"]
  end

  subgraph aws_staging["AWS staging"]
    L_STG["Lambda noma-noma-staging"]
    API_STG["REST API …/noma_staging"]
    WS_STG["WebSocket 1qefn6vt95"]
    DDB_STG["DynamoDB noma-staging_*"]
    AMP_STG["Amplify staging.d1f1y2ixvuy9lc…"]
  end

  subgraph aws_prod["AWS production"]
    L_PROD["Lambda noma-noma-prod"]
    API_PROD["REST API …/noma_prod"]
    WS_PROD["WebSocket 3vdnaldxj0"]
    DDB_PROD["DynamoDB noma-prod_*"]
    AMP_PROD["Amplify app.travelwithnoma.com"]
  end

  subgraph frontend_ci["Noma-Travel/Noma — GitHub Actions + Amplify"]
    GHA["e2e.yml: build + e2e-smoke"]
    AMP_BUILD["amplify.yml BUILD phase:\nnpm ci --include=dev → build →\ntest:component + test:e2e:nonchat"]
  end

  R2 --> T1
  R1 --> T2
  R3 --> T3
  R4 --> T3

  T1 --> DS
  T2 --> DS
  T3 --> DS

  DS --> REUSE --> ZAPPA
  ZAPPA --> L_STG
  ZAPPA --> L_PROD
  REUSE --> PD --> SYNC
  SYNC --> DDB_STG
  SYNC --> DDB_PROD
  DS -.->|"on failure"| NOTIFY

  R5 -->|"push staging/main"| AMP_BUILD
  R5 -->|"PR / push"| GHA
  AMP_BUILD --> AMP_STG
  AMP_BUILD --> AMP_PROD

  AMP_STG --> API_STG
  AMP_STG --> WS_STG
  AMP_PROD --> API_PROD
  AMP_PROD --> WS_PROD
  L_STG --> API_STG
  L_PROD --> API_PROD
```

---

## Backend deploy sequence (staging example)

```mermaid
sequenceDiagram
  participant Dev as Developer
  participant Dep as backend / renglo-lib / schd …
  participant Sys as system repo
  participant GHA as GitHub Actions
  participant AWS as AWS Lambda + API GW
  participant DDB as DynamoDB

  Dev->>Dep: merge PR to staging
  Dep->>Sys: repository_dispatch<br/>(SYSTEM_REPO_PAT)
  Sys->>GHA: deploy-staging.yml
  GHA->>GHA: pip install requirements.ci.staging.txt (@staging refs)
  GHA->>AWS: zappa_update.sh noma_staging update
  GHA->>GHA: post_deploy job
  GHA->>DDB: upload all blueprints
  GHA->>DDB: discover orgs → sync schd_tools / schd_actions
  alt deploy fails
    GHA->>Dev: Resend email to commit author
    GHA->>Dev: Slack #deployments
  end
```

**Concurrency:** `deploy-staging` and `deploy-production` groups queue overlapping runs (one completes at a time).

**Dependency repos** that dispatch to `system` on push to `staging`/`main`:

- `backend`, `renglo-lib`, `renglo-api`, `pes_noma`, `schd`

Each uses `deploy-trigger-staging.yml` or `deploy-trigger.yml` with secret `SYSTEM_REPO_PAT` (fine-grained PAT: **Contents read+write** on `Noma-Travel/system`).

---

## Frontend deploy & test gates

```mermaid
flowchart TB
  subgraph pr_gate["PR / push gate (GitHub only — no deploy)"]
    B1["job: build\nnpm ci --include=dev → npm run build"]
    B2["job: e2e-smoke\nreuse .next artifact\ntest:e2e:smoke"]
    B1 --> B2
  end

  subgraph amp_gate["Deploy gate (Amplify — WEB_COMPUTE)"]
    A1["preBuild: npm ci --include=dev + cypress verify"]
    A2["build: npm run build"]
    A3["start + wait-on /login"]
    A4["test:component"]
    A5["test:e2e:nonchat"]
    A6["artifact: .next/** only\n(no Cypress in runtime bundle)"]
    A1 --> A2 --> A3 --> A4 --> A5 --> A6
  end

  PR["NOMA PR / push staging|main"] --> pr_gate
  MERGE["Merge to staging/main"] --> amp_gate
  A6 --> LIVE["Amplify SSR deploy"]
```

| Suite | Runs in Amplify BUILD | Runs in GitHub e2e.yml | Manual |
|-------|----------------------|------------------------|--------|
| Component tests | Yes | No | `npm run test:component` |
| Non-chat E2E | Yes | No | `npm run test:e2e:nonchat` |
| Smoke E2E | No | Yes | `npm run test:e2e:smoke` |
| Chat / agent E2E | No | No | `npm run test:e2e:chat` (LLM-dependent) |

---

## Production promotion

```mermaid
flowchart LR
  STG_OK["Staging sign-off\n(UAT + E2E green)"]
  MERGE["Merge staging → main\n(coordinated across affected repos)"]
  PROD_DEPLOY["system deploy.yml\nrequirements.ci.txt @main"]
  PROD_POST["post_deploy on noma-prod"]
  PROD_FE["Amplify main branch build"]
  STG_OK --> MERGE --> PROD_DEPLOY --> PROD_POST
  MERGE --> PROD_FE
```

After promotion, verify prod ping (`GET …/noma_prod/ping`), a quick spot-check on the prod app, and `requirements.ci.txt` in deploy logs.

---

## Environment map (quick reference)

| | Staging | Production |
|---|---------|------------|
| REST API | `https://2r4dlx8qdj.execute-api.us-east-1.amazonaws.com/noma_staging` | `https://u8za3vvgbb.execute-api.us-east-1.amazonaws.com/noma_prod` |
| WebSocket | `wss://1qefn6vt95.execute-api.us-east-1.amazonaws.com/production` | `wss://3vdnaldxj0.execute-api.us-east-1.amazonaws.com/production` |
| NOMA URL | `https://staging.d1f1y2ixvuy9lc.amplifyapp.com` | `https://app.travelwithnoma.com` |
| Lambda | `noma-noma-staging` | `noma-noma-prod` |
| DynamoDB prefix | `noma-staging_*` | `noma-prod_*` |
| Cognito pool | `us-east-1_vBbXLDESt` | (prod pool — see Zappa settings) |

---

## Secrets checklist (operators)

| Secret | Where | Purpose |
|--------|-------|---------|
| `SYSTEM_REPO_PAT` | backend, renglo-*, pes_noma, schd | Cross-repo `repository_dispatch` |
| `ZAPPA_SETTINGS` / `ZAPPA_SETTINGS_STAGING` | system | Lambda env + Zappa config JSON |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | system | Deploy + post_deploy |
| `GH_PAT` | system | Checkout private repos in CI |
| `RESEND_API_KEY` / `SLACK_DEPLOY_WEBHOOK_URL` | system | Failure notifications |
| `CYPRESS_*` / `NEXT_PUBLIC_*` | NOMA (GitHub + Amplify) | E2E and build-time env |

---

## Troubleshooting pointers

| Symptom | Likely cause | Doc / fix |
|---------|--------------|-----------|
| Amplify BUILD fails on Cypress | devDeps skipped or WEB_COMPUTE ignores `test:` phase | [`NOMA/amplify.yml`](../NOMA/amplify.yml) — tests in **build** phase |
| Chat WebSocket HTTP 500 on connect | Missing `$connect` route/integration responses on MOCK API | `system/scripts/fix_staging_ws_connect.py` or launcher `create_websocket_api.py` |
| `Failed to fetch` after staging login | CORS / `FE_BASE_URL` mismatch or prod org IDs on Amplify **All branches** | [`STAGING_GUIDE.md`](STAGING_GUIDE.md) Step 8 |
| post_deploy finds 0 orgs | No orgs in staging DynamoDB yet | Complete onboarding on staging NOMA first |
| Deploy notify workflow 0s / skipped | Invalid `secrets.*` in workflow `if:` | Fixed in `notify-deploy-failure.yml` (2026-06-09) |
