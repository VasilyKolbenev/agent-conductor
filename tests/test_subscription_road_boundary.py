"""H5-V1 after I2b: a task on a subscription login runs inside the execution boundary only where the
harness has a RELAY, and the one answer for the road is still one.

The owner's decision of 21.10.2026 (``docs/recovery/2026-10-20/OPEN-DECISIONS.md``, H5-V1)
refused a connection that signs in by subscription, honestly and before anything exists, because
its child would need rights on the operator's own login home. The relay (H5-SUB-R5, decision of
23.10.2026) gives the child a fresh home with a copy of the access token instead, so the refusal
now stands only for a harness that has no relay (``HarnessProfile.login_relay``): Grok Build and
Kimi Code, and Claude Code and Codex with the relay taken off their profiles, which is the road a
harness without one is on. This file holds that where the code answers it:

- one answer for the road (``AttemptLaunch._login_road_covered``) stands behind the doors, the
  refusal before the claim, the spawn and the checker, on every harness that signs in: yes for
  the two with a relay (and a runner that lends a relay home), no for the others;
- ``process_boundary.LOGIN_LOAN_OPEN`` opens none of them: it is the runner's own gate on a login
  home, no transport names one, and opening it starts nothing;
- the refusal comes before any side effect: no claim, no home, no login lease, no spawn;
- the review road and the independent-checker road each ask the question themselves, so a
  subscription review and a subscription checker are refused through the runtime, not only when
  the helper under them is called directly;
- a road that skips the preflight cannot start a child either, on either side of the relay;
- the API-key road on Windows stays covered, with the runner's gate closed or open;
- a relay road is covered only where the login is kept in the folder the relay is derived from,
  ``<anything>/DecemberCommand/logins/<name>`` (``relay_home.relay_root_for``), judged by the
  written names alone: a login kept anywhere else has no relay home to run on; a harness with no
  relay is refused whichever folder its login is kept in, with the honest sentence of its own;
- a relayed attempt is always handed the claim of its action (a fault of the code otherwise);
- the receipt names the cause where the login is the one fact missing, and only there.

What a relayed task does is held in ``test_relay_road_success`` and the files beside it.
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
from conductor.command.contracts import ActionProposal, RunEnvelope
from conductor.command.execution_boundary import ATTEMPT_MODES, BoundaryUnavailable
from conductor.command.failure_reasons import reason_words
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.runtime import AttemptState, Budget, ControlRuntime

from tests import _fakeclaude, _fakecodex, _fakedsh, _fakegrok, _fakekimi
from tests import test_command_claude_review as claude_review
from tests import test_command_claude_transport as claude_t
from tests import test_command_codex_review as codex_review
from tests import test_command_codex_transport as codex_t
from tests import test_command_dsh_harness as dsh_t
from tests import test_command_grok_transport as grok_t
from tests import test_command_kimi_transport as kimi_t
from tests._boundary_assumed import boundary_assumed  # noqa: F401
from tests._fakeboundary import BoundaryRunner, confined, installed_outside_the_tree
from tests.test_independent_checker_transport import _run_state

SRC = Path(__file__).resolve().parents[1] / "src" / "conductor"

#: The four harnesses whose transport drives a vendor login; DSH has the API-key road only.
SIGNED_IN = [pytest.param((claude_t, _fakeclaude), id="claude-code"),
             pytest.param((codex_t, _fakecodex), id="codex"),
             pytest.param((grok_t, _fakegrok), id="grok-build"),
             pytest.param((kimi_t, _fakekimi), id="kimi-code")]
EVERY = [*SIGNED_IN, pytest.param((dsh_t, _fakedsh), id="deepseek-harness")]
#: Full-mode relay fixtures; Grok's review-only road is covered by test_grok_activation.
RELAYED = SIGNED_IN[:2]
#: The harnesses a subscription road is refused for. The third member is whether the profile has a
#: relay that is explicitly taken off; Kimi still has none.
REFUSED = [pytest.param((claude_t, _fakeclaude, True), id="claude-code-without-relay"),
           pytest.param((codex_t, _fakecodex, True), id="codex-without-relay"),
           pytest.param((grok_t, _fakegrok, True), id="grok-build-without-relay"),
           pytest.param((kimi_t, _fakekimi, False), id="kimi-code")]
#: The runner's gate as shipped, and opened the way the loan's own tests open it.
GATE = [pytest.param(False, id="gate-closed"), pytest.param(True, id="gate-open")]


#: Where a relay road keeps its login: the folder the relay is derived from.
PRODUCT_FOLDER = ("DecemberCommand", "logins", "x")
#: Where a harness with NO relay may keep its login: the product's folder, or any other. Nothing is
#: derived from the folder there, so the answer and the honest sentence cannot depend on it.
ANY_FOLDER = [pytest.param(PRODUCT_FOLDER, id="the-product-folder"),
              pytest.param(("auth", "x"), id="any-other-folder")]


def _signed_in(adapter, tmp_path, *, strip: bool = False, folder=PRODUCT_FOLDER) -> Path:
    """Re-pin a harness to a subscription login kept in a fresh, empty directory.

    ``folder`` is where it is kept under ``tmp_path``: by default the form a relay requires.
    ``strip`` takes the relay off the profile: the road of a harness that has none.
    """
    login = tmp_path.joinpath(*folder)
    login.mkdir(parents=True)
    adapter._pin = replace(adapter._pin, auth="subscription", auth_home=str(login))
    if strip:
        adapter.profile = replace(adapter.profile, login_relay=None)
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
CODEX_REVIEW_KNOBS = {_fakecodex.EMIT_REVIEW: "enabled-review-output"}


def _confirmed_review(adapter, root: Path):
    """Seed one review step under ``root`` and drive it through Confirm over ``adapter``."""
    module = claude_review if adapter.manifest.adapter_id == "claude-code" else codex_review
    seed = (claude_review.SEED_CONTENT if module is claude_review
            else "# Candidate\n\nReview this exact proposal.")
    store = RunStore(root)
    store.create_run(RunEnvelope(
        run_id=module.RUN_ID, cycle_id="review-cycle", created_at=claude_t.NOW,
        config_digest=snapshot_digest(module.CONFIG), mode="confirm"), module.CONFIG)
    store.append(ArtifactDocument(
        artifact_id="artifact-source-1", artifact_ref=module.INPUT_REF, run_id=module.RUN_ID,
        created_at=claude_t.NOW, media_type="text/markdown", content=seed))
    proposal: ActionProposal = module._proposal()
    store.append(proposal)
    runtime = ControlRuntime(
        store, AdapterRegistry([adapter]), clock=lambda: claude_t.NOW, ids=module._Ids())
    budget = Budget(max_actions=8, max_action_seconds=3600, max_confirmation_age_seconds=3600)
    return runtime.execute(runtime.authorize(module._confirmation(proposal), budget=budget))


# -- (a) one answer for the road, and the runner's gate opens none of it ------


@pytest.mark.parametrize("folder", ANY_FOLDER)
@pytest.mark.parametrize("gate", GATE)
@pytest.mark.parametrize("harness", REFUSED)
def test_every_door_refuses_a_subscription_road_with_no_relay_whatever_the_runners_gate(
        harness, gate, folder, tmp_path, monkeypatch):
    module, fake, strip = harness
    adapter, _root, log = module.a_harness(tmp_path)
    _signed_in(adapter, tmp_path, strip=strip, folder=folder)
    runner = confined(adapter, tmp_path / "scratch", platform="win32")
    monkeypatch.setattr(process_boundary, "LOGIN_LOAN_OPEN", gate)
    registry = AdapterRegistry([adapter])

    assert [adapter.boundary_provided(mode) for mode in ATTEMPT_MODES] == [False, False]
    assert [registry.execution_boundary(adapter.manifest.adapter_id, mode)
            for mode in ATTEMPT_MODES] == [False, False]
    assert (runner.entries, runner.runs) == ([], [])
    assert fake.spawns(log) == []


@pytest.mark.parametrize("gate", GATE)
@pytest.mark.parametrize("harness", RELAYED)
def test_every_door_admits_a_subscription_road_with_a_relay_whatever_the_runners_gate(
        harness, gate, tmp_path, monkeypatch):
    module, fake = harness
    adapter, _root, log = module.a_harness(tmp_path)
    _signed_in(adapter, tmp_path)
    runner = confined(adapter, tmp_path / "scratch", platform="win32")
    monkeypatch.setattr(process_boundary, "LOGIN_LOAN_OPEN", gate)
    registry = AdapterRegistry([adapter])

    assert [adapter.boundary_provided(mode) for mode in ATTEMPT_MODES] == [True, True]
    assert [registry.execution_boundary(adapter.manifest.adapter_id, mode)
            for mode in ATTEMPT_MODES] == [True, True]
    assert (runner.entries, runner.runs) == ([], [])
    assert fake.spawns(log) == []


class _LendsNoRelayHome(BoundaryRunner):
    """A runner whose entry takes the call but does not say it lends a relay home."""

    RELAY_HOME_LOANS = False


@pytest.mark.parametrize("harness", RELAYED)
def test_a_relay_road_over_a_runner_that_lends_no_relay_home_is_refused_before_a_spawn(
        harness, tmp_path):
    module, fake = harness
    adapter, root, log = module.a_harness(tmp_path)
    _signed_in(adapter, tmp_path)
    old = adapter._runner
    adapter._runner = _LendsNoRelayHome(
        old._root, scratch=tmp_path / "scratch", environ=old._environ)
    adapter.confine("win32")

    receipt = module.run_once(adapter, module.a_request())

    assert [adapter.boundary_provided(mode) for mode in ATTEMPT_MODES] == [False, False]
    assert receipt.outcome == "failed"
    assert receipt.detail == boundary_detail(adapter.profile.tool_noun)
    assert fake.spawns(log) == [] and _no_home_left(root, adapter)


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


# -- (a2) a relay road is covered only for a login kept where the relay can be derived ------

#: Where a login can be written that is not ``<anything>/DecemberCommand/logins/<name>``.
WRONG_FOLDERS = [
    pytest.param(("login",), id="a-bare-folder"),
    pytest.param(("logins", "x"), id="logins-without-the-product-folder"),
    pytest.param(("DecemberCommand", "x"), id="the-product-folder-without-logins"),
    pytest.param(("DecemberCommand", "logins"), id="logins-itself"),
    pytest.param(("DecemberCommand", "other", "x"), id="another-folder-beside-logins"),
]


@pytest.mark.parametrize("folder", WRONG_FOLDERS)
@pytest.mark.parametrize("harness", RELAYED)
def test_every_door_refuses_a_relay_road_whose_login_is_not_kept_in_the_product_folder(
        harness, folder, tmp_path):
    module, fake = harness
    adapter, _root, log = module.a_harness(tmp_path)
    _signed_in(adapter, tmp_path, folder=folder)
    runner = confined(adapter, tmp_path / "scratch", platform="win32")
    registry = AdapterRegistry([adapter])

    assert [adapter.boundary_provided(mode) for mode in ATTEMPT_MODES] == [False, False]
    assert [registry.execution_boundary(adapter.manifest.adapter_id, mode)
            for mode in ATTEMPT_MODES] == [False, False]
    assert (runner.entries, runner.runs) == ([], []) and fake.spawns(log) == []


@pytest.mark.parametrize("folder", [
    pytest.param(PRODUCT_FOLDER, id="the-product-spelling"),
    pytest.param(("decembercommand", "LOGINS", "claude"), id="case-folded")])
@pytest.mark.parametrize("harness", RELAYED)
def test_the_folder_of_the_login_is_judged_by_its_written_names_and_nothing_is_read(
        harness, folder, tmp_path):
    """A pure fact of the path: the doors answer for a folder that was never made."""
    module, fake = harness
    adapter, _root, log = module.a_harness(tmp_path)
    login = tmp_path.joinpath(*folder)
    adapter._pin = replace(adapter._pin, auth="subscription", auth_home=str(login))
    runner = confined(adapter, tmp_path / "scratch", platform="win32")

    assert [adapter.boundary_provided(mode) for mode in ATTEMPT_MODES] == [True, True]
    assert not login.exists() and not login.parent.exists(), "the door made or read a folder"
    assert (runner.entries, runner.runs) == ([], []) and fake.spawns(log) == []


@pytest.mark.parametrize("folder", WRONG_FOLDERS)
@pytest.mark.parametrize("harness", RELAYED)
def test_a_dispatch_on_a_relay_road_with_its_login_in_another_folder_is_refused_before_anything(
        harness, folder, tmp_path, monkeypatch):
    module, fake = harness
    adapter, root, log = module.a_harness(tmp_path)
    login = _signed_in(adapter, tmp_path, folder=folder)
    runner = confined(adapter, tmp_path / "scratch", platform="win32")
    entered = _leases(monkeypatch)
    request = module.a_request()

    receipt = module.run_once(adapter, request)

    assert receipt.outcome == "failed"
    assert receipt.detail == (
        f"the execution boundary is not provided for this {adapter.profile.tool_noun} attempt on "
        "this build, so no task was spawned")
    assert fake.spawns(log) == [], "a child was started with its login in another folder"
    assert (runner.entries, runner.runs, runner.events) == ([], [], [])
    assert entered == [], "the shared login lease was taken"
    assert not adapter._workspace.is_claimed(request.run_id, request.action_id)
    assert _no_home_left(root, adapter)
    assert list(login.iterdir()) == [], "the login home was touched"


@pytest.mark.parametrize("folder", WRONG_FOLDERS)
@pytest.mark.parametrize("harness", RELAYED)
def test_a_checker_on_a_relay_road_with_its_login_in_another_folder_is_refused_before_it_spawns(
        harness, folder, tmp_path):
    module, fake = harness
    adapter, _root, log = module.a_harness(tmp_path)
    _signed_in(adapter, tmp_path, folder=folder)
    runner = confined(adapter, tmp_path / "scratch", platform="win32")

    with pytest.raises(CheckFrameError) as refused:
        adapter._hold_checker_boundary()

    assert refused.value.reason == "boundary_unavailable"
    assert runner.runs == [] and fake.spawns(log) == []


@pytest.mark.parametrize("harness", RELAYED)
def test_a_review_on_a_relay_road_with_its_login_in_another_folder_is_refused_before_any_claim(
        harness, tmp_path, monkeypatch):
    """The review road asks the question itself, through the runtime."""
    module, fake = harness
    knobs = REVIEW_KNOBS if module is claude_t else CODEX_REVIEW_KNOBS
    adapter, root, log = module.a_harness(tmp_path, **knobs)
    login = _signed_in(adapter, tmp_path, folder=("login",))
    runner = confined(adapter, tmp_path / "scratch", platform="win32")
    entered = _leases(monkeypatch)
    receipts = _receipts(monkeypatch, adapter)
    sentence = boundary_detail(adapter.profile.tool_noun)

    attempt = _confirmed_review(adapter, root)

    assert attempt.state is AttemptState.FAILED, attempt.receipt.detail
    assert [(row.outcome, row.detail) for row in receipts] == [("failed", sentence)]
    assert fake.spawns(log) == [], "a child was started with its login in another folder"
    assert (runner.entries, runner.runs, runner.events) == ([], [], [])
    assert entered == [] and list(login.iterdir()) == []
    assert not adapter._workspace.is_claimed(attempt.request.run_id, attempt.request.action_id)


# -- (b) refused before any side effect ----------------------------------------


@pytest.mark.parametrize("folder", ANY_FOLDER)
@pytest.mark.parametrize("gate", GATE)
@pytest.mark.parametrize("harness", REFUSED)
def test_a_subscription_dispatch_with_no_relay_is_refused_before_any_claim_home_lease_or_spawn(
        harness, gate, folder, tmp_path, monkeypatch):
    module, fake, strip = harness
    adapter, root, log = module.a_harness(tmp_path)
    login = _signed_in(adapter, tmp_path, strip=strip, folder=folder)
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
@pytest.mark.parametrize("harness", [REFUSED[0], REFUSED[1]])
def test_a_road_that_skips_the_question_still_cannot_spawn_without_a_relay(
        harness, mode, tmp_path, monkeypatch):
    module, fake, strip = harness
    adapter, root, log = module.a_harness(tmp_path)
    _signed_in(adapter, tmp_path, strip=strip)
    runner = confined(adapter, tmp_path / "scratch", platform="win32")
    monkeypatch.setattr(process_boundary, "LOGIN_LOAN_OPEN", True)
    entered = _leases(monkeypatch)

    with pytest.raises(BoundaryUnavailable):
        adapter._attempt(("--version",), "work/work-001", timeout=30, mode=mode)

    assert entered == [] and runner.runs == [] and fake.spawns(log) == []
    assert _no_home_left(root, adapter)


@pytest.mark.parametrize("mode", ATTEMPT_MODES)
@pytest.mark.parametrize("harness", RELAYED)
def test_a_road_that_skips_the_preflight_cannot_spawn_on_a_relay_either(
        harness, mode, tmp_path, monkeypatch):
    """With a relay the boundary is provided, but nothing proved the login ready: nothing starts."""
    from conductor.command.adapters.relay_attempt import RelayNotStarted

    module, fake = harness
    adapter, root, log = module.a_harness(tmp_path)
    _signed_in(adapter, tmp_path)
    runner = confined(adapter, tmp_path / "scratch", platform="win32")
    _leases(monkeypatch)
    claim = adapter._claim_of(module.a_request())

    with pytest.raises(RelayNotStarted):
        adapter._attempt(("--version",), "work/work-001", timeout=30, mode=mode, claim=claim)

    assert runner.runs == [] and runner.entries == [] and fake.spawns(log) == []
    assert _no_home_left(root, adapter)


@pytest.mark.parametrize("mode", ATTEMPT_MODES)
@pytest.mark.parametrize("harness", RELAYED)
def test_a_relay_attempt_given_no_claim_is_a_fault_of_the_code_and_starts_nothing(
        harness, mode, tmp_path, monkeypatch):
    """The claim of a relayed attempt is taken by the attempt itself, after the boundary is
    entered; an attempt that was handed none would run with no marker, so it is refused first."""
    module, fake = harness
    adapter, root, log = module.a_harness(tmp_path)
    _signed_in(adapter, tmp_path)
    runner = confined(adapter, tmp_path / "scratch", platform="win32")
    entered = _leases(monkeypatch)

    with pytest.raises(adapter.error, match="claim"):
        adapter._attempt(("--version",), "work/work-001", timeout=30, mode=mode)

    assert entered == [], "the shared login lease was taken for an attempt that cannot be claimed"
    assert runner.runs == [] and runner.entries == [] and fake.spawns(log) == []
    assert _no_home_left(root, adapter)


@pytest.mark.parametrize("folder", ANY_FOLDER)
@pytest.mark.parametrize("harness", [REFUSED[0], REFUSED[1]])
def test_a_subscription_checker_with_no_relay_is_refused_before_it_spawns(
        harness, folder, tmp_path, monkeypatch):
    module, fake, strip = harness
    adapter, _root, log = module.a_harness(tmp_path)
    _signed_in(adapter, tmp_path, strip=strip, folder=folder)
    runner = confined(adapter, tmp_path / "scratch", platform="win32")
    monkeypatch.setattr(process_boundary, "LOGIN_LOAN_OPEN", True)

    with pytest.raises(CheckFrameError) as refused:
        adapter._hold_checker_boundary()

    assert refused.value.reason == "boundary_unavailable"
    assert runner.runs == [] and fake.spawns(log) == []


@pytest.mark.parametrize("harness", RELAYED)
def test_a_subscription_checker_with_a_relay_passes_the_boundary_question(
        harness, tmp_path):
    module, _fake = harness
    adapter, _root, _log = module.a_harness(tmp_path)
    _signed_in(adapter, tmp_path)
    confined(adapter, tmp_path / "scratch", platform="win32")

    adapter._hold_checker_boundary()


@pytest.mark.parametrize("folder", ANY_FOLDER)
@pytest.mark.parametrize("gate", GATE)
@pytest.mark.parametrize("harness", [REFUSED[0], REFUSED[1]])
def test_a_subscription_review_with_no_relay_is_refused_before_any_claim_home_lease_or_spawn(
        harness, gate, folder, tmp_path, monkeypatch):
    """The review road asks the question itself: the helper under the runtime is not enough."""
    module, fake, strip = harness
    knobs = REVIEW_KNOBS if module is claude_t else CODEX_REVIEW_KNOBS
    adapter, root, log = module.a_harness(tmp_path, **knobs)
    login = _signed_in(adapter, tmp_path, strip=strip, folder=folder)
    runner = confined(adapter, tmp_path / "scratch", platform="win32")
    monkeypatch.setattr(process_boundary, "LOGIN_LOAN_OPEN", gate)
    entered = _leases(monkeypatch)
    receipts = _receipts(monkeypatch, adapter)
    sentence = subscription_boundary_detail(adapter.profile.tool_noun)

    attempt = _confirmed_review(adapter, root)

    assert attempt.state is AttemptState.FAILED, attempt.receipt.detail
    assert [(row.outcome, row.detail) for row in receipts] == [("failed", sentence)]
    assert attempt.receipt.detail == f"adapter reported failed: {reason_words(sentence)}"
    assert fake.spawns(log) == [], "a child was started on the subscription road"
    assert (runner.entries, runner.runs, runner.events) == ([], [], [])
    assert entered == [], "the shared login lease was taken"
    assert not adapter._workspace.is_claimed(attempt.request.run_id, attempt.request.action_id)
    assert _no_home_left(root, adapter)
    assert list(login.iterdir()) == [], "the login home was touched"


#: The two ways a checker's subscription road is not covered, as ``(strip, folder)``: its relay
#: taken off the profile, or a relay whose login is kept in a folder it cannot be derived from.
UNCOVERED = [pytest.param((True, PRODUCT_FOLDER), id="no-relay"),
             pytest.param((False, ("login",)), id="relay-with-its-login-in-another-folder")]


@pytest.mark.parametrize("road", UNCOVERED)
@pytest.mark.parametrize("gate", GATE)
@pytest.mark.parametrize("vendor", ["claude-code", "codex"])
@pytest.mark.usefixtures("boundary_assumed")
def test_a_subscription_checker_the_boundary_cannot_cover_is_refused_through_the_runtime(
        vendor, gate, road, tmp_path, monkeypatch):
    """The checker road asks the question itself: not only ``_hold_checker_boundary`` called alone.

    The doer is a plain API-key transport that finishes its work; the checker, a different
    harness, holds the subscription login with its relay taken off, or kept in another folder than
    the relay is derived from, and is the only one confined: it is refused before any claim.
    """
    strip, folder = road
    if vendor == "codex":
        doer, root, _dlog = claude_t.a_harness(
            tmp_path / "doer", **{_fakeclaude.WRITE_FILE: "result.txt:done"})
        checker, _, check_log = codex_t.a_harness(
            tmp_path / "checker", root=root, **{_fakecodex.EMIT_VERDICT: "enabled-verdict-accept"})
        fake = _fakecodex
    else:
        doer, root, _dlog = codex_t.a_harness(
            tmp_path / "doer", **{_fakecodex.WRITE_FILE: "result.txt:done"})
        checker, _, check_log = claude_t.a_harness(
            tmp_path / "checker", root=root, **{_fakeclaude.EMIT_VERDICT: "enabled-verdict-accept"})
        fake = _fakeclaude
    runtime, authorization, store = _run_state(
        root, doer, checker, True, False, None, None, None)
    login = _signed_in(checker, tmp_path, strip=strip, folder=folder)
    runner = confined(checker, tmp_path / "scratch", platform="win32")
    monkeypatch.setattr(process_boundary, "LOGIN_LOAN_OPEN", gate)
    entered = _leases(monkeypatch)

    attempt = runtime.execute(authorization)

    assert attempt.state is AttemptState.VERIFICATION_FAILED, attempt.receipt.detail
    assert attempt.receipt.detail == verify_holds.CHECKER_BOUNDARY_UNAVAILABLE
    assert fake.spawns(check_log) == [], "the checker was started on the subscription road"
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
    from tests.test_independent_checker_transport import setup as checker_setup

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
    """What a harness with no relay (Grok Build, Kimi Code) is told: the owner's own words, that a
    subscription login for it is not supported inside the isolation yet, and nothing about an API
    key being the only road."""
    sentence = subscription_boundary_detail("Grok Build")

    assert sentence == (
        "this Grok Build connection signs in with a subscription, which is not supported inside "
        "the execution boundary for this harness yet, so no task was spawned")
    assert reason_words(sentence) == (
        "a subscription login for this harness is not supported inside the execution boundary yet")
    assert reason_words(boundary_detail("Grok Build")) != reason_words(sentence)
    assert "API key" not in sentence and "in this version" not in sentence


@pytest.mark.parametrize("folder", ANY_FOLDER)
@pytest.mark.parametrize("harness", [REFUSED[2], REFUSED[3]])
def test_grok_and_kimi_are_refused_a_subscription_task_with_the_honest_words(
        harness, folder, tmp_path):
    module, fake, strip = harness
    adapter, _root, log = module.a_harness(tmp_path)
    _signed_in(adapter, tmp_path, strip=strip, folder=folder)
    confined(adapter, tmp_path / "scratch", platform="win32")

    receipt = module.run_once(adapter, module.a_request())

    assert receipt.outcome == "failed" and fake.spawns(log) == []
    assert receipt.detail.endswith(
        "which is not supported inside the execution boundary for this harness yet, so no task "
        "was spawned")
    assert reason_words(receipt.detail) == (
        "a subscription login for this harness is not supported inside the execution boundary yet")


@pytest.mark.parametrize("platform", ["linux", "darwin"])
@pytest.mark.parametrize("strip", [True, False], ids=["no-relay", "relay"])
def test_where_the_platform_has_no_boundary_the_login_is_not_named(strip, platform, tmp_path):
    adapter, _root, log = claude_t.a_harness(tmp_path)
    _signed_in(adapter, tmp_path, strip=strip)
    runner = confined(adapter, tmp_path / "scratch", platform=platform)

    receipt = claude_t.run_once(adapter, claude_t.a_request())

    assert receipt.detail == boundary_detail(adapter.profile.tool_noun)
    assert _fakeclaude.spawns(log) == []
    assert runner.events == [] and runner.entries == [], "the runner was asked for something"


@pytest.mark.parametrize("strip", [True, False], ids=["no-relay", "relay"])
def test_a_build_installed_outside_the_tree_is_not_blamed_on_the_login(strip, tmp_path):
    adapter, _root, log = claude_t.a_harness(tmp_path)
    _signed_in(adapter, tmp_path, strip=strip)
    installed_outside_the_tree(adapter, tmp_path)
    confined(adapter, tmp_path / "scratch", platform="win32")

    receipt = claude_t.run_once(adapter, claude_t.a_request())

    assert receipt.detail == boundary_detail(adapter.profile.tool_noun)
    assert _fakeclaude.spawns(log) == []
