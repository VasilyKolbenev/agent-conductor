"""A direct authorize, resume or revoke tells the queue, inside the transaction (spec 4.4.5).

"A successful direct authorize or control resume of a run in the queue removes its entry with the
next write of the file, under the same lock; a revoke removes a resume entry." The hook is a call
on `policy.queue` next to the driver's `activate` and `deactivate`, made only when the journal
really changed (never for an exact retry, never for a pause), after the driver knows, and it
never undoes a grant: if the queue's own write fails the entry is hidden by the read and removed
by the next pass of the pump.
"""
from __future__ import annotations

import pytest

from conductor.command.run_store import RunStore
from conductor.command.store_errors import StoreError
from tests.test_policy_runtime import ASK, Activation, approve, pause, propose, setup


class Queue:
    """Records what the policy told it, and whether the root gate was held at that moment."""

    def __init__(self, order=None, fail=None):
        self.told = []
        self.order = order
        self.fail = fail

    def run_acted(self, run_id, action):
        self.told.append((run_id, action, RunStore.current_thread_holds_transaction()))
        if self.order is not None:
            self.order.append("queue")
        if self.fail is not None:
            raise self.fail


class Ordered(Activation):
    def __init__(self, order):
        super().__init__()
        self.order = order

    def activate(self, run_id, grant_id):
        self.order.append("activate")
        super().activate(run_id, grant_id)

    def deactivate(self, run_id):
        self.order.append("deactivate")
        super().deactivate(run_id)


def control_body(grant, kind, expected):
    return {"control_id": kind, "authorization_id": grant.authorization_id,
            "authorization_digest": grant.authorization_digest, "action": kind,
            "actor": "owner", "expected_control_id": expected}


def test_a_policy_is_built_with_no_queue(tmp_path):
    assert setup(tmp_path).policy.queue is None


def test_a_direct_authorize_tells_the_queue_once_inside_the_transaction_and_after_the_driver(
        tmp_path):
    f = setup(tmp_path)
    order = []
    f.policy.driver, f.policy.queue = Ordered(order), Queue(order)
    grant, body = approve(f)
    assert f.policy.queue.told == [("run", "authorize", True)]
    assert order == ["activate", "queue"]
    assert f.policy.authorize("run", body) == (grant, False)         # the exact retry
    assert len(f.policy.queue.told) == 1


def test_a_resume_and_a_revoke_tell_the_queue_and_a_pause_does_not(tmp_path):
    f = setup(tmp_path)
    grant, _ = approve(f)
    f.policy.queue = Queue()
    f.policy.control("run", control_body(grant, "pause", None))
    assert f.policy.queue.told == []
    f.policy.control("run", control_body(grant, "resume", "pause"))
    f.policy.control("run", control_body(grant, "revoke", "resume"))
    assert f.policy.queue.told == [("run", "resume", True), ("run", "revoke", True)]


def test_the_exact_retry_of_a_control_tells_the_queue_nothing(tmp_path):
    f = setup(tmp_path)
    grant, _ = approve(f)
    f.policy.queue = Queue()
    body = control_body(grant, "pause", None)
    f.policy.control("run", body)
    f.policy.control("run", body)
    f.policy.control("run", control_body(grant, "resume", "pause"))
    f.policy.control("run", control_body(grant, "resume", "pause"))
    assert [action for _, action, _ in f.policy.queue.told] == ["resume"]


def test_a_refused_authorize_or_resume_tells_the_queue_nothing(tmp_path):
    f = setup(tmp_path)
    grant, _ = approve(f)
    propose(f)
    f.runtime.authorize_policy("run", "proposal", grant.authorization_id)   # an open action
    pause(f, grant)
    f.policy.queue = Queue()
    with pytest.raises(Exception):
        f.policy.control("run", control_body(grant, "resume", "pause"))
    assert f.policy.queue.told == []


def test_a_store_error_of_the_hook_never_undoes_the_grant_or_the_control(tmp_path):
    f = setup(tmp_path)
    f.policy.queue = Queue(fail=StoreError("the queue file is not writable"))
    grant, _ = approve(f)
    kinds = [row.kind for row in f.store.read("run").records]
    assert "run_authorization" in kinds
    f.policy.control("run", control_body(grant, "pause", None))
    resumed, created = f.policy.control("run", control_body(grant, "resume", "pause"))
    assert created and resumed.action == "resume"
    assert [row.kind for row in f.store.read("run").records].count(
        "run_authorization_control") == 2


def test_a_fault_that_is_not_a_store_error_is_not_hidden(tmp_path):
    f = setup(tmp_path)
    f.policy.queue = Queue(fail=RuntimeError("a bug in the queue"))
    preview = f.policy.preview("run", ASK)
    with pytest.raises(RuntimeError):
        f.policy.authorize("run", {"authorization_id": "grant",
            "preview_digest": preview["preview_digest"], "authorized_by": "owner",
            "terms": preview["terms"], "supersedes": None})
