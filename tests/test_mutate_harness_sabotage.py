"""Sabotage suite for `scripts/mutate_merge.py` — the guards, kept honest.

Two independent reviews broke sixteen guards of this harness by hand and
recorded, each time, that nothing noticed. A report proves a guard held on the
day it was written; only a test proves it still holds after the next edit.
Each case below re-creates one of those diversions and pins the difference
between a guarded run and a sabotaged one.

Nothing here writes inside the repository. Every case copies the harness into a
temporary directory and sabotages the COPY, and the target it measures is a
synthetic three-line module in the same temporary directory. That is true by
construction, not by `finally`: no code in this module ever opens a file in the
working tree for writing, so an interrupted run cannot leave the tree changed.
The harness's own first gotcha is that it mutates `merge.py` in place, and
reproducing that gotcha inside the tests that close it would be a defect of
this round rather than its result.

An unsabotaged copy is byte-identical to the shipped script, so the "guarded"
half of every case exercises the code that ships.

The target is synthetic on purpose. A real run is thirteen pytest invocations;
these cases need one or two, which is what keeps a suite of them affordable.
"""
import ast
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "scripts" / "mutate_merge.py"

SYNTH_MERGE = 'def is_ready(state):\n    return state == "ready"\n'
SYNTH_TESTS = (
    "from conductor.merge import is_ready\n"
    "\n"
    "\n"
    "def test_a_ready_state_is_ready():\n"
    '    assert is_ready("ready")\n'
    "\n"
    "\n"
    "def test_a_busy_state_is_not_ready():\n"
    '    assert not is_ready("busy")\n'
)
RED_TESTS = SYNTH_TESTS + '\n\ndef test_planted_failure():\n    assert False\n'

ANCHOR = '    return state == "ready"'
DRIFTED = '    return state == "a line that is not in the file"'
KILLING = "    return True"                       # the busy case goes red
SURVIVING = '    return bool(state == "ready")'   # behaviour-preserving
UNPARSEABLE = '    return state ==== "ready"'     # pytest cannot even collect

SCORE = "mutations killed"


def _write(path: Path, text: str) -> None:
    """Write text with LF endings, whatever the platform would prefer."""
    path.write_text(text, encoding="utf-8", newline="")


def _driver(anchor: str, replacement: str) -> str:
    """A script that runs a harness copy with one synthetic mutation.

    Args:
        anchor: The text the single mutation looks for.
        replacement: What it substitutes.

    Returns:
        The driver source. `sys.argv[1]` is the harness copy; the rest is the
        harness's own command line.
    """
    return (
        "import importlib.util\n"
        "import sys\n"
        "spec = importlib.util.spec_from_file_location('harness_copy', sys.argv[1])\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(module)\n"
        f"module.MUTATIONS = [('the synthetic rule', {anchor!r}, {replacement!r},"
        " 'tests/test_synth.py')]\n"
        "raise SystemExit(module.main(sys.argv[2:]))\n"
    )


class _Lab:
    """A private copy of the harness plus synthetic targets to point it at."""

    def __init__(self, tmp_path: Path):
        self.tmp = tmp_path
        self.harness = tmp_path / "instrument" / "scripts" / "mutate_merge.py"
        self.harness.parent.mkdir(parents=True)
        shutil.copy2(HARNESS, self.harness)
        self._targets = 0

    def sabotage(self, edits: tuple[tuple[str, str], ...]) -> None:
        """Apply each `(old, new)` edit to the copy, exactly once each."""
        text = self.harness.read_text(encoding="utf-8")
        for old, new in edits:
            assert text.count(old) == 1, f"this diversion no longer applies: {old!r}"
            text = text.replace(old, new, 1)
        _write(self.harness, text)

    def target(self, tests: str = SYNTH_TESTS, package: bool = True,
               merge_bytes: bytes | None = None) -> Path:
        """Build a synthetic project root and return it.

        Args:
            tests: The targeted test file's source.
            package: Whether the source root is a regular package.
            merge_bytes: Raw bytes for `merge.py`, for sources that are valid
                Python without being valid UTF-8.
        """
        self._targets += 1
        root = self.tmp / f"target{self._targets}"
        (root / "src" / "conductor").mkdir(parents=True)
        if package:
            _write(root / "src" / "conductor" / "__init__.py", "")
        if merge_bytes is None:
            _write(root / "src" / "conductor" / "merge.py", SYNTH_MERGE)
        else:
            (root / "src" / "conductor" / "merge.py").write_bytes(merge_bytes)
        (root / "tests").mkdir()
        _write(root / "tests" / "test_synth.py", tests)
        return root

    def run(self, target: Path, anchor: str = ANCHOR, replacement: str = KILLING,
            python=None, optimize: bool = False,
            extra_args: tuple[str, ...] = ()) -> subprocess.CompletedProcess:
        """Run the harness copy against `target` and capture everything."""
        driver = self.tmp / "drive.py"
        _write(driver, _driver(anchor, replacement))
        cmd = [str(python or sys.executable)]
        if optimize:
            cmd.append("-O")
        cmd += [str(driver), str(self.harness), "--root", str(target), *extra_args]
        return subprocess.run(cmd, capture_output=True, text=True, timeout=900)


@pytest.fixture
def lab(tmp_path):
    """A fresh harness copy and workspace, outside the repository."""
    return _Lab(tmp_path)


def _venv(where: Path):
    """Build a pip-less venv and return its interpreter."""
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(where)],
                   check=True, capture_output=True, timeout=300)
    return (where / "Scripts" / "python.exe") if os.name == "nt" \
        else (where / "bin" / "python")


@pytest.fixture(scope="session")
def pytest_free_python(tmp_path_factory):
    """An interpreter that cannot import pytest.

    The cheap, deterministic stand-in for the reviewers' `--without-pip` venv:
    it carries no packages and no `.pth`, so `python -m pytest` exits 1 there —
    the exit code the scorer reads as an honest kill.
    """
    return _venv(tmp_path_factory.mktemp("nopytest") / "venv")


@pytest.fixture(scope="session")
def shadowing_python(tmp_path_factory):
    """An interpreter whose own `conductor` package wins the import.

    A namespace portion (a source root with no `__init__.py`) loses to the
    regular package this `.pth` supplies, which is the shadowing condition made
    deterministic without depending on the ambient environment.
    """
    home = tmp_path_factory.mktemp("shadow")
    decoy = home / "decoy"
    (decoy / "conductor").mkdir(parents=True)
    _write(decoy / "conductor" / "__init__.py", "")
    _write(decoy / "conductor" / "merge.py", SYNTH_MERGE)
    python = _venv(home / "venv")
    purelib = subprocess.run(
        [str(python), "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
        check=True, capture_output=True, text=True, timeout=300).stdout.strip()
    _write(Path(purelib) / "_decoy.pth",
           f"{decoy}\n{Path(pytest.__file__).resolve().parents[1]}\n")
    return python


# --- the instrument measures something real before anything is broken ---


def test_the_synthetic_target_is_a_real_measurement(lab):
    target = lab.target()
    result = lab.run(target)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "baseline: 2 targeted tests green on unmutated source" in result.stdout
    assert "VERDICT: PASS - 1/1 mutations killed" in result.stdout
    assert (target / "src" / "conductor" / "merge.py").read_text(
        encoding="utf-8") == SYNTH_MERGE          # restored


def test_python_O_changes_nothing_about_a_clean_run(lab):
    target = lab.target()
    plain = lab.run(target)
    optimised = lab.run(target, optimize=True)
    assert plain.returncode == optimised.returncode == 0
    assert plain.stdout == optimised.stdout


# --- the inventory: one row per diversion the reviewers got away with ---


@dataclass(frozen=True)
class Diversion:
    """One reviewer diversion, and the difference the guard makes.

    Attributes:
        diversion: What was broken, in the reviewers' words.
        edits: `(old, new)` substitutions applied to the harness COPY.
        tests: The synthetic test file the target ships.
        package: Whether the synthetic source root is an importable package.
        anchor: The anchor the single synthetic mutation looks for.
        replacement: What that mutation substitutes.
        interpreter: Which interpreter fixture runs it, or None for this one.
        optimize: Whether to run under `python -O`.
        merge_bytes: Raw bytes for the target's `merge.py`, when the case needs
            a source that is valid Python and not valid UTF-8.
        guarded: A string the shipped harness must say.
        reopened: A string only the sabotaged copy says.
    """

    diversion: str
    edits: tuple[tuple[str, str], ...]
    guarded: str
    reopened: str
    tests: str = SYNTH_TESTS
    package: bool = True
    anchor: str = ANCHOR
    replacement: str = KILLING
    interpreter: str | None = None
    optimize: bool = False
    merge_bytes: bytes | None = None


NO_BASELINE = ("            green = check_baseline(source_root, root, resolved)",
               "            green = 0")

# Valid Python, valid latin-1, not valid UTF-8: it imports, its tests are green,
# and the instrument breaks on reading it rather than on measuring anything.
LATIN1_MERGE = ("# -*- coding: latin-1 -*-\n"
                "# caf\xe9 a comment the source encoding allows\n"
                + SYNTH_MERGE).encode("latin-1")

DIVERSIONS = [
    Diversion(
        diversion="F/anchor-rot: the anchor no longer matches, plain run",
        edits=(("    if found != 1:", "    if False:"),),
        anchor=DRIFTED,
        guarded="its anchor appears 0 times in the source",
        reopened="SURVIVED: the synthetic rule",
    ),
    Diversion(
        diversion="F/anchor-rot under python -O, where `assert` was stripped",
        edits=(("    if found != 1:", "    if False:"),),
        anchor=DRIFTED,
        optimize=True,
        guarded="its anchor appears 0 times in the source",
        reopened="SURVIVED: the synthetic rule",
    ),
    Diversion(
        diversion="S6: any nonzero pytest exit counts as a kill",
        edits=(("    if returncode == 1:", "    if returncode != 0:"),),
        replacement=UNPARSEABLE,
        guarded="usage, collection or internal error",
        reopened="VERDICT: PASS - 1/1 mutations killed",
    ),
    Diversion(
        diversion="F'': the targeted file is already red, so every mutation reads as KILLED",
        edits=(NO_BASELINE,),
        tests=RED_TESTS,
        guarded="not green on unmutated source",
        reopened="VERDICT: PASS - 1/1 mutations killed",
    ),
    Diversion(
        diversion="S16/S5: `pytest` dropped from IMPORT_PROBE, on a pytest-free interpreter",
        edits=(('"import pathlib, sys, conductor.merge, pytest; "',
                '"import pathlib, sys, conductor.merge; "'), NO_BASELINE),
        interpreter="pytest_free_python",
        guarded="the probe failed to import",
        reopened="VERDICT: PASS - 1/1 mutations killed",
    ),
    Diversion(
        diversion="S8: the `probe.returncode != 0` branch never runs",
        edits=(("    if probe.returncode != 0:", "    if False:"),),
        interpreter="pytest_free_python",
        guarded="the probe failed to import",
        # Without the branch the empty probe output resolves to the working
        # directory and the run blames a shadowed import for a missing pytest.
        reopened="came from a tree outside the source root",
    ),
    Diversion(
        diversion="S10: verification moved to after all the mutations",
        edits=(("        resolved = verify_import_root(source_root, root)",
                "        resolved = merge_path"),
               ("            results = run_mutations(merge_path, source_root, root)",
                "            results = run_mutations(merge_path, source_root, root)\n"
                "            verify_import_root(source_root, root)")),
        package=False,
        interpreter="shadowing_python",
        guarded="import isolation not confirmed",
        reopened="SURVIVED: the synthetic rule",
    ),
    Diversion(
        diversion="S14: the verdict word is hardcoded to PASS",
        edits=(('    verdict = "PASS" if killed == total else "FAIL"',
                '    verdict = "PASS"'),),
        replacement=SURVIVING,
        guarded="VERDICT: FAIL - 0/1 mutations killed",
        reopened="VERDICT: PASS - 0/1 mutations killed",
    ),
    Diversion(
        diversion="an exception that is not an InvalidMeasurement escapes main and exits 1",
        # A duplicate handler: the first clause already takes every
        # InvalidMeasurement, so with this edit nothing else is converted and
        # the traceback reaches the interpreter, which exits 1 — the code the
        # table gives an honest survivor.
        edits=(("    except Exception as exc:", "    except InvalidMeasurement as exc:"),),
        merge_bytes=LATIN1_MERGE,
        guarded="the instrument itself failed",
        # The traceback is what the contract says never reaches the outside,
        # and the guarded run names the exception without letting one out.
        reopened="Traceback (most recent call last)",
    ),
]


@pytest.mark.parametrize("case", DIVERSIONS, ids=lambda c: c.diversion)
def test_each_guard_still_closes_the_hole_its_diversion_opened(case, lab, request):
    python = request.getfixturevalue(case.interpreter) if case.interpreter else None
    kwargs = dict(anchor=case.anchor, replacement=case.replacement,
                  python=python, optimize=case.optimize)
    target = dict(tests=case.tests, package=case.package,
                  merge_bytes=case.merge_bytes)

    guarded = lab.run(lab.target(**target), **kwargs)
    lab.sabotage(case.edits)
    reopened = lab.run(lab.target(**target), **kwargs)

    guarded_output = guarded.stdout + guarded.stderr
    reopened_output = reopened.stdout + reopened.stderr
    assert case.guarded in guarded_output, guarded_output
    assert case.reopened not in guarded_output, guarded_output
    # The other half, without which the first proves nothing: the scenario
    # really does discriminate, because the diversion really does get through.
    assert case.reopened in reopened_output, reopened_output


# --- exit 2 carries no score, on every path that reaches it ---


@pytest.mark.parametrize("tests, expected", [
    (RED_TESTS, "pytest exited 1"),
    (SYNTH_TESTS + "\nthis is a collection error(\n", "pytest exited 2"),
    ("def helper():\n    return 1\n", "pytest exited 5"),
], ids=["already red", "collection error", "collects nothing"])
def test_a_baseline_that_is_not_green_stops_before_the_first_mutation(lab, tests, expected):
    target = lab.target(tests=tests)
    before = (target / "src" / "conductor" / "merge.py").read_bytes()

    result = lab.run(target)

    assert result.returncode == 2, result.stdout + result.stderr
    assert "not green on unmutated source" in result.stderr
    assert expected in result.stderr
    assert (target / "src" / "conductor" / "merge.py").read_bytes() == before
    assert SCORE not in result.stdout + result.stderr
    assert "KILLED" not in result.stdout and "SURVIVED" not in result.stdout


@pytest.mark.parametrize("kwargs, expected", [
    ({"anchor": DRIFTED}, "its anchor appears 0 times in the source"),
    ({"anchor": DRIFTED, "optimize": True}, "its anchor appears 0 times in the source"),
    ({"replacement": UNPARSEABLE}, "usage, collection or internal error"),
], ids=["drifted anchor", "drifted anchor under -O", "mutation breaks collection"])
def test_a_mutation_that_was_never_measured_is_never_a_score(lab, kwargs, expected):
    result = lab.run(lab.target(), **kwargs)

    assert result.returncode == 2, result.stdout + result.stderr
    assert expected in result.stderr
    assert "no mutation score" in result.stderr
    assert SCORE not in result.stdout + result.stderr


# --- the exit-code table, executed row by row rather than mentioned ---


_ROW = re.compile(r"^ {4}(?P<mode>\S+(?: \S+)*?)? {2,}(?P<code>\d)  (?P<meaning>.+)$")
SCORE_SHAPED = re.compile(r"\d+\s*/\s*\d+")


def harness_doc() -> str:
    """The shipped harness's module docstring, read from the file that ships."""
    return ast.get_docstring(ast.parse(HARNESS.read_text(encoding="utf-8")))


def exit_table(doc: str) -> list[tuple[str, int, str]]:
    """Read the exit-code table out of the harness docstring.

    Args:
        doc: The harness module docstring.

    Returns:
        One `(mode, code, meaning)` triple per row, continuation lines folded
        into the meaning they belong to.
    """
    block = doc.split("Exit codes.", 1)[1].split("Exit 2 carries", 1)[0]
    rows: list[tuple[str, int, str]] = []
    mode = ""
    for line in block.splitlines():
        row = _ROW.match(line)
        if row:
            mode = row.group("mode") or mode
            rows.append((mode, int(row.group("code")), row.group("meaning")))
        elif rows and line.startswith("        ") and line.strip():
            last_mode, last_code, meaning = rows[-1]
            rows[-1] = (last_mode, last_code, f"{meaning} {line.strip()}")
    return rows


def claims_of(meaning: str) -> set[str]:
    """Name the checkable claims a row makes, read from what the row says."""
    claims = set()
    if "every mutation killed" in meaning:
        claims.add("all killed")
    if "a mutation survived" in meaning:
        claims.add("a survivor")
    if "invalid" in meaning or "never started" in meaning \
            or "did not check out" in meaning or "usage error" in meaning:
        claims.add("nothing measured")
    if "no mutations were run" in meaning.lower():
        claims.add("no mutations run")
    if "not used" in meaning:
        claims.add("unreachable")
    return claims


def _score(output: str) -> tuple[int, int]:
    """Return the `(killed, total)` the run reported, or `(-1, -1)` for none."""
    found = re.search(r"(\d+)/(\d+) mutations killed", output)
    return (int(found.group(1)), int(found.group(2))) if found else (-1, -1)


def test_every_row_of_the_exit_code_table_is_a_run_that_produced_it(lab):
    # The table was true when it was written and nothing kept it true: the only
    # test that looked at it checked that two substrings occurred in the
    # docstring, so the whole table could be replaced by one contradicting the
    # code on every row with the suite still green. Here each row is parsed out
    # of the prose, matched to a run that really produced that code in that
    # mode, and the row's own words are checked against what the run printed.
    no_engine = lab.target()
    (no_engine / "src" / "conductor" / "merge.py").unlink()
    runs = {
        ("normal run", 0): lab.run(lab.target()),
        ("normal run", 1): lab.run(lab.target(), replacement=SURVIVING),
        ("normal run", 2): lab.run(lab.target(), anchor=DRIFTED),
        ("--verify-only", 0): lab.run(lab.target(), extra_args=("--verify-only",)),
        ("--verify-only", 2): lab.run(no_engine, extra_args=("--verify-only",)),
    }
    rows = exit_table(harness_doc())
    assert rows, "no exit-code table could be read out of the docstring"
    unreachable = {(mode, code) for mode, code, meaning in rows
                   if "unreachable" in claims_of(meaning)}
    assert {(mode, code) for mode, code, _ in rows} - unreachable == set(runs)

    for mode, code, meaning in rows:
        claims = claims_of(meaning)
        assert claims, f"row {mode} {code} makes no claim this test can check: {meaning}"
        if "unreachable" in claims:
            assert all(run.returncode != code for (m, _), run in runs.items() if m == mode)
            continue
        run = runs[(mode, code)]
        output = run.stdout + run.stderr
        assert run.returncode == code, output
        killed, total = _score(output)
        if "all killed" in claims:
            assert total > 0 and killed == total, output
        if "a survivor" in claims:
            assert "SURVIVED" in output and 0 <= killed < total, output
        if "nothing measured" in claims:
            assert not SCORE_SHAPED.search(output) and SCORE not in output, output
        if "no mutations run" in claims:
            assert "no mutations were run" in output, output
            assert not SCORE_SHAPED.search(output), output
