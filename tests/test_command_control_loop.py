"""Tests for `conduct confirm` — the Day-1 control-loop gate from the CLI.

The command is driven through `main(argv)` exactly as its neighbours are, and it
honours the same stdout/stderr/exit-code contract: the canonical result receipt
on stdout, diagnostics on stderr, exit 0 only on a produced receipt. What is held
here is the circuit only this command has -- a fixed run driven through
confirm -> execute -> verify -> receipt through a deterministic child process, and a
refusal when a foreign run stands at its identity. That circuit brings its own
seeding helper, which is why it lives in a module of its own.
"""
import json
import os
import stat

import pytest
from conductor.__main__ import main
from conductor.command import control_loop
from conductor.command.contracts import ActionResultReceipt, RunEnvelope, canonical_json
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.adapters.process import ProcessRunner


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


def test_confirm_runs_the_loop_and_prints_a_succeeded_result_receipt(tmp_path, capsys):
    assert main(["confirm", "--dir", str(tmp_path)]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    out = captured.out
    assert out.endswith("\n") and out.count("\n") == 1  # one clean, redirectable line
    payload = json.loads(out)
    # The child exited zero; verification is honestly unavailable, never invented.
    assert payload["outcome"] == "succeeded"
    assert canonical_json(ActionResultReceipt.from_dict(payload)) == out.rstrip("\n")
    assert payload["evidence_refs"] == []
    assert "no verifier" in payload["detail"]


def test_confirm_records_the_confirmation_and_owned_process_receipt(tmp_path, capsys):
    assert main(["confirm", "--dir", str(tmp_path)]) == 0
    capsys.readouterr()
    records = _records(tmp_path)
    # The full loop is durable: a proposal, the request that records the
    # confirmation and the immutable result receipt. Unavailable verification
    # creates no false evidence record.
    assert [row.kind for row in records] == [
        "action_proposal", "action_request", "action_result"]
    by_kind = {row.kind: row.value for row in records}
    # The request IS the recorded confirmation, separate from the result, and it
    # names the confirming human and the exact confirmed digest.
    request, proposal = by_kind["action_request"], by_kind["action_proposal"]
    assert request.requested_by == "release-owner"
    assert request.preview_digest == proposal.preview_digest
    assert by_kind["action_result"].outcome == "succeeded"
    assert by_kind["action_result"].evidence_refs == ()


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
    assert main(["confirm", "--dir", str(tmp_path)]) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err.strip()
    assert journal.read_bytes() == before
    assert [row.kind for row in _records(tmp_path)] == []


@pytest.mark.parametrize("kind", ["symlink", "junction"])
@pytest.mark.parametrize("spot", ["run-root", "runs-root"])
def test_confirm_refuses_a_route_portal_before_spawn_and_leaves_both_sides_inert(
        kind, spot, tmp_path, capsys, monkeypatch):
    project, outside = tmp_path / "project", tmp_path / "outside"
    assert main(["confirm", "--dir", str(outside)]) == 0
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
    assert main(["confirm", "--dir", str(project)]) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and "content lies elsewhere" in captured.err
    assert _state(project) == before_project
    assert _state(outside) == before_outside


def test_confirm_refuses_a_hard_linked_journal_before_spawn_and_changes_no_alias(
        tmp_path, capsys, monkeypatch):
    project, outside = tmp_path / "project", tmp_path / "outside"
    assert main(["confirm", "--dir", str(project)]) == 0
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
    assert main(["confirm", "--dir", str(project)]) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and "hard links" in captured.err
    assert _state(project) == before_project
    assert _state(outside) == before_outside


def test_confirm_turns_an_unreadable_identity_walk_into_an_inert_cli_refusal(
        tmp_path, capsys, monkeypatch):
    assert main(["confirm", "--dir", str(tmp_path)]) == 0
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
    assert main(["confirm", "--dir", str(tmp_path)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "cannot read" in captured.err
    assert "secret OS wording" not in captured.err
    assert journal.read_bytes() == before
