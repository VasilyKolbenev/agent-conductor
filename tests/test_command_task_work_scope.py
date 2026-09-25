"""Where a task's work lives, judged on the FILESYSTEM and at every door.

A task's work item lives at ``work/_tasks/<scope>/<item>``; a task-less item at
``work/<item>``, exactly where it always has. The first answer to "two tasks from
one template must not share a directory" spelled the pair into one id,
``t<len>.<scope>.<item>`` -- injective between tasks, and still a LEGAL legacy id:
a task-less plan frozen before tasks existed could already carry ``t1.a.b``, and
on a case-insensitive filesystem ``T1.a.b`` named the same directory as task
``a``'s item ``b`` (the 2026-09-18 bounded review, R1 and R2). No spelling inside
the id grammar can be apart from every id that grammar admits, so the task now
travels BESIDE the item as ``work_scope`` and the workspace puts it under a
container whose name no id can begin with.

Every directory claim here is decided by `os.path.samefile` on directories the
workspace really created, never by comparing the strings a helper returned --
that is how the first answer passed three reviews while two tasks shared a
directory. The admission half is `plan_admission.work_scope_admits`: a step
writes into its own run's task, or into none, at the template doors and at the
raw graph door alike.
"""
from __future__ import annotations

import os

import pytest

from conductor.command.adapters.deep_commands import DeepDispatchArgs, DeepReviewArgs
from conductor.command.adapters.deep_contracts import DeepContractError
from conductor.command.adapters.harness_workspace import (
    TASKS_DIR,
    WORK_DIR,
    HarnessWorkspace,
    work_parts,
    work_route,
)
from conductor.command.contracts import ContractError, _id
from conductor.command.graph_definition import GraphNode
from conductor.command.graph_template import (
    TEMPLATE_DIR,
    GraphTemplate,
    RunBinding,
    load_template,
    materialize,
)
from conductor.command.graph_template_document import TemplateError
from conductor.command.plan_admission import work_scope_admits
from conductor.command.task_contracts import TaskBinding

from tests.test_command_graph_template import NOW, SOLO
from tests.test_command_workflow_draft import a_document

ROLE = "role-implementer"
STEP = "do"


def a_template(work_item_id: str = "work-001", **arguments) -> GraphTemplate:
    document = a_document()
    document["nodes"][1]["arguments"] = {
        **document["nodes"][1]["arguments"], "work_item_id": work_item_id, **arguments}
    return GraphTemplate.from_dict({**document, "template_id": "flow-task", "revision": 1})


def bound_to(task_id: str) -> dict:
    """The frozen configuration of a run that binds to one task."""
    return {**SOLO, "task": {"id": task_id, "work_scope": task_id}}


def plan(config: dict, template: GraphTemplate | None = None):
    return materialize(
        template if template is not None else a_template(),
        RunBinding.from_dict({"assignments": {ROLE: "solo"}}), config,
        graph_id="graph-scope", run_id="run-scope", created_at=NOW)


def arguments_of(definition) -> dict:
    """The step's payload in its canonical, JSON-shaped form."""
    return next(node for node in definition.nodes if node.node_id == STEP).payload()


def a_workspace(tmp_path) -> HarnessWorkspace:
    return HarnessWorkspace.at(tmp_path, home_dir="home", marker_dir="markers")


def directory_of(space: HarnessWorkspace, arguments: dict):
    """The directory an adapter would really stand in for these arguments."""
    return space.work_dir(arguments["work_item_id"], arguments.get("work_scope"))


# -- what materialize writes ------------------------------------------------------


def test_a_task_bound_plan_keeps_the_item_and_carries_the_task_beside_it():
    """The template's item is left exactly as written; the task travels as its
    own field, so there is no composite to be ambiguous about.

    Mutation: materialize stops adding `work_scope` -> red.
    """
    assert arguments_of(plan(bound_to("a"))) == {
        **arguments_of(plan(SOLO)), "work_scope": "a"}
    assert arguments_of(plan(bound_to("a")))["work_item_id"] == "work-001"


def test_a_task_less_plan_is_the_templates_payload_byte_for_byte():
    """No standing plan's directory may move, so a run with no task gets no
    `work_scope` key at all -- absent, not null."""
    assert "work_scope" not in arguments_of(plan(SOLO))
    assert arguments_of(plan(SOLO)) == dict(a_template().steps()[1].payload())


# -- where it lands, on this filesystem ---------------------------------------------


def test_two_tasks_from_one_template_are_two_directories_on_disk(tmp_path):
    """The promise T1 made, measured: same template, two tasks, two directories.

    Mutation: the workspace ignores `work_scope` -> one directory -> red.
    """
    space = a_workspace(tmp_path)
    first = directory_of(space, arguments_of(plan(bound_to("task-a"))))
    second = directory_of(space, arguments_of(plan(bound_to("task-b"))))
    assert not os.path.samefile(first, second)
    assert first == tmp_path.resolve() / WORK_DIR / TASKS_DIR / "task-a" / "work-001"


@pytest.mark.parametrize("legacy", [
    "t1.a.b",      # R1: what the retired encoding gave task `a`'s item `b`
    "T1.a.b",      # R2: the same name, one letter case away
    "t1.A.B", "tasks", "Tasks", "a", "b", "a.b",
])
def test_no_task_less_item_shares_a_directory_with_any_task(tmp_path, legacy):
    """R1 and R2 of the 2026-09-18 review, decided by `samefile` on this disk.

    Task `a`'s item `b`, and task `A`'s item `b` for the case-insensitive side,
    against every task-less item the review named and the names nearest to the
    container. Where the filesystem folds case, a pair of these WOULD be one
    directory if the task's work sat beside history in `work/`.

    Mutation: `work_parts` files a task's item as `work/<scope>.<item>` -> the
    `a.b` row is one directory with task `a`'s item `b` -> red.
    """
    space = a_workspace(tmp_path)
    old = space.work_dir(legacy)
    for scope in ("a", "A"):
        task = space.work_dir("b", scope)
        assert not os.path.samefile(old, task), (legacy, scope)


@pytest.mark.parametrize("name", [TASKS_DIR, TASKS_DIR.upper(), "_Tasks", "_"])
def test_the_task_container_is_a_name_no_work_item_can_have(name):
    """What makes the separation STRUCTURAL rather than a spelling: the id
    grammar every work item passes cannot begin with `_`, in any case, so no
    plan -- frozen before tasks or written since -- can name the container.

    Mutation: the container is named `tasks` -> the grammar admits it -> red.
    """
    with pytest.raises(ContractError):
        _id("work_item_id", name)
    with pytest.raises(DeepContractError):
        DeepDispatchArgs(name, "instr-001", "implement", [], "normal")


def test_two_pairs_a_bare_dot_would_spell_alike_are_two_directories(tmp_path):
    """The collision the first review found, still closed: scope `a` with item
    `b.c` and scope `a.b` with item `c`. Two components, so two directories."""
    space = a_workspace(tmp_path)
    assert not os.path.samefile(space.work_dir("b.c", "a"), space.work_dir("c", "a.b"))


def test_the_route_an_argv_names_is_the_directory_the_workspace_made(tmp_path):
    """One definition of the place, read two ways: the relative route a child is
    told and the directory it stands in cannot disagree."""
    space = a_workspace(tmp_path)
    for scope in (None, "task-a"):
        made = space.work_dir("work-001", scope)
        assert made == tmp_path.resolve().joinpath(*work_parts("work-001", scope))
        assert made.relative_to(tmp_path.resolve()).as_posix() == work_route(
            "work-001", scope)


# -- the argument contract ------------------------------------------------------------


@pytest.mark.parametrize("kind", ["dispatch", "review"])
def test_an_absent_scope_is_absent_in_the_payload_and_a_present_one_round_trips(kind):
    """Additive and omittable: no frozen payload moves, and a carried scope is
    carried exactly."""
    base = ({"work_item_id": "work-001", "instruction_ref": "instr-001",
             "profile": "implement", "artifact_refs": [],
             "output_limit_profile": "normal"} if kind == "dispatch" else
            {"work_item_id": "work-001", "target_artifact_refs": ["input-ref"],
             "review_profile": "quality"})
    kind_of = DeepDispatchArgs if kind == "dispatch" else DeepReviewArgs
    assert "work_scope" not in kind_of.from_dict(base).as_dict()
    assert kind_of.from_dict(base).task_scope is None
    scoped = kind_of.from_dict({**base, "work_scope": "task-a"})
    assert scoped.as_dict()["work_scope"] == "task-a" and scoped.task_scope == "task-a"


@pytest.mark.parametrize("kind", ["dispatch", "review"])
@pytest.mark.parametrize("scope", [None, "", "has space", "_tasks", "a/b", 7])
def test_a_scope_that_is_not_an_id_is_refused_by_the_contract(scope, kind):
    """An explicit null chose a value and is refused like any other wrong one --
    by the review contract as by the dispatch one, since a review's child stands
    in the directory its scope names too."""
    base = ({"work_item_id": "work-001", "instruction_ref": "instr-001",
             "profile": "implement", "artifact_refs": [],
             "output_limit_profile": "normal"} if kind == "dispatch" else
            {"work_item_id": "work-001", "target_artifact_refs": ["input-ref"],
             "review_profile": "quality"})
    kind_of = DeepDispatchArgs if kind == "dispatch" else DeepReviewArgs
    with pytest.raises(DeepContractError):
        kind_of.from_dict({**base, "work_scope": scope})


# -- who may write where: the admission rule ---------------------------------------------


def test_a_plan_agreeing_with_its_binding_is_admitted_either_way():
    """Controls on both sides: a task plan naming its own task, a task-less plan
    naming none."""
    work_scope_admits(plan(bound_to("a")).nodes, TaskBinding(task_id="a", work_scope="a"))
    work_scope_admits(plan(SOLO).nodes, None)


def test_a_task_less_run_given_a_step_that_names_a_task_is_refused_naming_it():
    """A template may write `work_scope` into a step's arguments -- the capability
    schema admits the key -- and a task-less run would then write into that
    task's directory. `materialize` leaves a task-less payload untouched, so
    it is the door that must say no.

    Mutation: `work_scope_admits` returns early for a task-less run -> red.
    """
    borrowed = plan(SOLO, a_template(work_scope="victim-task"))
    with pytest.raises(TemplateError) as refused:
        work_scope_admits(borrowed.nodes, None)
    assert "victim-task" in str(refused.value) and repr(STEP) in str(refused.value)


def test_a_task_run_whose_step_names_another_task_or_none_is_refused():
    """Another task's scope is another task's directory; no scope files the work
    among task-less history. Both are refused against the frozen binding."""
    binding = TaskBinding(task_id="a", work_scope="a")
    with pytest.raises(TemplateError, match="'b'"):
        work_scope_admits(plan(bound_to("b")).nodes, binding)
    with pytest.raises(TemplateError, match="None"):
        work_scope_admits(plan(SOLO).nodes, binding)


def _step(node_id: str, capability: str, **scope) -> GraphNode:
    arguments = ({"work_item_id": "work-001", "instruction_ref": "instr-001",
                  "profile": "implement", "artifact_refs": [],
                  "output_limit_profile": "normal"} if capability == "dispatch" else
                 {"work_item_id": "work-001", "target_artifact_refs": ["input-ref"],
                  "review_profile": "quality"})
    return GraphNode(node_id=node_id, kind="task", title=node_id, instance_id="solo",
                     capability=capability, arguments={**arguments, **scope})


@pytest.mark.parametrize("task, own, foreign", [
    pytest.param(None, {}, {"work_scope": "victim-task"}, id="task-less"),
    pytest.param(TaskBinding(task_id="a", work_scope="a"), {"work_scope": "a"}, {},
                 id="task-a")])
def test_the_plan_door_judges_every_work_bearing_step_not_only_the_first_dispatch(
        task, own, foreign):
    """A plan's SECOND work-bearing step, a review, is the one that writes
    elsewhere; the first, a dispatch, agrees. The door names the review step.

    Mutations: the door judges only the first work-bearing step, or only
    dispatch steps -> the plan is admitted -> red.
    """
    plan_nodes = (_step("first", "dispatch", **own), _step("second", "review", **foreign))
    with pytest.raises(TemplateError) as refused:
        work_scope_admits(plan_nodes, task)
    assert repr("second") in str(refused.value)


@pytest.mark.parametrize("shipped", sorted(path.stem for path in TEMPLATE_DIR.glob("*.json")))
def test_every_work_bearing_step_of_a_shipped_cycle_carries_the_runs_task(shipped):
    """Every cycle this build ships, opened under a task, files EVERY step that
    carries a work item -- review steps as well as the dispatch -- under that
    task, and the plan door admits it. Otherwise a task could not run the
    product's own cycle at all.

    Mutation: materialize scopes only dispatch steps -> the review steps carry
    no scope -> red.
    """
    template = load_template(shipped)
    roles = {step.role_id for step in template.steps() if step.role_id}
    verifier_roles = {step.verifier_role_id for step in template.steps() if step.verifier_role_id}
    roles |= verifier_roles
    config = bound_to("a")
    if verifier_roles:
        config = {**config, "instances": [*config["instances"],
            {**config["instances"][0], "id": "checker"}]}
    definition = materialize(
        template, RunBinding.from_dict({"assignments": {
            role: "checker" if role in verifier_roles else "solo" for role in roles}}),
        config, graph_id="graph-shipped", run_id="run-shipped", created_at=NOW)
    working = [node for node in definition.nodes if "work_item_id" in node.payload()]
    assert working, shipped
    assert {node.node_id: node.payload().get("work_scope") for node in working} == {
        node.node_id: "a" for node in working}
    work_scope_admits(definition.nodes, TaskBinding(task_id="a", work_scope="a"))


def test_the_shipped_cycles_carry_review_steps_the_scope_witness_reaches():
    """The witness above covers review steps only if some shipped cycle has one."""
    capabilities = {node.capability for path in TEMPLATE_DIR.glob("*.json")
                    for node in load_template(path.stem).steps()}
    assert {"dispatch", "review"} <= capabilities


def test_a_task_bound_run_overrides_a_scope_the_template_wrote():
    """Under a task the template cannot choose: materialize writes the run's own
    scope over whatever the arguments carried, so the door admits it."""
    overridden = plan(bound_to("a"), a_template(work_scope="victim-task"))
    assert arguments_of(overridden)["work_scope"] == "a"
    work_scope_admits(overridden.nodes, TaskBinding(task_id="a", work_scope="a"))


# -- the raw graph door, which the first answer never asked ---------------------------


def _graph_naming(scope: str | None) -> dict:
    from tests.test_command_graph_route import graph_body
    body = graph_body()
    if scope is not None:
        body["nodes"][2]["arguments"]["work_scope"] = scope
    return body


def test_the_raw_graph_door_refuses_a_task_less_run_a_step_that_names_a_task(tmp_path):
    """`POST /command/runs/<id>/graph` takes a whole plan from the caller. The
    retired shape rule was asked at the two template doors only, so this door
    would file a task-less run's work in any task's directory it named.

    Mutation: drop `work_scope_admits` from `_write_graph` -> 201 -> red.
    """
    from conductor.command.api_contracts import ERROR_STATUS
    from tests.test_command_graph_route import GRAPH_PATH, graph_api
    from tests.test_command_http_api import post
    from tests.test_command_run_routes import journal_of
    subject, store, events = graph_api(tmp_path)
    before = journal_of(store)

    refused = post(subject, GRAPH_PATH, _graph_naming("victim-task"))
    assert refused.status == ERROR_STATUS["contract_invalid"], refused.payload
    assert journal_of(store) == before and events == []
    assert post(subject, GRAPH_PATH, _graph_naming(None)).status == 201


@pytest.mark.parametrize("scope, admitted", [("a", True), ("b", False), (None, False)])
def test_the_raw_graph_door_holds_a_task_run_to_its_own_scope(tmp_path, scope, admitted):
    """Its own task is admitted; another task's scope, or none, is refused --
    the frozen binding is the one authority on where this run may write."""
    from conductor.command.api_contracts import ERROR_STATUS
    from conductor.command.run_store import snapshot_digest
    from tests.test_command_graph_route import graph_api
    from tests.test_command_http_api import CONFIG, post
    from tests.test_command_run_store import a_run
    subject, store, _events = graph_api(tmp_path)
    config = {**CONFIG, "task": {"id": "a", "work_scope": "a"}}
    store.create_run(a_run(run_id="run-task-a", mode="confirm",
                           config_digest=snapshot_digest(config)), config)

    answer = post(subject, "/command/runs/run-task-a/graph", _graph_naming(scope))
    expected = 201 if admitted else ERROR_STATUS["contract_invalid"]
    assert answer.status == expected, answer.payload
