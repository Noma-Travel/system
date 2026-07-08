"""Prepare command to start the local WebSocket dev service (extensions/wss)."""

from __future__ import annotations

from pathlib import Path

from noma_env.paths import WSS_DIR

WSS_SCRIPT = WSS_DIR / "dev_ws_service.py"


def wss_python() -> Path | None:
    """Python interpreter inside the wss-venv, or None if the venv is missing."""
    windows_python = WSS_DIR / "wss-venv" / "Scripts" / "python.exe"
    if windows_python.is_file():
        return windows_python
    unix_python = WSS_DIR / "wss-venv" / "bin" / "python"
    if unix_python.is_file():
        return unix_python
    return None


def can_start_wss() -> tuple[bool, str]:
    """Check WSS prerequisites; returns (ok, reason-if-not)."""
    if not WSS_DIR.is_dir():
        return False, f"wss repo not found (expected at {WSS_DIR}); clone it to enable local WebSocket"
    if not WSS_SCRIPT.is_file():
        return False, f"{WSS_SCRIPT} not found; update the wss repo"
    if wss_python() is None:
        return False, (
            f"wss-venv not found in {WSS_DIR}; create it with "
            "'python -m venv wss-venv' and 'pip install -r requirements.txt'"
        )
    return True, ""


def wss_command() -> list[str] | None:
    """Command to run the local WSS service, or None if prerequisites are missing."""
    ok, _ = can_start_wss()
    if not ok:
        return None
    return [str(wss_python()), str(WSS_SCRIPT)]
