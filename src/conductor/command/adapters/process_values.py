"""Pure process argument/input validation; the execution door stays in process.py."""
from __future__ import annotations
from collections.abc import Sequence


def validated_argv(value: object, error: type[Exception]) -> tuple[str, ...]:
    """A non-empty list of NUL-free strings; a shell string is not a command."""
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise error("argv must be a list of strings, never a shell string")
    rows = tuple(value)
    if not rows:
        raise error("argv must name at least the executable to run")
    for item in rows:
        if not isinstance(item, str):
            raise error(f"argv element must be a string, got {item!r}")
        if "\x00" in item:
            raise error("argv element must not contain NUL")
    return rows


def validated_stdin(value: object, error: type[Exception], limit: int) -> bytes | None:
    """Nothing, or a bounded NUL-free byte payload the child will read whole.

    Refused BEFORE the spawn, every time, because the alternative is a child
    that already exists when the input turns out to be inadmissible -- and a
    child that exists has already been handed the workspace.

    NUL is refused for the same reason argv refuses it: this payload is an
    instruction body, a text artefact, and an embedded NUL is either a truncation
    a downstream reader will act on or something that was never text.
    """
    if value is None:
        return None
    if type(value) is not bytes:
        raise error("stdin_bytes must be bytes or None, never text")
    if len(value) > limit:
        # The LENGTH is named and the content is not; this message is a road out.
        raise error(
            f"stdin_bytes is {len(value)} bytes, past the {limit} ceiling")
    if b"\x00" in value:
        raise error("stdin_bytes must not contain NUL")
    return value
