#!/usr/bin/env python3
"""
Delete a Cognito user by email attribute so you can sign up again with the same address.

Uses the same pool as env_config / zappa (override with COGNITO_USERPOOL_ID).
AWS profile: noma (override with AWS_PROFILE).
"""
import argparse
import os
import sys

import boto3

REGION = os.environ.get("COGNITO_REGION", "us-east-1")
PROFILE = os.environ.get("AWS_PROFILE", "noma")
# Default matches env_config.py / zappa_settings.json noma_prod
DEFAULT_POOL = os.environ.get("COGNITO_USERPOOL_ID", "us-east-1_yydZGkq4N")


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete Cognito user by email")
    parser.add_argument("email", help="Email address (must match Cognito email attribute)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List matching users but do not delete",
    )
    args = parser.parse_args()
    email = args.email.strip()
    pool_id = DEFAULT_POOL

    session = boto3.Session(profile_name=PROFILE, region_name=REGION)
    client = session.client("cognito-idp")

    # Filter syntax: https://docs.aws.amazon.com/cognito/latest/developerguide/how-to-manage-user-accounts.html
    resp = client.list_users(
        UserPoolId=pool_id,
        Filter=f'email = "{email}"',
        Limit=60,
    )
    users = resp.get("Users", [])
    if not users:
        print(f"No Cognito user with email={email!r} in pool {pool_id}.", file=sys.stderr)
        sys.exit(1)

    for u in users:
        username = u["Username"]
        status = u.get("UserStatus", "")
        print(f"Found Username={username!r} Status={status}")
        if args.dry_run:
            continue
        client.admin_delete_user(UserPoolId=pool_id, Username=username)
        print(f"Deleted: {username}")

    if args.dry_run:
        print("Dry run: no users deleted.")
    else:
        print("Cognito delete done.")


if __name__ == "__main__":
    main()
