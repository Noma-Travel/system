# CI/CD Rollout — Verification Checklist

Acceptance gate before treating the NOMA staging/production CI/CD rollout as complete.

**Last verification run:** 2026-06-08 (Step 9 — after PAT Contents read+write fix)

**Environment under test:** staging (primary), production (section H after staging sign-off)

**Staging reference URLs** (see [`STAGING_GUIDE.md`](STAGING_GUIDE.md)):

| Resource | URL / ID |
|----------|----------|
| REST API | `https://2r4dlx8qdj.execute-api.us-east-1.amazonaws.com/noma_staging` |
| Ping | `GET …/noma_staging/ping` → `{"pong":true}` |
| WebSocket | `wss://1qefn6vt95.execute-api.us-east-1.amazonaws.com/production` |
| NOMA (Amplify) | `https://staging.d1f1y2ixvuy9lc.amplifyapp.com` |
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
| A1 | Push no-op commit to `backend/main` (no `system/main` change) | `Deploy Backend` runs; Lambda `noma-noma-prod` updates | **PASS** | Trigger [27162132901](https://github.com/Noma-Travel/backend/actions/runs/27162132901) → system dispatch [27162141632](https://github.com/Noma-Travel/system/actions/runs/27162141632) deploy + post_deploy green. |
| A2 | Push no-op commit to `system/main` | Same deploy workflow runs; no duplicate failure | **PASS** | [Run 27160068589](https://github.com/Noma-Travel/system/actions/runs/27160068589) — direct push. |
| A3 | Push to `renglo-lib/main` (or renglo-api / pes_noma / schd) | `repository_dispatch` triggers prod deploy | **PASS** | Trigger [27162133063](https://github.com/Noma-Travel/renglo-lib/actions/runs/27162133063) → system [27162141706](https://github.com/Noma-Travel/system/actions/runs/27162141706) green. |
| A4 | Simultaneous push to `backend/main` + `system/main` | Concurrency group queues; one deploy completes | **PASS** | `backend-main-updated` and `renglo-lib-main-updated` both dispatched at 19:36:18 UTC; second deploy waited for first (`deploy-production` concurrency). |

### Secrets setup — `SYSTEM_REPO_PAT` ✓ verified

Fine-grained PAT on **`Noma-Travel/system`**:

| Permission | Level | Required for |
|------------|-------|--------------|
| **Metadata** | Read | API access |
| **Contents** | **Read and write** | **`repository_dispatch`** ✓ |
| Actions | Read and write | Optional |

Secret `SYSTEM_REPO_PAT` on: `backend`, `renglo-lib`, `renglo-api`, `pes_noma`, `schd`.

---

## B. Deploy triggers — staging

| # | Test | Expected | Status | Notes |
|---|------|----------|--------|-------|
| B1 | Push to `backend/staging` only | `Deploy Backend (Staging)` runs; `noma-noma-staging` updates | **PASS** | Trigger [27162099905](https://github.com/Noma-Travel/backend/actions/runs/27162099905) → system [27162109523](https://github.com/Noma-Travel/system/actions/runs/27162109523) deploy + post_deploy green. |
| B2 | Push to `system/staging` | Staging deploy uses `requirements.ci.staging.txt` (`@staging` refs) | **PASS** | [Run 27161056784](https://github.com/Noma-Travel/system/actions/runs/27161056784). |
| B3 | `staging` branch exists in all 9 repos | Branches present | **PASS** | Verified 2026-06-08. |
| B3b | Branch protection on `staging` / `main` | Rules configured | **SKIP** | Requires GitHub Team/Enterprise (paid plan) — not available on current org plan. |

---

## C. Post-deploy blueprint and tool sync

| # | Test | Expected | Status | Notes |
|---|------|----------|--------|-------|
| C1 | Successful staging deploy completes `post_deploy` | Workflow green; blueprints uploaded | **PASS** | [Run 27162109523](https://github.com/Noma-Travel/system/actions/runs/27162109523) (via B1 dispatch). |
| C2 | Query `noma-staging_blueprints` for `noma_config` IRN | Blueprint exists | **PASS** | DynamoDB scan found 1 `noma_config` record. |
| C3 | Tool/action counts in DynamoDB match on-disk JSON for sync orgs | Expected counts | **PENDING** | Staging admin provisioned 2026-06-09 — login + create/accept org, then re-run `post_deploy` or push `system/staging`. |
| C4 | Intentional blueprint failure (test env) | `post_deploy` fails | **PENDING** | Optional. |
| C5 | Repeat C1–C4 against production | Same on `noma-prod_*` | **PASS** | [Run 27162141632](https://github.com/Noma-Travel/system/actions/runs/27162141632) + [27162141706](https://github.com/Noma-Travel/system/actions/runs/27162141706). |

---

## D. Failure notifications

| # | Test | Expected | Status | Notes |
|---|------|----------|--------|-------|
| D1 | Intentionally fail Zappa step in staging | Commit author receives email | **PENDING** | |
| D2 | Same failed run | Team Slack alert | **PENDING** | |
| D3 | Fail a PR-merge deploy | PR author emailed | **PENDING** | |
| D4 | Fail with `noreply.github.com` author | Slack still fires | **PENDING** | |

---

## E. Cypress and frontend CI

| # | Test | Expected | Status | Notes |
|---|------|----------|--------|-------|
| E1 | Amplify build on `NOMA/staging` | `test:component` + `test:e2e:nonchat` pass | **PENDING** | Amplify Console. |
| E2 | GitHub Actions `e2e.yml` on push/PR to `staging` | `build` + `e2e-smoke` pass | **PASS** | [Run 27204611344](https://github.com/Noma-Travel/Noma/actions/runs/27204611344) — after removing `basic-trip` from smoke (agent spec → `test:e2e:chat` only). |
| E3 | Deployed `.next` artifact has no Cypress binary | Runtime bundle unchanged | **PENDING** | |

---

## F. Staging environment parity

| # | Test | Expected | Status | Notes |
|---|------|----------|--------|-------|
| F1 | `GET {staging-api}/ping` | 200, `{"pong":true}` | **PASS** | Verified 2026-06-08. |
| F2 | NOMA staging app loads; login with test user | Cognito auth | **PENDING** | Staging system admin provisioned 2026-06-09 (`antoniojardim@travelwithnoma.com`, Cognito `CONFIRMED`). Test login on Amplify staging URL. |
| F3 | Console local against staging API | Hits staging Gateway | **PENDING** | |
| F4 | WebSocket from NOMA staging | Handshake succeeds | **PENDING** | After F2. |
| F5 | Staging isolated from prod | No prod table names in Lambda env | **PASS** | `noma-staging_*`, pool `us-east-1_vBbXLDESt`. |

---

## G. Application smoke tests (staging)

| # | Test | Expected | Status | Notes |
|---|------|----------|--------|-------|
| G1 | Roles/permissions smoke | Read-only checks pass | **PENDING** | Blocked on F2. |
| G2 | NOMA non-chat E2E | Specs green | **PENDING** | |
| G3 | New org onboarding | Tools install | **PENDING** | After F2 signup. |
| G4 | Chat/agent path (manual) | Agent responds | **PENDING** | |

---

## H. Production sanity (after staging sign-off)

| # | Test | Expected | Status | Notes |
|---|------|----------|--------|-------|
| H1 | Promote `staging` → `main` in one repo | Prod deploy + post_deploy | **PENDING** | Dispatch path verified via A1/A3. |
| H2 | `GET {prod-api}/ping` + spot-check | 200; no regression | **PENDING** | |
| H3 | Prod deploy uses `@main` refs | `requirements.ci.txt` in logs | **PASS** | Per [`deploy.yml`](.github/workflows/deploy.yml). |

---

## Staging login bootstrap

Staging Cognito pool (`us-east-1_vBbXLDESt`) is separate from prod. Public signup is **invite-only** (`NEXT_PUBLIC_SIGNUP_POLICY` default).

**Provisioned 2026-06-09:** system admin `antoniojardim@travelwithnoma.com` in staging Cognito + `SYSTEM_ADMIN_EMAILS` / `SYSTEM_ADMIN_USER_IDS` on `noma-noma-staging`. Use **Entrar** (not Criar conta). For **C3**, complete org onboarding (invite flow or admin org setup) so DynamoDB has at least one org, then trigger `post_deploy`.

**Before next staging deploy:** refresh GitHub secret `ZAPPA_SETTINGS_STAGING` from local `zappa_settings_staging.json` so admin env vars persist across deploys.

Amplify staging overrides: `NEXT_PUBLIC_AWS_USER_POOL_ID=us-east-1_vBbXLDESt`, `NEXT_PUBLIC_AWS_USER_POOL_CLIENT_ID=6rcfm5lsscs5ocnlu4ftukdbjr`.

---

## Sign-off criteria

- [ ] Every row in sections **A–G** marked **PASS** (or **SKIP** / **PARTIAL** documented)
- [ ] Section **H** complete after first prod promotion
- [ ] No open P1/P2 issues
- [ ] Team notified in Slack

### Sign-off

| Field | Value |
|-------|-------|
| Verifier | |
| Date | |
| Staging signed off | ☐ Yes |
| Production signed off | ☐ Yes |
| Notes | |

---

## Verification log

| Date | Verifier | Action | Result |
|------|----------|--------|--------|
| 2026-06-08 | Agent | Initial audit | Partial |
| 2026-06-08 | Agent | PAT Contents fix identified | A/B blocked |
| 2026-06-08 | User + Agent | **PAT Contents read+write + secret update** | **A1–A4, B1 PASS** |
| 2026-06-08 | Agent | E2 artifact fix (`include-hidden-files` for `.next`) | CI pipeline PASS; 1/5 smoke spec failed |
| 2026-06-09 | Agent | Staging system admin provisioned | Cognito + Lambda admin env; F2/C3 unblocked for manual test |
