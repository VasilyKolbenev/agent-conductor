"""Claude review consumes and produces durable artifacts through Confirm."""
from __future__ import annotations

import hashlib
import json

from conductor.command.adapters import AdapterRegistry
from conductor.command.adapters.claude_code import (
    BARE_ARGV,
    INPUT_FORMAT_ARGV,
    NO_SESSION_ARGV,
    OUTPUT_FORMAT_ARGV,
    PRINT_FLAG,
    REVIEW_PERMISSION_MODE_ARGV,
    REVIEW_PROMPT,
)
from conductor.command.adapters.deep_commands import DeepReviewArgs
from conductor.command.artifacts import ArtifactDocument
from conductor.command.artifact_handoff import ArtifactHandoff
from conductor.command.contracts import ActionProposal, RunEnvelope
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.runtime import (
    AttemptState,
    Authorization,
    Budget,
    Confirmation,
    ControlRuntime,
)

from tests import _fakeclaude
from tests.test_command_claude_transport import NOW, a_harness


RUN_ID = "run-claude-review"
INSTANCE_ID = "claude-reviewer"
INPUT_REF = "artifact-input"
OUTPUT_REF = "artifact-reviewed"
PROBE = _fakeclaude.PROBE_PREFIX + "cafe1234" * 8
API_KEY = "sk-ant-api03-SYNTHETIC-REVIEW-NEVER-REAL"
REVIEW_TEXT = _fakeclaude.REVIEW_OUTPUT
CONFIG = {
    "cycle": {"id": "review-cycle", "phases": ["review"]},
    "instances": [{"id": INSTANCE_ID, "adapter": "claude-code"}],
}
ARGUMENTS = {
    "work_item_id": "work-001",
    "target_artifact_refs": [INPUT_REF],
    "result_artifact_ref": OUTPUT_REF,
    "review_profile": "quality",
}


class _Ids:
    def __init__(self) -> None:
        self._counts: dict[str, int] = {}

    def __call__(self, kind: str) -> str:
        self._counts[kind] = self._counts.get(kind, 0) + 1
        return f"{kind}-{self._counts[kind]}"


def _proposal(arguments=ARGUMENTS) -> ActionProposal:
    # This factory drives a current transport; it is not a historical journal fixture.
    return ActionProposal(
        proposal_id="proposal-review", run_id=RUN_ID,
        attempt_id="attempt-review", instance_id=INSTANCE_ID,
        capability="review", arguments=arguments, scope=("work",),
        proposed_by="lane", proposed_at=NOW, timeout_seconds=60,
        rationale="review the durable role handoff",
        config_digest=snapshot_digest(CONFIG), input_binding="proposal-v1")


def _confirmation(proposal: ActionProposal) -> Confirmation:
    return Confirmation(
        confirmation_id="confirmation-review", run_id=RUN_ID,
        proposal_id=proposal.proposal_id,
        preview_digest=proposal.preview_digest, capability="review",
        scope=("work",), config_digest=proposal.config_digest,
        confirmed_by="release-owner", confirmed_at=NOW)


#: What the seeded input artifact says by default: the probe token rides INSIDE
#: the durable material, so the leak scan has exactly one token to find.
SEED_CONTENT = f"# Candidate\n\nReview this exact proposal. {PROBE}"


def _run(tmp_path, *, arguments=ARGUMENTS, seed_content=SEED_CONTENT,
         **knobs: str):
    """Drive one review through Confirm; `seed_content` moves the probe elsewhere.

    A caller proving that some OTHER part of the task reached the child -- the
    step's purpose, say -- puts the probe there and hands in a seed without one,
    because the child refuses a stdin carrying two tokens as firmly as none.
    """
    values = {
        _fakeclaude.EMIT_REVIEW: "enabled-review-output",
        _fakeclaude.LEAK_CHECK: "enabled-review-leak-check",
        "ANTHROPIC_API_KEY": API_KEY,
        **knobs,
    }
    adapter, root, log = a_harness(tmp_path, **values)
    store = RunStore(root)
    store.create_run(
        RunEnvelope(
            run_id=RUN_ID, cycle_id="review-cycle", created_at=NOW,
            config_digest=snapshot_digest(CONFIG), mode="confirm"),
        CONFIG)
    seed = ArtifactDocument(
        artifact_id="artifact-source-1", artifact_ref=INPUT_REF,
        run_id=RUN_ID, created_at=NOW, media_type="text/markdown",
        content=seed_content)
    store.append(seed)
    proposal = _proposal(arguments)
    store.append(proposal)
    runtime = ControlRuntime(
        store, AdapterRegistry([adapter]), clock=lambda: NOW, ids=_Ids())
    budget = Budget(
        max_actions=8, max_action_seconds=3600,
        max_confirmation_age_seconds=3600)
    attempt = runtime.execute(runtime.authorize(
        _confirmation(proposal), budget=budget))
    return attempt, store, adapter, seed, log, root


def _records(store: RunStore):
    return store.read(RUN_ID).records


def test_review_reads_exact_artifact_bytes_and_records_one_causal_output(tmp_path):
    attempt, store, adapter, seed, log, _root = _run(tmp_path)

    assert attempt.state is AttemptState.SUCCEEDED, attempt.receipt.detail
    records = _records(store)
    outputs = [row.value for row in records if row.kind == "artifact"
               and row.value.source_action_id is not None]
    assert len(outputs) == 1
    output = outputs[0]
    assert output.artifact_ref == OUTPUT_REF
    assert output.content == REVIEW_TEXT + "\n"
    assert output.input_artifact_ids == (seed.artifact_id,)
    assert output.source_action_id == attempt.request.action_id
    assert adapter._review_attempts == {}
    evidence = [row.value for row in records if row.kind == "evidence"]
    assert len(evidence) == 1 and evidence[0].digest == output.digest()
    assert attempt.receipt.evidence_refs == (evidence[0].evidence_id,)

    prompt = _fakeclaude.prompt_spawns(log)
    assert len(prompt) == 1
    expected_argv = [
        *BARE_ARGV, PRINT_FLAG, REVIEW_PROMPT,
        *INPUT_FORMAT_ARGV, *OUTPUT_FORMAT_ARGV,
        *NO_SESSION_ARGV, *REVIEW_PERMISSION_MODE_ARGV,
    ]
    assert prompt[0]["argv"] == expected_argv
    assert "acceptEdits" not in prompt[0]["argv"]
    assert prompt[0]["marker"] == {
        "in_stdin": True, "in_argv": False,
        "in_cwd": False, "in_env": False,
    }
    args = DeepReviewArgs.from_dict(ARGUMENTS)
    task = adapter._review_task(args, (seed,)).encode("utf-8")
    assert prompt[0]["stdin"] == {
        "read": True, "bytes": len(task),
        "sha256": hashlib.sha256(task).hexdigest(),
    }


def test_review_never_persists_the_allowed_credential(tmp_path):
    attempt, store, _adapter, _seed, log, _root = _run(tmp_path)

    raw = json.dumps(
        [row.value.as_dict() for row in _records(store)],
        sort_keys=True).encode("utf-8") + log.read_bytes()
    assert attempt.state is AttemptState.SUCCEEDED
    assert API_KEY.encode() not in raw
    assert all("ANTHROPIC_API_KEY" in row["env_names"]
               for row in _fakeclaude.spawns(log))


def test_review_stderr_is_observed_but_never_becomes_artifact_content(tmp_path):
    attempt, store, _adapter, _seed, _log, _root = _run(
        tmp_path, **{_fakeclaude.EMIT_STDERR: API_KEY})

    outputs = [row.value for row in _records(store)
               if row.kind == "artifact" and row.value.source_action_id]
    raw = json.dumps(
        [row.value.as_dict() for row in _records(store)],
        sort_keys=True).encode("utf-8")
    assert attempt.state is AttemptState.SUCCEEDED
    assert len(outputs) == 1 and outputs[0].content == REVIEW_TEXT + "\n"
    assert API_KEY.encode() not in raw


def test_review_that_echoes_an_allowed_credential_is_never_published(tmp_path):
    attempt, store, _adapter, _seed, log, _root = _run(
        tmp_path, **{_fakeclaude.EMIT_STDOUT: API_KEY})

    raw = json.dumps(
        [row.value.as_dict() for row in _records(store)],
        sort_keys=True).encode("utf-8") + log.read_bytes()
    assert attempt.state is AttemptState.VERIFICATION_FAILED
    assert API_KEY.encode() not in raw
    produced = [row for row in _records(store)
                if row.kind in ("artifact", "evidence")]
    assert [row.kind for row in produced] == ["artifact"]


def test_missing_review_input_spawns_no_prompt_and_writes_no_output(tmp_path):
    arguments = dict(ARGUMENTS)
    arguments["target_artifact_refs"] = ["artifact-missing"]
    attempt, store, _adapter, _seed, log, _root = _run(
        tmp_path, arguments=arguments)

    assert attempt.state is AttemptState.FAILED
    assert _fakeclaude.prompt_spawns(log) == []
    assert _adapter._review_attempts == {}
    produced = [row for row in _records(store)
                if row.kind in ("artifact", "evidence")]
    assert [row.kind for row in produced] == ["artifact"]


def test_review_that_changes_the_tree_is_not_verified_or_published(tmp_path):
    attempt, store, _adapter, _seed, _log, root = _run(
        tmp_path, **{_fakeclaude.WRITE_FILE: "review.txt:changed"})

    assert (root / "work" / "work-001" / "review.txt").is_file()
    assert attempt.state is AttemptState.VERIFICATION_FAILED
    assert _adapter._review_attempts == {}
    produced = [row for row in _records(store)
                if row.kind in ("artifact", "evidence")]
    assert [row.kind for row in produced] == ["artifact"]


def test_blank_review_output_cannot_become_an_artifact(tmp_path):
    attempt, store, _adapter, _seed, _log, _root = _run(
        tmp_path, **{_fakeclaude.EMIT_REVIEW: ""})

    assert attempt.state is AttemptState.VERIFICATION_FAILED
    produced = [row for row in _records(store)
                if row.kind in ("artifact", "evidence")]
    assert [row.kind for row in produced] == ["artifact"]


def test_invalid_utf8_review_output_cannot_become_an_artifact(tmp_path):
    attempt, store, _adapter, _seed, _log, _root = _run(
        tmp_path,
        **{_fakeclaude.EMIT_REVIEW: "", _fakeclaude.EMIT_HEX: "ff"})

    assert attempt.state is AttemptState.VERIFICATION_FAILED
    produced = [row for row in _records(store)
                if row.kind in ("artifact", "evidence")]
    assert [row.kind for row in produced] == ["artifact"]


def test_truncated_review_output_stops_before_artifact_verification(tmp_path):
    attempt, store, _adapter, _seed, _log, _root = _run(
        tmp_path,
        **{_fakeclaude.EMIT_REVIEW: "", _fakeclaude.BOMB_BYTES: "20000"})

    assert attempt.state is AttemptState.FAILED
    produced = [row for row in _records(store)
                if row.kind in ("artifact", "evidence")]
    assert [row.kind for row in produced] == ["artifact"]


def test_restart_recovers_an_artifact_appended_before_its_evidence(tmp_path):
    attempt, source, _adapter, _seed, _log, _root = _run(tmp_path / "source")
    assert attempt.state is AttemptState.SUCCEEDED
    partial_root = tmp_path / "partial"
    partial_root.mkdir()
    partial = RunStore(partial_root)
    partial.create_run(
        RunEnvelope(
            run_id=RUN_ID, cycle_id="review-cycle", created_at=NOW,
            config_digest=snapshot_digest(CONFIG), mode="confirm"),
        CONFIG)
    request = None
    for row in source.read(RUN_ID).records:
        if row.kind in ("evidence", "action_result"):
            continue
        partial.append(row.value)
        if row.kind == "action_request":
            request = row.value
    assert request is not None
    assert [row.kind for row in partial.read(RUN_ID).records].count(
        "artifact") == 2
    assert all(row.kind != "evidence" for row in partial.read(RUN_ID).records)

    fresh, _root, fresh_log = a_harness(
        tmp_path / "fresh", root=partial_root)
    runtime = ControlRuntime(
        partial, AdapterRegistry([fresh]), clock=lambda: NOW, ids=_Ids())
    resumed = runtime.execute(Authorization(request=request))

    assert resumed.state is AttemptState.SUCCEEDED
    assert len(resumed.receipt.evidence_refs) == 1
    assert _fakeclaude.spawns(fresh_log) == []
    records = partial.read(RUN_ID).records
    assert [row.kind for row in records].count("artifact") == 2
    assert [row.kind for row in records].count("evidence") == 1
    assert [row.kind for row in records].count("action_result") == 1


def test_artifact_handoff_exact_retry_never_duplicates_recovered_evidence(tmp_path):
    attempt, store, _adapter, _seed, _log, _root = _run(tmp_path)
    request = attempt.request
    handoff = ArtifactHandoff(store, clock=lambda: NOW, ids=_Ids())

    first = handoff.record_review(
        request, OUTPUT_REF, input_artifact_ids=None, content=None,
        adapter_id="claude-code")
    second = handoff.record_review(
        request, OUTPUT_REF, input_artifact_ids=None, content=None,
        adapter_id="claude-code")

    assert first == second
    assert [row.kind for row in store.read(RUN_ID).records].count("artifact") == 2
    assert [row.kind for row in store.read(RUN_ID).records].count("evidence") == 1
