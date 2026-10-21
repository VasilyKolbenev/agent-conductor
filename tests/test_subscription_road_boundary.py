"""H5-V1: in V1 a task runs inside the execution boundary only on the API-key road.

The owner's decision of 21.10.2026 (``docs/recovery/2026-10-20/OPEN-DECISIONS.md``, H5-V1): a
connection that signs in by subscription is refused, honestly and before anything exists; the
scheme with a temporary home that holds only the credential comes after V1. This file holds the
decision where the code answers it:

- one answer for the road (``AttemptLaunch._login_road_covered``) stands behind the doors, the
  refusal before the claim, the spawn and the checker, on every harness that signs in;
- ``process_boundary.LOGIN_LOAN_OPEN`` opens none of them: it is the runner's own gate on a login
  home, no transport names one, and opening it starts nothing;
- the refusal comes before any side effect: no claim, no home, no login lease, no spawn;
- the review road and the independent-checker road each ask the question themselves, so a
  subscription review and a subscription checker are refused through the runtime, not only when
  the helper under them is called directly;
- the API-key road on Windows stays covered, with the runner's gate closed or open;
- the receipt names the cause where the login is the one fact missing, and only there.
"""
from __future__ import annotations

import ast
import contextlib
import inspect
from dataclasses import fields, replace
from pathlib import Path

import pytest

from conductor.command import verify_holds
from conductor.command.adapters import AdapterRegistry, harness_attempt, process_boundary
from conductor.command.adapters.harness_attempt import AttemptFolders
from conductor.command.adapters.harness_profile import (
    boundary_detail, subscription_boundary_detail)
from conductor.command.adapters.independent_check import CheckFrameError
from conductor.command.adapters.process import ProcessRunner
from conductor.command.artifacts import ArtifactDocument
from conductor.command.contracts import RunEnvelope
from conductor.command.execution_boundary import ATTEMPT_MODES, BoundaryUnavailable
from conductor.command.failure_reasons import reason_words
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.runtime import AttemptState, Budget, ControlRuntime

from tests import _fakeclaude, _fakecodex, _fakedsh, _fakegrok, _fakekimi
from tests import test_command_claude_transport as claude_t
from tests import test_command_codex_transport as codex_t
from tests import test_command_dsh_harness as dsh_t
from tests import test_command_grok_transport as grok_t
from tests import test_command_kimi_transport as kimi_t
from tests._boundary_assumed import boundary_assumed  # noqa: F401
from tests._fakeboundary import confined, installed_outside_the_tree
from tests.test_command_claude_review import (
    CONFIG, INPUT_REF, RUN_ID, SEED_CONTENT, _confirmation, _Ids, _proposal)
from tests.test_independent_checker_transport import setup as checker_setup

SRC = Path(__file__).resolve().parents[1] / "src" / "conductor"

#: The four harnesses whose transport drives a vendor login; DSH has the API-key road only.
SIGNED_IN = [pytest.param((claude_t, _fakeclaude), id="claude-code"),
             pytest.param((codex_t, _fakecodex), id="codex"),
             pytest.param((grok_t, _fakegrok), id="grok-build"),
             pytest.param((kimi_t, _fakekimi), id="kimi-code")]
EVERY = [*SIGNED_IN, pytest.param((dsh_t, _fakedsh), id="deepseek-harness")]
#: The runner's gate as shipped, and opened the way the loan's own tests open it.
GATE = [pytest.param(False, id="gate-closed"), pytest.param(True, id="gate-open")]


def _signed_in(adapter, tmp_path) -> Path:
    """Re-pin a harness to a subscription login kept in a fresh, empty directory."""
    login = tmp_path / "login"
    login.mkdir()
    adapter._pin = replace(adapter._pin, auth="subscription", auth_home=str(login))
    return login


def _leases(monkeypatch) -> list:
    """Record each entry of the login write guard (the shared login lease) and take none of it.

    An entry is ``(project root, login home)``; the login home is empty on the API-key road, so
    a run with a plain API-key doer records the doer's entries and none with a login home.
    """
    entered: list = []

    def guard(cls, *args):
        entered.append(args)
        return contextlib.nullcontext()

    monkeypatch.setattr(ProcessRunner, "login_write_guard", classmethod(guard))
    return entered


def _receipts(monkeypatch, adapter) -> list:
    """Record each receipt the adapter's ``execute`` hands to the runtime, before it rewords it."""
    seen: list = []
    execute = adapter.execute

    def recording(*args, **kwargs):
        seen.append(execute(*args, **kwargs))
        return seen[-1]

    monkeypatch.setattr(adapter, "execute", recording)
    return seen


def _no_home_left(root: Path, adapter) -> bool:
    homes = root / adapter.profile.home_dir
    return not homes.exists() or not list(homes.iterdir())


#: A review that would run to its end on the API-key road (the fake emits its review text).
REVIEW_KNOBS = {_fakeclaude.EMIT_REVIEW: "enabled-review-output",
                _fakeclaude.LEAK_CHECK: "enabled-review-leak-check",
                "ANTHROPIC_API_KEY": "sk-ant-api03-SYNTHETIC-SUBSCRIPTION-NEVER-REAL"}


def _confirmed_review(adapter, root: Path):
    """Seed one review step under ``root`` and drive it through Confirm over ``adapter``."""
    store = RunStore(root)
    store.create_run(RunEnvelope(
        run_id=RUN_ID, cycle_id="review-cycle", created_at=claude_t.NOW,
        config_digest=snapshot_digest(CONFIG), mode="confirm"), CONFIG)
    store.append(ArtifactDocument(
        artifact_id="artifact-source-1", artifact_ref=INPUT_REF, run_id=RUN_ID,
        created_at=claude_t.NOW, media_type="text/markdown", content=SEED_CONTENT))
    proposal = _proposal()
    store.append(proposal)
    runtime = ControlRuntime(
        store, AdapterRegistry([adapter]), clock=lambda: claude_t.NOW, ids=_Ids())
    budget = Budget(max_actions=8, max_action_seconds=3600, max_confirmation_age_seconds=3600)
    return runtime.execute(runtime.authorize(_confirmation(proposal), budget=budget))


# -- (a) one answer for the road, and the runner's gate opens none of it ------


@pytest.mark.parametrize("gate", GATE)
@pytest.mark.parametrize("harness", SIGNED_IN)
def test_every_door_refuses_the_subscription_road_whatever_the_runners_gate(
        harness, gate, tmp_path, monkeypatch):
    module, fake = harness
    adapter, _root, log = module.a_harness(tmp_path)
    _signed_in(adapter, tmp_path)
    runner = confined(adapter, tmp_path / "scratch", platform="win32")
    monkeypatch.setattr(process_boundary, "LOGIN_LOAN_OPEN", gate)
    registry = AdapterRegistry([adapter])

    assert [adapter.boundary_provided(mode) for mode in ATTEMPT_MODES] == [False, False]
    assert [registry.execution_boundary(adapter.manifest.adapter_id, mode)
            for mode in ATTEMPT_MODES] == [False, False]
    assert (runner.entries, runner.runs) == ([], [])
    assert fake.spawns(log) == []


def test_the_transport_names_no_login_home_so_no_transport_reaches_the_runners_gate():
    """``LOGIN_LOAN_OPEN`` is not a second answer for the road: no transport can ask it."""
    assert [field.name for field in fields(AttemptFolders)] == ["work", "home", "install"]
    tree = ast.parse(inspect.getsource(harness_attempt))
    built = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and getattr(node.func, "id", "") == "AttemptFolders"]
    assert len(built) == 1
    assert sorted(keyword.arg for keyword in built[0].keywords) == ["home", "install", "work"]


def _names(path: Path) -> set[str]:
    """Every name a module reads, imports or reaches as an attribute (its prose is not read)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    found |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    found |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
              for alias in node.names}
    return found


def test_only_the_runners_loan_reads_its_gate_and_no_door_asks_it():
    gate = {"LOGIN_LOAN_OPEN", "login_loan_provided"}
    readers = sorted(path.relative_to(SRC).as_posix() for path in SRC.rglob("*.py")
                     if _names(path) & gate)
    assert readers == ["command/adapters/process_boundary.py",
                       "command/adapters/process_loans.py"]


# -- (b) refused before any side effect ----------------------------------------


@pytest.mark.parametrize("gate", GATE)
@pytest.mark.parametrize("harness", SIGNED_IN)
def test_a_subscription_dispatch_is_refused_before_any_claim_home_lease_or_spawn(
        harness, gate, tmp_path, monkeypatch):
    module, fake = harness
    adapter, root, log = module.a_harness(tmp_path)
    login = _signed_in(adapter, tmp_path)
    runner = confined(adapter, tmp_path / "scratch", platform="win32")
    monkeypatch.setattr(process_boundary, "LOGIN_LOAN_OPEN", gate)
    entered = _leases(monkeypatch)
    request = module.a_request()

    receipt = module.run_once(adapter, request)

    assert receipt.outcome == "failed"
    assert receipt.detail == subscription_boundary_detail(adapter.profile.tool_noun)
    assert fake.spawns(log) == [], "a child was started on the subscription road"
    assert (runner.entries, runner.runs, runner.events) == ([], [], [])
    assert entered == [], "the shared login lease was taken"
    assert not adapter._workspace.is_claimed(request.run_id, request.action_id)
    assert _no_home_left(root, adapter)
    assert list(login.iterdir()) == [], "the login home was touched"


@pytest.mark.parametrize("mode", ATTEMPT_MODES)
def test_a_road_that_skips_the_question_still_cannot_spawn_on_the_subscription_road(
        mode, tmp_path, monkeypatch):
    adapter, root, log = claude_t.a_harness(tmp_path)
    _signed_in(adapter, tmp_path)
    runner = confined(adapter, tmp_path / "scratch", platform="win32")
    monkeypatch.setattr(process_boundary, "LOGIN_LOAN_OPEN", True)
    entered = _leases(monkeypatch)

    with pytest.raises(BoundaryUnavailable):
        adapter._attempt(("--version",), "work/work-001", timeout=30, mode=mode)

    assert entered == [] and runner.runs == [] and _fakeclaude.spawns(log) == []
    assert _no_home_left(root, adapter)


def test_a_subscription_checker_is_refused_before_it_spawns(tmp_path, monkeypatch):
    adapter, _root, log = codex_t.a_harness(tmp_path)
    _signed_in(adapter, tmp_path)
    runner = confined(adapter, tmp_path / "scratch", platform="win32")
    monkeypatch.setattr(process_boundary, "LOGIN_LOAN_OPEN", True)

    with pytest.raises(CheckFrameError) as refused:
        adapter._hold_checker_boundary()

    assert refused.value.reason == "boundary_unavailable"
    assert runner.runs == [] and _fakecodex.spawns(log) == []


@pytest.mark.parametrize("gate", GATE)
def test_a_subscription_review_is_refused_before_any_claim_home_lease_or_spawn(
        gate, tmp_path, monkeypatch):
    """The review road asks the question itself: the helper under the runtime is not enough."""
    adapter, root, log = claude_t.a_harness(tmp_path, **REVIEW_KNOBS)
    login = _signed_in(adapter, tmp_path)
    runner = confined(adapter, tmp_path / "scratch", platform="win32")
    monkeypatch.setattr(process_boundary, "LOGIN_LOAN_OPEN", gate)
    entered = _leases(monkeypatch)
    receipts = _receipts(monkeypatch, adapter)
    sentence = subscription_boundary_detail(adapter.profile.tool_noun)

    attempt = _confirmed_review(adapter, root)

    assert attempt.state is AttemptState.FAILED, attempt.receipt.detail
    assert [(row.outcome, row.detail) for row in receipts] == [("failed", sentence)]
    assert attempt.receipt.detail == f"adapter reported failed: {reason_words(sentence)}"
    assert _fakeclaude.spawns(log) == [], "a child was started on the subscription road"
    assert (runner.entries, runner.runs, runner.events) == ([], [], [])
    assert entered == [], "the shared login lease was taken"
    assert not adapter._workspace.is_claimed(attempt.request.run_id, attempt.request.action_id)
    assert _no_home_left(root, adapter)
    assert list(login.iterdir()) == [], "the login home was touched"


@pytest.mark.parametrize("gate", GATE)
@pytest.mark.usefixtures("boundary_assumed")
def test_a_subscription_checker_is_refused_through_the_runtime_before_any_claim_home_or_lease(
        gate, tmp_path, monkeypatch):
    """The checker road asks the question itself: not only ``_hold_checker_boundary`` called alone.

    The doer is a plain API-key transport that finishes its work; the checker, a different
    harness, holds the subscription login and is the only one confined.
    """
    runtime, authorization, store, _doer, checker, _log, check_log, root = checker_setup(
        tmp_path, cross=True)
    login = _signed_in(checker, tmp_path)
    runner = confined(checker, tmp_path / "scratch", platform="win32")
    monkeypatch.setattr(process_boundary, "LOGIN_LOAN_OPEN", gate)
    entered = _leases(monkeypatch)

    attempt = runtime.execute(authorization)

    assert attempt.state is AttemptState.VERIFICATION_FAILED, attempt.receipt.detail
    assert attempt.receipt.detail == verify_holds.CHECKER_BOUNDARY_UNAVAILABLE
    assert _fakecodex.spawns(check_log) == [], "the checker was started on the subscription road"
    assert (runner.entries, runner.runs, runner.events) == ([], [], [])
    assert [args for args in entered if args[1]] == [], "the shared login lease was taken"
    assert not checker.verification_started(attempt.request)
    assert not [row for row in store.read("run-001").records if row.kind == "evidence"]
    assert _no_home_left(root, checker)
    assert list(login.iterdir()) == [], "the login home was touched"


# -- (c) the API-key road on Windows stays covered -----------------------------


@pytest.mark.parametrize("gate", GATE)
@pytest.mark.parametrize("harness", EVERY)
def test_the_api_key_road_on_windows_stays_covered_whatever_the_runners_gate(
        harness, gate, tmp_path, monkeypatch):
    module, _fake = harness
    adapter, _root, _log = module.a_harness(tmp_path)
    confined(adapter, tmp_path / "scratch", platform="win32")
    monkeypatch.setattr(process_boundary, "LOGIN_LOAN_OPEN", gate)
    registry = AdapterRegistry([adapter])

    assert [adapter.boundary_provided(mode) for mode in ATTEMPT_MODES] == [True, True]
    assert [registry.execution_boundary(adapter.manifest.adapter_id, mode)
            for mode in ATTEMPT_MODES] == [True, True]


def test_an_api_key_dispatch_with_the_runners_gate_open_names_no_login_home(
        tmp_path, monkeypatch):
    adapter, _root, _log = claude_t.a_harness(tmp_path)
    runner = confined(adapter, tmp_path / "scratch", platform="win32")
    monkeypatch.setattr(process_boundary, "LOGIN_LOAN_OPEN", True)

    receipt = claude_t.run_once(adapter, claude_t.a_request())

    assert receipt.outcome == "succeeded", receipt.detail
    (entry,) = runner.entries
    assert type(entry.folders) is AttemptFolders and not hasattr(entry.folders, "login")


@pytest.mark.parametrize("gate", GATE)
def test_an_api_key_review_through_the_runtime_runs_inside_the_boundary_whatever_the_gate(
        gate, tmp_path, monkeypatch):
    """The control of the review test above: the same step, API key, is not refused."""
    adapter, root, log = claude_t.a_harness(tmp_path, **REVIEW_KNOBS)
    runner = confined(adapter, tmp_path / "scratch", platform="win32")
    monkeypatch.setattr(process_boundary, "LOGIN_LOAN_OPEN", gate)

    attempt = _confirmed_review(adapter, root)

    assert attempt.state is AttemptState.SUCCEEDED, attempt.receipt.detail
    (entry,) = runner.entries
    assert entry.mode == "review" and runner.runs
    assert len(_fakeclaude.spawns(log)) == len(runner.runs)


@pytest.mark.parametrize("gate", GATE)
@pytest.mark.usefixtures("boundary_assumed")
def test_an_api_key_checker_through_the_runtime_runs_inside_the_boundary_whatever_the_gate(
        gate, tmp_path, monkeypatch):
    """The control of the checker test above: the same run, API key, is not refused."""
    runtime, authorization, _store, _doer, checker, _log, check_log, _root = checker_setup(
        tmp_path, cross=True)
    runner = confined(checker, tmp_path / "scratch", platform="win32")
    monkeypatch.setattr(process_boundary, "LOGIN_LOAN_OPEN", gate)

    attempt = runtime.execute(authorization)

    assert attempt.state is AttemptState.SUCCEEDED, attempt.receipt.detail
    (entry,) = runner.entries
    assert entry.mode == "review" and runner.runs
    assert len(_fakecodex.task_spawns(check_log)) == 1


# -- (d) the receipt names the cause where it is the one cause -----------------


def test_the_subscription_sentence_names_the_login_mode_and_the_runtime_words_for_it():
    sentence = subscription_boundary_detail("Claude Code")

    assert sentence == (
        "this Claude Code connection signs in with a subscription, and in this version a task "
        "runs inside the execution boundary only with an API key, so no task was spawned")
    assert reason_words(sentence) == (
        "a subscription login does not run tasks inside the execution boundary in this version")
    assert reason_words(boundary_detail("Claude Code")) != reason_words(sentence)


@pytest.mark.parametrize("platform", ["linux", "darwin"])
def test_where_the_platform_has_no_boundary_the_login_is_not_named(platform, tmp_path):
    adapter, _root, log = claude_t.a_harness(tmp_path)
    _signed_in(adapter, tmp_path)
    confined(adapter, tmp_path / "scratch", platform=platform)

    receipt = claude_t.run_once(adapter, claude_t.a_request())

    assert receipt.detail == boundary_detail(adapter.profile.tool_noun)
    assert _fakeclaude.spawns(log) == []


def test_a_build_installed_outside_the_tree_is_not_blamed_on_the_login(tmp_path):
    adapter, _root, log = claude_t.a_harness(tmp_path)
    _signed_in(adapter, tmp_path)
    installed_outside_the_tree(adapter, tmp_path)
    confined(adapter, tmp_path / "scratch", platform="win32")

    receipt = claude_t.run_once(adapter, claude_t.a_request())

    assert receipt.detail == boundary_detail(adapter.profile.tool_noun)
    assert _fakeclaude.spawns(log) == []
