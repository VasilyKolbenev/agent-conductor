"""A raw journal claiming a review it cannot account for replays as CORRUPT.

The writer already refuses every substitution below. The writer is not the
subject: a journal is bytes on a disk, it outlives the process that wrote it, and
replay is where a build decides whether to believe them. Anything replay does not
check is a thing an operator can be shown as verified work that never happened.

Eight relations. Existence was all that was held at first -- the source action was
known, it had been observed, and every input id was SOME artifact this run knew,
none of which says the document is the one the action asked for:

1. the source action really carries `review`. Nothing else publishes an artifact;
2. the artifact's reference is the one the request named as its result;
3. its input ids are exactly what the request's own references resolve to, IN THE
   ORDER the request named them;
4. the verification evidence digests THAT artifact;
5. the succeeded result names that evidence.

And then a second round, because the five above were switched on by an ARTIFACT
being found rather than by the action's own capability -- so a journal that had
published none was read as a dispatch's and walked through all five:

6. a review's verification follows exactly one artifact of that review, and the
   document is ALREADY standing when the verification is judged;
7. one review carries one verification. Two verified rows are two answers;
8. a succeeded review stands on exactly one artifact and exactly one
   verification, and names that verification and nothing else.

Every case below rewrites ONE field of a real, honest journal and asserts the run
no longer replays. The honest journal is the positive control: rewritten with no
change at all, it still reads, so a case that fails is failing for the field it
edited rather than for the rewriting. The truncations are the other half of that
witness: an interrupted review claims LESS than it can account for, and still
replays.
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
    validate_review_evidence,
    validate_review_result,
)
from conductor.command.attempts import AttemptEvent
from conductor.command.contract_values import ContractError
from conductor.command.contracts import (
    ActionProposal,
    ActionRequest,
    ActionResultReceipt,
    EvidenceRef,
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


def _the_verification_is_duplicated(rows: list[dict]) -> None:
    """A SECOND verification for the same review, honest in every other field.

    Same uri, same digest, same adapter, its own id, standing right beside the
    first. Two verified answers to one question, and nothing in the journal says
    which one a result rests on.

    The terminal result goes with it, and that is what makes this wrong in
    exactly ONE way. A result has to name one row or the other, and either way
    the LAST link refuses it -- so the case would be caught by a rule it is not
    about, and a mutation on the rule it IS about would read green. What is left
    is `no-terminal-result-yet`, a prefix asserted to replay two tests below,
    plus one verification too many.
    """
    index = next(spot for spot, row in enumerate(rows)
                 if row["record_type"] == "evidence")
    twin = dict(rows[index]["record"], evidence_id="evidence-twin")
    rows.insert(index + 1, {"record_type": "evidence", "record": twin})
    rows[:] = [row for row in rows if row["record_type"] != "action_result"]


def _the_verification_stands_before_the_artifact(rows: list[dict]) -> None:
    """Not one field is edited: the two rows swap places.

    A verification that digests a document nobody has published yet. The rule
    used to look for the artifact, fail to find it, and read the row as a
    dispatch's -- so the earlier the tamper, the less was held.
    """
    artifact = next(spot for spot, row in enumerate(rows)
                    if row["record_type"] == "artifact"
                    and row["record"].get("source_action_id") is not None)
    evidence = next(spot for spot, row in enumerate(rows)
                    if row["record_type"] == "evidence")
    assert artifact < evidence, "production publishes the document first"
    rows[artifact], rows[evidence] = rows[evidence], rows[artifact]


def _the_produced_artifact_is_deleted(rows: list[dict]) -> None:
    """A succeeded review with nothing whatever to show for itself.

    The document and the verification that digested it are both gone and the
    result claims neither, so every rule that keyed on the artifact found none
    and stood down. What remains is a receipt saying a review succeeded, in a
    journal that cannot show one byte of what it produced.
    """
    produced_id = _produced(rows)["artifact_id"]
    rows[:] = [
        row for row in rows
        if row["record_type"] != "evidence"
        and not (row["record_type"] == "artifact"
                 and row["record"]["artifact_id"] == produced_id)]
    _of_type(rows, "action_result")[0]["evidence_refs"] = []


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
    # The three shapes that walked straight through, because every review rule
    # was switched on by an artifact BEING there rather than by the action's own
    # capability. Each is the same defect read from a different side.
    ("verification-duplicated", _the_verification_is_duplicated),
    ("verification-before-artifact", _the_verification_stands_before_the_artifact),
    ("artifact-deleted", _the_produced_artifact_is_deleted),
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


def _the_tail_after_the_artifact_is_lost(rows: list[dict]) -> None:
    """A crash between publishing the document and verifying it."""
    rows[:] = [row for row in rows
               if row["record_type"] not in ("evidence", "action_result")]


def _the_terminal_result_is_lost(rows: list[dict]) -> None:
    """A crash between verifying the document and writing the receipt."""
    rows[:] = [row for row in rows if row["record_type"] != "action_result"]


#: The two prefixes an interrupted review really leaves. Neither is a broken
#: chain, and a rule strict enough to refuse them would make a crash
#: unrecoverable rather than making a tamper detectable.
CRASH_PREFIXES = (
    ("no-verification-yet", _the_tail_after_the_artifact_is_lost),
    ("no-terminal-result-yet", _the_terminal_result_is_lost),
)


@pytest.mark.parametrize(
    "label,edit", CRASH_PREFIXES, ids=[row[0] for row in CRASH_PREFIXES])
def test_an_interrupted_review_still_replays_up_to_where_it_stopped(
        tmp_path, label, edit):
    """The other side of the witness, and the side that costs if it is missed.

    Every relation above is about a journal claiming MORE than it can account
    for. Truncation claims less, and a rule that could not tell the two apart
    would answer CORRUPT to an ordinary crash -- which is a build that cannot be
    restarted, dressed as a build that checks its work.
    """
    store, _root = _honest_run(tmp_path)

    _rewrite(store, edit)

    recovered = store.read(RUN_ID)
    assert recovered.warnings == ()
    assert _produced([
        {"record_type": row.kind, "record": row.value.as_dict()}
        for row in recovered.records])["artifact_ref"] == OUTPUT_REF


def _a_dispatch_request(action_id: str) -> ActionRequest:
    """One real dispatch, so a claim about dispatch is about a dispatch."""
    return ActionRequest(
        action_id=action_id, run_id=RUN_ID, attempt_id="attempt-dispatch",
        instance_id=INSTANCE_ID, capability="dispatch",
        arguments={
            "work_item_id": "work-001", "instruction_ref": "instr-001",
            "profile": "implement", "artifact_refs": [],
            "output_limit_profile": "normal"},
        scope=("work",), requested_by="tester", requested_at=NOW,
        idempotency_key="idem-dispatch", timeout_seconds=60,
        preview_digest="sha256:" + "a" * 64, mode="confirm")


def _honest_evidence(store: RunStore, **changes) -> EvidenceRef:
    """The run's own verification row, with named fields moved."""
    rows = [json.loads(line) for line in (
        Path(store.run_path(RUN_ID)) / "records.jsonl").read_text(
            encoding="utf-8").splitlines() if line.strip()]
    return EvidenceRef.from_dict(dict(_of_type(rows, "evidence")[0], **changes))


def test_a_dispatch_verification_is_left_alone_by_the_artifact_rules(tmp_path):
    """The rules are about a review's chain and may not judge another's.

    A dispatch's verification digests the CHANGE it made -- a fact with no
    document behind it -- so a rule demanding an artifact for every verification
    would refuse every honest dispatch in the product.

    The dispatch REQUEST is present, because that is what makes this a claim
    about dispatch: which chain a record belongs to is read from the capability,
    so a prior history with no request in it would be exercising the other
    reading entirely -- which is the test below, not this one.
    """
    store, _root = _honest_run(tmp_path)
    request = _a_dispatch_request("action-dispatched")
    stray = _honest_evidence(store, uri=f"verification/{request.action_id}")

    validate_review_evidence(stray, (request,))  # a dispatch: nothing to judge


def test_a_verification_for_an_action_this_run_does_not_know_is_not_judged(
        tmp_path):
    """The second reading, stated rather than left as a silence.

    An evidence row may name an action no request stands for; replay admits it,
    because nothing here can judge a chain whose authorizing request is absent.
    What such a row cannot do is be NAMED by a result -- `attempt_replay` admits
    only evidence appended after that action's own observed attempt event -- and
    that is why leaving it unjudged here costs nothing.
    """
    store, _root = _honest_run(tmp_path)
    stray = _honest_evidence(store, uri="verification/action-nobody-requested")

    validate_review_evidence(stray, ())


def test_a_succeeded_review_may_not_rest_on_a_verification_with_no_artifact(
        tmp_path):
    """The last link asks its own question rather than delegating it.

    On a whole journal `validate_review_evidence` meets this shape first: a
    verification with no document behind it is refused where it stands, so no
    substitution can leave one standing for the result rule to find. The
    relation still belongs here -- a rule that read "a verification exists" as
    "a document exists" would be resting on its neighbour, and a neighbour is
    not a reason.

    So it is asked of the rule directly, with the records it judges, and that is
    stated rather than hidden -- the same shape as any claim about a state this
    repository's fixtures cannot create.
    """
    store, _root = _honest_run(tmp_path)
    values = tuple(row.value for row in store.read(RUN_ID).records)
    request = next(value for value in values if isinstance(value, ActionRequest))
    evidence = next(value for value in values if isinstance(value, EvidenceRef))
    result = next(value for value in values
                  if isinstance(value, ActionResultReceipt))

    with pytest.raises(ContractError, match="artifacts of its own"):
        validate_review_result(result, (request, evidence))


def test_a_succeeded_review_may_not_name_its_evidence_among_others(tmp_path):
    """Exactness, asked directly, because a whole journal cannot reach it.

    Given one artifact and one verification, every OTHER id a result could name
    is already refused by `attempt_replay` -- so on a real journal the exact
    comparison and a mere intersection agree, and no substitution can tell them
    apart. The relation is still the product's: a receipt names the chain it
    rests on, not a set that happens to contain it.
    """
    store, _root = _honest_run(tmp_path)
    values = tuple(row.value for row in store.read(RUN_ID).records)
    result = next(value for value in values
                  if isinstance(value, ActionResultReceipt))
    prior = values[:values.index(result)]
    padded = ActionResultReceipt.from_dict(dict(
        result.as_dict(),
        evidence_refs=[*result.evidence_refs, "evidence-elsewhere"]))

    validate_review_result(result, prior)  # the control: the real one passes
    with pytest.raises(ContractError, match="exactly"):
        validate_review_result(padded, prior)


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
