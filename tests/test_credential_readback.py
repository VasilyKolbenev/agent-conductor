"""Unreadable post-spawn credentials cannot authorize publication or a verdict."""
import json
import os

import pytest

from conductor.command.runtime import AttemptState
from tests import _fakeclaude, _fakecodex
from tests.test_command_claude_transport import a_harness
from tests.test_command_codex_transport import a_harness as codex_harness
from tests.test_independent_checker_transport import CHECKER, RUN, _run_state
from tests.relay_roads import CLAUDE, CODEX, Site, digests
from tests._boundary_assumed import boundary_assumed  # noqa: F401

pytestmark = pytest.mark.usefixtures("boundary_assumed")
UNKNOWN = "NEW-unobserved-credential-0123456789"
DOER_REFUSAL = "the doer's credential read-back could not be established; nothing was published"
CHECKER_REFUSAL = (
    "the checker's credential read-back could not be established; no verdict was accepted")


def home(tmp_path, name, leaf):
    folder = tmp_path / name
    folder.mkdir()
    (folder / leaf).write_text(json.dumps({"token": "INITIAL-known-credential-0123"}))
    return folder


def case(tmp_path, *, corrupt_doer=False, verdict="accept"):
    login = home(tmp_path, "doer-login", ".credentials.json")
    doer, root, log = a_harness(tmp_path / "doer", auth="subscription", auth_home=str(login),
        **{_fakeclaude.WRITE_FILE: "result.txt:" + UNKNOWN,
           **({_fakeclaude.HOME_FILE: ".credentials.json:{broken"} if corrupt_doer else {})})
    checker_login = home(tmp_path, "checker-login", "auth.json")
    relative = os.path.relpath(checker_login / "auth.json", root / "work/work-001")
    knobs = {_fakecodex.EMIT_VERDICT: "enabled-verdict-" + verdict}
    if not corrupt_doer:
        knobs[_fakecodex.VERDICT_WRITE_FILE] = relative + ":{broken"
    checker, _, check_log = codex_harness(tmp_path / "checker", root=root,
        auth="subscription", auth_home=str(checker_login), **knobs)
    runtime, authorization, store = _run_state(root, doer, checker, True, False,
                                              None, None, None)
    return runtime, authorization, store, doer, checker, log, check_log, root


def test_unreadable_doer_readback_blocks_unknown_result_before_checker(tmp_path):
    runtime, authorization, store, doer, checker, log, check_log, root = case(
        tmp_path, corrupt_doer=True)
    attempt = runtime.execute(authorization)
    assert (root / "work/work-001/result.txt").read_text() == UNKNOWN
    assert attempt.state is AttemptState.VERIFICATION_FAILED
    assert attempt.receipt.detail == DOER_REFUSAL
    assert len(_fakeclaude.prompt_spawns(log)) == 1
    assert _fakecodex.task_spawns(check_log) == []
    assert checker.verification_started(attempt.request) is False
    assert not [r for r in store.read(RUN).records if r.kind in {"artifact", "evidence"}]
    assert doer._attempts == {} and doer._login_history == {} and doer._login_seen == ()


@pytest.mark.parametrize("verdict", ["accept", "reject"])
def test_unreadable_checker_readback_blocks_accept_and_reject(tmp_path, verdict):
    runtime, authorization, store, doer, checker, _, check_log, _ = case(
        tmp_path, verdict=verdict)
    attempt = runtime.execute(authorization)
    assert len(_fakecodex.task_spawns(check_log)) == 1
    assert attempt.state is AttemptState.VERIFICATION_FAILED
    assert attempt.receipt.detail == CHECKER_REFUSAL
    assert not [r for r in store.read(RUN).records
                if r.kind in {"evidence", "correction_feedback"}]
    assert UNKNOWN.encode() not in (store.run_path(RUN) / "records.jsonl").read_bytes()
    assert doer._attempts == {} and doer._login_history == {}
    assert checker._login_seen == () and checker._retained == 0


@pytest.mark.parametrize("corrupt", [False, True])
def test_actual_relay_readback_and_account_proof_reach_the_runtime(tmp_path, corrupt):
    knobs = {_fakeclaude.WRITE_FILE: "result.txt:" + UNKNOWN}
    if corrupt:
        knobs[_fakeclaude.HOME_FILE] = ".credentials.json:{broken"
    doer = Site(tmp_path, CLAUDE, **knobs)
    checker = Site(tmp_path, CODEX, root=doer.root, name="checker",
                   **{_fakecodex.EMIT_VERDICT: "enabled-verdict-accept"})
    originals = digests(doer.login), digests(checker.login)
    with doer.owned():
        runtime, authorization, store = _run_state(doer.root, doer.adapter, checker.adapter,
                                                  True, False, None, None, None)
        attempt = runtime.execute(authorization)
    expected = AttemptState.VERIFICATION_FAILED if corrupt else AttemptState.SUCCEEDED
    assert attempt.state is expected, attempt.receipt.detail
    if corrupt:
        assert attempt.receipt.detail == DOER_REFUSAL
        assert checker.tasks() == []
    proofs = [r.value for r in store.read(RUN).records
              if r.kind == "evidence" and r.value.kind == "subscription_account_v1"]
    assert len(proofs) == (1 if corrupt else 2)
    roles = {row.extra["binding"]["role"]: row for row in proofs}
    assert roles["doer"].extra["proof"]["vendor"] == "anthropic"
    assert roles["doer"].extra["binding"]["actor_instance_id"] == "claude-dev"
    if not corrupt:
        assert roles["checker"].extra["proof"]["vendor"] == "openai"
        assert roles["checker"].extra["binding"]["actor_instance_id"] == CHECKER
    assert all(row.extra["proof"]["status"] == "local_match"
               and row.verification == "unverified" for row in proofs)
    raw = (store.run_path(RUN) / "records.jsonl").read_bytes()
    assert b"00000000-0000-4000-8000-00000000000a" not in raw
    assert b"fake-codex-account-0001" not in raw and UNKNOWN.encode() not in raw
    assert originals == (digests(doer.login), digests(checker.login))
    assert doer.leftovers() == checker.leftovers() == []
    assert doer.lease_is_free() and checker.lease_is_free()


def test_a_sibling_road_cannot_erase_the_frozen_relay_readback_failure(tmp_path):
    from dataclasses import replace
    from conductor.command.adapters.headless_values import attempt_relation

    site = Site(tmp_path, CLAUDE, **{_fakeclaude.WRITE_FILE: "result.txt:" + UNKNOWN,
                                   _fakeclaude.HOME_FILE: ".credentials.json:{broken"})
    first = site.request()
    first_result = site.run(first)
    snapshot = site.adapter._attempts[attempt_relation(first)]
    assert snapshot.credential_readback_untrusted is True
    # Only the fake CLI's input changes. The adapter and credential reader remain real.
    site.runner._environ.pop(_fakeclaude.HOME_FILE)
    site.runner._environ[_fakeclaude.WRITE_FILE] = "result.txt:healthy second result"
    second = replace(first, action_id="second-action", attempt_id="second-attempt",
                     idempotency_key="second-dispatch")
    site.run(second)
    assert site.adapter._attempts[attempt_relation(second)].credential_readback_untrusted is False
    assert site.adapter.publish(first, first_result).refusal == "credential_readback_untrusted"
    assert site.adapter._attempts[attempt_relation(first)] is snapshot
    site.adapter.release(first)
    site.adapter.release(second)
    assert site.adapter._attempts == {} and site.adapter._login_history == {}
    assert site.adapter._login_seen == () and site.leftovers() == [] and site.lease_is_free()


@pytest.mark.parametrize("verdict", ["accept", "reject"])
def test_actual_checker_relay_readback_refuses_both_verdicts(tmp_path, verdict):
    from pathlib import Path

    doer = Site(tmp_path, CLAUDE, **{_fakeclaude.WRITE_FILE: "result.txt:checked result"})
    checker = Site(tmp_path, CODEX, root=doer.root, name="checker",
                   **{_fakecodex.EMIT_VERDICT: "enabled-verdict-" + verdict})
    seen = []
    checker.runner.hooks["run"] = lambda spec: seen.append(Path(spec.env["CODEX_HOME"]))

    def corrupt(*ignored):
        (seen[-1] / "auth.json").write_text("{broken", encoding="utf-8")

    checker.runner.hooks["exit"] = corrupt
    before = digests(checker.login)
    with doer.owned():
        runtime, authorization, store = _run_state(doer.root, doer.adapter, checker.adapter,
                                                  True, False, None, None, None)
        attempt = runtime.execute(authorization)
    assert seen and attempt.state is AttemptState.VERIFICATION_FAILED
    assert attempt.receipt.detail == CHECKER_REFUSAL
    assert len(checker.tasks()) == 1 and not seen[0].exists()
    assert digests(checker.login) == before and checker.leftovers() == []
    assert checker.lease_is_free() and checker.adapter._login_seen == ()
    records = store.read(RUN).records
    assert not [row for row in records if row.kind == "correction_feedback"]
    evidence = [row.value for row in records if row.kind == "evidence"]
    assert len(evidence) == 2
    assert all(row.kind == "subscription_account_v1" and row.verification == "unverified"
               for row in evidence)


def test_optional_absence_is_allowed_but_optional_stat_failure_is_not(tmp_path, monkeypatch):
    from pathlib import Path
    from conductor.command.adapters.login_home import credential_readback_trusted

    login = home(tmp_path, "login", "auth.json")
    names = ("auth.json", ".credentials.json")
    assert credential_readback_trusted(str(login), names, ("auth.json",)) is True
    original = Path.lstat

    def unreadable(path):
        if path == login / ".credentials.json":
            raise PermissionError("synthetic optional credential stat refusal")
        return original(path)

    monkeypatch.setattr(Path, "lstat", unreadable)
    assert credential_readback_trusted(str(login), names, ("auth.json",)) is False


@pytest.mark.parametrize("relay", [False, True])
@pytest.mark.parametrize("corrupt", [False, True])
def test_ordinary_confirm_verification_also_holds_readback(tmp_path, corrupt, relay):
    from contextlib import nullcontext
    from conductor.command.adapters import AdapterRegistry
    from conductor.command.contracts import ActionProposal, RunEnvelope
    from conductor.command.run_store import RunStore, snapshot_digest
    from conductor.command.runtime import ControlRuntime
    from tests.test_command_claude_transport import NOW, _Ids, a_request
    from tests.test_command_runtime_authorize import a_budget, a_confirmation

    knobs = {_fakeclaude.WRITE_FILE: "result.txt:" + UNKNOWN}
    if corrupt:
        knobs[_fakeclaude.HOME_FILE] = ".credentials.json:{broken"
    if relay:
        site = Site(tmp_path, CLAUDE, **knobs)
        doer, root, owner = site.adapter, site.root, site.owned()
    else:
        login = home(tmp_path, "login", ".credentials.json")
        doer, root, _ = a_harness(tmp_path / "ordinary", auth="subscription",
                                  auth_home=str(login), **knobs)
        owner = nullcontext()
    config = {"instances": [{"id": "doer", "adapter": "claude-code"}]}
    with owner:
        store = RunStore(root)
        store.create_run(RunEnvelope("ordinary", "cycle", NOW, snapshot_digest(config),
                                      mode="confirm"), config)
        proposal = ActionProposal("ordinary-proposal", "ordinary", "ordinary-attempt", "doer",
            "dispatch", a_request().arguments, ("work",), "owner", NOW, 60, "cycle",
            snapshot_digest(config), input_binding="proposal-v1")
        store.append(proposal)
        runtime = ControlRuntime(store, AdapterRegistry([doer]), clock=lambda: NOW, ids=_Ids())
        attempt = runtime.execute(runtime.authorize(
            a_confirmation(proposal, confirmed_at=NOW), budget=a_budget()))
    expected = AttemptState.VERIFICATION_FAILED if corrupt else AttemptState.SUCCEEDED
    assert attempt.state is expected, attempt.receipt.detail
    verified = [row for row in store.read("ordinary").records
                if row.kind == "evidence" and row.value.verification == "verified"]
    assert len(verified) == (0 if corrupt else 1)
    accounts = [row.value for row in store.read("ordinary").records
                if row.kind == "evidence" and row.value.kind == "subscription_account_v1"]
    assert len(accounts) == (1 if relay else 0)
    assert all(row.verification == "unverified" for row in accounts)
    assert doer._attempts == {} and doer._login_history == {}
