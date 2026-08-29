"""The run and workflow roads, driven over a real loopback socket.

Split from `test_command_run_routes.py` when that module reached the project's
800-line cap, at the seam it already banners. Every test there drives the API
object in process; every test here binds a real socket and speaks HTTP to it.
That is a different question -- not "does this route decide correctly" but
"does the whole road, transport included, carry a browser end to end" -- and it
is the one that catches a defect the in-process tests cannot see.

Helpers come from the parent module rather than being copied, so the two halves
cannot come to disagree about what a request looks like.
"""
from __future__ import annotations

import json
import socket
import threading
from contextlib import contextmanager

import pytest

from tests.test_command_run_routes import (
    CODEX_PROTOCOL,
    ERROR_STATUS,
    INCOMPLETE,
    INSTANCE,
    NOW,
    ProviderConfig,
    ROLE,
    SHIPPED,
    WORKFLOW,
    a_document,
    good_lane,
    server,
    urllib,
    write_project,
)

#
# Every test above calls `CommandApi` directly, which proves the route
# authority and nothing about whether a browser can reach it: a route that
# exists in the allowlist and is unreachable over HTTP is a route the table
# advertises and the server answers `route_not_found` for. So the last claim in
# this file is driven the way a Cockpit would drive it -- a real server, a real
# socket, the CSRF token the session route handed out, and a provider the
# factory resolved from an executable pinned on this disk.


def pinned(tmp_path):
    """One provider config whose executable really is on this disk.

    The factory stats an operator's ABSOLUTE pin and nothing else, so a file
    that exists is the whole difference between a provider this build can reach
    and one it cannot.
    """
    executable = tmp_path / "codex-executable"
    executable.write_text("", encoding="utf-8", newline="\n")
    return [ProviderConfig(provider_id="codex",
                           executable=str(executable.resolve()),
                           protocol=CODEX_PROTOCOL)]


@contextmanager
def a_served_project(tmp_path):
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    srv = server.build(root, port=0, providers=pinned(tmp_path),
                       clock=lambda: NOW)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        status, session = request(base, "GET", "/command/session")
        assert status == 200
        yield srv, base, session["csrf_token"]
    finally:
        srv.shutdown()
        srv.server_close()


def request(base, method, path, *, token=None, body=None):
    """One real HTTP call; a refusal comes back as a status, not an exception."""
    host = base.removeprefix("http://")
    headers = {"Host": host}
    data = None
    if body is not None:
        data = json.dumps(body, separators=(",", ":")).encode("utf-8")
        headers.update({"Origin": f"http://{host}", "X-Conduct-CSRF": token,
                        "Content-Type": "application/json",
                        "Content-Length": str(len(data))})
    call = urllib.request.Request(base + path, data=data, headers=headers,
                                  method=method)
    try:
        with urllib.request.urlopen(call, timeout=10) as answer:
            return answer.status, json.loads(answer.read() or b"null")
    except urllib.error.HTTPError as refused:
        return refused.code, json.loads(refused.read() or b"null")


def _publish(base, token, workflow_id, revision):
    """Publish over the wire the way a browser does: read, then echo.

    A publish names WHICH draft it reviewed, and a browser gets that digest
    the only way there is -- off the read it drew the review from. Written
    once here so both call sites take the same road, and so the refusal the
    second one reaches is the DRAWING's own rather than the earlier refusal
    for naming no reviewed draft at all.
    """
    read = request(base, "GET", f"/command/workflows/{workflow_id}")[1]
    return request(
        base, "POST", f"/command/workflows/{workflow_id}/revisions",
        token=token,
        body={"revision": revision,
              "reviewed_digest": read["draft"]["digest"]})


def test_a_browser_can_draw_a_workflow_and_open_a_run_from_it_over_a_socket(
        tmp_path):
    """The whole Studio road on the wire a browser really takes.

    The provider resolved through the factory from a pinned executable, so the
    availability the run route consulted is the one this build established
    rather than a descriptor a test made up.
    """
    with a_served_project(tmp_path) as (srv, base, token):
        listed = request(base, "GET", "/command/workflows")
        assert listed[0] == 200 and listed[1]["workflows"] == []
        assert [row["starter_id"] for row in listed[1]["starters"]] == \
            sorted(SHIPPED)

        assert request(base, "POST", f"/command/workflows/{WORKFLOW}/draft",
                       token=token, body=a_document())[0] == 201
        status, document = _publish(base, token, WORKFLOW, 1)
        assert status == 201, document
        assert request(base, "GET", f"/command/workflows/{WORKFLOW}/revisions/1"
                       ) == (200, {"workflow_id": WORKFLOW, "revision": 1,
                                   "document": document})

        status, opened = request(base, "POST", "/command/runs", token=token, body={
            "run_id": "run-over-the-socket", "cycle_id": "default-orbit",
            "mode": "confirm",
            "participants": [{"instance_id": INSTANCE, "provider_id": "codex",
                              "model": None}],
            "workflow_id": WORKFLOW, "revision": 1,
            "assignments": {ROLE: INSTANCE}})
        assert status == 201, opened
        assert opened["graph"]["run_id"] == "run-over-the-socket"
        assert [row.provider_id for row in srv.command_providers
                if row.available] == ["codex"]

        status, runs = request(base, "GET", "/command/runs")
        assert status == 200
        assert [row["run_id"] for row in runs["runs"]] == ["run-over-the-socket"]
        assert runs["runs"][0]["unreadable"] is False

        # And an unfinished drawing is refused the publish, on the wire.
        assert request(base, "POST", "/command/workflows/half-drawn/draft",
                       token=token, body=INCOMPLETE["a dangling edge"])[0] == 201
        status, refused = _publish(base, token, "half-drawn", 1)
        assert status == ERROR_STATUS["contract_invalid"]
        assert refused["diagnostics"][0]["code"] == "template_refused"
