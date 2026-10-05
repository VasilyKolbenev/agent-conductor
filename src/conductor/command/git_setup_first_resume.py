"""The decision table of the first commit: what to do next, given what is seen (spec 9.8, S4).

Pure: no file, no process, no clock. The driver reads three facts on every turn, asks this table
for ONE next action, performs it and reads again, so the first write and every recovery walk the
same table and no path can skip a check another path makes.
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
    """`index.lock` judged by its bytes (git_setup_first_lock)."""

    NONE = "none"
    OWN = "own"
    FOREIGN = "foreign"


class Index(Enum):
    """The owner's index against the tree this operation committed."""

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
    """A refusal, and the only two things the product may undo to make it."""

    reason: str
    release_own_lock: bool = False
    drop_copy: bool = False


def next_action(stage: str, ref: Ref, lock: Lock, index: Index) -> Act | Refuse:
    """The one next step for these facts.

    A ref that is not ours, or one recorded as moved and now absent, refuses `head_exists`; a
    foreign lock refuses `index_locked`. A ref at our commit takes the road of `ref_moved`. With
    the ref absent a missing lock is taken, an index found under our lock refuses `index_exists`,
    and the recorded stage says whether to mark the lock or to move the ref.
    """
    own = lock is Lock.OWN
    if ref is Ref.OTHER or (stage == REF_MOVED and ref is Ref.ABSENT):
        return Refuse("head_exists", release_own_lock=own)
    if lock is Lock.FOREIGN:
        return Refuse("index_locked", drop_copy=True)
    if ref is Ref.AT_COMMIT:
        return _after_the_ref_moved(stage, lock, index)
    if lock is Lock.NONE:
        return Act.TAKE_LOCK
    if index is not Index.ABSENT:
        return Refuse("index_exists", release_own_lock=True)
    return Act.MARK_LOCKED if stage == PREPARED else Act.MOVE_REF


def _after_the_ref_moved(stage: str, lock: Lock, index: Index) -> Act | Refuse:
    own = lock is Lock.OWN
    if stage != REF_MOVED:
        return Act.MARK_REF_MOVED
    if index is Index.MATCHES:
        return Act.RELEASE_LOCK if own else Act.FINISH
    if index is Index.OTHER:
        return Refuse("index_exists", release_own_lock=own)
    return Act.INSTALL_INDEX if own else Act.TAKE_LOCK
