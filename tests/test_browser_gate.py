"""The browser release gate's discipline, proven rather than promised.

Two halves. The behavioural half runs the real runner against synthetic
modules in a temporary directory and watches it do exactly what the gate
contract says: one fresh process per module, stop at the first red one, both
orders, a record for every run and full output for the failing one. The
discipline half pins what must stay absent: no retry, no rerun, no xfail and
no statistical waiver anywhere in the browser gate's sources.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from browser_tests import conftest as gate_conftest
from browser_tests import gate

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "browser_tests" / "gate.py"

_PASSING = "def test_green():\n    assert True\n"
_FAILING = "def test_red():\n    assert False, 'deliberate'\n"


def _run_gate(tmp_path: Path, *flags: str) -> tuple[int, dict]:
    modules = tmp_path / "modules"
    modules.mkdir(exist_ok=True)
    (modules / "test_a_first.py").write_text(_PASSING, encoding="utf-8")
    (modules / "test_m_middle.py").write_text(_FAILING, encoding="utf-8")
    (modules / "test_z_last.py").write_text(_PASSING, encoding="utf-8")
    artifacts = tmp_path / "artifacts"
    completed = subprocess.run(
        [sys.executable, "-m", "browser_tests.gate",
         "--modules-dir", str(modules), "--artifacts", str(artifacts),
         "--skip-version-probe", *flags],
        capture_output=True, text=True, cwd=str(ROOT), check=False)
    report = json.loads((artifacts / "gate.json").read_text(encoding="utf-8"))
    return completed.returncode, report


def test_the_gate_stops_at_the_first_red_module_and_records_everything(
        tmp_path: Path) -> None:
    code, report = _run_gate(tmp_path)
    assert code == 1 and report["result"] == "red"
    assert [row["module"] for row in report["records"]] == [
        "test_a_first.py", "test_m_middle.py"]
    failing = report["records"][-1]
    assert failing["exit_code"] != 0
    assert len(failing["failed_nodes"]) == 1
    assert failing["failed_nodes"][0].endswith("test_m_middle.py::test_red")
    assert (tmp_path / "artifacts" / "test_m_middle.stdout.txt").exists()
    assert (tmp_path / "artifacts" / "test_m_middle.stderr.txt").exists()
    # The green module leaves a record but no output dump.
    assert not (tmp_path / "artifacts" / "test_a_first.stdout.txt").exists()


def test_the_gate_honours_reverse_order_with_the_same_discipline(
        tmp_path: Path) -> None:
    code, report = _run_gate(tmp_path, "--reverse")
    assert code == 1 and report["order"] == "reverse"
    assert [row["module"] for row in report["records"]] == [
        "test_z_last.py", "test_m_middle.py"]


def test_the_evidence_hook_writes_node_id_traceback_and_live_screenshots(
        tmp_path: Path, monkeypatch) -> None:
    class FakePage:
        def is_closed(self) -> bool:
            return False

        def screenshot(self, path: str, full_page: bool) -> None:
            Path(path).write_bytes(b"png")

    class FakeReport:
        nodeid = "browser_tests/test_x.py::test_y[dark]"
        when = "call"
        longreprtext = "AssertionError: the flake's words"

    class FakeItem:
        funcargs = {"graph_page": FakePage(), "other": object()}

    monkeypatch.setenv(gate_conftest.ARTIFACTS_ENV, str(tmp_path))
    gate_conftest._write_failure_evidence(FakeItem(), FakeReport())
    stem = "browser_tests_test_x.py_test_y_dark_"
    failure = (tmp_path / f"{stem}.failure.txt").read_text(encoding="utf-8")
    assert "browser_tests/test_x.py::test_y[dark]" in failure
    assert "the flake's words" in failure
    assert (tmp_path / f"{stem}.page1.png").read_bytes() == b"png"


def test_the_gate_runs_each_module_exactly_once_with_no_second_chances():
    source = GATE.read_text(encoding="utf-8")
    # One subprocess call in the whole runner, inside no retry construct:
    # the only loop is the module walk in run_gate, which breaks on red.
    assert source.count("subprocess.run(") == 1
    # The docstring DENIES these words, so the scan reads the code alone —
    # a guard that greps prose fails on the sentence stating the rule.
    code = source.split('"""', 2)[2]
    for forbidden in ("reruns", "rerun_", "flaky", "xfail", "retry",
                      "attempt", "max_tries"):
        assert forbidden not in code, forbidden
    # And the browser suite itself carries no escape hatch a gate must fear.
    for module in sorted((ROOT / "browser_tests").glob("test_*.py")):
        text = module.read_text(encoding="utf-8")
        for forbidden in ("xfail", "flaky", "reruns", "skipif"):
            assert forbidden not in text, (module.name, forbidden)


def test_the_gate_names_the_engine_it_ran_on():
    source = GATE.read_text(encoding="utf-8")
    assert '"playwright": version("playwright")' in source
    assert '"chromium": browser.version' in source
    assert 'environment["DEBUG"] = "pw:browser*"' in source