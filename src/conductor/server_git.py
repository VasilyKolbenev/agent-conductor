"""The project's git reader of an `active` child (spec 9.3, 8.8, 8.9, 9.1.6).

`server_command.start_command` asks for one reader per process and hands it to the command
API; a process opened for viewing never asks (a view process creates no child process, so a
reader that existed there would be a second place that could start one). The reader does its
work on the first call, and only once:

1. the pinned git is checked (`tool_pins.verify_pin`: the pin is there, the version it says is
   the one that was pinned) and the environment of 8.9 is built for it with `tool_env`;
2. the folder `<data_root>/git/cwd` is made under the owner's write guard (a runner refuses a
   working folder that is the root itself, and the repository is named by `-C` in each call);
3. one `ProcessRunner` that may spawn is built over the project root, and with it the reader
   of `project_git`.

Lazy, because a server that never asks git then makes no folder, runs nothing and needs no pin
to start. Once, because spec 8.8 says the version is compared once per process. When the tool
cannot be used, every call raises `ToolUnavailable` and the verdict is not asked for again. A
fault that is not the tool's (the folder cannot be made, the owner is gone) is a plain
`GitReadFailed("git_failed")`, which the caller may try again: only what was judged about the
tool is remembered.
"""
from __future__ import annotations

import os
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from conductor import ownership, tool_env, tool_pins
from conductor.command import project_git
from conductor.command.adapters.process import ProcessRunner
from conductor.hub import home
from conductor.ownership_errors import OwnerRefused

CODE = "tool_unavailable"
#: Why the tool is not usable, the three words of 9.3.
REASONS = ("not_pinned", "version_changed", "missing")
#: The reason each refusal of `tool_pins` comes to. A `tools.json` that is not the schema is no
#: pin anyone can rely on, so it reads `not_pinned`; an executable that vanished or says nothing
#: readable reads `missing`.
_REASON_OF = {"git_not_pinned": "not_pinned", "tools_file_invalid": "not_pinned",
              "git_changed": "version_changed", "tool_version_unreadable": "missing"}


class ToolUnavailable(project_git.GitReadFailed):
    """git is not the pinned one: `code` is `tool_unavailable` and `reason` says which way.

    It is a `GitReadFailed`, so every caller that already judges a failed read judges this one
    too; a caller that knows the word reads `reason`.

    Raises:
        ValueError: `reason` is not one of `REASONS`.
    """

    def __init__(self, reason: str) -> None:
        if reason not in REASONS:
            raise ValueError(f"reason must be one of {', '.join(REASONS)}, not {reason!r}")
        super().__init__(CODE)
        self.reason = reason


@dataclass(frozen=True)
class _Tool:
    """What the judgement of the pin came to: the path to run and the environment to run it in."""

    path: str
    env: Mapping[str, str]


class _LazyReader:
    """The reader of one process: built on the first call, the tool judged once."""

    def __init__(self, root: Path | str, source: Mapping[str, str] | None,
                 folder: Path | str | None, verify: Callable[..., object] | None,
                 runner_class: Callable[..., object]) -> None:
        self._root = Path(root).resolve()
        self._source = os.environ if source is None else source
        self._folder, self._verify, self._runner_class = folder, verify, runner_class
        self._lock = threading.Lock()
        self._verdict: _Tool | str | None = None
        self._read: project_git.GitRead | None = None

    def __call__(self, args: Sequence[str], separate_stderr: bool = False, **keywords: object):
        """One git read; `stdin`, `output_limit` and `timeout` go on to the reader it built."""
        return self._ready()(args, separate_stderr, **keywords)

    def _ready(self) -> project_git.GitRead:
        with self._lock:
            if self._read is None:
                tool = self._judged()
                cwd = self._work_folder()
                runner = self._runner_class(self._root, environ={}, spawns_allowed=True)
                self._read = project_git.process_git_read(
                    runner, tool.path, str(cwd), env_allow=(), env=tool.env)
            return self._read

    def _judged(self) -> _Tool:
        if self._verdict is None:
            self._verdict = self._judge()
        if isinstance(self._verdict, str):
            raise ToolUnavailable(self._verdict)
        return self._verdict

    def _judge(self) -> _Tool | str:
        """The pinned git and its environment, or the reason it cannot be used."""
        try:
            folder = home.conduct_home_path() if self._folder is None else self._folder
            verify = tool_pins.verify_pin if self._verify is None else self._verify
            pin = verify("git", folder=folder, source=self._source)
            pins = tool_pins.load_pins(folder)
        except tool_pins.ToolPinError as error:
            return _REASON_OF.get(error.code, "missing")
        except home.ConductHomeInvalid:
            return "not_pinned"
        return _Tool(pin.path, tool_env.tool_env(self._source, pins, folder))

    def _work_folder(self) -> Path:
        """`<data_root>/git/cwd`, made under the owner's guard when it is not there yet."""
        try:
            with ownership.write_guard(self._root):
                cwd = ownership.data_root(self._root) / "git" / "cwd"
                cwd.mkdir(parents=True, exist_ok=True)
        except (OSError, OwnerRefused) as error:
            raise project_git.GitReadFailed("git_failed") from error
        return cwd


def project_git_reader(
        root: Path | str, *, source: Mapping[str, str] | None = None,
        folder: Path | str | None = None, verify: Callable[..., object] | None = None,
        runner_class: Callable[..., object] = ProcessRunner) -> project_git.GitRead:
    """The reader of the project's git for one `active` process; nothing runs until it is called.

    Args:
        root: The project root; the runner is built over it.
        source: The owner's environment `tool_env` takes its allowlisted names from; the
            process environment unless a test says another.
        folder: `<conduct-home>`; asked of `hub.home` at the first call unless a test says.
        verify: `tool_pins.verify_pin` unless a test stands in for it.
        runner_class: `ProcessRunner` unless a test stands in for it.

    Returns:
        A `GitRead`: `(args, separate_stderr=False) -> GitAnswer`. Every call raises
        `ToolUnavailable` while the tool cannot be used.
    """
    return _LazyReader(root, source, folder, verify, runner_class)
