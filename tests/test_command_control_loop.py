"""Tests for `conduct confirm` — the Day-1 control-loop gate from the CLI.

The command is driven through `main(argv)` exactly as its neighbours are, and it
honours the same stdout/stderr/exit-code contract: the canonical result receipt
on stdout, diagnostics on stderr, exit 0 only on a produced receipt. What is held
here is the circuit only this command has -- a fixed run driven through
confirm -> execute -> verify -> receipt against an in-process adapter, and a
refusal when a foreign run stands at its identity. That circuit brings its own
seeding helper, which is why it lives in a module of its own.
"""
import json

import pytest
from conductor.__main__ import main
from conductor.command import control_loop
from conductor.command.contracts import ActionResultReceipt, RunEnvelope, canonical_json
from conductor.command.run_store import RunStore, snapshot_digest


def _records(root, run_id=control_loop._RUN_ID):
    return RunStore(root).read(run_id).records


def test_confirm_runs_the_loop_and_prints_a_succeeded_result_receipt(tmp_path, capsys):
    assert main(["confirm", "--dir", str(tmp_path)]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    out = captured.out
    assert out.endswith("\n") and out.count("\n") == 1  # one clean, redirectable line
    payload = json.loads(out)
    # The printed line is the canonical form of a real, verified, succeeded receipt.
    assert payload["outcome"] == "succeeded"
    assert canonical_json(ActionResultReceipt.from_dict(payload)) == out.rstrip("\n")
    assert payload["evidence_refs"]  # a verified success points at its evidence


def test_confirm_records_the_confirmation_and_receipt_but_starts_no_process(tmp_path, capsys):
    assert main(["confirm", "--dir", str(tmp_path)]) == 0
    capsys.readouterr()
    records = _records(tmp_path)
    # The full loop is durable: a proposal, the request that records the
    # confirmation, the verification evidence, and the immutable result receipt.
    assert [row.kind for row in records] == [
        "action_proposal", "action_request", "evidence", "action_result"]
    by_kind = {row.kind: row.value for row in records}
    # The request IS the recorded confirmation, separate from the result, and it
    # names the confirming human and the exact confirmed digest.
    request, proposal = by_kind["action_request"], by_kind["action_proposal"]
    assert request.requested_by == "release-owner"
    assert request.preview_digest == proposal.preview_digest
    assert by_kind["action_result"].outcome == "succeeded"
    assert by_kind["evidence"].verification == "verified"


def test_confirm_is_idempotent_across_reruns_and_fresh_directories(tmp_path, capsys):
    assert main(["confirm", "--dir", str(tmp_path / "a")]) == 0
    first = capsys.readouterr().out
    # Re-running opens the same immutable run and yields identical bytes.
    assert main(["confirm", "--dir", str(tmp_path / "a")]) == 0
    assert capsys.readouterr().out == first
    # A fresh dir yields the very same receipt: nothing hidden leaks in.
    assert main(["confirm", "--dir", str(tmp_path / "b")]) == 0
    assert capsys.readouterr().out == first


def test_confirm_refuses_a_foreign_run_at_its_identity_with_empty_stdout(tmp_path, capsys):
    # A run standing at the gate's fixed id under a different frozen config is not
    # this scenario's own. The gate refuses it (exit 1, empty stdout) -- but this is
    # an honest refusal, NOT preview's proven inertness (control_loop docstring):
    # propose first appends one proposal bearing the FOUND run's config digest, then
    # authorize refuses at the config-digest check -- before any confirmation is
    # recorded, before execution, before a receipt. So the appended proposal is the
    # only durable trace, and the loop never reaches a request, evidence, or result.
    foreign = {"cycle": {"id": "control-loop-orbit", "phases": ["dispatch", "review"]},
               "instances": [{"id": "claude-dev", "adapter": "claude-code"}]}
    assert snapshot_digest(foreign) != snapshot_digest(control_loop.FROZEN_CONFIG)
    RunStore(tmp_path).create_run(
        RunEnvelope(run_id=control_loop._RUN_ID, cycle_id="control-loop-orbit",
                    created_at="2026-08-11T00:00:00Z",
                    config_digest=snapshot_digest(foreign), mode="confirm"),
        foreign)
    assert [row.kind for row in _records(tmp_path)] == []  # before: the run holds nothing
    assert main(["confirm", "--dir", str(tmp_path)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() != ""
    # After the refusal, exactly the appended proposal stands: no action_request (no
    # confirmation recorded), no evidence, no action_result. Were the config-digest
    # guard removed, the loop would confirm, execute, and append all three here.
    assert [row.kind for row in _records(tmp_path)] == ["action_proposal"]
