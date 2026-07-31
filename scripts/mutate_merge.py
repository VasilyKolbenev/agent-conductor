"""Mutation-testing harness for the merge engine (dev-only, mirrors the KALI
discipline: a green test suite that can't catch a mutated rule is not proof
of anything).

For each mutation below: apply ONE source-text substitution in place to
`src/conductor/merge.py`, run the targeted test file, and assert it goes
RED (nonzero pytest exit). The original bytes are restored in a `finally`
regardless of outcome, so the working tree is always left clean.

Usage: .venv\\Scripts\\python scripts\\mutate_merge.py
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MERGE_PATH = ROOT / "src" / "conductor" / "merge.py"

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
]


def run_targeted_test(test_file: str) -> int:
    # timeout=180: a mutation must never be allowed to hang the harness.
    # PYTHONDONTWRITEBYTECODE: a byte-identical-length mutation (e.g. == -> !=)
    # can poison __pycache__ — Python's timestamp+size staleness check misses the
    # mutate->restore round-trip, and later clean runs import the MUTATED bytecode
    # (phantom failures on a clean git diff). Never write bytecode from here.
    result = subprocess.run(
        [sys.executable, "-m", "pytest", test_file, "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=180,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    return result.returncode


def apply_mutation(original: bytes, anchor: str, replacement: str) -> bytes:
    text = original.decode("utf-8")
    assert text.count(anchor) == 1, f"anchor not found exactly once: {anchor!r}"
    mutated = text.replace(anchor, replacement, 1)
    return mutated.encode("utf-8")


def main() -> int:
    original = MERGE_PATH.read_bytes()
    results = []
    for name, anchor, replacement, test_file in MUTATIONS:
        mutated = apply_mutation(original, anchor, replacement)
        try:
            MERGE_PATH.write_bytes(mutated)
            try:
                returncode = run_targeted_test(test_file)
            except subprocess.TimeoutExpired:
                print(f"TIMEOUT: {name} (not counted as killed)")
                results.append((name, False))
            else:
                # pytest exit codes: 1 = genuine test failure (honest kill).
                # 2-5 = usage/collection/internal error — the mutation broke
                # something other than the assertions we're probing for, so
                # it must NOT be counted as a kill.
                if returncode == 1:
                    print(f"KILLED: {name}")
                    results.append((name, True))
                elif returncode == 0:
                    print(f"SURVIVED: {name}")
                    results.append((name, False))
                else:
                    print(f"HARNESS_ERROR: {name} exited {returncode} "
                          "(collection/usage error, not a test failure)")
                    results.append((name, False))
        finally:
            MERGE_PATH.write_bytes(original)
            # Verify the restore immediately — a corrupted restore must be
            # caught here, before the next mutation runs against a dirty base.
            assert MERGE_PATH.read_bytes() == original, (
                f"restore verification failed after mutation: {name}")

    total = len(results)
    killed_count = sum(1 for _, killed in results if killed)
    print(f"{killed_count}/{total} mutations killed")

    restored = MERGE_PATH.read_bytes() == original
    if not restored:
        print("ERROR: merge.py was not restored to its original bytes", file=sys.stderr)
        return 1
    return 0 if killed_count == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
