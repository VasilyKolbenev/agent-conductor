"""A run that the shared login lease refuses ends failed and says why, in the runtime's own words.

A review ruling accepted the refusal of a login lease when the OS boot counter cannot be read, on
the condition that the reason is visible to the person. `test_ownership_unavailable_reason` proves
the text at the hub, the writer commands, `conduct up` and `ProcessRunner.login_write_guard`. This
file follows it onto the last surface: a harness run. The lease guard raises while the run's own
transport is about to spawn, and the runtime used to record only "adapter execute lost its result",
an unknown outcome with no code and no reason.

What is held here:

* a dispatch whose lease is refused ends `failed`, spawns nothing, and its detail names the closed
  code and, when there is one, the closed reader code, in words the runtime owns (never the owner's
  prose, never a path).

The typed refusal and the table of words are held at their own seams in
`test_login_lease_refusal_words`.
"""
from __future__ import annotations

import pytest

from conductor import ownership, ownership_transition as transition
from conductor.boot_witness import BootRefused
from conductor.command import failure_reasons
from conductor.command.adapters import AdapterRegistry
from conductor.command.adapters.process import ProcessRunner
from conductor.command.artifacts import ArtifactDocument
from conductor.command.contracts import RunEnvelope
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.runtime import Budget, ControlRuntime
from conductor.command.runtime_values import AttemptState
from tests import _fakeclaude
from tests._boot_world import counter, measure
from tests.test_command_claude_review import (
    ARGUMENTS, CONFIG as REVIEW_CONFIG, INPUT_REF, RUN_ID, SEED_CONTENT, _confirmation, _proposal)
from tests.test_command_claude_transport import NOW, _Ids, a_request, run_once
from tests.test_harness_login_leaks import a_signed_in_home
from tests.test_harness_subscription_login import a_harness
from tests.test_independent_checker_transport import _run_state
from tests.test_command_run_store import CONFIG, a_run

SENTENCE = "the shared page is not the documented layout of this build"
READER_CODES = ("native_unavailable", "layout_unknown", "partial_read", "value_empty",
                "counter_overflow", "unsupported_platform")


def unreadable(code="layout_unknown"):
    def reader():
        raise BootRefused(code, SENTENCE)
    return reader


def an_owned_harness(tmp_path, monkeypatch):
    """A subscription harness whose project is activated; the live owner is opened by the test.

    The project is activated BEFORE the harness is built: the harness takes its run store from the
    layout it finds, and one built over the legacy layout cannot read what an owned run writes.
    """
    home = a_signed_in_home(tmp_path)
    (tmp_path / "root").mkdir()
    RunStore(tmp_path / "root").create_run(a_run(run_id="run-before-activation"), CONFIG)
    transition.activate(tmp_path / "root", legacy_writers_stopped=True)
    adapter, root, log = a_harness(tmp_path, auth="subscription", auth_home=str(home))
    measure(monkeypatch, counter(42))
    return adapter, root, log, home


@pytest.mark.parametrize("code", READER_CODES)
def test_a_run_whose_boot_counter_cannot_be_read_ends_failed_and_says_which_refusal_stopped_it(
        tmp_path, monkeypatch, code):
    adapter, root, log, _home = an_owned_harness(tmp_path, monkeypatch)
    with ownership.acquire_owner(root):
        runtime, authorization, _store = _run_state(
            root, adapter, adapter, False, False, None, None, None)
        measure(monkeypatch, unreadable(code))
        attempt = runtime.execute(authorization)
    detail = attempt.receipt.detail
    assert attempt.state is AttemptState.FAILED, detail
    assert "lost its result" not in detail
    assert "ownership_unavailable" in detail and code in detail, detail
    assert "boot counter" in detail, "the reason is said in words, not by the codes alone"
    assert SENTENCE not in detail, "the owner's prose is never copied into the run's record"
    assert str(tmp_path) not in detail and str(root) not in detail
    assert _fakeclaude.spawns(log) == [], "a child was started although the lease was refused"


def test_a_dispatch_receipt_carries_the_closed_codes_and_no_prose_of_the_owner(
        tmp_path, monkeypatch):
    adapter, root, log, _home = an_owned_harness(tmp_path, monkeypatch)
    with ownership.acquire_owner(root):
        measure(monkeypatch, unreadable("partial_read"))
        receipt = run_once(adapter, a_request())
    assert receipt.outcome == "failed"
    assert receipt.detail == ("the shared login lease was refused (ownership_unavailable: "
                              "partial_read), so no task was spawned")
    assert _fakeclaude.spawns(log) == []


def test_a_lease_refused_for_another_reason_says_that_code_and_names_no_reader(
        tmp_path, monkeypatch):
    adapter, root, log, home = an_owned_harness(tmp_path, monkeypatch)
    with ownership.acquire_owner(root):
        with ProcessRunner.login_write_guard(root, str(home)):
            receipt = run_once(adapter, a_request())
    assert receipt.outcome == "failed"
    assert receipt.detail == ("the shared login lease was refused (login_owner_busy), "
                              "so no task was spawned")
    assert _fakeclaude.spawns(log) == []
    said = failure_reasons.reason_words(receipt.detail)
    assert said is not None and "login_owner_busy" in said and "reader" not in said


def test_a_review_whose_lease_is_refused_ends_failed_and_says_which_refusal_stopped_it(
        tmp_path, monkeypatch):
    adapter, root, log, _home = an_owned_harness(tmp_path, monkeypatch)
    with ownership.acquire_owner(root):
        store = RunStore(root)
        store.create_run(RunEnvelope(
            run_id=RUN_ID, cycle_id="review-cycle", created_at=NOW,
            config_digest=snapshot_digest(REVIEW_CONFIG), mode="confirm"), REVIEW_CONFIG)
        store.append(ArtifactDocument(
            artifact_id="artifact-source-1", artifact_ref=INPUT_REF, run_id=RUN_ID,
            created_at=NOW, media_type="text/markdown", content=SEED_CONTENT))
        proposal = _proposal(ARGUMENTS)
        store.append(proposal)
        runtime = ControlRuntime(
            store, AdapterRegistry([adapter]), clock=lambda: NOW, ids=_Ids())
        authorization = runtime.authorize(_confirmation(proposal), budget=Budget(
            max_actions=8, max_action_seconds=3600, max_confirmation_age_seconds=3600))
        measure(monkeypatch, unreadable("value_empty"))
        attempt = runtime.execute(authorization)
    detail = attempt.receipt.detail
    assert attempt.state is AttemptState.FAILED, detail
    assert "ownership_unavailable" in detail and "value_empty" in detail, detail
    assert "lost its result" not in detail and SENTENCE not in detail
    assert _fakeclaude.spawns(log) == [], "a child was started although the lease was refused"
