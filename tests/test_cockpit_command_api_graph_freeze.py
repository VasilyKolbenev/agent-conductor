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

from conductor.command.adapters.deep_commands import DEEP_ARGUMENT_TYPES
from conductor.command.api_contracts import (
    ApiRefusal,
    parse_confirmation,
    parse_proposal,
)
from conductor.command.contracts import ActionProposal, ActionRequest
from conductor.command.graph_definition import GraphDefinition

from conductor.command import run_store as run_store_module

from tests.test_cockpit_command_api_freeze import _SPEC, CANON, CONFIRM_FIELDS

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
