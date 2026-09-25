"""Bind bounded-run instructions and initial inputs at one journal prefix."""
from __future__ import annotations

import hashlib

from .artifacts import latest_artifacts, required_input_refs, settled_products
from .authorization_terms import InitialInputBinding, InstructionBinding
from .contract_values import ContractError, _id, _unique_ids


def content_digest(document):
    """The exact UTF-8 content, not a digest claimed by an agent."""
    return "sha256:" + hashlib.sha256(document.content.encode("utf-8")).hexdigest()


def executable_nodes(definition):
    nodes = tuple(node for node in definition.nodes if node.capability is not None)
    if not nodes:
        raise ContractError("bounded authorization requires executable tasks")
    for node in nodes:
        if node.kind != "task" or node.capability not in {"dispatch", "review"}:
            raise ContractError("bounded authorization supports dispatch/review tasks only")
    return nodes


def bind_inputs(definition, prior_values):
    """Missing instructions never fall back to a mutable workspace file.

    A missing input can be supplied later only by a declared authorized review
    producer. The driver still has to establish same-grant origin on consumption.
    This relation reads no file, provider, clock, or live execution state.
    """
    nodes = executable_nodes(definition)
    documents = settled_products(prior_values)
    instructions = []
    for node in nodes:
        if node.capability == "dispatch":
            reference = _id("instruction_ref", node.arguments.get("instruction_ref"))
            document, = latest_artifacts(documents, (reference,))
            if document.source_action_id is not None:
                raise ContractError("initial instructions require a human source document")
            instructions.append(InstructionBinding(
                node.node_id, document.artifact_id, content_digest(document)))
    references = set()
    for node in nodes:
        references.update(_unique_ids("input references", required_input_refs(
            node.capability, node.arguments)))
    producers = {_id("result_artifact_ref", node.arguments.get("result_artifact_ref"))
                 for node in nodes if node.capability == "review"}
    available = {document.artifact_ref for document in documents}
    if references - available - producers:
        raise ContractError("initial inputs are missing and have no authorized producer")
    inputs = tuple(InitialInputBinding(row.artifact_ref, row.artifact_id, content_digest(row))
                   for row in latest_artifacts(documents, tuple(sorted(references & available))))
    return tuple(instructions), inputs
