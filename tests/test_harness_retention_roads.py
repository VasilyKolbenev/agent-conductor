"""A home that outlived its spawn stops the run on EVERY verification road.

Split from the login-leak module, which stood at 757 of 800 lines, and split on
a subject rather than on a size: next door proves what may happen to the secret
a login directory holds, while this proves what a run may publish after this
build failed a promise about a directory it minted.

The promise is the retention one: an attempt mints a profile home, and this
build takes it back when the attempt is over. When the machine refuses that
delete, the home survives with the child's own state in it -- and the question
this module holds is what the run is then allowed to say.

Three roads reach verification and they are NOT one road. The independent road
asks at `publish`, and that door was closed first. The other two are the bound
adapter's own `verify`: a review, which records a durable artifact carrying the
child's whole output, and a dispatch, which records evidence. A plan that names
no independent verifier never reaches the first door at all, so until the guard
these hold, an ordinary Confirm and an approved graph node both published a
success over a home this build had promised to take back and could not.

Driven through the real ControlRuntime and a real store, never through the
transport alone: what has to be proved is what a run's durable record ends up
holding, and the transport's own answer is one step short of that. The cleanup
refusal is the machine refusing, not a flag -- the third `discard_home` of the
road is made to raise BEFORE deleting, and the witness then asserts the
directory is physically still there. A refusal test that did not check that
would pass just as well against a home that was quietly removed.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from conductor.command.adapters import AdapterRegistry, harness_workspace
from conductor.command.artifacts import ArtifactDocument
from conductor.command.contracts import DecisionReceipt, RunEnvelope
from conductor.command.graph_definition import GraphDefinition, GraphEdge, GraphNode
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.runtime import AttemptState, Budget, ControlRuntime

from tests import _fakeclaude
from tests.test_command_claude_transport import NOW, _Ids
from tests.test_command_claude_review import (
    ARGUMENTS, CONFIG, INPUT_REF, RUN_ID, SEED_CONTENT, _confirmation, _proposal,
)
from tests.test_harness_login_leaks import a_signed_in_home
from tests.test_harness_subscription_login import a_harness

#: The vendor writes into its own home on every spawn, so the deletes are
#: counted rather than named: the version probe's, the login status probe's,
#: and third the TASK's. Failing the first two stops the dispatch before any
#: task, which is a different rule with its own witnesses.
TASK_HOME_DELETE = 3


def _dispatch_arguments() -> dict:
    return {
        "work_item_id": "work-001", "instruction_ref": INPUT_REF,
        "profile": "implement", "artifact_refs": [], "output_limit_profile": "normal",
    }


def _a_run(root, capability, proposal, *, with_graph):
    """One store holding a seeded input, this proposal, and its approved gate."""
    store = RunStore(root)
    store.create_run(
        RunEnvelope(run_id=RUN_ID, cycle_id="review-cycle", created_at=NOW,
                    config_digest=snapshot_digest(CONFIG), mode="confirm"),
        CONFIG)
    store.append(ArtifactDocument(
        artifact_id="artifact-source-1", artifact_ref=INPUT_REF, run_id=RUN_ID,
        created_at=NOW, media_type="text/markdown", content=SEED_CONTENT))
    if with_graph:
        store.append(GraphDefinition(
            graph_id="graph-retention", run_id=RUN_ID, created_at=NOW,
            nodes=(GraphNode(node_id="gate", kind="gate", title="Owner gate",
                             gate_id="owner-gate"),
                   GraphNode(node_id="do", kind="task", title="Do work",
                             instance_id=proposal.instance_id, capability=capability,
                             arguments=proposal.as_dict()["arguments"])),
            edges=(GraphEdge(from_node="gate", to_node="do"),)))
        store.append(DecisionReceipt(
            receipt_id="decision-owner-gate", run_id=RUN_ID, gate_id="owner-gate",
            action="approve", actor="owner", decided_at=NOW,
            reason="Approve the node this attempt runs under", scope_refs=("work",),
            config_digest=snapshot_digest(CONFIG)))
        proposal = replace(proposal, node_id="do", preview_digest="")
    store.append(proposal)
    return store, proposal


def _refusing_discard(monkeypatch, held, *, refuse):
    """Make the TASK's own home delete refuse, the way a locked tree does."""
    real = harness_workspace.HarnessWorkspace.discard_home
    seen: list[int] = []

    def discard(self, path):
        seen.append(1)
        if refuse and len(seen) == TASK_HOME_DELETE:
            held.append(path)
            raise OSError("this machine would not take the home back")
        return real(self, path)

    monkeypatch.setattr(
        harness_workspace.HarnessWorkspace, "discard_home", discard)


def _drive(tmp_path, monkeypatch, capability, *, refuse, with_graph):
    home = a_signed_in_home(tmp_path)
    knobs = ({_fakeclaude.EMIT_REVIEW: "enabled"} if capability == "review"
             else {_fakeclaude.WRITE_FILE: "result.txt:synthetic-work-result"})
    adapter, root, log = a_harness(
        tmp_path, auth="subscription", auth_home=str(home), **knobs)
    held: list = []
    _refusing_discard(monkeypatch, held, refuse=refuse)
    proposal = _proposal(ARGUMENTS)
    if capability == "dispatch":
        proposal = replace(proposal, capability="dispatch", preview_digest="",
                           arguments=_dispatch_arguments())
    store, proposal = _a_run(root, capability, proposal, with_graph=with_graph)
    runtime = ControlRuntime(
        store, AdapterRegistry([adapter]), clock=lambda: NOW, ids=_Ids())
    attempt = runtime.execute(runtime.authorize(
        replace(_confirmation(proposal), capability=capability),
        budget=Budget(max_actions=8, max_action_seconds=3600,
                      max_confirmation_age_seconds=3600)))
    records = store.read(RUN_ID).records
    return attempt, log, held, (
        [row.value for row in records
         if row.kind == "artifact" and row.value.source_action_id],
        [row.value for row in records if row.kind == "evidence"])


@pytest.mark.parametrize("capability", ["review", "dispatch"])
@pytest.mark.parametrize("with_graph", [False, True])
@pytest.mark.parametrize("refuse", [False, True])
def test_a_bound_verification_publishes_nothing_over_a_home_that_would_not_go(
        tmp_path, monkeypatch, capability, with_graph, refuse):
    """Eight combinations, and the pairing is the point.

    Both capabilities, both launch forms -- an ordinary Confirm and a task node
    behind an approved gate, neither naming an independent verifier -- and each
    of them driven twice: once with the cleanup this build normally does, and
    once with the machine refusing it.

    The controls are half the witness. A guard that refused everything would
    satisfy the refusal rows alone, and the four clean rows are what say this
    still publishes the work a run is entitled to.
    """
    attempt, _log, held, (artifacts, evidence) = _drive(
        tmp_path, monkeypatch, capability, refuse=refuse, with_graph=with_graph)

    assert bool(held) is refuse, "the fixture refused the delete it meant to"
    assert all(path.exists() for path in held), (
        "the home the delete refused is gone anyway, so this proves nothing")
    if not refuse:
        assert attempt.state is AttemptState.SUCCEEDED, attempt.receipt.detail
        assert len(evidence) == 1
        assert len(artifacts) == (1 if capability == "review" else 0)
        return
    assert attempt.state is not AttemptState.SUCCEEDED, attempt.receipt.detail
    assert evidence == [], "a run published evidence over a home it kept"
    assert artifacts == [], "the review's own text reached the record anyway"


def test_the_refusal_withholds_the_verdict_and_not_the_observation(
        tmp_path, monkeypatch):
    """What is refused is the verdict, never what this build watched happen.

    A guard that answered `failed`, or that reported no task, would be rewriting
    the observation: the child really ran and really exited zero, and a record
    saying otherwise is worse than the defect it replaces. The run lands on
    `verification_failed`, keeps the child's own exit code, and the spawn log
    still holds the task.
    """
    attempt, log, held, _records = _drive(
        tmp_path, monkeypatch, "dispatch", refuse=True, with_graph=False)

    assert held and all(path.exists() for path in held)
    assert attempt.state is AttemptState.VERIFICATION_FAILED, attempt.state.value
    assert attempt.receipt.exit_code == 0, attempt.receipt.exit_code
    assert len(_fakeclaude.prompt_spawns(log)) == 1, (
        "the record no longer says the task ran")


def test_one_actions_kept_home_does_not_refuse_another_actions_verification(
        tmp_path):
    """One adapter serves every action of its provider.

    The fact read is the ATTEMPT's, so a count a neighbour left on the transport
    is not this attempt's answer -- and reading `_retained` here, which is what
    a first version of this guard reaches for, is reading exactly that. This
    verification runs after its own turn is gone, so the count it would find is
    whatever ran last.
    """
    from tests.test_command_claude_transport import a_request, run_once

    adapter = a_harness(tmp_path)[0]
    request = a_request()
    receipt = run_once(adapter, request)
    adapter._retained = 1          # a sibling road failed its own cleanup

    verification = adapter.verify(request, receipt)

    assert "could not take back" not in (verification.detail or ""), (
        "a sibling's kept home refused this attempt's verification")
