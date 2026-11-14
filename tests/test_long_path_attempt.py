"""An attempt folder holding a tree deeper than the classic path limit is still cleaned up.

The first real attempt of cycle B (Claude Code 2.1.239) wrote its session files under its TEMP,
inside the attempt's `runtime` folder, 336 characters deep. The cleanup at the exit of the boundary
(`process_acl._empty_owned`) listed the tree with the plain name, the operating system answered
"not found", and the product refused the whole attempt as "owned attempt is unreadable" after the
child had finished. The cause is the name given to the operating system, so the fix is the name
(the extended-length form), and every check the cleanup makes stays exactly as it was: the portal,
the second hard link, the bound and the "changed during cleanup" test are asked on deep paths too.

The tests make the deep tree themselves (`tests/_deep_tree.py`), which proves the removal on a
machine where a plain long name does not work (Windows with `LongPathsEnabled` = 0, as measured).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from conductor.command.adapters import process_acl
from conductor.command.adapters.process_acl import AttemptAclJournal
from conductor.command.adapters.process_profile import ProfileRefused
from tests._boot_world import counter, later_boot, measure
from tests._deep_tree import (
    deep_tree, hard_link, junction, named, odd_name, plain, reads_as_another, remove, standing,
    without_long_paths)
from tests._prepared_world import LEGACY_SAME_MACHINE, read, rewrite
from tests.test_process_acl import fixture

NOW = counter(42)
KEYS = ("runtime", "work", "login")


@pytest.fixture(autouse=True)
def tidy(tmp_path):
    """A failing test leaves a tree pytest cannot remove with a plain name: take it away."""
    yield
    remove(tmp_path)


def an_attempt(tmp_path, *, folders=False):
    store, acl, profile_path, sid, state = fixture(tmp_path)
    record, paths = acl.prepare(profile_path, sid, "dispatch", folders=folders)
    return store, acl, record, paths, state


@pytest.mark.parametrize("key", KEYS)
def test_a_tree_deeper_than_the_limit_goes_with_the_attempt_folder_it_was_made_in(
        tmp_path, key):
    _store, acl, record, paths, _state = an_attempt(tmp_path)
    deep_tree(paths[key])

    acl.retire(record, proven=True)

    assert not standing(paths["parent"]), "the attempt folder is still there"
    assert read(record)["phase"] == "retired"


def test_a_machine_that_allows_long_names_gets_the_same_attempt_cleanup(tmp_path, monkeypatch):
    """The same removal where the system would answer "not found" to every plain deep name."""
    _store, acl, record, paths, _state = an_attempt(tmp_path)
    deep_tree(paths["runtime"])
    without_long_paths(monkeypatch)

    acl.retire(record, proven=True)

    assert not standing(paths["parent"]), "the attempt folder is still there"
    assert read(record)["phase"] == "retired"


def test_the_walk_names_every_entry_of_a_deep_tree_and_the_folder_it_began_at(tmp_path):
    _store, _acl, _record, paths, _state = an_attempt(tmp_path)
    tree = deep_tree(paths["runtime"])

    found = process_acl._walk_plain(paths["runtime"])

    assert {plain(path) for path in found} == (
        {plain(paths["runtime"])} | {plain(item) for item in tree.folders}
        | {plain(item) for item in tree.files}
        | {plain(os.path.dirname(tree.files[1]))}), "the walk missed an entry or made one up"
    assert found[0] == paths["runtime"], "the folder the walk began at is its first entry"


def test_a_restart_the_counter_proves_recovers_an_attempt_with_a_deep_tree(
        tmp_path, monkeypatch):
    """`conduct ownership recover-containers` is this `recover`, over the journal."""
    measure(monkeypatch, NOW)
    store, acl, record, paths, _state = an_attempt(tmp_path, folders=True)
    deep_tree(paths["runtime"])
    again = AttemptAclJournal(store, store.native, hold_factory=acl.hold_factory)
    measure(monkeypatch, later_boot(NOW))

    again.recover()

    assert not standing(paths["parent"]), "the attempt folder is still there"
    assert read(record)["phase"] == "retired"


def an_old_leftover(tmp_path, monkeypatch):
    """The attempt of the first B: a record from before the boot counter, its tree deep."""
    measure(monkeypatch, NOW)
    store, acl, record, paths, _state = an_attempt(tmp_path, folders=True)
    rewrite(record, lambda row: row.update(schema=1, boot=LEGACY_SAME_MACHINE))
    tree = deep_tree(paths["runtime"])
    journal = AttemptAclJournal(store, store.native, hold_factory=acl.hold_factory)
    return journal, record, paths, tree


def refused_until_proven(journal, record, monkeypatch, untouched):
    """Every proof the recovery stands on, one by one, ending with the boot that follows the
    preparation: not in the boot the record was met in, not after a restart until the record is
    prepared, not after the preparation until a restart follows it."""
    for boot in (NOW, later_boot(NOW)):  # its own boot; a restart, but the record is unprepared
        measure(monkeypatch, boot)
        with pytest.raises(ProfileRefused, match="profile_acl_unproven"):
            journal.recover()
        assert untouched(), f"the recovery cleaned up on {boot}"
    measure(monkeypatch, counter(43))
    journal.prepare_restart(record)
    with pytest.raises(ProfileRefused, match="profile_acl_unproven"):  # prepared, no restart since
        journal.recover()
    assert untouched()
    measure(monkeypatch, counter(44))


def test_a_leftover_of_the_old_format_with_a_deep_tree_is_recovered_only_on_the_proofs(
        tmp_path, monkeypatch):
    """Only after every proof the deep attempt folder is removed, and the record is retired."""
    journal, record, paths, tree = an_old_leftover(tmp_path, monkeypatch)

    def untouched() -> bool:
        return all(standing(item) for item in tree.files) and read(record)["phase"] == "applied"

    refused_until_proven(journal, record, monkeypatch, untouched)
    journal.recover()

    assert not standing(paths["parent"]), "the attempt folder is still there"
    assert read(record)["phase"] == "retired"


def an_irregular_entry(how, tree, outside):
    """A deep entry the cleanup must refuse: a second name for a file, or a junction."""
    if how == "hard link":
        hard_link(tree.leaf, named(outside / "alias.txt"))
    else:
        junction(os.path.join(tree.bottom, "door"), outside)


@pytest.mark.parametrize("how", ("hard link", "junction"))
def test_a_deep_portal_or_second_name_still_refuses_the_cleanup_and_touches_nothing(
        tmp_path, how):
    _store, acl, record, paths, state = an_attempt(tmp_path)
    tree = deep_tree(paths["runtime"])
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "kept.txt").write_bytes(b"kept")
    an_irregular_entry(how, tree, outside)
    before = dict(state)

    with pytest.raises(ProfileRefused, match="portal or irregular entry"):
        acl.retire(record, proven=True)

    assert all(standing(item) for item in tree.files), "the cleanup removed a file it refused over"
    assert (outside / "kept.txt").read_bytes() == b"kept"
    assert state == before, "an ACL was restored over a tree that was refused"
    assert read(record)["phase"] != "retired"


def test_a_folder_that_is_not_the_one_the_record_names_is_refused_with_its_deep_tree_untouched(
        tmp_path):
    """The identity of the four owned folders is asked before anything below them is looked at."""
    _store, acl, record, paths, state = an_attempt(tmp_path)
    tree = deep_tree(paths["runtime"])
    moved = tmp_path / "runtime-moved"
    os.rename(paths["runtime"], moved)
    paths["runtime"].mkdir()  # another folder under the same name
    kept = os.path.join(plain(moved), os.path.relpath(plain(tree.leaf), plain(paths["runtime"])))
    before = dict(state)

    with pytest.raises(ProfileRefused, match="owned attempt path identity changed"):
        acl.retire(record, proven=True)

    assert standing(kept), "the tree of the folder that was moved away was touched"
    assert state == before and read(record)["phase"] != "retired"


@pytest.mark.parametrize("how", ("second name", "junction"))
def test_a_deep_entry_that_changes_during_the_cleanup_is_refused_not_removed(
        tmp_path, monkeypatch, how):
    """The walk saw an ordinary file; before the removal it has a second name, or is a door."""
    _store, acl, record, paths, _state = an_attempt(tmp_path)
    tree = deep_tree(paths["runtime"])
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "kept.txt").write_bytes(b"kept")
    real = process_acl._walk_plain

    def walk_then_change(directory):
        found = real(directory)
        if directory == paths["runtime"] and how == "second name":
            hard_link(tree.leaf, named(tmp_path / "late-alias.txt"))
        elif directory == paths["runtime"]:
            os.unlink(tree.leaf)
            junction(tree.leaf, outside)
        return found

    monkeypatch.setattr(process_acl, "_walk_plain", walk_then_change)

    with pytest.raises(ProfileRefused, match="changed during cleanup"):
        acl.retire(record, proven=True)

    assert standing(tree.leaf)
    assert (outside / "kept.txt").read_bytes() == b"kept"
    if how == "second name":
        assert Path(named(tmp_path / "late-alias.txt")).read_bytes() == b"deep"


def entries_of(tree) -> int:
    """What the walk of a four-folder attempt meets: the four folders, the deep tree's folders
    and its side folder, and its three files."""
    return 4 + len(tree.folders) + 1 + len(tree.files)


def test_the_bound_on_the_entries_of_a_cleanup_is_reached_only_deep_in_the_tree(
        tmp_path, monkeypatch):
    """One entry fewer than the tree holds: the last entry the walk meets is a deep one."""
    _store, acl, record, paths, _state = an_attempt(tmp_path)
    tree = deep_tree(paths["runtime"])
    monkeypatch.setattr(process_acl, "_LIMIT", entries_of(tree) - 1)

    with pytest.raises(ProfileRefused, match="exceeds cleanup bound"):
        acl.retire(record, proven=True)

    assert all(standing(item) for item in tree.files)


def test_the_bound_stops_the_reading_of_a_wide_deep_folder_and_does_not_wait_for_its_end(
        tmp_path, monkeypatch):
    _store, acl, record, paths, _state = an_attempt(tmp_path)
    tree = deep_tree(paths["runtime"])
    for number in range(40):
        Path(os.path.join(tree.bottom, f"wide-{number}.dat")).write_bytes(b"x")
    looked_at, real = [], os.lstat

    def lstat(path, *args, **kwargs):
        looked_at.append(os.fspath(path))
        return real(path, *args, **kwargs)

    monkeypatch.setattr(process_acl.os, "lstat", lstat)
    monkeypatch.setattr(process_acl, "_LIMIT", 25)

    with pytest.raises(ProfileRefused, match="exceeds cleanup bound"):
        acl.retire(record, proven=True)

    wide = [path for path in looked_at if path.endswith(".dat")]
    assert 0 < len(wide) <= 25, f"{len(wide)} of 40 entries of the folder were looked at"


def test_the_bound_counts_the_folder_the_walk_begins_at(tmp_path, monkeypatch):
    _store, _acl, _record, paths, _state = an_attempt(tmp_path)
    monkeypatch.setattr(process_acl, "_LIMIT", 0)
    with pytest.raises(ProfileRefused, match="exceeds cleanup bound"):
        process_acl._walk_plain(paths["login"])  # a fresh folder: nothing in it but itself

    monkeypatch.setattr(process_acl, "_LIMIT", 1)

    assert process_acl._walk_plain(paths["login"]) == [paths["login"]]


def test_a_cleanup_whose_bound_is_exactly_the_deep_tree_goes_through(tmp_path, monkeypatch):
    _store, acl, record, paths, _state = an_attempt(tmp_path)
    tree = deep_tree(paths["runtime"])
    monkeypatch.setattr(process_acl, "_LIMIT", entries_of(tree))

    acl.retire(record, proven=True)

    assert not standing(paths["parent"]) and read(record)["phase"] == "retired"


def test_a_folder_the_system_will_not_list_refuses_the_cleanup_and_leaves_everything(
        tmp_path, monkeypatch):
    """The refusal itself: no entry is passed over, and nothing is removed before it is known."""
    _store, acl, record, paths, state = an_attempt(tmp_path)
    tree = deep_tree(paths["runtime"])
    real = os.scandir

    def scandir(path="."):
        if plain(path) == plain(tree.bottom):
            raise PermissionError(5, "Access is denied", os.fspath(path))
        return real(path)

    monkeypatch.setattr(process_acl.os, "scandir", scandir)
    before = dict(state)

    with pytest.raises(ProfileRefused, match="owned attempt is unreadable"):
        acl.retire(record, proven=True)

    assert all(standing(item) for item in tree.files), "the cleanup removed what it could not read"
    assert state == before and read(record)["phase"] != "retired"


# --- a name the system reads as another one ---------------------------------------------------

ODD = (("...", None), ("foo.", "foo"), ("foo ", "foo"))


def an_odd_folder(parent, name, neighbour):
    """The folder a child made under the name `name` (with a file in it) and the folder, with its
    own file, whose name the system takes `name` for; every path made, as it is written."""
    made = []
    for folder, data in ((name, b"odd"), (neighbour, b"plain")):
        if folder is None:
            continue
        top = odd_name(parent, folder)
        os.makedirs(top)
        made += [top, os.path.join(top, "inside.txt")]
        with open(made[-1], "wb") as out:
            out.write(data)
    return made


@reads_as_another
@pytest.mark.parametrize(("name", "neighbour"), ODD)
def test_the_cleanup_goes_by_the_name_a_child_gave_a_folder_not_the_one_the_system_reads_it_as(
        tmp_path, name, neighbour):
    """`...` read plainly is the folder above (a walk that never ends), `foo.` and `foo ` are
    `foo` (listed twice, and the folder of that name never listed)."""
    _store, acl, record, paths, _state = an_attempt(tmp_path)
    made = an_odd_folder(paths["runtime"], name, neighbour)

    acl.retire(record, proven=True)

    assert not any(os.path.lexists(item) for item in made), "a file the child made is still there"
    assert not standing(paths["parent"]), "the attempt folder is still there"
    assert read(record)["phase"] == "retired"


@reads_as_another
def test_a_junction_spelled_like_a_folder_beside_it_is_a_door_and_the_cleanup_stops(tmp_path):
    """`foo ` is `foo` to a plain name: asked so, the door passes for the folder it is beside."""
    _store, acl, record, paths, state = an_attempt(tmp_path)
    made = an_odd_folder(paths["runtime"], "foo", None)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "kept.txt").write_bytes(b"kept")
    junction(odd_name(paths["runtime"], "foo "), outside)
    before = dict(state)

    with pytest.raises(ProfileRefused, match="portal or irregular entry"):
        acl.retire(record, proven=True)

    assert (outside / "kept.txt").is_file(), "the cleanup went through the junction"
    assert all(os.path.lexists(item) for item in made), "the cleanup removed what it refused over"
    assert state == before and read(record)["phase"] != "retired"


@reads_as_another
def test_names_read_as_others_deep_in_an_old_leftover_go_as_they_stand_and_only_after_the_proofs(
        tmp_path, monkeypatch):
    """The recovery of the first B's kind of attempt, with a deep tree that also holds the names a
    plain call reads as other entries: nothing goes before the proofs, then each as it stands."""
    journal, record, paths, tree = an_old_leftover(tmp_path, monkeypatch)
    made = [item for name in ("...", ".. ", "foo.", " ", "foo")
            for item in an_odd_folder(tree.bottom, name, None)]

    def untouched() -> bool:
        return (all(standing(item) for item in tree.files)
                and all(os.path.lexists(item) for item in made)
                and read(record)["phase"] == "applied")

    refused_until_proven(journal, record, monkeypatch, untouched)
    journal.recover()

    assert not any(os.path.lexists(item) for item in made), "a name the child made is still there"
    assert not standing(paths["parent"]), "the attempt folder is still there"
    assert read(record)["phase"] == "retired"


@reads_as_another
def test_a_junction_spelled_like_a_folder_beside_it_in_an_old_leftover_still_refuses_the_recovery(
        tmp_path, monkeypatch):
    """The proofs hold and the cleanup may begin: a door that passes for its neighbour stops it."""
    journal, record, _paths, tree = an_old_leftover(tmp_path, monkeypatch)
    made = an_odd_folder(tree.bottom, "foo", None)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "kept.txt").write_bytes(b"kept")
    junction(odd_name(tree.bottom, "foo "), outside)

    def untouched() -> bool:
        return (all(standing(item) for item in tree.files)
                and all(os.path.lexists(item) for item in made)
                and read(record)["phase"] == "applied")

    refused_until_proven(journal, record, monkeypatch, untouched)
    with pytest.raises(ProfileRefused, match="portal or irregular entry"):
        journal.recover()

    assert untouched(), "the refused cleanup removed something"
    assert (outside / "kept.txt").read_bytes() == b"kept", "the cleanup went through the junction"
