"""Tests for the explicitly synthetic `conduct integration-smoke` CLI gate.

The command is driven through `main(argv)` exactly as its neighbours are, and it
honours the same stdout/stderr/exit-code contract: the canonical result receipt
on stdout, diagnostics on stderr, exit 0 only on a produced receipt. What is held
here is the circuit only this command has -- a fixed run driven through
authorize -> execute -> verify -> receipt through a deterministic child process, and a
refusal when a foreign run stands at its identity. That circuit brings its own
seeding helper, which is why it lives in a module of its own.
"""
import json
import os
from pathlib import Path
import stat

import pytest
from conductor.__main__ import main
from conductor.command import control_loop
from conductor.command.adapters import AdapterRegistry
from conductor.command.contracts import (
    ActionResultReceipt,
    ObservationRecord,
    RunEnvelope,
    canonical_json,
)
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.runtime import ControlRuntime
from conductor.command.adapters.process import ProcessRunner


def test_cli_exposes_only_the_synthetic_smoke_not_a_product_confirm(capsys):
    with pytest.raises(SystemExit) as stopped:
        main(["confirm"])
    assert stopped.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_public_smoke_prose_cannot_claim_a_product_human_confirm():
    root = Path(__file__).parents[1]
    files = [
        Path(control_loop.__file__),
        root / "src" / "conductor" / "__main__.py",
        root / "README.md", root / "docs" / "release-smoke.md",
    ]
    joined = "\n".join(path.read_text(encoding="utf-8") for path in files)
    for retired in ("conduct confirm", "fresh Human", "confirming human"):
        assert retired not in joined
    assert "integration-smoke" in joined
    assert "not a product Human Confirm surface" in joined


def _a_project(root):
    """The directory shape `conduct init` leaves, and the only one `main` drives.

    The CLI refuses a `--dir` that is not a Conduct project before it reaches
    this gate at all, so a smoke that means to exercise the gate has to stand in
    a project first. Seeding the directory rather than running `init` keeps each
    test's subject the loop, not the initializer.
    """
    root = Path(root)
    (root / "conductor").mkdir(parents=True, exist_ok=True)
    return root


def _records(root, run_id=control_loop._RUN_ID):
    return RunStore(root).read(run_id).records


_JUNCTION_TAG = getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", 0xA0000003)


def _portal(path):
    found = os.lstat(path)
    return stat.S_ISLNK(found.st_mode) or getattr(found, "st_reparse_tag", 0) == _JUNCTION_TAG


def _state(root):
    out, stack = {}, [root]
    while stack:
        for path in sorted(stack.pop().iterdir()):
            key = path.relative_to(root).as_posix()
            if _portal(path):
                out[key] = ("portal", os.readlink(path))
            elif path.is_dir():
                out[key] = ("dir",)
                stack.append(path)
            else:
                out[key] = ("file", path.read_bytes())
    return out


def _plant_portal(link, target, kind):
    if kind == "junction":
        try:
            import _winapi
            _winapi.CreateJunction(str(target), str(link))
        except (ImportError, AttributeError, OSError) as e:
            pytest.skip(f"junction unavailable: {e}")
    else:
        try:
            link.symlink_to(target, target_is_directory=True)
        except (OSError, NotImplementedError) as e:
            pytest.skip(f"directory symlink unavailable: {e}")


def test_integration_smoke_prints_an_observed_but_unverified_result_receipt(
        tmp_path, capsys):
    """The gate passes on an UNVERIFIED receipt, and that is the honest result.

    The child really did exit zero -- the durable observation next door holds
    that -- but the owned-process adapter checks nothing about the work, so it
    exposes no verifier, and the runtime refuses to spend `succeeded` on a
    process exit. Exit 0 here means the loop produced its immutable receipt,
    never that anything about the work was proved.
    """
    _a_project(tmp_path)
    assert main(["integration-smoke", "--dir", str(tmp_path)]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    out = captured.out
    assert out.endswith("\n") and out.count("\n") == 1  # one clean, redirectable line
    payload = json.loads(out)
    assert payload["outcome"] == "verification_failed"
    assert payload["outcome"] != "succeeded"
    assert canonical_json(ActionResultReceipt.from_dict(payload)) == out.rstrip("\n")
    assert payload["evidence_refs"] == []
    assert "no verifier" in payload["detail"]
    # The process exit is still reported, and it is still zero: unverified is
    # not the same claim as failed, and the receipt keeps the two apart.
    assert payload["exit_code"] == 0


def test_integration_smoke_records_synthetic_fixture_and_owned_process_receipt(
        tmp_path, capsys):
    _a_project(tmp_path)
    assert main(["integration-smoke", "--dir", str(tmp_path)]) == 0
    capsys.readouterr()
    records = _records(tmp_path)
    # The full loop is durable: a proposal, the request that records the
    # synthetic authorization fixture and immutable result receipt. A verifier
    # this adapter does not have creates no evidence record to point at.
    assert [row.kind for row in records] == [
        "action_proposal", "action_request",
        "attempt_event", "attempt_event", "action_result"]
    by_kind = {row.kind: row.value for row in records}
    # The request is the recorded synthetic fixture, separate from the result,
    # and names its fixture actor and exact preview digest.
    request, proposal = by_kind["action_request"], by_kind["action_proposal"]
    assert request.requested_by == "synthetic-integration-smoke"
    assert request.preview_digest == proposal.preview_digest
    assert by_kind["action_result"].outcome == "verification_failed"
    assert by_kind["action_result"].evidence_refs == ()
    # The observation is the half that IS proved: the child was watched exiting
    # zero, and that event keeps saying so beneath an unverified terminal result.
    observed = [
        row.value for row in records
        if row.kind == "attempt_event" and row.value.phase == "execution_observed"]
    assert [row.outcome for row in observed] == ["succeeded"]


def test_integration_smoke_is_idempotent_across_reruns_and_fresh_directories(
        tmp_path, capsys):
    _a_project(tmp_path / "a")
    _a_project(tmp_path / "b")
    assert main(["integration-smoke", "--dir", str(tmp_path / "a")]) == 0
    first = capsys.readouterr().out
    # Re-running opens the same immutable run and yields identical bytes.
    assert main(["integration-smoke", "--dir", str(tmp_path / "a")]) == 0
    assert capsys.readouterr().out == first
    # A fresh dir yields the very same receipt: nothing hidden leaks in.
    assert main(["integration-smoke", "--dir", str(tmp_path / "b")]) == 0
    assert capsys.readouterr().out == first


def _journal(root):
    return root / "conductor" / "runs" / control_loop._RUN_ID / "records.jsonl"


def _tear(journal):
    """Leave what a writer killed mid-append leaves: a newline-free tail."""
    with journal.open("ab") as stream:
        stream.write(b'{"record":{"partial')
    assert not journal.read_bytes().endswith(b"\n")


def _no_spawn(monkeypatch, why):
    monkeypatch.setattr(
        ProcessRunner, "_spawn",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError(why)))


def test_a_torn_journal_tail_the_gate_itself_wrote_is_repaired_rather_than_called_foreign(
        tmp_path, capsys):
    """A crash inside one append used to brick this gate for good.

    `_append_bytes` is one open, one write, one fsync: a kill or a full disk in
    the middle of it leaves a newline-free fragment on the end of records.jsonl.
    `read` reports that as a warning and leaves the bytes alone -- repair belongs
    to the run's single writer -- and this gate OR-ed that warning into its
    foreign-history refusal. So every later run answered "history this loop did
    not write" about records that were, line for line, its own, and the only
    escape was to delete the run directory, which is written down nowhere.

    The gate IS that single writer, so it recovers here: after the route, the
    envelope and the history have all proved the run is its own, and before it
    proposes anything into it.
    """
    _a_project(tmp_path)
    assert main(["integration-smoke", "--dir", str(tmp_path)]) == 0
    first = capsys.readouterr().out
    journal = _journal(tmp_path)
    whole = journal.read_bytes()
    _tear(journal)

    assert main(["integration-smoke", "--dir", str(tmp_path)]) == 0
    repaired = capsys.readouterr()
    assert repaired.out == first
    # The tail is gone and nothing else moved: what survives is exactly the
    # bytes this gate had already written, not a rewrite of them.
    assert journal.read_bytes() == whole

    # And the run is idempotent again, which is the property the wedge cost.
    assert main(["integration-smoke", "--dir", str(tmp_path)]) == 0
    assert capsys.readouterr().out == first
    assert journal.read_bytes() == whole


def test_opening_the_run_returns_it_already_whole_rather_than_repaired_downstream(
        tmp_path, capsys):
    """The repair is the gate's own act, at the point the gate chooses.

    A later `store.append` recovers the tail underneath anyone -- every append
    calls `recover` first -- so the propose that follows would truncate it too.
    That is not good enough for two reasons: it happens AFTER the identity door
    has already judged a prefix that was missing its last line, and it is a
    property of `CommandService`, not a promise this gate makes. So this drives
    `_open_run` alone: it returns with the run whole, before a proposal exists.
    """
    _a_project(tmp_path)
    assert main(["integration-smoke", "--dir", str(tmp_path)]) == 0
    capsys.readouterr()
    journal = _journal(tmp_path)
    whole = journal.read_bytes()
    _tear(journal)

    control_loop._open_run(RunStore(tmp_path))
    assert journal.read_bytes() == whole
    reread = RunStore(tmp_path).read(control_loop._RUN_ID)
    assert reread.warnings == ()
    assert [row.kind for row in reread.records] == [
        "action_proposal", "action_request",
        "attempt_event", "attempt_event", "action_result"]


def test_a_repair_that_leaves_the_run_still_warning_is_a_refusal_not_a_pass(
        tmp_path, capsys, monkeypatch):
    """Fail closed on any warning this writer cannot clear.

    `recover` clears every warning `read` can raise today, so this cannot be
    reached by damaging bytes; it is the guard that stops a future warning kind
    -- one recovery does not repair -- from being waved through by a gate that
    had only checked whether it TRIED. Recovery is replaced by a plain read to
    stand in for such a kind: the verdict comes from the fresh read afterwards,
    so the run is refused, named for what is actually wrong with it, and nothing
    is proposed into it.
    """
    _a_project(tmp_path)
    assert main(["integration-smoke", "--dir", str(tmp_path)]) == 0
    capsys.readouterr()
    journal = _journal(tmp_path)
    _tear(journal)
    before = journal.read_bytes()

    monkeypatch.setattr(RunStore, "recover", RunStore.read)
    _no_spawn(monkeypatch, "an unrepaired-warning refusal reached process spawn")
    assert main(["integration-smoke", "--dir", str(tmp_path)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "could not repair" in captured.err
    assert "incomplete record" in captured.err
    assert "history this loop did not write" not in captured.err
    assert journal.read_bytes() == before


def _foreign_line():
    """A complete, canonical record no history of this loop contains."""
    return canonical_json({
        "record": ObservationRecord(
            observation_id="planted-observation", run_id=control_loop._RUN_ID,
            adapter_id="owned-process", instance_id=control_loop._INSTANCE_ID,
            observed_at=control_loop._NOW, health="unknown").as_dict(),
        "record_type": "adapter_observation"}).encode("utf-8") + b"\n"


def test_a_torn_tail_over_a_record_this_loop_never_wrote_is_still_refused(
        tmp_path, capsys, monkeypatch):
    """The over-correction control: repair may not be a way past the identity door.

    The history is judged on the surviving prefix BEFORE anything is recovered,
    so a journal carrying one foreign complete record is refused whether or not
    a crash tail sits on top of it -- and the tail is still there afterwards,
    because a refused run is left exactly as it was found.
    """
    _a_project(tmp_path)
    assert main(["integration-smoke", "--dir", str(tmp_path)]) == 0
    capsys.readouterr()
    journal = _journal(tmp_path)
    with journal.open("ab") as stream:
        stream.write(_foreign_line())
    _tear(journal)
    before = journal.read_bytes()

    _no_spawn(monkeypatch, "a foreign-history refusal reached process spawn")
    assert main(["integration-smoke", "--dir", str(tmp_path)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "history this loop did not write" in captured.err
    assert journal.read_bytes() == before


def test_a_torn_tail_over_a_foreign_frozen_config_is_refused_before_any_repair(
        tmp_path, capsys, monkeypatch):
    """Foreign config is judged before the tail is, and refusing edits nothing."""
    foreign = {"cycle": {"id": "control-loop-orbit", "phases": ["dispatch", "review"]},
               "instances": [{"id": "claude-dev", "adapter": "claude-code"}]}
    assert snapshot_digest(foreign) != snapshot_digest(control_loop.FROZEN_CONFIG)
    RunStore(tmp_path).create_run(
        RunEnvelope(run_id=control_loop._RUN_ID, cycle_id="control-loop-orbit",
                    created_at=control_loop._NOW,
                    config_digest=snapshot_digest(foreign), mode="confirm"),
        foreign)
    journal = _journal(tmp_path)
    _tear(journal)
    before = journal.read_bytes()

    _no_spawn(monkeypatch, "a foreign-config refusal reached process spawn")
    assert main(["integration-smoke", "--dir", str(tmp_path)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "foreign envelope/config facts" in captured.err
    assert journal.read_bytes() == before


def test_a_broken_record_inside_the_journal_stays_corruption_and_is_never_truncated(
        tmp_path, capsys, monkeypatch):
    """The class the repair must not swallow: a complete line that is wrong.

    A torn tail is one interrupted write and is repairable. A complete record
    that contradicts its contract is corruption -- the store raises `CorruptRun`
    for it and never edits a byte -- and the gate reports the store's own line
    number rather than converting it into a repair or into a foreign-history
    verdict.
    """
    _a_project(tmp_path)
    assert main(["integration-smoke", "--dir", str(tmp_path)]) == 0
    capsys.readouterr()
    journal = _journal(tmp_path)
    lines = journal.read_bytes().splitlines(keepends=True)
    assert len(lines) == 5
    lines[1] = b'{"record":{},"record_type":"action_request"}\n'
    journal.write_bytes(b"".join(lines))
    before = journal.read_bytes()

    _no_spawn(monkeypatch, "a corruption refusal reached process spawn")
    assert main(["integration-smoke", "--dir", str(tmp_path)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "records.jsonl line 2 is invalid" in captured.err
    assert journal.read_bytes() == before


def test_request_only_smoke_history_is_owned_but_refuses_without_effect_authority(
        tmp_path, capsys, monkeypatch):
    store = RunStore(tmp_path)
    envelope = RunEnvelope(
        run_id=control_loop._RUN_ID, cycle_id="control-loop-orbit",
        created_at=control_loop._NOW,
        config_digest=snapshot_digest(control_loop.FROZEN_CONFIG), mode="confirm")
    store.create_run(envelope, control_loop.FROZEN_CONFIG)
    own_request_prefix = next(
        rows for rows in control_loop._expected_histories(envelope) if len(rows) == 2)
    for row in own_request_prefix:
        store.append(row.value)
    journal = store.run_path(control_loop._RUN_ID) / "records.jsonl"
    before = journal.read_bytes()
    monkeypatch.setattr(
        ProcessRunner, "_spawn",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("request-only recovery reached spawn")))
    assert main(["integration-smoke", "--dir", str(tmp_path)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "requires reconciliation" in captured.err
    assert journal.read_bytes() == before


def test_a_reconciled_request_only_run_is_not_a_history_this_gate_may_reopen(
        tmp_path, capsys, monkeypatch):
    """A deliberate exclusion from `_expected_histories`, not an oversight.

    That tuple answers exactly one question: is the run standing at this fixed
    id the output of THIS deterministic loop? Every prefix in it is one
    `render_integration_smoke` writes itself, the lease-only `unknown` that
    `execute` reaches after a crash included. `ControlRuntime.reconcile` is an
    operator's road, and admitting its terminal here would let a CI gate exit 0
    while printing a receipt whose dispatch never crossed the spawn surface the
    gate exists to prove. So the refusal stands, and unlike the torn-tail
    verdict it replaces, it is literally true: this loop did not write that
    record. The recovery is the one every foreign-history refusal has -- a fresh
    directory, which the idempotence test above shows yields the same receipt.
    """
    store = RunStore(tmp_path)
    envelope = RunEnvelope(
        run_id=control_loop._RUN_ID, cycle_id="control-loop-orbit",
        created_at=control_loop._NOW,
        config_digest=snapshot_digest(control_loop.FROZEN_CONFIG), mode="confirm")
    store.create_run(envelope, control_loop.FROZEN_CONFIG)
    own_request_prefix = next(
        rows for rows in control_loop._expected_histories(envelope) if len(rows) == 2)
    for row in own_request_prefix:
        store.append(row.value)
    # An empty registry: reconcile resolves no adapter, so nothing here could
    # have driven the dispatch even by accident.
    closed = ControlRuntime(
        store, AdapterRegistry([]), clock=lambda: control_loop._NOW,
        ids=control_loop._loop_id).reconcile(
            control_loop._RUN_ID, own_request_prefix[1].value.action_id)
    assert closed.receipt.outcome == "unknown"
    journal = _journal(tmp_path)
    before = journal.read_bytes()

    _no_spawn(monkeypatch, "a reconciled-history refusal reached process spawn")
    assert main(["integration-smoke", "--dir", str(tmp_path)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "history this loop did not write" in captured.err
    assert journal.read_bytes() == before


def test_integration_smoke_refuses_a_foreign_run_with_empty_stdout(tmp_path, capsys):
    # A run standing at the gate's fixed id under a different frozen config is not
    # this scenario's own. Identity is checked read-only before propose, so the
    # foreign run remains byte-for-byte as found.
    foreign = {"cycle": {"id": "control-loop-orbit", "phases": ["dispatch", "review"]},
               "instances": [{"id": "claude-dev", "adapter": "claude-code"}]}
    assert snapshot_digest(foreign) != snapshot_digest(control_loop.FROZEN_CONFIG)
    RunStore(tmp_path).create_run(
        RunEnvelope(run_id=control_loop._RUN_ID, cycle_id="control-loop-orbit",
                    created_at="2026-08-11T00:00:00Z",
                    config_digest=snapshot_digest(foreign), mode="confirm"),
        foreign)
    journal = tmp_path / "conductor" / "runs" / control_loop._RUN_ID / "records.jsonl"
    before = journal.read_bytes()
    assert [row.kind for row in _records(tmp_path)] == []
    assert main(["integration-smoke", "--dir", str(tmp_path)]) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err.strip()
    assert journal.read_bytes() == before
    assert [row.kind for row in _records(tmp_path)] == []


@pytest.mark.parametrize("kind", ["symlink", "junction"])
@pytest.mark.parametrize("spot", ["run-root", "runs-root"])
def test_integration_smoke_refuses_route_portal_before_spawn_and_leaves_sides_inert(
        kind, spot, tmp_path, capsys, monkeypatch):
    project, outside = tmp_path / "project", tmp_path / "outside"
    _a_project(outside)
    assert main(["integration-smoke", "--dir", str(outside)]) == 0
    capsys.readouterr()
    target_runs = outside / "conductor" / "runs"
    if spot == "run-root":
        link = project / "conductor" / "runs" / control_loop._RUN_ID
        target = target_runs / control_loop._RUN_ID
    else:
        link = project / "conductor" / "runs"
        target = target_runs
    link.parent.mkdir(parents=True)
    _plant_portal(link, target, kind)
    before_project, before_outside = _state(project), _state(outside)

    def forbidden_spawn(*args, **kwargs):
        raise AssertionError("containment refusal reached process spawn")

    monkeypatch.setattr(ProcessRunner, "_spawn", forbidden_spawn)
    assert main(["integration-smoke", "--dir", str(project)]) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and "content lies elsewhere" in captured.err
    assert _state(project) == before_project
    assert _state(outside) == before_outside


def test_integration_smoke_refuses_hard_linked_journal_before_spawn_and_changes_no_alias(
        tmp_path, capsys, monkeypatch):
    project, outside = tmp_path / "project", tmp_path / "outside"
    _a_project(project)
    assert main(["integration-smoke", "--dir", str(project)]) == 0
    capsys.readouterr()
    outside.mkdir()
    journal = project / "conductor" / "runs" / control_loop._RUN_ID / "records.jsonl"
    alias = outside / "journal-alias.jsonl"
    try:
        os.link(journal, alias)
    except OSError as e:
        pytest.skip(f"hard links unavailable: {e}")
    before_project, before_outside = _state(project), _state(outside)
    monkeypatch.setattr(
        ProcessRunner, "_spawn",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("containment refusal reached process spawn")))
    assert main(["integration-smoke", "--dir", str(project)]) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and "hard links" in captured.err
    assert _state(project) == before_project
    assert _state(outside) == before_outside


def test_integration_smoke_turns_unreadable_identity_walk_into_inert_cli_refusal(
        tmp_path, capsys, monkeypatch):
    _a_project(tmp_path)
    assert main(["integration-smoke", "--dir", str(tmp_path)]) == 0
    capsys.readouterr()
    journal = tmp_path / "conductor" / "runs" / control_loop._RUN_ID / "records.jsonl"
    before = journal.read_bytes()
    monkeypatch.setattr(
        control_loop, "unowned_paths",
        lambda path: (_ for _ in ()).throw(PermissionError("secret OS wording")))
    monkeypatch.setattr(
        ProcessRunner, "_spawn",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("unreadable-state refusal reached process spawn")))
    assert main(["integration-smoke", "--dir", str(tmp_path)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "cannot read" in captured.err
    assert "secret OS wording" not in captured.err
    assert journal.read_bytes() == before
