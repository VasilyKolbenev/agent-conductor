"""The plain records the supervisor hands out: what one look found, and what a project is (4.6.4).

They hold no state and make no move: `Supervisor` makes them, and the service and the summary
read them. They live apart from it so that the supervisor stays under the size of one file.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from conductor import up_status
from conductor.hub import lifecycle as words
from conductor.hub import spawn


@dataclass(frozen=True)
class Seen:
    """What one look at a project found: its status file, its process, and the hub's own child."""

    record: up_status.StatusRecord | None
    fresh: bool
    own: spawn.Child | None
    liveness: str
    live: bool
    mode: str | None
    unreadable: bool = False


@dataclass(frozen=True)
class RunScan:
    """What `run/` says: the mode of every live process, and the status files nobody can read."""

    live: dict[str, str]
    unreadable: tuple[str, ...]


@dataclass(frozen=True)
class UnlistedClosing:
    """A project that left the list while it still owes a closure (tech lead, 30.09, rule b).

    The hub cannot prove it closed without its root, so the entry blocks every next active child.
    `action` is what the page offers: put the project back in the list (the add dialog with the
    same folder, which finds the same root and id again).
    """

    project_id: str
    since: str
    action: str = "relist"


@dataclass(frozen=True)
class ChildReport:
    """A child the hub started, at the hub's exit: its drain deadline and whether it is gone."""

    project_id: str
    drain_deadline: datetime | None
    done: bool


@dataclass(frozen=True)
class ProjectStatus:
    """A project in the words of 4.6.4: its lifecycle, working state, mode and drain deadline."""

    lifecycle: words.Lifecycle
    working: str
    mode: str | None
    drain_deadline: datetime | None
    #: The port the child reported, while its process lives (`desk_url` is made from it, 4.6.4).
    port: int | None = None
    #: A 32-hex id the hub mints for each process it sees, so a restart is a new value.
    instance: str | None = None
    #: When the child last wrote `stopped`; `None` while it is anything else.
    stopped_at: datetime | None = None
