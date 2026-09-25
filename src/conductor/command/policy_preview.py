"""A finite, read-only candidate and one session-owned preview cache."""
from collections import OrderedDict
from datetime import datetime, timedelta
from threading import RLock

from .authorization_history import (journal_prefix_digest, validate_authorization_history)
from .authorization_inputs import bind_inputs, executable_nodes
from .authorization_terms import closed_fields, positive_integer
from .contract_values import ContractError, _content_digest
from .contracts import _thaw_json
from .run_authorization import RunAuthorization


PREVIEW_FIELDS = frozenset({"node_limits", "max_actions", "max_action_seconds",
                           "max_total_task_seconds", "duration_seconds"})
GENERATED_FIELDS = frozenset({"schema_version", "authorization_id", "authorized_by",
    "authorized_at", "expires_at", "supersedes", "authorization_digest"})
MAX_PREVIEWS = 64


def instant(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def later(value, seconds):
    return (instant(value) + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def authorization_terms(value, duration_seconds):
    return {**{k: v for k, v in value.as_dict().items() if k not in GENERATED_FIELDS},
            "duration_seconds": duration_seconds}


def from_terms(terms, *, authorization_id, authorized_by, authorized_at, supersedes):
    fields = (RunAuthorization._FIELDS - GENERATED_FIELDS) | {"duration_seconds"}
    terms = closed_fields(terms, fields, "authorization preview terms")
    duration = positive_integer("duration_seconds", terms.pop("duration_seconds"))
    return RunAuthorization(**terms, authorization_id=authorization_id,
        authorized_by=authorized_by, authorized_at=authorized_at,
        expires_at=later(authorized_at, duration), supersedes=supersedes)


def build_preview(recovered, body, *, budget, provider_digest, registry, clock, provider_facts=None):
    """No provider call, store write, ownership acquisition or execution."""
    body = closed_fields(body, PREVIEW_FIELDS, "automation preview")
    for key in PREVIEW_FIELDS - {"node_limits"}:
        positive_integer(key, body[key])
    if (body["max_actions"] > budget.max_actions
            or body["max_action_seconds"] > budget.max_action_seconds
            or body["max_total_task_seconds"] > budget.max_actions * budget.max_action_seconds):
        raise ContractError("authorization exceeds deployment budgets")
    values = tuple(row.value for row in recovered.records)
    definitions = [row.value for row in recovered.records if row.kind == "graph_definition"]
    if len(definitions) != 1:
        raise ContractError("authorization requires one frozen graph")
    definition, = definitions
    _hold_capabilities(recovered, definition, registry)
    instructions, inputs = bind_inputs(definition, values)
    previous = next((row for row in reversed(values) if type(row) is RunAuthorization), None)
    now = clock()
    candidate = RunAuthorization(authorization_id="preview", run_id=recovered.envelope.run_id,
        config_digest=recovered.envelope.config_digest, graph_digest=definition.digest(),
        provider_config_digest=provider_digest(recovered.config),
        source_prefix_digest=journal_prefix_digest(recovered.records), authorized_by="preview",
        authorized_at=now, expires_at=later(now, body["duration_seconds"]),
        supersedes=previous.authorization_id if previous else None,
        node_limits=body["node_limits"], instruction_bindings=instructions,
        initial_input_bindings=inputs, max_actions=body["max_actions"],
        max_action_seconds=body["max_action_seconds"],
        max_total_task_seconds=body["max_total_task_seconds"])
    validate_authorization_history(recovered, candidate)
    terms = authorization_terms(candidate, body["duration_seconds"])
    facts = provider_facts(recovered.config) if provider_facts is not None else None
    if facts is not None and _content_digest(facts) != candidate.provider_config_digest:
        raise ContractError("provider facts changed while building preview")
    return {"terms": terms, "preview_digest": _content_digest(terms), "previewed_at": now,
            "provider_facts": facts,
            "valid_until": later(now, min(300, budget.max_confirmation_age_seconds))}


def _hold_capabilities(recovered, definition, registry):
    from .contracts import frozen_config_bindings
    from .containment import unprovidable_sandboxes
    bindings = frozen_config_bindings(recovered.config)
    for node in executable_nodes(definition):
        adapter = bindings.get(node.instance_id)
        if registry.argument_schema(adapter, node.capability) != "deep-arguments-v1":
            raise ContractError("automation requires the registered deep argument schema")
        registry.validate_arguments(adapter, node.capability, _thaw_json(node.arguments))
        if unprovidable_sandboxes(node.resources):
            raise ContractError("automation cannot provide a required sandbox")
        if node.verifier_instance_id is not None:
            checker = bindings.get(node.verifier_instance_id)
            if not registry.verifies_independently(checker, node.capability):
                raise ContractError("automation requires the declared independent checker")


class PreviewCache:
    """One candidate per session/run; cache loss never becomes permission."""

    def __init__(self):
        self._entries = OrderedDict()
        self._lock = RLock()

    def put(self, session, run_id, preview):
        with self._lock:
            key = (session, run_id)
            self._entries.pop(key, None)
            self._entries[key] = _thaw_json(preview)
            while len(self._entries) > MAX_PREVIEWS:
                self._entries.popitem(last=False)

    def require(self, session, run_id, digest, terms, now):
        with self._lock:
            preview = self._entries.get((session, run_id))
            if preview is None or preview["preview_digest"] != digest or preview["terms"] != terms:
                raise ContractError("preview is absent, evicted or differs from the reviewed terms")
            if not instant(preview["previewed_at"]) <= instant(now) < instant(preview["valid_until"]):
                raise ContractError("preview has expired")
            return _thaw_json(preview)

    def discard(self, session, run_id):
        with self._lock:
            self._entries.pop((session, run_id), None)
