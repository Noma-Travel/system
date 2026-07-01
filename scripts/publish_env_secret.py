#!/usr/bin/env python3
"""Publish env secrets to AWS Secrets Manager (admin one-time / rotation)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from noma_env.aws_ssl import bootstrap_aws_ssl
from noma_env.paths import normalize_env, secret_id  # noqa: E402


def put_secret_payload(
    env: str,
    payload: dict,
    *,
    region: str = "us-east-1",
    profile: str = "noma",
) -> str:
    if not isinstance(payload, dict):
        raise ValueError("payload must be a flat object")

    bootstrap_aws_ssl()
    import boto3

    session = boto3.Session(profile_name=profile)
    client = session.client("secretsmanager", region_name=region)
    sid = secret_id(normalize_env(env))
    body = json.dumps(payload)
    try:
        client.put_secret_value(SecretId=sid, SecretString=body)
        action = "Updated"
    except client.exceptions.ResourceNotFoundException:
        client.create_secret(Name=sid, SecretString=body)
        action = "Created"
    print(f"{action} secret {sid} ({len(payload)} keys)")
    return sid


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish JSON secrets to AWS SM")
    parser.add_argument("env", help="staging or prod")
    parser.add_argument(
        "json_file",
        nargs="?",
        help="Path to flat JSON object (gitignored). Omit with --from-zappa.",
    )
    parser.add_argument(
        "--from-zappa",
        action="store_true",
        help="Extract secret keys from zappa_settings*.json and publish (no local JSON file)",
    )
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--profile", default="noma")
    args = parser.parse_args()

    env = normalize_env(args.env)
    bootstrap_aws_ssl()

    if args.from_zappa:
        from sync_secrets_from_zappa import extract_secrets_from_zappa

        payload = extract_secrets_from_zappa(env)
    else:
        if not args.json_file:
            print("Provide json_file or use --from-zappa")
            return 1
        path = Path(args.json_file)
        if not path.is_file():
            print(f"File not found: {path}")
            return 1
        payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        print("JSON must be a flat object")
        return 1

    put_secret_payload(env, payload, region=args.region, profile=args.profile)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
