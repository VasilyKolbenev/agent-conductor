"""A step's plan-side ceilings, and the two roads that spend them.

The inspector used to say `Timeout - not supported by this harness. A timeout is
a per-action field carried on a proposal, not on a workflow step` and
`Retry / attempt bound - ... The only bound a workflow document carries is a
loop's`. Both were true, and both were the problem: a bound that lives only on
the request is a bound the requester chooses, which is not a bound.

Two fields now: `timeout_seconds` and `attempt_bound`, on `TemplateNode` and on
the `GraphNode` a run freezes. Both are CEILINGS, never defaults, and both are
optional -- a node naming neither constrains neither, which is what every plan
written before they existed says and why `dalio-v1` digests exactly as it did.

What makes them real rather than stored is WHERE they are spent, and the two
places are deliberately different:

- the timeout is held in `graph_causality`, the one relation that runs on the
  honest road and again on a journal replayed from disk. A record written
  straight into `records.jsonl` cannot buy itself more time than the plan gave
  the step;
- the attempt bound is held in `ControlRuntime._hold_budget`, the last frame
  before a request is minted -- no durable byte written, no effect authority
  granted, no adapter touched. A bound checked after any of those is a bound
  that has already been exceeded once.

This product already had a field that was declared, validated, required in
every dispatch payload and read by nothing: `output_limit_profile`. These two
are the deliberate opposite, and the mutations below are what say so.
"""
from __future__ import annotations

import pytest

from conductor.command.contract_values import ContractError
from conductor.command.graph_definition import GraphDefinition, GraphNode
from conductor.command.graph_template import (
    GraphTemplate, RunBinding, TemplateNode, materialize)


def a_node(**changes):
    base = {"node_id": "step-one", "kind": "task", "title": "Step one",
            "instance_id": "dev", "capability": "dispatch",
            "arguments": {"work_item_id": "w-1"}}
    base.update(changes)
    return GraphNode(**base)


# -- the contract carries them, and refuses what it cannot honour ------------


def test_a_node_may_name_a_ceiling_on_its_time_and_on_its_attempts():
    node = a_node(timeout_seconds=600, attempt_bound=3)

    assert (node.timeout_seconds, node.attempt_bound) == (600, 3)
    assert node.as_dict()["timeout_seconds"] == 600
    assert node.as_dict()["attempt_bound"] == 3


def test_a_node_that_names_neither_writes_neither_and_does_not_move():
    """The whole backward-compatibility argument, in one assertion.

    A plan written before ceilings existed must digest exactly as it did, and
    it does because the keys are emitted only when named.
    """
    node = a_node()

    assert node.timeout_seconds is None and node.attempt_bound is None
    assert "timeout_seconds" not in node.as_dict()
    assert "attempt_bound" not in node.as_dict()


@pytest.mark.parametrize("field, value", [
    ("timeout_seconds", 0), ("timeout_seconds", -1),
    ("timeout_seconds", 86401),          # past what an action contract accepts
    ("timeout_seconds", True),           # bool is an int and True is not 1s
    ("timeout_seconds", "600"),          # a numeral is not a number
    ("attempt_bound", 0), ("attempt_bound", 100), ("attempt_bound", True),
])
def test_a_ceiling_this_build_could_not_honour_is_refused(field, value):
    """A plan naming 90000 seconds refuses every legal request.

    That is a plan nobody can run rather than a strict one, so the range is the
    ACTION contract's own and the refusal happens at construction.
    """
    with pytest.raises(ContractError):
        a_node(**{field: value})


def test_the_template_and_the_definition_judge_a_ceiling_by_one_rule():
    """Two contracts, one rule, so a template cannot store what a run refuses.

    A second copy of the range would let a template hold a ceiling the
    definition it materializes into would then reject -- a plan that cannot
    run, discovered at run time.
    """
    with pytest.raises(ContractError):
        TemplateNode(node_id="step-one", kind="task", title="Step one",
                     timeout_seconds=86401)


def test_a_ceiling_survives_materialization_into_the_run_it_freezes():
    """Miss the carry and the field is a template fact the run never hears."""
    template = GraphTemplate.from_dict({
        "schema_version": 1, "template_id": "flow", "revision": 1,
        "title": "Flow",
        # The gate is not decoration: an effect-capable step stands BEHIND one,
        # and the definition refuses a plan where it stands beside it.
        "nodes": [
            {"node_id": "confirm", "kind": "gate", "title": "Confirm",
             "gate_id": "gate-confirm", "resources": []},
            {"node_id": "step-one", "kind": "task", "title": "Step one",
             "role_id": "impl", "capability": "dispatch",
             "arguments": {"work_item_id": "w-1"},
             "resources": [], "timeout_seconds": 600,
             "attempt_bound": 2}],
        "edges": [{"from_node": "confirm", "to_node": "step-one"}]})

    plan = materialize(
        template, RunBinding.from_dict({"assignments": {"impl": "dev"}}),
        {"cycle": {"id": "c"}, "instances": [{"id": "dev", "adapter": "a"}]},
        graph_id="graph-1", run_id="run-1",
        created_at="2026-01-01T00:00:00Z")

    node = next(row for row in plan.nodes if row.node_id == "step-one")
    assert (node.timeout_seconds, node.attempt_bound) == (600, 2)


def test_a_ceiling_survives_a_round_trip_through_the_stored_document():
    """Read back, because a field that only writes is a field that is lost."""
    node = a_node(timeout_seconds=600, attempt_bound=2)

    again = GraphNode.from_dict(node.as_dict())

    assert (again.timeout_seconds, again.attempt_bound) == (600, 2)


# -- where they are SPENT, which is what makes them real ---------------------


def _bounded_run(tmp_path, **bounds):
    """A real run whose graph gives the Do node the ceilings under test.

    Built from the shipped Dalio definition and then re-issued with the two
    fields set, so what is exercised is a plan this product really materializes
    rather than a graph invented here.
    """
    from tests.test_command_graph_binding import CONFIG, RUN_ID, a_run
    from tests.alpha3_graph_artifacts import dalio_definition
    from conductor.command.run_store import RunStore, snapshot_digest

    plan = dalio_definition(run_id=RUN_ID)
    nodes = tuple(
        GraphNode.from_dict({**row.as_dict(), **bounds})
        if row.node_id == plan.stage_node("do").node_id else row
        for row in plan.nodes)
    store = RunStore(tmp_path)
    store.create_run(
        a_run(run_id=RUN_ID, mode="confirm",
              config_digest=snapshot_digest(CONFIG)), CONFIG)
    store.append(GraphDefinition(
        graph_id=plan.graph_id, run_id=plan.run_id,
        created_at=plan.created_at, nodes=nodes, edges=plan.edges))
    return store


def test_a_proposal_asking_past_the_plans_ceiling_is_refused_by_the_store(
        tmp_path):
    """Held in the relation that runs on append AND on replay.

    That is the point of the placement: a record written straight into
    records.jsonl, never passing the runtime at all, cannot buy itself more
    time than the plan gave the step.
    """
    from conductor.command.run_store import StoreError
    from tests.test_command_graph_binding import a_proposal

    store = _bounded_run(tmp_path, timeout_seconds=600)

    with pytest.raises(StoreError):
        store.append(a_proposal(timeout_seconds=900))


def test_a_proposal_asking_for_less_than_the_ceiling_is_accepted(tmp_path):
    """The over-correction control: a ceiling must not refuse legal work."""
    from tests.test_command_graph_binding import a_proposal

    store = _bounded_run(tmp_path, timeout_seconds=900)

    store.append(a_proposal(timeout_seconds=600))

    assert [row.kind for row in store.read("run-001").records][-1] ==         "action_proposal"


def test_a_node_naming_no_ceiling_constrains_nothing(tmp_path):
    """Every plan written before ceilings existed still runs unchanged."""
    from tests.test_command_graph_binding import a_proposal

    store = _bounded_run(tmp_path)

    store.append(a_proposal(timeout_seconds=900))

    assert [row.kind for row in store.read("run-001").records][-1] ==         "action_proposal"


# -- the attempt bound, driven through the road that spends it ---------------
#
# These are the witnesses this module should have opened with and did not. The
# ceiling above was mutation-proved; the attempt bound was not, and it shipped
# refusing the FIRST authorization because the count included proposals
# recorded after the one being authorized. Nothing here calls a helper: every
# test drives `ControlRuntime.authorize`, which is the only road that spends
# this bound.


def _authorizing(store):
    from tests.test_command_graph_binding import a_budget, a_runtime

    return a_runtime(store), a_budget()


def _proposal_on_the_do_node(store, index, attempt):
    """One proposal on the bounded node, appended the way a run really gets one."""
    from tests.test_command_graph_binding import a_proposal

    proposal = a_proposal(proposal_id=f"proposal-{index}",
                          attempt_id=f"attempt-{index}")
    store.append(proposal)
    return proposal


def test_a_bound_of_one_permits_the_first_authorization(tmp_path):
    """The case that shipped broken: a later proposal must not spend the bound.

    Two proposals stand in the journal and the FIRST is authorized. A proposal
    is a request for an attempt and not an attempt, so nothing has been spent
    yet and this must go through.
    """
    from tests.test_command_graph_binding import a_confirmation

    store = _bounded_run(tmp_path, attempt_bound=1)
    first = _proposal_on_the_do_node(store, 1, 1)
    _proposal_on_the_do_node(store, 2, 2)
    runtime, budget = _authorizing(store)

    authorization = runtime.authorize(a_confirmation(first), budget=budget)

    assert authorization.request.node_id == first.node_id


def test_the_bound_refuses_the_authorization_past_it(tmp_path):
    """The other direction: once the bound is spent, the next one is refused."""
    from conductor.command.runtime import AuthorizationError
    from tests.test_command_graph_binding import a_confirmation

    store = _bounded_run(tmp_path, attempt_bound=1)
    first = _proposal_on_the_do_node(store, 1, 1)
    second = _proposal_on_the_do_node(store, 2, 2)
    runtime, budget = _authorizing(store)
    runtime.authorize(a_confirmation(first), budget=budget)

    with pytest.raises(AuthorizationError, match="allows 1 attempt"):
        runtime.authorize(
            a_confirmation(second, confirmation_id="confirmation-002"),
            budget=budget)


def test_a_bound_of_two_permits_two_authorizations_and_refuses_the_third(
        tmp_path):
    """The bound is a count of authorizations, and it counts them exactly."""
    from conductor.command.runtime import AuthorizationError
    from tests.test_command_graph_binding import a_confirmation

    store = _bounded_run(tmp_path, attempt_bound=2)
    proposals = [_proposal_on_the_do_node(store, index, index)
                 for index in (1, 2, 3)]
    runtime, budget = _authorizing(store)

    for index, proposal in enumerate(proposals[:2], start=1):
        runtime.authorize(
            a_confirmation(proposal,
                           confirmation_id=f"confirmation-00{index}"),
            budget=budget)

    with pytest.raises(AuthorizationError, match="allows 2 attempt"):
        runtime.authorize(
            a_confirmation(proposals[2], confirmation_id="confirmation-003"),
            budget=budget)


def test_a_node_naming_no_attempt_bound_authorizes_without_limit(tmp_path):
    """The over-correction control: an unbounded step is still unbounded."""
    from tests.test_command_graph_binding import a_confirmation

    store = _bounded_run(tmp_path)
    proposals = [_proposal_on_the_do_node(store, index, index)
                 for index in (1, 2, 3)]
    runtime, budget = _authorizing(store)

    for index, proposal in enumerate(proposals, start=1):
        runtime.authorize(
            a_confirmation(proposal,
                           confirmation_id=f"confirmation-00{index}"),
            budget=budget)

    assert sum(1 for row in store.read("run-001").records
               if row.kind == "action_request") == 3
