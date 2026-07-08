#!/usr/bin/env python3
"""
Fire deploy-notification test scenarios so you can verify Slack/#deployments end to end.

Covers every notification path that is driven by GitHub ``repository_dispatch``
(the Amplify frontend deploy alerts). Backend-deploy and GitHub CI-gate alerts are
driven by ``workflow_run`` and cannot be faked with a dispatch; see --list for how
to exercise those.

Usage:
  # Fire all Amplify scenarios (staging/prod x success/failure):
  python test_deploy_notifications.py --all --github-token "$(gh auth token)"

  # Fire a single scenario:
  python test_deploy_notifications.py --scenario amplify-staging-success --github-token <token>

  # Just list every scenario and how it is tested:
  python test_deploy_notifications.py --list

The GitHub token needs the same scope as the NOMA ``GH_PAT`` secret (repo + workflow).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

GITHUB_REPO = "Noma-Travel/NOMA"
REGION = "us-east-1"
AMPLIFY_APP_ID = "d1f1y2ixvuy9lc"


def _amplify_console_url(branch: str) -> str:
    return (
        f"https://{REGION}.console.aws.amazon.com/amplify/home"
        f"?region={REGION}#{AMPLIFY_APP_ID}/{branch}/test"
    )


# Amplify (repository_dispatch) scenarios. environment_label mirrors what the Lambda
# produces: staging -> "staging", main -> "prod".
DISPATCH_SCENARIOS = {
    "amplify-staging-success": {
        "event_type": "amplify-build-succeeded",
        "branch": "staging",
        "environment_label": "staging",
        "expect": "white_check_mark: staging (NOMA Amplify) deploy succeeded — ... (staging)",
    },
    "amplify-staging-failure": {
        "event_type": "amplify-build-failed",
        "branch": "staging",
        "environment_label": "staging",
        "expect": "x: staging (NOMA Amplify) deploy failed — ... (staging)",
    },
    "amplify-prod-success": {
        "event_type": "amplify-build-succeeded",
        "branch": "main",
        "environment_label": "prod",
        "expect": "white_check_mark: prod (NOMA Amplify) deploy succeeded — ... (main)",
    },
    "amplify-prod-failure": {
        "event_type": "amplify-build-failed",
        "branch": "main",
        "environment_label": "prod",
        "expect": "x: prod (NOMA Amplify) deploy failed — ... (main)",
    },
}

# workflow_run scenarios cannot be dispatched; documented for --list.
WORKFLOW_RUN_SCENARIOS = {
    "ci-gate-staging-failure": (
        "Push a failing commit to staging -> Build and E2E fails -> "
        "notify-e2e-failure.yml (CI gate failed, branch staging, Cypress log lines)."
    ),
    "ci-gate-main-failure": (
        "Same as above on main. CI-gate success is intentionally silent."
    ),
    "backend-staging-success": (
        "Push to system staging (or dispatch backend-staging-updated) -> "
        "Deploy Backend (Staging) succeeds -> notify-staging-deploy-success.yml."
    ),
    "backend-staging-failure": (
        "A failing backend staging deploy -> notify-staging-deploy-failure.yml "
        "(includes deploy log lines)."
    ),
    "backend-prod-success": (
        "Push/merge to system main -> Deploy Backend (Production) succeeds -> "
        "notify-prod-deploy-success.yml."
    ),
    "backend-prod-failure": (
        "A failing backend production deploy -> notify-prod-deploy-failure.yml."
    ),
}


def _dispatch(token: str, scenario_key: str) -> None:
    cfg = DISPATCH_SCENARIOS[scenario_key]
    branch = cfg["branch"]
    payload = {
        "event_type": cfg["event_type"],
        "client_payload": {
            "environment_label": cfg["environment_label"],
            "branch": branch,
            "job_id": "test",
            "sha": "",
            "commit_message": f"test_deploy_notifications.py :: {scenario_key}",
            "commit_author_email": "",
            "triggered_by": "",
            "source_repo": GITHUB_REPO,
            "run_url": _amplify_console_url(branch),
        },
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.github.com/repos/{GITHUB_REPO}/dispatches",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            print(f"  [{scenario_key}] HTTP {resp.status} -> expect: {cfg['expect']}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"  [{scenario_key}] HTTP {exc.code} ERROR: {detail}", file=sys.stderr)
        raise


def list_scenarios() -> None:
    print("=" * 70)
    print("Deploy notification scenarios")
    print("=" * 70)
    print("\nrepository_dispatch (testable with this script):")
    for key, cfg in DISPATCH_SCENARIOS.items():
        print(f"  - {key:26s} expect: {cfg['expect']}")
    print("\nworkflow_run (need a real source run; not dispatchable):")
    for key, desc in WORKFLOW_RUN_SCENARIOS.items():
        print(f"  - {key:26s} {desc}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--github-token", default="", help="GitHub PAT (repo + workflow).")
    parser.add_argument(
        "--scenario",
        choices=sorted(DISPATCH_SCENARIOS.keys()),
        help="Fire a single Amplify scenario.",
    )
    parser.add_argument("--all", action="store_true", help="Fire all Amplify scenarios.")
    parser.add_argument("--list", action="store_true", help="List all scenarios and exit.")
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Seconds to wait between dispatches (default 2).",
    )
    args = parser.parse_args()

    if args.list:
        list_scenarios()
        return 0

    if not args.github_token:
        print("Provide --github-token (e.g. --github-token \"$(gh auth token)\").", file=sys.stderr)
        return 1

    if args.all:
        keys = list(DISPATCH_SCENARIOS.keys())
    elif args.scenario:
        keys = [args.scenario]
    else:
        print("Nothing to do. Use --all, --scenario <name>, or --list.", file=sys.stderr)
        return 1

    print(f"Firing {len(keys)} scenario(s) to {GITHUB_REPO}...")
    for i, key in enumerate(keys):
        _dispatch(args.github_token, key)
        if i < len(keys) - 1:
            time.sleep(args.delay)
    print("\nDone. Check Slack #deployments and NOMA Actions for the notify runs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
