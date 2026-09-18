"""The Studio's own surface: workflows, drafts, revisions, runs, and opening one.

Split out of ``http_api`` when that module reached its line cap, along the seam
the two halves already had. What stayed there is AUTHORITY -- the route table,
the transport gate, the registry and the reviewed provider descriptors. What
lives here is the Studio's own orchestration: every function below reads a
store and computes, and the two that write ask the boundary to judge rather
than judging for themselves. ``open_run`` takes ``judge_plan`` for exactly that
reason: a module that could decide a binding's reachability on its own would be
a second opinion about the one question the boundary exists to answer.

The seam is spelled as ``(status, payload)`` rather than as this package's
``CommandResponse``. That type belongs to the boundary, and importing it here
would make the two modules import each other -- so the boundary wraps, and
nothing in this file knows how a response is shaped on the wire.

Two of these answers carry a ``providers`` array, and it is the SAME
``provider_projection`` the per-run controls route carries. It answers a
different question from that route's ``instances``: a provider row is about this
BUILD and this MACHINE, an instance row is about one run's frozen binding, and a
consumer joins them by identity. It is here because a user with no runs at all
can reach these routes and can never reach a per-run one.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from .adapters.provider import provider_projection
from .api_contracts import ApiRefusal
from .studio_contracts import (
    RunInput, parse_draft_save, parse_run, parse_workflow_revision)
from .containment import run_route_violations
from .contracts import (
    ActionRequest, ActionResultReceipt, ContractError, frozen_config_workflow,
    _id)
from .graph_projection import graph_payload
from .graph_template import TemplateError, materialize
#: ONE `_gated`, shared with the command API. Two copies of "what was
#: judged is what is appended" could come to disagree about the one
#: thing that rule exists to make unrepresentable. ONE `_task` for the
#: two write roads -- from-template and the open_run retry -- so a frozen
#: binding is corrupt by one rule wherever a record is about to be
#: appended; the read projections below carry the same verdict in their
#: own words (an unreadable row, `run_corrupt` on the read).
from .plan_admission import _gated, _task, work_scope_admits
from .store_errors import RecordConflict, StoreError
#: By MODULE, because `task_routes` imports this module back for `run_ids`;
#: the name is looked up when `open_run` runs, never while either module is
#: half built.
from . import task_routes
from .task_contracts import TaskBinding, frozen_config_task
from .task_store import CorruptTask
from .template_store import RouteNotOwned
from .workflow_draft import (
    DraftRefused,
    publish_candidate,
    draft_digest,
    saved_draft,
    unchanged_from_published,
    starters,
    workflow_rows,
    workflow_state,
)

if TYPE_CHECKING:  # pragma: no cover - collaborators, never constructed here
    from .run_store import RunStore
    from .task_store import TaskStore
    from .template_store import TemplateStore

Answer = tuple[int, dict[str, Any]]

#: The instant a materialization that is NOT about to be written is built on. A
#: plan built to be thrown away must not read a clock, or a judgement would
#: depend on when it was made.
_PROBE_AT = "1970-01-01T00:00:00Z"
#: The identity a plan built only to be judged wears. A run's real plan is named
#: when it is about to be written; this one is thrown away, and giving it a
#: fixed name keeps a judgement from depending on an id generator.
_PROBE_GRAPH = "graph-open-run-probe"


def list_workflows(templates: "TemplateStore", providers,
                   project: str | None = None) -> Answer:
    """Every workflow this project holds, what this build can reach, and what
    it ships to start from.

    Three arrays and one name. ``workflows`` is this PROJECT's durable state;
    ``providers`` is this build and this machine; ``starters`` is what the wheel
    ships, so "create a workflow from blank or from a template" has both roads
    on one response.

    ``project`` is the identity `conduct init` wrote into ``map.toml``, handed
    IN rather than read here. This package holds no opinion about Protocol v1
    documents and imports nothing that reads one; the server owns that map, and
    it is the server that decides whether what it holds is a name at all. What
    arrives here is a name or ``null``, and ``null`` is a real answer -- a
    project scaffolded before this build named one, or one still carrying the
    placeholder, has no name to show and the screen says so rather than
    printing a placeholder in the largest type it has.
    """
    return 200, {
        "project": project,
        "workflows": workflow_rows(templates),
        "providers": provider_projection(providers),
        "starters": starters(),
    }


def read_workflow(templates: "TemplateStore", workflow_id: str) -> Answer:
    """One workflow: its revisions, its draft, and what stops it publishing."""
    return 200, workflow_state(templates, workflow_id)


def read_revision(
        templates: "TemplateStore", workflow_id: str, revision: int) -> Answer:
    """One immutable revision, read back through the contract's own door.

    ``load`` puts a stored document through ``GraphTemplate.from_dict``, so a
    revision this build can no longer speak is refused rather than half-served,
    and the refusal names the two facts the caller already supplied and no path.

    ``ContractError`` rather than ``TemplateError``: the store raises the narrow
    one for bytes it cannot open, and the CONTRACT raises the base class for a
    document that opens and is not a template. Both mean the same thing to a
    caller who asked for a revision -- this one cannot be served -- and catching
    only the narrow one answered `contract_invalid`, blaming the caller for a
    request that was perfectly well formed.
    """
    try:
        template = templates.load(workflow_id, revision)
    except ContractError:
        raise ApiRefusal.missing_revision(workflow_id, revision) from None
    return 200, {"workflow_id": workflow_id, "revision": revision,
                 "document": template.as_dict()}


def save_draft(
        templates: "TemplateStore", workflow_id: str,
        body: Mapping[str, Any], clock) -> Answer:
    """Replace this workflow's editable document and say where it now stands.

    The answer is the WHOLE workflow state rather than an acknowledgement, and
    it is the same projection the read route answers with: a client that just
    saved needs the diagnostics and the publishability of what it saved, and
    computing them a second way is how a screen comes to disagree with the route
    that will refuse it.

    ``201`` when this call is what first gave the workflow a draft, ``200`` for
    every later save. No run is involved, so no frame is published -- exactly as
    publishing a template emits none.

    The save is OPTIMISTIC: the body names which stored draft it is replacing,
    and a save whose expectation is not what stands is refused rather than
    written. Reading the standing draft, comparing it and writing are one
    transaction for the reason the publish chain is one: the read is what
    decides whether the write may happen, and a save landing between the two is
    exactly the thing the comparison exists to refuse.
    """
    asked = parse_draft_save(body)
    with templates.transaction(workflow_id):
        _replaces_what_was_read(templates, workflow_id, asked)
        created = saved_draft(templates, workflow_id, asked.document, clock)
        return (201 if created else 200), workflow_state(templates, workflow_id)


def _replaces_what_was_read(
        templates: "TemplateStore", workflow_id: str, asked) -> None:
    """The draft this save replaces is the one its client last read.

    Measured with two browser windows on one workflow: both drew, both saved,
    and the second write replaced the first's stored document with no revision
    holding it and no record anywhere that it had been saved. That is user work
    destroyed silently, which is worse than any refusal.

    Compared rather than merged: the alternative is this route deciding which of
    two people's drawings is the real one. The refused client keeps its own
    drawing -- nothing here touched it -- and the road forward is a read.

    A client that read NO draft expects none, and a draft that has appeared
    since is a conflict in exactly the same way: `None` on both sides agrees,
    and `None` against a stored draft does not.
    """
    standing = templates.load_draft(workflow_id)
    held = None if standing is None else draft_digest(standing.settled())
    if held != asked.expected_digest:
        raise ApiRefusal.conflicting_draft(workflow_id)


def publish_revision(
        templates: "TemplateStore", workflow_id: str,
        body: Mapping[str, Any]) -> Answer:
    """Turn a draft into a revision, or say exactly what stops it.

    The expected revision is the caller's, and it is what keeps two editors from
    silently overwriting each other's intent. A number the store has already
    passed is answered by the store's own arbitration -- identical bytes agree,
    different bytes are a ``RevisionConflict`` -- and a number that skips ahead
    of what exists is a request built on a workflow this client has not read.

    The draft is read ONCE, into a value, and that value is what is judged and
    what is published. Re-reading a durable source between the gate and the
    write is the defect ``http_api._gated`` exists to make unrepresentable, and
    it is exactly as available here: a draft replaced between the two would
    publish a document nothing had judged.

    The draft is discarded only AFTER the revision is on disk, and only when the
    draft is what was published: a caller that supplied its own document said
    nothing about the draft, so the draft is left standing.
    """
    asked = parse_workflow_revision(body)
    # The whole chain, under one per-workflow gate. Reading the draft, judging
    # it, writing the revision and consuming the draft are four steps against
    # one mutable file, and the server that runs them is a ThreadingHTTPServer:
    # a save landing between the judging and the consuming was deleted by a
    # publish that had never seen it, leaving no revision holding that work and
    # no record anywhere that it had been saved. Under the gate there are only
    # the two honest orders -- a save before the gate is taken makes the review
    # stale and the publish is refused, and a save after the whole chain is a
    # new draft standing beside the revision that was just written.
    with templates.transaction(workflow_id):
        return _publish_locked(templates, workflow_id, asked)


def _publish_locked(
        templates: "TemplateStore", workflow_id: str, asked) -> Answer:
    """One publish, with the workflow's draft held still for its duration."""
    revisions = templates.revisions(workflow_id)
    expected = 1 if not revisions else revisions[-1] + 1
    if asked.revision > expected:
        raise ApiRefusal.fixed("contract_invalid")
    from_draft = asked.document is None
    draft = templates.load_draft(workflow_id) if from_draft else None
    if from_draft and draft is None:
        # `draft_conflict` and not `contract_invalid`: the body is well formed
        # and the caller did nothing wrong -- the draft it named is not there.
        # Measured in a browser with two windows on one workflow: the second
        # saved and published, which consumed the one draft this workflow has,
        # and the first was told its REQUEST SHAPE was invalid for a confirm
        # that was perfectly well formed. A window told that can only offer the
        # same confirm again; told this, it re-reads and puts the revision that
        # now stands in front of the person. It is the same class as the save
        # road's refusal one door back, because it is the same fact: the draft
        # this client was working from is not what the store holds.
        raise ApiRefusal.unpublishable_draft(workflow_id, asked.revision)
    document = draft.settled() if draft is not None else asked.document
    _publishes_what_was_reviewed(from_draft, asked, document)
    # A publish that would write the document already standing is refused here
    # and not merely discouraged on screen. The read route computes the same
    # answer for the button's sake, but a client that never read it, or read it
    # and posted anyway, must not be able to create a durable record of an edit
    # that never happened -- one no reader could tell from a real one after the
    # fact. The comparison is the same function the read route calls.
    if _says_nothing_new(templates, workflow_id, document, asked.revision):
        raise ApiRefusal.fixed("contract_invalid")
    try:
        template = publish_candidate(
            document, workflow_id=workflow_id, revision=asked.revision)
    except DraftRefused as refused:
        return refused_with(refused)
    published = templates.save(template)
    if from_draft:
        # The BYTES that were read, not the workflow id. The gate already makes
        # this pair atomic; naming the draft makes it correct as well, so a
        # future caller that publishes without the gate leaves another client's
        # work standing instead of deleting it silently.
        templates.discard_draft(workflow_id, expecting=draft)
    return (201 if published.created else 200), template.as_dict()


def _publishes_what_was_reviewed(from_draft: bool, asked, document) -> None:
    """The draft about to be written is the one the caller says it reviewed.

    The review a person confirmed named a specific draft, and between that
    screen and this call another client may have saved a different one. There
    is no notification on that road -- saving a draft publishes no frame -- so
    the reviewing window cannot know, and publishing the CURRENT draft under a
    review of an older one writes a revision nobody read. Immutability then
    keeps it forever.

    Compared rather than resolved: the caller is told to look again, because
    the alternative is this route deciding which of two drawings a person meant.
    A caller supplying its own document is exempt, since those bytes ARE the
    identity it named.

    ``draft_changed`` and not ``contract_invalid``. The body is well formed and
    the caller did nothing wrong -- what changed is the world -- and a client
    told only that its request shape is invalid can do nothing but offer the
    same stale review again. Told THIS, a window can do the one useful thing:
    fetch the draft that is standing now and put it in front of the person.
    """
    if from_draft and asked.reviewed_digest != draft_digest(document):
        raise ApiRefusal.fixed("draft_changed")


def _says_nothing_new(templates, workflow_id: str, document, revision: int) -> bool:
    """Whether publishing this document would repeat the standing revision.

    The standing revision is read through the contract's own door; a revision
    this build cannot read is not a document anything can be compared against,
    so the answer is False and the publish proceeds on its own merits.
    """
    standing = revision - 1
    if standing < 1:
        return False
    try:
        published = templates.load(workflow_id, standing).as_dict()
    except ContractError:
        return False
    return unchanged_from_published(
        document, published, workflow_id=workflow_id, revision=revision)


def refused_with(refused: DraftRefused) -> Answer:
    """One ``contract_invalid``, carrying WHY beside the frozen envelope.

    The envelope is not widened: ``error`` is byte for byte the shape every
    other refusal on this surface answers with, so a client's refusal reader
    needs no second case. ``diagnostics`` is its sibling, and it exists because
    "this document is not a template" is useless to somebody drawing one.

    The rows come from the one real constructor, so a document this route
    refuses is exactly a document the read route already called unpublishable.
    """
    answer = ApiRefusal.fixed("contract_invalid")
    return answer.status, {
        **answer.as_dict(),
        "diagnostics": [dict(row) for row in refused.diagnostics]}


def open_run(
        store: "RunStore", templates: "TemplateStore", body: Mapping[str, Any],
        *, tasks: "TaskStore", clock, ids, reachable, judge_plan, publish,
        hold_route) -> Answer:
    """Open one run, and give it its plan in the same call.

    The standing run is looked for FIRST, before the task store, the clock,
    the roster, the template store or the registry is consulted -- the rule
    every other mutating route follows: a client whose reply was lost is owed
    the same answer from a process with a different roster, or over a task
    store that has since lost or corrupted the record, because what it asks
    about is already durable. A standing run never touches the task store;
    its binding is read off its own frozen configuration for the compare.

    Only a run about to be CREATED resolves its task through the store and is
    judged, whole, before one durable byte is written: the roster must carry
    every provider named, the revision must exist, and the plan that revision
    would materialize against this configuration must be one the bound
    adapters can serve. The revision is read ONCE and the value judged is the
    value appended -- ``_gated`` next door makes the alternative
    unrepresentable; re-reading a durable source between the gate and the
    write is the defect it was written for.
    """
    asked = parse_run(body)
    hold_route(asked.run_id)
    standing = _standing_run(store, asked.run_id)
    snapshot = _frozen_snapshot(asked, tasks, standing)
    checked = None if standing is not None else _judged_revision(
        templates, asked, snapshot, reachable, judge_plan)
    with store.transaction():
        hold_route(asked.run_id)
        standing = _standing_run(store, asked.run_id)
        if standing is not None:
            envelope = _repeats_the_standing_run(asked, snapshot, standing)
            created, graph = False, _standing_graph(standing)
        else:
            envelope = asked.build(snapshot, clock())
            store.create_run(envelope, snapshot)
            created, graph = True, None
            if asked.workflow_id is not None:
                graph = materialize(
                    _gated(checked), asked.binding, snapshot,
                    graph_id=ids("graph"), run_id=asked.run_id,
                    created_at=clock())
                store.append(graph)
    if created:
        publish(asked.run_id)
    return (201 if created else 200), {
        "run": envelope.as_dict(), "config": plain_json(snapshot),
        "graph": None if graph is None else graph.as_dict()}


def _frozen_snapshot(
        asked: RunInput, tasks: "TaskStore", standing) -> dict[str, Any]:
    """The configuration this run freezes, or the one it must repeat.

    A run about to be CREATED resolves its task through the store before the
    snapshot exists, so what is frozen is the record's own scope and never the
    caller's word for it; a task the store does not hold is refused by the id
    the caller sent, before the clock, the roster or the template store is
    consulted. A run that already STANDS at this id does not touch the task
    store: what it froze is durable, and a client whose reply was lost is owed
    the same answer whether the record has since vanished, gone corrupt or
    been replaced. Its binding is read off the standing configuration when
    that names the task the caller names -- none and none included -- and the
    retry road then compares the whole snapshot as it does every other field.
    """
    if standing is None:
        return asked.snapshot(
            task_routes.resolve_task_binding(tasks, asked.task_id))
    return asked.snapshot(_standing_binding(asked, standing))


def _standing_binding(asked: RunInput, standing) -> TaskBinding | None:
    """The task the standing run froze, when it is the one the caller names.

    Any other task under a standing run id is a conflict before a binding is
    even spelled: there is no record to resolve, because no run is about to be
    created, and inventing a scope from the caller's id would freeze the one
    thing the store exists to keep the caller from choosing. A binding that is
    present and malformed is `run_corrupt`, by the one rule every road holds.
    """
    bound = _task(standing.config)
    if (None if bound is None else bound.task_id) != asked.task_id:
        raise RecordConflict(
            f"run {asked.run_id!r} already records different facts")
    return bound


def _judged_revision(templates, asked, snapshot, reachable, judge_plan):
    """Judge a run about to be created, and hand back the value that was judged.

    Only a run about to be CREATED is judged -- the caller has already looked
    for a standing one and asks this for none: a client whose reply was lost
    is entitled to the same answer from a process that starts with a different
    roster, because what it is asking about is already durable.

    The revision is read ONCE, here, and it is this VALUE the caller appends.
    Handing back the name instead would let the caller read it again between the
    gate and the write, which is exactly the defect this shape makes
    unrepresentable.
    """
    _providers_are_configured(asked, reachable)
    if asked.workflow_id is None:
        return None
    checked = _workflow_revision(templates, asked)
    probe = materialize(
        checked, asked.binding, snapshot, graph_id=_PROBE_GRAPH,
        run_id=asked.run_id, created_at=_PROBE_AT)
    # The task this run is about to freeze is the snapshot's own -- judging the
    # plan that is about to be written, not a name re-read from anywhere.
    work_scope_admits(probe.nodes, frozen_config_task(snapshot))
    judge_plan(snapshot, asked.run_id, probe.nodes)
    return checked


def _standing_run(store: "RunStore", run_id: str):
    """The run already at this identity, or None -- and never an exception.

    The directory is looked at rather than a refusal caught, because "absent"
    and "present and corrupt" are two different answers, and swallowing a
    ``StoreError`` would call the second the first.
    """
    if not store.run_path(run_id).is_dir():
        return None
    return store.read(run_id)


def _repeats_the_standing_run(asked, snapshot: Mapping[str, Any], standing):
    """A run identity is written once, so a second open IS it or conflicts.

    The candidate is rebuilt on the standing envelope's own ``created_at``: the
    caller never supplied one, so comparing anything else would call every
    honest retry a conflict.
    """
    candidate = asked.build(snapshot, standing.envelope.created_at)
    if (candidate.as_dict() != standing.envelope.as_dict()
            or plain_json(standing.config) != snapshot):
        raise RecordConflict(
            f"run {asked.run_id!r} already records different facts")
    return standing.envelope


def _providers_are_configured(asked, reachable) -> None:
    """Every named provider is one THIS BUILD resolved as available.

    The empty roster is answered first and separately, because it is a
    different situation and a different instruction: nobody has written a
    provider configuration yet, and the refusal says where to write one. A
    caller told "provider 'x' is not available" when the answer is "there are
    none at all" would go looking for a typo.
    """
    if not reachable:
        raise ApiRefusal.service_no_providers()
    for participant in asked.participants:
        if participant.provider_id not in reachable:
            raise ApiRefusal.service_unknown_provider(participant.provider_id)


def _workflow_revision(templates: "TemplateStore", asked):
    """Read the revision this run will follow, ONCE, into one value.

    ``ContractError`` for `read_revision`'s reason: a stored document that opens
    and is not a template raises the base class, and a run asking to follow it
    is asking for a revision this build cannot serve -- not making an invalid
    request.
    """
    assert asked.workflow_id is not None and asked.revision is not None
    try:
        return templates.load(asked.workflow_id, asked.revision)
    except ContractError:
        raise ApiRefusal.missing_revision(
            asked.workflow_id, asked.revision) from None


def standing_graph(recovered):
    """The one graph this run already follows, if it follows any."""
    return next((row.value for row in recovered.records
                 if row.kind == "graph_definition"), None)


_standing_graph = standing_graph


def plain_json(value: object) -> object:
    """Copy a frozen JSON graph into the plain containers an encoder owns."""
    if isinstance(value, Mapping):
        return {key: plain_json(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [plain_json(item) for item in value]
    return value


def recovered_payload(
        recovered, tasks: "TaskStore | None" = None) -> dict[str, Any]:
    """One run read whole: its envelope, frozen config, journal, plan and task.

    Every part but the last two is a durable record verbatim. The plan, the
    digest computed over it and the position computed from the journal are
    computed here and stored nowhere, so nothing in them can drift from the
    records they were read out of. ``task`` is the run's frozen binding joined
    to the record it names: the boundary hands its store in, and a caller that
    hands none -- a `RecoveredRun` cannot name its project root, so nothing
    here could build one -- gets the binding with ``unreadable`` true rather
    than a title invented for it.
    """
    return {
        "run": recovered.envelope.as_dict(),
        "config": plain_json(recovered.config),
        "records": [{"record_type": row.kind, "record": row.value.as_dict()}
                    for row in recovered.records],
        "warnings": list(recovered.warnings),
        "graph": graph_payload(recovered),
        "task": _task_payload(recovered.config, tasks),
    }


def _task_payload(
        config: Mapping[str, Any], tasks: "TaskStore | None") -> dict[str, Any] | None:
    """The task a run froze, its title joined from the record at read time.

    ``null`` when the configuration carries no binding. A binding present and
    malformed is already-frozen bytes and not a malformed caller payload, so it
    is ``run_corrupt`` -- the word `_controls` uses for the same class of fact
    -- and never "no task". The title is ``null`` and ``unreadable`` true when
    the record is absent, corrupt, reachable by a second name, or no store was
    handed in: the binding still stands, because it is frozen, and what cannot
    be had is said rather than spelled as a task called nothing. A record's
    `RouteNotOwned` is about the TASK's route, never this run's, so it is a
    fact on the task and not a refusal of the run read.
    """
    try:
        bound = frozen_config_task(config)
    except ContractError as error:
        raise ApiRefusal.fixed("run_corrupt") from error
    if bound is None:
        return None
    record = None
    if tasks is not None:
        try:
            record = tasks.standing(bound.task_id)
        except (CorruptTask, RouteNotOwned):
            record = None
    return {"id": bound.task_id, "work_scope": bound.work_scope,
            "title": None if record is None else record.title,
            "unreadable": record is None}


def list_runs(store: "RunStore", providers) -> Answer:
    """Every run in this project, and the roster this build resolved.

    Nothing here is stored and nothing here writes: every field of every row is
    computed from the run's own durable records, and the replay is ``read``
    rather than ``recover``, so a listing repairs nothing either.
    """
    return 200, {
        "runs": [run_row(store, run_id) for run_id in run_ids(store)],
        "providers": provider_projection(providers),
    }


def run_ids(store: "RunStore") -> tuple[str, ...]:
    """Every run directory this store could address, ascending.

    Read off the directory rather than an index, for the template store's
    reason: the directories ARE the record. A name that is not a run id names no
    run this store could ever open, and a half-built staging directory is one of
    those -- ``create_run`` prefixes its with a dot, which the id grammar refuses
    at the first character.
    """
    try:
        entries = sorted(store.runs_root.iterdir())
    except OSError:
        return ()
    found: list[str] = []
    for entry in entries:
        if not entry.is_dir():
            continue
        try:
            found.append(_id("run_id", entry.name))
        except ContractError:
            continue
    return tuple(found)


def run_row(store: "RunStore", run_id: str) -> dict[str, Any]:
    """One run as a list row, with every derived word named for its source.

    ``envelope_status`` is the DURABLE word and it is a creation-time one: a
    ``RunEnvelope`` is immutable, so its ``status`` says what the run was opened
    as and never where it now stands. It is spelled with ``envelope_`` in front
    of it precisely so that no reader can take it for a live position.

    What is live is derived here, and each key says which records it came from:

    - ``undecided_gates`` -- the plan's gate nodes whose ``gate_id`` carries no
      unsuperseded ``decision`` receipt, counted through the same projection the
      run read answers with. ``0`` when the run follows no plan.
    - ``open_actions`` -- ``action_request`` records with no ``action_result``
      naming their ``action_id``.
    - ``last_outcome`` -- the ``outcome`` of the last ``action_result`` in
      append order, or ``null`` when there is none.

    - ``workflow_id`` / ``revision`` -- WHICH plan this run froze itself to
      follow, read out of the run's own frozen configuration. Both are ``null``
      together for a run opened with no workflow at all, which `conduct preview`
      and the control loop both are. They are read rather than derived: nothing
      here reconstructs a provenance, and a run whose configuration names none
      reports none.
    - ``task_id`` -- WHICH task this run froze itself to belong to, off the same
      configuration; ``null`` for a run bound to none. A binding present and
      malformed makes the row unreadable: corrupt must never read as "no task".

    There is deliberately no derived overall phase word. The journal does not
    carry one, and a word invented here would be a guess a reader trusts.

    A run that does not replay is LISTED, with ``unreadable`` true and every
    derived field null. A run you cannot see is worse than one you cannot read.
    """
    row: dict[str, Any] = {
        "run_id": run_id, "unreadable": True, "cycle_id": None,
        "created_at": None, "mode": None, "envelope_status": None,
        "graph_id": None, "undecided_gates": None, "open_actions": None,
        "last_outcome": None, "workflow_id": None, "revision": None,
        "task_id": None,
    }
    if run_route_violations(store, run_id):
        return row
    try:
        recovered = store.read(run_id)
        task = frozen_config_task(recovered.config)
    except (StoreError, ContractError):
        return row
    row.update(_derived_row(recovered, task))
    return row


def _derived_row(recovered, task: TaskBinding | None) -> dict[str, Any]:
    """The live half of a run row, computed from the journal it replayed.

    Separated from the row above so the row's own shape -- what a reader gets
    when a run CANNOT be read -- is visible on its own. Every key here is
    derived; none is stored anywhere. ``task`` is the binding the row already
    read, handed in rather than read twice.
    """
    values = [stored.value for stored in recovered.records]
    results = [value for value in values
               if isinstance(value, ActionResultReceipt)]
    answered = {receipt.action_id for receipt in results}
    requested = {value.action_id for value in values
                 if isinstance(value, ActionRequest)}
    graph = graph_payload(recovered)
    runtime = graph["runtime"]
    # Read, never reconstructed: the frozen configuration is the one document
    # that can say which revision this run followed, and `config_digest` has
    # already re-verified it on this very replay.
    followed = frozen_config_workflow(recovered.config)
    return {
        "unreadable": False,
        "workflow_id": None if followed is None else followed[0],
        "revision": None if followed is None else followed[1],
        "task_id": None if task is None else task.task_id,
        "cycle_id": recovered.envelope.cycle_id,
        "created_at": recovered.envelope.created_at,
        "mode": recovered.envelope.mode.value,
        "envelope_status": recovered.envelope.status,
        "graph_id": (None if graph["definition"] is None
                     else graph["definition"]["graph_id"]),
        "undecided_gates": 0 if runtime is None else sum(
            1 for node in runtime["nodes"] if node.get("decision") == "idle"),
        "open_actions": len(requested - answered),
        "last_outcome": results[-1].outcome if results else None,
    }
