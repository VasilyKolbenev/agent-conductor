"""A named checker needs a registered independent seam before a run can act."""
from dataclasses import replace

import pytest

from conductor.command.adapters import AdapterRegistry
from conductor.command.api_contracts import ApiRefusal
from conductor.command.authorize_holds import _hold_verifier_is_servable
from conductor.command.graph_definition import GraphNode
from conductor.command.http_holds import _verifiers_are_servable
from conductor.command.runtime import AuthorizationError, ControlRuntime
from tests.test_command_graph_route import graph_api, graph_body
from tests.test_command_plan_verifier import CHECKER, NODE, a_bound_store
from tests.test_command_run_store import CONFIG as RUN_CONFIG
from tests.test_command_runtime_authorize import (
    a_budget, a_confirmation, a_proposal, fixed_clock, fixed_ids,
)
from tests.test_command_runtime_execute import ScriptedAdapter


CONFIG = {"instances": [{"id": "worker", "adapter": "provider-doer"},
                        {"id": "checker", "adapter": "provider-checker"}]}


def node(verifier="checker"):
    return GraphNode(
        node_id="review", kind="task", title="Review", instance_id="worker",
        capability="review", arguments={}, verifier_instance_id=verifier)


def bound(config, run_id, instance_id):
    for row in config["instances"]:
        if row["id"] == instance_id:
            return row["adapter"]
    raise ApiRefusal.service_missing_instance(run_id, instance_id)


def test_open_asks_the_registry_fact_for_the_checker_and_the_doers_capability():
    calls = []

    def supported(adapter, capability):
        calls.append((adapter, capability))
        return True

    _verifiers_are_servable(
        CONFIG, "run-001", (node(),), bound, supported,
        reachable={"provider-checker"})
    assert calls == [("provider-checker", "review")]
    _verifiers_are_servable(CONFIG, "run-001", (node(None),), bound, supported)
    assert calls == [("provider-checker", "review")]


@pytest.mark.parametrize("answer", [False, None, 1, "yes"])
def test_open_requires_an_actual_independent_registry_fact(answer):
    with pytest.raises(ApiRefusal) as refusal:
        _verifiers_are_servable(
            CONFIG, "run-001", (node(),), bound, lambda *_: answer)
    assert refusal.value.code == "capability_unsupported"
    assert refusal.value.status == 409


def test_open_names_a_missing_checker_and_checks_reachability_first():
    calls = []
    with pytest.raises(ApiRefusal) as missing:
        _verifiers_are_servable(
            CONFIG, "run-001", (node("not-declared"),), bound,
            lambda *args: calls.append(args))
    assert missing.value.code == "service_refused"
    assert "not-declared" in str(missing.value)
    with pytest.raises(ApiRefusal) as unreachable:
        _verifiers_are_servable(
            CONFIG, "run-001", (node(),), bound,
            lambda *args: calls.append(args), reachable=set())
    assert unreachable.value.code == "service_refused"
    assert "checker" in str(unreachable.value)
    assert calls == []


def test_the_real_open_plan_judge_reaches_the_independent_checker_hold(tmp_path, monkeypatch):
    subject, _, _ = graph_api(tmp_path)
    monkeypatch.setattr(subject, "_reachable", lambda: {"claude-code", "codex"})
    body = graph_body()["nodes"][2]
    planned = GraphNode.from_dict({**body, "verifier_instance_id": "codex-review"})
    # The doer pair is fully servable; only the checker is missing a seam.
    with pytest.raises(ApiRefusal) as refusal:
        subject._judge_plan(RUN_CONFIG, "run-001", (planned,))
    assert refusal.value.code == "capability_unsupported"
    assert refusal.value.status == 409
    subject._judge_plan(RUN_CONFIG, "run-001", (GraphNode.from_dict(body),))


def test_authorize_refuses_an_unservable_checker_before_any_durable_request(tmp_path):
    store = a_bound_store(tmp_path, verifier=CHECKER)
    registry = AdapterRegistry([
        ScriptedAdapter(adapter_id="claude-code"),
        ScriptedAdapter(adapter_id="codex")])
    runtime = ControlRuntime(store, registry, clock=fixed_clock(), ids=fixed_ids())
    proposal = a_proposal(store, node_id=NODE)
    journal = store.run_path("run-001") / "records.jsonl"
    before = journal.read_bytes()
    with pytest.raises(AuthorizationError, match="codex-review.*cannot verify"):
        runtime.authorize(a_confirmation(proposal), budget=a_budget())
    assert journal.read_bytes() == before


def test_authorize_unknown_checker_is_named_and_unnamed_plan_uses_no_callback(tmp_path):
    store = a_bound_store(tmp_path, verifier="not-declared")
    proposal = a_proposal(store, node_id=NODE)
    recovered = store.read("run-001")
    with pytest.raises(AuthorizationError, match="not-declared.*not declared"):
        _hold_verifier_is_servable(proposal, recovered, lambda *_: True)
    # A proposal without a plan-bound node is the retained unnamed-verifier road.
    _hold_verifier_is_servable(replace(proposal, node_id=None, preview_digest=""),
                              recovered, None)


def test_authorize_uses_the_same_pair_fact_and_refuses_missing_or_broken_reader(tmp_path):
    store = a_bound_store(tmp_path, verifier=CHECKER)
    proposal = a_proposal(store, node_id=NODE)
    recovered = store.read("run-001")
    calls = []

    def supported(adapter, capability):
        calls.append((adapter, capability))
        return True

    _hold_verifier_is_servable(proposal, recovered, supported)
    assert calls == [("codex", "dispatch")]
    with pytest.raises(AuthorizationError, match="cannot verify"):
        _hold_verifier_is_servable(proposal, recovered, None)

    def broken(*_):
        raise LookupError("unregistered adapter")

    with pytest.raises(AuthorizationError, match="cannot verify"):
        _hold_verifier_is_servable(proposal, recovered, broken)
