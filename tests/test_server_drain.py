"""Witnesses for the section 4.1.6 drain: the real `conduct up` on an activated project.

Every witness drives a subprocess through the real `main` and the real `_serve`,
with fake dispatch behind the two adapter seats and a real shared-login lease
around every attempt. What they assert is the FINAL behavior: the `stopping`,
`stop_overdue`, `stop_uncertain` and `stopped` states of the status file, the
409 `server_stopping` refusal, the ownership head `closed` published only after
the attempt and its login lease retired, and the exit codes. None of them names a
function of the drain module: they were written, and shown red with `--runxfail`,
before it existed, and they passed unchanged when it landed.

The instrument control needs no drain: it proves the harness itself (fake dispatch,
lease, ownership close, Ctrl+C delivery) so a red witness cannot be blamed on it.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from tests._drain_harness import (
    PAST_THE_OLD_JOIN, PROBE, RUN_ID, WAIT, DrainChild, DrainProject, post_paths,
    stays_true, wait_until)

#: A drain begins at once; this bounds how long a witness waits to SEE it begin.
DRAIN_BEGINS = 10.0


@pytest.fixture
def project(tmp_path):
    made = DrainProject.build(tmp_path)
    yield made
    made.close()


def _holding_one_attempt(project, *, hub, ctrl_c="none", node_timeout=None,
                         margin=None) -> DrainChild:
    """A serving child with a grant and attempt 1 inside its effect and its login lease."""
    child = project.start(hub=hub, margin=margin, ctrl_c=ctrl_c)
    child.wait_serving()
    child.authorize(node_timeout)
    child.wait_attempt(1)
    return child


def _draining_by_eof(project, **options) -> DrainChild:
    child = _holding_one_attempt(project, hub=True, **options)
    child.close_stdin()
    return child


def _refused_as_stopping(child: DrainChild) -> bool:
    try:
        status, payload = child.http("POST", f"/command/runs/{RUN_ID}/automation/control")
    except OSError:
        return False
    return status == 409 and payload.get("error", {}).get("code") == "server_stopping"


def _wait_until_draining(child: DrainChild) -> None:
    wait_until(lambda: _refused_as_stopping(child), DRAIN_BEGINS,
               "a POST to be refused 409 server_stopping", child)


def _let_the_drain_settle(child: DrainChild, project: DrainProject, window: float) -> None:
    """Hold the attempt for a window while the drain runs its in-memory steps.

    The spec puts `hold_new_work()` one step after the status write and nothing
    durable marks that step, so a witness that released the attempt the instant it
    saw `stopping` would race the drain instead of judging it. A witness that also
    claims the drain WAITS holds the attempt past what `shutdown()` waits for a
    worker today (`PAST_THE_OLD_JOIN`), or a server that merely closes would pass.
    """
    stays_true(lambda: child.alive() and project.results() == [], window,
               "the running attempt is neither killed nor finished by the drain")


def _instant(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def test_the_drain_harness_runs_two_steps_and_a_real_ctrl_c_closes_the_idle_project(project):
    project.require_ctrl_c()
    child = project.start(hub=False, auto_release=True, ctrl_c="enabled", settle_delay=0)
    child.wait_serving()
    child.authorize()
    project.wait_run_terminal(child)
    assert project.results() == ["succeeded", "succeeded"]
    child.send_ctrl_c()
    assert child.wait_exit(WAIT) == 0
    assert project.head_phase() == "closed"
    assert len(project.closed_leases()) == 2 and not project.lease_standing()


def test_eof_stops_new_proposals_and_lets_the_running_attempt_finish(project):
    child = _draining_by_eof(project)
    child.wait_state("stopping", DRAIN_BEGINS)
    wait_until(lambda: (child.status() or {}).get("drain_deadline"), WAIT,
               "the status file to carry drain_deadline", child)
    _let_the_drain_settle(child, project, PROBE)
    child.release(1)
    assert child.wait_exit(WAIT) == 0
    assert project.results() == ["succeeded"]
    assert project.request_nodes() == ["do"]
    assert "next" not in project.proposal_nodes()
    assert child.state() == "stopped"


def test_closed_is_published_only_after_workers_and_the_login_lease_retire(project):
    child = _draining_by_eof(project)
    child.wait_state("stopping", DRAIN_BEGINS)
    stays_true(lambda: project.head_phase() == "opened" and project.lease_standing()
               and not project.closed_leases(), PAST_THE_OLD_JOIN,
               "the head stays opened while the attempt holds its lease")
    child.release(1)
    at_closed = {}

    def closed_is_visible() -> bool:
        if project.head_phase() != "closed":
            return False
        at_closed.update(leases=project.closed_leases(), standing=project.lease_standing())
        return True

    wait_until(closed_is_visible, WAIT, "the ownership head to say closed", child)
    assert len(at_closed["leases"]) == 1 and not at_closed["standing"]
    assert child.wait_exit(WAIT) == 0
    assert child.state() == "stopped"


def test_ctrl_c_in_standalone_up_takes_the_same_drain_path(project):
    project.require_ctrl_c()
    child = _holding_one_attempt(project, hub=False, ctrl_c="ignored")
    child.send_ctrl_c()
    _wait_until_draining(child)
    assert child.http("GET", "/command/session")[0] == 200
    _let_the_drain_settle(child, project, PAST_THE_OLD_JOIN)
    child.release(1)
    assert child.wait_exit(WAIT) == 0
    assert project.results() == ["succeeded"]
    assert "next" not in project.proposal_nodes()
    assert project.head_phase() == "closed" and len(project.closed_leases()) == 1


def test_attempt_past_the_deadline_leaves_stop_overdue_and_no_closed_record(project):
    child = _draining_by_eof(project, node_timeout=1, margin=0)
    child.wait_state("stop_overdue", WAIT)
    deadline = _instant(child.status()["drain_deadline"])
    assert deadline <= datetime.now(timezone.utc)
    stays_true(lambda: child.alive() and child.state() == "stop_overdue"
               and project.head_phase() == "opened" and project.lease_standing()
               and not project.closed_leases(), PAST_THE_OLD_JOIN,
               "an overdue drain keeps waiting and publishes no closed record")


def test_every_post_during_drain_is_refused_server_stopping(project):
    child = _draining_by_eof(project)
    child.wait_state("stopping", DRAIN_BEGINS)
    answers = {}
    for path in post_paths():
        status, payload = child.http("POST", path, {})
        answers[path] = (status, payload.get("error", {}).get("code"))
    assert answers == {path: (409, "server_stopping") for path in post_paths()}
    assert child.http("GET", "/command/session")[0] == 200


def test_second_ctrl_c_does_not_interrupt_drain(project):
    project.require_ctrl_c()
    child = _holding_one_attempt(project, hub=False, ctrl_c="ignored")
    child.send_ctrl_c()
    _wait_until_draining(child)
    child.send_ctrl_c()
    stays_true(lambda: child.alive() and project.results() == []
               and project.head_phase() == "opened", PAST_THE_OLD_JOIN,
               "the drain goes on after a second Ctrl+C")
    child.release(1)
    assert child.wait_exit(WAIT) == 0
    assert project.results() == ["succeeded"]
    assert project.head_phase() == "closed"


def test_unproven_retirement_ends_in_stop_uncertain_with_exit_1(project):
    child = project.start(hub=True, fault="quota_uncertain")
    child.wait_serving()
    child.close_stdin()
    assert child.wait_exit(WAIT) == 1
    assert child.state() == "stop_uncertain"
    assert project.head_phase() == "opened" and not project.closed_leases()
