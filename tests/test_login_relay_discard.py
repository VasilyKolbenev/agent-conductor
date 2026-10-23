"""`discard` and `sweep`: taking a relay home away, and the leftovers of an earlier attempt.

An attempt's relay home is removed by the product however the attempt ended, and the credential in
it goes first: a tree that cannot be removed (a file the child still holds) must leave no
credential behind. A link, a junction or a path past the classic limit that a child made inside the
relay home is removed as the entry it is and never walked through. Neither function raises: the
caller is told whether anything is left, and only a fault of its own (a key or a kind this build
never makes) is raised.

The relay documents of the copy are `test_login_relay_flow`; this file is the other half of the
same module and uses the same synthetic fixtures.
"""
from __future__ import annotations

import errno
import os
import sys
from pathlib import Path

import pytest

from conductor.command.adapters import login_relay
from conductor.command.adapters.login_relay import discard, sweep
from tests import relay_credentials as fake
from tests.relay_fixtures import link

KEY = "0123456789abcdef"
HEX = "fedcba9876543210"


def locked(monkeypatch, name):
    """A file that cannot be deleted, as the operating system answers it, whatever its mode."""
    real = os.unlink

    def unlink(path, *args, **kwargs):
        if Path(os.fspath(path)).name == name:
            raise PermissionError(errno.EACCES, "locked by another process")
        return real(path, *args, **kwargs)

    monkeypatch.setattr(login_relay.os, "unlink", unlink)


# --- discard ---------------------------------------------------------------------------------


def a_used_relay_home(base):
    """A relay home as an attempt leaves it: the copied files, and what the child made."""
    relay = fake.relay_home(base)
    (relay / ".credentials.json").write_bytes(b'{"claudeAiOauth": {}}')
    (relay / ".claude.json").write_bytes(b"{}")
    (relay / "sessions" / "one" / "two").mkdir(parents=True)
    (relay / "sessions" / "one" / "two" / "log.txt").write_bytes(b"log")
    (relay / "tmp").mkdir()
    (relay / "tmp" / "arg0").write_bytes(b"x")
    return relay


def test_discard_removes_the_credentials_and_the_whole_tree_and_says_so(tmp_path):
    relay = a_used_relay_home(tmp_path)

    assert discard(relay, (".credentials.json", ".claude.json")) is True
    assert not os.path.lexists(relay)


def test_discard_removes_a_file_the_child_made_read_only(tmp_path):
    relay = a_used_relay_home(tmp_path)
    os.chmod(relay / "tmp" / "arg0", 0o444)

    assert discard(relay) is True
    assert not os.path.lexists(relay)


def test_a_home_that_is_already_gone_is_discarded(tmp_path):
    assert discard(tmp_path / "never-made") is True


def test_the_credentials_are_gone_even_when_the_tree_cannot_be_removed(tmp_path, monkeypatch):
    relay = a_used_relay_home(tmp_path)
    (relay / "held.bin").write_bytes(b"held by the child, still running")
    locked(monkeypatch, "held.bin")

    assert discard(relay, (".credentials.json", ".claude.json")) is False

    assert not (relay / ".credentials.json").exists()
    assert not (relay / ".claude.json").exists()
    assert (relay / "held.bin").exists(), "the file that could not be removed is still there"


def test_a_name_that_is_not_one_name_is_not_followed_out_of_the_relay_home(tmp_path):
    relay = a_used_relay_home(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"not the relay's")

    assert discard(relay, ("../outside.txt", "..\\outside.txt", str(outside))) is True

    assert outside.read_bytes() == b"not the relay's"
    assert not os.path.lexists(relay)


def test_a_link_the_child_made_is_removed_as_a_link_and_never_followed(tmp_path):
    relay = a_used_relay_home(tmp_path)
    target = tmp_path / "somebody-elses-folder"
    target.mkdir()
    (target / "kept.txt").write_bytes(b"kept")
    link(relay / "door", target)

    assert discard(relay) is True

    assert not os.path.lexists(relay)
    assert (target / "kept.txt").read_bytes() == b"kept"


def test_a_relay_home_that_has_become_a_link_is_removed_as_a_link_only(tmp_path):
    target = tmp_path / "somebody-elses-folder"
    target.mkdir()
    (target / "kept.txt").write_bytes(b"kept")
    link(tmp_path / "relay-link", target)

    assert discard(tmp_path / "relay-link") is True

    assert not os.path.lexists(tmp_path / "relay-link")
    assert (target / "kept.txt").read_bytes() == b"kept"


def test_a_path_longer_than_the_classic_limit_is_discarded(tmp_path):
    """The tree really is deeper than the classic limit, whatever the machine allows.

    It proves the removal on a machine where a plain long name does not work (Windows with
    `LongPathsEnabled` = 0, as measured on the developer's); where plain long names work, it
    proves only that a long tree goes. That the extended-length form is what is asked of the file
    system is the next test, which does not depend on the machine's setting.
    """
    relay = fake.relay_home(tmp_path)
    deep = relay.joinpath(*("d" * 25 for _ in range(14)), "log.txt")
    prefix = "\\\\?\\" if os.name == "nt" else ""
    os.makedirs(prefix + str(deep.parent))
    Path(prefix + str(deep)).write_bytes(b"deep")

    assert len(str(deep)) > 300, "the path is not longer than the classic 260-character limit"
    assert discard(relay) is True
    assert not os.path.lexists(relay)


@pytest.mark.skipif(os.name != "nt", reason="the extended-length form is a Windows name")
def test_every_path_discard_asks_the_file_system_about_is_in_the_extended_length_form(
        tmp_path, monkeypatch):
    """Observed at the file-system boundary, so it holds with long paths enabled or not."""
    relay = a_used_relay_home(tmp_path)
    asked = []
    real = {name: getattr(os, name) for name in ("lstat", "scandir", "unlink", "rmdir")}

    def recording(name):
        def call(path, *args, **kwargs):
            asked.append(os.fspath(path))
            return real[name](path, *args, **kwargs)
        return call

    for name in real:
        monkeypatch.setattr(login_relay.os, name, recording(name))

    assert discard(relay, (".credentials.json", ".claude.json")) is True

    ours = [path for path in asked if "relay-home" in path]
    assert ours, "discard asked the file system nothing about the relay home"
    assert all(path.startswith("\\\\?\\") for path in ours), ours


def test_a_tree_deeper_than_the_recursion_limit_is_discarded(tmp_path):
    relay = fake.relay_home(tmp_path)
    depth, frame = 0, sys._getframe()
    while frame is not None:
        depth, frame = depth + 1, frame.f_back
    saved = sys.getrecursionlimit()
    sys.setrecursionlimit(depth + 60)  # the limit is lowered, not the tree grown to a thousand
    try:
        levels = sys.getrecursionlimit() + 40
        here = ("\\\\?\\" if os.name == "nt" else "") + str(relay)
        for _ in range(levels):  # one level at a time: `os.makedirs` itself recurses
            here = os.path.join(here, "d")
            os.mkdir(here)

        assert levels > sys.getrecursionlimit()
        assert discard(relay) is True
        assert not os.path.lexists(relay)
    finally:
        sys.setrecursionlimit(saved)


def test_discard_never_raises_for_a_path_it_cannot_even_name():
    assert discard("x\x00y") is False


# --- sweep -----------------------------------------------------------------------------------


#: Folders of the key folder that begin as a relay home's name does and are not one: they are not
#: this build's to remove. A short tail, a long tail, a tail that is not hex, a suffix, another
#: separator and no tail at all. (No capital letter: a Windows folder `C-...` IS `c-...`.)
NOT_A_HOME = ("c-notes", "c-0123", f"c-{HEX}0", f"c-{HEX[:-1]}g", f"c-{HEX}.bak", f"c_{HEX}", "c-")


def a_relay_root(base, key=KEY):
    relay = base / "DecemberCommand" / "relay"
    for name in (f"c-{HEX}", f"c-{'0' * 16}", f"x-{HEX}"):
        (relay / key / name).mkdir(parents=True)
        (relay / key / name / "auth.json").write_bytes(b"{}")
    for name in NOT_A_HOME:
        (relay / key / name).mkdir()
        (relay / key / name / "kept.txt").write_bytes(b"kept")
    (relay / key / "notes.txt").write_bytes(b"not a relay home")
    (relay / "aaaaaaaaaaaaaaaa" / f"c-{HEX}").mkdir(parents=True)
    return relay


def test_sweep_removes_the_leftover_homes_of_one_key_and_one_kind_and_no_others(tmp_path):
    relay = a_relay_root(tmp_path)

    assert sweep(relay, KEY, "c") == []

    assert sorted(path.name for path in (relay / KEY).iterdir()) == sorted(
        ["notes.txt", f"x-{HEX}", *NOT_A_HOME])
    assert all((relay / KEY / name / "kept.txt").read_bytes() == b"kept" for name in NOT_A_HOME)
    assert (relay / "aaaaaaaaaaaaaaaa" / f"c-{HEX}").is_dir()


def test_sweep_names_the_homes_it_could_not_remove(tmp_path, monkeypatch):
    relay = a_relay_root(tmp_path)
    (relay / KEY / f"c-{HEX}" / "held.bin").write_bytes(b"held")
    locked(monkeypatch, "held.bin")

    assert sweep(relay, KEY, "c") == [f"c-{HEX}"]

    assert (relay / KEY / f"c-{HEX}" / "held.bin").exists()
    assert not (relay / KEY / f"c-{'0' * 16}").exists()


def test_sweep_takes_the_credentials_first_from_a_home_it_cannot_remove(tmp_path, monkeypatch):
    relay = a_relay_root(tmp_path)
    home = relay / KEY / f"x-{HEX}"
    (home / "held.bin").write_bytes(b"held")
    locked(monkeypatch, "held.bin")

    assert sweep(relay, KEY, "x", ("auth.json",)) == [f"x-{HEX}"]

    assert not (home / "auth.json").exists()


def test_a_project_with_no_key_folder_has_nothing_to_sweep(tmp_path):
    (tmp_path / "relay").mkdir()

    assert sweep(tmp_path / "relay", KEY, "c") == []
    assert sweep(tmp_path / "no-relay-either", KEY, "c") == []


def test_a_key_that_is_not_a_folder_is_named_and_nothing_is_followed(tmp_path):
    relay = tmp_path / "relay"
    relay.mkdir()
    (relay / KEY).write_bytes(b"a file where the key folder belongs")

    assert sweep(relay, KEY, "c") == [KEY]
    assert (relay / KEY).read_bytes() == b"a file where the key folder belongs"


def test_a_key_that_is_a_link_is_named_and_what_it_leads_to_is_kept(tmp_path):
    relay = tmp_path / "relay"
    relay.mkdir()
    elsewhere = tmp_path / "elsewhere"
    (elsewhere / f"c-{HEX}").mkdir(parents=True)
    link(relay / KEY, elsewhere)

    assert sweep(relay, KEY, "c") == [KEY]
    assert (elsewhere / f"c-{HEX}").is_dir()


@pytest.mark.parametrize("key,kind", [
    ("..", "c"), ("abc", "c"), ("0123456789ABCDEF", "c"), (f"{KEY}/x", "c"), ("", "c"),
    (KEY, "cx"), (KEY, ""), (KEY, "/"), (KEY, "C"), (KEY, "1")])
def test_a_key_or_kind_that_is_not_one_this_build_makes_is_a_fault_of_the_caller(
        tmp_path, key, kind):
    with pytest.raises(ValueError):
        sweep(tmp_path, key, kind)
