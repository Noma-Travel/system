# CI/CD Rollout — Verification Checklist

Acceptance gate before treating the NOMA staging/production CI/CD rollout as complete.

**Last verification run:** 2026-06-08 (Step 9 re-run)

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
| A1 | Push no-op commit to `backend/main` (no `system/main` change) | `Deploy Backend` runs; Lambda `noma-noma-prod` updates | **FAIL** | [Run 27160446253](https://github.com/Noma-Travel/backend/actions/runs/27160446253) — `Resource not accessible by personal access token`. Same root cause as B1: PAT needs **Contents: Read and write** on `Noma-Travel/system`. |
| A2 | Push no-op commit to `system/main` | Same deploy workflow runs; no duplicate failure | **PASS** | [Run 27160068589](https://github.com/Noma-Travel/system/actions/runs/27160068589) — deploy + post_deploy green (direct push, no dispatch). |
| A3 | Push to `renglo-lib/main` (or renglo-api / pes_noma / schd) | `repository_dispatch` triggers prod deploy | **FAIL** | Same PAT permission issue as A1/B1 (all trigger workflows use `repository_dispatch`). |
| A4 | Simultaneous push to `backend/main` + `system/main` | Concurrency group queues; one deploy completes | **PENDING** | Blocked until A1 passes. |

### Secrets setup — `SYSTEM_REPO_PAT`

Fine-grained PAT on **`Noma-Travel/system`** (resource owner: Noma-Travel, all repositories or include `system`):

| Permission | Level | Required for |
|------------|-------|--------------|
| **Metadata** | Read | API access (auto-selected with Contents) |
| **Contents** | **Read and write** | **`repository_dispatch`** (this is the critical one) |
| Actions | Read and write | Optional — **not** sufficient alone for dispatch |

Add as secret `SYSTEM_REPO_PAT` on: `backend`, `renglo-lib`, `renglo-api`, `pes_noma`, `schd`.

**Common mistake:** Actions: Read and write ✓ but Contents: Read-only ✗ → dispatch fails with *Resource not accessible by personal access token* ([peter-evans/repository-dispatch](https://github.com/peter-evans/repository-dispatch#token) docs).

After changing PAT permissions: click **Update** on the token, **re-paste** into every repo's `SYSTEM_REPO_PAT` secret, then re-test B1.

**SSO note:** Fine-grained PATs have no "Configure SSO" button — org access is granted at token creation. SSO authorization applies only to **classic** PATs.

---

## B. Deploy triggers — staging

| # | Test | Expected | Status | Notes |
|---|------|----------|--------|-------|
| B1 | Push to `backend/staging` only | `Deploy Backend (Staging)` runs; `noma-noma-staging` updates | **FAIL** | [Run 27161730613](https://github.com/Noma-Travel/backend/actions/runs/27161730613) (2026-06-08 re-test) — still `Resource not accessible by personal access token`. Upgrade PAT **Contents** to **Read and write**, update secrets, re-push. |
| B2 | Push to `system/staging` | Staging deploy uses `requirements.ci.staging.txt` (`@staging` refs) | **PASS** | [Run 27161056784](https://github.com/Noma-Travel/system/actions/runs/27161056784) — deploy + post_deploy green. |
| B3 | `staging` branch exists in all 9 repos | Branches present | **PASS** | Verified 2026-06-08 via GitHub API. |
| B3b | Branch protection on `staging` / `main` | Rules configured per [`STAGING_GUIDE.md`](STAGING_GUIDE.md) | **PENDING** | Manual — GitHub Settings → Branches. |

---

## C. Post-deploy blueprint and tool sync

| # | Test | Expected | Status | Notes |
|---|------|----------|--------|-------|
| C1 | Successful staging deploy completes `post_deploy` | Workflow green; blueprints uploaded | **PASS** | [Run 27161056784](https://github.com/Noma-Travel/system/actions/runs/27161056784) job `post_deploy`. |
| C2 | Query `noma-staging_blueprints` for `noma_config` IRN | Blueprint exists | **PASS** | DynamoDB scan found 1 `noma_config` record (2026-06-08). |
| C3 | Tool/action counts in DynamoDB match on-disk JSON for sync orgs | Expected counts (see post_deploy log) | **SKIP** | 0 orgs in staging DynamoDB — tools sync skipped by design until first signup. |
| C4 | Intentional blueprint failure (test env) | `post_deploy` fails; workflow marked failed | **PENDING** | Optional — do not run on prod. |
| C5 | Repeat C1–C4 against production | Same behavior on `noma-prod_*` tables | **PASS** | [Run 27160068589](https://github.com/Noma-Travel/system/actions/runs/27160068589) — prod deploy + post_deploy green. |

---

## D. Failure notifications

| # | Test | Expected | Status | Notes |
|---|------|----------|--------|-------|
| D1 | Intentionally fail Zappa step in staging | Commit author receives email with run link | **PENDING** | |
| D2 | Same failed run | Team Slack channel receives alert | **PENDING** | |
| D3 | Fail a PR-merge deploy | PR author emailed (not only merge committer) | **PENDING** | |
| D4 | Fail with `noreply.github.com` author | Slack still fires; fallback map or warning logged | **PENDING** | |

**Note:** Staging failure notifications use [`notify-staging-deploy-failure.yml`](.github/workflows/notify-staging-deploy-failure.yml) via `workflow_run`.

---

## E. Cypress and frontend CI

| # | Test | Expected | Status | Notes |
|---|------|----------|--------|-------|
| E1 | Amplify build on `NOMA/staging` | `test:component` + `test:e2e:nonchat` pass | **PENDING** | Check Amplify Console → staging branch builds. |
| E2 | GitHub Actions `e2e.yml` on push/PR to `staging` | `build` + `e2e-smoke` pass | **FAIL** | [Run 27160536753](https://github.com/Noma-Travel/Noma/actions/runs/27160536753) — `build` passed; `e2e-smoke` failed: artifact `next-build` not found. Fix: add workflow `permissions` (committed locally). Re-test after push. |
| E3 | Deployed `.next` artifact has no Cypress binary | Runtime bundle unchanged | **PENDING** | Cypress is devDependency only. |

**Pre-check (NOMA repo secrets):** `NEXT_PUBLIC_*`, `CYPRESS_LOGIN_EMAIL`, `CYPRESS_LOGIN_PASSWORD`.

---

## F. Staging environment parity

| # | Test | Expected | Status | Notes |
|---|------|----------|--------|-------|
| F1 | `GET {staging-api}/ping` | 200, `{"pong":true}` | **PASS** | Verified 2026-06-08. |
| F2 | NOMA staging app loads; login with test user | Cognito auth against staging pool | **PENDING** | Staging Cognito pool is empty (0 users). Create user manually — see **Staging login bootstrap** below. |
| F3 | Console local against staging API | API calls hit staging Gateway, not prod | **PENDING** | [`console/.env.staging-local.TEMPLATE`](../console/.env.staging-local.TEMPLATE) |
| F4 | WebSocket from NOMA staging | Handshake succeeds | **PENDING** | Manual — after F2 login. |
| F5 | Staging DynamoDB / Cognito / S3 isolated from prod | No prod table names in Lambda env | **PASS** | Lambda uses `noma-staging_*` tables, pool `us-east-1_vBbXLDESt` (per `ZAPPA_SETTINGS_STAGING`). |

---

## G. Application smoke tests (staging)

| # | Test | Command / tool | Expected | Status | Notes |
|---|------|----------------|----------|--------|-------|
| G1 | Roles/permissions smoke | [`smoke_roles.sh`](../extensions/backend/scripts/smoke_roles.sh) | Read-only checks pass | **PENDING** | Blocked on F2 (staging tokens). |
| G2 | NOMA non-chat E2E | `npm run test:e2e:nonchat` | Specs green | **PENDING** | Or Amplify test phase (E1). |
| G3 | New org onboarding (optional) | Create test org on staging | Tools install via onboarding | **PENDING** | |
| G4 | Chat/agent path (manual) | Send test message in staging | Agent responds | **PENDING** | CloudWatch: `/aws/lambda/noma-noma-staging` |

---

## H. Production sanity (after staging sign-off)

| # | Test | Expected | Status | Notes |
|---|------|----------|--------|-------|
| H1 | Promote `staging` → `main` in one repo | Prod workflow runs; post_deploy succeeds | **PENDING** | Direct `system/main` deploy already verified (A2/C5). |
| H2 | `GET {prod-api}/ping` + spot-check `/auth/user` | 200; no regression | **PENDING** | |
| H3 | Prod deploy uses `@main` refs | CI logs show `requirements.ci.txt` | **PASS** | Prod deploy jobs use `requirements.ci.txt` per [`deploy.yml`](.github/workflows/deploy.yml). |

---

## Staging login bootstrap

Staging uses a **fresh Cognito pool** (`us-east-1_vBbXLDESt`). Production users are **not** copied automatically.

| Symptom | Cause |
|---------|--------|
| "Credenciais inválidas" with prod email/password | User does not exist in staging Cognito yet |

Create your user manually (Cognito console, AWS CLI, or self-serve signup with `NEXT_PUBLIC_SIGNUP_POLICY=open_self_serve` on Amplify staging branch).

**Amplify check:** Staging branch overrides must include `NEXT_PUBLIC_AWS_USER_POOL_ID=us-east-1_vBbXLDESt` and `NEXT_PUBLIC_AWS_USER_POOL_CLIENT_ID=6rcfm5lsscs5ocnlu4ftukdbjr`.

After first login, complete onboarding (new org/portfolio in staging DynamoDB) — expected on a fresh environment.

---

## Sign-off criteria

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

# Re-test B1 after fixing PAT (Contents: Read and write + update secrets)
git commit --allow-empty -m "ci: re-test staging deploy trigger" && git push origin staging

# Watch results
gh run list --repo Noma-Travel/backend --workflow "Trigger Staging Deploy" --limit 3
gh run list --repo Noma-Travel/system --workflow "Deploy Backend (Staging)" --limit 3
```

---

## Verification log

| Date | Verifier | Action | Result |
|------|----------|--------|--------|
| 2026-06-08 | Agent | Initial audit | Partial — B1, E2 |
| 2026-06-08 | Agent | Fix deploy-trigger JSON + e2e job id | Committed |
| 2026-06-08 | Agent | **Step 9 re-run** | A1/A3/B1 still FAIL — PAT needs **Contents: Read and write** (not Actions alone). B2/C/F1/F5/H3 PASS. E2 FAIL (artifact permissions). F2 pending user bootstrap. |
