#!/usr/bin/env python3
"""Verify E2E tenant isolation (no FCDG access)."""
from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

try:
    import truststore  # Windows / corporate CA fixes for boto3 (optional)

    truststore.inject_into_ssl()
except ImportError:
    pass

import boto3

FCDG_PORTFOLIO = "121609422c12"
FCDG_ORG = "57abb009d070"
E2E_EMAIL = "e2e+noma@travelwithnoma.com"

ENV_EXPECTED = {
    "staging": {
        "pool": "us-east-1_vBbXLDESt",
        "table": "noma-staging_entities",
        "ring_table": "noma-staging_data",
        "rel_table": "noma-staging_rel",
        "portfolio": "9a2c8d01a3d2",
        "org": "166d34b5349e",
    },
    "prod": {
        "pool": "us-east-1_yydZGkq4N",
        "table": "noma-prod_entities",
        "ring_table": "noma-prod_data",
        "rel_table": "noma-prod_rel",
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


def attendant_core_complete(attendant: dict, email: str) -> bool:
    name = str(attendant.get("name") or "").strip()
    if len(name.split()) < 2:
        return False
    if not str(attendant.get("email") or email).strip():
        return False
    dob = str(attendant.get("date_of_birth") or attendant.get("nascimento") or "").strip()
    if not dob:
        return False
    gender = str(
        attendant.get("gender") or attendant.get("sex") or attendant.get("sexo") or ""
    ).strip()
    if not gender:
        return False
    country = str(attendant.get("country") or attendant.get("pais") or "").strip()
    if not country:
        return False
    phone = str(
        attendant.get("mobile_phone") or attendant.get("client_whatsapp") or ""
    ).strip()
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) < 8:
        return False
    status = str(attendant.get("status") or "").strip().lower()
    user_id = str(attendant.get("user_id") or "").strip()
    return status in ("1", "active") and bool(user_id)


def extract_tree_ids(doc: dict) -> tuple[set[str], set[str]]:
    """Parse get_tree_full document (portfolios/orgs are dicts keyed by id)."""
    portfolio_ids: set[str] = set()
    org_ids: set[str] = set()

    portfolios = doc.get("portfolios") or doc.get("items") or []
    if isinstance(portfolios, dict):
        portfolio_ids.update(portfolios.keys())
        for portfolio in portfolios.values():
            if not isinstance(portfolio, dict):
                continue
            orgs = portfolio.get("orgs") or portfolio.get("organizations") or {}
            if isinstance(orgs, dict):
                org_ids.update(orgs.keys())
            else:
                for org in orgs:
                    if isinstance(org, dict):
                        oid = org.get("_id") or org.get("org_id")
                        if oid:
                            org_ids.add(oid)
        return portfolio_ids, org_ids

    for portfolio in portfolios:
        if not isinstance(portfolio, dict):
            continue
        pid = portfolio.get("_id") or portfolio.get("portfolio_id")
        if pid:
            portfolio_ids.add(pid)
        orgs = portfolio.get("orgs") or portfolio.get("organizations") or []
        if isinstance(orgs, dict):
            org_ids.update(orgs.keys())
        else:
            for org in orgs:
                if isinstance(org, dict):
                    oid = org.get("_id") or org.get("org_id")
                    if oid:
                        org_ids.add(oid)
    return portfolio_ids, org_ids


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
    os.environ["DYNAMODB_RINGDATA_TABLE"] = cfg.get("ring_table", "")
    os.environ["DYNAMODB_REL_TABLE"] = cfg.get("rel_table", "")
    os.environ["COGNITO_USERPOOL_ID"] = cfg["pool"]
    bootstrap()
    from renglo.auth.auth_controller import AuthController
    from renglo.data.data_controller import DataController
    from renglo.common import load_config

    config = load_config()
    auc = AuthController(config=config)
    dac = DataController(config=config)
    auc.set_invocation_user(user_id)
    tree = auc.get_tree_full(user_id=user_id)
    doc = tree.get("document") or {}

    portfolio_ids, org_ids = extract_tree_ids(doc)

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

    attendants = dac.get_a_b(cfg["portfolio"], cfg["org"], "noma_attendants", limit=1000)
    items = attendants.get("items", []) if attendants.get("success") else []
    admin = next(
        (a for a in items if str(a.get("email") or "").strip().lower() == E2E_EMAIL),
        None,
    )
    if not admin:
        issues.append(f"{name}: E2E admin attendant not found in org {cfg['org']}")
    elif not attendant_core_complete(admin, E2E_EMAIL):
        issues.append(
            f"{name}: E2E admin attendant core profile incomplete — "
            "re-run provision_e2e_tenant.py"
        )

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
