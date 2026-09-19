"""A request the build before the rule authorized is never carried out after it.

F1 put one rule on every door that lets NEW work reach a run: a task's run writes
only in its own task, a run with no task in none. The review that closed F1 left
one case to hold durably: a request ALREADY standing in the journal -- one the
build before the rule authorized for a proposal writing outside its run's task,
whose process ended before it executed. The rule may not re-judge it (an exact
retry must still be answered by its own standing request, or history stops
reading the way it did), and nothing may carry it out.

That holds by construction: execution authority is a grant held in the memory of
the runtime that appended the request (`ControlRuntime._grants`), so a restarted
process holds none for a standing request, and the exact-retry road answers
without minting one. These witnesses write the journal with the build before the
rule itself -- the same runtime with ONLY its scope hold removed -- and read it
with a fresh runtime, and with the real server, the way a restart would. A
restart is never instantaneous, so the retry is made both at the instant the
request was written and later.

A PLAN frozen before the rule is history too: its step may name any scope, and a
proposal carrying out that step is judged by the authority to execute exactly as
a proposal with no step is.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import conductor.command.runtime as runtime_module
from conductor.command.adapters import AdapterRegistry
from conductor.command.artifacts import ArtifactDocument
from conductor.command.contracts import ActionProposal, DecisionReceipt, RunEnvelope
from conductor.command.graph_definition import GraphDefinition, GraphEdge, GraphNode
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.runtime import AttemptState, ControlRuntime
from conductor.command.runtime_values import AuthorizationError, ExecutionError
from conductor.command.service import CommandService, ServiceError
from tests import _fakeclaude
from tests.test_command_claude_transport import NOW, _Ids, a_harness
from tests.test_command_runtime_authorize import a_budget, a_confirmation
from tests.test_command_task_scope_authority import (
    CAPS, DISPATCH, FOREIGN, OLD, REVIEW, RUN, _confirm, _open_graphless, _records, _seed,
    _task_spawns, place)
from tests.test_cycle_harness_check_fix import cycle  # noqa: F401 -- fixture

#: The review's three rows. History is about the retry road, not the comparison,
#: whose every spelling the authority module already pins at each door.
REVIEWED = FOREIGN[:3]
LATER = "2026-08-22T13:00:00Z"
RESTARTS = [pytest.param(NOW, id="retried-at-once"), pytest.param(LATER, id="retried-later")]
#: What the doer writes if it is ever spawned: its presence is an overwrite.
NEW = "written by a request nobody may carry out"


def _arguments(capability: str, scope: str | None) -> dict:
    arguments = dict(DISPATCH if capability == "dispatch" else REVIEW)
    return arguments if scope is None else {**arguments, "work_scope": scope}


def _authorized_before_the_rule(runtime: ControlRuntime, proposal: ActionProposal):
    """Authorize `proposal` exactly as the build before F1 did: every hold but scope."""
    with pytest.MonkeyPatch.context() as before_the_rule:
        before_the_rule.setattr(runtime_module, "_hold_work_scope",
                                lambda proposal, recovered: None)
        standing = runtime.authorize(
            a_confirmation(proposal, confirmed_by="owner", confirmed_at=NOW),
            budget=a_budget())
    # The old build DID record it: the case under test exists, it is not assumed.
    assert standing.record_created is True
    return standing.request


def _a_run_frozen(tmp_path, task: str | None, capability: str):
    doer, root, log = a_harness(tmp_path / "doer", auth="api_key",
                                **{_fakeclaude.WRITE_FILE: f"result.txt:{NEW}"})
    config = {"cycle": {"id": "default-orbit", "phases": ["implement", "review"]},
              "instances": [{"id": "claude-dev", "adapter": doer.manifest.adapter_id}]}
    if task is not None:
        config["task"] = {"id": task, "work_scope": task}
    store = RunStore(root)
    store.create_run(RunEnvelope(run_id=RUN, cycle_id="default-orbit", created_at=NOW,
                                 config_digest=snapshot_digest(config), mode="confirm"), config)
    if capability == "review":
        store.append(ArtifactDocument(
            artifact_id="input-001", artifact_ref="input-ref", run_id=RUN, created_at=NOW,
            media_type="text/markdown", content="Review this input."))
    return AdapterRegistry([doer]), store, snapshot_digest(config), root, log


def _a_proposal(capability: str, scope: str | None, digest: str, **extra) -> ActionProposal:
    return ActionProposal(
        proposal_id="proposal-001", run_id=RUN, attempt_id="attempt-001",
        instance_id="claude-dev", capability=capability,
        arguments=_arguments(capability, scope), scope=("work",), proposed_by="owner",
        proposed_at=NOW, timeout_seconds=60, rationale="Carry the work out.",
        config_digest=digest, input_binding="proposal-v1", **extra)


def _a_standing_request(tmp_path, task: str | None, capability: str, scope: str | None,
                        restart_at: str = NOW):
    registry, store, digest, root, log = _a_run_frozen(tmp_path, task, capability)
    proposal = _a_proposal(capability, scope, digest)
    store.append(proposal)
    # The process that recorded it ends here, before it executed anything.
    standing = _authorized_before_the_rule(
        ControlRuntime(store, registry, clock=lambda: NOW, ids=_Ids()), proposal)
    target = root.joinpath(*place(scope)) / "result.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(OLD, encoding="utf-8")
    restarted = ControlRuntime(store, registry, clock=lambda: restart_at, ids=_a_later_mint())
    return restarted, store, proposal, standing, target, log


def _a_later_mint() -> _Ids:
    """A restarted process never re-mints the ids the first one handed out, so an
    exact retry that compared a freshly minted action id would be seen here."""
    ids = _Ids()
    ids.count = 1000
    return ids


def _kinds(store: RunStore) -> list[str]:
    return [row.kind for row in store.read(RUN).records]


def _spawns(log: Path) -> list[dict]:
    if not log.exists():
        return []
    return [row for row in (json.loads(line) for line in
                            log.read_text(encoding="utf-8").splitlines())
            if row.get("argv") != ["--version"]]


@pytest.mark.parametrize("restart_at", RESTARTS)
@pytest.mark.parametrize("capability", CAPS)
@pytest.mark.parametrize("task, scope", REVIEWED)
def test_a_standing_request_writing_elsewhere_is_answered_but_never_carried_out(
        tmp_path, capability, task, scope, restart_at):
    """After a restart the exact retry is still answered by its own standing
    request -- history reads as it did -- and carrying it out is refused: no
    spawn, no journal byte, the directory it named untouched. Retried at the
    instant the request was written and an hour later.

    Mutations: the retry road mints a grant (always, or only for a later
    confirmation) -> `execute` spawns -> red; the scope hold moved above the
    retry road -> the retry is refused -> red.
    """
    restarted, store, proposal, standing, target, log = _a_standing_request(
        tmp_path, task, capability, scope, restart_at)
    before = _kinds(store)

    retried = restarted.authorize(
        a_confirmation(proposal, confirmed_by="owner", confirmed_at=restart_at),
        budget=a_budget())
    assert (retried.request, retried.record_created) == (standing, False)
    with pytest.raises(ExecutionError, match="no live execution grant"):
        restarted.execute(retried)
    assert _spawns(log) == []
    assert target.read_text(encoding="utf-8") == OLD
    assert _kinds(store) == before


@pytest.mark.parametrize("capability", CAPS)
@pytest.mark.parametrize("task, scope", REVIEWED)
def test_a_standing_request_writing_elsewhere_is_closed_as_unknown_and_runs_nothing(
        tmp_path, capability, task, scope):
    """The operator's road out of such a request still works on it: `reconcile`
    records one terminal result whose DURABLE outcome is `unknown`, prepares and
    spawns nothing, and the run still reads -- the journal-readability obligation
    the review kept separate.

    Mutation: reconcile records `succeeded` while returning `unknown` -> red.
    """
    restarted, store, _proposal, standing, target, log = _a_standing_request(
        tmp_path, task, capability, scope)

    closed = restarted.reconcile(RUN, standing.action_id)
    last = store.read(RUN).records[-1]
    assert (last.kind, last.value.action_id, last.value.outcome) == (
        "action_result", standing.action_id, "unknown")
    assert closed.state is AttemptState.UNKNOWN
    assert _spawns(log) == []
    assert target.read_text(encoding="utf-8") == OLD


@pytest.mark.parametrize("capability", CAPS)
@pytest.mark.parametrize("task, scope", REVIEWED)
def test_a_restarted_server_confirming_a_standing_request_runs_nothing(
        cycle, capability, task, scope):
    """The same case through the real server: the journal is written by the build
    before the rule over the server's own store, then Confirm is sent again. The
    end state is read first -- no child, the bytes untouched -- then the answer:
    `200` with the standing request itself.

    On this road three layers stand between a standing request and a child: the
    runtime mints no grant on the retry road, the route places only a request it
    has just appended (`admit` is called on the append road alone), and the
    coordinator refuses an authorization that created nothing. Mutations: the
    retry road hands out a grant and `record_created` -> the route answers 201
    and places nothing -> red on the answer; the retry road also admits -> the
    route places it, a child writes -> red on the end state.
    """
    _open_graphless(cycle, task)
    store = cycle.server.command_store
    if capability == "review":
        store.append(ArtifactDocument(
            artifact_id="input-001", artifact_ref="input-ref", run_id=RUN, created_at=NOW,
            media_type="text/markdown", content="Review this input."))
    proposal = _a_proposal(capability, scope, store.read(RUN).envelope.config_digest)
    store.append(proposal)
    standing = _authorized_before_the_rule(
        ControlRuntime(store, cycle.server.command_registry, clock=lambda: NOW, ids=_Ids()),
        proposal)
    target = _seed(cycle, scope)
    before = _records(cycle)

    status, answered = _confirm(cycle, proposal.proposal_id, proposal.preview_digest,
                                proposal.config_digest, capability)
    assert _task_spawns(cycle) == []
    assert target.read_text(encoding="utf-8") == OLD
    assert _records(cycle) == before
    assert (status, answered) == (200, standing.as_dict())


PLANNED = [pytest.param("victim", False, id="step-names-victim"),
           pytest.param(None, False, id="step-names-none"),
           pytest.param("own", True, id="step-names-own")]


@pytest.mark.parametrize("capability", CAPS)
@pytest.mark.parametrize("scope, admitted", PLANNED)
def test_a_step_a_plan_froze_before_the_rule_is_granted_only_in_its_own_task(
        tmp_path, capability, scope, admitted):
    """A plan frozen before the rule, on a run bound to task `own`, whose step
    names another task's scope, or none -- the plan doors never judged it. A
    proposal carrying the step out names the step, and both doors judge it
    exactly as a proposal naming no step: the proposal door refuses to record it,
    and one recorded anyway (as the build before the rule did) gets no authority
    to execute. Whatever is granted is carried out, and the end state is read
    first. The control is the same plan naming `own`, recorded and granted, so
    what refuses is the scope and no other hold of the plan.

    Mutations: either door exempts a proposal bound to a step -> the foreign
    step's proposal is recorded, or granted and carried out -> red.
    """
    registry, store, digest, root, log = _a_run_frozen(tmp_path, "own", capability)
    arguments = _arguments(capability, scope)
    store.append(GraphDefinition(
        graph_id="graph-001", run_id=RUN, created_at=NOW,
        nodes=(GraphNode(node_id="confirm-gate", kind="gate", title="Human",
                         gate_id="gate-confirm-do"),
               GraphNode(node_id="do", kind="task", title="Do the work",
                         instance_id="claude-dev", capability=capability,
                         arguments=arguments)),
        edges=(GraphEdge(from_node="confirm-gate", to_node="do"),)))
    store.append(DecisionReceipt(
        receipt_id="decision-gate-confirm-do", run_id=RUN, gate_id="gate-confirm-do",
        action="approve", actor="owner", decided_at=NOW, reason="Let the work through",
        scope_refs=("work",), config_digest=digest))
    target = root.joinpath(*place(scope)) / "result.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(OLD, encoding="utf-8")
    runtime = ControlRuntime(store, registry, clock=lambda: NOW, ids=_Ids())

    def propose():
        return CommandService(store, registry, clock=lambda: NOW, ids=_Ids()).propose(
            run_id=RUN, instance_id="claude-dev", attempt_id="attempt-001",
            capability=capability, arguments=arguments, scope=("work",),
            proposed_by="owner", rationale="Carry the work out.", timeout_seconds=60,
            node_id="do")

    if admitted:
        recorded = propose()
        granted = runtime.authorize(
            a_confirmation(recorded, confirmed_by="owner", confirmed_at=NOW), budget=a_budget())
        assert granted.record_created is True
        return
    with pytest.raises(ServiceError, match="task scope"):
        propose()
    proposal = _a_proposal(capability, scope, digest, node_id="do")
    store.append(proposal)
    refusal = None
    try:
        granted = runtime.authorize(
            a_confirmation(proposal, confirmed_by="owner", confirmed_at=NOW), budget=a_budget())
    except AuthorizationError as refused:
        refusal = refused
    else:
        runtime.execute(granted)
    assert _spawns(log) == []
    assert target.read_text(encoding="utf-8") == OLD
    assert "action_request" not in _kinds(store)
    assert isinstance(refusal, AuthorizationError) and "task scope" in str(refusal), refusal
