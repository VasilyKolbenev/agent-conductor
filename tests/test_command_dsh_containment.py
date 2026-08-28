"""The dsh workspace's writable routes are contained BEFORE every write.

Codex drove one probe at the prior SHA and it is the whole reason this module
exists:

    root/.dsh-home -> outside
    HarnessWorkspace.mint_home("attempt")
    OUTSIDE_CREATED=True

A portal planted at a name the workspace owns made the workspace create durable
state OUTSIDE the project root it is bound to. The same class covers the marker
and the work route, and it covers the evidence walk, which followed a junction
into a tree it does not own. What is held here is the RELATION, never a message:
after a refusal the outside tree is byte-for-byte as it was, and the route the
workspace refused is named by its typed structural fact.

The cleanup half is held the same way. A cleanup that can delete outside its own
root is a worse defect than the leak it fixes, so every delete here is proved
twice: the attempt home is gone, and the outside tree a portal inside that home
pointed at is untouched.

Every portal is planted by `tests.sabotage_fixtures`, whose builders never judge
their own output, and every assertion below reads the filesystem with an
independent witness.
"""
from __future__ import annotations

import os
import shutil
import threading
from pathlib import Path

import pytest

import conductor.command.adapters.harness_workspace as harness_workspace
from conductor.command.adapters.dsh_harness import HOME_DIR, MARKER_DIR
from conductor.command.adapters.harness_workspace import (
    WORK_DIR,
    HarnessWorkspace,
)

from tests import _fakedsh
from tests.sabotage_fixtures import (
    plant_outward_hard_link,
    plant_route_portal,
    skip_when_unavailable,
)
from tests.test_command_dsh_harness import PROVIDER_ID, a_harness, a_request, run_once

PORTALS = ("junction", "symlink")


def _refusal(call, *args):
    """Run one workspace door, reporting a refusal as a fact rather than a type.

    The probes below are born red on a tree where no refusal exists at all, so
    the FIRST thing each one holds is the durable relation -- what stands outside
    the root -- and only then that the door refused. This helper keeps the first
    assertion reachable on either tree.
    """
    try:
        call(*args)
    except Exception as error:  # noqa: BLE001 -- the probe reports, never selects
        return error
    return None


def _tree(root: Path) -> dict[str, object]:
    """Every name under ``root``, read with lstat alone and never followed."""
    out: dict[str, object] = {}
    stack = [root]
    while stack:
        for path in sorted(stack.pop().iterdir()):
            key = path.relative_to(root).as_posix()
            if path.is_symlink() or getattr(os.lstat(path), "st_reparse_tag", 0):
                out[key] = ("portal", os.readlink(path))
            elif path.is_dir():
                out[key] = ("dir",)
                stack.append(path)
            else:
                out[key] = ("file", path.read_bytes())
    return out


def _outside(tmp_path: Path) -> Path:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "kept.txt").write_text("owned by nobody here", encoding="utf-8")
    return outside


def _at(root: Path) -> HarnessWorkspace:
    """One spelling of the dsh workspace, so a gate test reads as a gate test.

    The door takes the home and marker names from the PROVIDER now, and dsh's
    are read from the dsh module rather than restated here: a rename there must
    move this whole file, not quietly leave it testing a second workspace.
    """
    return HarnessWorkspace.at(root, home_dir=HOME_DIR, marker_dir=MARKER_DIR)


def _rooted(tmp_path: Path) -> tuple[HarnessWorkspace, Path]:
    root = tmp_path / "root"
    root.mkdir()
    return _at(root), root


# --- the probe Codex ran, and its two siblings -------------------------------


@pytest.mark.parametrize("kind", PORTALS)
def test_a_portal_at_the_home_route_creates_no_attempt_home_outside_the_root(
        tmp_path, kind):
    workspace, root = _rooted(tmp_path)
    outside = _outside(tmp_path)
    with skip_when_unavailable():
        plant_route_portal(root / HOME_DIR, outside, kind=kind)
    before = _tree(outside)

    refusal = _refusal(workspace.mint_home, "attempt")

    assert not (outside / "attempt").exists(), "OUTSIDE_CREATED=True"
    assert _tree(outside) == before
    assert refusal is not None, "a portal on the home route must refuse the mint"


@pytest.mark.parametrize("kind", PORTALS)
def test_a_portal_that_replaces_the_resolved_root_creates_nothing_through_it(
        tmp_path, kind):
    """The ROOT is a route component too, and this is the case that proves it.

    The door's own docstring says the root is judged "because a portal standing
    AT a container adopts external state exactly as one standing inside it
    does" -- and until this test that sentence was unguarded: dropping the root
    from the walked route left every sibling above still passing, because each
    of them plants its portal one level DOWN.

    The case is narrow and it is real. A workspace resolves its root once, at
    construction, so an operator reaching a project through a link is answered
    about the real tree; that is the alias the gate test relies on and it must
    keep working. What must still refuse is the resolved root becoming a portal
    AFTER that: the door then holds a concrete path whose kind changed under it,
    and every name it would create beneath that path lands outside the project.
    """
    workspace, root = _rooted(tmp_path)
    outside = _outside(tmp_path)
    root.rmdir()
    with skip_when_unavailable():
        plant_route_portal(root, outside, kind=kind)
    before = _tree(outside)

    refusal = _refusal(workspace.mint_home, "attempt")

    assert not (outside / HOME_DIR).exists(), "OUTSIDE_CREATED=True"
    assert _tree(outside) == before
    assert refusal is not None, "a portal at the resolved root must refuse the mint"


@pytest.mark.parametrize("kind", PORTALS)
def test_a_portal_at_the_marker_route_claims_nothing_outside_the_root(tmp_path, kind):
    workspace, root = _rooted(tmp_path)
    outside = _outside(tmp_path)
    with skip_when_unavailable():
        plant_route_portal(root / MARKER_DIR, outside, kind=kind)
    before = _tree(outside)

    refusal = _refusal(workspace.claim, "act-1")

    assert not (outside / "act-1.marker").exists(), "OUTSIDE_CREATED=True"
    assert _tree(outside) == before
    assert refusal is not None, "a portal on the marker route must refuse the claim"


@pytest.mark.parametrize("kind", PORTALS)
def test_a_portal_at_the_work_route_creates_no_work_subtree_outside_the_root(
        tmp_path, kind):
    workspace, root = _rooted(tmp_path)
    outside = _outside(tmp_path)
    with skip_when_unavailable():
        plant_route_portal(root / WORK_DIR, outside, kind=kind)
    before = _tree(outside)

    refusal = _refusal(workspace.work_dir, "work-001")

    assert not (outside / "work-001").exists(), "OUTSIDE_CREATED=True"
    assert _tree(outside) == before
    assert refusal is not None, "a portal on the work route must refuse the mkdir"


@pytest.mark.parametrize("kind", PORTALS)
def test_a_portal_at_the_work_item_leaf_creates_nothing_through_it(tmp_path, kind):
    """The LEAF is a route component too, not merely the ancestors above it."""
    workspace, root = _rooted(tmp_path)
    outside = _outside(tmp_path)
    (root / WORK_DIR).mkdir()
    with skip_when_unavailable():
        plant_route_portal(root / WORK_DIR / "work-001", outside, kind=kind)
    before = _tree(outside)

    refusal = _refusal(workspace.work_dir, "work-001")

    assert _tree(outside) == before, "OUTSIDE_CREATED=True"
    assert refusal is not None, "a portal at the work item leaf must refuse"


def test_a_second_hard_link_on_a_marker_refuses_before_the_marker_is_rewritten(
        tmp_path):
    """A marker whose bytes answer to a name outside the root is not written."""
    workspace, root = _rooted(tmp_path)
    outside = _outside(tmp_path)
    (root / MARKER_DIR).mkdir()
    marker = root / MARKER_DIR / "act-1.marker"
    marker.write_text("planted", encoding="utf-8", newline="\n")
    alias = outside / "alias.marker"
    with skip_when_unavailable():
        plant_outward_hard_link(marker, alias)

    refusal = _refusal(workspace.claim, "act-1")

    assert alias.read_text(encoding="utf-8") == "planted", "ALIAS_REWRITTEN=True"
    assert refusal is not None, "a hard-linked marker must refuse the claim"


# --- the evidence walk never reads through a portal ---------------------------


@pytest.mark.parametrize("kind", PORTALS)
def test_the_work_digest_records_a_portal_by_name_and_never_descends_it(
        tmp_path, kind):
    workspace, root = _rooted(tmp_path)
    outside = _outside(tmp_path)
    (outside / "secret.txt").write_text("outside content", encoding="utf-8")
    work = root / WORK_DIR / "work-001"
    work.mkdir(parents=True)
    with skip_when_unavailable():
        plant_route_portal(work / "borrowed", outside, kind=kind)

    rows = workspace.digest_work_tree()

    assert "work-001/borrowed" in rows
    assert rows["work-001/borrowed"] in {"symlink", "junction", "reparse_point"}
    followed = [name for name in rows if name.startswith("work-001/borrowed/")]
    assert followed == [], f"DIGEST_FOLLOWED_PORTAL={followed}"


def test_the_work_digest_records_an_aliased_file_by_name_and_never_by_content(
        tmp_path):
    """Bytes that also answer to an outside name are a name here, never evidence."""
    workspace, root = _rooted(tmp_path)
    outside = _outside(tmp_path)
    work = root / WORK_DIR / "work-001"
    work.mkdir(parents=True)
    inside = work / "shared.txt"
    inside.write_text("first", encoding="utf-8", newline="\n")
    with skip_when_unavailable():
        plant_outward_hard_link(inside, outside / "shared.txt")

    rows = workspace.digest_work_tree()

    assert rows["work-001/shared.txt"] == "hard_link"
    assert not rows["work-001/shared.txt"].startswith("sha256")


# --- cleanup: a fixed owner, a fixed root, and a refusal instead of a guess ---


def test_an_attempt_home_is_discarded_whole_and_the_root_survives(tmp_path):
    workspace, root = _rooted(tmp_path)
    home = workspace.mint_home("attempt-1")
    (home / "sessions").mkdir()
    (home / "sessions" / "model.txt").write_text("model text", encoding="utf-8")

    workspace.discard_home(home)

    assert not home.exists()
    assert (root / HOME_DIR).is_dir(), "the fixed cleanup root is never removed"


@pytest.mark.parametrize("kind", PORTALS)
def test_discarding_a_home_removes_a_planted_portal_entry_and_not_its_target(
        tmp_path, kind):
    """The one relation a cleanup may never break: nothing outside its root dies."""
    workspace, _root = _rooted(tmp_path)
    outside = _outside(tmp_path)
    home = workspace.mint_home("attempt-1")
    with skip_when_unavailable():
        plant_route_portal(home / "escape", outside, kind=kind)
    before = _tree(outside)

    workspace.discard_home(home)

    assert not home.exists()
    assert outside.is_dir() and _tree(outside) == before, "OUTSIDE_DELETED=True"


def test_a_home_outside_the_fixed_cleanup_root_is_refused_and_left_standing(
        tmp_path):
    workspace, _root = _rooted(tmp_path)
    outside = _outside(tmp_path)
    stranger = outside / "not-a-home"
    stranger.mkdir()
    (stranger / "file.txt").write_text("kept", encoding="utf-8")
    before = _tree(outside)

    refusal = _refusal(workspace.discard_home, stranger)

    assert _tree(outside) == before, "OUTSIDE_DELETED=True"
    assert refusal is not None, "a path outside the fixed root must refuse"


@pytest.mark.parametrize("kind", PORTALS)
def test_the_sweep_refuses_a_portal_standing_where_a_home_would_and_names_it(
        tmp_path, kind):
    """A portal directly under the homes root was never minted here, so it stays."""
    workspace, root = _rooted(tmp_path)
    outside = _outside(tmp_path)
    (root / HOME_DIR).mkdir()
    with skip_when_unavailable():
        plant_route_portal(root / HOME_DIR / "foreign", outside, kind=kind)
    before = _tree(outside)

    refused = workspace.sweep_homes()

    assert (root / HOME_DIR / "foreign").exists()
    assert _tree(outside) == before, "OUTSIDE_DELETED=True"
    assert "foreign" in " ".join(refused)


def test_the_sweep_removes_every_home_a_crashed_attempt_left_behind(tmp_path):
    workspace, root = _rooted(tmp_path)
    first, second = workspace.mint_home("crashed-1"), workspace.mint_home("crashed-2")
    (first / "prompt.txt").write_text("the user task", encoding="utf-8")

    refused = workspace.sweep_homes()

    assert refused == ()
    assert not first.exists() and not second.exists()
    assert sorted(path.name for path in (root / HOME_DIR).iterdir()) == []


def test_a_minted_home_replaced_by_a_portal_is_removed_by_its_own_entry(tmp_path):
    """The case the contained-route idiom missed: the portal IS the home root.

    A portal met INSIDE a home was already removed by its own entry. A portal
    standing WHERE the home stands was refused instead -- correct for a name
    nobody here minted, wrong for the one this process just created and still
    remembers. The refusal is what left model-text state standing.
    """
    workspace, root = _rooted(tmp_path)
    outside = _outside(tmp_path)
    home = workspace.mint_home("attempt-1")
    home.rmdir()
    with skip_when_unavailable():
        plant_route_portal(home, outside, kind="junction")
    before = _tree(outside)

    workspace.discard_home(home)

    assert _tree(outside) == before, "OUTSIDE_DELETED=True"
    assert sorted((root / HOME_DIR).iterdir()) == [], "HOME_ENTRY_EXISTS True"


def test_a_portal_standing_where_no_minted_home_ever_stood_is_still_refused(tmp_path):
    """The other half of the same door: unminted names keep their old refusal."""
    workspace, root = _rooted(tmp_path)
    outside = _outside(tmp_path)
    (root / HOME_DIR).mkdir()
    with skip_when_unavailable():
        plant_route_portal(root / HOME_DIR / "foreign", outside, kind="junction")
    before = _tree(outside)

    refusal = _refusal(workspace.discard_home, root / HOME_DIR / "foreign")

    assert _tree(outside) == before, "OUTSIDE_DELETED=True"
    assert (root / HOME_DIR / "foreign").exists(), "FOREIGN_ENTRY_DELETED=True"
    assert refusal is not None, "a name this workspace never minted must refuse"


# --- the same relations, driven through the real adapter ----------------------


@pytest.mark.parametrize("kind", PORTALS)
def test_a_portal_at_the_home_route_spawns_no_task_through_the_real_adapter(
        tmp_path, kind):
    adapter, root, log = a_harness(tmp_path)
    outside = _outside(tmp_path)
    with skip_when_unavailable():
        plant_route_portal(root / HOME_DIR, outside, kind=kind)
    before = _tree(outside)

    receipt = run_once(adapter, a_request())

    assert _tree(outside) == before, "OUTSIDE_CREATED=True"
    assert _fakedsh.spawns(log) == [], "a refused route must spawn nothing at all"
    assert receipt.outcome == "failed"
    assert receipt.exit_code is None


def test_no_attempt_home_survives_a_completed_dispatch(tmp_path):
    """The retention truth: DSH_HOME is per-attempt, and nothing of it persists."""
    adapter, root, log = a_harness(
        tmp_path, FAKEDSH_HOME_FILE="sessions/turn.json:MODEL TEXT PLANTED HERE")
    run_once(adapter, a_request())

    homes = [row["dsh_home"] for row in _fakedsh.spawns(log)]
    assert len(homes) == 2 and len(set(homes)) == 2
    for home in homes:
        assert not Path(home).exists(), f"HOME_RETAINED={home}"
    assert sorted((root / HOME_DIR).iterdir()) == []
    planted = [
        path for path in root.rglob("*")
        if path.is_file() and b"MODEL TEXT PLANTED HERE" in path.read_bytes()]
    assert planted == [], f"MODEL_TEXT_RETAINED={planted}"


def _portal_kind(root: Path, work_item_id: str = "work-001") -> str:
    """What the child itself recorded about the portal it tried to plant."""
    witness = root / WORK_DIR / work_item_id / _fakedsh.PORTAL_WITNESS
    return witness.read_text(encoding="utf-8") if witness.exists() else "none"


def test_a_child_that_replaces_its_own_home_leaves_no_entry_and_no_damage(tmp_path):
    """Codex's probe, driven end to end through the real adapter.

    Verbatim, at the prior SHA::

        DISCARD=refused WorkspaceNotContained
        HOME_ENTRY_EXISTS True

    The child swapped the directory this process minted for a portal, so the
    contained-route walk refused the cleanup and the entry survived pointing at
    a tree nobody here owns.
    """
    outside = _outside(tmp_path)
    adapter, root, log = a_harness(tmp_path, FAKEDSH_HOME_PORTAL=str(outside))
    before = _tree(outside)

    receipt = run_once(adapter, a_request())

    if _portal_kind(root) == "none":
        pytest.skip("this platform granted the child neither junction nor symlink")
    assert _tree(outside) == before, "OUTSIDE_DELETED=True"
    assert sorted((root / HOME_DIR).iterdir()) == [], "HOME_ENTRY_EXISTS True"
    # The cleanup succeeded, so it says nothing beyond what the spawn observed.
    assert receipt.outcome == "succeeded" and receipt.exit_code == 0
    assert len(_fakedsh.task_spawns(log)) == 1


def test_a_discard_that_cannot_happen_is_stated_and_never_rewrites_the_spawn(
        tmp_path, monkeypatch):
    """Clause (b) and (c) as one relation: stated, unmasking, and then closed.

    At the prior SHA the refusal was a bare ``pass`` and the next dispatch ran
    anyway -- Codex read ``SWEEP ('attempt',)`` and ``HOME_AFTER_SWEEP True``
    while a second task still spawned.
    """
    outside = _outside(tmp_path)
    adapter, root, log = a_harness(tmp_path, FAKEDSH_HOME_PORTAL=str(outside))
    before = _tree(outside)

    def refuses(path, found):
        raise OSError("the entry could not be removed")

    monkeypatch.setattr(harness_workspace, "_remove_portal", refuses)
    first = run_once(adapter, a_request(action_id="act-1"))
    monkeypatch.undo()
    if _portal_kind(root) == "none":
        pytest.skip("this platform granted the child neither junction nor symlink")
    spawned_first = len(_fakedsh.spawns(log))

    second = run_once(adapter, a_request(action_id="act-2", work_item_id="work-002"))

    # (b) the retention is stated, and the spawn's own outcome is left standing.
    assert first.outcome == "succeeded" and first.exit_code == 0
    assert "could not be discarded" in first.detail, f"RETENTION_SILENT={first.detail}"
    # (c) the next dispatch is blocked, and the child's own log counts the zero.
    assert second.outcome == "failed" and second.exit_code is None
    assert len(_fakedsh.spawns(log)) == spawned_first, "SPAWNED_OVER_RESIDUE=True"
    assert _tree(outside) == before, "OUTSIDE_DELETED=True"
    assert (root / HOME_DIR).exists()


@pytest.mark.parametrize("kind", PORTALS)
def test_crash_residue_the_sweep_refuses_blocks_the_next_dispatch(tmp_path, kind):
    """A home the sweep may not delete is a block, never a line nobody reads."""
    adapter, root, log = a_harness(tmp_path)
    outside = _outside(tmp_path)
    (root / HOME_DIR).mkdir()
    with skip_when_unavailable():
        plant_route_portal(root / HOME_DIR / "residue", outside, kind=kind)
    before = _tree(outside)

    receipt = run_once(adapter, a_request())

    assert _fakedsh.spawns(log) == [], "SPAWNED_OVER_RESIDUE=True"
    assert receipt.outcome == "failed" and receipt.exit_code is None
    assert (root / HOME_DIR / "residue").exists(), "RESIDUE_DELETED=True"
    assert _tree(outside) == before, "OUTSIDE_DELETED=True"
    assert not (root / MARKER_DIR / "act-1.marker").exists()


def test_the_adapter_reports_a_refusal_and_never_claims_a_marker_it_could_not_write(
        tmp_path):
    adapter, root, log = a_harness(tmp_path)
    outside = _outside(tmp_path)
    with skip_when_unavailable():
        plant_route_portal(root / MARKER_DIR, outside, kind="symlink")

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "failed"
    assert not (outside / "act-1.marker").exists(), "OUTSIDE_CREATED=True"
    assert _fakedsh.task_spawns(log) == []
    assert adapter.manifest.adapter_id == PROVIDER_ID

def test_a_preflight_whose_own_home_survives_never_starts_the_task(
        tmp_path, monkeypatch):
    """Codex's probe: the version answered, its home stayed, the task ran anyway.

    Verbatim, at the prior SHA::

        SPAWNS=2
        task spawn 1
        outcome succeeded

    The version probe is an attempt like any other -- it mints a home and must
    take it back -- and when it could not, `_retained` counted the broken promise
    and `_preflight` still answered None. So the dispatch went on to claim the
    action and spawn the real task on top of state it had just failed to remove,
    and the failure survived as a sentence appended to a `succeeded` receipt.

    The sweep cannot be what catches this: the residue is made by THIS dispatch,
    after its own sweep has already run.
    """
    adapter, root, log = a_harness(tmp_path)
    discarded = HarnessWorkspace.discard_home
    refused: list[Path] = []

    def refuses_the_first(self, home):
        """Fail the preflight's cleanup once, then let every later one work."""
        if not refused:
            refused.append(home)
            raise OSError("the preflight home could not be removed")
        return discarded(self, home)

    monkeypatch.setattr(HarnessWorkspace, "discard_home", refuses_the_first)

    receipt = run_once(adapter, a_request(action_id="act-1"))

    assert len(refused) == 1, "the preflight's own discard was never reached"
    assert len(_fakedsh.spawns(log)) == 1, "SPAWNS must be the version probe alone"
    assert _fakedsh.task_spawns(log) == [], "TASK_SPAWNED_OVER_RESIDUE=True"
    assert not (root / MARKER_DIR / "act-1.marker").exists(), "CLAIMED_OVER_RESIDUE=True"
    assert receipt.outcome == "failed" and receipt.exit_code is None
    assert "could not take back the home" in receipt.detail, receipt.detail
    # Nothing was guessed at either: the home it could not remove is left exactly
    # where it stood, for the next dispatch's sweep to meet rather than a marker.
    assert refused[0].exists(), "PREFLIGHT_HOME_DELETED_BY_GUESS=True"

# -- one owner per resolved root: the whole dispatch, never the pieces ---------


def _holds(workspace, entered, release):
    """Take one root gate, announce it, and keep it until the test lets go."""
    with workspace.owned():
        entered.set()
        release.wait(10)


def _takes_the_gate(workspace, timeout=2.0):
    """Whether this workspace can ENTER its root gate within a bounded wait."""
    entered, done = threading.Event(), threading.Event()
    thread = threading.Thread(
        target=_holds, args=(workspace, entered, done), daemon=True)
    thread.start()
    took = entered.wait(timeout)
    done.set()
    thread.join(10)
    return took


def _cleanup_that_leaves_a_residue(paused, release):
    """A `discard_home` that fails its FIRST call and holds that caller there.

    The residue it leaves is one the sweep must REFUSE rather than delete -- a
    name under the home root whose kind is not a directory -- because a home the
    sweep can simply remove lets the next dispatch proceed honestly and proves
    nothing about who owned the root.
    """
    discarded = HarnessWorkspace.discard_home
    calls: list[Path] = []

    def refuses_the_first(self, home):
        calls.append(Path(home))
        if len(calls) > 1:
            return discarded(self, home)
        shutil.rmtree(home)
        Path(home).write_text("residue no sweep may delete", encoding="utf-8")
        paused.set()
        release.wait(10)
        raise OSError("the preflight home could not be removed")

    return refuses_the_first


def _race_two_dispatches(adapter, paused, release):
    """Hold A at its failing cleanup, start B, and report whether B got in.

    The witness is B's own thread: if the root is owned for the whole dispatch,
    B cannot finish while A is held, and `is_alive` says so without asking the
    code under test anything.
    """
    outcomes: dict[str, object] = {}

    def dispatch(name, request):
        outcomes[name] = run_once(adapter, request)

    first = threading.Thread(
        target=dispatch, args=("A", a_request(action_id="act-1")), daemon=True)
    first.start()
    assert paused.wait(10), "the first dispatch never reached its failing cleanup"
    second = threading.Thread(
        target=dispatch,
        args=("B", a_request(action_id="act-2", work_item_id="work-002")),
        daemon=True)
    second.start()
    second.join(2)
    entered_while_held = not second.is_alive()
    release.set()
    first.join(20)
    second.join(20)
    return outcomes, entered_while_held


def test_a_second_dispatch_cannot_reset_the_retention_a_live_one_recorded(
        tmp_path, monkeypatch):
    """Codex's probe: one adapter, two workers, and one shared retention count.

    Verbatim, at the prior SHA::

        FIRST_OUTCOME succeeded
        FIRST_RETAINED_REPORTED False
        SECOND_OUTCOME failed
        TASK_SPAWNS 1
        HELD_HOME_EXISTS True

    A's preflight failed to take back its home and counted it. B entered the
    same adapter, zeroed that count for its own dispatch, met the residue at its
    own sweep and refused -- and A, resuming, read a zero that belonged to B and
    spawned its task over the home it had just failed to remove. The count was
    only the visible half: sweep, preflight home, task home and cleanup are one
    owner's turn over one tree, and interleaved they read each other's state.
    """
    adapter, root, log = a_harness(tmp_path)
    paused, release = threading.Event(), threading.Event()
    monkeypatch.setattr(
        HarnessWorkspace, "discard_home", _cleanup_that_leaves_a_residue(paused, release))

    outcomes, entered_while_held = _race_two_dispatches(adapter, paused, release)

    assert entered_while_held is False, "B ran inside the root A was still holding"
    # A keeps its own account: the retention it recorded is the one it reads.
    assert outcomes["A"].outcome == "failed", f"FIRST_OUTCOME {outcomes['A'].outcome}"
    assert "could not take back the home" in outcomes["A"].detail
    assert "could not be discarded" in outcomes["A"].detail, "FIRST_RETAINED_REPORTED False"
    # B meets the residue at its own sweep, once the root is free.
    assert outcomes["B"].outcome == "failed"
    assert "may not delete" in outcomes["B"].detail, outcomes["B"].detail
    assert _fakedsh.task_spawns(log) == [], "TASK_SPAWNS must be 0"
    assert (root / HOME_DIR).exists(), "HELD_HOME_EXISTS must stay True"


@pytest.mark.parametrize("kind", PORTALS)
def test_one_resolved_root_is_one_gate_and_a_second_root_is_never_held(tmp_path, kind):
    """The gate's key is what a path RESOLVED to, never how it was spelled.

    Two adapters can be configured at different names for one tree -- a junction
    or a symbolic link is a perfectly ordinary way for an operator to reach a
    project -- and they must take the same turn, because the tree they sweep and
    mint under is the same tree. A different root shares nothing and waits for
    nothing: serializing dsh must not serialize the product.
    """
    root, elsewhere, alias = tmp_path / "root", tmp_path / "elsewhere", tmp_path / "alias"
    root.mkdir()
    elsewhere.mkdir()
    with skip_when_unavailable():
        plant_route_portal(alias, root, kind=kind)
    # Two questions, and the skip used to answer both with one. Whether the OS
    # resolves this portal is a platform fact, so the OS is asked -- here, by
    # this test, with a call that reaches no product code. Whether the workspace
    # keys its gate by what the path resolved to is the property this test
    # exists for, so it is asserted.
    #
    # Merged, they were `_at(alias).root != _at(root).root`, which is the
    # negation of the assertion four lines below computed from the very door
    # under test. `at()` losing its resolution -- `.absolute()`, bare `Path()`,
    # or a `_gate_key` returning the spelled path -- made that condition true,
    # and the guard reported SKIPPED on a green suite while blaming the platform
    # for a regression the product had just introduced. Measured, with
    # `.resolve()` swapped for `.absolute()` in harness_workspace.at:
    #
    #     SKIPPED [1] this platform did not resolve a junction to its target root
    #     SKIPPED [1] this platform did not resolve a symlink to its target root
    os_resolved_alias, os_resolved_root = os.path.realpath(alias), os.path.realpath(root)
    if os_resolved_alias != os_resolved_root:
        pytest.skip(f"this OS does not resolve a {kind} to its target: "
                    f"{os_resolved_alias!r} is not {os_resolved_root!r}")
    assert _at(alias).root == _at(root).root, "ALIAS_KEYED_BY_ITS_OWN_SPELLING"
    held, release = threading.Event(), threading.Event()
    holder = threading.Thread(
        target=_holds, args=(_at(root), held, release), daemon=True)
    holder.start()
    try:
        assert held.wait(10), "the holding workspace never took its own gate"
        assert _takes_the_gate(_at(alias)) is False, "ALIAS_RAN_CONCURRENTLY"
        assert _takes_the_gate(_at(elsewhere)) is True, "SECOND_ROOT_BLOCKED"
    finally:
        release.set()
        holder.join(10)
