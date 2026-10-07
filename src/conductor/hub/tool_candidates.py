"""The git and gh candidates the hub offers for a pin: found once, never shown as a path (8.8).

The hub looks for each tool one time in its life: `shutil.which` and the standard folders of the
spec. Each file found is read for its version the way a pin reads it (`tool_pins.probe_version`:
the absolute path, `--version`, the environment `tool_env` builds, nothing else) and kept under an
id this hub made up. The page is shown the id, the last folder and file name and the version, and
nothing else; the path stays here, and the pin route asks for it by id. A tool installed after
the pass is found by the next hub, not by this one: there is no way to search again.
"""
from __future__ import annotations

import ntpath
import os
import posixpath
import secrets
import shutil
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from conductor import tool_pins

#: The standard folders of spec 8.8, by OS kind and tool, in the order they are looked at.
STANDARD: Mapping[str, Mapping[str, tuple[str, ...]]] = {
    "nt": {"git": (r"C:\Program Files\Git\cmd",), "gh": (r"C:\Program Files\GitHub CLI",)},
    "posix": {tool: ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin")
              for tool in tool_pins.TOOLS}}


def standard_paths(tool: str, osname: str) -> list[str]:
    """The files the standard folders would hold for `tool` on this kind of OS (`nt`, `posix`).

    Only a `.exe` is looked for on Windows: `CreateProcess` would run a `.cmd` shim through the
    command interpreter, which is not the program a person was shown.
    """
    windows = osname == "nt"
    join = ntpath.join if windows else posixpath.join
    name = tool + (".exe" if windows else "")
    return [join(folder, name) for folder in STANDARD["nt" if windows else "posix"][tool]]


@dataclass(frozen=True)
class Candidate:
    """One tool the hub found: the id it is offered under, where it is and what it says."""

    candidate_id: str
    tool: str
    path: str
    display: str
    version: str


class ToolCandidates:
    """The candidates of one hub: found by one pass, read by the setup and by the pin route.

    The table is built whole by `discover` and replaced in one assignment, so a reader never
    waits for the pass (it may run for seconds, a probe at a time) and never sees half of it.
    """

    def __init__(self, folder: Path | str, *,
                 which: Callable[[str], str | None] = shutil.which,
                 isfile: Callable[[str], bool] = os.path.isfile,
                 probe: Callable[..., str] = tool_pins.probe_version, osname: str = os.name,
                 token: Callable[[], str] = lambda: secrets.token_hex(16),
                 run: tool_pins.Runner | None = None,
                 source: Mapping[str, str] | None = None) -> None:
        """Make the candidates of a hub; nothing is looked for until `discover` runs.

        Args:
            folder: The hub's folder (the version probe builds its environment from it).
            which: Finds a tool on the search path; `shutil.which` unless a test stands in.
            isfile: Whether a path is a file; `os.path.isfile` unless a test stands in.
            probe: Reads a version; `tool_pins.probe_version` unless a test stands in.
            osname: `nt` or `posix`: which standard folders and which file names count.
            token: Makes the 32 hexadecimal characters of an id.
            run: Runs `<path> --version`; the real process unless a test stands in.
            source: The environment the probe's own is built from; `os.environ` by default.
        """
        self._folder, self._which, self._isfile = Path(folder), which, isfile
        self._probe, self._osname, self._token = probe, osname, token
        self._run, self._source = run, source
        self._pass = threading.Lock()
        self._done = False
        self._table: Mapping[str, tuple[Candidate, ...]] = {}

    def discover(self) -> None:
        """The one pass: `which` and the standard folders, each file once, the readable kept.

        A second call, from any thread, returns when the first has ended and does nothing.
        """
        with self._pass:
            if self._done:
                return
            self._table = {tool: tuple(self._found(tool)) for tool in tool_pins.TOOLS}
            self._done = True

    def start(self, on_done: Callable[[], None]) -> threading.Thread:
        """Run `discover` on a daemon thread, then call `on_done` once (the page reads again)."""
        def run() -> None:
            self.discover()
            on_done()

        thread = threading.Thread(target=run, name="hub-tool-candidates", daemon=True)
        thread.start()
        return thread

    def offered(self, tool: str, *, settled: bool) -> list[dict[str, Any]]:
        """The rows of `GET /hub/setup` for `tool`: none while it is settled, never a path."""
        if settled:
            return []
        return [{"candidate_id": one.candidate_id, "display": one.display, "version": one.version}
                for one in self._table.get(tool, ())]

    def get(self, tool: str, candidate_id: str) -> Candidate | None:
        """The candidate of `tool` this hub issued under `candidate_id`, or `None`."""
        return next((one for one in self._table.get(tool, ())
                     if one.candidate_id == candidate_id), None)

    # -- the pass ----------------------------------------------------------------------------------

    def _found(self, tool: str) -> list[Candidate]:
        found, seen = [], set()
        for path in self._searched(tool):
            key = _same_file(path)
            if key is None or key in seen:
                continue
            seen.add(key)
            one = self._candidate(tool, path)
            if one is not None:
                found.append(one)
        return found

    def _searched(self, tool: str) -> list[str]:
        """The absolute, existing files to look at, the `which` result first."""
        named = self._which(tool)
        usable = (self._usable(path) for path in [named, *standard_paths(tool, self._osname)])
        return [path for path in usable if path is not None]

    def _usable(self, path: object) -> str | None:
        if not (isinstance(path, str) and path and os.path.isabs(path)):
            return None
        path = os.path.normpath(path)
        if self._osname == "nt" and not path.lower().endswith(".exe"):
            return None
        return path if self._isfile(path) else None

    def _candidate(self, tool: str, path: str) -> Candidate | None:
        try:
            version = self._probe(tool, path, folder=self._folder, run=self._run,
                                  source=self._source)
        except (tool_pins.ToolPinError, OSError, ValueError):
            return None                      # a list of candidates is a convenience, never a gate
        where = Path(path)
        return Candidate("cand-" + self._token(), tool, path,
                         f"{where.parent.name}{os.sep}{where.name}", version)


def _same_file(path: str) -> str | None:
    """The key two spellings of one file share, or `None` when the path cannot be resolved."""
    try:
        return os.path.normcase(os.path.realpath(path))
    except (OSError, ValueError):
        return None
