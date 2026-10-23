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
import shutil
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path

from conductor.command.adapters.process import ProcessRunner
from conductor.command.adapters.process_boundary import WindowsContainer
from conductor.command.adapters.process_profile import ProfileRefused
from conductor.command.adapters.relay_home import relay_home_shape, relay_root_for
from conductor.ownership_native import identity

#: A well-formed AppContainer SID, which is all ``WindowsContainer`` checks.
SID = "S-1-15-2-1-2-3-4-5-6-7"

#: What the product adds in front of a Node entry inside the boundary (H, DSH argv). The harness
#: fake for DSH is a Python script, which refuses these, so the double drops them from the argv it
#: really executes; the argv it RECORDS keeps them.
NODE_FLAGS = ("--preserve-symlinks", "--preserve-symlinks-main")

#: Where each harness's pinned file sits under the owner's install tree, as measured on 14.10
#: (H contract, section 5): ``harnesses/<name>/<version>``, and for two of the five a deeper
#: path to the file itself. The fixtures of the five transport suites install their fake there,
#: so the install folder an adapter asks for is a fact of the layout and not of the fake.
LAYOUT = {
    "claude-code": ("2.1.239", ()),
    "codex": ("0.112.0", ("node_modules", "@openai", "codex-win32-x64", "vendor",
                          "x86_64-pc-windows-msvc", "codex")),
    "grok-build": ("1.0.5", ()),
    "kimi-code": ("0.38.0", ()),
    "deepseek-harness": ("0.1.0-rc.7-pnpm", ("node_modules", "@deepseek-ai", "dsh", "lib")),
}


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


def version_folder(base, provider_id: str) -> Path:
    """The folder the boundary must be able to read for this harness: ``harnesses/<name>/<v>``."""
    return Path(base) / "harnesses" / provider_id / LAYOUT[provider_id][0]


def pin_dir(base, provider_id: str) -> Path:
    """The folder the pinned file itself sits in, at the depth the real install puts it."""
    return version_folder(base, provider_id).joinpath(*LAYOUT[provider_id][1])


def installed_outside_the_tree(adapter, base) -> None:
    """Re-pin a native-binary adapter to a copy of its executable outside ``harnesses/<n>/<v>``.

    The pin is still an absolute file that runs, so every other fact of the launch holds; only the
    install folder cannot be named from it.
    """
    elsewhere = Path(base) / "elsewhere"
    elsewhere.mkdir()
    moved = elsewhere / Path(adapter._pin.executable).name
    shutil.copy2(adapter._pin.executable, moved)
    adapter._pin = replace(adapter._pin, executable=str(moved))


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

    A home written as an ABSOLUTE path is a relay home. The double judges it by the very function
    the runner's loan and the transport's readiness use (``relay_home_shape``), against the
    project's login homes in ``auth_homes`` (none unless a test sets them), and refuses on entry,
    as the runner does, with a ``ProfileRefused``. It does not read DACLs: the loan's own tests do.

    The two native questions a relay attempt asks the runner before its claim have doubles too:
    ``ensure_relay_root`` makes the folder with no DACL (``relay_root_error``, when set, is raised
    instead) and ``relay_acl_refusal`` answers ``acl_refusal`` (a text, a callable of the relay
    home, or None). ``hooks`` name a callable per moment (``acl``, ``enter``, ``run``, ``exit``)
    that a test uses to look at, or change, the world at exactly that moment; ``outcome``, when
    set, is answered by ``run`` in place of a child.
    """

    def __init__(self, project_root, *, scratch, environ=None, spawns_allowed=True,
                 auth_homes=()):
        super().__init__(project_root, environ=environ, spawns_allowed=spawns_allowed)
        self._scratch = Path(scratch)
        self._open = 0
        self.auth_homes = tuple(auth_homes)
        self.entries: list[Entry] = []
        self.runs: list[Run] = []
        self.events: list[str] = []
        self.enter_error: BaseException | None = None
        self.exit_error: BaseException | None = None
        self.relay_root_error: BaseException | None = None
        self.acl_refusal = None
        self.hooks: dict = {}
        self.outcome = None

    def _hook(self, moment: str, *arguments) -> None:
        if moment in self.hooks:
            self.hooks[moment](*arguments)

    def ensure_relay_root(self, auth_home):  # type: ignore[override]
        self.events.append("relay-root")
        if self.relay_root_error is not None:
            raise self.relay_root_error
        root = relay_root_for(auth_home)
        root.mkdir(exist_ok=True)
        return root

    def relay_acl_refusal(self, auth_home, relay_home=None):  # type: ignore[override]
        self.events.append("acl" if relay_home is None else "acl-home")
        self._hook("acl", relay_home)
        refusal = self.acl_refusal
        return refusal(relay_home) if callable(refusal) else refusal

    def _home(self, folders) -> Path | None:
        """The home the attempt stands on: a route beneath the project, or a judged relay home."""
        if folders.home is None:
            return None
        home = Path(folders.home)
        if not home.is_absolute():
            return self._root / folders.home
        reason = relay_home_shape(
            self.auth_homes, self._root, identity(self._root), home,
            self._root / folders.work, Path(folders.install))
        if reason is not None:
            raise ProfileRefused("profile_acl_invalid", f"the relay home is refused: {reason}")
        return home

    @contextmanager
    def container_profile(self, *, internet_client=False, mode=None, folders=None):
        entry = Entry(mode, internet_client, folders)
        self.entries.append(entry)
        self.events.append("enter")
        if self.enter_error is not None:
            raise self.enter_error
        home = self._home(folders)
        runtime = self._scratch / f"attempt-{len(self.entries)}" / "runtime"
        runtime.mkdir(parents=True)
        entry.paths = {
            "parent": runtime.parent, "runtime": runtime,
            "work": self._root / folders.work, "home": home,
            "install": Path(folders.install)}
        self._open += 1
        try:
            self._hook("enter", entry)
            yield WindowsContainer(SID, internet_client), entry.paths
        finally:
            self._open -= 1
            self.events.append("exit")
        self._hook("exit", entry)
        if self.exit_error is not None:
            raise self.exit_error

    def run(self, spec):  # type: ignore[override]
        inside = self._open > 0
        self.runs.append(Run(spec.argv, spec.cwd, dict(spec.env), spec.boundary, inside))
        self.events.append("run-inside" if inside else "run-outside")
        if inside:
            self._hook("run", spec)
        if self.outcome is not None and inside:
            return self.outcome
        argv = tuple(token for token in spec.argv if token not in NODE_FLAGS)
        return super().run(replace(spec, boundary=None, argv=argv))


def recording(adapter, scratch, *, enter_error=None, exit_error=None,
              auth_homes=None) -> BoundaryRunner:
    """Put a recording boundary entry under a harness adapter, without confining it.

    The adapter keeps its pin, its root and its allowed environment; only the runner it spawns
    through is replaced, by one that shares them. ``auth_homes`` are the real login homes the
    project holds, which a relay home is judged against.
    """
    old = adapter._runner
    runner = BoundaryRunner(
        old._root, scratch=scratch, environ=old._environ, spawns_allowed=old._spawns_allowed,
        auth_homes=getattr(old, "auth_homes", ()) if auth_homes is None else auth_homes)
    runner.enter_error, runner.exit_error = enter_error, exit_error
    adapter._runner = runner
    return runner


def confined(adapter, scratch, *, platform: str = "win32", enter_error=None, exit_error=None,
             auth_homes=None):
    """``recording`` and then ``confine`` the adapter for ``platform``."""
    runner = recording(adapter, scratch, enter_error=enter_error, exit_error=exit_error,
                       auth_homes=auth_homes)
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
