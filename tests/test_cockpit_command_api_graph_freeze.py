"""The graph binding as the SPEC freezes it, not as a test blesses it.

Split from test_cockpit_command_api_freeze.py when that module crossed the
800-line cap: this file is the self-contained graph circuit -- the byte-
compatibility witness for every example written before graphs existed, the
graph-bound examples the production constructors derive, the digests they move,
and the inheritance the request may not decide for itself. The parent owns the
spec loader and the shared constants this module imports.

Adding `graph_definition` to a registry in a test would have been production
blessing itself. What makes it a re-freeze is that the authoritative document
now says so, and every assertion below reads that document.
"""
from __future__ import annotations

import json
import re

import pytest

from conductor.command.adapters import AdapterRegistry
from conductor.command.adapters.deep_commands import DEEP_ARGUMENT_TYPES
from conductor.command.api_contracts import (
    ApiRefusal,
    parse_confirmation,
    COMMAND_ARGUMENT_SCHEMA,
    parse_graph,
    parse_proposal,
)
from conductor.command.contracts import ActionProposal, ActionRequest, RunEnvelope
from conductor.command.graph_definition import GraphDefinition
from conductor.command.graph_projection import graph_runtime
from conductor.command.http_api import COMMAND_ROUTES, _match_route
from conductor.command.run_store import RecoveredRun, StoredRecord

from conductor.command import run_store as run_store_module

from tests.test_cockpit_command_api_freeze import _SPEC, CANON, CONFIRM_FIELDS
from tests.test_command_schema_doubles import DeepPlanAdapter

#: The paragraph in the spec that IS the closed durable vocabulary. The kinds
#: are read out of it and compared to the registry, so neither can move alone --
#: a substring pin would survive the spec dropping a kind, and would red on an
#: honest rewording.
_VOCABULARY_RE = re.compile(
    r"The record kinds and their contracts are the closed v2 vocabulary:"
    r"(?P<body>.*?)\n\n", re.DOTALL)
_KIND_RE = re.compile(r"`(?P<kind>[a-z_]+)` \(`(?P<contract>[A-Za-z]+)`\)")


# -- the graph binding, frozen in the spec rather than blessed by a test -------


def test_the_legacy_examples_still_carry_no_binding_at_all():
    """The byte-compatibility witness: adding an optional field moved nothing.

    Every example this spec carried before graphs existed is still exactly what
    it was, which is the whole reason the field is written only when present.
    """
    for name in ("propose_request", "action_proposal", "action_request"):
        assert "node_id" not in CANON[name], name
    request = ActionRequest.from_dict(CANON["action_request"])
    proposal = ActionProposal.from_dict(CANON["action_proposal"])
    assert (request.node_id, proposal.node_id) == (None, None)
    assert proposal.as_dict() == CANON["action_proposal"]


def test_the_graph_bound_examples_are_what_the_contracts_produce():
    """Derived by the production constructors, not typed by hand."""
    proposal = ActionProposal.from_dict(CANON["graph_bound_action_proposal"])
    request = ActionRequest.from_dict(CANON["graph_bound_action_request"])
    assert proposal.as_dict() == CANON["graph_bound_action_proposal"]
    assert request.as_dict() == CANON["graph_bound_action_request"]
    assert proposal.node_id == "apply"


def test_the_binding_is_inside_the_digests_the_spec_already_froze():
    """A recomputation, not a copied constant: the digest is taken here."""
    bound = ActionProposal.from_dict(CANON["graph_bound_action_proposal"])
    unbound = ActionProposal.from_dict(
        {key: value for key, value in CANON["graph_bound_action_proposal"].items()
         if key not in ("node_id", "preview_digest")})
    assert bound.preview_digest != unbound.preview_digest
    request = ActionRequest.from_dict(CANON["graph_bound_action_request"])
    assert request.preview_digest == bound.preview_digest


def test_the_request_inherits_the_proposals_binding_and_its_settled_facts():
    proposal = ActionProposal.from_dict(CANON["graph_bound_action_proposal"])
    request = ActionRequest.from_dict(CANON["graph_bound_action_request"])
    assert request.node_id == proposal.node_id
    assert request.idempotency_key == f"dispatch-{proposal.proposal_id}"
    for field in ("attempt_id", "instance_id", "capability", "timeout_seconds",
                  "preview_digest"):
        assert getattr(request, field) == getattr(proposal, field), field
    assert tuple(request.scope) == tuple(proposal.scope)
    assert dict(request.arguments) == dict(proposal.arguments)


def test_the_spec_says_the_store_holds_the_whole_relation_bound_or_not():
    """The wording change-detector for a rule the store now enforces.

    `arguments` were the one settled fact the store did not compare, and an
    unbound proposal never reached the node re-check that caught the rest -- so
    a Confirm could change the work under a confirmed proposal's name. The
    document has to carry that rule in words before any test blesses it.
    """
    text = " ".join(_SPEC.read_text(encoding="utf-8").split())
    required = (
        "MUST restate that proposal's whole unchanged-proposal relation of "
        "section 4.2, `arguments` among them",
        "whether or not either document names a node",
        "a request that names a node while repeating no proposal this run "
        "holds is refused",
    )
    assert all(statement in text for statement in required)


def test_the_canonical_graph_record_is_the_wrapper_the_journal_holds():
    wrapper = CANON["graph_definition_record"]
    assert set(wrapper) == {"record_type", "record"}
    assert wrapper["record_type"] == "graph_definition"
    graph = GraphDefinition.from_dict(wrapper["record"])
    assert graph.as_dict() == wrapper["record"]
    assert graph.stage_node("do").node_id == "apply"


def test_the_bound_proposal_and_the_canonical_graph_agree_on_the_node():
    """The example is a graph-BOUND proposal, so the plan has to back it."""
    graph = GraphDefinition.from_dict(CANON["graph_definition_record"]["record"])
    proposal = ActionProposal.from_dict(CANON["graph_bound_action_proposal"])
    node = next(row for row in graph.nodes if row.node_id == proposal.node_id)
    assert (node.instance_id, node.capability) == (
        proposal.instance_id, proposal.capability)
    assert node.payload() == json.loads(json.dumps(dict(proposal.arguments)))
    assert graph.run_id == proposal.run_id


@pytest.mark.parametrize("value", [None, "", "not a node", 17, [], {}])
def test_a_propose_body_node_id_that_is_not_a_name_is_refused(value):
    """Null among them: absent and null are different sentences."""
    body = {**CANON["graph_bound_propose_request"], "node_id": value}
    with pytest.raises(ApiRefusal):
        parse_proposal(body, adapter_capabilities=DEEP_ARGUMENT_TYPES)


def test_a_confirm_body_still_has_no_place_to_name_a_node():
    assert "node_id" not in CONFIRM_FIELDS
    with pytest.raises(ApiRefusal):
        parse_confirmation({**CANON["confirm_request"], "node_id": "apply"})


def test_the_spec_paragraph_and_the_registry_name_the_same_record_kinds():
    """The document is authoritative, so the registry is read AGAINST it.

    Adding a kind to the registry and calling that a re-freeze is production
    blessing itself. What the spec says is the vocabulary; this reads the kinds
    out of that sentence and holds the registry to them, in both directions.
    """
    text = _SPEC.read_text(encoding="utf-8")
    match = _VOCABULARY_RE.search(text)
    assert match, "the spec no longer carries its closed-vocabulary paragraph"
    spelled = {
        kind: contract
        for kind, contract in _KIND_RE.findall(match.group("body"))}
    assert spelled == {
        kind: contract.__name__
        for kind, (contract, _identity) in run_store_module._RECORDS.items()}


def test_the_canonical_graph_bound_body_is_accepted_by_the_real_parser():
    """The negatives below only prove what is refused; this proves what is not.

    Without it, a production door that stopped accepting `node_id` at all would
    leave every refusal test green.
    """
    submitted = parse_proposal(
        CANON["graph_bound_propose_request"],
        adapter_capabilities=DEEP_ARGUMENT_TYPES)
    assert submitted.node_id == "apply"
    assert submitted.capability == "dispatch"


def test_a_propose_body_that_names_no_node_is_still_accepted():
    """The legacy road stays open, which is why the field is optional."""
    submitted = parse_proposal(
        CANON["propose_request"], adapter_capabilities=DEEP_ARGUMENT_TYPES)
    assert submitted.node_id is None


# -- the graph route and the graph half of a read, as the SPEC freezes them ----


def test_the_spec_route_table_and_the_production_allowlist_are_one_surface():
    """Adding a route to production and calling it frozen is blessing itself.

    The parent module holds the spec's table to the reviewed shape; this holds
    it to the code, in both directions and in order, so a route can never exist
    in one of the two places alone.
    """
    spelled = tuple((row["method"], row["path"]) for row in CANON["route_table"])
    assert spelled == COMMAND_ROUTES


@pytest.mark.parametrize("method,path", [
    ("POST", "/command/runs/run-cockpit-001/graph"),
    ("GET", "/command/runs/run-cockpit-001/graph"),
])
def test_the_graph_tail_is_a_route_the_matcher_knows_by_name(method, path):
    """`COMMAND_ROUTES` is a list; `_RUN_ROUTE` is what actually admits a path.

    A route added to one and not the other is a route the table advertises and
    the server answers `route_not_found` for, so both are driven here: the POST
    is matched, and the GET is refused for its METHOD rather than its path.
    """
    if method == "POST":
        assert _match_route(method, path).name == "graph"
    else:
        with pytest.raises(ApiRefusal) as refused:
            _match_route(method, path)
        assert refused.value.code == "method_not_allowed"


def test_the_canonical_plan_body_builds_the_canonical_graph_record():
    """The stored record is DERIVED from the request beside it in the spec.

    Two documents typed by hand would agree with each other and with nothing
    else; this takes the browser body through the production door and the
    server's own injection, and holds the result to the frozen record.
    """
    record = CANON["graph_definition_record"]["record"]
    built = parse_graph(CANON["graph_request"]).build(
        run_id=record["run_id"], created_at=record["created_at"])
    assert built.as_dict() == record


def test_the_spec_says_both_roads_ask_one_pair_authority():
    """The wording change-detector for a law that spans two sections.

    A plan and a proposal describe the same work; the document has to say they
    ask one authority, in one order, with one word for each answer -- before
    any test blesses that. It said neither, and each road grew half of it.
    """
    text = " ".join(_SPEC.read_text(encoding="utf-8").split())
    required = (
        "Both routes ask one shared authority, over the triple "
        "`(bound adapter, capability, arguments)`, in this order",
        "MUST be exactly `deep-arguments-v1`, the one family this frozen API "
        "speaks",
        "MUST NOT be judged **and MUST NOT be rebuilt into their canonical "
        "form** either",
        "Steps 1 and 2 are `capability_unsupported` (409)",
        "Step 3 is `contract_invalid` (422)",
        "No refusal at any step writes a proposal or a graph, and none "
        "publishes a run signal",
        "the same authority a proposal passes, with the same order and the "
        "same words",
    )
    for statement in required:
        assert statement in text, statement


def test_the_canonical_plan_body_passes_the_registry_door_it_will_meet():
    """A frozen example the product would refuse is a frozen example of nothing.

    The route judges each bound node against the schema the registry recorded
    for that node's own (adapter, capability) pair, so the document this spec
    offers as THE graph request is driven through exactly that door, with an
    adapter that declares the family this API speaks.
    """
    registry = AdapterRegistry([DeepPlanAdapter()])
    submitted = parse_graph(CANON["graph_request"])
    bound = [node for node in submitted.nodes if node.capability is not None]
    assert bound, "the canonical plan carries at least one node that does work"
    for node in bound:
        assert registry.argument_schema(
            "claude-code", node.capability) == COMMAND_ARGUMENT_SCHEMA
        registry.validate_arguments("claude-code", node.capability, node.payload())


@pytest.mark.parametrize("owned", ["run_id", "created_at", "schema_version"])
def test_the_plan_body_refuses_the_facts_the_server_injects(owned):
    record = CANON["graph_definition_record"]["record"]
    with pytest.raises(ApiRefusal):
        parse_graph({**CANON["graph_request"], owned: record[owned]})


def test_the_canonical_runtime_projection_is_what_production_computes():
    """The frozen projection, recomputed from the frozen records beside it."""
    graph = GraphDefinition.from_dict(CANON["graph_definition_record"]["record"])
    proposal = ActionProposal.from_dict(CANON["graph_bound_action_proposal"])
    request = ActionRequest.from_dict(CANON["graph_bound_action_request"])
    recovered = RecoveredRun(
        envelope=RunEnvelope(
            run_id=graph.run_id, cycle_id="cockpit-orbit",
            created_at="2026-08-13T12:00:00Z",
            config_digest=proposal.config_digest, mode="confirm",
            status="active"),
        config={},
        records=(StoredRecord("graph_definition", graph),
                 StoredRecord("action_proposal", proposal),
                 StoredRecord("action_request", request)),
        warnings=())
    assert graph_runtime(recovered, graph) == CANON["graph_runtime_projection"]


def test_the_frozen_projection_says_confirmed_and_refuses_to_say_succeeded():
    """The one reading of this example a UI must not be able to make."""
    rows = {row["node_id"]: row
            for row in CANON["graph_runtime_projection"]["nodes"]}
    assert rows["apply"]["phase"] == "requested"
    assert rows["apply"]["outcome"] is None
    assert rows["human-gate"]["decision"] == "idle"
    assert (rows["retry"]["pass"], rows["retry"]["bound_reached"]) == (1, False)
