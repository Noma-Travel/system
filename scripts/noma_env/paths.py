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

_SKIP_DIR_NAMES = {"node_modules", ".git", "venv", ".venv", "__pycache__", ".next", "dist", "build"}


def _find_git_repo(name: str, fallback: Path, max_parent_hops: int = 2, max_child_depth: int = 2) -> Path:
    """Locate a sibling git repo by directory name, searching outward from SYSTEM_DIR.

    Looks at SYSTEM_DIR and up to `max_parent_hops` ancestors; from each of those,
    walks down up to `max_child_depth` levels of subdirectories for a folder that
    both matches `name` (case-insensitive) and is a git repo (has a `.git` entry).
    Falls back to `fallback` if nothing is found, so callers still get a Path.
    """
    target = name.lower()
    anchors = [SYSTEM_DIR]
    node = SYSTEM_DIR
    for _ in range(max_parent_hops):
        if node.parent == node:
            break
        node = node.parent
        anchors.append(node)

    def scan(directory: Path, depth: int) -> Path | None:
        try:
            children = sorted(directory.iterdir())
        except OSError:
            return None
        for child in children:
            if not child.is_dir() or child.name in _SKIP_DIR_NAMES:
                continue
            if child.name.lower() == target and (child / ".git").exists():
                return child
            if depth < max_child_depth:
                found = scan(child, depth + 1)
                if found is not None:
                    return found
        return None

    for anchor in anchors:
        found = scan(anchor, 1)
        if found is not None:
            return found
    return fallback


def _find_backend_package() -> Path:
    """Locate extensions/backend package dir (must contain noma/ handlers)."""
    fallback = WORKSPACE_ROOT / "extensions" / "backend" / "package"
    backend_repo = _find_git_repo("backend", fallback=WORKSPACE_ROOT / "extensions" / "backend")
    package = backend_repo / "package"
    if package.is_dir() and (package / "noma").is_dir():
        return package
    if fallback.is_dir() and (fallback / "noma").is_dir():
        return fallback
    return package if package.is_dir() else fallback


NOMA_DIR = _find_git_repo("noma", fallback=WORKSPACE_ROOT / "NOMA")
CONSOLE_DIR = _find_git_repo("console", fallback=WORKSPACE_ROOT / "console")
RENGLO_API_DIR = _find_git_repo("renglo-api", fallback=WORKSPACE_ROOT / "dev" / "renglo-api")
RENGLO_LIB_DIR = _find_git_repo("renglo-lib", fallback=WORKSPACE_ROOT / "dev" / "renglo-lib")
BACKEND_EXT_DIR = _find_git_repo("backend", fallback=WORKSPACE_ROOT / "extensions" / "backend")
NOMA_PACKAGE_DIR = _find_backend_package()
WSS_DIR = _find_git_repo("wss", fallback=WORKSPACE_ROOT / "extensions" / "wss")

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
