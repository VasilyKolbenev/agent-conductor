"""The seven frozen Cockpit command routes, independent of an HTTP server.

The facade accepts ordered raw header pairs and raw JSON bytes.  It emits only
validated contract payloads or closed :class:`ApiRefusal` envelopes; adapters
are never called directly and no request thread here performs an effect.

A Confirm records the durable action request and answers with it. When a
server-owned :class:`ExecutionCoordinator` is attached, that recorded action is
handed to its bounded queue and a worker thread performs the effect afterwards,
so the response never waits on an adapter. With no coordinator attached this
boundary executes nothing at all.

The controls route answers with two arrays: the run's own instance bindings, and
the reviewed provider roster this build was given. The roster is descriptors
only -- the boundary resolves nothing, reads no path, and holds no adapter of its
own -- and it is projected through the one reviewed provider projection.
"""
from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from .adapters import AdapterContractError, AdapterRegistry, UnsupportedCapability
from .adapters.provider import ProviderContract, provider_projection
from .api_contracts import (
    ARGUMENT_SCHEMAS,
    ApiRefusal,
    GraphInput,
    parse_confirmation,
    parse_decision,
    parse_graph,
    parse_proposal,
    refusal_from_exception,
)
from .containment import run_route_violations
from .contracts import ContractError, frozen_config_bindings
from .coordinator import ExecutionCoordinator
from .graph_projection import graph_payload
from .http_transport import (
    CommandSession,
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
    ("POST", "/command/runs/<run_id>/graph"),
)

_RUN_ROUTE = re.compile(
    r"/command/runs/([A-Za-z0-9][A-Za-z0-9._-]{0,127})"
    r"(?:/(controls|proposals|actions|decisions|graph))?\Z")


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
            publish_run: Callable[[str], None],
            providers: Iterable[ProviderContract] = ()) -> None:
        if not isinstance(store, RunStore) or not isinstance(registry, AdapterRegistry):
            raise TypeError("CommandApi requires a RunStore and AdapterRegistry")
        if not isinstance(session, CommandSession) or type(budget) is not Budget:
            raise TypeError("CommandApi requires a CommandSession and Budget")
        if not all(callable(value) for value in (clock, ids, publish_run)):
            raise TypeError("CommandApi providers must be callable")
        # Reviewed descriptors only, rebuilt by the projection before one field of
        # them is read; the boundary never resolves or probes a provider itself.
        self._providers = tuple(providers)
        self._store = store
        self._registry = registry
        self._session = session
        self._budget = Budget(
            budget.max_actions, budget.max_action_seconds,
            budget.max_confirmation_age_seconds)
        self._clock = clock
        self._ids = ids
        self._publish_run = publish_run
        self._service = CommandService(store, registry, clock=clock, ids=ids)
        self._runtime = ControlRuntime(
            store, registry, clock=clock, ids=ids, notify=publish_run)
        self._execution: ExecutionCoordinator | None = None

    @property
    def runtime(self) -> ControlRuntime:
        """Expose the same runtime whose fresh authorization grant execution needs."""
        return self._runtime

    @property
    def execution(self) -> ExecutionCoordinator | None:
        """The bound coordinator, or None while this API executes nothing at all."""
        return self._execution

    def attach_execution(self, execution: ExecutionCoordinator) -> None:
        """Bind the one server-owned coordinator that may spend this API's grants.

        The coordinator must already hold THIS api's runtime: execution authority
        is that runtime's memory-only grant, so a coordinator built over any other
        runtime could never execute what this boundary authorized. Binding happens
        once; this boundary never builds, starts, or stops a worker itself.
        """
        if not isinstance(execution, ExecutionCoordinator):
            raise TypeError("attach_execution requires an ExecutionCoordinator")
        if self._execution is not None:
            raise ValueError("a command API binds exactly one execution coordinator")
        if execution.runtime is not self._runtime:
            raise ValueError(
                "the coordinator must hold the runtime that authorizes on this API")
        self._execution = execution

    def handle(
            self, method: str, target: str,
            raw_headers: Iterable[tuple[str, str]], raw_body: bytes = b"") -> CommandResponse:
        """Dispatch one command request and normalize every expected refusal."""
        try:
            route = _match_route(method, _target_path(target))
            pairs = tuple(raw_headers)
            if method == "GET":
                host = validate_command_host(pairs, self._session.allowed_hosts)
                return self._get(route, host)
            body = self._session.validate_mutation(pairs, raw_body)
            return self._post(route, body)
        except ApiRefusal as refusal:
            return CommandResponse(refusal.status, refusal.as_dict())
        except Exception as error:
            try:
                refusal = refusal_from_exception(error)
            except TypeError:
                raise
            return CommandResponse(refusal.status, refusal.as_dict())

    def body_length(
            self, target: str,
            raw_headers: Iterable[tuple[str, str]]) -> int:
        """Hold the exact POST route and transport headers before a body read."""
        _match_route("POST", _target_path(target))
        return self._session.body_length(raw_headers)

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
        if route.name == "graph":
            return self._write_graph(route.run_id, body)
        return self._decide(route.run_id, body)

    def _write_graph(self, run_id: str, body: Mapping[str, Any]) -> CommandResponse:
        """Write the one graph a run follows; a run never edits the plan it has.

        The stable ``graph_id`` is the caller's, which is what makes an exact
        retry findable -- and it is found before the clock is read, so a repeat
        answers with the ``created_at`` the first write settled instead of
        minting a second identity's worth of facts under one id.
        """
        submitted = parse_graph(body)
        self._hold_route(run_id)
        self._bindings_are_servable(self._store.read(run_id).config, run_id, submitted)
        with self._store.transaction():
            self._hold_route(run_id)
            recovered = self._store.read(run_id)
            standing = next((
                row.value for row in recovered.records
                if row.kind == "graph_definition"
                and row.value.graph_id == submitted.graph_id), None)
            graph = submitted.build(
                run_id=run_id,
                created_at=self._clock() if standing is None else standing.created_at)
            if standing is not None:
                if standing != graph:
                    raise RecordConflict("graph identity records different facts")
                created, graph = False, standing
            else:
                # A graph under ANOTHER id is refused here, by the store's own
                # one-graph-per-run relation, which names the plan standing.
                created = self._store.append(graph)
        if created:
            self._publish_run(run_id)
        return CommandResponse(201 if created else 200, graph.as_dict())

    def _bindings_are_servable(
            self, config: Mapping[str, Any], run_id: str,
            submitted: GraphInput) -> None:
        """A plan may only name work this run and this build can carry out.

        The graph contract deliberately holds no provider: which adapter serves
        an instance is the run's frozen configuration's fact. So the plan is
        held to that configuration HERE, once, before it becomes durable --
        rather than becoming a stored plan whose every proposal is refused.
        """
        for node in submitted.nodes:
            if node.capability is None:
                continue
            bound = self._bound_adapter(config, run_id, node.instance_id)
            if node.capability not in self._registry.controls(bound):
                raise UnsupportedCapability("bound adapter lacks a node capability")

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
            self._hold_route(run_id)
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
                adapter_id=submitted.adapter_id, node_id=submitted.node_id)
            created = proposal.proposal_id not in prior_ids
        if created:
            self._publish_run(run_id)
        return CommandResponse(201 if created else 200, proposal.as_dict())

    def _authorize(self, run_id: str, body: Mapping[str, Any]) -> CommandResponse:
        """Record the confirmation and answer; the effect happens off this thread.

        The admission slot is claimed INSIDE authorize, on the one path that is
        about to append a fresh request and immediately before it does, so the two
        are bound: a full execution queue refuses the Confirm with nothing durable
        written, and a request that did become durable is already held by a live
        reservation a worker will drain. A duplicate Confirm appends nothing and
        therefore reaches no admission at all: it returns the same request through
        a full queue, queues nothing, and causes no second effect.
        """
        submitted = parse_confirmation(body)
        self._hold_route(run_id)
        confirmation = submitted.build(
            confirmation_id=self._ids("confirmation"), run_id=run_id,
            confirmed_at=self._clock())
        claimed: list[Any] = []
        try:
            authorization = self._runtime.authorize(
                confirmation, budget=self._budget,
                admit=None if self._execution is None else (
                    lambda: claimed.append(self._execution.claim())))
            if authorization.record_created:
                self._publish_run(run_id)
                for slot in claimed:
                    slot.place(authorization)
        finally:
            for slot in claimed:
                slot.release()
        return CommandResponse(
            201 if authorization.record_created else 200,
            authorization.request.as_dict())

    def _decide(self, run_id: str, body: Mapping[str, Any]) -> CommandResponse:
        submitted = parse_decision(body)
        self._hold_route(run_id)
        with self._store.transaction():
            self._hold_route(run_id)
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
        """Answer the run's instance controls, plus the reviewed provider roster.

        The two arrays answer two different questions and are kept apart. An
        ``instances`` row is about THIS RUN's frozen binding; a ``providers`` row
        is about the build and the machine, and carries only what
        ``provider_projection`` admits. A consumer joins them by identity, never
        by a displayed label.
        """
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
        return {"instances": rows, "providers": provider_projection(self._providers)}


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


def _target_path(target: str) -> str:
    """Accept an exact origin-form path; command routes have no query surface."""
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        raise ApiRefusal.fixed("route_not_found")
    return parsed.path


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
        # The one part of this response that is not a durable record verbatim:
        # the plan, the digest computed over it, and the position computed from
        # the records above. Nothing here is stored, so nothing here can drift.
        "graph": graph_payload(recovered),
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
