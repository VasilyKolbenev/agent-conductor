"""R5: a step whose harness has no execution boundary is refused before anything can spawn.

Every dispatch and review step demands the boundary of the machine that runs it (spec 10.6), and
it demands it WHETHER OR NOT THE PLAN SAYS SO: the TL merge gate requires the boundary for all
five harnesses, not as an opt-in by a plan word, and a plan written before R5 (the frozen desk
templates) names only ``project-root``. A plan may still write the word ``execution-boundary``
as a `sandbox` resource; it then asks for nothing more than every such step already does.
Unlike ``project-root`` it is not judged by a list: whether it is provided depends on the
platform and on the harness the step is bound to, so each door asks the adapter registry, and no
answer is "not provided". The registry fails closed: an adapter that exposes no boundary seam is
not provided, so a step bound to it is refused like any other that lacks the boundary (the owned
process adapter is such an adapter, and it runs an arbitrary child). A fake or a demo that starts
no vendor agent says so by exposing the seam and answering yes. The refusal is the one the doors
already had, with the new word in it: ``service_refused`` carrying ``{run_id, node_id, sandbox}``
at the plan door, a refused preview, and an authorization refused with the step named. No new
code enters the refusal vocabulary.

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
from conductor.command.adapters.process import ProcessAdapter, ProcessRunner
from conductor.command.api_contracts import ApiRefusal
from conductor.command.artifacts import ArtifactDocument
from conductor.command.authorize_holds import _hold_node_sandbox_is_provided, _hold_plan_admits
from conductor.command.containment import (
    SANDBOX_ROUTES,
    node_unprovidable_sandboxes,
    unprovidable_sandboxes,
)
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
from tests._fakeboundary import confined, installed_outside_the_tree, recording
from tests.test_command_run_store import CONFIG
from tests.test_command_sandbox_route import RUN_ID, _As, _run_following, a_plan, sandbox

#: The ways a harness the step is bound to can lack the boundary, each a different fact.
LINUX, NEVER, SUBSCRIPTION, OUTSIDE = (
    "a platform without a boundary", "a harness never confined", "the subscription login road",
    "a build installed outside the install tree")


def _harness(tmp_path, way):
    """The Claude adapter `CONFIG` binds ``claude-dev`` to, lacking the boundary in one way."""
    login = tmp_path / "login"
    login.mkdir()
    road = {"auth": "subscription", "auth_home": str(login)} if way == SUBSCRIPTION else {}
    adapter, _root, log = claude_t.a_harness(tmp_path, **road)
    scratch = tmp_path / "scratch"
    if way == OUTSIDE:
        installed_outside_the_tree(adapter, tmp_path)
    if way == NEVER:
        return adapter, recording(adapter, scratch), log
    return adapter, confined(adapter, scratch, platform="linux" if way == LINUX else "win32"), log


#: A plan that writes the boundary word, and one that names only the route every plan names. The
#: gate says the second is refused exactly like the first.
PLAN_WORDINGS = [pytest.param(True, id="plan-writes-the-word"),
                 pytest.param(False, id="plan-names-only-project-root")]


def _plan_and_run(tmp_path, writes_the_word=True):
    rows = (sandbox("project-root"), sandbox(BOUNDARY_ROUTE) if writes_the_word else None)
    plan = a_plan(resources=tuple(row for row in rows if row is not None))
    return plan, _run_following(tmp_path / "run", plan).read(RUN_ID)


# -- 1. the named witness ------------------------------------------------------


@pytest.mark.parametrize("writes_the_word", PLAN_WORDINGS)
@pytest.mark.parametrize("way", [LINUX, NEVER, SUBSCRIPTION, OUTSIDE])
def test_a_step_whose_harness_has_no_boundary_is_refused_before_spawn(
        way, writes_the_word, tmp_path):
    adapter, runner, log = _harness(tmp_path, way)
    registry = AdapterRegistry([adapter])
    plan, recovered = _plan_and_run(tmp_path, writes_the_word)

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


@pytest.mark.parametrize("way", [LINUX, SUBSCRIPTION, OUTSIDE])
def test_a_confined_adapter_asked_anyway_for_a_step_without_the_boundary_starts_no_child(
        way, tmp_path):
    """Defence in depth: a caller that skipped the doors still cannot start the child."""
    adapter, runner, log = _harness(tmp_path, way)

    receipt = claude_t.run_once(adapter, claude_t.a_request())

    assert receipt.outcome == "failed"
    assert _fakeclaude.spawns(log) == [], "a child was started for a step with no boundary"
    assert (runner.runs, runner.entries) == ([], [])


def test_a_transport_never_confined_launches_as_before_r5_and_no_door_passes_it(tmp_path):
    """The unconfined launch is the harness fakes' own, and no door lets a plan reach it.

    The provider door builds it only when its caller names ``None`` (the production server never
    does). A transport built that way launches as it did before R5, and the registry says it has
    no boundary, so every door refuses a dispatch or review step bound to it.
    """
    adapter, runner, log = _harness(tmp_path, NEVER)
    registry = AdapterRegistry([adapter])

    receipt = claude_t.run_once(adapter, claude_t.a_request())

    assert [registry.execution_boundary("claude-code", mode) for mode in ATTEMPT_MODES] == [
        False, False]
    assert receipt.outcome == "succeeded", receipt.detail
    assert len(_fakeclaude.spawns(log)) == len(runner.runs) >= 2
    assert runner.entries == [], "a never-confined transport entered the boundary"


@pytest.mark.parametrize("writes_the_word", PLAN_WORDINGS)
def test_the_same_step_on_a_harness_that_has_the_boundary_passes_every_door(
        writes_the_word, tmp_path):
    adapter, _root, _log = claude_t.a_harness(tmp_path)
    runner = confined(adapter, tmp_path / "scratch", platform="win32")
    registry = AdapterRegistry([adapter])
    plan, recovered = _plan_and_run(tmp_path, writes_the_word)

    assert _sandboxes_are_provided(
        RUN_ID, plan.nodes, execution_boundary=registry.execution_boundary,
        config=CONFIG) is None
    assert _hold_capabilities(recovered, plan, registry) is None
    assert _hold_plan_admits(_As("check"), recovered, registry=registry) is None
    assert (runner.runs, runner.entries) == ([], []), "judging a plan starts nothing"


@pytest.mark.parametrize("writes_the_word", PLAN_WORDINGS)
def test_a_step_bound_to_an_adapter_that_declares_it_starts_no_agent_passes_every_door(
        writes_the_word, tmp_path):
    """A fake or a demo has nothing to confine, and says so by exposing the seam and saying yes."""
    adapter, _root, _log = claude_t.a_harness(tmp_path)
    registry = AdapterRegistry([_declared(adapter)])
    plan, recovered = _plan_and_run(tmp_path, writes_the_word)

    assert _sandboxes_are_provided(
        RUN_ID, plan.nodes, execution_boundary=registry.execution_boundary,
        config=CONFIG) is None
    assert _hold_capabilities(recovered, plan, registry) is None
    assert _hold_plan_admits(_As("check"), recovered, registry=registry) is None


@pytest.mark.parametrize("writes_the_word", PLAN_WORDINGS)
def test_a_step_bound_to_an_adapter_that_exposes_no_boundary_seam_is_refused_at_every_door(
        writes_the_word, tmp_path):
    """Silence is not a yes: an adapter that never answers the question is refused, not passed."""
    adapter, _root, log = claude_t.a_harness(tmp_path)
    registry = AdapterRegistry([_seamless(adapter)])
    plan, recovered = _plan_and_run(tmp_path, writes_the_word)

    with pytest.raises(ApiRefusal) as plan_door:
        _sandboxes_are_provided(
            RUN_ID, plan.nodes, execution_boundary=registry.execution_boundary, config=CONFIG)
    with pytest.raises(ContractError, match="cannot provide a required sandbox"):
        _hold_capabilities(recovered, plan, registry)
    with pytest.raises(AuthorizationError, match=f"demands sandbox route.*{BOUNDARY_ROUTE}"):
        _hold_plan_admits(_As("check"), recovered, registry=registry)

    assert plan_door.value.detail["sandbox"] == BOUNDARY_ROUTE
    assert _fakeclaude.spawns(log) == []


def test_a_door_that_is_given_no_fact_refuses_the_boundary_word(tmp_path):
    plan, recovered = _plan_and_run(tmp_path)

    with pytest.raises(ApiRefusal) as plan_door:
        _sandboxes_are_provided(RUN_ID, plan.nodes)
    with pytest.raises(AuthorizationError, match=BOUNDARY_ROUTE):
        _hold_node_sandbox_is_provided(_As("check"), recovered)

    assert plan_door.value.detail["sandbox"] == BOUNDARY_ROUTE


def test_a_door_that_is_given_no_fact_cannot_judge_a_demand_the_plan_did_not_write(tmp_path):
    """The plan door's caller outside this lane hands no fact yet; the doors that spend do."""
    plan, recovered = _plan_and_run(tmp_path, writes_the_word=False)

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


def _node(capability, resources=()):
    return SimpleNamespace(capability=capability, resources=tuple(resources))


@pytest.mark.parametrize("capability", ["dispatch", "review"])
def test_every_step_that_starts_an_agent_demands_the_boundary_without_writing_the_word(
        capability):
    node = _node(capability, (sandbox("project-root"),))

    assert node_unprovidable_sandboxes(node, boundary=lambda: False) == (BOUNDARY_ROUTE,)
    assert node_unprovidable_sandboxes(node, boundary=lambda: True) == ()
    assert node_unprovidable_sandboxes(_node(capability), boundary=lambda: False) == (
        BOUNDARY_ROUTE,)


@pytest.mark.parametrize("capability", ["observe", "message", "pause", None])
def test_a_step_that_starts_no_agent_demands_nothing_it_did_not_write(capability):
    asked = []
    node = _node(capability, (sandbox("project-root"),))

    assert node_unprovidable_sandboxes(node, boundary=lambda: asked.append("asked")) == ()
    assert asked == [], "the fact was asked for a step that starts no agent"
    written = _node(capability, (sandbox(BOUNDARY_ROUTE),))
    assert node_unprovidable_sandboxes(written, boundary=lambda: False) == (BOUNDARY_ROUTE,)


def test_the_boundary_is_named_once_and_after_the_routes_the_plan_wrote():
    other = sandbox("docker")

    assert node_unprovidable_sandboxes(
        _node("dispatch", (other,)), boundary=lambda: False) == ("docker", BOUNDARY_ROUTE)
    assert node_unprovidable_sandboxes(
        _node("dispatch", (other, sandbox(BOUNDARY_ROUTE))),
        boundary=lambda: False) == ("docker", BOUNDARY_ROUTE)


def test_with_no_fact_a_step_is_judged_by_the_rows_it_wrote_and_by_nothing_it_implies():
    for rows in ((), (sandbox("project-root"),), (sandbox("docker"),),
                 (sandbox(BOUNDARY_ROUTE),)):
        node = _node("dispatch", rows)
        assert node_unprovidable_sandboxes(node, boundary=None) == unprovidable_sandboxes(rows)


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


def _wrapped(base, *, has_seam=False, answer=None):
    """A copy of ``base`` with its identity and argument schemas, choosing its boundary seam.

    Without ``has_seam`` it exposes no seam at all: it never answers the question. With it, the
    seam answers ``answer`` for every mode.
    """
    members = {"argument_schemas": type(base).argument_schemas}
    if has_seam:
        members["boundary_provided"] = lambda self, mode: answer
    copy = type("Wrapped", (), members)()
    copy.manifest = base.manifest
    for name in ("observe", "prepare", "execute", "verify"):
        setattr(copy, name, getattr(base, name))
    return copy


def _seamless(base):
    """An adapter that exposes no boundary seam, as the owned process adapter exposes none."""
    return _wrapped(base)


def _declared(base):
    """A fake or a demo that starts no vendor agent: it says so, for every mode, with a yes."""
    return _wrapped(base, has_seam=True, answer=True)


def test_the_registry_asks_the_adapter_and_fails_closed_for_one_that_never_answers(tmp_path):
    adapter, _root, _log = claude_t.a_harness(tmp_path)
    registry = AdapterRegistry([adapter])
    silent, declared = AdapterRegistry([_seamless(adapter)]), AdapterRegistry([_declared(adapter)])

    assert [registry.execution_boundary("claude-code", mode) for mode in ATTEMPT_MODES] == [
        False, False], "an adapter never confined has no boundary"
    confined(adapter, tmp_path / "scratch", platform="win32")
    assert [registry.execution_boundary("claude-code", mode) for mode in ATTEMPT_MODES] == [
        True, True]
    assert [silent.execution_boundary("claude-code", mode) for mode in ATTEMPT_MODES] == [
        False, False], "an adapter with no seam was passed"
    assert [declared.execution_boundary("claude-code", mode) for mode in ATTEMPT_MODES] == [
        True, True]
    with pytest.raises(AdapterContractError):
        registry.execution_boundary("no-such-adapter", "dispatch")
    with pytest.raises(ValueError, match="attempt mode"):
        registry.execution_boundary("claude-code", "plan")
    with pytest.raises(ValueError, match="attempt mode"):
        silent.execution_boundary("claude-code", "plan")


@pytest.mark.parametrize("answer", ["yes", 1, None, "True"])
def test_a_seam_that_answers_anything_but_true_is_not_a_yes(answer, tmp_path):
    adapter, _root, _log = claude_t.a_harness(tmp_path)
    registry = AdapterRegistry([_wrapped(adapter, has_seam=True, answer=answer)])

    assert registry.execution_boundary("claude-code", "dispatch") is False


def test_the_owned_process_adapter_runs_an_arbitrary_child_and_is_not_provided_the_boundary(
        tmp_path):
    """The one adapter in this build that starts an unvetted child has no seam: it is refused."""
    adapter = ProcessAdapter(
        "owned-process", ProcessRunner(tmp_path), clock=lambda: "2026-10-14T12:00:00Z",
        ids=lambda kind: f"{kind}-1")
    registry = AdapterRegistry([adapter])

    assert not hasattr(adapter, "boundary_provided")
    assert [registry.execution_boundary("owned-process", mode) for mode in ATTEMPT_MODES] == [
        False, False]


# -- 4. the roads that authorize an attempt ask the registry -------------------


def _authorize_the_demanding_step(tmp_path, adapter, root, writes_the_word=True):
    """Authorize the one review step of a run, via the runtime.

    Every review step demands the boundary; ``writes_the_word`` says whether its plan also names it.
    """
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
        resources=(sandbox(BOUNDARY_ROUTE),) if writes_the_word else ())
    store.append(GraphDefinition(
        graph_id="graph-review", run_id=review_t.RUN_ID, created_at=review_t.NOW,
        nodes=(step,), edges=()))
    proposal = replace(review_t._proposal(), node_id="review-step", preview_digest="")
    store.append(proposal)
    runtime = ControlRuntime(
        store, AdapterRegistry([adapter]), clock=lambda: review_t.NOW, ids=review_t._Ids())
    budget = Budget(max_actions=8, max_action_seconds=3600, max_confirmation_age_seconds=3600)
    return runtime.authorize(review_t._confirmation(proposal), budget=budget)


@pytest.mark.parametrize("writes_the_word", PLAN_WORDINGS)
def test_the_runtime_authorizes_a_step_demanding_the_boundary_only_on_a_confined_harness(
        writes_the_word, tmp_path):
    adapter, root, log = claude_t.a_harness(tmp_path / "confined")
    runner = confined(adapter, tmp_path / "confined-scratch", platform="win32")

    authorization = _authorize_the_demanding_step(tmp_path, adapter, root, writes_the_word)

    assert authorization.record_created is True
    assert (runner.runs, runner.entries) == ([], []), "authorizing started a child"
    assert _fakeclaude.spawns(log) == []


@pytest.mark.parametrize("writes_the_word", PLAN_WORDINGS)
@pytest.mark.parametrize("way", [LINUX, NEVER])
def test_the_runtime_refuses_a_step_demanding_the_boundary_before_any_attempt(
        way, writes_the_word, tmp_path):
    adapter, root, log = claude_t.a_harness(tmp_path / "bare")
    scratch = tmp_path / "bare-scratch"
    runner = (recording(adapter, scratch) if way == NEVER
              else confined(adapter, scratch, platform="linux"))

    with pytest.raises(AuthorizationError, match=f"demands sandbox route.*{BOUNDARY_ROUTE}"):
        _authorize_the_demanding_step(tmp_path, adapter, root, writes_the_word)

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
