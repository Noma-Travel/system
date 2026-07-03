#!/usr/bin/env python3
"""Extract secret env vars from Zappa settings and publish to AWS Secrets Manager."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SYSTEM_DIR = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from noma_env.paths import normalize_env, secret_id  # noqa: E402

# Keys stored in SM (not in versioned profiles)
SECRET_KEYS = frozenset({
    "CSRF_SESSION_KEY",
    "SECRET_KEY",
    "OPENAI_API_KEY",
    "RESEND_API_KEY",
    "AVIATION_STACK_API_KEY",
    "NEXT_PUBLIC_MS_CLIENT_SECRET",
    "TOKENS_KMS_KEY_ID",
    "RATEHAWK_HTTPS_PROXY",
    "CVC_CLIENT_SECRET",
    "CVC_USERNAME",
    "CVC_PASSWORD",
    "SLACK_API_ERRORS_WEBHOOK_URL",
    "SLACK_BOOKINGS_WEBHOOK_URL",
    "SLACK_ACTIVE_TRAVELS_WEBHOOK_URL",
    "ASAAS_API_KEY",
})

ZAPPA_FILES = {
    "staging": SYSTEM_DIR / "zappa_settings_staging.json",
    "production": SYSTEM_DIR / "zappa_settings.json",
}


def _zappa_stage_key(env: str) -> str:
    return "noma_staging" if env == "staging" else "noma_prod"


def extract_secrets_from_zappa(env: str) -> dict[str, str]:
    env_norm = normalize_env(env)
    zappa_path = ZAPPA_FILES[env_norm]
    if not zappa_path.is_file():
        raise FileNotFoundError(f"Zappa settings not found: {zappa_path}")

    data = json.loads(zappa_path.read_text(encoding="utf-8"))
    stage_key = _zappa_stage_key(env_norm)
    stage = data.get(stage_key) or {}
    env_vars = stage.get("environment_variables") or {}

    secrets: dict[str, str] = {}
    for key in SECRET_KEYS:
        value = env_vars.get(key)
        if value is not None and str(value).strip():
            secrets[key] = str(value)
    return secrets


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Zappa secrets to AWS SM")
    parser.add_argument("env", choices=["staging", "prod", "production"])
    parser.add_argument("--profile", default="noma")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    env = normalize_env(args.env)
    payload = extract_secrets_from_zappa(env)
    sid = secret_id(env)

    print(f"Extracted {len(payload)} secret keys for {env} from Zappa")
    print(f"Target: {sid}")
    if args.dry_run:
        print("Keys:", ", ".join(sorted(payload)))
        return 0

    from publish_env_secret import put_secret_payload

    put_secret_payload(env, payload, region=args.region, profile=args.profile)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
