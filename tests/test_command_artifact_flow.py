"""One step's product becomes the next step's requirement, through real transports.

THE GAP THIS CLOSES. Every half of the artifact chain was already driven
somewhere: ``test_command_claude_review`` proves a review consumes durable input
and publishes a durable output, ``test_command_artifact_dispatch`` proves a
dispatch resolves the LATEST document under a reference and verifies a real tree
change, and ``test_command_artifacts`` proves the store's chain rules on
hand-built journals. What nothing drove was the JOIN: no test in this tree ever
took the artifact one action produced and fed it to another action as a
requirement. So the product's central claim -- that a workflow hands work
between roles as immutable material -- rested on two halves that had never been
made to meet.

They meet here, in one run, over one root, through the real transport and the
real fake child:

    A  review    target_artifact_refs [artifact-seed]
                 result_artifact_ref   artifact-handoff      -> publishes it
    B  dispatch  artifact_refs        [artifact-handoff]     -> is handed it

and the four relations asserted are the four ways that could be false while
every existing test stayed green:

1. the BYTES A wrote reach B's child. Measured as the digest of what the child
   read off stdin, against the digest of the task this build composed -- and
   against a CONTROL digest of the same task with the durable material left
   out, so "the inputs were rendered" is a claim about a difference and not
   about a number recomputed from the same function twice;
2. B's evidence DIGEST folds A's artifact identity in. Recomputed from the
   work-tree readings this test takes either side of B's spawn, and compared
   against the same digest computed with no inputs -- again a difference;
3. the store's chain held on a fresh READ of the whole journal, which is where
   replay judges `_artifact_answers_its_request` -- and it is shown to be live
   rather than merely quiet, by offering the journal an artifact claiming B as
   its source and watching it refuse;
4. with A's artifact absent, B refuses fail-closed: the shipped sentence, no
   spawn, no evidence.

TWO HARNESSES, ONE ROOT, and the reason is the fake child. A's knobs make it
emit a review on stdout; B's make it write a file into the work tree. One child
cannot do both, because a review that changes the tree is refused as a review --
`test_review_that_changes_the_tree_is_not_verified_or_published` is that rule.
So each action gets a provider configured for the work it is really doing, both
resolved against the same root, exactly as two different providers bound to one
project would be. `test_restart_recovers_an_artifact_appended_before_its_evidence`
already builds a second harness over a first one's root.

THE PROBE. The fake's leak scan requires the task it reads to carry exactly one
probe token, and refuses to run at all otherwise -- so both tasks must carry
one, by whichever channel that action really uses. A's arrives inside the seeded
artifact it is asked to review; B's arrives inside the operator instruction it
is asked to carry out. A's OUTPUT carries none, which is what lets B's task hold
exactly one token while carrying A's whole product.
"""
from __future__ import annotations

import hashlib

import pytest

from conductor.command.adapters import AdapterRegistry
from conductor.command.adapters.deep_commands import DeepDispatchArgs
from conductor.command.adapters.headless_values import changed_paths
from conductor.command.artifacts import ArtifactDocument
from conductor.command.contracts import ActionProposal, RunEnvelope, _content_digest
from conductor.command.graph_definition import GraphDefinition, GraphNode
from conductor.command.graph_schedule import schedule
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.store_errors import RecordConflict, StoreError
from conductor.command.runtime import (
    AttemptState,
    Budget,
    Confirmation,
    ControlRuntime,
)

from tests import _fakeclaude
from tests.test_command_claude_transport import NOW, a_harness


RUN_ID = "run-artifact-flow"
REVIEWER = "claude-reviewer"
BUILDER = "claude-builder"
#: What A is given, what A publishes, and what B then requires. The middle one
#: is the whole subject of this module: it is named once and every reference to
#: it below is this constant, so a test that stopped joining the two actions
#: could not do it by quietly using two spellings of one name.
SEED_REF = "artifact-seed"
HANDOFF_REF = "artifact-handoff"
PROBE = _fakeclaude.PROBE_PREFIX + "d0c0ffee" * 8
INSTRUCTION = (
    f"Implement what the accepted review asks for. {PROBE}")
CONFIG = {
    "cycle": {"id": "flow-cycle", "phases": ["review", "dispatch"]},
    "instances": [
        {"id": REVIEWER, "adapter": "claude-code"},
        {"id": BUILDER, "adapter": "claude-code"},
    ],
}
REVIEW_ARGUMENTS = {
    "work_item_id": "work-flow",
    "target_artifact_refs": [SEED_REF],
    "result_artifact_ref": HANDOFF_REF,
    "review_profile": "quality",
}
DISPATCH_ARGUMENTS = {
    "work_item_id": "work-flow",
    "instruction_ref": "instr-001",
    "profile": "implement",
    "artifact_refs": [HANDOFF_REF],
    "output_limit_profile": "normal",
}
#: What the transport answers when a reference names no standing artifact. The
#: negative arm below asserts this exact sentence, because "no task was spawned"
#: is the promise a person is shown beside the control in the Studio.
UNAVAILABLE = "a durable dispatch input was unavailable, so no task was spawned"


class _Ids:
    def __init__(self) -> None:
        self._counts: dict[str, int] = {}

    def __call__(self, kind: str) -> str:
        self._counts[kind] = self._counts.get(kind, 0) + 1
        return f"{kind}-{self._counts[kind]}"


def _budget() -> Budget:
    return Budget(
        max_actions=8, max_action_seconds=3600,
        max_confirmation_age_seconds=3600)


def _open_run(root) -> RunStore:
    store = RunStore(root)
    store.create_run(
        RunEnvelope(
            run_id=RUN_ID, cycle_id="flow-cycle", created_at=NOW,
            config_digest=snapshot_digest(CONFIG), mode="confirm"),
        CONFIG)
    return store


def _act(store: RunStore, adapter, ids: _Ids, *, name: str, instance: str,
         capability: str, arguments: dict):
    """Propose, confirm and execute ONE action, the way the runtime does.

    The id source is handed IN and shared by both actions, which is not a
    convenience: a runtime given a fresh counter mints ``action-1`` again, and
    the store refuses the second request as one identity recording two
    different sets of facts. One run has one id source, here as in production.

    The two actions need two runtimes because they need two adapters -- an
    ``AdapterRegistry`` is keyed by adapter id, so one registry cannot hold two
    providers that answer to ``claude-code``. Everything durable is shared: one
    store, one root, one journal.
    """
    proposal = ActionProposal(
        proposal_id=f"proposal-{name}", run_id=RUN_ID,
        attempt_id=f"attempt-{name}", instance_id=instance,
        capability=capability, arguments=arguments, scope=("work",),
        proposed_by="lane", proposed_at=NOW, timeout_seconds=60,
        rationale=f"the {name} half of one durable handoff",
        config_digest=snapshot_digest(CONFIG))
    store.append(proposal)
    confirmation = Confirmation(
        confirmation_id=f"confirmation-{name}", run_id=RUN_ID,
        proposal_id=proposal.proposal_id,
        preview_digest=proposal.preview_digest, capability=capability,
        scope=("work",), config_digest=proposal.config_digest,
        confirmed_by="release-owner", confirmed_at=NOW)
    runtime = ControlRuntime(
        store, AdapterRegistry([adapter]), clock=lambda: NOW, ids=ids)
    return runtime.execute(runtime.authorize(confirmation, budget=_budget()))


def _reviewer(tmp_path, root=None):
    return a_harness(
        tmp_path / "reviewer", instruction=INSTRUCTION, root=root,
        **{_fakeclaude.EMIT_REVIEW: "enabled-review-output",
           _fakeclaude.LEAK_CHECK: "1"})


def _builder(tmp_path, root=None):
    return a_harness(
        tmp_path / "builder", instruction=INSTRUCTION, root=root,
        **{_fakeclaude.LEAK_CHECK: "1",
           _fakeclaude.WRITE_FILE: "implemented.py:what the review asked for"})


def _seed(store: RunStore) -> ArtifactDocument:
    seed = ArtifactDocument(
        artifact_id="artifact-seed-1", artifact_ref=SEED_REF, run_id=RUN_ID,
        created_at=NOW, media_type="text/markdown",
        content=f"# Candidate\n\nReview this exact proposal. {PROBE}")
    store.append(seed)
    return seed


def _artifacts(store: RunStore) -> list[ArtifactDocument]:
    return [row.value for row in store.read(RUN_ID).records
            if row.kind == "artifact"]


def _flow(tmp_path, *, seeded: bool = True):
    """Drive A then B over one root, measuring the tree either side of B."""
    ids = _Ids()
    reviewer, root, review_log = _reviewer(tmp_path)
    store = _open_run(root)
    if seeded:
        _seed(store)
        first = _act(store, reviewer, ids, name="review", instance=REVIEWER,
                     capability="review", arguments=REVIEW_ARGUMENTS)
    else:
        first = None
    builder, _root, build_log = _builder(tmp_path, root=root)
    before = builder._workspace.digest_work_tree()
    second = _act(store, builder, ids, name="dispatch", instance=BUILDER,
                  capability="dispatch", arguments=DISPATCH_ARGUMENTS)
    after = builder._workspace.digest_work_tree()
    return {
        "store": store, "first": first, "second": second,
        "reviewer": reviewer, "builder": builder,
        "review_log": review_log, "build_log": build_log,
        "before": before, "after": after, "root": root,
    }


# -- 1. the bytes A published are the bytes B's child read ---------------------


def test_the_artifact_one_step_publishes_is_handed_to_the_next_steps_child(
        tmp_path):
    """The join, measured at the far side of a real spawn.

    The digest is computed three ways on purpose. What the child READ is the
    fake's own measurement, taken in the child process. What this build SENT is
    recomposed here from the transport's own two halves. And the CONTROL is the
    same task with the durable material left out -- without it, this assertion
    would compare one function against itself and pass on a build that rendered
    nothing at all.
    """
    flow = _flow(tmp_path)
    assert flow["first"].state is AttemptState.SUCCEEDED, (
        flow["first"].receipt.detail)
    assert flow["second"].state is AttemptState.SUCCEEDED, (
        flow["second"].receipt.detail)

    published = [row for row in _artifacts(flow["store"])
                 if row.source_action_id is not None]
    assert len(published) == 1
    produced = published[0]
    assert produced.artifact_ref == HANDOFF_REF
    assert produced.source_action_id == flow["first"].request.action_id

    builder = flow["builder"]
    args = DeepDispatchArgs.from_dict(DISPATCH_ARGUMENTS)
    plain = builder._task_text(args, INSTRUCTION)
    sent = (plain + builder._render_inputs((produced,))).encode("utf-8")
    control = plain.encode("utf-8")
    # A's whole product really is inside what was sent, fenced as durable
    # material rather than as anything the child may act on as authority.
    assert produced.content.encode("utf-8") in sent
    assert produced.artifact_id.encode("utf-8") in sent
    assert produced.content.encode("utf-8") not in control

    prompt = _fakeclaude.prompt_spawns(flow["build_log"])
    assert len(prompt) == 1
    assert prompt[0]["stdin"] == {
        "read": True, "bytes": len(sent),
        "sha256": hashlib.sha256(sent).hexdigest(),
    }
    assert prompt[0]["stdin"]["sha256"] != hashlib.sha256(control).hexdigest()
    assert prompt[0]["marker"]["in_stdin"] is True


# -- 2. B's evidence digests the change AND the material it was given ----------


def test_the_consuming_steps_evidence_folds_in_the_artifact_it_was_handed(
        tmp_path):
    """A change digest that ignored its inputs would verify the wrong thing.

    Two dispatches that made the same edit from different material are not the
    same event, and the digest is what a later reader has to tell them apart
    by. So it is recomputed here from the readings this test took either side
    of the spawn, and compared against the digest of the same change with no
    inputs folded in -- the value a build that dropped the fold would produce.
    """
    flow = _flow(tmp_path)
    store = flow["store"]
    produced = next(row for row in _artifacts(store)
                    if row.source_action_id is not None)
    request = flow["second"].request
    changed = changed_paths(flow["before"], flow["after"])
    assert changed, "the dispatch changed nothing, so there is no digest to fold"

    def digest(inputs: list[str]) -> str:
        return _content_digest({
            "action_id": request.action_id,
            "input_artifact_ids": inputs,
            "changes": [{
                "path": name, "before": flow["before"].get(name),
                "after": flow["after"].get(name)} for name in changed],
        })

    evidence = [row.value for row in store.read(RUN_ID).records
                if row.kind == "evidence"
                and row.value.uri == f"verification/{request.action_id}"]
    assert len(evidence) == 1
    assert evidence[0].digest == digest([produced.artifact_id])
    assert evidence[0].digest != digest([]), (
        "the change digest does not depend on the artifact the step was given")
    assert flow["second"].receipt.evidence_refs == (evidence[0].evidence_id,)


# -- 3. the store's chain rule holds over the joined journal -------------------


def test_the_joined_journal_replays_and_its_chain_rule_is_still_live(tmp_path):
    """Both halves in one journal, judged by a fresh read of the whole thing.

    A read is where replay runs every chain rule, so a journal that comes back
    warning-free has satisfied `_artifact_answers_its_request` -- the artifact
    is the one A's request asked for, from the inputs it named, in the order it
    named them.

    That would also be true of a build whose rule had been deleted, so the rule
    is shown to be LIVE from the other side: the journal is offered an artifact
    claiming the DISPATCH as its source, which is the first thing that rule
    refuses -- a step that carries work out publishes no document, its evidence
    is the digest above. A store that accepted it would have accepted any
    artifact under any reference.
    """
    flow = _flow(tmp_path)
    store = flow["store"]
    recovered = store.read(RUN_ID)
    assert recovered.warnings == (), recovered.warnings

    produced = next(row for row in _artifacts(store)
                    if row.source_action_id is not None)
    consumed = flow["second"].request
    # B really asked for what A really published, by the one reference.
    assert list(consumed.arguments["artifact_refs"]) == [HANDOFF_REF]
    assert produced.artifact_ref == HANDOFF_REF
    assert produced.input_artifact_ids == ("artifact-seed-1",)

    with pytest.raises((RecordConflict, StoreError)):
        store.append(ArtifactDocument(
            artifact_id="artifact-forged", artifact_ref=HANDOFF_REF,
            run_id=RUN_ID, created_at=NOW, media_type="text/markdown",
            content="# Forged\n\nclaimed by the step that publishes nothing",
            source_action_id=consumed.action_id))


# -- 4. with the artifact absent, the consumer refuses and spawns nothing ------


def test_the_consumer_refuses_fail_closed_when_the_handoff_never_happened(
        tmp_path):
    """The negative arm, and the promise the Studio makes beside the control.

    The same document, the same reference, the same step -- with the producing
    action never run. Nothing is spawned, nothing is verified, nothing durable
    is written and the work tree is exactly as it was.
    """
    flow = _flow(tmp_path, seeded=False)

    assert flow["first"] is None
    assert flow["second"].state is AttemptState.FAILED
    assert _fakeclaude.prompt_spawns(flow["build_log"]) == []
    assert flow["builder"]._dispatch_inputs == {}
    records = flow["store"].read(RUN_ID).records
    assert all(row.kind not in ("evidence", "artifact") for row in records)
    # "No task was spawned" is a claim about the WORK as well as about the log.
    assert flow["before"] == flow["after"]


def test_the_refusal_names_the_unavailable_handoff_at_the_adapter_boundary(
        tmp_path):
    """WHERE the shipped sentence exists, which is not where a reader expects.

    Written after this module's first draft asserted the sentence off
    ``attempt.receipt.detail`` and got ``adapter reported failed``. The
    transport composes a fixed sentence naming the fail-closed reason;
    ``ControlRuntime._resolve`` replaces it with a sentence of its own, and the
    durable ``AttemptEvent`` has no detail field at all -- so the REASON a
    dispatch was refused survives nowhere in the journal. The refusal does: the
    outcome, the absent spawn and the absent evidence are all durable, and they
    are what the test above holds.

    So the sentence is asserted where it is really produced, by re-driving the
    very request the runtime already made through the adapter's own two doors.
    Nothing is written by this road -- the resolution fails before anything is
    claimed or spawned -- which is itself part of the claim.
    """
    flow = _flow(tmp_path, seeded=False)
    builder, store = flow["builder"], flow["store"]
    before = [row.kind for row in store.read(RUN_ID).records]

    request = flow["second"].request
    receipt = builder.execute(builder.prepare(request))

    assert receipt.outcome == "failed"
    assert receipt.detail == UNAVAILABLE
    assert _fakeclaude.prompt_spawns(flow["build_log"]) == []
    assert [row.kind for row in store.read(RUN_ID).records] == before


# -- 5. with `block`, the plan waits instead of spawning a refusal ------------


def _before_the_dispatch(flow) -> tuple:
    """This run's journal at the moment B became eligible, and no later.

    Every record of B's own action is dropped, so what is left is exactly what
    stood when the plan was asked whether B could run: the seed, A's records,
    and whatever A published. A real journal prefix rather than a hand-built
    one -- these bytes were written by the transports above.
    """
    action_id = flow["second"].request.action_id
    return tuple(
        row.value for row in flow["store"].read(RUN_ID).records
        if getattr(row.value, "action_id", None) != action_id)


def _waiting_plan(policy: str | None) -> GraphDefinition:
    """One step, no roads in, needing the document A publishes.

    A REVIEW rather than a dispatch, and the contract chose that: an
    effect-capable step must stand behind a gate, and a gate would give this
    plan a road whose state could open or close the step for a reason that is
    not the document. A review consumes the same handoff by the same reference
    through the same one authority, so the step below is blocked or runnable
    for exactly one reason and the witness can say which.
    """
    return GraphDefinition(
        graph_id="graph-handoff", run_id=RUN_ID, created_at=NOW,
        nodes=(GraphNode(node_id="check", kind="task", title="Check it",
                         instance_id=REVIEWER, capability="review",
                         arguments={"work_item_id": "work-flow",
                                    "target_artifact_refs": [HANDOFF_REF],
                                    "result_artifact_ref": "artifact-verdict",
                                    "review_profile": "quality"},
                         missing_artifact_policy=policy),),
        edges=())


def test_a_blocking_step_waits_until_a_real_review_publishes_its_input(tmp_path):
    """The arrival, end to end, on the road a review actually takes.

    The step has no predecessors at all, so nothing about the plan's shape can
    open or close it: the ONLY difference between the two journals below is
    whether `artifact-handoff` exists. In the first it does not, because no
    review ran. In the second a real review ran through a real transport and
    published it, and the store admitted the document only because its chain
    rule agreed it was the one that request asked for.

    That is the owner's requirement demonstrated rather than described: with
    `block`, the plan WAITS for a document, and the thing that ends the wait is
    the document arriving.
    """
    # Two roots: one run id, and a store refuses to open it twice.
    waiting = schedule(_waiting_plan("block"), _before_the_dispatch(
        _flow(tmp_path / "unpublished", seeded=False)))
    arrived = schedule(_waiting_plan("block"), _before_the_dispatch(
        _flow(tmp_path / "published", seeded=True)))

    assert waiting.state_of("check") == "blocked"
    assert waiting.nodes[0].awaiting_artifacts == (HANDOFF_REF,)
    assert waiting.runnable == () and waiting.run_state == "stalled"

    assert arrived.state_of("check") == "runnable"
    assert arrived.nodes[0].awaiting_artifacts == ()
    assert arrived.runnable == ("check",) and arrived.run_state == "open"


@pytest.mark.parametrize("policy", [None, "fail"])
def test_the_same_journal_without_block_offers_the_step_and_fails_closed(
        tmp_path, policy):
    """The discriminating control, and it is the one that carries the ruling.

    The SAME journal that leaves a `block` step waiting leaves a `fail` step --
    and a step naming no policy at all -- RUNNABLE. Without this, every
    assertion above would also pass on a build that blocked every step whose
    inputs were missing, which is not what any plan written before this field
    existed asks for.

    What such a step then meets is the shipped fail-closed refusal, asserted
    here as the same sentence section 4 above holds: the plan offers the work,
    the transport resolves the input, and the refusal is durable with no task
    spawned. `fail` and silence are one behaviour, said twice.
    """
    flow = _flow(tmp_path, seeded=False)
    offered = schedule(_waiting_plan(policy), _before_the_dispatch(flow))

    assert offered.state_of("check") == "runnable"
    assert offered.nodes[0].awaiting_artifacts == ()
    assert offered.run_state == "open"

    builder = flow["builder"]
    receipt = builder.execute(builder.prepare(flow["second"].request))
    assert receipt.outcome == "failed"
    assert receipt.detail == UNAVAILABLE
    assert _fakeclaude.prompt_spawns(flow["build_log"]) == []
