"""Getting bytes onto a disk so that a crash can never publish half of them.

Split out of ``run_store`` when that module reached its line cap, along a seam
it already had rather than one invented for the split: everything here is about
FILES, and nothing here knows what a run, a record or a journal is. The store
imports them back under their old names, so no caller anywhere learns that the
split happened -- the same shape ``store_errors`` and ``graph_values`` already
have.

Four ways to write, and each is a different promise:

- ``_exclusive_bytes`` publishes a file all-or-nothing AND only if the name is
  unclaimed. Staged privately, fsynced, then linked into place, because
  ``os.link`` refuses a taken name on every platform this product supports --
  which is what makes exclusivity the arbiter between two writers racing for one
  identity rather than whoever wrote last.
- ``_append_bytes`` adds to a file already there, in one open, one write and one
  fsync.
- ``_replace_bytes`` swaps a file's whole content atomically.
- ``_write_all`` underlies all three and is the reason they are promises at all:
  ``os.write`` may write FEWER bytes than it was given, so a single call is a
  truncated record waiting to happen.

``_O_BINARY`` is here for the same reason and is not portability boilerplate: on
Windows the CRT translates every LF written through a text-mode descriptor into
CRLF, and the journal is the one durable file this package APPENDS to rather
than stages. Without the flag one record's two durable spellings would differ by
a carriage return each.

Like the module it came from, this has no contract, adapter or server imports
beyond the two error types it raises and the one canonical spelling it writes.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .contracts import ContractError, canonical_json
from .store_errors import CorruptRun, StoreError


def _canonical_bytes(value: object) -> bytes:
    try:
        return (canonical_json(value) + "\n").encode("utf-8")
    except ContractError as e:
        raise StoreError(f"value is not canonical JSON: {e}") from e


def _write_all(fd: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(fd, payload[offset:])
        if written <= 0:
            raise OSError("write returned no progress")
        offset += written


def _exclusive_bytes(path: Path, payload: bytes) -> None:
    """Publish `payload` at `path` all-or-nothing, and only if `path` is unclaimed.

    The content is staged under a private name and fsynced first, so a crash can
    never publish a half-written or zero-length file; `os.link` then refuses an
    already-claimed name on every supported platform, which keeps exclusivity the
    arbiter between two writers racing for the same identity.
    """
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    stage = Path(raw)
    try:
        _write_all(fd, payload)
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.link(stage, path)
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            stage.unlink()
        except FileNotFoundError:
            pass


#: Windows opens a descriptor in text mode unless told otherwise, and the CRT
#: then translates every LF written through it into CRLF. `tempfile.mkstemp`
#: already sets this flag for the staged writes, so without it here the two
#: durable spellings of one record would differ by a CR each: the journal line is
#: appended, while `run.json`, `config.json` and every `decisions/*.json` are
#: staged. Absent on POSIX, where `getattr` supplies the no-op 0.
_O_BINARY = getattr(os, "O_BINARY", 0)


def _append_bytes(path: Path, payload: bytes) -> None:
    fd: int | None = None
    try:
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | _O_BINARY)
        _write_all(fd, payload)
        os.fsync(fd)
    finally:
        if fd is not None:
            os.close(fd)


def _replace_bytes(path: Path, payload: bytes) -> None:
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp = Path(raw)
    try:
        _write_all(fd, payload)
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.replace(temp, path)
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def _fsync_dir(path: Path) -> None:
    """Best-effort directory durability; Windows cannot open directories this way."""
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _json_object(path: Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as e:
        raise CorruptRun(f"{description} is unreadable: {e}") from e
    if not isinstance(value, dict):
        raise CorruptRun(f"{description} must be a JSON object")
    return value
