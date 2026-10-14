"""A runner whose execution-boundary entry is a recording double (R5, lane L's side).

The host's entry is ``ProcessRunner.container_profile``: a context manager that yields the trusted
launch value and the attempt's own folders, and that refuses to enter or to leave. This double
stands in for it and keeps a record of every use, so a test can prove what the ADAPTERS do with
the entry without a Windows host, a container profile or a live owner:

- whether a child was started inside the block or outside it, in what order, and with which
  launch value and environment;
- what the adapter asked the entry for (the mode, the network, the folders);
- that a refused entry, or a refused exit, reaches the adapter as the entry's own error.

It confines nothing. A child that is started with a launch value runs plainly, with the value
removed from its spec, so the harness fakes (``tests/_fake*``) can still be real executables. The
witness that a confined agent cannot write the project root or the owner's ``.git`` is the host's
native one (``tests/test_process_acl_native.py``), not this file's.
"""
from __future__ import annotations

import inspect
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path

from conductor.command.adapters.process import ProcessRunner
from conductor.command.adapters.process_boundary import WindowsContainer

#: A well-formed AppContainer SID, which is all ``WindowsContainer`` checks.
SID = "S-1-15-2-1-2-3-4-5-6-7"


def takes_the_call(entry) -> bool:
    """Whether ``entry``, a runner's ``container_profile``, binds the call the adapters make.

    Read off the signature by the one rule Python itself uses to bind a call, and spelled out
    here rather than taken from the product: the tests compare the product's answer with it.
    """
    try:
        inspect.signature(entry).bind(None, mode="dispatch", internet_client=True, folders=None)
    except TypeError:
        return False
    return True


@dataclass
class Entry:
    """One call of the entry: what the adapter asked for."""

    mode: str | None
    internet_client: bool
    folders: object
    paths: dict[str, Path | None] | None = None


@dataclass(frozen=True)
class Run:
    """One child the runner was asked to start."""

    argv: tuple[str, ...]
    cwd: str
    env: dict[str, str]
    boundary: WindowsContainer | None
    inside: bool


class BoundaryRunner(ProcessRunner):
    """A ``ProcessRunner`` over a recording boundary entry; see the module docstring.

    ``entries``, ``runs`` and ``events`` are the record; ``enter_error`` and ``exit_error``, when
    set, are raised when the block is entered and when it is left after a clean body.
    """

    def __init__(self, project_root, *, scratch, environ=None, spawns_allowed=True):
        super().__init__(project_root, environ=environ, spawns_allowed=spawns_allowed)
        self._scratch = Path(scratch)
        self._open = 0
        self.entries: list[Entry] = []
        self.runs: list[Run] = []
        self.events: list[str] = []
        self.enter_error: BaseException | None = None
        self.exit_error: BaseException | None = None

    @contextmanager
    def container_profile(self, *, internet_client=False, mode=None, folders=None):
        entry = Entry(mode, internet_client, folders)
        self.entries.append(entry)
        self.events.append("enter")
        if self.enter_error is not None:
            raise self.enter_error
        runtime = self._scratch / f"attempt-{len(self.entries)}" / "runtime"
        runtime.mkdir(parents=True)
        entry.paths = {
            "parent": runtime.parent, "runtime": runtime,
            "work": self._root / folders.work,
            "home": None if folders.home is None else self._root / folders.home,
            "install": Path(folders.install)}
        self._open += 1
        try:
            yield WindowsContainer(SID, internet_client), entry.paths
        finally:
            self._open -= 1
            self.events.append("exit")
        if self.exit_error is not None:
            raise self.exit_error

    def run(self, spec):  # type: ignore[override]
        inside = self._open > 0
        self.runs.append(Run(spec.argv, spec.cwd, dict(spec.env), spec.boundary, inside))
        self.events.append("run-inside" if inside else "run-outside")
        return super().run(replace(spec, boundary=None))


def recording(adapter, scratch, *, enter_error=None, exit_error=None) -> BoundaryRunner:
    """Put a recording boundary entry under a harness adapter, without confining it.

    The adapter keeps its pin, its root and its allowed environment; only the runner it spawns
    through is replaced, by one that shares them.
    """
    old = adapter._runner
    runner = BoundaryRunner(
        old._root, scratch=scratch, environ=old._environ, spawns_allowed=old._spawns_allowed)
    runner.enter_error, runner.exit_error = enter_error, exit_error
    adapter._runner = runner
    return runner


def confined(adapter, scratch, *, platform: str = "win32", enter_error=None, exit_error=None):
    """``recording`` and then ``confine`` the adapter for ``platform``."""
    runner = recording(adapter, scratch, enter_error=enter_error, exit_error=exit_error)
    adapter.confine(platform)
    return runner


def recording_runners(monkeypatch, scratch) -> list[BoundaryRunner]:
    """Make the provider door build a recording boundary entry in place of the shipped runner.

    The shipped runner's entry cannot take the attempt's own folders until the runner's change
    merges, and an adapter over it answers that it has no boundary (the fact follows the entry).
    What the door does with a platform is asked of a runner whose entry can be called. Returns
    the list the door's runners are appended to.
    """
    from conductor.command import providers as provider_factory

    made: list[BoundaryRunner] = []

    def runner(base, environ=None, spawns_allowed=True):
        made.append(BoundaryRunner(
            base, scratch=scratch, environ=environ, spawns_allowed=spawns_allowed))
        return made[-1]

    monkeypatch.setattr(provider_factory, "ProcessRunner", runner)
    return made
