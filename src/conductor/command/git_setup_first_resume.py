"""The decision table of the first commit: what to do next, given what is seen (spec 9.8, S4).

Pure: no file, no process, no clock. The driver reads three facts on every turn, asks this table
for ONE next action, performs it and reads again, so the first write and every recovery walk the
same table and no path can skip a check another path makes.

A stage outside `STAGES` is refused here, `awaiting_signature` included: that wait has a table of
its own and never reaches the driver. A final refusal also drops the operation's own copy in
`.git` (review ruling, decision E): the copy is proved by the stored install bytes and laid again
from them by a later repeat, so no refusal leaves it behind; only a damaged record removes nothing.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

PREPARED, LOCKED, REF_MOVED = "prepared", "locked", "ref_moved"
STAGES = (PREPARED, LOCKED, REF_MOVED)


class Ref(Enum):
    """The target ref against this operation's commit."""

    ABSENT = "absent"
    AT_COMMIT = "at_commit"
    OTHER = "other"


class Lock(Enum):
    """`index.lock` judged by the whole binding, never by its bytes alone (git_setup_first_lock)."""

    NONE = "none"
    OWN = "own"
    FOREIGN = "foreign"


class Index(Enum):
    """The owner's index against the tree this operation committed.

    `MATCHES` says the index is equivalent to the tree and nothing about who wrote the file
    (review ruling OD-3): an equivalent index is left exactly as it is, never moved or deleted."""

    ABSENT = "absent"
    MATCHES = "matches"
    OTHER = "other"


class Act(Enum):
    """The only effects the driver may perform, one per turn."""

    TAKE_LOCK = "take_lock"
    MARK_LOCKED = "mark_locked"
    MOVE_REF = "move_ref"
    MARK_REF_MOVED = "mark_ref_moved"
    INSTALL_INDEX = "install_index"
    RELEASE_LOCK = "release_lock"
    FINISH = "finish"


@dataclass(frozen=True)
class Refuse:
    """A refusal, and the only two things the product may undo to make it: its own lock and its
    own copy, each proved by the stored bytes. A foreign lock, ref or index is never touched."""

    reason: str
    release_own_lock: bool = False
    drop_copy: bool = False


def next_action(stage: str, ref: Ref, lock: Lock, index: Index) -> Act | Refuse:
    """The one next step for these facts.

    A stage outside STAGES is a damaged record: it refuses `setup_damaged` before anything else
    and undoes nothing. A ref that is not ours, or one recorded as moved and now absent, refuses
    `head_exists`; a foreign lock refuses `index_locked`. A ref at our commit takes the road of
    `ref_moved`. With the ref absent a missing lock is taken, an index found under our lock
    refuses `index_exists`, and the recorded stage says whether to mark the lock or to move the
    ref. Every refusal but `setup_damaged` drops the own copy.
    """
    if stage not in STAGES:
        return Refuse("setup_damaged")
    own = lock is Lock.OWN
    if ref is Ref.OTHER or (stage == REF_MOVED and ref is Ref.ABSENT):
        return Refuse("head_exists", release_own_lock=own, drop_copy=True)
    if lock is Lock.FOREIGN:
        return Refuse("index_locked", drop_copy=True)
    if ref is Ref.AT_COMMIT:
        return _after_the_ref_moved(stage, lock, index)
    if lock is Lock.NONE:
        return Act.TAKE_LOCK
    if index is not Index.ABSENT:
        return Refuse("index_exists", release_own_lock=True, drop_copy=True)
    return Act.MOVE_REF if stage == LOCKED else Act.MARK_LOCKED


def _after_the_ref_moved(stage: str, lock: Lock, index: Index) -> Act | Refuse:
    own = lock is Lock.OWN
    if stage != REF_MOVED:
        return Act.MARK_REF_MOVED
    if index is Index.MATCHES:
        return Act.RELEASE_LOCK if own else Act.FINISH
    if index is Index.OTHER:
        return Refuse("index_exists", release_own_lock=own, drop_copy=True)
    return Act.INSTALL_INDEX if own else Act.TAKE_LOCK
