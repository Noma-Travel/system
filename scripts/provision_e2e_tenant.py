#!/usr/bin/env python3
"""
Provision a dedicated Noma E2E tenant (portfolio + org + org_admin user).

Creates (or reuses) a Cognito user, portfolio, org, admin attendant bootstrap,
and optional chat test traveler "Antonio Jardim". Idempotent by tenant name +
user email within each environment.

Usage:
  set AWS_PROFILE=noma
  python scripts/provision_e2e_tenant.py --env staging --email e2e+noma@travelwithnoma.com --password "$E2E_PASSWORD"
  python scripts/provision_e2e_tenant.py --env prod --email e2e+noma@travelwithnoma.com --password "$E2E_PASSWORD"

Password may also be supplied via E2E_PASSWORD env var. If omitted, a random
password is generated and printed once (save it for Amplify / GitHub secrets).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import string
import sys
from pathlib import Path

try:
    import truststore  # Windows / corporate CA fixes for boto3 (optional)

    truststore.inject_into_ssl()
except ImportError:
    pass

import boto3
from botocore.exceptions import ClientError

TENANT_NAME = "Noma E2E"
CHAT_TRAVELER_NAME = "Antonio Jardim"
# Synthetic core profile so dashboard routes (e.g. /dashboard/invoices) are not blocked
# by the attendant profile gate. Document is intentionally omitted (not required for core).
E2E_CORE_PROFILE = {
    "country": "Brazil",
    "date_of_birth": "01/01/1990",
    "gender": "male",
    "mobile_phone": "+5511999990001",
    "client_whatsapp": "+5511999990001",
}
REGION = "us-east-1"
PROFILE = os.environ.get("AWS_PROFILE", "noma")

ENV_PROFILES = {
    "staging": {
        "COGNITO_USERPOOL_ID": "us-east-1_vBbXLDESt",
        "COGNITO_APP_CLIENT_ID": "6rcfm5lsscs5ocnlu4ftukdbjr",
        "COGNITO_REGION": "us-east-1",
        "DYNAMODB_ENTITY_TABLE": "noma-staging_entities",
        "DYNAMODB_BLUEPRINT_TABLE": "noma-staging_blueprints",
        "DYNAMODB_RINGDATA_TABLE": "noma-staging_data",
        "DYNAMODB_REL_TABLE": "noma-staging_rel",
        "DYNAMODB_CHAT_TABLE": "noma-staging_chat",
        "S3_BUCKET_NAME": "noma-staging-42067270",
        "SYS_ENV": "noma_staging",
        "URL_PREFIX": "noma_staging",
        "API_BASE_URL": "https://2r4dlx8qdj.execute-api.us-east-1.amazonaws.com/noma_staging",
        "CHAT_WS": "wss://1qefn6vt95.execute-api.us-east-1.amazonaws.com/production",
    },
    "prod": {
        "COGNITO_USERPOOL_ID": "us-east-1_yydZGkq4N",
        "COGNITO_APP_CLIENT_ID": "ede7jbk4ru8mdhomrjiie5c5d",
        "COGNITO_REGION": "us-east-1",
        "DYNAMODB_ENTITY_TABLE": "noma-prod_entities",
        "DYNAMODB_BLUEPRINT_TABLE": "noma-prod_blueprints",
        "DYNAMODB_RINGDATA_TABLE": "noma-prod_data",
        "DYNAMODB_REL_TABLE": "noma-prod_rel",
        "DYNAMODB_CHAT_TABLE": "noma-prod_chat",
        "S3_BUCKET_NAME": "noma-prod-44841892",
        "SYS_ENV": "noma_prod",
        "URL_PREFIX": "noma_prod",
        "API_BASE_URL": "https://u8za3vvgbb.execute-api.us-east-1.amazonaws.com/noma_prod",
        "CHAT_WS": "wss://3vdnaldxj0.execute-api.us-east-1.amazonaws.com/production",
    },
}


def user_id_from_sub(sub: str) -> str:
    return hashlib.md5(sub.encode("utf-8")).hexdigest()[:9]


def _bootstrap_paths() -> Path:
    system_dir = Path(__file__).resolve().parents[1]
    root = system_dir.parent
    for rel in (
        "extensions/backend/package",
        "dev/renglo-api",
        "dev/renglo-lib",
        str(system_dir),
    ):
        p = str(root / rel)
        if p not in sys.path:
            sys.path.insert(0, p)
    return system_dir


def apply_env_profile(profile: dict[str, str]) -> dict[str, str]:
    for key, value in profile.items():
        os.environ[key] = value
    return profile


def generate_password(length: int = 24) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%&*"
    while True:
        pwd = "".join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(c.islower() for c in pwd)
            and any(c.isupper() for c in pwd)
            and any(c.isdigit() for c in pwd)
        ):
            return pwd


def list_user_by_email(cognito, pool_id: str, email: str) -> dict | None:
    r = cognito.list_users(
        UserPoolId=pool_id,
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


def ensure_cognito_user(
    cognito, pool_id: str, email: str, password: str, first: str, last: str
) -> dict:
    user = list_user_by_email(cognito, pool_id, email)
    if user:
        print(f"Cognito: found existing user {email}")
        cognito.admin_set_user_password(
            UserPoolId=pool_id,
            Username=user.get("Username") or email,
            Password=password,
            Permanent=True,
        )
        print(f"Cognito: password reset for {email}")
        return user

    cognito.admin_create_user(
        UserPoolId=pool_id,
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
        UserPoolId=pool_id,
        Username=email,
        Password=password,
        Permanent=True,
    )
    print(f"Cognito: created user {email}")
    user = list_user_by_email(cognito, pool_id, email)
    if not user:
        raise RuntimeError(f"Could not find user after create: {email}")
    return user


def ensure_ddb_user(auc, user_id: str, email: str, first: str, last: str) -> None:
    existing = auc.get_entity("user", user_id=user_id)
    if existing.get("success"):
        print(f"DynamoDB: user entity already exists (_id={user_id})")
        return
    result = auc.create_user_funnel(user_id=user_id, email=email, name=first, slot_a=last)
    if not result.get("success"):
        raise RuntimeError(f"create_user_funnel failed: {result}")
    print(f"DynamoDB: created user entity (_id={user_id})")


def find_existing_tenant(auc, user_id: str) -> tuple[str | None, str | None]:
    resp = auc.AUM.list_entity("irn:entity:portfolio:*", limit=250)
    portfolios = (resp or {}).get("document", {}).get("items", []) or []
    for portfolio in portfolios:
        if portfolio.get("name") != TENANT_NAME:
            continue
        portfolio_id = portfolio.get("_id")
        if not portfolio_id:
            continue
        team_id = auc._pick_user_team_in_portfolio(user_id=user_id, portfolio_id=portfolio_id)
        if not team_id:
            continue
        org_index = f"irn:entity:portfolio/org:{portfolio_id}/*"
        org_resp = auc.AUM.list_entity(org_index, limit=50)
        orgs = (org_resp or {}).get("document", {}).get("items", []) or []
        for org in orgs:
            if org.get("name") == TENANT_NAME and org.get("_id"):
                return portfolio_id, org["_id"]
    return None, None


def _post_a_b(dac, portfolio_id: str, org_id: str, ring: str, body: dict) -> dict:
    result, status = dac.post_a_b(portfolio_id, org_id, ring, body)
    if not isinstance(result, dict):
        raise RuntimeError(f"post_a_b unexpected response: {result!r} status={status}")
    if not result.get("success") and status not in (200, 201):
        raise RuntimeError(f"post_a_b failed ({status}): {result}")
    return result


def ensure_org_onboarding(auc, dac, portfolio_id: str, org_id: str, user_id: str) -> None:
    from noma.handlers.noma_onboardings import NomaOnboardings

    tools = dac.get_a_b(portfolio_id, org_id, "schd_tools", limit=50)
    tool_count = len(tools.get("items") or []) if tools.get("success") else 0
    if tool_count >= 40:
        print(f"Onboarding: {tool_count} schd_tools present — skipping tool install")
        return
    if tool_count:
        print(f"Onboarding: only {tool_count} schd_tools — running full tool install")

    team_id = auc._pick_user_team_in_portfolio(user_id=user_id, portfolio_id=portfolio_id)
    if not team_id:
        print("Onboarding: skipped — could not resolve team for portfolio")
        return
    onboarding = NomaOnboardings()
    onboarding.AUC.set_invocation_user(user_id)
    try:
        result = onboarding.run(
            {
                "portfolio": portfolio_id,
                "team": team_id,
                "org": org_id,
                "name": TENANT_NAME,
            }
        )
    except Exception as exc:
        print(f"Onboarding: warning — tool install raised: {exc}")
        return
    if result.get("success"):
        print(f"Onboarding: default tools installed for org {org_id}")
    else:
        print(f"Onboarding: warning — tool install may have failed: {result.get('message')}")

    try:
        auc.set_invocation_user(user_id)
        auc.refresh_tree()
        print("Auth tree: refreshed for E2E user")
    except Exception as exc:
        print(f"Auth tree: warning — refresh failed (non-fatal): {exc}")


def ensure_admin_attendant(
    dac, auc, portfolio_id: str, org_id: str, user_id: str, email: str, first: str, last: str
) -> None:
    from noma.handlers.bootstrap_org_admin import BootstrapOrgAdmin

    auc.set_invocation_user(user_id)
    resp = dac.get_a_b(portfolio_id, org_id, "noma_attendants", limit=1000)
    items = resp.get("items", []) if resp and resp.get("success") else []
    admin_email = email.strip().lower()
    caller = next(
        (
            a
            for a in items
            if str(a.get("email") or "").strip().lower() == admin_email
        ),
        None,
    )
    if caller is None:
        body = {
            "name": f"{first} {last}".strip(),
            "email": email,
            "user_id": user_id,
            "status": "active",
            "isActive": True,
        }
        created = _post_a_b(dac, portfolio_id, org_id, "noma_attendants", body)
        print(f"Attendants: created admin member record for {email}")
    else:
        print(f"Attendants: admin member record already exists for {email}")

    boot = BootstrapOrgAdmin().run(
        {
            "portfolio": portfolio_id,
            "org": org_id,
            "caller_email": email,
        }
    )
    if not boot.get("success"):
        raise RuntimeError(f"bootstrap_org_admin failed: {boot}")
    print(f"Role: org_admin bootstrapped ({boot.get('message')})")


def _find_attendant_by_email(items: list[dict], email: str) -> dict | None:
    target = email.strip().lower()
    return next(
        (a for a in items if str(a.get("email") or "").strip().lower() == target),
        None,
    )


def _attendant_core_complete(attendant: dict, email: str) -> bool:
    """Mirror frontend validateAttendantCoreProfile (no travel document)."""
    name = str(attendant.get("name") or "").strip()
    if len(name.split()) < 2:
        return False
    if not str(attendant.get("email") or email).strip():
        return False
    dob = str(
        attendant.get("date_of_birth") or attendant.get("nascimento") or ""
    ).strip()
    if not dob:
        return False
    gender = str(
        attendant.get("gender") or attendant.get("sex") or attendant.get("sexo") or ""
    ).strip()
    if not gender:
        return False
    country = str(
        attendant.get("country") or attendant.get("pais") or ""
    ).strip()
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


def ensure_admin_attendant_core_profile(
    dac,
    auc,
    portfolio_id: str,
    org_id: str,
    user_id: str,
    email: str,
    first: str,
    last: str,
) -> None:
    from noma.handlers.complete_attendant import CompleteAttendant

    auc.set_invocation_user(user_id)
    resp = dac.get_a_b(portfolio_id, org_id, "noma_attendants", limit=1000)
    items = resp.get("items", []) if resp and resp.get("success") else []
    attendant = _find_attendant_by_email(items, email)
    if attendant and _attendant_core_complete(attendant, email):
        print(f"Attendants: core profile already complete for {email}")
        return

    full_name = f"{first} {last}".strip()
    result = CompleteAttendant().complete_attendant(
        portfolio_id=portfolio_id,
        email=email,
        name=full_name,
        country=E2E_CORE_PROFILE["country"],
        date_of_birth=E2E_CORE_PROFILE["date_of_birth"],
        gender=E2E_CORE_PROFILE["gender"],
        status=1,
        org_hint=org_id,
        mobile_phone=E2E_CORE_PROFILE["mobile_phone"],
        client_whatsapp=E2E_CORE_PROFILE["client_whatsapp"],
    )
    if not result.get("success"):
        raise RuntimeError(f"complete_attendant failed for E2E admin: {result}")
    print(f"Attendants: core profile completed for {email} (dashboard gates unlocked)")


def ensure_chat_traveler(dac, portfolio_id: str, org_id: str, email: str) -> None:
    resp = dac.get_a_b(portfolio_id, org_id, "noma_attendants", limit=1000)
    items = resp.get("items", []) if resp and resp.get("success") else []
    exists = any(
        CHAT_TRAVELER_NAME.lower() in str(a.get("name") or "").lower() for a in items
    )
    if exists:
        print(f'Attendants: "{CHAT_TRAVELER_NAME}" already exists — ok.')
        return
    created = _post_a_b(
        dac,
        portfolio_id,
        org_id,
        "noma_attendants",
        {
            "name": CHAT_TRAVELER_NAME,
            "email": email,
            "isActive": True,
            "status": "active",
            "sendEmail": False,
        },
    )
    if not created.get("success"):
        raise RuntimeError(f'Failed to create chat traveler "{CHAT_TRAVELER_NAME}": {created}')
    print(f'Attendants: created chat traveler "{CHAT_TRAVELER_NAME}".')


def print_summary(env: str, profile: dict[str, str], email: str, password: str, portfolio_id: str, org_id: str) -> None:
    summary = {
        "environment": env,
        "email": email,
        "password": password,
        "E2E_PORTFOLIO_ID": portfolio_id,
        "E2E_ORG_ID": org_id,
        "NEXT_PUBLIC_API_BASE_URL": profile["API_BASE_URL"],
        "NEXT_PUBLIC_AWS_USER_POOL_ID": profile["COGNITO_USERPOOL_ID"],
        "NEXT_PUBLIC_AWS_USER_POOL_CLIENT_ID": profile["COGNITO_APP_CLIENT_ID"],
        "NEXT_PUBLIC_CHAT_WS": profile["CHAT_WS"],
        "NEXT_PUBLIC_PORTFOLIO_ID": portfolio_id,
        "NEXT_PUBLIC_ORG_ID": org_id,
        "CYPRESS_LOGIN_EMAIL": email,
        "CYPRESS_LOGIN_PASSWORD": password,
        "CYPRESS_E2E_PORTFOLIO_ID": portfolio_id,
        "CYPRESS_E2E_ORG_ID": org_id,
    }
    print()
    print("=" * 72)
    print(f"E2E tenant ready ({env})")
    print("=" * 72)
    print(json.dumps(summary, indent=2))
    print()
    print("Paste the values above into Amplify branch secrets and GitHub Environment secrets.")
    print("Do NOT commit the password to git.")


def provision(
    env: str,
    email: str,
    password: str,
    first: str,
    last: str,
    skip_chat_traveler: bool,
) -> int:
    profile = ENV_PROFILES[env]
    apply_env_profile(profile)
    _bootstrap_paths()

    from renglo_api import create_app

    app = create_app()
    with app.app_context():
        return _provision_in_context(
            env=env,
            profile=profile,
            email=email,
            password=password,
            first=first,
            last=last,
            skip_chat_traveler=skip_chat_traveler,
        )


def _provision_in_context(
    env: str,
    profile: dict[str, str],
    email: str,
    password: str,
    first: str,
    last: str,
    skip_chat_traveler: bool,
) -> int:
    from renglo.auth.auth_controller import AuthController
    from renglo.data.data_controller import DataController
    from renglo.common import load_config

    config = load_config()
    session = boto3.Session(profile_name=PROFILE, region_name=REGION)
    cognito = session.client("cognito-idp")
    pool_id = profile["COGNITO_USERPOOL_ID"]

    user = ensure_cognito_user(cognito, pool_id, email, password, first, last)
    sub = sub_from_user(user)
    if not sub:
        user = list_user_by_email(cognito, pool_id, email) or user
        sub = sub_from_user(user)
    if not sub:
        print("ERROR: could not read Cognito sub", file=sys.stderr)
        return 1

    user_id = user_id_from_sub(sub)
    auc = AuthController(config=config)
    dac = DataController(config=config)
    auc.set_invocation_user(user_id)

    ensure_ddb_user(auc, user_id, email, first, last)

    portfolio_id, org_id = find_existing_tenant(auc, user_id)
    if portfolio_id and org_id:
        print(f"Tenant: reusing existing portfolio={portfolio_id} org={org_id}")
        ensure_org_onboarding(auc, dac, portfolio_id, org_id, user_id)
    else:
        print("Tenant: creating portfolio + org funnels...")
        portfolio_resp = auc.create_portfolio_funnel(
            name=TENANT_NAME,
            about="Dedicated automated E2E tenant - do not use for customer data.",
            user_id=user_id,
        )
        if not portfolio_resp.get("success"):
            raise RuntimeError(f"create_portfolio_funnel failed: {portfolio_resp}")
        portfolio_id = portfolio_resp["document"][0]["document"]["_id"]
        print(f"Portfolio: created {portfolio_id}")

        org_resp = auc.create_org_funnel(
            name=TENANT_NAME,
            portfolio_id=portfolio_id,
            user_id=user_id,
        )
        if not org_resp.get("success"):
            raise RuntimeError(f"create_org_funnel failed: {org_resp}")
        org_id = org_resp["document"][0]["document"]["_id"]
        if not org_id:
            raise RuntimeError(f"Could not resolve org id from funnel: {org_resp}")
        print(f"Org: created {org_id}")
        ensure_org_onboarding(auc, dac, portfolio_id, org_id, user_id)

    ensure_admin_attendant(dac, auc, portfolio_id, org_id, user_id, email, first, last)
    ensure_admin_attendant_core_profile(
        dac, auc, portfolio_id, org_id, user_id, email, first, last
    )
    if not skip_chat_traveler:
        ensure_chat_traveler(dac, portfolio_id, org_id, email)

    print_summary(env, profile, email, password, portfolio_id, org_id)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision dedicated Noma E2E tenant")
    parser.add_argument("--env", choices=sorted(ENV_PROFILES), required=True)
    parser.add_argument("--email", default="e2e+noma@travelwithnoma.com")
    parser.add_argument("--password", default=os.environ.get("E2E_PASSWORD", ""))
    parser.add_argument("--first", default="Noma")
    parser.add_argument("--last", default="E2E")
    parser.add_argument(
        "--skip-chat-traveler",
        action="store_true",
        help=f'Skip creating "{CHAT_TRAVELER_NAME}" (Cypress seed.ts can create it).',
    )
    args = parser.parse_args()

    email = args.email.strip().lower()
    password = args.password or generate_password()
    if not args.password:
        print("Generated E2E password (save for Amplify/GitHub secrets).")

    try:
        return provision(
            env=args.env,
            email=email,
            password=password,
            first=args.first,
            last=args.last,
            skip_chat_traveler=args.skip_chat_traveler,
        )
    except ClientError as e:
        print(f"AWS error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
