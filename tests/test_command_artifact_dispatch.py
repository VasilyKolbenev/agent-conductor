"""Dispatch resolves durable role inputs and verifies an actual tree change."""
from __future__ import annotations

import hashlib

from conductor.command.adapters import AdapterRegistry
from conductor.command.adapters.deep_commands import DeepDispatchArgs
from conductor.command.artifacts import ArtifactDocument
from conductor.command.contracts import ActionProposal, RunEnvelope
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.runtime import (
    AttemptState,
    Budget,
    Confirmation,
    ControlRuntime,
)

from tests import _fakeclaude
from tests.test_command_claude_transport import NOW, a_harness


RUN_ID = "run-artifact-dispatch"
INSTANCE_ID = "claude-worker"
INSTRUCTION = "Implement the accepted plan and leave one contained change."
PROBE = _fakeclaude.PROBE_PREFIX + "bead5678" * 8
CONFIG = {
    "cycle": {"id": "artifact-cycle", "phases": ["dispatch"]},
    "instances": [{"id": INSTANCE_ID, "adapter": "claude-code"}],
}
ARGUMENTS = {
    "work_item_id": "work-001",
    "instruction_ref": "instr-001",
    "profile": "implement",
    "artifact_refs": ["artifact-plan"],
    "output_limit_profile": "normal",
}


class _Ids:
    def __init__(self) -> None:
        self._counts: dict[str, int] = {}

    def __call__(self, kind: str) -> str:
        self._counts[kind] = self._counts.get(kind, 0) + 1
        return f"{kind}-{self._counts[kind]}"


def _drive(tmp_path, *, artifact_refs=("artifact-plan",)):
    adapter, root, log = a_harness(
        tmp_path, instruction=INSTRUCTION,
        **{
            _fakeclaude.LEAK_CHECK: "1",
            _fakeclaude.WRITE_FILE: "implemented.py:verified change",
        })
    store = RunStore(root)
    store.create_run(
        RunEnvelope(
            run_id=RUN_ID, cycle_id="artifact-cycle", created_at=NOW,
            config_digest=snapshot_digest(CONFIG), mode="confirm"),
        CONFIG)
    first = ArtifactDocument(
        artifact_id="artifact-plan-1", artifact_ref="artifact-plan",
        run_id=RUN_ID, created_at=NOW, media_type="text/markdown",
        content="# Plan\n\nAn earlier revision that must not be dispatched.")
    latest = ArtifactDocument(
        artifact_id="artifact-plan-2", artifact_ref="artifact-plan",
        run_id=RUN_ID, created_at=NOW, media_type="text/markdown",
        content=f"# Plan\n\nImplement this revision only. {PROBE}")
    store.append(first)
    store.append(latest)
    arguments = {**ARGUMENTS, "artifact_refs": list(artifact_refs)}
    proposal = ActionProposal(
        proposal_id="proposal-dispatch", run_id=RUN_ID,
        attempt_id="attempt-dispatch", instance_id=INSTANCE_ID,
        capability="dispatch", arguments=arguments, scope=("work",),
        proposed_by="lane", proposed_at=NOW, timeout_seconds=60,
        rationale="implement the latest durable role handoff",
        config_digest=snapshot_digest(CONFIG))
    store.append(proposal)
    confirmation = Confirmation(
        confirmation_id="confirmation-dispatch", run_id=RUN_ID,
        proposal_id=proposal.proposal_id,
        preview_digest=proposal.preview_digest, capability="dispatch",
        scope=("work",), config_digest=proposal.config_digest,
        confirmed_by="release-owner", confirmed_at=NOW)
    runtime = ControlRuntime(
        store, AdapterRegistry([adapter]), clock=lambda: NOW, ids=_Ids())
    budget = Budget(
        max_actions=8, max_action_seconds=3600,
        max_confirmation_age_seconds=3600)
    attempt = runtime.execute(runtime.authorize(confirmation, budget=budget))
    return attempt, store, adapter, latest, log, root


def test_dispatch_receives_latest_exact_artifact_and_records_change_evidence(
        tmp_path):
    attempt, store, adapter, latest, log, root = _drive(tmp_path)

    assert attempt.state is AttemptState.SUCCEEDED, attempt.receipt.detail
    assert adapter._dispatch_inputs == {}
    assert (root / "work" / "work-001" / "implemented.py").is_file()
    records = store.read(RUN_ID).records
    evidence = [row.value for row in records if row.kind == "evidence"]
    assert len(evidence) == 1
    assert attempt.receipt.evidence_refs == (evidence[0].evidence_id,)
    assert [row.kind for row in records].count("artifact") == 2

    prompt = _fakeclaude.prompt_spawns(log)
    assert len(prompt) == 1
    assert prompt[0]["marker"] == {
        "in_stdin": True, "in_argv": False,
        "in_cwd": False, "in_env": False,
    }
    args = DeepDispatchArgs.from_dict(ARGUMENTS)
    expected = (
        adapter._task_text(args, INSTRUCTION)
        + adapter._render_inputs((latest,))).encode("utf-8")
    assert prompt[0]["stdin"] == {
        "read": True, "bytes": len(expected),
        "sha256": hashlib.sha256(expected).hexdigest(),
    }


def test_missing_dispatch_artifact_ref_spawns_no_task_and_records_no_evidence(
        tmp_path):
    attempt, store, _adapter, _latest, log, _root = _drive(
        tmp_path, artifact_refs=("artifact-missing",))

    assert attempt.state is AttemptState.FAILED
    assert _adapter._dispatch_inputs == {}
    assert _fakeclaude.prompt_spawns(log) == []
    assert all(row.kind != "evidence" for row in store.read(RUN_ID).records)
