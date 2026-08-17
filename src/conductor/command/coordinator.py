"""The server-owned execution coordinator: a bounded queue and one owned worker.

`POST /command/runs/<run_id>/actions` records a confirmation and answers; it must
never perform the effect on the request thread. This module is the seam that
carries the recorded action from that answer to the effect, and it holds four
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
  at most ``capacity`` actions are outstanding and an overflow refuses the Confirm
  with nothing durable written and no adapter seam reached.
- **Owned shutdown.** The coordinator mints an unguessable token for the worker it
  starts and retires only a token it minted. There is no method that stops a
  thread by name, identity, or PID, so one coordinator cannot retire another's
  worker.
- **Nothing is resumed.** The queue is memory-only and is never seeded from the
  store. A restarted process therefore enqueues nothing: a durable request with no
  terminal result stays ambiguous, exactly as the runtime requires, and no effect
  is repeated.

Shutdown puts its retiring sentinel BEHIND whatever is already queued, so an
action admitted before it still runs; the join is bounded, so a worker still
inside an attempt is left to finish as a daemon thread rather than holding the
process open. An attempt that never ran leaves its durable request without a
terminal result -- the same ambiguity a crash leaves -- and the runtime refuses to
resume that without a fresh grant.
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
#: How long a retiring worker is joined for before the caller stops waiting.
JOIN_TIMEOUT_SECONDS = 5.0


class ExecutionRefused(ServiceError):
    """The coordinator will not accept this action; nothing was authorized."""


class ExecutionOwnershipError(RuntimeError):
    """A stop names a worker token this coordinator did not mint or no longer holds."""


class _Slot:
    """One claimed admission slot: placed at most once, then released for good.

    ``release`` is idempotent and is a no-op once the slot has been placed, so the
    caller can release it in a ``finally`` without knowing which road it took.
    """

    def __init__(self, coordinator: "ExecutionCoordinator") -> None:
        self._coordinator = coordinator
        self._settled = False

    def place(self, authorization: Authorization) -> None:
        """Hand exactly one fresh authorization to the worker; refuse anything else."""
        if self._settled:
            raise ExecutionRefused("an admission slot may be placed only once")
        if not isinstance(authorization, Authorization):
            raise ExecutionRefused("execution requires an Authorization from authorize")
        if authorization.record_created is not True:
            raise ExecutionRefused(
                "execution requires the authorization that created the durable request")
        self._settled = True
        self._coordinator._enqueue(authorization)

    def release(self) -> None:
        """Give an unplaced slot back; a placed slot keeps it until its attempt settles."""
        if self._settled:
            return
        self._settled = True
        self._coordinator._settle()


class ExecutionCoordinator:
    """Run authorized actions off the request thread, bounded and owned.

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
        self._queue: queue.SimpleQueue[Any] = queue.SimpleQueue()
        self._lock = threading.Lock()
        self._settled = threading.Condition(self._lock)
        self._outstanding = 0
        self._placed = 0
        self._refused: list[str] = []
        self._accepting = False
        self._workers: dict[str, threading.Thread] = {}

    @property
    def runtime(self) -> ControlRuntime:
        """The one runtime whose memory-only grant this coordinator can spend."""
        return self._runtime

    @property
    def capacity(self) -> int:
        """The ceiling on outstanding actions; a claim past it is refused."""
        return self._capacity

    def placements(self) -> int:
        """How many authorizations reached the queue, counted independently of the store."""
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
        """Mint one worker token, start its thread, and begin accepting claims."""
        with self._lock:
            if self._workers:
                raise ExecutionOwnershipError("this coordinator already owns a worker")
            token = secrets.token_hex(16)
            thread = threading.Thread(
                target=self._work, name="conduct-execution", daemon=True)
            self._workers[token] = thread
            self._accepting = True
            thread.start()
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
        """Retire exactly the worker this token names; refuse a token minted elsewhere."""
        with self._lock:
            thread = self._workers.pop(token, None)
            if thread is None:
                raise ExecutionOwnershipError(
                    f"stop names worker token {token!r}, which this coordinator did "
                    "not mint or no longer holds")
            self._accepting = False
        self._queue.put(None)
        thread.join(timeout)

    def shutdown(self, *, timeout: float = JOIN_TIMEOUT_SECONDS) -> None:
        """Retire only the workers this coordinator minted; safe to call twice."""
        with self._lock:
            retiring = tuple(self._workers.items())
            self._workers.clear()
            self._accepting = False
        for _token, thread in retiring:
            self._queue.put(None)
            thread.join(timeout)

    def _enqueue(self, authorization: Authorization) -> None:
        with self._lock:
            self._placed += 1
        self._queue.put(authorization)

    def _settle(self) -> None:
        with self._settled:
            self._outstanding -= 1
            self._settled.notify_all()

    def _work(self) -> None:
        """Drive one authorization at a time until a sentinel retires this worker."""
        while True:
            authorization = self._queue.get()
            if authorization is None:
                return
            try:
                self._runtime.execute(authorization)
            except Exception:  # noqa: BLE001 -- a refused attempt must not kill the worker
                with self._lock:
                    self._refused.append(authorization.request.action_id)
            finally:
                self._settle()
