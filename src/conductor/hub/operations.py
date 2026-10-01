"""Bounded in-memory progress for adding a locally chosen folder through the CLI door."""
from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from conductor.hub import events, job, refusals

LIMIT = 50
START_WAIT_SECONDS = 35
MAX_LINE_BYTES = 65536
MAX_OUTPUT_BYTES = 1048576
STEPS = ("admit", "git", "init", "activate", "providers", "exclude", "instructions", "register")
_REFUSED = re.compile(r"^conduct projects add: refused ([a-z][a-z0-9_]*): .+$")


@dataclass(frozen=True)
class FolderPick:
    """A path held only by the hub's future native dialog, never supplied by HTTP."""

    path: str
    project: str  # none | legacy | activated


class Operations:
    def __init__(self, folder: Path, bus: events.EventBus, *,
                 start: Callable[[str], None], status: Callable[[str], tuple[str, str | None]],
                 popen: Callable[..., subprocess.Popen] = subprocess.Popen,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._folder, self._bus = Path(folder), bus
        self._start, self._status, self._popen, self._clock = start, status, popen, clock
        self._lock = threading.RLock()
        self._rows: OrderedDict[str, dict] = OrderedDict()

    def begin(self, pick: FolderPick, name: str, confirmed: bool) -> str:
        with self._lock:
            if any(row["state"] == "running" for row in self._rows.values()):
                raise refusals.HubRefusal("operation_busy")
            ident = f"operation-{secrets.token_hex(16)}"
            row = {"operation_id": ident, "kind": "add", "source": "folder", "state": "running",
                   "step": "admit", "project_id": None, "code": None, "result": None}
            self._rows[ident] = row
            while len(self._rows) > LIMIT:
                self._rows.popitem(last=False)
        self._publish(ident)
        thread = threading.Thread(target=self._run, args=(ident, pick, name, confirmed),
                                  name=f"hub-add-{ident[-8:]}", daemon=True)
        thread.start()
        return ident

    def get(self, ident: str) -> dict:
        with self._lock:
            row = self._rows.get(ident)
            if row is None:
                raise refusals.HubRefusal("operation_not_found", {"operation_id": ident})
            return dict(row)

    def _publish(self, ident: str) -> None:
        self._bus.publish("operation", operation_id=ident)

    def _change(self, ident: str, **fields) -> None:
        with self._lock:
            self._rows[ident].update(fields)
        self._publish(ident)

    def _run(self, ident: str, pick: FolderPick, name: str, confirmed: bool) -> None:
        try:
            result, code = self._cli(ident, pick.path, name, confirmed)
            if code is not None:
                self._change(ident, state="failed", code=code)
                return
            if result is None:
                self._change(ident, state="failed", code="subprocess_failed")
                return
            project_id = result.get("project_id")
            if not isinstance(project_id, str) or re.fullmatch(r"[0-9a-f]{32}", project_id) is None:
                self._change(ident, state="failed", code="subprocess_failed")
                return
            visible = {key: result.get(key) for key in (
                "folder", "activated", "providers", "git", "exclude", "exclude_names",
                "agent_instructions", "projects_home_created")}
            self._change(ident, project_id=project_id, result=visible, step="start")
            try:
                self._start(project_id)
            except refusals.HubRefusal as error:
                self._change(ident, state="failed", code=self._known(error.code))
                return
            deadline = self._clock() + START_WAIT_SECONDS
            while self._clock() < deadline:
                state, state_code = self._status(project_id)
                if state == "running":
                    self._change(ident, state="succeeded", code=None)
                    return
                if state in {"failed", "missing", "identity_mismatch", "recovery_required",
                             "stop_uncertain"}:
                    self._change(ident, state="failed", code=self._known(state_code or "start_failed"))
                    return
                time.sleep(0.1)
            self._change(ident, state="failed", code="start_timeout")
        except Exception:  # a background operation must end in its closed vocabulary
            self._change(ident, state="failed", code="subprocess_failed")

    @staticmethod
    def _known(code: str) -> str:
        return code if code in refusals.OPERATION_ERROR_CODES else "subprocess_failed"

    def _cli(self, ident: str, path: str, name: str, confirmed: bool) -> tuple[dict | None, str | None]:
        # A file, rather than an anonymous pipe, lets the short ownership command finish if the
        # hub exits mid-step. The child has its own process group/session and is not killed by hub.
        fd, output_path = tempfile.mkstemp(prefix="hub-add-out-", dir=self._folder)
        os.close(fd)
        try:
            fd, error_path = tempfile.mkstemp(prefix="hub-add-err-", dir=self._folder)
            os.close(fd)
            try:
                return self._cli_files(ident, path, name, confirmed, output_path, error_path)
            finally:
                os.unlink(error_path)
        finally:
            os.unlink(output_path)

    def _cli_files(self, ident: str, path: str, name: str, confirmed: bool,
                   output_path: str, error_path: str) -> tuple[dict | None, str | None]:
        argv = [sys.executable, "-m", "conductor", "projects", "add", "--dir", path,
                "--name", name]
        if confirmed:
            argv.append("--legacy-writers-stopped")
        # Writer and reader must be independently opened: a duplicated handle shares the
        # file position, allowing the next CLI line to overwrite a line already inspected.
        with open(output_path, "wb", buffering=0) as writer, open(output_path, "rb", buffering=0) as output, \
                open(error_path, "wb", buffering=0) as error_writer, \
                open(error_path, "rb", buffering=0) as errors:
            if os.name == "nt":
                policy = job.own_policy()
                if policy == "kill_on_close":
                    raise OSError("the hub's Windows job cannot release an ownership command")
                flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
                if policy == "breakaway":
                    flags |= subprocess.CREATE_BREAKAWAY_FROM_JOB
                isolated = {"creationflags": flags}
            else:
                isolated = {"start_new_session": True}
            process = self._popen(argv, cwd=self._folder, stdin=subprocess.DEVNULL,
                                  env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                                  stdout=writer, stderr=error_writer, **isolated)
            position = 0
            result = None
            valid = True
            while process.poll() is None:
                if valid:
                    position, result, valid = self._read_progress(ident, output, position, result)
                time.sleep(0.05)
            if valid:
                position, result, valid = self._read_progress(ident, output, position, result)
            errors.seek(0)
            lines = errors.read(65536).decode("utf-8", errors="replace").splitlines()
            if process.returncode != 0:
                matched = _REFUSED.fullmatch(lines[0]) if len(lines) == 1 else None
                return None, self._known(matched[1] if matched else "subprocess_failed")
            return (result, None) if valid else (None, "subprocess_failed")

    def _read_progress(self, ident: str, output, position: int,
                       result: dict | None) -> tuple[int, dict | None, bool]:
        output.seek(position)
        while True:
            start = output.tell()
            if start >= MAX_OUTPUT_BYTES:
                return start, result, not bool(output.read(1))
            line = output.readline(min(MAX_LINE_BYTES + 1, MAX_OUTPUT_BYTES - start + 1))
            if not line:
                return start, result, True
            if len(line) > MAX_LINE_BYTES or start + len(line) > MAX_OUTPUT_BYTES:
                return start, result, False
            if not line.endswith(b"\n"):
                return start, result, True  # wait for the writer to finish the line
            position = output.tell()
            try:
                item = json.loads(line)
            except (UnicodeError, ValueError):
                return position, result, False
            if not isinstance(item, dict):
                return position, result, False
            if set(item) == {"step"} and item["step"] in STEPS:
                index = STEPS.index(item["step"])
                self._change(ident, step=STEPS[index + 1] if index + 1 < len(STEPS) else "start")
            elif set(item) == {"result"} and isinstance(item["result"], dict):
                result = item["result"]
            else:
                return position, result, False
