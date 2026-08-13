"""The cwd containment door: a child runs only strictly, locally beneath the root.

This is the path-escape sabotage class the runner owns. One relation closes it:
every component of the route from the resolved project root down to the cwd is
read with `os.lstat`, following nothing, and must be a real local directory.
A `..` segment, a path outside the root, the root itself, or a symlink/junction
anywhere on the route refuses -- and refuses BEFORE any child is spawned, proven
by a side effect the child would have produced never appearing. The argv-target
half of the class is here too: a traversal string in an argument is inert data
the runner hands the child untouched, never a path the runner itself follows.

Portals are planted with the same privilege-free technique the preview route
tests use: an NTFS junction via `_winapi.CreateJunction`, a symlink where the
platform grants it. The portal detector's four relations are pinned at unit
level over fabricated stat objects, both sides written here.
"""
from __future__ import annotations

import os
import stat
import types

import pytest

from conductor.command.adapters.process import (
    CommandSpec,
    ContainmentError,
    OwnershipError,
    ProcessRunner,
    _detected_portal,
)

from tests._fakeproc import DUMP_ARGV, DUMP_CWD, PID_FILE, fake_argv
import json


@pytest.fixture
def root(tmp_path):
    (tmp_path / "project" / "work").mkdir(parents=True)
    return tmp_path / "project"


@pytest.fixture
def runners():
    built = []

    def make(project_root, **kwargs):
        runner = ProcessRunner(project_root, **kwargs)
        built.append(runner)
        return runner

    yield make
    for runner in built:
        for token in runner.active_tokens():
            try:
                runner.stop(token)
            except OwnershipError:
                pass


def _junction_or_skip(link, target):
    try:
        import _winapi
        _winapi.CreateJunction(str(target), str(link))
    except (ImportError, AttributeError, OSError) as e:
        pytest.skip(f"this platform cannot make a junction: {e}")


def _symlink_or_skip(link, target):
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError) as e:  # pragma: no cover - platform policy
        pytest.skip(f"this platform did not permit a symbolic link: {e}")


def _refused_before_spawn(runner, cwd, tmp_path):
    """Attempt a run at `cwd`; hold the refusal AND that no child ever spawned.

    The command names a pid file the child writes the instant it starts. A
    containment refusal must raise before spawn, so that file never appears and
    the runner owns nothing -- the before/after state of the whole attempt.
    """
    marker = tmp_path / f"spawned-{abs(hash(str(cwd)))}"
    with pytest.raises(ContainmentError) as caught:
        runner.run(CommandSpec(
            argv=fake_argv(), cwd=str(cwd), env={PID_FILE: str(marker)},
            timeout_seconds=10))
    assert not marker.exists()  # the child never ran: refused before spawn
    assert runner.active_tokens() == ()
    return str(caught.value)


# --- the positive route, and the plain-path refusals ---


def test_a_directory_strictly_beneath_the_root_runs_there(root, runners):
    runner = runners(root)
    outcome = runner.run(CommandSpec(
        argv=fake_argv(), cwd="work", env={DUMP_CWD: "1"}, timeout_seconds=10))
    reported = outcome.output.decode("utf-8").splitlines()[0]
    assert reported.startswith("CWD ")
    assert os.path.samefile(reported[4:], root / "work")


def test_the_project_root_itself_is_not_strictly_beneath_the_root(root, runners, tmp_path):
    message = _refused_before_spawn(runners(root), root, tmp_path)
    assert "strictly beneath the project root, not the root itself" in message


def test_a_cwd_outside_the_root_is_refused(root, runners, tmp_path):
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    message = _refused_before_spawn(runners(root), outside, tmp_path)
    assert "is not beneath the project root" in message


def test_a_cwd_reaching_out_through_dotdot_is_refused(root, runners, tmp_path):
    message = _refused_before_spawn(runners(root), "work/../../escape", tmp_path)
    assert "escapes the project root through '..'" in message


def test_a_missing_cwd_component_is_refused(root, runners, tmp_path):
    message = _refused_before_spawn(runners(root), "work/absent", tmp_path)
    assert "does not exist or cannot be read" in message


def test_a_file_on_the_route_is_not_a_directory(root, runners, tmp_path):
    (root / "work" / "afile").write_bytes(b"x")
    message = _refused_before_spawn(runners(root), "work/afile", tmp_path)
    assert "is not a directory" in message


# --- portals on the route: the whole route, not just the leaf ---


@pytest.mark.parametrize("kind", ["junction", "symlink"])
@pytest.mark.parametrize("depth", ["leaf", "intermediate"])
def test_a_portal_on_the_cwd_route_is_refused_before_spawn(
        kind, depth, root, runners, tmp_path):
    """A symlink or junction at any route component refuses before the child exists.

    At the leaf the cwd names the portal itself; one level up the cwd names a
    child of it, so the walk meets the portal before it would descend. Either
    way the escape is caught by reading the component, never by following it.
    """
    outside = tmp_path / "outside"
    (outside / "inner").mkdir(parents=True)
    portal = root / "portal"
    if kind == "junction":
        _junction_or_skip(portal, outside)
    else:
        _symlink_or_skip(portal, outside)
    cwd = "portal" if depth == "leaf" else "portal/inner"
    message = _refused_before_spawn(runners(root), cwd, tmp_path)
    assert repr(str(root.resolve() / "portal")) in message
    assert ("a directory junction" if kind == "junction" else "a symbolic link") in message


def test_the_portal_detector_names_its_kinds_and_answers_none_for_an_ordinary_object():
    """`_detected_portal` over the relations lstat can hand it; both sides test-local."""
    symlink = types.SimpleNamespace(st_mode=stat.S_IFLNK | 0o777, st_reparse_tag=0)
    assert _detected_portal(symlink) == "a symbolic link"
    junction = types.SimpleNamespace(
        st_mode=stat.S_IFDIR | 0o755, st_reparse_tag=0xA0000003)
    assert _detected_portal(junction) == "a directory junction"
    other = types.SimpleNamespace(st_mode=stat.S_IFREG | 0o644, st_reparse_tag=0x80000017)
    assert _detected_portal(other) == "a reparse point (tag 0x80000017)"
    ordinary = types.SimpleNamespace(st_mode=stat.S_IFDIR | 0o755, st_reparse_tag=0)
    assert _detected_portal(ordinary) is None


# --- the argv-target half: a traversal argument is inert data, not a path ---


def test_a_path_traversal_argument_is_handed_to_the_child_as_inert_text(root, runners):
    """An argument that looks like an escape is data the child receives verbatim.

    The runner's only filesystem boundary is the cwd; arguments are opaque. A
    `..`-laden argument neither escapes nor is acted upon by the runner: the run
    succeeds in the contained cwd and the child echoes the argument unchanged.
    """
    runner = runners(root)
    traversal = "../../../../etc/passwd"
    outcome = runner.run(CommandSpec(
        argv=fake_argv(traversal), cwd="work", env={DUMP_ARGV: "1"}, timeout_seconds=10))
    assert outcome.status == "completed"
    echoed = json.loads(outcome.output.decode("utf-8").splitlines()[0][len("ARGV "):])
    assert echoed == [traversal]
