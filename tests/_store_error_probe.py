"""Why did the command API answer 500 `store_error`? A test-only way to read the cause.

Not a test file. The public answer stays fixed and safe (`store_error`, no cause): the wire
never learns more. This wraps, inside one `with`, the single function where the command API
turns an exception into a public answer, and for each answer that is `store_error` keeps
the STAGE (the last frames of the original raise, as `file:function:line`) and, for every
exception in the chain, its type, `errno`, `winerror` and the BASE NAME of the file the OS
names. It keeps no message, no folder of a path, and nothing a file held.

Use, in a test helper that meets an unexpected 500:

    with store_error_probe.watching() as seen:
        ...the calls...
    assert status == 201, (answer, store_error_probe.describe(seen))
"""
from __future__ import annotations

import os
import traceback
from collections.abc import Iterator
from contextlib import contextmanager

from conductor.command import http_api

_FRAMES = 6


def _link(error: BaseException) -> dict:
    name = os.path.basename(str(getattr(error, "filename", "") or "").replace("\\", "/"))
    return {"type": f"{type(error).__module__}.{type(error).__name__}",
            "errno": getattr(error, "errno", None),
            "winerror": getattr(error, "winerror", None), "file": name or None}


def _chain(error: BaseException) -> list[dict]:
    chain, seen = [], set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        chain.append(_link(error))
        error = error.__cause__ or error.__context__
    return chain


def _stage(error: BaseException) -> list[str]:
    deepest = error
    while deepest.__cause__ is not None:
        deepest = deepest.__cause__
    return [f"{os.path.basename(frame.filename)}:{frame.name}:{frame.lineno}"
            for frame in traceback.extract_tb(deepest.__traceback__)[-_FRAMES:]]


@contextmanager
def watching() -> Iterator[list[dict]]:
    """Record, while inside, each exception the API answers as `store_error`."""
    seen: list[dict] = []
    original = http_api.refusal_from_exception

    def probe(error: Exception):
        refusal = original(error)
        if refusal.code == "store_error":
            seen.append({"stage": _stage(error), "chain": _chain(error)})
        return refusal

    http_api.refusal_from_exception = probe
    try:
        yield seen
    finally:
        http_api.refusal_from_exception = original


def describe(seen: list[dict]) -> str:
    """One line per record: the stage, then the chain from the answer down to the cause."""
    lines = []
    for record in seen:
        chain = " <- ".join(
            f"{link['type'].rsplit('.', 1)[-1]}(errno={link['errno']}, "
            f"winerror={link['winerror']}, file={link['file']})" for link in record["chain"])
        lines.append(f"stage={' > '.join(record['stage'])}; chain={chain}")
    return "\n".join(lines) or "no store_error answer was made"
