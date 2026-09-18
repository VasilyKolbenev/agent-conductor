"""A malformed frozen task binding refuses the from-template road as CORRUPT.

Seam: ``POST /command/runs/<run_id>/graph/from-template`` over a run whose
frozen configuration carries a ``task`` key the binding contract refuses.
`materialize` reads that key through `frozen_config_task`, and the
`ContractError` it raises is about already-frozen bytes and never about the
request in hand -- so the boundary judges the binding first, through
`plan_admission._task`, the way `_bindings` already judges an invalid instance
binding: `CorruptRun`, answered ``run_corrupt``, with the journal untouched.

The controls run the same road with the same template, so the claim isolates
"malformed" from "any task key at all". And the road's other promise is held
here on the filesystem: a task-less plan standing in the journal and a new task
given the item the retired encoding would have collided with are two
directories, the legacy bytes are untouched, and the legacy plan still retries.

Mutation: skip `_task` in `_materialize_graph` -> the malformed binding answers
422 contract_invalid -> red; the controls stay green.
"""
from __future__ import annotations

import os

from conductor.command.adapters import AdapterRegistry
from conductor.command.adapters.harness_workspace import HarnessWorkspace
from conductor.command.api_contracts import ERROR_STATUS
from conductor.command.graph_template import GraphTemplate, RunBinding, materialize
from conductor.command.http_api import CommandApi, PRODUCT_COMMAND_BUDGET
from conductor.command.http_transport import CommandSession
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.template_store import TemplateStore

from tests.test_command_http_api import NOW, PORT, RUN_ID, TOKEN, ids, post
from tests.test_command_run_routes import journal_of
from tests.test_command_run_store import CONFIG, a_run
from tests.test_command_schema_doubles import DeepPlanAdapter
from tests.test_command_template_routes import (
    FROM_TEMPLATE_PATH,
    code_of,
    contracts,
)
from tests.test_command_workflow_draft import a_document

TEMPLATE = "flow-task"
ROLE = "role-implementer"
#: The instance `CONFIG` binds to claude-code, which the double registers.
INSTANCE = "claude-dev"


def a_template(work_item_id: str = "work-001") -> GraphTemplate:
    document = a_document()
    document["nodes"][1]["arguments"]["work_item_id"] = work_item_id
    return GraphTemplate.from_dict(
        {**document, "template_id": TEMPLATE, "revision": 1})


def api_over(tmp_path, config: dict, template: GraphTemplate):
    """One API over a run already frozen with `config`, holding `template`."""
    store = RunStore(tmp_path)
    store.create_run(a_run(
        run_id=RUN_ID, mode="confirm", config_digest=snapshot_digest(config)),
        config)
    templates = TemplateStore(tmp_path)
    templates.save(template)
    events = []
    subject = CommandApi(
        store, AdapterRegistry([DeepPlanAdapter()]),
        session=CommandSession(PORT, TOKEN), budget=PRODUCT_COMMAND_BUDGET,
        clock=lambda: NOW, ids=ids(), publish_run=events.append,
        providers=contracts(), templates=templates)
    return subject, store, events


def from_template() -> dict:
    return {"graph_id": "graph-from-template-001", "template_id": TEMPLATE,
            "revision": 1, "assignments": {ROLE: INSTANCE}}


def test_a_malformed_frozen_task_binding_is_run_corrupt_and_writes_nothing(
        tmp_path):
    """Half a binding is frozen bytes, not a request: the word is `run_corrupt`.

    Mutation: skip `_task` in `_materialize_graph` -> `materialize`'s
    `ContractError` reaches the wire as 422 contract_invalid -> red.
    """
    subject, store, events = api_over(
        tmp_path, {**CONFIG, "task": {"id": "t1"}}, a_template())
    before = journal_of(store)

    refused = post(subject, FROM_TEMPLATE_PATH, from_template())
    assert (refused.status, code_of(refused)) == (
        ERROR_STATUS["run_corrupt"], "run_corrupt")
    assert journal_of(store) == before and events == []


def test_a_well_formed_frozen_binding_files_the_plans_work_under_its_scope(
        tmp_path):
    """Control: the same road with a binding the contract admits is a 201 whose
    dispatching step keeps the template's item and carries the frozen scope."""
    subject, _store, events = api_over(
        tmp_path, {**CONFIG, "task": {"id": "t1", "work_scope": "scope-x"}},
        a_template())

    created = post(subject, FROM_TEMPLATE_PATH, from_template())
    assert created.status == 201, created.payload
    step = next(node for node in created.payload["nodes"]
                if node["node_id"] == "do")
    assert step["arguments"]["work_item_id"] == "work-001"
    assert step["arguments"]["work_scope"] == "scope-x"
    assert events == [RUN_ID]


def test_a_task_less_plan_spelled_like_the_retired_task_shape_is_its_own_work(
        tmp_path):
    """No spelling is reserved any more: task work lives under a container no
    item can name, so a task-less item may be anything the grammar admits --
    including what the retired encoding called a task's item -- and it is
    filed exactly as the template wrote it, with no scope."""
    subject, _store, events = api_over(tmp_path, CONFIG, a_template("t1.a.work-001"))

    created = post(subject, FROM_TEMPLATE_PATH, from_template())
    assert created.status == 201, created.payload
    step = next(node for node in created.payload["nodes"] if node["node_id"] == "do")
    assert step["arguments"]["work_item_id"] == "t1.a.work-001"
    assert "work_scope" not in step["arguments"]
    assert events == [RUN_ID]


def test_a_standing_legacy_run_and_a_new_task_never_share_a_directory(tmp_path):
    """R1 of the 2026-09-18 review, as it asked to be witnessed.

    A task-less plan standing in the journal with the item ``t1.a.b`` -- what
    the retired encoding gave task ``a``'s item ``b`` -- and work already on disk
    under it. Then a new task ``a`` in the SAME project, given item ``b``. The
    first answer put both in one directory. Now: two directories by
    `os.path.samefile`, the legacy bytes untouched after the task's directory is
    made, and the legacy plan's exact retry still answers the plan that stands.

    Mutation: `work_parts` files a task's item beside history again -> red.
    """
    subject, store, events = api_over(tmp_path, CONFIG, a_template("t1.a.b"))
    legacy = materialize(
        a_template("t1.a.b"), RunBinding.from_dict({"assignments": {ROLE: INSTANCE}}),
        CONFIG, graph_id="graph-from-template-001", run_id=RUN_ID, created_at=NOW)
    store.append(legacy)
    space = HarnessWorkspace.at(tmp_path, home_dir="home", marker_dir="markers")
    old = space.work_dir("t1.a.b")
    (old / "result.txt").write_bytes(b"legacy work, written before tasks existed")

    task_config = {**CONFIG, "task": {"id": "a", "work_scope": "a"}}
    store.create_run(a_run(run_id="run-task-a", mode="confirm",
                           config_digest=snapshot_digest(task_config)), task_config)
    TemplateStore(tmp_path).save(GraphTemplate.from_dict(
        {**a_template("b").as_dict(), "template_id": "flow-b"}))
    created = post(subject, "/command/runs/run-task-a/graph/from-template",
                   {**from_template(), "graph_id": "graph-task-a", "template_id": "flow-b"})
    assert created.status == 201, created.payload
    step = next(node for node in created.payload["nodes"] if node["node_id"] == "do")
    new = space.work_dir(step["arguments"]["work_item_id"], step["arguments"]["work_scope"])

    assert not os.path.samefile(old, new)
    assert new == tmp_path.resolve() / "work" / "_tasks" / "a" / "b"
    assert (old / "result.txt").read_bytes() == b"legacy work, written before tasks existed"
    again = post(subject, FROM_TEMPLATE_PATH, from_template())
    assert again.status == 200, again.payload
    assert again.payload == legacy.as_dict()


def test_the_longest_scope_and_the_longest_item_are_two_components_and_admitted(
        tmp_path):
    """The retired encoding summed scope and item into one 128-character id and
    refused a pair that overflowed it. Two components have no sum to overflow:
    a 64-character scope and a 64-character item are each within bounds."""
    scope = "s" * 64
    subject, _store, _events = api_over(
        tmp_path, {**CONFIG, "task": {"id": scope, "work_scope": scope}},
        a_template("w" * 64))

    created = post(subject, FROM_TEMPLATE_PATH, from_template())
    assert created.status == 201, created.payload
    step = next(node for node in created.payload["nodes"] if node["node_id"] == "do")
    assert (step["arguments"]["work_item_id"], step["arguments"]["work_scope"]) == (
        "w" * 64, scope)
