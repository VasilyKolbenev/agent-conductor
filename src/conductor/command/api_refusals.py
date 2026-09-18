"""The closed refusal vocabulary, and the one shape allowed to carry it.

Split out of ``api_contracts`` when that module reached the project's line cap,
along the seam its own first line already draws: it is "closed browser inputs
and typed sanitized refusals", and those are two circuits. The INPUT half --
every ``parse_*`` for every route, and the closed field sets they are held to --
stayed there. This is the OUTPUT half: which codes exist, what each says when it
carries no detail, which details are reviewed enough to render into a browser,
and the frozen exception that refuses to be built any other way.

An earlier attempt at this split moved the shape and left three of its
dependencies behind -- ``_PHASE_MESSAGES``, ``HttpRefusal`` and
``_EXCEPTION_SLOTS`` -- so ``ApiRefusal`` raised at construction, an
untranslatable exception reached the boundary, and a hundred and eighty-four
tests failed. All three are here now, beside the code that needs them, and
``_ID_RE`` came with ``_safe_id`` for the same reason.

The two halves meet in exactly one place: ``refusal_from_exception``, which
stayed next door because it is a translation OF the input road's failures rather
than part of this vocabulary.

``api_contracts`` imports every name here back under its old spelling, so no
caller anywhere learns that the split happened -- and the freeze tests, which
import from that surface rather than reading this file, go on asking the
question they always asked.

Like the module it came from, this constructs no durable response and calls no
service, store, runtime, adapter, filesystem, process, or server seam.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import FrozenInstanceError, dataclass
from types import MappingProxyType

from .http_transport import HttpRefusal

ERROR_STATUS = MappingProxyType({
    "same_origin_denied": 403,
    "csrf_denied": 403,
    "method_not_allowed": 405,
    "route_not_found": 404,
    "malformed_request": 400,
    "contract_invalid": 422,
    "run_corrupt": 409,
    "store_error": 500,
    "route_unsafe": 409,
    "service_refused": 409,
    "capability_unsupported": 409,
    "authorization_refused": 409,
    "proposal_rebind_required": 409,
    "record_conflict": 409,
    "draft_changed": 409,
    "draft_conflict": 409,
    "run_terminal": 409,
    "gate_unreached": 409,
})

_FIXED_MESSAGES = MappingProxyType({
    "same_origin_denied": "request origin is not allowed",
    "csrf_denied": "request CSRF token is not current",
    "method_not_allowed": "request method is not allowed for this route",
    "route_not_found": "command route does not exist",
    "malformed_request": "request transport or JSON shape is malformed",
    "contract_invalid": "request values do not satisfy the contract",
    "run_corrupt": "stored run is corrupt",
    "store_error": "run store could not complete the request",
    "route_unsafe": "run route is not structurally contained",
    "service_refused": "command service refused the request",
    "capability_unsupported": "adapter does not support this capability",
    "authorization_refused": "confirmation did not authorize the request",
    "proposal_rebind_required": "this proposal predates material binding; "
                                "create a new proposal and review it before confirming",
    "record_conflict": "durable record identity conflicts",
    #: Its own code rather than one more `contract_invalid`, because the caller
    #: did nothing wrong and there is something specific to DO about it: the
    #: draft moved under an open review, and the window must fetch the new one
    #: and ask the person to look again. A client cannot tell that from "the
    #: request shape is invalid", so it could only offer to try again -- which
    #: would publish the same stale review a second time.
    "draft_changed": "the draft changed since it was reviewed; read it again",
    #: One class, two roads. A client writes against the draft it last READ --
    #: a save names the one it means to replace, a publish names the one it
    #: reviewed -- and this is the answer when the store no longer holds that
    #: draft. `draft_changed` stays a separate word because it is a separate,
    #: already-reviewed fact: the reviewed draft is still there and its CONTENT
    #: moved. This one covers the draft that was replaced under a save and the
    #: draft that is gone under a confirm, and neither is `contract_invalid`:
    #: the body is well formed, the caller is not at fault, and a client told
    #: its request shape was wrong can only send that shape again.
    #:
    #: The two roads carry different detail -- see `_REVIEWED_FACTS` -- so this
    #: fixed sentence is the vocabulary-completeness one, never the answer a
    #: real refusal on either road gives.
    "draft_conflict": "the stored draft is not the one this request was "
                      "working from",
    #: Its own code rather than `record_conflict` or `service_refused`, because
    #: it is neither a clash of identities nor a service declining: the run
    #: recorded that its plan ended, and NOTHING will be accepted on it again.
    #: A client told `service_refused` could reasonably retry; there is nothing
    #: here to retry. It carries no detail, so it is judged by the fixed-message
    #: branch and needs no `_REVIEWED_FACTS` row.
    "run_terminal": "run has recorded its terminal and accepts no further "
                    "records",
    #: Its own code rather than `service_refused`, and for `run_terminal`'s
    #: reason: the source is the PLAN. The body is well formed, the caller is
    #: not at fault, and what refuses them is that this run has not arrived at
    #: the gate they are answering -- which is a fact that CHANGES as the plan
    #: goes on, so a client is being told to wait rather than to correct
    #: anything. It carries no detail: what is still owed is the schedule's
    #: answer, and the screen already reads it from `graph.schedule` rather
    #: than from a refusal envelope.
    "gate_unreached": "a decision may stand only on a gate this run's plan "
                      "has reached",
})


_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_REFUSAL_BUILD = object()
#: The attributes the interpreter and its plumbing assign to an exception in
#: flight. A frozen dataclass refuses every assignment, these included, which
#: left a refusal unable to travel the one road Python carries it on.
_EXCEPTION_SLOTS = frozenset({
    "__traceback__", "__cause__", "__context__", "__suppress_context__",
    "__notes__",
})
#: What an operator must do when this build resolved no provider at all. It is
#: a DIFFERENT situation from naming a provider that is not available, and the
#: two must never share a sentence: one person has written no configuration yet
#: and the other has written one that does not carry the id they asked for. This
#: one is actionable and says exactly what to DO. It used to say where to act
#: -- the file and its five keys -- which was the only actionable thing there
#: was to say while hand-writing that file was the only road. Now there is a
#: command, so the sentence names the command; the file is still named, because
#: an operator who prefers to write it is not being told they may not.
NO_PROVIDERS_MESSAGE = (
    "this build resolved no available provider; run `conduct providers` to "
    "configure one — it asks for the paths and the environment variable names, "
    "and writes conductor/providers.json for you")
_PHASE_MESSAGES = MappingProxyType({
    "same_origin_denied": frozenset({
        "request Host is not allowed", "request origin is not allowed"}),
    "malformed_request": frozenset({
        "request transport or JSON shape is malformed",
        "request Content-Type is not supported",
        "request body is not one JSON object",
    }),
    "service_refused": frozenset({NO_PROVIDERS_MESSAGE}),
})


def _safe_id(value: object) -> bool:
    return isinstance(value, str) and _ID_RE.fullmatch(value) is not None


def _safe_detail(value: object) -> bool:
    """One detail value: a safe id, or a counting number spelled as itself."""
    if type(value) is int and not isinstance(value, bool):
        return value >= 1
    return _safe_id(value)


#: Every refusal that may carry a detail, as `(code, fields, sentence)`. A
#: closed table rather than a condition, because the closure is the point: a
#: detail is rendered into a browser, so what may appear there is reviewed one
#: fact at a time. The sentence is built from the SAME fields the detail
#: carries, so a message and its structured half cannot drift apart -- and a
#: refusal assembled anywhere else, with any other wording, is refused at
#: construction rather than shipped.
_REVIEWED_FACTS = (
    ("service_refused", ("run_id", "instance_id"),
     lambda facts: f"frozen config declares no instance '{facts['instance_id']}'"),
    ("service_refused", ("run_id", "instance_id"),
     lambda facts: (f"instance '{facts['instance_id']}' is bound to a provider "
                    "this build cannot reach")),
    ("service_refused", ("run_id", "template_id", "revision"),
     lambda facts: (f"no stored template '{facts['template_id']}' at revision "
                    f"{facts['revision']}")),
    # The same fact asked WITHOUT a run: the workflow read routes belong to no
    # run, so a run id in their refusal would be a fact they do not have. The
    # field sets differ, which is what keeps the two reviewed rows apart.
    ("service_refused", ("template_id", "revision"),
     lambda facts: (f"no stored template '{facts['template_id']}' at revision "
                    f"{facts['revision']}")),
    # A task this build does not hold, named by the id the caller sent and by
    # nothing else: no run, because the task routes belong to no run, and no
    # path. The one-field set is what keeps it apart from every row above.
    ("service_refused", ("task_id",),
     lambda facts: f"no stored task '{facts['task_id']}'"),
    ("service_refused", ("provider_id",),
     lambda facts: (f"provider '{facts['provider_id']}' is not one this build "
                    "resolved as available")),
    # The two roads a client writes against a draft it has read, kept apart by
    # their field sets exactly as the two template rows above are: a SAVE names
    # the workflow whose stored draft is not the one it meant to replace, and a
    # PUBLISH names the revision it can no longer construct. Neither names the
    # standing digest: which document is there is not something a refused
    # caller should infer, and the read that follows answers it properly.
    ("draft_conflict", ("workflow_id",),
     lambda facts: (f"the stored draft of '{facts['workflow_id']}' is not the "
                    "one this request expected to replace")),
    ("draft_conflict", ("workflow_id", "revision"),
     lambda facts: (f"no draft of '{facts['workflow_id']}' stands to publish "
                    f"as revision {facts['revision']}")),
    # ONE route, never a list: by the rule above a detail is a safe id or a
    # counting number, reviewed one fact at a time because it is rendered.
    # A gate that may not be set aside, named by the GATE id the caller
    # themself sent -- not by the node, because a person answering a gate knows
    # it by the id on the decision they are making.
    ("service_refused", ("run_id", "gate_id"),
     lambda facts: (f"gate '{facts['gate_id']}' requires explicit human "
                    "approval and cannot be waived")),
    ("service_refused", ("run_id", "node_id", "sandbox"),
     lambda facts: (f"step '{facts['node_id']}' demands sandbox route "
                    f"'{facts['sandbox']}' that this build does not provide")),
)


def _reviewed_fact(code: str, message: str, detail: dict) -> bool:
    """Whether this refusal is one of the reviewed facts, whole."""
    for reviewed, fields, sentence in _REVIEWED_FACTS:
        if code != reviewed or set(detail) != set(fields):
            continue
        if all(_safe_detail(detail[key]) for key in fields) \
                and message == sentence(detail):
            return True
    return False


@dataclass(frozen=True, init=False)
class ApiRefusal(Exception):
    """One closed browser-safe refusal; no exception prose is carried through."""

    code: str
    message: str
    detail: Mapping[str, str]

    def __init__(
            self, build: object, code: str, message: str,
            detail: Mapping[str, str]) -> None:
        if build is not _REFUSAL_BUILD:
            raise ValueError("API refusals require a reviewed factory")
        if code not in ERROR_STATUS:
            raise ValueError("unknown API refusal code")
        copied = dict(detail)
        if copied:
            if not _reviewed_fact(code, message, copied):
                raise ValueError("API refusal detail must match a reviewed fact")
        else:
            messages = _PHASE_MESSAGES.get(code, frozenset()) | {
                _FIXED_MESSAGES[code]}
            if message not in messages:
                raise ValueError("API refusal message must match a reviewed template")
        object.__setattr__(self, "code", code)
        object.__setattr__(self, "message", message)
        object.__setattr__(self, "detail", MappingProxyType(copied))
        Exception.__init__(self, message)

    @property
    def status(self) -> int:
        return ERROR_STATUS[self.code]

    def as_dict(self) -> dict[str, object]:
        """Return exactly the frozen refusal envelope."""
        return {"error": {
            "code": self.code, "message": self.message, "detail": dict(self.detail)}}

    @classmethod
    def fixed(cls, code: str) -> "ApiRefusal":
        """Build one vocabulary-complete refusal with no submitted detail."""
        if code not in _FIXED_MESSAGES:
            raise ValueError("unknown API refusal code") from None
        return cls(_REFUSAL_BUILD, code, _FIXED_MESSAGES[code], {})

    @classmethod
    def from_http(cls, refusal: HttpRefusal) -> "ApiRefusal":
        """Preserve the transport's reviewed phase-specific safe message."""
        if not isinstance(refusal, HttpRefusal):
            raise ValueError("HTTP refusal must be typed")
        return cls(_REFUSAL_BUILD, refusal.code, refusal.message, {})

    @classmethod
    def service_missing_instance(
            cls, run_id: str, instance_id: str) -> "ApiRefusal":
        """Name one validated frozen-config relation without exception prose."""
        if not _safe_id(run_id) or not _safe_id(instance_id):
            raise ValueError("service refusal identifiers must be safe IDs") from None
        detail = {"run_id": run_id, "instance_id": instance_id}
        message = f"frozen config declares no instance '{instance_id}'"
        return cls(_REFUSAL_BUILD, "service_refused", message, detail)

    @classmethod
    def service_missing_revision(
            cls, run_id: str, template_id: str, revision: int) -> "ApiRefusal":
        """Name a revision this build does not hold, and no path to look at."""
        detail = {"run_id": run_id, "template_id": template_id,
                  "revision": revision}
        message = f"no stored template '{template_id}' at revision {revision}"
        return cls(_REFUSAL_BUILD, "service_refused", message, detail)

    @classmethod
    def missing_revision(cls, template_id: str, revision: int) -> "ApiRefusal":
        """Name a revision this build does not hold, with no run and no path."""
        detail = {"template_id": template_id, "revision": revision}
        message = f"no stored template '{template_id}' at revision {revision}"
        return cls(_REFUSAL_BUILD, "service_refused", message, detail)

    @classmethod
    def missing_task(cls, task_id: str) -> "ApiRefusal":
        """Name a task this build does not hold, with no run and no path."""
        detail = {"task_id": task_id}
        message = f"no stored task '{task_id}'"
        return cls(_REFUSAL_BUILD, "service_refused", message, detail)

    @classmethod
    def conflicting_draft(cls, workflow_id: str) -> "ApiRefusal":
        """Say the stored draft is not the one this save meant to replace.

        The save road's half of `draft_conflict`. It names the workflow and
        nothing about the document that is standing: the refused caller's road
        forward is a READ, which answers that properly and in full.
        """
        if not _safe_id(workflow_id):
            raise ValueError("draft refusal identifiers must be safe IDs") from None
        detail = {"workflow_id": workflow_id}
        message = (f"the stored draft of '{workflow_id}' is not the one this "
                   "request expected to replace")
        return cls(_REFUSAL_BUILD, "draft_conflict", message, detail)

    @classmethod
    def unpublishable_draft(cls, workflow_id: str, revision: int) -> "ApiRefusal":
        """Say no draft stands to publish as the revision the caller named.

        The publish road's half of the same class. A publish-from-draft always
        names WHICH draft it reviewed, so this is only reached by a caller
        naming one the store does not hold -- consumed by another client's
        publish, or never stored at all, which is one fact from here.
        """
        if not _safe_id(workflow_id):
            raise ValueError("draft refusal identifiers must be safe IDs") from None
        detail = {"workflow_id": workflow_id, "revision": revision}
        message = (f"no draft of '{workflow_id}' stands to publish as revision "
                   f"{revision}")
        return cls(_REFUSAL_BUILD, "draft_conflict", message, detail)

    @classmethod
    def service_no_providers(cls) -> "ApiRefusal":
        """Say that nothing is configured, and exactly where to configure it.

        An empty roster is a first-class state of a fresh project, not a fault:
        nobody has written `conductor/providers.json` yet. So the refusal is a
        instruction rather than a diagnosis, and it carries no detail at all --
        there is no id to name, which is precisely what distinguishes it from a
        request that named a provider this build does not have.
        """
        return cls(_REFUSAL_BUILD, "service_refused", NO_PROVIDERS_MESSAGE, {})

    @classmethod
    def service_unknown_provider(cls, provider_id: str) -> "ApiRefusal":
        """Name the PROVIDER a caller chose that this build cannot reach.

        The id is the caller's own word, echoed back, so nothing about this
        build's roster leaks: a provider that is configured and unavailable and
        a provider nobody configured are refused in the same sentence, exactly
        as `service_unreachable_adapter` refuses the two by one rule.
        """
        if not _safe_id(provider_id):
            raise ValueError("service refusal identifiers must be safe IDs") from None
        detail = {"provider_id": provider_id}
        message = (f"provider '{provider_id}' is not one this build resolved as "
                   "available")
        return cls(_REFUSAL_BUILD, "service_refused", message, detail)

    @classmethod
    def service_unreachable_adapter(
            cls, run_id: str, instance_id: str) -> "ApiRefusal":
        """Name the INSTANCE, because the product behind it is not the fact.

        Whether a provider can be reached is a state this build resolved, and
        the refusal says only that the instance a role was bound to is not
        reachable. Naming the adapter would put a vendor in a message the
        Cockpit renders, and a caller who supplied the binding already knows
        which instance they chose.
        """
        detail = {"run_id": run_id, "instance_id": instance_id}
        message = (f"instance '{instance_id}' is bound to a provider this build "
                   "cannot reach")
        return cls(_REFUSAL_BUILD, "service_refused", message, detail)


    @classmethod
    def gate_refuses_waiver(cls, run_id: str, gate_id: str) -> "ApiRefusal":
        """The gate's own id back, because that is what the caller named.

        A waiver is refused BEFORE anything is appended, so this sentence is
        the whole of what the run records about the attempt: nothing else
        happened. The gate id came out of the caller's own decision body.
        """
        detail = {"run_id": run_id, "gate_id": gate_id}
        message = (f"gate '{gate_id}' requires explicit human approval and "
                   "cannot be waived")
        return cls(_REFUSAL_BUILD, "service_refused", message, detail)

    @classmethod
    def plan_sandbox_unprovidable(
            cls, run_id: str, node_id: str, route: str) -> "ApiRefusal":
        """The STEP and ONE route, both the caller's own words: no vendor is
        near this fact, so echoing the route says which row to change.
        """
        detail = {"run_id": run_id, "node_id": node_id, "sandbox": route}
        message = (f"step '{node_id}' demands sandbox route "
                   f"'{route}' that this build does not provide")
        return cls(_REFUSAL_BUILD, "service_refused", message, detail)


def _refusal_setattr(self: ApiRefusal, name: str, value: object) -> None:
    """Stay frozen as a value, and travel as an exception.

    Every mutating route re-checks its containment INSIDE the store
    transaction, because a route can be made unsafe between the first check and
    the lock. That second refusal never arrived: `contextlib` assigns
    `__traceback__` to an exception on its way out of a context manager, a
    frozen dataclass refuses the assignment, and what reached the boundary was
    an untranslatable `TypeError` instead of one closed `409 route_unsafe`.

    Only the attributes the interpreter and its plumbing own are let through.
    The three reviewed fields stay exactly as read-only as before, and say so
    with the dataclass's own error.
    """
    if name in _EXCEPTION_SLOTS:
        object.__setattr__(self, name, value)
        return
    raise FrozenInstanceError(f"cannot assign to field {name!r}")


# `dataclass(frozen=True)` refuses to install its guard over a `__setattr__`
# written in the class body, so the widened guard is installed right after the
# decorator has run rather than instead of it.
ApiRefusal.__setattr__ = _refusal_setattr
