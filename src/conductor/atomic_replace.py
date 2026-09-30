"""Publish a file's whole content at once, and wait out a reader that holds it.

Staged beside the target and fsynced, then swapped in with `os.replace`, so a
reader sees the old whole or the new whole and never a torn file. On Windows a
reader that has the target open without delete sharing makes the swap fail with
`PermissionError` until it lets go; a hub that polls a status file would
otherwise cost its writer a state change, so that one error is retried a bounded
number of times. Anything else, and the last `PermissionError` once the bound is
spent, reaches the caller unchanged.

The other side of the same swap is `read_bytes`: a file in the middle of a swap
refuses a NEW open with `PermissionError` for a few milliseconds, so a reader
waits that out with its own, much shorter, bound.
"""
from __future__ import annotations

import os
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

#: Tries of `os.replace` before a held target is given up on.
ATTEMPTS = 100
#: Seconds between two tries; together with `ATTEMPTS`, about two seconds.
PAUSE_SECONDS = 0.02
#: Tries of a read that a swap in flight refuses. The refusal lasted at most 3.3 ms in the
#: measurement (two readers and a writer spinning on one file), so the bound is a wait of under
#: 0.1 s in all: a file that stays refused is an unreadable file, and says so soon.
READ_ATTEMPTS = 10
READ_PAUSE_SECONDS = 0.01


def replace_bytes(
        path: Path | str, payload: bytes, *,
        replace: Callable[[Path, Path], object] = os.replace,
        sleep: Callable[[float], object] = time.sleep) -> None:
    """Replace `path` with `payload` atomically.

    Args:
        path: The file to publish; its folder must exist.
        payload: The whole new content.
        replace: The swap, `os.replace` unless a test stands in for a held file.
        sleep: The pause between tries.

    Raises:
        PermissionError: The target stayed held for every try.
        OSError: The stage or the swap failed for a reason waiting cannot cure.
    """
    target = Path(path)
    descriptor, raw = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp",
                                       dir=target.parent)
    stage = Path(raw)
    try:
        with os.fdopen(descriptor, "wb") as staged:
            staged.write(payload)
            staged.flush()
            os.fsync(staged.fileno())
        _swap(stage, target, replace, sleep)
    finally:
        stage.unlink(missing_ok=True)


def read_bytes(
        path: Path | str, *, read: Callable[[Path], bytes] | None = None,
        sleep: Callable[[float], object] | None = None) -> bytes:
    """Read a whole file that `replace_bytes` may be swapping at this very moment.

    Args:
        path: The file to read.
        read: The read, `Path.read_bytes` unless a test stands in for a file being swapped.
        sleep: The pause between tries, `time.sleep` unless a test stands in.

    Raises:
        PermissionError: The file stayed refused for every try.
        OSError: The read failed for a reason waiting cannot cure (a missing file among them),
            which is raised at once.
    """
    target = Path(path)
    take, pause = read or Path.read_bytes, sleep or time.sleep
    for _ in range(READ_ATTEMPTS - 1):
        try:
            return take(target)
        except PermissionError:
            pause(READ_PAUSE_SECONDS)
    return take(target)


def _swap(stage: Path, target: Path, replace: Callable[[Path, Path], object],
          sleep: Callable[[float], object]) -> None:
    for attempt in range(ATTEMPTS):
        try:
            replace(stage, target)
            return
        except PermissionError:
            if attempt == ATTEMPTS - 1:
                raise
            sleep(PAUSE_SECONDS)
