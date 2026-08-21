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


def test_one_providers_sweep_removes_its_own_homes_and_no_neighbours(tmp_path):
    """The isolation distinct names buy, held from BOTH sides in one test.

    One side alone is not a guard. A sweep bounded to some other provider's
    home root -- or to nothing at all -- leaves the neighbour's tree untouched
    just as faithfully as a correct one does, so "the neighbour survived" passes
    on a sweep that does nothing whatsoever. What makes the bound checkable is
    the pair: this provider's own crashed home is gone, and the neighbour's is
    not, after the same call.
    """
    root = _root(tmp_path)
    one = HarnessWorkspace.at(root, home_dir=ONE_HOME, marker_dir=ONE_MARKER)
    two = HarnessWorkspace.at(root, home_dir=TWO_HOME, marker_dir=TWO_MARKER)
    crashed = one.mint_home("attempt-1")
    (crashed / "state.json").write_text("{}", encoding="utf-8")
    theirs = two.mint_home("attempt-1")
    (theirs / "state.json").write_text("{}", encoding="utf-8")

    refused = one.sweep_homes()

    assert refused == (), "a neighbour's home is not even seen, let alone refused"
    assert not crashed.exists(), "OWN_CRASHED_HOME_SURVIVED=True"
    assert (theirs / "state.json").read_text(encoding="utf-8") == "{}", (
        "NEIGHBOUR_HOME_SWEPT=True")


def test_the_marker_name_is_the_route_the_door_actually_walks(tmp_path):
    """``marker_path`` cannot name one route while ``claim`` writes another.

    The unvalidated name and the walked route were computed separately, so the
    two could disagree and nothing would say which was wrong. They are one
    expression now, and this holds it the only way that means anything: the file
    ``claim`` really created is found AT the name ``marker_path`` reports.
    """
    root = _root(tmp_path)
    workspace = HarnessWorkspace.at(root, home_dir=ONE_HOME, marker_dir=ONE_MARKER)

    workspace.claim("act-1")

    named = workspace.marker_path("act-1")
    assert named.is_file(), f"NOTHING_AT_THE_NAMED_MARKER={named}"
    assert named.read_text(encoding="utf-8") == "act-1"
    assert named.parent.name == ONE_MARKER, "the marker stands in the marker root"


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


def test_two_providers_on_one_root_take_one_turn_over_the_tree_they_share(tmp_path):
    """Neighbours DO queue, and this test used to claim the opposite.

    It was written to match a comment above the gate promising that one harness's
    root never stops another provider. The comment was aspirational; the code was
    right; and changing the code to match the comment opened a race. The
    reproduction, before the revert:

        wrote_while_one_owned_root=True
        foreign_change=['b/foreign.txt']

    Distinct home and marker names are what make CLEANUP safe -- each provider
    deletes only under its own root. They do not make a turn unnecessary,
    because `work` and `instructions` belong to the RUN and every provider reads
    and writes the same two.

    Held with its own opposite, or a door with no gate at all would pass: a
    second root must NOT wait.
    """
    root = _root(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    holder = HarnessWorkspace.at(root, home_dir=ONE_HOME, marker_dir=ONE_MARKER)
    neighbour = HarnessWorkspace.at(root, home_dir=TWO_HOME, marker_dir=TWO_MARKER)
    unrelated = HarnessWorkspace.at(
        elsewhere, home_dir=ONE_HOME, marker_dir=ONE_MARKER)
    held, release = threading.Event(), threading.Event()
    thread = threading.Thread(
        target=_holds, args=(holder, held, release), daemon=True)
    thread.start()
    try:
        assert held.wait(10), "the holding workspace never took its own gate"
        assert _takes_the_gate(neighbour) is False, "NEIGHBOUR_RAN_CONCURRENTLY=True"
        assert _takes_the_gate(unrelated) is True, "SECOND_ROOT_BLOCKED=True"
    finally:
        release.set()
        thread.join(10)


def test_a_neighbour_cannot_change_the_shared_work_tree_during_another_turn(
        tmp_path):
    """The consequence the turn exists for, read off the disk rather than the lock.

    A test that only proved the neighbour waits would still pass on a gate that
    serialized the wrong thing. What must be true is that nothing a neighbour
    writes can appear in the diff the holder computes across its own turn --
    because that diff is the evidence a verification judges, and a foreign path
    in it reads as a change outside the authorized subtree.
    """
    root = _root(tmp_path)
    holder = HarnessWorkspace.at(root, home_dir=ONE_HOME, marker_dir=ONE_MARKER)
    neighbour = HarnessWorkspace.at(root, home_dir=TWO_HOME, marker_dir=TWO_MARKER)
    (holder.work_dir("a") / "mine.txt").write_text("a", encoding="utf-8")
    started, done = threading.Event(), threading.Event()

    def writes_its_own_work_item() -> None:
        started.set()
        with neighbour.owned():
            (neighbour.work_dir("b") / "foreign.txt").write_text(
                "b", encoding="utf-8")
        done.set()

    with holder.owned():
        before = holder.digest_work_tree()
        thread = threading.Thread(target=writes_its_own_work_item, daemon=True)
        thread.start()
        assert started.wait(10), "the neighbour thread never started"
        landed = done.wait(2)
        after = holder.digest_work_tree()

    thread.join(10)
    changed = sorted(
        name for name in set(before) | set(after)
        if before.get(name) != after.get(name))
    assert landed is False, "WROTE_WHILE_ONE_OWNED_ROOT=True"
    assert changed == [], f"FOREIGN_CHANGE={changed}"
