"""An in-memory turn indexed with workspace-owned synchronization values.

Extracted from harness_workspace at its 800-line ceiling. That door still
owns the guard, weak table and lock factory; this helper imports no thread,
filesystem, process or core module. The original _root_gate entry delegates
here with the same objects, key and locking order. No second table is made.
"""
from __future__ import annotations


class _RootGate:
    """One weakly indexed, workspace-owned process-local harness root gate."""

    __slots__ = ("lock", "__weakref__")

    def __init__(self, lock) -> None:
        self.lock = lock

    def acquire(self) -> bool:
        return self.lock.acquire()

    def release(self) -> None:
        self.lock.release()


# Process-local only, and keyed by the RESOLVED root, so two workspaces reached
# by different names for one tree take the same gate and a second tree takes its
# own. The weak table releases a root nothing holds. This is the same shape the
# run store's root gate and the runtime's operation lock already use; it is
# deliberately NOT either of them -- a dispatch must not hold a store
# transaction across a child process.
#
# The key was briefly the root TOGETHER WITH the two names a provider owns,
# reasoning that two providers own different homes and markers and so have no
# state to contend over. That reasoning was WRONG and the change was a race:
# they also share `work` and `instructions`, and the evidence snapshot spans the
# WHOLE work tree. A neighbour writing its own work item during another
# provider's dispatch lands in that provider's before/after diff, where it reads
# as a change outside the authorized subtree -- a mismatch pinned on a child
# that did nothing wrong. Reproduced, before the revert, as:
#     wrote_while_one_owned_root=True
#     foreign_change=['b/foreign.txt']
#
# The prose above this gate had claimed for a long time that one harness's root
# must not stop "another provider". That claim was aspirational and the CODE was
# right; the correction was to fix the sentence, not the key. A comment is not a
# specification, and a guarantee is not safe to invert because a comment nearby
# describes a nicer world.
#
# Serializing providers on one root is the cost, and it is the honest one: they
# are writing into one tree and reading evidence from all of it.
def indexed_root_gate(key, *, guard, gates, lock_factory) -> _RootGate:
    with guard:
        gate = gates.get(key)
        if gate is None:
            gate = _RootGate(lock_factory())
            gates[key] = gate
        return gate
