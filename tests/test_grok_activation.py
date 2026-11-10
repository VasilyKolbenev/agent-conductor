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
EXPECTED_ARGV = ["--no-auto-update", "--output-format", "json",
                 "--allow", "Read", "--allow", "Grep", "--allow", "Glob",
                 "--deny", "Edit", "--deny", "Bash", "--deny", "WebFetch",
                 "--deny", "WebSearch", "--deny", "MCPTool", "--prompt-file"]


def _site(tmp_path, auth, case="enabled-fixed-review"):
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
        FAKEGROK_REVIEW=case)
    runner = confined(adapter, tmp_path / "scratch", auth_homes=(login,))
    return adapter, root, log, login, data, runner


def _confirmed_review(adapter, root, *, run_id="run-grok", diagnostic=False):
    config = {"cycle": {"id": "grok-review", "phases": ["diagnose"]},
              "instances": [{"id": "reviewer", "adapter": "grok-build"}]}
    arguments = {"work_item_id": "work-001", "target_artifact_refs": ["candidate"],
                 "result_artifact_ref": "diagnosis", "review_profile": "quality"}
    if diagnostic:
        arguments["grok_diagnostic"] = "session-phase-v1"
    digest = snapshot_digest(config)
    with ownership.acquire_owner(root):
        store = RunStore(root)
        store.create_run(RunEnvelope(run_id=run_id, cycle_id="grok-review", created_at=NOW,
                                    config_digest=digest, mode="confirm"), config)
        store.append(ArtifactDocument(artifact_id="seed-1", artifact_ref="candidate",
            run_id=run_id, created_at=NOW, media_type="text/markdown", content=SEED))
        proposal = ActionProposal(proposal_id="proposal-review", run_id=run_id,
            attempt_id="attempt-review", instance_id="reviewer", capability="review",
            arguments=arguments, scope=("work",), proposed_by="lane", proposed_at=NOW,
            timeout_seconds=60, rationale="diagnose the candidate", config_digest=digest,
            input_binding="proposal-v1")
        store.append(proposal)
        runtime = ControlRuntime(store, AdapterRegistry([adapter]), clock=lambda: NOW, ids=_Ids())
        confirmation = Confirmation(confirmation_id="confirmation-review", run_id=run_id,
            proposal_id=proposal.proposal_id, preview_digest=proposal.preview_digest,
            capability="review", scope=("work",), config_digest=digest,
            confirmed_by="test-owner", confirmed_at=NOW)
        return runtime.execute(runtime.authorize(confirmation, budget=Budget(
            max_actions=1, max_action_seconds=60, max_confirmation_age_seconds=60)))


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
    assert GrokBuildAdapter.profile.output_limit == 557056
    assert GrokBuildAdapter.profile.login_relay is not None
    assert GrokBuildAdapter.profile.login_relay.kind == "g"


@pytest.mark.parametrize("auth,case,reason", [
    ("api_key", "enabled-fixed-review", None),
    ("subscription", "enabled-fixed-review", None),
    ("subscription", "error-auth", "the harness reported that sign-in is required"),
    pytest.param("subscription", "terminal-error:Couldn't start session: sensitive-fixture",
                 "the harness reported an embedded agent startup failure", id="phase-agent-start"),
    pytest.param("subscription", "terminal-error:Couldn't initialize: sensitive-fixture",
                 "the harness reported an agent initialization failure", id="phase-initialize"),
    pytest.param("subscription", "terminal-error:Couldn't create session: permission denied "
                 "sensitive-fixture",
                 "the harness reported a task session opening failure", id="phase-session-open"),
    pytest.param("subscription", "terminal-error:sensitive-fixture says Couldn't initialize: abc",
                 "the harness reported an unclassified service error", id="phase-quoted"),
    pytest.param("subscription", "terminal-error:Couldn't initializeLater: sensitive-fixture",
                 "the harness reported an unclassified service error", id="phase-lookalike"),
    pytest.param("subscription", "terminal-error:Couldn't initialize",
                 "the harness reported a session startup failure", id="phase-bare"),
    pytest.param("subscription", "terminal-error:COULDN'T INITIALIZE:private",
                 "the harness reported a session startup failure", id="phase-imprecise"),
    pytest.param("subscription", "terminal-error:Couldn't initialize: ",
                 "the harness reported a session startup failure", id="phase-empty-detail"),
    pytest.param("subscription", 'terminal-json:{"message":"Couldn\'t initialize: private",'
                 '"usage_is_incomplete":true}',
                 "the harness reported an unclassified service error with incomplete usage data",
                 id="phase-conflicting-usage"),
    pytest.param("subscription", 'terminal-json:{"message":"COULDN\'T INITIALIZE:private",'
                 '"usage_is_incomplete":true}',
                 "the harness reported an unclassified service error with incomplete usage data",
                 id="phase-imprecise-conflict"),
    pytest.param("subscription", 'terminal-json:{"message":"Connection closed unexpectedly",'
                 '"usage":{"total_tokens":2}}',
                 "the harness reported an unclassified service error with recorded token usage",
                 id="phase-channel-conflicting-usage"),
    pytest.param("subscription", "terminal-error:Connection closed unexpectedly.",
                 "the harness reported a connection failure", id="phase-channel-approximate"),
    pytest.param("subscription", "terminal-error:Connection closed unexpectedly",
                 "the harness reported that its local prompt channel closed",
                 id="phase-channel"),
    pytest.param("subscription", "terminal-error:connection refused sensitive-fixture",
                 "the harness reported a connection failure", id="terminal-connection"),
    pytest.param("subscription", "terminal-error:max turns reached",
                 "the harness reported that the turn limit was reached", id="terminal-turn-limit"),
    pytest.param("subscription", "terminal-error:Grok Build is not yet available for this account.",
                 "the harness reported an access refusal", id="terminal-account"),
    pytest.param("subscription", "terminal-error:sensitive-fixture mentions max turns reached",
                 "the harness reported an unclassified service error", id="terminal-unknown"),
    pytest.param("subscription", 'terminal-json:{"usage":{"total_tokens":12}}',
                 "the harness reported an unclassified service error with recorded token usage",
                 id="terminal-usage"),
    pytest.param("subscription", 'terminal-json:{"usage_is_incomplete":true}',
                 "the harness reported an unclassified service error with incomplete usage data",
                 id="terminal-incomplete"),
    pytest.param("subscription", 'terminal-json:{"usage":{"total_tokens":true},"status":403}',
                 "the harness reported an unclassified service error", id="terminal-malformed"),
    ("subscription", "escaped-login", "the review contained sensitive output"),
    ("subscription", "invalid-success", "the review returned an invalid terminal response"),
    ("subscription", "truncated", "the review result exceeded the artifact byte limit"),
])
def test_production_review_reads_the_task_file_and_cleans_its_home(
        tmp_path, monkeypatch, auth, case, reason):
    adapter, root, log, login, original, runner = _site(tmp_path, auth, case)
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
    attempt = _confirmed_review(adapter, root)
    records = RunStore(root).read("run-grok").records

    outputs = [row.value for row in records if row.kind == "artifact"
               and row.value.source_action_id is not None]
    if reason is not None:
        assert not outputs
        (result,) = [row.value for row in records if row.kind == "action_result"]
        assert result.outcome == "failed" and reason in result.detail
        if case.startswith(("terminal-error:", "terminal-json:")):
            assert result.detail == "adapter reported failed: " + reason
            assert result.exit_code == 1 and not result.evidence_refs
        assert not any(word in result.detail for word in ("sensitive-fixture", "fake-access"))
        assert not Path(_fakegrok.prompt_spawns(log)[0]["grok_home"]).exists()
        return
    assert attempt.state is AttemptState.SUCCEEDED, receipts
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


def _diagnostic_run(tmp_path, case):
    adapter, root, log, login, original, runner = _site(tmp_path, "subscription", case)
    attempt = _confirmed_review(adapter, root, diagnostic=True)
    replay = RunStore(root)
    records = replay.read("run-grok").records
    (result,) = [row.value for row in records if row.kind == "action_result"]
    outputs = [row.value for row in records if row.kind == "artifact"
               and row.value.source_action_id is not None]
    children = _fakegrok.prompt_spawns(log)
    assert len(children) == 1, "a confirmed diagnostic review must launch exactly one prompt"
    (child,) = children
    home = Path(child["grok_home"])
    assert child["argv"] == [*EXPECTED_ARGV[:2], "streaming-messages-json", *EXPECTED_ARGV[3:],
                             str(home / "conduct-task.txt")]
    assert [entry.mode for entry in runner.entries] == ["review"]
    assert not home.exists() and (login / "auth.json").read_bytes() == original
    journal = (replay.run_path("run-grok") / "records.jsonl").read_bytes()
    assert b"wire-private" not in journal
    assert b"fake-access-activation-1234" not in journal
    return adapter, root, log, attempt, result, outputs


def test_one_diagnostic_review_persists_all_assistant_text_and_keeps_next_review_default(tmp_path):
    adapter, root, log, attempt, result, outputs = _diagnostic_run(tmp_path, "stream-full")
    assert attempt.state is AttemptState.SUCCEEDED
    assert result.outcome == "succeeded"
    (document,) = outputs
    expected = "  Первая строка.\n\n\tСледующая строка.  \n".encode("utf-8")
    assert document.content.encode("utf-8") == expected
    assert document.source_action_id == result.action_id
    assert document.artifact_ref == "diagnosis" and document.input_artifact_ids == ("seed-1",)

    ordinary = _confirmed_review(adapter, root, run_id="run-ordinary")
    assert ordinary.state is AttemptState.SUCCEEDED
    (ordinary_doc,) = [row.value for row in RunStore(root).read("run-ordinary").records
                       if row.kind == "artifact" and row.value.source_action_id is not None]
    assert ordinary_doc.content == REVIEW + "\n"
    _marked, unmarked = _fakegrok.prompt_spawns(log)
    assert unmarked["argv"][:-1] == EXPECTED_ARGV


@pytest.mark.parametrize("case,reason", [
    ("stream-after-open", "the diagnostic reported an opened session before the error"),
    ("stream-access", "the diagnostic reported an opened session before the error"
                      " | the harness reported an access refusal"),
    ("stream-before-open", "the diagnostic reported no session ID before the error"),
    ("stream-mismatch", "the diagnostic stream did not establish a result"),
    ("stream-no-terminal", "the diagnostic stream did not establish a result"),
    ("stream-oversize", "its output was longer than the capture bound"),
    ("stream-secret", "the review contained sensitive output"),
])
def test_failed_diagnostic_preserves_only_the_fixed_reason(tmp_path, case, reason):
    _, _, _, attempt, result, outputs = _diagnostic_run(tmp_path, case)
    assert attempt.state is AttemptState.FAILED
    assert result.outcome == "failed"
    assert result.detail == "adapter reported failed: " + reason
    assert not outputs and not result.evidence_refs
