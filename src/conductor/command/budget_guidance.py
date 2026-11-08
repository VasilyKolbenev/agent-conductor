"""Explain and tighten a fresh plan's time limits without quoting model usage or starting work."""
from collections.abc import Mapping
from datetime import datetime
from math import ceil
import re

from .artifacts import required_input_refs, settled_products
from .attempts import AttemptEvent
from .authorization_terms import closed_fields
from .contract_values import ContractError
from .contracts import ActionRequest, ActionResultReceipt
from .plan_budget import plan_budget
from .run_authorization import RunAuthorization
from .store_errors import StoreError
from .workflow_flow import ENTRY_INPUTS


_BASE_SECONDS = {"quick": 180, "balanced": 360, "thorough": 600}
_MARGIN = {"quick": 1.25, "balanced": 1.5, "thorough": 2}
_HISTORY_RUNS = 3


def _entry_documents(records):
    docs = settled_products(row.value for row in records)
    return {doc.artifact_ref: doc.content for doc in docs if doc.artifact_ref in ENTRY_INPUTS}


def _matching_runs(store, recovered):
    """Look at up to three earlier wizard runs of this task. Custom run ids need no history."""
    owner = recovered.config.get("task")
    task = owner.get("id") if isinstance(owner, Mapping) else None
    if not isinstance(task, str):
        return
    number = re.fullmatch(re.escape(task) + r"-r([1-9][0-9]{0,5})", recovered.envelope.run_id)
    if number is None:
        return
    current = int(number[1])
    for index in range(current - 1, max(0, current - _HISTORY_RUNS - 1), -1):
        try:
            prior = store.read(f"{task}-r{index}")
        except StoreError:
            continue
        if (all(prior.config.get(key) == recovered.config.get(key)
                for key in ("task", "workflow", "instances"))
                and _entry_documents(prior.records) == _entry_documents(recovered.records)):
            yield prior


def _observations(records, graph, provider_digest):
    """Measure a completed lease-to-observation interval for an identical, unchecked step."""
    grants = {row.value.authorization_id: row.value.authorization_digest for row in records
              if isinstance(row.value, RunAuthorization)
              and row.value.provider_config_digest == provider_digest}
    previous = [row.value for row in records if row.kind == "graph_definition"]
    if len(previous) != 1:
        return
    previous_nodes = {n.node_id: n for n in previous[0].nodes}
    comparable = {n.node_id: n.instance_id for n in graph.nodes
                  if n == previous_nodes.get(n.node_id)
                  and n.capability and not n.verifier_instance_id}
    requests = {row.value.action_id: row.value for row in records
                if isinstance(row.value, ActionRequest)}
    success = {(row.value.action_id, row.value.attempt_id) for row in records
               if isinstance(row.value, ActionResultReceipt) and row.value.outcome == "succeeded"}
    starts = {}
    for row in records:
        event = row.value
        if (not isinstance(event, AttemptEvent)
                or (event.action_id, event.attempt_id) not in success):
            continue
        request = requests.get(event.action_id)
        if (request is None or comparable.get(request.node_id) != request.instance_id
                or request.instance_id != event.instance_id
                or request.attempt_id != event.attempt_id
                or not request.run_authorization_id
                or grants.get(request.run_authorization_id) != request.run_authorization_digest):
            continue
        if event.phase == "effect_lease":
            starts[event.attempt_id] = datetime.fromisoformat(event.recorded_at)
        elif event.outcome == "succeeded" and event.attempt_id in starts:
            seconds = ceil((datetime.fromisoformat(event.recorded_at) - starts[event.attempt_id])
                           .total_seconds())
            if seconds > 0:
                yield request.node_id, seconds


def recommendation(store, recovered, limits, choice, provider_digest):
    """Return terms, their usual budget and the nonsensitive facts behind the recommendation."""
    depth = closed_fields(choice, {"depth"}, "budget recommendation")["depth"]
    if type(depth) is not str or depth not in _BASE_SECONDS:
        raise ContractError("unsupported budget recommendation depth")
    if any(isinstance(row.value, RunAuthorization) for row in recovered.records):
        raise ContractError("budget recommendations apply before the first authorization")
    definitions = [row.value for row in recovered.records if row.kind == "graph_definition"]
    if len(definitions) != 1:
        raise ContractError("authorization requires one frozen graph")
    graph = definitions[0]
    steps = [n for n in graph.nodes if n.capability is not None]
    inputs = _entry_documents(recovered.records)
    size = sum(len(value.encode("utf-8")) for value in inputs.values())
    samples = {n.node_id: [] for n in steps}
    for prior in _matching_runs(store, recovered):
        for step, seconds in _observations(prior.records, graph, provider_digest):
            samples[step].append(seconds)
    wanted = {}
    history = []
    for node in steps:
        refs = required_input_refs(node.capability, node.payload())
        if not isinstance(refs, (list, tuple)):
            raise ContractError("step inputs must be a list of references")
        # These are initial time reserves, never forecasts or subscription charges.
        extra = 120 * (node.capability == "dispatch") + 90 * bool(node.verifier_instance_id)
        extra += 90 * (len(steps) >= 3) + 60 * min(3, len(node.resources))
        extra += 60 * (len(refs) >= 2) + 120 * (size >= 8192)
        planned = _BASE_SECONDS[depth] + extra
        measured = samples[node.node_id]
        if measured:
            if len(measured) >= 2:
                planned = max(planned, ceil(max(measured) * _MARGIN[depth]))
            history.append({"step_id": node.node_id, "samples": len(measured),
                            "min_seconds": min(measured), "max_seconds": max(measured)})
        wanted[node.node_id] = planned
    budget = plan_budget(graph.nodes, graph.edges, limits, suggested_seconds=wanted)
    summary = {"depth": depth, "status": "preliminary", "base_seconds": _BASE_SECONDS[depth],
               "step_count": len(steps),
               "checker_steps": sum(bool(n.verifier_instance_id) for n in steps),
               "effect_steps": sum(n.capability == "dispatch" for n in steps),
               "resources": len({(r.kind, r.name) for n in steps for r in n.resources}),
               "input_bytes": size, "history_samples": sum(r["samples"] for r in history),
               "history": history, "limited_steps": [r["step_id"] for r in budget["steps"]
                   if r["timeout_seconds"] < wanted[r["step_id"]]]}
    return budget["terms_draft"], budget, summary
