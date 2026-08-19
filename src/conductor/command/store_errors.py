"""What the run store refuses with, held apart so its rules can import them.

The graph causality rules next door raise these, and the store raises them too;
neither may import the other, so the words they share live here. The store
re-exports every name under its original spelling, so no caller learns of it.
"""
from __future__ import annotations


class StoreError(RuntimeError):
    """The run store cannot safely complete the requested operation."""


class RunExists(StoreError):
    """Exclusive run creation found an existing identity."""


class RecordConflict(StoreError):
    """An immutable identity or idempotency key was reused with new meaning."""


class CorruptRun(StoreError):
    """Durable bytes contradict the contracts or one another."""
