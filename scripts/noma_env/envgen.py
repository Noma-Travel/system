"""Resolve and write environment files for noma/console/backend."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from noma_env.loader import load_catalog, load_flat_yaml, load_mappings
from noma_env.paths import (
    BACKEND_ENV_CONFIG,
    BACKEND_ENV_DEVELOPMENT,
    CATALOG_PATH,
    CONSOLE_ENV,
    LOCAL_OVERRIDE_PATH,
    MAPPINGS_PATH,
    NOMA_ENV,
    handler_path,
    normalize_env,
    normalize_handler,
    profile_path,
    secret_id,
)
from noma_env.secrets import fetch_secrets
from noma_env.writers import write_app_files

logger = logging.getLogger(__name__)

ROUTING_KEYS = frozenset(
    {
        "BASE_URL",
        "NEXT_PUBLIC_API_BASE_URL",
        "NEXT_PUBLIC_VITE_API_URL",
        "VITE_API_URL",
        "VITE_API_PROXY_TARGET",
        "WEBSOCKET_CONNECTIONS",
        "NEXT_PUBLIC_CHAT_WS",
        "VITE_WEBSOCKET_URL",
    }
)


@dataclass
class GenerateResult:
    env: str
    handler: str
    apps: list[str]
    merged: dict[str, str]
    written: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    missing_required: list[str] = field(default_factory=list)


def _merge_dict(base: dict[str, str], overlay: dict[str, str]) -> dict[str, str]:
    result = dict(base)
    for key, value in overlay.items():
        if value is not None and str(value).strip() != "":
            result[key] = str(value)
    return result


def _apply_mappings(canonical: dict[str, str], mappings: dict[str, dict[str, str]]) -> dict[str, str]:
    out = dict(canonical)
    for source_key, targets in mappings.items():
        if source_key not in canonical or not canonical[source_key]:
            continue
        value = canonical[source_key]
        for _app, dest_key in targets.items():
            out[dest_key] = value
    return out


def _normalize_ws_urls(values: dict[str, str]) -> dict[str, str]:
    out = dict(values)
    ws_https = out.get("WEBSOCKET_CONNECTIONS", "")
    if ws_https.startswith("https://"):
        wss = "wss://" + ws_https[len("https://") :]
        out.setdefault("NEXT_PUBLIC_CHAT_WS", wss)
        out.setdefault("VITE_WEBSOCKET_URL", wss)
    return out


def _collect_required_missing(
    catalog: dict[str, dict[str, Any]],
    merged: dict[str, str],
    env: str,
) -> list[str]:
    missing: list[str] = []
    for var_name, meta in catalog.items():
        required_in = meta.get("required_in") or []
        if env not in required_in:
            continue
        if not str(merged.get(var_name, "")).strip():
            missing.append(var_name)
    return missing


def resolve(
    env: str,
    handler: str,
    *,
    catalog_path: Path = CATALOG_PATH,
    mappings_path: Path = MAPPINGS_PATH,
    local_override_path: Path = LOCAL_OVERRIDE_PATH,
    fetch_sm: bool = True,
) -> GenerateResult:
    env_norm = normalize_env(env)
    handler_norm = normalize_handler(handler)

    catalog = load_catalog(catalog_path)
    mappings = load_mappings(mappings_path)

    merged: dict[str, str] = {}
    merged = _merge_dict(merged, load_flat_yaml(profile_path(env_norm)))

    if fetch_sm:
        sm_values = fetch_secrets(secret_id(env_norm))
        if sm_values:
            merged = _merge_dict(merged, sm_values)
        else:
            logger.warning("No secrets loaded from %s", secret_id(env_norm))

    handler_file = handler_path(handler_norm)
    if handler_file.exists():
        handler_values = load_flat_yaml(handler_file)
        if handler_values:
            merged = _merge_dict(merged, handler_values)

    if local_override_path.exists():
        merged = _merge_dict(merged, load_flat_yaml(local_override_path))

    merged = _apply_mappings(merged, mappings)
    merged = _normalize_ws_urls(merged)

    if merged.get("COGNITO_REGION"):
        merged.setdefault("AWS_REGION", merged["COGNITO_REGION"])

    missing = _collect_required_missing(catalog, merged, env_norm)
    warnings: list[str] = []
    if missing:
        warnings.append(f"Missing required vars for env={env_norm}: {', '.join(missing)}")

    return GenerateResult(
        env=env_norm,
        handler=handler_norm,
        apps=[],
        merged=merged,
        warnings=warnings,
        missing_required=missing,
    )


def generate(
    env: str,
    handler: str,
    apps: list[str],
    *,
    dry_run: bool = False,
    output_roots: dict[str, Path] | None = None,
    fetch_sm: bool = True,
) -> GenerateResult:
    env_norm = normalize_env(env)
    handler_norm = normalize_handler(handler)
    app_set = {a.strip().lower() for a in apps}

    result = resolve(env_norm, handler_norm, fetch_sm=fetch_sm)
    result.apps = sorted(app_set)

    if dry_run:
        return result

    roots = output_roots or {}
    backend_config = roots.get("backend_config", BACKEND_ENV_CONFIG)
    backend_env = roots.get("backend_env", BACKEND_ENV_DEVELOPMENT)
    console_env = roots.get("console_env", CONSOLE_ENV)
    noma_env = roots.get("noma_env", NOMA_ENV)

    result.written = write_app_files(
        app_set,
        backend_config=backend_config,
        backend_env=backend_env,
        console_env=console_env,
        noma_env=noma_env,
        merged=result.merged,
    )
    return result


def default_handler_for_apps(env: str, apps: set[str]) -> str:
    if "backend" in apps:
        return "local"
    return normalize_env(env)
