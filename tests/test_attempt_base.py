"""The before side is proved by the frozen Git tree, never by today's working file."""
from dataclasses import replace
from hashlib import new as hash_object

import pytest

from conductor.command.accept_manifest import FileImage, SnapshotRefused, build_snapshot
from conductor.command.attempt_base import import_attempt_base, read_attempt_base
from conductor.command.project_git import GitAnswer
from conductor.command.seed_record import SeedRecord, Skip
from tests.git_repo_helpers import commit, git as invoke_git, needs_git, real_reader, repository


def object_id(data, kind, fmt):
    raw = kind.encode() + b" " + str(len(data)).encode() + b"\0" + data
    return hash_object(fmt, raw).hexdigest()


def tree(*rows):
    return b"".join(mode + b" " + name + b"\0" + bytes.fromhex(oid) for mode, name, oid in rows)


def setup_tree(tmp_path, fmt="sha1"):
    root = tmp_path / "project"
    (root / "conductor").mkdir(parents=True)
    inputs = {k: FileImage(v) for k, v in {"d/file": b"base", "gone": b"removed"}.items()}
    snapshot = build_snapshot(inputs, {"d/file": FileImage(b"after"), "new": FileImage(b"added")},
                              object_format=fmt)
    objects = {}

    def keep(kind, raw):
        oid = object_id(raw, kind, fmt)
        objects[kind, oid] = raw
        return oid

    file = keep("blob", b"base")
    gone = keep("blob", b"removed")
    sub = keep("tree", tree((b"100644", b"file", file)))
    top = keep("tree", tree((b"40000", b"d", sub), (b"100644", b"gone", gone)))
    seed = SeedRecord("task", "task", "work-001", "git", "a" * len(top), top, fmt, None,
                      2, 11, False, "staging", (), (), (), "2026-11-09T08:00:00Z")

    def git(argv, separate_stderr, *, output_limit):
        assert separate_stderr and 0 < output_limit <= 1024 * 1024 + 1
        assert argv[:-3] == ["--no-optional-locks", "-C", str(root), "--git-dir=.git", "-c",
                             "core.useReplaceRefs=false", "--no-replace-objects"]
        op, kind, oid = argv[-3:]
        assert op == "cat-file"
        return GitAnswer(0, objects[kind, oid])

    return root, seed, snapshot.rows, git, objects


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_before_bytes_and_absence_are_proved_from_the_frozen_tree(tmp_path, fmt):
    root, seed, rows, git, _ = setup_tree(tmp_path, fmt)
    observed = read_attempt_base(root, "run", seed, rows, git=git)
    assert observed == {"d/file": b"base", "gone": b"removed"}
    assert not (root / "conductor" / "accept" / "run" / "base").exists()


def test_view_import_reads_another_repository_pins_and_keeps_proved_absence(tmp_path):
    root, seed, rows, git, objects = setup_tree(tmp_path)
    copy = tmp_path / "view"
    (copy / "conductor").mkdir(parents=True)
    with pytest.raises(SnapshotRefused, match="base_unavailable"):
        read_attempt_base(copy, "run", seed, rows)
    import_attempt_base(copy, "run", seed, rows, git, source_root=root)
    import_attempt_base(copy, "run", seed, rows, git, source_root=root)
    objects.clear()
    (copy / "gone").write_bytes(b"not historical bytes")
    (copy / "new").write_bytes(b"present today")
    assert read_attempt_base(copy, "run", seed, rows) == {"d/file": b"base", "gone": b"removed"}
    with pytest.raises(SnapshotRefused, match="base_unavailable"):
        read_attempt_base(copy, "other-run", seed, rows)


@pytest.mark.parametrize("kind", ["root_tree", "nested_tree", "blob"])
def test_tampered_archive_objects_never_become_before_images(tmp_path, kind):
    root, seed, rows, git, objects = setup_tree(tmp_path)
    import_attempt_base(root, "run", seed, rows, git)
    leaf = object_id(b"base", "blob", "sha1")
    child = object_id(tree((b"100644", b"file", leaf)), "tree", "sha1")
    oid = {"root_tree": seed.base_tree, "nested_tree": child, "blob": leaf}[kind]
    target = root / "conductor" / "accept" / "run" / "base" / oid
    assert target.read_bytes() in objects.values()
    target.write_bytes(b"forged")
    with pytest.raises(SnapshotRefused, match="snapshot_damaged"):
        read_attempt_base(root, "run", seed, rows)
    with pytest.raises(SnapshotRefused, match="snapshot_damaged"):
        import_attempt_base(root, "run", seed, rows, git)
    assert target.read_bytes() == b"forged"


def test_wrong_blob_from_git_is_refused_before_any_write(tmp_path):
    root, seed, rows, git, objects = setup_tree(tmp_path)
    key = ("blob", object_id(b"base", "blob", "sha1"))
    objects[key] = b"forged"
    with pytest.raises(SnapshotRefused, match="snapshot_damaged"):
        import_attempt_base(root, "run", seed, rows, git)
    assert not (root / "conductor" / "accept").exists()


def test_a_tree_cannot_be_supplied_under_the_hash_of_a_blob_with_the_same_bytes(tmp_path):
    root, seed, rows, _git, objects = setup_tree(tmp_path)
    raw_tree = objects["tree", seed.base_tree]
    wrong_type = object_id(raw_tree, "blob", "sha1")
    seed = replace(seed, base_tree=wrong_type)
    with pytest.raises(SnapshotRefused, match="snapshot_damaged"):
        read_attempt_base(root, "run", seed, rows, git=lambda *a, **k: GitAnswer(0, raw_tree))


def test_ambiguous_tree_entries_cannot_hide_a_regular_file(tmp_path):
    root, seed, rows, _git, objects = setup_tree(tmp_path)
    raw = objects["tree", seed.base_tree] * 2
    seed = replace(seed, base_tree=object_id(raw, "tree", "sha1"))
    with pytest.raises(SnapshotRefused, match="snapshot_damaged"):
        read_attempt_base(root, "run", seed, rows, git=lambda *a, **k: GitAnswer(0, raw))


@pytest.mark.parametrize("change", [
    {"path": "d/file", "state": "added"}, {"path": "not-here", "state": "modified"},
    {"path": "gone", "state": "deleted", "mode": "100755"}, {"path": "../escape"},
    {"path": "CON"}, {"path": "d"}, {"path": ".git/config"}, {"path": "AGENT.md"},
])
def test_row_and_tree_have_to_agree_before_transfer(tmp_path, change):
    root, seed, rows, git, _ = setup_tree(tmp_path)
    with pytest.raises(SnapshotRefused):
        read_attempt_base(root, "run", seed, [replace(rows[0], **change)], git=git)


def test_a_skipped_directory_cannot_reappear_under_another_spelling(tmp_path):
    root, seed, rows, git, _ = setup_tree(tmp_path)
    seed = replace(seed, skipped=(Skip("D", "budget"),))
    with pytest.raises(SnapshotRefused):
        read_attempt_base(root, "run", seed, rows, git=git)


def test_empty_seed_only_proves_an_addition_without_git(tmp_path):
    root, seed, rows, _, _ = setup_tree(tmp_path)
    empty = replace(seed, source="empty", base_commit=None, base_tree=None, object_format=None)
    assert read_attempt_base(root, "run", empty, [rows[-1]]) == {}
    with pytest.raises(SnapshotRefused, match="snapshot_damaged"):
        read_attempt_base(root, "run", empty, [rows[0]])


def test_bounded_git_and_known_sensitive_source_do_not_publish(tmp_path):
    root, seed, rows, git, _ = setup_tree(tmp_path)
    with pytest.raises(SnapshotRefused, match="result_too_large"):
        import_attempt_base(root, "run", seed, rows, lambda *a, **k: GitAnswer(0, b"", True))
    with pytest.raises(SnapshotRefused, match="base_unavailable"):
        import_attempt_base(root, "run", seed, rows, git, sensitive=(b"base",))
    assert not (root / "conductor" / "accept").exists()


@needs_git
def test_real_git_reads_the_pinned_tree_after_head_moves(tmp_path):
    source = repository(tmp_path)
    before = commit(source, {"folder/code.py": b"old\n"}, "recorded base")
    top = invoke_git("rev-parse", before + "^{tree}", cwd=source).stdout.decode().strip()
    commit(source, {"folder/code.py": b"later HEAD\n", "new": b"unrelated"}, "changed HEAD")
    root, seed, _, _, _ = setup_tree(tmp_path)
    seed = replace(seed, base_commit=before, base_tree=top)
    rows = build_snapshot({"folder/code.py": FileImage(b"old\n")},
                          {"folder/code.py": FileImage(b"new\n"), "new": FileImage(b"added")},
                          object_format="sha1").rows
    reader = real_reader(tmp_path)
    assert read_attempt_base(source, "run", seed, rows, git=reader) == {"folder/code.py": b"old\n"}
    import_attempt_base(root, "run", seed, rows, reader, source_root=source)
    assert read_attempt_base(root, "run", seed, rows) == {"folder/code.py": b"old\n"}
