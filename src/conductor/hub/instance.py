"""The one live hub: `hub.lock` held for the life of the process, `hub.json` saying where it is.

Spec 4.1.7: `hub.lock` is held all the time the hub lives, so a second `conduct hub` finds it
held, prints the URL of the live hub from `hub.json` and exits 0. The lock is the OS's and is
freed when its holder dies, so a `hub.json` left by a hub that died never blocks the next one:
the lock decides who is live, and the file only says where. `hub.json` is
`{pid, process_started, port, url, started_at}`, written by the hub that holds the lock and
removed by that same hub when it leaves.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from conductor import atomic_replace, process_identity
from conductor.hub import home, lockfile
from conductor.ownership_native import NativeHold

LOCK_NAME = "hub.lock"
JSON_NAME = "hub.json"
_KEYS = frozenset({"pid", "process_started", "port", "url", "started_at"})
_INSTANT = "%Y-%m-%dT%H:%M:%SZ"


class HubAlreadyRunning(Exception):
    """Another hub holds `hub.lock`; `url` is where it says it is, or `None`."""

    def __init__(self, url: str | None) -> None:
        self.url = url
        where = f" at {url}" if url else ""
        super().__init__(f"another hub is running{where}")


class HubLockLost(RuntimeError):
    """This hub no longer holds `hub.lock`: it was closed, or the file was replaced."""


@dataclass(frozen=True)
class HubJson:
    """The content of `hub.json`."""

    pid: int
    process_started: str | None
    port: int
    url: str
    started_at: str


def _folder(folder: Path | str | None) -> Path:
    return home.conduct_home_path() if folder is None else Path(folder)


def _record(document: object) -> HubJson:
    if not isinstance(document, dict) or set(document) != _KEYS:
        raise ValueError("not exactly the keys of hub.json")
    pid, port, url = document["pid"], document["port"], document["url"]
    if type(pid) is not int or pid < 1 or type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("pid and port must be whole numbers in range")
    if url != f"http://127.0.0.1:{port}/":
        raise ValueError("url must be the loopback address of the port")
    started = document["process_started"]
    if started is not None and not isinstance(started, str):
        raise ValueError("process_started must be null or text")
    datetime.strptime(str(document["started_at"]), _INSTANT)
    return HubJson(pid, started, port, url, document["started_at"])


def read_hub_json(folder: Path | str | None = None) -> HubJson | None:
    """`hub.json` as written, or `None` when it is absent or is not the record."""
    try:
        return _record(json.loads((_folder(folder) / JSON_NAME).read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        return None


class HubInstance:
    """The hold on `hub.lock` of the hub that is live: take it with `acquire`."""

    def __init__(self, folder: Path, hold: NativeHold) -> None:
        self.folder = folder
        self._hold = hold

    @classmethod
    def acquire(cls, folder: Path | str | None = None) -> HubInstance:
        """Take `hub.lock`, making the folder and the file when they are absent.

        Raises:
            HubAlreadyRunning: Another hub holds the lock; `url` is its address when
                `hub.json` says one.
            OSError: The folder or the lock file could not be made.
        """
        where = _folder(folder)
        where.mkdir(mode=0o700, parents=True, exist_ok=True)
        lockfile.make(where / LOCK_NAME)
        try:
            hold = lockfile.take(where / LOCK_NAME, attempts=1, pause=0)
        except lockfile.LockBusy:
            live = read_hub_json(where)
            raise HubAlreadyRunning(live.url if live else None) from None
        return cls(where, hold)

    @property
    def held(self) -> bool:
        """Whether this hub still holds the lock."""
        return not self._hold.closed

    def check(self) -> None:
        """Raise `HubLockLost` unless the lock is still this hub's and still names its file."""
        if not self.held:
            raise HubLockLost("hub.lock is no longer held by this hub")
        try:
            self._hold.check()
        except OSError as error:
            raise HubLockLost(f"hub.lock is not the file this hub took: {error}") from error

    def publish(self, port: int, *, now: str | None = None) -> HubJson:
        """Write `hub.json` for the port this hub is serving on.

        Raises:
            HubLockLost: The lock is no longer held.
            OSError: The file could not be written.
        """
        self.check()
        moment = now or datetime.now(timezone.utc).strftime(_INSTANT)
        started = process_identity.started_of(os.getpid())
        written = HubJson(os.getpid(), started, port, f"http://127.0.0.1:{port}/", moment)
        document = {"pid": written.pid, "process_started": written.process_started,
                    "port": written.port, "url": written.url, "started_at": written.started_at}
        payload = json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n"
        atomic_replace.replace_bytes(self.folder / JSON_NAME, payload.encode("utf-8"))
        return written

    def close(self) -> None:
        """Remove the `hub.json` this hub wrote and let go of the lock; closing twice is fine."""
        if not self.held:
            return
        ours = read_hub_json(self.folder)
        if ours is not None and ours.pid == os.getpid():
            try:
                (self.folder / JSON_NAME).unlink()
            except OSError:
                pass                      # a stale hub.json is harmless: the lock decides
        self._hold.close()
