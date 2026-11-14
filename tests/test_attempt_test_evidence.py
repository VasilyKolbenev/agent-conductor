"""A test report belongs to one action and verified bytes; source names are not test outcomes."""
from types import SimpleNamespace

import pytest

from conductor.command.accept_manifest import FileImage, SnapshotRefused, build_snapshot
from conductor.command.attempt_test_evidence import import_test_evidence, read_test_evidence

CODE = b"def test_only_success():\n    assert count([1, 0]) == 1\n"
BASE = "a" * 40


def example(root):
    (root / "conductor").mkdir(exist_ok=True)
    req = SimpleNamespace(action_id="action-one", attempt_id="attempt-first", run_id="case")
    seed = SimpleNamespace(base_commit=BASE)
    snapshot = build_snapshot({}, {"tests/test_count.py": FileImage(CODE)}, object_format="sha1")
    files = {r.path: r.sha256.removeprefix("sha256:") for r in snapshot.rows}
    report = dict(run="case", action="verification/action-one", source_commit=BASE,
                  manifest=snapshot.digest, files=files, tests=[1, 0, 0, 0])
    return req, seed, snapshot, report


def read(root, req, seed, snap):
    return read_test_evidence(root, req, snap.digest, seed, snap)


def test_source_assertion_does_not_expose_withheld_values(tmp_path):
    req, seed, _, _ = example(tmp_path)
    data = b"def test_hidden():\n    assert password == 'example'\npassword='example'\n"
    snap = build_snapshot({}, {"tests/test_private.py": FileImage(data)}, object_format="sha1")
    view = read(tmp_path, req, seed, snap)
    assert view["status"] == "not_recorded" and view["cases"] == []


def test_external_summary_and_source_have_independent_meanings(tmp_path):
    req, seed, snap, report = example(tmp_path)
    before = read(tmp_path, req, seed, snap)
    assert before["status"] == "not_recorded"
    assert before["summary"] is None
    assert before["cases"] == [dict(name="test_only_success", path="tests/test_count.py",
                                    line=2, assertion="assert count([1, 0]) == 1")]
    assert not (tmp_path / "conductor" / "accept").exists()
    import_test_evidence(tmp_path, req, snap.digest, seed, snap, report)
    assert read(tmp_path, req, seed, snap) == {
        "status": "recorded", "source": "external", "cases": before["cases"],
        "summary": {"total": 1, "errors": 0, "failures": 0, "skipped": 0}}
    import_test_evidence(tmp_path, req, snap.digest, seed, snap, report)  # same receipt
    with pytest.raises(SnapshotRefused):
        changed = dict(report, tests=[4, 0, 0, 0])
        import_test_evidence(tmp_path, req, snap.digest, seed, snap, changed)
    assert read(tmp_path, req, seed, snap)["summary"]["total"] == 1


@pytest.mark.parametrize("change", [
    {"run": "other"}, {"action": "verification/earlier"}, {"manifest": "sha256:" + "0" * 64},
    {"source_commit": "b" * 40}, {"files": {}}, {"tests": [True, 0, 0, 0]},
])
def test_mismatched_or_malformed_report_cannot_be_imported(tmp_path, change):
    req, seed, snap, report = example(tmp_path)
    with pytest.raises(SnapshotRefused):
        import_test_evidence(tmp_path, req, snap.digest, seed, snap, {**report, **change})
    assert read(tmp_path, req, seed, snap)["status"] == "not_recorded"


def test_swapped_attempt_or_damaged_record_is_distinct_from_no_tests(tmp_path):
    req, seed, snap, report = example(tmp_path)
    import_test_evidence(tmp_path, req, snap.digest, seed, snap, report)
    req.attempt_id = "another"
    assert read(tmp_path, req, seed, snap)["status"] == "unavailable"
    req.attempt_id = "attempt-first"
    stored, = (tmp_path / "conductor" / "accept" / "case" / "tests").glob("*.json")
    stored.write_bytes(b"{")
    assert read(tmp_path, req, seed, snap)["status"] == "unavailable"
