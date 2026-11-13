"""The selected base tree and sealed tests support a static comparison without running tests."""
from dataclasses import replace

import pytest

from conductor.command.accept_manifest import FileImage, build_snapshot
from conductor.command.accept_snapshot import write_snapshot
from conductor.command.attempt_detail import read_attempt
from conductor.command.project_git import GitAnswer
from conductor.command.run_store import StoredRecord
from conductor.command.seed_record import SeedRecord, write_seed
from tests.test_attempt_base import object_id, tree
from tests.test_attempt_projection import RUN, TASK, attempt, journal
from tests.test_seed_record import a_git_seed


OLD = b"def tally(rows):\n    return len(rows)\n"
NEW = b"def tally(rows):\n    return sum(x is not None for x in rows)\n"
EXPORT = b"from .counts import tally\n"
CHECK = b"""import unittest
from sample import tally

class Checks(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(tally([]), 0)

    def test_mixed(self):
        rows = [[1, 2], None, {"v": 3}]
        self.assertEqual(tally(rows), 2)
"""


def projection(root, old=OLD, new=NEW, check=CHECK, export=EXPORT, patched_export=None):
    objects = {}

    def keep(kind, raw):
        oid = object_id(raw, kind, "sha1")
        objects[kind, oid] = raw
        return oid

    def git(argv, _separate_stderr, *, output_limit):
        raw = objects[tuple(argv[-2:])]
        assert len(raw) < output_limit
        return GitAnswer(0, raw)

    names = ("sample/counts.py", "sample/__init__.py", "test_counter.py")
    package = tree((b"100644", b"__init__.py", keep("blob", export)),
                   (b"100644", b"counts.py", keep("blob", old)))
    base = keep("tree", tree((b"40000", b"sample", keep("tree", package))))
    seed = a_git_seed(task_id=TASK, work_scope=TASK, base_tree=base)
    write_seed(root, SeedRecord.from_dict(seed))
    initial = {names[0]: FileImage(old), names[1]: FileImage(export)}
    final = {**initial, names[0]: FileImage(new), names[2]: FileImage(check)}
    if patched_export is not None:
        final[names[1]] = FileImage(patched_export)
    snap = build_snapshot(initial, final, object_format="sha1")
    digest = write_snapshot(root, RUN, snap, object_format="sha1")
    req, proof, result = attempt(root, "before", {})
    value = replace(proof.value, digest=digest,
                    extra={"accept_manifest_digest": digest, "work_tree_digest": digest})
    records = journal(req, StoredRecord(proof.kind, value), result)
    return read_attempt(root, records, "do", "act-before", git=git)["tests"]["cases"]


def test_exact_old_return_and_reexport_for_each_sealed_assertion(tmp_path):
    cases = projection(tmp_path)
    assert [(c["name"], c.get("old_length")) for c in cases] == [
        ("test_empty", {"expression": "len(rows)", "function": "tally", "path": "sample/counts.py",
                        "line": 2, "actual": 0, "expected": 0}),
        ("test_mixed", {"expression": "len(rows)", "function": "tally", "path": "sample/counts.py",
                        "line": 2, "actual": 3, "expected": 2})]


@pytest.mark.parametrize("change", [
    {"old": b"len = lambda rows: 0\n" + OLD},
    {"old": OLD.replace(b"return len(rows)", b"rows.clear()\n    return len(rows)")},
    {"new": b"# changed comments only\n" + OLD},
    {"new": OLD.replace(b"rows", b"items")},
    {"export": b"from .other import tally\n"},
    {"patched_export": b"from .other import tally\n"},
    {"check": CHECK.replace(b"from sample import tally", b"from other import tally")},
    {"check": CHECK.replace(b"class Checks", b"tally = lambda rows: 0\nclass Checks")},
])
def test_missing_or_changed_target_never_confers_an_old_result(tmp_path, change):
    cases = projection(tmp_path, **change)
    assert len(cases) == 2
    assert all("old_length" not in c for c in cases)


@pytest.mark.parametrize("assignment", [
    b"rows = list(range(3))", b"rows = [*entries]", b"rows = [1]\n        rows.extend([2])",
    b"rows = [unknown()]", b"rows = [[1] for _ in range(3)]", b"rows = [{[]: None}]",
    b"rows = " + b"[" * 55 + b"0" + b"]" * 55,
])
def test_unsupported_input_keeps_the_known_sibling_and_the_original_case(tmp_path, assignment):
    src = CHECK.replace(b'rows = [[1, 2], None, {"v": 3}]', assignment)
    empty, unknown = projection(tmp_path, check=src)
    assert empty["old_length"]["actual"] == 0
    assert unknown["name"] == "test_mixed" and "old_length" not in unknown
