"""A raw journal claiming a review it cannot account for replays as CORRUPT.

The writer already refuses every substitution below. The writer is not the
subject: a journal is bytes on a disk, it outlives the process that wrote it, and
replay is where a build decides whether to believe them. Anything replay does not
check is a thing an operator can be shown as verified work that never happened.

Five relations, and existence was all that was held before. The source action was
known, it had been observed, and every input id was SOME artifact this run knew
-- none of which says the document is the one the action asked for:

1. the source action really carries `review`. Nothing else publishes an artifact;
2. the artifact's reference is the one the request named as its result;
3. its input ids are exactly what the request's own references resolve to, IN THE
   ORDER the request named them;
4. the verification evidence digests THAT artifact;
5. the succeeded result names that evidence.

Every case below rewrites ONE field of a real, honest journal and asserts the run
no longer replays. The honest journal is the positive control: rewritten with no
change at all, it still reads, so a case that fails is failing for the field it
edited rather than for the rewriting.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from conductor.command.adapters import AdapterRegistry
from conductor.command.artifacts import (
    ArtifactDocument,
    validate_artifact_source,
)
from conductor.command.attempts import AttemptEvent
from conductor.command.contract_values import ContractError
from conductor.command.contracts import (
    ActionProposal,
    ActionRequest,
    RunEnvelope,
    canonical_json,
)
from conductor.command.run_store import CorruptRun, RunStore, snapshot_digest
from conductor.command.runtime import (
    AttemptState,
    Budget,
    Confirmation,
    ControlRuntime,
)

from tests import _fakeclaude
from tests.test_command_claude_review import CONFIG, INSTANCE_ID, _Ids
from tests.test_command_claude_transport import NOW, a_harness

RUN_ID = "run-causality"
#: TWO inputs, because order is one of the relations and a single input cannot
#: show it. Their refs are distinct so a swap is observable.
FIRST_REF, SECOND_REF = "artifact-brief", "artifact-notes"
#: Seeded and never asked for. A substitution needs a KNOWN artifact to name, or
#: it is refused for being unknown and says nothing about the relation under
#: test.
SPARE_REF = "artifact-spare"
OUTPUT_REF = "artifact-reviewed"
ARGUMENTS = {
    "work_item_id": "work-001",
    "target_artifact_refs": [FIRST_REF, SECOND_REF],
    "result_artifact_ref": OUTPUT_REF,
    "review_profile": "quality",
}


def _honest_run(tmp_path: Path):
    """One real review, through the real runtime, over two durable inputs."""
    adapter, root, _log = a_harness(
        tmp_path, **{_fakeclaude.EMIT_REVIEW: "enabled-review-output"})
    store = RunStore(root)
    store.create_run(
        RunEnvelope(
            run_id=RUN_ID, cycle_id="review-cycle", created_at=NOW,
            config_digest=snapshot_digest(CONFIG), mode="confirm"),
        CONFIG)
    for index, ref in enumerate((FIRST_REF, SECOND_REF, SPARE_REF), start=1):
        store.append(ArtifactDocument(
            artifact_id=f"artifact-seed-{index}", artifact_ref=ref,
            run_id=RUN_ID, created_at=NOW, media_type="text/markdown",
            content=f"# {ref}\n\nmaterial number {index}."))
    proposal = ActionProposal(
        proposal_id="proposal-causality", run_id=RUN_ID,
        attempt_id="attempt-causality", instance_id=INSTANCE_ID,
        capability="review", arguments=ARGUMENTS, scope=("work",),
        proposed_by="lane", proposed_at=NOW, timeout_seconds=60,
        rationale="review two durable inputs", config_digest=snapshot_digest(CONFIG))
    store.append(proposal)
    runtime = ControlRuntime(
        store, AdapterRegistry([adapter]), clock=lambda: NOW, ids=_Ids())
    attempt = runtime.execute(runtime.authorize(
        Confirmation(
            confirmation_id="confirmation-causality", run_id=RUN_ID,
            proposal_id=proposal.proposal_id,
            preview_digest=proposal.preview_digest, capability="review",
            scope=("work",), config_digest=proposal.config_digest,
            confirmed_by="release-owner", confirmed_at=NOW),
        budget=Budget(max_actions=8, max_action_seconds=3600,
                      max_confirmation_age_seconds=3600)))
    assert attempt.state is AttemptState.SUCCEEDED, attempt.receipt.detail
    return store, root


def _rewrite(store: RunStore, edit) -> None:
    """Apply one edit to the raw journal, exactly as a tamperer would.

    Read as text, parsed, one field changed, written back. Nothing goes through
    the store's own writer, which is the whole point: the writer already refuses
    every one of these.
    """
    path = Path(store.run_path(RUN_ID)) / "records.jsonl"
    rows = [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]
    edit(rows)
    path.write_text(
        "".join(canonical_json(row) + "\n" for row in rows),
        encoding="utf-8", newline="\n")


def _of_type(rows: list[dict], record_type: str) -> list[dict]:
    return [row["record"] for row in rows if row["record_type"] == record_type]


def _produced(rows: list[dict]) -> dict:
    """The review's OWN artifact, which is the one with a source action."""
    return next(
        row for row in _of_type(rows, "artifact")
        if row.get("source_action_id") is not None)


def test_the_honest_journal_replays_and_is_the_control_for_every_case(tmp_path):
    """Rewritten with no change at all, a real journal still reads.

    Without this the cases below could all be passing because the rewriting
    itself corrupts the file, and every one of them would look like a guard.
    """
    store, _root = _honest_run(tmp_path)

    _rewrite(store, lambda rows: None)

    recovered = store.read(RUN_ID)
    assert recovered.warnings == ()
    produced = _produced([
        {"record_type": row.kind, "record": row.value.as_dict()}
        for row in recovered.records])
    assert produced["artifact_ref"] == OUTPUT_REF
    assert produced["input_artifact_ids"] == ["artifact-seed-1", "artifact-seed-2"]


def _reseal(rows: list[dict]) -> None:
    """Re-digest the later links, so a case is wrong in exactly ONE way.

    Editing the artifact changes its digest, which breaks the verification link
    as well -- and then the case is caught by whichever rule runs first, not by
    the one it is named for. Five mutations were GREEN because of this: the
    relation each named could be removed entirely and the case still failed, on
    the neighbour.

    So every artifact edit reseals the evidence that digests it. What remains
    broken is the one relation the case is about.
    """
    produced = ArtifactDocument.from_dict(_produced(rows))
    _of_type(rows, "evidence")[0]["digest"] = produced.digest()


def _capability_is_not_review(rows: list[dict]) -> None:
    request = _of_type(rows, "action_request")[0]
    request["capability"] = "dispatch"


def _result_ref_is_another_name(rows: list[dict]) -> None:
    _produced(rows)["artifact_ref"] = "artifact-somewhere-else"
    _reseal(rows)


def _inputs_are_reordered(rows: list[dict]) -> None:
    produced = _produced(rows)
    produced["input_artifact_ids"] = list(
        reversed(produced["input_artifact_ids"]))
    _reseal(rows)


def _inputs_name_another_known_artifact(rows: list[dict]) -> None:
    produced = _produced(rows)
    # A real artifact of this run, and one the request never asked for.
    produced["input_artifact_ids"] = ["artifact-seed-1", "artifact-seed-3"]
    _reseal(rows)


def _inputs_drop_one(rows: list[dict]) -> None:
    produced = _produced(rows)
    produced["input_artifact_ids"] = produced["input_artifact_ids"][:1]
    _reseal(rows)


def _evidence_digests_something_else(rows: list[dict]) -> None:
    evidence = _of_type(rows, "evidence")[0]
    evidence["digest"] = "sha256:" + "b" * 64


def _result_names_no_evidence(rows: list[dict]) -> None:
    result = _of_type(rows, "action_result")[0]
    result["evidence_refs"] = []


def _the_verification_is_deleted(rows: list[dict]) -> None:
    """No evidence row at all, and a result that does not claim one.

    This is the only shape that reaches the FIRST half of the result rule --
    "produced an artifact and succeeded with no verification evidence". Clearing
    the reference alone leaves the evidence standing and lands on the second
    half instead, which is what made a mutation on the first half GREEN.
    """
    rows[:] = [row for row in rows if row["record_type"] != "evidence"]
    _of_type(rows, "action_result")[0]["evidence_refs"] = []


def _result_names_another_evidence(rows: list[dict]) -> None:
    result = _of_type(rows, "action_result")[0]
    result["evidence_refs"] = ["evidence-elsewhere"]


#: One substitution each, named by the relation it breaks.
SUBSTITUTIONS = (
    # Lands on the proposal chain rather than on the artifact rule -- a request
    # may not say a capability its own proposal did not. Kept because the
    # relation is what matters, not which guard reaches it first; the artifact
    # rule's own half is held directly below, where a whole journal cannot go.
    ("request-capability", _capability_is_not_review),
    ("result-ref", _result_ref_is_another_name),
    ("input-order", _inputs_are_reordered),
    ("input-identity", _inputs_name_another_known_artifact),
    ("input-count", _inputs_drop_one),
    ("evidence-digest", _evidence_digests_something_else),
    ("result-names-nothing", _result_names_no_evidence),
    ("verification-deleted", _the_verification_is_deleted),
    # Lands on the attempt-event chain: a result may not name evidence that
    # never followed an observed attempt. The half that IS the artifact chain's
    # own is `result-names-nothing` above.
    ("result-names-another", _result_names_another_evidence),
)


@pytest.mark.parametrize(
    "label,edit", SUBSTITUTIONS, ids=[row[0] for row in SUBSTITUTIONS])
def test_a_substituted_journal_is_corrupt_rather_than_a_verified_run(
        tmp_path, label, edit):
    """Every one of these replayed as a sound, verified run before.

    `CorruptRun` and not a warning: a warning is something a caller may read and
    carry on past, and there is no honest way to carry on past a journal whose
    own records do not account for each other.
    """
    store, _root = _honest_run(tmp_path)

    _rewrite(store, edit)

    with pytest.raises(CorruptRun):
        store.read(RUN_ID)


def test_a_dispatch_verification_is_left_alone_by_the_artifact_rules(tmp_path):
    """The rules are about a review's chain and may not judge another's.

    A dispatch's verification digests the CHANGE it made -- a fact with no
    document behind it -- so a rule demanding an artifact for every verification
    would refuse every honest dispatch in the product.
    """
    store, _root = _honest_run(tmp_path)
    rows = [json.loads(line) for line in (
        Path(store.run_path(RUN_ID)) / "records.jsonl").read_text(
            encoding="utf-8").splitlines() if line.strip()]
    evidence = _of_type(rows, "evidence")[0]

    # The same evidence row, standing for an action that produced no artifact.
    from conductor.command.artifacts import validate_review_evidence
    from conductor.command.contracts import EvidenceRef

    stray = EvidenceRef.from_dict(
        dict(evidence, uri="verification/action-with-no-artifact"))

    validate_review_evidence(stray, ())  # no prior artifact: nothing to judge


def _with_temp_root():
    return Path(tempfile.mkdtemp(dir=r"C:\Users\User\AppData\Local\Temp\a6"))


def test_an_artifact_whose_source_action_is_not_a_review_is_refused():
    """The relation a whole journal cannot reach, asserted where it lives.

    A request may not carry a capability its own proposal did not, and that
    older rule speaks first -- so no rewriting of a real journal can put a
    dispatch action under a review's artifact. The relation still has to hold:
    nothing but a review publishes a document, and a build that assumed so
    without saying so would be one edit away from a dispatch's evidence being
    read as an artifact's.

    So it is asked of the rule directly, with the two records it judges, and
    that is stated rather than hidden -- the same shape as any claim about a
    state this repository's fixtures cannot create.
    """
    request = ActionRequest(
        action_id="action-1", run_id=RUN_ID, attempt_id="attempt-1",
        instance_id=INSTANCE_ID, capability="dispatch",
        arguments={
            "work_item_id": "work-001", "instruction_ref": "instr-001",
            "profile": "implement", "artifact_refs": [],
            "output_limit_profile": "normal"},
        scope=("work",), requested_by="tester", requested_at=NOW,
        idempotency_key="idem-1", timeout_seconds=60,
        preview_digest="sha256:" + "a" * 64, mode="confirm")
    observed = AttemptEvent(
        event_id="event-1", run_id=RUN_ID, action_id="action-1",
        attempt_id="attempt-1", instance_id=INSTANCE_ID,
        adapter_id="claude-code", phase="execution_observed", recorded_at=NOW,
        request_digest="sha256:" + "c" * 64, recovery_ref="recovery-1",
        outcome="succeeded", exit_code=0, schema_version=2)
    produced = ArtifactDocument(
        artifact_id="artifact-out-1", artifact_ref=OUTPUT_REF, run_id=RUN_ID,
        created_at=NOW, media_type="text/markdown", content="# review\n",
        source_action_id="action-1", input_artifact_ids=())

    with pytest.raises(ContractError, match="publishes no artifact"):
        validate_artifact_source(produced, (request, observed))
