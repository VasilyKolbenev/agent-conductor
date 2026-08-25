"""Codex review consumes and produces durable artifacts through Confirm.

The second real reviewer in the roster, and the one that makes the control a
PRODUCT seam rather than one vendor's. Claude Code's review runs under a
`--permission-mode plan` this build pins; Codex CLI's runs under
`--sandbox read-only`. Neither buys a containment claim -- see
`codex_cli.REVIEW_SANDBOX_ARGV` -- and the two providers are held to the same
outcome by the same shared transport: durable material in, one durable document
out, and a refusal if the authorized work tree moved.

What this file does NOT test is `codex exec review`. That subcommand exists and
reviews a git diff; this control reviews artifacts, and the argv assertion below
is what keeps the two from being confused for each other.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from conductor.command.adapters import AdapterRegistry
from conductor.command.adapters.codex_cli import (
    COLOR_ARGV,
    EPHEMERAL_ARGV,
    EXEC_ARGV,
    LAST_MESSAGE_NAME,
    REVIEW_SANDBOX_ARGV,
    SKIP_GIT_REPO_CHECK_ARGV,
    STDIN_PROMPT,
    TELEMETRY_ARGV,
)
from conductor.command.adapters.deep_commands import DeepReviewArgs
from conductor.command.artifacts import ArtifactDocument
from conductor.command.contracts import (
    ActionProposal,
    ActionRequest,
    RunEnvelope,
)
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.runtime import (
    AttemptState,
    Budget,
    Confirmation,
    ControlRuntime,
)

from tests import _fakecodex
from tests.test_command_codex_transport import NOW, a_harness

RUN_ID = "run-codex-review"
INSTANCE_ID = "codex-reviewer"
INPUT_REF = "artifact-input"
OUTPUT_REF = "artifact-reviewed"
PROBE = _fakecodex.PROBE_PREFIX + "beef4321" * 8
API_KEY = "sk-proj-SYNTHETIC-CODEX-REVIEW-NEVER-REAL"
REVIEW_TEXT = _fakecodex.REVIEW_OUTPUT
CONFIG = {
    "cycle": {"id": "review-cycle", "phases": ["review"]},
    "instances": [{"id": INSTANCE_ID, "adapter": "codex"}],
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
    return ActionProposal(
        proposal_id="proposal-review", run_id=RUN_ID,
        attempt_id="attempt-review", instance_id=INSTANCE_ID,
        capability="review", arguments=arguments, scope=("work",),
        proposed_by="lane", proposed_at=NOW, timeout_seconds=60,
        rationale="review the durable role handoff",
        config_digest=snapshot_digest(CONFIG))


def _confirmation(proposal: ActionProposal) -> Confirmation:
    return Confirmation(
        confirmation_id="confirmation-review", run_id=RUN_ID,
        proposal_id=proposal.proposal_id,
        preview_digest=proposal.preview_digest, capability="review",
        scope=("work",), config_digest=proposal.config_digest,
        confirmed_by="release-owner", confirmed_at=NOW)


def _run(tmp_path, *, arguments=ARGUMENTS, **knobs: str):
    values = {
        _fakecodex.EMIT_REVIEW: "enabled-review-output",
        _fakecodex.LEAK_CHECK: "enabled-review-leak-check",
        "OPENAI_API_KEY": API_KEY,
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
        content=f"# Candidate\n\nReview this exact proposal. {PROBE}")
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


def test_codex_review_reads_exact_artifact_bytes_and_records_one_output(tmp_path):
    """One review, end to end, through the ordinary Confirm runtime.

    The whole chain is asserted where it lands: the output is the child's own
    stdout, its reference is the one the request asked for, its inputs are the
    ids the request's references resolved to, the verification digests that
    document, and the receipt names that verification.
    """
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


def test_the_codex_review_argv_is_read_only_and_carries_no_task(tmp_path):
    """Every token spelled, because a review's argv is a safety claim.

    Two things are asserted rather than described. `--sandbox read-only` is
    present and `workspace-write` is nowhere in the list -- the dispatch road's
    policy must not reach a review by inheritance. And `review` is not a token
    at all: `codex exec review` reviews a git diff, and sending it would be
    answering a different question under the same word.

    The task rides stdin and the marker scan proves it reached no other channel.
    """
    _attempt, _store, adapter, seed, log, _root = _run(tmp_path)

    spawned = _fakecodex.task_spawns(log)
    assert len(spawned) == 1
    argv = spawned[0]["argv"]
    home = spawned[0]["codex_home"]
    assert argv == [
        *EXEC_ARGV, *SKIP_GIT_REPO_CHECK_ARGV, *EPHEMERAL_ARGV,
        *COLOR_ARGV, *REVIEW_SANDBOX_ARGV, *TELEMETRY_ARGV,
        "-o", str(Path(home) / LAST_MESSAGE_NAME), STDIN_PROMPT,
    ]
    assert "workspace-write" not in argv
    assert "review" not in argv
    assert spawned[0]["marker"] == {
        "in_stdin": True, "in_argv": False,
        "in_cwd": False, "in_env": False,
    }
    args = DeepReviewArgs.from_dict(ARGUMENTS)
    task = adapter._review_task(args, (seed,)).encode("utf-8")
    assert spawned[0]["stdin"] == {
        "read": True, "bytes": len(task),
        "sha256": hashlib.sha256(task).hexdigest(),
    }


def test_a_codex_review_never_persists_the_allowed_credential(tmp_path):
    attempt, store, _adapter, _seed, log, _root = _run(tmp_path)

    raw = json.dumps(
        [row.value.as_dict() for row in _records(store)],
        sort_keys=True).encode("utf-8") + log.read_bytes()
    assert attempt.state is AttemptState.SUCCEEDED
    assert API_KEY.encode() not in raw
    assert all("OPENAI_API_KEY" in row["env_names"]
               for row in _fakecodex.spawns(log))


def test_a_codex_review_that_changes_the_tree_is_not_verified_or_published(
        tmp_path):
    """What makes the review read-only, since the sandbox flag does not.

    `WindowsSandboxLevel` defaults to Disabled, so a policy is a request. The
    tree is digested before the spawn and again after it, and a review that
    moved one byte is refused at verification -- which is the claim a reader
    should take away, and it holds against a child that ignored the flag
    entirely.
    """
    attempt, store, _adapter, _seed, _log, root = _run(
        tmp_path, **{_fakecodex.WRITE_FILE: "review.txt:changed"})

    assert (root / "work" / "work-001" / "review.txt").is_file()
    assert attempt.state is AttemptState.VERIFICATION_FAILED
    produced = [row for row in _records(store)
                if row.kind in ("artifact", "evidence")]
    assert [row.kind for row in produced] == ["artifact"]


def test_a_codex_review_that_echoes_an_allowed_credential_is_never_published(
        tmp_path):
    attempt, store, _adapter, _seed, log, _root = _run(
        tmp_path, **{_fakecodex.EMIT_STDOUT: API_KEY})

    raw = json.dumps(
        [row.value.as_dict() for row in _records(store)],
        sort_keys=True).encode("utf-8") + log.read_bytes()
    assert attempt.state is AttemptState.VERIFICATION_FAILED
    assert API_KEY.encode() not in raw
    produced = [row for row in _records(store)
                if row.kind in ("artifact", "evidence")]
    assert [row.kind for row in produced] == ["artifact"]


def test_a_codex_review_naming_a_missing_input_spawns_no_prompt(tmp_path):
    arguments = dict(ARGUMENTS)
    arguments["target_artifact_refs"] = ["artifact-missing"]
    attempt, store, adapter, _seed, log, _root = _run(
        tmp_path, arguments=arguments)

    assert attempt.state is AttemptState.FAILED
    assert _fakecodex.task_spawns(log) == []
    assert adapter._review_attempts == {}
    produced = [row for row in _records(store)
                if row.kind in ("artifact", "evidence")]
    assert [row.kind for row in produced] == ["artifact"]


def test_a_codex_review_naming_no_result_artifact_spawns_no_prompt(tmp_path):
    """A revision-1 payload is readable and unrunnable, on this provider too.

    The contract admits an omitted `result_artifact_ref` so the frozen revision
    stays parseable. Running one would spend a model call on an answer with
    nowhere durable to go, so the refusal stands BEFORE the spawn -- and it is
    the shared transport's, which is why it must hold for a provider whose
    review road was written later.

    Driven at the adapter's own seam rather than through the runtime, because
    the SENTENCE is what is under test here and the runtime replaces an
    adapter's detail with its own word. What the runtime road proves -- that a
    failed review publishes nothing -- is proved by its own tests above.
    """
    adapter, _root, log = a_harness(
        tmp_path, **{_fakecodex.EMIT_REVIEW: "enabled-review-output"})
    request = _proposal().as_dict()
    receipt = adapter.execute(adapter.prepare(ActionRequest(
        action_id="action-no-result", run_id=RUN_ID, attempt_id="attempt-1",
        instance_id=INSTANCE_ID, capability="review",
        arguments={
            "work_item_id": request["arguments"]["work_item_id"],
            "target_artifact_refs": [INPUT_REF],
            "review_profile": "quality"},
        scope=("work",), requested_by="tester", requested_at=NOW,
        idempotency_key="idem-no-result", timeout_seconds=60,
        preview_digest="sha256:" + "a" * 64, mode="confirm")))

    assert receipt.outcome == "failed"
    assert "names no result artifact" in receipt.detail
    assert _fakecodex.task_spawns(log) == [], "A_MODEL_CALL_WAS_SPENT"
    assert adapter._review_attempts == {}
