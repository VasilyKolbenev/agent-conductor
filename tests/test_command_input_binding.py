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
from dataclasses import replace

import pytest

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
from conductor.command.contracts import ABSENT, ActionProposal, ActionRequest, RunEnvelope
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
    _proposal as _review_proposal,
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


def _proposal():
    """This module's live binding witnesses use the current proposal contract."""
    return replace(_review_proposal(), input_binding="proposal-v1",
                   preview_digest="")


def _legacy_review_proposal():
    """Historical compatibility witnesses intentionally retain the old shape."""
    return replace(_review_proposal(), input_binding=ABSENT, preview_digest="")


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
        config_digest=snapshot_digest(CONFIG), input_binding="proposal-v1")


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
    """A ref no document precedes is the refusal it always was: no spawn.

    Not even the version preflight (the fold review's C5/H1): the inputs are
    resolved on the road's first step, so the Studio's sentence "the attempt
    is refused before anything is spawned" is what happens. And a refused
    attempt leaves nothing resident: the materials the first step resolved
    go with it (the fold review's C1).
    """
    late = _document("artifact-late-1", "artifact-late", "# Late\n\nToo late.")
    receipt, store, adapter, log, root = _refused(
        tmp_path, after=(late,), arguments={"artifact_refs": ["artifact-late"]},
        probe=False)

    assert receipt.outcome == "failed", receipt.detail
    assert receipt.detail == UNAVAILABLE
    assert _fakeclaude.spawns(log) == []
    assert adapter._materials == {} and adapter._dispatch_inputs == {}


@pytest.mark.parametrize("preflight_outcome", ("success", "refused", "raised"))
def test_materials_survive_only_until_the_dispatch_consumes_or_refuses_them(
        tmp_path, monkeypatch, preflight_outcome):
    """A populated cache, not an empty one, is forgotten on every early exit.

    The missing-input witness above refuses before `_materials` is assigned.
    Here both documents are resolved and observed at preflight, after which a
    version refusal or exception must discard them just as a task consumes them.
    """
    instruction = _document("instruction-first", DOC_REF, "Do the reviewed work.")
    material = _document("input-first", "artifact-plan", "The reviewed source.")
    _, authorization, _, adapter, log, _, _ = _authorized(
        tmp_path, before=(instruction, material), probe=False,
        arguments={"instruction_ref": DOC_REF, "artifact_refs": ["artifact-plan"]})
    original_preflight = adapter._preflight
    reached = []

    def preflight(request):
        assert tuple(adapter._materials.values()) == (
            (instruction, (material,)),)
        reached.append(True)
        if preflight_outcome == "raised":
            raise RuntimeError("preflight witness")
        if preflight_outcome == "refused":
            return adapter._receipt(request, "failed", None, "preflight refused")
        return original_preflight(request)

    monkeypatch.setattr(adapter, "_preflight", preflight)
    prepared = adapter.prepare(authorization.request)
    if preflight_outcome == "raised":
        with pytest.raises(RuntimeError, match="preflight witness"):
            adapter.execute(prepared)
    else:
        receipt = adapter.execute(prepared)
        assert receipt.outcome == (
            "succeeded" if preflight_outcome == "success" else "failed")
    assert reached == [True]
    assert adapter._materials == {}
    assert len(_fakeclaude.prompt_spawns(log)) == (preflight_outcome == "success")


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


def _ghost_keyed(key: str, **changes) -> ActionRequest:
    """A hand-made request under one idempotency key, for this run."""
    return ActionRequest.from_dict({
        **a_request(**changes).as_dict(), "run_id": RUN_ID, "idempotency_key": key})


def test_a_request_naming_a_proposal_the_run_does_not_hold_is_refused_by_name(
        tmp_path):
    """The slice-3 review's #1, the transport half.

    A key that begins `dispatch-` and names a proposal this run does not hold
    can only be hand-made -- the runtime mints the link from a proposal it
    just read -- and it was refused under "a durable dispatch input was
    unavailable", a sentence about the wrong cause. The refusal names the
    proposal now, spawns nothing, and the empty suffix still names nobody:
    `dispatch-` alone is the file road, byte-for-byte as before.
    """
    adapter, root, log = a_harness(
        tmp_path, instruction=INSTRUCTION,
        **{_fakeclaude.WRITE_FILE: "implemented.py:verified change"})
    store = RunStore(root)
    store.create_run(
        RunEnvelope(
            run_id=RUN_ID, cycle_id="artifact-cycle", created_at=NOW,
            config_digest=snapshot_digest(CONFIG), mode="confirm"),
        CONFIG)
    receipt = run_once(adapter, _ghost_keyed("dispatch-ghost"))
    assert receipt.outcome == "failed"
    assert receipt.detail == (
        f"the request names proposal 'ghost', which run {RUN_ID!r} does not "
        "hold, so no task was spawned")
    assert _fakeclaude.spawns(log) == []
    assert adapter._materials == {}
    assert [row.kind for row in store.read(RUN_ID).records] == []
    # The same shape on the review road, refused by the same name -- and
    # before the version preflight there too: no process at all.
    review = _ghost_keyed("dispatch-ghost", action_id="act-2",
                          capability="review", arguments=REVIEW_ARGUMENTS)
    receipt = run_once(adapter, review)
    assert receipt.outcome == "failed"
    assert receipt.detail.startswith("the request names proposal 'ghost'")
    assert _fakeclaude.spawns(log) == []
    # An empty suffix names nobody: the file road runs, one child spawned.
    receipt = run_once(adapter, _ghost_keyed("dispatch-", action_id="act-3"))
    assert "proposal" not in (receipt.detail or "")
    assert len(_fakeclaude.prompt_spawns(log)) == 1


def _review_request(key: str) -> ActionRequest:
    return _ghost_keyed(key, capability="review", arguments=REVIEW_ARGUMENTS)


def _reviewed(request: ActionRequest, *inputs: str) -> ArtifactDocument:
    """The artifact a review request published, claiming these inputs."""
    return ArtifactDocument(
        artifact_id="artifact-reviewed-1", artifact_ref=OUTPUT_REF,
        run_id=RUN_ID, created_at=NOW, media_type="text/markdown",
        content="# Reviewed", source_action_id=request.action_id,
        input_artifact_ids=tuple(inputs))


def test_the_replay_judge_refuses_the_same_ghost_the_transport_refuses():
    """The slice-3 review's #1, the judge half: two readers, one answer.

    `_the_request_saw` answered "everything before the artifact" for a
    request naming a proposal the run does not hold, so the replay admitted a
    review artifact the transport would have refused to produce. It refuses
    now, naming the proposal; a request naming no proposal at all keeps the
    road every journal written before the binding took.
    """
    from conductor.command.artifacts import validate_artifact_source
    from tests.test_command_graph_projection import an_event

    seed = _document("artifact-source-1", INPUT_REF, "# Candidate")
    ghost = _review_request("dispatch-ghost")
    prior = (seed, ghost, an_event(ghost, "execution_observed", outcome="succeeded", exit_code=0))
    try:
        validate_artifact_source(_reviewed(ghost, "artifact-source-1"), prior)
    except ContractError as error:
        assert "names proposal 'ghost', which this run does not hold" in str(error)
    else:
        raise AssertionError("a ghost proposal was admitted on replay")
    unnamed = _review_request("idem-act-1")
    validate_artifact_source(
        _reviewed(unnamed, "artifact-source-1"),
        (seed, unnamed, an_event(unnamed, "execution_observed", outcome="succeeded", exit_code=0)))


def test_a_review_recorded_over_a_document_its_proposal_never_saw_is_refused_on_replay():
    """The slice-3 review's #13, ruled: the binding holds on replay too.

    A journal where a document under the target reference was published
    between the proposal and the review's execution, and the review recorded
    THAT document as its input, is a journal the transport can no longer
    write. On replay it is refused -- correctness of the binding over
    compatibility with a server no deployment holds -- while a hand-made
    request naming no proposal keeps the older answer.
    """
    from conductor.command.artifacts import validate_artifact_source
    from tests.test_command_graph_projection import an_event

    earlier = _document("artifact-source-1", INPUT_REF, "# Candidate, first")
    proposal = _proposal_for({**REVIEW_ARGUMENTS})
    later = _document("artifact-source-2", INPUT_REF, "# Candidate, after the proposal")
    minted = _review_request(f"dispatch-{proposal.proposal_id}")
    prior = (earlier, proposal, later, minted, an_event(minted, "execution_observed", outcome="succeeded", exit_code=0))
    try:
        validate_artifact_source(_reviewed(minted, "artifact-source-2"), prior)
    except ContractError as error:
        assert "input ids do not match" in str(error)
    else:
        raise AssertionError("a review over the later document replayed")
    validate_artifact_source(_reviewed(minted, "artifact-source-1"), prior)
    unnamed = _review_request("idem-act-1")
    validate_artifact_source(
        _reviewed(unnamed, "artifact-source-2"),
        (earlier, proposal, later, unnamed, an_event(unnamed, "execution_observed", outcome="succeeded", exit_code=0)))


def _a_review_run_with_a_later_candidate(tmp_path, *, marked=False):
    """A review harness, its run, the seed, the proposal and a later candidate."""
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
    store.append(_document("artifact-source-1", INPUT_REF, "# Candidate, first",
                           run_id=REVIEW_RUN))
    proposal = _proposal() if marked else _legacy_review_proposal()
    store.append(proposal)
    store.append(_document(
        "artifact-source-2", INPUT_REF,
        f"# Candidate, after the proposal. {REVIEW_PROBE}", run_id=REVIEW_RUN))
    return adapter, root, store, proposal


def _record_a_later_candidate(tmp_path, monkeypatch, *, marked=False):
    """Simulate the old transport and writer, then restore every real reader."""
    from conductor.command import artifacts as artifacts_module
    from conductor.command.adapters.artifact_transport import ArtifactAwareTransport

    adapter, root, store, proposal = _a_review_run_with_a_later_candidate(
        tmp_path, marked=marked)
    monkeypatch.setattr(
        ArtifactAwareTransport, "_inputs",
        lambda self, request, refs: self._handoff.resolve(request.run_id, refs))
    monkeypatch.setattr(
        artifacts_module, "_artifact_answers_its_request", lambda *_: None)
    runtime = ControlRuntime(
        store, AdapterRegistry([adapter]), clock=lambda: NOW, ids=_Ids())
    # The older server had neither the live re-propose guard nor bound inputs.
    monkeypatch.setattr(runtime._registry, "argument_schema", lambda *_: None)
    budget = Budget(
        max_actions=8, max_action_seconds=3600,
        max_confirmation_age_seconds=3600)
    attempt = runtime.execute(runtime.authorize(
        _confirmation(proposal), budget=budget))
    assert attempt.state is AttemptState.SUCCEEDED, attempt.receipt.detail
    journal = store.run_path(REVIEW_RUN) / "records.jsonl"
    before = journal.read_bytes()
    monkeypatch.undo()
    return root, attempt, journal, before


def test_a_journal_an_older_server_wrote_keeps_its_original_input_semantics(
        tmp_path, monkeypatch):
    """Old unmarked proposals replay unchanged; new marked ones bind at preview."""
    root, attempt, journal, before = _record_a_later_candidate(tmp_path, monkeypatch)
    recovered = RunStore(root).read(REVIEW_RUN)
    produced = [row.value for row in recovered.records if row.kind == "artifact"
                and row.value.source_action_id == attempt.request.action_id]
    assert len(produced) == 1
    assert produced[0].input_artifact_ids == ("artifact-source-2",)
    assert recovered.warnings == ()
    assert journal.read_bytes() == before


def test_a_marked_journal_cannot_claim_the_later_document_on_read(tmp_path, monkeypatch):
    """The same bad consumption is not grandfathered on the marked contract."""
    from conductor.command.run_store import CorruptRun

    root, _, journal, before = _record_a_later_candidate(
        tmp_path, monkeypatch, marked=True)
    with pytest.raises(CorruptRun, match="input ids do not match"):
        RunStore(root).read(REVIEW_RUN)
    assert journal.read_bytes() == before


def test_the_two_readers_of_the_proposal_link_are_one(tmp_path):
    """The slice-3 review's #3: one prefix, one parser.

    The store's relation pass and the replay's binding each parsed
    `dispatch-<proposal_id>` with a constant of their own; nothing pinned
    them equal. The store's now IS the replay's, and the store's lookup is
    the replay's parse followed by a search of the run, so the same key
    names the same proposal -- or nobody -- on both roads.
    """
    from conductor.command import graph_causality
    from conductor.command.attempt_replay import PROPOSAL_KEY, proposal_named_by

    assert graph_causality.DISPATCH_KEY_PREFIX is PROPOSAL_KEY
    store = RunStore(tmp_path)
    store.create_run(
        RunEnvelope(
            run_id=RUN_ID, cycle_id="artifact-cycle", created_at=NOW,
            config_digest=snapshot_digest(CONFIG), mode="confirm"),
        CONFIG)
    proposal = _proposal_for({**ARGUMENTS, "artifact_refs": []})
    store.append(proposal)
    recovered = store.read(RUN_ID)
    for key, named in ((f"dispatch-{proposal.proposal_id}", proposal.proposal_id),
                       ("dispatch-ghost", "ghost"), ("dispatch-", None),
                       ("idem-x", None)):
        request = _ghost_keyed(key)
        assert proposal_named_by(request) == named, key
        held = graph_causality._proposal_named_by(recovered, request)
        assert (held is None) == (named != proposal.proposal_id), key
        if held is not None:
            assert held.proposal_id == named


def test_a_request_names_the_proposal_it_was_minted_from_or_nobody():
    """`dispatch-<proposal_id>` is the runtime's own link, read back here.

    A request the runtime authorized carries it; a hand-made request carries
    whatever its author wrote. One that names NO proposal takes the file road,
    byte-for-byte as before this rule existed; one naming a proposal the run
    does not hold is refused by name (the two tests above).
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
