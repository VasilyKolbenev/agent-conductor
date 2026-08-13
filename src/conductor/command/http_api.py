"""The six frozen Cockpit command routes, independent of an HTTP server.

The facade accepts ordered raw header pairs and raw JSON bytes.  It emits only
validated contract payloads or closed :class:`ApiRefusal` envelopes; adapters
are never called directly and this boundary never executes an action.
"""
from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from .adapters import AdapterContractError, AdapterRegistry, UnsupportedCapability
from .api_contracts import (
    ARGUMENT_SCHEMAS,
    ApiRefusal,
    parse_confirmation,
    parse_decision,
    parse_proposal,
    refusal_from_exception,
)
from .containment import run_route_violations
from .contracts import ContractError, frozen_config_bindings
from .http_transport import (
    CommandSession,
    HttpRefusal,
    command_content_length,
    validate_command_host,
)
from .run_store import CorruptRun, RecordConflict, RunStore
from .runtime import Budget, ControlRuntime
from .service import CommandService


PRODUCT_COMMAND_BUDGET = Budget(
    max_actions=8,
    max_action_seconds=3600,
    max_confirmation_age_seconds=3600,
)

COMMAND_ROUTES = (
    ("GET", "/command/session"),
    ("GET", "/command/runs/<run_id>"),
    ("GET", "/command/runs/<run_id>/controls"),
    ("POST", "/command/runs/<run_id>/proposals"),
    ("POST", "/command/runs/<run_id>/actions"),
    ("POST", "/command/runs/<run_id>/decisions"),
)

_RUN_ROUTE = re.compile(
    r"/command/runs/([A-Za-z0-9][A-Za-z0-9._-]{0,127})"
    r"(?:/(controls|proposals|actions|decisions))?\Z")


@dataclass(frozen=True)
class CommandResponse:
    """One JSON response; the server owns byte serialization and headers."""

    status: int
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class _Route:
    name: str
    run_id: str | None = None


class CommandApi:
    """Bind transport, typed route authority, store, service, and authorization."""

    def __init__(
            self, store: RunStore, registry: AdapterRegistry, *,
            session: CommandSession, budget: Budget,
            clock: Callable[[], str], ids: Callable[[str], str],
            publish_run: Callable[[str], None]) -> None:
        if not isinstance(store, RunStore) or not isinstance(registry, AdapterRegistry):
            raise TypeError("CommandApi requires a RunStore and AdapterRegistry")
        if not isinstance(session, CommandSession) or not isinstance(budget, Budget):
            raise TypeError("CommandApi requires a CommandSession and Budget")
        if not all(callable(value) for value in (clock, ids, publish_run)):
            raise TypeError("CommandApi providers must be callable")
        self._store = store
        self._registry = registry
        self._session = session
        self._budget = budget
        self._clock = clock
        self._ids = ids
        self._publish_run = publish_run
        self._service = CommandService(store, registry, clock=clock, ids=ids)
        self._runtime = ControlRuntime(store, registry, clock=clock, ids=ids)

    @property
    def runtime(self) -> ControlRuntime:
        """Expose the same runtime whose fresh authorization grant execution needs."""
        return self._runtime

    def handle(
            self, method: str, target: str,
            raw_headers: Iterable[tuple[str, str]], raw_body: bytes = b"") -> CommandResponse:
        """Dispatch one command request and normalize every expected refusal."""
        try:
            route = _match_route(method, urlsplit(target).path)
            pairs = tuple(raw_headers)
            if method == "GET":
                host = validate_command_host(pairs, self._session.allowed_hosts)
                return self._get(route, host)
            try:
                length = command_content_length(pairs)
            except HttpRefusal:
                length = None
            bounded = raw_body if length == len(raw_body) else b""
            body = self._session.validate_mutation(pairs, bounded)
            return self._post(route, body)
        except ApiRefusal as refusal:
            return CommandResponse(refusal.status, refusal.as_dict())
        except Exception as error:
            try:
                refusal = refusal_from_exception(error)
            except TypeError:
                raise
            return CommandResponse(refusal.status, refusal.as_dict())

    def _get(self, route: _Route, host: str) -> CommandResponse:
        if route.name == "session":
            return CommandResponse(200, self._session.session_response(host))
        assert route.run_id is not None
        self._hold_route(route.run_id)
        recovered = self._store.read(route.run_id)
        if route.name == "run":
            return CommandResponse(200, _recovered_payload(recovered))
        return CommandResponse(200, self._controls(recovered.config))

    def _post(self, route: _Route, body: Mapping[str, Any]) -> CommandResponse:
        assert route.run_id is not None
        if route.name == "proposals":
            return self._propose(route.run_id, body)
        if route.name == "actions":
            return self._authorize(route.run_id, body)
        return self._decide(route.run_id, body)

    def _propose(self, run_id: str, body: Mapping[str, Any]) -> CommandResponse:
        declared = {
            capability for manifest in self._registry.manifests()
            for capability in manifest.capabilities}
        submitted = parse_proposal(body, adapter_capabilities=declared)
        self._hold_route(run_id)
        initial = self._store.read(run_id)
        bound = self._bound_adapter(initial.config, run_id, submitted.instance_id)
        if submitted.capability not in self._registry.controls(bound):
            raise UnsupportedCapability("bound adapter lacks submitted capability")
        with self._store.transaction():
            recovered = self._store.read(run_id)
            prior_ids = {
                row.value.proposal_id for row in recovered.records
                if row.kind == "action_proposal"}
            proposal = self._service.propose(
                run_id=run_id, instance_id=submitted.instance_id,
                attempt_id=submitted.attempt_id, capability=submitted.capability,
                arguments=submitted.arguments, scope=submitted.scope,
                proposed_by=submitted.proposed_by, rationale=submitted.rationale,
                timeout_seconds=submitted.timeout_seconds,
                adapter_id=submitted.adapter_id)
            created = proposal.proposal_id not in prior_ids
        if created:
            self._publish_run(run_id)
        return CommandResponse(201 if created else 200, proposal.as_dict())

    def _authorize(self, run_id: str, body: Mapping[str, Any]) -> CommandResponse:
        submitted = parse_confirmation(body)
        self._hold_route(run_id)
        confirmation = submitted.build(
            confirmation_id=self._ids("confirmation"), run_id=run_id,
            confirmed_at=self._clock())
        authorization = self._runtime.authorize(confirmation, budget=self._budget)
        if authorization.record_created:
            self._publish_run(run_id)
        return CommandResponse(
            201 if authorization.record_created else 200,
            authorization.request.as_dict())

    def _decide(self, run_id: str, body: Mapping[str, Any]) -> CommandResponse:
        submitted = parse_decision(body)
        self._hold_route(run_id)
        with self._store.transaction():
            recovered = self._store.read(run_id)
            prior = next((
                row.value for row in recovered.records
                if row.kind == "decision"
                and row.value.receipt_id == submitted.receipt_id), None)
            decided_at = prior.decided_at if prior is not None else self._clock()
            decision = submitted.build(
                run_id=run_id, decided_at=decided_at,
                config_digest=recovered.envelope.config_digest)
            if prior is not None:
                if prior != decision:
                    raise RecordConflict("decision identity records different facts")
                created = False
                decision = prior
            else:
                created = self._store.append(decision)
        if created:
            self._publish_run(run_id)
        return CommandResponse(201 if created else 200, decision.as_dict())

    def _hold_route(self, run_id: str) -> None:
        if run_route_violations(self._store, run_id):
            raise ApiRefusal.fixed("route_unsafe")

    def _bound_adapter(
            self, config: Mapping[str, Any], run_id: str, instance_id: str) -> str:
        bindings = _bindings(config)
        bound = bindings.get(instance_id)
        if bound is None:
            raise ApiRefusal.service_missing_instance(run_id, instance_id)
        return bound

    def _controls(self, config: Mapping[str, Any]) -> dict[str, object]:
        rows = []
        for instance_id, adapter_id in sorted(_bindings(config).items()):
            try:
                declared = self._registry.controls(adapter_id)
            except AdapterContractError:
                declared = ()
            rows.append({
                "instance_id": instance_id,
                "adapter_id": adapter_id,
                "controls": sorted(set(declared) & set(ARGUMENT_SCHEMAS)),
            })
        return {"instances": rows}


def _match_route(method: str, path: str) -> _Route:
    if method not in {"GET", "POST"}:
        known = path == "/command/session" or _RUN_ROUTE.fullmatch(path) is not None
        raise ApiRefusal.fixed("method_not_allowed" if known else "route_not_found")
    if path == "/command/session":
        if method != "GET":
            raise ApiRefusal.fixed("method_not_allowed")
        return _Route("session")
    matched = _RUN_ROUTE.fullmatch(path)
    if matched is None:
        raise ApiRefusal.fixed("route_not_found")
    run_id, tail = matched.groups()
    name = tail or "run"
    expected = "GET" if name in {"run", "controls"} else "POST"
    if method != expected:
        raise ApiRefusal.fixed("method_not_allowed")
    return _Route(name, run_id)


def _recovered_payload(recovered) -> dict[str, object]:
    config = _plain_json(recovered.config)
    records = [
        {"record_type": row.kind, "record": row.value.as_dict()}
        for row in recovered.records]
    return {
        "run": recovered.envelope.as_dict(),
        "config": config,
        "records": records,
        "warnings": list(recovered.warnings),
    }


def _plain_json(value: object) -> object:
    """Copy a frozen JSON graph into the plain containers an HTTP encoder owns."""
    if isinstance(value, Mapping):
        return {key: _plain_json(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain_json(item) for item in value]
    return value


def _bindings(config: Mapping[str, Any]) -> dict[str, str]:
    """Treat an invalid durable binding as corruption, never caller input."""
    try:
        return frozen_config_bindings(config)
    except ContractError:
        raise CorruptRun("frozen configuration has invalid instance bindings") from None
