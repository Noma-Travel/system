"""
EventBridge target: Amplify deployment status → GitHub repository_dispatch.
  FAILED  -> amplify-build-failed
  SUCCEED -> amplify-build-succeeded

Environment variables:
  GITHUB_REPO          default Noma-Travel/NOMA
  GITHUB_SECRET_ARN    Secrets Manager ARN with key GITHUB_TOKEN (or plain string secret)
  AMPLIFY_APP_ID       default d1f1y2ixvuy9lc
  AWS_REGION           set automatically by Lambda
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

import boto3

# Amplify jobStatus -> GitHub repository_dispatch event type.
STATUS_EVENT_TYPE = {
    "FAILED": "amplify-build-failed",
    "SUCCEED": "amplify-build-succeeded",
}
DEFAULT_APP_ID = "d1f1y2ixvuy9lc"
DEFAULT_GITHUB_REPO = "Noma-Travel/NOMA"
BRANCH_ENV_LABEL = {
    "staging": "staging",
    "main": "prod",
}


def _github_token() -> str:
    arn = os.environ.get("GITHUB_SECRET_ARN", "").strip()
    if not arn:
        raise ValueError("GITHUB_SECRET_ARN is not set")
    sm = boto3.client("secretsmanager")
    resp = sm.get_secret_value(SecretId=arn)
    raw = resp.get("SecretString") or ""
    if not raw:
        raise ValueError("Secret is empty")
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            for key in ("GITHUB_TOKEN", "GH_PAT", "token"):
                if parsed.get(key):
                    return str(parsed[key]).strip()
    except json.JSONDecodeError:
        pass
    return raw.strip()


def _amplify_job_summary(app_id: str, branch: str, job_id: str) -> dict:
    region = os.environ.get("AWS_REGION", "us-east-1")
    client = boto3.client("amplify", region_name=region)
    resp = client.get_job(appId=app_id, branchName=branch, jobId=job_id)
    job = resp.get("job") or {}
    return job.get("summary") or {}


def _github_commit(repo: str, sha: str, token: str) -> dict:
    if not sha:
        return {}
    url = f"https://api.github.com/repos/{repo}/commits/{sha}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError:
        return {}


def _amplify_console_url(region: str, app_id: str, branch: str, job_id: str) -> str:
    return (
        f"https://{region}.console.aws.amazon.com/amplify/home"
        f"?region={region}#{app_id}/{branch}/{job_id}"
    )


def _dispatch_github(repo: str, token: str, event_type: str, payload: dict) -> None:
    owner, name = repo.split("/", 1)
    url = f"https://api.github.com/repos/{owner}/{name}/dispatches"
    body = json.dumps({"event_type": event_type, "client_payload": payload}).encode(
        "utf-8"
    )
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        if resp.status not in (204, 200):
            raise RuntimeError(f"GitHub dispatch unexpected status {resp.status}")


def handler(event, context):
    detail = event.get("detail") or {}
    job_status = str(detail.get("jobStatus") or "").upper()
    event_type = STATUS_EVENT_TYPE.get(job_status)
    if not event_type:
        return {"skipped": True, "reason": f"jobStatus={job_status}"}

    app_id = str(detail.get("appId") or os.environ.get("AMPLIFY_APP_ID") or DEFAULT_APP_ID)
    branch = str(detail.get("branchName") or "").strip()
    job_id = str(detail.get("jobId") or "").strip()
    if not branch or not job_id:
        raise ValueError(f"Missing branchName or jobId in event detail: {detail}")

    expected_app = os.environ.get("AMPLIFY_APP_ID", DEFAULT_APP_ID).strip()
    if app_id != expected_app:
        return {"skipped": True, "reason": f"appId {app_id} != {expected_app}"}

    region = os.environ.get("AWS_REGION", "us-east-1")
    github_repo = os.environ.get("GITHUB_REPO", DEFAULT_GITHUB_REPO).strip()
    token = _github_token()

    summary = _amplify_job_summary(app_id, branch, job_id)
    commit_sha = str(summary.get("commitId") or "").strip()
    commit_message = str(summary.get("commitMessage") or "").strip()

    author_email = ""
    author_login = ""
    if commit_sha:
        commit = _github_commit(github_repo, commit_sha, token)
        commit_data = commit.get("commit") or {}
        author = commit_data.get("author") or {}
        author_email = str(author.get("email") or "").strip()
        gh_author = commit.get("author") or {}
        author_login = str(gh_author.get("login") or "").strip()

    env_label = BRANCH_ENV_LABEL.get(branch, branch)
    client_payload = {
        "environment_label": env_label,
        "branch": branch,
        "job_id": job_id,
        "sha": commit_sha,
        "commit_message": commit_message,
        "commit_author_email": author_email,
        "triggered_by": author_login,
        "source_repo": github_repo,
        "run_url": _amplify_console_url(region, app_id, branch, job_id),
    }

    _dispatch_github(github_repo, token, event_type, client_payload)
    return {
        "dispatched": True,
        "event_type": event_type,
        "branch": branch,
        "job_id": job_id,
        "sha": commit_sha,
    }
