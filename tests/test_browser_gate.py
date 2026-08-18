"""The browser release gate's discipline, proven rather than promised.

Two halves. The behavioural half runs the real runner against synthetic
modules in a temporary directory and watches it do exactly what the gate
contract says: one fresh process per module, stop at the first red one, both
orders, records for every run, full output for the failing one, ambient
pytest configuration ignored, skips treated as the waivers they are, hangs
killed and recorded. The discipline half pins what must stay absent: no
retry, no rerun, no xfail, no skip and no statistical waiver anywhere in the
browser gate's sources.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from browser_tests import conftest as gate_conftest

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "browser_tests" / "gate.py"
CONFTEST = ROOT / "browser_tests" / "conftest.py"

_PASSING = "def test_green():\n    assert True\n"
_FAILING = "def test_red():\n    assert False, 'deliberate'\n"
_DEFAULT_MODULES = {
    "test_a_first.py": _PASSING,
    "test_m_middle.py": _FAILING,
    "test_z_last.py": _PASSING,
}


def _run_gate(tmp_path: Path, *flags: str,
              modules: dict[str, str] | None = None,
              extra_env: dict[str, str] | None = None) -> tuple[int, dict]:
    modules_dir = tmp_path / "modules"
    modules_dir.mkdir(exist_ok=True)
    for name, body in (modules or _DEFAULT_MODULES).items():
        (modules_dir / name).write_text(body, encoding="utf-8")
    artifacts = tmp_path / "artifacts"
    environment = {**os.environ, **(extra_env or {})}
    completed = subprocess.run(
        [sys.executable, "-m", "browser_tests.gate",
         "--modules-dir", str(modules_dir), "--artifacts", str(artifacts),
         "--skip-version-probe", *flags],
        capture_output=True, text=True, cwd=str(ROOT), env=environment,
        check=False)
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
    # stderr is recorded for GREEN runs too — the browser channel of a
    # near-miss is the diagnostic corpus; stdout dumps stay failure-only.
    assert (tmp_path / "artifacts" / "test_a_first.stderr.txt").exists()
    assert not (tmp_path / "artifacts" / "test_a_first.stdout.txt").exists()


def test_the_gate_honours_reverse_order_with_the_same_discipline(
        tmp_path: Path) -> None:
    code, report = _run_gate(tmp_path, "--reverse")
    assert code == 1 and report["order"] == "reverse"
    assert [row["module"] for row in report["records"]] == [
        "test_z_last.py", "test_m_middle.py"]


def test_ambient_pytest_configuration_cannot_soften_the_gate(
        tmp_path: Path) -> None:
    """PYTEST_ADDOPTS=--collect-only would run nothing and call it green."""
    code, report = _run_gate(
        tmp_path, extra_env={"PYTEST_ADDOPTS": "--collect-only"})
    assert code == 1 and report["result"] == "red"
    assert report["records"][-1]["failed_nodes"][0].endswith("::test_red")


def test_a_skipped_test_is_a_waiver_and_reds_the_gate(tmp_path: Path) -> None:
    skipping = ("import pytest\n\n"
                "@pytest.mark.skip(reason='a waiver by another name')\n"
                "def test_was_a_guard():\n    assert False\n")
    code, report = _run_gate(
        tmp_path, modules={"test_only.py": skipping})
    assert code == 1 and report["result"] == "red"
    assert report["records"][-1]["skipped"] == 1
    assert report["records"][-1]["exit_code"] == 0


def test_a_hanging_module_is_killed_recorded_and_the_report_survives(
        tmp_path: Path) -> None:
    hanging = "import time\n\ndef test_wedge():\n    time.sleep(120)\n"
    code, report = _run_gate(
        tmp_path, "--module-timeout", "5",
        modules={"test_a_ok.py": _PASSING, "test_b_hang.py": hanging})
    assert code == 1 and report["result"] == "red"
    assert [row["module"] for row in report["records"]] == [
        "test_a_ok.py", "test_b_hang.py"]
    assert report["records"][-1]["exit_code"] == "timed-out"


def _fake_page_module() -> str:
    return (
        "import pytest\n"
        "from pathlib import Path\n\n"
        "class FakePage:\n"
        "    closed = False\n"
        "    def is_closed(self):\n"
        "        return self.closed\n"
        "    def screenshot(self, path, full_page):\n"
        "        Path(path).write_bytes(b'png')\n\n"
        "@pytest.fixture\n"
        "def fake_page():\n"
        "    yield FakePage()\n\n"
        "@pytest.fixture\n"
        "def raising_teardown(fake_page):\n"
        "    yield fake_page\n"
        "    raise RuntimeError('teardown crash, the flake\\'s class')\n\n"
        "def test_call_failure(fake_page):\n"
        "    assert False, 'call-phase failure'\n\n"
        "def test_teardown_failure(raising_teardown):\n"
        "    assert True\n\n"
        "def test_green(fake_page):\n"
        "    assert True\n")


def _run_hook_module(tmp_path: Path, with_env: bool) -> Path:
    modules_dir = tmp_path / ("armed" if with_env else "inert")
    modules_dir.mkdir()
    (modules_dir / "conftest.py").write_text(
        CONFTEST.read_text(encoding="utf-8"), encoding="utf-8")
    (modules_dir / "test_hook.py").write_text(
        _fake_page_module(), encoding="utf-8")
    evidence = modules_dir / "evidence"
    environment = dict(os.environ)
    if with_env:
        environment[gate_conftest.ARTIFACTS_ENV] = str(evidence)
    else:
        environment.pop(gate_conftest.ARTIFACTS_ENV, None)
    subprocess.run(
        [sys.executable, "-m", "pytest", str(modules_dir / "test_hook.py"),
         "-q", "-p", "no:cacheprovider"],
        capture_output=True, text=True, cwd=str(ROOT), env=environment,
        check=False)
    return evidence


def test_the_evidence_hook_records_call_and_teardown_failures_end_to_end(
        tmp_path: Path) -> None:
    """The real conftest, a real pytest run: the flake's own teardown class
    leaves a phase-stamped record, and a green test leaves nothing."""
    evidence = _run_hook_module(tmp_path, with_env=True)
    names = sorted(path.name for path in evidence.iterdir())
    call = [n for n in names if "test_call_failure" in n]
    teardown = [n for n in names if "test_teardown_failure" in n]
    assert any(n.endswith(".call.failure.txt") for n in call), names
    assert any(n.endswith(".png") for n in call), names
    assert any(n.endswith(".teardown.failure.txt") for n in teardown), names
    assert not [n for n in names if "test_green" in n]
    text = next(evidence.glob("*teardown.failure.txt")).read_text("utf-8")
    assert "teardown crash" in text and "phase: teardown" in text


def test_the_evidence_hook_is_inert_without_the_gate_environment(
        tmp_path: Path) -> None:
    evidence = _run_hook_module(tmp_path, with_env=False)
    assert not evidence.exists()


def test_the_evidence_walk_finds_pages_the_test_never_put_in_funcargs(
        tmp_path: Path, monkeypatch) -> None:
    class FakePage:
        def __init__(self) -> None:
            self.saved: list[str] = []

        def is_closed(self) -> bool:
            return False

        def screenshot(self, path: str, full_page: bool) -> None:
            Path(path).write_bytes(b"png")

    class FakeContext:
        def __init__(self, *pages: FakePage) -> None:
            self.pages = list(pages)

    class FakeBrowser:
        def __init__(self, *contexts: FakeContext) -> None:
            self.contexts = list(contexts)

    inline = FakePage()

    class FakeReport:
        nodeid = "browser_tests/test_x.py::test_inline"
        when = "call"
        longreprtext = "AssertionError"

    class FakeItem:
        funcargs = {"chromium": FakeBrowser(FakeContext(inline))}

    monkeypatch.setenv(gate_conftest.ARTIFACTS_ENV, str(tmp_path))
    gate_conftest._write_failure_evidence(FakeItem(), FakeReport())
    saved = list(tmp_path.glob("*.png"))
    assert len(saved) == 1, "the inline page must be found through the browser"
    failure = next(tmp_path.glob("*.call.failure.txt")).read_text("utf-8")
    assert "live pages: 1" in failure


def test_the_gate_runs_each_module_exactly_once_with_no_second_chances():
    source = GATE.read_text(encoding="utf-8")
    # One subprocess call in the whole runner, inside no retry construct:
    # the only loop is the module walk in run_gate, which returns on red.
    assert source.count("subprocess.run(") == 1
    # The docstring DENIES these words, so the scan reads the code alone —
    # a guard that greps prose fails on the sentence stating the rule.
    code = source.split('"""', 2)[2]
    for forbidden in ("reruns", "rerun_", "flaky", "xfail", "retry",
                      "max_tries"):
        assert forbidden not in code, forbidden
    # And the browser suite itself carries no escape hatch a gate must fear —
    # skips included (the gate additionally reds on any skip at runtime).
    # These are code tokens, not bare words: prose saying "skipped the
    # boundary" is a sentence, not a waiver.
    for module in sorted((ROOT / "browser_tests").glob("test_*.py")):
        text = module.read_text(encoding="utf-8")
        for forbidden in ("xfail", "flaky", "reruns", "pytest.skip",
                          "mark.skip", "skipif", "importorskip"):
            assert forbidden not in text, (module.name, forbidden)


def test_the_gate_names_the_engine_it_ran_on():
    source = GATE.read_text(encoding="utf-8")
    assert '"playwright": version("playwright")' in source
    assert '"chromium": browser.version' in source
    assert 'environment["DEBUG"] = "pw:browser*"' in source
    assert 'environment.pop("PYTEST_ADDOPTS", None)' in source
    assert 'environment.pop("PYTEST_PLUGINS", None)' in source