"""Workspace path resolution for noma env tooling."""

from __future__ import annotations

from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = SCRIPT_DIR.parent
SYSTEM_DIR = SCRIPTS_DIR.parent
WORKSPACE_ROOT = SYSTEM_DIR.parent

CONFIG_DIR = SYSTEM_DIR / "config"
PROFILES_DIR = CONFIG_DIR / "profiles"
HANDLER_DIR = CONFIG_DIR / "handler_overrides"
CATALOG_PATH = CONFIG_DIR / "env.catalog.yaml"
MAPPINGS_PATH = CONFIG_DIR / "mappings.yaml"
LOCAL_OVERRIDE_PATH = CONFIG_DIR / "local.override.yaml"

NOMA_DIR = WORKSPACE_ROOT / "NOMA"
CONSOLE_DIR = WORKSPACE_ROOT / "console"

BACKEND_ENV_CONFIG = SYSTEM_DIR / "env_config.py"
BACKEND_ENV_DEVELOPMENT = SYSTEM_DIR / "env.development"
CONSOLE_ENV = CONSOLE_DIR / ".env.development"
NOMA_ENV = NOMA_DIR / ".env.local"

VALID_ENVS = frozenset({"staging", "production", "prod"})
VALID_HANDLERS = frozenset({"local", "staging", "production", "prod"})
VALID_APPS = frozenset({"noma", "console", "backend"})

ENV_ALIASES = {"prod": "production", "production": "production", "staging": "staging"}
HANDLER_ALIASES = {"prod": "production", "production": "production", "staging": "staging", "local": "local"}


def normalize_env(value: str) -> str:
    key = value.strip().lower()
    if key not in ENV_ALIASES:
        raise ValueError(f"Unknown env '{value}'. Use staging or prod.")
    return ENV_ALIASES[key]


def normalize_handler(value: str) -> str:
    key = value.strip().lower()
    if key not in HANDLER_ALIASES:
        raise ValueError(f"Unknown handler '{value}'. Use local, staging, or prod.")
    return HANDLER_ALIASES[key]


def profile_path(env: str) -> Path:
    return PROFILES_DIR / f"{env}.yaml"


def handler_path(handler: str) -> Path:
    name = "prod" if handler == "production" else handler
    return HANDLER_DIR / f"{name}.yaml"


def secret_id(env: str) -> str:
    return f"noma/env/{env}"
