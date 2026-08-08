"""Mutation-testing harness for the merge engine (dev-only, mirrors the KALI
discipline: a green test suite that can't catch a mutated rule is not proof
of anything).

For each mutation below: apply ONE source-text substitution in place to
`src/conductor/merge.py`, run the targeted test file, and require pytest to
exit 1 — a genuine test failure, the only exit code that is a kill. Any other
nonzero exit (2-5: usage, collection or internal errors) means the mutation
was never measured, and an unmeasured mutation may not be folded into a score.
The original bytes are restored from an in-memory copy and the restore is
PROVED by content hash.

Before the first mutation the harness checks two things about itself. Where
`conductor.merge` is actually imported from: file isolation is not
verification isolation, so an editable install (a `.pth` in site-packages) or
an installed copy can shadow an exported tree, and the harness would mutate
one file while pytest imported another and print a plausible score that means
nothing. Belonging to the source root is not enough there — the import must
resolve to the very file the run mutates, byte for byte the same path, because
a root carrying both `conductor/merge.py` and a `conductor/merge/` package
passes any looser test while every mutation lands in a file nobody imports.
And whether the targeted tests are green on unmutated source: a test file that
is already red reports every mutation aimed at it as KILLED.

What the restore does and does not promise. An `OSError` in the restore is
retried, and when the content hash still cannot be confirmed the run stops and
names the file that may still carry a mutation. A hard kill of the process
between the mutation write and the restore is outside that promise: it leaves
a mutated `merge.py` and says nothing at all. Crash-safe restore — writing
beside the target and renaming, or restoring from git — is a separate task
with its own review, queued as the first backlog item in
docs/plans/2026-08-03-p0-control-loop-and-december-ui.md §10.

Exit codes. The code describes whether the mode that was REQUESTED succeeded;
it is not in every mode a mutation score.

    normal run      0  valid measurement, every mutation killed
                    1  valid measurement, a mutation survived
                    2  the measurement is invalid or never started
    --verify-only   0  the instrument checked out; NO mutations were run, so
                       this zero does not mean any mutation was killed
                    2  the instrument did not check out, or a usage error
                    1  not used

Exit 2 carries no mutation score of any kind — not `0/13`, not a zero. Every
path THIS MODULE takes to it runs through `_invalid_measurement`, and the score
is printed by a function that path never reaches. An exception the instrument
did not expect is such a path: `main` converts anything that is not already an
`InvalidMeasurement` into one, because a traceback escaping to the interpreter
would exit 1 — the code reserved for an honest survivor. The traceback is not
part of the contract; the named infrastructure failure and the 2 are. There is
exactly one more way out with a 2, and it is not in this module: `argparse`
exits 2 itself on an unrecognised argument. That overlap is deliberate and means the same thing — a
usage error is likewise a run in which no valid measurement happened — and
argparse prints usage to stderr and stops before anything is measured, so the
rule holds on that path too.

Usage:
    .venv\\Scripts\\python scripts\\mutate_merge.py          # in-tree, as CI runs it
    python scripts/mutate_merge.py --root DIR               # an exported tree
    python scripts/mutate_merge.py --verify-only            # provenance, no mutation
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parent.parent

EXIT_OK = 0
EXIT_SURVIVORS = 1
EXIT_INVALID = 2                 # no score is printed on this path — see above

RESTORE_ATTEMPTS = 3
RESTORE_DELAY_S = 0.2
SUBPROCESS_TIMEOUT_S = 180       # nothing the harness starts may hang it

# `pytest` is imported by the probe on purpose: PYTHONNOUSERSITE hides a
# user-site pytest, and `python -m pytest` without pytest exits 1 — which this
# harness would otherwise read as an honest kill.
IMPORT_PROBE = (
    "import pathlib, sys, conductor.merge, pytest; "
    "sys.stdout.write(str(pathlib.Path(conductor.merge.__file__).resolve()))"
)


class InvalidMeasurement(RuntimeError):
    """This run cannot produce a mutation score, so it must not print one."""


# Adjacent §6.1 ladder rows, verbatim, so a swap is assembled from them: the
# status ladder and the action ladder are written out twice by hand, and only
# a test keeps `project_status.reason` and `next_action.kind` in agreement.
ACTION_FIX_LANE = (
    '    broken = _broken_lanes(state)\n'
    '    if broken:\n'
    '        return _action("fix_lane", broken[0],\n'
    '                       f"Fix conductor/lanes/{broken[0]}.json '
    '— the lane cannot be read.")\n'
)
ACTION_FIX_INVARIANT = (
    '    bad = _broken_invariants(state)\n'
    '    if bad:\n'
    '        return _action("fix_invariant", bad[0], '
    'f"Restore the broken invariant {bad[0]}.")\n'
)
STATUS_BROKEN_LANE = (
    '    broken = _broken_lanes(state)\n'
    '    if broken:\n'
    '        return _blocked("broken_lane", f"lane {broken[0]} is unreadable" '
    'if len(broken) == 1\n'
    '                        else f"{len(broken)} lanes are unreadable")\n'
)
STATUS_INVARIANT = (
    '    bad = _broken_invariants(state)\n'
    '    if bad:\n'
    '        return _blocked("invariant_broken", f"invariant {bad[0]} is broken" '
    'if len(bad) == 1\n'
    '                        else f"{len(bad)} invariants are broken")\n'
)

# Each mutation: (name, anchor, replacement, test file it must turn red)
MUTATIONS: list[tuple[str, str, str, str]] = [
    (
        "disagreement requires refuted only (drop partial)",
        '    if any(vd["disposition"] in ("refuted", "partial") for vd in others.values()):',
        '    if any(vd["disposition"] in ("refuted",) for vd in others.values()):',
        "tests/test_merge_review.py",
    ),
    (
        "self-verdict exclusion dropped",
        '            others = {a: vd for a, vd in all_verdicts.items() if a != view["author"]}',
        "            others = dict(all_verdicts)",
        "tests/test_merge_review.py",
    ),
    (
        "collision suspension dropped",
        "        collided = len(owner_list) > 1",
        "        collided = False",
        "tests/test_merge_review.py",
    ),
    (
        "stale lanes skipped in _nodes voting",
        '    for v in live:\n'
        '        for nid, status in (v["_data"].get("map_status") or {}).items():',
        '    for v in live:\n'
        '        if v["stale"]: continue\n'
        '        for nid, status in (v["_data"].get("map_status") or {}).items():',
        "tests/test_merge_nodes.py",
    ),
    (
        "future-exclusion dropped in _cycle",
        '        if phase is None or v["stale"] or v["_future"] or v["_dt"] is None:',
        '        if phase is None or v["stale"] or v["_dt"] is None:',
        "tests/test_merge_queue_phase.py",
    ),
    (
        "future-voter total exclusion dropped in _nodes (eligible -> cast)",
        '        eligible = [c for c in cast if not c[1]]   # future voters never win (owner decision)',
        '        eligible = cast   # future voters never win (owner decision)',
        "tests/test_merge_nodes.py",
    ),
    (
        "pending_verdicts: self-verdict exclusion dropped",
        '            if not any(v.get("role") == rid for a, v in f["verdicts"].items()\n'
        '                       if a != f["author"]):',
        '            if not any(v.get("role") == rid for a, v in f["verdicts"].items()):',
        "tests/test_merge_pending.py",
    ),
    (
        "pending_verdicts: suspended skip dropped (condition inverted)",
        '        if f["review_state"] == "suspended":\n'
        '            continue',
        '        if f["review_state"] != "suspended":\n'
        '            continue',
        "tests/test_merge_pending.py",
    ),
    (
        "action ladder: fix_lane and fix_invariant rows swapped",
        ACTION_FIX_LANE + ACTION_FIX_INVARIANT,
        ACTION_FIX_INVARIANT + ACTION_FIX_LANE,
        "tests/test_merge_status.py",
    ),
    (
        "status ladder: broken_lane and invariant_broken rows swapped",
        STATUS_BROKEN_LANE + STATUS_INVARIANT,
        STATUS_INVARIANT + STATUS_BROKEN_LANE,
        "tests/test_merge_status.py",
    ),
    (
        "complete: stale-lane clause dropped (a stale lane could read as success)",
        '            and not any(ln["broken"] or ln["stale"] for ln in state["lanes"]))',
        '            and not any(ln["broken"] for ln in state["lanes"]))',
        "tests/test_merge_status.py",
    ),
    (
        "next_action: start_work guard widened from ready to not-complete",
        '    if state["project_status"]["state"] == "ready":',
        '    if state["project_status"]["state"] != "complete":',
        "tests/test_merge_status.py",
    ),
    (
        "role projection: stage presence guard dropped (absent stage becomes null)",
        '    if "stage" in role:\n        out["stage"] = role["stage"]\n',
        '    out["stage"] = role.get("stage")\n',
        "tests/test_merge_queue_phase.py",
    ),
]


def subprocess_env(source_root: Path) -> dict[str, str]:
    """Build the one environment every harness subprocess runs in.

    PYTHONPATH is replaced, never extended: an inherited value is exactly the
    ambiguity this harness exists to remove. PYTHONNOUSERSITE hides a user-site
    pytest, so the probe's `import pytest` means the pytest the mutation runs
    will actually use; it does not decide which `conductor` wins, because
    PYTHONPATH already precedes every site directory on `sys.path`.
    PYTHONDONTWRITEBYTECODE is a
    correctness guard, not a speed one: a mutation of identical byte length
    (`==` -> `!=`) can poison `__pycache__`, because Python's timestamp+size
    staleness check misses the mutate->restore round-trip and later clean runs
    then import the MUTATED bytecode (phantom failures on a clean git diff).

    Args:
        source_root: The `src` directory that must own the `conductor` package.

    Returns:
        A complete environment mapping for `subprocess.run`.
    """
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHONPATH"] = str(source_root)
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _is_inside(path: Path, root: Path) -> bool:
    """Return whether `path` resolves to somewhere under `root`."""
    try:
        return path.resolve().is_relative_to(root.resolve())
    except OSError:                                   # unresolvable path
        return False


def _shadow_report(resolved: Path, source_root: Path) -> str:
    """Say which copy won the import, and that no score exists for this run."""
    if any(p.name in ("site-packages", "dist-packages") for p in resolved.parents):
        where = "an installed copy under site-packages"
    elif _is_inside(resolved, ROOT):
        where = "the working tree"
    else:
        where = "a tree outside the source root"
    return (f"import isolation not confirmed - conductor.merge came from {where}.\n"
            f"  source root under measurement: {source_root}\n"
            f"  conductor.merge imported from: {resolved}\n"
            f"  interpreter:                   {sys.executable}\n"
            "  The harness would have mutated one file while pytest imported\n"
            "  another. No mutation was applied and nothing was measured, so\n"
            "  this run has no mutation score - not even a zero.")


def _wrong_file_report(resolved: Path, merge_path: Path) -> str:
    """Say that the imported file is under the root but is not the mutated one."""
    return ("import isolation not confirmed - conductor.merge lies under the "
            "source root but is not the file this run mutates.\n"
            f"  conductor.merge imported from: {resolved}\n"
            f"  the file that would be mutated: {merge_path}\n"
            "  A package beats a module of the same name, so a root carrying\n"
            "  both loses every mutation into a file nobody imports. No\n"
            "  mutation was applied and nothing was measured, so this run has\n"
            "  no mutation score - not even a zero.")


def verify_import_root(source_root: Path, cwd: Path, merge_path: Path) -> Path:
    """Confirm `conductor.merge` imports from the file this run will mutate.

    Runs in the same subprocess environment the mutations will run in, before
    the first mutation, because file isolation is not verification isolation.
    Membership of `source_root` is the weaker half and is checked first, for
    the sake of the message it produces; the requirement is exact equality with
    `merge_path`, since a mutation of any other file measures nothing.

    Args:
        source_root: The `src` directory that must own the import.
        cwd: Working directory for the probe, as for the test runs.
        merge_path: The file the mutations will be written to.

    Returns:
        The resolved path of `conductor.merge.__file__`.

    Raises:
        InvalidMeasurement: The probe could not run, the import failed, it
            resolved outside `source_root`, or it resolved to some other file
            under it.
    """
    try:
        probe = subprocess.run(
            [sys.executable, "-c", IMPORT_PROBE], cwd=cwd, capture_output=True,
            text=True, timeout=SUBPROCESS_TIMEOUT_S, env=subprocess_env(source_root))
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise InvalidMeasurement(f"the import probe could not run: {exc}") from exc
    if probe.returncode != 0:
        raise InvalidMeasurement(
            "import isolation not confirmed - the probe failed to import\n"
            f"  conductor.merge and pytest with PYTHONPATH={source_root}:\n"
            f"{probe.stderr.strip()}")
    resolved = Path(probe.stdout.strip())
    if not _is_inside(resolved, source_root):
        raise InvalidMeasurement(_shadow_report(resolved, source_root))
    if resolved != merge_path.resolve():
        raise InvalidMeasurement(_wrong_file_report(resolved, merge_path))
    return resolved


def print_provenance(source_root: Path, resolved: Path) -> None:
    """Print what this run measured and where it came from (DO-7 reads this).

    Args:
        source_root: The verified source root.
        resolved: The verified `conductor.merge.__file__`.
    """
    print("--- provenance ---")
    print(f"source root:     {source_root}")
    print(f"conductor.merge: {resolved}")
    print(f"interpreter:     {sys.executable}")
    print("------------------")


def targeted_test_files() -> list[str]:
    """Return every test file the mutations are scored against, in order.

    Returns:
        The distinct `test_file` entries of `MUTATIONS`, declaration order kept.
    """
    files: list[str] = []
    for _, _, _, test_file in MUTATIONS:
        if test_file not in files:
            files.append(test_file)
    return files


def run_pytest(argv: list[str], source_root: Path, cwd: Path) -> subprocess.CompletedProcess:
    """Run pytest the one way this harness ever runs it.

    Both the baseline and every mutant run come through here, so the
    interpreter, the working directory and the environment cannot drift apart
    between what the baseline proved and what the mutations were measured in.

    Args:
        argv: Arguments after `-m pytest`.
        source_root: Source root the subprocess imports from.
        cwd: Working directory for pytest.

    Returns:
        The completed process, output captured as text.
    """
    return subprocess.run(
        [sys.executable, "-m", "pytest", *argv],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=SUBPROCESS_TIMEOUT_S,
        env=subprocess_env(source_root),
    )


def run_targeted_test(test_file: str, source_root: Path, cwd: Path) -> int:
    """Run one targeted test file against the currently mutated source.

    Args:
        test_file: Path of the test file, relative to `cwd`.
        source_root: Source root the subprocess imports from.
        cwd: Working directory for pytest.

    Returns:
        The pytest exit code.
    """
    return run_pytest([test_file, "-q"], source_root, cwd).returncode


def _collected_tests(report: Path) -> int:
    """Count the test cases pytest recorded in its JUnit report.

    Args:
        report: The `--junit-xml` file pytest was asked to write.

    Returns:
        The number of `testcase` elements in the report.

    Raises:
        InvalidMeasurement: The report is missing or unreadable, so how many
            tests actually ran is unknown.
    """
    try:
        root = ElementTree.parse(report).getroot()
    except (OSError, ElementTree.ParseError) as exc:
        raise InvalidMeasurement(
            f"the baseline test report could not be read ({exc}), so how many "
            "tests ran is unknown and nothing here can be measured.") from exc
    return len(root.findall(".//testcase"))


def check_baseline(source_root: Path, cwd: Path, resolved: Path) -> int:
    """Prove the targeted tests are green on unmutated source, before mutating.

    A targeted test file that is already red reports every mutation aimed at it
    as KILLED — the same defect class as a wrong import root, a plausible
    number that measures nothing. This runs the exact set of files the
    mutations are scored against, through `run_pytest`, so it uses the same
    interpreter, PYTHONPATH, working directory and environment the mutant runs
    will use, against the import root `verify_import_root` has just confirmed.
    A green exit is not enough on its own: pytest exits 5, not 0, when it
    collects nothing, but the count is checked rather than inferred.

    Args:
        source_root: The verified source root.
        cwd: Working directory for pytest, as for the mutant runs.
        resolved: The confirmed `conductor.merge.__file__`, named in failures.

    Returns:
        The number of tests that ran.

    Raises:
        InvalidMeasurement: The run was not green, collected nothing, or could
            not complete. No mutation has been applied at that point.
    """
    workspace = Path(tempfile.mkdtemp(prefix="mutate_merge_baseline_"))
    report = workspace / "baseline.xml"
    try:
        try:
            result = run_pytest([*targeted_test_files(), "-q", f"--junit-xml={report}"],
                                source_root, cwd)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise InvalidMeasurement(
                f"the baseline test run could not complete: {exc}") from exc
        if result.returncode != 0:
            raise InvalidMeasurement(_baseline_report(result, resolved))
        collected = _collected_tests(report)
        if collected == 0:
            raise InvalidMeasurement(
                "the baseline run collected no test at all, so its green exit "
                "proves nothing.\n"
                f"  test files: {', '.join(targeted_test_files())}")
        return collected
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def _baseline_report(result: subprocess.CompletedProcess, resolved: Path) -> str:
    """Say why the unmutated tree is not a thing anything can be measured against."""
    tail = "\n".join(f"  | {line}" for line
                     in (result.stdout + result.stderr).strip().splitlines()[-15:])
    return (f"the targeted tests are not green on unmutated source (pytest "
            f"exited {result.returncode}).\n"
            f"  conductor.merge under measurement: {resolved}\n"
            "  A mutation aimed at an already-red file reads as KILLED, so\n"
            f"  nothing here can be measured.\n{tail}")


def apply_mutation(name: str, original: bytes, anchor: str, replacement: str) -> bytes:
    """Return `original` with `anchor` replaced once by `replacement`.

    The anchor count is CHECKED, never asserted: `assert` disappears under
    `python -O`, and without the check `str.replace` silently substitutes
    nothing and the unapplied mutation is scored as SURVIVED.

    Args:
        name: The mutation's catalogue name, for the failure message.
        original: The unmutated source bytes.
        anchor: The text the mutation replaces.
        replacement: The text it is replaced with.

    Returns:
        The mutated source bytes.

    Raises:
        InvalidMeasurement: The anchor does not appear exactly once, so the
            catalogue has drifted from the merge engine.
    """
    text = original.decode("utf-8")
    found = text.count(anchor)
    if found != 1:
        raise InvalidMeasurement(
            f"mutation {name!r}: its anchor appears {found} times in the source, "
            "not once, so the mutation catalogue has drifted from the merge "
            "engine. No mutation was applied and nothing was measured.\n"
            f"  anchor: {anchor!r}")
    return text.replace(anchor, replacement, 1).encode("utf-8")


def restore_source(path: Path, original: bytes) -> None:
    """Restore `path` from the in-memory original and prove it by content hash.

    An `OSError` here used to escape a `finally` block with the mutation still
    applied and the check that would have caught it unrun. A poisoned tree
    makes every later run measure code that is not in the repository, so a
    restore that cannot be confirmed is fatal and loud, never quiet.

    Args:
        path: The file to restore.
        original: The bytes the file must contain afterwards.

    Raises:
        InvalidMeasurement: The content could not be confirmed within
            `RESTORE_ATTEMPTS`. The file may still carry a mutation.
    """
    want = hashlib.sha256(original).hexdigest()
    problem = "unknown"
    for attempt in range(RESTORE_ATTEMPTS):
        try:
            if hashlib.sha256(path.read_bytes()).hexdigest() == want:
                return
            path.write_bytes(original)
            if hashlib.sha256(path.read_bytes()).hexdigest() == want:
                return
            problem = "the bytes on disk still differ after rewriting"
        except OSError as exc:
            problem = f"{type(exc).__name__}: {exc}"
        if attempt + 1 < RESTORE_ATTEMPTS:
            time.sleep(RESTORE_DELAY_S * (attempt + 1))
    raise InvalidMeasurement(
        f"restore could not be confirmed after {RESTORE_ATTEMPTS} attempts "
        f"({problem}).\n"
        f"  THE FILE MAY STILL CARRY A MUTATION: {path}\n"
        f"  Restore it before running anything else:  git checkout -- {path}")


def clear_pycache(source_root: Path) -> None:
    """Delete every `__pycache__` under `source_root` on the way out.

    Stale bytecode outlives a restore: a mutation of identical byte length
    defeats Python's timestamp+size staleness check, so a cache written by any
    process between mutate and restore can be imported by a later clean run.

    Args:
        source_root: The source root whose caches are dropped.
    """
    for cache in sorted(source_root.rglob("__pycache__")):
        try:
            shutil.rmtree(cache)
        except OSError as exc:
            print(f"WARNING: could not clear {cache}: {exc}", file=sys.stderr)


def _score_mutation(name: str, test_file: str, source_root: Path, cwd: Path) -> bool:
    """Run one mutation's targeted tests and report whether it was killed.

    Args:
        name: The mutation's catalogue name.
        test_file: The test file that must turn red.
        source_root: Source root the subprocess imports from.
        cwd: Working directory for pytest.

    Returns:
        Whether pytest exited 1, the only exit code that is a kill.

    Raises:
        InvalidMeasurement: pytest could not run, timed out, or exited 2-5 — a
            usage, collection or internal error. The mutation was never
            measured, so it may not be folded into a score as a survivor.
    """
    try:
        returncode = run_targeted_test(test_file, source_root, cwd)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise InvalidMeasurement(
            f"mutation {name!r}: the run of {test_file} could not complete "
            f"({exc}), so the mutation was never measured.") from exc
    if returncode == 1:
        print(f"KILLED: {name}")
        return True
    if returncode == 0:
        print(f"SURVIVED: {name}")
        return False
    raise InvalidMeasurement(
        f"mutation {name!r}: pytest exited {returncode} on {test_file} - a "
        "usage, collection or internal error, not a test result. Only exit 1 "
        "is a kill, so this mutation was never measured.")


def run_mutations(merge_path: Path, source_root: Path, cwd: Path) -> list[tuple[str, bool]]:
    """Apply each mutation in turn, scoring it against its targeted tests.

    Args:
        merge_path: The merge engine file, mutated in place.
        source_root: Source root the subprocesses import from.
        cwd: Working directory for the test runs.

    Returns:
        One `(name, killed)` pair per mutation, in declaration order.

    Raises:
        InvalidMeasurement: A mutation could not be applied, or a restore
            could not be confirmed. The run stops there; no score is produced.
    """
    original = merge_path.read_bytes()
    results: list[tuple[str, bool]] = []
    for name, anchor, replacement, test_file in MUTATIONS:
        mutated = apply_mutation(name, original, anchor, replacement)
        try:
            merge_path.write_bytes(mutated)
        except OSError as exc:
            restore_source(merge_path, original)      # a failed write may truncate
            raise InvalidMeasurement(
                f"mutation {name!r} could not be applied to {merge_path}: {exc}\n"
                "  Nothing was measured, so this run has no mutation score.") from exc
        try:
            results.append((name, _score_mutation(name, test_file, source_root, cwd)))
        finally:
            restore_source(merge_path, original)
    return results


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the harness command line.

    Args:
        argv: Argument list, or None to read `sys.argv`.

    Returns:
        The parsed namespace (`root`, `verify_only`).
    """
    parser = argparse.ArgumentParser(
        description="Mutation-test the merge engine and prove what was measured.")
    parser.add_argument(
        "--root", type=Path, default=ROOT, metavar="DIR",
        help="Project root to measure: DIR/src is the source root and DIR the "
             "working directory for pytest. Defaults to this repository.")
    parser.add_argument(
        "--verify-only", action="store_true",
        help="Verify the import root and print provenance, then stop without "
             "mutating anything.")
    return parser.parse_args(argv)


def _invalid_measurement(exc: InvalidMeasurement) -> int:
    """Report a run that produced no valid measurement, and exit 2.

    Every path to `EXIT_INVALID` ends here, and this is the only place in the
    module that returns it, so "exit 2 prints no mutation score" is held by the
    shape of the code rather than by remembering it at each raise site. It
    writes to stderr only: stdout carries results, and there is no result.

    Args:
        exc: Why this run cannot be trusted to have measured anything.

    Returns:
        `EXIT_INVALID`.
    """
    print(f"INVALID MEASUREMENT: {exc}", file=sys.stderr)
    print("VERDICT: INVALID - this run produced no mutation score, not even a zero",
          file=sys.stderr)
    return EXIT_INVALID


def report_score(results: list[tuple[str, bool]]) -> int:
    """Print the verdict for a valid measurement and return its exit code.

    Args:
        results: One `(name, killed)` pair per mutation actually measured.

    Returns:
        `EXIT_OK` when every mutation was killed, else `EXIT_SURVIVORS`.
    """
    killed = sum(1 for _, was_killed in results if was_killed)
    total = len(results)
    verdict = "PASS" if killed == total else "FAIL"
    print(f"VERDICT: {verdict} - {killed}/{total} mutations killed")
    return EXIT_OK if killed == total else EXIT_SURVIVORS


def main(argv: list[str] | None = None) -> int:
    """Check the instrument, then score every mutation. See module docstring."""
    args = parse_args(argv)
    try:
        root = args.root.resolve()
        source_root = root / "src"
        merge_path = source_root / "conductor" / "merge.py"
        if not merge_path.is_file():
            raise InvalidMeasurement(f"no merge engine to mutate at {merge_path}")
        resolved = verify_import_root(source_root, root, merge_path)
        print_provenance(source_root, resolved)
        if args.verify_only:
            print("VERDICT: verification passed - import isolation confirmed, "
                  "no mutations were run")
            return EXIT_OK
        try:
            green = check_baseline(source_root, root, resolved)
            print(f"baseline: {green} targeted tests green on unmutated source")
            results = run_mutations(merge_path, source_root, root)
        finally:
            clear_pycache(source_root)
        return report_score(results)
    except InvalidMeasurement as exc:
        return _invalid_measurement(exc)
    except Exception as exc:                      # noqa: BLE001 — see below
        # The other half of the exit contract. Whatever else goes wrong on the
        # measuring path — a source that is not UTF-8, a workspace that cannot
        # be created, a read that fails — is an instrument failure, and letting
        # its traceback reach the interpreter would exit 1, the code reserved
        # for an honest survivor. Every mode of failure converges here so that
        # `1` cannot be produced by anything except a completed measurement.
        return _invalid_measurement(InvalidMeasurement(
            f"the instrument itself failed ({type(exc).__name__}: {exc}), so "
            "nothing here was measured."))


if __name__ == "__main__":
    raise SystemExit(main())
