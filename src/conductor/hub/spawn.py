"""The hub starts a project's child the way spec 4.1.4 says.

The command is `sys.executable -m conductor up ...`, never `conduct` from PATH, with the flags of
the table of 4.1.4. The start is the one a hub child is given: its stdin is a pipe the hub keeps
and writes nothing into (the end of that pipe is the stop request, and it arrives however the
hub dies), stdout is discarded, stderr goes to `logs/<project_id>.log` with the previous log kept
once as `.log.1`, the working folder is `<conduct-home>` (so the child does not hold the project
folder), no handle of another child is inherited, and the child has a process group (Windows) or
a session (POSIX) of its own, so Ctrl+C and a closed terminal do not reach it. This module does
not use `ProcessRunner` and puts the child in no job of its own: a runner would demand a live
owner of the project, always end the group, and on Windows tie the child to a job that dies with
the hub. The only thing it asks about jobs is the policy of the hub's own (ADR-1b): a child
breaks away from a job that allows it, and is not started at all in one that does not.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from conductor import up_flags

#: The command every child is started with; a test may replace it by the head of a fake-dispatch
#: child, and nothing else does.
HEAD = (sys.executable, "-m", "conductor")
JOB_POLICIES = ("none", "breakaway", "kill_on_close")
#: `CREATE_BREAKAWAY_FROM_JOB`: a child of a job that allows it may leave the job.
_BREAKAWAY = 0x01000000

_PROJECT_ID = re.compile(r"[0-9a-f]{32}")
_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_TRANSITION = re.compile(_UUID)
_AUTO_CONTINUE = re.compile(_UUID + r"@[1-9][0-9]{0,8}")


class SpawnRefused(Exception):
    """The child was not started: `code` is a code of 4.1.5 (`hub_in_kill_on_close_job`,
    `start_failed`) and `detail` one line."""

    def __init__(self, code: str, detail: str) -> None:
        self.code, self.detail = code, detail
        super().__init__(f"{code}: {detail}")


@dataclass
class Child:
    """A started child: what the hub knows of it before its status file says more."""

    popen: subprocess.Popen
    argv: list[str]
    project_id: str
    mode: str
    instance: str
    started_at: float
    log_path: Path

    def poll(self) -> int | None:
        """The exit code, or `None` while the process runs."""
        return self.popen.poll()

    def wait(self, timeout: float | None = None) -> int:
        """Wait for the exit and return its code."""
        return self.popen.wait(timeout)

    def close_stdin(self) -> None:
        """End the pipe: the child reads end of file, and drains (4.1.6)."""
        try:
            if self.popen.stdin is not None:
                self.popen.stdin.close()
        except (OSError, ValueError):
            pass


def status_path(conduct_home: Path, project_id: str) -> Path:
    """`<conduct-home>/run/<project_id>.json`, the file only the child writes."""
    return conduct_home / "run" / f"{project_id}.json"


def log_path(conduct_home: Path, project_id: str) -> Path:
    """`<conduct-home>/logs/<project_id>.log`, the child's stderr."""
    return conduct_home / "logs" / f"{project_id}.log"


def child_argv(head: Sequence[str], conduct_home: Path, hub_origin: str, *, project_id: str,
               root: Path | str, port: int, mode: str, transition: str | None = None,
               auto_continue: str | None = None) -> list[str]:
    """The command line of 4.1.4, flags in the order of its table.

    Raises:
        ValueError: A value is off its grammar, or flags go together that the child would
            refuse (`--transition` needs `--mode active`, `--auto-continue` needs
            `--transition`): starting a child only to be told so is a waste the hub avoids.
    """
    _require(project_id, transition, auto_continue, port, mode)
    argv = [*head, "up", "--dir", str(root), "--port", str(port), "--project-id", project_id,
            "--hub-origin", hub_origin, "--status-file",
            str(status_path(conduct_home, project_id)), "--stop-on-stdin-eof", "--mode", mode]
    if transition is not None:
        argv += ["--transition", transition]
    if auto_continue is not None:
        argv += ["--auto-continue", auto_continue]
    return argv


def _require(project_id: str, transition: str | None, auto_continue: str | None, port: int,
             mode: str) -> None:
    if mode not in up_flags.MODES:
        raise ValueError(f"mode must be one of {', '.join(up_flags.MODES)}, not {mode!r}")
    if not (isinstance(project_id, str) and _PROJECT_ID.fullmatch(project_id)):
        raise ValueError("project_id must be 32 lowercase hex characters")
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError("port must be a whole number from 0 to 65535")
    if transition is not None and not (mode == "active" and _TRANSITION.fullmatch(transition)):
        raise ValueError("a transition is a uuid and goes only with --mode active")
    if auto_continue is not None and not (transition is not None
                                          and _AUTO_CONTINUE.fullmatch(auto_continue)):
        raise ValueError("a flag is <flag_id>@<revision> and goes only with a transition")


class Spawner:
    """Starts children for one hub: its folder, its origin and the policy of its own job."""

    def __init__(self, conduct_home: Path | str, *, hub_origin: str,
                 head: Sequence[str] = HEAD, environ: Mapping[str, str] | None = None,
                 popen: Callable[..., subprocess.Popen] = subprocess.Popen,
                 job_policy: Callable[[], str] | None = None) -> None:
        if not up_flags.is_hub_origin(hub_origin):
            raise ValueError("hub_origin must be http://127.0.0.1:<port>")
        self._home = Path(conduct_home)
        self._origin, self._head = hub_origin, tuple(head)
        self._environ = dict(os.environ if environ is None else environ)
        self._popen = popen
        self._job_policy = job_policy or (lambda: "none")

    def start(self, *, project_id: str, root: Path | str, port: int, mode: str,
              transition: str | None = None, auto_continue: str | None = None) -> Child:
        """Start the child of one project.

        Raises:
            ValueError: See `child_argv`, or the job policy is not one of the three.
            SpawnRefused: `hub_in_kill_on_close_job` (nothing was made, not even a log), or
                `start_failed` (the OS could not start the process).
        """
        argv = child_argv(self._head, self._home, self._origin, project_id=project_id,
                          root=root, port=port, mode=mode, transition=transition,
                          auto_continue=auto_continue)
        extra = self._breakaway_flags()
        log = _rotate(log_path(self._home, project_id))
        options = {"stdin": subprocess.PIPE, "stdout": subprocess.DEVNULL, "stderr": log,
                   "cwd": str(self._home), "close_fds": True,
                   "env": {**self._environ, "CONDUCT_HOME": str(self._home)},
                   **_isolation(extra)}
        try:
            with log:
                process = self._popen(argv, **options)
        except OSError as error:
            raise SpawnRefused("start_failed", f"the process could not be started: {error}"
                               ) from error
        return Child(process, argv, project_id, mode, uuid.uuid4().hex, time.monotonic(),
                     Path(log.name))

    def _breakaway_flags(self) -> int:
        policy = self._job_policy()
        if policy not in JOB_POLICIES:
            raise ValueError(f"the job policy must be one of {', '.join(JOB_POLICIES)}")
        if policy == "kill_on_close":
            raise SpawnRefused("hub_in_kill_on_close_job",
                               "this hub runs inside a job that ends its children with it, "
                               "and the job does not let them leave")
        return _BREAKAWAY if policy == "breakaway" else 0


def _isolation(extra_flags: int) -> dict:
    """A group (Windows) or a session (POSIX) of its own, and no console window."""
    if os.name != "nt":
        return {"start_new_session": True}
    flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW | extra_flags
    return {"creationflags": flags}


def _rotate(path: Path):
    """Keep the previous log once as `.log.1` and open a new one for the child's stderr."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.exists():
        os.replace(path, path.with_name(path.name + ".1"))
    return path.open("wb")
