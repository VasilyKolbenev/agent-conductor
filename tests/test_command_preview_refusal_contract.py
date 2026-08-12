"""The refusal contract of `conduct preview`: facts, exact paths, and no advice.

Owner decision 2026-08-12 narrowed the remediation contract: a refusal that
declines a run directory the preview found or failed to read — and a store-level
creation failure — holds six points, every one by execution here. Exit code 1;
an empty stdout; the run tree byte for byte and structurally unchanged, links
included; stderr naming what was reliably detected, the exact preview-run path
and the exact paths of foreign objects where they are reliably established, and
stating in so many words that the preview changed nothing in the run directory;
no remediation promise and no destructive command; and, where StoreError or
CorruptRun prevents establishing what a local object is, the stated limit that
no safe automatic remediation is defined. Accuracy over pseudo-actionability:
the preview does not guess which object a human should delete, so no message
may advise deleting or moving anything.

Self-contained on purpose: the immutability snapshot below is this module's own
walk — structure, bytes and link targets, read with pathlib and os.lstat alone,
never with the production `snapshot_digest` — so the check cannot be satisfied
by the very code it judges. Expected paths are computed from the fixture root,
never from the production function whose message they check.

The changed-nothing words are additionally held road-wide at the bottom of this
module, as a relation rather than a presence: they must appear exactly when the
call refused AND a before/after snapshot of the exact run path is identical, so
a road that creates the run and then refuses may not carry them.
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
    """Create a run the preview would resume as its own; each test plants one flaw."""
    RunStore(root).create_run(
        RunEnvelope(run_id="preview-run", cycle_id="preview-orbit",
                    created_at="2026-08-11T00:00:00Z",
                    config_digest=snapshot_digest(preview.FROZEN_CONFIG), mode="propose"),
        preview.FROZEN_CONFIG)
    return root / "conductor" / "runs" / "preview-run"


def _run_dir(root):
    """The path the preview's run occupies under `root`, computed with pathlib alone.

    Never `RunStore.run_path`: the message under test was rendered through that
    function, and both sides of a check may not be computed by one production
    function.
    """
    return (root / "conductor" / "runs" / "preview-run").resolve()


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
    junction are recorded by their own target and never entered — the snapshot
    itself must not read through an object the production walk may not read
    through, or planting content behind a portal could never be told from
    planting it in the run.
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


#: Words that would promise remediation or propose a destructive command. The
#: contract bans them from every refusal: no rm, no Remove-Item, no mv, no
#: advice to delete or move anything, no promise that rerunning helps.
_ADVICE = re.compile(
    r"\b(?:rm|mv|del|rmdir|unlink|Remove-Item|Move-Item)\b"
    r"|\b(?i:delete[ds]?|deleting|remove[ds]?|removing|move[ds]?|moving|rerun)\b")


def _refusal_holding_the_contract(root, capsys, *, watched=None):
    """Refuse, and hold every contract point one call can hold; return stderr.

    Exit 1; stdout empty; the tree under `watched` (default: the whole runs
    directory) identical before and after by this module's own walk; the exact
    run path named; the changed-nothing statement present — paired here with
    the snapshot that makes it true — and not one advisory or destructive word.
    """
    watched = watched if watched is not None else root / "conductor" / "runs"
    before = _tree_state(watched)
    assert main(["preview", "--dir", str(root)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert _tree_state(watched) == before
    err = captured.err
    assert repr(str(_run_dir(root))) in err
    assert "changed nothing in the run directory" in err
    advice = _ADVICE.search(err)
    assert advice is None, f"a refusal advised {advice.group(0)!r}: {err!r}"
    return err


# --- the snapshot's own witnesses: a guard nothing exercises is vacuous ---


def test_the_tree_state_reports_new_entries_changed_bytes_and_lost_structure(tmp_path):
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
    (base / "sub" / "a.txt").write_bytes(b"one")
    (base / "sub" / "empty").mkdir()
    assert set(_tree_state(base)) - set(before) == {"sub/empty"}  # structure alone


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
    # Retargeting the portal is a difference even when every byte elsewhere agrees.
    twin = tmp_path / "elsewhere-twin"
    twin.mkdir()
    (twin / "inside.txt").write_bytes(b"content that lies elsewhere")
    os.rmdir(base / "portal")
    _junction_or_skip(base / "portal", twin)
    assert _tree_state(base) != state


# --- closure A: an orphan decisions receipt the preview never minted ---


def test_an_orphan_decisions_receipt_refuses_the_run_with_facts_and_no_advice(
        tmp_path, capsys):
    """A decisions/*.json the preview never minted refuses the run on stated facts.

    The receipt is orphaned — its journal line blanked away — so it reaches the
    refusal as the replay's own warning and as a history the preview never
    wrote. The message names the receipt and the run path, states that nothing
    was changed, and proposes nothing: not the receipt's deletion, not the
    run's.
    """
    run_dir = _seed_the_previews_identity(tmp_path)
    RunStore(tmp_path).append(DecisionReceipt(
        receipt_id="foreign-receipt", run_id="preview-run", gate_id="foreign-gate",
        action="approve", actor="someone-else", decided_at="2026-08-11T00:00:00Z",
        reason="a gate this preview never opened", scope_refs=("src",),
        config_digest=snapshot_digest(preview.FROZEN_CONFIG)))
    (run_dir / "records.jsonl").write_bytes(b"")
    err = _refusal_holding_the_contract(tmp_path, capsys)
    assert "foreign-receipt" in err


# --- closure B: a receipt-looking name nested deeper than the store writes ---


def test_a_receipt_named_file_nested_below_decisions_is_named_by_its_exact_path(
        tmp_path, capsys):
    """`decisions/sub/x.json` is foreign however receipt-like its name reads.

    The store writes receipts directly in `decisions/` and nowhere deeper, and
    its replay never opens this file — the independent read below proves the
    run replays clean — so only the ownership walk can refuse it, and it must
    name the exact path, not the basename a receipt would have.
    """
    run_dir = _seed_the_previews_identity(tmp_path)
    nested = run_dir / "decisions" / "sub"
    nested.mkdir()
    (nested / "x.json").write_bytes(b"{}")
    found = RunStore(tmp_path).read("preview-run")
    assert found.records == () and found.warnings == ()
    err = _refusal_holding_the_contract(tmp_path, capsys)
    assert repr(str(_run_dir(tmp_path) / "decisions" / "sub" / "x.json")) in err


# --- closures C and D: links and junctions, dangling and directory-pointed ---


def test_a_dangling_symlink_inside_the_run_is_named_by_its_exact_path(
        tmp_path, capsys):
    run_dir = _seed_the_previews_identity(tmp_path)
    _symlink_or_skip(run_dir / "stray-link", tmp_path / "nowhere")
    err = _refusal_holding_the_contract(tmp_path, capsys)
    assert repr(str(_run_dir(tmp_path) / "stray-link")) in err


def test_a_junction_refuses_the_run_even_when_its_target_holds_nothing(
        tmp_path, capsys):
    """An empty-target junction answers is_dir True and is_symlink False, and hides.

    Established by execution on this interpreter: a walk that skips plain
    directories and recurses with rglob adopts exactly this object silently —
    nothing lies behind it for the recursion to name — and the preview would
    append into the run. The junction itself must refuse the run, by name.
    """
    run_dir = _seed_the_previews_identity(tmp_path)
    (tmp_path / "elsewhere").mkdir()
    _junction_or_skip(run_dir / "portal", tmp_path / "elsewhere")
    assert (run_dir / "portal").is_dir() and not (run_dir / "portal").is_symlink()
    err = _refusal_holding_the_contract(tmp_path, capsys)
    assert repr(str(_run_dir(tmp_path) / "portal")) in err


@pytest.mark.parametrize("kind", ["junction", "symlink"])
def test_a_directory_portal_is_named_by_its_own_path_and_never_entered(
        kind, tmp_path, capsys):
    """A junction or directory symlink is one foreign object, not a door to walk.

    What lies behind it lies outside the run: naming content through the portal
    would name objects this refusal has no standing over, and reading through
    it would judge bytes the run directory does not hold. So the portal is
    named by its own exact path, its content goes unmentioned, and the target
    tree survives the refusal untouched.
    """
    run_dir = _seed_the_previews_identity(tmp_path)
    target = tmp_path / "elsewhere"
    target.mkdir()
    (target / "inside.txt").write_bytes(b"content that lies elsewhere")
    if kind == "junction":
        _junction_or_skip(run_dir / "portal", target)
    else:
        _symlink_or_skip(run_dir / "portal", target, directory=True)
    outside_before = _tree_state(target)
    err = _refusal_holding_the_contract(tmp_path, capsys)
    assert repr(str(_run_dir(tmp_path) / "portal")) in err
    assert "inside.txt" not in err
    assert _tree_state(target) == outside_before


# --- closure E: several foreign objects at once, each named by its exact path ---


def test_every_reliably_established_foreign_object_is_named_when_several_stand_together(
        tmp_path, capsys):
    run_dir = _seed_the_previews_identity(tmp_path)
    (run_dir / "stray.bin").write_bytes(b"one")
    (run_dir / "decisions" / "sub").mkdir()
    (run_dir / "decisions" / "sub" / "x.json").write_bytes(b"{}")
    (run_dir / "nested").mkdir()
    (run_dir / "nested" / "blob.bin").write_bytes(b"two")
    err = _refusal_holding_the_contract(tmp_path, capsys)
    named = _run_dir(tmp_path)
    for foreign in ("stray.bin", "decisions/sub/x.json", "nested/blob.bin"):
        assert repr(str(named.joinpath(*foreign.split("/")))) in err


# --- closure F: corruption and foreign objects simultaneously ---


def test_a_ragged_tail_and_a_foreign_object_are_both_told_in_one_refusal(
        tmp_path, capsys):
    """When the replay still answers, its warning and the foreign path both reach stderr.

    The tail is the store's to warn about and the stray file is the walk's to
    name; a refusal that spoke only the first would hide a fact it reliably
    holds, and one that spoke only the second would adopt unjudged journal
    bytes into silence.
    """
    run_dir = _seed_the_previews_identity(tmp_path)
    (run_dir / "records.jsonl").write_bytes(b'{"record_type":"partial')
    (run_dir / "stray.bin").write_bytes(b"beside the ragged journal")
    found = RunStore(tmp_path).read("preview-run")
    assert found.warnings  # the replay itself still answers, warning as it does
    err = _refusal_holding_the_contract(tmp_path, capsys)
    assert all(warning in err for warning in found.warnings)
    assert repr(str(_run_dir(tmp_path) / "stray.bin")) in err


def test_corruption_the_store_raises_on_still_names_the_limit_beside_a_foreign_object(
        tmp_path, capsys):
    """When the store raises, the refusal owes the limit and the path, not a guess.

    With `run.json` unreadable, nothing can safely establish what the stray
    file beside it is to this run, so the message does not enumerate it; it
    names what was reliably detected, the run path, and the stated limit —
    no safe automatic remediation is defined.
    """
    run_dir = _seed_the_previews_identity(tmp_path)
    (run_dir / "run.json").write_bytes(b"{ this is not json")
    (run_dir / "stray.bin").write_bytes(b"beside the corrupt envelope")
    err = _refusal_holding_the_contract(tmp_path, capsys)
    assert "run.json" in err
    assert "no safe automatic remediation is defined" in err
    assert "investigate" in err


# --- closure G: StoreError/CorruptRun raised directly by the store ---


def test_a_run_whose_envelope_is_invalid_json_is_refused_at_the_stated_limit(
        tmp_path, capsys):
    run_dir = _seed_the_previews_identity(tmp_path)
    (run_dir / "run.json").write_bytes(b"{ this is not json")
    err = _refusal_holding_the_contract(tmp_path, capsys)
    assert "run.json" in err
    assert "no safe automatic remediation is defined" in err


def test_a_file_standing_at_the_runs_own_path_is_not_reported_as_nonexistent(
        tmp_path, capsys):
    """What stands at the identity exists; the message may not say the opposite.

    A FILE at `conductor/runs/preview-run` makes creation refuse (the name is
    claimed) and replay refuse (no directory to read) — and the store's own
    sentence for the second, "does not exist", is the opposite of the truth
    here. The refusal states what was reliably detected instead: the path is
    claimed, and no replayable run directory stands at it.
    """
    runs = tmp_path / "conductor" / "runs"
    runs.mkdir(parents=True)
    (runs / "preview-run").write_bytes(b"a file standing where the run would")
    err = _refusal_holding_the_contract(tmp_path, capsys)
    assert "does not exist" not in err
    assert "not a run directory" in err
    assert "no safe automatic remediation is defined" in err


# --- the scope guard's last road: store-level creation failure ---


def test_a_creation_failure_refuses_with_facts_and_leaves_the_whole_tree_unchanged(
        tmp_path, capsys):
    """A run store that cannot create the run is a refusal, not a traceback.

    With a FILE standing at `conductor/runs`, creation fails before one byte is
    staged. The contract still holds: exit 1, stdout empty, nothing anywhere
    changed — the snapshot here watches the whole fixture tree, since no run
    directory exists to scope to — and stderr names the run path the preview
    could not claim, without advising anything.
    """
    (tmp_path / "conductor").mkdir()
    (tmp_path / "conductor" / "runs").write_bytes(b"not a directory")
    err = _refusal_holding_the_contract(tmp_path, capsys, watched=tmp_path)
    assert "detected" in err


# --- the changed-nothing words, held road-wide as a measured relation ---
#
# The words `changed nothing in the run directory` are a claim about what one
# call did, so their presence may not be pinned road by road: the expected side
# below is derived, per driven road, from a snapshot of the exact run path taken
# before and after the call by this module's own walk. The pre-existing-run
# service refusals — e.g. an adapter mismatch on a run already standing — are
# not driven here.


_CHANGED_NOTHING = "changed nothing in the run directory"


def _run_path_state(path):
    """Test-local state of the exact run path: absent, a portal, a file, or its tree.

    Absence is a state of its own, not an error: on the creation roads the path
    is not there before the call, and whether it is there after is precisely
    what the relation needs to see. A portal at the path is recorded by its
    target and never entered, on the ground `_tree_state` states for entries.
    """
    if not os.path.lexists(path):
        return ("absent",)
    if _lies_elsewhere(path):
        return ("link", os.readlink(path))
    if path.is_dir():
        return ("dir", _tree_state(path))
    return ("file", path.read_bytes())


def _drive_holding_the_phrase_to_the_snapshot(root, capsys, *argv):
    """Drive one preview call and hold the changed-nothing words to the relation.

    The one guard every road below shares: the words appear on stderr exactly
    when the call both refused (exit 1) and left the exact run path — its state
    snapshotted before and after by `_run_path_state`, never by production code
    — as it was found. The expected side is derived from that measurement, not
    picked per road. Returns the exit code, both snapshots and the captured
    streams, so each road can witness what it additionally knows.
    """
    run_path = root / "conductor" / "runs" / "preview-run"
    before = _run_path_state(run_path)
    code = main(["preview", "--dir", str(root), *argv])
    captured = capsys.readouterr()
    after = _run_path_state(run_path)
    expected = code == 1 and before == after
    present = _CHANGED_NOTHING in captured.err
    assert present == expected, (
        "the changed-nothing words must ride exactly the refusals that hold "
        f"them true: exit {code}, run path "
        f"{'unchanged' if before == after else 'changed'}, phrase "
        f"{'present' if present else 'absent'} in {captured.err!r}")
    return code, before, after, captured


def test_the_run_path_state_tells_absence_a_file_and_a_tree_apart(tmp_path):
    spot = tmp_path / "spot"
    assert _run_path_state(spot) == ("absent",)
    spot.write_bytes(b"a file where the run would stand")
    assert _run_path_state(spot) == ("file", b"a file where the run would stand")
    spot.unlink()
    spot.mkdir()
    (spot / "a.txt").write_bytes(b"one")
    assert _run_path_state(spot) == ("dir", {"a.txt": ("file", b"one")})


def test_the_run_path_state_records_a_portal_at_the_path_without_entering_it(tmp_path):
    target = tmp_path / "elsewhere"
    target.mkdir()
    (target / "inside.txt").write_bytes(b"content that lies elsewhere")
    _junction_or_skip(tmp_path / "spot", target)
    kind, pointed = _run_path_state(tmp_path / "spot")
    assert kind == "link" and str(target) in pointed


def test_a_successful_creation_says_no_phrase_and_the_snapshot_sees_the_run_appear(
        tmp_path, capsys):
    """Exit 0 and a run path gone from absent to a tree: no refusal, no phrase.

    This road doubles as the witness that the snapshot machinery sees change:
    were `_run_path_state` blind, `before != after` could not hold here.
    """
    code, before, after, captured = _drive_holding_the_phrase_to_the_snapshot(
        tmp_path, capsys)
    assert code == 0
    assert before == ("absent",) and after[0] == "dir"
    assert captured.err == ""


def test_reopening_the_previews_own_run_says_no_phrase_and_leaves_the_path_as_it_was(
        tmp_path, capsys):
    """Exit 0 on the reopen and a snapshot identical before and after.

    The witness that the machinery sees no-change where there is none: the
    reopen writes nothing, and the relation requires the phrase absent all the
    same, because the exit code is 0.
    """
    assert main(["preview", "--dir", str(tmp_path)]) == 0
    capsys.readouterr()
    code, before, after, _ = _drive_holding_the_phrase_to_the_snapshot(
        tmp_path, capsys)
    assert code == 0
    assert before[0] == "dir" and before == after


def test_a_service_refusal_that_created_the_run_does_not_claim_it_changed_nothing(
        tmp_path, capsys):
    """An unknown instance is refused downstream of creation: the run appears, exit 1.

    The road where exit 1 and a changed run path meet: `create_run` succeeds,
    then the service refuses the instance in its own words, so the
    changed-nothing words would be false and the relation requires their
    absence. The service refusal of a run already standing (an adapter
    mismatch, say) is a different road, not driven here.
    """
    code, before, after, captured = _drive_holding_the_phrase_to_the_snapshot(
        tmp_path, capsys, "--instance", "unknown-instance")
    assert code == 1
    assert before == ("absent",) and after[0] == "dir"  # this very call made the run
    assert captured.out == ""


def test_a_foreign_object_refusal_says_the_phrase_the_snapshot_measures_true(
        tmp_path, capsys):
    run_dir = _seed_the_previews_identity(tmp_path)
    (run_dir / "stray.bin").write_bytes(b"foreign, and left exactly as found")
    code, before, after, _ = _drive_holding_the_phrase_to_the_snapshot(
        tmp_path, capsys)
    assert code == 1 and before == after


def test_an_unreplayable_run_refusal_says_the_phrase_the_snapshot_measures_true(
        tmp_path, capsys):
    run_dir = _seed_the_previews_identity(tmp_path)
    (run_dir / "run.json").write_bytes(b"{ this is not json")
    code, before, after, _ = _drive_holding_the_phrase_to_the_snapshot(
        tmp_path, capsys)
    assert code == 1 and before == after


def test_an_uncreatable_run_path_refusal_says_the_phrase_with_the_path_absent_throughout(
        tmp_path, capsys):
    """A FILE at `conductor/runs` fails creation below the run path itself.

    The exact run path is absent before and absent after — absence being a
    state the snapshot records — so the relation requires the phrase, exactly
    as the refusal owes it.
    """
    (tmp_path / "conductor").mkdir()
    (tmp_path / "conductor" / "runs").write_bytes(b"not a directory")
    code, before, after, _ = _drive_holding_the_phrase_to_the_snapshot(
        tmp_path, capsys)
    assert code == 1
    assert before == ("absent",) and after == ("absent",)
