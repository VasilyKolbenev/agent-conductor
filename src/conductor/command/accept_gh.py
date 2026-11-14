"""The pinned gh of an `active` child, run through the one execution door (spec 9.3, 8.8, 8.9).

`server_command.start_command` asks for one reader per process and hands it to the command API;
a process opened for viewing never asks. The reader does its work on the first call, and only
once: it checks the pinned gh, builds the environment of 8.9 for it (which holds no token, no
host override and no askpass program), makes the working folder `<data_root>/git/cwd` under the
owner's guard and builds one runner that may spawn.

Lazy, because a server that never publishes then runs nothing and needs no pin. Once, because
spec 8.8 compares the version once per process. When the pin cannot be used every call raises
`GhUnavailable` and the verdict is not asked for again; a fault that is not the tool's (the
folder cannot be made) is an `OSError`, which the caller may try again.

Standard error is kept out of the answer and is kept nowhere: what the caller reads is the
standard output of the command and its exit code, and a failure is told by those two alone.
"""
from __future__ import annotations

import os
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from conductor import ownership, tool_env, tool_pins
from conductor.command.adapters.process import CommandSpec, ContainmentError, ProcessRunner
from conductor.hub import home
from conductor.ownership_errors import OwnerRefused

#: Why the tool is not usable, the three words of 9.3 (the words `tool_unavailable` carries).
REASONS = ("not_pinned", "version_changed", "missing")
#: One call may take a minute (9.3); what it may bring back is cut and says so.
TIMEOUT_SECONDS = 60
OUTPUT_LIMIT = 1024 * 1024
_REASON_OF = {"gh_not_pinned": "not_pinned", "tools_file_invalid": "not_pinned",
              "tools_file_unreadable": "not_pinned", "gh_changed": "version_changed",
              "tool_version_unreadable": "missing"}


class GhUnavailable(Exception):
    """gh is not the pinned one: `reason` is one of `REASONS`."""

    def __init__(self, reason: str) -> None:
        if reason not in REASONS:
            raise ValueError(f"reason must be one of {', '.join(REASONS)}, not {reason!r}")
        super().__init__("tool_unavailable")
        self.reason = reason


@dataclass(frozen=True)
class GhAnswer:
    """What one gh call said: its exit code (None when it was cut short) and its output.

    `hidden` is set when the output carries a value of the environment the child ran in; such an
    answer is never read, only counted as a failure.
    """

    exit_code: int | None
    output: bytes
    truncated: bool = False
    timed_out: bool = False
    hidden: bool = False


#: One call: `gh(args, *, stdin=None, timeout=None, output_limit=None) -> GhAnswer`.
GhRead = Callable[..., GhAnswer]


@dataclass(frozen=True)
class _Tool:
    path: str
    env: Mapping[str, str]


class _LazyGh:
    """The reader of one process: built on the first call, the tool judged once."""

    def __init__(self, root: Path | str, source: Mapping[str, str] | None,
                 folder: Path | str | None, verify: Callable[..., object] | None,
                 runner_class: Callable[..., object]) -> None:
        self._root = Path(root).resolve()
        self._source = os.environ if source is None else source
        self._folder, self._verify, self._runner_class = folder, verify, runner_class
        self._lock = threading.Lock()
        self._verdict: _Tool | str | None = None
        self._runner: object | None = None
        self._cwd: Path | None = None

    def __call__(self, args: Sequence[str], *, stdin: bytes | None = None,
                 timeout: float | None = None, output_limit: int | None = None) -> GhAnswer:
        tool, runner, cwd = self._ready()
        spec = CommandSpec(
            argv=(tool.path, *args), cwd=str(cwd), env_allow=(), env=tool.env,
            stdin_bytes=stdin, output_limit=OUTPUT_LIMIT if output_limit is None else output_limit,
            timeout_seconds=TIMEOUT_SECONDS if timeout is None else timeout, separate_stderr=True)
        try:
            outcome = runner.run(spec)
        except ContainmentError as error:
            raise OSError("the working folder of gh is not usable") from error
        return GhAnswer(exit_code=outcome.exit_code, output=outcome.output,
                        truncated=outcome.output_truncated,
                        timed_out=outcome.status == "timed_out",
                        hidden=outcome.output_contains_env_value)

    def _ready(self) -> tuple[_Tool, object, Path]:
        with self._lock:
            if self._verdict is None:
                self._verdict = self._judge()
            if isinstance(self._verdict, str):
                raise GhUnavailable(self._verdict)
            if self._runner is None:
                self._cwd = self._work_folder()
                self._runner = self._runner_class(self._root, environ={}, spawns_allowed=True)
            return self._verdict, self._runner, self._cwd

    def _judge(self) -> _Tool | str:
        """The pinned gh and its environment, or the reason it cannot be used."""
        try:
            folder = home.conduct_home_path() if self._folder is None else self._folder
            verify = tool_pins.verify_pin if self._verify is None else self._verify
            pin = verify("gh", folder=folder, source=self._source)
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
        except OwnerRefused as error:
            raise OSError("the working folder of gh cannot be made") from error
        return cwd


def project_gh_reader(
        root: Path | str, *, source: Mapping[str, str] | None = None,
        folder: Path | str | None = None, verify: Callable[..., object] | None = None,
        runner_class: Callable[..., object] = ProcessRunner) -> GhRead:
    """The reader of the pinned gh for one `active` process; nothing runs until it is called.

    Args:
        root: The project root; the runner is built over it.
        source: The owner's environment `tool_env` takes its allowlisted names from; the
            process environment unless a test says another.
        folder: `<conduct-home>`; asked of `hub.home` at the first call unless a test says.
        verify: `tool_pins.verify_pin` unless a test stands in for it.
        runner_class: `ProcessRunner` unless a test stands in for it.

    Returns:
        A `GhRead`. Every call raises `GhUnavailable` while the tool cannot be used.
    """
    return _LazyGh(root, source, folder, verify, runner_class)
