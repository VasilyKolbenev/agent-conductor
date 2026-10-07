"""The preparation read of a task (spec 6.4.2) and `missing_bindings`, the rules of `bind_inputs`
that answer instead of raising.

A run is built here the way the desk builds it: opened on a shipped cycle bound to a task, then
given the documents its steps read. The stage of each run is the first of five that fits, so the
order is held as a table over the facts and every stage that can occur today is reached by a
real run. `queued` and the receipt time need the queue store (spec 4.4, days 7 to 9): the read
takes them from a `QueueView` its caller hands in, so the order is complete and tested now.
"""
import itertools

import pytest

from conductor.command import task_preparation
from conductor.command.adapters import AdapterRegistry
from conductor.command.api_refusals import ApiRefusal
from conductor.command.artifacts import ArtifactDocument, required_input_refs
from conductor.command.authorization_inputs import bind_inputs, executable_nodes
from conductor.command.contract_values import ContractError, _id, _unique_ids
from conductor.command.contracts import DecisionReceipt, RunEnvelope
from conductor.command.graph_definition import GraphDefinition, GraphEdge, GraphNode
from conductor.command.graph_schedule import schedule
from conductor.command.http_api import CommandApi
from conductor.command.http_transport import CommandSession
from conductor.command.graph_template import (
    TEMPLATE_DIR, GraphTemplate, RunBinding, load_template, materialize)
from conductor.command.policy_service import PolicyService
from conductor.command.run_closing import close_if_terminal
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.runtime import Budget
from conductor.command.task_contracts import MAX_TASK_ID, TaskRecord
from conductor.command.task_store import TaskStore
from conductor.command.workflow_flow import compile_flow
from tests.test_command_graph_projection import a_proposal, a_request, a_result
from tests.test_command_http_api import PORT, TOKEN, get_headers, post
from tests.test_command_workflow_flow import CANONICAL, STUDIO_CORPUS, accepted
from tests.test_command_workflow_routes import durable_digest
from tests.test_policy_runtime import NOW, PD, Activation
from tests.test_standard_cycle_correction import Checker, Doer

TASK = "task-prepare-1"
#: The terms the standard cycle is offered (spec 7.8): four actions, 12 600 s, a 16 200 s window.
STANDARD_ASK = {
    "node_limits": [{"node_id": "analyst", "timeout_seconds": 1800, "max_attempts": 1},
                    {"node_id": "do", "timeout_seconds": 1800, "max_attempts": 3}],
    "max_actions": 4, "max_action_seconds": 3600, "max_total_task_seconds": 12600,
    "duration_seconds": 16200}
CARRIES = ["run_id", "created_at", "workflow_id", "revision", "stage", "missing", "grant", "queue"]


def config_for(run_id, task_id, workflow_id):
    return {"cycle": {"id": run_id},
            "instances": [{"id": "doer", "adapter": "claude-code"},
                          {"id": "checker", "adapter": "codex-cli"}],
            "workflow": {"id": workflow_id, "revision": 1},
            "task": {"id": task_id, "work_scope": task_id},
            "automation_contract": "bounded-run-v1"}


def binding_of(template):
    return RunBinding(assignments={
        role: "checker" if role == "role-checker" else "doer" for role in template.roles})


class Project:
    """One project folder holding a task and the runs opened for it."""

    def __init__(self, root):
        self.root = root
        self.store, self.tasks = RunStore(root), TaskStore(root)
        self.tasks.create_task(TaskRecord(
            task_id=TASK, title="Prepare it", work_scope=TASK, created_at=NOW))
        registry = AdapterRegistry([Doer(self.store), Checker(self.store, [])])
        self.policy = PolicyService(
            self.store, registry, budget=Budget(8, 3600, 300), clock=lambda: NOW,
            provider_digest=lambda config: PD, owner_check=lambda: None, session="session",
            notify=lambda run_id: None)
        self.policy.driver = Activation()

    def open_run(self, number, workflow="desk-standard", task_id=TASK, template=None):
        run_id = f"{task_id}-r{number}"
        config = config_for(run_id, task_id, workflow)
        self.store.create_run(RunEnvelope(
            run_id, run_id, NOW, snapshot_digest(config), mode="policy"), config)
        template = load_template(workflow) if template is None else template
        self.store.append(materialize(
            template, binding_of(template), config, graph_id=f"graph-{run_id}", run_id=run_id,
            created_at=NOW))
        return run_id

    def publish(self, run_id, *refs):
        for ref in refs:
            self.store.append(ArtifactDocument(
                artifact_id=f"doc-{ref}", run_id=run_id, artifact_ref=ref, created_at=NOW,
                media_type="text/markdown", content=f"{ref}.\n"))

    def ready_run(self, number):
        run_id = self.open_run(number)
        self.publish(run_id, "artifact-brief", "artifact-materials", "instruction-do")
        return run_id

    def grant(self, run_id, ask=STANDARD_ASK):
        preview = self.policy.preview(run_id, ask)
        return self.policy.authorize(run_id, {
            "authorization_id": f"grant-{run_id}", "preview_digest": preview["preview_digest"],
            "authorized_by": "owner", "terms": preview["terms"], "supersedes": None})[0]

    def gate_only_run(self, number):
        """A plan of one gate, decided: nothing is left to open, so the plan is `complete`."""
        run_id = f"{TASK}-r{number}"
        config = config_for(run_id, TASK, "custom")
        self.store.create_run(RunEnvelope(
            run_id, run_id, NOW, snapshot_digest(config), mode="policy"), config)
        self.store.append(GraphDefinition(
            f"graph-{run_id}", run_id, NOW,
            nodes=(GraphNode("gate", "gate", "Approve", gate_id="gate-id"),), edges=()))
        self.store.append(DecisionReceipt(
            "decision", run_id, "gate-id", "approve", "owner", NOW, "Reviewed", ("gate-id",),
            snapshot_digest(config)))
        return run_id

    def stalled_run(self, number):
        """A gate, then the shipped `do` step allowed one attempt, answered `unknown`: the bound
        is spent, so what is owed is owed for good. The plan reads `stalled` and no ending is
        recorded yet. A confirm-mode run, because a bounded run's store takes no request by hand."""
        run_id = f"{TASK}-r{number}"
        config = config_for(run_id, TASK, "custom")
        self.store.create_run(RunEnvelope(
            run_id, run_id, NOW, snapshot_digest(config), mode="confirm"), config)
        template = load_template("desk-short")
        drawn = materialize(template, binding_of(template), config, graph_id="graph-drawn",
                            run_id=run_id, created_at=NOW)
        step = GraphNode.from_dict(
            {**next(node for node in drawn.nodes if node.node_id == "do").as_dict(),
             "attempt_bound": 1})
        self.store.append(GraphDefinition(
            f"graph-{run_id}", run_id, NOW, edges=(GraphEdge("gate", "do"),),
            nodes=(GraphNode("gate", "gate", "Approve", gate_id="gate-id"), step)))
        self.store.append(DecisionReceipt(
            "decision", run_id, "gate-id", "approve", "owner", NOW, "Reviewed", ("src",),
            snapshot_digest(config)))
        self.publish(run_id, "artifact-brief", "artifact-materials", "instruction-do")
        proposal = a_proposal(
            node_id="do", index=1, run_id=run_id, instance_id=step.instance_id,
            capability=step.capability, arguments=step.payload(),
            config_digest=snapshot_digest(config))
        request = a_request(proposal, index=1, run_id=run_id)
        for record in (proposal, request, a_result(
                request, index=1, run_id=run_id, outcome="unknown", evidence_refs=())):
            self.store.append(record)
        return run_id

    def read(self, queue=None):
        args = () if queue is None else (queue,)
        status, payload = task_preparation.read_preparation(self.tasks, self.store, TASK, *args)
        assert status == 200
        return payload

    def row(self, run_id, queue=None):
        return next(row for row in self.read(queue)["runs"] if row["run_id"] == run_id)


@pytest.fixture
def project(tmp_path):
    return Project(tmp_path / "project")


# --- the stage: the first that fits ---------------------------------------------------------------

STAGE_ORDER = ("ended", "queued", "authorized", "documents_missing", "ready_to_preview")


def expected_stage(ended, queued, granted, missing):
    return next(name for name, holds in zip(STAGE_ORDER, (ended, queued, granted, missing, True))
                if holds)


@pytest.mark.parametrize("facts", list(itertools.product([False, True], repeat=4)))
def test_preparation_reports_the_first_matching_stage(facts):
    assert task_preparation.first_stage(*facts) == expected_stage(*facts)


def test_each_stage_a_real_run_can_reach_today_is_reached_by_one(project):
    missing, ready = project.open_run(1), project.ready_run(2)
    granted, queued = project.ready_run(3), project.ready_run(4)
    project.grant(granted)
    project.grant(queued)
    ended = project.gate_only_run(5)
    line = {"state": "waiting", "position": 1, "reason_code": None,
            "state_since": "2026-08-11T11:00:00Z"}
    view = task_preparation.QueueView(entries={queued: line})
    stages = {row["run_id"]: row["stage"] for row in project.read(view)["runs"]}
    assert stages == {missing: "documents_missing", ready: "ready_to_preview",
                      granted: "authorized", queued: "queued", ended: "ended"}


def test_a_run_whose_ending_is_recorded_is_ended_and_the_record_changes_nothing_else(project):
    run_id = project.gate_only_run(1)
    before = project.row(run_id)
    ids = iter(range(10))
    closed = close_if_terminal(project.store, run_id, clock=lambda: NOW,
                               ids=lambda kind: f"{kind}-{next(ids)}")
    assert closed is not None
    assert project.row(run_id) == before and before["stage"] == "ended"


def test_a_run_closed_as_stalled_is_ended_by_its_record_alone(project):
    run_id = project.stalled_run(1)
    records = project.store.read(run_id).records
    plan = next(row.value for row in records if row.kind == "graph_definition")
    assert schedule(plan, tuple(row.value for row in records)).run_state == "stalled"
    before = project.row(run_id)
    closed = close_if_terminal(project.store, run_id, clock=lambda: NOW,
                               ids=lambda kind: f"{kind}-1")
    assert closed is not None and closed.state == "stalled"
    assert before["stage"] == "ready_to_preview"
    assert project.row(run_id) == {**before, "stage": "ended"}


def test_a_queue_entry_of_an_ended_run_does_not_make_it_queued(project):
    ended = project.gate_only_run(1)
    view = task_preparation.QueueView(entries={ended: {
        "state": "waiting", "position": 1, "reason_code": None, "state_since": None}})
    assert project.row(ended, view)["stage"] == "ended"


# --- the shape ------------------------------------------------------------------------------------


def test_the_read_carries_the_task_the_seed_the_next_number_and_the_runs_by_id(project):
    second, first = project.ready_run(2), project.open_run(1)
    payload = project.read()
    assert list(payload) == ["task", "seed", "next_run_number", "runs"]
    assert payload["task"] == {"schema_version": 1, "task_id": TASK, "title": "Prepare it",
                               "work_scope": TASK, "created_at": NOW}
    assert payload["seed"] is None and payload["next_run_number"] == 3
    assert [row["run_id"] for row in payload["runs"]] == [first, second]
    assert list(payload["runs"][0]) == CARRIES


def test_a_run_row_names_its_cycle_its_revision_its_missing_documents_and_no_grant_or_queue(
        project):
    run_id = project.open_run(1)
    project.publish(run_id, "artifact-brief")
    assert project.row(run_id) == {
        "run_id": run_id, "created_at": NOW, "workflow_id": "desk-standard", "revision": 1,
        "stage": "documents_missing",
        "missing": {"instructions": [{"node_id": "do", "instruction_ref": "instruction-do"}],
                    "inputs": ["artifact-materials"]},
        "grant": None, "queue": None}


def test_a_run_with_a_grant_shows_the_last_grant_and_no_receipt_time_without_the_queue(project):
    run_id = project.ready_run(1)
    project.grant(run_id)
    row = project.row(run_id)
    assert row["stage"] == "authorized" and row["missing"] == {"instructions": [], "inputs": []}
    assert row["grant"] == {"authorization_id": f"grant-{run_id}", "authorized_by": "owner",
                            "authorized_at": NOW, "preauthorized_at": None}


def test_preparation_shows_preauthorized_at_for_a_grant_started_by_the_queue(project):
    run_id = project.ready_run(1)
    project.grant(run_id)
    times = {(run_id, f"grant-{run_id}"): "2026-08-11T11:00:00Z",
             (run_id, "another-grant"): "2026-08-11T10:00:00Z",
             ("another-run", f"grant-{run_id}"): "2026-08-11T09:00:00Z"}
    view = task_preparation.QueueView(
        preauthorized=lambda run, grant: times.get((run, grant.authorization_id)))
    assert project.row(run_id, view)["grant"]["preauthorized_at"] == "2026-08-11T11:00:00Z"
    assert project.row(run_id)["grant"]["preauthorized_at"] is None


def test_a_queue_entry_is_shown_with_exactly_its_four_facts(project):
    run_id = project.ready_run(1)
    line = {"state": "waiting", "position": 2, "reason_code": "seed_blocked",
            "state_since": "2026-08-11T11:00:00Z", "internal": "left out"}
    row = project.row(run_id, task_preparation.QueueView(entries={run_id: line}))
    assert row["queue"] == {"position": 2, "state": "waiting", "reason_code": "seed_blocked",
                            "state_since": "2026-08-11T11:00:00Z"}


def test_a_run_of_another_task_and_a_run_that_follows_no_task_are_not_listed(project):
    mine = project.open_run(1)
    other = project.open_run(2, task_id="task-other")
    assert [row["run_id"] for row in project.read()["runs"]] == [mine]
    assert other not in [row["run_id"] for row in project.read()["runs"]]


def test_a_run_that_follows_no_workflow_is_listed_with_no_cycle_and_nothing_missing(project):
    run_id = f"{TASK}-r1"
    config = {"cycle": {"id": run_id}, "instances": [], "task": {"id": TASK, "work_scope": TASK}}
    project.store.create_run(RunEnvelope(
        run_id, run_id, NOW, snapshot_digest(config), mode="confirm"), config)
    row = project.row(run_id)
    assert (row["workflow_id"], row["revision"], row["stage"]) == (None, None, "ready_to_preview")
    assert row["missing"] == {"instructions": [], "inputs": []}


# --- the next number counts every run of the task, readable or not ------------------------------


def test_next_run_number_counts_unreadable_runs_of_the_task(project):
    kept = [project.open_run(1), project.open_run(3)]
    broken = project.store.runs_root / f"{TASK}-r7"
    broken.mkdir(parents=True)
    (broken / "run.json").write_text("not json", encoding="utf-8")
    (project.store.runs_root / "task-other-r9").mkdir()
    (project.store.runs_root / f"{TASK}-r8x").mkdir()
    (project.store.runs_root / f"{TASK}-r5-r6").mkdir()
    payload = project.read()
    assert [row["run_id"] for row in payload["runs"]] == kept
    assert payload["next_run_number"] == 8


def test_next_run_number_is_one_for_a_task_with_no_run(project):
    assert project.read()["next_run_number"] == 1 and project.read()["runs"] == []


# --- refusals and the read's promise --------------------------------------------------------------


def test_preparation_of_an_unknown_task_is_service_refused_with_its_id(project):
    with pytest.raises(ApiRefusal) as refused:
        task_preparation.read_preparation(project.tasks, project.store, "task-nope")
    assert refused.value.code == "service_refused"
    assert dict(refused.value.detail) == {"task_id": "task-nope"}


def test_reading_the_preparation_writes_nothing(project):
    run_id = project.ready_run(1)
    project.grant(run_id)
    before = durable_digest(project.root)
    project.read()
    assert durable_digest(project.root) == before


# --- missing_bindings: the rules of bind_inputs that answer instead of raising ------------------


def plan_of(document):
    template = GraphTemplate.from_dict(
        {**document, "template_id": "template-plan", "revision": 1})
    config = config_for("run-plan", "task-plan", "template-plan")
    return materialize(template, binding_of(template), config, graph_id="graph-plan",
                       run_id="run-plan", created_at=NOW)


def document(ref, **more):
    return ArtifactDocument(artifact_id=f"doc-{ref}", run_id="run-plan", artifact_ref=ref,
                            created_at=NOW, media_type="text/markdown", content=ref, **more)


def reading_an_input_twice(document):
    """The template with its dispatch step naming its first input a second time."""
    def repeated(node):
        refs = node["arguments"]["artifact_refs"]
        return {**node, "arguments": {**node["arguments"], "artifact_refs": [*refs, refs[0]]}}
    return {**document, "nodes": [repeated(node) if node.get("capability") == "dispatch" else node
                                  for node in document["nodes"]]}


def corpus_plans():
    """Every shipped template, every form of the corpus that becomes a plan, and one shipped
    template altered so that its dispatch step reads an input twice."""
    found = {path.stem: plan_of({**load_template(path.stem).as_dict()})
             for path in sorted(TEMPLATE_DIR.glob("*.json"))}
    found["desk-standard-reading-an-input-twice"] = plan_of(
        reading_an_input_twice(load_template("desk-standard").as_dict()))
    corpus = [accepted(raw) for raw in STUDIO_CORPUS.values()]
    corpus += [compile_flow(flow) for flow in CANONICAL.values()]
    for number, raw in enumerate(corpus):
        try:
            found[f"form-{number}"] = plan_of(raw)
        except ContractError:
            continue
    return found


def _bindable(plan):
    """Whether `bind_inputs` judges the plan itself acceptable, whatever is published.

    Three of its refusals are about the plan and no document's business: a step that is neither
    a dispatch nor a review, a review that names no valid result document, and a step that reads
    one input twice (or in no valid form).
    """
    try:
        for node in executable_nodes(plan):
            _unique_ids("input references", required_input_refs(node.capability, node.arguments))
            if node.capability == "review":
                _id("result_artifact_ref", node.arguments.get("result_artifact_ref"))
    except ContractError:
        return False
    return True


def instructions_of(plan):
    return [node.arguments["instruction_ref"] for node in plan.nodes
            if node.capability == "dispatch"]


def reads_of(plan):
    """Every document any step of the plan reads: its instructions and its inputs, the ones a
    review of the plan produces for a later step included."""
    inputs = (ref for node in plan.nodes if node.capability is not None
              for ref in required_input_refs(node.capability, node.arguments))
    return sorted({*instructions_of(plan), *inputs})


def published_states(plan):
    """Nothing, the brief alone, what a run is handed, every document any step reads, and each of
    those last two sets but one document."""
    everything = ["artifact-brief", "artifact-materials", *instructions_of(plan)]
    reads = reads_of(plan)
    states = [[], ["artifact-brief"], everything, reads]
    for whole in (everything, reads):
        states += [[ref for ref in whole if ref != gone] for gone in whole]
    return states


def accepts(plan, values):
    try:
        bind_inputs(plan, values)
    except ContractError:
        return False
    return True


ALL_PLANS = corpus_plans()
PLANS = {name: plan for name, plan in ALL_PLANS.items() if _bindable(plan)}
SET_ASIDE = {name: plan for name, plan in ALL_PLANS.items() if name not in PLANS}


@pytest.mark.parametrize("name", sorted(PLANS))
def test_missing_bindings_is_empty_exactly_when_bind_inputs_accepts(name):
    plan = PLANS[name]
    for refs in published_states(plan):
        values = tuple(document(ref) for ref in refs)
        missing = task_preparation.missing_bindings(plan, values)
        assert (not missing["instructions"] and not missing["inputs"]) == accepts(plan, values), (
            name, refs, missing)


@pytest.mark.parametrize("name", sorted(SET_ASIDE))
def test_a_plan_left_out_of_that_claim_is_refused_by_bind_inputs_with_every_document_published(
        name):
    plan = SET_ASIDE[name]
    assert not accepts(plan, tuple(document(ref) for ref in reads_of(plan)))


@pytest.mark.parametrize("name", ["dalio-v1", "desk-standard-reading-an-input-twice"])
def test_a_plan_bind_inputs_refuses_however_it_is_published_can_read_as_missing_nothing(name):
    """Why those plans are left out: a review naming no result document (`dalio-v1`) and a step
    reading one input twice are the plan's fault, and `missing_bindings` names no document for
    either, so with every document published it says nothing is missing and `bind_inputs`
    still refuses."""
    plan = SET_ASIDE[name]
    values = tuple(document(ref) for ref in reads_of(plan))
    assert task_preparation.missing_bindings(plan, values) == {"instructions": [], "inputs": []}
    assert not accepts(plan, values)


def test_the_corpus_reaches_the_shipped_cycles_and_at_least_four_forms():
    assert {"desk-standard", "desk-short", "desk-starter-docs", "dalio-v5"} <= set(PLANS)
    assert len([name for name in PLANS if name.startswith("form-")]) >= 4


def test_missing_bindings_names_each_absent_instruction_and_input_in_plan_order():
    plan = PLANS["desk-standard"]
    assert task_preparation.missing_bindings(plan, ()) == {
        "instructions": [{"node_id": "do", "instruction_ref": "instruction-do"}],
        "inputs": ["artifact-brief", "artifact-materials"]}
    brief = (document("artifact-brief"),)
    assert task_preparation.missing_bindings(plan, brief)["inputs"] == ["artifact-materials"]


def test_an_input_a_review_of_the_plan_produces_is_not_missing():
    plan = PLANS["desk-standard"]
    assert "artifact-analyst" not in task_preparation.missing_bindings(plan, ())["inputs"]


def test_an_instruction_an_agent_wrote_is_not_the_owners_document():
    plan = PLANS["desk-standard"]
    values = (document("artifact-brief"), document("artifact-materials"),
              document("instruction-do", source_action_id="action-1"))
    assert task_preparation.missing_bindings(plan, values)["instructions"] == [
        {"node_id": "do", "instruction_ref": "instruction-do"}]


def test_the_latest_version_of_a_document_is_the_one_that_counts():
    plan = PLANS["desk-short"]
    values = (document("instruction-do"), document("artifact-brief"),
              document("artifact-materials"),
              document("instruction-do", source_action_id="action-2"))
    assert task_preparation.missing_bindings(plan, values)["instructions"] == [
        {"node_id": "do", "instruction_ref": "instruction-do"}]


def test_a_plan_with_no_step_that_carries_out_work_misses_nothing():
    plan = GraphDefinition("graph-gate", "run-plan", NOW,
                           nodes=(GraphNode("gate", "gate", "Approve", gate_id="gate-id"),),
                           edges=())
    assert task_preparation.missing_bindings(plan, ()) == {"instructions": [], "inputs": []}


# --- the route (spec 6.4.2, route-canon 2a) --------------------------------------------------


def door(project):
    """The command API over the project's own stores; events collects the frames it publishes."""
    events = []
    api = CommandApi(project.store, project.policy.registry,
                     session=CommandSession(PORT, TOKEN), budget=project.policy.budget,
                     clock=lambda: NOW, ids=lambda kind: f"{kind}-1", publish_run=events.append,
                     tasks=project.tasks)
    return api, events


def preparation_path(task_id=TASK):
    return f"/command/tasks/{task_id}/preparation"


def test_the_preparation_route_answers_what_the_read_answers(project):
    project.ready_run(1)
    project.open_run(2)
    api, _events = door(project)
    answer = api.handle("GET", preparation_path(), get_headers())
    assert answer.status == 200
    assert answer.payload == project.read()
    assert [row["stage"] for row in answer.payload["runs"]] == [
        "ready_to_preview", "documents_missing"]


def test_an_unknown_task_on_the_route_is_409_service_refused_naming_it(project):
    api, _events = door(project)
    refused = api.handle("GET", preparation_path("task-nope"), get_headers())
    assert (refused.status, refused.payload["error"]["code"]) == (409, "service_refused")
    assert refused.payload["error"]["detail"] == {"task_id": "task-nope"}


def test_the_preparation_route_takes_no_other_verb(project):
    api, _events = door(project)
    refused = post(api, preparation_path(), {})
    assert (refused.status, refused.payload["error"]["code"]) == (405, "method_not_allowed")


def test_the_preparation_route_writes_nothing_and_publishes_no_frame(project):
    project.ready_run(1)
    api, events = door(project)
    before = durable_digest(project.root)
    assert api.handle("GET", preparation_path(), get_headers()).status == 200
    assert events == [] and durable_digest(project.root) == before


@pytest.mark.parametrize("path", [
    f"/command/tasks/{TASK}/preparation/", f"/command/tasks/{TASK}/preparation/x",
    f"/command/tasks/{TASK}/prepare", f"/command/tasks//preparation",
    f"/command/tasks/{'t' * (MAX_TASK_ID + 1)}/preparation", f"/command/tasks/{TASK}/seeds"])
def test_a_task_id_past_its_bound_and_a_tail_beyond_preparation_are_no_route(project, path):
    api, _events = door(project)
    refused = api.handle("GET", path, get_headers())
    assert (refused.status, refused.payload["error"]["code"]) == (404, "route_not_found")
