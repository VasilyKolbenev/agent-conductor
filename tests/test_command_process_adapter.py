"""The thin process-backed adapter: the four CMD-3 seams over the owned runner.

The adapter is deliberately small and honest. Its manifest declares only the two
controls it holds -- observe and dispatch -- and every other control is absent,
never present-but-empty. `observe` reports `unknown` without probing the
machine; `execute` runs one structured command through the runner and maps its
outcome onto the receipt vocabulary, where a timeout is a distinct failure and
never a success; `verify` returns `unavailable`, because watching a process exit
is not evidence the requested effect occurred. The whole prepare -> execute ->
verify chain is exercised over a deterministic fake executable, which is the
seam lane A's Confirm gate wires after lanes A and B merge.
"""
from __future__ import annotations

import pytest

from conductor.command.adapters import AdapterRegistry
from conductor.command.adapters.base import (
    AdapterContractError,
    UnsupportedCapability,
)
from conductor.command.adapters.process import (
    OwnershipError,
    ProcessAdapter,
    ProcessRunner,
)
from conductor.command.contracts import ActionRequest, canonical_json

from tests._fakeproc import EMIT_STDOUT, EXIT, SLEEP, fake_argv

NOW = "2026-08-11T10:00:00Z"
DIGEST = "sha256:" + "0" * 64


def _ids():
    counters: dict[str, int] = {}

    def mint(purpose: str) -> str:
        counters[purpose] = counters.get(purpose, 0) + 1
        return f"{purpose}-{counters[purpose]}"

    return mint


@pytest.fixture
def adapters(tmp_path):
    (tmp_path / "project" / "work").mkdir(parents=True)
    built = []

    def make():
        runner = ProcessRunner(tmp_path / "project")
        adapter = ProcessAdapter("owned-process", runner, clock=lambda: NOW, ids=_ids())
        built.append(runner)
        return adapter

    yield make
    for runner in built:
        for token in runner.active_tokens():
            try:
                runner.stop(token)
            except OwnershipError:
                pass


def _request(*, capability="dispatch", arguments=None, timeout=10):
    return ActionRequest(
        action_id="act-1", run_id="run-1", attempt_id="att-1", instance_id="inst-1",
        capability=capability, arguments=arguments if arguments is not None else _args(),
        scope=("work",), requested_by="tester", requested_at=NOW,
        idempotency_key="idem-1", timeout_seconds=timeout, preview_digest=DIGEST,
        mode="confirm")


def _args(env_knobs=None, argv_extra=()):
    return {"argv": fake_argv(*argv_extra), "cwd": "work",
            "env": dict(env_knobs or {}), "output_limit": 65536}


# --- manifest honesty: only the controls it holds ---


def test_the_manifest_declares_only_observe_and_dispatch(adapters):
    manifest = adapters().manifest
    assert set(manifest.capabilities) == {"observe", "dispatch"}
    for absent in ("pause", "resume", "stop", "retry", "switch", "review",
                   "evidence", "notify", "message"):
        assert absent not in manifest.capabilities


def test_the_adapter_registers_and_exposes_its_controls_through_the_sdk(adapters):
    adapter = adapters()
    registry = AdapterRegistry([adapter])
    assert set(registry.controls("owned-process")) == {"observe", "dispatch"}
    assert any(m.adapter_id == "owned-process" for m in registry.manifests())


def test_observe_reports_unknown_and_claims_no_available_capabilities(adapters):
    adapter = adapters()
    observation = adapter.observe("inst-1", "run-1")
    assert observation.health == "unknown"
    assert observation.available_capabilities == ()
    # the SDK accepts it: identity matches and no undeclared capability is claimed.
    registry = AdapterRegistry([adapter])
    assert registry.observe("owned-process", "inst-1", "run-1").health == "unknown"


# --- prepare binds one unchanged request; refuses what it cannot do ---


def test_prepare_builds_a_prepared_action_bound_to_the_unchanged_request(adapters):
    adapter = adapters()
    request = _request()
    prepared = adapter.prepare(request)
    assert prepared.adapter_id == "owned-process"
    assert canonical_json(prepared.request) == canonical_json(request)
    assert tuple(prepared.adapter_payload["argv"]) == tuple(fake_argv())
    assert prepared.adapter_payload["cwd"] == "work"
    # and the SDK's own prepare confirms the request survived untouched.
    assert AdapterRegistry([adapter]).prepare("owned-process", request) == prepared


def test_prepare_refuses_a_capability_the_adapter_does_not_hold(adapters):
    with pytest.raises(UnsupportedCapability, match="only prepares 'dispatch'"):
        adapters().prepare(_request(capability="pause"))


def test_prepare_refuses_dispatch_arguments_without_a_command(adapters):
    with pytest.raises(AdapterContractError, match="not a valid command"):
        adapters().prepare(_request(arguments={"cwd": "work"}))


# --- execute maps the process outcome honestly ---


def test_execute_maps_a_zero_exit_to_succeeded(adapters):
    adapter = adapters()
    receipt = adapter.execute(adapter.prepare(_request(
        arguments=_args({EMIT_STDOUT: "done"}))))
    assert receipt.outcome == "succeeded"
    assert receipt.exit_code == 0
    assert receipt.action_id == "act-1" and receipt.run_id == "run-1"


def test_execute_maps_a_nonzero_exit_to_failed(adapters):
    adapter = adapters()
    receipt = adapter.execute(adapter.prepare(_request(arguments=_args({EXIT: "3"}))))
    assert receipt.outcome == "failed"
    assert receipt.exit_code == 3


def test_execute_maps_a_timeout_to_failed_never_succeeded(adapters):
    """The runner's distinct timeout fact reaches the receipt as failure, not success."""
    adapter = adapters()
    receipt = adapter.execute(adapter.prepare(_request(
        arguments=_args({SLEEP: "5"}), timeout=1)))
    assert receipt.outcome == "failed"
    assert receipt.outcome != "succeeded"
    assert "timeout" in (receipt.detail or "")
    assert receipt.exit_code is None


def test_verify_reports_unavailable_never_verified(adapters):
    adapter = adapters()
    request = _request()
    receipt = adapter.execute(adapter.prepare(request))
    verification = adapter.verify(request, receipt)
    assert verification.state == "unavailable"
    assert verification.state != "verified"
    assert verification.evidence_refs == ()


def test_a_dispatch_flows_prepare_execute_verify_over_a_fake_executable(adapters):
    """The seam the Day-1 cross-lane gate wires: one command, end to end, honest."""
    adapter = adapters()
    request = _request(arguments=_args({EMIT_STDOUT: "ok"}))
    prepared = adapter.prepare(request)
    receipt = adapter.execute(prepared)
    verification = adapter.verify(request, receipt)
    assert receipt.outcome == "succeeded"
    assert receipt.action_id == request.action_id
    assert verification.state == "unavailable"  # honest: no independent check held
