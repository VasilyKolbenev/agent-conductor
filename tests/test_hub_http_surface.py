"""The hub's HTTP surface over real sockets (spec 4.6.2, 4.6.3, 4.6.4, 4.6.7).

Transport first, the same for every route: the one Host (`localhost:<hub>` is refused and the
refusal names the address that works, before any route is chosen), Origin, the hub's own CSRF
token, the JSON content type and the 64 KiB limit, no CORS header anywhere, the hub's policy
exactly once on every answer (assets, JSON, refusals, the event stream, the pages the standard
library writes for a bad request), a query is never part of a route, a key that names a place on
disk is refused at any depth, and no answer holds an absolute path. Then the live routes in the
forms of 4.6.4, the stream that carries identifiers only, and the writes that change which
project is active: each refusal of 4.6.3 is reached and leaves `hub-state.json` byte for byte as
it was.
"""
from __future__ import annotations

import json
import re
import threading
import time

import pytest

from conductor.hub import events, operations, refusals, routes, server
from conductor.hub.assets import HUB_ASSETS
from tests._hub_fake_child import FakeChild, run_row, serve_standard, task_row
from tests._hub_stack import A, B, C, Stack, raw_exchange, request

CSP = ("default-src 'self'; frame-src http://127.0.0.1:*; frame-ancestors 'none'; "
       "base-uri 'none'; form-action 'none'; object-src 'none'")
ACTIVATE = "/hub/projects/{}/activate"


@pytest.fixture
def stack(tmp_path):
    made = Stack(tmp_path)
    yield made
    made.close()


def _envelope(reply) -> dict:
    body = reply.json()
    assert set(body) == {"error"} and set(body["error"]) == {"code", "message", "detail"}
    return body["error"]


def _code(reply, status: int) -> str:
    assert reply.status == status, (reply.status, reply.body[:200])
    return _envelope(reply)["code"]


# -- the Host ------------------------------------------------------------------------------------


def test_localhost_is_refused_on_every_method_and_the_refusal_names_the_address_that_works(stack):
    for method in ("GET", "POST", "OPTIONS", "HEAD", "PUT"):
        reply = request(stack.port, method, "/hub/projects", host=f"localhost:{stack.port}")
        assert reply.status == 403, method
        if method != "HEAD":
            assert _envelope(reply)["code"] == "same_origin_denied"
            assert f"http://127.0.0.1:{stack.port}" in reply.body.decode("utf-8")


def test_the_host_is_judged_before_the_route_and_before_the_stream_opens(stack):
    for target in ("/hub/nothing-here", "/hub/events", "/", "/hub/hub.js", "/hub/session"):
        reply = request(stack.port, "GET", target, host=f"localhost:{stack.port}")
        assert _code(reply, 403) == "same_origin_denied", target
        assert reply.header("Content-Type") == ["application/json; charset=utf-8"]


def test_a_host_that_is_wrong_missing_or_doubled_is_refused(stack):
    for host in (f"127.0.0.1:{stack.port + 1}", "127.0.0.1", "evil.example", None):
        assert _code(request(stack.port, "GET", "/hub/projects", host=host), 403) == \
            "same_origin_denied", host
    doubled = raw_exchange(stack.port, (
        f"GET /hub/projects HTTP/1.1\r\nHost: 127.0.0.1:{stack.port}\r\n"
        f"Host: 127.0.0.1:{stack.port}\r\nConnection: close\r\n\r\n").encode("ascii"))
    assert doubled.startswith(b"HTTP/1.1 403")


# -- writes: Origin, token, type, size ----------------------------------------------------------


def test_a_write_from_another_origin_or_with_none_is_refused_before_anything_is_done(stack):
    before = stack.state_bytes()
    target = ACTIVATE.format(A)
    for origin in (f"http://localhost:{stack.port}", "http://evil.example", None,
                   f"http://127.0.0.1:{stack.port + 1}"):
        assert _code(stack.post(target, origin=origin), 403) == "same_origin_denied", origin
    assert stack.state_bytes() == before and stack.world.spawner.calls == []


def test_a_write_needs_the_hubs_own_token_and_not_a_childs_or_none(stack):
    target = ACTIVATE.format(A)
    for token in ("not-the-token", "", None, stack.token + "x"):
        assert _code(stack.post(target, token=token), 403) == "csrf_denied", token
    assert stack.post(target).status == 202


def test_a_write_must_be_one_json_object_of_the_right_type_and_at_most_64_kib(stack):
    target = ACTIVATE.format(A)
    for kind in ("text/plain", "application/x-www-form-urlencoded", None):
        assert _code(stack.post(target, content_type=kind), 400) == "malformed_request", kind
    for raw in (b"[]", b"3", b"not json", b'{"a": 1, "a": 2}', b"", b'{"a": NaN}'):
        assert _code(stack.post(target, body=raw), 400) == "malformed_request", raw
    edge = json.dumps({"order": []}).encode("utf-8")
    assert stack.post("/hub/queue/order", body=edge).status == 200


def test_a_body_over_64_kib_is_refused_on_its_length_alone_and_the_connection_ends(stack):
    """The length is announced and the body never sent: the limit is judged from the header."""
    def head(length: int) -> bytes:
        lines = ("POST /hub/queue/order HTTP/1.1", f"Host: 127.0.0.1:{stack.port}",
                 f"Origin: http://127.0.0.1:{stack.port}", f"X-Conduct-CSRF: {stack.token}",
                 "Content-Type: application/json", f"Content-Length: {length}", "", "")
        return "\r\n".join(lines).encode("ascii")

    answered = raw_exchange(stack.port, head(64 * 1024 + 1))
    assert answered.startswith(b"HTTP/1.1 400") and b"malformed_request" in answered
    assert b"Connection: close" in answered
    assert raw_exchange(stack.port, head(64 * 1024), wait=0.5) == b"", \
        "a length at the limit is accepted, and the server waits for its body"


def test_a_refused_write_leaves_the_connection_usable_or_closed_never_confused(stack):
    """The body of a write refused before it is read is not left for the next request."""
    payload = b'{"order": []}' + b" " * 100
    first = (f"POST /hub/queue/order HTTP/1.1\r\nHost: 127.0.0.1:{stack.port}\r\n"
             f"Content-Type: application/json\r\nContent-Length: {len(payload)}\r\n\r\n"
             ).encode("ascii") + payload
    second = (f"GET /hub/session HTTP/1.1\r\nHost: 127.0.0.1:{stack.port}\r\n"
              "Connection: close\r\n\r\n").encode("ascii")
    answered = raw_exchange(stack.port, first + second)
    assert answered.count(b"HTTP/1.1 ") <= 2
    assert answered.startswith(b"HTTP/1.1 403"), "no Origin and no token"
    assert b"csrf_token" not in answered.split(b"\r\n\r\n", 1)[0]


# -- methods, CORS, the policy, the query ----------------------------------------------------------


def test_other_methods_are_405_on_known_paths_and_404_on_the_rest_and_carry_no_cors(stack):
    for method in ("OPTIONS", "PUT", "PATCH", "DELETE", "TRACE", "HEAD", "CONNECT"):
        reply = request(stack.port, method, "/hub/projects")
        assert reply.status == 405, method
        assert not [k for k, _ in reply.headers if k.lower().startswith("access-control")]
        unknown = request(stack.port, method, "/hub/nothing")
        assert unknown.status == 404, method
        if method != "HEAD":
            assert _envelope(reply)["code"] == "method_not_allowed"
            assert _envelope(unknown)["code"] == "route_not_found"
    preflight = request(stack.port, "OPTIONS", "/hub/queue/order", headers={
        "Origin": "http://evil.example", "Access-Control-Request-Method": "POST"})
    assert preflight.status == 405
    assert not [k for k, _ in preflight.headers if k.lower().startswith("access-control")]


def test_no_answer_of_any_kind_carries_a_cors_header(stack):
    replies = [stack.get(t) for t in ("/", "/hub/hub.js", "/hub/session", "/hub/projects",
                                      "/hub/nothing", "/hub/setup?x=1")]
    replies.append(stack.post("/hub/queue/order", {"order": []}))
    replies.append(stack.post("/hub/queue/order", {"bad": 1}))
    for reply in replies:
        assert not [k for k, _ in reply.headers if k.lower().startswith("access-control")]
        assert reply.header("Cache-Control") == ["no-store"]


def _policies(reply) -> list[str]:
    return reply.header("Content-Security-Policy")


def test_the_hubs_policy_is_on_every_answer_exactly_once(stack):
    assets = list(HUB_ASSETS)
    replies = [stack.get(t) for t in ("/", "/hub/session", "/hub/projects", "/hub/limits",
                                      "/hub/setup", "/hub/nothing", "/hub/projects?x=1",
                                      "/hub/operations/operation-" + "0" * 32, *assets)]
    replies += [request(stack.port, m, "/hub/projects") for m in ("HEAD", "OPTIONS", "PUT")]
    replies += [request(stack.port, "GET", "/", host="localhost:1")]
    replies += [stack.post("/hub/queue/order", {"order": []}), stack.post("/hub/queue/order", {}),
                stack.post(ACTIVATE.format("f" * 32)), stack.post("/hub/queue/order", token=None)]
    for reply in replies:
        assert _policies(reply) == [CSP], (reply.status, reply.headers)
    assert server.HUB_CSP == CSP


def test_the_policy_is_on_the_pages_the_standard_library_writes_and_on_the_stream(stack):
    port = stack.port
    bad_line = raw_exchange(port, (f"GET /hub/projects extra HTTP/1.1\r\n"
                                   f"Host: 127.0.0.1:{port}\r\n\r\n").encode("ascii"))
    assert bad_line.startswith(b"HTTP/") and b"400" in bad_line.split(b"\r\n", 1)[0]
    unknown_method = raw_exchange(port, (f"FOO /hub/projects HTTP/1.1\r\nHost: 127.0.0.1:{port}"
                                         "\r\nConnection: close\r\n\r\n").encode("ascii"))
    too_long = raw_exchange(port, b"GET /" + b"a" * 70000 + b" HTTP/1.1\r\n\r\n")
    for answered in (bad_line, unknown_method, too_long):
        head = answered.split(b"\r\n\r\n", 1)[0].decode("latin-1")
        assert head.lower().count("content-security-policy:") == 1, head
        assert f"Content-Security-Policy: {CSP}" in head
    assert unknown_method.split(b"\r\n", 1)[0].split()[1] == b"405"
    stream = raw_exchange(port, (f"GET /hub/events HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
                                 "Connection: close\r\n\r\n").encode("ascii"), wait=0.6)
    head = stream.split(b"\r\n\r\n", 1)[0].decode("latin-1")
    assert head.lower().count("content-security-policy:") == 1 and "text/event-stream" in head


def test_a_query_is_never_part_of_a_route_on_a_get_or_a_write(stack):
    for target in ("/hub/projects?x=1", "/hub/session?", "/?a", "/hub/hub.js?v=2"):
        assert _code(stack.get(target), 404) == "route_not_found", target
    assert _code(stack.post("/hub/queue/order?force=1", {"order": []}), 404) == "route_not_found"
    assert _code(stack.post(ACTIVATE.format(A) + "?x=1"), 404) == "route_not_found"


# -- the body's keys ---------------------------------------------------------------------------


@pytest.mark.parametrize("body", [
    {"root": "C:\\x"}, {"path": "x"}, {"dir": "x"}, {"order": [], "root": "x"},
    {"order": [{"path": "x"}]}, {"a": {"b": [{"c": {"dir": 1}}]}}])
def test_a_key_that_names_a_place_is_422_before_the_route_is_judged(stack, body):
    for target in ("/hub/queue/order", ACTIVATE.format("f" * 32), ACTIVATE.format(A)):
        assert _code(stack.post(target, body), 422) == "contract_invalid", (target, body)
    assert stack.world.spawner.calls == []


def test_a_key_the_route_does_not_take_or_a_missing_one_is_422(stack):
    assert _code(stack.post("/hub/queue/order", {"order": [], "extra": 1}), 422) == \
        "contract_invalid"
    assert _code(stack.post("/hub/queue/order", {}), 422) == "contract_invalid"
    assert _code(stack.post(ACTIVATE.format(A), {"force": True}), 422) == "contract_invalid"
    assert _code(stack.post("/hub/dialogs/folder", {}), 422) == "contract_invalid"


def test_an_order_that_is_not_a_list_of_ids_is_422_and_writes_nothing(stack):
    before = stack.state_bytes()
    for order in ("abc", [1], ["x"], [A.upper()], None, {"a": 1}):
        assert _code(stack.post("/hub/queue/order", {"order": order}), 422) == "contract_invalid"
    assert stack.state_bytes() == before


# -- what the answers hold -----------------------------------------------------------------------


def test_the_session_is_the_token_and_the_hubs_own_origin_and_nothing_else(stack):
    reply = stack.get("/hub/session")
    assert reply.status == 200 and set(reply.json()) == {"csrf_token", "origin"}
    assert reply.json()["origin"] == f"http://127.0.0.1:{stack.port}"
    assert len(reply.json()["csrf_token"]) >= 43
    assert stack.get("/hub/session").json() == reply.json(), "one token for the life of the hub"


def test_every_file_of_the_registry_and_the_page_is_served_with_its_type_and_its_bytes(stack):
    import importlib.resources as resources
    panel = resources.files("conductor") / "panel"
    for route, (content_type, name) in HUB_ASSETS.items():
        reply = stack.get(route)
        assert reply.status == 200 and reply.header("Content-Type") == [content_type], route
        assert reply.body == (panel / name).read_bytes(), route
    page = stack.get("/")
    assert page.status == 200 and page.header("Content-Type") == ["text/html; charset=utf-8"]
    assert page.body == (panel / "hub.html").read_bytes()
    assert _code(stack.get("/hub/hub.html"), 404) == "route_not_found"
    assert _code(stack.get("/hub/studio.js"), 404) == "route_not_found"


def _keys_of(fixture: str) -> set[str]:
    from pathlib import Path
    path = Path(__file__).resolve().parent / "fixtures" / "hub" / fixture
    return set(json.loads(path.read_text(encoding="utf-8"))["response"])


def test_the_reads_answer_in_the_forms_of_the_fixture_the_spec_and_one_added_key_make(stack):
    projects = stack.get("/hub/projects").json()
    assert set(projects) == _keys_of("hub_projects.json"), "the fixture is the form"
    assert projects["unlisted_closing"] == [] and len(projects["projects"]) == 3
    assert projects["projects_home"] == {"state": "default", "name": "ConductProjects"}
    assert set(stack.get("/hub/limits").json()) == _keys_of("hub_limits.json")
    setup = stack.get("/hub/setup").json()
    assert set(setup) == _keys_of("hub_setup.json")
    assert setup["hub_job"] == "none" and setup["logins"] == []
    assert set(setup["tools"]) == {"gh", "git"} and setup["profile"] == "absent"
    assert setup["projects_home"] == {"state": "default", "name": "ConductProjects",
                                      "default_name": "ConductProjects"}


def test_no_answer_holds_an_absolute_path_even_with_deep_roots(stack):
    for reply in (stack.get("/hub/projects"), stack.get("/hub/limits"), stack.get("/hub/setup"),
                  stack.get("/hub/session"), stack.post(ACTIVATE.format("f" * 32)),
                  stack.post(ACTIVATE.format(A), {"path": "x"})):
        text = reply.body.decode("utf-8")
        for name, root in stack.world.roots.items():
            assert root not in text and json.dumps(root)[1:-1] not in text, (name, text[:200])
        assert not re.search(r"[A-Za-z]:[\\/]", text.replace("http://", "")), text[:200]
        assert str(stack.world.home) not in text
    rows = stack.get("/hub/projects").json()["projects"]
    assert [row["folder"] for row in rows] == ["a", "b", "c"]


def test_a_registry_that_cannot_be_read_is_409_registry_invalid_and_is_not_rewritten(stack):
    path = stack.world.home / "registry.json"
    path.write_text("{not json", encoding="utf-8")
    assert _code(stack.get("/hub/projects"), 409) == "registry_invalid"
    assert path.read_text(encoding="utf-8") == "{not json"


# -- the routes this build answers, and the ones it does not -------------------------------

LIVE = {("GET", "/"), ("GET", "/hub/<name>"), ("GET", "/hub/session"), ("GET", "/hub/events"),
        ("GET", "/hub/projects"), ("GET", "/hub/limits"), ("GET", "/hub/setup"),
        ("GET", "/hub/operations/<operation_id>"), ("GET", "/hub/dialogs/<pick_id>"),
        ("POST", "/hub/dialogs/folder"), ("POST", "/hub/dialogs/<pick_id>/cancel"),
        ("POST", "/hub/projects"),
        ("POST", "/hub/projects/<project_id>/activate"),
        ("POST", "/hub/projects/<project_id>/view"), ("POST", "/hub/projects/<project_id>/stop"),
        ("POST", "/hub/projects/<project_id>/forget"), ("POST", "/hub/queue/order")}


def test_the_live_routes_are_these_and_are_all_rows_of_the_table():
    assert set(server.LIVE_ROUTES) == LIVE
    assert LIVE <= {(row.method, row.path) for row in routes.HUB_ROUTES}


def test_a_route_of_the_table_with_no_handler_yet_answers_route_not_found_and_says_so(stack):
    ids = {"project_id": A, "operation_id": "operation-" + "0" * 32, "pick_id": "pick-" + "0" * 32,
           "login_key": "ab" * 32, "tool": "gh", "owner": "octocat"}
    bodies = {"/hub/dialogs/folder": {"purpose": "project"},
              "/hub/setup/projects-home": {"default": True},
              "/hub/tools/<tool>/pin": {"candidate_id": "cand-" + "0" * 32},
              "/hub/projects": {"source": "scratch", "folder": "x", "name": "x"}}
    checked = 0
    for row in routes.HUB_ROUTES:
        if (row.method, row.path) in LIVE:
            continue
        target = re.sub(r"<([a-z_]+)>", lambda hit: ids[hit.group(1)], row.path)
        reply = stack.get(target) if row.method == "GET" else stack.post(
            target, bodies.get(row.path, {}))
        assert _code(reply, 404) == "route_not_found", (row.method, row.path)
        assert _envelope(reply)["detail"] == {"reason": "not in this build"}
        checked += 1
    assert checked == len(routes.HUB_ROUTES) - len(LIVE) == 9


def test_hub_dialog_issues_only_a_pick_id_and_reads_a_safe_folder_name(stack, tmp_path):
    folder = tmp_path / "chosen"
    folder.mkdir()
    stack.service._dialogs._choose = lambda _ident: {"path": str(folder)}
    stack.service._dialogs._available = lambda: True
    sent = stack.post("/hub/dialogs/folder", {"purpose": "project"})
    assert sent.status == 202
    ident = sent.json()["pick_id"]
    for _ in range(100):
        row = stack.get(f"/hub/dialogs/{ident}").json()
        if row["state"] != "open":
            break
        time.sleep(.01)
    assert row == {"pick_id": ident, "purpose": "project", "state": "picked",
                   "folder": "chosen", "project": "none", "code": None}
    assert str(folder) not in json.dumps(row)
    assert stack.post(f"/hub/dialogs/{ident}/cancel", {}).status == 200
    assert stack.get(f"/hub/dialogs/{ident}").json()["state"] == "cancelled"


def test_add_project_requires_a_hub_issued_pick_and_never_accepts_a_web_path(stack):
    pick = "pick-" + "0" * 32
    assert _code(stack.post("/hub/projects", {"source": "folder", "pick_id": pick,
               "name": "Example", "legacy_writers_stopped": True}), 409) == "pick_invalid"
    assert _code(stack.post("/hub/projects", {"source": "folder", "pick_id": pick,
               "name": "Example", "legacy_writers_stopped": True,
               "dir": "C:\\secret"}), 422) == "contract_invalid"
    assert _code(stack.get("/hub/operations/operation-" + "0" * 32), 404) == \
        "operation_not_found"


def test_hub_issued_folder_pick_runs_the_real_cli_and_exposes_a_pathless_operation(
        stack, tmp_path, monkeypatch):
    project = tmp_path / "new-project"
    project.mkdir()
    monkeypatch.setenv("CONDUCT_HOME", str(stack.world.home))
    pick_id = "pick-" + "1" * 32
    stack.service._pick_resolver = lambda ident: (
        operations.FolderPick(str(project), "none") if ident == pick_id else None)
    stack.service._consume_pick = lambda _ident: None
    stack.service._operations._start = lambda _project_id: None
    stack.service._operations._status = lambda _project_id: ("running", None)
    sent = stack.post("/hub/projects", {"source": "folder", "pick_id": pick_id,
                      "name": "New project", "legacy_writers_stopped": False})
    assert sent.status == 202
    ident = sent.json()["operation_id"]
    for _ in range(100):
        row = stack.get(f"/hub/operations/{ident}").json()
        if row["state"] != "running":
            break
        time.sleep(0.05)
    assert row["state"] == "succeeded", row
    assert row["step"] == "start" and row["result"]["folder"] == "new-project"
    assert "root" not in row["result"] and str(project) not in json.dumps(row)
    stack.tick()
    assert any(one["project_id"] == row["project_id"] for one in
               stack.get("/hub/projects").json()["projects"])


# -- the stream ------------------------------------------------------------------------------------


def _open_stream(port: int) -> tuple:
    import socket
    sock = socket.create_connection(("127.0.0.1", port), timeout=5)
    sock.sendall((f"GET /hub/events HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
                  "Connection: close\r\n\r\n").encode("ascii"))
    return sock, bytearray()


def _frames(sock, seen: bytearray, want: int, seconds: float = 5.0) -> list[dict]:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        body = bytes(seen).split(b"\r\n\r\n", 1)
        found = [] if len(body) < 2 else [json.loads(part[len(b"data: "):])
                                          for part in body[1].split(b"\n\n")
                                          if part.startswith(b"data: ")]
        if len(found) >= want:
            return found
        try:
            seen.extend(sock.recv(4096))
        except TimeoutError:
            continue
    return found


def test_the_stream_starts_with_projects_then_carries_identifiers_only(stack):
    sock, seen = _open_stream(stack.port)
    try:
        assert _frames(sock, seen, 1) == [{"kind": "projects"}]
        stack.bus.publish("project", project_id=A)
        stack.bus.publish("limits")
        stack.bus.publish("operation", operation_id="operation-" + "0" * 32)
        got = _frames(sock, seen, 4)
        assert got[1:] == [{"kind": "project", "project_id": A}, {"kind": "limits"},
                           {"kind": "operation", "operation_id": "operation-" + "0" * 32}]
        for one in got:
            assert set(one) == {"kind", *events.FRAME_KEYS[one["kind"]]}
    finally:
        sock.close()


def test_a_client_that_leaves_the_stream_is_forgotten(stack):
    sock, seen = _open_stream(stack.port)
    _frames(sock, seen, 1)
    assert stack.bus.clients == 1
    sock.close()
    deadline = time.monotonic() + 8
    while stack.bus.clients and time.monotonic() < deadline:
        stack.bus.publish("limits")
        time.sleep(0.1)
    assert stack.bus.clients == 0


def test_a_hub_that_shuts_down_ends_its_streams(stack):
    sock, seen = _open_stream(stack.port)
    _frames(sock, seen, 1)
    threading.Thread(target=stack.server.shutdown, daemon=True).start()
    sock.settimeout(5)
    end = time.monotonic() + 8
    closed = False
    while time.monotonic() < end and not closed:
        try:
            closed = sock.recv(4096) == b""
        except TimeoutError:
            continue
    sock.close()
    assert closed


def test_an_unknown_kind_of_frame_cannot_be_built():
    for bad in ({"kind": "run", "run_id": "x"}, {"kind": "project"},
                {"kind": "project", "project_id": "not-hex"}, {"kind": "limits", "x": "y"},
                {"kind": "pick", "pick_id": "pick-" + "G" * 32}):
        kind = bad.pop("kind")
        with pytest.raises(ValueError):
            events.frame(kind, **bad)


# -- the writes that change which project is active or open ---------------------------------


def _running(stack, name: str = "a", *, mode: str = "active", port: int = 7701) -> None:
    stack.world.alive.add({"a": 101, "b": 202, "c": 303}[name])
    stack.world.put_status(name, "serving", mode=mode, port=port)


def _refused_and_unchanged(stack, target: str, status: int, code: str, body=None) -> None:
    before = stack.state_bytes()
    calls = len(stack.world.spawner.calls)
    assert _code(stack.post(target, body), status) == code, target
    assert stack.state_bytes() == before, f"{code} changed hub-state.json"
    assert len(stack.world.spawner.calls) == calls


def test_activating_a_project_answers_202_and_the_move_shows_in_its_row(stack):
    reply = stack.post(ACTIVATE.format(A))
    assert reply.status == 202 and reply.json() == {"project_id": A, "working": "active"}
    stack.tick()
    (call,) = stack.world.spawner.calls
    assert (call["project_id"], call["mode"]) == (A, "active")
    row = stack.get("/hub/projects").json()["projects"][0]
    assert (row["project_id"], row["working"]) == (A, "active")


def test_activate_and_view_refuse_by_the_rules_of_the_table_and_change_nothing(stack):
    ghost = "f" * 32
    _refused_and_unchanged(stack, ACTIVATE.format(ghost), 404, "project_not_found")
    _refused_and_unchanged(stack, f"/hub/projects/{ghost}/view", 404, "project_not_found")
    stack.post(ACTIVATE.format(A))
    stack.tick()
    _running(stack, "a", port=stack.port)
    _refused_and_unchanged(stack, ACTIVATE.format(A), 409, "already_active")
    _refused_and_unchanged(stack, f"/hub/projects/{A}/view", 409, "already_active")
    stack.world.spawner.refusal = server_refusal()
    _refused_and_unchanged(stack, ACTIVATE.format(B), 409, "hub_in_kill_on_close_job")
    _refused_and_unchanged(stack, f"/hub/projects/{B}/view", 409, "hub_in_kill_on_close_job")
    stack.world.spawner.refusal = None
    stack.post(f"/hub/projects/{B}/view")
    _running(stack, "b", mode="view", port=stack.port)
    _refused_and_unchanged(stack, f"/hub/projects/{B}/view", 409, "project_running")


@pytest.mark.parametrize("route", ["activate", "view"])
def test_activate_and_view_answer_409_registry_invalid_when_hub_state_cannot_be_read(
        stack, route, capsys):
    path = stack.world.home / "hub-state.json"
    path.write_bytes(b"{not json")
    reply = stack.post(f"/hub/projects/{A}/{route}")
    assert _code(reply, 409) == "registry_invalid"
    assert _envelope(reply)["detail"] == {"file": "hub-state.json"}
    assert path.read_bytes() == b"{not json", "the unreadable file was written over"
    assert stack.world.spawner.calls == [], "a child was started on a state nobody could read"
    assert "Traceback" not in capsys.readouterr().err


def test_each_read_of_the_supervisors_status_refuses_a_hub_state_that_cannot_be_read(stack):
    """A reorder of `_state()` ahead of `_status()` would leave these two reads exposed."""
    assert stack.post(ACTIVATE.format(A)).status == 202
    whole = stack.world.store.load()
    (stack.world.home / "hub-state.json").write_bytes(b"{not json")
    for read in (lambda: stack.service._status(stack.service._require(A)),
                 lambda: stack.service._require_the_active_can_yield(whole, B)):
        with pytest.raises(refusals.HubRefusal) as caught:
            read()
        assert (caught.value.code, dict(caught.value.detail)) == (
            "registry_invalid", {"file": "hub-state.json"})


def server_refusal():
    from conductor.hub import spawn
    return spawn.SpawnRefused("hub_in_kill_on_close_job", "a job")


def test_a_project_that_cannot_be_used_is_refused_by_what_state_it_is_in(stack):
    stack.world.put_status("b", "stop_uncertain")                       # not confirmed stopped
    _refused_and_unchanged(stack, ACTIVATE.format(B), 409, "recovery_required")
    _refused_and_unchanged(stack, f"/hub/projects/{B}/view", 409, "recovery_required")
    stack.world.put_status("c", "refused", code="project_identity_changed")
    _refused_and_unchanged(stack, ACTIVATE.format(C), 409, "project_unavailable")
    _refused_and_unchanged(stack, f"/hub/projects/{C}/view", 409, "project_unavailable")
    row = {r["project_id"]: r for r in stack.get("/hub/projects").json()["projects"]}
    assert row[B]["state"] == "stop_uncertain" and row[C]["state"] == "identity_mismatch"


def test_a_folder_that_is_gone_or_another_reads_missing_and_cannot_be_activated(stack):
    stack.service._folder_ok = lambda project: project.project_id != C
    row = {r["project_id"]: r for r in stack.get("/hub/projects").json()["projects"]}
    assert row[C]["state"] == "missing" and row[A]["state"] == "stopped"
    _refused_and_unchanged(stack, ACTIVATE.format(C), 409, "project_unavailable")


def test_the_active_project_that_is_not_confirmed_closed_keeps_the_next_from_becoming_active(
        stack):
    stack.post(ACTIVATE.format(A))
    stack.tick()
    stack.world.gone("a", "stop_uncertain", head="opened")
    _refused_and_unchanged(stack, ACTIVATE.format(B), 409, "active_not_closed")


def test_stopping_answers_202_and_refuses_what_is_not_running_or_has_not_reported(stack):
    _refused_and_unchanged(stack, f"/hub/projects/{B}/stop", 409, "project_not_running")
    _refused_and_unchanged(stack, f"/hub/projects/{'f' * 32}/stop", 404, "project_not_found")
    stack.post(ACTIVATE.format(A))
    stack.tick()                                  # A's child started, and has reported nothing
    stack.world.alive.add(101)
    _refused_and_unchanged(stack, f"/hub/projects/{A}/stop", 409, "project_busy")
    _running(stack, "a", port=stack.port)
    reply = stack.post(f"/hub/projects/{A}/stop")
    assert reply.status == 202 and reply.json() == {"project_id": A, "state": "stopping"}
    assert stack.world.spawner.children[0].closed and stack.state_bytes() is not None


def test_forgetting_answers_200_and_refuses_a_running_project(stack):
    _running(stack, "b", mode="view", port=stack.port)
    _refused_and_unchanged(stack, f"/hub/projects/{B}/forget", 409, "project_running")
    reply = stack.post(f"/hub/projects/{C}/forget")
    assert reply.status == 200 and reply.json() == {"project_id": C}
    ids = [row["project_id"] for row in stack.get("/hub/projects").json()["projects"]]
    assert ids == [A, B]
    _refused_and_unchanged(stack, f"/hub/projects/{C}/forget", 404, "project_not_found")


def test_the_queue_is_reordered_only_by_a_permutation_of_itself(stack):
    from conductor.hub import state
    flag = "f1f1f1f1-f1f1-41f1-81f1-f1f1f1f1f1f1"
    stack.world.store.update(lambda s: state.enqueue(state.enqueue(s, B, flag), C, flag))
    before = stack.state_bytes()
    for wrong in ([B], [B, C, A], [B, B], [C, B, A], []):
        assert _code(stack.post("/hub/queue/order", {"order": wrong}), 409) == \
            "project_queue_changed", wrong
        assert stack.state_bytes() == before, "a refused order wrote something"
    reply = stack.post("/hub/queue/order", {"order": [C, B]})
    assert reply.status == 200 and reply.json() == {"project_queue": [C, B]}
    listed = stack.get("/hub/projects").json()
    assert listed["project_queue"] == [C, B]
    assert {r["project_id"]: r["queue_position"] for r in listed["projects"]}[C] == 1


def test_a_closing_entry_of_a_project_off_the_list_is_named_in_the_projects_answer(stack):
    stack.post(ACTIVATE.format(A))
    stack.tick()
    _running(stack, "a", port=stack.port)
    stack.post(f"/hub/projects/{A}/stop")
    stack.world.gone("a")                    # dead and closed, but no pass has proven it yet
    assert stack.post(f"/hub/projects/{A}/forget").status == 200
    stack.tick()
    listed = stack.get("/hub/projects").json()
    assert [row["project_id"] for row in listed["projects"]] == [B, C]
    (owed,) = listed["unlisted_closing"]
    assert set(owed) == {"project_id", "since", "action"} and owed["action"] == "relist"
    assert owed["project_id"] == A


def test_every_refusal_of_a_live_route_that_the_table_names_was_reached_above_or_is_listed_here():
    """A guard on this file: the refusals of the live rows the tests above do not reach."""
    reached = {"project_not_found", "already_active", "active_not_closed", "project_unavailable",
               "recovery_required", "project_busy", "hub_in_kill_on_close_job", "project_running",
               "project_not_running", "project_queue_changed", "operation_not_found",
               "pick_not_found", "dialog_busy", "dialog_unavailable"}
    # POST /hub/projects is live for folder picks only. Keep the full frozen route vocabulary,
    # including the not-yet-live github/scratch branches, explicit in this source guard.
    add_declared = {"name_invalid", "folder_invalid", "windows_name_unsafe", "repo_invalid",
                    "pick_invalid", "legacy_writers_unconfirmed", "folder_exists",
                    "projects_home_invalid", "git_not_pinned", "git_changed", "gh_not_pinned",
                    "gh_changed", "review_harness_missing", "operation_busy", "registry_busy",
                    "registry_invalid"}
    add_row = next(row for row in routes.HUB_ROUTES
                   if (row.method, row.path) == ("POST", "/hub/projects"))
    assert set(add_row.refusals) == add_declared
    named = {code for row in routes.HUB_ROUTES if (row.method, row.path) in LIVE
             for code in row.refusals}
    assert named <= reached | add_declared | {"route_not_found"}, sorted(named - reached - add_declared)
    assert reached <= set(refusals.HUB_ERROR_STATUS)


# -- a running child, read for real ---------------------------------------------------------------


def test_a_running_childs_tasks_reach_the_projects_answer_through_the_reader(stack):
    child = FakeChild(A)
    try:
        serve_standard(child, [task_row("task-001", "Fix the payment form")],
                       [run_row("run-001", "task-001")])
        stack.post(ACTIVATE.format(A))
        stack.tick()
        stack.world.alive.add(101)
        stack.world.put_status("a", "serving", port=child.port)
        stack.tick(2)
        row = stack.get("/hub/projects").json()["projects"][0]
        assert row["state"] == "running" and row["data"] == "live"
        assert row["desk_url"] == f"http://127.0.0.1:{child.port}/panel/desk.html"
        assert row["tasks"][0]["task"]["title"] == "Fix the payment form"
        assert {req.method for req in child.log} == {"GET"}
    finally:
        child.close()


def test_the_view_child_of_the_project_just_made_active_is_not_the_live_limits(stack):
    from conductor.hub import state

    quotas = {"as_of": "2026-09-30T09:00:00Z", "max_age_seconds": 300, "providers": [],
              "snapshots": []}
    assert stack.snapshots.put_limits(A, taken_at=quotas["as_of"], quotas=quotas) == "written"
    stack.world.store.update(lambda s: state.begin_switch(
        s, B, kind="manual", transition_id="00000000-0000-0000-0000-0000000000cc",
        since="2026-09-30T10:00:00Z", flag=None, previous=None))
    before = (stack.world.home / "limits.json").read_bytes()
    child = FakeChild(B, mode="view")
    try:
        serve_standard(child, [task_row("task-001", "Fix")], [run_row("run-001", "task-001")])
        child.put("/command/quotas", {**quotas, "hub_snapshot": {
            "project_id": A, "taken_at": quotas["as_of"]}})
        _running(stack, "b", mode="view", port=child.port)
        stack.mono.advance(31)
        stack.reader.step()
        assert any(req.target == "/command/quotas" for req in child.log), "the child was not read"
        answer = stack.get("/hub/limits").json()
        assert (answer["source"], answer["project_id"], answer["taken_at"]) == (
            "snapshot", A, quotas["as_of"]), "the view child's echo was served as live limits"
        assert (stack.world.home / "limits.json").read_bytes() == before
    finally:
        child.close()
