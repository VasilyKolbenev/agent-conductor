"""The table of the hub's routes, and the session that guards its writes (spec 4.6.2, 4.6.3).

`HUB_ROUTES` is one tuple, frozen here row by row the way `COMMAND_ROUTES` is frozen in
`test_command_http_api.py`: method, path, the exact key sets a body may have, and the refusals the
row names. Every path-parameter grammar is judged by ids it accepts and ids it does not, an unknown
path is `route_not_found` and a known path under another method is `method_not_allowed`, a query is
never part of a route, and the three bodies of `POST /hub/projects` are told apart by their keys.
`HubSession` has ONE allowed host, unlike the commands' session that has two.
"""
from __future__ import annotations

import re

import pytest

from conductor.command.http_transport import HttpRefusal
from conductor.hub import refusals, routes, session
from conductor.hub.assets import HUB_ASSETS

PROJECT = "3f9c0d5a7b2e4c168a90d3e1f4b7a625"
OPERATION = "operation-" + "0123456789abcdef" * 2
PICK = "pick-" + "fedcba9876543210" * 2
LOGIN = "ab" * 32
EMPTY = frozenset()
TRANSPORT = ("same_origin_denied", "csrf_denied", "malformed_request", "route_not_found",
             "method_not_allowed", "contract_invalid")

#: Every row of 4.6.3: (method, path) -> (the key sets a body may have, the refusals of the row).
#: The transport refusals act on all of them and are not repeated.
ROWS = {
    ("GET", "/"): ((), ()),
    ("GET", "/hub/<name>"): ((), ("route_not_found",)),
    ("GET", "/hub/session"): ((), ()),
    ("GET", "/hub/events"): ((), ()),
    ("GET", "/hub/projects"): ((), ()),
    ("GET", "/hub/limits"): ((), ()),
    ("GET", "/hub/setup"): ((), ()),
    ("GET", "/hub/operations/<operation_id>"): ((), ("operation_not_found",)),
    ("GET", "/hub/dialogs/<pick_id>"): ((), ("pick_not_found",)),
    ("GET", "/hub/github/status"): ((), ()),
    ("GET", "/hub/github/repos"): ((), ("gh_not_pinned", "gh_changed", "gh_not_logged_in",
                                        "gh_unreachable", "gh_failed")),
    ("GET", "/hub/github/repos/<owner>"): ((), ("gh_not_pinned", "gh_changed", "gh_not_logged_in",
                                               "gh_unreachable", "gh_failed")),
    ("POST", "/hub/dialogs/folder"): (({"purpose"},), ("dialog_busy", "dialog_unavailable")),
    ("POST", "/hub/dialogs/<pick_id>/cancel"): (((),), ("pick_not_found",)),
    ("POST", "/hub/projects"): (
        ({"source", "pick_id", "name", "legacy_writers_stopped"},
         {"source", "repo", "folder", "name"}, {"source", "folder", "name"}),
        ("name_invalid", "folder_invalid", "windows_name_unsafe", "repo_invalid", "pick_invalid",
         "legacy_writers_unconfirmed", "folder_exists", "projects_home_invalid",
         "git_not_pinned", "git_changed", "gh_not_pinned", "gh_changed",
         "review_harness_missing", "operation_busy", "registry_busy", "registry_invalid")),
    ("POST", "/hub/setup/projects-home"): (
        ({"pick_id"}, {"default"}),
        ("pick_invalid", "projects_home_invalid", "windows_path_too_long")),
    ("POST", "/hub/tools/<tool>/pin"): (
        ({"candidate_id"},), ("candidate_not_found", "git_changed", "gh_changed", "git_too_old",
                              "tool_version_unreadable")),
    ("POST", "/hub/projects/<project_id>/activate"): (
        ((),), ("project_not_found", "already_active", "active_not_closed", "project_unavailable",
                "recovery_required", "project_busy", "hub_in_kill_on_close_job")),
    ("POST", "/hub/projects/<project_id>/view"): (
        ((),), ("project_not_found", "already_active", "project_running", "project_unavailable",
                "recovery_required", "project_busy", "hub_in_kill_on_close_job")),
    ("POST", "/hub/projects/<project_id>/stop"): (
        ((),), ("project_not_found", "project_not_running", "project_busy")),
    ("POST", "/hub/projects/<project_id>/recover"): (
        ((),), ("project_not_found", "project_running", "recover_not_needed", "project_busy")),
    ("POST", "/hub/projects/<project_id>/providers"): (
        ((),), ("project_not_found", "profile_absent", "profile_invalid", "project_busy")),
    ("POST", "/hub/projects/<project_id>/forget"): (
        ((),), ("project_not_found", "project_running")),
    ("POST", "/hub/logins/<login_key>/recover"): (
        ((),), ("login_not_found", "recover_not_needed")),
    ("POST", "/hub/operations/<operation_id>/cancel"): (
        ((),), ("operation_not_found", "operation_not_cancellable")),
    ("POST", "/hub/queue/order"): (({"order"},), ("project_queue_changed",)),
}
#: `HUB_WRITE_TARGETS` of 4.6.3: target -> (method, path); the fourteen writes of the page.
WRITE_TARGETS = {
    "pickFolder": "/hub/dialogs/folder", "pickCancel": "/hub/dialogs/<pick_id>/cancel",
    "projectAdd": "/hub/projects", "projectsHome": "/hub/setup/projects-home",
    "toolPin": "/hub/tools/<tool>/pin", "projectActivate": "/hub/projects/<project_id>/activate",
    "projectView": "/hub/projects/<project_id>/view",
    "projectStop": "/hub/projects/<project_id>/stop",
    "projectRecover": "/hub/projects/<project_id>/recover",
    "projectProviders": "/hub/projects/<project_id>/providers",
    "projectForget": "/hub/projects/<project_id>/forget",
    "loginRecover": "/hub/logins/<login_key>/recover",
    "operationCancel": "/hub/operations/<operation_id>/cancel",
    "queueOrder": "/hub/queue/order"}


def test_the_route_table_is_frozen_row_by_row_in_the_order_of_the_spec():
    assert [(row.method, row.path) for row in routes.HUB_ROUTES] == list(ROWS)
    assert isinstance(routes.HUB_ROUTES, tuple) and len(routes.HUB_ROUTES) == 26
    for row in routes.HUB_ROUTES:
        bodies, named = ROWS[(row.method, row.path)]
        assert {frozenset(keys) for keys in row.bodies} == {frozenset(keys) for keys in bodies}, (
            row.method, row.path)
        assert row.refusals == named, (row.method, row.path)


def test_the_writes_of_the_page_are_exactly_the_post_rows_of_the_table():
    posts = {row.path for row in routes.HUB_ROUTES if row.method == "POST"}
    assert posts == set(WRITE_TARGETS.values()) and len(posts) == 14
    assert all(row.bodies for row in routes.HUB_ROUTES if row.method == "POST")
    assert not any(row.bodies for row in routes.HUB_ROUTES if row.method == "GET")


def test_every_refusal_a_row_names_is_a_code_of_the_route_list_and_no_transport_code():
    for row in routes.HUB_ROUTES:
        for code in row.refusals:
            assert code in refusals.HUB_ERROR_STATUS, (row.path, code)
            if code in TRANSPORT:                     # the one row the table answers "404" for
                assert (row.path, code) == ("/hub/<name>", "route_not_found"), (row.path, code)
        assert len(set(row.refusals)) == len(row.refusals), row.path


@pytest.mark.parametrize("name,good,bad", [
    ("project_id", [PROJECT, "0" * 32], ["", "A" * 32, PROJECT[:-1], PROJECT + "0", "g" * 32,
                                          "../" + PROJECT[3:], PROJECT.upper()]),
    ("operation_id", [OPERATION], ["operation-" + "0" * 31, "operation-" + "G" * 32, PROJECT,
                                   "operation-" + "0" * 33, "Operation-" + "0" * 32]),
    ("pick_id", [PICK], ["pick-" + "0" * 31, "pick-" + "0" * 33, "pick-" + "Z" * 32, PROJECT]),
    ("login_key", [LOGIN], ["ab" * 31, "ab" * 33, "AB" * 32, "xy" * 32]),
    ("tool", ["gh", "git"], ["", "GH", "gitt", "hg", "gh/git"]),
    ("owner", ["octocat", "a", "a-b-9", "A" * 39], ["", "A" * 40, "a_b", "a.b", "a b", "-" * 40]),
])
def test_each_path_parameter_takes_its_grammar_and_nothing_else(name, good, bad):
    assert set(routes.PARAM_GRAMMAR) == {"project_id", "operation_id", "pick_id", "login_key",
                                         "tool", "owner"}
    template = next(row for row in routes.HUB_ROUTES if f"<{name}>" in row.path)
    for value in good:
        found = routes.match(template.method, _fill(template.path, name, value))
        assert found.params[name] == value
    for value in bad:
        with pytest.raises(refusals.HubRefusal) as raised:
            routes.match(template.method, _fill(template.path, name, value))
        assert raised.value.code == "route_not_found", (name, value)


def _fill(path: str, name: str, value: str) -> str:
    others = {"project_id": PROJECT, "operation_id": OPERATION, "pick_id": PICK,
              "login_key": LOGIN, "tool": "gh", "owner": "octocat"}
    others[name] = value
    return re.sub(r"<([a-z_]+)>", lambda hit: others[hit.group(1)], path)


def _code(method: str, target: str) -> str:
    with pytest.raises(refusals.HubRefusal) as raised:
        routes.match(method, target)
    return raised.value.code


def test_an_unknown_path_is_route_not_found_and_a_known_path_under_another_method_is_not_allowed():
    for method, target in (("GET", "/nope"), ("GET", "/hub"), ("GET", "/hub/"), ("GET", "//"),
                           ("GET", "/hub/projects/"), ("GET", "/Hub/projects"),
                           ("POST", "/hub/zzz"), ("GET", "/hub/projects/" + PROJECT),
                           ("GET", "/command/runs"), ("GET", "/hub/%70rojects"),
                           ("GET", "/hub/projects/../projects"), ("GET", "")):
        assert _code(method, target) == "route_not_found", (method, target)
    for method, target in (("POST", "/hub/projects/" + PROJECT + "/../../hub/projects"),):
        assert _code(method, target) == "route_not_found"
    for method, target in (("POST", "/hub/session"), ("GET", "/hub/queue/order"),
                           ("PUT", "/hub/projects"), ("DELETE", "/hub/projects"),
                           ("OPTIONS", "/hub/events"), ("HEAD", "/hub/projects"),
                           ("GET", f"/hub/projects/{PROJECT}/activate"),
                           ("POST", "/"), ("POST", "/hub/hub.js")):
        assert _code(method, target) == "method_not_allowed", (method, target)


def test_a_query_or_a_fragment_is_never_part_of_a_route():
    for target in ("/hub/projects?x=1", "/?x", "/hub/events?since=3", "/hub/hub.js?v=2",
                   "/hub/projects#x", f"/hub/projects/{PROJECT}/activate?force=1"):
        method = "POST" if target.endswith("?force=1") else "GET"
        assert _code(method, target) == "route_not_found", target


def test_a_file_of_the_hub_is_a_route_only_when_the_registry_names_it():
    for path in HUB_ASSETS:
        found = routes.match("GET", path)
        assert found.route.path == "/hub/<name>" and found.params == {"name": path[len("/hub/"):]}
    assert _code("GET", "/hub/hub.html") == "route_not_found", "hub.html is `GET /`, not a row"
    assert _code("GET", "/hub/studio.js") == "route_not_found"
    assert _code("GET", "/hub/../panel/studio.js") == "route_not_found"
    assert routes.match("GET", "/hub/session").route.path == "/hub/session", \
        "a named route wins over the file row"
    assert routes.match("GET", "/").route.path == "/"


def test_the_three_bodies_of_adding_a_project_are_told_apart_by_their_exact_keys():
    add = routes.match("POST", "/hub/projects").route
    folder = {"source": "folder", "pick_id": PICK, "name": "web-app",
              "legacy_writers_stopped": False}
    github = {"source": "github", "repo": "owner/name", "folder": "name", "name": "Мой сайт"}
    scratch = {"source": "scratch", "folder": "idea-bot", "name": "Бот идей"}
    for body in (folder, github, scratch):
        assert routes.check_body(add, body) == frozenset(body)
    for body in ({**folder, "extra": 1}, {k: v for k, v in folder.items() if k != "name"},
                 {**scratch, "pick_id": PICK}, {}, {"source": "scratch"},
                 {**github, "pick_id": PICK}):
        with pytest.raises(refusals.HubRefusal) as raised:
            routes.check_body(add, body)
        assert raised.value.code == "contract_invalid", body


def test_a_key_that_names_a_place_on_disk_is_contract_invalid_at_any_depth_before_the_route_is():
    stop = routes.match("POST", f"/hub/projects/{PROJECT}/stop").route
    order = routes.match("POST", "/hub/queue/order").route
    for body in ({"root": "C:\\x"}, {"path": "x"}, {"dir": "x"}, {"order": [{"path": "x"}]},
                 {"a": {"b": [{"c": {"dir": 1}}]}}, {"order": [], "root": ""}):
        for row in (stop, order):
            with pytest.raises(refusals.HubRefusal) as raised:
                routes.check_body(row, body)
            assert raised.value.code == "contract_invalid", (row.path, body)
    assert routes.check_body(stop, {}) == EMPTY
    assert routes.check_body(order, {"order": [PROJECT]}) == frozenset({"order"})


def test_a_get_takes_no_body_and_a_post_with_a_body_its_row_does_not_name_is_refused():
    events = routes.match("GET", "/hub/events").route
    assert routes.check_body(events, {}) == EMPTY
    with pytest.raises(refusals.HubRefusal) as raised:
        routes.check_body(events, {"x": 1})
    assert raised.value.code == "contract_invalid"


# -- the session -------------------------------------------------------------------------------


def _headers(port: int, token: str, *, host: str | None = None, origin: str | None = None,
             content_type: str = "application/json", length: int = 2) -> list[tuple[str, str]]:
    return [("Host", host or f"127.0.0.1:{port}"), ("Origin", origin or f"http://127.0.0.1:{port}"),
            ("X-Conduct-CSRF", token), ("Content-Type", content_type),
            ("Content-Length", str(length))]


def test_the_session_has_one_host_and_the_commands_second_spelling_is_not_it():
    one = session.HubSession.mint(7700)
    assert one.allowed_hosts == frozenset({"127.0.0.1:7700"})
    assert one.canonical_host == "127.0.0.1:7700" and one.origin == "http://127.0.0.1:7700"
    with pytest.raises(HttpRefusal) as raised:
        one.check_host([("Host", "localhost:7700")])
    assert raised.value.code == "same_origin_denied" and raised.value.status == 403
    assert one.check_host([("Host", "127.0.0.1:7700")]) == "127.0.0.1:7700"
    for bad in ([], [("Host", "127.0.0.1:7701")], [("Host", "127.0.0.1:7700"),
                                                  ("Host", "127.0.0.1:7700")]):
        with pytest.raises(HttpRefusal):
            one.check_host(bad)


def test_the_session_answer_is_the_token_and_the_origin_and_no_other_key():
    made = session.HubSession(7700, "t" * 43)
    assert made.session_response("127.0.0.1:7700") == {"csrf_token": "t" * 43,
                                                       "origin": "http://127.0.0.1:7700"}
    with pytest.raises(HttpRefusal):
        made.session_response("localhost:7700")


def test_a_minted_token_has_at_least_32_bytes_of_entropy_and_is_never_printed():
    asked: list[int] = []
    made = session.HubSession.mint(7700, token_factory=lambda n: asked.append(n) or "s" * 43)
    assert asked == [32]
    assert "s" * 43 not in repr(made) and "s" * 43 not in str(made)
    real = session.HubSession.mint(7700)
    assert len(real.session_response("127.0.0.1:7700")["csrf_token"]) >= 43
    for port in (0, -1, 65536, True, "7700"):
        with pytest.raises(ValueError):
            session.HubSession(port, "t")
    with pytest.raises(ValueError):
        session.HubSession(7700, "")


def test_a_write_needs_the_hubs_own_origin_token_content_type_and_a_bounded_json_object():
    made = session.HubSession(7700, "tok")
    body = b"{}"
    assert made.validate_mutation(_headers(7700, "tok"), body) == {}
    assert made.body_length(_headers(7700, "tok")) == 2
    wrong = {
        "origin": _headers(7700, "tok", origin="http://localhost:7700"),
        "host": _headers(7700, "tok", host="localhost:7700", origin="http://localhost:7700"),
        "csrf": _headers(7700, "not-it"),
        "content_type": _headers(7700, "tok", content_type="text/plain"),
        "body": _headers(7700, "tok", length=64 * 1024 + 1)}
    for phase, headers in wrong.items():
        with pytest.raises(HttpRefusal) as raised:
            made.validate_mutation(headers, body)
        assert raised.value.phase == phase, phase
    with pytest.raises(HttpRefusal):
        made.validate_mutation(_headers(7700, "tok", length=3), body)
    with pytest.raises(HttpRefusal):
        made.validate_mutation(_headers(7700, "tok", length=2), b"[]")
