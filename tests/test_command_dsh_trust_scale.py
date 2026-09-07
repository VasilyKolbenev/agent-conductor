"""What a dsh exit code buys, driven through the REAL runtime, not a scripted one.

Codex drove the whole Confirm runtime over the fake dsh entrypoint at the prior
SHA and read back an inverted scale:

    NO_CHANGE   -> succeeded, evidence=()
    WITH_CHANGE -> verification_failed, evidence=()

An attempt that changed NOTHING reached the strongest terminal state in the
machine, and an attempt that changed a real file reached a weaker one. Absence of
proof was being read as proof: the adapter answered ``unavailable`` -- the token
the runtime reserves for "this adapter exposes no verifier at all" -- and the
runtime let observed process success stand as the terminal word.

The scale this module holds is the honest one. Exit zero is an observation of a
process and buys nothing beyond that. A task that changed nothing still ends in
``verification_failed``. A contained change now earns one durable EvidenceRef,
recorded after the observation, so only that row reaches ``succeeded``. It wins
because of evidence, never because of the exit code.

The second half of the same honesty is the prompt. A dispatch whose task text
names only an instruction IDENTIFIER would send the real dsh a vague sentence
instead of the user's task, so the instruction is MATERIALIZED from a contained
file the workspace owns, and a dispatch that cannot materialize it refuses
before any child exists rather than dispatching a prompt that is not the task.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from conductor.command.adapters import AdapterRegistry
from conductor.command.adapters.harness_workspace import WORK_DIR
from conductor.command.contracts import ActionProposal, RunEnvelope
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.runtime import (
    AttemptState,
    Budget,
    Confirmation,
    ControlRuntime,
)

from tests import _fakedsh
from tests.test_command_dsh_harness import (
    DIGEST,
    NOW,
    PROVIDER_ID,
    a_harness,
    a_request,
    run_once,
)

INSTANCE = "dsh-dev"
RUN_ID = "run-dsh"
CONFIG = {
    "cycle": {"id": "dsh-orbit", "phases": ["dispatch"]},
    "instances": [{"id": INSTANCE, "adapter": PROVIDER_ID}],
}
ARGUMENTS = {
    "work_item_id": "work-001", "instruction_ref": "instr-001",
    "profile": "implement", "artifact_refs": [],
    "output_limit_profile": "normal"}


def _ids():
    counters: dict[str, int] = {}

    def mint(purpose):
        counters[purpose] = counters.get(purpose, 0) + 1
        return f"{purpose}-{counters[purpose]}"

    return mint


def _driven(tmp_path: Path, **knobs: str):
    """Authorize and execute ONE dsh dispatch through the real ControlRuntime."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    adapter, root, log = a_harness(tmp_path, **knobs)
    store = RunStore(root)
    store.create_run(
        RunEnvelope(
            run_id=RUN_ID, cycle_id="dsh-orbit", created_at=NOW,
            config_digest=snapshot_digest(CONFIG), mode="confirm"),
        CONFIG)
    # The trust witness executes today's task; it is not a saved legacy request.
    proposal = ActionProposal(
        proposal_id="proposal-dsh", run_id=RUN_ID, attempt_id="attempt-dsh",
        instance_id=INSTANCE, capability="dispatch", arguments=ARGUMENTS,
        scope=("work",), proposed_by="lane", proposed_at=NOW, timeout_seconds=60,
        rationale="drive the dsh harness through the real Confirm runtime",
        config_digest=snapshot_digest(CONFIG), input_binding="proposal-v1")
    store.append(proposal)
    runtime = ControlRuntime(
        store, AdapterRegistry([adapter]), clock=lambda: NOW, ids=_ids())
    confirmation = Confirmation(
        confirmation_id="confirmation-dsh", run_id=RUN_ID,
        proposal_id=proposal.proposal_id, preview_digest=proposal.preview_digest,
        capability="dispatch", scope=("work",),
        config_digest=proposal.config_digest, confirmed_by="release-owner",
        confirmed_at=NOW)
    authorization = runtime.authorize(
        confirmation,
        budget=Budget(max_actions=8, max_action_seconds=3600,
                      max_confirmation_age_seconds=3600))
    return runtime.execute(authorization), store, root, log


def _row(attempt) -> tuple[str, tuple[str, ...]]:
    """The exact pair Codex printed: the terminal state and its evidence refs."""
    return attempt.state.value, tuple(attempt.receipt.evidence_refs)


def _kinds(store) -> list[str]:
    return [row.kind for row in store.read(RUN_ID).records]


# --- the two-row table, driven end to end ------------------------------------


def test_a_dsh_attempt_that_changed_nothing_never_reaches_succeeded(tmp_path):
    attempt, store, _root, log = _driven(tmp_path)

    assert _row(attempt) != ("succeeded", ()), "NO_CHANGE -> succeeded, evidence=()"
    assert attempt.state is AttemptState.VERIFICATION_FAILED
    assert attempt.receipt.outcome == "verification_failed"
    assert attempt.verification_evidence == ()
    # The process WAS observed, and that observation is the durable fact exit
    # zero actually bought: one execution_observed event, and no evidence record.
    assert "evidence" not in _kinds(store)
    assert len(_fakedsh.task_spawns(log)) == 1


def test_a_dsh_attempt_with_a_real_change_earns_durable_evidence(tmp_path):
    attempt, store, root, _log = _driven(
        tmp_path, FAKEDSH_WRITE_FILE="added.txt:written by the task")

    assert (root / WORK_DIR / "work-001" / "added.txt").exists()
    assert attempt.state is AttemptState.SUCCEEDED
    assert len(attempt.verification_evidence) == 1
    assert len(attempt.receipt.evidence_refs) == 1
    assert _kinds(store).count("evidence") == 1


def test_the_recorded_trust_table_distinguishes_observation_from_evidence(tmp_path):
    """Only the row carrying an actual contained change may become success."""
    no_change, _s, _r, _l = _driven(tmp_path / "a")
    with_change, _s2, _r2, _l2 = _driven(
        tmp_path / "b", FAKEDSH_WRITE_FILE="added.txt:real work")

    table = {"NO_CHANGE": _row(no_change), "WITH_CHANGE": _row(with_change)}

    assert table["NO_CHANGE"] == ("verification_failed", ())
    assert table["WITH_CHANGE"][0] == "succeeded"
    assert len(table["WITH_CHANGE"][1]) == 1, table


def test_a_direct_adapter_without_the_runs_store_cannot_mint_evidence(tmp_path):
    """Evidence is a durable run fact, not an identifier from an isolated seam."""
    adapter, _root, _log = a_harness(
        tmp_path, FAKEDSH_WRITE_FILE="added.txt:written by the task")
    request = a_request()
    receipt = run_once(adapter, request)

    verification = adapter.verify(request, receipt)

    assert verification.state != "verified", "UNBACKED_VERIFIED=True"
    assert verification.evidence_refs == ()
    assert verification.state != "unavailable", "ABSENCE_READ_AS_NO_VERIFIER=True"


def test_a_dsh_attempt_with_no_snapshot_is_not_an_absent_verifier(tmp_path):
    """A restarted adapter holds no snapshot; that is absence of proof, not of a verifier."""
    adapter, _root, _log = a_harness(tmp_path)
    request = a_request()
    receipt = run_once(adapter, request)
    fresh = type(adapter)(
        adapter._pin, adapter._runner, root=adapter._root, clock=lambda: NOW,
        ids=lambda purpose: f"{purpose}-fresh", adapter_id=PROVIDER_ID)

    verification = fresh.verify(request, receipt)

    assert verification.state != "unavailable", "ABSENCE_READ_AS_NO_VERIFIER=True"
    assert verification.evidence_refs == ()


# --- the prompt is the task, or there is no prompt ----------------------------


def _task_token(log) -> str:
    return _fakedsh.task_spawns(log)[0]["argv"][2]


def _instruction(root: Path) -> Path:
    """The one contained name a materialized instruction may be read from."""
    from conductor.command.adapters.harness_workspace import INSTRUCTION_DIR

    return root / INSTRUCTION_DIR / "instr-001.md"


def test_the_dispatched_task_carries_the_materialized_instruction_not_its_id(
        tmp_path):
    adapter, root, log = a_harness(tmp_path)
    body = "Rewrite the digest walk so it never follows a junction."
    _instruction(root).write_text(
        body, encoding="utf-8", newline="\n")

    run_once(adapter, a_request())

    token = _task_token(log)
    assert body in token, f"INSTRUCTION_NOT_MATERIALIZED={token!r}"
    assert "work-001" in token and "implement" in token


def test_a_dispatch_whose_instruction_cannot_be_materialized_spawns_nothing(
        tmp_path):
    adapter, root, log = a_harness(tmp_path)
    _instruction(root).unlink()

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "failed"
    assert _fakedsh.spawns(log) == [], "VAGUE_PROMPT_DISPATCHED=True"
    assert receipt.exit_code is None


@pytest.mark.parametrize("body", ["", "   \n"])
def test_an_empty_instruction_is_not_a_task_and_is_refused_before_any_child(
        tmp_path, body):
    adapter, root, log = a_harness(tmp_path)
    _instruction(root).write_text(
        body, encoding="utf-8", newline="\n")

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "failed"
    assert _fakedsh.spawns(log) == [], "VAGUE_PROMPT_DISPATCHED=True"


def test_an_instruction_reached_through_a_portal_is_never_read(tmp_path):
    from tests.sabotage_fixtures import plant_symlink, skip_when_unavailable

    adapter, root, log = a_harness(tmp_path)
    planted = tmp_path / "outside-instruction.md"
    planted.write_text("borrowed text", encoding="utf-8", newline="\n")
    target = _instruction(root)
    target.unlink()
    with skip_when_unavailable():
        plant_symlink(target, planted)

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "failed"
    assert _fakedsh.spawns(log) == [], "PORTAL_INSTRUCTION_READ=True"
    assert DIGEST not in (receipt.detail or "")
