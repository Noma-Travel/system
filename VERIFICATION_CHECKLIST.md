# CI/CD Rollout — Verification Checklist

Acceptance gate before treating the NOMA staging/production CI/CD rollout as complete.

**Environment under test:** staging (primary), production (section H after staging sign-off)

**Staging reference URLs** (see [`STAGING_GUIDE.md`](STAGING_GUIDE.md)):

| Resource | URL / ID |
|----------|----------|
| REST API | `https://2r4dlx8qdj.execute-api.us-east-1.amazonaws.com/noma_staging` |
| Ping | `GET …/noma_staging/ping` → `{"pong":true}` |
| WebSocket | `wss://1qefn6vt95.execute-api.us-east-1.amazonaws.com/production` |
| NOMA (Amplify) | `https://staging.d1uvu3pkmkr1l6.amplifyapp.com` |
| Lambda | `noma-noma-staging` |
| DynamoDB prefix | `noma-staging_*` |
| Cognito pool | `us-east-1_vBbXLDESt` |

---

## How to use this document

1. Work through sections **A → G** in order (or in parallel where independent).
2. Mark each row: **PASS** / **FAIL** / **SKIP** / **PENDING**
3. Link GitHub Actions run URLs or screenshots for failures.
4. Section **H** runs only after staging sign-off and first prod promotion test.
5. Complete **Sign-off** at the bottom.

---

## A. Deploy triggers — production

| # | Test | Expected | Status | Notes |
|---|------|----------|--------|-------|
| A1 | Push no-op commit to `backend/main` (no `system/main` change) | `Deploy Backend (Production)` runs; Lambda `noma-noma-prod` updates | PENDING | |
| A2 | Push no-op commit to `system/main` | Same deploy workflow runs; no duplicate failure | PENDING | |
| A3 | Push to `renglo-lib/main` (or renglo-api / pes_noma / schd) | `repository_dispatch` triggers prod deploy | PENDING | |
| A4 | Simultaneous push to `backend/main` + `system/main` | Concurrency group queues; one deploy completes | PENDING | |

**Pre-check:** Each triggering repo has secret `SYSTEM_REPO_PAT` with dispatch permission on `Noma-Travel/system`.

### Secrets setup — `SYSTEM_REPO_PAT`

Create a **fine-grained PAT** (or classic PAT with `repo` scope) with access to **`Noma-Travel/system`**:

| Permission | Level |
|------------|-------|
| Metadata | Read |
| Contents | Read |
| **Actions** | **Read and write** |

Add as secret `SYSTEM_REPO_PAT` on: `backend`, `renglo-lib`, `renglo-api`, `pes_noma`, `schd`.

Without **Actions: Read and write**, `repository_dispatch` fails with *Resource not accessible by personal access token*.

**Also check:** If the org uses SAML SSO, open the PAT in GitHub → **Configure SSO** → authorize **Noma-Travel**. After creating or rotating the PAT, re-paste it into `SYSTEM_REPO_PAT` on every triggering repo (updating the PAT in GitHub settings alone is not enough).

---

## Staging login bootstrap

Staging uses a **fresh Cognito pool** (`us-east-1_vBbXLDESt`). Production users are **not** copied automatically.

| Symptom | Cause |
|---------|--------|
| "Credenciais inválidas" with a prod email/password | User does not exist in staging Cognito yet |

**Option A — Admin-create your user (recommended for UAT):**

```bash
# 1. Create user (email as username)
aws cognito-idp admin-create-user \
  --user-pool-id us-east-1_vBbXLDESt \
  --username "you@travelwithnoma.com" \
  --user-attributes Name=email,Value=you@travelwithnoma.com Name=email_verified,Value=true Name=name,Value="Your Name" \
  --message-action SUPPRESS \
  --profile noma

# 2. Set a staging-only password (must be permanent before login works)
aws cognito-idp admin-set-user-password \
  --user-pool-id us-east-1_vBbXLDESt \
  --username "you@travelwithnoma.com" \
  --password "YOUR_STAGING_PASSWORD" \
  --permanent \
  --profile noma
```

**Option B — Self-serve signup:** On the Amplify **staging** branch only, set `NEXT_PUBLIC_SIGNUP_POLICY=open_self_serve`, redeploy, then use **Criar conta**. Default is `invite_only`.

**Amplify check:** Staging branch overrides must include `NEXT_PUBLIC_AWS_USER_POOL_ID=us-east-1_vBbXLDESt` and `NEXT_PUBLIC_AWS_USER_POOL_CLIENT_ID=6rcfm5lsscs5ocnlu4ftukdbjr` (not prod pool IDs).

After first login you may need to **complete onboarding** (new org/portfolio in staging DynamoDB) — expected on a fresh environment.

---

## B. Deploy triggers — staging

| # | Test | Expected | Status | Notes |
|---|------|----------|--------|-------|
| B1 | Push to `backend/staging` only | `Deploy Backend (Staging)` runs; `noma-noma-staging` updates | **FAIL → ACTION** | JSON payload fixed (`toJSON`). Remaining error: `Resource not accessible by personal access token` — update `SYSTEM_REPO_PAT` on each triggering repo (see **Secrets setup** below). |
| B2 | Push to `system/staging` | Staging deploy uses `requirements.ci.staging.txt` (`@staging` refs) | **PASS** | [Run 27160059162](https://github.com/Noma-Travel/system/actions/runs/27160059162) — deploy + post_deploy green. |
| B3 | `staging` branch exists in all 9 repos | Branches present | **PASS** | Verified 2026-06-08 via GitHub API. |
| B3b | Branch protection on `staging` / `main` | Rules configured per [`STAGING_GUIDE.md`](STAGING_GUIDE.md) | PENDING | Manual — GitHub Settings → Branches. |

---

## C. Post-deploy blueprint and tool sync

| # | Test | Expected | Status | Notes |
|---|------|----------|--------|-------|
| C1 | Successful staging deploy completes `post_deploy` | Workflow green; blueprints uploaded | **PASS** | [Run 27160059162](https://github.com/Noma-Travel/system/actions/runs/27160059162) job `post_deploy`. |
| C2 | Query `noma-staging_blueprints` for `noma_config` IRN | Blueprint exists | PENDING | AWS Console or CLI: `aws dynamodb query …` |
| C3 | Tool/action counts in DynamoDB match on-disk JSON for sync orgs | Expected counts (see post_deploy log) | PENDING | If zero orgs on staging, tools sync skipped by design. |
| C4 | Intentional blueprint failure (test env) | `post_deploy` fails; workflow marked failed | PENDING | Optional — do not run on prod. |
| C5 | Repeat C1–C4 against production | Same behavior on `noma-prod_*` tables | PENDING | After first prod deploy with post_deploy enabled. |

**Observed (staging run 27160059162):** auto-discovery path used (`--sync-all-orgs`); 21 blueprint files uploaded to `noma-staging_blueprints`.

---

## D. Failure notifications

| # | Test | Expected | Status | Notes |
|---|------|----------|--------|-------|
| D1 | Intentionally fail Zappa step in staging | Commit author receives email with run link | PENDING | Use test branch or `workflow_dispatch` if added. |
| D2 | Same failed run | Team Slack channel receives alert | PENDING | Requires `RESEND_API_KEY`, `SLACK_DEPLOY_TEAM_WEBHOOK_URL` on `system`. |
| D3 | Fail a PR-merge deploy | PR author emailed (not only merge committer) | PENDING | |
| D4 | Fail with `noreply.github.com` author | Slack still fires; fallback map or warning logged | PENDING | |

**Note:** Staging failure notifications use [`notify-staging-deploy-failure.yml`](.github/workflows/notify-staging-deploy-failure.yml) via `workflow_run` (not nested in deploy workflow).

---

## E. Cypress and frontend CI

| # | Test | Expected | Status | Notes |
|---|------|----------|--------|-------|
| E1 | Amplify build on `NOMA/staging` | `test:component` + `test:e2e:nonchat` pass | PENDING | Check Amplify Console → staging branch builds. |
| E2 | GitHub Actions `e2e.yml` on push/PR to `staging` | `build` + `e2e-smoke` pass | **PENDING** | Removed cross-repo `notify_failure` job (blocked workflow validation). Re-add via `workflow_run` after `system` repo grants reusable workflow access to `Noma`. |
| E3 | Deployed `.next` artifact has no Cypress binary | Runtime bundle unchanged | PENDING | Cypress is devDependency only; confirm in Amplify artifact. |

**Pre-check (NOMA repo secrets):** `NEXT_PUBLIC_*`, `CYPRESS_LOGIN_EMAIL`, `CYPRESS_LOGIN_PASSWORD`, plus notification secrets if using `notify_failure` job.

---

## F. Staging environment parity

| # | Test | Expected | Status | Notes |
|---|------|----------|--------|-------|
| F1 | `GET {staging-api}/ping` | 200, `{"pong":true}` | **PASS** | Verified 2026-06-08. |
| F2 | NOMA staging app loads; login with test user | Cognito auth against staging pool | PENDING | **Staging Cognito is separate from prod** — pool `us-east-1_vBbXLDESt` starts empty. Prod passwords do not work. Bootstrap a user (see **Staging login bootstrap** below). |
| F3 | Console local against staging API | API calls hit staging Gateway, not prod | PENDING | Copy [`console/.env.staging-local.TEMPLATE`](../console/.env.staging-local.TEMPLATE) → `.env.development`. |
| F4 | WebSocket from NOMA staging | Handshake succeeds | PENDING | Manual — send chat message; check Network → WS. |
| F5 | Staging DynamoDB / Cognito / S3 isolated from prod | No prod table names in Lambda env | PENDING | Compare `ZAPPA_SETTINGS_STAGING` vs prod secret. |

---

## G. Application smoke tests (staging)

| # | Test | Command / tool | Expected | Status | Notes |
|---|------|----------------|----------|--------|-------|
| G1 | Roles/permissions smoke | [`backend/scripts/smoke_roles.sh`](../extensions/backend/scripts/smoke_roles.sh) with staging `API`, `PORT`, `ORG`, tokens | All read-only checks pass | PENDING | Requires Cognito tokens from staging login. |
| G2 | NOMA non-chat E2E | `npm run test:e2e:nonchat` against staging URL | Specs green | PENDING | Or rely on Amplify test phase (E1). |
| G3 | New org onboarding (optional) | Create test org on staging | Tools install via `NomaOnboardings` | PENDING | |
| G4 | Chat/agent path (manual) | Send test message in staging | Agent responds; no import errors in CloudWatch | PENDING | Check `/aws/lambda/noma-noma-staging` logs. |

---

## H. Production sanity (after staging sign-off)

| # | Test | Expected | Status | Notes |
|---|------|----------|--------|-------|
| H1 | Promote `staging` → `main` in one repo | Prod workflow runs; post_deploy succeeds | PENDING | |
| H2 | `GET {prod-api}/ping` + spot-check `/auth/user` | 200; no regression | PENDING | |
| H3 | Prod deploy uses `@main` refs | CI logs show `requirements.ci.txt`, not `.staging` | PENDING | |

---

## Sign-off criteria

All must be true before closing the CI/CD initiative:

- [ ] Every row in sections **A–G** marked **PASS** (or **SKIP** with documented reason)
- [ ] Section **H** complete after first prod promotion
- [ ] No open P1/P2 issues from verification runs
- [ ] Team notified in Slack that CI/CD rollout is complete

### Sign-off

| Field | Value |
|-------|-------|
| Verifier | |
| Date | |
| Staging signed off | ☐ Yes |
| Production signed off | ☐ Yes |
| Notes | |

---

## Quick commands

```bash
# Staging ping
curl -s "https://2r4dlx8qdj.execute-api.us-east-1.amazonaws.com/noma_staging/ping"

# Re-trigger staging deploy (after fixing triggers)
git commit --allow-empty -m "ci: re-test staging deploy trigger" && git push origin staging

# Roles smoke (set tokens first)
export API=https://2r4dlx8qdj.execute-api.us-east-1.amazonaws.com/noma_staging
export PORT=<portfolio_id> ORG=<org_id> TRAVELER_TOKEN=... ADMIN_TOKEN=...
bash extensions/backend/scripts/smoke_roles.sh

# Watch system staging deploys
gh run list --repo Noma-Travel/system --workflow "Deploy Backend (Staging)" --limit 5
```

---

## Verification log

| Date | Verifier | Action | Result |
|------|----------|--------|--------|
| 2026-06-08 | Agent (automated) | Initial audit: staging deploy + post_deploy + ping | Partial pass — see B1, E2 |
| 2026-06-08 | Agent | Fix deploy-trigger JSON (`toJSON`) + e2e `needs['e2e-smoke']` | Committed — re-test pending |
