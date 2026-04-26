"""Unit tests for scripts/check_prereqs.py.

The script is a stdlib-only pre-flight check that verifies Python >= 3.13 and that
`uv` is available on PATH. On failure it emits an OS-specific install hint and exits
non-zero. Tests are hermetic: no real PATH lookups, no real version probes.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "check_prereqs.py"


def _load_module():
    """Load scripts/check_prereqs.py as a fresh module each call."""
    spec = importlib.util.spec_from_file_location("check_prereqs", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def cp():
    return _load_module()


def test_python_version_ok_above_threshold(cp):
    """A 3.13.x version satisfies the check."""
    assert cp.python_version_ok((3, 13, 0))
    assert cp.python_version_ok((3, 14, 1))
    assert cp.python_version_ok((4, 0, 0))


def test_python_version_ok_below_threshold(cp):
    """A 3.12 or earlier version fails the check."""
    assert not cp.python_version_ok((3, 12, 9))
    assert not cp.python_version_ok((3, 0, 0))
    assert not cp.python_version_ok((2, 7, 18))


def test_install_hint_for_python_mentions_python_org(cp):
    """The Python install hint must point users at python.org regardless of OS."""
    assert "python.org" in cp.install_hint_python("Linux").lower()
    assert "python.org" in cp.install_hint_python("Darwin").lower()
    assert "python.org" in cp.install_hint_python("Windows").lower()


def test_install_hint_for_uv_linux_macos_uses_curl(cp):
    """Linux and macOS get the upstream `astral.sh/uv/install.sh` curl line."""
    for system in ("Linux", "Darwin"):
        hint = cp.install_hint_uv(system)
        assert "curl" in hint
        assert "astral.sh" in hint


def test_install_hint_for_uv_windows_uses_powershell(cp):
    """Windows gets the upstream PowerShell `irm` line."""
    hint = cp.install_hint_uv("Windows")
    assert "powershell" in hint.lower() or "irm" in hint.lower()
    assert "astral.sh" in hint


def test_run_returns_zero_when_all_prereqs_present(cp, monkeypatch):
    """Happy path: real Python + uv → exit 0, success message printed."""
    monkeypatch.setattr(cp, "current_python_version", lambda: (3, 13, 1))
    monkeypatch.setattr(cp, "uv_available", lambda: True)
    monkeypatch.setattr(cp, "current_system", lambda: "Linux")
    rc = cp.run()
    assert rc == 0


def test_run_returns_nonzero_when_python_too_old(cp, monkeypatch, capsys):
    """Old Python fails the check and surfaces the python.org hint."""
    monkeypatch.setattr(cp, "current_python_version", lambda: (3, 12, 0))
    monkeypatch.setattr(cp, "uv_available", lambda: True)
    monkeypatch.setattr(cp, "current_system", lambda: "Darwin")
    rc = cp.run()
    captured = capsys.readouterr()
    assert rc != 0
    assert "python.org" in (captured.out + captured.err).lower()


def test_run_returns_nonzero_when_uv_missing_linux(cp, monkeypatch, capsys):
    """Missing `uv` on Linux surfaces the curl install hint."""
    monkeypatch.setattr(cp, "current_python_version", lambda: (3, 13, 1))
    monkeypatch.setattr(cp, "uv_available", lambda: False)
    monkeypatch.setattr(cp, "current_system", lambda: "Linux")
    rc = cp.run()
    captured = capsys.readouterr()
    assert rc != 0
    assert "curl" in (captured.out + captured.err)
    assert "astral.sh" in (captured.out + captured.err)


def test_run_returns_nonzero_when_uv_missing_windows(cp, monkeypatch, capsys):
    """Missing `uv` on Windows surfaces the PowerShell install hint."""
    monkeypatch.setattr(cp, "current_python_version", lambda: (3, 13, 1))
    monkeypatch.setattr(cp, "uv_available", lambda: False)
    monkeypatch.setattr(cp, "current_system", lambda: "Windows")
    rc = cp.run()
    captured = capsys.readouterr()
    out = (captured.out + captured.err).lower()
    assert rc != 0
    assert "irm" in out or "powershell" in out


def test_uv_available_uses_shutil_which(cp, monkeypatch):
    """Verify uv_available delegates to shutil.which (boundary check)."""
    import shutil

    monkeypatch.setattr(
        shutil, "which", lambda name: "/usr/local/bin/uv" if name == "uv" else None
    )
    assert cp.uv_available() is True
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert cp.uv_available() is False


def test_current_python_version_matches_sys(cp):
    """Sanity: the helper returns the live interpreter's version."""
    expected = sys.version_info[:3]
    assert cp.current_python_version() == expected
