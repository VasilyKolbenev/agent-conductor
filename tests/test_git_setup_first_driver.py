"""The driver of the first commit below the route (plan Task 7; rulings OD-3, OD-4, decision E).

What the route test cannot see: how the owner's index is read (equivalence of the tree and nothing
more), the order in which the product's files and the owner's files come into being, what a
refusal undoes and what it keeps, and that the walk of the decision table ends. The operation of a
test is made by hand, phase A and the records, so a state a crash would leave can be built exactly.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from conductor.command import git_setup_first as first
from conductor.command import git_setup_first_lock as lock
from conductor.command import git_setup_first_records as records
from conductor.command.git_setup_first_prepare import prepare
from conductor.command.git_setup_first_resume import Act, Index
from conductor.command.git_setup_records import SetupRefused
from conductor.command.project_git import GitAnswer, GitReadFailed
from conductor.ownership import data_root
from tests.git_first_bench import confirm, confirm_door, op_file, project, seal  # noqa: F401
from tests.git_repo_helpers import needs_git, snapshot
from tests.test_command_http_api import NOW
from tests.test_git_setup import reason

FILES = {"a.txt": b"one\n", "docs/b.md": b"two\n"}
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
TREE = "1" * 40
DOOR = pytest.mark.usefixtures("confirm_door")


def text(p, *args):
    return p.git(*args, cwd=p.root).stdout.decode().strip()


def an_operation(p):
    """Phase A by hand and the op record `prepared`: nothing in `.git` but objects."""
    shown = seal(p)
    digest, message = shown["paths_digest"], first.message("snapshot", len(shown["files"]))
    made = prepare(p.root, p.spy, shown, message, "snapshot", digest)
    op = records.new_op("snapshot", digest, "Owner", shown, made, NOW, message)
    return records.start(p.root, op, made.install), made


def owner_ref(p):
    made = text(p, "commit-tree", "-m", "owner", EMPTY_TREE)
    p.git("update-ref", "refs/heads/trunk", made, cwd=p.root)
    return made


def copies(p):
    return sorted(path.name for path in (p.root / ".git").glob("conduct-first-index-*"))


def install_files(p):
    return sorted((data_root(p.root) / "git" / "setup").glob("first_commit.index-*"))


# --- the read of the owner's index: equivalence of the tree, nothing about whose file it is -----


class Reader:
    """A Git that answers one `GitAnswer` to everything, keeps its calls and may act as it does."""

    def __init__(self, answer, during=None):
        self.answer, self.during, self.calls = answer, during, []

    def __call__(self, args, separate_stderr=False, **keywords):
        self.calls.append((tuple(args), separate_stderr, keywords))
        if self.during is not None:
            self.during()
        return self.answer


def a_folder_with_an_index(tmp_path, data=b"not read by the scripted reader"):
    folder = tmp_path / "gitdir"
    folder.mkdir()
    (folder / "index").write_bytes(data)
    return folder


def test_index_state_is_absent_without_a_git_call_when_no_index_file_stands(tmp_path):
    reader = Reader(GitAnswer(0, b""))
    assert first.index_state("root", reader, TREE, tmp_path) is Index.ABSENT
    assert reader.calls == []


@pytest.mark.parametrize("code, expected", [(0, Index.MATCHES), (1, Index.OTHER)])
def test_index_state_reads_only_exit_zero_as_equivalent_and_exit_one_as_another_tree(
        tmp_path, code, expected):
    reader = Reader(GitAnswer(code, b""))
    assert first.index_state("root", reader, TREE, a_folder_with_an_index(tmp_path)) is expected


def test_index_state_asks_one_read_only_diff_of_the_owners_index_and_names_no_file_for_it(tmp_path):
    reader = Reader(GitAnswer(0, b""))
    first.index_state("root", reader, TREE, a_folder_with_an_index(tmp_path))
    assert reader.calls == [(("--no-optional-locks", "-C", "root", "diff-index", "--cached",
                              "--quiet", TREE), True, {})]


@pytest.mark.parametrize("answer, word", [
    (GitAnswer(128, b""), "git_failed"), (GitAnswer(2, b""), "git_failed"),
    (GitAnswer(None, b""), "git_timed_out"), (GitAnswer(0, b"", timed_out=True), "git_timed_out"),
    (GitAnswer(0, b"", truncated=True), "git_failed"),
    (GitAnswer(1, b"", truncated=True), "git_failed")])
def test_an_error_a_timeout_or_a_cut_answer_is_never_an_index_state(tmp_path, answer, word):
    folder = a_folder_with_an_index(tmp_path)
    with pytest.raises(GitReadFailed) as caught:
        first.index_state("root", Reader(answer), TREE, folder)
    assert caught.value.code == word
    assert (folder / "index").read_bytes() == b"not read by the scripted reader"


def test_an_index_that_changed_under_the_read_is_never_an_index_state(tmp_path):
    folder = a_folder_with_an_index(tmp_path)
    reader = Reader(GitAnswer(0, b""), during=lambda: (folder / "index").write_bytes(b"other"))
    with pytest.raises(GitReadFailed) as caught:
        first.index_state("root", reader, TREE, folder)
    assert caught.value.code == "git_failed"


def test_an_index_that_is_a_directory_is_another_index_and_is_not_read(tmp_path):
    folder = tmp_path / "gitdir"
    (folder / "index").mkdir(parents=True)
    reader = Reader(GitAnswer(0, b""))
    assert first.index_state("root", reader, TREE, folder) is Index.OTHER
    assert reader.calls == []


def test_an_index_that_is_a_link_is_another_index_and_is_not_read(tmp_path):
    folder, target = tmp_path / "gitdir", tmp_path / "elsewhere"
    folder.mkdir()
    target.write_bytes(b"x")
    try:
        (folder / "index").symlink_to(target)
    except OSError as error:
        pytest.skip(str(error))
    reader = Reader(GitAnswer(0, b""))
    assert first.index_state("root", reader, TREE, folder) is Index.OTHER
    assert reader.calls == [] and target.read_bytes() == b"x"


@needs_git
def test_an_absent_index_is_never_read_as_equivalent_to_the_empty_tree(tmp_path):
    p = project(tmp_path, FILES)
    folder = p.root / ".git"
    assert not (folder / "index").exists()
    alone = p.git("diff-index", "--cached", "--quiet", EMPTY_TREE, cwd=p.root)
    assert alone.returncode == 0           # the premise: Git alone calls "nothing there" equal
    assert first.index_state(p.root, p.spy, EMPTY_TREE, folder) is Index.ABSENT


@needs_git
def test_an_equivalent_owner_index_is_read_as_matching_and_left_untouched(tmp_path):
    p = project(tmp_path, FILES)
    folder = p.root / ".git"
    p.git("add", "a.txt", cwd=p.root)
    tree = text(p, "write-tree")
    path = folder / "index"
    before = (path.read_bytes(), os.lstat(path))
    assert first.index_state(p.root, p.spy, tree, folder) is Index.MATCHES
    assert first.index_state(p.root, p.spy, EMPTY_TREE, folder) is Index.OTHER
    after = (path.read_bytes(), os.lstat(path))
    assert after[0] == before[0] and after[1].st_ino == before[1].st_ino
    assert after[1].st_mtime_ns == before[1].st_mtime_ns and not (folder / "index.lock").exists()


@needs_git
def test_an_owner_index_of_the_empty_tree_is_equivalent_in_mode_empty_and_left_untouched(tmp_path):
    p = project(tmp_path, FILES)
    folder = p.root / ".git"
    p.git("read-tree", "--empty", cwd=p.root)
    before = (folder / "index").read_bytes()
    assert len(before) == 65
    assert first.index_state(p.root, p.spy, EMPTY_TREE, folder) is Index.MATCHES
    assert (folder / "index").read_bytes() == before


# --- the order of effects (OD-4) -----------------------------------------------------------------


def look(p):
    """Which of the files of the operation stand now."""
    folder, op = p.root / ".git", op_file(p)
    return dict(install=bool(install_files(p)), copy=bool(copies(p)),
                stage=json.loads(op.read_text())["stage"] if op.exists() else None,
                lock=(folder / "index.lock").exists(), index=(folder / "index").exists(),
                ref=(folder / "refs" / "heads" / "trunk").exists())


STANDS = dict(install=True, copy=False, index=False, ref=False)
ORDER = [
    ("_do_take_lock", dict(STANDS, stage="prepared", lock=False)),
    ("_do_mark_locked", dict(STANDS, stage="prepared", lock=True)),
    ("_do_move_ref", dict(STANDS, stage="locked", lock=True)),
    ("_do_mark_ref_moved", dict(STANDS, stage="locked", lock=True, ref=True)),
    ("_do_install_index", dict(STANDS, stage="ref_moved", lock=True, ref=True)),
    ("_do_finish", dict(STANDS, stage="ref_moved", lock=False, index=True, ref=True)),
]


@needs_git
@DOOR
def test_first_commit_publishes_the_bytes_then_the_op_then_the_copy_then_the_lock(
        tmp_path, monkeypatch):
    p = project(tmp_path, FILES)
    seen, moves = [], []
    for name, _ in ORDER:
        def watch(api, op, real=getattr(first, name), name=name):
            seen.append((name, look(p)))
            return real(api, op)
        monkeypatch.setattr(first, name, watch)
    real_move = lock._move

    def watch_move(source, target):
        if target.name == "index.lock":
            moves.append((source.name.startswith("conduct-first-index-"), look(p)))
        return real_move(source, target)

    monkeypatch.setattr(lock, "_move", watch_move)
    assert confirm(p).status == 201
    assert seen == ORDER
    assert moves == [(True, dict(STANDS, stage="prepared", copy=True, lock=False))]
    assert look(p) == dict(install=False, copy=False, stage=None, lock=False, index=True, ref=True)


@needs_git
@DOOR
def test_the_receipt_is_written_before_the_op_is_retired_and_the_bytes_stand_until_then(
        tmp_path, monkeypatch):
    p = project(tmp_path, FILES)
    seen, real = [], records.retire
    receipt = data_root(p.root) / "git" / "setup" / "first_commit.json"

    def watching(root, op):
        seen.append(dict(receipt=receipt.exists(), op=op_file(p).exists(),
                         install=bool(install_files(p))))
        return real(root, op)

    monkeypatch.setattr(records, "retire", watching)
    assert confirm(p).status == 201
    assert seen == [dict(receipt=True, op=True, install=True)]


# --- what a refusal undoes and what it keeps (decision E) ---------------------------------------


@needs_git
def test_a_refusal_drops_the_own_copy_and_keeps_the_op_and_its_install_bytes(tmp_path):
    p = project(tmp_path, FILES)
    op, made = an_operation(p)
    lock.ensure_copy(p.root / ".git", op.nonce, made.install)
    assert copies(p)
    owner = owner_ref(p)
    with pytest.raises(SetupRefused) as caught:
        first.drive(p.api, op)
    assert caught.value.reason == "head_exists"
    assert copies(p) == [] and op_file(p).exists() and len(install_files(p)) == 1
    assert text(p, "rev-parse", "refs/heads/trunk") == owner
    assert not (p.root / ".git" / "index.lock").exists()


@needs_git
def test_a_refusal_for_a_foreign_lock_drops_the_copy_and_leaves_the_lock_alone(tmp_path):
    p = project(tmp_path, FILES)
    op, made = an_operation(p)
    lock.ensure_copy(p.root / ".git", op.nonce, made.install)
    (p.root / ".git" / "index.lock").write_bytes(b"")
    with pytest.raises(SetupRefused) as caught:
        first.drive(p.api, op)
    assert caught.value.reason == "index_locked"
    assert (p.root / ".git" / "index.lock").read_bytes() == b"" and copies(p) == []
    assert op_file(p).exists() and len(install_files(p)) == 1


@needs_git
def test_a_refusal_frees_the_own_lock_and_drops_the_copy_of_an_operation_the_owner_overtook(
        tmp_path):
    p = project(tmp_path, FILES)
    op, made = an_operation(p)
    lock.take_lock(p.root / ".git", op.nonce, made.install)
    assert (p.root / ".git" / "index.lock").exists()
    owner = owner_ref(p)
    with pytest.raises(SetupRefused) as caught:
        first.drive(p.api, op)
    assert caught.value.reason == "head_exists"
    assert not (p.root / ".git" / "index.lock").exists() and copies(p) == []
    assert text(p, "rev-parse", "refs/heads/trunk") == owner
    assert op_file(p).exists() and len(install_files(p)) == 1


@needs_git
def test_a_refusal_that_cannot_prove_the_install_bytes_removes_nothing_and_says_setup_damaged(
        tmp_path):
    p = project(tmp_path, FILES)
    op, made = an_operation(p)
    lock.take_lock(p.root / ".git", op.nonce, made.install)
    owner_ref(p)
    install_files(p)[0].write_bytes(b"torn")
    with pytest.raises(SetupRefused) as caught:
        first.drive(p.api, op)
    assert caught.value.reason == "setup_damaged"
    assert (p.root / ".git" / "index.lock").read_bytes() == made.install


@needs_git
@DOOR
def test_other_terms_over_an_operation_whose_ref_moved_are_refused_and_nothing_is_undone(tmp_path):
    p = project(tmp_path, FILES)
    digest = seal(p)["paths_digest"]
    op, made = an_operation(p)
    lock.take_lock(p.root / ".git", op.nonce, made.install)
    op = first._do_mark_locked(p.api, op)
    first._do_move_ref(p.api, op)
    before = (snapshot(p.root / ".git"), op_file(p).read_bytes())
    refused = confirm(p, digest=digest, actor="Another")
    assert refused.status == 409 and reason(refused) == "setup_terms_changed"
    assert (snapshot(p.root / ".git"), op_file(p).read_bytes()) == before


# --- the driver makes no file effect of its own --------------------------------------------------

#: What would put a name into, or take one out of, `.git` from the driver itself. Every file the
#: driver makes or removes is the records' or the lock module's, which never replace.
FILE_EFFECTS = ("os.replace", "os.rename", "os.unlink", "os.remove", "os.link", "shutil",
                ".unlink(", ".rename(", ".replace(", ".write_bytes", ".write_text", "open(")


def file_effects(source):
    """The spellings of a file effect that `source` holds, one line number each."""
    return [(number, word) for number, line in enumerate(source.splitlines(), 1)
            for word in FILE_EFFECTS if word in line.split("#")[0]]


def test_the_driver_module_makes_and_removes_no_file_of_its_own():
    source = Path(first.__file__).read_text(encoding="utf-8")
    assert file_effects(source) == []


def test_the_scan_for_file_effects_sees_each_spelling_it_looks_for():
    for word in FILE_EFFECTS:
        assert file_effects(f"    {word}x, y)") == [(1, word)], word
    assert file_effects("    harmless(name)  # os.replace is only named here") == []


# --- the end of the walk -------------------------------------------------------------------------


@needs_git
def test_a_walk_that_never_ends_is_setup_damaged_after_the_turns_it_is_given(tmp_path, monkeypatch):
    p = project(tmp_path, FILES)
    op, _ = an_operation(p)
    asked = []

    def never_done(*facts):
        asked.append(facts)
        return Act.RELEASE_LOCK

    monkeypatch.setattr(first, "next_action", never_done)
    with pytest.raises(SetupRefused) as caught:
        first.drive(p.api, op)
    assert caught.value.reason == "setup_damaged" and len(asked) == first.MAX_TURNS


# --- the objects the write relies on --------------------------------------------------------------


class Objects:
    """A Git that answers `cat-file --batch-check` for the names it is told it holds."""

    def __init__(self, held):
        self.held, self.calls = held, []

    def __call__(self, args, separate_stderr=False, **keywords):
        self.calls.append((tuple(args), keywords))
        names = keywords["stdin"].decode("ascii").splitlines()
        lines = [f"{name} {self.held[name]} 1" if name in self.held else f"{name} missing"
                 for name in names]
        return GitAnswer(0, ("\n".join(lines) + "\n").encode("ascii"))


def an_object_world(blobs):
    shown = {"files": [{"git_oid": f"{n:040x}"} for n in range(blobs)]}
    made = SimpleNamespace(tree="a" * 40, commit="b" * 40)
    held = {row["git_oid"]: "blob" for row in shown["files"]}
    return shown, made, {**held, made.tree: "tree", made.commit: "commit"}


def test_the_objects_the_write_relies_on_are_asked_for_in_calls_under_the_stdin_bound():
    shown, made, held = an_object_world(5000)
    reader = Objects(held)
    first._objects_present(Path("root"), reader, shown, made)
    sizes = [len(keywords["stdin"]) for _, keywords in reader.calls]
    assert len(sizes) == 3 and max(sizes) <= 128 * 1024
    assert all("--batch-check" in args for args, _ in reader.calls)


@pytest.mark.parametrize("damage", ["blob_missing", "tree_missing", "commit_missing",
                                    "blob_is_a_tree", "tree_is_a_blob"])
def test_a_missing_or_mistyped_object_is_paths_changed(damage):
    shown, made, held = an_object_world(3)
    blob = shown["files"][1]["git_oid"]
    held = {"blob_missing": {k: v for k, v in held.items() if k != blob},
            "tree_missing": {k: v for k, v in held.items() if k != made.tree},
            "commit_missing": {k: v for k, v in held.items() if k != made.commit},
            "blob_is_a_tree": {**held, blob: "tree"},
            "tree_is_a_blob": {**held, made.tree: "blob"}}[damage]
    with pytest.raises(SetupRefused) as caught:
        first._objects_present(Path("root"), Objects(held), shown, made)
    assert caught.value.reason == "paths_changed"


def test_a_signed_road_has_no_commit_to_ask_for_and_every_other_object_is_still_asked():
    shown, made, held = an_object_world(2)
    made.commit = None
    reader = Objects({k: v for k, v in held.items() if k != "b" * 40})
    first._objects_present(Path("root"), reader, shown, made)
    asked = reader.calls[0][1]["stdin"].decode("ascii").split()
    assert "b" * 40 not in asked and made.tree in asked and len(asked) == 3
