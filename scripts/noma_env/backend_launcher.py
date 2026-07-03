"""Prepare environment and command to start the local Flask backend."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from noma_env.paths import NOMA_PACKAGE_DIR, RENGLO_API_DIR, RENGLO_LIB_DIR, SYSTEM_DIR


def build_backend_env(
    aws_profile: str = "noma",
    aws_region: str = "us-east-1",
) -> dict[str, str]:
    env = os.environ.copy()
    env["AWS_PROFILE"] = aws_profile
    env["AWS_DEFAULT_REGION"] = aws_region

    parts: list[str] = []
    if NOMA_PACKAGE_DIR.is_dir():
        parts.append(str(NOMA_PACKAGE_DIR))
    if RENGLO_API_DIR.is_dir():
        parts.append(str(RENGLO_API_DIR))
    if RENGLO_LIB_DIR.is_dir():
        parts.append(str(RENGLO_LIB_DIR))

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
