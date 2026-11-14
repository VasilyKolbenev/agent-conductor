"""Portable collectors leave Windows backends behind their existing native-use gates."""
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
COLLECTORS = (
    "tests.os_boundary_box",
    "tests.test_kimi_home_loan_native",
    "tests.test_kimi_read_config_native",
    "tests.test_kimi_session_state_native",
    "tests.test_kimi_state_journal_native",
    "tests.test_kimi_read_role_policy",
    "tests.test_patch_do_native",
)
BLOCKER = """
import importlib
import importlib.abc
import sys

blocked = {"tests.os_boundary_windows", "conductor.command.adapters._winlaunch"}
attempts = []
assert not blocked.intersection(sys.modules), "native backend was already imported"

class UnavailableWindows(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in blocked:
            attempts.append(fullname)
            raise ImportError("blocked native dependency: " + fullname)

sys.meta_path.insert(0, UnavailableWindows())
"""


def isolated(source, *arguments):
    result = subprocess.run(
        [sys.executable, "-c", BLOCKER + source, *arguments], cwd=ROOT,
        capture_output=True, timeout=30, check=False)
    assert result.returncode == 0, (result.stdout + result.stderr).decode(
        "utf-8", errors="backslashreplace")
    return result.stdout.splitlines()


@pytest.mark.parametrize("collector", COLLECTORS)
def test_portable_collector_does_not_load_windows_backends(collector):
    assert isolated("""
module = importlib.import_module(sys.argv[1])
assert module.__name__ == sys.argv[1]
assert attempts == [], attempts
print("imported " + module.__name__)
""", collector) == [("imported " + collector).encode()]


def test_native_use_still_refuses_when_windows_backend_is_unavailable():
    assert isolated("""
from tests.os_boundary_box import powershell_line
assert attempts == [], attempts
try:
    powershell_line("exit 0")
except ImportError as error:
    assert str(error) == "blocked native dependency: tests.os_boundary_windows", str(error)
else:
    raise AssertionError("native use silently accepted an unavailable Windows backend")
assert attempts == ["tests.os_boundary_windows"], attempts
print("native use refused")
""") == [b"native use refused"]
