"""The containment gate over the preview's writable route: portals and aliases refuse.

Owner-reproduced LIVE defects (2026-08-13, on the committed SHA this round
fixes): a directory symlink or an NTFS junction standing AT
`conductor/runs/preview-run` was followed, the valid run behind it was adopted
as the preview's own, and the append landed in the EXTERNAL journal — exit 0,
0 to 609 bytes; `records.jsonl` replaced by a hard link to an empty file
outside the run carried the append into that file simultaneously — samefile
True, st_nlink 2, exit 0, 0 to 609 bytes; and with `conductor/runs` itself a
portal, a fresh run was created and filled outside the project. One class: a
name on the writable route whose content lies — or also lies — outside the
run tree, followed instead of checked, because `_points_elsewhere` was applied
only to objects INSIDE the run and never to the route that reaches it. One
door closes the class: before any durable action the preview reads every
component of the route with `os.lstat` alone — `conductor`, `runs`, the run
directory, `decisions`, and every store-owned file present — and refuses a
symlink, junction or other reparse point at any of them, and an owned file
that is not a regular file with exactly one hard link.

Each regression here asserts BOTH sides of the relation: the refusal — exit 1,
empty stdout, stderr naming the detected fact and the exact paths, the
changed-nothing statement, no advisory or destructive word — AND byte-for-byte
inertness of the found state and of the external target, via this module's own
before/after snapshots.

Self-contained on purpose: the snapshot walk reads with pathlib and os.lstat
alone, records a portal by its own target and never steps through it, and
every expected path is computed from the fixture roots — both sides of a check
may not come from one production function, and the walk under test must never
supply its own witness.
"""
import os
import re
import stat

import pytest
from conductor.__main__ import main
from conductor.command import preview
from conductor.command.contracts import DecisionReceipt, RunEnvelope
from conductor.command.run_store import RunStore, snapshot_digest


def _seed_the_previews_identity(root):
    """Create the empty, resumable run the preview would adopt as its own."""
    RunStore(root).create_run(
        RunEnvelope(run_id="preview-run", cycle_id="preview-orbit",
                    created_at="2026-08-11T00:00:00Z",
                    config_digest=snapshot_digest(preview.FROZEN_CONFIG),
                    mode="propose"),
        preview.FROZEN_CONFIG)
    return root / "conductor" / "runs" / "preview-run"


#: A junction's reparse tag; the constant exists on every platform since 3.8.
_JUNCTION_TAG = getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", 0xA0000003)


def _lies_elsewhere(path):
    """Test-local: a symbolic link, or an NTFS junction by its own reparse tag."""
    if path.is_symlink():
        return True
    return getattr(path.lstat(), "st_reparse_tag", 0) == _JUNCTION_TAG


def _tree_state(root):
    """Every durable fact under `root`: each entry's kind, and its bytes or target.

    Structure rides in the keys, so an object appearing or vanishing is a
    difference and not merely a change of content. A symbolic link and a
    junction are recorded by their own target and never entered: the snapshot
    itself must not read through an object the gate under test may not read
    through, or an append that landed behind a portal could never be told
    from one that landed in the tree.
    """
    state = {}
    stack = [root]
    while stack:
        for path in sorted(stack.pop().iterdir()):
            key = path.relative_to(root).as_posix()
            if _lies_elsewhere(path):
                state[key] = ("link", os.readlink(path))
            elif path.is_dir():
                state[key] = ("dir",)
                stack.append(path)
            else:
                state[key] = ("file", path.read_bytes())
    return state


def _junction_or_skip(link, target):
    """Make an NTFS junction — no privilege needed on Windows — or skip elsewhere."""
    try:
        import _winapi
        _winapi.CreateJunction(str(target), str(link))
    except (ImportError, AttributeError, OSError) as e:
        pytest.skip(f"this platform cannot make a junction: {e}")


def _symlink_or_skip(link, target, *, directory=False):
    """Make a symbolic link, or skip: Windows grants that privilege, it does not assume it."""
    try:
        link.symlink_to(target, target_is_directory=directory)
    except (OSError, NotImplementedError) as e:  # pragma: no cover - platform policy
        pytest.skip(f"this platform did not permit a symbolic link: {e}")


def _hard_link_or_skip(existing, new):
    """Give `existing`'s bytes the second name `new` — NTFS needs no privilege —
    or skip on a filesystem that cannot link at all."""
    try:
        os.link(existing, new)
    except OSError as e:  # pragma: no cover - platform policy
        pytest.skip(f"this filesystem did not permit a hard link: {e}")


#: Words that would promise remediation or propose a destructive command; the
#: refusal contract bans them from every refusal, the route gate's included.
_ADVICE = re.compile(
    r"\b(?:rm|mv|del|rmdir|unlink|Remove-Item|Move-Item)\b"
    r"|\b(?i:delete[ds]?|deleting|remove[ds]?|removing|move[ds]?|moving|rerun)\b")


def _named_run_dir(project):
    """The run path as the refusal must name it, from the fixture root alone.

    The PROJECT root is resolved and the components are joined below it with
    pathlib, never resolved through them: resolving the full path would step
    through the very portal under test and name the external target instead.
    """
    return project.resolve() / "conductor" / "runs" / "preview-run"


def _refused_with_both_sides_inert(project, outside, capsys):
    """Drive one preview; hold the refusal AND the inertness of both sides.

    Exit 1; stdout empty; the whole project fixture tree and the whole
    external tree each identical before and after by this module's own walk —
    which is what makes the changed-nothing words, also required here, true;
    the exact run path named; and not one advisory or destructive word.
    Returns stderr so each test can hold the facts only it knows.
    """
    project_before = _tree_state(project)
    outside_before = _tree_state(outside)
    assert main(["preview", "--dir", str(project)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert _tree_state(project) == project_before
    assert _tree_state(outside) == outside_before
    err = captured.err
    assert repr(str(_named_run_dir(project))) in err
    assert "changed nothing in the run directory" in err
    advice = _ADVICE.search(err)
    assert advice is None, f"a refusal advised {advice.group(0)!r}: {err!r}"
    return err


# --- the snapshot's own witnesses: a guard nothing exercises is vacuous ---


def test_the_tree_state_reports_new_entries_and_changed_bytes(tmp_path):
    base = tmp_path / "tree"
    (base / "sub").mkdir(parents=True)
    (base / "sub" / "a.txt").write_bytes(b"one")
    before = _tree_state(base)
    assert before == {"sub": ("dir",), "sub/a.txt": ("file", b"one")}
    (base / "b.txt").write_bytes(b"planted")
    assert set(_tree_state(base)) - set(before) == {"b.txt"}
    (base / "b.txt").unlink()
    (base / "sub" / "a.txt").write_bytes(b"two")
    assert _tree_state(base) != before  # same paths, different bytes


def test_the_tree_state_records_a_portal_by_its_target_and_never_reads_through_it(
        tmp_path):
    base = tmp_path / "tree"
    base.mkdir()
    target = tmp_path / "elsewhere"
    target.mkdir()
    (target / "inside.txt").write_bytes(b"content that lies elsewhere")
    _junction_or_skip(base / "portal", target)
    state = _tree_state(base)
    kind, pointed = state["portal"]
    assert kind == "link" and str(target) in pointed
    assert "portal/inside.txt" not in state  # never entered


# --- the owner's portal scenarios, and the same relation one and two levels up ---


#: Every directory component of the writable route below the project root, by
#: the path parts a test plants a portal at. Six cases — three spots by two
#: portal kinds — one relation: the component is read, never followed.
_PORTAL_SPOTS = {
    "the conductor directory": ("conductor",),
    "the runs root": ("conductor", "runs"),
    "the run boundary": ("conductor", "runs", "preview-run"),
}


@pytest.mark.parametrize("kind", ["junction", "symlink"])
@pytest.mark.parametrize("spot", sorted(_PORTAL_SPOTS))
def test_a_portal_on_the_writable_route_is_refused_and_nothing_lands_behind_it(
        spot, kind, tmp_path, capsys):
    """A route component that points elsewhere refuses before anything durable.

    At the run boundary the portal's target is a VALID resumable run — the
    owner's exact reproduction, where the baseline adopted it and grew its
    journal 0 to 609 bytes with exit 0. One and two levels up the target is an
    empty external directory, where the baseline materialized a fresh run
    outside the project with exit 0. Born red on each of those exit-0 roads;
    the refusal must name the portal's own path and the detected kind, and
    both trees — the project's and the external target's — must be
    byte-for-byte and structurally as planted.
    """
    project = tmp_path / "project"
    outside = tmp_path / "outside"
    parts = _PORTAL_SPOTS[spot]
    if spot == "the run boundary":
        target = _seed_the_previews_identity(outside)
        assert (target / "records.jsonl").read_bytes() == b""
    else:
        outside.mkdir()
        target = outside
    link = project.joinpath(*parts)
    link.parent.mkdir(parents=True, exist_ok=True)
    if kind == "junction":
        _junction_or_skip(link, target)
    else:
        _symlink_or_skip(link, target, directory=True)
    err = _refused_with_both_sides_inert(project, outside, capsys)
    assert repr(str(project.resolve().joinpath(*parts))) in err
    assert ("a directory junction" if kind == "junction"
            else "a symbolic link") in err


# --- MAJOR-2: hard-link laundering through a permitted, writable name ---


def test_a_journal_hard_linked_to_a_file_outside_the_run_is_refused_unappended(
        tmp_path, capsys):
    """An alias under the allowed name `records.jsonl` is not the store's own file.

    The owner's exact reproduction: the baseline accepted the aliased journal
    as its own and the append landed simultaneously in the external file —
    samefile True, st_nlink 2, exit 0, the alias grown 0 to 609 bytes. Born
    red on that exit-0 road. The refusal must name the journal's exact path
    and the detected link count, and the external alias must still hold zero
    bytes.
    """
    project = tmp_path / "project"
    outside = tmp_path / "outside"
    outside.mkdir()
    alias = outside / "laundered.jsonl"
    alias.write_bytes(b"")
    journal = _seed_the_previews_identity(project) / "records.jsonl"
    journal.unlink()
    _hard_link_or_skip(alias, journal)
    assert os.path.samefile(journal, alias)
    assert os.lstat(journal).st_nlink == 2
    err = _refused_with_both_sides_inert(project, outside, capsys)
    assert repr(str(_named_run_dir(project) / "records.jsonl")) in err
    assert "2 hard links" in err
    assert alias.read_bytes() == b""  # the external side of MAJOR-2, still empty


def test_an_envelope_hard_linked_outside_the_run_is_refused_before_adoption(
        tmp_path, capsys):
    """The door is the route, not the journal's name: `run.json` is held to it too.

    This run replays cleanly — envelope matched, history empty — so the
    baseline ADOPTED it and appended, exit 0, with the envelope's bytes
    answering to an external name the preview cannot see. Born red on that
    exit-0 road; the same one mechanism refuses it, because an owned file
    with two names is judged by the relation, not by which name it wears.
    """
    project = tmp_path / "project"
    outside = tmp_path / "outside"
    outside.mkdir()
    envelope = _seed_the_previews_identity(project) / "run.json"
    _hard_link_or_skip(envelope, outside / "kept-envelope.json")
    assert os.lstat(envelope).st_nlink == 2
    err = _refused_with_both_sides_inert(project, outside, capsys)
    assert repr(str(_named_run_dir(project) / "run.json")) in err
    assert "2 hard links" in err


def test_a_receipt_hard_linked_outside_the_run_is_named_by_the_route_gate(
        tmp_path, capsys):
    """A `decisions/*.json` receipt is a store-written name, so the gate holds it.

    The baseline already refused this run — a decision is not the preview's
    own history — so this regression is red on the message, not the exit
    code: nothing at baseline named the alias, and a refusal that reads the
    receipt's content has already opened a file whose bytes also stand
    outside the run. The gate must name the receipt's exact path and the
    detected link count before the store opens anything.
    """
    project = tmp_path / "project"
    outside = tmp_path / "outside"
    outside.mkdir()
    run_dir = _seed_the_previews_identity(project)
    RunStore(project).append(DecisionReceipt(
        receipt_id="foreign-receipt", run_id="preview-run", gate_id="foreign-gate",
        action="approve", actor="someone-else", decided_at="2026-08-11T00:00:00Z",
        reason="a gate this preview never opened", scope_refs=("src",),
        config_digest=snapshot_digest(preview.FROZEN_CONFIG)))
    receipt = run_dir / "decisions" / "foreign-receipt.json"
    _hard_link_or_skip(receipt, outside / "kept-receipt.json")
    assert os.lstat(receipt).st_nlink == 2
    err = _refused_with_both_sides_inert(project, outside, capsys)
    assert repr(str(_named_run_dir(project) / "decisions" / "foreign-receipt.json")) in err
    assert "2 hard links" in err


# --- a portal at `decisions`: a route component gone, not clutter beside one ---


def test_a_decisions_directory_that_is_a_portal_is_refused_as_the_route(
        tmp_path, capsys):
    """A symlinked `decisions` is refused before the store opens anything behind it.

    The baseline refused this run too — the ownership walk names any link it
    meets — but only after `read` had already globbed receipts THROUGH the
    portal, so this regression is red on the message: the route entry and its
    detected kind were never said. The gate now speaks first, on lstat alone.
    """
    project = tmp_path / "project"
    outside = tmp_path / "outside"
    outside.mkdir()
    run_dir = _seed_the_previews_identity(project)
    (run_dir / "decisions").rmdir()
    _symlink_or_skip(run_dir / "decisions", outside, directory=True)
    err = _refused_with_both_sides_inert(project, outside, capsys)
    assert repr(str(_named_run_dir(project) / "decisions")) in err
    assert "route:" in err and "a symbolic link" in err
