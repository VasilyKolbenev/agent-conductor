"""What the preview does with a journal that stops mid-record, and with a link.

Split out of ``test_command_preview`` when that module crossed the line cap,
along the seam the house rule names. The circuit that moved is one subject: a
run at the preview's identity whose durable bytes are INCOMPLETE or whose route
holds an object the store does not own. The identity tests it left behind ask a
different question -- whether a whole, readable run is the preview's own -- and
the two share only the named helpers imported below.

Every expected side is still produced the same way it was: by running the real
command in a directory the refusing test never touches, so no check has both of
its sides from one place.
"""
from __future__ import annotations

import os
import shutil

import pytest

from conductor.__main__ import main
from conductor.command import preview
from conductor.command.contracts import DecisionReceipt, RunEnvelope, canonical_json
from conductor.command.run_store import RunStore, snapshot_digest

from tests.test_command_preview import (
    _FOREIGN_CONFIG,
    _durable_snapshot,
    _named_run_path,
    _refuses_and_leaves_the_run_directory_untouched,
    _refusal_sides,
    _seed_run_at_the_previews_identity,
    _the_previews_own_envelope,
    _the_previews_own_history,
    a_project,
)


# --- CMD-4 MAJOR-B: an incomplete crash tail is not a history the preview may adopt ---
#
# `RunStore.read` replays read-only, so a journal ending mid-record keeps those bytes
# where they lie and the incomplete tail is reported as a WARNING rather than as a
# record. Judging a found run by its replayed records alone therefore reads a
# permitted history out of a journal that still carries unjudged bytes — and the
# first append goes through the repairing store, which truncates them away. The run
# is adopted, the proposal lands in it, and durable bytes the preview never wrote are
# silently gone. So any warning at all from the read-only replay refuses the run,
# before one byte is appended.


def _the_previews_own_record_bytes(root, capsys):
    """The exact journal line a genuine `conduct preview` writes, terminator included."""
    assert main(["preview", "--dir", str(a_project(root))]) == 0
    capsys.readouterr()
    return (root / "conductor" / "runs" / "preview-run" / "records.jsonl").read_bytes()


#: Incomplete final fragments a crash mid-append can leave, built from the record the
#: preview itself would write. The last two are the ones that matter: the preview's
#: own intent whole but unterminated, and a strict prefix of it. Were "the tail looks
#: like mine" ever enough, those two would be adopted — and a tail is evidence of what
#: some writer intended, never of which writer it was.
_TAILS = {
    "foreign bytes": lambda own: b'{"record_type":"foreign-partial"',
    "the preview's own record, unterminated": lambda own: own.rstrip(b"\n"),
    "a strict prefix of the preview's own record": lambda own: own[:len(own) // 2],
}


@pytest.mark.parametrize("tail", sorted(_TAILS))
def test_preview_refuses_an_otherwise_empty_run_whose_journal_ends_mid_record(
        tail, tmp_path, capsys):
    """What may be resumed is an EMPTY journal, not a journal that REPLAYS as empty.

    A run created and never appended to is the preview's own to resume, and the
    records replayed out of this one say exactly that — because `read` dropped the
    unterminated tail from what it returns and left it on disk for its writer. Resume
    it and the very next append runs the repairing store over those bytes and deletes
    them: durable bytes this preview never wrote, changed by this preview.
    """
    own_line = _the_previews_own_record_bytes(tmp_path / "own", capsys)
    journal = _seed_run_at_the_previews_identity(
        tmp_path, cycle_id="preview-orbit", config=preview.FROZEN_CONFIG, mode="propose")
    journal.write_bytes(_TAILS[tail](own_line))
    # The replayed records are the empty history the preview is allowed to resume:
    # nothing but the warning stands between this run and an append into it.
    found = RunStore(tmp_path).read("preview-run")
    assert found.records == ()
    err = _refuses_and_leaves_the_run_directory_untouched(tmp_path, capsys)
    # And the refusal says what the store said, taken from the store rather than
    # written down here, so the two cannot drift into naming different complaints.
    assert found.warnings and all(warning in err for warning in found.warnings)


@pytest.mark.parametrize("tail", sorted(_TAILS))
def test_preview_refuses_its_own_completed_run_whose_journal_ends_mid_record(
        tail, tmp_path, capsys):
    """The completed history the preview owns does not vouch for bytes written after it.

    Reopening its own finished run is free — the proposal is immutable and the store
    recognises the retry — and this is the one thing that freedom does not extend to:
    bytes past the record it wrote. They replay away into a warning, leaving a history
    that is the preview's own to the letter, so this run is adopted on exactly the
    same evidence as a genuine reopen unless the warning itself refuses it.
    """
    own_line = _the_previews_own_record_bytes(tmp_path / "own", capsys)
    journal = _seed_run_at_the_previews_identity(
        tmp_path, cycle_id="preview-orbit", config=preview.FROZEN_CONFIG, mode="propose")
    journal.write_bytes(own_line + _TAILS[tail](own_line))
    # Record for record the preview's own, compared against a run production wrote in
    # a directory this one never touched — the permitted history, not a lookalike.
    found = RunStore(tmp_path).read("preview-run")
    assert ([row.value for row in found.records]
            == [row.value for row in RunStore(tmp_path / "own").read("preview-run").records])
    err = _refuses_and_leaves_the_run_directory_untouched(tmp_path, capsys)
    assert found.warnings and all(warning in err for warning in found.warnings)


#: Files a run directory can hold that `RunStore.read` never opens: it reads
#: `run.json`, `config.json`, `records.jsonl` and `decisions/*.json` and nothing
#: else. The first is the signature of a writer that crashed inside its own
#: publish — the same unfinished durable bytes an incomplete tail is, reaching the
#: preview without a warning to announce them, because no reader looked.
_UNOWNED_FILES = {
    "a staging file a crashed writer left inside the run":
        ".records.jsonl.7f3a.tmp",
    "a foreign file beside the journal": "stray.bin",
    "a non-receipt file under decisions/": "decisions/notes.txt",
}


@pytest.mark.parametrize("planted", sorted(_UNOWNED_FILES))
def test_preview_refuses_a_run_holding_a_file_the_store_does_not_own(
        planted, tmp_path, capsys):
    """Unjudged durable bytes reach the preview without a warning when nobody reads them.

    The warning check above catches unfinished bytes the store SAW and declined to
    touch. These are unfinished bytes the store never looked at: `read` opens four
    names and no others, so a `.records.jsonl.<rand>.tmp` — exactly what a writer
    that died inside `_exclusive_bytes` or `_replace_bytes` leaves — replays as a
    flawless, permitted, warning-free history. Adopting that run is the same class
    MAJOR-B closes, reached by a door the replay cannot see through.
    """
    _seed_run_at_the_previews_identity(
        tmp_path, cycle_id="preview-orbit", config=preview.FROZEN_CONFIG, mode="propose")
    name = _UNOWNED_FILES[planted]
    tmp_path.joinpath("conductor", "runs", "preview-run", *name.split("/")).write_bytes(
        b"bytes only their writer can finish")
    # Every fact the replay can state is one the preview may resume: the empty
    # history it created for itself, and not one warning. The file alone refuses.
    found = RunStore(tmp_path).read("preview-run")
    assert found.records == () and found.warnings == ()
    err = _refuses_and_leaves_the_run_directory_untouched(tmp_path, capsys)
    assert repr(str(_named_run_path(tmp_path).joinpath(*name.split("/")))) in err


def test_removing_a_ragged_run_out_of_band_lets_the_preview_create_a_fresh_one(
        tmp_path, capsys):
    """The refusal advises nothing; this holds what an operator can still do anyway.

    A ragged journal is refused permanently at a fixed id, and the message names
    the run's exact path without proposing any way out — the owner's contract
    (2026-08-12) trades pseudo-actionability for accuracy, and the message side
    of it lives in tests/test_command_preview_refusal_contract.py. What survives
    here as a behavioral regression is the system property underneath: the
    preview neither adopts, repairs nor blocks the refused directory, so an
    operator who removes it out of band gets a fresh run on the next preview,
    byte for byte the one a genuine preview writes anywhere.
    """
    genuine = _the_previews_own_record_bytes(tmp_path / "own", capsys)
    journal = _seed_run_at_the_previews_identity(
        tmp_path, cycle_id="preview-orbit", config=preview.FROZEN_CONFIG, mode="propose")
    journal.write_bytes(genuine.rstrip(b"\n"))
    err = _refuses_and_leaves_the_run_directory_untouched(tmp_path, capsys)
    named = _named_run_path(tmp_path)
    assert repr(str(named)) in err
    # The removal is this test's own act, advised by nobody: the identity freed,
    # the preview writes the same journal it writes into a directory it has
    # never seen.
    shutil.rmtree(named)
    assert main(["preview", "--dir", str(a_project(tmp_path))]) == 0
    capsys.readouterr()
    assert journal.read_bytes() == genuine


def test_the_refusal_names_every_warning_when_one_replay_reports_two(tmp_path, capsys):
    """More than one warning is reachable, and naming only the first would hide one.

    A run can hold an orphan `decisions/` receipt AND a journal that ends
    mid-record, and `RunStore.read` reports both. Every refusal above is seeded to
    produce exactly one warning, so `differences.extend(...)` could be narrowed to
    `differences.append(found.warnings[0])` with all of them still green — the
    relation they hold (every warning the store named appears in the refusal) is
    only worth something once a fixture makes the store name two.
    """
    own_line = _the_previews_own_record_bytes(tmp_path / "own", capsys)
    journal = _seed_run_at_the_previews_identity(
        tmp_path, cycle_id="preview-orbit", config=preview.FROZEN_CONFIG, mode="propose")
    RunStore(tmp_path).append(DecisionReceipt(
        receipt_id="foreign-receipt", run_id="preview-run", gate_id="foreign-gate",
        action="approve", actor="someone-else", decided_at="2026-08-11T00:00:00Z",
        reason="a gate this preview never opened", scope_refs=("src",),
        config_digest=snapshot_digest(preview.FROZEN_CONFIG)))
    # The receipt's journal line replaced by an unterminated one: the receipt is
    # now an orphan and the journal is now ragged, two complaints from one replay.
    journal.write_bytes(own_line.rstrip(b"\n"))
    found = RunStore(tmp_path).read("preview-run")
    assert len(found.warnings) == 2
    err = _refuses_and_leaves_the_run_directory_untouched(tmp_path, capsys)
    assert all(warning in err for warning in found.warnings)


# --- CMD-4 round 4: the owner narrowed the contract -- facts, and no advice ---
#
# Refusals once ended in a remedy sentence that classified the run into a
# clutter road and a dead-end road and told a human what to move or delete. The
# owner decision of 2026-08-12 removed that entirely: a refusal names what was
# reliably detected, the exact paths involved, and the fact that nothing was
# changed -- and advises nothing, because naming the wrong object to destroy is
# worse than naming no object at all. The message contract is held by execution
# in tests/test_command_preview_refusal_contract.py. What stays here are the
# behavioral regressions for the system property the old advice traded on: the
# preview neither adopts, repairs nor blocks a refused run, so out-of-band
# removal of exactly the foreign object -- or of the whole run -- still leads
# where it always led.


def test_moving_a_foreign_object_out_of_band_reopens_the_run_with_records_intact(
        tmp_path, capsys):
    """The run beneath a foreign object is whole, and refusing it destroys nothing.

    Refused twice -- rerunning changes nothing, since this preview repairs
    nothing -- and the moment the one foreign object is gone, the run opens and
    holds the journal it always held, byte for byte. The refusal named the
    object's exact path without asking anyone to act: the move is this test's
    own.
    """
    genuine = _the_previews_own_record_bytes(tmp_path, capsys)
    journal = tmp_path / "conductor" / "runs" / "preview-run" / "records.jsonl"
    stray = journal.parent / "stray.bin"
    stray.write_bytes(b"an editor's swap file, or whatever the antivirus dropped")
    err = _refuses_and_leaves_the_run_directory_untouched(tmp_path, capsys)
    assert repr(str(_named_run_path(tmp_path) / "stray.bin")) in err
    assert main(["preview", "--dir", str(a_project(tmp_path))]) == 1  # waiting mends nothing
    capsys.readouterr()
    shutil.move(str(stray), str(tmp_path / "stray.bin"))
    assert main(["preview", "--dir", str(a_project(tmp_path))]) == 0
    capsys.readouterr()
    assert journal.read_bytes() == genuine


def test_moving_a_ragged_run_aside_out_of_band_lets_a_fresh_run_be_written(
        tmp_path, capsys):
    """A run the replay disagrees with is never adopted, and never blocks its name.

    The refused bytes survive under the name they were moved to -- nothing here
    deletes anything -- and the preview, finding its identity free again, writes
    a fresh run byte for byte the one it writes anywhere.
    """
    genuine = _the_previews_own_record_bytes(tmp_path, capsys)
    ragged_run = tmp_path / "conductor" / "runs" / "preview-run"
    (ragged_run / "records.jsonl").write_bytes(genuine + genuine.rstrip(b"\n"))
    err = _refuses_and_leaves_the_run_directory_untouched(tmp_path, capsys)
    assert repr(str(_named_run_path(tmp_path))) in err
    assert main(["preview", "--dir", str(a_project(tmp_path))]) == 1  # waiting mends nothing
    capsys.readouterr()
    aside = tmp_path / "kept-aside"
    shutil.move(str(ragged_run), str(aside))
    assert main(["preview", "--dir", str(a_project(tmp_path))]) == 0
    capsys.readouterr()
    assert (ragged_run / "records.jsonl").read_bytes() == genuine
    assert (aside / "records.jsonl").read_bytes() == genuine + genuine.rstrip(b"\n")


# --- CMD-4 Q2-2: the run's path once reached one refusal road out of two ---
#
# The run directory used to reach the message out of the unjudged-bytes check
# alone, so a run refused purely on facts the replay states was told nothing.
# The contract facts now close every refusal in `_run_differences` itself, so
# the road that never enters the unowned-files walk carries them too.

#: Refusals whose every difference is a fact the replay STATES: no warning, and no
#: file the store does not own, so nothing on this road ever entered that check.
_REPLAY_STATED_REFUSALS = {
    "another cycle": {
        "cycle_id": "foreign-orbit", "config": preview.FROZEN_CONFIG, "mode": "propose"},
    "another frozen config": {
        "cycle_id": "preview-orbit", "config": _FOREIGN_CONFIG, "mode": "propose"},
    "another mode": {
        "cycle_id": "preview-orbit", "config": preview.FROZEN_CONFIG, "mode": "confirm"},
}


@pytest.mark.parametrize("seeded", sorted(_REPLAY_STATED_REFUSALS))
def test_a_refusal_on_facts_the_replay_states_still_names_the_run_directory(
        seeded, tmp_path, capsys):
    """No warning and no foreign object, and the contract facts arrive anyway.

    The run here disagrees on a fact the replay states and on nothing else, so
    nothing on this road ever enters the unowned-files walk -- the road that
    once carried the run's path alone. The expected path is computed from the
    fixture root, never read back from production; and the system property
    stays: this run is not the preview's, rerunning changes nothing, and once
    the run is moved aside out of band a fresh preview is written.
    """
    _seed_run_at_the_previews_identity(tmp_path, **_REPLAY_STATED_REFUSALS[seeded])
    found = RunStore(tmp_path).read("preview-run")
    assert found.warnings == ()
    err = _refuses_and_leaves_the_run_directory_untouched(tmp_path, capsys)
    named = _named_run_path(tmp_path)
    assert repr(str(named)) in err
    assert "changed nothing in the run directory" in err
    assert main(["preview", "--dir", str(a_project(tmp_path))]) == 1  # waiting mends nothing
    capsys.readouterr()
    shutil.move(str(named), str(tmp_path / "kept-aside"))
    assert main(["preview", "--dir", str(a_project(tmp_path))]) == 0
    capsys.readouterr()
    assert (named / "records.jsonl").read_bytes() == _the_previews_own_record_bytes(
        tmp_path / "fresh", capsys)


# --- the walk's reach: "a file OR A LINK", dangling or pointed at a directory ---


def _symlink_or_skip(link, target, *, directory=False):
    """Make a symbolic link, or skip: Windows grants that privilege, it does not assume it."""
    try:
        link.symlink_to(target, target_is_directory=directory)
    except (OSError, NotImplementedError) as e:  # pragma: no cover - platform policy
        pytest.skip(f"this platform did not permit a symbolic link: {e}")


@pytest.mark.parametrize("points_at", ["a directory", "a name that is not there"])
def test_preview_names_a_link_the_store_does_not_own_whatever_it_points_at(
        points_at, tmp_path, capsys):
    """`Path.is_file` is False for a link to a directory and for a dangling one.

    A walk that keeps only what `is_file` admits therefore steps straight past the
    two durable objects this preview can judge least: a link points somewhere this
    command never looked, and it may point nowhere at all. Neither is a file the
    store wrote, on exactly the ground a stray file is not, so the link is named
    by its exact path -- and the run beneath it is whole: with that one name
    unlinked out of band, the run opens again holding every record it held.
    """
    _seed_run_at_the_previews_identity(
        tmp_path, cycle_id="preview-orbit", config=preview.FROZEN_CONFIG, mode="propose")
    run_path = tmp_path / "conductor" / "runs" / "preview-run"
    link = run_path / "stray-link"
    if points_at == "a directory":
        (tmp_path / "elsewhere").mkdir()
        _symlink_or_skip(link, tmp_path / "elsewhere", directory=True)
    else:
        _symlink_or_skip(link, tmp_path / "nowhere")
    # The filter that walked past it, and every fact the replay can state saying
    # this run is the preview's own to resume: the link alone refuses it.
    assert link.is_symlink() and not link.is_file()
    found = RunStore(tmp_path).read("preview-run")
    assert found.records == () and found.warnings == ()
    err = _refuses_and_leaves_the_run_directory_untouched(tmp_path, capsys)
    assert repr(str(_named_run_path(tmp_path) / "stray-link")) in err
    # The unlinking is this test's own act: that one name gone, the run opens.
    #
    # Which call removes a link is a fact about the LINK's own kind, not about
    # what it points at. `link.is_dir()` follows the link and answers True for a
    # POSIX symlink to a directory -- which `rmdir` then refuses, because the
    # name is a symlink and not a directory. Windows directory links and
    # junctions really are removed with `rmdir`; POSIX symlinks always with
    # `unlink`, whatever they point at. Asked of the platform rather than of the
    # target, and the production containment is untouched: this is the test's
    # own cleanup and nothing follows the link either way.
    if os.name == "nt" and link.is_dir():
        link.rmdir()
    else:
        link.unlink()
    assert main(["preview", "--dir", str(a_project(tmp_path))]) == 0
    capsys.readouterr()
    assert (run_path / "records.jsonl").read_bytes() == _the_previews_own_record_bytes(
        tmp_path / "fresh", capsys)
