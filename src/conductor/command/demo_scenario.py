"""The demo's command-side story, written by the same doors a real project uses.

`conduct demo` used to copy four Protocol v1 files and serve them. The Studio
reads none of Protocol v1, so the front door opened on an empty Overview, an
empty workflow list and an empty run list, while the entire demonstration sat on
`/state.json` where only the classic panel could see it. A person meeting this
product for the first time met nothing.

WHAT THIS WRITES, and why it is not a fixture. Every byte below goes through
`TemplateStore.save` and `RunStore.append` -- the production writers, with every
causal relation they enforce. The graph is `materialize`d from the shipped
starter against the run's own frozen configuration. The journal is replayed and
re-validated on every read, exactly as a journal this product wrote in anger
would be. Nothing here is a shape invented for a screen: if a relation in
`graph_causality`, `attempt_replay` or `artifacts` changed underneath it, this
would stop building rather than quietly demonstrate something the product no
longer does.

That is also why the story is BUILT rather than shipped as frozen bytes. A
packaged `runs/` tree would be a second set of durable identities to migrate
every time the record vocabulary grows, and it could drift from the writers
without anything noticing. This cannot drift: it is the writers.

WHAT IT DOES NOT DO. It spawns no process and reaches no adapter. The attempt
events and the receipt describe an execution that this function did not perform,
which is what a scenario is -- and `conduct demo` says so on stderr, into a
throwaway directory, over a copy of the fixture that is never written back.

THE SHAPE OF THE STORY. Two tasks, written by `TaskStore.create_task`: the run
belongs to the first through the `task` binding frozen inside its configuration,
and the second has not been run yet. One workflow with one published revision;
one run frozen against that exact revision, its roles carried by three different
participants; one step carried from proposal to verified receipt through all
five durable steps the Runs screen draws; one gate a person already answered,
and one still waiting for them. Both gates are real: the approved one is a
`DecisionReceipt` in the journal with its own exclusive file, and the waiting
one is waiting in the only way this product represents waiting -- a gate node no
receipt has answered.
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .attempts import AttemptEvent, action_request_digest
from .contracts import (
    ActionProposal,
    ActionRequest,
    ActionResultReceipt,
    DecisionReceipt,
    EvidenceRef,
    RunEnvelope,
)
from .graph_template import RunBinding, load_template, materialize
from .run_store import RunStore, snapshot_digest
from .task_contracts import TaskRecord
from .task_store import TaskStore
from .template_store import TemplateStore

#: The starter the story is told with. `dalio-v2` and not `dalio-v1`: v1's
#: review steps name nowhere to publish a result, so a run of it cannot produce
#: an artifact, and the demo would have to leave out the half of the product
#: that explains what a step actually did.
STARTER = "dalio-v2"
#: The workflow a person opens. Named for what it is rather than for the
#: template it came from -- a reader meeting this build should see a project,
#: not a fixture id.
WORKFLOW_ID = "release-review"
REVISION = 1
RUN_ID = "demo-run-001"
CYCLE_ID = "release-cycle"
#: The participant that carries the effecting step.
INSTANCE_ID = "demo-implementer"
#: Who carries each of the starter's roles: three different participants, so
#: the scene draws a crew rather than one planet doing everything. Each is bound
#: to a different catalogued provider (`_adapter_id`), in this order.
PARTICIPANTS = (INSTANCE_ID, "demo-analyst", "demo-architect")
ROLES = {"role-thinker": "demo-analyst", "role-diagnostician": "demo-analyst",
         "role-designer": "demo-architect", "role-implementer": INSTANCE_ID}
#: The task this run belongs to, and a second task nobody has run yet. The
#: binding is the frozen `{"task": {"id", "work_scope"}}` key; the scope is the
#: id, as the task route creates it.
TASK_ID = "task-release-1-4"
TASK_TITLE = "Review the 1.4 release before it ships"
SECOND_TASK_ID = "task-login-timeout"
SECOND_TASK_TITLE = "Fix the login timeout on slow networks"
#: The gate the story shows ANSWERED, and the gate it leaves WAITING. Both ids
#: come from the shipped starter; a starter that renamed either would fail to
#: build here rather than silently demonstrate one gate.
ANSWERED_GATE = "gate-confirm-do"
WAITING_GATE = "gate-result"
#: The step the story carries all the way. It is the starter's one effecting
#: step, which is the one whose timeline is worth reading.
CARRIED_NODE = "do"
#: One fixed instant. A demo that read a clock would produce different durable
#: bytes on every materialization, so two people following the same script
#: would be looking at different digests.
NOW = "2026-03-02T09:00:00Z"


def _ids(prefix: str) -> str:
    """Deterministic identities, so the same demo is the same demo."""
    return f"{prefix}-demo-0001"


def _adapter_id(rank: int = 0) -> str:
    """The provider this demo binds a participant to, ASKED for.

    Never spelled here. This module sits on the request path, where naming a
    provider is refused by construction -- `tests/test_alpha1_gate_g_provider
    _breadth.py` reads every literal in this package and fails on any that
    carries a provider identity, and it is right to: a demo that named one
    would be the first place a provider id leaked into generic code, and it
    would go on demonstrating a provider long after the roster had moved.

    The catalogued id at `rank` in sorted order, so the answer is stable across
    runs and follows whatever this build actually ships.
    """
    from .providers import PROVIDER_CATALOG

    return sorted(PROVIDER_CATALOG)[rank]


def _snapshot() -> dict[str, Any]:
    """The frozen configuration this run replays against.

    Only keys the Studio's payload boundary admits -- `cycle`, `instances`,
    `workflow`, `task` -- because any other would make the whole run
    unreadable to the window rather than partly readable.

    `workflow` and `task` are what make this run's identity durable: they live
    INSIDE the document `config_digest` is taken over, so replay re-verifies
    them and no later revision or retitling can change what this run followed
    or whose it is.
    """
    return {
        "cycle": {"id": CYCLE_ID},
        "instances": [{"id": instance, "adapter": _adapter_id(rank)}
                      for rank, instance in enumerate(PARTICIPANTS)],
        "task": {"id": TASK_ID, "work_scope": TASK_ID},
        "workflow": {"id": WORKFLOW_ID, "revision": REVISION},
    }


def _publish(templates: TemplateStore) -> None:
    """Publish the starter as this workflow's first immutable revision."""
    template = load_template(STARTER)
    document = dict(template.as_dict())
    document["template_id"] = WORKFLOW_ID
    document["revision"] = REVISION
    document["title"] = "Release review"
    templates.save(type(template).from_dict(document))


def _plan(templates: TemplateStore, store: RunStore) -> Any:
    """Materialize the published revision into this run's own frozen plan.

    Read back out of the store rather than kept from `_publish`: the revision a
    run follows is the one on disk, and reading it here is the same road
    `open_run` takes.
    """
    template = templates.load(WORKFLOW_ID, REVISION)
    binding = RunBinding.from_dict(
        {"assignments": {role: ROLES[role] for role in template.roles}})
    definition = materialize(
        template, binding, store.read(RUN_ID).config,
        graph_id=_ids("graph"), run_id=RUN_ID, created_at=NOW)
    store.append(definition)
    return definition


def _node(definition, node_id: str):
    return next(row for row in definition.nodes if row.node_id == node_id)


def _answer_the_first_gate(store: RunStore, digest: str) -> None:
    """The decision a person already made, as the receipt it really is.

    Appended through `RunStore.append`, which writes the exclusive file in
    `decisions/` before the journal line -- the two-home protocol. A receipt
    hand-written into `records.jsonl` would replay as a run whose exclusive
    file is missing, which is a corrupt run rather than a demonstration.
    """
    store.append(DecisionReceipt(
        receipt_id=_ids("decision"), run_id=RUN_ID, gate_id=ANSWERED_GATE,
        action="approve", actor="release-owner", decided_at=NOW,
        reason="The plan is what we agreed; carry it out.",
        scope_refs=(CARRIED_NODE,), config_digest=digest))


def _ask_and_authorize(store: RunStore, node) -> ActionRequest:
    """What was proposed, and what a person's confirmation authorized.

    Two records rather than one because they are two events: a proposal is a
    request FOR an attempt, and only the request is an attempt. The store holds
    them to each other -- the request repeats every fact of the proposal it
    names in `idempotency_key`, and both are held to the plan's own node.
    """
    proposal = ActionProposal(
        proposal_id=_ids("proposal"), run_id=RUN_ID, attempt_id=_ids("attempt"),
        instance_id=node.instance_id, capability=node.capability,
        arguments=node.payload(), scope=("src", "docs"),
        proposed_by=INSTANCE_ID, proposed_at=NOW, timeout_seconds=900,
        rationale="Carry out the step the gate approved.",
        config_digest=store.read(RUN_ID).envelope.config_digest,
        node_id=node.node_id)
    store.append(proposal)
    request = ActionRequest(
        action_id=_ids("action"), run_id=RUN_ID, attempt_id=proposal.attempt_id,
        instance_id=proposal.instance_id, capability=proposal.capability,
        arguments=proposal.arguments, scope=proposal.scope,
        requested_by="release-owner", requested_at=NOW,
        idempotency_key=f"dispatch-{proposal.proposal_id}",
        timeout_seconds=proposal.timeout_seconds,
        preview_digest=proposal.preview_digest, mode="confirm",
        node_id=proposal.node_id)
    store.append(request)
    return request


def _observe_and_verify(store: RunStore, request: ActionRequest) -> None:
    """What happened to the authorized attempt, in the order it can be known.

    The lease is appended BEFORE any effect, so a crash after it leaves a run
    that knows an effect may have happened; the observation is what was seen;
    the evidence must land after the observation and be verified by the bound
    adapter; and only then may a receipt say `succeeded` and point at it. Each
    of those is a relation the store enforces, not an ordering chosen here.
    """
    shared = {
        "run_id": RUN_ID, "action_id": request.action_id,
        "attempt_id": request.attempt_id, "instance_id": request.instance_id,
        "adapter_id": _adapter_id(), "recorded_at": NOW,
        "request_digest": action_request_digest(request),
        "recovery_ref": _ids("recovery"), "schema_version": 2,
    }
    store.append(AttemptEvent(
        event_id=_ids("lease"), phase="effect_lease", outcome=None,
        exit_code=None, **shared))
    store.append(AttemptEvent(
        event_id=_ids("observed"), phase="execution_observed",
        outcome="succeeded", exit_code=0, **shared))
    evidence = EvidenceRef(
        evidence_id=_ids("evidence"), run_id=RUN_ID, kind="verification",
        uri=f"verification/{request.action_id}",
        label="The step's own verification, recorded after it was observed.",
        created_by=_adapter_id(), observed_at=NOW,
        verification="verified", verified_by=_adapter_id(),
        verified_at=NOW)
    store.append(evidence)
    store.append(ActionResultReceipt(
        receipt_id=_ids("receipt"), action_id=request.action_id, run_id=RUN_ID,
        attempt_id=request.attempt_id, instance_id=request.instance_id,
        outcome="succeeded", observed_at=NOW, exit_code=0,
        evidence_refs=(evidence.evidence_id,),
        detail="Observed as succeeded and verified by the bound adapter."))


def build(project_root: str | Path) -> Mapping[str, Any]:
    """Write the demo's workflow, revision and run into one project.

    Args:
        project_root: The directory whose `conductor/` this writes into. It
            must already exist; `conduct demo` points this at the throwaway
            copy it just materialized.

    Returns:
        The identities a caller may want to name in a message: the workflow,
        its revision, the run, the task it belongs to, and the gate still
        waiting for a person.

    Raises:
        StoreError: A durable relation refused a record. That is not a demo
            fault to be swallowed -- it means this story is no longer one the
            product's own rules admit, and it must be seen.
    """
    root = Path(project_root)
    templates, store = TemplateStore(root), RunStore(root)
    tasks = TaskStore(root)
    for task_id, title in ((TASK_ID, TASK_TITLE), (SECOND_TASK_ID, SECOND_TASK_TITLE)):
        tasks.create_task(TaskRecord(
            task_id=task_id, title=title, work_scope=task_id, created_at=NOW))
    _publish(templates)
    snapshot = _snapshot()
    store.create_run(
        RunEnvelope(run_id=RUN_ID, cycle_id=CYCLE_ID, created_at=NOW,
                    config_digest=snapshot_digest(snapshot), mode="confirm"),
        snapshot)
    definition = _plan(templates, store)
    digest = store.read(RUN_ID).envelope.config_digest
    _answer_the_first_gate(store, digest)
    _observe_and_verify(store, _ask_and_authorize(
        store, _node(definition, CARRIED_NODE)))
    return {
        "workflow_id": WORKFLOW_ID, "revision": REVISION, "run_id": RUN_ID,
        "task_id": TASK_ID,
        "answered_gate": ANSWERED_GATE, "waiting_gate": WAITING_GATE,
    }
