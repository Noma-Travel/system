#!/usr/bin/env python3
"""Orchestrate env generation and local dev processes for NOMA stack."""

from __future__ import annotations

import argparse
import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from noma_env.backend_launcher import backend_command, build_backend_env
from noma_env.envgen import default_handler_for_apps, generate
from noma_env.paths import CONSOLE_DIR, NOMA_DIR, SYSTEM_DIR, VALID_APPS, normalize_env
from noma_env.terminal_spawn import spawn_in_terminal

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("run")


def parse_run_args(argv: list[str]) -> tuple[list[str], str | None, str | None]:
    apps: list[str] = []
    env_value: str | None = None
    handler_value: str | None = None

    for token in argv:
        if token.startswith("env:"):
            env_value = token.split(":", 1)[1]
        elif token.startswith("handler:"):
            handler_value = token.split(":", 1)[1]
        elif token in VALID_APPS:
            apps.append(token)
        else:
            raise SystemExit(f"Unknown token: {token}")

    if not apps:
        raise SystemExit("Specify at least one app: noma, console, backend")
    if not env_value:
        raise SystemExit("env:staging or env:prod is required")

    return apps, env_value, handler_value


def print_banner(env: str, handler: str, apps: list[str]) -> None:
    logger.info("=" * 60)
    logger.info("noma run  env=%s  handler=%s  apps=%s", env, handler, ",".join(apps))
    logger.info("=" * 60)


def spawn_process(name: str, cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.Popen:
    logger.info("[%s] %s", name, " ".join(cmd))
    return subprocess.Popen(
        cmd,
        cwd=str(cwd),
        env=env,
        shell=False,
    )


# Dev ports each app binds to. Freed automatically before launch so a stale
# process from a previous run never forces the app onto a different port.
APP_PORTS: dict[str, int] = {"noma": 3000, "console": 5174, "backend": 5001}


def free_ports(apps: list[str]) -> None:
    """Kill whatever is holding the ports of the apps we are about to launch."""
    if sys.platform == "win32":
        return  # run.ps1 handles the Windows path
    for app in apps:
        port = APP_PORTS.get(app)
        if not port:
            continue
        try:
            result = subprocess.run(
                ["lsof", "-ti", f"tcp:{port}"],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            logger.warning("lsof not found; cannot free port %s for %s", port, app)
            continue
        for pid in result.stdout.split():
            try:
                os.kill(int(pid), signal.SIGKILL)
                logger.info("freed port %s (killed pid %s) for %s", port, pid, app)
            except (ProcessLookupError, ValueError, PermissionError):
                pass


def run_dev_processes(apps: list[str]) -> int:
    free_ports(apps)
    children: list[tuple[str, subprocess.Popen]] = []

    def shutdown(_signum=None, _frame=None) -> None:
        for name, proc in children:
            if proc.poll() is None:
                logger.info("[%s] stopping", name)
                proc.terminate()
        for name, proc in children:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    signal.signal(signal.SIGINT, shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, shutdown)

    spawn = lambda name, cmd, cwd, env=None: spawn_in_terminal(
        name, cmd, cwd, env, same_terminal=same_terminal
    )

    if "backend" in apps:
        children.append(
            (
                "backend",
                spawn("backend", backend_command(), SYSTEM_DIR, build_backend_env()),
            )
        )
    if "console" in apps:
        children.append(("console", spawn("console", ["npm", "run", "dev"], CONSOLE_DIR)))
    if "noma" in apps:
        children.append(("noma", spawn("noma", ["npm", "run", "dev"], NOMA_DIR)))

    if not children:
        return 0

    if not same_terminal:
        started = ", ".join(name for name, _ in children)
        logger.info("Started in separate windows: %s", started)
        logger.info("Press Ctrl+C in this terminal to stop all apps")

    exit_code = 0
    try:
        while True:
            for name, proc in children:
                code = proc.poll()
                if code is not None and code != 0:
                    logger.error("[%s] exited with %s", name, code)
                    exit_code = code
                    shutdown()
                    return exit_code
            if all(proc.poll() is not None for _, proc in children):
                break
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown()
    return exit_code


def cmd_run(argv: list[str], *, same_terminal: bool = False) -> int:
    apps, env_raw, handler_raw = parse_run_args(argv)
    app_set = set(apps)
    env_norm = normalize_env(env_raw)
    handler_norm = (
        __import__("noma_env.paths", fromlist=["normalize_handler"]).normalize_handler(handler_raw)
        if handler_raw
        else default_handler_for_apps(env_norm, app_set)
    )

    print_banner(env_norm, handler_norm, apps)
    result = generate(env_norm, handler_norm, apps)
    for warning in result.warnings:
        logger.warning(warning)
    for path in result.written:
        logger.info("wrote %s", path)

    return run_dev_processes(apps, same_terminal=same_terminal)


def cmd_check() -> int:
    from check_env_catalog import run_check

    return run_check()


def cmd_verify(argv: list[str]) -> int:
    from verify_env_run import run_verify

    return run_verify(argv)


def main() -> int:
    parser = argparse.ArgumentParser(description="Noma local dev orchestrator")
    parser.add_argument("tokens", nargs="*", help="e.g. noma console backend env:staging handler:local")
    parser.add_argument("--check", action="store_true", help="Validate catalog drift only")
    parser.add_argument("--verify", action="store_true", help="Run env generation verification matrix")
    parser.add_argument(
        "--same-terminal",
        action="store_true",
        help="Run all apps in this terminal instead of separate windows",
    )
    args = parser.parse_args()

    if args.check:
        return cmd_check()
    if args.verify:
        return cmd_verify(args.tokens)
    if not args.tokens:
        parser.print_help()
        return 1
    return cmd_run(args.tokens, same_terminal=args.same_terminal)


if __name__ == "__main__":
    if sys.platform == "win32":
        # signal.pause not available; sleep loop in run_dev_processes handles it
        pass
    raise SystemExit(main())
