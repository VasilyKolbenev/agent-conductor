"""CommandService: observe in every mode, propose only above observe.

The service turns a registered adapter's report into a durable observation and a
lane's intent into an immutable proposal. It never prepares, never executes,
never reaches a subprocess or a browser, and never invents an id or a clock: both
arrive through injected, deterministic providers. Absence of an adapter, an
observation, or a proposal is never dressed up as success.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from conductor.command import service as service_module
from conductor.command.adapters import AdapterContractError, AdapterRegistry
from conductor.command.adapters.base import CAPABILITIES, UnsupportedCapability
from conductor.command.contracts import ActionProposal, ControlMode, ObservationRecord
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.service import CommandService, ServiceError

from tests.test_command_adapters import FakeAdapter, RecordingAdapter
from tests.test_command_run_store import CONFIG, a_run


NOW = "2026-08-11T10:00:00Z"

ALLOWED_SERVICE_IMPORTS = frozenset({
    "__future__", "collections.abc", "dataclasses", "typing",
})


def fixed_ids():
    return lambda purpose: f"{purpose}-fixed"


def fixed_clock():
    return lambda: NOW


def a_store(tmp_path, *, mode="propose"):
    store = RunStore(tmp_path)
    store.create_run(a_run(mode=mode, config_digest=snapshot_digest(CONFIG)), CONFIG)
    return store


def a_service(tmp_path, *, mode="propose", adapters=None):
    store = a_store(tmp_path, mode=mode)
    registry = AdapterRegistry(adapters if adapters is not None else [FakeAdapter()])
    return CommandService(store, registry, clock=fixed_clock(), ids=fixed_ids()), store


def propose_kwargs(**changes):
    values = {
        "run_id": "run-001",
        "adapter_id": "claude-code",
        "instance_id": "claude-dev",
        "attempt_id": "attempt-001",
        "capability": "dispatch",
        "arguments": {"handoff": "packet-001"},
        "scope": ("src",),
        "proposed_by": "claude-dev",
        "rationale": "The lane finished its handoff and asks to dispatch review.",
        "timeout_seconds": 900,
    }
    values.update(changes)
    return values


def test_observe_works_in_every_mode_and_persists_a_durable_observation(tmp_path):
    for index, mode in enumerate(member.value for member in ControlMode):
        service, store = a_service(tmp_path / f"m{index}", mode=mode)
        record = service.observe(
            run_id="run-001", adapter_id="claude-code", instance_id="claude-dev")
        assert isinstance(record, ObservationRecord)
        assert record.observation_id == "observation-fixed"
        assert record.health == "ready"
        stored = store.read("run-001").records
        assert [row.kind for row in stored] == ["adapter_observation"]
        assert stored[0].value == record


def test_propose_is_forbidden_in_observe_and_never_records_one(tmp_path):
    service, store = a_service(tmp_path, mode="observe")
    with pytest.raises(ServiceError, match="observe"):
        service.propose(**propose_kwargs())
    assert store.read("run-001").records == ()


@pytest.mark.parametrize("mode", [
    member.value for member in ControlMode if member is not ControlMode.OBSERVE])
def test_propose_is_allowed_above_observe_and_persists_an_immutable_proposal(tmp_path, mode):
    service, store = a_service(tmp_path / mode, mode=mode)
    proposal = service.propose(**propose_kwargs())
    assert isinstance(proposal, ActionProposal)
    assert proposal.proposal_id == "proposal-fixed"
    assert proposal.proposed_at == NOW
    assert proposal.config_digest == snapshot_digest(CONFIG)
    stored = store.read("run-001").records
    assert [row.kind for row in stored] == ["action_proposal"]
    assert stored[0].value == proposal


def test_a_repeated_proposal_does_not_duplicate_the_history(tmp_path):
    service, store = a_service(tmp_path)
    first = service.propose(**propose_kwargs())
    second = service.propose(**propose_kwargs())
    assert first == second
    assert [row.kind for row in store.read("run-001").records] == ["action_proposal"]


def test_only_a_registered_adapter_can_be_observed_or_proposed_through(tmp_path):
    service, store = a_service(tmp_path)
    with pytest.raises(AdapterContractError, match="not registered"):
        service.observe(
            run_id="run-001", adapter_id="ghost", instance_id="claude-dev")
    with pytest.raises(AdapterContractError, match="not registered"):
        service.propose(**propose_kwargs(adapter_id="ghost"))
    assert store.read("run-001").records == ()


def test_a_capability_outside_the_manifest_is_refused_before_the_adapter_is_touched(tmp_path):
    adapter = FakeAdapter(capabilities=("observe",))
    service, store = a_service(tmp_path, adapters=[adapter])
    with pytest.raises(UnsupportedCapability, match="dispatch"):
        service.propose(**propose_kwargs(capability="dispatch"))
    # The refusal read the registered manifest, not the adapter: no seam ran.
    assert adapter.observations == 0
    assert adapter.preparations == 0
    assert store.read("run-001").records == ()


def test_propose_never_prepares_the_action(tmp_path):
    adapter = FakeAdapter()
    service, _ = a_service(tmp_path, adapters=[adapter])
    service.propose(**propose_kwargs())
    # The boundary is after a proposal is confirmed; the service stops short of it.
    assert adapter.preparations == 0


def test_no_public_service_method_ever_drives_a_side_effecting_adapter_seam(tmp_path):
    """Behavioral closure for the execution ban: an adapter that records every
    side-effecting seam it is asked to run -- execute, verify, and via __getattr__
    anything reached under any other name -- stays untouched when the whole public
    surface of the service runs over the entire capability set.
    """
    calls: list[str] = []
    adapter = RecordingAdapter(calls)
    store = a_store(tmp_path, mode="policy")
    registry = AdapterRegistry([adapter])
    service = CommandService(store, registry, clock=fixed_clock(), ids=fixed_ids())

    for index, capability in enumerate(sorted(CAPABILITIES)):
        service.observe(
            run_id="run-001", adapter_id="claude-code",
            instance_id="claude-dev", observation_id=f"observation-{index}")
        service.propose(**propose_kwargs(
            capability=capability, proposal_id=f"proposal-{index}"))
    assert calls == []


def test_the_service_source_opens_no_execution_or_subprocess_door():
    """A cheap second signal beside the behavioral guard: the module imports only
    value modules and never names an execute, prepare, subprocess, or system call.
    """
    source = Path(service_module.__file__).resolve()
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level >= 1:
                continue  # a sibling module inside the command package
            imported.add(node.module or "")
    assert imported <= ALLOWED_SERVICE_IMPORTS, sorted(imported - ALLOWED_SERVICE_IMPORTS)
    attribute_calls = {
        node.func.attr for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not attribute_calls & {
        "execute", "prepare", "run", "Popen", "system", "which", "import_module"}
    name_calls = {
        node.func.id for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "__import__" not in name_calls and "eval" not in name_calls


def test_a_missing_run_is_never_dressed_up_as_a_successful_observation(tmp_path):
    service, _ = a_service(tmp_path)
    with pytest.raises(Exception, match="run 'run-404' does not exist"):
        service.observe(
            run_id="run-404", adapter_id="claude-code", instance_id="claude-dev")


def test_an_adapter_that_reports_a_foreign_identity_yields_no_observation(tmp_path):
    adapter = FakeAdapter()
    service, store = a_service(tmp_path, adapters=[adapter])
    adapter.observe = lambda instance_id, run_id: __import__(
        "conductor.command.adapters.base", fromlist=["AdapterObservation"]
    ).AdapterObservation(
        adapter_id="somebody-else", instance_id=instance_id, run_id=run_id,
        observed_at=NOW, health="ready", available_capabilities=())
    with pytest.raises(AdapterContractError, match="returned identity"):
        service.observe(
            run_id="run-001", adapter_id="claude-code", instance_id="claude-dev")
    assert store.read("run-001").records == ()


def test_the_ids_and_clock_are_injected_not_read_from_a_hidden_source(tmp_path):
    seen: list[str] = []

    def ids(purpose):
        seen.append(purpose)
        return f"{purpose}-inj"

    store = a_store(tmp_path, mode="propose")
    service = CommandService(
        store, AdapterRegistry([FakeAdapter()]), clock=lambda: NOW, ids=ids)
    observation = service.observe(
        run_id="run-001", adapter_id="claude-code", instance_id="claude-dev")
    proposal = service.propose(**propose_kwargs())
    assert observation.observation_id == "observation-inj"
    assert proposal.proposal_id == "proposal-inj"
    assert proposal.proposed_at == NOW
    assert seen == ["observation", "proposal"]
