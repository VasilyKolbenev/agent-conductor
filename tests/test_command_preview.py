"""Tests for `conduct preview` — the Day-1 control-loop gate.

The command is driven through `main(argv)` exactly as its neighbours in
test_cli.py are, and it honours the same stdout/stderr/exit-code contract. What
is held here is the circuit only this command has: a run created at a FIXED
identity inside whatever `--dir` names, so the command can find a run it never
wrote, and a refusal message with structure of its own. That circuit brings its
own seeded-run helpers and its own reader for the refusal, which is why it lives
in a module of its own rather than among the CLI's general tests.
"""
import json
import os
import re
import shutil

import pytest
from conductor.__main__ import main
from conductor.command import preview
from conductor.command.contracts import (
    ActionProposal,
    DecisionReceipt,
    RunEnvelope,
    canonical_json,
)
from conductor.command.run_store import RunStore, snapshot_digest


def a_project(root):
    """Say the one thing `conduct preview` now requires before it writes anything.

    The command used to bring `conductor/` into existence as a side effect of
    making `conductor/runs/`, which turned any directory it was pointed at into
    a project -- and a durably broken one, because a later `conduct init` there
    refuses an existing `conductor/` and reports state the person never created
    as their own. Only `init` may create a project now, so every test below that
    starts from an empty directory has to say what `init` would have said.

    It is deliberately the bare directory and not a scaffolded project: the
    preview's own circuit is what these tests hold, and anything else `init`
    writes would be state they never asked about.
    """
    (root / "conductor").mkdir(parents=True, exist_ok=True)
    return root


# --- CMD-4 MAJOR-2: the Day-1 preview gate (create run -> propose dispatch -> inspect) ---
#
# `conduct preview` drives the fixed CommandService end to end from the CLI: it
# creates or opens a run with a frozen config and prints one dispatch proposal's
# canonical form for inspection. It prepares and executes nothing, and it honours
# the same stdout/stderr/exit-code contract as its neighbours.


def test_preview_creates_a_run_and_prints_a_canonical_dispatch_proposal(tmp_path, capsys):
    assert main(["preview", "--dir", str(a_project(tmp_path))]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    out = captured.out
    assert out.endswith("\n") and out.count("\n") == 1  # one clean, redirectable line
    payload = json.loads(out)
    # It is a dispatch proposal for the configured instance, and its preview_digest
    # is a real digest of its own content: reconstructing the contract recomputes it.
    assert payload["capability"] == "dispatch"
    assert payload["instance_id"] == "claude-dev"
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", payload["preview_digest"])
    assert canonical_json(ActionProposal.from_dict(payload)) == out.rstrip("\n")
    # The run and its proposal are durable under --dir; nothing was executed.
    records = tmp_path / "conductor" / "runs" / "preview-run" / "records.jsonl"
    assert records.is_file()


def test_preview_is_deterministic_across_reruns_and_fresh_directories(tmp_path, capsys):
    assert main(["preview", "--dir", str(a_project(tmp_path / "a"))]) == 0
    first = capsys.readouterr().out
    # Re-running in the same dir opens the existing run and yields identical bytes.
    assert main(["preview", "--dir", str(a_project(tmp_path / "a"))]) == 0
    assert capsys.readouterr().out == first
    # A fresh dir yields the very same canonical preview: nothing hidden leaks in.
    assert main(["preview", "--dir", str(a_project(tmp_path / "b"))]) == 0
    assert capsys.readouterr().out == first


def test_preview_refuses_an_unknown_instance_on_stderr_with_empty_stdout(tmp_path, capsys):
    assert main(["preview", "--dir", str(a_project(tmp_path)), "--instance", "ghost"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "ghost" in captured.err


def test_preview_refuses_an_adapter_that_mismatches_the_frozen_binding(tmp_path, capsys):
    assert main(["preview", "--dir", str(a_project(tmp_path)), "--adapter", "codex"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    # The refusal names the instance and the binding it violates, not the caller's word.
    assert "claude-dev" in captured.err and "codex" in captured.err


# --- CMD-4 MAJOR-3: the preview opens ITS run, or none at all ---
#
# `preview-run` is a fixed identity inside whatever directory `--dir` names, so
# the command can FIND a run it never created. Trusting what it finds would let a
# foreign cycle, a foreign frozen config or a foreign mode decide what the printed
# proposal says and whose append-only history it lands in — the same class as
# MAJOR-1: trusting discovered state instead of checking it against the frozen
# identity. So an existing run is replayed and held against the preview's own
# constants before one byte is appended, and a run that differs is left alone.

#: A configuration that is NOT the preview's frozen one, yet binds `claude-dev`
#: to `claude-code` exactly as it does — so every check downstream of identity
#: passes and only the identity check can refuse it.
_FOREIGN_CONFIG = {
    "cycle": {"id": "preview-orbit", "phases": ["dispatch", "review"]},
    "instances": [{"id": "claude-dev", "adapter": "claude-code"}],
}


def _seed_run_at_the_previews_identity(root, *, cycle_id, config, mode, extra=None):
    """Create the run `conduct preview` will find, from facts the caller chooses."""
    RunStore(root).create_run(
        RunEnvelope(run_id="preview-run", cycle_id=cycle_id,
                    created_at="2026-08-11T00:00:00Z",
                    config_digest=snapshot_digest(config), mode=mode,
                    extra=extra or {}),
        config)
    return root / "conductor" / "runs" / "preview-run" / "records.jsonl"


def _durable_snapshot(root):
    """Every durable byte beneath `conductor/runs`, keyed by path relative to it.

    The whole runs directory, not records.jsonl alone and not even the run
    directory alone: a refusal that left a `.tmp` staging file inside the run or
    rewrote a receipt under `decisions/` would leave that one journal untouched
    and still have changed a history it promised not to touch, and the one
    staging artifact this command can actually leak — `create_run` mints its
    staging directory as `conductor/runs/.preview-run.<rand>/` — is a level ABOVE
    the run directory, so a snapshot rooted there could not see it at all. The
    set of paths rides along in the mapping's own keys, so a file appearing or
    vanishing is a difference and not merely a change of content.

    What this helper reports is held directly by
    `test_the_durable_snapshot_reports_a_file_planted_at_each_path_it_names`:
    a guard nothing exercises cannot tell a widened snapshot from the digest of
    one journal it replaced.
    """
    runs = root / "conductor" / "runs"
    return {
        path.relative_to(runs).as_posix(): path.read_bytes()
        for path in sorted(runs.rglob("*")) if path.is_file()
    }


def _named_run_path(root):
    """The run directory's path as the refusal must name it, from the fixture root.

    Computed with pathlib alone, never with `RunStore.run_path`: the message
    under test was rendered through that production function, and both sides of
    a check may not be computed by one function.
    """
    return (root / "conductor" / "runs" / "preview-run").resolve()


#: The paths a refusal could leave behind, each named in `_durable_snapshot`'s own
#: reasons for being the whole runs directory: an edited `decisions/` receipt, a
#: `.tmp` leaked inside the run by a writer that crashed mid-publish, and
#: `create_run`'s staging directory, which lives one level above the run itself.
_LEAKABLE_PATHS = [
    "preview-run/decisions/planted-receipt.json",
    "preview-run/.records.jsonl.planted.tmp",
    ".preview-run.planted/records.jsonl",
]


@pytest.mark.parametrize("planted", _LEAKABLE_PATHS)
def test_the_durable_snapshot_reports_a_file_planted_at_each_path_it_names(
        planted, tmp_path):
    """The immutability guard every refusal below rests on, exercised on its own.

    Every refusal test asserts the snapshot is unchanged, and each one of them
    passes just as well when the snapshot narrows to a digest of `records.jsonl`
    — no production path this command has leaks any of these files, so the
    widened guard has power but no witness. This is that witness: it plants one
    file at each path the docstring names and requires the snapshot to report it
    as a NEW key, which reds the moment the helper stops looking anywhere but at
    the journal.
    """
    _seed_run_at_the_previews_identity(
        tmp_path, cycle_id="preview-orbit", config=preview.FROZEN_CONFIG, mode="propose")
    before = _durable_snapshot(tmp_path)
    leaked = tmp_path.joinpath("conductor", "runs", *planted.split("/"))
    leaked.parent.mkdir(parents=True, exist_ok=True)
    leaked.write_bytes(b"bytes the preview never wrote")
    after = _durable_snapshot(tmp_path)
    # A new path, reported as a key of its own: the mapping is the set of files as
    # much as it is their content, so appearing is itself the difference.
    assert set(after) - set(before) == {planted}
    assert after != before


def _refuses_and_leaves_the_run_directory_untouched(root, capsys):
    """Run the preview against the seeded run; return the refusal's stderr."""
    before = _durable_snapshot(root)
    assert main(["preview", "--dir", str(a_project(root))]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    # Byte for byte and path for path: a refusal that wrote anyway is the defect.
    assert _durable_snapshot(root) == before
    assert captured.err.strip()
    return captured.err


def _the_previews_own_envelope(root, capsys):
    """The envelope a genuine `conduct preview` freezes, read back off its own disk.

    This is the expected side of every refusal below, and it is produced by
    production code in a directory the refusing test never touches — so a test
    comparing it against a value the test itself seeded is comparing two facts
    that came from two different places, never one echoed back at itself.
    """
    assert main(["preview", "--dir", str(a_project(root))]) == 0
    capsys.readouterr()
    return RunStore(root).read("preview-run").envelope.as_dict()


#: One difference entry of the refusal, in the order the refusal put its sides in.
_SIDES = re.compile(r"(?P<field>\w+): expected (?P<expected>.*?), found (?P<found>.*)")


def _refusal_sides(err, field):
    """Return `(expected, found)` for `field` exactly as the refusal ordered them.

    The shape is a change detector for the wording; the load-bearing claim is
    what each caller does with the pair. Asserting that a value merely APPEARS
    in the refusal cannot tell "expected preview-orbit, found foreign-orbit"
    from its exact inversion — a pair can, because the two sides come from
    different code and only one arrangement of them is true.

    One entry per line, matched whole: the found side of an entry is a value the
    preview does not control, so a reader that let it open an entry of its own
    would report differences the preview never named.
    """
    for entry in err.splitlines():
        found = _SIDES.fullmatch(entry.strip())
        if found is not None and found.group("field") == field:
            return found.group("expected"), found.group("found")
    raise AssertionError(f"the refusal states no {field!r} difference: {err!r}")


def test_preview_reopens_its_own_run_without_appending_a_second_proposal(tmp_path, capsys):
    assert main(["preview", "--dir", str(a_project(tmp_path))]) == 0
    first = capsys.readouterr().out
    journal = tmp_path / "conductor" / "runs" / "preview-run" / "records.jsonl"
    written = journal.read_bytes()
    assert len(written.splitlines()) == 1
    # The identical run is the one run this command may reopen, and reopening it
    # costs the history nothing: the proposal is the same immutable record.
    assert main(["preview", "--dir", str(a_project(tmp_path))]) == 0
    assert capsys.readouterr().out == first
    assert journal.read_bytes() == written


def test_preview_resumes_a_run_of_its_own_that_was_created_but_never_appended_to(
        tmp_path, capsys):
    """A run this preview created and then died before appending into is still its own.

    `create_run` publishes the envelope, the frozen config and an EMPTY journal in
    one exclusive step, so the window between creating the run and appending the
    proposal leaves exactly this on disk — the crash the run store is built to
    survive. It is one of the two histories the preview may own; the other, the
    completed one, is held by the reopen test above. Held apart from that one
    because the two are separate alternatives in the same authority: without this,
    dropping "nothing yet" would turn every half-written preview run into a
    permanent refusal at a fixed id, and no test would feel the difference.
    """
    # The expected stdout comes from a fresh directory the seeded run never touches:
    # what a resumed run must print is what production prints with nothing found.
    assert main(["preview", "--dir", str(a_project(tmp_path / "fresh"))]) == 0
    fresh = capsys.readouterr().out
    journal = _seed_run_at_the_previews_identity(
        tmp_path, cycle_id="preview-orbit", config=preview.FROZEN_CONFIG, mode="propose")
    assert journal.read_bytes() == b""
    assert main(["preview", "--dir", str(a_project(tmp_path))]) == 0
    captured = capsys.readouterr()
    # Resumed, not refused and not restarted: the same canonical preview, and the
    # one proposal the empty journal was still owed, appended into the found run.
    assert captured.err == ""
    assert captured.out == fresh
    assert len(journal.read_bytes().splitlines()) == 1


def test_preview_refuses_a_run_at_its_identity_that_belongs_to_another_cycle(tmp_path, capsys):
    own = _the_previews_own_envelope(tmp_path / "own", capsys)
    _seed_run_at_the_previews_identity(
        tmp_path, cycle_id="foreign-orbit", config=preview.FROZEN_CONFIG, mode="propose")
    err = _refuses_and_leaves_the_run_directory_untouched(tmp_path, capsys)
    # Which cycle stands on which side is the whole claim: the expected side is the
    # one the preview itself froze, the found side is the one this test seeded.
    # Swapping them would make the refusal an exact inversion of the truth.
    assert _refusal_sides(err, "cycle_id") == (repr(own["cycle_id"]), repr("foreign-orbit"))
    assert own["cycle_id"] == preview.FROZEN_CONFIG["cycle"]["id"] != "foreign-orbit"


def test_preview_refuses_a_run_at_its_identity_frozen_on_another_config(tmp_path, capsys):
    own = _the_previews_own_envelope(tmp_path / "own", capsys)
    _seed_run_at_the_previews_identity(
        tmp_path, cycle_id="preview-orbit", config=_FOREIGN_CONFIG, mode="propose")
    err = _refuses_and_leaves_the_run_directory_untouched(tmp_path, capsys)
    # Both digests are named, and neither is written down here: the expected side is
    # the digest the preview froze, the found side the one this test seeded — named
    # in that order, or the refusal accuses the frozen config of being the foreign one.
    assert _refusal_sides(err, "config_digest") == (
        repr(own["config_digest"]), repr(snapshot_digest(_FOREIGN_CONFIG)))
    assert own["config_digest"] == snapshot_digest(preview.FROZEN_CONFIG)
    # And the configuration itself is reported as differing, in its own entry —
    # `config_digest` alone would mean the refusal rested on sha256 and nothing else.
    assert any(entry.strip().startswith("config: ") for entry in err.splitlines())


def test_preview_refuses_a_run_at_its_identity_opened_in_another_mode(tmp_path, capsys):
    own = _the_previews_own_envelope(tmp_path / "own", capsys)
    _seed_run_at_the_previews_identity(
        tmp_path, cycle_id="preview-orbit", config=preview.FROZEN_CONFIG, mode="confirm")
    err = _refuses_and_leaves_the_run_directory_untouched(tmp_path, capsys)
    # `confirm` is not `observe`, so the service would have proposed into this run
    # without complaint: nothing but the identity check stands between them. The
    # expected side is the mode the preview opens its own run in, not the seeded one.
    assert _refusal_sides(err, "mode") == (repr(own["mode"]), repr("confirm"))
    assert own["mode"] != "confirm"


@pytest.mark.parametrize("carried", [None, False, 0, "", [], {}, "absent"])
def test_preview_refuses_a_run_carrying_an_envelope_field_the_preview_never_froze(
        carried, tmp_path, capsys):
    """A durable field the preview does not know is a disagreement, whatever it holds.

    The contracts keep unknown fields on purpose, so a foreign run can carry one
    while every named field matches. Reading the two rows with `dict.get` would
    answer None for the key this preview lacks AND for a key the found run holds
    as null, making those two different durable facts compare equal — the whole
    parametrisation exists to keep every JSON-falsy value on the refusing side of
    that distinction, not just the ones that happen not to collide with None.

    The last value is not falsy. It is the one string that collides with the word
    the refusal itself speaks for a field that is missing, and the pair below
    tells the two apart: the marker is bare and a stored value is quoted, so a
    rendering that collapsed them would report a run carrying `absent` and a run
    lacking the field in exactly the same words.
    """
    own = _the_previews_own_envelope(tmp_path / "own", capsys)
    _seed_run_at_the_previews_identity(
        tmp_path, cycle_id="preview-orbit", config=preview.FROZEN_CONFIG,
        mode="propose", extra={"foreign_authority": carried})
    err = _refuses_and_leaves_the_run_directory_untouched(tmp_path, capsys)
    # `absent` is what the preview's own envelope is, and the carried value is what
    # the found run holds — in that order. Inverted, the refusal would report the
    # foreign run as the one lacking the field and the preview as the one carrying it.
    assert "foreign_authority" not in own
    assert _refusal_sides(err, "foreign_authority") == ("absent", repr(carried))


def test_a_value_a_found_run_carries_cannot_forge_a_difference_of_its_own(tmp_path, capsys):
    """The refusal's entries are the preview's; a found value may only be one side of one.

    Every entry pairs a field the preview named with a value it does not control,
    rendered into the same message. Joined on a separator that value could itself
    contain, a run could carry `a; mode: expected 1, found 2` and any reader that
    split the message up would read a mode difference the preview never found —
    the same "found state decides what we say" class as the refusal above, one
    level down and diagnostic only. `repr` cannot produce a newline, so an entry
    per line is a boundary the found side cannot cross.
    """
    forgery = "a; mode: expected 1, found 2"
    own = _the_previews_own_envelope(tmp_path / "own", capsys)
    _seed_run_at_the_previews_identity(
        tmp_path, cycle_id="preview-orbit", config=preview.FROZEN_CONFIG,
        mode="propose", extra={"foreign_authority": forgery})
    err = _refuses_and_leaves_the_run_directory_untouched(tmp_path, capsys)
    # One sentence and one difference, however much punctuation the value carries:
    # the entries stand on a boundary the found side cannot put inside itself. The
    # two lines after the difference are the contract facts every refusal ends
    # with -- the run directory's path and the changed-nothing statement -- and
    # the forgery bought no line beside those three.
    header, *entries = err.strip().splitlines()
    assert "nothing was proposed into it" in header
    differences = [entry for entry in entries if _SIDES.fullmatch(entry.strip())]
    assert len(entries) == 3 and len(differences) == 1
    # And that one entry is the field the preview named, holding the whole forgery
    # quoted as its found side. The mode it spells out is not reported at all —
    # the seeded run's mode is in fact the preview's own, so there is nothing to say.
    assert _refusal_sides(err, "foreign_authority") == ("absent", repr(forgery))
    assert own["mode"] == "propose"
    with pytest.raises(AssertionError, match="the refusal states no 'mode' difference"):
        _refusal_sides(err, "mode")


def _the_previews_own_history(root, capsys):
    """The records a genuine `conduct preview` leaves in its own run, named as it names them.

    Spelled out here rather than imported, so the expectation below is an
    independent restatement of the history and not the module's own answer.
    """
    assert main(["preview", "--dir", str(a_project(root))]) == 0
    capsys.readouterr()
    records = RunStore(root).read("preview-run").records
    return tuple(f"{row.kind} {row.value.proposal_id!r}" for row in records)


@pytest.mark.parametrize("only_the_receipt_file", [False, True])
def test_preview_refuses_a_run_at_its_identity_holding_a_record_it_never_wrote(
        only_the_receipt_file, tmp_path, capsys):
    """A found run's HISTORY is state too, and an envelope that matches does not vouch for it.

    Envelope and frozen config can agree byte for byte while the journal holds a
    record this preview never minted. Appending into that run would put the
    proposal into somebody else's history — no worse a printed preview, but the
    same class one level down: state found and not checked. The preview's own
    history is fully predictable, so it is checked against exactly that.

    `decisions/` is durable state of its own, and the parametrisation covers both
    ways a receipt can reach a replay: journalled, and surviving only as its
    exclusive file with the journal line lost to a crash.
    """
    own = _the_previews_own_history(tmp_path / "own", capsys)
    assert len(own) == 1
    journal = _seed_run_at_the_previews_identity(
        tmp_path, cycle_id="preview-orbit", config=preview.FROZEN_CONFIG, mode="propose")
    RunStore(tmp_path).append(DecisionReceipt(
        receipt_id="foreign-receipt", run_id="preview-run", gate_id="foreign-gate",
        action="approve", actor="someone-else", decided_at="2026-08-11T00:00:00Z",
        reason="a gate this preview never opened", scope_refs=("src",),
        config_digest=snapshot_digest(preview.FROZEN_CONFIG)))
    if only_the_receipt_file:
        journal.write_bytes(b"")
    err = _refuses_and_leaves_the_run_directory_untouched(tmp_path, capsys)
    # The expected side is the history the preview writes for itself; the found side
    # is the one this test planted. Inverted, the refusal would blame its own run.
    assert _refusal_sides(err, "history") == (f"nothing yet or [{own[0]}]", "[decision]")


def test_preview_refuses_a_run_holding_its_own_proposal_id_on_other_facts(tmp_path, capsys):
    """A history that reads as the preview's own is still held to the facts under it.

    `_history` names a proposal by kind and id, and the preview's id is
    deterministic — so a run holding a proposal at that id, minted by someone else
    with a rationale this preview never wrote, passes the identity check as the
    preview's own reopened run. What refuses it is the store one level down: an
    identity that already records different facts is a conflict, not the identical
    retry that makes a genuine reopen free.

    The outcome is what is held here, not the wording, because this refusal is the
    store's sentence and not the preview's: exit 1, nothing on stdout, and a
    journal byte for byte. Without it the defence in depth would be an accident of
    a seam two modules away rather than a claim of this command's.
    """
    assert main(["preview", "--dir", str(a_project(tmp_path / "own"))]) == 0
    capsys.readouterr()
    own = RunStore(tmp_path / "own").read("preview-run").records[0].value
    _seed_run_at_the_previews_identity(
        tmp_path, cycle_id="preview-orbit", config=preview.FROZEN_CONFIG, mode="propose")
    # Same id, same run, same frozen config — one different fact, and the digest
    # recomputed over it, so what stands at the identity is a genuine other record.
    forged = ActionProposal.from_dict({
        **own.as_dict(), "rationale": "a rationale this preview never wrote",
        "preview_digest": ""})
    assert forged.proposal_id == own.proposal_id and forged != own
    assert RunStore(tmp_path).append(forged) is True
    err = _refuses_and_leaves_the_run_directory_untouched(tmp_path, capsys)
    assert own.proposal_id in err


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
