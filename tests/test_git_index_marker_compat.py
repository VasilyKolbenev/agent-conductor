"""A Git reads the bytes the product installs: the marker costs one stderr line and nothing else.

Every probe takes the reader's Git as a parameter (`tests.git_first_readers.READERS`): the current
Git always, and the isolated Git 2.31 when `CONDUCT_OLD_GIT` names it (gate G-old of the plan; the
`old_git` ids are skipped, with the reason, while it is unset). Each runs for SHA-1 and SHA-256
and for both modes of a first commit (an empty tree, and a tree of files). The repositories are
scratch folders outside every repository, and the account's Git configuration is out of sight.
"""
from dataclasses import dataclass

import pytest

from conductor.command.accept_manifest import sha256
from conductor.command.git_setup_first_index import (
    Binding, IndexFormatRefused, IndexShape, mark, terms_hash, verify, verify_binding)
from tests.git_first_readers import READERS
from tests.git_first_scratch import NOTICE, Scratch, notice_lines, scratch
from tests.git_index_bytes import SIZE, digest, extension
from tests.git_repo_helpers import needs_git

pytestmark = needs_git
FORMATS = ["sha1", "sha256"]
FILES = {"a.txt": "one\n", "d/b.txt": "two\n", "d/e/c.txt": "three\n"}
MODES = {"empty": {}, "snapshot": FILES}
NONCE, OTHER_NONCE = "0123456789abcdef", "fedcba9876543210"
SIX = {"f1.txt": "1\n", "f2.txt": "2\n", "f3.txt": "3\n", "f4.txt": "4\n", "f5.txt": "5\n",
       "d/y.txt": "y\n"}
FAMILIES = {
    "end_of_entries": [("index.recordEndOfIndexEntries", "true")],
    "threads_auto": [("index.threads", "true")],
    "threads_four": [("index.threads", "4")],
    "untracked_cache": [("core.untrackedCache", "true")],
    "version_four": [("index.version", "4")],
    "skip_hash": [("index.skipHash", "true")],
    "split_index": [("core.splitIndex", "true")],
    "many_files": [("feature.manyFiles", "true")],
}
FAMILIES["all_together"] = [pair for pairs in list(FAMILIES.values()) for pair in pairs]
#: The settings that put an end-of-entries extension (EOIE) into an index the owner's Git writes.
EOIE_FAMILIES = ("end_of_entries", "threads_auto", "threads_four")
for_every_reader = pytest.mark.parametrize("which", READERS)
for_every_format = pytest.mark.parametrize("fmt", FORMATS)
for_both_modes = pytest.mark.parametrize("mode", MODES)


def reads(tree):
    """The three reads of the owner's Git that the ruling names, as argument lists."""
    return {"diff-index": ("--no-optional-locks", "diff-index", "--cached", "--quiet", tree),
            "status": ("status", "--porcelain"), "write-tree": ("write-tree",)}


@dataclass(frozen=True)
class Made:
    """One operation's bytes for a tree, built by the reader's own Git."""

    box: Scratch
    tree: str
    rows: int
    base: bytes
    marked: bytes
    claim: Binding


def operation(box, tree, base, mode, rows, nonce):
    """Mark `base` for an operation with this nonce; the terms come from the same call."""
    paths = None if mode == "empty" else "sha256:" + "c" * 64
    terms = terms_hash(nonce=nonce, mode=mode, digest_version=2, paths_digest=paths,
                       target_ref="refs/heads/main", object_format=box.fmt, expected_tree=tree,
                       file_count=rows)
    marked = mark(base, box.fmt, nonce=nonce, terms=terms)
    return Made(box, tree, rows, base, marked,
                Binding(nonce, sha256(marked), terms, tree, box.fmt, rows))


def made(tmp_path, which, fmt, mode, nonce=NONCE):
    box = scratch(tmp_path, which, fmt)
    tree = box.tree(MODES[mode])
    return operation(box, tree, box.base(tree, len(MODES[mode])), mode, len(MODES[mode]), nonce)


def published(m):
    """The state the owner's Git meets: the branch is at the commit, the marked bytes installed."""
    m.box.publish(m.box.commit(m.tree))
    m.box.install(m.marked)
    return m.box


@for_every_reader
@for_every_format
@for_both_modes
def test_marked_index_is_read_by_git_with_one_ignored_extension_line_in_both_formats_and_modes(
        tmp_path, which, fmt, mode):
    m = made(tmp_path, which, fmt, mode)
    box, seen = published(m), {}
    for name, read in reads(m.tree).items():
        box.install(m.marked)
        done = box.run(*read, check=False)
        seen[name] = (done.returncode, notice_lines(done), done.stdout.decode().strip())
    print(f"marker-line {which} {fmt} {mode}: {seen}")     # what the gate driver copies out
    assert seen == {"diff-index": (0, [NOTICE], ""), "status": (0, [NOTICE], ""),
                    "write-tree": (0, [NOTICE], m.tree)}


@for_every_reader
@for_every_format
@for_both_modes
def test_the_marker_survives_the_reads_and_goes_with_the_owners_next_write(
        tmp_path, which, fmt, mode):
    m = made(tmp_path, which, fmt, mode)
    box = published(m)
    box.run(*reads(m.tree)["diff-index"])
    box.run(*reads(m.tree)["status"])
    assert verify(box.installed(), fmt, entries=m.rows).marker == (NONCE, m.claim.terms)
    box.write({"later.txt": "later\n"})
    box.run("add", "later.txt")
    assert b"CNDT" not in box.installed()


@for_every_reader
@for_every_format
def test_a_lower_case_marker_would_break_every_read_so_the_signature_is_pinned(
        tmp_path, which, fmt):
    m = made(tmp_path, which, fmt, "snapshot")
    body = m.base[:-SIZE[fmt]] + extension(b"cndt", b"v1;nonce=" + NONCE.encode())
    box, broken = published(m), {}
    for name, read in reads(m.tree).items():
        box.install(body + digest(fmt, body))
        done = box.run(*read, check=False)
        broken[name] = (done.returncode != 0, "cndt" in done.stderr.decode().lower())
    assert broken == {name: (True, True) for name in reads(m.tree)}


@for_every_reader
@for_every_format
@for_both_modes
def test_the_format_check_accepts_exactly_what_the_readers_git_builds_under_the_pin(
        tmp_path, which, fmt, mode):
    m = made(tmp_path, which, fmt, mode)
    assert verify(m.base, fmt, entries=m.rows) == IndexShape(
        entries=m.rows, extensions=("TREE",), tree_root=m.tree, marker=None)
    assert verify(m.marked, fmt, entries=m.rows).extensions == ("TREE", "CNDT")


@for_every_reader
@for_every_format
@for_both_modes
def test_two_operations_give_different_bytes_on_the_readers_git_and_each_binding_proves_its_own(
        tmp_path, which, fmt, mode):
    first = made(tmp_path, which, fmt, mode, NONCE)
    second = operation(first.box, first.tree, first.base, mode, first.rows, OTHER_NONCE)
    assert len({first.base, first.marked, second.marked}) == 3
    assert [verify_binding(first.marked, first.claim), verify_binding(second.marked, first.claim),
            verify_binding(first.marked, second.claim),
            verify_binding(second.marked, second.claim)] == [True, False, False, True]
    for one in (first, second):
        box = published(one)
        assert box.run(*reads(one.tree)["diff-index"], check=False).returncode == 0


def foreign_bytes(box, mode):
    """What the reader's own Git writes where the product would install: the empty index of
    `read-tree --empty` (mode empty), or the owner's `add -A` with `write-tree` (mode snapshot)."""
    if mode == "empty":
        box.run("read-tree", "--empty")
    else:
        box.run("add", "-A")
        box.run("write-tree")
    data = box.installed()
    (box.git_dir / "index").unlink()
    return data


@for_every_reader
@for_every_format
@for_both_modes
def test_bytes_the_readers_own_git_writes_are_never_judged_own_in_both_modes_and_formats(
        tmp_path, which, fmt, mode):
    m = made(tmp_path, which, fmt, mode)
    foreign = foreign_bytes(m.box, mode)
    assert sha256(foreign) != m.claim.install_sha256
    assert verify_binding(foreign, m.claim) is False
    assert verify_binding(foreign, Binding(NONCE, sha256(foreign), m.claim.terms, m.tree, fmt,
                                           m.rows)) is False
    assert verify_binding(m.marked, m.claim) is True


@for_every_format
def test_in_mode_empty_the_current_git_writes_the_unmarked_base_bytes_itself(tmp_path, fmt):
    """The measured fact that makes the marker necessary: the owner's `read-tree --empty` writes
    the very bytes the product would build for the empty tree, so equal bytes prove nothing. Only
    the current Git is asserted; what the old Git writes goes into the evidence file."""
    m = made(tmp_path, "current", fmt, "empty")
    assert foreign_bytes(m.box, "empty") == m.base != m.marked


def families_built(box, tree, *, pin):
    """For each family: the bytes the product's commands give with that owner configuration set,
    and the shared index files that appeared. Every setting is unset again afterwards."""
    built = {}
    for name, pairs in FAMILIES.items():
        for key, value in pairs:
            box.run("config", "--local", key, value)
        data = box.base(tree, len(SIX), pin=pin)
        shared = box.shared_indexes()
        for key in dict.fromkeys(key for key, _ in pairs):
            box.run("config", "--local", "--unset", key)
        for leftover in shared:
            (box.git_dir / leftover).unlink()
        built[name] = (data, shared)
    return built


def judged(data, fmt):
    try:
        shape = verify(data, fmt, entries=len(SIX))
    except IndexFormatRefused as refused:
        return refused.reason
    return "plain" if shape.extensions == ("TREE",) else "other:" + ",".join(shape.extensions)


@for_every_reader
@for_every_format
def test_the_pin_keeps_every_optional_extension_out_of_an_index_the_product_builds(
        tmp_path, which, fmt):
    box = scratch(tmp_path, which, fmt)
    tree = box.tree(SIX)
    pinned = families_built(box, tree, pin=True)
    assert {name: judged(data, fmt) for name, (data, _) in pinned.items()} == {
        name: "plain" for name in FAMILIES}
    assert {name: shared for name, (_, shared) in pinned.items()} == {name: [] for name in FAMILIES}
    assert len({data for data, _ in pinned.values()}) == 1
    assert verify(pinned["all_together"][0], fmt, entries=len(SIX)).tree_root == tree


@for_every_reader
@for_every_format
def test_without_the_pin_an_owner_setting_puts_an_end_of_entries_extension_into_the_bytes(
        tmp_path, which, fmt):
    box = scratch(tmp_path, which, fmt)
    tree = box.tree(SIX)
    loose = families_built(box, tree, pin=False)
    outcomes = {name: judged(data, fmt) for name, (data, _) in loose.items()}
    assert any(outcomes[name] == "extension_not_allowed" for name in EOIE_FAMILIES), outcomes


@for_every_format
def test_without_the_pin_every_owner_setting_changes_the_bytes_of_the_current_git(tmp_path, fmt):
    """Measured on the current Git: no family is ignored, so each flag of the pin is load-bearing.
    What the old Git does is recorded in the evidence file, not assumed."""
    box = scratch(tmp_path, "current", fmt)
    tree = box.tree(SIX)
    outcomes = {name: judged(data, fmt) for name, (data, _) in
                families_built(box, tree, pin=False).items()}
    assert {name: outcome for name, outcome in outcomes.items() if outcome == "plain"} == {}


def standing(git_dir):
    """The identity of the lock and of the index: bytes, size, modification time and inode."""
    return [(path.read_bytes(), path.stat().st_size, path.stat().st_mtime_ns, path.stat().st_ino)
            for path in (git_dir / "index.lock", git_dir / "index")]


@for_every_reader
@for_every_format
def test_the_drivers_git_commands_work_under_a_standing_index_lock_on_this_git(
        tmp_path, which, fmt):
    m = made(tmp_path, which, fmt, "snapshot")
    box, git_dir = m.box, m.box.git_dir
    other_tree = box.tree({"z.txt": "other\n"})
    first, second = box.commit(m.tree, "first"), box.commit(m.tree, "second")
    box.install(m.marked)
    (git_dir / "index.lock").write_bytes(b"")
    before = standing(git_dir)
    quiet = reads("")["diff-index"][:-1]
    against = [box.run(*quiet, tree, check=False).returncode for tree in (m.tree, other_tree)]
    assert against == [0, 1]
    assert standing(git_dir) == before
    dies = box.run("write-tree", check=False)
    assert dies.returncode != 0 and b"index.lock" in dies.stderr
    assert standing(git_dir) == before
    (git_dir / "index").unlink()
    emptied = box.empty_tree()
    assert [box.run(*quiet, tree, check=False).returncode for tree in (emptied, m.tree)] == [0, 1]
    assert not (git_dir / "index").exists()
    zero = "0" * len(m.tree)
    box.run("update-ref", "-m", "first commit", "refs/heads/trunk", first, zero)
    refused = box.run("update-ref", "-m", "other", "refs/heads/trunk", second, zero, check=False)
    assert refused.returncode != 0 and box.text("rev-parse", "refs/heads/trunk") == first
    assert (git_dir / "index.lock").read_bytes() == b""
