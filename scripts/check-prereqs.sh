#!/usr/bin/env bash
# POSIX shim that dispatches to scripts/check_prereqs.py.
# Verifies Python is on PATH first; otherwise prints a clear install hint
# and exits non-zero before attempting to invoke the .py script.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_SCRIPT="${SCRIPT_DIR}/check_prereqs.py"

if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
else
    echo "[fail] No python interpreter on PATH." >&2
    echo "Install Python 3.13+ from https://python.org and rerun this script." >&2
    exit 1
fi

exec "${PYTHON_BIN}" "${PY_SCRIPT}" "$@"
