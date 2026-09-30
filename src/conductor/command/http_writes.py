"""Dispatch existing write routes; HTTP serialization and the stores stay in CommandApi.

Extracted along the POST boundary when the facade reached its module limit.
The supplied facade owns the stores, the registry and the execution binding
exactly as before; this module creates no runtime, worker, provider, collector
or execution authority. Every handler answers ``(status, payload)`` and the
facade shapes that pair into its response.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from .adapters.provider import provider_projection
from .api_contracts import (
    ApiRefusal,
    ArtifactInput,
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
)
from .artifacts import ArtifactDocument
from .command_routes import Route
from .graph_definition import GraphDefinition, GraphNode
from .graph_template import GraphTemplate, TemplateError
#: Pure admission holds live next door; registry authority is passed as a fact.
from .http_holds import (
    _hold_gate_admits,
    _hold_gate_is_reached,
    _hold_not_terminal,
    _hold_plan_pre_answers_no_gate,
    _sandboxes_are_provided,
    _verifiers_are_servable,
)
from .plan_admission import _gated, _plan, _servable_pair, _task, work_scope_admits
from .run_closing import close_if_terminal
from .run_store import RecordConflict
from . import flow_routes, project_routes, studio_routes, task_routes
from .studio_routes import standing_graph as _standing_graph

if TYPE_CHECKING:
    from .http_api import CommandApi

_Reply = tuple[int, Mapping[str, Any]]

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


def write_route(api: CommandApi, route: Route, body: Mapping[str, Any]) -> _Reply:
    if route.name.startswith("automation_"):
        from .policy_routes import route as policy_route
        return policy_route(api, route.name, route.run_id, body)
    if route.name == "templates":
        return _publish_template(api, body)
    if route.name == "runs":
        return _open_run(api, body)
    if route.name == "tasks":
        return task_routes.create_task(api._tasks, body, clock=api._clock)
    if route.name == "workflow_flow":
        assert route.workflow_id is not None
        return _write_flow(api, route.workflow_id, body)
    if route.name == "project_cycle_pin":
        return flow_routes.pin_project_cycle(api._cycle, api._templates, body, api._clock)
    if route.name in {"workflow_draft", "workflow_revisions"}:
        assert route.workflow_id is not None
        if route.name == "workflow_draft":
            return _save_draft(api, route.workflow_id, body)
        return _publish_revision(api, route.workflow_id, body)
    assert route.run_id is not None
    if route.name == "graph_from_template":
        return _materialize_graph(api, route.run_id, body)
    if route.name == "proposals":
        return _propose(api, route.run_id, body)
    if route.name == "actions":
        return _authorize(api, route.run_id, body)
    if route.name == "graph":
        return _write_graph(api, route.run_id, body)
    if route.name == "artifacts":
        return _write_artifact(api, route.run_id, body)
    return _decide(api, route.run_id, body)


def _save_draft(
        api: CommandApi, workflow_id: str, body: Mapping[str, Any]) -> _Reply:
    return studio_routes.save_draft(
        api._templates, workflow_id, body, api._clock)


def _publish_revision(
        api: CommandApi, workflow_id: str, body: Mapping[str, Any]) -> _Reply:
    return studio_routes.publish_revision(api._templates, workflow_id, body)


def _write_flow(
        api: CommandApi, workflow_id: str, body: Mapping[str, Any]) -> _Reply:
    return flow_routes.write_flow(
        api._templates, workflow_id, body, api._clock, flow_routes.product_limits(api._budget),
        lambda binding: flow_routes.binding_facts(api._registry, binding))


def _write_artifact(
        api: CommandApi, run_id: str, body: Mapping[str, Any]) -> _Reply:
    """Append one immutable handoff, return its exact retry, or refuse an end."""
    return append_artifact(api, run_id, parse_artifact(body))


def write_materials(api: CommandApi, run_id: str, body: Mapping[str, Any]) -> _Reply:
    """Compose the materials of a run into `artifact-materials` and append it (spec 6.2.3).

    The composing is `project_routes`'; the append is the artifacts door's own function.
    """
    return append_artifact(api, run_id, project_routes.materials_document(api, run_id, body))


def append_artifact(api: CommandApi, run_id: str, submitted: ArtifactInput) -> _Reply:
    """The one door through which a document reaches a run's journal from a request.

    The artifacts route and the materials route both end here, so "the same transaction and the
    same refusal of an ended run" is one function and not two copies of it.
    """
    api._hold_route(run_id)
    with api._store.transaction():
        api._hold_route(run_id)
        recovered = api._store.read(run_id)
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
            # AFTER the identity branch, because the ending refuses RECORDS
            # and an exact retry appends none; strictly before the clock and
            # the append, so a refusal reads no instant and leaves the run
            # byte-identical.
            _hold_not_terminal(recovered)
            artifact = submitted.build(
                run_id=run_id, created_at=api._clock())
            created = api._store.append(artifact)
    if created:
        api._publish_run(run_id)
    return (201 if created else 200), artifact.as_dict()


def _publish_template(api: CommandApi, body: Mapping[str, Any]) -> _Reply:
    """Publish one immutable revision, or agree it is already published.

    No run is involved, so no run is read, held or published: this route
    touches the template store and nothing else, and emits no frame on any
    outcome. A signal is a claim that some run changed, and none did.

    The store decides between the two success answers, because the store is
    what knows: identical bytes are the request already satisfied, and
    different bytes under one revision are two plans wearing one identity.
    """
    template = parse_template(body)
    published = api._templates.save(template)
    return (201 if published.created else 200), template.as_dict()


def _materialize_graph(
        api: CommandApi, run_id: str, body: Mapping[str, Any]) -> _Reply:
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
    api._hold_route(run_id)
    initial = api._store.read(run_id)
    checked = None
    if _standing_graph(initial) is None:
        # Judged out here rather than under the lock, exactly as the graph
        # route does: a graph is append-only, so a plan that finds none
        # standing now is the plan this run may still be given.
        _instances_are_declared(api, initial.config, run_id, asked)
        # A malformed task binding is `run_corrupt`, not a contract fault.
        task = _task(initial.config)
        checked = _revision(api, run_id, asked)
        probe = _plan(checked, initial.config, run_id, asked, _PROBE_AT)
        # Create road only: the comparison road below admits nothing.
        work_scope_admits(probe.nodes, task)
        # One judgement per plan, whichever door writes it: a checker that cannot check
        api._judge_plan(initial.config, run_id, probe.nodes)  # would wedge an immutable plan
    with api._store.transaction():
        api._hold_route(run_id)
        recovered = api._store.read(run_id)
        standing = _standing_graph(recovered)
        if standing is not None:
            _repeats_the_standing_plan(api, run_id, standing, asked, checked)
            created, graph = False, standing
        else:
            _hold_plan_pre_answers_no_gate(
                run_id, recovered, _gated(checked).nodes)
            graph = _plan(_gated(checked), initial.config, run_id, asked,
                          api._clock())
            created = api._store.append(graph)
    if created:
        api._publish_run(run_id)
    return (201 if created else 200), graph.as_dict()


def _revision(api: CommandApi, run_id: str, asked: TemplateRef) -> GraphTemplate:
    """Read one stored revision, ONCE, into the snapshot everything uses.

    Reading it twice was the defect this shape exists to prevent. The gates
    ran on one read and the transaction appended a second, so a revision
    replaced between them put a plan into an immutable journal that nothing
    had judged -- an unservable one, on a route whose contract promises
    zero durable bytes for exactly that fact. There is now one read, and
    what is appended is what was judged.
    """
    try:
        return api._templates.load(asked.template_id, asked.revision)
    except TemplateError:
        raise ApiRefusal.service_missing_revision(
            run_id, asked.template_id, asked.revision) from None


def _repeats_the_standing_plan(
        api: CommandApi, run_id: str, standing: GraphDefinition,
        asked: TemplateRef, checked: GraphTemplate | None) -> None:
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
    template = _revision(api, run_id, asked) if checked is None else checked
    candidate = _plan(template, api._store.read(run_id).config, run_id,
                      asked, standing.created_at)
    if standing != candidate:
        raise RecordConflict(
            f"graph {standing.graph_id!r} already records different facts")


def _instances_are_declared(
        api: CommandApi, config: Mapping[str, Any], run_id: str,
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
        api._bound_adapter(config, run_id, instance)


def _bindings_are_reachable(
        api: CommandApi, config: Mapping[str, Any], run_id: str,
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
    reachable = api._reachable()
    for node in nodes:
        if node.capability is None:
            continue
        bound = api._bound_adapter(config, run_id, node.instance_id)
        if bound not in reachable:
            raise ApiRefusal.service_unreachable_adapter(
                run_id, node.instance_id)


def _reachable(api: CommandApi) -> frozenset[str]:
    """Which adapters this build can actually reach, by STATE not by name.

    `provider_projection` is the one authority on that question and this is
    the only place it is asked. What comes back is a state word from a
    closed vocabulary -- never a product, never a display name, never a
    guess from an id -- so a provider this build has never heard of and a
    provider that is merely unreachable are refused by the same rule and in
    the same words, and neither refusal knows which one it was.
    """
    return frozenset(
        row["provider_id"] for row in provider_projection(api._providers)
        if row["availability"] == _REACHABLE)


def _write_graph(api: CommandApi, run_id: str, body: Mapping[str, Any]) -> _Reply:
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
    api._hold_route(run_id)
    initial = api._store.read(run_id)
    if _standing_graph(initial) is None:
        # Judged out here rather than under the lock: a graph is
        # append-only, so a plan that finds none standing now is the plan
        # this run may still be given.
        api._bindings_are_servable(
            initial.config, run_id, submitted.nodes)
        work_scope_admits(submitted.nodes, _task(initial.config))
    with api._store.transaction():
        api._hold_route(run_id)
        recovered = api._store.read(run_id)
        standing = _standing_graph(recovered)
        if standing is not None:
            _repeats_the_standing_graph(run_id, standing, submitted)
            created, graph = False, standing
        else:
            _hold_plan_pre_answers_no_gate(
                run_id, recovered, submitted.nodes)
            graph = submitted.build(run_id=run_id, created_at=api._clock())
            created = api._store.append(graph)
    if created:
        api._publish_run(run_id)
    return (201 if created else 200), graph.as_dict()


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


def _propose(api: CommandApi, run_id: str, body: Mapping[str, Any]) -> _Reply:
    """Record one proposal; a resubmit after the ending is a NEW record.

    The one door where the ending is asked before the identity lookup, and
    it is not an exception to the rule the other three follow. A caller
    cannot name a proposal: the id is minted here, so no request this door
    receives can be an exact retry of a record that already stands, and the
    `200` below is reached only by a mint that collided with one. Every
    resubmit after a run has ended asks for a record that does not exist
    yet, which is exactly what a finished run refuses.
    """
    submitted = parse_proposal(body)
    api._hold_route(run_id)
    initial = api._store.read(run_id)
    bound = api._bound_adapter(initial.config, run_id, submitted.instance_id)
    # The same pair authority a plan meets, and BEFORE the payload is
    # judged or rebuilt: an unsupported pair is unsupported whatever its
    # arguments say, and answering the payload's question first gave two
    # different words for one fact about one pair.
    _servable_pair(
        api._registry, bound, submitted.capability, submitted.arguments)
    arguments = canonical_arguments(
        submitted.capability, submitted.arguments)
    with api._store.transaction():
        api._hold_route(run_id)
        recovered = api._store.read(run_id)
        _hold_not_terminal(recovered)
        prior_ids = {
            row.value.proposal_id for row in recovered.records
            if row.kind == "action_proposal"}
        proposal = api._service.propose(
            run_id=run_id, instance_id=submitted.instance_id,
            attempt_id=submitted.attempt_id, capability=submitted.capability,
            arguments=arguments, scope=submitted.scope,
            proposed_by=submitted.proposed_by, rationale=submitted.rationale,
            timeout_seconds=submitted.timeout_seconds,
            adapter_id=submitted.adapter_id, node_id=submitted.node_id)
        created = proposal.proposal_id not in prior_ids
    if created:
        api._publish_run(run_id)
    return (201 if created else 200), proposal.as_dict()


def _authorize(api: CommandApi, run_id: str, body: Mapping[str, Any]) -> _Reply:
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
    api._hold_route(run_id)
    confirmation = submitted.build(
        confirmation_id=api._ids("confirmation"), run_id=run_id,
        confirmed_at=api._clock())
    claimed: list[Any] = []
    try:
        authorization = api._runtime.authorize(
            confirmation, budget=api._budget,
            admit=None if api._execution is None else (
                lambda: claimed.append(api._execution.claim())))
        if authorization.record_created:
            api._publish_run(run_id)
            for slot in claimed:
                slot.place(authorization)
    finally:
        for slot in claimed:
            slot.release()
    return (201 if authorization.record_created else 200,
            authorization.request.as_dict())


def _decide(api: CommandApi, run_id: str, body: Mapping[str, Any]) -> _Reply:
    submitted = parse_decision(body)
    api._hold_route(run_id)
    with api._store.transaction():
        api._hold_route(run_id)
        recovered = api._store.read(run_id)
        # The waiver rule is about the decision's CONTENT and not about
        # records, so it stays in front of everything: a waived protected
        # gate is refused whether or not this receipt already stands.
        _hold_gate_admits(run_id, recovered, submitted)
        prior = next((
            row.value for row in recovered.records
            if row.kind == "decision"
            and row.value.receipt_id == submitted.receipt_id), None)
        if prior is not None:
            decision = submitted.build(
                run_id=run_id, decided_at=prior.decided_at,
                config_digest=recovered.envelope.config_digest)
            if prior != decision:
                raise RecordConflict("decision identity records different facts")
            created, decision = False, prior
        else:
            # AFTER the prior lookup, exactly as `_write_artifact` asks it:
            # the ending refuses RECORDS, and an exact retry of a receipt
            # this run already carries appends none -- including the very
            # decision that ended the run. Before the clock and the append,
            # so a refusal reads no instant and leaves the run byte-identical.
            _hold_not_terminal(recovered)
            # And beside it the plan's own permission: this run must have
            # ARRIVED at the gate, or the receipt must correct the one
            # standing on it. Its sentence is next door, with the rest.
            _hold_gate_is_reached(recovered, submitted)
            decision = submitted.build(
                run_id=run_id, decided_at=api._clock(),
                config_digest=recovered.envelope.config_digest)
            created = api._store.append(decision)
            # A decision is one of the two facts that can settle a step, so
            # the plan is asked whether this run has just ended -- inside
            # the same transaction, against the journal that now holds it.
            close_if_terminal(api._store, run_id, clock=api._clock,
                              ids=api._ids)
    if created:
        api._publish_run(run_id)
    return (201 if created else 200), decision.as_dict()


# -- opening one run, plan included -------------------------------------


def _open_run(api: CommandApi, body: Mapping[str, Any]) -> _Reply:
    """Open one run, and give it its plan in the same call.

    The road itself is next door with the rest of the Studio surface; what
    stays here is the AUTHORITY it has to ask for. `_judge_plan` is that
    authority in one callable: this boundary owns the registry and the
    reviewed provider descriptors, and a module that could reach around it
    to judge a binding for itself would be a second opinion about the one
    question this class exists to answer.
    """
    return studio_routes.open_run(
        api._store, api._templates, body, tasks=api._tasks,
        clock=api._clock, ids=api._ids, reachable=api._reachable(),
        judge_plan=api._judge_plan, publish=api._publish_run,
        hold_route=api._hold_route)


def _judge_plan(
        api: CommandApi, snapshot: Mapping[str, Any], run_id: str,
        nodes: Sequence[GraphNode]) -> None:
    """Both binding verdicts, in the order the template road already asks them.

    Reachability first: a plan naming an instance this build cannot reach is
    refused for what the machine is, before the registry is asked what the
    pair can serve. Answering them the other way round would report a
    payload problem about work that could never have run at all.

    The ROUTE demand is asked last and is a different kind of question from
    the two above: those ask whether the machine a step is bound to can do
    the work, and this asks whether the machine can give the work the route
    the plan demanded. A step may be perfectly bound and still name a
    sandbox nothing here provides.
    """
    _bindings_are_reachable(api, snapshot, run_id, nodes)
    api._bindings_are_servable(snapshot, run_id, nodes)
    _verifiers_are_servable(
        snapshot, run_id, nodes, api._bound_adapter,
        api._registry.verifies_independently, reachable=api._reachable())
    _sandboxes_are_provided(run_id, nodes)
