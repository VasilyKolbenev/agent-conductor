"""The legacy panel read routes answer only a Host this process minted.

`server.py` grew a command arm that validates Host, Origin and a per-process
CSRF token, but the read routes it was born with — the panel, the merged state,
the raw lanes, the handoff packets, the harness registry and the SSE stream —
answered any Host at all. A page a developer visits while `conduct up` runs can
re-resolve its own name to 127.0.0.1, fetch every one of those routes
cross-origin and read the whole merged project. The read arm now spends the
SAME allowlist the command arm spends, so widening one can never quietly widen
only the other.

Every test here talks to a real socket on a real bound server. A Host is a wire
fact: a stubbed header proves nothing about what the platform's own request
parser hands the handler, and the SSE claim in particular is a claim about
which bytes reach the wire FIRST — the stream commits a 200 before it writes a
frame, so a refusal that arrives after dispatch is not a refusal at all.
"""
from __future__ import annotations

import contextlib
import importlib.resources
import json
import socket
import threading
import urllib.error
import urllib.request

import pytest

from conductor import harnesses, server
from tests.test_store import write_project


#: One distinctive token planted in the project so a leak is nameable. It rides
#: the map's project name into `state.json` and the handoff packet, and the
#: lane's own bytes into `/lane/claude.json`.
MARKER = "PROJECT-MARKER-7f3ac91e"
MAP_TOML = (
    "schema_version = 1\n"
    f'project = "{MARKER}"\n'
    '[[nodes]]\nid = "a"\nlabel = "a"\nkind = "artifact"\n'
)
LANE = json.dumps({
    "schema_version": 1, "author": "claude",
    "updated": "2026-07-30T11:00:00+00:00",
    "now": {"task": MARKER},
})
#: Every legacy read route, with one byte string its 200 answer certainly
#: carries and a refusal certainly must not. `/` and `/panel/graph.html` carry
#: no project byte, so their witness is the packaged document's own title tag;
#: without it a 403 body could not be told apart from a served page.
WITNESS = {
    "/": b"<title>",
    "/panel/graph.html": b"<title>",
    "/state.json": MARKER.encode("ascii"),
    "/harnesses.json": b"claude-code",
    "/lane/claude.json": MARKER.encode("ascii"),
    "/handoff/claude.md": MARKER.encode("ascii"),
}
GREETING = b'data: {"kind":"state"}'


@contextlib.contextmanager
def _serving(tmp_path):
    """Serve one marked project on a real OS-assigned loopback port."""
    root = write_project(tmp_path, map_toml=MAP_TOML, lanes={"claude": LANE})
    subject = server.build(root, port=0)
    thread = threading.Thread(target=subject.serve_forever, daemon=True)
    thread.start()
    try:
        yield subject
    finally:
        subject.shutdown()
        subject.server_close()


def _get(port: int, path: str, *, host: str):
    """GET one route over a real socket with an explicitly chosen Host.

    `urllib` suppresses its own computed Host once the caller supplies one, so
    the connection still goes to 127.0.0.1 while the wire carries whatever name
    a rebinding page would have carried.
    """
    call = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", headers={"Host": host}, method="GET")
    try:
        with urllib.request.urlopen(call, timeout=10) as answer:
            return answer.status, answer.read(), dict(answer.headers)
    except urllib.error.HTTPError as refused:
        return refused.code, refused.read(), dict(refused.headers)


def _raw_get(port: int, target: str, header_lines, *, stop: bytes | None = None) -> bytes:
    """Hand-write a request and return every byte the server answers with.

    `urllib` will not send two Host headers, nor none at all, and it will not
    show the response line of a stream it is still reading — so header
    cardinality and the SSE ordering claim both need the raw wire.
    """
    request = (
        f"GET {target} HTTP/1.1\r\n"
        + "".join(f"{name}: {value}\r\n" for name, value in header_lines)
        + "\r\n"
    ).encode("ascii")
    received = bytearray()
    with socket.create_connection(("127.0.0.1", port), timeout=5) as client:
        client.sendall(request)
        while True:
            try:
                chunk = client.recv(4096)
            except OSError:
                break
            if not chunk:
                break
            received.extend(chunk)
            if stop is not None and stop in received:
                break
    return bytes(received)


def _packaged(name: str) -> bytes:
    return (importlib.resources.files("conductor") / "panel" / name).read_bytes()


def _assert_served(path: str, status: int, body: bytes, headers: dict) -> None:
    """Assert the exact document each read route owes, not merely a 200."""
    assert status == 200, path
    assert headers["Cache-Control"] == "no-store", path
    if path == "/":
        assert headers["Content-Type"] == "text/html; charset=utf-8"
        assert body == _packaged("index.html")
    elif path == "/panel/graph.html":
        assert headers["Content-Type"] == "text/html; charset=utf-8"
        assert body == _packaged("graph.html")
    elif path == "/state.json":
        assert headers["Content-Type"] == "application/json; charset=utf-8"
        assert json.loads(body)["project"] == MARKER
    elif path == "/harnesses.json":
        assert headers["Content-Type"] == "application/json; charset=utf-8"
        assert json.loads(body) == harnesses.as_payload()
    elif path == "/lane/claude.json":
        assert headers["Content-Type"] == "application/json; charset=utf-8"
        assert json.loads(body) == json.loads(LANE)
    elif path == "/handoff/claude.md":
        assert headers["Content-Type"] == "text/markdown; charset=utf-8"
        assert f"Project: {MARKER}" in body.decode("utf-8")
    else:
        raise AssertionError(f"unlisted read route {path!r}")


def test_every_panel_read_route_still_serves_both_loopback_names_the_process_minted(
        tmp_path):
    """A Host gate that broke the panel would be a denial of service, not a fix."""
    with _serving(tmp_path) as subject:
        port = subject.server_address[1]
        for host in (f"127.0.0.1:{port}", f"localhost:{port}"):
            for path in WITNESS:
                status, body, headers = _get(port, path, host=host)
                _assert_served(path, status, body, headers)
                assert WITNESS[path] in body, (host, path)


def test_no_panel_read_route_answers_a_foreign_host_and_none_leaks_a_project_byte(
        tmp_path):
    """The whole point: a rebinding page must read nothing, not merely be logged."""
    with _serving(tmp_path) as subject:
        port = subject.server_address[1]
        foreign = f"evil.example.com:{port}"
        for path in WITNESS:
            status, body, headers = _get(port, path, host=foreign)
            assert status == 403, path
            assert WITNESS[path] not in body, path
            assert MARKER.encode("ascii") not in body, path
            assert headers["Cache-Control"] == "no-store", path


def test_the_read_arm_spends_the_same_two_host_values_the_command_session_minted(
        tmp_path):
    """One allowlist, or widening the command arm silently widens the panel too.

    The accepted set is read off the live session rather than copied into this
    file, so a second allowlist grown beside it would show up here as a name
    the read arm serves that the session never minted — and the near misses
    below are the shapes a hand-rolled comparison would most likely admit.
    """
    with _serving(tmp_path) as subject:
        port = subject.server_address[1]
        for host in sorted(subject.command_session.allowed_hosts):
            status, _body, _headers = _get(port, "/state.json", host=host)
            assert status == 200, host
        near_misses = (
            "127.0.0.1", f"LOCALHOST:{port}", f"[::1]:{port}",
            f"127.0.0.1:{port}.", f"localhost:{port + 1}",
        )
        for host in near_misses:
            status, body, _headers = _get(port, "/state.json", host=host)
            assert status == 403, host
            assert MARKER.encode("ascii") not in body, host


def test_a_read_needs_exactly_one_host_header_neither_two_nor_none(tmp_path):
    """Cardinality is the rule, not similarity: two agreeing Hosts still refuse.

    A proxy that appends its own Host leaves the handler two truths and no way
    to pick, which is precisely the ambiguity the transport already refuses for
    a mutation. The single-Host exchange at the end is the calibration: the same
    hand-written writer serves a 200, so a 403 above is about the header.
    """
    with _serving(tmp_path) as subject:
        port = subject.server_address[1]
        allowed = f"127.0.0.1:{port}"
        doubled = _raw_get(
            port, "/state.json", (("Host", allowed), ("Host", allowed)))
        assert doubled.startswith(b"HTTP/1.0 403"), doubled[:64]
        assert MARKER.encode("ascii") not in doubled
        absent = _raw_get(port, "/state.json", ())
        assert absent.startswith(b"HTTP/1.0 403"), absent[:64]
        assert MARKER.encode("ascii") not in absent
        single = _raw_get(port, "/state.json", (("Host", allowed),))
        assert single.startswith(b"HTTP/1.0 200"), single[:64]
        assert MARKER.encode("ascii") in single


def test_the_events_stream_refuses_a_foreign_host_before_it_commits_a_200(tmp_path):
    """`_serve_events` writes its status line first; a late 403 would be a lie.

    Once `send_response(200)` and `end_headers()` have run there is no status
    left to send, so the only honest refusal is one that happens before dispatch
    reaches the stream. That is what the first bytes on the wire prove here.
    """
    with _serving(tmp_path) as subject:
        port = subject.server_address[1]
        answer = _raw_get(
            port, "/events", (("Host", f"evil.example.com:{port}"),))
        assert answer.startswith(b"HTTP/1.0 403"), answer[:64]
        assert b"text/event-stream" not in answer
        assert GREETING not in answer
        assert MARKER.encode("ascii") not in answer


def test_the_events_stream_still_opens_and_greets_an_allowed_host(tmp_path):
    """The panel's only live channel; refusing it would blank every badge."""
    with _serving(tmp_path) as subject:
        port = subject.server_address[1]
        for host in (f"127.0.0.1:{port}", f"localhost:{port}"):
            answer = _raw_get(port, "/events", (("Host", host),), stop=GREETING)
            assert answer.startswith(b"HTTP/1.0 200"), (host, answer[:64])
            assert b"Content-Type: text/event-stream" in answer, host
            assert GREETING in answer, host


def test_the_command_arm_keeps_its_own_json_refusal_while_the_read_arm_answers_prose(
        tmp_path):
    """Over-correction control: the gate belongs after the command branch.

    The command surface refuses a foreign Host in the frozen error envelope and
    owns that vocabulary. A read gate placed one line too early would answer
    `/command/session` in the legacy read arm's plain prose instead — the two
    shapes below are what makes that mistake visible rather than invisible.
    """
    with _serving(tmp_path) as subject:
        port = subject.server_address[1]
        foreign = f"evil.example.com:{port}"
        status, body, headers = _get(port, "/command/session", host=foreign)
        assert status == 403
        assert headers["Content-Type"] == "application/json; charset=utf-8"
        assert json.loads(body) == {"error": {
            "code": "same_origin_denied",
            "message": "request Host is not allowed", "detail": {}}}
        read_status, read_body, read_headers = _get(
            port, "/state.json", host=foreign)
        assert read_status == 403
        assert read_headers["Content-Type"] == "text/plain; charset=utf-8"
        with pytest.raises(json.JSONDecodeError):
            json.loads(read_body)


def test_an_allowed_host_still_reaches_the_command_surface_unchanged(tmp_path):
    """The read gate must not have become a second gate the command arm pays."""
    with _serving(tmp_path) as subject:
        port = subject.server_address[1]
        status, body, _headers = _get(
            port, "/command/session", host=f"127.0.0.1:{port}")
        assert status == 200
        payload = json.loads(body)
        assert payload["origin"] == f"http://127.0.0.1:{port}"
        assert payload["csrf_token"]
