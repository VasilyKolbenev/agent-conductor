"""Admission is atomic with the durable request, and an exact retry is not new work.

Two relations, each first reproduced as a release-gate probe against the code
that failed it.

- **No orphan.** A durable ``action_request`` may not exist without a live
  reservation that will carry it. The probe retires the coordinator inside the
  exact window the request thread owns -- after the confirmation is admitted and
  before its authorization is handed on -- and then holds the journal against
  what the queue really carries: a recorded request, one placement, and a
  terminal receipt for that same action.
- **An exact retry bypasses capacity.** A repeat Confirm restating the same facts
  creates no new work: it appends nothing, queues nothing and performs no second
  effect. A full queue therefore has nothing to gate, so the frozen API's 200
  with the prior ``ActionRequest`` is owed whatever the queue holds.

Both drive the same deterministic fake provider the coordinator gates use, so
every ordering claim is held by an Event and never by a sleep.
"""
from __future__ import annotations

from conductor.command.contracts import ActionRequest
from conductor.command.coordinator import ExecutionCoordinator
from conductor.command.http_api import CommandApi, PRODUCT_COMMAND_BUDGET
from conductor.command.http_transport import CommandSession
from conductor.command.runtime import Authorization

from tests.test_command_execution_coordinator import (
    NOW,
    PROVIDER_ID,
    a_store,
    an_api,
    confirm,
    ids,
    kinds,
    post,
    provider_registry,
    results,
)
from tests.test_command_http_api import PORT, RUN_ID, TOKEN, confirm_body


#: A gate that is never opened must fail a test, not hang it.
WAIT = 20.0
#: The retiring join in the probe below deliberately overlaps a request thread
#: that has not yet handed its authorization on, so it is kept short on purpose.
RETIRE_TIMEOUT = 0.2


def test_an_exact_retry_is_answered_with_the_prior_request_while_the_queue_is_full(
        tmp_path):
    """A repeat Confirm creates no work, so a full queue has nothing to gate."""
    api, store, coordinator, adapter, _published = an_api(tmp_path, capacity=1)
    try:
        adapter.gate.clear()
        proposed, confirmed = confirm(api)
        assert confirmed.status == 201, confirmed.payload
        # The single admission slot is provably occupied: the one worker is
        # parked inside execute and only this test can release it.
        assert adapter.entered.wait(WAIT) is True
        retry = post(
            api, f"/command/runs/{RUN_ID}/actions", confirm_body(proposed.payload))
        assert (retry.status, retry.payload) == (200, confirmed.payload)
        # The retry is not work: nothing durable, nothing queued, no second effect.
        assert kinds(store).count("action_request") == 1
        assert coordinator.placements() == 1
        assert adapter.executions == 1
    finally:
        adapter.gate.set()
        coordinator.shutdown()


def test_a_retirement_inside_the_admission_window_loses_no_confirmed_action(tmp_path):
    """A recorded request is carried by a reservation the retirement cannot strand."""
    holder: dict[str, ExecutionCoordinator] = {}
    signalled: list[str] = []

    def publish(run_id: str) -> None:
        # The Confirm's own signal is raised after the request is durable and
        # before its authorization is handed on: exactly the window the probe
        # needs. Retiring here strands the request unless admission already
        # bound it to a reservation a retiring worker still drains.
        signalled.append(run_id)
        if len(signalled) == 2:
            holder["coordinator"].shutdown(timeout=RETIRE_TIMEOUT)

    mint = ids()
    store = a_store(tmp_path)
    registry = provider_registry(tmp_path, mint)
    api = CommandApi(
        store, registry, session=CommandSession(PORT, TOKEN),
        budget=PRODUCT_COMMAND_BUDGET, clock=lambda: NOW, ids=mint,
        publish_run=publish)
    coordinator = ExecutionCoordinator(api.runtime)
    holder["coordinator"] = coordinator
    api.attach_execution(coordinator)
    coordinator.start()
    try:
        _proposed, confirmed = confirm(api)
        assert confirmed.status == 201, confirmed.payload
        action_id = confirmed.payload["action_id"]
        recorded = [
            row.value.action_id for row in store.read(RUN_ID).records
            if row.kind == "action_request"]
        assert recorded == [action_id]
        # The request is durable, so a live reservation must be carrying it.
        assert coordinator.placements() == 1
        assert coordinator.wait_idle(WAIT) is True
        assert [row.action_id for row in results(store)] == [action_id]
    finally:
        coordinator.shutdown()


def test_the_coordinator_remembers_only_a_bounded_tail_of_what_it_refused(tmp_path):
    """Real refusals past the bound drop the oldest; the coordinator cannot grow by them."""
    api, _store, coordinator, adapter, _published = an_api(tmp_path)
    bound = coordinator.refusal_memory
    try:
        _proposed, confirmed = confirm(api)
        assert confirmed.status == 201, confirmed.payload
        assert coordinator.wait_idle(WAIT) is True
        granted = confirmed.payload
        fabricated = [f"action-ungranted-{index}" for index in range(bound + 5)]
        for action_id in fabricated:
            coordinator.claim().place(Authorization(
                request=ActionRequest.from_dict({**granted, "action_id": action_id}),
                record_created=True))
            assert coordinator.wait_idle(WAIT) is True
        # Every fabricated authorization was refused by the runtime, and the
        # coordinator kept exactly the newest `bound` of them.
        assert coordinator.refusals() == tuple(fabricated[-bound:])
        assert adapter.executions == 1
    finally:
        coordinator.shutdown()
