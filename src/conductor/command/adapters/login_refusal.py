"""The closed ids of a refused shared-login lease, and the one sentence a transport writes for them.

The owner's own sentence names state of the operator's machine (a path, a build number), so it
never reaches a receipt. A transport that meets a refusal at the entry of its login guard keeps
only an id from the two closed lists below, and the runtime answers with words of its own
(`command/failure_reasons.py`): the sentence here is a way to hand two ids across, not prose.
"""
from __future__ import annotations

#: The refusals of the owner that can stop the guard from opening: the project's own owner
#: (`ownership.py`) and the shared login lease (`ownership_login.py`). Each is raised by those
#: sources, and the runtime has words for each (`tests/test_login_lease_refusal_words.py`).
LEASE_CODES = frozenset({
    "ownership_unavailable", "login_recovery_required", "login_owner_busy",
    "login_ownership_invalid", "login_context_required", "recovery_required",
    "owner_required", "ownership_lost", "transition_conflict"})
#: The reasons the boot reader gives when `ownership_unavailable` is the boot counter.
READER_CODES = frozenset({
    "native_unavailable", "layout_unknown", "partial_read", "value_empty", "counter_overflow",
    "unsupported_platform"})


def _closed(value: object, members: frozenset[str]) -> str | None:
    return value if type(value) is str and value in members else None


def ids_of(error: BaseException) -> tuple[str, str | None] | None:
    """The closed lease code of a refusal, and the closed reader code under it, or None.

    The owner raises its refusal either as it is (the project's guard) or converted into the
    process runner's own type with the refusal as its cause (the login lease); in both the
    reader's refusal is the cause of the owner's.

    Args:
        error: What the guard raised while it was being entered.

    Returns:
        ``(code, reader)`` when the refusal carries a code of `LEASE_CODES`; ``reader`` is None
        unless a code of `READER_CODES` stands under it. None for any other error.
    """
    owner = error
    code = _closed(getattr(owner, "code", None), LEASE_CODES)
    if code is None:
        owner = error.__cause__
        code = _closed(getattr(owner, "code", None), LEASE_CODES)
    if code is None:
        return None
    return code, _closed(getattr(owner.__cause__, "code", None), READER_CODES)


def sentence(code: str, reader: str | None = None) -> str:
    """The receipt detail of a lease refused before any task was spawned: two ids, no prose."""
    named = code if reader is None else f"{code}: {reader}"
    return f"the shared login lease was refused ({named}), so no task was spawned"
