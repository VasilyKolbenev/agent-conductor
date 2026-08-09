"""Sabotage suite for `scripts/mutate_merge.py` — the guards, kept honest.

Four independent reviews broke guards of this harness by hand and recorded,
each time, that nothing noticed. A report proves a guard held on the day it was
written; only a test proves it still holds after the next edit. Each case
re-creates one of those diversions and pins the difference between a guarded
run and a sabotaged one.

Where the cases live, and why they are not all here. `DIVERSIONS` below carries
the ones that need a running instrument: a harness copy is sabotaged, pointed
at a synthetic target, and the two runs are compared. The rest pin a single
function's behaviour, and live in tests/test_mutate_harness.py, or they pin the
shipped script's structure and prose, and live in
tests/test_mutate_harness_contract.py. Counting rows in any one file therefore
undercounts, so no file is the inventory: `INVENTORY` is, and
`test_the_inventory_of_diversions_is_complete_and_every_entry_resolves` fails if
a case loses the test that pins it, wherever that test lives. The inventory
below is complete: sixteen cases from the first review round and nine from the
second, one of which is a guard that never existed rather than one that broke.

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
SIBLINGS = (ROOT / "tests" / "test_mutate_harness.py",
            ROOT / "tests" / "test_mutate_harness_contract.py")

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
               merge_bytes: bytes | None = None, shadow_package: bool = False) -> Path:
        """Build a synthetic project root and return it.

        Args:
            tests: The targeted test file's source.
            package: Whether the source root is a regular package.
            merge_bytes: Raw bytes for `merge.py`, for sources that are valid
                Python without being valid UTF-8.
            shadow_package: Also ship a `conductor/merge/` package, which wins
                the import over the `merge.py` the harness would mutate.
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
        if shadow_package:
            (root / "src" / "conductor" / "merge").mkdir()
            _write(root / "src" / "conductor" / "merge" / "__init__.py", SYNTH_MERGE)
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
        shadow_package: Whether the target also ships a `conductor/merge/`
            package, which wins the import over the file being mutated.
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
    shadow_package: bool = False


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
        edits=(("        resolved = verify_import_root(source_root, root, merge_path)",
                "        resolved = merge_path"),
               ("            results = run_mutations(merge_path, source_root, root)",
                "            results = run_mutations(merge_path, source_root, root)\n"
                "            verify_import_root(source_root, root, merge_path)")),
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
    Diversion(
        diversion="the import root is checked for membership but not for identity",
        edits=(("    if resolved != merge_path.resolve():", "    if False:"),),
        shadow_package=True,
        guarded="is not the file this run mutates",
        reopened="SURVIVED: the synthetic rule",
    ),
]


@pytest.mark.parametrize("case", DIVERSIONS, ids=lambda c: c.diversion)
def test_each_guard_still_closes_the_hole_its_diversion_opened(case, lab, request):
    python = request.getfixturevalue(case.interpreter) if case.interpreter else None
    kwargs = dict(anchor=case.anchor, replacement=case.replacement,
                  python=python, optimize=case.optimize)
    target = dict(tests=case.tests, package=case.package,
                  merge_bytes=case.merge_bytes, shadow_package=case.shadow_package)

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


# --- the inventory: every diversion either has a test, or a stated reason ---


PINS = ("row", "behaviour", "structure", "prose")


@dataclass(frozen=True)
class Case:
    """One diversion from a review, and the test that now catches it.

    Attributes:
        diversion: What was broken, in the reviewers' words.
        round: Which review round broke it, 1 or 2.
        pin: How it is held. `row` re-applies the diversion to a harness copy
            and runs it; `behaviour` executes the guarded code and asserts what
            it does; `structure` reads the module's shape; `prose` pins a claim
            about code whose defect is deliberately still open.
        pinned_by: Names of the tests that catch it. A `row` case names one of
            the `DIVERSIONS` ids above; every other name is a test function,
            here or in tests/test_mutate_harness.py.
        why_not_automated: Required of, and only of, a `prose` case: why no
            test re-applies the diversion itself.
    """

    diversion: str
    round: int
    pin: str
    pinned_by: tuple[str, ...]
    why_not_automated: str = ""


INVENTORY = [
    Case("spec B: a hard kill between the mutation write and the restore leaves a "
         "mutated merge.py and says nothing", 1, "prose",
         ("test_the_docstring_admits_the_window_the_restore_design_leaves_open",),
         "crash-safe restore is a separate task by owner decision, so the design still "
         "has this window and the honest guard is the prose that admits it"),
    Case("spec F: anchor rot under python -O, where `assert` was stripped", 1, "row",
         ("F/anchor-rot under python -O, where `assert` was stripped",
          "test_the_anchor_check_still_runs_under_python_O")),
    Case("spec F': a targeted test file that cannot be collected, so pytest exits 2 "
         "and the mutation is never measured", 1, "row",
         ("S6: any nonzero pytest exit counts as a kill",
          "test_a_pytest_exit_that_is_not_a_test_result_is_an_invalid_measurement")),
    Case("spec F'': the targeted file is already red, so every mutation reads as KILLED",
         1, "row",
         ("F'': the targeted file is already red, so every mutation reads as KILLED",
          "test_a_red_targeted_file_stops_the_run_before_the_first_mutation")),
    Case("spec S11: the provenance source-root line hardcoded to a lie", 1, "behaviour",
         ("test_provenance_prints_the_path_the_probe_resolved_not_the_expected_one",
          "test_verify_only_confirms_the_import_root_and_says_no_mutations_were_run")),
    Case("spec S12: the provenance interpreter line hardcoded to a lie", 1, "behaviour",
         ("test_verify_only_confirms_the_import_root_and_says_no_mutations_were_run",)),
    Case("spec S13: print_provenance prints the expected merge path, not the resolved one",
         1, "behaviour",
         ("test_provenance_prints_the_path_the_probe_resolved_not_the_expected_one",)),
    Case("spec S14: the verdict word is hardcoded to PASS", 1, "row",
         ("S14: the verdict word is hardcoded to PASS",
          "test_the_verdict_word_follows_the_score_it_reports")),
    Case("spec S16: `pytest` dropped from IMPORT_PROBE", 1, "row",
         ("S16/S5: `pytest` dropped from IMPORT_PROBE, on a pytest-free interpreter",
          "test_an_interpreter_that_cannot_run_a_test_cannot_produce_a_score")),
    Case("quality S5: `pytest` dropped from IMPORT_PROBE — the same edit to the same "
         "constant under the same interpreter condition as spec S16, merged into one row",
         1, "row",
         ("S16/S5: `pytest` dropped from IMPORT_PROBE, on a pytest-free interpreter",)),
    Case("quality S6: any nonzero pytest exit counts as a kill", 1, "row",
         ("S6: any nonzero pytest exit counts as a kill",
          "test_a_pytest_exit_that_is_not_a_test_result_is_an_invalid_measurement")),
    Case("quality S8: the `probe.returncode != 0` branch never runs", 1, "row",
         ("S8: the `probe.returncode != 0` branch never runs",
          "test_an_interpreter_that_cannot_run_a_test_cannot_produce_a_score")),
    Case("quality S9: no restore after a mutation write that truncates before failing",
         1, "behaviour",
         ("test_a_mutation_write_that_truncates_before_failing_is_restored",)),
    Case("quality S10: verification moved to after all the mutations", 1, "row",
         ("S10: verification moved to after all the mutations",
          "test_a_shadowed_import_root_refuses_before_any_mutation_and_never_scores")),
    Case("quality anchor rot on a plain run: the anchor no longer matches merge.py",
         1, "row",
         ("F/anchor-rot: the anchor no longer matches, plain run",
          "test_an_anchor_that_no_longer_matches_is_an_invalid_measurement_not_a_survivor")),
    Case("quality PYTHONNOUSERSITE: the docstring's stated reason for the flag does not "
         "hold, because PYTHONPATH precedes every site directory", 1, "prose",
         ("test_the_pythonnousersite_reason_is_the_one_that_holds",),
         "the finding was about the prose and not about behaviour: a reviewer installed "
         "a real user-site package and confirmed the rewritten claim by execution"),
    Case("spec: an exception that is not an InvalidMeasurement escapes main, so the "
         "process exits 1 — the code reserved for an honest survivor", 2, "row",
         ("an exception that is not an InvalidMeasurement escapes main and exits 1",
          "test_an_instrument_failure_that_is_not_an_invalid_measurement_still_exits_two",
          "test_nothing_main_does_after_reading_its_arguments_runs_outside_the_funnel")),
    Case("quality: tempfile.mkdtemp raises OSError inside check_baseline, before the "
         "baseline has run", 2, "behaviour",
         ("test_a_workspace_that_cannot_be_created_is_not_a_surviving_mutation",
          "test_an_instrument_failure_that_is_not_an_invalid_measurement_still_exits_two")),
    Case("spec: `_QUIET_FAILURE = EXIT_INVALID` and `return _QUIET_FAILURE` — a second "
         "exit-2 door under another name, printing a fabricated score", 2, "structure",
         ("test_exit_two_is_returned_by_one_helper_and_by_nothing_else_in_the_module",)),
    Case("spec: the same alias taken with `sys.exit` instead of `return`, which the guard "
         "still read by the spelling of its argument", 2, "structure",
         ("test_exit_two_is_returned_by_one_helper_and_by_nothing_else_in_the_module",
          "test_the_exit_surface_guard_reads_the_doors_and_not_the_spelling_of_a_code")),
    Case("spec: main hands print_provenance the path it is about to mutate instead of "
         "the one the probe resolved", 2, "behaviour",
         ("test_main_verifies_the_file_it_will_mutate_and_shows_what_the_probe_resolved",)),
    Case("quality: check_baseline calls subprocess.run itself with a second environment "
         "builder that agrees today", 2, "structure",
         ("test_one_place_in_the_module_starts_a_pytest_and_it_is_run_pytest",
          "test_the_baseline_and_the_mutant_runs_come_from_one_environment")),
    Case("quality: the whole exit-code table replaced by one that contradicts the code "
         "on every row", 2, "behaviour",
         ("test_every_row_of_the_exit_code_table_is_a_run_that_produced_it",)),
    Case("quality: a true unrelated sentence containing the word `always` reddens the "
         "guard on the restore prose", 2, "structure",
         ("test_the_restore_window_guard_reads_the_claim_and_not_the_word_always",)),
    Case("the guard that never existed: the import is checked for membership of the "
         "source root but never for being the file the run mutates", 2, "row",
         ("the import root is checked for membership but not for identity",
          "test_an_import_under_the_source_root_is_still_refused_when_it_is_another_file")),
]

_NUMBERS = {"sixteen": 16, "eight": 8, "seven": 7, "nine": 9, "ten": 10}


def _test_names(path: Path) -> set[str]:
    """Every test function defined in a test module, read from its AST."""
    return {node.name for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")}


def test_the_inventory_of_diversions_is_complete_and_every_entry_resolves():
    # The docstring names a count and the module shows fewer rows than that,
    # because half the pins are prose and structure and live next door. An
    # auditor counting rows cannot tell a deliberate split from cases silently
    # dropped, and a coincidental "16 passed" makes the undercount plausible.
    # So the split is written down as data and checked: every name here must
    # resolve to a test that exists in one of the three modules, every
    # parametrised row must be claimed by an entry, and the counts stated in
    # the docstring must be the counts in the table.
    known = _test_names(Path(__file__)) | {case.diversion for case in DIVERSIONS}
    for sibling in SIBLINGS:
        known |= _test_names(sibling)
    for case in INVENTORY:
        assert case.pinned_by, case.diversion
        for name in case.pinned_by:
            assert name in known, f"{case.diversion!r} points at a missing test: {name}"

    claimed = {name for case in INVENTORY for name in case.pinned_by}
    assert {case.diversion for case in DIVERSIONS} <= claimed

    stated = re.search(
        r"(\w+) cases from the first review round and (\w+) from the second",
        " ".join(__doc__.split()))
    assert stated, "the docstring no longer states how many cases the inventory has"
    first, second = stated.groups()
    assert _NUMBERS[first] == sum(1 for case in INVENTORY if case.round == 1)
    assert _NUMBERS[second] == sum(1 for case in INVENTORY if case.round == 2)
    assert len({case.diversion for case in INVENTORY}) == len(INVENTORY)


def test_a_case_pinned_only_by_prose_is_the_only_kind_that_states_a_reason():
    # The rule that keeps the inventory honest rather than merely complete. A
    # diversion may be left without a test that re-applies it, but not
    # silently: `prose` is the only pin that admits that, and it must say why.
    rows = {case.diversion for case in DIVERSIONS}
    for case in INVENTORY:
        assert case.pin in PINS, case.diversion
        assert bool(case.why_not_automated) == (case.pin == "prose"), case.diversion
        named_rows = rows & set(case.pinned_by)
        assert bool(named_rows) == (case.pin == "row"), case.diversion
        if case.pin != "row":
            assert all(name.startswith("test_") for name in case.pinned_by), case.diversion
