#!/usr/bin/env python3
"""Verify run/envgen output for scenario matrix."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from noma_env.envgen import generate, resolve  # noqa: E402
from noma_env.loader import load_flat_yaml  # noqa: E402


SCENARIOS = [
    {
        "name": "staging+local noma,backend",
        "env": "staging",
        "handler": "local",
        "apps": ["noma", "backend"],
        "assertions": {
            "NEXT_PUBLIC_API_BASE_URL": "http://127.0.0.1:5001",
            "COGNITO_USERPOOL_ID": "us-east-1_vBbXLDESt",
            "NEXT_PUBLIC_AWS_USER_POOL_ID": "us-east-1_vBbXLDESt",
        },
    },
    {
        "name": "prod+prod noma,console",
        "env": "prod",
        "handler": "prod",
        "apps": ["noma", "console"],
        "assertions": {
            "BASE_URL": "",
            "APP_FE_BASE_URL": "https://app.travelwithnoma.com",
            "NEXT_PUBLIC_API_BASE_URL": "https://u8za3vvgbb.execute-api.us-east-1.amazonaws.com/noma_prod",
            "VITE_API_URL": "https://u8za3vvgbb.execute-api.us-east-1.amazonaws.com/noma_prod",
            "COGNITO_USERPOOL_ID": "us-east-1_yydZGkq4N",
        },
    },
    {
        "name": "staging+staging console only",
        "env": "staging",
        "handler": "staging",
        "apps": ["console"],
        "assertions": {
            "BASE_URL": "",
            "APP_FE_BASE_URL": "https://staging.travelwithnoma.com",
            "VITE_API_URL": "https://2r4dlx8qdj.execute-api.us-east-1.amazonaws.com/noma_staging",
        },
    },
    {
        "name": "prod+local noma only",
        "env": "prod",
        "handler": "local",
        "apps": ["noma"],
        "assertions": {
            "NEXT_PUBLIC_API_BASE_URL": "http://127.0.0.1:5001",
            "NEXT_PUBLIC_AWS_USER_POOL_ID": "us-east-1_yydZGkq4N",
        },
    },
    {
        "name": "staging+local backend only",
        "env": "staging",
        "handler": "local",
        "apps": ["backend"],
        "assertions": {
            "BASE_URL": "http://127.0.0.1:5001",
            "DYNAMODB_ENTITY_TABLE": "noma-staging_entities",
        },
    },
    {
        "name": "staging+local full stack files",
        "env": "staging",
        "handler": "local",
        "apps": ["noma", "console", "backend"],
        "assertions": {
            "VITE_API_URL": "http://127.0.0.1:5001",
            "NEXT_PUBLIC_API_BASE_URL": "http://127.0.0.1:5001",
            "COGNITO_USERPOOL_ID": "us-east-1_vBbXLDESt",
        },
    },
]


def _parse_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        out[key.strip()] = val.strip().strip("'").strip('"')
    return out


def _parse_env_config(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip("'").strip('"')
        if key.isupper():
            out[key] = val
    return out


def merged_from_files(tmp: Path, apps: list[str]) -> dict[str, str]:
    merged: dict[str, str] = {}
    if "backend" in apps:
        merged.update(_parse_env_config(tmp / "env_config.py"))
    if "noma" in apps:
        merged.update(_parse_dotenv(tmp / ".env.local"))
    if "console" in apps:
        merged.update(_parse_dotenv(tmp / ".env.development"))
    return merged


def run_verify(_argv: list[str]) -> int:
    failures: list[str] = []

    print("=" * 60)
    print("verify_env_run")
    print("=" * 60)

    for scenario in SCENARIOS:
        name = scenario["name"]
        apps = scenario["apps"]
        scenario_failures: list[str] = []
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            roots = {
                "backend_config": tmp / "env_config.py",
                "backend_env": tmp / "env.development",
                "console_env": tmp / ".env.development",
                "noma_env": tmp / ".env.local",
            }
            result = generate(
                scenario["env"],
                scenario["handler"],
                apps,
                dry_run=False,
                output_roots=roots,
                fetch_sm=False,
            )
            merged = result.merged
            for key, expected in scenario["assertions"].items():
                actual = merged.get(key, "")
                if actual != expected:
                    scenario_failures.append(f"{key} expected {expected!r} got {actual!r}")

            file_merged = merged_from_files(tmp, apps)
            for key, expected in scenario["assertions"].items():
                actual = file_merged.get(key, merged.get(key, ""))
                if actual != expected:
                    scenario_failures.append(
                        f"(file) {key} expected {expected!r} got {actual!r}"
                    )

        if scenario_failures:
            failures.append(f"{name}: " + "; ".join(scenario_failures))
            print(f"FAIL scenario: {name}")
        else:
            print(f"PASS scenario: {name}")

    if failures:
        print("=" * 60)
        for item in failures:
            print(f"FAIL: {item}")
        return 1

    print("OK: all scenarios passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_verify(sys.argv[1:]))
