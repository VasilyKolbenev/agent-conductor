"""The task of a file-channel provider, written once into the home of its attempt (I1).

A vendor whose headless mode reads its prompt only from a file (``--prompt-file <path>``) cannot
be handed the task on stdin, and the command line is the one place the task must never stand. So
the task is ONE new file in the folder of the attempt itself, under a name this build fixes
(``harness_profile.TASK_FILE_NAME``), and the argv names it by its absolute path (``path_in``): a
function of the home alone, which carries no run, no action and no word of the task -- as the
``-o`` file of Codex names its final message. The home is a fresh folder this build minted, it is
the folder the child is given rights on, and it goes with the file in it when the attempt ends.

``place`` is called from ONE place, ``headless_spec.attempt_spec``, because every road (a home of
the project, a relay home, a dispatch, a review) builds the spec its child starts from there. It is
called for no other folder: the home is either a direct child of the project's home root, or a
relay home (``<relay>/<16 hex>/<letter>-<16 hex>``), and never a login folder or the work tree.

A refusal is a ``ProcessRunnerError`` (``TaskFileRefused``), the family every road already turns
into a value or a fixed sentence. A raw ``OSError`` would not be one: raised inside the shared login
lease it would mark the lease uncertain until the machine restarts (``relay_attempt``). So EVERY
failure of the disk is wrapped, the cleanup of a failed placement never raises, and the refusal
carries a closed word and no path, no byte of the task and no system message.

What is proved before anything is written: the payload is bytes, within the stdin bound, free of
NUL, strict UTF-8 and not only white space (the vendor trims a prompt and refuses an empty one).
What is proved after: the file read back is the payload, whole and exactly, and has one link. A
file that is not is removed, but only a file THIS call created -- one that was already standing is
refused and left as it was. The file is created new (``O_EXCL``) with the rights of its owner; it
is not read-only to the child, whose rights are the home's, and it is written once and not changed.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from .harness_profile import TASK_FILE_NAME
from .process import STDIN_LIMIT
from .process_errors import ProcessRunnerError
from .relay_home import HOME_NAME, RELAY_DIR

#: The key folder of a project in the relay folder: 16 lower-case hex (`relay_home.relay_key`).
_KEY = re.compile(r"[0-9a-f]{16}\Z")
#: What a refusal says first; a closed word follows it and nothing else.
REFUSED = "the task file could not be placed"


class TaskFileRefused(ProcessRunnerError):
    """The task could not be placed: ``home``, ``payload`` or ``write``, and nothing more."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"{REFUSED} ({reason})")
        self.reason = reason


def path_in(home: str | os.PathLike) -> str:
    """The path of the task file of an attempt home: the home, and the one fixed name."""
    return str(Path(home) / TASK_FILE_NAME)


def place(home: str | os.PathLike, payload: bytes, homes_root: str | os.PathLike) -> str:
    """Write the task into ``home`` as a new file; its path.

    Args:
        home: The attempt home: a direct child of ``homes_root``, or a relay home.
        payload: The task, as the bytes the file is to hold.
        homes_root: The home root of the project (``HarnessWorkspace.homes_root``).

    Raises:
        TaskFileRefused: The home is neither of the two, the payload is no task, or the disk
            could not hold it exactly. Nothing this call created is left standing.
    """
    where = _attempt_home(home, homes_root)
    _proved_task(payload)
    path = path_in(where)
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    descriptor, made = -1, False
    try:
        descriptor = os.open(path, flags, 0o600)
        made = True
        _write_all(descriptor, payload)
        _read_back(descriptor, payload)
        finished, descriptor = descriptor, -1
        os.close(finished)
    except (OSError, ValueError, UnicodeError):
        _take_back(path, descriptor, made)
        raise TaskFileRefused("write") from None
    return path


def _attempt_home(home: object, homes_root: object) -> Path:
    """The home, if it is a place this build writes a task into; else a refusal."""
    try:
        found, base = Path(home), Path(homes_root)  # type: ignore[arg-type]
    except TypeError:
        raise TaskFileRefused("home") from None
    key = found.parent
    of_the_project = key == base
    relay = (HOME_NAME.fullmatch(found.name) is not None and _KEY.fullmatch(key.name) is not None
             and key.parent.name.casefold() == RELAY_DIR)
    if not (of_the_project or relay):
        raise TaskFileRefused("home")
    return found


def _proved_task(payload: object) -> None:
    """Refuse anything that is not a task a vendor can be told to read."""
    if type(payload) is not bytes or not 0 < len(payload) <= STDIN_LIMIT or b"\x00" in payload:
        raise TaskFileRefused("payload")
    try:
        text = payload.decode("utf-8")
    except UnicodeError:
        raise TaskFileRefused("payload") from None
    if not text.strip():
        raise TaskFileRefused("payload")


def _write_all(descriptor: int, payload: bytes) -> None:
    """Write every byte; a write that takes none is an error and not a loop."""
    written = 0
    while written < len(payload):
        took = os.write(descriptor, payload[written:])
        if took <= 0:
            raise OSError("the file took no byte")
        written += took


def _read_back(descriptor: int, payload: bytes) -> None:
    """The file holds exactly the payload, and has one link: or an error."""
    os.lseek(descriptor, 0, os.SEEK_SET)
    back = b""
    while len(back) <= len(payload):
        chunk = os.read(descriptor, len(payload) + 1 - len(back))
        if not chunk:
            break
        back += chunk
    if back != payload:
        raise OSError("the file is not what was written")
    if os.fstat(descriptor).st_nlink != 1:
        raise OSError("the file has another link")


def _take_back(path: str, descriptor: int, made: bool) -> None:
    """Close what is open and remove what THIS call made; a failure of either is not reported."""
    if descriptor >= 0:
        try:
            os.close(descriptor)
        except OSError:
            pass
    if made:
        try:
            os.unlink(path)
        except OSError:
            pass
