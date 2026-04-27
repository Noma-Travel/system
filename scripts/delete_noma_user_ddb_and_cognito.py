#!/usr/bin/env python3
"""
Delete a Noma user from Cognito and remove their core DynamoDB rows so they can sign up again.

Derives app user_id as md5(cognito sub)[:9] (same as AuthController._user_id_from_claims).

Removes:
  - Cognito user (filter by email)
  - Entity row: (index=irn:entity:user:*, _id=user_id)
  - Rel rows: irn:rel:user:team:{user_id}:* (and matching irn:rel:team:user:… for each team)
  - Rel rows: email invites under index irn:rel:email:hash:ttl:*:*:* with rel beginning with {email}:
  - S3 object auth/tree/{user_id} in S3_BUCKET_NAME (if bucket configured)

Optional wide cleanup (off by default): scan noma-prod_data / noma-prod_chat for references — use
org-specific tooling if you still see duplicate-key issues.

Usage (AWS profile noma, region us-east-1):
  set AWS_PROFILE=noma
  python scripts/delete_noma_user_ddb_and_cognito.py you@email.com
  python scripts/delete_noma_user_ddb_and_cognito.py a@b.com c@d.com
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys

import boto3
from botocore.exceptions import ClientError

# Defaults match system/env_config.py and delete_cognito_user_by_email.py
REGION = os.environ.get("COGNITO_REGION", "us-east-1")
PROFILE = os.environ.get("AWS_PROFILE", "noma")
COGNITO_POOL = os.environ.get("COGNITO_USERPOOL_ID", "us-east-1_yydZGkq4N")
ENTITY_TABLE = os.environ.get("DYNAMODB_ENTITY_TABLE", "noma-prod_entities")
REL_TABLE = os.environ.get("DYNAMODB_REL_TABLE", "noma-prod_rel")
S3_BUCKET = os.environ.get("S3_BUCKET_NAME", "noma-prod-44841892")

USER_ENTITY_INDEX = "irn:entity:user:*"
EMAIL_REL_INDEX = "irn:rel:email:hash:ttl:*:*:*"


def user_id_from_sub(sub: str) -> str:
    return hashlib.md5(sub.encode("utf-8")).hexdigest()[:9]


def list_cognito_by_email(cognito, email: str) -> list[dict]:
    r = cognito.list_users(
        UserPoolId=COGNITO_POOL,
        Filter=f'email = "{email}"',
        Limit=10,
    )
    return r.get("Users", [])


def sub_from_user(u: dict) -> str | None:
    for a in u.get("Attributes", []):
        if a.get("Name") == "sub":
            return a.get("Value")
    return None


def delete_s3_tree_if_any(s3, user_id: str) -> None:
    key = f"auth/tree/{user_id}"
    if not S3_BUCKET:
        return
    try:
        s3.delete_object(Bucket=S3_BUCKET, Key=key)
        print(f"  S3: deleted s3://{S3_BUCKET}/{key} (or it did not exist)")
    except ClientError as e:
        print(f"  S3: warning — {e}", file=sys.stderr)


def delete_user_data(ddb, user_id: str, email: str) -> None:
    rel = ddb.Table(REL_TABLE)
    ent = ddb.Table(ENTITY_TABLE)
    # 1) user:team → collect team_ids, then delete both directions
    idx_ut = f"irn:rel:user:team:{user_id}:*"
    team_ids: list[str] = []
    q = {
        "KeyConditionExpression": "#i = :idx",
        "ExpressionAttributeNames": {"#i": "index"},
        "ExpressionAttributeValues": {":idx": idx_ut},
    }
    while True:
        r = rel.query(**q)
        for it in r.get("Items", []):
            tid = it.get("rel")
            if isinstance(tid, str):
                team_ids.append(tid)
            rel.delete_item(Key={"index": it["index"], "rel": it["rel"]})
            print(f"  rel: deleted user:team -> team_id={it.get('rel')!r}")
        if not r.get("LastEvaluatedKey"):
            break
        q["ExclusiveStartKey"] = r["LastEvaluatedKey"]

    for tid in team_ids:
        idx_tu = f"irn:rel:team:user:{tid}:*"
        r = rel.get_item(Key={"index": idx_tu, "rel": user_id})
        if "Item" in r:
            rel.delete_item(Key={"index": idx_tu, "rel": user_id})
            print(f"  rel: deleted team:user team={tid!r} user_id={user_id!r}")

    # 2) email:hash:ttl invite rows
    eprefix = f"{email}:"
    q2 = {
        "KeyConditionExpression": "#i = :eidx AND begins_with(#r, :pre)",
        "ExpressionAttributeNames": {"#i": "index", "#r": "rel"},
        "ExpressionAttributeValues": {":eidx": EMAIL_REL_INDEX, ":pre": eprefix},
    }
    while True:
        r = rel.query(**q2)
        for it in r.get("Items", []):
            rel.delete_item(Key={"index": it["index"], "rel": it["rel"]})
            rel_preview = (it.get("rel") or "")[:80]
            print(f"  rel: deleted email:hash:ttl rel={rel_preview!r}...")
        if not r.get("LastEvaluatedKey"):
            break
        q2 = {**q2, "ExclusiveStartKey": r["LastEvaluatedKey"]}

    # 3) user entity
    try:
        ent.delete_item(Key={"index": USER_ENTITY_INDEX, "_id": user_id})
        print(f"  entity: deleted user row _id={user_id!r}")
    except ClientError as e:
        print(f"  entity: delete failed: {e}", file=sys.stderr)


def delete_cognito(cognito, username: str) -> None:
    cognito.admin_delete_user(UserPoolId=COGNITO_POOL, Username=username)
    print(f"  cognito: deleted Username={username!r}")


def process_email(ddb, cognito, s3, email: str, dry_run: bool) -> None:
    email = email.strip()
    print(f"=== {email} ===")
    users = list_cognito_by_email(cognito, email)
    sub: str | None = None
    username: str | None = None
    if users:
        u = users[0]
        username = u.get("Username")
        sub = sub_from_user(u)
        print(f"  cognito: found Username={username!r} Status={u.get('UserStatus')!r} sub={sub!r}")
    else:
        print("  cognito: no user with this email (continuing with Dynamo from email hash only if we had sub)")

    if not sub and not users:
        print("  No Cognito user; cannot derive user_id from sub. You may need to clean Dynamo by hand for this email.")
        return

    if sub:
        user_id = user_id_from_sub(sub)
    else:
        user_id = ""
        # Cannot derive; skip DDB
        if dry_run:
            return
        return

    print(f"  derived user_id (md5(sub)[:9]) = {user_id!r}")

    if dry_run:
        print("  dry-run: would delete Cognito + DDB for this user_id")
        return

    # Order: DDB first while we still have consistent data; then Cognito
    if user_id:
        delete_user_data(ddb, user_id, email)
        delete_s3_tree_if_any(s3, user_id)
    if users and username is not None:
        delete_cognito(cognito, username)
    print("  done.\n")


def main() -> None:
    p = argparse.ArgumentParser(description="Delete Noma user: Cognito + core DynamoDB rows")
    p.add_argument("emails", nargs="+", help="Email address(es)")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    session = boto3.Session(profile_name=PROFILE, region_name=REGION)
    ddb = session.resource("dynamodb")
    cognito = session.client("cognito-idp")
    s3 = session.client("s3")

    for e in args.emails:
        process_email(ddb, cognito, s3, e, args.dry_run)


if __name__ == "__main__":
    main()
