"""
Patch Zappa's create_handler_venv() for Windows + modern pip:

1. subprocess.Popen must use stderr=PIPE or communicate() returns None for stderr.
2. Guard stderr logging when stderr is None (older Zappa builds).
3. pip refuses `pip install pip==... --target <dir>` on Windows; drop pip from pkg_list.
"""
from __future__ import annotations

import pathlib
import sys


def main() -> int:
    try:
        import zappa
    except ImportError:
        print("patch_zappa_handler_venv: zappa not installed, skip", file=sys.stderr)
        return 0

    core = pathlib.Path(zappa.__file__).resolve().parent / "core.py"
    text = core.read_text(encoding="utf-8")
    orig = text

    old_popen = "pip_process = subprocess.Popen(command, stdout=subprocess.PIPE)"
    new_popen = (
        "pip_process = subprocess.Popen("
        "command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)"
    )
    if old_popen in text:
        text = text.replace(old_popen, new_popen, 1)

    needle = '        pkg_list.append("setuptools")'
    inject = (
        '        pkg_list.append("setuptools")\n'
        '        pkg_list = [p for p in pkg_list if p.split("==", 1)[0].lower() != "pip"]'
    )
    if needle in text and "pkg_list = [p for p in pkg_list if p.split" not in text:
        text = text.replace(needle, inject, 1)

    # Older Zappa: bare stderror_result.strip() when stderr is None
    text = text.replace(
        "if stderror_result.strip():",
        "if stderror_result is not None and stderror_result.strip():",
    )

    if text == orig:
        print(f"patch_zappa_handler_venv: no changes needed: {core}")
        return 0

    core.write_text(text, encoding="utf-8")
    print(f"patch_zappa_handler_venv: patched {core}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
