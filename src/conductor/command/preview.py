"""CLI-only dispatch preview: create a run, propose one dispatch, inspect it.

This is the Day-1 control-loop gate. It creates or opens a run with a frozen
config, asks the fixed CommandService for one dispatch ActionProposal bound to a
configured instance, and returns the canonical preview with its preview_digest
for inspection. It prepares nothing, executes nothing, and spawns no process:
the proposal seam is upstream of preparation, and this module never crosses it.

The scenario is fixed and self-contained so the preview is reproducible: the same
frozen config, the same deterministic ids and clock, and the same request every
time, which is what lets a reader trust the printed preview_digest. What a caller
chooses is only the instance (and, to exercise the binding, the adapter it claims
drives that instance) -- and neither is trusted over the frozen config: an unknown
instance or a mismatched adapter is refused by the same seam MAJOR-1 fixed.

The run directory is state too, and it is trusted no further. The preview's run
id is fixed, so a run at that identity may be one this command never created; it
is replayed and checked against the constants below before a single record is
appended, and a run that disagrees on any of them is refused with its history
untouched. Reopening the preview's own run stays free: the proposal is immutable
and identical, so the store recognises the retry and writes nothing.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .adapters import (
    AdapterContractError,
    AdapterManifest,
    AdapterObservation,
    AdapterRegistry,
)
from .contracts import RunEnvelope, _freeze_json, canonical_json
from .run_store import RecoveredRun, RunExists, RunStore, StoreError, snapshot_digest
from .service import CommandService, ServiceError

#: The one frozen configuration the preview run pins. Its instances section is the
#: authority the service derives each instance's adapter from.
FROZEN_CONFIG: Mapping[str, Any] = {
    "cycle": {"id": "preview-orbit", "phases": ["dispatch"]},
    "instances": [
        {"id": "claude-dev", "adapter": "claude-code"},
    ],
}

#: The instance the preview proposes against unless the caller names another.
DEFAULT_INSTANCE = "claude-dev"

#: The frozen configuration in the shape `RunStore` replays a stored one, so a
#: found run's durable configuration can be compared against this module's own
#: constant directly, structure to structure, and not through its digest alone.
_REPLAYED_FROZEN_CONFIG = _freeze_json(dict(FROZEN_CONFIG))

_RUN_ID = "preview-run"
_ATTEMPT_ID = "preview-attempt"
_NOW = "2026-08-11T00:00:00Z"
_ARGUMENTS: Mapping[str, Any] = {"handoff": "preview-packet"}
_SCOPE = ("src",)
_PROPOSED_BY = "preview"
_RATIONALE = "Day-1 preview: propose one dispatch and inspect its canonical form."
_TIMEOUT_SECONDS = 900


class PreviewError(RuntimeError):
    """The preview flow cannot produce a proposal to inspect."""


class _PreviewAdapter:
    """A minimal registered adapter for the preview; it never prepares or executes.

    It exists so the registry can judge the bound adapter's declared capabilities.
    Its prepare/execute/verify seams are present because registration requires
    them, and they refuse outright: the preview never reaches preparation.
    """

    def __init__(self) -> None:
        self.manifest = AdapterManifest(
            adapter_id="claude-code", display_name="Claude Code", vendor="Anthropic",
            version="1", capabilities=("observe", "dispatch"), docs_url="")

    def observe(self, instance_id: str, run_id: str) -> AdapterObservation:
        return AdapterObservation(
            adapter_id="claude-code", instance_id=instance_id, run_id=run_id,
            observed_at=_NOW, health="ready", available_capabilities=("observe", "dispatch"))

    def prepare(self, request: Any) -> Any:
        raise PreviewError("the preview never prepares an action")

    def execute(self, prepared: Any) -> Any:
        raise PreviewError("the preview never executes an action")

    def verify(self, request: Any, result: Any) -> Any:
        raise PreviewError("the preview never verifies an action")


_ABSENT: Any = object()
"""Stands for a key a row does not carry, which `None` cannot stand for."""


def _shown(row: Mapping[str, Any], name: str) -> str:
    """Render one field for the refusal message, saying `absent` when it is missing."""
    value = row.get(name, _ABSENT)
    return "absent" if value is _ABSENT else repr(value)


def _run_differences(found: RecoveredRun, expected: RunEnvelope) -> tuple[str, ...]:
    """Name every fact on which a found run disagrees with the preview's frozen one.

    The authority is the whole serialized envelope: the two rows must be equal,
    so a run whose durable envelope differs at all is not this preview's run.
    The per-field walk below only explains that disagreement, and it reads both
    rows through `_ABSENT` rather than `dict.get`, because `get` answers None
    both for a key that is missing and for a key that holds null — two
    different durable facts, and the contracts keep unknown fields on purpose.

    The fields are not listed here: they are whatever `RunEnvelope` serializes,
    so a field added to the contract is compared without this function learning
    about it. The configuration is compared as well as its digest, because
    "the digest matches" is a statement about sha256 and this is a statement
    about the configuration the service is about to work from.
    """
    found_row, expected_row = found.envelope.as_dict(), expected.as_dict()
    differences = []
    if found_row != expected_row:
        differences = [
            f"{name}: expected {_shown(expected_row, name)}, "
            f"found {_shown(found_row, name)}"
            for name in sorted(set(expected_row) | set(found_row))
            if expected_row.get(name, _ABSENT) != found_row.get(name, _ABSENT)
        ]
        if not differences:      # unequal rows the field walk could not name
            differences = ["envelope: the stored envelope is not this preview's"]
    if found.config != _REPLAYED_FROZEN_CONFIG:
        differences.append("config: the stored configuration is not the frozen one")
    return tuple(differences)


def render_dispatch_preview(
        project_root: str, *, instance_id: str = DEFAULT_INSTANCE,
        adapter_id: str | None = None) -> str:
    """Create or open the preview run, propose one dispatch, return its canonical form.

    Args:
        project_root: The directory holding (or to hold) ``conductor/runs``.
        instance_id: The configured instance to propose against.
        adapter_id: An adapter the caller claims drives the instance, cross-checked
            against the frozen config; None trusts the config's binding outright.

    Returns:
        The canonical JSON of the ActionProposal, including its preview_digest.

    Raises:
        PreviewError: The run cannot be created, a run already stands at the
            preview's identity without being the preview's own run, the instance
            is unknown, the claimed adapter mismatches the binding, or the
            capability is not declared by the bound adapter.
    """
    store = RunStore(project_root)
    envelope = RunEnvelope(
        run_id=_RUN_ID, cycle_id="preview-orbit", created_at=_NOW,
        config_digest=snapshot_digest(FROZEN_CONFIG), mode="propose")
    try:
        try:
            store.create_run(envelope, FROZEN_CONFIG)
        except RunExists:
            # A run already at this identity is state the preview FOUND, not state
            # it froze. Replay it read-only and hold it against this module's own
            # constants BEFORE anything is appended: only the very same preview run
            # may be reopened, and one that is not keeps its history byte for byte.
            differences = _run_differences(store.read(_RUN_ID), envelope)
            if differences:
                raise PreviewError(
                    f"run {_RUN_ID!r} already exists and is not this preview's run, "
                    "so nothing was proposed into it: " + "; ".join(differences))
        service = CommandService(
            store, AdapterRegistry([_PreviewAdapter()]),
            clock=lambda: _NOW, ids=lambda purpose: f"{purpose}-{_RUN_ID}")
        proposal = service.propose(
            run_id=_RUN_ID, instance_id=instance_id, adapter_id=adapter_id,
            attempt_id=_ATTEMPT_ID, capability="dispatch", arguments=_ARGUMENTS,
            scope=_SCOPE, proposed_by=_PROPOSED_BY, rationale=_RATIONALE,
            timeout_seconds=_TIMEOUT_SECONDS)
    except (ServiceError, AdapterContractError, StoreError) as e:
        raise PreviewError(str(e)) from e
    return canonical_json(proposal)
