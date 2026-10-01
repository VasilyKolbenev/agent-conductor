"""One bounded native folder dialog; paths stay inside this hub process."""
from __future__ import annotations

import json
import importlib.util
import os
import secrets
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable

from conductor import ownership_records
from conductor.command.adapters import _procgroup
from conductor.hub import events, operations, projects_add, refusals

TIMEOUT = 600
PICK_LIFETIME = 600
OUTPUT_LIMIT = 4096
def _backend_available(backend: str) -> bool:
    if backend == "mac":
        return Path("/usr/bin/osascript").is_file()
    tkinter = importlib.util.find_spec("tkinter") is not None
    if backend == "windows":
        return tkinter
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")) and (
        any(Path(path).is_file() for path in ("/usr/bin/zenity", "/usr/bin/kdialog"))
        or tkinter)


class Dialogs:
    def __init__(self, home: Path, bus: events.EventBus, *,
                 popen: Callable[..., subprocess.Popen] = subprocess.Popen,
                 clock: Callable[[], float] = time.monotonic,
                 backend: str | None = None,
                 available: Callable[[], bool] | None = None) -> None:
        self._home, self._bus, self._popen, self._clock = Path(home), bus, popen, clock
        self._backend = backend or ("windows" if os.name == "nt" else
                                    "mac" if sys.platform == "darwin" else "linux")
        self._available = available or (lambda: _backend_available(self._backend))
        self._lock = threading.RLock()
        self._rows: dict[str, dict] = {}
        self._paths: dict[str, str] = {}
        self._group: object | None = None
        self._open: str | None = None

    def begin(self, purpose: str) -> str:
        if purpose != "project":
            raise refusals.HubRefusal("route_not_found", {"reason": "purpose not in this build"})
        if not self._available():
            raise refusals.HubRefusal("dialog_unavailable")
        with self._lock:
            if self._open is not None:
                self._row(self._open)
            # A cancelled/expired helper still owns the one slot until it has actually exited.
            if self._open is not None:
                raise refusals.HubRefusal("dialog_busy")
            ident = "pick-" + secrets.token_hex(16)
            self._rows[ident] = {"pick_id": ident, "purpose": purpose, "state": "open",
                                 "folder": None, "project": None, "code": None,
                                 "expires": self._clock() + PICK_LIFETIME}
            self._open = ident
        threading.Thread(target=self._run, args=(ident,), daemon=True,
                         name="hub-folder-picker").start()
        return ident

    def get(self, ident: str) -> dict:
        with self._lock:
            row = self._row(ident)
            return {key: value for key, value in row.items() if key != "expires"}

    def resolve(self, ident: str) -> operations.FolderPick | None:
        with self._lock:
            try:
                row = self._row(ident)
            except refusals.HubRefusal:
                return None
            if row["state"] != "picked" or row["purpose"] != "project":
                return None
            path = self._paths.get(ident)
            return None if path is None else operations.FolderPick(path, row["project"])

    def consume(self, ident: str) -> None:
        with self._lock:
            self._paths.pop(ident, None)
            row = self._rows.get(ident)
            if row is not None:
                row.update(state="expired", folder=None, project=None)

    def cancel(self, ident: str) -> None:
        with self._lock:
            row = self._row(ident)
            if row["state"] == "expired":
                raise refusals.HubRefusal("pick_not_found")
            group = self._group if self._open == ident and row["state"] == "open" else None
            self._paths.pop(ident, None)
            row.update(state="cancelled", folder=None, project=None, code=None)
            if group is not None:
                group.terminate()
        self._bus.publish("pick", pick_id=ident)

    def close(self) -> None:
        with self._lock:
            group = self._group
            if group is not None:
                group.terminate()
            self._paths.clear()
            for row in self._rows.values():
                row.update(state="expired", folder=None, project=None, code=None)

    def _row(self, ident: str) -> dict:
        row = self._rows.get(ident)
        if row is None:
            raise refusals.HubRefusal("pick_not_found")
        if self._clock() >= row["expires"] and row["state"] != "expired":
            if self._open == ident and self._group is not None:
                self._group.terminate()
            row.update(state="expired", folder=None, project=None, code=None)
            self._paths.pop(ident, None)
            self._bus.publish("pick", pick_id=ident)
        return row

    def _finish(self, ident: str, state: str, *, path: str | None = None,
                project: str | None = None, code: str | None = None) -> None:
        with self._lock:
            row = self._row(ident)
            if row["state"] != "open":
                return
            row.update(state=state, folder=Path(path).name if path else None,
                       project=project, code=code)
            if state == "picked" and path:
                self._paths[ident] = path
            if self._open == ident:
                self._open = None
        self._bus.publish("pick", pick_id=ident)

    def _run(self, ident: str) -> None:
        try:
            answer = self._choose(ident)
            if answer.get("cancelled") is True:
                self._finish(ident, "cancelled")
            elif not isinstance(answer.get("path"), str):
                self._finish(ident, "failed", code="dialog_unavailable")
            else:
                path = answer["path"]
                try:
                    root, _registry = projects_add._admit(path, None, self._home)
                    _root, head = ownership_records.state(root)
                    project = "activated" if head and head["phase"] in {
                        "active", "opened", "closed", "recovered"} else (
                        "legacy" if os.path.lexists(root / "conductor") else "none")
                except projects_add.AddRefused as error:
                    self._finish(ident, "refused", code=error.code)
                    return
                except ownership_records.OwnerRefused as error:
                    self._finish(ident, "refused", code=error.code)
                    return
                self._finish(ident, "picked", path=str(root), project=project)
        except subprocess.TimeoutExpired:
            self._finish(ident, "failed", code="dialog_timeout")
        except Exception:  # this background boundary must settle even after a failed admission
            self._finish(ident, "failed", code="dialog_unavailable")
        finally:
            with self._lock:
                if self._open == ident:
                    self._open = None

    def _choose(self, ident: str) -> dict:
        argv = [sys.executable, "-m", "conductor.hub.pick_folder", "--backend", self._backend]
        proc = self._popen(argv, cwd=self._home, stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                           **_procgroup.popen_kwargs())
        try:
            try:
                group = _procgroup.make_group(proc)
            except Exception:
                proc.kill()
                proc.wait()
                raise
            with self._lock:
                if self._rows[ident]["state"] != "open":
                    group.terminate()
                else:
                    self._group = group
            try:
                raw, _ = proc.communicate(timeout=TIMEOUT)
            except subprocess.TimeoutExpired:
                group.terminate()
                proc.wait()
                raise
            finally:
                with self._lock:
                    if self._group is group:
                        self._group = None
                group.close()
            if proc.returncode != 0 or len(raw) > OUTPUT_LIMIT:
                raise ValueError("native picker failed")
            answer = json.loads(raw.decode("utf-8"))
            if not isinstance(answer, dict) or set(answer) not in (
                    {"path"}, {"cancelled"}, {"unavailable"}):
                raise ValueError("native picker protocol")
            return answer
        finally:
            if proc.stdout is not None:
                proc.stdout.close()
