"""Observe/Propose service: the read side of December Command, and no more.

The service has two doors. `observe` turns a registered adapter's validated
health and capability facts into a durable ObservationRecord while discarding
untrusted prose, and it works in every control mode. `propose`
turns a lane's intent into an immutable ActionProposal, and it is refused in
Observe mode. Neither door prepares an action, executes one, spawns a process,
or writes through a browser: preparation begins only after a proposal is
confirmed, which is past this seam. Ids and timestamps arrive through injected,
deterministic providers, so nothing here reads a hidden clock or invents an id.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any

from .adapters import AdapterRegistry, UnsupportedCapability
from .contracts import (
    ABSENT,
    ActionProposal,
    ControlMode,
    ObservationRecord,
    PROPOSAL_INPUT_BINDING,
    ContractError,
    frozen_config_bindings,
)
from .dispatch import DispatchArgumentError
from .run_store import RunStore
from .new_work_admission import admit_new_work
from .task_contracts import frozen_config_task, work_scope_disagreement


class ServiceError(RuntimeError):
    """The service refuses an operation the authority ladder does not permit."""


def _hold_proposal_writes_in_its_task(recovered, run_id: str,
                                      arguments: Mapping[str, Any]) -> None:
    """A proposal's work item is filed under its OWN run's task, or under none.

    The plan doors hold a planned run to this already; a run that follows no
    graph reaches the proposal door with arguments its caller wrote, and a
    `work_scope` there is a directory path. So the rule the plans answer is
    asked here too, of every new proposal, graph or no graph -- one predicate,
    `task_contracts.work_scope_disagreement`, and never a second spelling.

    Raises:
        ServiceError: The arguments name a scope the run is not bound to, name
            one when the run binds no task, or name none when it binds one.
    """
    try:
        task = frozen_config_task(recovered.config)
    except ContractError:
        raise ServiceError(f"run {run_id!r} froze an invalid task binding") from None
    refused = work_scope_disagreement(arguments, task)
    if refused is not None:
        raise ServiceError(f"a proposal on run {run_id!r} {refused}")


def _hold_proposal_names_its_node(recovered, run_id: str,
                                  node_id: str | None) -> None:
    """A proposal on a PLANNED run says which step it carries out.

    An unbound proposal on a run that follows a graph is authority the plan
    never gave. Nothing downstream can hold it to a node's facts, its ceilings
    or its verifier -- and it silently MIS-RESOLVES that verifier, because both
    verifier doors key off the request's binding, so an unbound action on a
    verifier-carrying node falls back to the doer that was supposed to be
    checked by somebody else.

    A plan-less run is guarded by the graph's absence and is byte-identical to
    what it always was: runs without a graph existed before graphs did.

    Raises:
        ServiceError: The run follows a graph and the proposal names no node.
    """
    graph = next((row.value for row in recovered.records
                  if row.kind == "graph_definition"), None)
    if graph is not None and node_id is None:
        raise ServiceError(
            f"run {run_id!r} follows graph {graph.graph_id!r}; a proposal on a "
            "planned run must name the node it carries out")


class CommandService:
    """Bind one RunStore and one AdapterRegistry into the observe/propose seam."""

    def __init__(
            self, store: RunStore, registry: AdapterRegistry, *,
            clock: Callable[[], str], ids: Callable[[str], str]) -> None:
        self._store = store
        self._registry = registry
        self._clock = clock
        self._ids = ids

    def _bound_adapter(
            self, config: Mapping[str, Any], instance_id: str,
            adapter_id: str | None) -> str:
        """Derive the adapter the frozen config binds to `instance_id`, or refuse.

        The binding comes from the pinned frozen config, never from the caller: an
        instance the config does not declare is refused, and an adapter the caller
        names that is not the bound one is a mismatch. Both refusals happen here, so
        they precede every adapter seam and every durable append.
        """
        bindings = frozen_config_bindings(config)
        bound = bindings.get(instance_id)
        if bound is None:
            raise ServiceError(
                f"frozen config declares no instance {instance_id!r}; an unknown "
                "instance cannot be observed or proposed")
        if adapter_id is not None and adapter_id != bound:
            raise ServiceError(
                f"instance {instance_id!r} is bound to adapter {bound!r} by the "
                f"frozen config, not {adapter_id!r}")
        return bound

    def _append_proposal(self, recovered, bound: str, proposal: ActionProposal) -> None:
        """Standing IDs retain exact-repeat/conflict arbitration in the store."""
        standing = any(row.kind == "action_proposal" and
                       row.value.proposal_id == proposal.proposal_id
                       for row in recovered.records)
        if not standing:
            admit_new_work(self._store.project_root,
                           self._registry.argument_schema(bound, proposal.capability),
                           proposal.capability, proposal.arguments)
        self._store.append(proposal)

    def observe(
            self, *, run_id: str, instance_id: str, adapter_id: str | None = None,
            observation_id: str | None = None,
            evidence_refs: Iterable[str] = ()) -> ObservationRecord:
        """Persist one durable observation from the config-bound adapter, in any mode."""
        recovered = self._store.read(run_id)  # the run must already exist to be observed
        bound = self._bound_adapter(recovered.config, instance_id, adapter_id)
        try:
            observed = self._registry.observe(bound, instance_id, run_id)
        except Exception:
            raise ServiceError("adapter observe failed") from None
        record = ObservationRecord(
            observation_id=observation_id or self._ids("observation"),
            run_id=run_id,
            adapter_id=bound,
            instance_id=instance_id,
            observed_at=self._clock(),
            health=observed.health,
            available_capabilities=observed.available_capabilities,
            detail="",
            evidence_refs=tuple(evidence_refs),
        )
        self._store.append(record)
        return record

    def propose(
            self, *, run_id: str, instance_id: str, attempt_id: str,
            capability: str, arguments: Mapping[str, Any], scope: Iterable[str],
            proposed_by: str, rationale: str, timeout_seconds: int,
            adapter_id: str | None = None,
            node_id: str | None = None,
            proposal_id: str | None = None,
            proposed_at: str | None = None, feedback_ids=ABSENT) -> ActionProposal:
        """Persist one immutable proposal; refused in Observe, prepares nothing."""
        recovered = self._store.read(run_id)
        envelope = recovered.envelope
        if envelope.mode is ControlMode.OBSERVE:
            raise ServiceError(
                "propose is not permitted in observe mode; observe first, "
                "then raise the run to propose")
        _hold_proposal_names_its_node(recovered, run_id, node_id)
        # The adapter is derived from the pinned frozen config, so an unknown
        # instance or a mismatched adapter is refused before the manifest is read.
        bound = self._bound_adapter(recovered.config, instance_id, adapter_id)
        # controls() reads the manifest of the config-bound adapter, never the
        # adapter object and never the caller's choice, so a capability the bound
        # adapter does not declare cannot be laundered through a foreign manifest.
        if capability not in self._registry.controls(bound):
            raise UnsupportedCapability(
                f"adapter {bound!r} does not declare capability {capability!r}")
        try:
            self._registry.validate_arguments(bound, capability, arguments)
        except DispatchArgumentError as e:
            raise ServiceError(str(e)) from e
        _hold_proposal_writes_in_its_task(recovered, run_id, arguments)
        proposal = ActionProposal(
            proposal_id=proposal_id or self._ids("proposal"),
            run_id=run_id,
            attempt_id=attempt_id,
            instance_id=instance_id,
            capability=capability,
            arguments=arguments,
            scope=tuple(scope),
            proposed_by=proposed_by,
            proposed_at=proposed_at or self._clock(),
            timeout_seconds=timeout_seconds,
            rationale=rationale,
            config_digest=envelope.config_digest,
            node_id=node_id, feedback_ids=feedback_ids,
            input_binding=(
                PROPOSAL_INPUT_BINDING
                if capability in ("dispatch", "review") and self._registry.argument_schema(
                    bound, capability) == "deep-arguments-v1" else ABSENT),
        )
        self._append_proposal(recovered, bound, proposal)
        return proposal
