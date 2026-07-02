"""Prepare environment and command to start the local Flask backend."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from noma_env.paths import SYSTEM_DIR, WORKSPACE_ROOT


def build_backend_env(
    aws_profile: str = "noma",
    aws_region: str = "us-east-1",
) -> dict[str, str]:
    env = os.environ.copy()
    env["AWS_PROFILE"] = aws_profile
    env["AWS_DEFAULT_REGION"] = aws_region

    dev_api = WORKSPACE_ROOT / "dev" / "renglo-api"
    dev_lib = WORKSPACE_ROOT / "dev" / "renglo-lib"
    noma_pkg = WORKSPACE_ROOT / "extensions" / "backend" / "package"

    parts: list[str] = []
    if noma_pkg.is_dir():
        parts.append(str(noma_pkg))
    if dev_api.is_dir():
        parts.append(str(dev_api))
    if dev_lib.is_dir():
        parts.append(str(dev_lib))

    if parts:
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = os.pathsep.join(parts + ([existing] if existing else []))

    return env


def backend_python() -> Path:
    venv_python = SYSTEM_DIR / "venv" / "Scripts" / "python.exe"
    if venv_python.is_file():
        return venv_python
    unix_venv = SYSTEM_DIR / "venv" / "bin" / "python"
    if unix_venv.is_file():
        return unix_venv
    return Path(sys.executable)


def backend_command() -> list[str]:
    return [str(backend_python()), str(SYSTEM_DIR / "main.py")]
