#!/usr/bin/env python3
"""
Create or promote a platform admin user for the Console.

- Cognito: create user (optional) and add to group ``global_admin``
- DynamoDB: ensure user entity exists (md5(sub)[:9], same as login)

Usage:
  set AWS_PROFILE=noma
  python scripts/create_global_admin.py you@company.com
  python scripts/create_global_admin.py you@company.com --password 'YourSecurePass1!'
  python scripts/create_global_admin.py you@company.com --promote-only

Requires backend with get_tree_global_admin deployed. User must sign out/in after promotion.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

# Defaults aligned with system/env_config.py and delete_noma_user_ddb_and_cognito.py
REGION = os.environ.get("COGNITO_REGION", "us-east-1")
PROFILE = os.environ.get("AWS_PROFILE", "noma")
COGNITO_POOL = os.environ.get("COGNITO_USERPOOL_ID", "us-east-1_yydZGkq4N")
ENTITY_TABLE = os.environ.get("DYNAMODB_ENTITY_TABLE", "noma-prod_entities")
ADMIN_GROUP = "global_admin"
USER_ENTITY_INDEX = "irn:entity:user:*"


def user_id_from_sub(sub: str) -> str:
    return hashlib.md5(sub.encode("utf-8")).hexdigest()[:9]


def _bootstrap_renglo():
    system_dir = Path(__file__).resolve().parents[1]
    root = system_dir.parent
    renglo_lib = root / "dev" / "renglo-lib"
    for p in (str(renglo_lib), str(system_dir)):
        if p not in sys.path:
            sys.path.insert(0, p)


def list_user_by_email(cognito, email: str) -> dict | None:
    r = cognito.list_users(
        UserPoolId=COGNITO_POOL,
        Filter=f'email = "{email}"',
        Limit=10,
    )
    users = r.get("Users", [])
    return users[0] if users else None


def sub_from_user(user: dict) -> str | None:
    for attr in user.get("Attributes", []):
        if attr.get("Name") == "sub":
            return attr.get("Value")
    return user.get("Username")


def ensure_cognito_group(cognito) -> None:
    try:
        cognito.create_group(
            UserPoolId=COGNITO_POOL,
            GroupName=ADMIN_GROUP,
            Description="Platform-wide Console admin",
        )
        print(f"Cognito: created group {ADMIN_GROUP}")
    except ClientError as e:
        if e.response["Error"]["Code"] == "GroupExistsException":
            print(f"Cognito: group {ADMIN_GROUP} already exists")
        else:
            raise


def create_cognito_user(cognito, email: str, password: str, first: str, last: str) -> dict:
    cognito.admin_create_user(
        UserPoolId=COGNITO_POOL,
        Username=email,
        UserAttributes=[
            {"Name": "email", "Value": email},
            {"Name": "email_verified", "Value": "true"},
            {"Name": "given_name", "Value": first},
            {"Name": "family_name", "Value": last},
        ],
        MessageAction="SUPPRESS",
    )
    cognito.admin_set_user_password(
        UserPoolId=COGNITO_POOL,
        Username=email,
        Password=password,
        Permanent=True,
    )
    print(f"Cognito: created user {email}")
    user = list_user_by_email(cognito, email)
    if not user:
        raise RuntimeError(f"Could not find user after create: {email}")
    return user


def add_to_admin_group(cognito, username: str) -> None:
    cognito.admin_add_user_to_group(
        UserPoolId=COGNITO_POOL,
        Username=username,
        GroupName=ADMIN_GROUP,
    )
    print(f"Cognito: added {username} to {ADMIN_GROUP}")


def ensure_ddb_user(user_id: str, email: str, first: str, last: str) -> None:
    _bootstrap_renglo()
    from renglo.auth.auth_controller import AuthController

    try:
        import env_config as ec

        config = {
            "DYNAMODB_ENTITY_TABLE": getattr(ec, "DYNAMODB_ENTITY_TABLE", ENTITY_TABLE),
            "DYNAMODB_REL_TABLE": getattr(ec, "DYNAMODB_REL_TABLE", ""),
            "COGNITO_REGION": getattr(ec, "COGNITO_REGION", REGION),
            "COGNITO_USERPOOL_ID": getattr(ec, "COGNITO_USERPOOL_ID", COGNITO_POOL),
        }
    except ImportError:
        config = {
            "DYNAMODB_ENTITY_TABLE": ENTITY_TABLE,
            "COGNITO_REGION": REGION,
            "COGNITO_USERPOOL_ID": COGNITO_POOL,
        }
    auc = AuthController(config=config)
    existing = auc.get_entity("user", user_id=user_id)
    if existing.get("success"):
        print(f"DynamoDB: user entity already exists (_id={user_id})")
        return

    result = auc.create_user_funnel(
        user_id=user_id,
        email=email,
        name=first,
        slot_a=last,
    )
    if not result.get("success"):
        raise RuntimeError(f"create_user_funnel failed: {result}")
    print(f"DynamoDB: created user entity (_id={user_id})")


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or promote a global Console admin")
    parser.add_argument("email", help="Admin email (Cognito username)")
    parser.add_argument("--password", help="Permanent password (required for new users)")
    parser.add_argument("--first", default="Admin", help="Given name")
    parser.add_argument("--last", default="User", help="Family name")
    parser.add_argument(
        "--promote-only",
        action="store_true",
        help="Only add existing Cognito user to global_admin (do not create)",
    )
    args = parser.parse_args()
    email = args.email.strip().lower()

    session = boto3.Session(profile_name=PROFILE, region_name=REGION)
    cognito = session.client("cognito-idp")

    ensure_cognito_group(cognito)

    user = list_user_by_email(cognito, email)
    if not user:
        if args.promote_only:
            print(f"ERROR: no Cognito user for {email}", file=sys.stderr)
            return 1
        if not args.password:
            print("ERROR: --password required to create a new user", file=sys.stderr)
            return 1
        user = create_cognito_user(
            cognito, email, args.password, args.first, args.last
        )
    else:
        print(f"Cognito: found existing user {email}")

    username = user.get("Username") or email
    add_to_admin_group(cognito, username)

    sub = sub_from_user(user)
    if not sub:
        user = list_user_by_email(cognito, email) or user
        sub = sub_from_user(user)
    if not sub:
        print("ERROR: could not read Cognito sub", file=sys.stderr)
        return 1

    user_id = user_id_from_sub(sub)
    ensure_ddb_user(user_id, email, args.first, args.last)

    print()
    print("Done. Next steps:")
    print(f"  1. Sign in to Console as {email}")
    print("  2. Sign out and back in if you promoted an existing account (refresh JWT groups)")
    print(f"  3. Optional: GET /_auth/tree/refresh or delete S3 auth/tree/{user_id}")
    print(f"     app user_id: {user_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
