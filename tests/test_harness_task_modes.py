"""Synthetic review-only transport: early refusal, final spawn guard and checker policy."""
from __future__ import annotations

import pytest

from conductor.command.adapters.claude_code import ClaudeCodeTransport
from conductor.command.adapters.harness_attempt import AttemptLaunch
from conductor.command.adapters.harness_profile import boundary_detail
from conductor.command.execution_boundary import BoundaryUnavailable
from conductor.command.runtime import AttemptState
from tests import _fakeclaude, test_adapter_boundary_roads as review_road
from tests._boundary_assumed import boundary_assumed  # noqa: F401
from tests._fakeboundary import confined, recording
from tests.test_command_claude_transport import a_harness, a_request, run_once


class ReviewOnly(ClaudeCodeTransport):
    task_modes = ("review",)
    serves_checks = False


def _tree(root):
    return {path.relative_to(root).as_posix(): path.read_bytes() if path.is_file() else None
            for path in root.rglob("*")}


@pytest.mark.parametrize("bounded", [False, True])
@pytest.mark.parametrize("auth", ["api_key", "subscription"])
def test_denied_dispatch_has_no_preflight_claim_or_new_files(tmp_path, bounded, auth):
    login = tmp_path / "fake-login"
    login.mkdir()
    adapter, root, log = a_harness(
        tmp_path, auth=auth, auth_home=str(login) if auth == "subscription" else "")
    adapter.task_modes = ("review",)
    runner = (confined if bounded else recording)(adapter, tmp_path / "scratch")
    request = a_request()
    before = _tree(root)

    receipt = run_once(adapter, request)

    assert receipt.outcome == "failed"
    assert receipt.detail == boundary_detail(adapter.profile.tool_noun)
    assert _fakeclaude.spawns(log) == []
    assert (runner.entries, runner.runs, runner.events) == ([], [], [])
    assert not adapter._workspace.is_claimed(request.run_id, request.action_id)
    assert _tree(root) == before
    assert not adapter.boundary_provided("dispatch")


@pytest.mark.parametrize("bounded", [False, True])
def test_narrowing_after_preflight_refuses_before_the_task_claim(tmp_path, monkeypatch, bounded):
    adapter, root, log = a_harness(tmp_path)
    runner = (confined if bounded else recording)(adapter, tmp_path / "scratch")
    request = a_request()
    prepared = adapter.prepare(request)
    original_run = runner.run

    def narrow_after_version(spec):
        outcome = original_run(spec)
        if "--version" in spec.argv:
            adapter.task_modes = ("review",)
        return outcome

    monkeypatch.setattr(runner, "run", narrow_after_version)
    with pytest.raises(BoundaryUnavailable) as refused:
        adapter.execute(prepared)
    assert refused.value.mode == "dispatch"
    assert len(_fakeclaude.spawns(log)) == 1, "only the completed version preflight may run"
    assert _fakeclaude.prompt_spawns(log) == []
    assert not adapter._workspace.is_claimed(request.run_id, request.action_id)
    assert runner.entries == []
    homes = root / adapter.profile.home_dir
    assert not homes.exists() or list(homes.iterdir()) == []


def test_checker_declarations_are_disabled_explicitly_and_defaults_stay_available():
    assert getattr(AttemptLaunch, "task_modes", None) == ("dispatch", "review")
    assert ReviewOnly.review_enabled is True
    assert ReviewOnly.verify_for is None
    assert ReviewOnly.verification_started is None
    assert callable(ClaudeCodeTransport.verify_for)
    assert callable(ClaudeCodeTransport.verification_started)

    class ChecksRestored(ReviewOnly):
        serves_checks = True

    assert callable(ChecksRestored.verify_for)
    assert callable(ChecksRestored.verification_started)


@pytest.mark.usefixtures("boundary_assumed")
def test_review_only_transport_still_runs_a_real_fake_review(tmp_path, monkeypatch):
    adapters = []

    def review_only_harness(*args, **kwargs):
        original, root, log = a_harness(*args, **kwargs)
        adapter = ReviewOnly(
            original._pin, original._runner, root=root, clock=original._clock, ids=original._ids)
        adapters.append(adapter)
        return adapter, root, log

    monkeypatch.setattr(review_road, "a_harness", review_only_harness)
    attempt, runner, log = review_road._review(tmp_path, "win32")

    assert attempt.state is AttemptState.SUCCEEDED, attempt.receipt.detail
    assert attempt.receipt.evidence_refs, "a no-op review cannot supply durable evidence"
    assert len(_fakeclaude.prompt_spawns(log)) == 1
    assert [entry.mode for entry in runner.entries] == ["review"]
    assert runner.events[-3:] == ["enter", "run-inside", "exit"]
    assert adapters[0].verify_for is None
    assert adapters[0].boundary_provided("review")
    assert not adapters[0].boundary_provided("dispatch")
