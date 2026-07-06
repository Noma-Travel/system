"""Load YAML config fragments."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}")
    return data


def load_flat_yaml(path: Path) -> dict[str, str]:
    """Load simple key: value yaml (profiles, handler overrides)."""
    raw = load_yaml(path)
    flat: dict[str, str] = {}
    for key, value in raw.items():
        if key.startswith("#") or value is None:
            continue
        flat[str(key)] = str(value)
    return flat


def load_catalog(path: Path) -> dict[str, dict[str, Any]]:
    data = load_yaml(path)
    vars_block = data.get("vars", data)
    if not isinstance(vars_block, dict):
        return {}
    return {str(k): v if isinstance(v, dict) else {} for k, v in vars_block.items()}


def load_mappings(path: Path) -> dict[str, dict[str, str]]:
    data = load_yaml(path)
    result: dict[str, dict[str, str]] = {}
    for canonical, targets in data.items():
        if not isinstance(targets, dict):
            continue
        result[str(canonical)] = {str(app): str(var) for app, var in targets.items()}
    return result
