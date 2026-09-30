"""The project's task queue: what a human put in it, and what the server does with that (spec 4.4).

A run is put in the queue with a PREAUTHORIZATION: the human looked at the card of conditions
(6.4.5) and confirmed exactly those terms, by their digest, or confirmed resuming a grant he was
looking at. The file (`queue_store`) keeps it across a restart or a change of mode, but the file
alone is never permission: this service keeps, in memory, which preauthorizations THIS process
admitted (4.4.2), and the pump (`queue_pump`) starts only admitted ones, after asking the preview
again and finding the same digest.

This module is the human's side: enqueue, order, withdraw, the hook a direct authorize or resume
uses to take its entry out, and the read. Every write happens under the root gate the run store
shares, so the file, the receipt and the journal are ordered; they are still three separate
writes, and the pump reconciles each state a crash can leave between them.
"""
from __future__ import annotations

import copy
import time
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from typing import Any

from .api_refusals import ApiRefusal
from .authorization_history import bounded_history_enabled, validate_authorization_history
from .contract_values import ContractError
from .policy_history import spent_budget
from .contracts import ActionRequest
from .policy_preview import PreviewStale, build_preview
from .policy_view import automation_view
from .queue_bodies import Ask
from .queue_pump import run_pass
from .queue_reading import (
    CORRUPT, Facts, assemble, done_reason, grant_standing, run_ended, slot_reading)
from .queue_store import MAX_QUEUE, CorruptReceipt, QueueEntry, QueueFile, QueueStore
from .run_authorization import RunAuthorizationControl
from .store_errors import StoreError
from .task_contracts import frozen_config_task
from .template_store import RouteNotOwned

class QueueService:
    """The queue of one project, in one server process."""

    def __init__(self, policy: Any, tasks: Any, *, mode: str = "active",
                 monotonic: Callable[[], float] = time.monotonic,
                 started_at: str | None = None) -> None:
        """Hold the collaborators; a constructor writes nothing and starts nothing (spec 4.4.3).

        Args:
            policy: The `PolicyService` of this process (its run store, preview cache, owner
                check, clock and driver slot).
            tasks: The project's `TaskStore`, for the title of a run's task.
            mode: `active` or `view` (the `ProjectIdentity` mode).
            monotonic: A clock for the owner retry interval, replaceable in tests.
            started_at: The moment this process started, for the `server_restarted` entries;
                by default the wall clock now. The server clock is never read here: a
                constructor that took a tick would change what every test that counts them sees.
        """
        self.policy, self.tasks, self.mode = policy, tasks, mode
        self.store = QueueStore(policy.store.project_root)
        self.monotonic = monotonic
        self.started_at = started_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.admitted: set[tuple[str, str, str]] = set()
        self.owner_retry_at = 0.0

    # --- the facts --------------------------------------------------------------------------------

    def holder(self) -> str | None:
        """The run the driver holds, or None (a view process has no driver)."""
        driver = self.policy.driver
        if driver is None:
            return None
        snapshot = driver.slot()
        return snapshot.active_run_id or snapshot.inflight_run_id

    def slot(self) -> dict[str, Any]:
        """The slot of this process, read the way 4.4.6 says."""
        return slot_reading(self.policy.driver, self.mode,
                            lambda run_id: automation_view(self.policy, run_id))

    def facts(self, file: QueueFile) -> list[Facts]:
        """What is known about every entry of the file, read once."""
        holder = self.holder()
        return [self._facts_of(entry, holder) for entry in file.entries]

    def _facts_of(self, entry: QueueEntry, holder: str | None) -> Facts:
        recovered = self._recovered(entry.run_id)
        task_id, title = self._task_of(recovered)
        return Facts(entry, recovered, self._receipt(entry), entry.key in self.admitted,
                     holder == entry.run_id, task_id, title)

    def _recovered(self, run_id: str) -> Any | None:
        try:
            return self.policy.store.read(run_id)
        except (StoreError, ContractError):
            return None

    def _receipt(self, entry: QueueEntry) -> Any:
        if entry.key is None:
            return None
        try:
            return self.store.read_receipt(*entry.key)
        except (CorruptReceipt, RouteNotOwned):
            return CORRUPT

    def _task_of(self, recovered: Any | None) -> tuple[str | None, str | None]:
        if recovered is None:
            return None, None
        try:
            binding = frozen_config_task(recovered.config)
            if binding is None:
                return None, None
            record = self.tasks.standing(binding.task_id)
        except (StoreError, ContractError):
            return None, None
        return binding.task_id, None if record is None else record.title

    def processed(self, facts: Sequence[Facts], now: str) -> dict[str, str]:
        """`{run_id: why}` for every entry that is done and only waits to be removed."""
        return {item.entry.run_id: why for item in facts
                if (why := done_reason(item, now)) is not None}

    # --- the read ---------------------------------------------------------------------------------

    def read(self) -> dict[str, Any]:
        """The answer of `GET /command/queue` (spec 4.4.6); it writes nothing."""
        with self.store.transaction():
            file = self.store.read()
            return assemble(file.revision, self.facts(file), slot=self.slot(), mode=self.mode,
                            now=self.policy.clock(), process_started=self.started_at)

    # --- writing: one commit, frames for the runs it touched --------------------------------------

    def commit(self, entries: Sequence[QueueEntry], touched: Sequence[str]) -> QueueFile:
        """Write the file with these entries; tell the desk about every run the write touched."""
        written = self.store.write(tuple(entries))
        keep = {row.key for row in written.entries if row.key is not None}
        self.admitted &= keep
        for run_id in dict.fromkeys(touched):
            self.policy.notify(run_id)
        driver = self.policy.driver
        if driver is not None:
            driver.wake_queue()
        return written

    def _live(self, file: QueueFile, now: str) -> tuple[list[QueueEntry], list[str]]:
        """The entries that are not done, in order, and the runs of those that were dropped."""
        facts = self.facts(file)
        done = self.processed(facts, now)
        return ([row for row in file.entries if row.run_id not in done],
                [row.run_id for row in file.entries if row.run_id in done])

    # --- enqueue ----------------------------------------------------------------------------------

    def enqueue(self, ask: Ask) -> bool:
        """Put a run in the queue, or give its entry a new preauthorization (spec 4.4.5).

        The checks run under the root gate in the order of 4.4.5: readiness, an exact repeat,
        the owner, the conditions, room. Returns True when a NEW entry was written; False when
        the entry was updated in place or the ask was an exact repeat that wrote nothing.

        Raises:
            ApiRefusal: `queue_not_ready`, `queue_full`, or `preview_stale` (a `PreviewStale`).
            ContractError: the conditions do not hold (`contract_invalid`).
            AuthorizationError: no live owner (`authorization_refused`).
        """
        policy = self.policy
        with self.store.transaction():
            now = policy.clock()
            recovered = self._ready(ask, now)
            file = self.store.read()
            standing = next((row for row in file.entries if row.run_id == ask.run_id), None)
            if standing is not None and _same(standing, ask):
                return False
            policy.owner_check()
            self._hold_conditions(ask, recovered, now)
            live, dropped = self._live(file, now)
            created = not any(row.run_id == ask.run_id for row in live)
            if created and len(live) >= MAX_QUEUE:
                raise ApiRefusal.fixed("queue_full")
            entry = _entry_of(ask, now, None if created else standing_of(live, ask.run_id))
            entries = [entry if row.run_id == ask.run_id else row for row in live]
            self.commit(entries if not created else [*entries, entry], [ask.run_id, *dropped])
            self.admitted.add(entry.key)
            if ask.kind == "start":
                policy.previews.discard(policy.session, ask.run_id)
            return created

    def _ready(self, ask: Ask, now: str) -> Any:
        """The run, if it may be queued at all (spec 4.4.5 step 3); else `queue_not_ready`."""
        not_ready = ApiRefusal.fixed("queue_not_ready")
        recovered = self._recovered(ask.run_id)
        if recovered is None or not bounded_history_enabled(recovered):
            raise not_ready
        if run_ended(recovered) or self.holder() == ask.run_id:
            raise not_ready
        standing = grant_standing(recovered, now)
        if ask.kind == "start" and standing:
            raise not_ready      # a live grant: the run is being carried out, or was granted
        if ask.kind == "resume" and not standing:
            raise not_ready      # nothing to resume: no grant, a revoked one, an expired one
        return recovered

    def _hold_conditions(self, ask: Ask, recovered: Any, now: str) -> None:
        """The terms still hold (spec 4.4.5 step 6): the preview, the history, one more action."""
        policy = self.policy
        if ask.kind == "resume":
            policy._hold_resume(recovered)
            validate_authorization_history(recovered, _control_of(ask, recovered.envelope.run_id,
                                                                  now))
            return
        body = ask.body
        policy.previews.require(policy.session, ask.run_id, body["preview_digest"],
                                body["terms"], now)
        fresh = build_preview(recovered, copy.deepcopy(ask.preauth.asked), budget=policy.budget,
                              registry=policy.registry, provider_digest=policy.provider_digest,
                              clock=lambda: now, provider_facts=policy.provider_facts)
        if fresh["terms"] != body["terms"] or fresh["preview_digest"] != body["preview_digest"]:
            raise PreviewStale("reviewed starting facts changed; preview again")
        candidate = policy._candidate(body, now)
        if candidate.run_id != ask.run_id:
            raise ContractError("preview belongs to another run")
        validate_authorization_history(recovered, candidate)
        if not _admits_one_more(recovered, candidate):
            raise ContractError("these conditions admit no further action of any step")

    # --- order and withdraw -----------------------------------------------------------------------

    def order(self, expected_revision: int, run_ids: Sequence[str]) -> bool:
        """Reorder the visible entries; True when the file was written (spec 4.4.5).

        The same order as now writes nothing whatever the revision; a stale revision with
        another order is `queue_changed`; the current revision with a list that is not a
        permutation of the visible entries is `contract_invalid`.
        """
        with self.store.transaction():
            now = self.policy.clock()
            file = self.store.read()
            live, dropped = self._live(file, now)
            visible = [row.run_id for row in live]
            if list(run_ids) == visible:
                return False
            if expected_revision != file.revision:
                raise ApiRefusal.fixed("queue_changed")
            if sorted(run_ids) != sorted(visible):
                raise ContractError("the order is not a permutation of the queued runs")
            self.policy.owner_check()
            by_run = {row.run_id: row for row in live}
            moved = [run_id for run_id, before in zip(run_ids, visible) if run_id != before]
            self.commit([by_run[run_id] for run_id in run_ids], [*moved, *dropped])
            return True

    def withdraw(self, run_id: str) -> bool:
        """Take a run out of the queue; True when the file was written (spec 4.4.5)."""
        with self.store.transaction():
            now = self.policy.clock()
            file = self.store.read()
            live, dropped = self._live(file, now)
            if not any(row.run_id == run_id for row in live):
                return False
            self.policy.owner_check()
            self.commit([row for row in live if row.run_id != run_id], [run_id, *dropped])
            return True

    # --- the hook of a direct authorize, resume or revoke -----------------------------------------

    def run_acted(self, run_id: str, action: str) -> None:
        """A human acted on this run by hand; its entry is now the same act twice (spec 4.4.5).

        Called by `PolicyService` inside its transaction. An authorize or a resume takes the
        entry out; a revoke takes out a `resume` entry only (a start entry wants a new grant).
        """
        with self.store.transaction():
            file = self.store.read()
            entry = next((row for row in file.entries if row.run_id == run_id), None)
            if entry is None or (action == "revoke" and entry.kind != "resume"):
                return
            self.commit([row for row in file.entries if row.run_id != run_id], [])

    # --- the pump ---------------------------------------------------------------------------------

    def start_next(self) -> bool:
        """One pass of the pump (spec 4.4.4); True when a run was started or resumed."""
        return run_pass(self)


def _same(standing: QueueEntry, ask: Ask) -> bool:
    """The entry already holds this very preauthorization (the moment it was given aside)."""
    pre = standing.preauthorization
    if pre is None or standing.kind != ask.kind or type(pre) is not type(ask.preauth):
        return False
    return ({**pre.as_dict(), "preauthorized_at": None}
            == {**ask.preauth.as_dict(), "preauthorized_at": None})


def standing_of(live: Sequence[QueueEntry], run_id: str) -> QueueEntry:
    return next(row for row in live if row.run_id == run_id)


def _entry_of(ask: Ask, now: str, standing: QueueEntry | None) -> QueueEntry:
    """The entry for this ask: a new one, or the standing one's place with the new body."""
    if standing is None:
        return QueueEntry(ask.run_id, ask.kind, now, ask.preauth.human, ask.preauth, None)
    return QueueEntry(ask.run_id, ask.kind, standing.enqueued_at, standing.enqueued_by,
                      ask.preauth, None)


def _control_of(ask: Ask, run_id: str, now: str) -> RunAuthorizationControl:
    return RunAuthorizationControl(**ask.body, action="resume", run_id=run_id, recorded_at=now)


def _admits_one_more(recovered: Any, grant: Any) -> bool:
    """At least one executable step could still be authorized an action under these terms.

    The numbers of a grant are totals for the whole run, not an addition: `hold_request_budget`
    counts the requests of every grant. So the terms are asked the same arithmetic, for the
    cheapest step that has attempts left; without this a run that stops at once in `stalled` /
    `admission_refused` would take the slot of the whole queue.
    """
    values = tuple(row.value for row in recovered.records)
    definition = next(row.value for row in recovered.records if row.kind == "graph_definition")
    actions, seconds = spent_budget(values, definition)
    if actions >= grant.max_actions:
        return False
    nodes = {node.node_id: node for node in definition.nodes}
    requests = [value for value in values if type(value) is ActionRequest]
    for limit in grant.node_limits:
        spent = sum(1 for request in requests if request.node_id == limit.node_id)
        doubled = nodes[limit.node_id].verifier_instance_id is not None
        reserve = limit.timeout_seconds * (2 if doubled else 1)
        if (spent < limit.max_attempts and reserve <= grant.max_action_seconds
                and seconds + reserve <= grant.max_total_task_seconds):
            return True
    return False
