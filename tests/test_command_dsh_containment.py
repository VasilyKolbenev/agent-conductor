"""The dsh workspace's writable routes are contained BEFORE every write.

Codex drove one probe at the prior SHA and it is the whole reason this module
exists:

    root/.dsh-home -> outside
    DshWorkspace.mint_home("attempt")
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
from pathlib import Path

import pytest

import conductor.command.adapters.dsh_workspace as dsh_workspace
from conductor.command.adapters.dsh_workspace import (
    HOME_DIR,
    MARKER_DIR,
    WORK_DIR,
    DshWorkspace,
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


def _rooted(tmp_path: Path) -> tuple[DshWorkspace, Path]:
    root = tmp_path / "root"
    root.mkdir()
    return DshWorkspace.at(root), root


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

    monkeypatch.setattr(dsh_workspace, "_remove_portal", refuses)
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
