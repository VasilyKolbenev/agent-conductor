"""What a plan must satisfy before one durable byte of it is written.

Split out of ``http_api`` when that module reached its line cap, along the seam
it already had: these were its only module-level functions, and every one of
them is a pure judgement over values a caller hands in. No route, no store, no
clock, no ``self``. The API imports them back under their old names, so no
caller anywhere learns that the split happened -- the shape ``authorize_holds``
and ``verify_holds`` already have one layer down, and for the same reason: a
refusal that needs nothing but its arguments does not belong inside the class
that happens to ask it.

They are five answers to five different questions, and keeping them apart is
what stopped two write roads answering one question two ways:

- ``_plan`` BUILDS, through the one production constructor and never field by
  field, from a template already in hand.
- ``_gated`` says which snapshot was judged, and refuses rather than reading a
  second one -- the whole defect that shape exists to make unrepresentable.
- ``_servable_pair`` says whether this build can carry the work out at all, in
  one order that is also the taxonomy of its two refusals.
- ``_bindings`` says which adapter a run's FROZEN configuration names, and
  treats an invalid one as corruption rather than as caller input.
- ``_task`` says which task that configuration froze, by the same rule.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .adapters import AdapterContractError, AdapterRegistry, UnsupportedCapability
from .api_contracts import (
    ARGUMENT_SCHEMAS,
    COMMAND_ARGUMENT_SCHEMA,
    ApiRefusal,
    TemplateRef,
)
from .contracts import ContractError, frozen_config_bindings
from .graph_definition import GraphDefinition
from .graph_template import GraphTemplate, TemplateError, materialize
from .store_errors import CorruptRun
from .task_contracts import TaskBinding, frozen_config_task, work_scope_disagreement


def _plan(template: GraphTemplate, config: Mapping[str, Any], run_id: str,
          asked: TemplateRef, created_at: str) -> GraphDefinition:
    """Build one plan from one snapshot, by the production door alone.

    Nothing assembles a definition field by field. `materialize` is the one
    constructor, and the template it is given is a value already in hand --
    never a name this function goes and resolves, which is what kept the judged
    revision and the appended one from being the same one.
    """
    return materialize(template, asked.binding, config, graph_id=asked.graph_id,
                       run_id=run_id, created_at=created_at)


def _gated(checked: GraphTemplate | None) -> GraphTemplate:
    """The revision the gates ran on, or a refusal rather than a second read.

    `None` here would mean the transaction found no standing graph while the
    read before it found one -- impossible for an append-only record. If it
    ever became possible, the answer must not be to fetch the revision again:
    that is the whole defect this shape makes unrepresentable. What was judged
    is what is appended, and when what was judged is missing there is nothing
    to append.
    """
    if checked is None:
        raise ApiRefusal.fixed("store_error")
    return checked


def _servable_pair(
        registry: AdapterRegistry, bound: str, capability: str,
        arguments: Mapping[str, Any]) -> None:
    """One verdict for one (adapter, capability, arguments), whichever road asks.

    A plan and a proposal describe the same work, so they may not disagree about
    whether that work can be carried out. They did. The graph route asked the
    registry what it recorded for the pair; the proposal route asked only
    whether the manifest named the capability, and the registry's own
    validation is a no-op for an adapter that declared no schema -- so a
    proposal reached Confirm through an adapter that never said how it reads
    those arguments. The other direction disagreed on the WORD: a capability
    this API's registry does not carry answered `contract_invalid` on one road
    and `capability_unsupported` on the other.

    So both roads ask this, in this order, and the order is the taxonomy:

    1. the frozen API must carry an argument schema for the capability at all;
    2. the pair must serve it through the one family this API speaks;
    3. the payload must satisfy that pair's schema.

    The first two are `capability_unsupported`: this build cannot carry out
    that work, whatever the request said. The third is `contract_invalid`: the
    work is servable and these particular values are not.
    """
    if capability not in ARGUMENT_SCHEMAS:
        raise UnsupportedCapability(
            "the frozen command API carries no argument schema for this capability")
    if registry.argument_schema(bound, capability) != COMMAND_ARGUMENT_SCHEMA:
        raise UnsupportedCapability(
            "bound adapter does not serve this capability through the "
            "argument schema this API speaks")
    try:
        registry.validate_arguments(bound, capability, arguments)
    except AdapterContractError:
        # The registry judged; naming the answer in the frozen HTTP vocabulary
        # is this boundary's job, and a payload that does not satisfy its
        # schema is exactly `contract_invalid`.
        raise ApiRefusal.fixed("contract_invalid") from None


def _bindings(config: Mapping[str, Any]) -> dict[str, str]:
    """Treat an invalid durable binding as corruption, never caller input."""
    try:
        return frozen_config_bindings(config)
    except ContractError:
        raise CorruptRun("frozen configuration has invalid instance bindings") from None


def _task(config: Mapping[str, Any]) -> TaskBinding | None:
    """Treat an invalid durable task binding as corruption, never caller input.

    `_bindings`' rule for the other key a frozen configuration carries.
    `materialize` reads it through the same strict reader and would refuse it
    a moment later -- as a CONTRACT fault, which is the wrong word for bytes
    the caller never sent.
    """
    try:
        return frozen_config_task(config)
    except ContractError:
        raise CorruptRun("frozen configuration has an invalid task binding") from None


def work_scope_admits(nodes, task: TaskBinding | None) -> None:
    """Refuse a plan whose steps would write outside this run's own task.

    A step's ``work_scope`` places its work at ``work/_tasks/<scope>/<item>``
    (`harness_workspace.work_parts`). So a step naming a scope this run is not
    bound to would write into ANOTHER task's directory, a task-less plan naming
    one would too, and a task-bound plan naming none would file its work among
    task-less history. The run's frozen task binding is the one authority on
    which task it belongs to; a plan agrees with it exactly or is not admitted.

    Asked of the plan that is about to be WRITTEN -- a materialized probe, or a
    submitted graph -- because that is what reaches a child, and never of a plan
    that already stands: a comparison road re-materializes only to compare bytes,
    and an admission rule there would re-judge a journal frozen before it existed.

    Args:
        nodes: The steps of the plan this run is about to be given.
        task: The task this run binds, or ``None`` when it binds none.

    Raises:
        TemplateError: A step's scope disagrees with the binding; the refusal
            names the step, what it said and what the run is bound to. It is a
            `ContractError`, so the wire word is ``contract_invalid``.
    """
    for node in nodes:
        refused = work_scope_disagreement(node.payload(), task)
        if refused is not None:
            raise TemplateError(f"step {node.node_id!r} {refused}")
