"""A proposal on a planned run names its step, and what the window may ask for.

Split out of ``tests/test_command_run_terminal_doors.py`` when that module
reached the project's line cap, along the seam its own docstring already drew:
that module holds three circuits and **presence** is one of them, self-contained
and about a different door from the other two. Everything moved here moved
byte-identically; the two witnesses at the bottom are new, and they are the
reason the split had to happen before them.

The circuit, in the order a reader meets it:

- the legacy panel's composer emits seven keys and CANNOT emit ``node_id``, so
  it is refused on every planned run and unchanged on a plan-less one. Both
  directions, because a door refusing everything would pass either alone;
- the Studio's own nine-key body, which names the step the schedule chose, is
  ACCEPTED. That is the direction the two above cannot state between them;
- what the window is allowed to ASK FOR, which is not simply what the plan
  allows. Two ceilings apply and only one of them is the plan's, and the second
  is spent at a different door -- so a body honouring the plan alone was
  accepted at propose and refused at every Confirm;
- and what does NOT age: the freshness budget judges the confirmation the
  server mints at the moment of the press. An old proposal with current material
  binding is still confirmable; an unbound legacy one requires a new preview
  because of its missing binding, not its age.

The ending, the eligibility rules and the four write doors stay next door.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from conductor.command.api_contracts import ERROR_STATUS
from conductor.command.contracts import ABSENT, ActionProposal
from conductor.command.graph_definition import GraphDefinition, GraphNode
from conductor.command.service import ServiceError
from tests.test_command_graph_binding import RUN_ID, a_runtime, a_store
from tests.test_command_http_api import api, post, proposal_body
from tests.test_command_run_terminal_doors import NOW, journal_bytes, kinds
from tests.test_command_schema_doubles import DeepDispatchAdapter, DeepPlanAdapter

#: A ceiling a plan may legally name and a run's budget will not honour.
#: `PRODUCT_COMMAND_BUDGET.max_action_seconds` is 3600, and `GraphNode` admits
#: anything up to 86400 -- so this number is where the two disagree.
WIDE_CEILING = 7200
#: What the window asks for at most, and `studio-runstep.DEFAULT_TIMEOUT`'s own
#: value. Spelled here rather than imported: this module is the DURABLE side of
#: the relation, and reading the number out of the window it is meant to hold
#: would be the window checking itself.
WINDOW_CEILING = 900
LONG_AGO = "2000-01-01T00:00:00Z"


# -- presence: a proposal on a planned run names its step ----------------------


def legacy_composer_body():
    """Exactly the seven keys `panel/command.js` `proposalBody` can emit.

    Written out rather than derived, because the point is what that composer
    CANNOT put in: there is no `node_id` key anywhere in it, and no branch of
    that function adds one.
    """
    body = proposal_body()
    assert set(body) == {
        "instance_id", "attempt_id", "capability", "arguments", "scope",
        "proposed_by", "rationale", "timeout_seconds"}
    return body


def test_the_legacy_composers_body_is_refused_on_a_planned_run(tmp_path):
    """Witness 3, first direction, and the intended behavioural change.

    An unbound proposal on a planned run is authority the plan never gave, and
    it silently mis-resolves the verifier as well. Refusing is the only honest
    answer until that panel learns to bind a node.
    """
    from tests.alpha3_graph_artifacts import dalio_definition

    subject, store, _ = api(tmp_path, adapters=[DeepDispatchAdapter()])
    store.append(dalio_definition(run_id=RUN_ID))
    before = journal_bytes(store)

    refused = post(subject, f"/command/runs/{RUN_ID}/proposals",
                   legacy_composer_body())

    assert refused.status == ERROR_STATUS["service_refused"]
    assert refused.payload["error"]["code"] == "service_refused"
    assert journal_bytes(store) == before


def test_the_same_body_is_accepted_unchanged_on_a_plan_less_run(tmp_path):
    """Witness 3, second direction: runs without a graph are byte-identical.

    Without this the refusal above could equally be a composer that stopped
    working at all.
    """
    subject, store, _ = api(tmp_path, adapters=[DeepDispatchAdapter()])

    answer = post(subject, f"/command/runs/{RUN_ID}/proposals",
                  legacy_composer_body())

    assert answer.status == 201
    assert "node_id" not in answer.payload
    assert kinds(store) == ["action_proposal"]


def test_the_service_refusal_names_the_graph_and_what_is_missing(tmp_path):
    """A caller has to learn WHICH plan is making the demand."""
    from tests.alpha3_graph_artifacts import dalio_definition

    store = a_store(tmp_path, with_graph=False)
    store.append(dalio_definition(run_id=RUN_ID))
    service = a_runtime(store)  # builds the store-backed service seam too

    assert service is not None
    with pytest.raises(ServiceError, match="must name the node it carries out"):
        _propose_unbound(store)


def test_the_studios_step_body_is_accepted_on_a_planned_run_beside_the_refused_legacy_one(
        tmp_path):
    """The third direction, which the two above cannot state between them.

    A door refusing BOTH bodies would pass them: one says the unbound body is
    refused on a planned run, the other that it is unchanged without a plan.
    Neither says a body NAMING its step is accepted -- the shape the Studio met
    before it sent `node_id`. The nine keys are `studio-runstep.proposalBody`'s.
    """
    from tests.alpha3_graph_artifacts import dalio_definition

    subject, store, _ = api(tmp_path, adapters=[DeepPlanAdapter()])
    store.append(dalio_definition(run_id=RUN_ID))
    node = next(row for row in dalio_definition().nodes if row.node_id == "goal")
    body = {"instance_id": node.instance_id, "capability": node.capability,
            "attempt_id": "attempt-goal-0", "arguments": node.payload(),
            "scope": ["src"], "proposed_by": "release-owner",
            "rationale": "Start the plan at its first step.",
            "timeout_seconds": 900, "node_id": node.node_id}

    accepted = post(subject, f"/command/runs/{RUN_ID}/proposals", body)

    assert accepted.status == 201 and accepted.payload["node_id"] == "goal"
    assert kinds(store) == ["graph_definition", "action_proposal"]
    before = journal_bytes(store)
    unbound = {name: value for name, value in body.items() if name != "node_id"}
    assert post(subject, f"/command/runs/{RUN_ID}/proposals",
                unbound).status == ERROR_STATUS["service_refused"]
    assert journal_bytes(store) == before


def _propose_unbound(store):
    from conductor.command.adapters import AdapterRegistry
    from conductor.command.service import CommandService
    from tests.test_command_schema_doubles import DeepDispatchAdapter

    body = legacy_composer_body()
    CommandService(store, AdapterRegistry([DeepDispatchAdapter()]),
                   clock=lambda: NOW,
                   ids=lambda kind: f"{kind}-001").propose(
        run_id=RUN_ID, node_id=None, **body)


# -- what the window may ask for, and what does not age -----------------------


def _the_goal_node():
    from tests.alpha3_graph_artifacts import dalio_definition

    return next(row for row in dalio_definition().nodes if row.node_id == "goal")


def _a_plan_with_a_wide_ceiling(run_id):
    """The shipped plan, its first step allowed far more time than the budget."""
    from tests.alpha3_graph_artifacts import dalio_definition

    plan = dalio_definition(run_id=run_id)
    nodes = tuple(
        GraphNode.from_dict({**row.as_dict(), "timeout_seconds": WIDE_CEILING})
        if row.node_id == "goal" else row for row in plan.nodes)
    return GraphDefinition(graph_id=plan.graph_id, run_id=run_id,
                           created_at=plan.created_at, nodes=nodes,
                           edges=plan.edges)


def _step_body(node, *, timeout):
    """`studio-runstep.proposalBody`'s nine keys, with the ceiling under test."""
    return {"instance_id": node.instance_id, "capability": node.capability,
            "attempt_id": "attempt-goal-0", "arguments": node.payload(),
            "scope": ["src"], "proposed_by": "release-owner",
            "rationale": "Start the plan at its first step.",
            "timeout_seconds": timeout, "node_id": node.node_id}


def _confirm_of(payload):
    """`studio-runstep.confirmBody`: the stored proposal's facts, restated."""
    return {"proposal_id": payload["proposal_id"],
            "preview_digest": payload["preview_digest"],
            "capability": payload["capability"], "scope": payload["scope"],
            "config_digest": payload["config_digest"],
            "confirmed_by": "release-owner"}


@pytest.mark.parametrize(
    "asked,confirmed", [(WINDOW_CEILING, 201),
                        (WIDE_CEILING, ERROR_STATUS["authorization_refused"])],
    ids=["the smaller of the two", "the plan's own"])
def test_the_windows_own_ceiling_is_what_makes_a_confirm_land_on_a_wide_plan(
        tmp_path, asked, confirmed):
    """Two ceilings apply, and they are spent at two different doors.

    `graph_causality._within_the_planned_ceiling` refuses a document asking for
    more than its STEP allows, and it is spent at propose. `_hold_budget`
    refuses a proposal past the RUN's `max_action_seconds`, and it is spent at
    AUTHORIZE. So a plan may legally name a ceiling the run will not honour --
    and a window honouring only the plan's number proposed cleanly and made
    every Confirm 409, under a stale-screen sentence blaming a plan that had
    not moved.

    Both directions, because either alone proves nothing: the window's number
    lands, the plan's own does not, and the difference between the two runs is
    one integer in a body.
    """
    subject, store, _ = api(tmp_path, adapters=[DeepPlanAdapter()])
    store.append(_a_plan_with_a_wide_ceiling(RUN_ID))

    made = post(subject, f"/command/runs/{RUN_ID}/proposals",
                _step_body(_the_goal_node(), timeout=asked))

    # The plan admits both: its own ceiling is the wider of the two.
    assert made.status == 201, made.payload
    answer = post(subject, f"/command/runs/{RUN_ID}/actions",
                  _confirm_of(made.payload))
    assert answer.status == confirmed, answer.payload


@pytest.mark.parametrize("bound", [True, False], ids=["bound-old", "legacy-old"])
def test_a_proposal_written_long_ago_is_judged_by_binding_not_its_age(
        tmp_path, bound):
    """Freshness judges CONFIRMATION time, separately from material binding.

    Both proposals are a quarter century old against a 3600-second budget.
    Current binding is accepted; omitting it gives the specific new-preview
    refusal and changes no journal bytes. Merely rewording the old assertion
    or marking every old fixture current would lose that distinction.
    """
    subject, store, _ = api(tmp_path, adapters=[DeepPlanAdapter()])
    from tests.alpha3_graph_artifacts import dalio_definition

    store.append(dalio_definition(run_id=RUN_ID))
    node = _the_goal_node()
    stale = ActionProposal(
        proposal_id="proposal-of-the-year-2000", run_id=RUN_ID,
        attempt_id="attempt-goal-0", instance_id=node.instance_id,
        capability=node.capability, arguments=node.payload(), scope=("src",),
        proposed_by="release-owner", proposed_at=LONG_AGO,
        timeout_seconds=WINDOW_CEILING,
        rationale="Written long before anybody confirmed it.",
        config_digest=store.read(RUN_ID).envelope.config_digest, node_id="goal",
        input_binding="proposal-v1" if bound else ABSENT)
    store.append(stale)
    before = journal_bytes(store)

    answer = post(subject, f"/command/runs/{RUN_ID}/actions", {
        "proposal_id": stale.proposal_id,
        "preview_digest": stale.preview_digest,
        "capability": stale.capability, "scope": list(stale.scope),
        "config_digest": stale.config_digest, "confirmed_by": "release-owner"})

    assert answer.status == (201 if bound else 409), answer.payload
    assert kinds(store) == ["graph_definition", "action_proposal"] + (
        ["action_request"] if bound else [])
    if not bound:
        assert answer.payload["error"]["code"] == "proposal_rebind_required"
        assert journal_bytes(store) == before
    # And the window DRAWS nothing about a proposal aging. Read as code, so the
    # comment recording why the sentence went does not satisfy its own absence;
    # `tests/test_studio_step_source.py` holds the same relation from the other
    # side, on the sentences rather than on the fact beneath them.
    from tests.test_graph_source import _code

    panel = Path(__file__).resolve().parents[1] / "src" / "conductor" / "panel"
    assert "freshness" not in _code(panel / "studio-runstep.js").casefold()
