"""Flow schema v1: the editor's model of steps, roads and loops (spec 7.2), closed at every level.

Pure: no store, clock or registry. ``settled_flow`` judges FORM only -- keys, types, vocabularies
and counts -- and returns a new plain document. Whether an id is well formed, a text is one line
or a number is in range is for the rules (``flow_rules``): a rule can only address a step that was
first allowed to exist, so a bad id must settle here and be refused there.
"""
from __future__ import annotations

import copy
import math
import re
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from .authorization_terms import AUTOMATION_CONTRACT
from .contract_values import ContractError
from .graph_template_document import SCHEMA_VERSION
from .workflow_draft import MAX_DRAFT_EDGES as MAX_LINKS, MAX_DRAFT_NODES as MAX_STEPS
from .workflow_draft import NOT_YET_FIELDS, parse_document

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
#: The role keys of a template node that a flow types only on an agent step. The core accepts a
#: gate or a loop that binds a role, so an import must hold one; a flow has no typed place for it
#: on such a step, and it lives in that step's `ext` (spec 7.3, rules 2 and 3), where the compiler
#: lays it over the node like any other key. `EXT_FIELDS` stays the nine keys of spec 7.2.
BOUND_EXT_FIELDS = frozenset({"role_id", "capability", "verifier_role_id"})
#: The keys the `ext` of each step type may carry: an agent already types its role, and a route
#: is a task with none.
STEP_EXT_FIELDS = MappingProxyType({
    "agent": EXT_FIELDS, "route": EXT_FIELDS,
    "human": EXT_FIELDS | BOUND_EXT_FIELDS, "loop": EXT_FIELDS | BOUND_EXT_FIELDS,
})
#: Where each typed step field lands in a template node; ``ext`` lands in ``EXT_FIELDS``.
TEMPLATE_FIELD_OF_STEP_FIELD = MappingProxyType({
    "step_id": "node_id", "type": "kind", "title": "title", "purpose": "purpose",
    "position": "position", "timeout_seconds": "timeout_seconds", "role_id": "role_id",
    "capability": "capability", "verifier_role_id": "verifier_role_id",
    "review_profile": "arguments", "reads": "arguments", "instruction_from": "arguments",
    "back_to": "loop", "bound": "loop",
})


class FlowShapeError(ContractError):
    """A flow the closed shapes refuse.

    ``path`` addresses the first fault, for example ``flow.steps[2].role_id``.
    """

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
            "timeout_seconds": _whole(f"{path}.timeout_seconds", body["timeout_seconds"],
                                      nullable=True)}
    if kind == "agent":
        step.update(_agent(path, body))
    if kind == "loop":
        step.update(back_to=_text(f"{path}.back_to", body["back_to"]),
                    bound=_whole(f"{path}.bound", body["bound"]))
    step["ext"] = _ext(f"{path}.ext", body["ext"], STEP_EXT_FIELDS[kind])
    return step


def _agent(path: str, body: dict[str, Any]) -> dict[str, Any]:
    profile = body["review_profile"]
    if profile is not None and profile not in REVIEW_PROFILES:
        raise FlowShapeError(f"{path}.review_profile",
                             f"must be null or one of {', '.join(REVIEW_PROFILES)}")
    reads = _sequence(f"{path}.reads", body["reads"], MAX_READS)
    return {"role_id": _text(f"{path}.role_id", body["role_id"]),
            "capability": _text(f"{path}.capability", body["capability"]),
            "verifier_role_id": _text(f"{path}.verifier_role_id", body["verifier_role_id"],
                                      nullable=True),
            "review_profile": profile,
            "reads": [_text(f"{path}.reads[{n}]", row) for n, row in enumerate(reads)],
            "instruction_from": _text(f"{path}.instruction_from", body["instruction_from"],
                                      nullable=True)}


def _link(path: str, value: object) -> dict[str, str]:
    body = _object(path, value, LINK_FIELDS)
    when = body["when"]
    if type(when) is not str or when not in LINK_WHEN:
        raise FlowShapeError(f"{path}.when", f"must be one of {', '.join(LINK_WHEN)}")
    return {"from": _text(f"{path}.from", body["from"]),
            "to": _text(f"{path}.to", body["to"]), "when": when}


def _flow_ext(path: str, value: object) -> dict[str, None]:
    body = _object(path, value, FLOW_EXT_FIELDS, required=False)
    if body.get("execution_contract", None) is not None:
        raise FlowShapeError(f"{path}.execution_contract",
                             "may only be null: a null drops the contract")
    return dict(body)


def _ext(path: str, value: object, allowed=EXT_FIELDS) -> dict[str, Any]:
    body = _object(path, value, allowed, required=False)
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


# --- compile: a flow becomes a workflow document (spec 7.3) ------------------------------------

#: The English name of a role kind, shown when a step's author left the title empty. The kind is
#: read from the role's name: `role-<kind>` or `role-<kind>-<n>` (spec 7.2.2).
KIND_TITLES = MappingProxyType({
    "analyst": "Analyst", "designer": "Designer", "diagnostician": "Diagnostician",
    "reviewer": "Reviewer", "doer": "Doer", "tester": "Tester",
})
_STEP_TITLES = MappingProxyType({"human": "Decision", "loop": "Loop", "route": "Route"})
_KIND_OF_ROLE = re.compile(r"role-([a-z]+)(?:-[0-9]+)?\Z")
_NODE_KIND = MappingProxyType({"agent": "task", "route": "task", "human": "gate", "loop": "loop"})
#: What the entry steps read: the two documents every run is opened with (spec 6.2.3, 7.3).
ENTRY_INPUTS = ("artifact-brief", "artifact-materials")
#: Every step of a compiled cycle works in this one folder, so a later step sees an earlier one's
#: changes and "accept" moves one folder (spec 7.3, 9.1.1).
WORK_ITEM_ID = "work-001"


def compile_flow(flow: object) -> dict[str, Any]:
    """The workflow document of a flow, without `template_id` and `revision` (spec 7.3).

    The order of steps and of links is the order of nodes and of edges: the driver takes the first
    ready node of the plan, and the schedule breaks a tie between loops by it. An `ext` key is
    written over the computed value whole.

    Raises:
        FlowShapeError: The flow is not in the closed shape of `settled_flow`.
    """
    settled = settled_flow(flow)
    steps, links = settled["steps"], settled["links"]
    inputs = _step_inputs(steps, links)
    document: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION, "title": settled["title"],
        "nodes": [_node(row, inputs.get(row["step_id"], [])) for row in steps],
        "edges": [_edge(link) for link in links]}
    if "execution_contract" not in settled["ext"]:
        document["execution_contract"] = AUTOMATION_CONTRACT
    return document


def kind_title(step: dict[str, Any]) -> str:
    """The name a step shows when its own title is empty."""
    if step["type"] != "agent":
        return _STEP_TITLES[step["type"]]
    role = step["role_id"]
    named = _KIND_OF_ROLE.fullmatch(role)
    if named is not None and named.group(1) in KIND_TITLES:
        return KIND_TITLES[named.group(1)]
    return role[len("role-"):] if role.startswith("role-") else role


def _node(step: dict[str, Any], inputs: list[str]) -> dict[str, Any]:
    node: dict[str, Any] = {"node_id": step["step_id"], "kind": _NODE_KIND[step["type"]],
                            "title": step["title"] or kind_title(step)}
    for key in ("purpose", "position", "timeout_seconds"):
        if step[key] is not None:
            node[key] = copy.deepcopy(step[key])
    node.update(_typed_part(step, inputs))
    for key, value in step["ext"].items():
        if key == "success_requires" and value is None:
            node.pop(key, None)
        else:
            node[key] = copy.deepcopy(value)
    return node


def _typed_part(step: dict[str, Any], inputs: list[str]) -> dict[str, Any]:
    """What a step's type writes into its node, before its `ext` is laid over it."""
    kind = step["type"]
    if kind == "human":
        return {"gate_id": f"gate-{step['step_id']}", "success_requires": "human_approval",
                "resources": []}
    if kind == "loop":
        return {"loop": {"bound": step["bound"], "back_to": step["back_to"]}, "resources": []}
    if kind == "route":
        return {"resources": []}
    return _agent_part(step, inputs)


def _agent_part(step: dict[str, Any], inputs: list[str]) -> dict[str, Any]:
    part: dict[str, Any] = {"role_id": step["role_id"], "capability": step["capability"]}
    if step["verifier_role_id"] is not None:
        part["verifier_role_id"] = step["verifier_role_id"]
    if step["capability"] == "review":
        arguments = {"work_item_id": WORK_ITEM_ID, "target_artifact_refs": list(inputs),
                     "result_artifact_ref": f"artifact-{step['step_id']}"}
        if step["review_profile"] is not None:
            arguments["review_profile"] = step["review_profile"]
        return {**part, "arguments": arguments, "resources": []}
    if step["capability"] == "dispatch":
        source = step["instruction_from"] or step["step_id"]
        arguments = {"work_item_id": WORK_ITEM_ID, "instruction_ref": f"instruction-{source}",
                     "profile": "implement", "artifact_refs": list(inputs),
                     "output_limit_profile": "normal"}
        return {**part, "arguments": arguments,
                "resources": [{"kind": "sandbox", "name": "project-root"}]}
    return {**part, "arguments": {}, "resources": []}


def _edge(link: dict[str, str]) -> dict[str, str]:
    edge = {"from_node": link["from"], "to_node": link["to"]}
    condition = LINK_WHEN[link["when"]]
    if condition is not None:
        edge["condition"] = condition
    return edge


def _step_inputs(steps: list[dict[str, Any]], links: list[dict[str, str]]) -> dict[str, list[str]]:
    """The documents each agent step reads (spec 7.3, L23), by the step's id.

    An entry step, with no review anywhere above it along the roads, reads the brief and the
    materials. Any other step reads the result of the nearest reviews above it, and of the steps
    it names in `reads`, in the order of `steps`.
    """
    order, reviews, parents = _roads(steps, links)
    found: dict[str, list[str]] = {}
    for row in steps:
        if row["type"] != "agent":
            continue
        nearest = _nearest_reviews(row["step_id"], parents, reviews)
        chosen = sorted(nearest | {name for name in row["reads"] if name in order},
                        key=order.__getitem__)
        refs = [f"artifact-{name}" for name in chosen]
        found[row["step_id"]] = refs if nearest else [*ENTRY_INPUTS, *refs]
    return found


def _roads(steps: list[dict[str, Any]], links: list[dict[str, str]]):
    """The order of steps, the review steps, and the steps above each step along the roads."""
    order = {row["step_id"]: n for n, row in enumerate(steps)}
    reviews = {row["step_id"] for row in steps
               if row["type"] == "agent" and row["capability"] == "review"}
    parents: dict[str, list[str]] = {}
    for link in links:
        parents.setdefault(link["to"], []).append(link["from"])
    return order, reviews, parents


def _nearest_reviews(step_id: str, parents: dict[str, list[str]], reviews: set[str]) -> set[str]:
    """The review steps first met walking up the roads from `step_id` (a review stops the walk)."""
    found: set[str] = set()
    seen = {step_id}
    pending = list(parents.get(step_id, ()))
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        if name in reviews:
            found.add(name)
        else:
            pending.extend(parents.get(name, ()))
    return found


# --- import: a workflow document becomes a flow (spec 7.3) --------------------------------------

_WHEN_OF_CONDITION = MappingProxyType({
    condition: when for when, condition in LINK_WHEN.items() if condition is not None})
#: The keys of a template node that only `ext` can carry, in the order `import_template` tests them.
_EXT_ORDER = ("stage", "arguments", "resources", "attempt_bound", "required_evidence",
              "failure_policy", "missing_artifact_policy", "gate_id", "success_requires")
#: What a gate or a loop adds to that list when it binds a role, tested first.
_BOUND_ORDER = ("role_id", "capability", "verifier_role_id")


def import_template(document: object) -> dict[str, Any]:
    """The flow of a workflow document: a template as shipped or stored, or a draft (spec 7.3).

    `compile_flow(import_template(doc))` is `doc` for every document a template accepts, and
    `import_template(compile_flow(f)) == f` for a flow in canonical form. The typed fields are
    read from the document; what the compiler would write anyway is left out of `ext`, and every
    other value the document carries is kept there, so nothing is lost and nothing is read-only.
    A gate or a loop that binds a role keeps the binding in its `ext` (`BOUND_EXT_FIELDS`).
    `template_id` and `revision` name the workflow, not the drawing, and are not read.

    Raises:
        ContractError: The document is not one a template could carry (a key it does not name,
            a node or edge the core refuses, a size bound).
    """
    if not isinstance(document, Mapping):
        raise FlowShapeError("document", "must be a JSON object")
    body = parse_document({key: value for key, value in document.items()
                           if key not in NOT_YET_FIELDS})
    nodes = body["nodes"]
    links = [_link_of(row) for row in body["edges"]]
    steps = [_bare_step(node) for node in nodes]
    flow = {"flow_version": FLOW_VERSION, "title": body["title"], "steps": steps, "links": links,
            "ext": {} if body.get("execution_contract") == AUTOMATION_CONTRACT
            else {"execution_contract": None}}
    _read_typed_arguments(steps, links, nodes)
    for step, node, made in zip(steps, nodes, compile_flow(flow)["nodes"]):
        step["ext"] = _extension(node, made, step["type"])
    return settled_flow(flow)


def _link_of(edge: dict[str, str]) -> dict[str, str]:
    when = "always" if "condition" not in edge else _WHEN_OF_CONDITION[edge["condition"]]
    return {"from": edge["from_node"], "to": edge["to_node"], "when": when}


def _bare_step(node: dict[str, Any]) -> dict[str, Any]:
    """The typed fields of one node's step, before its arguments and `ext` are read."""
    kind = {"gate": "human", "loop": "loop"}.get(node["kind"]) or (
        "agent" if "capability" in node else "route")
    step: dict[str, Any] = {
        "step_id": node["node_id"], "type": kind, "title": None,
        "purpose": node.get("purpose"), "position": copy.deepcopy(node.get("position")),
        "timeout_seconds": node.get("timeout_seconds")}
    if kind == "agent":
        step.update(role_id=node["role_id"], capability=node["capability"],
                    verifier_role_id=node.get("verifier_role_id"), review_profile=None,
                    reads=[], instruction_from=None)
    if kind == "loop":
        step.update(back_to=node["loop"]["back_to"], bound=node["loop"]["bound"])
    step["ext"] = {}
    if node["title"] != kind_title(step):
        step["title"] = node["title"]
    return step


def _read_typed_arguments(steps: list[dict[str, Any]], links: list[dict[str, str]],
                          nodes: list[dict[str, Any]]) -> None:
    """Say a review's profile and reads and a dispatch's instruction source with typed fields.

    Only what the document's own arguments spell is read, and only what `flow_rules` would accept:
    a `reads` names a review above the step, and an `instruction_from` names a dispatch step that
    owns its instruction. Whether the typed fields say all the arguments do is decided afterwards,
    by compiling the step and comparing; arguments that differ go whole into `ext`.
    """
    order, reviews, parents = _roads(steps, links)
    borrowed = _borrowed_instructions(steps, nodes)
    for step, node in zip(steps, nodes):
        if step["type"] != "agent" or step["capability"] not in ("review", "dispatch"):
            continue
        name, arguments = step["step_id"], node["arguments"]
        if step["capability"] == "review":
            profile = arguments.get("review_profile")
            step["review_profile"] = profile if profile in REVIEW_PROFILES else None
            refs = arguments.get("target_artifact_refs")
        else:
            source = borrowed.get(name)
            step["instruction_from"] = source if source not in borrowed else None
            refs = arguments.get("artifact_refs")
        readable = (reviews & _above(name, parents)) - _nearest_reviews(name, parents, reviews)
        extra = _extra_reads(refs, readable - {name}, order)
        step["reads"] = extra if len(extra) <= MAX_READS else []


def _borrowed_instructions(steps: list[dict[str, Any]], nodes: list[dict[str, Any]]) -> dict:
    """For each dispatch step whose instruction ref names another dispatch step, that step.

    The caller types a borrowing only when the named step is not itself in this mapping, so that
    a step never borrows from one that borrows (`instruction_from_invalid`).
    """
    dispatching = {row["step_id"] for row in steps
                   if row["type"] == "agent" and row["capability"] == "dispatch"}
    found = {}
    for step, node in zip(steps, nodes):
        if step["step_id"] in dispatching:
            source = _instruction_source(
                node["arguments"].get("instruction_ref"), step["step_id"], dispatching)
            if source is not None:
                found[step["step_id"]] = source
    return found


def _instruction_source(ref: object, own: str, dispatching: set[str]) -> str | None:
    """The dispatch step whose instruction this ref names, when it is not the step's own."""
    if not isinstance(ref, str) or not ref.startswith("instruction-"):
        return None
    name = ref[len("instruction-"):]
    return name if name != own and name in dispatching else None


def _above(step_id: str, parents: dict[str, list[str]]) -> set[str]:
    """Every step above `step_id` along the roads."""
    found: set[str] = set()
    pending = list(parents.get(step_id, ()))
    while pending:
        name = pending.pop()
        if name not in found:
            found.add(name)
            pending.extend(parents.get(name, ()))
    return found


def _extra_reads(refs: object, candidates: set[str], order: dict[str, int]) -> list[str]:
    """The review steps a step's input list names beyond the nearest ones, in the order of steps."""
    if not isinstance(refs, list):
        return []
    named = {ref[len("artifact-"):] for ref in refs
             if isinstance(ref, str) and ref.startswith("artifact-")}
    return sorted(named & candidates, key=order.__getitem__)


def _extension(node: dict[str, Any], made: dict[str, Any], kind: str) -> dict[str, Any]:
    """The keys of a document node that the compiler would not write itself, with their values.

    A key the compiler writes and the document lacks is said as null; the only one that can
    happen is `success_requires` on a gate that demands nothing, and null means "not written".
    A gate or a loop, whose step types have no role of their own, also keeps the role keys the
    node carries.
    """
    ext: dict[str, Any] = {}
    keys = (*_BOUND_ORDER, *_EXT_ORDER) if kind in ("human", "loop") else _EXT_ORDER
    for key in keys:
        if key in node:
            if key not in made or node[key] != made[key]:
                ext[key] = copy.deepcopy(node[key])
        elif key in made:
            ext[key] = None
    return ext
