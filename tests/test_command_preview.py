"""Tests for `conduct preview` — the Day-1 control-loop gate.

The command is driven through `main(argv)` exactly as its neighbours in
test_cli.py are, and it honours the same stdout/stderr/exit-code contract. What
is held here is the circuit only this command has: a run created at a FIXED
identity inside whatever `--dir` names, so the command can find a run it never
wrote, and a refusal message with structure of its own. That circuit brings its
own seeded-run helpers and its own reader for the refusal, which is why it lives
in a module of its own rather than among the CLI's general tests.
"""
import hashlib
import json
import re

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


# --- CMD-4 MAJOR-2: the Day-1 preview gate (create run -> propose dispatch -> inspect) ---
#
# `conduct preview` drives the fixed CommandService end to end from the CLI: it
# creates or opens a run with a frozen config and prints one dispatch proposal's
# canonical form for inspection. It prepares and executes nothing, and it honours
# the same stdout/stderr/exit-code contract as its neighbours.


def test_preview_creates_a_run_and_prints_a_canonical_dispatch_proposal(tmp_path, capsys):
    assert main(["preview", "--dir", str(tmp_path)]) == 0
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
    assert main(["preview", "--dir", str(tmp_path / "a")]) == 0
    first = capsys.readouterr().out
    # Re-running in the same dir opens the existing run and yields identical bytes.
    assert main(["preview", "--dir", str(tmp_path / "a")]) == 0
    assert capsys.readouterr().out == first
    # A fresh dir yields the very same canonical preview: nothing hidden leaks in.
    assert main(["preview", "--dir", str(tmp_path / "b")]) == 0
    assert capsys.readouterr().out == first


def test_preview_refuses_an_unknown_instance_on_stderr_with_empty_stdout(tmp_path, capsys):
    assert main(["preview", "--dir", str(tmp_path), "--instance", "ghost"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "ghost" in captured.err


def test_preview_refuses_an_adapter_that_mismatches_the_frozen_binding(tmp_path, capsys):
    assert main(["preview", "--dir", str(tmp_path), "--adapter", "codex"]) == 1
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


def _refuses_and_leaves_the_history_untouched(root, journal, capsys):
    """Run the preview against the seeded run; return the refusal's stderr."""
    before = hashlib.sha256(journal.read_bytes()).hexdigest()
    assert main(["preview", "--dir", str(root)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    # Byte-identical by digest: a refusal that appended anyway would be the defect.
    assert hashlib.sha256(journal.read_bytes()).hexdigest() == before
    assert captured.err.strip()
    return captured.err


def _the_previews_own_envelope(root, capsys):
    """The envelope a genuine `conduct preview` freezes, read back off its own disk.

    This is the expected side of every refusal below, and it is produced by
    production code in a directory the refusing test never touches — so a test
    comparing it against a value the test itself seeded is comparing two facts
    that came from two different places, never one echoed back at itself.
    """
    assert main(["preview", "--dir", str(root)]) == 0
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
    assert main(["preview", "--dir", str(tmp_path)]) == 0
    first = capsys.readouterr().out
    journal = tmp_path / "conductor" / "runs" / "preview-run" / "records.jsonl"
    written = journal.read_bytes()
    assert len(written.splitlines()) == 1
    # The identical run is the one run this command may reopen, and reopening it
    # costs the history nothing: the proposal is the same immutable record.
    assert main(["preview", "--dir", str(tmp_path)]) == 0
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
    assert main(["preview", "--dir", str(tmp_path / "fresh")]) == 0
    fresh = capsys.readouterr().out
    journal = _seed_run_at_the_previews_identity(
        tmp_path, cycle_id="preview-orbit", config=preview.FROZEN_CONFIG, mode="propose")
    assert journal.read_bytes() == b""
    assert main(["preview", "--dir", str(tmp_path)]) == 0
    captured = capsys.readouterr()
    # Resumed, not refused and not restarted: the same canonical preview, and the
    # one proposal the empty journal was still owed, appended into the found run.
    assert captured.err == ""
    assert captured.out == fresh
    assert len(journal.read_bytes().splitlines()) == 1


def test_preview_refuses_a_run_at_its_identity_that_belongs_to_another_cycle(tmp_path, capsys):
    own = _the_previews_own_envelope(tmp_path / "own", capsys)
    journal = _seed_run_at_the_previews_identity(
        tmp_path, cycle_id="foreign-orbit", config=preview.FROZEN_CONFIG, mode="propose")
    err = _refuses_and_leaves_the_history_untouched(tmp_path, journal, capsys)
    # Which cycle stands on which side is the whole claim: the expected side is the
    # one the preview itself froze, the found side is the one this test seeded.
    # Swapping them would make the refusal an exact inversion of the truth.
    assert _refusal_sides(err, "cycle_id") == (repr(own["cycle_id"]), repr("foreign-orbit"))
    assert own["cycle_id"] == preview.FROZEN_CONFIG["cycle"]["id"] != "foreign-orbit"


def test_preview_refuses_a_run_at_its_identity_frozen_on_another_config(tmp_path, capsys):
    own = _the_previews_own_envelope(tmp_path / "own", capsys)
    journal = _seed_run_at_the_previews_identity(
        tmp_path, cycle_id="preview-orbit", config=_FOREIGN_CONFIG, mode="propose")
    err = _refuses_and_leaves_the_history_untouched(tmp_path, journal, capsys)
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
    journal = _seed_run_at_the_previews_identity(
        tmp_path, cycle_id="preview-orbit", config=preview.FROZEN_CONFIG, mode="confirm")
    err = _refuses_and_leaves_the_history_untouched(tmp_path, journal, capsys)
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
    journal = _seed_run_at_the_previews_identity(
        tmp_path, cycle_id="preview-orbit", config=preview.FROZEN_CONFIG,
        mode="propose", extra={"foreign_authority": carried})
    err = _refuses_and_leaves_the_history_untouched(tmp_path, journal, capsys)
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
    journal = _seed_run_at_the_previews_identity(
        tmp_path, cycle_id="preview-orbit", config=preview.FROZEN_CONFIG,
        mode="propose", extra={"foreign_authority": forgery})
    err = _refuses_and_leaves_the_history_untouched(tmp_path, journal, capsys)
    # One sentence and one difference, however much punctuation the value carries:
    # the entries stand on a boundary the found side cannot put inside itself.
    header, *entries = err.strip().splitlines()
    assert "nothing was proposed into it" in header
    assert len(entries) == 1
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
    assert main(["preview", "--dir", str(root)]) == 0
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
    err = _refuses_and_leaves_the_history_untouched(tmp_path, journal, capsys)
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
    assert main(["preview", "--dir", str(tmp_path / "own")]) == 0
    capsys.readouterr()
    own = RunStore(tmp_path / "own").read("preview-run").records[0].value
    journal = _seed_run_at_the_previews_identity(
        tmp_path, cycle_id="preview-orbit", config=preview.FROZEN_CONFIG, mode="propose")
    # Same id, same run, same frozen config — one different fact, and the digest
    # recomputed over it, so what stands at the identity is a genuine other record.
    forged = ActionProposal.from_dict({
        **own.as_dict(), "rationale": "a rationale this preview never wrote",
        "preview_digest": ""})
    assert forged.proposal_id == own.proposal_id and forged != own
    assert RunStore(tmp_path).append(forged) is True
    err = _refuses_and_leaves_the_history_untouched(tmp_path, journal, capsys)
    assert own.proposal_id in err
