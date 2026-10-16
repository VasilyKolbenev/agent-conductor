"""The call a confined attempt makes on the runner's boundary entry, and which runner takes it.

Both halves live here so that the call that is made and the check that vouches for it cannot
drift apart. A confined attempt asks ``ProcessRunner.container_profile`` for its own folders. A
build whose runner has no such entry would raise out of it once the attempt was claimed, and
the attempt would be recorded ``unknown``. So the doors ask first, by the signature alone:
``entry_takes_the_call`` binds the call to the entry the runner has and never calls it.

A leaf of the ``command`` package, like ``execution_boundary``: standard library only, no file,
no process. The adapters import it, and it imports none of them.
"""
from __future__ import annotations

import inspect


def entry_call(mode: str, folders: object | None) -> dict[str, object]:
    """The keyword arguments of the one call a confined attempt makes on the runner's entry.

    Args:
        mode: ``dispatch`` or ``review``, the attempt mode (``execution_boundary.ATTEMPT_MODES``).
        folders: The attempt's own folders, or None when the call is only being checked.
    """
    return {"mode": mode, "internet_client": True, "folders": folders}


def entry_takes_the_call(runner: object, mode: str) -> bool:
    """Whether the entry of ``runner`` binds the call of ``entry_call``, without calling it.

    Read off the entry's signature by Python's own binding rule. A runner with no such entry, or
    one whose signature cannot be read, answers no.
    """
    entry = getattr(type(runner), "container_profile", None)
    try:
        inspect.signature(entry).bind(runner, **entry_call(mode, None))
    except (TypeError, ValueError):
        return False
    return True
