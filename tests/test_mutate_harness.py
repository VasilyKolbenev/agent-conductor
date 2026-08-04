"""Tests for `scripts/mutate_merge.py` — the instrument, not the code it measures.

Two defects of one class are pinned here: a measuring instrument that reports
a plausible number which is not true.

The first is import isolation. The repo's `.venv` carries an editable-install
`.pth` pointing at the working tree, so measuring an exported copy isolates
FILES but not IMPORTS — the harness mutated the export's `merge.py` while
pytest imported the working tree's, and printed `0/13 killed`. That is not
"every mutant survived", it is an invalid run. File isolation is not
verification isolation until the harness has confirmed the actual import root,
and a wrong import root must never render as a mutation score, not even zero.

The second is the restore path. An `OSError` raised inside a `finally` block
left a mutation applied to the working tree with the check that would have
caught it unrun, and the tree stayed poisoned for hours: every later run then
measures code that is not in the repository.

The shadowing fixture below CONSTRUCTS the exact condition — an export plus an
editable `.pth` pointing somewhere else — instead of trusting the ambient
environment to still carry one. Without that construction, none of the
assertions here would have teeth, which is what the first test checks.
"""
import ast
import importlib.util
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCORE_SHAPED = re.compile(r"\d+\s*/\s*\d+")

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "scripts" / "mutate_merge.py"
WORKING_TREE_MERGE = (ROOT / "src" / "conductor" / "merge.py").resolve()


def _load_harness():
    """Import `scripts/mutate_merge.py`, which is a script and not a package."""
    spec = importlib.util.spec_from_file_location("mutate_merge", HARNESS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


harness = _load_harness()


def run_harness(python, *args, env=None):
    """Run the harness script under `python` and capture everything it says."""
    return subprocess.run([str(python), str(HARNESS), *args],
                          capture_output=True, text=True, timeout=900, env=env)


# --- the constructed condition: an export shadowed by an editable install ---


@pytest.fixture(scope="session")
def export(tmp_path_factory):
    """A file-isolated copy of the tree, as a `git archive` export would be."""
    root = tmp_path_factory.mktemp("export").resolve()
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    shutil.copytree(ROOT / "src", root / "src", ignore=ignore)
    shutil.copytree(ROOT / "tests", root / "tests", ignore=ignore)
    shutil.copy2(ROOT / "pyproject.toml", root / "pyproject.toml")
    return root


@pytest.fixture(scope="session")
def shadowing_python(tmp_path_factory):
    """An interpreter carrying an editable `.pth` that points at the working tree.

    The second path on the `.pth` keeps pytest importable: a venv built without
    pip has no packages of its own, and the harness must still be able to run
    the targeted tests it scores mutations with.
    """
    venv = tmp_path_factory.mktemp("shadow") / "venv"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(venv)],
                   check=True, capture_output=True, timeout=300)
    python = (venv / "Scripts" / "python.exe") if os.name == "nt" \
        else (venv / "bin" / "python")
    purelib = subprocess.run(
        [str(python), "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
        check=True, capture_output=True, text=True, timeout=300).stdout.strip()
    pth = Path(purelib) / "_editable_impl_working_tree.pth"
    pth.write_text(f"{ROOT / 'src'}\n{Path(pytest.__file__).resolve().parents[1]}\n",
                   encoding="utf-8")
    return python


@pytest.fixture(scope="session")
def shadowed_export(tmp_path_factory, export):
    """An export whose own `conductor` cannot win the import.

    Dropping `__init__.py` leaves every file the harness would mutate exactly
    where it was, but makes the export a namespace portion — and a namespace
    portion loses to the regular package the `.pth` supplies. That is the
    original defect (mutate here, import there) made deterministic.
    """
    tree = tmp_path_factory.mktemp("shadowed").resolve() / "tree"
    shutil.copytree(export, tree, ignore=shutil.ignore_patterns("__pycache__"))
    (tree / "src" / "conductor" / "__init__.py").unlink()
    return tree


def test_the_shadowing_fixture_really_does_shadow_the_export(export, shadowing_python):
    # Everything below is worth nothing unless this still holds: with no
    # PYTHONPATH the export loses the import to the editable install, which is
    # exactly the condition that once produced a false 0/13.
    probe = subprocess.run([str(shadowing_python), "-c", harness.IMPORT_PROBE],
                           cwd=export, capture_output=True, text=True, timeout=300)
    assert probe.returncode == 0, probe.stderr
    assert Path(probe.stdout.strip()) == WORKING_TREE_MERGE


def test_measuring_an_export_under_an_editable_install_is_honest_not_plausible(
        export, shadowing_python):
    # The acceptance condition: run from an export while an editable install of
    # the working tree exists. The only two honest outcomes are a true 13/13 or
    # a refusal — never a score computed against a file nobody imported.
    stale = export / "src" / "conductor" / "__pycache__"
    stale.mkdir(exist_ok=True)
    (stale / "merge.cpython-000.pyc").write_bytes(b"stale bytecode")
    working_tree_before = WORKING_TREE_MERGE.read_bytes()

    result = run_harness(shadowing_python, "--root", str(export))

    assert result.returncode == harness.EXIT_OK, result.stdout + result.stderr
    assert "VERDICT: PASS - 13/13 mutations killed" in result.stdout
    assert f"conductor.merge: {export / 'src' / 'conductor' / 'merge.py'}" in result.stdout
    assert str(WORKING_TREE_MERGE) not in result.stdout   # the export was measured, not us
    assert WORKING_TREE_MERGE.read_bytes() == working_tree_before
    assert not stale.exists()                             # stale bytecode cleared on exit


def test_a_shadowed_import_root_refuses_before_any_mutation_and_never_scores(
        shadowed_export, shadowing_python):
    merge_path = shadowed_export / "src" / "conductor" / "merge.py"
    before = merge_path.read_bytes()

    result = run_harness(shadowing_python, "--root", str(shadowed_export))

    assert result.returncode == harness.EXIT_INVALID
    assert "INVALID MEASUREMENT" in result.stderr
    assert "import isolation not confirmed" in result.stderr
    assert str(shadowed_export / "src") in result.stderr      # what we asked to measure
    assert str(WORKING_TREE_MERGE) in result.stderr           # what actually imported
    # The law being pinned: an unknown state may not be displayed as a result.
    combined = result.stdout + result.stderr
    assert "no mutation score" in combined
    assert "killed" not in combined.lower() and "0/13" not in combined
    # "before any mutation" is the other half of this test's name, and the
    # bytes being right at the end cannot tell "never written" from "written
    # and restored". No mutation was reported, so none was run.
    assert "SURVIVED" not in combined
    assert "KILLED" not in combined
    assert "baseline" not in combined      # the refusal precedes even the baseline
    assert merge_path.read_bytes() == before                  # refused before mutating


def test_an_inherited_pythonpath_cannot_redirect_the_measurement(export, shadowing_python):
    # An ambiguous PYTHONPATH is the other way the import root drifts away from
    # the files being mutated, so the harness sets it rather than adding to it.
    result = run_harness(shadowing_python, "--root", str(export), "--verify-only",
                         env={**os.environ, "PYTHONPATH": str(ROOT / "src")})
    assert result.returncode == harness.EXIT_OK, result.stderr
    assert f"conductor.merge: {export / 'src' / 'conductor' / 'merge.py'}" in result.stdout
    assert "import isolation confirmed" in result.stdout


def test_the_subprocess_environment_is_pinned_and_never_inherited(monkeypatch):
    monkeypatch.setenv("PYTHONPATH", str(ROOT / "src"))
    monkeypatch.delenv("PYTHONNOUSERSITE", raising=False)
    env = harness.subprocess_env(Path("/somewhere/else/src"))
    assert env["PYTHONPATH"] == str(Path("/somewhere/else/src"))
    assert env["PYTHONNOUSERSITE"] == "1"
    assert env["PYTHONDONTWRITEBYTECODE"] == "1"


# --- the restore path: crash-safe, or loud about not being ---


class _FlakyFile:
    """A `Path` stand-in that fails or silently corrupts chosen writes.

    Writes are numbered from 1 in call order, which is how the tests below say
    "the mutation lands, and the restore is what breaks".
    """

    def __init__(self, real: Path, failing=(), corrupting=()):
        self.real = real
        self.failing = set(failing)
        self.corrupting = set(corrupting)
        self.writes = 0

    def read_bytes(self) -> bytes:
        return self.real.read_bytes()

    def write_bytes(self, data: bytes) -> int:
        self.writes += 1
        if self.writes in self.failing:
            raise OSError(5, "the volume went away mid-write")
        if self.writes in self.corrupting:
            data = data + b"# a write that lands the wrong bytes\n"
        return self.real.write_bytes(data)

    def __str__(self) -> str:
        return str(self.real)


@pytest.fixture
def source_copy(tmp_path, monkeypatch):
    """A throwaway copy of the merge engine — nothing here may touch the tree."""
    monkeypatch.setattr(harness, "RESTORE_DELAY_S", 0)
    path = tmp_path / "merge.py"
    path.write_bytes(WORKING_TREE_MERGE.read_bytes())
    return path


def _mutate_on_disk(path: Path) -> bytes:
    """Leave `path` mutated and return the bytes it must be restored to."""
    original = path.read_bytes()
    path.write_bytes(original + b"# mutation still applied\n")
    return original


def test_a_transient_write_failure_is_retried_until_the_hash_confirms(source_copy):
    original = _mutate_on_disk(source_copy)
    flaky = _FlakyFile(source_copy, failing={1})
    harness.restore_source(flaky, original)
    assert source_copy.read_bytes() == original
    assert flaky.writes == 2          # the retry really happened


def test_a_restore_that_never_lands_fails_loudly_and_names_the_file(source_copy):
    original = _mutate_on_disk(source_copy)
    with pytest.raises(harness.InvalidMeasurement) as raised:
        harness.restore_source(_FlakyFile(source_copy, failing=range(1, 99)), original)
    message = str(raised.value)
    assert "MAY STILL CARRY A MUTATION" in message
    assert str(source_copy) in message and "git checkout --" in message
    assert "the volume went away mid-write" in message


def test_a_write_that_lands_the_wrong_bytes_is_caught_by_the_content_hash(source_copy):
    # The failure no exception reports: the write "succeeds" and the file is
    # still not what the repository says it is. Only the hash sees this.
    original = _mutate_on_disk(source_copy)
    with pytest.raises(harness.InvalidMeasurement) as raised:
        harness.restore_source(_FlakyFile(source_copy, corrupting=range(1, 99)), original)
    assert "still differ" in str(raised.value)
    assert "MAY STILL CARRY A MUTATION" in str(raised.value)


def test_an_unconfirmed_restore_stops_the_run_and_tells_the_truth_about_the_tree(
        source_copy, monkeypatch):
    # Write 1 applies the mutation; every restore after it fails. The run must
    # stop there and say the file is still mutated, rather than carrying on and
    # measuring a tree nobody would recognise.
    calls = []
    monkeypatch.setattr(harness, "run_targeted_test",
                        lambda *args, **kwargs: (calls.append(args), 1)[1])
    flaky = _FlakyFile(source_copy, failing=range(2, 99))
    with pytest.raises(harness.InvalidMeasurement) as raised:
        harness.run_mutations(flaky, source_copy.parent, source_copy.parent)
    assert len(calls) == 1                                    # stopped at mutation #1
    assert "MAY STILL CARRY A MUTATION" in str(raised.value)
    assert source_copy.read_bytes() != WORKING_TREE_MERGE.read_bytes()   # and it is true


def test_a_stumbling_restore_still_leaves_no_mutation_applied(source_copy, monkeypatch):
    monkeypatch.setattr(harness, "run_targeted_test", lambda *args, **kwargs: 1)
    flaky = _FlakyFile(source_copy, failing={2, 5})           # two restores stumble once
    results = harness.run_mutations(flaky, source_copy.parent, source_copy.parent)
    assert [killed for _, killed in results] == [True] * len(harness.MUTATIONS)
    assert source_copy.read_bytes() == WORKING_TREE_MERGE.read_bytes()


# --- the exit-code contract: a code describes the mode that was requested ---


def _returns_exit_invalid(node) -> bool:
    """Whether an AST node is the harness's invalid-measurement exit code."""
    if isinstance(node, ast.Name):
        return node.id == "EXIT_INVALID"
    return isinstance(node, ast.Constant) and node.value == 2


def test_exit_two_is_returned_by_one_helper_and_by_nothing_else_in_the_module():
    # Sixteen independent `print(...); return 2` sites are the design in which
    # the seventeenth forgets to stay silent. The invariant "exit 2 prints no
    # score" is held here by the shape of the module, read from its AST, not by
    # remembering it at each raise site. (`argparse` also exits 2 on a usage
    # error — that happens inside argparse, not in this module, and the module
    # docstring names the overlap.)
    tree = ast.parse(HARNESS.read_text(encoding="utf-8"))
    returners = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.Return) and _returns_exit_invalid(inner.value):
                returners.add(node.name)
    assert returners == {"_invalid_measurement"}
    exits = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and ast.unparse(n.func) in ("sys.exit", "SystemExit", "exit")
             and any(_returns_exit_invalid(a) for a in n.args)]
    assert exits == []


def test_an_invalid_measurement_prints_no_score_and_returns_exit_two(capsys):
    code = harness._invalid_measurement(harness.InvalidMeasurement("the volume went away"))
    captured = capsys.readouterr()
    assert code == harness.EXIT_INVALID == 2
    assert captured.out == ""                        # nothing at all on stdout
    assert "the volume went away" in captured.err
    assert "no mutation score" in captured.err
    assert not SCORE_SHAPED.search(captured.err)     # not even a zero


def test_the_verdict_word_follows_the_score_it_reports(capsys):
    assert harness.report_score([("a", True), ("b", True)]) == harness.EXIT_OK
    assert "VERDICT: PASS - 2/2 mutations killed" in capsys.readouterr().out
    assert harness.report_score([("a", True), ("b", False)]) == harness.EXIT_SURVIVORS
    assert "VERDICT: FAIL - 1/2 mutations killed" in capsys.readouterr().out


def test_a_usage_error_exits_two_before_anything_could_be_measured():
    # The one exit-2 path that does not run through the helper, because it
    # happens inside argparse. The docstring claims it prints usage and stops
    # before anything is measured; this is that claim, executed.
    result = run_harness(sys.executable, "--no-such-flag")
    assert result.returncode == harness.EXIT_INVALID
    assert result.stdout == ""
    assert "unrecognized arguments" in result.stderr
    assert not SCORE_SHAPED.search(result.stderr)


# --- an unmeasured mutation may not be folded into a score ---


def test_only_pytest_exit_1_counts_as_a_kill(monkeypatch):
    monkeypatch.setattr(harness, "run_targeted_test", lambda *a, **k: 1)
    assert harness._score_mutation("m", "t.py", Path("src"), Path(".")) is True
    monkeypatch.setattr(harness, "run_targeted_test", lambda *a, **k: 0)
    assert harness._score_mutation("m", "t.py", Path("src"), Path(".")) is False


@pytest.mark.parametrize("returncode", [2, 3, 4, 5])
def test_a_pytest_exit_that_is_not_a_test_result_is_an_invalid_measurement(
        monkeypatch, returncode):
    # A collection error means the mutation was never measured. Folding it into
    # the score as "not killed" is the same defect as a wrong import root: a
    # plausible number that measures nothing.
    monkeypatch.setattr(harness, "run_targeted_test", lambda *a, **k: returncode)
    with pytest.raises(harness.InvalidMeasurement) as raised:
        harness._score_mutation("m", "t.py", Path("src"), Path("."))
    assert "never measured" in str(raised.value)
    assert str(returncode) in str(raised.value)


def test_a_targeted_run_that_never_finishes_is_an_invalid_measurement(monkeypatch):
    def timed_out(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="pytest", timeout=1)

    monkeypatch.setattr(harness, "run_targeted_test", timed_out)
    with pytest.raises(harness.InvalidMeasurement) as raised:
        harness._score_mutation("m", "t.py", Path("src"), Path("."))
    assert "never measured" in str(raised.value)


def test_an_anchor_that_no_longer_matches_is_an_invalid_measurement_not_a_survivor():
    with pytest.raises(harness.InvalidMeasurement) as raised:
        harness.apply_mutation("a named row", b"one line\n", "gone from the source", "x")
    message = str(raised.value)
    assert "a named row" in message and "0 times" in message


def test_the_anchor_check_still_runs_under_python_O(tmp_path):
    # `assert` is stripped by -O; the guard that proves a mutation was really
    # applied may not be. Without this, -O turns an unapplied mutation into a
    # SURVIVED line inside a score.
    script = tmp_path / "under_o.py"
    script.write_text(
        "import importlib.util, sys\n"
        f"spec = importlib.util.spec_from_file_location('m', r'{HARNESS}')\n"
        "m = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(m)\n"
        "try:\n"
        "    m.apply_mutation('a named row', b'one line\\n', 'gone', 'x')\n"
        "except m.InvalidMeasurement:\n"
        "    print('REFUSED')\n"
        "    sys.exit(0)\n"
        "sys.exit(1)\n", encoding="utf-8")
    result = subprocess.run([sys.executable, "-O", str(script)],
                            capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "REFUSED" in result.stdout


# --- the four provenance facts and the verdict word, pinned ---


def test_provenance_prints_the_path_the_probe_resolved_not_the_expected_one(capsys):
    # In every green run the expected and the resolved `merge` path coincide,
    # so a test comparing them to each other separates nothing. These two
    # deliberately differ: a package beats a module of the same name, so a root
    # carrying both `merge.py` and `merge/` imports the latter.
    source_root = Path("/measured/src")
    resolved = source_root / "conductor" / "merge" / "__init__.py"
    harness.print_provenance(source_root, resolved)
    out = capsys.readouterr().out
    assert f"source root:     {source_root}" in out
    assert f"conductor.merge: {resolved}" in out
    assert str(source_root / "conductor" / "merge.py") not in out
    assert f"interpreter:     {sys.executable}" in out


def test_verify_only_confirms_the_import_root_and_says_no_mutations_were_run(
        export, shadowing_python):
    result = run_harness(shadowing_python, "--root", str(export), "--verify-only")
    assert result.returncode == harness.EXIT_OK, result.stderr
    assert f"source root:     {export / 'src'}" in result.stdout
    assert f"conductor.merge: {export / 'src' / 'conductor' / 'merge.py'}" in result.stdout
    assert f"interpreter:     {shadowing_python}" in result.stdout
    assert "no mutations were run" in result.stdout
    assert "killed" not in result.stdout.lower()
    assert not SCORE_SHAPED.search(result.stdout)


# --- the baseline: a red test file scores every mutation aimed at it as KILLED ---


def _recorder(returncode=0, testcases=1):
    """A `subprocess` stand-in that records calls and fakes a JUnit report."""
    calls = []

    def run(cmd, **kwargs):
        calls.append((list(cmd), kwargs))
        for arg in cmd:
            if str(arg).startswith("--junit-xml="):
                cases = "<testcase/>" * testcases
                Path(str(arg).split("=", 1)[1]).write_text(
                    f"<testsuites><testsuite>{cases}</testsuite></testsuites>",
                    encoding="utf-8")
        return subprocess.CompletedProcess(cmd, returncode, "captured out", "captured err")

    return calls, SimpleNamespace(run=run, TimeoutExpired=subprocess.TimeoutExpired)


def test_the_baseline_covers_exactly_the_files_the_mutations_are_scored_against():
    declared = [test_file for _, _, _, test_file in harness.MUTATIONS]
    assert set(harness.targeted_test_files()) == set(declared)
    assert len(harness.targeted_test_files()) == len(set(declared))


def test_the_baseline_and_the_mutant_runs_come_from_one_environment(monkeypatch, tmp_path):
    # Not "built the same way" — the same. Two builders drift apart at the
    # first edit, and then the baseline proves the wrong tree is green.
    calls, fake = _recorder()
    monkeypatch.setattr(harness, "subprocess", fake)
    source_root, cwd = tmp_path / "src", tmp_path
    harness.check_baseline(source_root, cwd, source_root / "conductor" / "merge.py")
    harness.run_targeted_test("tests/test_merge_review.py", source_root, cwd)

    (baseline_cmd, baseline_kw), (mutant_cmd, mutant_kw) = calls
    assert baseline_cmd[:3] == mutant_cmd[:3] == [sys.executable, "-m", "pytest"]
    assert baseline_kw["cwd"] == mutant_kw["cwd"] == cwd
    assert baseline_kw["env"] == mutant_kw["env"] == harness.subprocess_env(source_root)
    assert [a for a in baseline_cmd if a.endswith(".py")] == harness.targeted_test_files()


def test_a_baseline_that_is_not_green_is_an_invalid_measurement(monkeypatch, tmp_path):
    calls, fake = _recorder(returncode=1)
    monkeypatch.setattr(harness, "subprocess", fake)
    with pytest.raises(harness.InvalidMeasurement) as raised:
        harness.check_baseline(tmp_path / "src", tmp_path, tmp_path / "merge.py")
    assert "not green on unmutated source" in str(raised.value)
    assert "reads as KILLED" in str(raised.value)


def test_a_baseline_that_collected_nothing_is_an_invalid_measurement(monkeypatch, tmp_path):
    # A green exit over zero tests proves nothing, and it is a distinct failure
    # from a red one.
    calls, fake = _recorder(returncode=0, testcases=0)
    monkeypatch.setattr(harness, "subprocess", fake)
    with pytest.raises(harness.InvalidMeasurement) as raised:
        harness.check_baseline(tmp_path / "src", tmp_path, tmp_path / "merge.py")
    assert "collected no test at all" in str(raised.value)


def test_pytest_exits_five_when_it_collects_nothing(tmp_path):
    # The fact the baseline docstring rests on, executed rather than assumed.
    (tmp_path / "test_nothing.py").write_text("def helper():\n    return 1\n",
                                              encoding="utf-8")
    result = subprocess.run([sys.executable, "-m", "pytest", "test_nothing.py", "-q"],
                            cwd=tmp_path, capture_output=True, text=True, timeout=300)
    assert result.returncode == 5


def test_a_red_targeted_file_stops_the_run_before_the_first_mutation(
        tmp_path, export, shadowing_python):
    # The defect: a targeted file that is already red reports every mutation
    # aimed at it as KILLED, because the harness only ever asked for exit 1.
    tree = tmp_path / "already_red"
    shutil.copytree(export, tree, ignore=shutil.ignore_patterns("__pycache__"))
    red = tree / "tests" / harness.targeted_test_files()[0].split("/")[-1]
    red.write_text(red.read_text(encoding="utf-8") +
                   "\n\ndef test_planted_failure_unrelated_to_merge():\n"
                   "    assert False\n", encoding="utf-8")
    merge_path = tree / "src" / "conductor" / "merge.py"
    before = merge_path.read_bytes()

    result = run_harness(shadowing_python, "--root", str(tree))

    assert result.returncode == harness.EXIT_INVALID, result.stdout + result.stderr
    assert "not green on unmutated source" in result.stderr
    assert merge_path.read_bytes() == before            # never touched
    assert "KILLED" not in result.stdout and "SURVIVED" not in result.stdout
    assert "mutations killed" not in result.stdout + result.stderr


# --- prose about this code is code: these pin claims, not wording ---


def test_the_docstring_states_the_kill_rule_the_scorer_actually_applies():
    doc = harness.__doc__
    assert "nonzero pytest exit" not in doc      # only exit 1 is a kill
    assert "exit 1" in doc


def test_the_docstring_does_not_promise_a_tree_that_is_always_left_clean():
    # A hard kill between the mutation write and the restore leaves a mutated
    # file and says nothing. The docstring may not offer two exhaustive
    # outcomes while that third one exists.
    doc = harness.__doc__
    assert "always" not in doc
    assert "hard kill" in doc
    assert "separate task" in doc


def test_the_exit_table_covers_verify_only_and_the_argparse_overlap():
    doc = harness.__doc__
    assert "--verify-only" in doc
    assert "argparse" in doc


def test_the_pythonnousersite_reason_is_the_one_that_holds():
    # PYTHONPATH precedes every site directory, so the flag does not keep a
    # user-site install from shadowing the source root. What it does do is hide
    # a user-site pytest, which is why the probe imports pytest at all.
    doc = harness.subprocess_env.__doc__
    assert "from shadowing the source root" not in doc
    assert "pytest" in doc


def test_a_source_that_cannot_be_written_is_an_invalid_measurement_not_a_score(
        tmp_path, export, shadowing_python):
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("root ignores the read-only bit")
    tree = tmp_path / "readonly"
    shutil.copytree(export, tree, ignore=shutil.ignore_patterns("__pycache__"))
    merge_path = tree / "src" / "conductor" / "merge.py"
    before = merge_path.read_bytes()
    os.chmod(merge_path, stat.S_IREAD)
    try:
        result = run_harness(shadowing_python, "--root", str(tree))
    finally:
        os.chmod(merge_path, stat.S_IREAD | stat.S_IWRITE)
    assert result.returncode == harness.EXIT_INVALID
    assert "could not be applied" in result.stderr
    assert "no mutation score" in result.stderr
    assert "killed" not in (result.stdout + result.stderr).lower()
    assert merge_path.read_bytes() == before
