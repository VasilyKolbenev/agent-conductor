"""Observe/Propose service: the read side of December Command, and no more.

The service has two doors. `observe` turns a registered adapter's live report
into a durable ObservationRecord, and it works in every control mode. `propose`
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
from .contracts import ActionProposal, ControlMode, ObservationRecord
from .run_store import RunStore


class ServiceError(RuntimeError):
    """The service refuses an operation the authority ladder does not permit."""


class CommandService:
    """Bind one RunStore and one AdapterRegistry into the observe/propose seam."""

    def __init__(
            self, store: RunStore, registry: AdapterRegistry, *,
            clock: Callable[[], str], ids: Callable[[str], str]) -> None:
        self._store = store
        self._registry = registry
        self._clock = clock
        self._ids = ids

    def observe(
            self, *, run_id: str, adapter_id: str, instance_id: str,
            observation_id: str | None = None,
            evidence_refs: Iterable[str] = ()) -> ObservationRecord:
        """Persist one durable observation from a registered adapter, in any mode."""
        self._store.read(run_id)  # the run must already exist to be observed
        observed = self._registry.observe(adapter_id, instance_id, run_id)
        record = ObservationRecord(
            observation_id=observation_id or self._ids("observation"),
            run_id=run_id,
            adapter_id=observed.adapter_id,
            instance_id=observed.instance_id,
            observed_at=observed.observed_at,
            health=observed.health,
            available_capabilities=observed.available_capabilities,
            detail=observed.detail,
            evidence_refs=tuple(evidence_refs),
        )
        self._store.append(record)
        return record

    def propose(
            self, *, run_id: str, adapter_id: str, instance_id: str, attempt_id: str,
            capability: str, arguments: Mapping[str, Any], scope: Iterable[str],
            proposed_by: str, rationale: str, timeout_seconds: int,
            proposal_id: str | None = None,
            proposed_at: str | None = None) -> ActionProposal:
        """Persist one immutable proposal; refused in Observe, prepares nothing."""
        envelope = self._store.read(run_id).envelope
        if envelope.mode is ControlMode.OBSERVE:
            raise ServiceError(
                "propose is not permitted in observe mode; observe first, "
                "then raise the run to propose")
        # controls() reads the manifest reviewed at registration, never the adapter
        # object, so an undeclared capability is refused before any seam could run.
        if capability not in self._registry.controls(adapter_id):
            raise UnsupportedCapability(
                f"adapter {adapter_id!r} does not declare capability {capability!r}")
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
        )
        self._store.append(proposal)
        return proposal
