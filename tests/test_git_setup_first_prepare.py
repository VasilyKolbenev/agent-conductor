"""Phase A of the first commit: objects, one parentless commit and the marked bytes, no lock.

Every test takes the preview the route shows (`seal`) and hands exactly that to `prepare`, on a
scratch project outside every repository. What phase A may leave behind is objects and nothing
else: no ref, no index, no lock, no file of the product's own records. The three tests of gate G-old
(rows 4 and 7 of plan 4a.6) take the reader's Git as a parameter, so the isolated Git 2.31 builds,
marks and reads the bytes when `CONDUCT_OLD_GIT` names it; while it is unset their `old_git` ids are
skipped with the reason.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from conductor.command import git_setup_first_prepare as prepare_module
from conductor.command import git_setup_modes, git_setup_snapshot
from conductor.command.accept_manifest import SnapshotRefused, blob_oid, sha256
from conductor.command.git_setup_first_index import (
    INDEX_PIN, Binding, terms_hash, verify, verify_binding)
from conductor.command.git_setup_first_prepare import prepare
from conductor.command.git_setup_records import SetupRefused
from conductor.command.project_git import GitAnswer, GitReadFailed
from conductor.ownership import data_root
from tests.git_first_bench import project, seal
from tests.git_first_readers import READERS, reader_binary
from tests.git_first_scratch import NOTICE, notice_lines
from tests.git_repo_helpers import git, needs_git, snapshot

FORMATS = ["sha1", "sha256"]
FILES = {"a.txt": b"one\n", "d/b.txt": b"two\n", "d/e/c.txt": b"three\n"}
MESSAGE = "Первый коммит: 3 файла (Conduct)\n\nConduct-Setup: first-commit\n".encode("utf-8")
#: The settings of the owner's own repository that change the bytes Git writes for an index.
FAMILIES = {
    "split_index": [("core.splitIndex", "true")],
    "end_of_entries": [("index.recordEndOfIndexEntries", "true")],
    "threads_four": [("index.threads", "4")],
    "untracked_cache": [("core.untrackedCache", "true")],
    "version_four": [("index.version", "4")],
    "skip_hash": [("index.skipHash", "true")],
    "many_files": [("feature.manyFiles", "true")],
}
FAMILIES["all_together"] = [pair for pairs in list(FAMILIES.values()) for pair in pairs]
INDEX_COMMANDS = ("read-tree", "update-index", "write-tree", "diff-index")
for_every_reader = pytest.mark.parametrize("which", READERS)
for_every_format = pytest.mark.parametrize("fmt", FORMATS)
for_both_modes = pytest.mark.parametrize("mode", ["empty", "snapshot"])


def run(p, mode="snapshot", message=MESSAGE, **changes):
    """The preview, then the preparation of exactly what it showed: (shown, digest, made)."""
    shown = {**seal(p, mode), **changes}
    digest = shown["paths_digest"] if mode == "snapshot" else None
    return shown, digest, prepare(p.root, p.spy, shown, message, mode, digest)


def only_objects_changed(p, before):
    """Phase A published nothing: objects only, no ref, no index, no lock, no record."""
    after = snapshot(p.root / ".git")
    changed = {name for name in {*before, *after} if before.get(name) != after.get(name)}
    assert all(name.startswith("objects/") for name in changed), sorted(changed)
    assert "index" not in after and "index.lock" not in after and after["HEAD"] == before["HEAD"]
    gone = p.git("rev-parse", "--verify", "-q", "refs/heads/trunk", cwd=p.root, check=False)
    assert gone.returncode != 0
    records = (data_root(p.root) / "git" / "setup").glob("first_commit*")
    assert not list(records)                  # the init receipt is there; no first-commit record
    return changed


def modes_of(p, tree):
    """The path and mode of every entry of a tree, as `git ls-tree` shows them."""
    lines = p.git("ls-tree", "-r", tree, cwd=p.root).stdout.decode("utf-8").splitlines()
    return {line.split("\t")[1]: line.split()[0] for line in lines}


def owned_indexes(p):
    return sorted(path.name for path in (data_root(p.root) / "git").glob("index-first-*"))


TIMED_OUT = GitAnswer(None, b"", timed_out=True)


def answering(p, word, answer):
    """The product's reader, except that the one command that names `word` gets `answer`."""
    def reader(args, *positional, **keywords):
        if word in args:
            return answer
        return p.spy(args, *positional, **keywords)
    return reader


def refusal_of(action):
    """The closed word of the refusal `action` raises: a reason, or the code of a failed Git."""
    with pytest.raises((SetupRefused, GitReadFailed)) as caught:
        action()
    return getattr(caught.value, "reason", None) or caught.value.code


def the_bench_source():
    return (Path(__file__).parent / "git_first_bench.py").read_text(encoding="utf-8")


def test_the_bench_builds_its_reader_only_through_product_reader():
    source = the_bench_source()
    assert "product_reader(" in source
    for forbidden in ("ProcessRunner(", "process_git_read(", "ISOLATED"):
        assert forbidden not in source, forbidden


@needs_git
def test_prepare_writes_objects_and_a_parentless_commit_but_no_ref_index_or_lock(tmp_path):
    p = project(tmp_path, FILES)
    before = snapshot(p.root / ".git")
    shown, _digest, made = run(p)
    assert only_objects_changed(p, before)
    raw = p.git("cat-file", "commit", made.commit, cwd=p.root).stdout
    head, _, body = raw.partition(b"\n\n")
    lines = head.decode("utf-8").splitlines()
    author = shown["author"]
    assert [line for line in lines if line.startswith("tree ")] == [f"tree {made.tree}"]
    assert not any(line.startswith("parent ") for line in lines)
    assert any(line.startswith(f"author {author['name']} <{author['email']}> ") for line in lines)
    assert body == MESSAGE
    assert made.count == len(FILES) and made.nonce and made.install


@needs_git
def test_prepare_oids_equal_the_preview_oids_or_refuse_paths_changed(tmp_path):
    p = project(tmp_path, FILES)
    before = snapshot(p.root / ".git")
    shown = seal(p)
    (p.root / "a.txt").write_bytes(b"changed after the preview\n")
    with pytest.raises(SetupRefused) as caught:
        prepare(p.root, p.spy, shown, MESSAGE, "snapshot", shown["paths_digest"])
    assert caught.value.reason == "paths_changed"
    only_objects_changed(p, before)
    assert p.spy.argv("commit-tree") == [] and owned_indexes(p) == []


def cleaner(tmp_path, name, tail):
    """A clean filter written in Python; its command line for `filter.demo.clean`."""
    script = tmp_path / name
    script.write_text("import sys\nsys.stdout.buffer.write("
                      f"sys.stdin.buffer.read().replace(b'raw', b'clean'){tail})\n",
                      encoding="utf-8")
    return f'"{Path(sys.executable).as_posix()}" "{script.as_posix()}"'


@needs_git
def test_first_commit_preview_binds_the_clean_filtered_blob_ids(tmp_path):
    p = project(tmp_path)
    original, other = cleaner(tmp_path, "clean.py", ""), cleaner(tmp_path, "other.py", " + b'!'")
    p.git("config", "filter.demo.clean", original, cwd=p.root)
    (p.root / ".gitattributes").write_bytes(b"*.dat filter=demo\n")
    (p.root / "data.dat").write_bytes(b"raw payload\n")
    shown = seal(p)
    row = next(row for row in shown["files"] if row["path"] == "data.dat")
    assert row["git_oid"] == blob_oid(b"clean payload\n", shown["object_format"])
    p.git("config", "filter.demo.clean", other, cwd=p.root)
    before = snapshot(p.root / ".git")
    with pytest.raises(SetupRefused) as caught:
        prepare(p.root, p.spy, shown, MESSAGE, "snapshot", shown["paths_digest"])
    assert caught.value.reason == "paths_changed"
    only_objects_changed(p, before)
    p.git("config", "filter.demo.clean", original, cwd=p.root)     # the shown bytes again
    made = prepare(p.root, p.spy, shown, MESSAGE, "snapshot", shown["paths_digest"])
    stored = p.git("cat-file", "blob", f"{made.tree}:data.dat", cwd=p.root).stdout
    assert stored == b"clean payload\n"


@needs_git
def test_prepare_builds_the_tree_from_the_shown_git_mode_and_looks_at_no_file_mode(
        tmp_path, monkeypatch):
    p = project(tmp_path, {"a.sh": b"echo a\n", "b.txt": b"b\n"})
    p.git("config", "core.filemode", "false", cwd=p.root)
    shown = seal(p)
    for row, mode in zip(shown["files"], ("100755", "100644"), strict=True):
        row["git_mode"] = mode            # what the person was shown, not what the files say

    def decided(*_args, **_keywords):
        raise AssertionError("the preparation made a mode decision of its own")

    monkeypatch.setattr(git_setup_modes, "effective_git_mode", decided)
    monkeypatch.setattr(git_setup_modes, "core_filemode", decided)
    monkeypatch.setattr(git_setup_snapshot, "effective_git_mode", decided)
    monkeypatch.setattr(git_setup_snapshot, "core_filemode", decided)
    made = prepare(p.root, p.spy, shown, MESSAGE, "snapshot", shown["paths_digest"])
    assert modes_of(p, made.tree) == {"a.sh": "100755", "b.txt": "100644"}
    source = Path(prepare_module.__file__).read_text(encoding="utf-8")
    for word in ("lstat", "st_mode", "S_IX", "core_filemode", "effective_git_mode", "filemode"):
        assert word not in source, word


@needs_git
@pytest.mark.skipif(os.name == "nt", reason="needs a real execute bit")
def test_prepare_records_the_executable_bit_as_git_add_would(tmp_path):
    files = {"run.sh": b"#!/bin/sh\n", "plain.txt": b"x\n"}

    def made_in(name, filemode=None):
        p = project(tmp_path, files, name=name)
        (p.root / "run.sh").chmod(0o755)
        (p.root / "plain.txt").chmod(0o644)
        if filemode is not None:
            p.git("config", "core.filemode", filemode, cwd=p.root)
        return p, *run(p)

    p, _shown, _digest, made = made_in("true")
    assert modes_of(p, made.tree) == {"run.sh": "100755", "plain.txt": "100644"}
    p, _shown, _digest, made = made_in("false", "false")
    assert modes_of(p, made.tree) == {"run.sh": "100644", "plain.txt": "100644"}
    p = project(tmp_path, files, name="flipped")
    shown = seal(p)
    (p.root / "run.sh").chmod(0o755)                # a mode-only change after the preview
    with pytest.raises(SetupRefused) as caught:
        prepare(p.root, p.spy, shown, MESSAGE, "snapshot", shown["paths_digest"])
    assert caught.value.reason == "paths_changed" and p.spy.argv("--refresh")


@needs_git
@for_every_reader
@for_every_format
@pytest.mark.parametrize("family", FAMILIES)
def test_prepare_builds_a_plain_index_even_when_the_owner_configures_the_optional_extensions(
        tmp_path, which, fmt, family):
    p = project(tmp_path, FILES, which=which, fmt=fmt)
    for key, value in FAMILIES[family]:
        p.git("config", key, value, cwd=p.root)
    _shown, _digest, made = run(p)
    shape = verify(made.install, fmt, entries=len(FILES))
    assert shape.extensions == ("TREE", "CNDT") and shape.tree_root == made.tree
    assert made.install[4:8] == b"\0\0\0\2"
    assert not list((p.root / ".git").glob("sharedindex.*"))


@needs_git
@for_every_reader
@for_every_format
@pytest.mark.parametrize("family", ["end_of_entries", "all_together"])
def test_without_the_pin_the_same_configs_reach_the_bytes_and_the_format_check_refuses_them(
        tmp_path, monkeypatch, which, fmt, family):
    """Calibration of the test above: it would be red were the pin gone from the calls."""
    p = project(tmp_path, FILES, which=which, fmt=fmt)
    for key, value in FAMILIES[family]:
        p.git("config", key, value, cwd=p.root)
    shown = seal(p)
    monkeypatch.setattr(prepare_module, "INDEX_PIN", ())
    with pytest.raises(GitReadFailed) as caught:
        prepare(p.root, p.spy, shown, MESSAGE, "snapshot", shown["paths_digest"])
    assert caught.value.code == "git_failed"
    assert p.spy.argv("commit-tree") == [] and owned_indexes(p) == []


@needs_git
def test_every_index_command_of_the_preparation_carries_the_whole_pin(tmp_path):
    p = project(tmp_path, FILES)
    shown = seal(p)
    start = len(p.spy.calls)
    prepare(p.root, p.spy, shown, MESSAGE, "snapshot", shown["paths_digest"])
    seen = {}
    for args, _keywords in p.spy.calls[start:]:
        for word in INDEX_COMMANDS:
            if word in args:
                seen.setdefault(word, []).append(args)
    assert set(seen) == set(INDEX_COMMANDS)
    for word, calls in seen.items():
        for args in calls:
            assert any(args[i:i + len(INDEX_PIN)] == INDEX_PIN for i in range(len(args))), word


def terms_of(shown, mode, digest, made, fmt):
    return terms_hash(nonce=made.nonce, mode=mode, digest_version=shown["digest_version"],
                      paths_digest=digest, target_ref=shown["target_ref"], object_format=fmt,
                      expected_tree=made.tree, file_count=made.count)


@needs_git
@for_every_reader
@for_every_format
@for_both_modes
def test_prepare_marks_the_install_bytes_in_both_modes_and_formats(tmp_path, which, fmt, mode):
    p = project(tmp_path, FILES if mode == "snapshot" else None, which=which, fmt=fmt)
    first, second = run(p, mode), run(p, mode)
    claims = []
    for shown, digest, made in (first, second):
        terms = terms_of(shown, mode, digest, made, fmt)
        shape = verify(made.install, fmt, entries=made.count)
        assert shape.marker == (made.nonce, terms) and shape.tree_root == made.tree
        claims.append(Binding(made.nonce, sha256(made.install), terms, made.tree, fmt, made.count))
        assert verify_binding(made.install, claims[-1])
        assert len(made.install) not in (65, 89)         # not the bytes of an empty index
    one, two = first[2], second[2]
    assert one.nonce != two.nonce and sha256(one.install) != sha256(two.install)
    assert one.tree == two.tree
    assert not verify_binding(two.install, claims[0])    # one operation's bytes are not the other's
    assert not verify_binding(one.install, claims[1])


@needs_git
@for_every_reader
@for_every_format
def test_prepare_checks_that_the_pinned_git_reads_the_marked_bytes_before_anything_is_published(
        tmp_path, which, fmt):
    p = project(tmp_path, FILES, which=which, fmt=fmt)
    shown = seal(p)
    before = snapshot(p.root / ".git")

    unreadable = answering(p, "diff-index", GitAnswer(128, b""))
    with pytest.raises(GitReadFailed) as caught:
        prepare(p.root, unreadable, shown, MESSAGE, "snapshot", shown["paths_digest"])
    assert caught.value.code == "git_failed"
    only_objects_changed(p, before)
    assert p.spy.argv("commit-tree") == [] and owned_indexes(p) == []
    made = prepare(p.root, p.spy, shown, MESSAGE, "snapshot", shown["paths_digest"])
    assert made.commit and made.install


@needs_git
def test_prepare_refuses_when_a_file_changes_between_the_object_write_and_the_refresh(tmp_path):
    p = project(tmp_path, {"new.txt": b"before"})
    shown = seal(p)
    before = snapshot(p.root / ".git")

    def moved(args, *positional, **keywords):
        result = p.spy(args, *positional, **keywords)
        if "hash-object" in args and "-w" in args:
            (p.root / "new.txt").write_bytes(b"after")
        return result

    with pytest.raises(SetupRefused) as caught:
        prepare(p.root, moved, shown, MESSAGE, "snapshot", shown["paths_digest"])
    assert caught.value.reason == "paths_changed"
    refreshes = p.spy.argv("--refresh")
    assert refreshes and all("-q" not in args for args in refreshes)   # the refresh refused it
    only_objects_changed(p, before)
    assert p.spy.argv("commit-tree") == [] and owned_indexes(p) == []


@needs_git
@pytest.mark.parametrize("word, answer, word_of_refusal", [
    ("--refresh", GitAnswer(1, b"a.txt: needs update\n"), "paths_changed"),
    ("--refresh", GitAnswer(128, b""), "git_failed"),
    ("--refresh", TIMED_OUT, "git_timed_out"),
    ("diff-index", GitAnswer(1, b""), "git_failed"),
    ("diff-index", TIMED_OUT, "git_timed_out"),
    ("write-tree", GitAnswer(128, b""), "git_failed"),
    ("read-tree", GitAnswer(128, b""), "git_failed"),
    ("update-index", GitAnswer(128, b""), "git_failed")])
def test_each_git_command_of_the_preparation_refuses_in_its_own_closed_word(
        tmp_path, word, answer, word_of_refusal):
    p = project(tmp_path, FILES)
    shown = seal(p)
    reader = answering(p, word, answer)
    assert refusal_of(lambda: prepare(
        p.root, reader, shown, MESSAGE, "snapshot", shown["paths_digest"])) == word_of_refusal
    assert p.spy.argv("commit-tree") == [] and owned_indexes(p) == []


@needs_git
def test_prepare_refuses_when_the_read_leaves_other_bytes_in_the_owned_index(tmp_path):
    p = project(tmp_path, FILES)
    shown = seal(p)

    def rewriting(args, *positional, **keywords):
        answer = p.spy(args, *positional, **keywords)
        if "diff-index" in args:
            keywords["index_file"].path.write_bytes(b"not the bytes that were to be installed")
        return answer

    assert refusal_of(lambda: prepare(
        p.root, rewriting, shown, MESSAGE, "snapshot", shown["paths_digest"])) == "git_failed"
    assert p.spy.argv("commit-tree") == [] and owned_indexes(p) == []


@needs_git
def test_prepare_never_writes_into_an_owned_index_that_was_replaced(tmp_path):
    p = project(tmp_path, FILES)
    shown = seal(p)
    swapped = {}

    def replacing(args, *positional, **keywords):
        answer = p.spy(args, *positional, **keywords)
        if "--refresh" in args:             # the owned file gets a new identity, same bytes
            path = keywords["index_file"].path
            swapped.update(path=path, data=path.read_bytes())
            other = path.with_name(path.name + ".swap")      # made while the first still stands,
            other.write_bytes(swapped["data"])               # so no file system hands its id back
            other.replace(path)
        return answer

    with pytest.raises(SnapshotRefused):
        prepare(p.root, replacing, shown, MESSAGE, "snapshot", shown["paths_digest"])
    assert swapped["path"].read_bytes() == swapped["data"]      # the unmarked bytes: not written
    assert p.spy.argv("commit-tree") == [] and p.spy.argv("diff-index") == []


@needs_git
def test_a_hash_answer_that_is_not_one_id_per_row_is_git_failed_and_nothing_goes_on(tmp_path):
    p = project(tmp_path, FILES)
    shown = seal(p)
    for answer in (GitAnswer(0, b"abc\n"), GitAnswer(0, b"")):
        reader = answering(p, "hash-object", answer)
        assert refusal_of(lambda: prepare(
            p.root, reader, shown, MESSAGE, "snapshot", shown["paths_digest"])) == "git_failed"
    assert p.spy.argv("write-tree") == [] and owned_indexes(p) == []


class Batches:
    """A reader that never runs Git: it keeps what it is asked and answers one id per line."""

    def __init__(self):
        self.asked = []

    def __call__(self, args, separate_stderr=False, *, stdin=None, **keywords):
        self.asked.append((args, stdin))
        count = len(stdin.splitlines())
        return GitAnswer(0, b"".join(b"%040x\n" % len(self.asked) for _ in range(count)))

    def lines(self):
        return b"".join(data for _, data in self.asked).decode("utf-8").splitlines()


def test_the_hash_and_index_batches_keep_every_row_in_order_under_the_stdin_limit():
    rows = [dict(path=f"{n:03d}" + "x" * 30000, git_oid=f"{n:040x}", git_mode="100644")
            for n in range(12)]
    order = [f"{n:03d}" for n in range(12)]
    root, reader = Path("/not/a/folder"), Batches()
    ids = git_setup_snapshot.hash_rows(root, reader, rows, "sha1", write=True)
    assert len(ids) == 12 and len(reader.asked) > 1
    assert all("-w" in args and len(data) <= 128 * 1024 for args, data in reader.asked)
    assert [line.split("/")[-1][:3] for line in reader.lines()] == order
    reader = Batches()
    prepare_module._enter(root, reader, rows, "the owned index")
    assert len(reader.asked) > 1 and all(len(data) <= 128 * 1024 for _, data in reader.asked)
    assert [line.split("\t")[1][:3] for line in reader.lines()] == order


def empty_tree(tmp_path, which, fmt):
    """The empty tree of an object format, made by the reader's own Git in a scratch repository."""
    binary = reader_binary(which)
    scratch = tmp_path / f"scratch-{fmt}"
    scratch.mkdir()
    git("init", "-q", f"--object-format={fmt}", cwd=scratch, binary=binary)
    return git("write-tree", cwd=scratch, binary=binary).stdout.decode().strip()


@needs_git
@for_every_format
def test_prepare_of_an_empty_project_commits_the_empty_tree(tmp_path, fmt):
    p = project(tmp_path, FILES, fmt=fmt)           # files on disk, and mode `empty` ignores them
    _shown, _digest, made = run(p, "empty")
    assert made.tree == empty_tree(tmp_path, "current", fmt) and made.count == 0
    shape = verify(made.install, fmt, entries=0)
    assert shape.extensions == ("TREE", "CNDT") and shape.tree_root == made.tree
    raw = p.git("cat-file", "commit", made.commit, cwd=p.root).stdout.decode("utf-8")
    assert f"tree {made.tree}\n" in raw and "\nparent " not in raw


def entry_times(listing):
    """The modification time (seconds) of every entry in `git ls-files --stage --debug`."""
    return [int(line.split()[1].split(":")[0]) for line in listing.splitlines()
            if line.strip().startswith("mtime:")]


@needs_git
def test_installed_bytes_describe_the_committed_tree_with_fresh_stat_data(tmp_path):
    p = project(tmp_path, FILES)
    shown, _digest, made = run(p)
    installed = tmp_path / "installed-index"
    installed.write_bytes(made.install)
    env = {"GIT_INDEX_FILE": str(installed)}
    same = p.git("diff-index", "--cached", "--quiet", made.commit, cwd=p.root, env=env)
    assert same.returncode == 0 and notice_lines(same) == [NOTICE]
    stage = p.git("ls-files", "--stage", cwd=p.root, env=env).stdout.decode("utf-8")
    assert stage.splitlines() == [f"{row['git_mode']} {row['git_oid']} 0\t{row['path']}"
                                  for row in shown["files"]]
    debug = p.git("ls-files", "--debug", cwd=p.root, env=env).stdout.decode("utf-8")
    assert len(entry_times(debug)) == len(FILES) and all(entry_times(debug))


@needs_git
def test_prepare_without_a_commit_when_signing_is_required(tmp_path):
    p = project(tmp_path, FILES)
    before = snapshot(p.root / ".git")
    shown, digest, made = run(p, signing=True)
    assert made.commit is None and made.tree and made.count == len(FILES)
    assert p.spy.argv("commit-tree") == []
    assert verify(made.install, "sha1", entries=len(FILES)).marker == (
        made.nonce, terms_of(shown, "snapshot", digest, made, "sha1"))
    only_objects_changed(p, before)


@needs_git
def test_prepare_removes_both_owned_indexes(tmp_path):
    p = project(tmp_path, FILES)
    run(p)
    assert owned_indexes(p) == []
    shown = seal(p)

    def moved(args, *positional, **keywords):
        result = p.spy(args, *positional, **keywords)
        if "hash-object" in args and "-w" in args:
            (p.root / "a.txt").write_bytes(b"after the write\n")
        return result

    with pytest.raises(SetupRefused):
        prepare(p.root, moved, shown, MESSAGE, "snapshot", shown["paths_digest"])
    assert p.spy.argv("--refresh") and owned_indexes(p) == []     # a failed run leaves none either
