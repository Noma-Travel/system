#!/usr/bin/env python3
"""Scan codebase for environment variable references and emit catalog draft."""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE = SCRIPT_DIR.parent.parent

IGNORE_DIRS = {
    "node_modules",
    ".git",
    "venv",
    ".venv",
    "dist",
    "build",
    "coverage",
    ".next",
    "__pycache__",
    "cypress/videos",
    "cypress/screenshots",
}

PATTERNS = [
    (re.compile(r"os\.environ\[['\"]([A-Z][A-Z0-9_]+)['\"]"), "backend"),
    (re.compile(r"os\.environ\.get\(['\"]([A-Z][A-Z0-9_]+)['\"]"), "backend"),
    (re.compile(r"os\.getenv\(['\"]([A-Z][A-Z0-9_]+)['\"]"), "backend"),
    (re.compile(r"process\.env\.([A-Z][A-Z0-9_]+)"), "noma"),
    (re.compile(r"import\.meta\.env\.([A-Z][A-Z0-9_]+)"), "console"),
    (re.compile(r"Cypress\.env\(['\"]([A-Z0-9_]+)['\"]"), "cypress"),
]

SCAN_ROOTS = [
    WORKSPACE / "system",
    WORKSPACE / "dev" / "renglo-api",
    WORKSPACE / "dev" / "renglo-lib",
    WORKSPACE / "extensions" / "backend",
    WORKSPACE / "NOMA",
    WORKSPACE / "console",
]


def should_skip(path: Path) -> bool:
    return any(part in IGNORE_DIRS for part in path.parts)


def scan_file(path: Path, findings: dict[str, set[str]]) -> None:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return
    for pattern, consumer in PATTERNS:
        for match in pattern.finditer(text):
            var = match.group(1)
            if var in ("NODE_ENV", "PATH", "HOME", "USER"):
                continue
            findings[var].add(consumer)


def scan(base: Path) -> dict[str, set[str]]:
    findings: dict[str, set[str]] = defaultdict(set)
    for root in SCAN_ROOTS:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or should_skip(path):
                continue
            if path.suffix not in {
                ".py",
                ".ts",
                ".tsx",
                ".js",
                ".jsx",
                ".mjs",
                ".json",
                ".md",
            }:
                continue
            scan_file(path, findings)
    return findings


def emit_yaml(findings: dict[str, set[str]]) -> str:
    lines = ["# AUTO-GENERATED — review before merging into env.catalog.yaml", "vars:"]
    for var in sorted(findings):
        consumers = sorted(findings[var])
        lines.append(f"  {var}:")
        lines.append(f"    consumers: [{', '.join(consumers)}]")
        lines.append("    secret: false")
        lines.append("    required_in: []")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit env vars in Noma workspace")
    parser.add_argument(
        "-o",
        "--output",
        default=str(SCRIPT_DIR.parent / "config" / "env.catalog.generated.yaml"),
    )
    args = parser.parse_args()

    findings = scan(WORKSPACE)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(emit_yaml(findings), encoding="utf-8")

    print("=" * 60)
    print(f"Audit complete: {len(findings)} variables")
    print(f"Output: {output.resolve()}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
