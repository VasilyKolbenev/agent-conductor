"""One cycle, written once in roles, run on two different deployments.

This is the scenario the whole slice exists for, driven through the product's
own doors and no shortcuts: the shipped Dalio template is published, two runs
whose frozen configurations bind DIFFERENT instances each materialize it, and
the step that acts is then proposed against through the ordinary proposal
route -- with the payload the plan itself carries.

The revision is the DEFAULT one, `dalio-v2`, and it is named once at
`DEFAULT_TEMPLATE`. Revision 1 is the historical witness: runs materialized from
it, the ALPHA-3 fixture carries its shape, and a replay must reproduce it -- but
its review steps name nowhere to publish, so it is not what a new run is given.
This file is route materialization, so it materializes the default.

Nothing here builds a `GraphDefinition`. Nothing here names a provider. What
proves the role abstraction is not that the two records look similar but that
they are the SAME work, told apart only by who does it: one topology, one set
of digests-that-differ, and two journals that each answer for their own run.
"""
from __future__ import annotations

import json

from conductor.command.adapters import AdapterRegistry
from conductor.command.graph_definition import GraphDefinition
from conductor.command.graph_dalio import is_dalio_template
from conductor.command.graph_template import load_template
from conductor.command.http_api import CommandApi, PRODUCT_COMMAND_BUDGET
from conductor.command.http_transport import CommandSession
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.template_store import TemplateStore

from tests.test_command_http_api import (
    NOW,
    PORT,
    TOKEN,
    ids,
    post,
    proposal_body,
)
from tests.test_command_run_store import a_run
from tests.test_command_schema_doubles import DeepPlanAdapter
from tests.test_command_template_routes import TEMPLATES_PATH, contracts

#: Two deployments of one cycle. The first spreads four roles over two
#: instances; the second gives all four to one, which is what a small install
#: looks like. The adapters behind them are the configuration's business and
#: appear in no plan.
SPREAD = {
    "cycle": {"id": "default-orbit", "phases": ["goal", "detect", "design"]},
    "instances": [
        {"id": "claude-dev", "adapter": "claude-code"},
        {"id": "codex-review", "adapter": "codex"},
    ],
}
SOLO = {
    "cycle": {"id": "default-orbit", "phases": ["goal", "detect", "design"]},
    "instances": [{"id": "solo-node", "adapter": "claude-code"}],
}


def deployment(tmp_path, run_id, config):
    """One run, one API, one template store -- a whole install in miniature.

    The registry holds an adapter for every adapter the configuration binds,
    because that is what an install IS: the configuration says which product
    drives each instance, and the registry is where those products are.
    """
    store = RunStore(tmp_path)
    store.create_run(a_run(
        run_id=run_id, mode="confirm", config_digest=snapshot_digest(config)),
        config)
    events = []
    bound = sorted({row["adapter"] for row in config["instances"]})
    subject = CommandApi(
        store, AdapterRegistry([DeepPlanAdapter(name) for name in bound]),
        session=CommandSession(PORT, TOKEN), budget=PRODUCT_COMMAND_BUDGET,
        clock=lambda: NOW, ids=ids(), publish_run=events.append,
        providers=contracts(), templates=TemplateStore(tmp_path))
    return subject, store, events


def _values(document) -> set:
    """Every string VALUE in a document, keys excluded.

    A key and a value fail differently here: `instance_id` is a key this record
    must carry, and `claude-code` is a value it must not.
    """
    if isinstance(document, dict):
        return {word for item in document.values() for word in _values(item)}
    if isinstance(document, list):
        return {word for item in document for word in _values(item)}
    return {document} if isinstance(document, str) else set()


#: The shipped revision a run materializes from. This file drives the DEFAULT
#: cycle, so the revision is read off the template rather than written as a
#: literal beside it -- a number typed twice is a number that can disagree with
#: the file it names.
DEFAULT_TEMPLATE = "dalio-v2"


def default_body(**changes):
    document = load_template(DEFAULT_TEMPLATE).as_dict()
    document.update(changes)
    return document


def materialize_on(subject, run_id, graph_id, assignments, template=None):
    template = load_template(DEFAULT_TEMPLATE) if template is None else template
    return post(subject, f"/command/runs/{run_id}/graph/from-template", {
        "graph_id": graph_id, "template_id": template.template_id,
        "revision": template.revision, "assignments": assignments})


def two_deployments(tmp_path):
    """Publish the shipped cycle on two installs and materialize it on each.

    Everything goes through the routes a browser would call: nothing here
    builds a `GraphDefinition`, and nothing here names a provider.
    """
    template = load_template(DEFAULT_TEMPLATE)
    spread_api, spread_store, spread_events = deployment(
        tmp_path / "spread", "run-spread", SPREAD)
    solo_api, solo_store, solo_events = deployment(
        tmp_path / "solo", "run-solo", SOLO)
    for subject in (spread_api, solo_api):
        assert post(subject, TEMPLATES_PATH, default_body()).status == 201

    spread = materialize_on(spread_api, "run-spread", "graph-spread", {
        "role-thinker": "codex-review", "role-diagnostician": "codex-review",
        "role-designer": "codex-review", "role-implementer": "claude-dev"})
    solo = materialize_on(solo_api, "run-solo", "graph-solo",
                          {role: "solo-node" for role in template.roles})
    assert spread.status == solo.status == 201
    return (
        (GraphDefinition.from_dict(spread.payload), spread_store, spread_events),
        (GraphDefinition.from_dict(solo.payload), solo_store, solo_events),
    )


def test_one_cycle_written_in_roles_is_the_same_work_on_two_deployments(tmp_path):
    """Same topology, same stages, and the product recognises what it shipped."""
    (across, _, _), (alone, _, _) = two_deployments(tmp_path)
    assert is_dalio_template(across) and is_dalio_template(alone)
    assert [node.node_id for node in across.nodes] == \
        [node.node_id for node in alone.nodes]
    assert across.edges == alone.edges
    assert [node.stage for node in across.nodes] == \
        [node.stage for node in alone.nodes]


def test_two_deployments_of_one_cycle_are_two_records_that_name_their_own(tmp_path):
    """Told apart only by WHO does the work -- which is what a role is for."""
    (across, spread_store, spread_events), (alone, solo_store, solo_events) = \
        two_deployments(tmp_path)
    assert sorted({node.instance_id for node in across.nodes
                   if node.instance_id}) == ["claude-dev", "codex-review"]
    assert {node.instance_id for node in alone.nodes
            if node.instance_id} == {"solo-node"}
    assert across.digest() != alone.digest()

    for store, run_id, definition, events in (
            (spread_store, "run-spread", across, spread_events),
            (solo_store, "run-solo", alone, solo_events)):
        stored = [row.value for row in store.read(run_id).records
                  if row.kind == "graph_definition"]
        assert stored == [definition]
        assert events == [run_id]


def test_no_adapter_and_no_role_survives_into_either_durable_record(tmp_path):
    """A template says roles; the record it becomes says instances.

    Asserted as a set of VALUES rather than a substring search, because an
    instance an operator called `codex-review` contains an adapter's name and
    is still an instance -- that name is the operator's, and it is exactly what
    the record is supposed to carry.
    """
    for definition, _store, _events in two_deployments(tmp_path):
        document = definition.as_dict()
        rendered = json.dumps(document)
        assert '"role_id"' not in rendered
        assert "adapter" not in rendered
        assert not _values(document) & {"claude-code", "codex"}


def test_the_step_that_acts_is_one_this_product_can_be_asked_to_do(tmp_path):
    """A plan nobody could act on would be a cycle that only looks like one.

    The acting step's payload comes out of the materialized record and goes
    back in through the ordinary proposal route, unchanged. One schema, two
    callers: what the plan may say, a proposal may repeat -- and the proposal
    is bound to the node it came from.
    """
    subject, _store, _events = deployment(tmp_path, "run-act", SOLO)
    assert post(subject, TEMPLATES_PATH, default_body()).status == 201
    template = load_template(DEFAULT_TEMPLATE)
    created = materialize_on(subject, "run-act", "graph-act",
                             {role: "solo-node" for role in template.roles})
    assert created.status == 201

    definition = GraphDefinition.from_dict(created.payload)
    acting = next(node for node in definition.nodes
                  if node.capability == "dispatch")
    proposed = post(subject, "/command/runs/run-act/proposals", {
        **proposal_body(),
        "instance_id": acting.instance_id,
        "capability": acting.capability,
        "arguments": acting.payload(),
        "node_id": acting.node_id,
    })
    assert proposed.status == 201, proposed.payload
    assert proposed.payload["node_id"] == acting.node_id
    assert proposed.payload["instance_id"] == "solo-node"


def test_a_second_run_reuses_the_revision_the_first_one_already_published(tmp_path):
    """Reuse is the point: a template outlives the run that first used it.

    Both runs live in one project, so they share one template store -- and the
    second materializes from bytes the first published, without republishing
    and without the file being written twice.
    """
    store = RunStore(tmp_path)
    for run_id in ("run-first", "run-second"):
        store.create_run(a_run(
            run_id=run_id, mode="confirm",
            config_digest=snapshot_digest(SOLO)), SOLO)
    events = []
    subject = CommandApi(
        store, AdapterRegistry([DeepPlanAdapter()]),
        session=CommandSession(PORT, TOKEN), budget=PRODUCT_COMMAND_BUDGET,
        clock=lambda: NOW, ids=ids(), publish_run=events.append,
        providers=contracts(), templates=TemplateStore(tmp_path))

    assert post(subject, TEMPLATES_PATH, default_body()).status == 201
    template = load_template(DEFAULT_TEMPLATE)
    assignments = {role: "solo-node" for role in template.roles}
    first = materialize_on(subject, "run-first", "graph-a", assignments)
    second = materialize_on(subject, "run-second", "graph-b", assignments)
    assert first.status == second.status == 201

    # One published revision, two runs, two records that differ only in whose.
    assert TemplateStore(tmp_path).revisions("template-dalio") == (2,)
    assert first.payload["run_id"] == "run-first"
    assert second.payload["run_id"] == "run-second"
    assert first.payload["nodes"] == second.payload["nodes"]
    assert sorted(events) == ["run-first", "run-second"]
