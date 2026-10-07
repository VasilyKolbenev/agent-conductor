"""Accumulated bytes stay bound across review, retries and a later transfer read."""
from dataclasses import replace
import os

import pytest

from conductor.command import accept_snapshot as store
from conductor.command.accept_manifest import (
    FileImage, Snapshot, SnapshotRefused, blob_oid, build_snapshot, read_manifest, sha256,
)


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_accumulation_keeps_an_earlier_change_and_binds_deletion_mode_and_binary_bytes(fmt):
    base = {"a.py": FileImage(b"old"), "removed.txt": FileImage(b"gone"),
            "script": FileImage(b"same"), "unchanged": FileImage(b"fixed")}
    # b.bin is this attempt; a.py is a change left by a preceding rejected attempt.
    current = {"a.py": FileImage(b"earlier"), "b.bin": FileImage(b"\x00\xff\r\n"),
               "script": FileImage(b"same", "100755"), "unchanged": base["unchanged"]}
    snapshot = build_snapshot(base, current, object_format=fmt)
    assert [(r.path, r.state, r.mode) for r in snapshot.rows] == [
        ("a.py", "modified", "100644"), ("b.bin", "added", "100644"),
        ("removed.txt", "deleted", "100644"), ("script", "modified", "100755")]
    deleted = snapshot.rows[2]
    assert (deleted.length, deleted.sha256, deleted.git_oid) == (
        4, sha256(b"gone"), blob_oid(b"gone", fmt))
    assert deleted.sha256 not in snapshot.blobs
    assert snapshot.blobs[sha256(b"earlier")] == b"earlier"
    assert snapshot.blobs[sha256(b"\x00\xff\r\n")] == b"\x00\xff\r\n"
    without_mode = {**current, "script": FileImage(b"same")}
    assert build_snapshot(base, without_mode, object_format=fmt).digest != snapshot.digest
    assert build_snapshot(dict(reversed(list(base.items()))), current,
                          object_format=fmt).digest == snapshot.digest


def test_seed_skip_is_not_a_deletion_and_cannot_be_reintroduced_below_a_skipped_directory():
    base = {"omitted/a": FileImage(b"base"), "keep": FileImage(b"base")}
    assert build_snapshot(base, {"keep": base["keep"]}, object_format="sha1",
                          seed_skipped=frozenset({"omitted"})).rows == ()
    with pytest.raises(SnapshotRefused, match="reserved_path"):
        build_snapshot(base, {"OMITTED/new": FileImage(b"bad")}, object_format="sha1",
                       seed_skipped=frozenset({"omitted"}))


@pytest.mark.parametrize("path", ["../escape", "a/.git/config", "work/owner", "a\\b", 'a"b'])
def test_an_untransferable_path_never_becomes_a_snapshot(path):
    with pytest.raises(SnapshotRefused):
        build_snapshot({}, {path: FileImage(b"bad")}, object_format="sha1")


def test_store_reuses_without_writes_and_later_reads_only_captured_bytes(tmp_path, monkeypatch):
    snapshot = build_snapshot({}, {"a.py": FileImage(b"checked")}, object_format="sha1")
    digest = store.write_snapshot(tmp_path, "run-a", snapshot, object_format="sha1")
    def no_write(*_args):
        pytest.fail("reusing the same snapshot must not publish anything")
    monkeypatch.setattr(store, "_exclusive_bytes", no_write)
    assert store.write_snapshot(tmp_path, "run-a", snapshot, object_format="sha1") == digest
    # A subsequent live result cannot replace the material the independent check saw.
    (tmp_path / "a.py").write_bytes(b"changed after check")
    loaded = store.read_snapshot(tmp_path, "run-a", digest, object_format="sha1")
    assert loaded.payload == snapshot.payload and dict(loaded.blobs) == dict(snapshot.blobs)
    with pytest.raises(SnapshotRefused, match="snapshot_damaged"):
        store.read_snapshot(tmp_path, "run-b", digest, object_format="sha1")


def test_damage_is_not_repaired_and_manifest_is_published_after_all_blobs(tmp_path, monkeypatch):
    snapshot = build_snapshot({}, {"a.py": FileImage(b"checked")}, object_format="sha1")
    real = store._exclusive_bytes
    def interrupted(path, payload):
        if path.suffix == ".json":
            raise OSError("disk full before manifest publication")
        real(path, payload)
    monkeypatch.setattr(store, "_exclusive_bytes", interrupted)
    with pytest.raises(SnapshotRefused, match="snapshot_damaged"):
        store.write_snapshot(tmp_path, "run-a", snapshot, object_format="sha1")
    with pytest.raises(SnapshotRefused):
        store.read_snapshot(tmp_path, "run-a", snapshot.digest, object_format="sha1")
    monkeypatch.setattr(store, "_exclusive_bytes", real)
    store.write_snapshot(tmp_path, "run-a", snapshot, object_format="sha1")
    blob = next((tmp_path / "conductor/accept/run-a/blobs").iterdir())
    blob.write_bytes(b"corrupt")
    for operation in (
            lambda: store.read_snapshot(tmp_path, "run-a", snapshot.digest, object_format="sha1"),
            lambda: store.write_snapshot(tmp_path, "run-a", snapshot, object_format="sha1")):
        with pytest.raises(SnapshotRefused, match="snapshot_damaged"):
            operation()
    assert blob.read_bytes() == b"corrupt"


def test_an_aliased_blob_is_refused_even_with_matching_bytes(tmp_path):
    snapshot = build_snapshot({}, {"a": FileImage(b"same")}, object_format="sha1")
    store.write_snapshot(tmp_path, "run-a", snapshot, object_format="sha1")
    blob = next((tmp_path / "conductor/accept/run-a/blobs").iterdir())
    other = tmp_path / "foreign"
    os.link(blob, other)
    with pytest.raises(SnapshotRefused, match="snapshot_damaged"):
        store.read_snapshot(tmp_path, "run-a", snapshot.digest, object_format="sha1")
    assert other.read_bytes() == b"same"


def test_a_published_snapshot_with_a_missing_blob_is_not_silently_repaired(tmp_path):
    snapshot = build_snapshot({}, {"a": FileImage(b"same")}, object_format="sha1")
    store.write_snapshot(tmp_path, "run-a", snapshot, object_format="sha1")
    blob = next((tmp_path / "conductor/accept/run-a/blobs").iterdir())
    blob.unlink()
    with pytest.raises(SnapshotRefused, match="snapshot_damaged"):
        store.write_snapshot(tmp_path, "run-a", snapshot, object_format="sha1")
    assert not blob.exists()


def test_forged_metadata_and_noncanonical_manifest_refuse_before_publication(tmp_path):
    snapshot = build_snapshot({}, {"a": FileImage(b"same")}, object_format="sha1")
    forged = Snapshot((replace(snapshot.rows[0], git_oid="0" * 40),), snapshot.blobs)
    with pytest.raises(SnapshotRefused, match="snapshot_damaged"):
        store.write_snapshot(tmp_path, "run-a", forged, object_format="sha1")
    assert not (tmp_path / "conductor").exists()
    for payload in (snapshot.payload + b"\n", snapshot.payload.replace(b'"length":4',
                                                                       b'"length":true')):
        with pytest.raises(SnapshotRefused, match="snapshot_damaged"):
            read_manifest(payload, object_format="sha1")
