"""The other trees a child writes in are walked and removed past the classic path limit too.

The attempt folder is `test_long_path_attempt`. The same cause, a deep name given to the operating
system in its plain form, stood in four more places that a child's tree reaches: the attempt homes
of the harness workspace (`discard_home`, `sweep_homes`), the per-run names taken back from a
login directory (`login_home.measure`, `take_back`), the work tree read for the evidence of a task
(`work_seed`) and the relay home (`login_relay.discard`, `sweep`, `read_leaf`; `relay_home`'s
`leaf_kind`). Each is asked on a tree the test makes deeper than 260 characters, and the checks of
each (portal, second hard link, kind of entry) are asked on deep paths as well.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from conductor.command.adapters import login_home, login_relay
from conductor.command.adapters.harness_workspace import (
    HOME_LEAF_ABSENT, HOME_LEAF_EMPTY, HOME_LEAF_FILE, HOME_LEAF_OTHER, HarnessWorkspace,
    WorkspaceNotContained)
from conductor.command.adapters.relay_home import leaf_kind
from conductor.command.adapters.work_seed import CaptureRefused
from tests._deep_tree import (
    LEVELS, WIDTH, deep_tree, hard_link, junction, named, odd_name, plain, reads_as_another,
    remove, standing, without_long_paths)

DEEP = hashlib.sha256(b"deep").hexdigest()
ITEM = "work-001"


@pytest.fixture(autouse=True)
def tidy(tmp_path):
    """A failing test leaves a tree pytest cannot remove with a plain name: take it away."""
    yield
    remove(tmp_path)


def a_workspace(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    return HarnessWorkspace.at(root, home_dir=".one-home", marker_dir=".one-marker")


def a_target(tmp_path):
    """A folder outside every tree, which no removal may reach through a portal."""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "kept.txt").write_bytes(b"kept")
    return outside


# --- the attempt homes of the harness workspace -----------------------------------------------


def test_discard_home_removes_a_tree_deeper_than_the_limit(tmp_path):
    workspace = a_workspace(tmp_path)
    home = workspace.mint_home("attempt-1")
    deep_tree(home)

    workspace.discard_home(home)

    assert not standing(home), "the attempt home is still there"
    assert not standing(workspace.homes_root() / "attempt-1")


def test_a_machine_that_allows_long_names_gets_the_same_discard_of_a_home(tmp_path, monkeypatch):
    """The same removal where the system would answer "not found" to every plain deep name."""
    workspace = a_workspace(tmp_path)
    home = workspace.mint_home("attempt-1")
    deep_tree(home)
    without_long_paths(monkeypatch)

    workspace.discard_home(home)

    assert not standing(home), "the attempt home is still there"


def test_a_junction_deep_in_a_home_is_removed_as_itself_and_what_it_names_is_kept(tmp_path):
    workspace = a_workspace(tmp_path)
    home = workspace.mint_home("attempt-1")
    tree = deep_tree(home)
    outside = a_target(tmp_path)
    junction(os.path.join(tree.bottom, "door"), outside)

    workspace.discard_home(home)

    assert not standing(home)
    assert (outside / "kept.txt").read_bytes() == b"kept"


def test_a_second_name_deep_in_a_home_is_removed_as_a_name_and_the_bytes_stay_elsewhere(tmp_path):
    workspace = a_workspace(tmp_path)
    home = workspace.mint_home("attempt-1")
    tree = deep_tree(home)
    hard_link(tree.leaf, named(tmp_path / "alias.txt"))

    workspace.discard_home(home)

    assert not standing(home)
    assert (tmp_path / "alias.txt").read_bytes() == b"deep"


def test_sweep_homes_removes_the_deep_trees_of_every_home_a_crash_left(tmp_path):
    workspace = a_workspace(tmp_path)
    homes = [workspace.mint_home(name) for name in ("attempt-1", "attempt-2")]
    for home in homes:
        deep_tree(home)

    refused = workspace.sweep_homes()

    assert refused == ()
    assert [standing(home) for home in homes] == [False, False]


def test_a_home_that_is_a_file_is_still_named_and_left_by_the_sweep_beside_deep_ones(tmp_path):
    workspace = a_workspace(tmp_path)
    home = workspace.mint_home("attempt-1")
    deep_tree(home)
    (workspace.homes_root() / "not-a-home.txt").write_bytes(b"x")

    assert workspace.sweep_homes() == ("not-a-home.txt",)

    assert not standing(home) and (workspace.homes_root() / "not-a-home.txt").exists()


def made(path, data: bytes = b"") -> str:
    """A file (and the folders above it) at `path`, which is written as the system must read it."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as out:
        out.write(data)
    return path


def intact(path, data: bytes) -> bool:
    """Whether the file is still there with its bytes: a missing file is a False, not an error."""
    return os.path.isfile(path) and Path(path).read_bytes() == data


@reads_as_another
@pytest.mark.parametrize("how", ("discard_home", "sweep_homes"))
def test_a_junction_spelled_like_the_folder_beside_it_is_removed_as_itself_not_walked(
        tmp_path, how):
    """`foo ` is `foo` to a plain name: asked so, the junction passes for the folder it is beside
    and the removal goes through it, into what it names."""
    workspace = a_workspace(tmp_path)
    home = workspace.mint_home("attempt-1")
    inside = made(os.path.join(odd_name(home, "foo"), "inside.txt"), b"inside")
    outside = a_target(tmp_path)
    (outside / "sub").mkdir()
    (outside / "sub" / "kept2.txt").write_bytes(b"kept2")
    junction(odd_name(home, "foo "), outside)

    if how == "discard_home":
        workspace.discard_home(home)
    else:
        assert workspace.sweep_homes() == ()

    assert not standing(home), "the attempt home is still there"
    assert not os.path.lexists(inside)
    assert intact(outside / "kept.txt", b"kept"), "removed through the junction"
    assert intact(outside / "sub" / "kept2.txt", b"kept2"), "removed through the junction"


@reads_as_another
@pytest.mark.parametrize("name", ("...", ".. ", " ", "attempt-2.", "attempt-2 "))
def test_sweep_homes_goes_by_the_name_a_child_gave_a_folder_not_the_one_the_system_reads_it_as(
        tmp_path, name):
    """The sweep lists the homes root and asks about each name it was given. `...`, `.. ` and ` `
    are the root itself to a plain name: asked so, the folder of a child is the whole root, and the
    sweep takes it away with what it was to name and leave (a note, a junction), saying nothing.
    `attempt-2.` is `attempt-2`, which is not there: asked so, the folder is passed over."""
    workspace = a_workspace(tmp_path)
    home = workspace.mint_home("attempt-1")
    homes = workspace.homes_root()
    note = made(str(homes / "not-a-home.txt"), b"x")
    outside = a_target(tmp_path)
    junction(odd_name(homes, "door"), outside)
    odd = made(os.path.join(odd_name(homes, name), "spawn.txt"), b"child")

    refused = workspace.sweep_homes()

    assert refused == ("door", "not-a-home.txt"), f"what is not a home was named as {refused}"
    assert intact(note, b"x"), "a name the sweep leaves was taken away"
    assert os.path.lexists(odd_name(homes, "door")), "a junction the sweep leaves was taken away"
    assert intact(outside / "kept.txt", b"kept"), "removed through the junction"
    assert not os.path.lexists(os.path.dirname(odd)), "the folder the child made is still there"
    assert not os.path.lexists(odd_name(homes, "attempt-1")), "the home is still there"


@reads_as_another
@pytest.mark.parametrize("mark", (" ", "."))
def test_sweep_homes_names_a_junction_spelled_like_a_home_beside_it_and_follows_it_nowhere(
        tmp_path, mark):
    """`attempt-1 ` and `attempt-1.` are `attempt-1` to a plain name: asked so, the junction is
    not seen as a portal at all, and is neither named nor left as a portal is."""
    workspace = a_workspace(tmp_path)
    workspace.mint_home("attempt-1")
    homes = workspace.homes_root()
    outside = a_target(tmp_path)
    junction(odd_name(homes, "attempt-1" + mark), outside)

    refused = workspace.sweep_homes()

    assert refused == ("attempt-1" + mark,), f"a portal in the homes root was named as {refused}"
    assert os.path.lexists(odd_name(homes, "attempt-1" + mark)), "the junction was taken away"
    assert not os.path.lexists(odd_name(homes, "attempt-1")), "the home is still there"
    assert intact(outside / "kept.txt", b"kept"), "removed through the junction"


# --- names taken back from a login directory --------------------------------------------------


def a_login_home(tmp_path):
    home = tmp_path / "login"
    (home / "sessions").mkdir(parents=True)
    (home / "config.json").write_bytes(b"{}")
    return home


def test_a_deep_session_a_spawn_wrote_is_measured_and_taken_back(tmp_path):
    home = a_login_home(tmp_path)
    before = login_home.measure(str(home), ("sessions",))
    tree = deep_tree(home / "sessions" / "p1")

    after = login_home.measure(str(home), ("sessions",))
    added = login_home.appeared(before, after)
    left = login_home.take_back(str(home), ("sessions",), added)

    deepest = os.path.relpath(plain(tree.leaf), plain(home)).replace("\\", "/")
    assert after is not None and deepest in after, "the measurement lost the deep names"
    assert left == (), f"names left standing: {left}"
    assert not standing(home / "sessions" / "p1")
    assert (home / "config.json").read_bytes() == b"{}" and (home / "sessions").is_dir()


def test_a_file_a_spawn_added_to_a_deep_folder_that_was_there_is_taken_back(tmp_path):
    home = a_login_home(tmp_path)
    tree = deep_tree(home / "sessions" / "p1")
    before = login_home.measure(str(home), ("sessions",))
    added_file = os.path.join(tree.bottom, "new.txt")
    Path(added_file).write_bytes(b"new")

    after = login_home.measure(str(home), ("sessions",))
    added = login_home.appeared(before, after)
    left = login_home.take_back(str(home), ("sessions",), added)

    assert added is not None and len(added) == 1, f"one name appeared, not {added}"
    assert left == () and not standing(added_file), "the new deep file is still there"
    assert standing(tree.leaf), "a file that was there before the spawn was taken back"


@reads_as_another
@pytest.mark.parametrize(("spawned", "operators"), (
    ("a ", "a"), ("a.", "a"), ("...", "other")))
def test_taking_back_a_name_the_spawn_made_never_takes_the_operators_the_system_reads_it_as(
        tmp_path, spawned, operators):
    """`a ` and `a.` are `a`, and `...` is the folder it stands in: removed by the plain name,
    the operator's own files go and the spawn's stay, and the call still says it left nothing."""
    home = a_login_home(tmp_path)
    kept = made(str(home / "sessions" / operators / "operator.txt"), b"operator")
    before = login_home.measure(str(home), ("sessions",))
    mine = made(os.path.join(odd_name(home / "sessions", spawned), "spawn.txt"), b"spawn")

    after = login_home.measure(str(home), ("sessions",))
    added = login_home.appeared(before, after)
    left = login_home.take_back(str(home), ("sessions",), added)

    assert added == {f"sessions/{spawned}", f"sessions/{spawned}/spawn.txt"}, added
    assert intact(kept, b"operator"), "the operator's file was taken back"
    assert not os.path.lexists(mine) and left == (), f"names left standing: {left}"


@reads_as_another
def test_a_junction_spelled_like_a_folder_beside_it_makes_the_measurement_unknown(tmp_path):
    """`foo ` is `foo` to a plain name: asked so, the door passes for the folder it is beside, and
    the measurement would go through it and count what is outside as the spawn's."""
    home = a_login_home(tmp_path)
    made(os.path.join(odd_name(home / "sessions", "foo"), "inside.txt"), b"inside")
    assert login_home.measure(str(home), ("sessions",)) is not None, "the folder alone is unknown"

    junction(odd_name(home / "sessions", "foo "), a_target(tmp_path))

    assert login_home.measure(str(home), ("sessions",)) is None


def test_a_junction_deep_under_a_declared_directory_makes_the_measurement_unknown(tmp_path):
    """The tree alone is measured; the junction in it is a door, and a door is unknown."""
    home = a_login_home(tmp_path)
    tree = deep_tree(home / "sessions" / "p1")
    assert login_home.measure(str(home), ("sessions",)) is not None, "the deep tree is unknown"

    junction(os.path.join(tree.bottom, "door"), a_target(tmp_path))

    assert login_home.measure(str(home), ("sessions",)) is None


# --- the work tree read for the evidence ------------------------------------------------------


def a_work_item(tmp_path):
    workspace = a_workspace(tmp_path)
    work = workspace.work_dir(ITEM)
    return workspace, work, deep_tree(work)


def keys_of(tree, base) -> dict:
    """The key a file has among the work tree's: its path from `base`, with forward slashes."""
    return {plain(path): os.path.relpath(plain(path), plain(base)).replace("\\", "/")
            for path in tree.files}


def test_the_digest_of_the_work_tree_holds_every_file_of_a_deep_tree(tmp_path):
    workspace, _work, tree = a_work_item(tmp_path)

    digests = workspace.digest_work_tree()

    expected = {key: DEEP for key in keys_of(tree, workspace.root / "work").values()}
    assert digests == expected


def test_a_deep_work_item_is_listed_and_its_changed_file_read_whole(tmp_path):
    workspace, _work, tree = a_work_item(tmp_path)
    keys = keys_of(tree, workspace.root / "work")
    changed = keys[plain(tree.leaf)]

    listing, contents = workspace.read_work_tree(ITEM, (changed,))

    assert listing == {key: DEEP for key in keys.values()}
    assert contents == {changed: b"deep"}


def test_a_deep_work_item_is_captured_with_its_bytes_and_its_modes(tmp_path):
    workspace, work, tree = a_work_item(tmp_path)
    keys = keys_of(tree, work)

    captured = workspace.capture_work_tree(ITEM)
    modes = workspace.work_modes(ITEM)

    assert {key: data for key, (_mode, data) in captured.items()} == dict.fromkeys(
        keys.values(), b"deep")
    assert modes == dict.fromkeys(keys.values(), False)


def reported() -> str:
    """A deleted file as the result reports it: its path from the work tree, forward slashes."""
    return f"{ITEM}/" + "/".join(["d" * WIDTH] * LEVELS) + "/log.txt"


def test_a_reported_deletion_that_still_has_a_deep_file_is_refused(tmp_path):
    workspace, _work, tree = a_work_item(tmp_path)
    assert reported().replace("/", os.sep) in plain(tree.leaf), "the reported path is not it"

    with pytest.raises(WorkspaceNotContained, match="still has a file"):
        workspace.absent_result_paths((reported(),))


def test_a_reported_deletion_of_a_deep_file_that_is_gone_is_accepted(tmp_path):
    workspace, _work, tree = a_work_item(tmp_path)
    os.unlink(tree.leaf)

    assert workspace.absent_result_paths((reported(),)) == (reported(),)


def test_a_deep_junction_is_recorded_by_kind_in_the_evidence_and_never_walked(tmp_path):
    workspace, work, tree = a_work_item(tmp_path)
    outside = a_target(tmp_path)
    door = os.path.join(tree.bottom, "door")
    junction(door, outside)
    key = os.path.relpath(plain(door), plain(workspace.root / "work")).replace("\\", "/")

    digests = workspace.digest_work_tree()
    listing, _contents = workspace.read_work_tree(ITEM, ())

    portal = ("junction", "symlink")  # a symbolic link where the system has no junctions
    assert digests[key] in portal and listing[key] in portal
    assert not any("kept.txt" in name for name in digests), "the walk went through the junction"
    with pytest.raises(CaptureRefused, match="irregular_result"):
        workspace.capture_work_tree(ITEM)
    assert (outside / "kept.txt").read_bytes() == b"kept"


def test_a_second_name_deep_in_the_work_tree_is_recorded_as_one_and_not_read(tmp_path):
    workspace, work, tree = a_work_item(tmp_path)
    hard_link(tree.leaf, named(tmp_path / "alias.txt"))
    key = os.path.relpath(plain(tree.leaf), plain(workspace.root / "work")).replace("\\", "/")

    assert workspace.digest_work_tree()[key] == "hard_link"
    with pytest.raises(CaptureRefused, match="irregular_result"):
        workspace.capture_work_tree(ITEM)


def test_a_machine_that_allows_long_names_gets_the_same_digest_of_a_deep_work_tree(
        tmp_path, monkeypatch):
    workspace, _work, tree = a_work_item(tmp_path)
    without_long_paths(monkeypatch)

    digests = workspace.digest_work_tree()

    assert digests == {key: DEEP for key in keys_of(tree, workspace.root / "work").values()}


@reads_as_another
def test_a_junction_spelled_like_the_folder_beside_it_is_recorded_as_a_door_in_every_walk(
        tmp_path):
    """`foo ` is `foo` to a plain name: asked so, the junction passes for the folder it is beside,
    and the evidence holds what is outside the work tree as if the task had written it."""
    workspace = a_workspace(tmp_path)
    work = workspace.work_dir(ITEM)
    made(os.path.join(odd_name(work, "foo"), "inside.txt"), b"inside")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_bytes(b"OUTSIDE-SECRET")
    junction(odd_name(work, "foo "), outside)
    door, secret = f"{ITEM}/foo ", f"{ITEM}/foo /secret.txt"
    portal = ("junction", "symlink")  # a symbolic link where the system has no junctions

    digests = workspace.digest_work_tree()
    listing, contents = workspace.read_work_tree(ITEM, (secret,))

    assert digests[door] in portal and listing[door] in portal
    assert secret not in digests and secret not in listing, "the walk went through the junction"
    assert contents == {}, "the bytes outside the work tree were read as the task's"
    for walk in (workspace.capture_work_tree, workspace.work_modes):
        with pytest.raises(CaptureRefused, match="irregular_result"):
            walk(ITEM)


# --- the relay home ---------------------------------------------------------------------------

KEY = "0123456789abcdef"
HEX = "fedcba9876543210"


def test_sweep_removes_a_leftover_relay_home_with_a_deep_tree(tmp_path):
    relay = tmp_path / "DecemberCommand" / "relay"
    home = relay / KEY / f"c-{HEX}"
    home.mkdir(parents=True)
    (home / ".credentials.json").write_bytes(b"{}")
    deep_tree(home)

    assert login_relay.sweep(relay, KEY, "c", (".credentials.json",)) == []

    assert not standing(home)


def test_sweep_reaches_a_relay_folder_that_is_itself_past_the_limit(tmp_path):
    relay = Path(plain(deep_tree(tmp_path / "top").bottom)) / "DecemberCommand" / "relay"
    home = relay / KEY / f"c-{HEX}"
    os.makedirs(named(home))
    Path(named(home / ".credentials.json")).write_bytes(b"{}")
    assert len(plain(home)) > 260, "the relay folder is not past the limit"

    assert login_relay.sweep(relay, KEY, "c", (".credentials.json",)) == []

    assert not standing(home) and standing(relay / KEY), "the home is there, or the key is not"


def test_discard_removes_a_deep_junction_as_itself_and_keeps_what_it_names(tmp_path):
    home = tmp_path / "relay-home"
    home.mkdir()
    tree = deep_tree(home)
    outside = a_target(tmp_path)
    junction(os.path.join(tree.bottom, "door"), outside)

    assert login_relay.discard(home) is True

    assert not standing(home) and (outside / "kept.txt").read_bytes() == b"kept"


def a_deep_leaf(tmp_path, content: bytes):
    """A file at a path past the classic limit, and the plain spelling a caller has of it."""
    tree = deep_tree(tmp_path / "home")
    leaf = os.path.join(os.path.dirname(tree.leaf), "leaf.json")
    Path(leaf).write_bytes(content)
    return tree, plain(leaf)


def test_a_credential_file_at_a_deep_path_is_read_not_called_absent(tmp_path):
    _tree, leaf = a_deep_leaf(tmp_path, b'{"token": "x"}')

    found = login_relay.read_leaf(leaf)

    assert isinstance(found, login_relay.Leaf), found
    assert found.doc == {"token": "x"}
    assert found.digest == hashlib.sha256(b'{"token": "x"}').hexdigest()


def test_a_deep_credential_file_with_a_second_name_is_still_unsafe(tmp_path):
    tree, leaf = a_deep_leaf(tmp_path, b"{}")
    hard_link(named(leaf), named(tmp_path / "alias.json"))

    assert login_relay.read_leaf(leaf) == login_relay.Refused("leaf_unsafe")


def test_a_name_that_is_not_there_is_absent_at_a_deep_path_too(tmp_path):
    tree, _leaf = a_deep_leaf(tmp_path, b"{}")

    assert login_relay.read_leaf(plain(os.path.join(tree.bottom, "nothing.json"))) == (
        login_relay.Refused("leaf_absent"))


def test_the_kind_of_a_leaf_of_a_deep_relay_home_is_told_from_lstat_alone(tmp_path):
    tree = deep_tree(tmp_path / "home")
    home = plain(tree.bottom)
    Path(os.path.join(tree.bottom, "full.json")).write_bytes(b"{}")
    Path(os.path.join(tree.bottom, "empty.json")).write_bytes(b"")
    hard_link(os.path.join(tree.bottom, "full.json"), named(tmp_path / "alias.json"))
    os.mkdir(os.path.join(tree.bottom, "folder"))

    kinds = {name: leaf_kind(home, name)
             for name in ("full.json", "empty.json", "missing.json", "folder", "log.txt")}

    assert kinds == {"full.json": HOME_LEAF_OTHER, "empty.json": HOME_LEAF_EMPTY,
                     "missing.json": HOME_LEAF_ABSENT, "folder": HOME_LEAF_OTHER,
                     "log.txt": HOME_LEAF_FILE}
