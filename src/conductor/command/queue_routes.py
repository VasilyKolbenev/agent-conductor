"""The four queue routes (spec 4.4.5): one read and three writes, each answering with the read.

`GET /command/queue`, `POST /command/queue`, `POST /command/queue/order` and
`POST /command/queue/<run_id>/withdraw` all work in both modes and never refuse
`project_not_active`: in a process opened for viewing a put-in-queue is only a write (there is no
pump), and what the entry says there is part of the read. Every write answers with the read as it
stands after it, so a desk never guesses what the queue looks like.

The checks are the service's (`queue_service`) and the bodies are closed in `queue_bodies`; this
module only puts them in the order of the spec, `_hold_route` between the closed body and the
service, and chooses the status: 201 for an entry that is new, 200 for everything else.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from .queue_bodies import parse_order, parse_withdraw, parse_write
from .queue_service import QueueService

if TYPE_CHECKING:
    from .http_api import CommandApi

Answer = tuple[int, dict[str, Any]]


def make_queue(api: CommandApi) -> QueueService:
    """The queue of this API's project, attached to its policy so the driver and a direct
    authorize can reach it; the mode is the one the server was started in (spec 4.3.1)."""
    identity = api._identity
    queue = QueueService(api._policy, api._tasks, mode=identity.mode,
                         project_id=identity.project_id, transition_id=identity.transition_id,
                         auto_continue=identity.auto_continue, flags=api._flag)
    api._policy.queue = queue
    return queue


def read_queue(api: CommandApi) -> Answer:
    """`GET /command/queue`: the slot and the entries (spec 4.4.6)."""
    return 200, api._queue.read()


def write_queue(api: CommandApi, body: Mapping[str, Any]) -> Answer:
    """`POST /command/queue`: put a run in the queue, or renew the preauthorization it holds."""
    ask = parse_write(body, api._clock())
    api._hold_route(ask.run_id)
    created = api._queue.enqueue(ask)
    return (201 if created else 200), api._queue.read()


def write_order(api: CommandApi, body: Mapping[str, Any]) -> Answer:
    """`POST /command/queue/order`: permute the visible entries."""
    revision, run_ids = parse_order(body)
    api._queue.order(revision, run_ids)
    return 200, api._queue.read()


def write_withdraw(api: CommandApi, run_id: str, body: Mapping[str, Any]) -> Answer:
    """`POST /command/queue/<run_id>/withdraw`: take a run out; a run that is not there is 200."""
    parse_withdraw(body)
    api._queue.withdraw(run_id)
    return 200, api._queue.read()
