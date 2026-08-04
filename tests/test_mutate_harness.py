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
import importlib.util
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

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

    assert result.returncode == harness.EXIT_INFRASTRUCTURE
    assert "INFRASTRUCTURE ERROR" in result.stderr
    assert "import isolation not confirmed" in result.stderr
    assert str(shadowed_export / "src") in result.stderr      # what we asked to measure
    assert str(WORKING_TREE_MERGE) in result.stderr           # what actually imported
    # The law being pinned: an unknown state may not be displayed as a result.
    combined = result.stdout + result.stderr
    assert "no mutation score" in combined
    assert "killed" not in combined.lower() and "0/13" not in combined
    assert merge_path.read_bytes() == before                  # refused before mutating


def test_an_inherited_pythonpath_cannot_redirect_the_measurement(export, shadowing_python):
    # An ambiguous PYTHONPATH is the other way the import root drifts away from
    # the files being mutated, so the harness sets it rather than adding to it.
    result = run_harness(shadowing_python, "--root", str(export), "--verify-only",
                         env={**os.environ, "PYTHONPATH": str(ROOT / "src")})
    assert result.returncode == harness.EXIT_OK, result.stderr
    assert f"conductor.merge: {export / 'src' / 'conductor' / 'merge.py'}" in result.stdout
    assert "VERDICT: import isolation confirmed" in result.stdout


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
    with pytest.raises(harness.InfrastructureError) as raised:
        harness.restore_source(_FlakyFile(source_copy, failing=range(1, 99)), original)
    message = str(raised.value)
    assert "MAY STILL CARRY A MUTATION" in message
    assert str(source_copy) in message and "git checkout --" in message
    assert "the volume went away mid-write" in message


def test_a_write_that_lands_the_wrong_bytes_is_caught_by_the_content_hash(source_copy):
    # The failure no exception reports: the write "succeeds" and the file is
    # still not what the repository says it is. Only the hash sees this.
    original = _mutate_on_disk(source_copy)
    with pytest.raises(harness.InfrastructureError) as raised:
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
    with pytest.raises(harness.InfrastructureError) as raised:
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


def test_a_source_that_cannot_be_written_is_an_infrastructure_error_not_a_score(
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
    assert result.returncode == harness.EXIT_INFRASTRUCTURE
    assert "could not be applied" in result.stderr
    assert "no mutation score" in result.stderr
    assert "killed" not in (result.stdout + result.stderr).lower()
    assert merge_path.read_bytes() == before
