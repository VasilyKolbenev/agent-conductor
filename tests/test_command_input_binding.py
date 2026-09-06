"""What a task reads is what stood when its proposal was written.

R04 of the review of ``8dec0e4``, half (b), under the owner's correction of
2026-09-06: *a source is bound when it is confirmed, never chosen again at
execution*. Two roads resolved their durable inputs as "the latest document
under the ref" AT EXECUTION -- the dispatch's ``artifact_refs`` and the
review's ``target_artifact_refs`` -- and the dispatch's instruction had no
durable road at all: it was a file under ``instructions/`` that ``conduct
init`` never writes. A document published between the confirmation and the
execution therefore substituted the material a person had confirmed, and a
person with no file could not run the shipped starter's first step from the
product.

The rule, held here end to end: the instruction is the latest durable
document under ``instruction_ref`` -- and every input the latest under its
ref -- among the records standing BEFORE the proposal the request was minted
from (``idempotency_key == "dispatch-<proposal_id>"``, the link the runtime
already writes). A document appended after that proposal is durable and is
not read; replay resolves the same document from the same bytes. No document
under the instruction's ref means the workspace file, byte-for-byte as before;
neither means the fixed containment refusal, before any preflight, with no
child spawned. The bound document's id joins the dispatch inputs, so the
evidence digest names it.

Every claim is measured on the far side: the fake child reports the length
and digest of the bytes it read and where the probe token stood, never the
text -- so "the child read the earlier document" is a digest equality against
a frame built from that document alone.
"""
from __future__ import annotations

import hashlib

from conductor.command.adapters import AdapterRegistry
from conductor.command.adapters.deep_commands import (
    DeepDispatchArgs,
    DeepReviewArgs,
)
from conductor.command.adapters.harness_profile import uncontained_detail
from conductor.command.adapters.harness_workspace import INSTRUCTION_DIR, WORK_DIR
from conductor.command.artifact_handoff import ArtifactHandoff
from conductor.command.artifacts import ArtifactDocument
from conductor.command.contract_values import ContractError
from conductor.command.contracts import ActionProposal, ActionRequest, RunEnvelope
from conductor.command.run_store import RunStore, StoreError, snapshot_digest
from conductor.command.runtime import (
    AttemptState,
    Budget,
    Confirmation,
    ControlRuntime,
)

from tests import _fakeclaude
from tests.test_command_artifact_dispatch import (
    ARGUMENTS,
    CONFIG,
    INSTANCE_ID,
    INSTRUCTION,
    RUN_ID,
    _Ids,
)
from tests.test_command_claude_review import (
    API_KEY,
    INPUT_REF,
    OUTPUT_REF,
    _confirmation,
    _proposal,
)
from tests.test_command_claude_review import ARGUMENTS as REVIEW_ARGUMENTS
from tests.test_command_claude_review import CONFIG as REVIEW_CONFIG
from tests.test_command_claude_review import PROBE as REVIEW_PROBE
from tests.test_command_claude_review import RUN_ID as REVIEW_RUN
from tests.test_command_claude_transport import NOW, a_harness, a_request, run_once

#: The shipped starter's own instruction reference: no file of that name is
#: ever written by `conduct init`, which is the finding.
DOC_REF = "instruction-plan"
PROBE = _fakeclaude.PROBE_PREFIX + "feed0123" * 8
UNAVAILABLE = "a durable dispatch input was unavailable, so no task was spawned"


def _document(artifact_id: str, artifact_ref: str, content: str,
              run_id: str = RUN_ID) -> ArtifactDocument:
    return ArtifactDocument(
        artifact_id=artifact_id, artifact_ref=artifact_ref, run_id=run_id,
        created_at=NOW, media_type="text/markdown", content=content)


def _proposal_for(body: dict) -> ActionProposal:
    return ActionProposal(
        proposal_id="proposal-bound", run_id=RUN_ID,
        attempt_id="attempt-bound", instance_id=INSTANCE_ID,
        capability="dispatch", arguments=body, scope=("work",),
        proposed_by="lane", proposed_at=NOW, timeout_seconds=60,
        rationale="carry out the bound sources",
        config_digest=snapshot_digest(CONFIG))


def _authorized(tmp_path, *, before=(), after=(), arguments=None, probe=True,
                instruction_file=True):
    """Documents, then the proposal, then more documents, then the Confirm.

    `before` stands when the proposal is written and `after` is appended
    over it before anything executes -- the shape the owner's control names.
    Answers with the runtime and the authorization it minted, so a caller
    may hand the request to the runtime or straight to the transport.
    """
    knobs = {_fakeclaude.WRITE_FILE: "implemented.py:verified change"}
    if probe:
        knobs[_fakeclaude.LEAK_CHECK] = "1"
    adapter, root, log = a_harness(tmp_path, instruction=INSTRUCTION, **knobs)
    if not instruction_file:
        (root / INSTRUCTION_DIR / "instr-001.md").unlink()
    store = RunStore(root)
    store.create_run(
        RunEnvelope(
            run_id=RUN_ID, cycle_id="artifact-cycle", created_at=NOW,
            config_digest=snapshot_digest(CONFIG), mode="confirm"),
        CONFIG)
    for document in before:
        store.append(document)
    body = {**ARGUMENTS, "artifact_refs": [], **(arguments or {})}
    proposal = _proposal_for(body)
    store.append(proposal)
    for document in after:
        store.append(document)
    confirmation = Confirmation(
        confirmation_id="confirmation-bound", run_id=RUN_ID,
        proposal_id=proposal.proposal_id,
        preview_digest=proposal.preview_digest, capability="dispatch",
        scope=("work",), config_digest=proposal.config_digest,
        confirmed_by="release-owner", confirmed_at=NOW)
    runtime = ControlRuntime(
        store, AdapterRegistry([adapter]), clock=lambda: NOW, ids=_Ids())
    budget = Budget(
        max_actions=8, max_action_seconds=3600,
        max_confirmation_age_seconds=3600)
    authorization = runtime.authorize(confirmation, budget=budget)
    return runtime, authorization, store, adapter, log, root, body


def _drive(tmp_path, **shape):
    """`_authorized`, then the runtime's own execute: the whole road."""
    runtime, authorization, store, adapter, log, root, body = _authorized(
        tmp_path, **shape)
    attempt = runtime.execute(authorization)
    return attempt, store, adapter, log, root, body


def _refused(tmp_path, **shape):
    """`_authorized`, then the TRANSPORT's own execute, for its receipt.

    The runtime's terminal receipt says only that the adapter reported a
    failure; the sentence under test is the transport's, so the authorized
    request -- the one that names its proposal -- is handed to it directly,
    exactly as the R04 probe did.
    """
    _runtime, authorization, store, adapter, log, root, body = _authorized(
        tmp_path, **shape)
    return run_once(adapter, authorization.request), store, adapter, log, root


def _frame(adapter, body: dict, instruction: str, inputs=()) -> bytes:
    """The bytes the child is owed, built from ONE instruction and ONE set."""
    args = DeepDispatchArgs.from_dict(body)
    return (adapter._task_text(args, instruction)
            + adapter._render_inputs(tuple(inputs))).encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _the_prompt(log) -> dict:
    rows = _fakeclaude.prompt_spawns(log)
    assert len(rows) == 1, f"EXPECTED_ONE_PROMPT_SPAWN={len(rows)}"
    return rows[0]


def _read_exactly(log, expected: bytes) -> None:
    row = _the_prompt(log)
    assert row["marker"]["in_stdin"] is True and row["marker"]["in_argv"] is False
    assert row["stdin"] == {
        "read": True, "bytes": len(expected), "sha256": _sha(expected)}


def _evidence_digest(store: RunStore, run_id: str = RUN_ID) -> str:
    rows = [row.value for row in store.read(run_id).records
            if row.kind == "evidence"]
    assert len(rows) == 1, [row.kind for row in store.read(run_id).records]
    assert rows[0].digest is not None
    return rows[0].digest


# -- the instruction ------------------------------------------------------------


def test_the_instruction_is_the_document_standing_when_the_proposal_was_written(
        tmp_path):
    """No file under `instructions/`, one durable document: the child reads it.

    The shipped starter's `do` step names `instruction-plan`, a file `conduct
    init` never writes (the R04 probe: a clean tree holds no `instructions/`
    at all). A document published under that ref, before the proposal, is the
    instruction -- and the whole stdin is the frame built from that document
    and nothing else.
    """
    plan = _document("instruction-plan-1", DOC_REF, f"# Plan\n\nDo this. {PROBE}")
    attempt, store, adapter, log, root, body = _drive(
        tmp_path, before=(plan,), arguments={"instruction_ref": DOC_REF})

    assert attempt.state is AttemptState.SUCCEEDED, attempt.receipt.detail
    assert not (root / INSTRUCTION_DIR / f"{DOC_REF}.md").exists()
    _read_exactly(log, _frame(adapter, body, plan.content))


def test_a_document_published_after_the_proposal_never_substitutes_the_instruction(
        tmp_path):
    """The owner's control, on the instruction: bound at the proposal.

    A second document under the same ref lands after the proposal and before
    the execution. It is durable -- the journal holds both -- and it is not
    what the child reads: the stdin digest is the frame over the FIRST
    document, and the later one's words appear in no frame.
    """
    plan = _document("instruction-plan-1", DOC_REF, f"# Plan\n\nDo this. {PROBE}")
    later = _document("instruction-plan-2", DOC_REF,
                      "# Plan\n\nA later revision the child must not read.")
    attempt, store, adapter, log, root, body = _drive(
        tmp_path, before=(plan,), after=(later,),
        arguments={"instruction_ref": DOC_REF})

    assert attempt.state is AttemptState.SUCCEEDED, attempt.receipt.detail
    kinds = [row.kind for row in store.read(RUN_ID).records]
    assert kinds.count("artifact") == 2, kinds
    _read_exactly(log, _frame(adapter, body, plan.content))


def test_the_file_road_is_read_byte_for_byte_when_no_document_stands(tmp_path):
    """Nothing published under the ref: the workspace file, exactly as before."""
    attempt, store, adapter, log, root, body = _drive(tmp_path, probe=False)

    assert attempt.state is AttemptState.SUCCEEDED, attempt.receipt.detail
    row = _the_prompt(log)
    expected = _frame(adapter, body, INSTRUCTION)
    assert row["stdin"] == {
        "read": True, "bytes": len(expected), "sha256": _sha(expected)}


def test_neither_a_document_nor_a_file_spawns_nothing_and_says_so(tmp_path):
    """The R04 probe, made a test: refused before the preflight, no child.

    The receipt carries the transport's fixed containment sentence -- never a
    path -- and the spawn log does not exist: not even the version preflight
    ran, because a dispatch that cannot read its instruction never reaches it.
    No work directory was minted either.
    """
    receipt, store, adapter, log, root = _refused(
        tmp_path, arguments={"instruction_ref": DOC_REF}, probe=False)

    assert receipt.outcome == "failed", receipt.detail
    assert receipt.detail == uncontained_detail(adapter.profile.tool_noun)
    assert _fakeclaude.spawns(log) == []
    assert not (root / WORK_DIR).exists()


# -- the dispatch inputs --------------------------------------------------------


def test_a_dispatch_input_published_after_the_proposal_is_not_what_the_child_reads(
        tmp_path):
    """The same rule, one field over: `artifact_refs` bind at the proposal.

    `ArtifactHandoff.resolve` answered "the latest document under the ref" at
    execution -- the lazy resolution the owner's correction names for the
    instruction. Two documents under `artifact-plan`, one before and one after
    the proposal: the child is handed the first, whole, and the frame's digest
    says so.
    """
    first = _document("artifact-plan-1", "artifact-plan",
                      f"# Plan\n\nImplement this one. {PROBE}")
    later = _document("artifact-plan-2", "artifact-plan",
                      "# Plan\n\nNot this one: it landed after the proposal.")
    attempt, store, adapter, log, root, body = _drive(
        tmp_path, before=(first,), after=(later,),
        arguments={"artifact_refs": ["artifact-plan"]})

    assert attempt.state is AttemptState.SUCCEEDED, attempt.receipt.detail
    _read_exactly(log, _frame(adapter, body, INSTRUCTION, (first,)))


def test_an_input_published_only_after_the_proposal_is_unavailable(tmp_path):
    """A ref no document precedes is the refusal it always was: no spawn."""
    late = _document("artifact-late-1", "artifact-late", "# Late\n\nToo late.")
    receipt, store, adapter, log, root = _refused(
        tmp_path, after=(late,), arguments={"artifact_refs": ["artifact-late"]},
        probe=False)

    assert receipt.outcome == "failed", receipt.detail
    assert receipt.detail == UNAVAILABLE
    assert _fakeclaude.prompt_spawns(log) == []


def test_the_bound_instruction_names_itself_in_the_evidence_digest(tmp_path):
    """The evidence names what was read: a different document, a different digest.

    Calibrated first -- two fresh runs bound to the same document produce the
    same digest, so the third run's difference is the document's and not the
    clock's or the tree's.
    """
    content = f"# Plan\n\nDo this. {PROBE}"
    digests = []
    for name, artifact_id in (("a", "instruction-plan-1"), ("b", "instruction-plan-1"),
                              ("c", "instruction-plan-9")):
        attempt, store, *_ = _drive(
            tmp_path / name, before=(_document(artifact_id, DOC_REF, content),),
            arguments={"instruction_ref": DOC_REF})
        assert attempt.state is AttemptState.SUCCEEDED, attempt.receipt.detail
        digests.append(_evidence_digest(store))
    assert digests[0] == digests[1], digests
    assert digests[2] != digests[0], digests


# -- the review inputs ----------------------------------------------------------


def test_a_review_input_published_after_the_proposal_is_not_what_the_reviewer_reads(
        tmp_path):
    """The review road binds its material at the proposal as well.

    The reviewer's stdin is the review frame over the seed that stood when
    the proposal was written; the candidate published after it is durable and
    unread, and the published review names the seed as its one input.
    """
    adapter, root, log = a_harness(tmp_path, **{
        _fakeclaude.EMIT_REVIEW: "enabled-review-output",
        _fakeclaude.LEAK_CHECK: "enabled-review-leak-check",
        "ANTHROPIC_API_KEY": API_KEY})
    store = RunStore(root)
    store.create_run(
        RunEnvelope(
            run_id=REVIEW_RUN, cycle_id="review-cycle", created_at=NOW,
            config_digest=snapshot_digest(REVIEW_CONFIG), mode="confirm"),
        REVIEW_CONFIG)
    seed = _document("artifact-source-1", INPUT_REF,
                     f"# Candidate\n\nReview this exact proposal. {REVIEW_PROBE}",
                     run_id=REVIEW_RUN)
    store.append(seed)
    proposal = _proposal()
    store.append(proposal)
    store.append(_document(
        "artifact-source-2", INPUT_REF,
        "# Candidate\n\nA later candidate the reviewer must not read.",
        run_id=REVIEW_RUN))
    runtime = ControlRuntime(
        store, AdapterRegistry([adapter]), clock=lambda: NOW, ids=_Ids())
    budget = Budget(
        max_actions=8, max_action_seconds=3600,
        max_confirmation_age_seconds=3600)
    attempt = runtime.execute(runtime.authorize(
        _confirmation(proposal), budget=budget))

    assert attempt.state is AttemptState.SUCCEEDED, attempt.receipt.detail
    args = DeepReviewArgs.from_dict(REVIEW_ARGUMENTS)
    expected = adapter._task_stdin(adapter._review_task(args, (seed,)))
    row = _the_prompt(log)
    assert row["stdin"] == {
        "read": True, "bytes": len(expected), "sha256": _sha(expected)}
    published = [row.value for row in store.read(REVIEW_RUN).records
                 if row.kind == "artifact" and row.value.artifact_ref == OUTPUT_REF]
    assert len(published) == 1
    assert tuple(published[0].input_artifact_ids) == ("artifact-source-1",)


# -- the rule itself ------------------------------------------------------------


def test_the_handoff_binds_by_journal_position_and_refuses_a_proposal_it_cannot_find(
        tmp_path):
    """The resolver's own answers, over one journal, without a child."""
    store = RunStore(tmp_path)
    store.create_run(
        RunEnvelope(
            run_id=RUN_ID, cycle_id="artifact-cycle", created_at=NOW,
            config_digest=snapshot_digest(CONFIG), mode="confirm"),
        CONFIG)
    first = _document("x-1", "artifact-x", "# x, first")
    second = _document("x-2", "artifact-x", "# x, second, still before")
    later = _document("x-3", "artifact-x", "# x, after the proposal")
    store.append(first)
    store.append(second)
    proposal = _proposal_for({**ARGUMENTS, "artifact_refs": ["artifact-x"]})
    store.append(proposal)
    store.append(later)
    handoff = ArtifactHandoff(store, clock=lambda: NOW, ids=_Ids())

    bound = handoff.bound(RUN_ID, proposal.proposal_id, ["artifact-x"])
    assert [row.artifact_id for row in bound] == ["x-2"]
    assert handoff.instruction(RUN_ID, proposal.proposal_id, "artifact-x").artifact_id == "x-2"
    assert handoff.instruction(RUN_ID, proposal.proposal_id, "artifact-y") is None
    # Nothing precedes the proposal under that ref: the same refusal
    # `latest_artifacts` has always made, never a document from after it.
    try:
        handoff.bound(RUN_ID, proposal.proposal_id, ["artifact-y"])
    except ContractError:
        pass
    else:
        raise AssertionError("a ref no document precedes was resolved")
    # And a proposal the journal does not hold binds nothing at all.
    try:
        handoff.bound(RUN_ID, "proposal-ghost", ["artifact-x"])
    except StoreError:
        pass
    else:
        raise AssertionError("an absent proposal bound a document")
    # `resolve` keeps today's answer for callers that name no proposal.
    assert [row.artifact_id for row in handoff.resolve(RUN_ID, ["artifact-x"])] == ["x-3"]


def test_a_request_names_the_proposal_it_was_minted_from_or_nobody():
    """`dispatch-<proposal_id>` is the runtime's own link, read back here.

    A request the runtime authorized carries it; a hand-made request carries
    whatever its author wrote, and names no proposal -- so the transport takes
    the file road for it, byte-for-byte as before this rule existed.
    """
    # Imported here rather than at the top, so that every behavioural witness
    # above still collects -- and reds on its own behaviour -- on a tree that
    # does not carry the seam yet. The rule is the replay's; the transport
    # reaches it through the handoff seam, and both answers are held equal.
    from conductor.command.attempt_replay import proposal_named_by

    assert proposal_named_by(a_request()) is None
    minted = ActionRequest.from_dict({
        **a_request().as_dict(), "idempotency_key": "dispatch-proposal-7"})
    assert proposal_named_by(minted) == "proposal-7"
    assert ArtifactHandoff.named_proposal(minted) == "proposal-7"
    assert ArtifactHandoff.named_proposal(a_request()) is None
