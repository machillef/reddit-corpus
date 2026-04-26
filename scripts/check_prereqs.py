#!/usr/bin/env python3
"""Pre-flight check for reddit-corpus.

Verifies Python >= 3.13 and that `uv` is on PATH. On failure, prints an
OS-specific install hint and exits non-zero. Stdlib-only on purpose so the
user can run it before `uv sync`.

Run directly:
    python3 scripts/check_prereqs.py
"""

from __future__ import annotations

import platform
import shutil
import sys

MIN_PYTHON: tuple[int, int, int] = (3, 13, 0)


def python_version_ok(version: tuple[int, int, int]) -> bool:
    """True if `version` meets MIN_PYTHON."""
    return version >= MIN_PYTHON


def current_python_version() -> tuple[int, int, int]:
    return sys.version_info[:3]


def uv_available() -> bool:
    return shutil.which("uv") is not None


def current_system() -> str:
    return platform.system()


def install_hint_python(system: str) -> str:
    base = "Install Python 3.13+ from https://python.org"
    if system == "Windows":
        return f"{base} (or `winget install Python.Python.3.13`)."
    if system == "Darwin":
        return f"{base} (or `brew install python@3.13`)."
    return f"{base} (or use your distro's package manager / pyenv)."


def install_hint_uv(system: str) -> str:
    if system == "Windows":
        return 'Install uv: powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"'
    return "Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh"


def run() -> int:
    """Run the pre-flight check. Return 0 on success, 1 on any missing prereq."""
    failures: list[str] = []
    system = current_system()

    py = current_python_version()
    if python_version_ok(py):
        print(f"[ok] Python {py[0]}.{py[1]}.{py[2]} (>= 3.13)")
    else:
        msg = (
            f"[fail] Python {py[0]}.{py[1]}.{py[2]} is too old; need >= 3.13. "
            f"{install_hint_python(system)}"
        )
        print(msg, file=sys.stderr)
        failures.append("python")

    if uv_available():
        print("[ok] uv is on PATH")
    else:
        msg = f"[fail] uv is not on PATH. {install_hint_uv(system)}"
        print(msg, file=sys.stderr)
        failures.append("uv")

    if failures:
        print(f"\nMissing prerequisites: {', '.join(failures)}", file=sys.stderr)
        return 1

    print("\nAll prerequisites satisfied. Run `uv sync` next.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
