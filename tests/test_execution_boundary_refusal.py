"""R5: a step whose harness has no execution boundary is refused before anything can spawn.

A `sandbox` resource named ``execution-boundary`` is the demand an agent step makes of the
machine that runs it (spec 10.6). Unlike ``project-root`` it is not judged by a list: whether it
is provided depends on the platform and on the harness the step is bound to, so each door asks
the adapter registry, and no answer is "not provided". The refusal is the one the doors already
had, with the new word in it: ``service_refused`` carrying ``{run_id, node_id, sandbox}`` at the
plan door, a refused preview, and an authorization refused with the step named. No new code
enters the refusal vocabulary.

The fake that records spawns is ``tests/_fakeboundary.py`` over the harness fake that logs every
child it receives, so "nothing is spawned" is read from the child itself, not from the adapter.
"""
from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from conductor.command import containment, policy_runtime
from conductor.command import runtime as runtime_module
from conductor.command.adapters import AdapterRegistry
from conductor.command.adapters.base import AdapterContractError
from conductor.command.api_contracts import ApiRefusal
from conductor.command.artifacts import ArtifactDocument
from conductor.command.authorize_holds import _hold_node_sandbox_is_provided, _hold_plan_admits
from conductor.command.containment import SANDBOX_ROUTES, unprovidable_sandboxes
from conductor.command.contract_values import ContractError
from conductor.command.contracts import RunEnvelope
from conductor.command.execution_boundary import ATTEMPT_MODES, BOUNDARY_ROUTE
from conductor.command.graph_definition import GraphDefinition, GraphNode
from conductor.command.http_holds import _sandboxes_are_provided
from conductor.command.policy_preview import _hold_capabilities
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.runtime import Budget, ControlRuntime
from conductor.command.runtime_values import AuthorizationError

from tests import _fakeclaude
from tests import test_command_claude_review as review_t
from tests import test_command_claude_transport as claude_t
from tests._fakeboundary import confined, recording
from tests.test_command_run_store import CONFIG
from tests.test_command_sandbox_route import RUN_ID, _As, _run_following, a_plan, sandbox

#: The three ways a harness the step is bound to can lack the boundary, each a different fact.
LINUX, NEVER, SUBSCRIPTION = (
    "a platform without a boundary", "a harness never confined", "the subscription login road")


def _harness(tmp_path, way):
    """The Claude adapter `CONFIG` binds ``claude-dev`` to, lacking the boundary in one way."""
    login = tmp_path / "login"
    login.mkdir()
    road = {"auth": "subscription", "auth_home": str(login)} if way == SUBSCRIPTION else {}
    adapter, _root, log = claude_t.a_harness(tmp_path, **road)
    scratch = tmp_path / "scratch"
    if way == NEVER:
        return adapter, recording(adapter, scratch), log
    return adapter, confined(adapter, scratch, platform="linux" if way == LINUX else "win32"), log


def _plan_and_run(tmp_path):
    plan = a_plan(resources=(sandbox("project-root"), sandbox(BOUNDARY_ROUTE)))
    return plan, _run_following(tmp_path / "run", plan).read(RUN_ID)


# -- 1. the named witness ------------------------------------------------------


@pytest.mark.parametrize("way", [LINUX, NEVER, SUBSCRIPTION])
def test_a_step_whose_harness_has_no_boundary_is_refused_before_spawn(way, tmp_path):
    adapter, runner, log = _harness(tmp_path, way)
    registry = AdapterRegistry([adapter])
    plan, recovered = _plan_and_run(tmp_path)

    with pytest.raises(ApiRefusal) as plan_door:
        _sandboxes_are_provided(
            RUN_ID, plan.nodes, execution_boundary=registry.execution_boundary, config=CONFIG)
    with pytest.raises(ContractError, match="cannot provide a required sandbox"):
        _hold_capabilities(recovered, plan, registry)
    with pytest.raises(AuthorizationError, match=f"demands sandbox route.*{BOUNDARY_ROUTE}"):
        _hold_plan_admits(_As("check"), recovered, registry=registry)

    assert plan_door.value.code == "service_refused"
    assert plan_door.value.detail == {
        "run_id": RUN_ID, "node_id": "check", "sandbox": BOUNDARY_ROUTE}
    assert (runner.runs, runner.entries) == ([], []), "a door started something"
    assert _fakeclaude.spawns(log) == [], "a child was started for a step with no boundary"


@pytest.mark.parametrize("way", [LINUX, SUBSCRIPTION])
def test_a_confined_adapter_asked_anyway_for_a_step_without_the_boundary_starts_no_child(
        way, tmp_path):
    """Defence in depth: a caller that skipped the doors still cannot start the child."""
    adapter, runner, log = _harness(tmp_path, way)

    receipt = claude_t.run_once(adapter, claude_t.a_request())

    assert receipt.outcome == "failed"
    assert _fakeclaude.spawns(log) == [], "a child was started for a step with no boundary"
    assert (runner.runs, runner.entries) == ([], [])


def test_a_transport_never_confined_launches_as_before_r5_and_no_door_passes_it(tmp_path):
    """The state production is in until the switch: nothing confines, so every door refuses.

    The launch of a never-confined transport is the one that existed before R5. It is pinned here
    so that making confinement the default is a decision with a failing test, not a drift.
    """
    adapter, runner, log = _harness(tmp_path, NEVER)
    registry = AdapterRegistry([adapter])

    receipt = claude_t.run_once(adapter, claude_t.a_request())

    assert [registry.execution_boundary("claude-code", mode) for mode in ATTEMPT_MODES] == [
        False, False]
    assert receipt.outcome == "succeeded", receipt.detail
    assert len(_fakeclaude.spawns(log)) == len(runner.runs) >= 2
    assert runner.entries == [], "a never-confined transport entered the boundary"


def test_the_same_step_on_a_harness_that_has_the_boundary_passes_every_door(tmp_path):
    adapter, _root, _log = claude_t.a_harness(tmp_path)
    runner = confined(adapter, tmp_path / "scratch", platform="win32")
    registry = AdapterRegistry([adapter])
    plan, recovered = _plan_and_run(tmp_path)

    assert _sandboxes_are_provided(
        RUN_ID, plan.nodes, execution_boundary=registry.execution_boundary,
        config=CONFIG) is None
    assert _hold_capabilities(recovered, plan, registry) is None
    assert _hold_plan_admits(_As("check"), recovered, registry=registry) is None
    assert (runner.runs, runner.entries) == ([], []), "judging a plan starts nothing"


def test_a_door_that_is_given_no_fact_refuses_the_boundary_word(tmp_path):
    plan, recovered = _plan_and_run(tmp_path)

    with pytest.raises(ApiRefusal) as plan_door:
        _sandboxes_are_provided(RUN_ID, plan.nodes)
    with pytest.raises(AuthorizationError, match=BOUNDARY_ROUTE):
        _hold_node_sandbox_is_provided(_As("check"), recovered)

    assert plan_door.value.detail["sandbox"] == BOUNDARY_ROUTE


def test_a_plan_that_does_not_demand_the_boundary_is_not_asked_about_it(tmp_path):
    plan = a_plan(resources=(sandbox("project-root"),))
    recovered = _run_following(tmp_path / "run", plan).read(RUN_ID)

    assert _sandboxes_are_provided(RUN_ID, plan.nodes) is None
    assert _hold_node_sandbox_is_provided(_As("check"), recovered) is None


# -- 2. the word, and the fact that judges it ---------------------------------


def test_the_boundary_word_is_judged_by_the_fact_it_is_given_and_by_no_list():
    row = sandbox(BOUNDARY_ROUTE)

    assert BOUNDARY_ROUTE not in SANDBOX_ROUTES
    assert unprovidable_sandboxes((row,)) == (BOUNDARY_ROUTE,)
    assert unprovidable_sandboxes((row,), boundary=lambda: True) == ()
    assert unprovidable_sandboxes((row,), boundary=lambda: False) == (BOUNDARY_ROUTE,)
    assert unprovidable_sandboxes((row,), boundary=lambda: 1) == (BOUNDARY_ROUTE,)


def test_the_fact_is_asked_only_when_a_step_demands_the_boundary():
    asked = []

    unprovidable_sandboxes((sandbox("project-root"),), boundary=lambda: asked.append("asked"))

    assert asked == []


def test_a_step_is_judged_by_its_doers_mode_and_by_the_read_mode_of_its_checker():
    asked = []

    def registry(adapter_id, mode):
        asked.append((adapter_id, mode))
        return True

    config = {"instances": [{"id": "doer", "adapter": "adapter-a"},
                            {"id": "checker", "adapter": "adapter-b"}]}
    dispatch = SimpleNamespace(
        instance_id="doer", capability="dispatch", verifier_instance_id="checker")
    review = SimpleNamespace(instance_id="doer", capability="review", verifier_instance_id=None)

    assert containment.node_boundary(registry, config, dispatch)() is True
    assert asked == [("adapter-a", "dispatch"), ("adapter-b", "review")]
    asked.clear()
    assert containment.node_boundary(registry, config, review)() is True
    assert asked == [("adapter-a", "review")]


def test_a_step_is_provided_only_if_the_doer_and_the_checker_both_are():
    config = {"instances": [{"id": "doer", "adapter": "adapter-a"},
                            {"id": "checker", "adapter": "adapter-b"}]}
    node = SimpleNamespace(
        instance_id="doer", capability="dispatch", verifier_instance_id="checker")

    for only in ("adapter-a", "adapter-b"):
        judge = containment.node_boundary(lambda adapter, mode: adapter == only, config, node)
        assert judge() is False


def _unknown_adapter(adapter_id, mode):
    raise AdapterContractError("not registered")


@pytest.mark.parametrize("changes,ask", [
    pytest.param({"instance_id": "stranger"}, lambda adapter, mode: True, id="unbound-instance"),
    pytest.param({"capability": "observe"}, lambda adapter, mode: True, id="foreign-capability"),
    pytest.param({}, _unknown_adapter, id="registry-raises"),
    pytest.param({}, lambda adapter, mode: "yes", id="answer-is-not-a-bool"),
])
def test_what_a_door_cannot_establish_is_not_provided(changes, ask):
    config = {"instances": [{"id": "doer", "adapter": "adapter-a"}]}
    node = SimpleNamespace(
        **{"instance_id": "doer", "capability": "dispatch", "verifier_instance_id": None,
           **changes})

    assert containment.node_boundary(ask, config, node)() is False


def test_the_capabilities_that_start_an_agent_are_exactly_the_modes_the_boundary_knows():
    assert set(containment.BOUNDARY_MODES.values()) == set(ATTEMPT_MODES)
    assert set(containment.BOUNDARY_MODES) == {"dispatch", "review"}


# -- 3. the registry's fact ----------------------------------------------------


class _Seamless:
    """An adapter that starts no vendor agent: it exposes no boundary seam at all."""

    def __init__(self, base):
        self.manifest = base.manifest
        for name in ("observe", "prepare", "execute", "verify"):
            setattr(self, name, getattr(base, name))


def test_the_registry_asks_the_adapter_that_launches_agents_and_passes_one_that_does_not(tmp_path):
    adapter, _root, _log = claude_t.a_harness(tmp_path)
    registry = AdapterRegistry([adapter])
    other = AdapterRegistry([_Seamless(adapter)])

    assert [registry.execution_boundary("claude-code", mode) for mode in ATTEMPT_MODES] == [
        False, False], "an adapter never confined has no boundary"
    confined(adapter, tmp_path / "scratch", platform="win32")
    assert [registry.execution_boundary("claude-code", mode) for mode in ATTEMPT_MODES] == [
        True, True]
    assert other.execution_boundary("claude-code", "dispatch") is True
    with pytest.raises(AdapterContractError):
        registry.execution_boundary("no-such-adapter", "dispatch")
    with pytest.raises(ValueError, match="attempt mode"):
        registry.execution_boundary("claude-code", "plan")
    with pytest.raises(ValueError, match="attempt mode"):
        other.execution_boundary("claude-code", "plan")


# -- 4. the roads that authorize an attempt ask the registry -------------------


def _authorize_the_demanding_step(tmp_path, adapter, root):
    """Authorize the one review step of a run whose plan demands the boundary, via the runtime."""
    store = RunStore(root)
    store.create_run(RunEnvelope(
        run_id=review_t.RUN_ID, cycle_id="review-cycle", created_at=review_t.NOW,
        config_digest=snapshot_digest(review_t.CONFIG), mode="confirm"), review_t.CONFIG)
    store.append(ArtifactDocument(
        artifact_id="artifact-source-1", artifact_ref=review_t.INPUT_REF, run_id=review_t.RUN_ID,
        created_at=review_t.NOW, media_type="text/markdown", content=review_t.SEED_CONTENT))
    step = GraphNode(
        node_id="review-step", kind="task", title="Review it", instance_id=review_t.INSTANCE_ID,
        capability="review", arguments=review_t.ARGUMENTS,
        resources=(sandbox(BOUNDARY_ROUTE),))
    store.append(GraphDefinition(
        graph_id="graph-review", run_id=review_t.RUN_ID, created_at=review_t.NOW,
        nodes=(step,), edges=()))
    proposal = replace(review_t._proposal(), node_id="review-step", preview_digest="")
    store.append(proposal)
    runtime = ControlRuntime(
        store, AdapterRegistry([adapter]), clock=lambda: review_t.NOW, ids=review_t._Ids())
    budget = Budget(max_actions=8, max_action_seconds=3600, max_confirmation_age_seconds=3600)
    return runtime.authorize(review_t._confirmation(proposal), budget=budget)


def test_the_runtime_authorizes_a_step_demanding_the_boundary_only_on_a_confined_harness(tmp_path):
    adapter, root, log = claude_t.a_harness(tmp_path / "confined")
    runner = confined(adapter, tmp_path / "confined-scratch", platform="win32")

    authorization = _authorize_the_demanding_step(tmp_path, adapter, root)

    assert authorization.record_created is True
    assert (runner.runs, runner.entries) == ([], []), "authorizing started a child"
    assert _fakeclaude.spawns(log) == []


@pytest.mark.parametrize("way", [LINUX, NEVER])
def test_the_runtime_refuses_a_step_demanding_the_boundary_before_any_attempt(way, tmp_path):
    adapter, root, log = claude_t.a_harness(tmp_path / "bare")
    scratch = tmp_path / "bare-scratch"
    runner = (recording(adapter, scratch) if way == NEVER
              else confined(adapter, scratch, platform="linux"))

    with pytest.raises(AuthorizationError, match=f"demands sandbox route.*{BOUNDARY_ROUTE}"):
        _authorize_the_demanding_step(tmp_path, adapter, root)

    assert (runner.runs, runner.entries) == ([], [])
    assert _fakeclaude.spawns(log) == []


@pytest.mark.parametrize("module", [runtime_module, policy_runtime])
def test_each_road_that_authorizes_an_attempt_hands_the_plan_holds_the_registry(module):
    """The call site, which the hold's own tests cannot reach: delete it and they stay green."""
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    calls = [node for node in ast.walk(tree)
             if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "_hold_plan_admits"]

    assert len(calls) == 1
    assert [keyword.arg for keyword in calls[0].keywords] == ["registry"]
