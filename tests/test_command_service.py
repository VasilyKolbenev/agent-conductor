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
from conductor.command.adapters.process import ProcessAdapter, ProcessRunner
from conductor.command.adapters.base import CAPABILITIES, UnsupportedCapability
from conductor.command.contracts import (
    ActionProposal,
    ControlMode,
    ObservationRecord,
    frozen_config_bindings,
)
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


def test_observe_discards_untrusted_adapter_detail_from_return_and_journal(tmp_path):
    secret = "APIKEY_SECRET_IN_OBSERVATION_DETAIL"
    adapter = FakeAdapter()
    adapter.observe = lambda instance_id, run_id: __import__(
        "conductor.command.adapters.base", fromlist=["AdapterObservation"]
    ).AdapterObservation(
        adapter_id="claude-code", instance_id=instance_id, run_id=run_id,
        observed_at=NOW, health="ready", available_capabilities=("observe",),
        detail=secret)
    service, store = a_service(tmp_path, adapters=[adapter])
    record = service.observe(run_id="run-001", instance_id="claude-dev")
    journal = store.run_path("run-001").joinpath("records.jsonl").read_bytes()
    assert record.detail == ""
    assert secret not in repr(record)
    assert secret.encode() not in journal


def test_observe_snapshots_stateful_adapter_claims_once_and_persists_bound_facts(tmp_path):
    secret = "APIKEY_SECRET_IN_SHIFTING_OBSERVATION"

    class ShiftingObservation(__import__(
            "conductor.command.adapters.base",
            fromlist=["AdapterObservation"]).AdapterObservation):
        def __getattribute__(self, name):
            if name in {
                    "adapter_id", "instance_id", "run_id",
                    "available_capabilities", "detail"}:
                armed = object.__getattribute__(self, "__dict__").get("_armed", False)
                if armed:
                    reads = object.__getattribute__(self, "__dict__").setdefault(
                        "_reads", {})
                    count = reads.get(name, 0)
                    reads[name] = count + 1
                    if count:
                        return {
                            "adapter_id": "foreign-adapter",
                            "instance_id": "foreign-instance",
                            "run_id": "foreign-run",
                            "available_capabilities": ("stop",),
                            "detail": secret,
                        }[name]
            return super().__getattribute__(name)

    raw = ShiftingObservation(
        adapter_id="claude-code", instance_id="claude-dev", run_id="run-001",
        observed_at=NOW, health="ready", available_capabilities=("observe",),
        detail=secret)
    object.__setattr__(raw, "_armed", True)
    adapter = FakeAdapter()
    adapter.observe = lambda instance_id, run_id: raw
    service, store = a_service(tmp_path, adapters=[adapter])
    record = service.observe(run_id="run-001", instance_id="claude-dev")
    journal = store.run_path("run-001").joinpath("records.jsonl").read_bytes()
    assert (record.adapter_id, record.instance_id, record.run_id) == (
        "claude-code", "claude-dev", "run-001")
    assert record.health == "ready"
    assert record.available_capabilities == ("observe",)
    assert "stop" not in record.available_capabilities
    assert secret not in repr(record) and secret.encode() not in journal


@pytest.mark.parametrize("secret", [
    "APIKEY_SECRET_IN_OBSERVE_EXCEPTION_CLASS",
    "APIKEY_SECRET_IN_OBSERVE_EXCEPTION_MESSAGE",
])
def test_observe_failure_exposes_only_runtime_owned_wording_and_appends_nothing(
        tmp_path, secret):
    adapter = FakeAdapter()
    exception_type = type(
        "APIKEY_SECRET_IN_OBSERVE_EXCEPTION_CLASS", (RuntimeError,), {})

    def fail(instance_id, run_id):
        raise exception_type("APIKEY_SECRET_IN_OBSERVE_EXCEPTION_MESSAGE")

    adapter.observe = fail
    service, store = a_service(tmp_path, adapters=[adapter])
    journal = store.run_path("run-001").joinpath("records.jsonl")
    before = journal.read_bytes()
    with pytest.raises(ServiceError) as caught:
        service.observe(run_id="run-001", instance_id="claude-dev")
    assert str(caught.value) == "adapter observe failed"
    assert secret not in str(caught.value)
    assert journal.read_bytes() == before
    assert secret.encode() not in journal.read_bytes()


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


def test_an_instance_bound_to_an_unregistered_adapter_cannot_be_reached(tmp_path):
    # The caller no longer names the adapter; the frozen config binds it. CONFIG
    # binds 'codex-review' to the 'codex' adapter, which is absent from this
    # registry, so the instance cannot be observed or proposed through at all --
    # and neither door writes a record while refusing.
    service, store = a_service(tmp_path)  # registry holds only 'claude-code'
    with pytest.raises(ServiceError, match="adapter observe failed"):
        service.observe(run_id="run-001", instance_id="codex-review")
    with pytest.raises(AdapterContractError, match="not registered"):
        service.propose(**propose_kwargs(
            instance_id="codex-review", adapter_id=None, capability="observe"))
    assert store.read("run-001").records == ()


def test_a_capability_outside_the_manifest_is_refused_before_the_adapter_is_touched(tmp_path):
    adapter = FakeAdapter(capabilities=("observe",))
    adapter.validate_arguments = lambda *args: (_ for _ in ()).throw(
        AssertionError("unsupported capability touched mutable adapter validation"))
    service, store = a_service(tmp_path, adapters=[adapter])
    with pytest.raises(UnsupportedCapability, match="dispatch"):
        service.propose(**propose_kwargs(capability="dispatch"))
    # The refusal read the registered manifest, not the adapter: no seam ran.
    assert adapter.observations == 0
    assert adapter.preparations == 0
    assert store.read("run-001").records == ()


def test_process_dispatch_rejects_literal_env_before_proposal_or_spawn(tmp_path):
    secret = "APIKEY-proposal-must-not-persist"
    config = {
        "cycle": {"id": "orbit-001", "phases": ["dispatch"]},
        "instances": [{"id": "worker", "adapter": "owned-process"}],
    }
    store = RunStore(tmp_path)
    store.create_run(
        a_run(mode="propose", config_digest=snapshot_digest(config)), config)
    (tmp_path / "work").mkdir()
    runner = ProcessRunner(tmp_path, environ={})
    adapter = ProcessAdapter(
        "owned-process", runner, clock=fixed_clock(), ids=fixed_ids())
    subject = CommandService(
        store, AdapterRegistry([adapter]), clock=fixed_clock(), ids=fixed_ids())
    before = store.run_path("run-001").joinpath("records.jsonl").read_bytes()
    with pytest.raises(ServiceError, match="literal env values"):
        subject.propose(**propose_kwargs(
            adapter_id="owned-process", instance_id="worker",
            arguments={
                "argv": ["python", "tool.py"], "cwd": "work",
                "env": {"API_TOKEN": secret},
            }))
    after = store.run_path("run-001").joinpath("records.jsonl").read_bytes()
    assert after == before and secret.encode() not in after
    assert runner.active_tokens() == ()


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
    with pytest.raises(ServiceError, match="adapter observe failed"):
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


# --- MAJOR-1: the instance -> adapter binding is derived from the frozen config,
# never trusted from the caller. CONFIG binds 'claude-dev' to 'claude-code' and
# 'codex-review' to 'codex'. Each guard below holds that RELATION -- the adapter a
# door touches or stores equals the one the frozen config declares for the
# instance -- with its two sides drawn from different code.

def _two_adapter_service(tmp_path, *, mode="propose"):
    """A service whose registry holds both adapters CONFIG binds instances to."""
    claude = FakeAdapter("claude-code", ("observe", "dispatch"))
    codex = FakeAdapter("codex", ("observe",))
    return a_service(tmp_path, mode=mode, adapters=[claude, codex])


def test_observe_refuses_an_unknown_instance_before_the_adapter_is_touched(tmp_path):
    tripwire = FakeAdapter()

    def boom(instance_id, run_id):
        raise AssertionError("an unknown instance must never reach the adapter")

    tripwire.observe = boom
    service, store = a_service(tmp_path, mode="observe", adapters=[tripwire])
    before = len(store.read("run-001").records)
    with pytest.raises(ServiceError, match="ghost-instance"):
        service.observe(
            run_id="run-001", adapter_id="claude-code", instance_id="ghost-instance")
    assert len(store.read("run-001").records) == before  # the journal did not grow
    assert tripwire.observations == 0


def test_propose_refuses_an_unknown_instance_before_any_record_is_written(tmp_path):
    service, store = a_service(tmp_path)
    before = len(store.read("run-001").records)
    with pytest.raises(ServiceError, match="ghost-instance"):
        service.propose(**propose_kwargs(instance_id="ghost-instance"))
    assert len(store.read("run-001").records) == before


def test_an_adapter_that_is_not_the_instances_binding_is_refused_on_both_doors(tmp_path):
    service, store = _two_adapter_service(tmp_path)
    # 'claude-dev' is bound to 'claude-code'; naming 'codex' is a mismatch, refused
    # before the adapter is touched and before anything is written.
    with pytest.raises(ServiceError, match="claude-dev"):
        service.observe(
            run_id="run-001", adapter_id="codex", instance_id="claude-dev")
    with pytest.raises(ServiceError, match="claude-dev"):
        service.propose(**propose_kwargs(
            adapter_id="codex", instance_id="claude-dev", capability="observe"))
    assert store.read("run-001").records == ()


def test_a_capability_cannot_be_laundered_through_a_foreign_adapters_manifest(tmp_path):
    service, store = _two_adapter_service(tmp_path)
    # 'codex-review' is bound to 'codex', which does not declare 'dispatch'. The
    # defect let a caller name the foreign 'claude-code' (which does) and launder
    # the capability past the check; the mismatch is now refused first.
    with pytest.raises(ServiceError, match="codex-review"):
        service.propose(**propose_kwargs(
            instance_id="codex-review", adapter_id="claude-code", capability="dispatch"))
    # And with the bound adapter named, the capability is judged only by ITS
    # manifest, so 'dispatch' is still absent and refused.
    with pytest.raises(UnsupportedCapability, match="dispatch"):
        service.propose(**propose_kwargs(
            instance_id="codex-review", adapter_id="codex", capability="dispatch"))
    assert store.read("run-001").records == ()


def test_a_capability_the_bound_adapter_declares_stays_allowed(tmp_path):
    service, store = _two_adapter_service(tmp_path)
    proposal = service.propose(**propose_kwargs(
        instance_id="claude-dev", adapter_id="claude-code", capability="dispatch"))
    assert proposal.instance_id == "claude-dev"
    assert proposal.capability == "dispatch"
    assert [row.kind for row in store.read("run-001").records] == ["action_proposal"]


def test_the_instance_adapter_relation_survives_replay_by_a_new_run_store(tmp_path):
    service, _ = _two_adapter_service(tmp_path)
    service.observe(run_id="run-001", instance_id="claude-dev")
    proposal = service.propose(**propose_kwargs(
        instance_id="claude-dev", capability="dispatch"))

    # A fresh store process replays the durable bytes with no adapter in hand.
    replayed = RunStore(tmp_path).read("run-001")
    stored = {row.kind: row.value for row in replayed.records}
    observation = stored["adapter_observation"]

    # Declaration side: parsed straight from the frozen config by this test.
    declared = {entry["id"]: entry["adapter"] for entry in replayed.config["instances"]}
    # The observation carries its adapter durably; it is the one the config declares.
    assert observation.adapter_id == declared[observation.instance_id] == "claude-code"
    # The proposal carries no adapter field, yet production derives it unambiguously
    # and verifiably from the pinned frozen config -- and it agrees with the
    # declaration this test read independently.
    derived = frozen_config_bindings(replayed.config)[proposal.instance_id]
    assert derived == declared[proposal.instance_id] == "claude-code"
