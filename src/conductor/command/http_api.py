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
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from .adapters import AdapterContractError, AdapterRegistry, UnsupportedCapability
from .adapters.provider import ProviderContract, provider_projection
from .api_contracts import (
    ARGUMENT_SCHEMAS,
    COMMAND_ARGUMENT_SCHEMA,
    ApiRefusal,
    GraphInput,
    TemplateRef,
    canonical_arguments,
    parse_artifact,
    parse_confirmation,
    parse_decision,
    parse_graph,
    parse_graph_from_template,
    parse_proposal,
    parse_template,
    refusal_from_exception,
)
from .command_routes import (
    COMMAND_ROUTES,
    Route as _Route,
    match_route as _match_route,
    target_path as _target_path,
)
from .containment import run_route_violations
from .artifacts import ArtifactDocument
from .contracts import (
    ActionRequest,
    ActionResultReceipt,
    ContractError,
    RunEnvelope,
    _id,
    frozen_config_bindings,
    frozen_config_models,
)
from .coordinator import ExecutionCoordinator
from .graph_definition import GraphDefinition, GraphNode
from .graph_projection import graph_payload
from .graph_template import (
    TEMPLATE_DIR,
    GraphTemplate,
    TemplateError,
    load_template,
    materialize,
)
from .http_transport import (
    CommandSession,
    validate_command_host,
)
from .run_store import CorruptRun, RecordConflict, RunStore, StoreError
from .template_store import TemplateStore
from .runtime import Budget, ControlRuntime
from .service import CommandService
from . import studio_routes
from .studio_routes import (
    plain_json as _plain_json,
    recovered_payload as _recovered_payload,
    standing_graph as _standing_graph,
)


PRODUCT_COMMAND_BUDGET = Budget(
    max_actions=8,
    max_action_seconds=3600,
    max_confirmation_age_seconds=3600,
)

#: The one availability state in which this build can reach a provider at
#: all. A word from `AVAILABILITY_STATES`, compared as a STATE: what makes a
#: binding admissible is what this build resolved about the transport, never
#: which product is behind it.
_REACHABLE = "available"
#: The instant a materialization that is NOT about to be written is built on.
#: Two of the three callers want no timestamp -- one is judging servability
#: before the transaction, one is rebuilding a candidate to compare against a
#: record that already carries one -- and a plan built to be thrown away must
#: not read a clock, or a comparison would depend on when it was made.
_PROBE_AT = "1970-01-01T00:00:00Z"
#: The identity a plan built only to be judged wears. A run's real plan is named
#: by the server when it is about to be written; this one is thrown away, and
#: giving it a fixed name keeps a judgement from depending on an id generator.
_PROBE_GRAPH = "graph-open-run-probe"


@dataclass(frozen=True)
class CommandResponse:
    """One JSON response; the server owns byte serialization and headers."""

    status: int
    payload: Mapping[str, Any]


class CommandApi:
    """Bind transport, typed route authority, store, service, and authorization."""

    def __init__(
            self, store: RunStore, registry: AdapterRegistry, *,
            session: CommandSession, budget: Budget,
            clock: Callable[[], str], ids: Callable[[str], str],
            publish_run: Callable[[str], None],
            providers: Iterable[ProviderContract] = (),
            templates: TemplateStore | None = None) -> None:
        if not isinstance(store, RunStore) or not isinstance(registry, AdapterRegistry):
            raise TypeError("CommandApi requires a RunStore and AdapterRegistry")
        if templates is not None and not isinstance(templates, TemplateStore):
            raise TypeError("CommandApi templates must be a TemplateStore")
        if not isinstance(session, CommandSession) or type(budget) is not Budget:
            raise TypeError("CommandApi requires a CommandSession and Budget")
        if not all(callable(value) for value in (clock, ids, publish_run)):
            raise TypeError("CommandApi providers must be callable")
        # Reviewed descriptors only, rebuilt by the projection before one field of
        # them is read; the boundary never resolves or probes a provider itself.
        self._providers = tuple(providers)
        self._store = store
        # Rooted at the same project as the run store, because one project owns
        # one set of reusable plans; a caller may hand in its own for a test.
        self._templates = (
            TemplateStore(store.project_root) if templates is None else templates)
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
        if route.name == "workflows":
            return self._list_workflows()
        if route.name == "runs":
            return self._list_runs()
        if route.name in {"workflow", "workflow_revision"}:
            assert route.workflow_id is not None
            if route.name == "workflow":
                return self._workflow_state(route.workflow_id)
            assert route.revision is not None
            return self._read_revision(route.workflow_id, route.revision)
        assert route.run_id is not None
        self._hold_route(route.run_id)
        recovered = self._store.read(route.run_id)
        if route.name == "run":
            return CommandResponse(200, _recovered_payload(recovered))
        return CommandResponse(200, self._controls(recovered.config))

    def _post(self, route: _Route, body: Mapping[str, Any]) -> CommandResponse:
        if route.name == "templates":
            return self._publish_template(body)
        if route.name == "runs":
            return self._open_run(body)
        if route.name in {"workflow_draft", "workflow_revisions"}:
            assert route.workflow_id is not None
            if route.name == "workflow_draft":
                return self._save_draft(route.workflow_id, body)
            return self._publish_revision(route.workflow_id, body)
        assert route.run_id is not None
        if route.name == "graph_from_template":
            return self._materialize_graph(route.run_id, body)
        if route.name == "proposals":
            return self._propose(route.run_id, body)
        if route.name == "actions":
            return self._authorize(route.run_id, body)
        if route.name == "graph":
            return self._write_graph(route.run_id, body)
        if route.name == "artifacts":
            return self._write_artifact(route.run_id, body)
        return self._decide(route.run_id, body)

    # -- the Studio surface: projections computed next door, wrapped here ----
    #
    # Each of the five below is one line for one reason: `studio_routes` speaks
    # `(status, payload)` and knows nothing about how a response is shaped on
    # the wire, so the boundary that owns `CommandResponse` is the one that
    # builds it. Putting anything else in these methods would put a second
    # decision somewhere it could disagree with the first.

    def _list_workflows(self) -> CommandResponse:
        return CommandResponse(
            *studio_routes.list_workflows(self._templates, self._providers))

    def _workflow_state(self, workflow_id: str) -> CommandResponse:
        return CommandResponse(
            *studio_routes.read_workflow(self._templates, workflow_id))

    def _read_revision(self, workflow_id: str, revision: int) -> CommandResponse:
        return CommandResponse(
            *studio_routes.read_revision(self._templates, workflow_id, revision))

    def _save_draft(
            self, workflow_id: str, body: Mapping[str, Any]) -> CommandResponse:
        return CommandResponse(
            *studio_routes.save_draft(
                self._templates, workflow_id, body, self._clock))

    def _publish_revision(
            self, workflow_id: str, body: Mapping[str, Any]) -> CommandResponse:
        return CommandResponse(
            *studio_routes.publish_revision(self._templates, workflow_id, body))

    def _list_runs(self) -> CommandResponse:
        return CommandResponse(
            *studio_routes.list_runs(self._store, self._providers))

    def _write_artifact(
            self, run_id: str, body: Mapping[str, Any]) -> CommandResponse:
        """Append one immutable handoff, or return its exact durable retry."""
        submitted = parse_artifact(body)
        self._hold_route(run_id)
        with self._store.transaction():
            self._hold_route(run_id)
            recovered = self._store.read(run_id)
            standing = next((
                row.value for row in recovered.records
                if row.kind == "artifact"
                and row.value.artifact_id == submitted.artifact_id), None)
            if standing is not None:
                assert isinstance(standing, ArtifactDocument)
                candidate = submitted.build(
                    run_id=run_id, created_at=standing.created_at)
                if candidate != standing:
                    raise RecordConflict(
                        f"artifact identity {standing.artifact_id!r} "
                        "already records different facts")
                created, artifact = False, standing
            else:
                artifact = submitted.build(
                    run_id=run_id, created_at=self._clock())
                created = self._store.append(artifact)
        if created:
            self._publish_run(run_id)
        return CommandResponse(201 if created else 200, artifact.as_dict())

    def _publish_template(self, body: Mapping[str, Any]) -> CommandResponse:
        """Publish one immutable revision, or agree it is already published.

        No run is involved, so no run is read, held or published: this route
        touches the template store and nothing else, and emits no frame on any
        outcome. A signal is a claim that some run changed, and none did.

        The store decides between the two success answers, because the store is
        what knows: identical bytes are the request already satisfied, and
        different bytes under one revision are two plans wearing one identity.
        """
        template = parse_template(body)
        published = self._templates.save(template)
        return CommandResponse(
            201 if published.created else 200, template.as_dict())

    def _materialize_graph(
            self, run_id: str, body: Mapping[str, Any]) -> CommandResponse:
        """Build this run's one plan from a stored revision and a binding.

        The order is В§4.4's order, for В§4.4's reason: the standing graph is
        looked for FIRST, before the clock, the store of templates, the
        registry, the provider descriptors or the frozen configuration is
        consulted at all. A client whose reply was lost is entitled to the same
        answer from a process that starts with a different registry -- or with
        none -- because the record is already durable and nothing about it
        depends on what this build can reach today.
        """
        asked = parse_graph_from_template(body)
        self._hold_route(run_id)
        initial = self._store.read(run_id)
        checked = None
        if _standing_graph(initial) is None:
            # Judged out here rather than under the lock, exactly as the graph
            # route does: a graph is append-only, so a plan that finds none
            # standing now is the plan this run may still be given.
            self._instances_are_declared(initial.config, run_id, asked)
            checked = self._revision(run_id, asked)
            probe = _plan(checked, initial.config, run_id, asked, _PROBE_AT)
            self._bindings_are_reachable(initial.config, run_id, probe.nodes)
            self._bindings_are_servable(initial.config, run_id, probe.nodes)
        with self._store.transaction():
            self._hold_route(run_id)
            standing = _standing_graph(self._store.read(run_id))
            if standing is not None:
                self._repeats_the_standing_plan(run_id, standing, asked, checked)
                created, graph = False, standing
            else:
                graph = _plan(_gated(checked), initial.config, run_id, asked,
                              self._clock())
                created = self._store.append(graph)
        if created:
            self._publish_run(run_id)
        return CommandResponse(201 if created else 200, graph.as_dict())

    def _revision(self, run_id: str, asked: TemplateRef) -> GraphTemplate:
        """Read one stored revision, ONCE, into the snapshot everything uses.

        Reading it twice was the defect this shape exists to prevent. The gates
        ran on one read and the transaction appended a second, so a revision
        replaced between them put a plan into an immutable journal that nothing
        had judged -- an unservable one, on a route whose contract promises
        zero durable bytes for exactly that fact. There is now one read, and
        what is appended is what was judged.
        """
        try:
            return self._templates.load(asked.template_id, asked.revision)
        except TemplateError:
            raise ApiRefusal.service_missing_revision(
                run_id, asked.template_id, asked.revision) from None

    def _repeats_the_standing_plan(
            self, run_id: str, standing: GraphDefinition, asked: TemplateRef,
            checked: GraphTemplate | None) -> None:
        """A run carries one graph, so a second request either IS it or conflicts.

        The candidate is re-materialized on the standing record's own
        `created_at`: the caller never supplied one, so comparing anything else
        would call every honest retry a conflict.

        The snapshot already gated is reused when there is one. When there is
        not -- the ordinary retry, which found a graph standing and gated
        nothing -- the revision is read here, and that read is safe in the one
        direction that matters: a revision that somehow differs makes the
        candidate differ, which is a `409`. It can turn an honest retry into a
        conflict; it can never turn a different plan into a `200`, and it
        writes nothing either way.
        """
        if standing.graph_id != asked.graph_id:
            raise RecordConflict(
                f"run {run_id!r} already follows graph {standing.graph_id!r}; "
                "one run carries one graph")
        template = self._revision(run_id, asked) if checked is None else checked
        candidate = _plan(template, self._store.read(run_id).config, run_id,
                          asked, standing.created_at)
        if standing != candidate:
            raise RecordConflict(
                f"graph {standing.graph_id!r} already records different facts")

    def _instances_are_declared(
            self, config: Mapping[str, Any], run_id: str,
            asked: TemplateRef) -> None:
        """Every instance a role is bound to is one this run's config declares.

        `materialize` refuses this too, and would refuse it a moment later --
        but it refuses it as a CONTRACT fault, which is the wrong word. That an
        instance is absent from a frozen configuration is a fact about this
        RUN, not about the shape of the request, and В§4.4 already answers it
        `service_refused` through this same door. Asking here keeps one word for
        one fact across both roads.
        """
        for instance in asked.binding.instances:
            self._bound_adapter(config, run_id, instance)

    def _bindings_are_reachable(
            self, config: Mapping[str, Any], run_id: str,
            nodes: Iterable[GraphNode]) -> None:
        """Every acting node's instance is bound to a provider this build can reach.

        This is the template road's rule and NOT В§4.4's. That route was frozen
        without it and stays byte-compatible: adding a refusal to a surface a
        client already depends on is a change of behaviour however good the
        reason, and the two roads write the same record by different rights.
        The materialize road may ask, because it is new and its contract says so.

        Asked BEFORE the pair door, because the two answer different questions
        and the coarser one is the more useful refusal: an unreachable provider
        cannot serve any capability, so reporting which schema it fails to speak
        would name a consequence instead of the cause.
        """
        reachable = self._reachable()
        for node in nodes:
            if node.capability is None:
                continue
            bound = self._bound_adapter(config, run_id, node.instance_id)
            if bound not in reachable:
                raise ApiRefusal.service_unreachable_adapter(
                    run_id, node.instance_id)

    def _reachable(self) -> frozenset[str]:
        """Which adapters this build can actually reach, by STATE not by name.

        `provider_projection` is the one authority on that question and this is
        the only place it is asked. What comes back is a state word from a
        closed vocabulary -- never a product, never a display name, never a
        guess from an id -- so a provider this build has never heard of and a
        provider that is merely unreachable are refused by the same rule and in
        the same words, and neither refusal knows which one it was.
        """
        return frozenset(
            row["provider_id"] for row in provider_projection(self._providers)
            if row["availability"] == _REACHABLE)

    def _write_graph(self, run_id: str, body: Mapping[str, Any]) -> CommandResponse:
        """Write the one graph a run follows; a run never edits the plan it has.

        The standing graph is looked for FIRST, before the clock, the registry
        or the frozen configuration is consulted at all, because an exact retry
        is answered from the journal and by nothing else. Validating first made
        a durable, immutable record's answer depend on mutable process state: a
        client whose reply was lost, retrying against a process that starts
        with a different registry, was refused a record it had already written.

        So only a plan that is about to become durable is judged, and a repeat
        answers with the very record standing -- ``created_at`` included, so no
        second identity's worth of facts is ever minted under one id.
        """
        submitted = parse_graph(body)
        self._hold_route(run_id)
        initial = self._store.read(run_id)
        if _standing_graph(initial) is None:
            # Judged out here rather than under the lock: a graph is
            # append-only, so a plan that finds none standing now is the plan
            # this run may still be given.
            self._bindings_are_servable(
                initial.config, run_id, submitted.nodes)
        with self._store.transaction():
            self._hold_route(run_id)
            standing = _standing_graph(self._store.read(run_id))
            if standing is not None:
                self._repeats_the_standing_graph(run_id, standing, submitted)
                created, graph = False, standing
            else:
                graph = submitted.build(run_id=run_id, created_at=self._clock())
                created = self._store.append(graph)
        if created:
            self._publish_run(run_id)
        return CommandResponse(201 if created else 200, graph.as_dict())

    @staticmethod
    def _repeats_the_standing_graph(
            run_id: str, standing: GraphDefinition,
            submitted: GraphInput) -> None:
        """A run carries one graph, so a second request either IS it or conflicts.

        The candidate is rebuilt on the standing record's own ``created_at``:
        the caller never supplied one, so comparing anything else would call
        every honest retry a conflict.
        """
        candidate = submitted.build(
            run_id=run_id, created_at=standing.created_at)
        if standing.graph_id != candidate.graph_id:
            raise RecordConflict(
                f"run {run_id!r} already follows graph {standing.graph_id!r}; "
                "one run carries one graph")
        if standing != candidate:
            raise RecordConflict(
                f"graph {standing.graph_id!r} already records different facts")

    def _bindings_are_servable(
            self, config: Mapping[str, Any], run_id: str,
            nodes: Iterable[GraphNode]) -> None:
        """A plan may only name work this run and this build can carry out.

        The graph contract deliberately holds no provider: which adapter serves
        an instance is the run's frozen configuration's fact. So the plan is
        held to that configuration HERE, once, before it becomes durable --
        rather than becoming a stored plan whose every proposal is refused.

        The PAIR is what decides, not the capability alone. A capability name is
        shared; the payload family behind it belongs to the adapter. Judging a
        plan against the global schema table accepted graphs an adapter could
        never execute: the route answered 201, the first proposal against that
        node answered `service_refused`, and the immutable plan stood in the
        journal with no way to edit or remove it. So the registry is asked what
        it recorded for this adapter and this capability, that answer must be
        the one family this API speaks, and the payload then goes through the
        registry's own door -- the same one `CommandService.propose` calls.
        """
        for node in nodes:
            if node.capability is None:
                continue
            bound = self._bound_adapter(config, run_id, node.instance_id)
            _servable_pair(
                self._registry, bound, node.capability, node.payload())

    def _propose(self, run_id: str, body: Mapping[str, Any]) -> CommandResponse:
        submitted = parse_proposal(body)
        self._hold_route(run_id)
        initial = self._store.read(run_id)
        bound = self._bound_adapter(initial.config, run_id, submitted.instance_id)
        # The same pair authority a plan meets, and BEFORE the payload is
        # judged or rebuilt: an unsupported pair is unsupported whatever its
        # arguments say, and answering the payload's question first gave two
        # different words for one fact about one pair.
        _servable_pair(
            self._registry, bound, submitted.capability, submitted.arguments)
        arguments = canonical_arguments(
            submitted.capability, submitted.arguments)
        with self._store.transaction():
            self._hold_route(run_id)
            recovered = self._store.read(run_id)
            prior_ids = {
                row.value.proposal_id for row in recovered.records
                if row.kind == "action_proposal"}
            proposal = self._service.propose(
                run_id=run_id, instance_id=submitted.instance_id,
                attempt_id=submitted.attempt_id, capability=submitted.capability,
                arguments=arguments, scope=submitted.scope,
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

    # -- opening one run, plan included -------------------------------------

    def _open_run(self, body: Mapping[str, Any]) -> CommandResponse:
        """Open one run, and give it its plan in the same call.

        The road itself is next door with the rest of the Studio surface; what
        stays here is the AUTHORITY it has to ask for. `_judge_plan` is that
        authority in one callable: this boundary owns the registry and the
        reviewed provider descriptors, and a module that could reach around it
        to judge a binding for itself would be a second opinion about the one
        question this class exists to answer.
        """
        return CommandResponse(*studio_routes.open_run(
            self._store, self._templates, body,
            clock=self._clock, ids=self._ids, reachable=self._reachable(),
            judge_plan=self._judge_plan, publish=self._publish_run,
            hold_route=self._hold_route))

    def _judge_plan(
            self, snapshot: Mapping[str, Any], run_id: str,
            nodes: Sequence[GraphNode]) -> None:
        """Both binding verdicts, in the order the template road already asks them.

        Reachability first: a plan naming an instance this build cannot reach is
        refused for what the machine is, before the registry is asked what the
        pair can serve. Answering them the other way round would report a
        payload problem about work that could never have run at all.
        """
        self._bindings_are_reachable(snapshot, run_id, nodes)
        self._bindings_are_servable(snapshot, run_id, nodes)

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

        ``model`` is on the instance row for the same reason ``adapter_id`` is:
        both are what this run's frozen configuration says about a DEPLOYMENT,
        and neither appears in a graph document, where a plan names roles. It is
        ``null`` when the instance pins none, and null is not a default -- it
        says this build chose no model and whatever the provider's own
        configuration decides is what will run. A reader that showed a name
        there would be inventing the one fact this row exists to report.
        """
        models = frozen_config_models(config)
        rows = []
        for instance_id, adapter_id in sorted(_bindings(config).items()):
            try:
                declared = self._registry.controls(adapter_id)
            except AdapterContractError:
                declared = ()
            rows.append({
                "instance_id": instance_id,
                "adapter_id": adapter_id,
                "model": models.get(instance_id),
                "controls": sorted(set(declared) & set(ARGUMENT_SCHEMAS)),
            })
        return {"instances": rows, "providers": provider_projection(self._providers)}


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
