"""What one adapter may hold between `execute` and `verify`, and whose it is.

An adapter instance serves every worker bound to its root, so everything it
keeps across the two halves of an action is shared state -- and the only thing
that makes such state safe is the key it is filed under and the guarantee that it
goes away.

Three relations, each reproduced as a defect before it was closed:

- **an `action_id` is not an identity.** Nothing makes one unique across runs:
  the contract validates a charset, the store is per-run, and a runtime mints
  `action-1` for the first action of every run it serves. Filed under that alone,
  one run's verification consumed another run's review;
- **what is held may not be the material.** The caches carried whole
  `ArtifactDocument`s -- an operator's durable content -- where the only thing
  ever read from them was an artifact ID. A probe found a seeded secret still
  resident after a succeeded dispatch;
- **every road out of `verify` must forget.** Three did not: the early refusal of
  a non-succeeded outcome, the raise when a result does not belong to its
  request, and the two hand-backs to the base verifier.

The claims are written against the ARTIFACT-AWARE transport because that is the
one that holds material, and the key they rest on is the base's too.
"""
from __future__ import annotations

from pathlib import Path

from conductor.command.adapters.headless_values import attempt_relation
from conductor.command.artifacts import ArtifactDocument
from conductor.command.contracts import (
    ActionRequest,
    ActionResultReceipt,
    RunEnvelope,
)
from conductor.command.run_store import RunStore, snapshot_digest

from tests import _fakeclaude
from tests.test_command_claude_review import CONFIG, INPUT_REF, OUTPUT_REF
from tests.test_command_claude_transport import NOW, a_harness

#: The one action id both runs carry, which is what a per-run mint really gives.
ACTION = "action-1"
ATTEMPT = "attempt-1"
INSTANCE = "claude-reviewer"
#: Distinctive, and seeded as an operator's own durable material.
SECRET = "PROPRIETARY-SPEC-BODY-THAT-MUST-NOT-LINGER"

REVIEW_ARGUMENTS = {
    "work_item_id": "work-001",
    "target_artifact_refs": [INPUT_REF],
    "result_artifact_ref": OUTPUT_REF,
    "review_profile": "quality",
}
DISPATCH_ARGUMENTS = {
    "work_item_id": "work-001", "instruction_ref": "instr-001",
    "profile": "implement", "artifact_refs": [INPUT_REF],
    "output_limit_profile": "normal",
}


def a_request(run_id: str, capability: str = "review") -> ActionRequest:
    """One action, in whichever run asks for it. The other three ids never move."""
    return ActionRequest(
        action_id=ACTION, run_id=run_id, attempt_id=ATTEMPT,
        instance_id=INSTANCE, capability=capability,
        arguments=REVIEW_ARGUMENTS if capability == "review" else DISPATCH_ARGUMENTS,
        scope=("work",), requested_by="tester", requested_at=NOW,
        idempotency_key=f"idem-{run_id}", timeout_seconds=60,
        preview_digest="sha256:" + "a" * 64, mode="confirm")


def a_receipt(request: ActionRequest, *, outcome: str = "succeeded",
              exit_code: int | None = 0, **changes) -> ActionResultReceipt:
    """A receipt for one request. Built here, because that is the point.

    A restarted runtime replays a receipt it stored; an adapter that trusted the
    one it happened to return last would be trusting its own memory rather than
    the relation it was handed.
    """
    values = {
        "action_id": request.action_id, "run_id": request.run_id,
        "attempt_id": request.attempt_id, "instance_id": request.instance_id}
    values.update(changes)
    return ActionResultReceipt(
        receipt_id="receipt-1", outcome=outcome, observed_at=NOW,
        exit_code=exit_code, **values)


def seed(store: RunStore, run_id: str, artifact_id: str, body: str) -> str:
    store.create_run(
        RunEnvelope(
            run_id=run_id, cycle_id="review-cycle", created_at=NOW,
            config_digest=snapshot_digest(CONFIG), mode="confirm"),
        CONFIG)
    store.append(ArtifactDocument(
        artifact_id=artifact_id, artifact_ref=INPUT_REF, run_id=run_id,
        created_at=NOW, media_type="text/markdown", content=body))
    return artifact_id


def a_reviewer(tmp_path: Path, **knobs: str):
    """One adapter, and the runs are seeded into the root it was built on."""
    # The leak scan stays OFF here: it would demand a probe token inside every
    # seeded artifact, which is a fact about that suite's witness rather than
    # about what an adapter may hold.
    adapter, root, log = a_harness(tmp_path, **{
        _fakeclaude.EMIT_REVIEW: "enabled-review-output", **knobs})
    return adapter, RunStore(root), root, log


def _held(adapter) -> str:
    """Everything this adapter is holding, as text a search can read."""
    return "".join(repr(cache) for cache in (
        adapter._dispatch_inputs, adapter._review_attempts, adapter._attempts))


# --- an action id is not an identity -----------------------------------------


def test_a_verification_for_another_run_never_consumes_this_ones_review(tmp_path):
    """The substitution, driven: same action, different run, nothing shared.

    Run A reviews and leaves its output waiting for verification. Run B then
    asks to verify an action carrying the SAME id, the same attempt id and the
    same instance -- everything an `action_id` key can see.

    What separates a fixed build from the broken one is NOT that run B is
    refused: under the old key it was refused too, because the store declines an
    artifact whose source action that run never recorded. It is that run B's
    verification CONSUMED run A's review on the way to being refused -- popped it
    by action id, tried to write A's text into B's journal, and left A with
    nothing to be verified from. So what is asserted is A's material: still
    there, still A's own, after B has come and gone.
    """
    adapter, store, _root, _log = a_reviewer(tmp_path)
    seed(store, "run-a", "artifact-a-seed", f"# A\n\n{SECRET}")
    seed(store, "run-b", "artifact-b-seed", "# B\n\nsomething else entirely.")
    request_a = a_request("run-a")
    receipt_a = adapter.execute(adapter.prepare(request_a))
    assert receipt_a.outcome == "succeeded", receipt_a.detail

    request_b = a_request("run-b")
    verification_b = adapter.verify(request_b, a_receipt(request_b))

    assert verification_b.state == "error", (
        "run B was handed a verification built out of run A's review")
    outputs = [
        row.value for row in store.read("run-b").records
        if row.kind == "artifact" and row.value.source_action_id is not None]
    assert outputs == [], f"RUN_B_RECORDED={[row.artifact_ref for row in outputs]}"
    held = adapter._review_attempts.get(attempt_relation(request_a))
    assert held is not None, "RUN_B_CONSUMED_RUN_AS_REVIEW"
    assert held.input_artifact_ids == ("artifact-a-seed",)


def test_what_an_attempt_leaves_is_filed_under_all_four_of_its_ids(tmp_path):
    """The key itself, read rather than inferred from behaviour.

    Behaviour tests can pass on a key that happens not to collide in the case
    they drive. This one says what the key IS, so a narrowing back to any subset
    of the four ids is a failure here rather than a defect found later.
    """
    adapter, store, _root, _log = a_reviewer(tmp_path)
    seed(store, "run-a", "artifact-a-seed", "# A\n\nreview this.")
    request = a_request("run-a")

    adapter.execute(adapter.prepare(request))

    assert list(adapter._review_attempts) == [
        ("run-a", ACTION, ATTEMPT, INSTANCE)]
    assert list(adapter._attempts) == [("run-a", ACTION, ATTEMPT, INSTANCE)]
    assert attempt_relation(request) == ("run-a", ACTION, ATTEMPT, INSTANCE)


# --- what is held may not be the material ------------------------------------


def test_a_dispatch_holds_no_artifact_content_after_its_action(tmp_path):
    """The inputs are IDS. The capability to hold content is gone, not unused.

    A dispatch resolves an operator's durable artifacts to build its task, and
    the only thing verification ever reads back from them is which ones they
    were. Holding the documents kept the whole material resident for as long as
    the entry lived -- and a succeeded dispatch whose verification never comes
    lives forever.
    """
    adapter, store, root, _log = a_reviewer(
        tmp_path, **{_fakeclaude.WRITE_FILE: "out.py:done"})
    seed(store, "run-a", "artifact-secret-1", f"# Spec\n\n{SECRET}")
    request = a_request("run-a", capability="dispatch")
    instructions = Path(root) / "instructions"
    instructions.mkdir(exist_ok=True)
    (instructions / "instr-001.md").write_text(
        "Add the guard.", encoding="utf-8", newline="\n")

    receipt = adapter.execute(adapter.prepare(request))

    assert receipt.outcome == "succeeded", receipt.detail
    assert adapter._dispatch_inputs[attempt_relation(request)] == (
        "artifact-secret-1",)
    assert SECRET not in _held(adapter), "THE_ADAPTER_STILL_HOLDS_THE_MATERIAL"


def test_a_review_holds_the_ids_of_what_it_read_and_not_the_documents(tmp_path):
    """The same narrowing on the review road, where the inputs are the subject."""
    adapter, store, _root, _log = a_reviewer(tmp_path)
    seed(store, "run-a", "artifact-a-seed", f"# A\n\n{SECRET}")
    request = a_request("run-a")

    adapter.execute(adapter.prepare(request))

    attempt = adapter._review_attempts[attempt_relation(request)]
    assert attempt.input_artifact_ids == ("artifact-a-seed",)
    assert SECRET not in _held(adapter), "THE_ADAPTER_STILL_HOLDS_THE_MATERIAL"


# --- every road out of verify forgets ----------------------------------------


def test_the_early_refusal_of_a_failed_result_still_forgets_the_attempt(tmp_path):
    """The road that returns before judging anything used to keep everything."""
    adapter, store, _root, _log = a_reviewer(tmp_path)
    seed(store, "run-a", "artifact-a-seed", f"# A\n\n{SECRET}")
    request = a_request("run-a")
    adapter.execute(adapter.prepare(request))
    assert attempt_relation(request) in adapter._review_attempts

    verification = adapter.verify(
        request, a_receipt(request, outcome="failed", exit_code=1))

    assert verification.state == "error"
    assert adapter._review_attempts == {} and adapter._attempts == {}
    assert SECRET not in _held(adapter)


def test_a_result_that_does_not_belong_raises_and_still_forgets(tmp_path):
    """Raising is not a licence to keep what the attempt left behind.

    `_hold_result` refuses a result whose four ids are not the request's -- a
    programming fault, and the right answer is to raise. It stands inside the
    try for exactly this reason: the discard runs on the way out either way.
    """
    adapter, store, _root, _log = a_reviewer(tmp_path)
    seed(store, "run-a", "artifact-a-seed", f"# A\n\n{SECRET}")
    request = a_request("run-a")
    adapter.execute(adapter.prepare(request))

    failed = False
    try:
        adapter.verify(request, a_receipt(request, run_id="run-elsewhere"))
    except Exception:  # noqa: BLE001 -- the type is the adapter's own refusal
        failed = True

    assert failed, "a foreign result must not be verified"
    assert adapter._review_attempts == {} and adapter._attempts == {}
    assert SECRET not in _held(adapter)
