"""The flow of a workflow over HTTP: read it, write it, publish it (spec 7.1, ADR-9).

The same orchestration `studio_routes` gives the draft and revision routes, one door for the
desk: a flow goes in, the server compiles it, holds it to the rules, keeps the draft under the
same optimistic check as `/draft`, and publishes a revision under the same workflow lock as
`/revisions`. Every function answers `(status, payload)`; the boundary shapes the response.
The verdict on which harness a role is given to belongs here, to the layer that holds the
registry (spec 7.1); the pure modules only judge the facts they are handed.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .api_refusals import ApiRefusal
from .authorization_terms import human_identity
from .contract_values import ContractError, _digest, _id
from .flow_rules import FLOW_CODES, flow_rules
from .graph_template import GraphTemplate, load_template
from .plan_budget import plan_budget, product_limits  # noqa: F401 - re-exported
from .project_cycle import PinRecord
from .studio_routes import _replaces_what_was_read, refused_with
from .workflow_draft import (
    DraftRefused, draft_digest, parse_document, publish_candidate, saved_draft,
    unchanged_from_published)
from .workflow_flow import FlowShapeError, compile_flow, import_template, settled_flow

Answer = tuple[int, dict[str, Any]]
#: Workflows the product ships under these names accept only their own starter (spec 7.1).
RESERVED_PREFIX = "desk-"
_FIELDS = frozenset({"source", "expected_digest", "expected_absent", "publish_revision", "binding"})
_COPY_KEYS = {"workflow_id", "revision"}


@dataclass(frozen=True)
class FlowWrite:
    """One `POST …/flow`, judged for shape: where the flow comes from and what to do with it."""

    source: str
    value: Any
    expected_digest: str | None
    publish_revision: int | None
    binding: dict[str, str] | None


def binding_facts(registry: Any, binding: Mapping[str, str]) -> dict[str, dict | None]:
    """What each role's harness can do, as the registry recorded it; None when it has none."""
    manifests = {row.adapter_id: row for row in registry.manifests()}
    facts: dict[str, dict | None] = {}
    for role, provider in binding.items():
        manifest = manifests.get(provider)
        facts[role] = None if manifest is None else {
            "capabilities": list(manifest.capabilities),
            "verifies": [name for name in manifest.capabilities
                         if registry.verifies_independently(provider, name)]}
    return facts


# --- the body ---------------------------------------------------------------------------------


def parse_flow_write(body: object) -> FlowWrite:
    """Validate a `FlowWrite`: closed keys, one source, exactly one expectation."""
    if not isinstance(body, Mapping) or any(not isinstance(key, str) for key in body):
        raise ApiRefusal.fixed("contract_invalid")
    supplied = set(body)
    if "source" not in supplied or supplied - _FIELDS:
        raise ApiRefusal.fixed("contract_invalid")
    kind, value = _source_of(body["source"])
    expected = _expectation(body)
    revision = _revision_number(body.get("publish_revision"))
    return FlowWrite(kind, value, expected, revision, _binding(body.get("binding")))


def _contract(check: Callable[..., Any], *arguments: Any) -> Any:
    try:
        return check(*arguments)
    except ContractError:
        raise ApiRefusal.fixed("contract_invalid") from None


def _source_of(source: object) -> tuple[str, Any]:
    if not isinstance(source, Mapping) or len(source) != 1:
        raise ApiRefusal.fixed("contract_invalid")
    (kind, value), = source.items()
    if kind == "flow" and isinstance(value, Mapping):
        return kind, value
    if kind == "starter_id":
        return kind, _contract(_id, "starter_id", value)
    if kind == "copy_of" and isinstance(value, Mapping) and _COPY_KEYS == set(value):
        return kind, (_contract(_id, "workflow_id", value["workflow_id"]),
                      _revision_number(value["revision"], required=True))
    raise ApiRefusal.fixed("contract_invalid")


def _expectation(body: Mapping[str, Any]) -> str | None:
    """The digest of the draft the client read, or None for `expected_absent: true`."""
    if ("expected_absent" in body) == ("expected_digest" in body):
        raise ApiRefusal.fixed("contract_invalid")
    if "expected_absent" in body:
        if body["expected_absent"] is not True:
            raise ApiRefusal.fixed("contract_invalid")
        return None
    return _contract(_digest, "expected_digest", body["expected_digest"])


def _revision_number(value: object, *, required: bool = False) -> int | None:
    if value is None and not required:
        return None
    if type(value) is not int or value < 1:
        raise ApiRefusal.fixed("contract_invalid")
    return value


def _binding(value: object) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ApiRefusal.fixed("contract_invalid")
    return {_contract(_id, "role_id", role): _contract(_id, "provider_id", provider)
            for role, provider in value.items()}


# --- the state ----------------------------------------------------------------------------------


def read_flow(templates: Any, workflow_id: str, limits: Mapping[str, int]) -> Answer:
    """`GET …/flow`: the flow being edited, or the latest revision's, with its diagnostics."""
    return 200, _state(templates, workflow_id, limits)


def _state(templates: Any, workflow_id: str, limits: Mapping[str, int],
           facts: Mapping[str, Any] | None = None,
           published: dict[str, Any] | None = None) -> dict[str, Any]:
    revisions = templates.revisions(workflow_id)
    latest = revisions[-1] if revisions else None
    standing = _latest_document(templates, workflow_id, latest)
    draft = templates.load_draft(workflow_id)
    shown = standing if draft is None else draft.settled()
    flow = None if shown is None else _flow_or_none(shown)
    document, rows, budget = _judge(flow, workflow_id, facts, limits, shown is not None)
    return {
        "workflow_id": workflow_id,
        "source": "draft" if draft is not None else ("none" if shown is None else "published"),
        "draft_digest": None if draft is None else draft_digest(shown),
        "flow": flow,
        "revision_flow": None if standing is None else _flow_or_none(standing),
        "diagnostics": rows,
        "publishable": flow is not None and not _errors(rows),
        "budget": budget,
        "latest_revision": latest,
        "next_revision": 1 if latest is None else latest + 1,
        "published": published,
    }


def _latest_document(templates: Any, workflow_id: str, latest: int | None) -> dict | None:
    """The latest revision as stored, or None when there is none or it cannot be read."""
    if latest is None:
        return None
    try:
        return templates.load(workflow_id, latest).as_dict()
    except ContractError:
        return None


def _flow_or_none(document: Mapping[str, Any]) -> dict[str, Any] | None:
    try:
        return import_template(document)
    except ContractError:
        return None


def _errors(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if row["severity"] == "error"]


def _judge(flow: object, workflow_id: str, facts: Mapping[str, Any] | None,
           limits: Mapping[str, int], stored: bool = True):
    """`(compiled document, rows, budget)` for a flow; a flow that cannot be opened is one row.

    The document is None when the form refuses the flow. The budget is filled only when the
    compiled document builds a template (spec 7.1, step 2).
    """
    if flow is None:
        rows = [_row("template_refused")] if stored else []
        return None, rows, None
    try:
        settled = settled_flow(flow)
    except FlowShapeError:
        return None, flow_rules(flow), None
    document = compile_flow(settled)
    budget = _budget_of(document, workflow_id, limits)
    return document, flow_rules(settled, document, facts, budget), budget


def _row(code: str) -> dict[str, Any]:
    return {"code": code, "severity": FLOW_CODES[code], "at": None, "params": {}}


def _budget_of(document: Mapping[str, Any], workflow_id: str,
               limits: Mapping[str, int]) -> dict[str, Any] | None:
    try:
        template = GraphTemplate.from_dict(
            {**document, "template_id": workflow_id, "revision": 1})
    except ContractError:
        return None
    return plan_budget(*template.settled(), limits)


# --- the write ----------------------------------------------------------------------------------


def write_flow(templates: Any, workflow_id: str, body: Mapping[str, Any], clock: Callable[[], str],
               limits: Mapping[str, int],
               facts_of: Callable[[Mapping[str, str]], Mapping[str, Any]] | None = None) -> Answer:
    """`POST …/flow`: source to flow, rules and compile, the draft, and when asked a revision.

    A flow the form or the core refuses is `contract_invalid` with the rows and nothing is
    saved. Any other fault is saved with the draft and shown in `diagnostics`; only a
    publication needs a clean flow. A publication that cannot be made (a fault row, a number
    the store holds with other facts) is refused whole: no draft is saved either, so the
    expectation the client held still stands. `201` when this call made a draft that stands
    or a revision, `200` when nothing is new.
    """
    asked = parse_flow_write(body)
    if workflow_id.startswith(RESERVED_PREFIX) and (
            asked.source != "starter_id" or asked.value != workflow_id):
        raise ApiRefusal.fixed("contract_invalid")
    facts = None if asked.binding is None or facts_of is None else facts_of(asked.binding)
    document, rows, _ = _judge(_source_flow(templates, asked), workflow_id, facts, limits)
    if document is None:
        return refused_with(DraftRefused(tuple(rows)))
    try:
        draft_document = parse_document(document)
    except ContractError:
        return refused_with(DraftRefused(tuple(rows or [_row("template_refused")])))
    with templates.transaction(workflow_id):
        if not templates.draft_path(workflow_id).parent.is_dir():
            templates.admit_draft_write(workflow_id)
        _replaces_what_was_read(templates, workflow_id, asked)
        _hold_publish_number(templates, workflow_id, asked.publish_revision)
        plan, refused = _judged_publication(
            templates, workflow_id, asked.publish_revision, draft_document, rows)
        if refused is not None:
            return refused
        created = saved_draft(templates, workflow_id, draft_document, clock)
        published = _publish(templates, workflow_id, plan)
        state = _state(templates, workflow_id, limits, facts, published)
    made = (published is not None and published["created"]) or (
        created and state["source"] == "draft")
    return (201 if made else 200), state


def _source_flow(templates: Any, asked: FlowWrite) -> object:
    """The flow this write is about: the one sent, a shipped starter, or a project revision."""
    if asked.source == "flow":
        return asked.value
    if asked.source == "starter_id":
        return _contract(lambda name: import_template(load_template(name).as_dict()), asked.value)
    workflow_id, revision = asked.value
    try:
        document = templates.load(workflow_id, revision).as_dict()
    except ContractError:
        raise ApiRefusal.missing_revision(workflow_id, revision) from None
    return _contract(import_template, document)


def _hold_publish_number(templates: Any, workflow_id: str, revision: int | None) -> None:
    """A number that skips ahead of what exists is refused before anything is written."""
    if revision is None:
        return
    revisions = templates.revisions(workflow_id)
    if revision > (1 if not revisions else revisions[-1] + 1):
        raise ApiRefusal.fixed("contract_invalid")


@dataclass(frozen=True)
class _Publication:
    """The revision a write asked for, judged before any byte of the write is stored."""

    revision: int
    #: None when the document repeats `revision` (the latest): there is nothing to write.
    template: GraphTemplate | None


def _judged_publication(templates: Any, workflow_id: str, revision: int | None,
                        document: dict[str, Any], rows: list[dict[str, Any]]):
    """`(plan, refusal)`: what publishing would do, decided before the draft is written.

    Every refusal of a publication is here, so a publication that is refused has saved no
    draft either and the client's expectation of the draft still stands (spec 7.1, step 4).
    A number the store already holds is arbitrated by the store itself: `save` on a claimed
    number reads and compares and writes nothing, so the answer is the one `/revisions` gives.
    """
    if revision is None:
        return None, None
    if _errors(rows):
        return None, refused_with(DraftRefused(tuple(rows)))
    revisions = templates.revisions(workflow_id)
    latest = revisions[-1] if revisions else None
    if _repeats(templates, workflow_id, document, latest):
        return _Publication(latest, None), None
    try:
        template = publish_candidate(document, workflow_id=workflow_id, revision=revision)
    except DraftRefused as refused:
        return None, refused_with(refused)
    if revision in revisions:
        templates.save(template)
    return _Publication(revision, template), None


def _publish(templates: Any, workflow_id: str,
             plan: _Publication | None) -> dict[str, Any] | None:
    """The revision this call wrote or found equal; every refusal came before the draft."""
    if plan is None:
        return None
    draft = templates.load_draft(workflow_id)
    if plan.template is None:
        templates.discard_draft(workflow_id, expecting=draft)
        return {"revision": plan.revision, "created": False}
    if not templates.revision_path(workflow_id, plan.revision).parent.is_dir():
        templates.admit_revision_write(workflow_id, plan.revision)
    saved = templates.save(plan.template)
    if saved.created:
        templates.discard_draft(workflow_id, expecting=draft)
    return {"revision": plan.revision, "created": saved.created}


def _repeats(templates: Any, workflow_id: str, document: dict[str, Any],
             latest: int | None) -> bool:
    """Whether this document says nothing the latest revision does not (spec 7.1, step 4)."""
    standing = _latest_document(templates, workflow_id, latest)
    if standing is None or latest is None:
        return False
    return unchanged_from_published(
        document, standing, workflow_id=workflow_id, revision=latest + 1)


# --- the project's pinned cycle (spec 7.10) ---------------------------------------------------

_PIN_FIELDS = frozenset({"workflow_id", "actor"})


def read_project_cycle(pins: Any, templates: Any) -> Answer:
    """`GET /command/project/cycle`: the workflow the human pinned as the project's, or none."""
    return 200, {"pinned": _pinned(pins.read(), templates)}


def pin_project_cycle(pins: Any, templates: Any, body: object,
                      clock: Callable[[], str]) -> Answer:
    """`POST /command/project/cycle/pin`: pin a published workflow, or unpin with `null`.

    The same pin by the same person again writes nothing, and answers what the read answers. A
    workflow with no published revision cannot be pinned (`contract_invalid`); unpinning what is
    not pinned writes no file. The handler reads no driver and no policy and starts nothing, so
    it answers the same in every mode of the server.
    """
    workflow_id, actor = _pin_body(body)
    if workflow_id is not None and not templates.revisions(workflow_id):
        raise ApiRefusal.fixed("contract_invalid")
    with pins.transaction():
        standing = pins.read()
        if not _repeats_the_pin(standing, workflow_id, actor):
            pins.write(PinRecord(workflow_id, actor, clock()))
            standing = pins.read()
    return 200, {"pinned": _pinned(standing, templates)}


def _pin_body(body: object) -> tuple[str | None, str]:
    """A closed body: the workflow (an id, or null to unpin) and the human who asked."""
    if not isinstance(body, Mapping) or set(body) != _PIN_FIELDS:
        raise ApiRefusal.fixed("contract_invalid")
    workflow_id = body["workflow_id"]
    if workflow_id is not None:
        workflow_id = _contract(_id, "workflow_id", workflow_id)
    return workflow_id, _contract(human_identity, "actor", body["actor"])


def _repeats_the_pin(standing: PinRecord | None, workflow_id: str | None, actor: str) -> bool:
    if workflow_id is None:
        return standing is None or standing.workflow_id is None
    return (standing is not None and standing.workflow_id == workflow_id
            and standing.set_by == actor)


def _pinned(record: PinRecord | None, templates: Any) -> dict[str, Any] | None:
    """The pin as the read shows it; the latest revision is read now, never stored."""
    if record is None or record.workflow_id is None:
        return None
    revisions = templates.revisions(record.workflow_id)
    return {"workflow_id": record.workflow_id,
            "latest_revision": revisions[-1] if revisions else None,
            "set_by": record.set_by, "set_at": record.set_at}
