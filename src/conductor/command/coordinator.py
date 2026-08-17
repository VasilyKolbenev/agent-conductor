"""The server-owned execution coordinator: a bounded queue and owned workers.

`POST /command/runs/<run_id>/actions` records a confirmation and answers; it must
never perform the effect on the request thread. This module is the seam that
carries the recorded action from that answer to the effect, and it holds five
relations the HTTP boundary cannot hold by itself:

- **Fresh authority only.** The coordinator carries an ``Authorization`` value,
  never a run id or an action id it could look up and re-authorize. It refuses an
  authorization that created no durable request, so a duplicate Confirm -- which
  answers with ``record_created`` false -- places nothing. And execution authority
  still lives in the ``ControlRuntime``'s memory-only grant: a fabricated
  authorization for a durable request this process never authorized is refused by
  ``ControlRuntime.execute`` and reaches no adapter. That is why
  :meth:`CommandApi.attach_execution` requires the coordinator to hold the very
  runtime that authorizes.
- **Bounded admission, refused before any effect.** A slot is claimed BEFORE the
  durable request is appended and released only when its attempt has settled, so
  at most ``capacity`` actions are outstanding ACROSS ALL WORKERS and an overflow
  refuses the Confirm with nothing durable written and no adapter seam reached.
- **Fan-out.** :meth:`start` mints one worker per call, so a coordinator can hold
  several. Each admitted action is assigned, at placement time, to the LIVE
  worker carrying the fewest outstanding actions, ties broken by token order, so
  two actions bound to two different provider instances are driven by two
  different threads and can be inside their adapters' execute seams at the same
  instant. Assignment is deterministic and reads only live workers, so a retired
  worker is never given another action.
- **Owned, per-worker shutdown.** The coordinator mints an unguessable token for
  each worker it starts and gives that worker its OWN queue. A stop places the
  retiring sentinel on exactly that worker's queue, which no other worker ever
  reads, so the token retires the worker it names and cannot retire another --
  the guarantee a single shared queue could not make, because there any idle
  worker may consume any sentinel. The worker is removed from the roster before
  its sentinel is placed, so nothing further is assigned to it while everything
  already queued to it still runs first. There is no method that stops a thread
  by name, identity, or PID, so one coordinator cannot retire another's worker.
- **Nothing is resumed.** The queues are memory-only and are never seeded from
  the store. A restarted process therefore enqueues nothing: a durable request
  with no terminal result stays ambiguous, exactly as the runtime requires, and
  no effect is repeated.

Shutdown puts each retiring sentinel BEHIND whatever is already queued to that
worker, so an action admitted before it still runs; the join is bounded, so a
worker still inside an attempt is left to finish as a daemon thread rather than
holding the process open. An attempt that never ran leaves its durable request
without a terminal result -- the same ambiguity a crash leaves -- and the runtime
refuses to resume that without a fresh grant.

Serialization is not this module's to invent: every durable write goes through
``RunStore``, whose process-local root transaction admits one writer at a time,
so concurrent workers append a well-formed, replayable journal without any
adapter seam being reached while a transaction is held.
"""
from __future__ import annotations

import queue
import secrets
import threading
from typing import Any

from .runtime import Authorization, ControlRuntime
from .service import ServiceError

#: How many authorized actions may be outstanding (queued or running) at once.
MAX_OUTSTANDING_ACTIONS = 64
#: How many workers one coordinator may mint; fan-out is bounded, not unbounded.
MAX_EXECUTION_WORKERS = 16
#: How long a retiring worker is joined for before the caller stops waiting.
JOIN_TIMEOUT_SECONDS = 5.0


class ExecutionRefused(ServiceError):
    """The coordinator will not accept this action; nothing was authorized."""


class ExecutionOwnershipError(RuntimeError):
    """A stop names a worker token this coordinator did not mint or no longer holds."""


class _Worker:
    """One minted worker: its private inbox, its thread, and its current load.

    The inbox is the whole of this worker's addressability. Only ``_work`` for
    THIS worker reads it, so an authorization or a retiring sentinel placed on it
    can reach no other worker.
    """

    __slots__ = ("inbox", "load", "thread", "token")

    def __init__(self, token: str) -> None:
        self.token = token
        self.inbox: queue.SimpleQueue[Any] = queue.SimpleQueue()
        self.thread: threading.Thread | None = None
        self.load = 0


class _Slot:
    """One claimed admission slot: placed at most once, then released for good.

    ``release`` is idempotent and is a no-op once the slot has been placed, so the
    caller can release it in a ``finally`` without knowing which road it took. A
    placement that was refused placed nothing, so its slot is still releasable.
    """

    def __init__(self, coordinator: "ExecutionCoordinator") -> None:
        self._coordinator = coordinator
        self._settled = False

    def place(self, authorization: Authorization) -> None:
        """Hand exactly one fresh authorization to a worker; refuse anything else."""
        if self._settled:
            raise ExecutionRefused("an admission slot may be placed only once")
        if not isinstance(authorization, Authorization):
            raise ExecutionRefused("execution requires an Authorization from authorize")
        if authorization.record_created is not True:
            raise ExecutionRefused(
                "execution requires the authorization that created the durable request")
        self._coordinator._enqueue(authorization)
        self._settled = True

    def release(self) -> None:
        """Give an unplaced slot back; a placed slot keeps it until its attempt settles."""
        if self._settled:
            return
        self._settled = True
        self._coordinator._settle()


class ExecutionCoordinator:
    """Run authorized actions off the request thread, bounded, owned, and in parallel.

    The coordinator drives the runtime it was given and nothing else: it does not
    read the store, prepare an adapter, or interpret an attempt. It counts what it
    admitted and what it refused so those facts can be held as data rather than
    inferred from durable side effects.
    """

    def __init__(
            self, runtime: ControlRuntime, *,
            capacity: int = MAX_OUTSTANDING_ACTIONS) -> None:
        if not isinstance(runtime, ControlRuntime):
            raise TypeError("an execution coordinator requires a ControlRuntime")
        if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity < 1:
            raise ValueError("capacity must be an integer >= 1")
        self._runtime = runtime
        self._capacity = capacity
        self._lock = threading.Lock()
        self._settled = threading.Condition(self._lock)
        self._outstanding = 0
        self._placed = 0
        self._refused: list[str] = []
        self._accepting = False
        self._workers: dict[str, _Worker] = {}

    @property
    def runtime(self) -> ControlRuntime:
        """The one runtime whose memory-only grant this coordinator can spend."""
        return self._runtime

    @property
    def capacity(self) -> int:
        """The ceiling on outstanding actions across every worker; a claim past it is refused."""
        return self._capacity

    def placements(self) -> int:
        """How many authorizations reached a worker, counted independently of the store."""
        with self._lock:
            return self._placed

    def refusals(self) -> tuple[str, ...]:
        """The action ids whose execute refused; the runtime wrote their fate, not this."""
        with self._lock:
            return tuple(self._refused)

    def owned_tokens(self) -> tuple[str, ...]:
        """The worker tokens this coordinator minted and still holds."""
        with self._lock:
            return tuple(sorted(self._workers))

    def start(self) -> str:
        """Mint one more worker with its own queue and begin accepting claims."""
        with self._lock:
            if len(self._workers) >= MAX_EXECUTION_WORKERS:
                raise ExecutionOwnershipError(
                    "this coordinator already owns its full fan-out of workers")
            token = secrets.token_hex(16)
            worker = _Worker(token)
            worker.thread = threading.Thread(
                target=self._work, args=(worker,), name="conduct-execution",
                daemon=True)
            self._workers[token] = worker
            self._accepting = True
            worker.thread.start()
        return token

    def claim(self) -> _Slot:
        """Reserve one admission slot, or refuse before anything durable happens."""
        with self._lock:
            if not self._accepting:
                raise ExecutionRefused(
                    "the execution coordinator is not accepting actions")
            if self._outstanding >= self._capacity:
                raise ExecutionRefused(
                    "the bounded execution queue holds its full capacity of actions")
            self._outstanding += 1
        return _Slot(self)

    def wait_idle(self, timeout: float = JOIN_TIMEOUT_SECONDS) -> bool:
        """Block until every claimed slot has settled; report whether it did."""
        with self._settled:
            return self._settled.wait_for(lambda: self._outstanding == 0, timeout)

    def stop_worker(
            self, token: str, *, timeout: float = JOIN_TIMEOUT_SECONDS) -> None:
        """Retire exactly the worker this token names; refuse a token minted elsewhere.

        The sentinel goes on that worker's own inbox, which no other worker reads,
        so this retires the named worker and never a sibling that happens to be
        idle. Workers minted afterwards keep running and claims keep being
        accepted while any worker remains.
        """
        with self._lock:
            worker = self._workers.pop(token, None)
            if worker is None:
                raise ExecutionOwnershipError(
                    f"stop names worker token {token!r}, which this coordinator did "
                    "not mint or no longer holds")
            self._accepting = bool(self._workers)
        worker.inbox.put(None)
        assert worker.thread is not None
        worker.thread.join(timeout)

    def shutdown(self, *, timeout: float = JOIN_TIMEOUT_SECONDS) -> None:
        """Retire only the workers this coordinator minted; safe to call twice."""
        with self._lock:
            retiring = tuple(self._workers.values())
            self._workers.clear()
            self._accepting = False
        for worker in retiring:
            worker.inbox.put(None)
        for worker in retiring:
            assert worker.thread is not None
            worker.thread.join(timeout)

    def _enqueue(self, authorization: Authorization) -> None:
        """Assign one authorization to the least loaded live worker's own inbox."""
        with self._lock:
            live = [self._workers[token] for token in sorted(self._workers)]
            if not live:
                raise ExecutionRefused(
                    "this coordinator holds no worker to run the action")
            worker = min(live, key=lambda row: row.load)
            worker.load += 1
            self._placed += 1
        worker.inbox.put(authorization)

    def _settle(self, worker: _Worker | None = None) -> None:
        with self._settled:
            if worker is not None:
                worker.load -= 1
            self._outstanding -= 1
            self._settled.notify_all()

    def _work(self, worker: _Worker) -> None:
        """Drive one authorization at a time until THIS worker's sentinel arrives."""
        while True:
            authorization = worker.inbox.get()
            if authorization is None:
                return
            try:
                self._runtime.execute(authorization)
            except Exception:  # noqa: BLE001 -- a refused attempt must not kill the worker
                with self._lock:
                    self._refused.append(authorization.request.action_id)
            finally:
                self._settle(worker)
