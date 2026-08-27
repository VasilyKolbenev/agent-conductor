"""The parent's end of a child's stdin, with one step of the delivery made to fail.

Three tests used to reach ``incomplete`` by asking the OPERATING SYSTEM to break
the write: hand a child that reads nothing more bytes than a pipe can hold, and
wait for the parent's write to fail. Remote run #10 showed what that measures.
Windows breaks at a few kilobytes; a Linux pipe takes 64 KiB whole -- which is
the very ceiling this build bounds an instruction body at -- so on Linux the
write, the flush and the close all SUCCEEDED and the runner reported
``delivered``. That is exactly what ``delivered`` is documented to mean, and it
was not what the tests said. The assertion was about a kernel constant, and no
payload this build is allowed to send can outrun it.

So the failure is moved to the place that can state it. ``_Owned._feed`` makes
three calls and raises the state to ``delivered`` only if all three finished: it
WRITES in a loop, because a raw stream may take fewer bytes than it was offered;
it FLUSHES; and it CLOSES, and that close is the child's end of input rather
than cleanup after it. Each double built here fails exactly one of those three
and nothing else -- on every operating system, at any payload size, with no
timing in it anywhere.

**The carrier.** A double built with one wraps a REAL child's stdin: the bytes it
accepts are passed through, and the close is passed through ALWAYS, before any
refusal of its own. That is deliberate twice over. A child blocked on a read to
EOF that never comes is a hang rather than a failure; and a truncated delivery is
then witnessed from the FAR side, by a real child reporting the short payload it
really received, instead of being asserted about a pipe nobody can see.

Nothing here decides what ``delivered`` MEANS. It decides only where the step
that fails is, so that the meaning can be read on every system this build runs on.
"""
from __future__ import annotations

from collections.abc import Callable

from conductor.command.adapters import process as process_module


class ChildInput:
    """A stdin stream with at most one of the three delivery steps made to fail.

    Only the three names ``_Owned._feed`` uses are offered -- ``write``,
    ``flush``, ``close``. A feed that reached for a fourth would fail here rather
    than pass against a double richer than the thing it stands in for.
    """

    def __init__(self, *, carrier=None, ceiling: int | None = None,
                 per_write: int | None = None, flush_fails: bool = False,
                 close_fails: bool = False) -> None:
        self.carrier = carrier
        #: Take this many bytes in total and then take nothing more, ever.
        self.ceiling = ceiling
        #: Take at most this many bytes per call, and the whole payload in the end.
        self.per_write = per_write
        self.flush_fails = flush_fails
        self.close_fails = close_fails
        #: What this side really accepted, and how often each step ran. A test
        #: reads these rather than inferring the steps from the state they set.
        self.written = bytearray()
        self.writes = 0
        self.flushes = 0
        self.closes = 0

    def _room(self, offered: int) -> int:
        room = offered
        if self.ceiling is not None:
            room = min(room, self.ceiling - len(self.written))
        if self.per_write is not None:
            room = min(room, self.per_write)
        return room

    def write(self, view) -> int:
        self.writes += 1
        room = self._room(len(view))
        if room <= 0:
            return 0
        chunk = bytes(view[:room])
        if self.carrier is not None:
            # A raw pipe may itself take fewer bytes than it is offered, so what
            # REALLY left is what is reported back: the feed's own loop is what
            # then carries the rest, which is the relation being observed.
            chunk = chunk[:self.carrier.write(chunk)]
        self.written += chunk
        return len(chunk)

    def flush(self) -> None:
        self.flushes += 1
        if self.flush_fails:
            raise OSError("the stream refused to flush")
        if self.carrier is not None:
            self.carrier.flush()

    def close(self) -> None:
        self.closes += 1
        # The carrier is closed BEFORE any refusal of this double's own: that
        # close is the child's end of input, and a child still blocked on a read
        # to EOF would hang the run rather than fail it.
        if self.carrier is not None:
            self.carrier.close()
        if self.close_fails:
            raise OSError("the descriptor was already gone")


def every_child_input(
        monkeypatch, build: Callable[[object], ChildInput]) -> list[ChildInput]:
    """Give every PIPED spawn from here on a stdin that ``build`` makes of the real one.

    Only a piped spawn is touched. A spawn made with no payload has no stdin at
    all -- the version preflight every native pin runs is one of those -- so the
    fault reaches the task spawn and nothing else, without the test having to
    know how many spawns a road makes.

    The doubles are returned in spawn order, so a test can read what really left
    this side instead of inferring it from the state the feed set.
    """
    made: list[ChildInput] = []
    real_popen = process_module.subprocess.Popen

    def spawn(*args, **kwargs):
        proc = real_popen(*args, **kwargs)
        if proc.stdin is not None:
            proc.stdin = build(proc.stdin)
            made.append(proc.stdin)
        return proc

    monkeypatch.setattr(process_module.subprocess, "Popen", spawn)
    return made
