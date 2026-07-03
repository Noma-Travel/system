"""Spawn dev processes in separate terminal windows when possible."""

from __future__ import annotations

import logging
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger("run")

CREATE_NEW_CONSOLE = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)


def _spawn_same_terminal(
    name: str,
    cmd: list[str],
    cwd: Path,
    env: dict[str, str] | None,
) -> subprocess.Popen:
    logger.info("[%s] %s", name, " ".join(cmd))
    return subprocess.Popen(cmd, cwd=str(cwd), env=env, shell=False)


def _spawn_windows_console(
    name: str,
    cmd: list[str],
    cwd: Path,
    env: dict[str, str] | None,
) -> subprocess.Popen:
    title = f"noma-{name}"
    # cmd /c keeps a single supervisable process while setting the window title.
    inner = subprocess.list2cmdline(cmd)
    wrapped = ["cmd", "/c", f"title {title} && {inner}"]
    logger.info("[%s] new window: %s", name, " ".join(cmd))
    return subprocess.Popen(
        wrapped,
        cwd=str(cwd),
        env=env,
        shell=False,
        creationflags=CREATE_NEW_CONSOLE,
    )


def _spawn_macos_terminal(
    name: str,
    cmd: list[str],
    cwd: Path,
    env: dict[str, str] | None,
) -> subprocess.Popen | None:
    inner = " ".join(shlex.quote(part) for part in cmd)
    cwd_q = shlex.quote(str(cwd))
    env_exports = ""
    if env:
        for key, value in env.items():
            if key not in os.environ or os.environ[key] != value:
                env_exports += f"export {key}={shlex.quote(value)}; "
    script = f"cd {cwd_q}; {env_exports}{inner}; exec bash"
    osa = shutil.which("osascript")
    if not osa:
        return None
    logger.info("[%s] new Terminal window: %s", name, " ".join(cmd))
    return subprocess.Popen(
        [osa, "-e", f'tell application "Terminal" to do script "{script}"'],
        shell=False,
    )


def _spawn_linux_terminal(
    name: str,
    cmd: list[str],
    cwd: Path,
    env: dict[str, str] | None,
) -> subprocess.Popen | None:
    title = f"noma-{name}"
    inner = " ".join(shlex.quote(part) for part in cmd)
    cwd_q = shlex.quote(str(cwd))
    env_exports = ""
    if env:
        for key, value in env.items():
            if key not in os.environ or os.environ[key] != value:
                env_exports += f"export {key}={shlex.quote(value)}; "
    script = f"cd {cwd_q}; {env_exports}{inner}; exec bash"

    terminal = os.environ.get("TERMINAL")
    candidates: list[list[str]] = []
    if terminal:
        candidates.append([terminal, "-e", "bash", "-lc", script])
    if shutil.which("gnome-terminal"):
        candidates.append(["gnome-terminal", f"--title={title}", "--", "bash", "-lc", script])
    if shutil.which("konsole"):
        candidates.append(["konsole", "--new-tab", "-p", f"tabtitle={title}", "-e", "bash", "-lc", script])
    if shutil.which("xterm"):
        candidates.append(["xterm", "-T", title, "-e", "bash", "-lc", script])

    for candidate in candidates:
        try:
            logger.info("[%s] new window (%s): %s", name, candidate[0], " ".join(cmd))
            return subprocess.Popen(candidate, shell=False)
        except OSError:
            continue
    return None


def spawn_in_terminal(
    name: str,
    cmd: list[str],
    cwd: Path,
    env: dict[str, str] | None = None,
    *,
    same_terminal: bool = False,
) -> subprocess.Popen:
    """Start cmd in a new terminal window, or the current one if requested/unavailable."""
    if same_terminal:
        return _spawn_same_terminal(name, cmd, cwd, env)

    proc: subprocess.Popen | None = None
    if sys.platform == "win32":
        proc = _spawn_windows_console(name, cmd, cwd, env)
    elif sys.platform == "darwin":
        proc = _spawn_macos_terminal(name, cmd, cwd, env)
    else:
        proc = _spawn_linux_terminal(name, cmd, cwd, env)

    if proc is None:
        logger.warning("[%s] no terminal emulator found; running in this terminal", name)
        return _spawn_same_terminal(name, cmd, cwd, env)
    return proc
