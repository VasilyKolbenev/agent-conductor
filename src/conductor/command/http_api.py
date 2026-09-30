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
from datetime import timedelta
from typing import Any
from urllib.parse import urlsplit

from .adapters import AdapterContractError, AdapterRegistry, UnsupportedCapability
from .adapters.provider import ProviderContract, provider_projection
from .api_contracts import (
    COMMAND_ARGUMENT_SCHEMA,
    ApiRefusal,
    refusal_from_exception,
)
from .command_routes import (
    COMMAND_ROUTES,
    Route as _Route,
    match_route as _match_route,
    target_path as _target_path,
)
from .containment import run_route_violations, unprovidable_sandboxes
from .contracts import (
    ActionRequest,
    ActionResultReceipt,
    ContractError,
    RunEnvelope,
    _id,
    frozen_config_bindings,
)
from .coordinator import ExecutionCoordinator
from .instance_controls import instance_controls
from .isolation_facts import reference_block
from .graph_definition import GraphNode
from .graph_projection import graph_payload
from .graph_template import (
    TEMPLATE_DIR,
    load_template,
    materialize,
)
from .graph_causality import standing_terminal
from .plan_admission import (  # noqa: F401 -- re-exported under their old names
    _bindings,
    _gated,
    _plan,
    _servable_pair,
    _task,
    work_scope_admits,
)
from .http_transport import (
    CommandSession,
    validate_command_host,
)
from .run_store import CorruptRun, RunStore, StoreError
from .new_work_admission import admit_new_work
from .project_claim import UNCLAIMED, ProjectIdentity
from .auto_continue import AutoContinueStore
from .project_cycle import ProjectCycleStore
from .project_git import GitRead
from .task_store import TaskStore
from .template_store import TemplateStore
from .runtime import Budget, ControlRuntime
from .service import CommandService
from .quota_service import QuotaService
from .quota_views import DEFAULT_QUOTA_MAX_AGE, QuotaView, validate_get as _quota_get
from . import http_reads, http_writes, studio_routes
from .studio_routes import (
    plain_json as _plain_json,
    recovered_payload as _recovered_payload,
)


PRODUCT_COMMAND_BUDGET = Budget(
    max_actions=8,
    max_action_seconds=3600,
    max_confirmation_age_seconds=3600,
)

#: The identity a plan built only to be judged wears. A run's real plan is named
#: by the server when it is about to be written; this one is thrown away, and
#: giving it a fixed name keeps a judgement from depending on an id generator.
_PROBE_GRAPH = "graph-open-run-probe"


@dataclass(frozen=True)
class CommandResponse:
    """One JSON response; the server owns byte serialization and headers."""

    status: int
    payload: Mapping[str, Any]


def _admit_parts(
        store: object, registry: object, templates: object, tasks: object, identity: object,
        session: object, budget: object, calls: Iterable[object]) -> None:
    """The type of every collaborator, judged before the API keeps one of them."""
    if not isinstance(store, RunStore) or not isinstance(registry, AdapterRegistry):
        raise TypeError("CommandApi requires a RunStore and AdapterRegistry")
    if templates is not None and not isinstance(templates, TemplateStore):
        raise TypeError("CommandApi templates must be a TemplateStore")
    if tasks is not None and not isinstance(tasks, TaskStore):
        raise TypeError("CommandApi tasks must be a TaskStore")
    if not isinstance(identity, ProjectIdentity):
        raise TypeError("CommandApi identity must be a ProjectIdentity")
    if not isinstance(session, CommandSession) or type(budget) is not Budget:
        raise TypeError("CommandApi requires a CommandSession and Budget")
    if not all(callable(value) for value in calls):
        raise TypeError("CommandApi providers must be callable")


def _quota_reader(quota_view: object, service: QuotaService | None,
                  max_age: timedelta) -> object:
    """The reader of `GET /command/quotas`: the one handed in, or the cache-only default.

    A process opened for viewing is given a reader of the hub's last snapshot (spec 4.3.1); it
    only has to answer `payload(contracts, now)` as the default does. The service and the
    maximum age build the default and nothing else.
    """
    if quota_view is None:
        return QuotaView(service, max_age)
    if not callable(getattr(quota_view, "payload", None)):
        raise TypeError("CommandApi quota_view must have a payload method")
    return quota_view


def _project_stores(
        store: RunStore, templates: TemplateStore | None,
        tasks: TaskStore | None
) -> tuple[TemplateStore, TaskStore, ProjectCycleStore, AutoContinueStore]:
    """The plans, the tasks, the pinned cycle and the continue-after flag of this project.

    All are rooted at the same project as the run store, because one project owns one set of
    each; the task store holds the SAME process-local gate the run store holds for that root, and
    so does the cycle store (spec 7.10, one small file). A caller may hand in its own templates
    or tasks for a test.
    """
    return (TemplateStore(store.project_root) if templates is None else templates,
            TaskStore(store.project_root) if tasks is None else tasks,
            ProjectCycleStore(store.project_root), AutoContinueStore(store.project_root))


class CommandApi:
    """Bind transport, typed route authority, store, service, and authorization."""

    def __init__(
            self, store: RunStore, registry: AdapterRegistry, *,
            session: CommandSession, budget: Budget,
            clock: Callable[[], str], ids: Callable[[str], str],
            publish_run: Callable[[str], None],
            providers: Iterable[ProviderContract] = (),
            provider_configs=(),
            quota_service: QuotaService | None = None,
            quota_max_age: timedelta = DEFAULT_QUOTA_MAX_AGE,
            quota_view: object | None = None,
            templates: TemplateStore | None = None,
            tasks: TaskStore | None = None,
            project: Callable[[], str | None] = lambda: None,
            identity: ProjectIdentity = UNCLAIMED,
            project_git: GitRead | None = None) -> None:
        _admit_parts(store, registry, templates, tasks, identity, session, budget,
                     (clock, ids, publish_run, project))
        if project_git is not None and not callable(project_git):
            raise TypeError("CommandApi project_git must be a git reader")
        # Reviewed descriptors only, rebuilt by the projection before one field of
        # them is read; the boundary never resolves or probes a provider itself.
        self._providers = tuple(providers)
        self._quota_view = _quota_reader(quota_view, quota_service, quota_max_age)
        # A CALLABLE, not a value: the map holding the name is re-read while the
        # server runs, so a name captured here would go stale against it.
        self._project = project
        # What this server is, and the claim a request may make on it (spec 4.5.1).
        self._identity = identity
        # The reader of the project's git (spec 9.3), or None for a server that has none.
        self._project_git = project_git
        self._store = store
        self._templates, self._tasks, self._cycle, self._flag = _project_stores(
            store, templates, tasks)
        self._registry = registry
        self._session = session
        self._budget = Budget(
            budget.max_actions, budget.max_action_seconds,
            budget.max_confirmation_age_seconds)
        self._clock = clock
        self._ids = ids
        from .policy_wiring import notify_run, make_policy
        from .queue_routes import make_queue
        self._publish_run = notify_run(self, publish_run)
        self._service = CommandService(store, registry, clock=clock, ids=ids)
        self._runtime = ControlRuntime(
            store, registry, clock=clock, ids=ids, notify=self._publish_run)
        self._execution: ExecutionCoordinator | None = None
        self._policy = make_policy(self, provider_configs)
        self._queue = make_queue(self)
        self._runtime._policy = self._policy

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
                self._identity.check(pairs)
                if route.name == "quotas":
                    _quota_get(target, pairs, raw_body)
                return self._localized(self._get(route, host), pairs)
            body = self._session.validate_mutation(pairs, raw_body)
            self._identity.check(pairs)
            return self._localized(self._post(route, body), pairs)
        except ApiRefusal as refusal:
            return CommandResponse(refusal.status, refusal.as_dict())
        except Exception as error:
            try:
                refusal = refusal_from_exception(error)
            except TypeError:
                raise
            return CommandResponse(refusal.status, refusal.as_dict())

    @staticmethod
    def _localized(response, pairs):
        from .response_locale import language_for, localize_criteria
        return CommandResponse(response.status, localize_criteria(response.payload, language_for(pairs)))

    def body_length(
            self, target: str,
            raw_headers: Iterable[tuple[str, str]]) -> int:
        """Hold the exact POST route and transport headers before a body read."""
        _match_route("POST", _target_path(target))
        return self._session.body_length(raw_headers)

    def _get(self, route: _Route, host: str) -> CommandResponse:
        return CommandResponse(*http_reads.read_route(self, route, host))

    def _post(self, route: _Route, body: Mapping[str, Any]) -> CommandResponse:
        return CommandResponse(*http_writes.write_route(self, route, body))

    # -- the Studio surface: projections computed next door, wrapped here ----
    #
    # Each of the five below is one line for one reason: `studio_routes` speaks
    # `(status, payload)` and knows nothing about how a response is shaped on
    # the wire, so the boundary that owns `CommandResponse` is the one that
    # builds it. Putting anything else in these methods would put a second
    # decision somewhere it could disagree with the first.

    def _list_workflows(self) -> CommandResponse:
        return CommandResponse(
            *studio_routes.list_workflows(
                self._templates, self._providers, self._project()))

    def _workflow_state(self, workflow_id: str) -> CommandResponse:
        return CommandResponse(
            *studio_routes.read_workflow(self._templates, workflow_id))

    def _read_revision(self, workflow_id: str, revision: int) -> CommandResponse:
        return CommandResponse(
            *studio_routes.read_revision(self._templates, workflow_id, revision))

    def _list_runs(self) -> CommandResponse:
        return CommandResponse(
            *studio_routes.list_runs(self._store, self._providers, computed_at=self._clock()))

    def _reachable(self) -> frozenset[str]:
        """The adapters this build can reach; the rule is in ``http_writes``."""
        return http_writes._reachable(self)

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
            admit_new_work(self._store.project_root,
                           self._registry.argument_schema(bound, node.capability),
                           node.capability, node.payload())

    def _judge_plan(
            self, snapshot: Mapping[str, Any], run_id: str,
            nodes: Sequence[GraphNode]) -> None:
        """Both binding verdicts; the rule is in ``http_writes``, the authority here."""
        http_writes._judge_plan(self, snapshot, run_id, nodes)

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
        """Join neither deployment facts nor build facts by a display label."""
        providers = provider_projection(self._providers)
        # The login mode and the vendor's own sandbox are MACHINE facts and live
        # on the provider row; a binding is a RUN fact. Joined here, once, so the
        # browser is never the place two projections become a promise.
        facts = {row["provider_id"]: {
            "auth": row.get("auth"), "vendor_sandbox": row.get("vendor_sandbox")}
            for row in providers}
        try:
            instances = instance_controls(config, self._registry, facts)
        except ContractError as error:
            # These are already-frozen bytes, not a malformed caller payload.
            raise ApiRefusal.fixed("run_corrupt") from error
        return {"instances": instances, "providers": providers,
                "isolation_facts": list(reference_block())}
