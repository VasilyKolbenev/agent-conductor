"""The one way the hub's files are locked: a file beside them, held exclusively (spec 4.1.3).

The lock is a `NativeHold` on a small file of its own, taken without waiting on the OS and
retried a bounded number of times, so that a holder that dies frees it by dying and a holder
that lives is waited for at most about two seconds. The file is made when it is absent, and
exclusively, so two processes that both find it missing make it once. Readers take no lock:
the files they read are swapped whole (`atomic_replace`).
"""
from __future__ import annotations

import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from conductor.ownership_native import NativeHold

#: Tries of the non-blocking lock, and the pause between two: about two seconds together.
ATTEMPTS = 100
PAUSE_SECONDS = 0.02


class LockBusy(OSError):
    """Another process held the lock for every try."""


def make(path: Path) -> None:
    """Make the lock file when it is absent; one that is there is left alone.

    Raises:
        OSError: The file could not be made (the folder is missing or not writable).
    """
    try:
        os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    except FileExistsError:
        pass


def take(path: Path, *, attempts: int = ATTEMPTS, pause: float = PAUSE_SECONDS) -> NativeHold:
    """Hold `path` exclusively, trying `attempts` times and pausing `pause` seconds between.

    Returns:
        The hold; the caller closes it.

    Raises:
        ValueError: `attempts` is less than one.
        LockBusy: Every try found the lock held by another holder.
    """
    if attempts < 1:
        raise ValueError("a lock needs at least one try")
    refused: OSError | None = None
    for attempt in range(attempts):
        try:
            return NativeHold(path, exclusive=True)
        except OSError as error:
            refused = error
            if attempt < attempts - 1:
                time.sleep(pause)
    raise LockBusy(f"{path.name} is held by another process: {refused}") from refused


@contextmanager
def held(path: Path, *, attempts: int = ATTEMPTS,
         pause: float = PAUSE_SECONDS) -> Iterator[None]:
    """Hold the lock at `path` for the body, making the file first when it is absent.

    Raises:
        LockBusy: The lock stayed held by another holder.
        OSError: The lock file could not be made.
    """
    make(path)
    hold = take(path, attempts=attempts, pause=pause)
    try:
        yield
    finally:
        hold.close()
