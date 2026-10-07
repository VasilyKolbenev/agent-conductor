"""No work lands outside its run's task -- with a plan or without one.

The plan doors held a PLANNED run to its task (`plan_admission.work_scope_admits`).
A run that follows no graph never reached them: the ordinary proposal route took a
caller-written `work_scope`, and the transport used it as a path. The 2026-09-18
repeat review drove it over HTTP: a task-less run, and a run bound to task `own`,
each overwrote task `victim`'s files; a run bound to `own` that named no scope
overwrote the task-less `work/<item>` (review F1, P1).

One predicate (`task_contracts.work_scope_disagreement`) now answers at three
doors, and each door has its own witness here, so a mutation at one is not hidden
by the refusal of another:

- the PROPOSAL door (`CommandService.propose`): a proposal that would write outside
  its run's task is never recorded -- asserted over HTTP on the review's rows and
  on the service directly;
- the AUTHORITY to execute (`ControlRuntime.authorize`): a proposal that reached
  the journal by any other road -- recorded before the rule, or appended directly
  -- gets no grant, and without a grant nothing is spawned; asserted through the
  real confirmation route and on the runtime directly.

The rule is EXACT equality with the frozen scope, and the rows below pin that
exactness at every door: a scope that extends the run's own, one its own extends,
one of the same length, one that differs only in case, and one that differs only
by a trailing dot -- the last two name the run's own directory on this
filesystem and a different one on others, so no door may fold them together.
Every end state (no child, the bytes of the directory named) is asserted BEFORE
the status, so a door that opens reddens the line that says what it let happen.

Dispatch and review both carry a work item, so both are covered. Only the vendor
program is scripted.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from conductor.command.adapters import AdapterRegistry
from conductor.command.adapters.claude_code import CLAUDE_PROVIDER_ID
from conductor.command.api_contracts import ERROR_STATUS
from conductor.command.artifacts import ArtifactDocument
from conductor.command.contracts import ActionProposal, RunEnvelope
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.runtime import ControlRuntime
from conductor.command.runtime_values import AuthorizationError
from conductor.command.service import CommandService, ServiceError
from tests import _fakeclaude
from tests.test_command_claude_transport import NOW, _Ids, a_harness
from tests.test_command_runtime_authorize import a_budget, a_confirmation
from tests.test_cycle_harness_check_fix import DRAFT, cycle  # noqa: F401 -- fixture

RUN = "run-scope-001"
OLD = "bytes that were here before -- nobody was given this directory"
CAPS = ("dispatch", "review")
#: (the run's task, the scope the proposal names). The first three are the rows
#: the review found overwriting a directory that was not theirs.
FOREIGN = [
    pytest.param(None, "victim", id="taskless-names-victim"),
    pytest.param("own", "victim", id="own-names-victim"),
    pytest.param("own", None, id="own-names-none"),
    pytest.param("own", "owner", id="own-names-owner"),
    pytest.param("owner", "own", id="owner-names-own"),
    pytest.param("own", "abc", id="own-names-abc"),
    pytest.param("own", "OWN", id="own-names-OWN"),
    pytest.param("own", "own.", id="own-names-own-dot"),
]
#: ... and the two that must still carry work out, each in its OWN place.
OWN = [pytest.param("own", "own", id="own-names-own"),
       pytest.param(None, None, id="taskless-names-none")]
TASKS = ("own", "owner", "victim")
DISPATCH = {"work_item_id": "work-001", "instruction_ref": "instr-001",
            "profile": "implement", "artifact_refs": [], "output_limit_profile": "small"}
REVIEW = {"work_item_id": "work-001", "target_artifact_refs": ["input-ref"],
          "result_artifact_ref": "review-result", "review_profile": "quality"}


def place(scope: str | None) -> tuple[str, ...]:
    """Where a proposal naming `scope` would put work-001, spelled by the TEST."""
    return ("work", "work-001") if scope is None else ("work", "_tasks", scope, "work-001")


# -- the review's rows, over the real server ----------------------------------------


def _open_graphless(cycle, task: str | None) -> None:
    for task_id in TASKS:
        assert cycle.call("POST", "/command/tasks",
                          {"task_id": task_id, "title": f"task {task_id}"})[0] == 201
    status, opened = cycle.call("POST", "/command/runs", {
        "run_id": RUN, "cycle_id": "default-orbit", "mode": "confirm",
        "participants": [{"instance_id": "claude-dev", "provider_id": CLAUDE_PROVIDER_ID,
                          "model": None}],
        "workflow_id": None, "revision": None, "assignments": {}, "task_id": task})
    assert status == 201, opened
    assert cycle.call("POST", f"/command/runs/{RUN}/artifacts", {
        "artifact_id": "brief-1", "artifact_ref": "instr-001",
        "media_type": "text/markdown", "content": "Do the work."})[0] == 201


def _propose(cycle, scope: str | None):
    arguments = dict(DISPATCH, **({} if scope is None else {"work_scope": scope}))
    return cycle.call("POST", f"/command/runs/{RUN}/proposals", {
        "instance_id": "claude-dev", "attempt_id": "attempt-001", "capability": "dispatch",
        "arguments": arguments, "scope": ["work"], "proposed_by": "owner",
        "rationale": "Carry the work out.", "timeout_seconds": 60})


def _confirm(cycle, proposal_id: str, preview_digest: str, config_digest: str,
             capability: str = "dispatch"):
    answer = cycle.call("POST", f"/command/runs/{RUN}/actions", {
        "proposal_id": proposal_id, "preview_digest": preview_digest,
        "capability": capability, "scope": ["work"], "config_digest": config_digest,
        "confirmed_by": "owner"})
    assert cycle.server.command_execution.wait_idle(120) is True
    return answer


def _seeded(root: Path, scope: str | None) -> Path:
    """Bytes nobody may overwrite, in the directory `scope` names under `root`."""
    target = root.joinpath(*place(scope)) / "result.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(OLD, encoding="utf-8")
    return target


def _seed(cycle, scope: str | None) -> Path:
    return _seeded(cycle.root, scope)


def _records(cycle) -> list[str]:
    status, run = cycle.call("GET", f"/command/runs/{RUN}")
    assert status == 200, run
    return [row["record_type"] for row in run["records"]]


def _task_spawns(cycle) -> list[dict]:
    if not cycle.doer_log.exists():
        return []
    return [row for row in (json.loads(line) for line in
                            cycle.doer_log.read_text(encoding="utf-8").splitlines())
            if row.get("argv") != ["--version"]]


@pytest.mark.parametrize("task, scope", FOREIGN)
def test_a_graphless_proposal_writing_outside_its_task_is_never_recorded(cycle, task, scope):
    """Refused AT THE PROPOSAL DOOR (`service_refused`) with nothing recorded.

    Driven the way a person drives it: propose, and confirm only what was
    admitted. The end state is read first -- no child, the directory's bytes as
    they were -- then the door's own answer.

    Mutations: drop the proposal door's hold -> the proposal is recorded and
    answered 201 -> red on the journal and the status, while the end state still
    holds because the authority to execute refuses the confirmation (its own
    witness is below). Drop both holds -> a child writes -> red on the end state.
    """
    _open_graphless(cycle, task)
    target = _seed(cycle, scope)
    before = _records(cycle)

    status, answered = _propose(cycle, scope)
    if status == 201:
        _confirm(cycle, answered["proposal_id"], answered["preview_digest"],
                 answered["config_digest"])
    assert _task_spawns(cycle) == []
    assert target.read_text(encoding="utf-8") == OLD
    assert _records(cycle) == before
    assert (status, answered["error"]["code"]) == (
        ERROR_STATUS["service_refused"], "service_refused"), answered


@pytest.mark.parametrize("task, scope", FOREIGN)
def test_a_recorded_proposal_writing_elsewhere_is_confirmed_into_no_process(cycle, task, scope):
    """The same rows, as a proposal ALREADY in the journal -- one recorded before
    this rule existed, which the proposal door can no longer turn away. Confirmed
    through the real route, it is refused by the authority to execute
    (`authorization_refused`): no request, no child, the bytes untouched.

    Written through the server's own store, so the proposal door is never asked
    and cannot be what refuses. Mutation: drop `_hold_work_scope` -> the route
    grants and a child overwrites the target -> red on the end state, read first.
    """
    _open_graphless(cycle, task)
    target = _seed(cycle, scope)
    store = cycle.server.command_store
    arguments = dict(DISPATCH, **({} if scope is None else {"work_scope": scope}))
    proposal = ActionProposal(
        proposal_id="proposal-recorded", run_id=RUN, attempt_id="attempt-001",
        instance_id="claude-dev", capability="dispatch", arguments=arguments,
        scope=("work",), proposed_by="owner", proposed_at="2026-09-18T12:00:00Z",
        timeout_seconds=60, rationale="Carry the work out.",
        config_digest=store.read(RUN).envelope.config_digest, input_binding="proposal-v1")
    store.append(proposal)
    before = _records(cycle)

    status, refused = _confirm(cycle, proposal.proposal_id, proposal.preview_digest,
                               proposal.config_digest)
    assert _task_spawns(cycle) == []
    assert target.read_text(encoding="utf-8") == OLD
    assert _records(cycle) == before
    assert (status, refused["error"]["code"]) == (
        ERROR_STATUS["authorization_refused"], "authorization_refused"), refused


@pytest.mark.parametrize("task, scope", OWN)
def test_a_graphless_proposal_writing_in_its_own_place_still_carries_the_work_out(
        cycle, task, scope):
    """The two positive controls: the child stands in exactly the place the run
    owns, compared as a whole resolved path, and writes there."""
    _open_graphless(cycle, task)
    target = _seed(cycle, scope)
    status, proposal = _propose(cycle, scope)
    assert status == 201, proposal
    status, confirmed = _confirm(cycle, proposal["proposal_id"],
                                 proposal["preview_digest"], proposal["config_digest"])
    assert status == 201, confirmed
    spawns = _task_spawns(cycle)
    assert [Path(row["cwd"]).resolve() for row in spawns] == [
        cycle.root.resolve().joinpath(*place(scope))]
    assert target.read_text(encoding="utf-8") == DRAFT


# -- the two doors, asked directly -------------------------------------------------


def _a_run(tmp_path, task: str | None, capability: str, scope: str | None, *,
           binding: object = None, **knobs: str) -> SimpleNamespace:
    """A graphless run with one proposal written, NOT yet recorded anywhere.

    `binding` replaces the frozen task binding outright -- how a run whose
    binding does not read is written.
    """
    doer, root, log = a_harness(tmp_path / "doer", auth="api_key", **knobs)
    config = {"cycle": {"id": "default-orbit", "phases": ["implement", "review"]},
              "instances": [{"id": "claude-dev", "adapter": doer.manifest.adapter_id}]}
    if binding is not None:
        config["task"] = binding
    elif task is not None:
        config["task"] = {"id": task, "work_scope": task}
    store = RunStore(root)
    store.create_run(RunEnvelope(run_id=RUN, cycle_id="default-orbit", created_at=NOW,
                                 config_digest=snapshot_digest(config), mode="confirm"), config)
    if capability == "review":
        store.append(ArtifactDocument(
            artifact_id="input-001", artifact_ref="input-ref", run_id=RUN, created_at=NOW,
            media_type="text/markdown", content="Review this input."))
    arguments = dict(DISPATCH if capability == "dispatch" else REVIEW)
    if scope is not None:
        arguments["work_scope"] = scope
    proposal = ActionProposal(
        proposal_id="proposal-001", run_id=RUN, attempt_id="attempt-001",
        instance_id="claude-dev", capability=capability, arguments=arguments,
        scope=("work",), proposed_by="owner", proposed_at=NOW, timeout_seconds=60,
        rationale="Carry the work out.", config_digest=snapshot_digest(config),
        input_binding="proposal-v1")
    return SimpleNamespace(registry=AdapterRegistry([doer]), store=store,
                           proposal=proposal, root=root, log=log)


def _kinds(store: RunStore) -> list[str]:
    return [row.kind for row in store.read(RUN).records]


def _spawns(log: Path) -> list[dict]:
    if not log.exists():
        return []
    return [row for row in (json.loads(line) for line in
                            log.read_text(encoding="utf-8").splitlines())
            if row.get("argv") != ["--version"]]


def _propose_directly(run: SimpleNamespace):
    return CommandService(run.store, run.registry, clock=lambda: NOW, ids=_Ids()).propose(
        run_id=RUN, instance_id="claude-dev", attempt_id="attempt-001",
        capability=run.proposal.capability, arguments=run.proposal.arguments,
        scope=("work",), proposed_by="owner", rationale="Carry the work out.",
        timeout_seconds=60)


def _authorize_directly(run: SimpleNamespace):
    runtime = ControlRuntime(run.store, run.registry, clock=lambda: NOW, ids=_Ids())
    granted = runtime.authorize(a_confirmation(run.proposal, confirmed_at=NOW),
                                budget=a_budget())
    return runtime, granted


def _carry_out(run: SimpleNamespace, proposal: ActionProposal | None = None):
    """Confirm, and carry out whatever is granted -- the road a person's Confirm
    takes. Returns the refusal, or None when the work was granted and executed,
    so a door that opens is seen by what its child did, not only by its answer."""
    runtime = ControlRuntime(run.store, run.registry, clock=lambda: NOW, ids=_Ids())
    try:
        granted = runtime.authorize(
            a_confirmation(proposal or run.proposal, confirmed_at=NOW), budget=a_budget())
    except AuthorizationError as refusal:
        return refusal
    runtime.execute(granted)
    return None


@pytest.mark.parametrize("capability", CAPS)
@pytest.mark.parametrize("task, scope", FOREIGN)
def test_the_service_refuses_the_proposal_before_one_byte_is_recorded(
        tmp_path, capability, task, scope):
    """The proposal door, asked by its direct caller rather than by the route.

    Mutation: drop `_hold_proposal_writes_in_its_task` -> the proposal is appended
    -> red.
    """
    run = _a_run(tmp_path, task, capability, scope)
    before = _kinds(run.store)
    with pytest.raises(ServiceError, match="task scope"):
        _propose_directly(run)
    assert _kinds(run.store) == before


@pytest.mark.parametrize("capability", CAPS)
@pytest.mark.parametrize("task, scope", FOREIGN)
def test_a_recorded_proposal_writing_elsewhere_is_granted_no_authority_to_execute(
        tmp_path, capability, task, scope):
    """The authority boundary, on a proposal the proposal door never judged: one
    appended to the journal directly, as a proposal recorded before the rule
    existed would be. No grant, so nothing can be spawned (`execute` refuses an
    action this runtime did not grant), and no request is written. Whatever is
    granted is carried out, and the end state is read before the refusal.

    Mutation: drop `_hold_work_scope` from `authorize` -> a request is granted
    and a child spawned -> red on the end state.
    """
    run = _a_run(tmp_path, task, capability, scope)
    run.store.append(run.proposal)
    target = _seeded(run.root, scope)
    before = _kinds(run.store)
    refusal = _carry_out(run)
    assert _spawns(run.log) == []
    assert target.read_text(encoding="utf-8") == OLD
    assert _kinds(run.store) == before
    assert isinstance(refusal, AuthorizationError) and "task scope" in str(refusal), refusal


@pytest.mark.parametrize("foreign_first", [
    pytest.param(False, id="compliant-recorded-first"),
    pytest.param(True, id="foreign-recorded-first")])
def test_the_authority_judges_the_proposal_it_is_asked_to_grant(tmp_path, foreign_first):
    """Two proposals on one task-less run: one filing its work where the run may,
    one naming task `victim`. Whichever was recorded first, the one naming victim
    is refused and nothing runs, and the other is granted -- the hold reads the
    proposal being confirmed, never a neighbour in the journal.

    Mutation: the hold judges the run's first recorded proposal -> one order
    carries victim's work out, the other refuses the compliant one -> red.
    """
    run = _a_run(tmp_path, None, "dispatch", None)
    compliant = run.proposal
    foreign = ActionProposal(
        proposal_id="proposal-foreign", run_id=RUN, attempt_id="attempt-002",
        instance_id="claude-dev", capability="dispatch",
        arguments={**DISPATCH, "work_scope": "victim"}, scope=("work",), proposed_by="owner",
        proposed_at=NOW, timeout_seconds=60, rationale="Carry the work out.",
        config_digest=compliant.config_digest, input_binding="proposal-v1")
    for proposal in ((foreign, compliant) if foreign_first else (compliant, foreign)):
        run.store.append(proposal)
    target = _seeded(run.root, "victim")

    refusal = _carry_out(run, foreign)
    assert _spawns(run.log) == []
    assert target.read_text(encoding="utf-8") == OLD
    assert isinstance(refusal, AuthorizationError) and "task scope" in str(refusal), refusal
    assert _authorize_directly(run)[1].record_created is True


@pytest.mark.parametrize("capability", CAPS)
@pytest.mark.parametrize("task, scope", OWN)
def test_work_granted_in_its_own_place_stands_in_exactly_that_place(
        tmp_path, capability, task, scope):
    """The controls at the authority boundary, carried all the way to the child:
    granted, executed, and the child's cwd is the whole path the run owns --
    for review as for dispatch, since a review stands in the directory of the
    work it reviews. An always-refusing hold reds here, and so does a transport
    that files either capability's child anywhere else.

    Mutation: the review transport routes its child without the scope -> a
    task's review stands in `work/work-001` -> red.
    """
    run = _a_run(tmp_path, task, capability, scope,
                 **{_fakeclaude.WRITE_FILE: "result.txt:done",
                    _fakeclaude.EMIT_REVIEW: "enabled-review-output"})
    run.store.append(run.proposal)
    runtime, granted = _authorize_directly(run)
    assert granted.record_created is True
    runtime.execute(granted)
    assert [Path(row["cwd"]).resolve() for row in _spawns(run.log)] == [
        run.root.resolve().joinpath(*place(scope))]


@pytest.mark.parametrize("capability", CAPS)
@pytest.mark.parametrize("scope", [pytest.param("victim", id="names-victim"),
                                   pytest.param(None, id="names-none")])
def test_a_run_whose_task_binding_does_not_read_is_given_no_work_at_either_door(
        tmp_path, capability, scope):
    """Half a binding is not "no task": a run whose frozen binding does not read
    as one belongs to NO answer, so neither door may treat it as task-less --
    which would refuse a proposal naming a scope but let one naming NONE file its
    work among task-less history. Both are refused at the proposal door and at
    the authority to execute, each naming the binding; whatever is granted is
    carried out, and the end state is read first.

    Mutations: either hold reads an unreadable binding as no task, wholly or only
    when no scope is named -> the no-scope proposal is recorded, or granted and
    carried out -> red.
    """
    run = _a_run(tmp_path, None, capability, scope, binding={"id": "own"})
    target = _seeded(run.root, scope)
    before = _kinds(run.store)
    with pytest.raises(ServiceError, match="invalid task binding"):
        _propose_directly(run)
    assert _kinds(run.store) == before

    run.store.append(run.proposal)
    refusal = _carry_out(run)
    assert _spawns(run.log) == []
    assert target.read_text(encoding="utf-8") == OLD
    assert "action_request" not in _kinds(run.store)
    assert isinstance(refusal, AuthorizationError), refusal
    assert "invalid task binding" in str(refusal)
