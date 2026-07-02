#!/usr/bin/env python3
"""Print resolved env vars per scenario (secrets masked) for manual review."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from noma_env.envgen import generate, resolve  # noqa: E402

SCENARIOS = [
    ("staging + local (noma+backend)", "staging", "local", ["noma", "backend"]),
    ("staging + local (full stack)", "staging", "local", ["noma", "console", "backend"]),
    ("staging + staging (console only)", "staging", "staging", ["console"]),
    ("prod + local (noma only)", "prod", "local", ["noma"]),
    ("prod + prod (noma+console)", "prod", "prod", ["noma", "console"]),
    ("prod + local (backend only)", "prod", "local", ["backend"]),
]

SECRET_SUBSTRINGS = ("KEY", "SECRET", "PASSWORD", "TOKEN", "PROXY", "WEBHOOK")


def mask(key: str, value: str) -> str:
    if not value:
        return "(empty)"
    upper = key.upper()
    if any(s in upper for s in SECRET_SUBSTRINGS):
        return f"*** ({len(value)} chars)"
    if len(value) > 80:
        return value[:77] + "..."
    return value


def show_vars(merged: dict[str, str], keys: list[str]) -> None:
    for key in keys:
        print(f"    {key}={mask(key, merged.get(key, ''))}")


KEY_GROUPS = {
    "auth": [
        "COGNITO_USERPOOL_ID",
        "COGNITO_APP_CLIENT_ID",
        "COGNITO_REGION",
        "NEXT_PUBLIC_AWS_USER_POOL_ID",
        "NEXT_PUBLIC_AWS_USER_POOL_CLIENT_ID",
        "VITE_COGNITO_USERPOOL_ID",
        "VITE_COGNITO_APP_CLIENT_ID",
    ],
    "routing": [
        "BASE_URL",
        "NEXT_PUBLIC_API_BASE_URL",
        "VITE_API_URL",
        "WEBSOCKET_CONNECTIONS",
        "NEXT_PUBLIC_CHAT_WS",
        "VITE_WEBSOCKET_URL",
    ],
    "backend": [
        "DYNAMODB_ENTITY_TABLE",
        "SYS_ENV",
        "ALLOW_DEV_ORIGINS",
        "WL_NAME",
    ],
    "secrets": [
        "CSRF_SESSION_KEY",
        "SECRET_KEY",
        "OPENAI_API_KEY",
        "RESEND_API_KEY",
        "CVC_CLIENT_SECRET",
    ],
}


def main() -> int:
    print("=" * 70)
    print("noma env scenarios (fetch_sm=True, dry_run=True)")
    print("Command equivalent: python scripts/run.py <apps> env:<env> handler:<handler>")
    print("=" * 70)

    for label, env, handler, apps in SCENARIOS:
        print()
        print(f"## {label}")
        apps_s = " ".join(apps)
        print(f"    run {apps_s} env:{env} handler:{handler}")
        result = resolve(env, handler, fetch_sm=True)
        merged = result.merged
        if result.warnings:
            for w in result.warnings:
                print(f"    WARN: {w}")
        for group_name, keys in KEY_GROUPS.items():
            print(f"  [{group_name}]")
            show_vars(merged, keys)

    print()
    print("=" * 70)
    print("Done. Secrets are masked; lengths shown only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
