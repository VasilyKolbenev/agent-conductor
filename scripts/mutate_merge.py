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
]


def run_targeted_test(test_file: str) -> int:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", test_file, "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
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
            returncode = run_targeted_test(test_file)
            killed = returncode != 0
            results.append((name, killed))
            print(f"{'KILLED' if killed else 'SURVIVED'}: {name}")
        finally:
            MERGE_PATH.write_bytes(original)

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
