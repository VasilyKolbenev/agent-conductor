"""Flow schema v1: the editor's model of steps, roads and loops (spec 7.2), closed at every level.

Pure: no store, clock or registry. ``settled_flow`` judges FORM only -- keys, types, vocabularies
and counts -- and returns a new plain document. Whether an id is well formed, a text is one line
or a number is in range is for the rules (``flow_rules``): a rule can only address a step that was
first allowed to exist, so a bad id must settle here and be refused there.
"""
from __future__ import annotations

import copy
import math
from types import MappingProxyType
from typing import Any

from .contract_values import ContractError
from .workflow_draft import MAX_DRAFT_EDGES as MAX_LINKS, MAX_DRAFT_NODES as MAX_STEPS

FLOW_VERSION = 1
MAX_READS = 8
STEP_TYPES = ("agent", "human", "route", "loop")
_COMMON = ("step_id", "type", "title", "purpose", "position", "timeout_seconds")
#: The exact keys of each step type, in the order ``settled_flow`` writes them.
STEP_FIELDS = MappingProxyType({
    "agent": (*_COMMON, "role_id", "capability", "verifier_role_id", "review_profile", "reads",
              "instruction_from", "ext"),
    "human": (*_COMMON, "ext"),
    "route": (*_COMMON, "ext"),
    "loop": (*_COMMON, "back_to", "bound", "ext"),
})
FLOW_FIELDS = ("flow_version", "title", "steps", "links", "ext")
LINK_FIELDS = ("from", "to", "when")
#: A road's word and the edge condition the compiler writes for it; ``always`` writes none.
LINK_WHEN = MappingProxyType({
    "success": "on_succeeded", "failed": "on_failed", "approved": "on_approved",
    "rejected": "on_rejected", "changes_requested": "on_changes_requested",
    "waived": "on_waived", "bound_reached": "on_bound_reached",
    "bound_remaining": "on_bound_remaining", "always": None,
})
#: Held equal to the adapter vocabulary by a test, not imported: that package brings the
#: registry and the store into a module that is meant to be pure.
REVIEW_PROFILES = ("spec", "quality", "security")
#: What a step may override of the compiler's value; a key here REPLACES the computed one whole.
EXT_FIELDS = frozenset({
    "stage", "arguments", "resources", "attempt_bound", "required_evidence", "failure_policy",
    "missing_artifact_policy", "gate_id", "success_requires",
})
FLOW_EXT_FIELDS = frozenset({"execution_contract"})
#: Where each typed step field lands in a template node; ``ext`` lands in ``EXT_FIELDS``.
TEMPLATE_FIELD_OF_STEP_FIELD = MappingProxyType({
    "step_id": "node_id", "type": "kind", "title": "title", "purpose": "purpose",
    "position": "position", "timeout_seconds": "timeout_seconds", "role_id": "role_id",
    "capability": "capability", "verifier_role_id": "verifier_role_id",
    "review_profile": "arguments", "reads": "arguments", "instruction_from": "arguments",
    "back_to": "loop", "bound": "loop",
})


class FlowShapeError(ContractError):
    """A flow the closed shapes refuse; ``path`` addresses the first fault, e.g. flow.steps[2].role_id."""

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(f"{path}: {reason}")
        self.path, self.reason = path, reason


def settled_flow(value: object) -> dict[str, Any]:
    """The flow as a new plain document, or FlowShapeError at the address of the first fault.

    The input is neither mutated nor aliased. Keys come out in the canonical order of each shape.
    """
    body = _object("flow", value, FLOW_FIELDS)
    if type(body["flow_version"]) is not int or body["flow_version"] != FLOW_VERSION:
        raise FlowShapeError("flow.flow_version", f"must be the whole number {FLOW_VERSION}")
    title = _text("flow.title", body["title"])
    steps = _sequence("flow.steps", body["steps"], MAX_STEPS)
    links = _sequence("flow.links", body["links"], MAX_LINKS)
    return {"flow_version": FLOW_VERSION, "title": title,
            "steps": [_step(f"flow.steps[{n}]", row) for n, row in enumerate(steps)],
            "links": [_link(f"flow.links[{n}]", row) for n, row in enumerate(links)],
            "ext": _flow_ext("flow.ext", body["ext"])}


def _step(path: str, value: object) -> dict[str, Any]:
    if type(value) is not dict:
        raise FlowShapeError(path, "must be a JSON object")
    kind = value.get("type")
    if type(kind) is not str or kind not in STEP_FIELDS:
        raise FlowShapeError(f"{path}.type", f"must be one of {', '.join(STEP_TYPES)}")
    body = _object(path, value, STEP_FIELDS[kind])
    step = {"step_id": _text(f"{path}.step_id", body["step_id"]), "type": kind,
            "title": _text(f"{path}.title", body["title"], nullable=True),
            "purpose": _text(f"{path}.purpose", body["purpose"], nullable=True),
            "position": _position(f"{path}.position", body["position"]),
            "timeout_seconds": _whole(f"{path}.timeout_seconds", body["timeout_seconds"], nullable=True)}
    if kind == "agent":
        step.update(_agent(path, body))
    if kind == "loop":
        step.update(back_to=_text(f"{path}.back_to", body["back_to"]),
                    bound=_whole(f"{path}.bound", body["bound"]))
    step["ext"] = _ext(f"{path}.ext", body["ext"])
    return step


def _agent(path: str, body: dict[str, Any]) -> dict[str, Any]:
    profile = body["review_profile"]
    if profile is not None and profile not in REVIEW_PROFILES:
        raise FlowShapeError(f"{path}.review_profile", f"must be null or one of {', '.join(REVIEW_PROFILES)}")
    reads = _sequence(f"{path}.reads", body["reads"], MAX_READS)
    return {"role_id": _text(f"{path}.role_id", body["role_id"]),
            "capability": _text(f"{path}.capability", body["capability"]),
            "verifier_role_id": _text(f"{path}.verifier_role_id", body["verifier_role_id"], nullable=True),
            "review_profile": profile,
            "reads": [_text(f"{path}.reads[{n}]", row) for n, row in enumerate(reads)],
            "instruction_from": _text(f"{path}.instruction_from", body["instruction_from"], nullable=True)}


def _link(path: str, value: object) -> dict[str, str]:
    body = _object(path, value, LINK_FIELDS)
    when = body["when"]
    if type(when) is not str or when not in LINK_WHEN:
        raise FlowShapeError(f"{path}.when", f"must be one of {', '.join(LINK_WHEN)}")
    return {"from": _text(f"{path}.from", body["from"]), "to": _text(f"{path}.to", body["to"]), "when": when}


def _flow_ext(path: str, value: object) -> dict[str, None]:
    body = _object(path, value, FLOW_EXT_FIELDS, required=False)
    if body.get("execution_contract", None) is not None:
        raise FlowShapeError(f"{path}.execution_contract", "may only be null: a null drops the contract")
    return dict(body)


def _ext(path: str, value: object) -> dict[str, Any]:
    body = _object(path, value, EXT_FIELDS, required=False)
    for key, item in body.items():
        _plain(f"{path}.{key}", item)
    return copy.deepcopy(body)


def _object(path: str, value: object, keys, *, required: bool = True) -> dict[str, Any]:
    """A plain dict whose keys are all named in ``keys`` (and, when required, all present)."""
    if type(value) is not dict:
        raise FlowShapeError(path, "must be a JSON object")
    if any(type(key) is not str for key in value):
        raise FlowShapeError(path, "has a key that is not text")
    for key in value:
        if key not in keys:
            raise FlowShapeError(f"{path}.{key}", "is not a key of this shape")
    for key in keys if required else ():
        if key not in value:
            raise FlowShapeError(f"{path}.{key}", "is missing")
    return value


def _sequence(path: str, value: object, limit: int) -> list[Any]:
    if type(value) is not list:
        raise FlowShapeError(path, "must be a JSON array")
    if len(value) > limit:
        raise FlowShapeError(path, f"holds at most {limit} entries, this one {len(value)}")
    return value


def _text(path: str, value: object, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if type(value) is not str:
        raise FlowShapeError(path, "must be text" + (" or null" if nullable else ""))
    return value


def _whole(path: str, value: object, *, nullable: bool = False) -> int | None:
    if value is None and nullable:
        return None
    if type(value) is not int:
        raise FlowShapeError(path, "must be a whole number" + (" or null" if nullable else ""))
    return value


def _position(path: str, value: object) -> dict[str, int] | None:
    if value is None:
        return None
    body = _object(path, value, ("x", "y"))
    return {"x": _whole(f"{path}.x", body["x"]), "y": _whole(f"{path}.y", body["y"])}


def _plain(path: str, value: object) -> None:
    """Refuse anything that is not plain JSON, walking without recursion."""
    pending = [value]
    while pending:
        item = pending.pop()
        kind = type(item)
        if kind is dict and all(type(key) is str for key in item):
            pending.extend(item.values())
        elif kind is list:
            pending.extend(item)
        elif item is None or kind in (str, int, bool) or (kind is float and math.isfinite(item)):
            continue
        else:
            raise FlowShapeError(path, "must hold plain JSON only")
