"""Ownership of `index.lock` by the whole binding, and the moves that never replace (S4).

The lock module is pure file work on a folder, so most of these tests need no Git: the bytes are
built by hand (`tests.git_index_bytes`) and marked by the product's own `mark`. One test takes the
bytes the reader's own Git writes (`tests.git_first_readers.READERS`: the current Git, and the
isolated 2.31 when `CONDUCT_OLD_GIT` names it) and shows that none of them is judged the product's
(gate G-old, row 5). The two ways of moving a name are both run on every platform: a name moved by
a link and an unlink leaves two names for one inode when the second half fails, and the states of
that are checked on hard links here as on a POSIX file system.
"""
import ast
import errno
import os
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from conductor.command import git_setup_first_lock as lock_module
from conductor.command.accept_manifest import sha256
from conductor.command.git_setup_first_index import Binding, binding_of, mark
from conductor.command.git_setup_first_lock import (
    INDEX, LOCK, MoveRefused, NameTaken, copy_path, drop_copy, ensure_copy, install_index,
    lock_state, release_own_lock, take_lock)
from conductor.command.git_setup_first_records import INDEX_LIMIT, Op
from conductor.command.git_setup_first_resume import (
    PREPARED, REF_MOVED, Act, Index, Lock, Ref, next_action)
from conductor.command.git_setup_records import SetupRefused
from tests.git_first_readers import READERS
from tests.git_first_scratch import scratch
from tests.git_index_bytes import DEFAULT_TREE, plain
from tests.git_repo_helpers import needs_git
from tests.test_git_index_marker_compat import FILES, MODES, NONCE, OTHER_NONCE, operation
from tests.test_git_setup_first_records import DIGEST, an_op

FORMATS = ["sha1", "sha256"]
#: The tree every Git of that hash format names for the empty tree: what an index of no entries
#: carries as its cache tree, in the 65 and 89 bytes Git itself writes for it.
EMPTY_TREE = {"sha1": "4b825dc642cb6eb9a060e54bf8d69288fbee4904",
              "sha256": "6ef19b41225c5369f1c104d45d8d85efa9b057b53b14b4b9b939dd74decc5321"}
EMPTY_BYTES = {"sha1": 65, "sha256": 89}
for_every_format = pytest.mark.parametrize("fmt", FORMATS)
for_every_reader = pytest.mark.parametrize("which", READERS)
for_both_modes = pytest.mark.parametrize("mode", MODES)
for_both_sizes = pytest.mark.parametrize("rows", [0, 3])


@dataclass(frozen=True)
class Made:
    """One operation's marked bytes, its binding (taken from a verified op) and its folder."""

    git_dir: Path
    binding: Binding
    op: Op
    base: bytes
    data: bytes

    @property
    def lock(self) -> Path:
        return self.git_dir / LOCK

    @property
    def index(self) -> Path:
        return self.git_dir / INDEX

    @property
    def copy(self) -> Path:
        return copy_path(self.git_dir, self.op.nonce)


def made(tmp_path, fmt="sha1", rows=0, *, nonce=NONCE, tree=None, name="gitdir"):
    """The marked bytes of an operation over `rows` of the files, and the binding of its op."""
    root = DEFAULT_TREE[fmt] if tree is None else tree
    first = an_op(nonce=nonce, mode="snapshot" if rows else "empty",
                  paths_digest=DIGEST if rows else None, object_format=fmt, expected_tree=root,
                  commit="b" * len(root), file_count=rows)
    base = plain(list(FILES)[:rows], fmt, tree=root)
    data = mark(base, fmt, nonce=nonce, terms=binding_of(first).terms)
    op = replace(first, install_sha256=sha256(data))
    git_dir = tmp_path / name
    git_dir.mkdir()
    return Made(git_dir, binding_of(op), op, base, data)


def snap(path):
    """What a stray touch would change about one name: its file id, size, time and bytes."""
    found = os.lstat(path)
    return found.st_ino, found.st_size, found.st_mtime_ns, path.read_bytes()


def refused_and_untouched(m, before):
    """Every function of the module leaves a lock that is not this operation's exactly as it was."""
    assert lock_state(m.git_dir, m.binding) is Lock.FOREIGN
    assert release_own_lock(m.git_dir, m.binding) is False
    assert install_index(m.git_dir, m.binding, m.data) is False
    with pytest.raises(NameTaken):
        take_lock(m.git_dir, m.binding.nonce, m.data)
    assert snap(m.lock) == before
    assert not m.index.exists()


@pytest.fixture(params=["native", "linked"])
def moves(request, monkeypatch):
    """Every way this host moves a name: `native`, and `linked` where native is a rename."""
    if request.param == "linked":
        if os.name != "nt":
            pytest.skip("a move off Windows is already made by a link")
        monkeypatch.setattr(lock_module, "LINK_MOVES", True)
    return request.param


@pytest.fixture
def by_link(monkeypatch, tmp_path):
    """Moves made by a link and an unlink, whatever the host; skips where no hard link exists."""
    probe = tmp_path / "probe-a"
    probe.write_bytes(b"x")
    try:
        os.link(probe, tmp_path / "probe-b")
    except OSError:
        pytest.skip("this file system makes no hard links")
    monkeypatch.setattr(lock_module, "LINK_MOVES", True)


def failing_first_unlink(monkeypatch):
    """The first removal of a name fails (a crash between the two halves of a move)."""
    real, calls = os.unlink, []

    def unlink(path):
        calls.append(Path(path).name)
        if len(calls) == 1:
            raise OSError(errno.EIO, "the removal failed")
        real(path)

    monkeypatch.setattr(lock_module, "_unlink", unlink)
    return calls


@for_every_format
@for_both_sizes
def test_lock_state_names_none_own_and_foreign_by_the_whole_binding(tmp_path, fmt, rows):
    m = made(tmp_path, fmt, rows)
    assert lock_state(m.git_dir, m.binding) is Lock.NONE
    m.lock.write_bytes(m.data)
    assert lock_state(m.git_dir, m.binding) is Lock.OWN
    terms = m.binding.terms
    names = list(FILES)[:rows] + ["z.txt"]
    elsewhere = {
        "one byte flipped": m.data[:-1] + bytes([m.data[-1] ^ 1]),
        "the same entries without the marker": m.base,
        "the marker of another nonce": mark(m.base, fmt, nonce=OTHER_NONCE, terms=terms),
        "the marker of other terms": mark(m.base, fmt, nonce=NONCE, terms="f" * 64),
        "the right marker on one more entry": mark(
            plain(names, fmt, tree=m.op.expected_tree), fmt, nonce=NONCE, terms=terms),
    }
    for what, data in elsewhere.items():
        m.lock.write_bytes(data)
        assert lock_state(m.git_dir, m.binding) is Lock.FOREIGN, what


@pytest.mark.parametrize("part", ["nonce", "terms", "install_sha256", "expected_tree",
                                  "object_format", "file_count"])
def test_a_lock_is_foreign_when_any_one_part_of_its_binding_differs(tmp_path, part):
    m = made(tmp_path, "sha1", 3)
    m.lock.write_bytes(m.data)
    assert lock_state(m.git_dir, m.binding) is Lock.OWN
    other = {"nonce": OTHER_NONCE, "terms": "f" * 64, "install_sha256": "sha256:" + "f" * 64,
             "expected_tree": "c" * 40, "object_format": "sha256", "file_count": 4}[part]
    changed = replace(m.binding, **{part: other})
    assert lock_state(m.git_dir, changed) is Lock.FOREIGN


def test_the_marked_bytes_of_another_operation_are_foreign_to_this_one(tmp_path):
    mine = made(tmp_path, "sha1", 3, name="mine")
    theirs = made(tmp_path, "sha1", 3, nonce=OTHER_NONCE, name="theirs")
    assert mine.data != theirs.data
    mine.lock.write_bytes(theirs.data)
    assert lock_state(mine.git_dir, mine.binding) is Lock.FOREIGN
    assert lock_state(mine.git_dir, theirs.binding) is Lock.OWN


def test_an_empty_index_lock_is_foreign_and_survives_a_release_and_a_copy_drop(tmp_path):
    m = made(tmp_path, "sha1", 3)
    m.lock.write_bytes(b"")
    before = snap(m.lock)
    drop_copy(m.git_dir, m.op.nonce, m.data)             # no copy stands: nothing to do
    refused_and_untouched(m, before)
    assert snap(m.lock) == before


@for_every_format
def test_an_unmarked_lock_with_the_bytes_git_writes_for_an_empty_index_is_foreign_and_untouched(
        tmp_path, fmt):
    m = made(tmp_path, fmt, 0, tree=EMPTY_TREE[fmt])
    assert len(m.base) == EMPTY_BYTES[fmt] and m.base != m.data
    m.lock.write_bytes(m.base)
    refused_and_untouched(m, snap(m.lock))


@needs_git
@for_every_reader
@for_every_format
@for_both_modes
def test_the_bytes_the_readers_git_writes_for_an_empty_index_are_a_foreign_lock_and_stay_untouched(
        tmp_path, which, fmt, mode):
    box = scratch(tmp_path, which, fmt)
    tree = box.tree(MODES[mode])
    rows = len(MODES[mode])
    product = operation(box, tree, box.base(tree, rows), mode, rows, NONCE)
    owners = {"the base bytes the product builds, unmarked": product.base}
    owners.update(owners_own_bytes(box, mode))
    assert {sha256(data) for data in owners.values()}.isdisjoint({sha256(product.marked)})
    print(f"foreign-lock {which} {fmt} {mode}: "           # what the gate driver shows (-rP)
          + "; ".join(f"{what} {len(data)} bytes {sha256(data)[7:19]}"
                      for what, data in owners.items())
          + f"; the marked bytes {len(product.marked)} bytes {sha256(product.marked)[7:19]}")
    m = Made(box.git_dir, product.claim, an_op(), product.base, product.marked)
    m.lock.write_bytes(m.data)
    assert lock_state(m.git_dir, m.binding) is Lock.OWN        # the calibration: it can say yes
    for what, data in owners.items():
        m.lock.unlink()
        m.lock.write_bytes(data)
        try:
            refused_and_untouched(m, snap(m.lock))
        except AssertionError as error:
            raise AssertionError(f"{what}: {error}") from None


def owners_own_bytes(box, mode):
    """The index files the owner's own commands write for the same tree, each from no index at
    all; the folder is left with no index again. A command that writes none adds no candidate."""
    sequences = ({"read-tree --empty": [("read-tree", "--empty")],
                  "write-tree": [("write-tree",)]} if mode == "empty" else
                 {"add -A": [("add", "-A")],
                  "add -A, then write-tree": [("add", "-A"), ("write-tree",)]})
    index, found = box.git_dir / "index", {}
    for what, commands in sequences.items():
        index.unlink(missing_ok=True)
        for command in commands:
            box.run(*command)
        if index.exists():
            found[f"the owner's `git {what}`"] = index.read_bytes()
    index.unlink(missing_ok=True)
    assert found, "the owner's Git wrote no index at all: the witness would test nothing"
    return found


def test_a_lock_that_is_a_directory_is_foreign_and_never_entered(tmp_path):
    m = made(tmp_path, "sha1", 3)
    m.lock.mkdir()
    (m.lock / "kept").write_bytes(m.data)
    assert lock_state(m.git_dir, m.binding) is Lock.FOREIGN
    assert release_own_lock(m.git_dir, m.binding) is False
    assert install_index(m.git_dir, m.binding, m.data) is False
    with pytest.raises(NameTaken):
        take_lock(m.git_dir, m.binding.nonce, m.data)
    assert m.lock.is_dir() and (m.lock / "kept").read_bytes() == m.data


def test_a_lock_that_is_a_symbolic_link_to_the_right_bytes_is_foreign_and_never_followed(tmp_path):
    m = made(tmp_path, "sha1", 3)
    target = tmp_path / "elsewhere"
    target.write_bytes(m.data)
    try:
        os.symlink(target, m.lock)
    except (OSError, NotImplementedError):
        pytest.skip("this account cannot make symbolic links")
    assert lock_state(m.git_dir, m.binding) is Lock.FOREIGN
    assert release_own_lock(m.git_dir, m.binding) is False
    with pytest.raises(NameTaken):
        take_lock(m.git_dir, m.binding.nonce, m.data)
    assert m.lock.is_symlink() and target.read_bytes() == m.data


def test_take_lock_never_replaces_an_existing_lock(tmp_path, moves):
    m = made(tmp_path, "sha1", 3)
    m.lock.write_bytes(b"somebody's lock")
    before = snap(m.lock)
    with pytest.raises(NameTaken):
        take_lock(m.git_dir, m.binding.nonce, m.data)
    assert snap(m.lock) == before
    assert m.copy.read_bytes() == m.data                  # the caller drops the copy
    drop_copy(m.git_dir, m.binding.nonce, m.data)
    assert not m.copy.exists() and snap(m.lock) == before


def test_take_lock_moves_the_copy_and_the_lock_is_then_own(tmp_path, moves):
    m = made(tmp_path, "sha1", 3)
    ensure_copy(m.git_dir, m.binding.nonce, m.data)
    assert m.copy.read_bytes() == m.data and lock_state(m.git_dir, m.binding) is Lock.NONE
    take_lock(m.git_dir, m.binding.nonce, m.data)
    assert lock_state(m.git_dir, m.binding) is Lock.OWN
    assert not m.copy.exists() and m.lock.read_bytes() == m.data


def test_the_walk_take_then_install_leaves_the_installed_bytes_under_one_name(tmp_path, moves):
    m = made(tmp_path, "sha256", 3)
    take_lock(m.git_dir, m.binding.nonce, m.data)
    assert install_index(m.git_dir, m.binding, m.data) is True
    assert sorted(path.name for path in m.git_dir.iterdir()) == [INDEX]
    assert m.index.read_bytes() == m.data
    assert lock_state(m.git_dir, m.binding) is Lock.NONE


def test_release_never_removes_a_lock_whose_bytes_changed_after_the_proof(tmp_path, monkeypatch):
    m = made(tmp_path, "sha1", 3)
    m.lock.write_bytes(m.data)
    real = lock_module._bytes_of

    def swapped_after_the_proof(path, found):
        proof = real(path, found)
        path.write_bytes(b"x" * (len(m.data) + 7))        # other bytes, another size
        return proof

    monkeypatch.setattr(lock_module, "_bytes_of", swapped_after_the_proof)
    assert release_own_lock(m.git_dir, m.binding) is False
    assert m.lock.read_bytes() == b"x" * (len(m.data) + 7)


def test_bytes_are_read_only_from_the_file_that_was_looked_at(tmp_path):
    m = made(tmp_path, "sha1", 3)
    m.copy.write_bytes(m.data)
    m.lock.write_bytes(m.data)                            # the same size, another file
    looked_at = os.lstat(m.copy)
    assert lock_module._bytes_of(m.copy, looked_at) == m.data
    assert lock_module._bytes_of(m.lock, looked_at) is None


def test_a_file_that_grew_between_the_look_and_the_read_is_not_read(tmp_path):
    m = made(tmp_path, "sha1", 3)
    m.lock.write_bytes(m.data)
    looked_at = os.lstat(m.lock)
    with open(m.lock, "ab") as stream:
        stream.write(b"more")
    assert lock_module._bytes_of(m.lock, looked_at) is None


def test_a_copy_that_appeared_before_it_was_created_is_damage_and_is_not_overwritten(tmp_path):
    m = made(tmp_path, "sha1", 3)
    m.copy.write_bytes(b"another file's bytes")
    with pytest.raises(SetupRefused) as caught:
        lock_module._write_new(m.copy, m.data)
    assert caught.value.reason == "setup_damaged"
    assert m.copy.read_bytes() == b"another file's bytes"


def test_release_removes_the_own_lock_and_nothing_else(tmp_path, moves):
    m = made(tmp_path, "sha1", 3)
    m.lock.write_bytes(m.data)
    (m.git_dir / "HEAD").write_bytes(b"ref: refs/heads/main\n")
    assert release_own_lock(m.git_dir, m.binding) is True
    assert sorted(path.name for path in m.git_dir.iterdir()) == ["HEAD"]


STATES = [("C",), ("C", "L"), ("L",), ("L", "I"), ("C", "L", "I"), ("I",), ("C", "I")]


def one_inode(m, names):
    """One file under every name of `names` (C the copy, L the lock, I the index)."""
    paths = {"C": m.copy, "L": m.lock, "I": m.index}
    first, *rest = names
    paths[first].write_bytes(m.data)
    for name in rest:
        os.link(paths[first], paths[name])
    return paths


@pytest.mark.parametrize("alias", [False, True], ids=["no_foreign_name", "a_foreign_name"])
@pytest.mark.parametrize("names", STATES, ids=["".join(state) for state in STATES])
def test_an_own_lock_is_recognised_in_every_name_state_of_its_inode_and_a_foreign_name_spoils_it(
        tmp_path, by_link, names, alias):
    m = made(tmp_path, "sha1", 3)
    paths = one_inode(m, names)
    if alias:
        os.link(paths[names[0]], m.git_dir / "foreign-alias")
    expected = (Lock.FOREIGN if alias else Lock.OWN) if "L" in names else Lock.NONE
    assert lock_state(m.git_dir, m.binding) is expected
    before = {name: snap(path) for name, path in paths.items() if path.exists()}
    assert release_own_lock(m.git_dir, m.binding) is (expected is Lock.OWN)
    left = {name for name, path in paths.items() if path.exists()}
    assert left == set(names) - ({"L"} if expected is Lock.OWN else set())
    assert all(snap(paths[name]) == before[name] for name in left)


def test_a_crash_between_the_halves_of_taking_the_lock_leaves_an_own_lock_and_the_copy(
        tmp_path, by_link, monkeypatch):
    m = made(tmp_path, "sha1", 3)
    failing_first_unlink(monkeypatch)
    with pytest.raises(OSError):
        take_lock(m.git_dir, m.binding.nonce, m.data)
    assert m.copy.exists() and m.lock.exists()
    assert lock_state(m.git_dir, m.binding) is Lock.OWN
    assert release_own_lock(m.git_dir, m.binding) is True
    assert not m.lock.exists() and m.copy.read_bytes() == m.data


def test_a_crash_between_the_halves_of_the_install_leaves_an_own_lock_over_the_index(
        tmp_path, by_link, monkeypatch):
    m = made(tmp_path, "sha1", 3)
    take_lock(m.git_dir, m.binding.nonce, m.data)
    calls = failing_first_unlink(monkeypatch)
    with pytest.raises(OSError):
        install_index(m.git_dir, m.binding, m.data)
    assert calls == [LOCK]                                 # the copy was gone: only the lock failed
    assert m.index.read_bytes() == m.data and lock_state(m.git_dir, m.binding) is Lock.OWN
    with pytest.raises(NameTaken):
        install_index(m.git_dir, m.binding, m.data)        # the second try cannot replace the index
    assert release_own_lock(m.git_dir, m.binding) is True
    assert sorted(path.name for path in m.git_dir.iterdir()) == [INDEX]


def test_a_take_that_died_between_its_halves_goes_on_by_the_table_to_one_installed_index(
        tmp_path, by_link, monkeypatch):
    """The two-name states are rows of the one common table, not an exception beside it."""
    m = made(tmp_path, "sha1", 3)
    failing_first_unlink(monkeypatch)
    with pytest.raises(OSError):
        take_lock(m.git_dir, m.binding.nonce, m.data)             # the names {C, L} stand
    monkeypatch.setattr(lock_module, "_unlink", os.unlink)
    own = lock_state(m.git_dir, m.binding)
    assert next_action(PREPARED, Ref.ABSENT, own, Index.ABSENT) is Act.MARK_LOCKED
    assert next_action(REF_MOVED, Ref.AT_COMMIT, own, Index.ABSENT) is Act.INSTALL_INDEX
    assert install_index(m.git_dir, m.binding, m.data) is True
    assert sorted(path.name for path in m.git_dir.iterdir()) == [INDEX]


def test_an_install_that_died_between_its_halves_is_finished_by_the_table_with_one_release(
        tmp_path, by_link, monkeypatch):
    m = made(tmp_path, "sha1", 3)
    take_lock(m.git_dir, m.binding.nonce, m.data)
    failing_first_unlink(monkeypatch)
    with pytest.raises(OSError):
        install_index(m.git_dir, m.binding, m.data)               # the names {L, I} stand
    monkeypatch.setattr(lock_module, "_unlink", os.unlink)
    own = lock_state(m.git_dir, m.binding)
    # The index file holds the very bytes of the tree: the driver's read says it matches.
    assert next_action(REF_MOVED, Ref.AT_COMMIT, own, Index.MATCHES) is Act.RELEASE_LOCK
    assert release_own_lock(m.git_dir, m.binding) is True
    gone = lock_state(m.git_dir, m.binding)
    assert next_action(REF_MOVED, Ref.AT_COMMIT, gone, Index.MATCHES) is Act.FINISH
    assert sorted(path.name for path in m.git_dir.iterdir()) == [INDEX]


def test_a_copy_that_shares_its_inode_with_the_installed_index_is_dropped_by_name_only(
        tmp_path, by_link):
    m = made(tmp_path, "sha1", 3)
    paths = one_inode(m, ("I", "C"))
    index_before = snap(m.index)
    drop_copy(m.git_dir, m.binding.nonce, m.data)
    assert not paths["C"].exists() and snap(m.index) == index_before


def test_a_copy_that_shares_its_inode_with_the_lock_and_the_index_is_dropped_by_name_only(
        tmp_path, by_link):
    m = made(tmp_path, "sha1", 3)
    paths = one_inode(m, ("C", "L", "I"))
    kept = {"L": snap(m.lock), "I": snap(m.index)}
    drop_copy(m.git_dir, m.binding.nonce, m.data)
    assert not paths["C"].exists()
    assert {"L": snap(m.lock), "I": snap(m.index)} == kept
    assert lock_state(m.git_dir, m.binding) is Lock.OWN


def test_a_copy_that_is_a_second_name_of_some_other_file_is_not_dropped(tmp_path, by_link):
    m = made(tmp_path, "sha1", 3)
    paths = one_inode(m, ("C",))
    os.link(paths["C"], m.git_dir / "foreign-alias")
    drop_copy(m.git_dir, m.binding.nonce, m.data)
    assert m.copy.read_bytes() == m.data and (m.git_dir / "foreign-alias").exists()


def test_a_copy_with_other_bytes_is_not_dropped(tmp_path):
    m = made(tmp_path, "sha1", 3)
    m.copy.write_bytes(m.data[:-1] + b"?")
    drop_copy(m.git_dir, m.binding.nonce, m.data)
    assert m.copy.exists()


def attributes_with_their_function(tree):
    """Every `value.attribute` the code spells as (value, attribute, the function it stands in)."""
    found = []

    def visit(node, scope):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.Attribute):
                found.append((ast.unparse(child.value), child.attr, scope))
            visit(child, child.name if isinstance(child, ast.FunctionDef) else scope)

    visit(tree, "")
    return found


def test_the_module_replaces_no_name_and_renames_only_in_the_windows_move():
    tree = ast.parse(Path(lock_module.__file__).read_text(encoding="utf-8"))
    used = attributes_with_their_function(tree)
    assert not [use for use in used if use[1] in ("replace", "renames", "move", "system")]
    assert {(value, scope) for value, name, scope in used if name == "rename"} \
        == {("os", "_move_by_rename")}
    assert {(value, scope) for value, name, scope in used if name == "link"} \
        == {("os", "_move_by_link")}
    imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
                for alias in node.names}
    assert not imported & {"shutil", "subprocess", "tempfile"}, imported


@pytest.mark.parametrize("code", [errno.EPERM, errno.ENOTSUP, errno.EXDEV])
def test_a_link_the_file_system_refuses_is_a_refusal_that_moves_nothing_and_falls_back_to_nothing(
        tmp_path, by_link, monkeypatch, code):
    m = made(tmp_path, "sha1", 3)
    ensure_copy(m.git_dir, m.binding.nonce, m.data)

    def refuses(*_args, **_keywords):
        raise OSError(code, "the file system refuses")

    def forbidden(*_args, **_keywords):
        raise AssertionError("a replacing or renaming call was tried after the link failed")

    monkeypatch.setattr(os, "link", refuses)
    monkeypatch.setattr(os, "rename", forbidden)
    monkeypatch.setattr(os, "replace", forbidden)
    with pytest.raises(MoveRefused):
        take_lock(m.git_dir, m.binding.nonce, m.data)
    assert m.copy.exists() and not m.lock.exists()
    m.copy.unlink()
    m.lock.write_bytes(m.data)
    with pytest.raises(MoveRefused):
        install_index(m.git_dir, m.binding, m.data)
    assert m.lock.exists() and not m.index.exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows moves a name by one rename")
def test_the_windows_move_is_one_rename_and_never_makes_two_names(tmp_path, monkeypatch):
    m = made(tmp_path, "sha1", 3)

    def forbidden(*_args, **_keywords):
        raise AssertionError("a hard link was made on Windows")

    monkeypatch.setattr(os, "link", forbidden)
    take_lock(m.git_dir, m.binding.nonce, m.data)
    assert sorted(path.name for path in m.git_dir.iterdir()) == [LOCK]
    assert install_index(m.git_dir, m.binding, m.data) is True
    assert sorted(path.name for path in m.git_dir.iterdir()) == [INDEX]


@pytest.mark.skipif(os.name != "nt", reason="only Windows moves a name by a rename")
def test_a_rename_that_fails_for_another_reason_than_a_taken_name_is_a_refusal_not_a_taken_name(
        tmp_path, monkeypatch):
    m = made(tmp_path, "sha1", 3)
    ensure_copy(m.git_dir, m.binding.nonce, m.data)

    def busy(*_args, **_keywords):
        raise PermissionError(errno.EACCES, "the file is in use")

    monkeypatch.setattr(os, "rename", busy)
    with pytest.raises(MoveRefused):
        take_lock(m.git_dir, m.binding.nonce, m.data)
    assert m.copy.exists() and not m.lock.exists()


@pytest.mark.parametrize("kind", ["file", "directory"])
def test_install_never_replaces_an_index_that_appeared_under_the_lock(tmp_path, moves, kind):
    m = made(tmp_path, "sha1", 3)
    take_lock(m.git_dir, m.binding.nonce, m.data)
    if kind == "file":
        m.index.write_bytes(b"the owner's index")
    else:
        m.index.mkdir()
        (m.index / "kept").write_bytes(b"inside")
    before = snap(m.lock)
    with pytest.raises(NameTaken):
        install_index(m.git_dir, m.binding, m.data)
    assert snap(m.lock) == before
    if kind == "file":
        assert m.index.read_bytes() == b"the owner's index"
    else:
        assert (m.index / "kept").read_bytes() == b"inside"


def test_no_function_of_the_module_touches_an_index_that_is_not_the_products(tmp_path, moves):
    m = made(tmp_path, "sha1", 3)
    m.index.write_bytes(m.data)                            # equal bytes, another file: not ours
    before = snap(m.index)
    ensure_copy(m.git_dir, m.binding.nonce, m.data)
    take_lock(m.git_dir, m.binding.nonce, m.data)
    assert lock_state(m.git_dir, m.binding) is Lock.OWN
    drop_copy(m.git_dir, m.binding.nonce, m.data)
    with pytest.raises(NameTaken):
        install_index(m.git_dir, m.binding, m.data)
    assert release_own_lock(m.git_dir, m.binding) is True
    assert snap(m.index) == before


def test_dropping_the_copy_beside_a_foreign_lock_leaves_the_lock_byte_for_byte(tmp_path):
    m = made(tmp_path, "sha1", 3)
    m.lock.write_bytes(b"somebody's lock")
    before = snap(m.lock)
    with pytest.raises(NameTaken):
        take_lock(m.git_dir, m.binding.nonce, m.data)
    drop_copy(m.git_dir, m.binding.nonce, m.data)
    assert not m.copy.exists() and snap(m.lock) == before


def test_a_partial_copy_is_replaced_and_a_different_full_copy_is_damage(tmp_path):
    m = made(tmp_path, "sha1", 3)
    for held in (m.data[:len(m.data) // 2], b""):
        m.copy.write_bytes(held)
        ensure_copy(m.git_dir, m.binding.nonce, m.data)
        assert m.copy.read_bytes() == m.data
        m.copy.unlink()
    for held in (m.data[:-1] + b"?", m.data + b"?"):
        m.copy.write_bytes(held)
        with pytest.raises(SetupRefused) as caught:
            ensure_copy(m.git_dir, m.binding.nonce, m.data)
        assert caught.value.reason == "setup_damaged"
        assert m.copy.read_bytes() == held                 # never deleted
        m.copy.unlink()


def test_a_partial_copy_that_has_another_name_is_damage_and_is_not_removed(tmp_path, by_link):
    m = made(tmp_path, "sha1", 3)
    m.copy.write_bytes(m.data[:10])
    os.link(m.copy, m.git_dir / "foreign-alias")
    with pytest.raises(SetupRefused):
        ensure_copy(m.git_dir, m.binding.nonce, m.data)
    assert m.copy.read_bytes() == m.data[:10]


def test_a_copy_that_is_a_directory_is_damage_and_is_left_alone(tmp_path):
    m = made(tmp_path, "sha1", 3)
    m.copy.mkdir()
    with pytest.raises(SetupRefused) as caught:
        ensure_copy(m.git_dir, m.binding.nonce, m.data)
    assert caught.value.reason == "setup_damaged" and m.copy.is_dir()


def test_a_lock_name_whose_state_cannot_be_read_is_foreign_and_not_absent(tmp_path, monkeypatch):
    m = made(tmp_path, "sha1", 3)
    m.lock.write_bytes(m.data)
    real = os.lstat

    def unreadable(path, *args, **keywords):
        if Path(path).name == LOCK:
            raise PermissionError(errno.EACCES, "no access")
        return real(path, *args, **keywords)

    monkeypatch.setattr(os, "lstat", unreadable)
    assert lock_state(m.git_dir, m.binding) is Lock.FOREIGN
    assert release_own_lock(m.git_dir, m.binding) is False


def test_a_lock_larger_than_the_index_limit_is_foreign_and_is_never_opened(tmp_path, monkeypatch):
    m = made(tmp_path, "sha1", 3)
    m.lock.write_bytes(m.data)
    assert INDEX_LIMIT > len(m.data)
    monkeypatch.setattr(lock_module, "INDEX_LIMIT", len(m.data) - 1)

    def never(*_args, **_keywords):
        raise AssertionError("a file over the limit was opened")

    monkeypatch.setattr(lock_module, "open", never, raising=False)
    assert lock_state(m.git_dir, m.binding) is Lock.FOREIGN


def test_files_without_a_file_id_are_never_counted_as_one_file(tmp_path, monkeypatch):
    m = made(tmp_path, "sha1", 3)
    m.copy.write_bytes(m.data)
    m.lock.write_bytes(m.data)
    real = lock_module._look

    def without_ids(path):
        found = real(path)
        if isinstance(found, str):
            return found
        values = list(found)
        values[1] = 0                                      # st_ino
        return os.stat_result(values)

    monkeypatch.setattr(lock_module, "_look", without_ids)
    assert lock_module._shares(m.lock, without_ids(m.copy)) is False
