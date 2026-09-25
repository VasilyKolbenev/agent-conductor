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
from browser_tests import gate

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
              conftest: str | None = None,
              extra_env: dict[str, str] | None = None) -> tuple[int, dict]:
    modules_dir = tmp_path / "modules"
    modules_dir.mkdir(exist_ok=True)
    for name, body in (modules or _DEFAULT_MODULES).items():
        (modules_dir / name).write_text(body, encoding="utf-8")
    if conftest is not None:
        (modules_dir / "conftest.py").write_text(conftest, encoding="utf-8")
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


def test_the_record_counts_every_way_a_test_can_avoid_passing(
        tmp_path: Path) -> None:
    """The four waiver outcomes are named in the record, always."""
    _, report = _run_gate(tmp_path, modules={"test_only.py": _PASSING})
    record = report["records"][-1]
    assert all(record[name] == 0 for name in gate.WAIVER_OUTCOMES)
    assert set(gate.WAIVER_OUTCOMES) == {
        "skipped", "xfailed", "xpassed", "deselected"}


#: A conftest hook that waives a failing test at collection time. No word of
#: it appears in any test source, so only counting outcomes catches it.
_DYNAMIC_XFAIL_CONFTEST = (
    "import pytest\n\n"
    "def pytest_collection_modifyitems(items):\n"
    "    for item in items:\n"
    "        item.add_marker(pytest.mark.xfail(reason='dynamic waiver'))\n")
_DYNAMIC_DESELECT_CONFTEST = (
    "def pytest_collection_modifyitems(config, items):\n"
    "    config.hook.pytest_deselected(items=list(items))\n"
    "    items[:] = []\n")


def test_a_dynamically_waived_failure_reds_the_gate(tmp_path: Path) -> None:
    """A conftest that xfails everything leaves exit 0 and '1 xfailed' —
    a green-looking run in which the guard never actually held."""
    code, report = _run_gate(
        tmp_path, modules={"test_only.py": _FAILING},
        conftest=_DYNAMIC_XFAIL_CONFTEST)
    assert code == 1 and report["result"] == "red"
    record = report["records"][-1]
    assert record["exit_code"] == 0 and record["xfailed"] == 1


def test_a_dynamically_deselected_test_reds_the_gate(tmp_path: Path) -> None:
    """Deselection removes a guard just as completely as a skip does."""
    code, report = _run_gate(
        tmp_path, modules={"test_only.py": _PASSING},
        conftest=_DYNAMIC_DESELECT_CONFTEST)
    assert code == 1 and report["result"] == "red"
    assert report["records"][-1]["deselected"] == 1


def test_the_gate_owns_its_temporary_root_and_ignores_the_machines(
        tmp_path: Path) -> None:
    """A module using tmp_path stays green when the shared temporary
    directory is unusable — the gate's verdict is about the code, not the
    host's leftovers or ACLs."""
    using_tmp = ("def test_writes(tmp_path):\n"
                 "    (tmp_path / 'x').write_text('ok')\n"
                 "    assert (tmp_path / 'x').read_text() == 'ok'\n")
    missing = tmp_path / "no-such-temp-dir"
    code, report = _run_gate(
        tmp_path, modules={"test_only.py": using_tmp},
        extra_env={"TEMP": str(missing), "TMP": str(missing),
                   "TMPDIR": str(missing)})
    assert code == 0 and report["result"] == "green"
    record = report["records"][-1]
    # The basetemp is the gate's own, inside the artifacts, and recorded.
    basetemp = Path(record["basetemp"])
    assert basetemp.parent == tmp_path / "artifacts" / "basetemp"
    assert basetemp.name == "test_only" and basetemp.exists()


def test_each_module_gets_a_basetemp_of_its_own(tmp_path: Path) -> None:
    code, report = _run_gate(
        tmp_path, modules={"test_a.py": _PASSING, "test_b.py": _PASSING})
    assert code == 0
    roots = [row["basetemp"] for row in report["records"]]
    assert len(set(roots)) == 2, roots


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


#: A module that reports, into the artifacts, where the gate told the engine
#: of its own process to log. Chromium picks that file itself when nobody
#: names it, and on Windows picks a path beside the executable — shared by
#: every run on the machine, and outside what --artifacts promises to hold.
_REPORTS_ITS_LOG = (
    "import os\n"
    "from pathlib import Path\n\n"
    "def test_reports_where_chromium_must_log():\n"
    "    named = os.environ['CHROME_LOG_FILE']\n"
    "    artifacts = Path(os.environ['CONDUCT_GATE_ARTIFACTS'])\n"
    "    stem = Path(__file__).stem\n"
    "    assert Path.cwd() == artifacts / 'working' / stem\n"
    "    assert os.environ['PYTHONIOENCODING'] == 'utf-8'\n"
    "    (artifacts / (stem + '.named.txt')).write_text(named, 'utf-8')\n")


def test_relative_gate_paths_survive_the_isolated_child_working_directory(
        tmp_path: Path, monkeypatch) -> None:
    modules = tmp_path / "modules"
    modules.mkdir()
    (modules / "test_relative.py").write_text(_REPORTS_ITS_LOG, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    code = gate.run_gate(Path("modules"), Path("artifacts"), False, True)
    report = json.loads((tmp_path / "artifacts/gate.json").read_text(encoding="utf-8"))
    assert code == 0 and report["result"] == "green", report
    row = report["records"][0]
    assert Path(row["cwd"]) == tmp_path / "artifacts/working/test_relative"
    assert Path(row["basetemp"]).is_absolute()
    assert (tmp_path / "artifacts/test_relative.named.txt").is_file()


def test_every_module_is_told_to_keep_chromiums_own_log_in_the_artifacts(
        tmp_path: Path) -> None:
    """Two modules, two named files, both inside the run's artifacts."""
    code, report = _run_gate(tmp_path, modules={
        "test_a.py": _REPORTS_ITS_LOG, "test_b.py": _REPORTS_ITS_LOG})
    assert code == 0 and report["result"] == "green"
    artifacts = tmp_path / "artifacts"
    named = [Path((artifacts / f"{stem}.named.txt").read_text("utf-8"))
             for stem in ("test_a", "test_b")]
    for path in named:
        # Absolute, because a working directory must not decide this.
        assert path.is_absolute(), path
        assert artifacts in path.parents, path
    # And per module: one shared file cannot say which module was speaking.
    assert named[0] != named[1], named


def test_naming_that_log_leaves_the_rest_of_the_childs_world_alone(
        tmp_path: Path) -> None:
    """The containment EXTENDS the machine's environment, never replaces it:
    a child handed a stripped world would fail for reasons of its own."""
    environment = gate._child_environment(tmp_path, ROOT, Path("test_x.py"))
    assert environment["PATH"] == os.environ["PATH"]
    named = Path(environment["CHROME_LOG_FILE"])
    assert tmp_path in named.parents and named.name.startswith("test_x")


class _RecordingChromium:
    """Enough Playwright to see what the gate hands its own launch."""

    def __init__(self) -> None:
        self.launched: dict[str, object] = {}

    def launch(self, **kwargs: object) -> "_RecordingChromium":
        self.launched = kwargs
        return self

    version = "test-chromium"

    def close(self) -> None:
        return None

    def __enter__(self) -> "_RecordingChromium":
        return self

    def __exit__(self, *exception: object) -> bool:
        return False

    @property
    def chromium(self) -> "_RecordingChromium":
        return self


def test_the_gates_own_version_probe_launches_under_the_same_containment(
        tmp_path: Path, monkeypatch) -> None:
    """The probe runs in the GATE's process, where no child environment
    reaches — the one launch a per-module fix would silently leave loose."""
    recorder = _RecordingChromium()
    monkeypatch.setattr("playwright.sync_api.sync_playwright", lambda: recorder)
    versions = gate.probe_versions(tmp_path)
    assert versions["chromium"] == "test-chromium"
    named = Path(recorder.launched["env"]["CHROME_LOG_FILE"])
    assert named.is_absolute() and tmp_path in named.parents
    assert recorder.launched["args"] == [f"--log-file={named}"]
    # The machine's own environment travels with it, not just the one key.
    assert recorder.launched["env"]["PATH"] == os.environ["PATH"]


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
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", str(modules_dir / "test_hook.py"),
         "-q", "-p", "no:cacheprovider", "--rootdir", str(modules_dir)],
        capture_output=True, text=True, cwd=str(modules_dir), env=environment,
        check=False)
    (modules_dir / "pytest.stdout.txt").write_text(completed.stdout, encoding="utf-8")
    (modules_dir / "pytest.stderr.txt").write_text(completed.stderr, encoding="utf-8")
    assert completed.returncode == 1, (
        f"Expected intentional call/teardown failures (exit 1), got {completed.returncode}.\n"
        f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}")
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
    # The prose DENIES these words, so the scan reads executable code alone:
    # a guard that greps a docstring or a comment fails on the very sentence
    # that states the rule (tests/test_panel_cascade.py makes the same
    # distinction for the panel's sources).
    body = source.split('"""', 2)[2]
    code = "\n".join(line.split("#", 1)[0] for line in body.splitlines())
    for forbidden in ("reruns", "rerun_", "flaky", "retry", "max_tries",
                      "mark.xfail", "runxfail"):
        assert forbidden not in code, forbidden
    # "xfail" may appear in the runner only as the outcome noun it REDS on:
    # never as a marker it applies and never as a flag it passes.
    for line in code.splitlines():
        if "xfail" in line:
            assert "xfailed" in line, line
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
    # All four configuration channels shut, including the project's own
    # addopts and any plugin that would load itself into the run.
    assert 'environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"' in source
    assert '"-o", "addopts="' in source
    assert '"--basetemp", str(basetemp)' in source
