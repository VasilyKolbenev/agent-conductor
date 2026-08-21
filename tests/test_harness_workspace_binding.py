"""The workspace door is bound to ONE provider's names, and proves it at birth.

The door beneath every headless harness owns four subtrees. Two of them belong
to the RUN -- the authorized work tree and the instruction directory -- and are
the door's own constants, shared by every provider driving that run. The other
two belong to the PROVIDER: the home its vendor's tool keeps a profile in, and
the marker namespace one attempt is claimed in. Those two are handed in.

Handing them in is what makes the door reusable, and it is also what makes it
possible to hand in a pair that destroys the run. Three relations hold that
shut, and each is a fact about consequences rather than about a message:

- a home and a marker with ONE name make `discard_home` -- a deliberate,
  bounded, recursive delete -- erase the markers that prove what already ran, so
  a crash-safe adapter would run a finished task a second time;
- a home or marker named for a run-owned subtree points that same delete at the
  task's own evidence, or at the text it was asked to do;
- two providers sharing one home name take each other's attempt directories for
  their own, which is a leak in both directions and a delete in one.

The gate is the fourth relation and it runs the other way: providers that own
DIFFERENT names have no state to contend over, so serializing them would be a
cost with nothing bought. The door promises in its own comments that one
harness's root never stops another provider; the test at the bottom is what
makes that promise checkable rather than decorative.

Nothing here is about dsh, kimi, or any other product. The names below are
written in this file precisely because the door must hold for pairs no provider
in the tree has claimed yet.
"""
from __future__ import annotations

import threading
from pathlib import Path

import pytest

from conductor.command.adapters.harness_workspace import (
    INSTRUCTION_DIR,
    WORK_DIR,
    HarnessWorkspace,
    WorkspaceNotContained,
)

#: Two providers that exist nowhere but here, so the relations below are held
#: against the DOOR rather than against whatever the catalog happens to carry.
ONE_HOME, ONE_MARKER = ".one-home", ".one-marker"
TWO_HOME, TWO_MARKER = ".two-home", ".two-marker"


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "root"
    root.mkdir()
    return root


def _refusal(call, *args, **kwargs):
    """Run one door, reporting a refusal as a value so the fact can be read first."""
    try:
        call(*args, **kwargs)
    except WorkspaceNotContained as error:
        return error
    return None


# --- the pair a provider may not bring ---------------------------------------


def test_one_name_for_both_the_home_and_the_marker_is_refused(tmp_path):
    root = _root(tmp_path)

    refusal = _refusal(
        HarnessWorkspace.at, root, home_dir=".same", marker_dir=".same")

    assert refusal is not None, "a home and a marker sharing one name must refuse"


def test_a_home_discard_leaves_the_markers_that_prove_what_already_ran(tmp_path):
    """The consequence the refusal above exists to prevent, held on real files.

    A marker is what stops a crashed dispatch from running a finished task
    twice. Were the two names one, the home this test discards would take the
    marker with it and `is_claimed` would answer False about work that already
    happened -- so the property is read through `is_claimed`, the question an
    adapter actually asks, and not through the path.
    """
    root = _root(tmp_path)
    workspace = HarnessWorkspace.at(root, home_dir=ONE_HOME, marker_dir=ONE_MARKER)
    workspace.claim("act-1")
    home = workspace.mint_home("attempt-1")
    (home / "profile.json").write_text("{}", encoding="utf-8")

    workspace.discard_home(home)

    assert not home.exists(), "the attempt home is gone"
    assert workspace.is_claimed("act-1") is True, "CLAIM_LOST_WITH_THE_HOME=True"


@pytest.mark.parametrize("reserved", (WORK_DIR, INSTRUCTION_DIR))
@pytest.mark.parametrize("field", ("home_dir", "marker_dir"))
def test_a_run_owned_subtree_is_refused_as_a_providers_own_name(
        tmp_path, reserved, field):
    """Neither name may be the work tree or the instruction directory.

    Both are run facts every provider reads. A home pointed at either one aims
    the home cleanup at the task's evidence or at its instructions, and the
    marker case is the same delete reached one call later.
    """
    root = _root(tmp_path)
    names = {"home_dir": ONE_HOME, "marker_dir": ONE_MARKER} | {field: reserved}

    refusal = _refusal(HarnessWorkspace.at, root, **names)

    assert refusal is not None, f"{field}={reserved!r} must refuse"


@pytest.mark.parametrize(
    "name", ("..", ".", "", "a/b", "a\\b", "C:evil", "a\x00b"))
def test_a_provider_name_that_is_not_one_local_component_is_refused(tmp_path, name):
    """A name is a CHILD of the root, never a route out of it."""
    root = _root(tmp_path)

    refusal = _refusal(
        HarnessWorkspace.at, root, home_dir=name, marker_dir=ONE_MARKER)

    assert refusal is not None, f"home_dir={name!r} must refuse"


# --- two providers under one root are strangers ------------------------------


def test_one_providers_sweep_never_removes_another_providers_attempt_home(tmp_path):
    """The isolation the distinct names buy, read on the disk after the sweep."""
    root = _root(tmp_path)
    one = HarnessWorkspace.at(root, home_dir=ONE_HOME, marker_dir=ONE_MARKER)
    two = HarnessWorkspace.at(root, home_dir=TWO_HOME, marker_dir=TWO_MARKER)
    ours = two.mint_home("attempt-1")
    (ours / "state.json").write_text("{}", encoding="utf-8")

    refused = one.sweep_homes()

    assert refused == (), "a neighbour's home is not even seen, let alone refused"
    assert (ours / "state.json").read_text(encoding="utf-8") == "{}", (
        "NEIGHBOUR_HOME_SWEPT=True")


def _holds(workspace, entered, release):
    """Take one gate, announce it, and keep it until the test lets go."""
    with workspace.owned():
        entered.set()
        release.wait(10)


def _takes_the_gate(workspace, timeout=2.0):
    """Whether this workspace can ENTER its gate within a bounded wait."""
    entered, done = threading.Event(), threading.Event()
    thread = threading.Thread(
        target=_holds, args=(workspace, entered, done), daemon=True)
    thread.start()
    took = entered.wait(timeout)
    done.set()
    thread.join(10)
    return took


def test_two_providers_on_one_root_never_wait_for_each_other(tmp_path):
    """The gate key is the root AND the names, so neighbours do not queue.

    Held together with its own opposite: the SAME provider on the same root must
    still serialize, or this test would pass just as well on a door that had no
    gate at all.
    """
    root = _root(tmp_path)
    holder = HarnessWorkspace.at(root, home_dir=ONE_HOME, marker_dir=ONE_MARKER)
    neighbour = HarnessWorkspace.at(root, home_dir=TWO_HOME, marker_dir=TWO_MARKER)
    twin = HarnessWorkspace.at(root, home_dir=ONE_HOME, marker_dir=ONE_MARKER)
    held, release = threading.Event(), threading.Event()
    thread = threading.Thread(
        target=_holds, args=(holder, held, release), daemon=True)
    thread.start()
    try:
        assert held.wait(10), "the holding workspace never took its own gate"
        assert _takes_the_gate(neighbour) is True, "NEIGHBOUR_BLOCKED=True"
        assert _takes_the_gate(twin) is False, "TWIN_RAN_CONCURRENTLY=True"
    finally:
        release.set()
        thread.join(10)
