"""Fresh import orders: a store must not initialise the adapter package."""
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize("first", [
    "run_store", "task_store", "template_store", "service", "http_api",
    "path_admission", "work_layout", "new_work_admission",
])
def test_store_and_admission_import_before_adapters_in_a_fresh_interpreter(
        tmp_path, first):
    root = Path(__file__).resolve().parents[1]
    script = '''
import importlib
from pathlib import Path
import sys
root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root / "src"))
assert "conductor.command.adapters" not in sys.modules
first = importlib.import_module("conductor.command." + sys.argv[2])
assert Path(first.__file__).resolve().is_relative_to(root / "src")
if sys.argv[2] not in ("service", "http_api"):
    assert "conductor.command.adapters" not in sys.modules
from conductor.command import work_layout
from conductor.command.adapters import harness_workspace
assert harness_workspace.work_parts is work_layout.work_parts
assert harness_workspace.work_route is work_layout.work_route
assert harness_workspace.work_parts("item") == ("work", "item")
assert harness_workspace.work_parts("item", "scope") == ("work", "_tasks", "scope", "item")
print("ok")
'''
    result = subprocess.run(
        [sys.executable, "-I", "-c", script, str(root), first],
        cwd=tmp_path, capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "ok\n"
