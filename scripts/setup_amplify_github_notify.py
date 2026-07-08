#!/usr/bin/env python3
"""
Deploy EventBridge rule + Lambda that forwards Amplify build status to GitHub
repository_dispatch on Noma-Travel/NOMA:
  FAILED  -> amplify-build-failed
  SUCCEED -> amplify-build-succeeded

Usage:
  python setup_amplify_github_notify.py --profile noma --github-token ghp_xxx
  python setup_amplify_github_notify.py --profile noma --test-dispatch
  python setup_amplify_github_notify.py --profile noma --test-dispatch-success

Requires AWS credentials with IAM, Lambda, EventBridge, Secrets Manager, Amplify read.
The GitHub token needs repo scope (or fine-grained: Contents read + Actions write on NOMA).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
import zipfile
from pathlib import Path

import boto3

ACCOUNT_ID = "158711196499"
REGION = "us-east-1"
AMPLIFY_APP_ID = "d1f1y2ixvuy9lc"
GITHUB_REPO = "Noma-Travel/NOMA"
LAMBDA_NAME = "noma-amplify-github-notify"
RULE_NAME = "noma-amplify-build-failed"
SECRET_NAME = "noma/amplify-github-notify"
ROLE_NAME = "noma-amplify-github-notify-role"

HANDLER_DIR = Path(__file__).resolve().parent.parent / "lambda" / "amplify_github_notify"


def _session(profile: str | None):
    return boto3.Session(profile_name=profile, region_name=REGION)


def _zip_lambda() -> bytes:
    handler_path = HANDLER_DIR / "handler.py"
    if not handler_path.is_file():
        raise FileNotFoundError(handler_path)
    buf = tempfile.SpooledTemporaryFile()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(handler_path, "handler.py")
    buf.seek(0)
    return buf.read()


def _trust_policy() -> str:
    return json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "lambda.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }
            ],
        }
    )


def _role_policy(secret_arn: str) -> str:
    return json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": [
                        "logs:CreateLogGroup",
                        "logs:CreateLogStream",
                        "logs:PutLogEvents",
                    ],
                    "Resource": "arn:aws:logs:*:*:*",
                },
                {
                    "Effect": "Allow",
                    "Action": ["secretsmanager:GetSecretValue"],
                    "Resource": secret_arn,
                },
                {
                    "Effect": "Allow",
                    "Action": ["amplify:GetJob"],
                    "Resource": f"arn:aws:amplify:{REGION}:{ACCOUNT_ID}:apps/{AMPLIFY_APP_ID}/*",
                },
            ],
        }
    )


def _event_pattern() -> str:
    return json.dumps(
        {
            "source": ["aws.amplify"],
            "detail-type": ["Amplify Deployment Status Change"],
            "detail": {
                "appId": [AMPLIFY_APP_ID],
                "jobStatus": ["FAILED", "SUCCEED"],
            },
        }
    )


def ensure_secret(sm, token: str) -> str:
    try:
        resp = sm.describe_secret(SecretId=SECRET_NAME)
        arn = resp["ARN"]
        sm.put_secret_value(
            SecretId=SECRET_NAME,
            SecretString=json.dumps({"GITHUB_TOKEN": token}),
        )
        print(f"Updated secret {SECRET_NAME}")
    except sm.exceptions.ResourceNotFoundException:
        resp = sm.create_secret(
            Name=SECRET_NAME,
            Description="GitHub PAT for Amplify failure → repository_dispatch",
            SecretString=json.dumps({"GITHUB_TOKEN": token}),
        )
        arn = resp["ARN"]
        print(f"Created secret {SECRET_NAME}")
    return arn


def ensure_role(iam, secret_arn: str) -> str:
    try:
        role = iam.get_role(RoleName=ROLE_NAME)["Role"]
        role_arn = role["Arn"]
        print(f"Using existing role {ROLE_NAME}")
    except iam.exceptions.NoSuchEntityException:
        role = iam.create_role(
            RoleName=ROLE_NAME,
            AssumeRolePolicyDocument=_trust_policy(),
            Description="Lambda role for Amplify to GitHub failure notify",
        )["Role"]
        role_arn = role["Arn"]
        print(f"Created role {ROLE_NAME}")
        time.sleep(10)

    iam.put_role_policy(
        RoleName=ROLE_NAME,
        PolicyName="amplify-github-notify",
        PolicyDocument=_role_policy(secret_arn),
    )
    return role_arn


def ensure_lambda(lam, role_arn: str, secret_arn: str) -> str:
    zip_bytes = _zip_lambda()
    env = {
        "GITHUB_SECRET_ARN": secret_arn,
        "AMPLIFY_APP_ID": AMPLIFY_APP_ID,
        "GITHUB_REPO": GITHUB_REPO,
    }
    try:
        lam.get_function(FunctionName=LAMBDA_NAME)
        lam.update_function_code(FunctionName=LAMBDA_NAME, ZipFile=zip_bytes)
        time.sleep(3)
        lam.update_function_configuration(
            FunctionName=LAMBDA_NAME,
            Role=role_arn,
            Handler="handler.handler",
            Runtime="python3.12",
            Timeout=30,
            Environment={"Variables": env},
        )
        print(f"Updated Lambda {LAMBDA_NAME}")
    except lam.exceptions.ResourceNotFoundException:
        lam.create_function(
            FunctionName=LAMBDA_NAME,
            Runtime="python3.12",
            Role=role_arn,
            Handler="handler.handler",
            Timeout=30,
            Environment={"Variables": env},
            Code={"ZipFile": zip_bytes},
            Description="Amplify FAILED to GitHub repository_dispatch",
        )
        print(f"Created Lambda {LAMBDA_NAME}")

    fn = lam.get_function(FunctionName=LAMBDA_NAME)
    return fn["Configuration"]["FunctionArn"]


def ensure_eventbridge(events, lambda_arn: str) -> None:
    rule_arn = events.put_rule(
        Name=RULE_NAME,
        Description="NOMA Amplify build failed → GitHub notify workflow",
        EventPattern=_event_pattern(),
        State="ENABLED",
    )["RuleArn"]
    print(f"Rule {RULE_NAME} enabled: {rule_arn}")

    events.put_targets(
        Rule=RULE_NAME,
        Targets=[
            {
                "Id": "amplify-github-notify",
                "Arn": lambda_arn,
            }
        ],
    )
    print("EventBridge target attached")


def ensure_lambda_permission(lam, rule_arn: str) -> None:
    sid = "AllowEventBridgeInvoke"
    try:
        lam.add_permission(
            FunctionName=LAMBDA_NAME,
            StatementId=sid,
            Action="lambda:InvokeFunction",
            Principal="events.amazonaws.com",
            SourceArn=rule_arn,
        )
        print("Lambda invoke permission added")
    except lam.exceptions.ResourceConflictException:
        print("Lambda invoke permission already exists")


def test_dispatch(token: str, event_type: str = "amplify-build-failed") -> None:
    import urllib.request

    workflow = (
        "notify-amplify-success.yml"
        if event_type == "amplify-build-succeeded"
        else "notify-amplify-failure.yml"
    )
    payload = {
        "event_type": event_type,
        "client_payload": {
            "environment_label": "staging",
            "branch": "staging",
            "job_id": "test",
            "sha": "",
            "commit_message": f"setup_amplify_github_notify.py test dispatch ({event_type})",
            "commit_author_email": "",
            "triggered_by": "",
            "source_repo": GITHUB_REPO,
            "run_url": (
                f"https://{REGION}.console.aws.amazon.com/amplify/home"
                f"?region={REGION}#{AMPLIFY_APP_ID}/staging/test"
            ),
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
    with urllib.request.urlopen(req, timeout=20) as resp:
        print(f"Test dispatch HTTP {resp.status} — check NOMA Actions for {workflow}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="noma", help="AWS profile (default: noma)")
    parser.add_argument(
        "--github-token",
        default=os.environ.get("GITHUB_TOKEN", ""),
        help="GitHub PAT (repo + workflow). Or set GITHUB_TOKEN env var.",
    )
    parser.add_argument(
        "--test-dispatch",
        action="store_true",
        help="Only fire a test failure repository_dispatch (no AWS deploy)",
    )
    parser.add_argument(
        "--test-dispatch-success",
        action="store_true",
        help="Only fire a test success repository_dispatch (no AWS deploy)",
    )
    args = parser.parse_args()

    if args.test_dispatch or args.test_dispatch_success:
        if not args.github_token:
            print("Provide --github-token or GITHUB_TOKEN for --test-dispatch", file=sys.stderr)
            return 1
        if args.test_dispatch:
            test_dispatch(args.github_token, "amplify-build-failed")
        if args.test_dispatch_success:
            test_dispatch(args.github_token, "amplify-build-succeeded")
        return 0

    if not args.github_token:
        print(
            "Provide --github-token or GITHUB_TOKEN (same PAT as NOMA GH_PAT secret).",
            file=sys.stderr,
        )
        return 1

    session = _session(args.profile)
    sm = session.client("secretsmanager")
    iam = session.client("iam")
    lam = session.client("lambda")
    events = session.client("events")

    secret_arn = ensure_secret(sm, args.github_token)
    role_arn = ensure_role(iam, secret_arn)
    lambda_arn = ensure_lambda(lam, role_arn, secret_arn)
    ensure_eventbridge(events, lambda_arn)
    rule = events.describe_rule(Name=RULE_NAME)
    ensure_lambda_permission(lam, rule["Arn"])

    print()
    print("Done. Amplify FAILED/SUCCEED jobs on app", AMPLIFY_APP_ID, "will trigger")
    print("  Noma-Travel/NOMA → notify-amplify-failure.yml (FAILED)")
    print("  Noma-Travel/NOMA → notify-amplify-success.yml (SUCCEED)")
    print()
    print("Verify with:")
    print(f"  python {Path(__file__).name} --test-dispatch --github-token <token>")
    print(f"  python {Path(__file__).name} --test-dispatch-success --github-token <token>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
