"""The review road and the independent-check road launch through the boundary entry in READ mode.

``test_adapter_boundary_launch`` holds the dispatch road for the five adapters. A review is a
task attempt too, and so is a plan-named checker's verdict: both are handed the work folder, so
both start inside the entry, with the mode that only reads it (``review``), and both are refused
before anything is spawned when the boundary is not provided.
"""
from __future__ import annotations

import pytest

from conductor.command.adapters import AdapterRegistry
from conductor.command.artifacts import ArtifactDocument
from conductor.command.contracts import RunEnvelope
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.runtime import AttemptState, Budget, ControlRuntime
from conductor.command import verify_holds

from tests import _fakeclaude, _fakecodex
from tests._boundary_assumed import boundary_assumed  # noqa: F401
from tests._fakeboundary import confined
from tests.test_command_claude_review import (
    CONFIG, INPUT_REF, RUN_ID, SEED_CONTENT, _confirmation, _Ids, _proposal)
from tests.test_command_claude_transport import NOW, a_harness
from tests.test_independent_checker_transport import setup as checker_setup

#: The doer of the checker tests is a plain transport that the plan door must let through; the
#: checker is confined by the test itself and answers for itself.
pytestmark = pytest.mark.usefixtures("boundary_assumed")


def _review(tmp_path, platform):
    """One review driven through Confirm over a confined Claude adapter."""
    knobs = {_fakeclaude.EMIT_REVIEW: "enabled-review-output",
             _fakeclaude.LEAK_CHECK: "enabled-review-leak-check",
             "ANTHROPIC_API_KEY": "sk-ant-api03-SYNTHETIC-BOUNDARY-NEVER-REAL"}
    adapter, root, log = a_harness(tmp_path, **knobs)
    runner = confined(adapter, tmp_path / "scratch", platform=platform)
    store = RunStore(root)
    store.create_run(RunEnvelope(
        run_id=RUN_ID, cycle_id="review-cycle", created_at=NOW,
        config_digest=snapshot_digest(CONFIG), mode="confirm"), CONFIG)
    store.append(ArtifactDocument(
        artifact_id="artifact-source-1", artifact_ref=INPUT_REF, run_id=RUN_ID,
        created_at=NOW, media_type="text/markdown", content=SEED_CONTENT))
    proposal = _proposal()
    store.append(proposal)
    runtime = ControlRuntime(store, AdapterRegistry([adapter]), clock=lambda: NOW, ids=_Ids())
    budget = Budget(max_actions=8, max_action_seconds=3600, max_confirmation_age_seconds=3600)
    attempt = runtime.execute(runtime.authorize(_confirmation(proposal), budget=budget))
    return attempt, runner, log


def test_a_review_starts_inside_the_boundary_entry_in_read_mode(tmp_path):
    attempt, runner, log = _review(tmp_path, "win32")

    assert attempt.state is AttemptState.SUCCEEDED, attempt.receipt.detail
    (entry,) = runner.entries
    assert (entry.mode, entry.internet_client) == ("review", True)
    assert entry.folders.work == "work/work-001"
    assert runner.events[-3:] == ["enter", "run-inside", "exit"]
    assert len(_fakeclaude.spawns(log)) == len(runner.runs)


@pytest.mark.parametrize("platform", ["linux", "darwin"])
def test_a_review_whose_boundary_is_refused_spawns_nothing(platform, tmp_path):
    attempt, runner, log = _review(tmp_path, platform)

    assert attempt.state is AttemptState.FAILED
    assert _fakeclaude.spawns(log) == []
    assert (runner.entries, runner.runs) == ([], [])


def test_a_checker_starts_its_verdict_inside_the_boundary_entry_in_read_mode(tmp_path):
    runtime, authorization, store, _doer, checker, _log, check_log, _root = checker_setup(
        tmp_path, cross=True)
    runner = confined(checker, tmp_path / "scratch")

    attempt = runtime.execute(authorization)

    assert attempt.state is AttemptState.SUCCEEDED, attempt.receipt.detail
    (entry,) = runner.entries
    assert (entry.mode, entry.internet_client) == ("review", True)
    assert runner.events[-3:] == ["enter", "run-inside", "exit"]
    assert len(_fakecodex.task_spawns(check_log)) == 1


@pytest.mark.parametrize("platform", ["linux", "darwin"])
def test_a_checker_whose_boundary_is_refused_spawns_nothing_and_says_why(platform, tmp_path):
    runtime, authorization, store, _doer, checker, log, check_log, _root = checker_setup(
        tmp_path, cross=True)
    runner = confined(checker, tmp_path / "scratch", platform=platform)

    attempt = runtime.execute(authorization)

    assert attempt.state is AttemptState.VERIFICATION_FAILED
    assert attempt.receipt.detail == verify_holds.CHECKER_BOUNDARY_UNAVAILABLE
    assert _fakecodex.spawns(check_log) == [], "the checker was started without the boundary"
    assert (runner.entries, runner.runs) == ([], [])
    assert not [row for row in store.read("run-001").records if row.kind == "evidence"]
    assert len(_fakeclaude.prompt_spawns(log)) == 1, "the doer, never confined, still ran"
