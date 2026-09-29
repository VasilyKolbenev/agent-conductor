"""The rules a flow is held to, and the address of every fault (spec 7.4).

Pure: no store, clock or registry. A row is `{"code", "severity", "at", "params"}`: the desk takes
its words from the code and its highlight from the address (`{"step_id"}`, `{"link": [from, to,
when]}` or null). The order in which faults are looked for is the order of the spec: the form and
the ids, then each step alone, then topology and meaning, and only when nothing is wrong the whole
document goes to the real constructor, whose answer has no address. The rules never restate the
core: an id, a purpose, a bound and a step are judged by the functions the core judges them by.
"""
from __future__ import annotations

import copy
import itertools
import re
from collections.abc import Iterable, Mapping
from types import MappingProxyType, SimpleNamespace
from typing import Any

from .contract_values import ContractError, _id
from .graph_conditions import _CONDITIONS_BY_KIND
from .graph_definition import EFFECTING_CAPABILITIES
from .graph_roads import loop_body
from .graph_template_document import TemplateNode
from .graph_values import MAX_ACTION_SECONDS, MAX_LOOP_BOUND, MIN_LOOP_BOUND, settled_purpose
from .workflow_draft import draft_diagnostics
from .workflow_flow import (
    ENTRY_INPUTS, KIND_TITLES, LINK_WHEN, FlowShapeError, compile_flow, settled_flow)

#: Every code a row may carry, with its severity: an error refuses a publication, a warning never
#: does. Closed, and the desk holds a Russian and an English text for each (spec 7.4).
FLOW_CODES = MappingProxyType({
    "flow_invalid": "error", "id_invalid": "error", "id_repeated": "error",
    "step_id_reserved": "error", "text_invalid": "error", "ref_unknown": "error",
    "when_invalid": "error", "link_makes_cycle": "error", "ext_invalid": "error",
    "dispatch_without_checker": "error", "checker_is_doer": "error", "dead_join": "error",
    "final_gate_missing": "error", "dispatch_not_accepted": "error", "loop_body_empty": "error",
    "gate_before_dispatch": "error", "instruction_from_invalid": "error",
    "reads_invalid": "error", "bound_range": "error", "timeout_range": "error",
    "clean_over_actions": "error", "clean_over_time": "error", "template_refused": "error",
    "contract_refused": "error",
    "worst_over_actions": "warning", "worst_over_time": "warning", "timeout_clamped": "warning",
    "review_after_dispatch": "warning", "role_kind_mismatch": "warning",
    "link_outside_desk": "warning", "fork_failure_stops": "warning", "loop_order": "warning",
    "rework_after_correction": "warning", "return_after_correction": "warning",
    "role_unassigned": "warning", "role_capability_unsupported": "warning",
    "checker_cannot_verify": "warning",
})
#: A step id whose `artifact-<id>` the run's own documents already hold (spec 6.2, 7.4).
RESERVED_STEP_IDS = frozenset(ref[len("artifact-"):] for ref in ENTRY_INPUTS)
#: The capability a role kind is drawn for (spec 7.2.2); the same keys as `KIND_TITLES`.
CAPABILITY_OF_KIND = MappingProxyType({
    "analyst": "review", "designer": "review", "diagnostician": "review", "reviewer": "review",
    "doer": "dispatch", "tester": "dispatch",
})
MAX_TEXT = 500
#: The words of a road that the desk draws by default; any other is an extended field (7.2.1).
_DESK_WORDS = frozenset({"success", "approved", "rejected"})
_ROLE_KIND = re.compile(r"role-([a-z]+)(?:-[0-9]+)?\Z")
_ADDRESSED_BEFORE_EXT = frozenset({
    "id_invalid", "text_invalid", "bound_range", "timeout_range", "checker_is_doer"})
_STEP_PATH = re.compile(r"flow\.(steps|links)\[([0-9]+)\]")


def flow_rules(flow: object, doc: Mapping[str, Any] | None = None,
               binding: Mapping[str, Any] | None = None,
               budget: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    """The rows for a flow: errors first, in the order of spec 7.4, then warnings.

    Args:
        flow: The flow, as the desk sent it; a flow the form refuses answers one `flow_invalid`.
        doc: `compile_flow` of the flow, when the caller has it already.
        binding: Role to facts of the harness it is given to, for the three binding warnings:
            `{role_id: {"capabilities": [...], "verifies": bool} | None}`. None asks nothing.
        budget: The `plan_budget` answer for the compiled document, when it was built; it
            supplies the rows of the budget and of the clamped time.
    """
    try:
        settled = settled_flow(flow)
    except FlowShapeError as error:
        return [_flow_invalid(flow, error)]
    document = compile_flow(settled) if doc is None else doc
    graph = _Graph(settled)
    rows = _address_errors(graph, document)
    rows += _budget_errors(budget)
    if not any(row["severity"] == "error" for row in rows):
        rows += _constructor_rows(document)
    return rows + _warnings(graph, document, binding, budget)


def _row(code: str, at: dict | None = None, **params: Any) -> dict[str, Any]:
    return {"code": code, "severity": FLOW_CODES[code], "at": at, "params": params}


def _at_step(name: str) -> dict[str, Any]:
    return {"step_id": name}


def _at_link(link: Mapping[str, str]) -> dict[str, Any]:
    return {"link": [link["from"], link["to"], link["when"]]}


def _flow_invalid(raw: object, error: FlowShapeError) -> dict[str, Any]:
    """One row for a flow the form refuses, addressed to the step or link the path names."""
    at = None
    named = _STEP_PATH.match(error.path)
    if named is not None and isinstance(raw, Mapping):
        try:
            item = raw[named.group(1)][int(named.group(2))]
            at = (_at_step(item["step_id"]) if named.group(1) == "steps"
                  else _at_link(item))
        except (KeyError, IndexError, TypeError):
            at = None
    return _row("flow_invalid", at, path=error.path)


class _Graph:
    """The roads of a flow: what leads to what, and what can be reached from where."""

    def __init__(self, flow: Mapping[str, Any]) -> None:
        self.flow, self.steps, self.links = flow, flow["steps"], flow["links"]
        self.by_id: dict[str, dict] = {}
        self.order: dict[str, int] = {}
        for number, row in enumerate(self.steps):
            self.by_id.setdefault(row["step_id"], row)
            self.order.setdefault(row["step_id"], number)
        self.into: dict[str, list[dict]] = {name: [] for name in self.by_id}
        self.out: dict[str, list[dict]] = {name: [] for name in self.by_id}
        for link in self.links:
            if link["from"] in self.by_id and link["to"] in self.by_id:
                self.out[link["from"]].append(link)
                self.into[link["to"]].append(link)
        self.bounded = "execution_contract" not in flow["ext"]
        self._bodies: dict[str, frozenset[str]] = {}

    def reach(self, starts: Iterable[str], words: Iterable[str] | None = None) -> set[str]:
        """Every step reachable from `starts`, themselves included, along roads of `words`."""
        found: set[str] = set()
        pending = list(starts)
        while pending:
            name = pending.pop()
            if name in found:
                continue
            found.add(name)
            pending.extend(link["to"] for link in self.out[name]
                           if words is None or link["when"] in words)
        return found

    def above(self, name: str) -> set[str]:
        """Every step above `name` along the roads."""
        found: set[str] = set()
        pending = [link["from"] for link in self.into[name]]
        while pending:
            up = pending.pop()
            if up not in found:
                found.add(up)
                pending.extend(link["from"] for link in self.into[up])
        return found

    def body(self, loop: str) -> frozenset[str]:
        """The steps a loop step reopens (both ends included), by the core's own walk."""
        if loop not in self._bodies:
            nodes = [SimpleNamespace(
                node_id=name, loop=SimpleNamespace(back_to=row.get("back_to")))
                for name, row in self.by_id.items()]
            edges = [SimpleNamespace(from_node=link["from"], to_node=link["to"])
                     for links in self.out.values() for link in links]
            target = next(node for node in nodes if node.node_id == loop)
            self._bodies[loop] = loop_body(nodes, edges, target)
        return self._bodies[loop]

    def kind(self, name: str) -> str:
        return self.by_id[name]["type"]


def _is_dispatch(step: Mapping[str, Any]) -> bool:
    return step["type"] == "agent" and step["capability"] in EFFECTING_CAPABILITIES


def _is_review(step: Mapping[str, Any]) -> bool:
    return step["type"] == "agent" and step["capability"] == "review"


# --- the errors, in the order of spec 7.4 ----------------------------------------------------


def _address_errors(graph: _Graph, document: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = _identity_rows(graph) + _reference_rows(graph) + _range_rows(graph)
    rows += _checker_rows(graph)
    rows += _road_rows(graph, document) + _meaning_rows(graph)
    rows += _extension_rows(graph, document, {
        row["at"]["step_id"] for row in rows
        if row["code"] in _ADDRESSED_BEFORE_EXT and row["at"] and "step_id" in row["at"]})
    return rows


def _valid_id(value: object) -> bool:
    try:
        _id("id", value)
    except ContractError:
        return False
    return True


def _id_fields(step: Mapping[str, Any]) -> list[tuple[str, Any]]:
    fields: list[tuple[str, Any]] = [("step_id", step["step_id"])]
    if step["type"] == "agent":
        fields += [("role_id", step["role_id"]), ("capability", step["capability"])]
        fields += [(name, step[name]) for name in ("verifier_role_id", "instruction_from")
                   if step[name] is not None]
        fields += [(f"reads[{number}]", name) for number, name in enumerate(step["reads"])]
    if step["type"] == "loop":
        fields.append(("back_to", step["back_to"]))
    return fields


def _identity_rows(graph: _Graph) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for step in graph.steps:
        name, at = step["step_id"], _at_step(step["step_id"])
        rows += [_row("id_invalid", at, field=field) for field, value in _id_fields(step)
                 if not _valid_id(value)]
        if name in seen:
            rows.append(_row("id_repeated", at))
        seen.add(name)
        if name in RESERVED_STEP_IDS:
            rows.append(_row("step_id_reserved", at))
        rows += _text_rows(step, at)
    if not _sound_text(graph.flow["title"], required=True):
        rows.append(_row("text_invalid", None, field="title"))
    pairs: set[tuple[str, str]] = set()
    for link in graph.links:
        at = _at_link(link)
        rows += [_row("id_invalid", at, field=field) for field in ("from", "to")
                 if not _valid_id(link[field])]
        if (link["from"], link["to"]) in pairs:
            rows.append(_row("id_repeated", at))
        pairs.add((link["from"], link["to"]))
    return rows


def _text_rows(step: Mapping[str, Any], at: dict) -> list[dict[str, Any]]:
    rows = []
    if not _sound_text(step["title"]):
        rows.append(_row("text_invalid", at, field="title"))
    try:
        settled_purpose(step["purpose"])
    except ContractError:
        rows.append(_row("text_invalid", at, field="purpose"))
    return rows


def _sound_text(value: str | None, *, required: bool = False) -> bool:
    """A title is one line of at most 500 characters; empty is not text, absent is allowed."""
    if value is None:
        return not required
    return (bool(value.strip()) and len(value) <= MAX_TEXT
            and not any(mark in value for mark in ("\x00", "\n", "\r")))


def _reference_rows(graph: _Graph) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for step in graph.steps:
        at = _at_step(step["step_id"])
        for field, value in _id_fields(step)[1:]:
            if field in ("role_id", "capability", "verifier_role_id"):
                continue
            if _valid_id(value) and value not in graph.by_id:
                rows.append(_row("ref_unknown", at, field=field, ref=value))
    for link in graph.links:
        rows += [_row("ref_unknown", _at_link(link), field=field, ref=link[field])
                 for field in ("from", "to")
                 if _valid_id(link[field]) and link[field] not in graph.by_id]
    return rows


def _range_rows(graph: _Graph) -> list[dict[str, Any]]:
    rows = []
    for step in graph.steps:
        at = _at_step(step["step_id"])
        seconds = step["timeout_seconds"]
        if seconds is not None and not 1 <= seconds <= MAX_ACTION_SECONDS:
            rows.append(_row("timeout_range", at))
        if step["type"] == "loop" and not MIN_LOOP_BOUND <= step["bound"] <= MAX_LOOP_BOUND:
            rows.append(_row("bound_range", at, field="bound"))
        bound = step["ext"].get("attempt_bound")
        if bound is not None and not (type(bound) is int
                                      and MIN_LOOP_BOUND <= bound <= MAX_LOOP_BOUND):
            rows.append(_row("bound_range", at, field="attempt_bound"))
    return rows


def _checker_rows(graph: _Graph) -> list[dict[str, Any]]:
    rows = []
    for step in graph.steps:
        if step["type"] != "agent":
            continue
        at = _at_step(step["step_id"])
        if _is_dispatch(step) and step["verifier_role_id"] is None:
            rows.append(_row("dispatch_without_checker", at))
        if step["verifier_role_id"] is not None and step["verifier_role_id"] == step["role_id"]:
            rows.append(_row("checker_is_doer", at))
    return rows


def _road_rows(graph: _Graph, document: Mapping[str, Any]) -> list[dict[str, Any]]:
    nodes = {row["node_id"]: row for row in document["nodes"]}
    rows = [_row("when_invalid", _at_link(link), **why)
            for link, why in _impossible_words(graph, nodes)]
    rows += [_row("link_makes_cycle", _at_link(link)) for link in _cycle_closers(graph)]
    rows += [_row("dead_join", _at_step(join), source=source)
             for join, source in _dead_joins(graph).items()]
    return rows


def _impossible_words(graph: _Graph, nodes: Mapping[str, Any]):
    """Links whose word the step behind them cannot produce, or that mix roads (spec 7.4)."""
    for name, links in graph.out.items():
        step = graph.by_id[name]
        allowed = _words_of(step, nodes.get(name, {}))
        conditional = [link for link in links if link["when"] != "always"]
        for link in links:
            if link["when"] != "always" and link["when"] not in allowed:
                yield link, {"reason": "word"}
            elif link["when"] == "always" and conditional:
                yield link, {"reason": "mixed_roads"}


def _words_of(step: Mapping[str, Any], node: Mapping[str, Any]) -> set[str]:
    """The words of a road this step can produce: what its kind says, less a waiver it refuses."""
    kind = {"agent": "task", "human": "gate", "loop": "loop"}.get(step["type"])
    if kind is None:
        return set()
    produced = _CONDITIONS_BY_KIND[kind]
    words = {when for when, condition in LINK_WHEN.items() if condition in produced}
    if step["type"] == "human" and node.get("success_requires") == "human_approval":
        words.discard("waived")
    return words


def _cycle_closers(graph: _Graph) -> list[dict[str, str]]:
    """The links that close a cycle: a road that returns to a step whose walk is still open."""
    colour: dict[str, int] = {}
    closers = []
    for start in graph.by_id:
        if start in colour:
            continue
        colour[start] = 1
        stack = [(start, iter(graph.out[start]))]
        while stack:
            name, roads = stack[-1]
            link = next(roads, None)
            if link is None:
                colour[name] = 2
                stack.pop()
            elif colour.get(link["to"], 0) == 1:
                closers.append(link)
            elif link["to"] not in colour:
                colour[link["to"]] = 1
                stack.append((link["to"], iter(graph.out[link["to"]])))
    return closers


def _dead_joins(graph: _Graph) -> dict[str, str]:
    """Steps that wait for roads from two different outcomes of one step: they never start."""
    found: dict[str, str] = {}
    for source, links in graph.out.items():
        by_word: dict[str, list[dict]] = {}
        for link in links:
            if link["when"] != "always":
                by_word.setdefault(link["when"], []).append(link)
        for one, other in itertools.combinations(sorted(by_word), 2):
            first = graph.reach(link["to"] for link in by_word[one])
            second = graph.reach(link["to"] for link in by_word[other])
            for join in sorted(first & second, key=graph.order.__getitem__):
                if join not in found and _waits_for_both(
                        graph, join, (by_word[one], first), (by_word[other], second)):
                    found[join] = source
    return found


def _waits_for_both(graph: _Graph, join: str, one: tuple, other: tuple) -> bool:
    def branch(links: list[dict], reached: set[str]) -> list[dict]:
        return [road for road in graph.into[join] if road in links or road["from"] in reached]
    return any(a is not b for a in branch(*one) for b in branch(*other))


def _meaning_rows(graph: _Graph) -> list[dict[str, Any]]:
    rows = _gate_rows(graph)
    for step in graph.steps:
        if graph.by_id[step["step_id"]] is not step:
            continue  # a repeated id is already an error; its second holder is not judged
        at = _at_step(step["step_id"])
        if step["type"] == "loop" and step["back_to"] in graph.by_id:
            if step["back_to"] == step["step_id"] or not graph.body(step["step_id"]):
                rows.append(_row("loop_body_empty", at))
        if step["type"] == "agent":
            rows += _instruction_rows(graph, step, at) + _reads_rows(graph, step, at)
        if _is_dispatch(step) and not graph.bounded and not _behind_a_gate(graph, step):
            rows.append(_row("gate_before_dispatch", at))
    return rows


def _final_gates(graph: _Graph) -> list[str]:
    return [step["step_id"] for step in graph.steps if step["type"] == "human"
            and not any(link["when"] == "approved" for link in graph.out[step["step_id"]])]


def _gate_rows(graph: _Graph) -> list[dict[str, Any]]:
    finals = _final_gates(graph)
    if not finals:
        return [_row("final_gate_missing")]
    rows = []
    for step in graph.steps:
        if _is_dispatch(step) and not graph.reach(
                [step["step_id"]], {"success", "approved", "always"}) & set(finals):
            rows.append(_row("dispatch_not_accepted", _at_step(step["step_id"])))
    return rows


def _behind_a_gate(graph: _Graph, step: Mapping[str, Any]) -> bool:
    roads = graph.into[step["step_id"]]
    return bool(roads) and all(graph.kind(link["from"]) == "human" for link in roads)


def _instruction_rows(graph: _Graph, step: dict, at: dict) -> list[dict[str, Any]]:
    source = step["instruction_from"]
    if source is None or source not in graph.by_id:
        return []
    other = graph.by_id[source]
    if (not _is_dispatch(step) or source == step["step_id"] or not _is_dispatch(other)
            or other["instruction_from"] is not None):
        return [_row("instruction_from_invalid", at, ref=source)]
    return []


def _reads_rows(graph: _Graph, step: dict, at: dict) -> list[dict[str, Any]]:
    above = graph.above(step["step_id"])
    return [_row("reads_invalid", at, ref=name) for name in step["reads"]
            if name in graph.by_id and not (
                _is_review(graph.by_id[name]) and name in above and name != step["step_id"])]


def _extension_rows(graph: _Graph, document: Mapping[str, Any],
                    skipped: set[str]) -> list[dict[str, Any]]:
    """A step built alone, as a template node, that the core refuses (spec 7.4, step 2)."""
    rows = []
    for number, step in enumerate(graph.steps):
        if step["step_id"] in skipped or number >= len(document["nodes"]):
            continue
        node = document["nodes"][number]
        if _builds(node):
            continue
        culprits = [key for key in step["ext"] if _builds_without(graph.flow, number, key)]
        params = {"field": culprits[0]} if len(culprits) == 1 else {}
        rows.append(_row("ext_invalid", _at_step(step["step_id"]), **params))
    return rows


def _builds(node: Mapping[str, Any]) -> bool:
    try:
        TemplateNode.from_dict(copy.deepcopy(dict(node)))
    except ContractError:
        return False
    return True


def _builds_without(flow: Mapping[str, Any], number: int, key: str) -> bool:
    """Whether the step's node builds once its `key` override is taken away."""
    trial = copy.deepcopy(dict(flow))
    del trial["steps"][number]["ext"][key]
    return _builds(compile_flow(trial)["nodes"][number])


def _constructor_rows(document: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The answer of the real constructor to the whole document; it names no step (spec 7.4)."""
    return [_row(row["code"]) for row in draft_diagnostics(
        document, workflow_id="workflow-probe", revision=1)]


# --- the budget rows -------------------------------------------------------------------------


def _budget_errors(budget: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if budget is None:
        return []
    limits, clean = budget["limits"], budget["clean"]
    rows = []
    if clean["actions"] > limits["max_actions"]:
        rows.append(_row("clean_over_actions"))
    if clean["seconds"] > limits["max_total_task_seconds"]:
        rows.append(_row("clean_over_time"))
    return rows


def _budget_warnings(budget: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if budget is None:
        return []
    limits, worst = budget["limits"], budget["worst"]
    rows = []
    if worst["actions"] > limits["max_actions"]:
        rows.append(_row("worst_over_actions"))
    if worst["seconds"] > limits["max_total_task_seconds"]:
        rows.append(_row("worst_over_time"))
    return rows


def _clamped_rows(budget: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    steps = [] if budget is None else budget["steps"]
    return [_row("timeout_clamped", _at_step(row["step_id"])) for row in steps if row["clamped"]]


# --- the warnings ----------------------------------------------------------------------------


def _warnings(graph: _Graph, document: Mapping[str, Any], binding: Mapping[str, Any] | None,
              budget: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    rows = _clamped_rows(budget) + _placement_rows(graph) + _outside_desk_rows(graph)
    rows += _loop_rows(graph)
    rows += [] if binding is None else _binding_rows(graph, binding)
    return rows + _budget_warnings(budget)


def _placement_rows(graph: _Graph) -> list[dict[str, Any]]:
    rows = []
    for step in graph.steps:
        if step["type"] != "agent":
            continue
        at = _at_step(step["step_id"])
        if _is_review(step) and any(_is_dispatch(graph.by_id[name])
                                    for name in graph.above(step["step_id"])):
            rows.append(_row("review_after_dispatch", at))
        named = _ROLE_KIND.fullmatch(step["role_id"])
        kind = named.group(1) if named is not None else None
        if kind in KIND_TITLES and CAPABILITY_OF_KIND[kind] != step["capability"]:
            rows.append(_row("role_kind_mismatch", at))
    return rows


def _outside_desk_rows(graph: _Graph) -> list[dict[str, Any]]:
    rows = [_row("link_outside_desk", _at_link(link)) for link in graph.links
            if not _in_desk(graph, link)]
    rows += [_row("fork_failure_stops", _at_step(name)) for name, links in graph.out.items()
             if any(count > 1 for count in _word_counts(links).values())]
    return rows


def _in_desk(graph: _Graph, link: Mapping[str, str]) -> bool:
    """A road the desk draws: success, approved, rejected, and a loop's own entry roads."""
    if link["when"] in _DESK_WORDS:
        return True
    into_loop = link["to"] in graph.by_id and graph.kind(link["to"]) == "loop"
    return into_loop and link["when"] in ("failed", "changes_requested")


def _word_counts(links: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for link in links:
        counts[link["when"]] = counts.get(link["when"], 0) + 1
    return counts


def _loops_of(graph: _Graph) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """The pass loops (a failed dispatch step into a loop) and the rework loops (a gate's
    changes requested into a loop), each as `(loop step, the step that leads into it)`."""
    passes: list[tuple[str, str]] = []
    reworks: list[tuple[str, str]] = []
    for step in graph.steps:
        if (step["type"] != "loop" or step["back_to"] not in graph.by_id
                or graph.by_id[step["step_id"]] is not step):
            continue
        for link in graph.into[step["step_id"]]:
            source = graph.by_id[link["from"]]
            if link["when"] == "failed" and _is_dispatch(source):
                passes.append((step["step_id"], link["from"]))
            elif link["when"] == "changes_requested" and source["type"] == "human":
                reworks.append((step["step_id"], link["from"]))
    return passes, reworks


def _loop_rows(graph: _Graph) -> list[dict[str, Any]]:
    passes, reworks = _loops_of(graph)
    rows = [_row("loop_order", _at_step(loop)) for loop in _in_order(graph, {
        loop for loop, _ in passes for rework, _ in reworks
        if graph.order[loop] < graph.order[rework]
        and graph.body(loop) & graph.body(rework)})]
    rows += [_row("rework_after_correction", _at_step(name)) for name in _in_order(graph, {
        source for _, source in passes for rework, _ in reworks
        if source in graph.body(rework)})]
    rows += [_row("return_after_correction", _at_step(name))
             for name in _in_order(graph, _returned_to_after_own_passes(graph, passes))]
    return rows


def _in_order(graph: _Graph, names: set[str]) -> list[str]:
    return sorted(names, key=graph.order.__getitem__)


def _returned_to_after_own_passes(graph: _Graph, passes: list[tuple[str, str]]) -> set[str]:
    """Dispatch steps with passes of their own and a return from another step (spec 7.6)."""
    homes = {(source, graph.by_id[loop]["back_to"]) for loop, source in passes}
    return {home for source, home in homes if source == home
            and any(other != home and target == home for other, target in homes)}


def _binding_rows(graph: _Graph, binding: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for step in graph.steps:
        if step["type"] != "agent":
            continue
        at, role = _at_step(step["step_id"]), step["role_id"]
        facts = binding.get(role)
        if facts is None:
            rows.append(_row("role_unassigned", at, role_id=role))
        elif step["capability"] not in facts["capabilities"]:
            rows.append(_row("role_capability_unsupported", at, role_id=role))
        checker = step["verifier_role_id"]
        if checker is None:
            continue
        if binding.get(checker) is None:
            rows.append(_row("role_unassigned", at, role_id=checker))
        elif not binding[checker]["verifies"]:
            rows.append(_row("checker_cannot_verify", at, role_id=checker))
    return rows
