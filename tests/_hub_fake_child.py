"""A fake child on a real loopback socket, for the tests of what the hub reads (not a test file).

It answers the reads of spec 4.5.6 from a table the test sets, and it writes down EVERY request it
gets (method, target, headers as sent), so a test can say what the hub asked and what it did not.
Anything that is not a GET is answered `405` and logged: a hub that writes to a child is caught by
the log, not by the answer. `/events` is a stream the test feeds frame by frame.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

HUB_ORIGIN = "http://127.0.0.1:7700"


@dataclass(frozen=True)
class Request:
    """One request the child received, exactly as it came."""

    method: str
    target: str
    headers: dict[str, str]


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False


class FakeChild:
    """A child of one project: the four keys of `GET /command/project` and a table of answers."""

    def __init__(self, project_id: str, *, mode: str = "active",
                 hub_origin: str | None = HUB_ORIGIN, shown_project_id: str | None = None) -> None:
        self.project_id = project_id
        self.identity = {"project_id": shown_project_id or project_id, "hub_origin": hub_origin,
                         "demo": False, "mode": mode}
        self.log: list[Request] = []
        #: target -> (status, body) or a callable that answers `(status, body)` for the request.
        self.answers: dict[str, Any] = {}
        self.delay: dict[str, float] = {}
        self.project_status = 200
        self._frames: list[bytes] = []
        self._frames_changed = threading.Condition()
        self._closed = False
        self._server = _Server(("127.0.0.1", 0), self._handler())
        self.port = self._server.server_address[1]
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    # -- what a test sets --------------------------------------------------------------------

    def put(self, target: str, body: Any, status: int = 200) -> None:
        self.answers[target] = (status, body)

    def send_frame(self, frame: dict | bytes) -> None:
        raw = frame if isinstance(frame, bytes) else (
            b"data: " + json.dumps(frame).encode("utf-8") + b"\n\n")
        with self._frames_changed:
            self._frames.append(raw)
            self._frames_changed.notify_all()

    def drop_streams(self) -> None:
        """End every open `/events` stream now (the next one is a new connection)."""
        with self._frames_changed:
            self._frames.append(b"")
            self._frames_changed.notify_all()

    # -- what a test reads -------------------------------------------------------------------

    def targets(self, method: str | None = None) -> list[str]:
        return [request.target for request in self.log
                if method is None or request.method == method]

    def count(self, target: str) -> int:
        return self.targets().count(target)

    def close(self) -> None:
        self._closed = True
        with self._frames_changed:
            self._frames_changed.notify_all()
        self._server.shutdown()
        self._server.server_close()

    # -- the server ---------------------------------------------------------------------------

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args: object) -> None:
                return

            def _note(self) -> Request:
                request = Request(self.command, self.path,
                                  {name.lower(): value for name, value in self.headers.items()})
                owner.log.append(request)
                return request

            def do_GET(self) -> None:  # noqa: N802
                request = self._note()
                if self.path == "/events":
                    owner._stream(self)
                    return
                owner._answer(self, request)

            def _refuse_other(self) -> None:
                self._note()
                body = b'{"error":{"code":"method_not_allowed"}}'
                self.send_response(405)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            do_POST = do_PUT = do_DELETE = do_PATCH = _refuse_other  # noqa: N815

        return Handler

    def _body_for(self, request: Request) -> tuple[int, Any]:
        if request.target == "/command/project":
            return self.project_status, self.identity
        found = self.answers.get(request.target)
        if found is None:
            return 404, {"error": {"code": "route_not_found", "message": "", "detail": {}}}
        return found(request) if callable(found) else found

    def _answer(self, handler: BaseHTTPRequestHandler, request: Request) -> None:
        pause = self.delay.get(request.target, 0.0)
        if pause:
            time.sleep(pause)
        status, body = self._body_for(request)
        raw = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        try:
            handler.send_response(status)
            handler.send_header("Content-Type", "application/json; charset=utf-8")
            handler.send_header("Content-Length", str(len(raw)))
            handler.end_headers()
            handler.wfile.write(raw)
        except OSError:
            return

    def _stream(self, handler: BaseHTTPRequestHandler) -> None:
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream")
        handler.send_header("Connection", "close")
        handler.end_headers()
        handler.close_connection = True
        seen = [len(self._frames)]
        try:
            handler.wfile.write(b'data: {"kind":"state"}\n\n')
            handler.wfile.flush()
            while not self._closed:
                with self._frames_changed:
                    self._frames_changed.wait_for(
                        lambda: self._closed or len(self._frames) > seen[0], timeout=0.2)
                    fresh, seen[0] = self._frames[seen[0]:], len(self._frames)
                for frame in fresh:
                    if frame == b"":
                        return
                    handler.wfile.write(frame)
                    handler.wfile.flush()
        except OSError:
            return


def run_row(run_id: str, task_id: str | None, *, human_state: str = "not_required",
            created_at: str = "2026-09-30T09:00:00Z", **changes: Any) -> dict[str, Any]:
    """A row of `GET /command/runs` as the server spells it."""
    row = {"run_id": run_id, "unreadable": False, "cycle_id": "default-orbit",
           "created_at": created_at, "mode": "policy", "envelope_status": "created",
           "graph_id": "graph-" + run_id, "undecided_gates": 0, "open_actions": 0,
           "last_outcome": None, "workflow_id": "desk-standard", "revision": 1,
           "task_id": task_id, "human_state": human_state}
    return {**row, **changes}


def task_row(task_id: str, title: str, **changes: Any) -> dict[str, Any]:
    """A row of `GET /command/tasks`."""
    return {**{"schema_version": 1, "task_id": task_id, "title": title, "unreadable": False,
               "created_at": "2026-09-30T08:00:00Z", "work_scope": task_id}, **changes}


def automation(run_id: str, state: str = "waiting", reason: str = "plan_waiting",
               expires_at: str | None = "2026-09-30T12:00:00Z") -> dict[str, Any]:
    """The answer of `GET /command/runs/<id>/automation` (the fields the hub keeps, and more)."""
    return {"run_id": run_id, "authorization": None, "control": None, "state": state,
            "reason_code": reason, "active_action_id": None, "next_node_id": None,
            "spent_actions": 0, "remaining_actions": 3, "spent_task_seconds": 0,
            "remaining_task_seconds": 600, "expires_at": expires_at, "owner_present": True}


def situation(counts: dict[str, list[str]] | None = None, gates: list[dict] | None = None,
              state: str = "required") -> dict[str, Any]:
    """`graph.situation` as `human_situation` spells it."""
    counts = counts or {}
    reasons = ("gate_decision", "confirmation", "input_document", "reconcile", "attempt_bound",
               "run_ended")
    return {"state": state, "computed_at": "2026-09-30T10:00:00Z", "gates": gates or [],
            "checked": [{"reason": reason, "count": len(counts.get(reason, [])),
                         "sources": counts.get(reason, [])} for reason in reasons],
            "unknown_because": [], "unknown_sources": []}


def run_detail(run_id: str, counts: dict[str, list[str]], gates: list[dict] | None = None,
               records: list[dict] | None = None, nodes: list[dict] | None = None,
               ) -> dict[str, Any]:
    """The answer of `GET /command/runs/<id>` (the parts the hub reads)."""
    return {"run": {"run_id": run_id}, "config": {}, "records": records or [], "warnings": [],
            "graph": {"situation": situation(counts, gates), "runtime": {"nodes": nodes or []}},
            "task": None}


def serve_standard(child: FakeChild, tasks: list[dict], runs: list[dict],
                   details: dict[str, dict] | None = None,
                   automations: dict[str, dict] | None = None) -> None:
    """Teach a child the reads of a cycle: tasks, runs, one automation per run, the details."""
    child.put("/command/tasks", {"tasks": tasks})
    child.put("/command/runs", {"runs": runs, "providers": []})
    for run in runs:
        found = (automations or {}).get(run["run_id"]) or automation(run["run_id"])
        child.put(f"/command/runs/{run['run_id']}/automation", found)
    for run_id, detail in (details or {}).items():
        child.put(f"/command/runs/{run_id}", detail)
    child.put("/command/quotas", {"as_of": "2026-09-30T10:00:00Z", "max_age_seconds": 300,
                                  "providers": [], "snapshots": []})
