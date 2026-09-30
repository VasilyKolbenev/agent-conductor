"""The frames of `GET /hub/events`: identifiers and nothing else (spec 4.6.4).

A frame tells the page WHICH route to read again; it is never a fact on the screen. There are six
kinds, each with its own keys, and the identifiers are held to the grammar of 4.6.3, so a frame of
another kind or with another key cannot be built. Each client has its own mailbox: frames are kept
in order and once (a burst of the same frame is one frame), and a client that falls too far behind
gets the three plain frames that make it read everything again instead of an unbounded queue.
"""
from __future__ import annotations

import re
import threading
from collections.abc import Mapping
from types import MappingProxyType

from conductor.command.contracts import canonical_json

#: Kind -> the keys of its frame besides `kind` (4.6.4). Each key is an identifier.
FRAME_KEYS: Mapping[str, tuple[str, ...]] = MappingProxyType({
    "projects": (), "project": ("project_id",), "limits": (), "setup": (),
    "operation": ("operation_id",), "pick": ("pick_id",)})
_GRAMMAR = {"project_id": re.compile(r"[0-9a-f]{32}"),
            "operation_id": re.compile(r"operation-[0-9a-f]{32}"),
            "pick_id": re.compile(r"pick-[0-9a-f]{32}")}
MAX_PENDING = 256
#: What a client that fell behind is sent instead of what it missed: read everything again.
CATCH_UP = ({"kind": "projects"}, {"kind": "limits"}, {"kind": "setup"})


def frame(kind: str, **ids: str) -> dict[str, str]:
    """Build one frame.

    Raises:
        ValueError: `kind` is not one of the six, the keys are not exactly its own, or an
            identifier is outside the grammar of 4.6.3.
    """
    if kind not in FRAME_KEYS or set(ids) != set(FRAME_KEYS[kind]):
        raise ValueError(f"{kind!r} is not a frame with the keys {sorted(ids)}")
    for name, value in ids.items():
        if not isinstance(value, str) or _GRAMMAR[name].fullmatch(value) is None:
            raise ValueError(f"{name} is not an identifier of the grammar of 4.6.3")
    return {"kind": kind, **ids}


def encode(one: Mapping[str, str]) -> bytes:
    """The bytes of one frame on the wire: `data: <canonical JSON>` and a blank line."""
    return b"data: " + canonical_json(dict(one)).encode("utf-8") + b"\n\n"


class Mailbox:
    """One client's pending frames: ordered, each once, bounded."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._pending: dict[tuple[tuple[str, str], ...], dict[str, str]] = {}

    def publish(self, one: Mapping[str, str]) -> None:
        key = tuple(sorted(one.items()))
        with self._lock:
            if len(self._pending) >= MAX_PENDING and key not in self._pending:
                self._pending = {tuple(sorted(f.items())): dict(f) for f in CATCH_UP}
            else:
                self._pending.setdefault(key, dict(one))
            self._event.set()

    def wake(self) -> None:
        """Wake the waiter without a frame (shutdown)."""
        self._event.set()

    def wait(self, timeout: float) -> bool:
        """Wait for a frame or a wake; `False` on timeout."""
        return self._event.wait(timeout)

    def drain(self) -> tuple[bytes, ...]:
        """The pending frames as bytes, in the order they came; the mailbox is empty after."""
        with self._lock:
            frames = tuple(encode(one) for one in self._pending.values())
            self._pending = {}
            self._event.clear()
            return frames


class EventBus:
    """The mailboxes of the clients connected now."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._boxes: set[Mailbox] = set()

    def register(self) -> Mailbox:
        """Add one client; return its private mailbox."""
        box = Mailbox()
        with self._lock:
            self._boxes.add(box)
        return box

    def unregister(self, box: Mailbox) -> None:
        """Drop one client (idempotent)."""
        with self._lock:
            self._boxes.discard(box)

    def publish(self, kind: str, **ids: str) -> None:
        """Build a frame and put it in every mailbox."""
        one = frame(kind, **ids)
        with self._lock:
            boxes = tuple(self._boxes)
        for box in boxes:
            box.publish(one)

    def wake_all(self) -> None:
        """Wake every waiting client without a frame."""
        with self._lock:
            boxes = tuple(self._boxes)
        for box in boxes:
            box.wake()

    @property
    def clients(self) -> int:
        """How many clients are connected."""
        with self._lock:
            return len(self._boxes)
