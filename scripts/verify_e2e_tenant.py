#!/usr/bin/env python3
"""Verify E2E tenant isolation (no FCDG access)."""
from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import boto3

FCDG_PORTFOLIO = "121609422c12"
FCDG_ORG = "57abb009d070"
E2E_EMAIL = "e2e+noma@travelwithnoma.com"

ENV_EXPECTED = {
    "staging": {
        "pool": "us-east-1_vBbXLDESt",
        "table": "noma-staging_entities",
        "portfolio": "9a2c8d01a3d2",
        "org": "166d34b5349e",
    },
    "prod": {
        "pool": "us-east-1_yydZGkq4N",
        "table": "noma-prod_entities",
        "portfolio": "b6fdc865b66a",
        "org": "dc0878c2135b",
    },
}


def user_id_from_sub(sub: str) -> str:
    return hashlib.md5(sub.encode("utf-8")).hexdigest()[:9]


def bootstrap():
    system_dir = Path(__file__).resolve().parents[1]
    root = system_dir.parent
    for rel in ("extensions/backend/package", "dev/renglo-api", "dev/renglo-lib", str(system_dir)):
        p = str(root / rel)
        if p not in sys.path:
            sys.path.insert(0, p)


def verify_env(name: str, cfg: dict) -> list[str]:
    issues: list[str] = []
    profile = os.environ.get("AWS_PROFILE", "noma")
    session = boto3.Session(profile_name=profile, region_name="us-east-1")
    cognito = session.client("cognito-idp")

    users = cognito.list_users(
        UserPoolId=cfg["pool"], Filter=f'email = "{E2E_EMAIL}"', Limit=5
    ).get("Users", [])
    if not users:
        issues.append(f"{name}: Cognito user {E2E_EMAIL} not found")
        return issues

    sub = next(
        (a["Value"] for a in users[0].get("Attributes", []) if a.get("Name") == "sub"),
        users[0].get("Username"),
    )
    user_id = user_id_from_sub(sub)

    os.environ["DYNAMODB_ENTITY_TABLE"] = cfg["table"]
    os.environ["COGNITO_USERPOOL_ID"] = cfg["pool"]
    bootstrap()
    from renglo.auth.auth_controller import AuthController
    from renglo.common import load_config

    auc = AuthController(config=load_config())
    auc.set_invocation_user(user_id)
    tree = auc.get_tree_full(user_id=user_id)
    doc = tree.get("document") or {}

    portfolios = doc.get("portfolios") or doc.get("items") or []
    if isinstance(portfolios, dict):
        portfolios = list(portfolios.values())

    portfolio_ids = set()
    org_ids = set()
    for p in portfolios:
        if not isinstance(p, dict):
            continue
        pid = p.get("_id") or p.get("portfolio_id")
        if pid:
            portfolio_ids.add(pid)
        for o in p.get("orgs") or p.get("organizations") or []:
            if isinstance(o, dict) and o.get("_id"):
                org_ids.add(o["_id"])

    if FCDG_PORTFOLIO in portfolio_ids or FCDG_ORG in org_ids:
        issues.append(f"{name}: E2E user can see FCDG tenant — FAIL")
    if cfg["portfolio"] not in portfolio_ids:
        issues.append(f"{name}: expected portfolio {cfg['portfolio']} not in tree {portfolio_ids}")
    if cfg["org"] not in org_ids:
        issues.append(f"{name}: expected org {cfg['org']} not in tree {org_ids}")

  # global_admin check
    groups = cognito.admin_list_groups_for_user(
        UserPoolId=cfg["pool"], Username=users[0]["Username"]
    ).get("Groups", [])
    if any(g.get("GroupName") == "global_admin" for g in groups):
        issues.append(f"{name}: user is in global_admin group — FAIL")

    if not issues:
        print(f"{name}: OK — user_id={user_id} portfolios={portfolio_ids} orgs={org_ids}")
    return issues


def main() -> int:
    all_issues: list[str] = []
    for name, cfg in ENV_EXPECTED.items():
        all_issues.extend(verify_env(name, cfg))
    if all_issues:
        for i in all_issues:
            print(f"ISSUE: {i}", file=sys.stderr)
        return 1
    print("All E2E tenant isolation checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
