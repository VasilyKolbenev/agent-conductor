"""Production Grok review activation, using fake login and real fake children only."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from conductor import ownership, ownership_transition
from conductor.command.adapters import AdapterRegistry
from conductor.command.adapters.grok_build import GrokBuildAdapter
from conductor.command.adapters.harness_profile import boundary_detail
from conductor.command.artifacts import ArtifactDocument
from conductor.command.contracts import ActionProposal, RunEnvelope
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.runtime import AttemptState, Budget, Confirmation, ControlRuntime
from tests import _fakegrok
from tests._fakeboundary import confined
from tests.test_command_grok_transport import NOW, _Ids, a_harness, a_request, run_once

SCOPE = "https://auth.x.ai::b1a00492-073a-47ea-816f-4c329264a828"
REVIEW = "# Diagnosis\nThe fake review read the supplied candidate."
SEED = "Candidate input: task-file-probe-7f62."
EXPECTED_ARGV = ["--no-auto-update", "--output-format", "plain",
                 "--allow", "Read", "--allow", "Grep", "--allow", "Glob",
                 "--deny", "Edit", "--deny", "Bash", "--deny", "WebFetch",
                 "--deny", "WebSearch", "--deny", "MCPTool", "--prompt-file"]


def _site(tmp_path, auth):
    login = tmp_path / "DecemberCommand" / "logins" / "grok-build"
    login.mkdir(parents=True)
    original = {SCOPE: {"auth_mode": "oidc", "key": "fake-access-activation-1234",
                       "refresh_token": "fake-refresh-activation-9876",
                       "user_id": "fake-grok-account-0001", "expires_at": "2026-08-21T18:00:00Z",
                       "oidc_issuer": "https://auth.x.ai",
                       "oidc_client_id": "b1a00492-073a-47ea-816f-4c329264a828"}}
    data = json.dumps(original).encode()
    (login / "auth.json").write_bytes(data)
    root = tmp_path / "root"
    (root / "conductor").mkdir(parents=True)
    ownership_transition.activate(root, legacy_writers_stopped=True)
    adapter, root, log = a_harness(
        tmp_path, root=root, production=True, auth=auth,
        auth_home=str(login) if auth == "subscription" else "",
        FAKEGROK_REVIEW="enabled-fixed-review")
    runner = confined(adapter, tmp_path / "scratch", auth_homes=(login,))
    return adapter, root, log, login, data, runner


@pytest.mark.parametrize("auth", ["api_key", "subscription"])
def test_production_dispatch_is_refused_before_preflight_or_claim(tmp_path, auth):
    adapter, root, log, _login, _data, runner = _site(tmp_path, auth)
    request = a_request()
    with ownership.acquire_owner(root):
        receipt = run_once(adapter, request)
    assert receipt.outcome == "failed"
    assert receipt.detail == boundary_detail("Grok Build")
    assert _fakegrok.spawns(log) == []
    assert runner.entries == []
    assert not adapter._workspace.is_claimed(request.run_id, request.action_id)
    assert not adapter.boundary_provided("dispatch")
    assert not AdapterRegistry([adapter]).verifies_independently("grok-build", "review")


def test_production_grok_declares_review_file_relay_and_no_checker():
    assert GrokBuildAdapter.review_enabled
    assert GrokBuildAdapter.task_modes == ("review",)
    assert GrokBuildAdapter.verify_for is None
    assert GrokBuildAdapter.verification_started is None
    assert GrokBuildAdapter.profile.task_channel == "file"
    assert GrokBuildAdapter.profile.output_limit == 49152
    assert GrokBuildAdapter.profile.login_relay is not None
    assert GrokBuildAdapter.profile.login_relay.kind == "g"


@pytest.mark.parametrize("auth", ["api_key", "subscription"])
def test_production_review_reads_the_task_file_and_cleans_its_home(tmp_path, monkeypatch, auth):
    adapter, root, log, login, original, runner = _site(tmp_path, auth)
    assert "review" in adapter.manifest.capabilities
    held = {}
    receipts = []
    original_execute = adapter.execute

    def execute_and_record(prepared):
        receipt = original_execute(prepared)
        receipts.append(receipt)
        return receipt

    monkeypatch.setattr(adapter, "execute", execute_and_record)

    def inspect_task(spec):
        home = Path(spec.env["GROK_HOME"])
        held.update({path.name: path.read_bytes() for path in home.iterdir() if path.is_file()})

    runner.hooks["run"] = inspect_task
    config = {"cycle": {"id": "grok-review", "phases": ["diagnose"]},
              "instances": [{"id": "reviewer", "adapter": "grok-build"}]}
    digest = snapshot_digest(config)
    with ownership.acquire_owner(root):
        store = RunStore(root)
        store.create_run(RunEnvelope(run_id="run-grok", cycle_id="grok-review", created_at=NOW,
                                    config_digest=digest, mode="confirm"), config)
        store.append(ArtifactDocument(artifact_id="seed-1", artifact_ref="candidate",
            run_id="run-grok", created_at=NOW, media_type="text/markdown", content=SEED))
        proposal = ActionProposal(proposal_id="proposal-review", run_id="run-grok",
            attempt_id="attempt-review", instance_id="reviewer", capability="review",
            arguments={"work_item_id": "work-001", "target_artifact_refs": ["candidate"],
                       "result_artifact_ref": "diagnosis", "review_profile": "quality"},
            scope=("work",), proposed_by="lane", proposed_at=NOW, timeout_seconds=60,
            rationale="diagnose the candidate", config_digest=digest, input_binding="proposal-v1")
        store.append(proposal)
        runtime = ControlRuntime(store, AdapterRegistry([adapter]), clock=lambda: NOW, ids=_Ids())
        confirmation = Confirmation(confirmation_id="confirmation-review", run_id="run-grok",
            proposal_id=proposal.proposal_id, preview_digest=proposal.preview_digest,
            capability="review", scope=("work",), config_digest=digest,
            confirmed_by="test-owner", confirmed_at=NOW)
        attempt = runtime.execute(runtime.authorize(confirmation, budget=Budget(
            max_actions=1, max_action_seconds=60, max_confirmation_age_seconds=60)))
        records = store.read("run-grok").records

    assert attempt.state is AttemptState.SUCCEEDED, receipts
    outputs = [row.value for row in records if row.kind == "artifact"
               and row.value.source_action_id is not None]
    assert len(outputs) == 1 and outputs[0].content == REVIEW + "\n"
    assert outputs[0].input_artifact_ids == ("seed-1",)
    (child,) = _fakegrok.prompt_spawns(log)
    assert child["argv"][:-1] == EXPECTED_ARGV
    home = Path(child["grok_home"])
    assert child["argv"][-1] == str(home / "conduct-task.txt")
    assert SEED not in " ".join(child["argv"])
    task = held["conduct-task.txt"]
    assert SEED.encode() in task
    assert child["task_sha256"] == hashlib.sha256(task).hexdigest()
    assert child["task_size"] == len(task) > len(SEED)
    assert [entry.mode for entry in runner.entries] == ["review"]
    assert not home.exists(), "attempt home and prompt file must be removed"
    assert (login / "auth.json").read_bytes() == original
    assert not child["home_report"]["refresh"]
    if auth == "subscription":
        expected = json.loads(original)
        del expected[SCOPE]["refresh_token"]
        assert json.loads(held["auth.json"]) == expected
        assert child["home_report"]["access"] is True
        assert child["home_report"]["account"] == "fake-grok-account-0001"
        assert child["home_report"]["files"] == ["auth.json", "conduct-task.txt"]
        assert home.name.startswith("g-") and home != login
    else:
        assert child["home_report"]["files"] == ["conduct-task.txt"]
