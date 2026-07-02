#!/usr/bin/env python3
"""Validate env.catalog.yaml against code references."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from audit_env_vars import scan, SCAN_ROOTS, WORKSPACE  # noqa: E402
from noma_env.loader import load_catalog  # noqa: E402
from noma_env.paths import CATALOG_PATH, CONFIG_DIR  # noqa: E402

GENERATED_CATALOG_PATH = CONFIG_DIR / "env.catalog.generated.yaml"

# Runtime / CI / test-only — not part of centralized app config
IGNORE_VARS = frozenset({
    "ADMIN_EMAIL",
    "ADMIN_PASSWORD",
    "AMPLIFY_APP_ID",
    "API_BASE_URL",
    "APP_ENV",
    "AWS_ACCESS_KEY_ID",
    "AWS_DEFAULT_REGION",
    "AWS_EXECUTION_ENV",
    "AWS_LAMBDA_FUNCTION_NAME",
    "AWS_NO_VERIFY_SSL",
    "AWS_PROFILE",
    "AWS_REGION",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "BOOKING_TOKEN",
    "CI",
    "CIRCLECI",
    "CYPRESS_LOGIN_EMAIL",
    "CYPRESS_LOGIN_PASSWORD",
    "CYPRESS_E2E_PORTFOLIO_ID",
    "CYPRESS_E2E_ORG_ID",
    "DEBUG",
    "DEBUG_DIR",
    "DEBUG_JSON",
    "E2E_CHECKOUT_SANDBOX",
    "E2E_ORG_ID",
    "E2E_PORTFOLIO_ID",
    "FLASK_DEBUG",
    "FORCE_TREE_FROM_DB",
    "GITHUB_ACTIONS",
    "HOME",
    "HOSTNAME",
    "LOCATOR",
    "LOG_LEVEL",
    "LOGIN_EMAIL",
    "LOGIN_PASSWORD",
    "MONGODB_DB",
    "MONGODB_URI",
    "NODE_ENV",
    "PATH",
    "PORT",
    "PRICE",
    "RATE_TOKEN",
    "RESERVATION_TOKEN",
    "REXTUR_GUS_BASE",
    "REXTUR_GUS_KEY",
    "REXTUR_GUS_LIVE",
    "REXTUR_LIVE_TEST",
    "SEARCH_AGES",
    "SEARCH_DATE",
    "SEARCH_DEST",
    "SEARCH_ORIGIN",
    "SEARCH_SOURCE",
    "SKIP_CANCEL",
    "SOURCE",
    "TICKET_NUMBER",
    "URL_PREFIX",
    "USER",
    "VERCEL",
    "VERCEL_ENV",
    "WA_DEFAULT_ORG",
    "WA_DEFAULT_PORTFOLIO",
    "WHATSAPP_WEBHOOK_SECRET",
    "TWILIO_AUTH_TOKEN",
    "TWILIO_WEBHOOK_URL_OVERRIDE",
})


ORG_SCOPED_PREFIXES = ("cvc_", "asaas_", "rextur_")


def run_check() -> int:
    catalog = load_catalog(CATALOG_PATH)
    if GENERATED_CATALOG_PATH.is_file():
        catalog = {**load_catalog(GENERATED_CATALOG_PATH), **catalog}

    findings = scan(WORKSPACE)

    missing_in_catalog: list[str] = []
    for var in sorted(findings):
        if var in catalog or var in IGNORE_VARS:
            continue
        if any(var.lower().startswith(p) for p in ORG_SCOPED_PREFIXES):
            continue
        if var.startswith("CYPRESS_"):
            continue
        missing_in_catalog.append(var)

    warnings: list[str] = []
    if missing_in_catalog:
        warnings.append(
            f"{len(missing_in_catalog)} code refs not in catalog: "
            + ", ".join(missing_in_catalog[:15])
            + ("..." if len(missing_in_catalog) > 15 else "")
        )

    for var_name, meta in catalog.items():
        required_in = meta.get("required_in") or []
        if not required_in:
            continue
        if meta.get("secret"):
            continue

    print("=" * 60)
    print("check_env_catalog")
    print("=" * 60)
    if warnings:
        for w in warnings:
            print(f"WARN: {w}")
        return 1
    print("OK: catalog covers discovered code references")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_check())
