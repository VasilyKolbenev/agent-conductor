"""Publish a file's whole content at once, and wait out a reader that holds it.

Staged beside the target and fsynced, then swapped in with `os.replace`, so a
reader sees the old whole or the new whole and never a torn file. On Windows a
reader that has the target open without delete sharing makes the swap fail with
`PermissionError` until it lets go; a hub that polls a status file would
otherwise cost its writer a state change, so that one error is retried a bounded
number of times. Anything else, and the last `PermissionError` once the bound is
spent, reaches the caller unchanged.
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
