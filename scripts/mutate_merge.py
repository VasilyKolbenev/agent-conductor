"""Mutation-testing harness for the merge engine (dev-only, mirrors the KALI
discipline: a green test suite that can't catch a mutated rule is not proof
of anything).

For each mutation below: apply ONE source-text substitution in place to
`src/conductor/merge.py`, run the targeted test file, and assert it goes
RED (nonzero pytest exit). The original bytes are restored from an in-memory
copy and the restore is PROVED by content hash, so the working tree is always
left clean — or the run stops saying, unmistakably, that it is not.

Before the first mutation the harness confirms where `conductor.merge` is
actually imported from. File isolation is not verification isolation: an
editable install (a `.pth` in site-packages) or an installed copy can shadow
an exported tree, so the harness mutates one file while pytest imports
another and prints a plausible score that means nothing. A wrong import root
is an infrastructure error (exit 3), never a mutation score.

Exit codes: 0 every mutation killed, 1 a mutation survived, 3 the instrument
itself could not be trusted and nothing was measured.

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
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

EXIT_OK = 0
EXIT_SURVIVORS = 1
EXIT_INFRASTRUCTURE = 3          # never overlaps a score: nothing was measured

RESTORE_ATTEMPTS = 3
RESTORE_DELAY_S = 0.2

# `pytest` is imported by the probe on purpose: PYTHONNOUSERSITE hides a
# user-site pytest, and `python -m pytest` without pytest exits 1 — which this
# harness would otherwise read as an honest kill.
IMPORT_PROBE = (
    "import pathlib, sys, conductor.merge, pytest; "
    "sys.stdout.write(str(pathlib.Path(conductor.merge.__file__).resolve()))"
)


class InfrastructureError(RuntimeError):
    """The instrument is untrustworthy, so no number it produced is a result."""


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
    ambiguity this harness exists to remove. PYTHONNOUSERSITE keeps a user-site
    install from shadowing the source root. PYTHONDONTWRITEBYTECODE is a
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


def verify_import_root(source_root: Path, cwd: Path) -> Path:
    """Confirm `conductor.merge` imports from `source_root` and nowhere else.

    Runs in the same subprocess environment the mutations will run in, before
    the first mutation, because file isolation is not verification isolation.

    Args:
        source_root: The `src` directory that must own the import.
        cwd: Working directory for the probe, as for the test runs.

    Returns:
        The resolved path of `conductor.merge.__file__`.

    Raises:
        InfrastructureError: The probe could not run, the import failed, or it
            resolved outside `source_root`.
    """
    try:
        probe = subprocess.run(
            [sys.executable, "-c", IMPORT_PROBE], cwd=cwd, capture_output=True,
            text=True, timeout=180, env=subprocess_env(source_root))
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise InfrastructureError(f"the import probe could not run: {exc}") from exc
    if probe.returncode != 0:
        raise InfrastructureError(
            "import isolation not confirmed - the probe failed to import\n"
            f"  conductor.merge and pytest with PYTHONPATH={source_root}:\n"
            f"{probe.stderr.strip()}")
    resolved = Path(probe.stdout.strip())
    if not _is_inside(resolved, source_root):
        raise InfrastructureError(_shadow_report(resolved, source_root))
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


def run_targeted_test(test_file: str, source_root: Path, cwd: Path) -> int:
    """Run one targeted test file against the currently mutated source.

    Args:
        test_file: Path of the test file, relative to `cwd`.
        source_root: Source root the subprocess imports from.
        cwd: Working directory for pytest.

    Returns:
        The pytest exit code.
    """
    # timeout=180: a mutation must never be allowed to hang the harness.
    result = subprocess.run(
        [sys.executable, "-m", "pytest", test_file, "-q"],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=180,
        env=subprocess_env(source_root),
    )
    return result.returncode


def apply_mutation(original: bytes, anchor: str, replacement: str) -> bytes:
    """Return `original` with `anchor` replaced once by `replacement`."""
    text = original.decode("utf-8")
    assert text.count(anchor) == 1, f"anchor not found exactly once: {anchor!r}"
    mutated = text.replace(anchor, replacement, 1)
    return mutated.encode("utf-8")


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
        InfrastructureError: The content could not be confirmed within
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
    raise InfrastructureError(
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
    """Run one mutation's targeted tests and report whether it was killed."""
    try:
        returncode = run_targeted_test(test_file, source_root, cwd)
    except subprocess.TimeoutExpired:
        print(f"TIMEOUT: {name} (not counted as killed)")
        return False
    # pytest exit codes: 1 = genuine test failure (honest kill). 2-5 =
    # usage/collection/internal error — the mutation broke something other than
    # the assertions we're probing for, so it must NOT be counted as a kill.
    if returncode == 1:
        print(f"KILLED: {name}")
        return True
    if returncode == 0:
        print(f"SURVIVED: {name}")
        return False
    print(f"HARNESS_ERROR: {name} exited {returncode} "
          "(collection/usage error, not a test failure)")
    return False


def run_mutations(merge_path: Path, source_root: Path, cwd: Path) -> list[tuple[str, bool]]:
    """Apply each mutation in turn, scoring it against its targeted tests.

    Args:
        merge_path: The merge engine file, mutated in place.
        source_root: Source root the subprocesses import from.
        cwd: Working directory for the test runs.

    Returns:
        One `(name, killed)` pair per mutation, in declaration order.

    Raises:
        InfrastructureError: A mutation could not be applied, or a restore
            could not be confirmed. The run stops there; no score is produced.
    """
    original = merge_path.read_bytes()
    results: list[tuple[str, bool]] = []
    for name, anchor, replacement, test_file in MUTATIONS:
        mutated = apply_mutation(original, anchor, replacement)
        try:
            merge_path.write_bytes(mutated)
        except OSError as exc:
            restore_source(merge_path, original)      # a failed write may truncate
            raise InfrastructureError(
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


def main(argv: list[str] | None = None) -> int:
    """Verify the import root, then score every mutation. See module docstring."""
    args = parse_args(argv)
    root = args.root.resolve()
    source_root = root / "src"
    merge_path = source_root / "conductor" / "merge.py"
    try:
        if not merge_path.is_file():
            raise InfrastructureError(f"no merge engine to mutate at {merge_path}")
        print_provenance(source_root, verify_import_root(source_root, root))
        if args.verify_only:
            print("VERDICT: import isolation confirmed - no mutation requested")
            return EXIT_OK
        try:
            results = run_mutations(merge_path, source_root, root)
        finally:
            clear_pycache(source_root)
    except InfrastructureError as exc:
        print(f"INFRASTRUCTURE ERROR: {exc}", file=sys.stderr)
        print("VERDICT: INFRASTRUCTURE ERROR - this run produced no mutation score",
              file=sys.stderr)
        return EXIT_INFRASTRUCTURE
    killed = sum(1 for _, was_killed in results if was_killed)
    total = len(results)
    verdict = "PASS" if killed == total else "FAIL"
    print(f"VERDICT: {verdict} - {killed}/{total} mutations killed")
    return EXIT_OK if killed == total else EXIT_SURVIVORS


if __name__ == "__main__":
    raise SystemExit(main())
