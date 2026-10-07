"""A checker whose shared login lease is refused fails the check and says which refusal stopped it.

`test_login_lease_refusal_reason` follows a refused lease on the doer's road. The independent
checker has a road of its own (`ArtifactAwareTransport.verify_for`), and its first spawn, the
version preflight, enters the same guard. A reviewer's probe of 06.10 ran it through
`runtime.execute` with a live owner: the control run ended `succeeded`, and the same run with the
boot reader refused when the checker began ended `verification_failed` with "the checker could not
read the exact result materials safely" and no code, a sentence that names another fault.

What is held here, with the refusal made at the moment the checker begins (the doer has finished):

* the run ends `verification_failed`, no child is started by the checker, and the detail names the
  closed lease code and, when there is one, the closed reader code, in words the runtime owns;
* the owner's own sentence, a path and "lost its result" never reach the record;
* the same run without a refusal succeeds and its checker does spawn, so the cases above are not
  vacuous.

The words themselves, and what is never echoed, are held at their own seam in
`test_login_lease_refusal_words`.
"""
from __future__ import annotations

import contextlib

import pytest

from conductor import ownership, ownership_transition as transition
from conductor.boot_witness import BootRefused
from conductor.command.adapters.process import ProcessRunner
from conductor.command.failure_reasons import LEASE_WORDS, READER_WORDS
from conductor.command.run_store import RunStore
from conductor.command.runtime_values import AttemptState
from tests import _fakeclaude
from tests._boot_world import counter, measure
from tests.test_command_run_store import CONFIG, a_run
from tests.test_harness_login_leaks import a_signed_in_home
from tests.test_harness_subscription_login import a_harness
from tests.test_independent_checker_transport import _run_state
from tests.test_login_ownership import CRASH, child
from tests.test_project_ownership import activated

SENTENCE = "the shared page is not the documented layout of this build"
READER_CODES = ("native_unavailable", "layout_unknown", "partial_read", "value_empty",
                "counter_overflow", "unsupported_platform")
CHECKER_WORDS = "the checker's shared login lease was refused"


def boot_unreadable(reader):
    def refuse(monkeypatch, root, home, tmp_path):
        def unreadable():
            raise BootRefused(reader, SENTENCE)
        measure(monkeypatch, unreadable)
        return contextlib.nullcontext()
    return refuse


def lease_held(monkeypatch, root, home, tmp_path):
    return ProcessRunner.login_write_guard(root, str(home))


def lease_left_by_another_project(monkeypatch, root, home, tmp_path):
    """A project that crashed inside the shared lease and never closed it."""
    other = tmp_path / "project-a"
    other.mkdir()
    activated(other)
    done = child(other, home, CRASH)
    assert done.returncode == 0, done.stderr
    return contextlib.nullcontext()


def no_refusal(monkeypatch, root, home, tmp_path):
    return contextlib.nullcontext()


def a_run_whose_checker_meets(tmp_path, monkeypatch, refusal):
    """Execute one run to its end; the refusal is made when the checker begins, not before.

    Returns the attempt, the spawn log and how many children had been started by then.
    """
    home = a_signed_in_home(tmp_path)
    (tmp_path / "root").mkdir()
    RunStore(tmp_path / "root").create_run(a_run(run_id="run-before-activation"), CONFIG)
    transition.activate(tmp_path / "root", legacy_writers_stopped=True)
    adapter, root, log = a_harness(
        tmp_path, auth="subscription", auth_home=str(home),
        **{_fakeclaude.WRITE_FILE: "result.txt:done",
           _fakeclaude.EMIT_VERDICT: "enabled-verdict-accept"})
    measure(monkeypatch, counter(42))
    original, before_checker = adapter.verify_for, []

    def verify_for(*args, **kwargs):
        before_checker.append(len(_fakeclaude.spawns(log)))
        with refusal(monkeypatch, root, home, tmp_path):
            return original(*args, **kwargs)

    monkeypatch.setattr(adapter, "verify_for", verify_for)
    with ownership.acquire_owner(root):
        runtime, authorization, _store = _run_state(
            root, adapter, adapter, False, False, None, None, None)
        attempt = runtime.execute(authorization)
    assert len(before_checker) == 1, "the checker was not asked exactly once"
    return attempt, log, before_checker[0]


CASES = [
    *[pytest.param(boot_unreadable(reader), "ownership_unavailable", reader,
                   id=f"boot-counter-{reader}") for reader in READER_CODES],
    pytest.param(lease_held, "login_owner_busy", None, id="lease-already-held"),
    pytest.param(lease_left_by_another_project, "login_recovery_required", None,
                 id="lease-left-by-another-project"),
]


def test_a_run_whose_checker_meets_no_refusal_succeeds_and_the_checker_spawns(
        tmp_path, monkeypatch):
    attempt, log, doer_spawns = a_run_whose_checker_meets(tmp_path, monkeypatch, no_refusal)
    assert attempt.state is AttemptState.SUCCEEDED, attempt.receipt.detail
    assert len(_fakeclaude.spawns(log)) > doer_spawns, "the control never ran its checker"


@pytest.mark.parametrize(("refusal", "code", "reader"), CASES)
def test_a_checker_whose_login_lease_is_refused_ends_verification_failed_and_says_which_refusal(
        tmp_path, monkeypatch, refusal, code, reader):
    attempt, log, doer_spawns = a_run_whose_checker_meets(tmp_path, monkeypatch, refusal)
    detail = attempt.receipt.detail
    named = code if reader is None else f"{code}, {reader}: {READER_WORDS[reader]}"
    assert attempt.state is AttemptState.VERIFICATION_FAILED, detail
    assert detail == f"{CHECKER_WORDS}: {LEASE_WORDS[code]} ({named})"
    assert "exact result materials" not in detail and "lost its result" not in detail
    assert SENTENCE not in detail, "the owner's prose is never copied into the run's record"
    assert str(tmp_path) not in detail
    assert len(_fakeclaude.spawns(log)) == doer_spawns, "the checker started a child"
