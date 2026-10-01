"""The hub page contract fixture: one response per GET route, one frame per SSE kind.

Spec 4.6.3 names the routes and 4.6.4 the forms. This file holds the page's builder
(lane D2, transfer T1) to the same forms without a server: every fixture parses,
names the one GET route it answers, has exactly the keys of that route's form, and
its identifiers follow the grammar of 4.6.3. The two GET rows that serve files
(`/` and `/hub/<name>`) have no JSON form and no fixture.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "hub"

FORMS = {
    "GET /hub/session": {"csrf_token", "origin"},
    "GET /hub/projects": {"computed_at", "active_project_id", "project_queue",
                          "projects_home", "projects", "unlisted_closing"},
    "GET /hub/limits": {"computed_at", "project_id", "source", "taken_at", "as_of",
                        "max_age_seconds", "accounts"},
    "GET /hub/setup": {"profile", "projects_home", "tools", "logins", "hub_job",
                       "clone_recovery"},
    "GET /hub/operations/<operation_id>": {
        "operation_id", "kind", "source", "state", "step", "project_id", "code", "result"},
    "GET /hub/dialogs/<pick_id>": {"pick_id", "purpose", "state", "folder", "project", "code"},
    "GET /hub/github/status": {"state", "login", "login_command"},
    "GET /hub/github/repos": {"owner", "repos"},
    "GET /hub/github/repos/<owner>": {"owner", "repos"},
}
EVENTS = "GET /hub/events"
#: A fixture may name, under this key, the dotted paths of values that are only
#: illustrations of what the server will produce; they hold no contract.
ILLUSTRATIVE = "illustrative"
OPERATION = "GET /hub/operations/<operation_id>"
#: The lines of the `.git/info/exclude` block, in the one spelling of spec 9.2 (and the
#: example of 8.1): five product names, then a folder and a marker file per harness.
BLOCK_LINES = ["/conductor/", "/conductor.v3/", "/.conduct*", "/work/", "/instructions/"] + [
    line for harness in ("claude", "codex", "grok", "kimi", "dsh")
    for line in (f"/.{harness}-home/", f"/.{harness}-marker")]
PROJECT_ROW = {
    "project_id", "name", "folder", "source", "repo", "state", "working", "mode",
    "queue_position", "stopped_at", "resume_run_id", "auto_continue", "state_code",
    "drain_deadline", "instance", "desk_url", "data", "snapshot_at", "tasks", "task_queue"}
TASK_ROW = {"task", "run", "automation", "attention"}
ATTENTION = {"reasons", "gates", "runtime", "journal", "observed_at", "unreadable"}
#: A closing entry of a project off the list (tech lead, 30.09, rule b): the one key that 4.6.4 does
#: not have, added to `GET /hub/projects` so the page can offer to put the project back.
UNLISTED = {"project_id", "since", "action"}
ACCOUNT_CARD = {"key", "verified", "row"}
REPO_ROW = {"full_name", "description", "visibility", "updated_at", "archived", "fork"}
FRAMES = {"projects": {"kind"}, "project": {"kind", "project_id"}, "limits": {"kind"},
          "setup": {"kind"}, "operation": {"kind", "operation_id"},
          "pick": {"kind", "pick_id"}}
GRAMMAR = {"project_id": r"[0-9a-f]{32}", "instance": r"[0-9a-f]{32}",
           "operation_id": r"operation-[0-9a-f]{32}", "pick_id": r"pick-[0-9a-f]{32}",
           "login_key": r"[0-9a-f]{64}", "candidate_id": r"cand-[0-9a-f]{32}"}


def _documents() -> dict[str, dict]:
    found: dict[str, dict] = {}
    for path in sorted(FIXTURES.glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        route = document["route"]
        assert route not in found, f"{path.name} repeats the route {route!r}"
        found[route] = document
    return found


def _walk(value, key=None):
    """Yield (key, value) for every scalar under `value`, keys of the nearest object."""
    if isinstance(value, dict):
        for name, inner in value.items():
            yield from _walk(inner, name)
    elif isinstance(value, list):
        for inner in value:
            yield from _walk(inner, key)
    else:
        yield key, value


def test_every_hub_fixture_parses_and_names_one_get_route_of_the_spec():
    documents = _documents()
    assert set(documents) == {*FORMS, EVENTS}
    for route, document in documents.items():
        body = "frames" if route == EVENTS else "response"
        assert set(document) - {ILLUSTRATIVE} == {"route", "status", body}, route
        assert document["status"] == 200, route


def test_each_response_has_exactly_the_keys_of_its_spec_form():
    documents = _documents()
    for route, keys in FORMS.items():
        assert set(documents[route]["response"]) == keys, route
    projects = documents["GET /hub/projects"]["response"]["projects"]
    assert all(set(row) == PROJECT_ROW for row in projects)
    tasks = [task for row in projects for task in row["tasks"]]
    assert tasks and all(set(task) == TASK_ROW for task in tasks)
    assert any(task["attention"] and set(task["attention"]) == ATTENTION for task in tasks)
    owed = documents["GET /hub/projects"]["response"]["unlisted_closing"]
    assert owed and all(set(row) == UNLISTED and row["action"] == "relist" for row in owed)
    cards = documents["GET /hub/limits"]["response"]["accounts"]
    assert cards and all(set(card) == ACCOUNT_CARD for card in cards)
    for route in ("GET /hub/github/repos", "GET /hub/github/repos/<owner>"):
        rows = documents[route]["response"]["repos"]
        assert rows and all(set(row) == REPO_ROW for row in rows)


def test_the_events_fixture_holds_one_frame_of_each_kind_and_only_identifiers():
    frames = _documents()[EVENTS]["frames"]
    assert [frame["kind"] for frame in frames] == list(FRAMES)
    assert all(set(frame) == FRAMES[frame["kind"]] for frame in frames)


def test_identifiers_in_the_hub_fixtures_follow_the_grammar_of_the_spec():
    checked = 0
    for document in _documents().values():
        for key, value in _walk(document):
            if key in GRAMMAR and value is not None:
                assert re.fullmatch(GRAMMAR[key], value), (key, value)
                checked += 1
    assert checked >= len(GRAMMAR)


def test_a_fixture_that_names_a_route_outside_the_spec_is_caught(tmp_path, monkeypatch):
    broken = tmp_path / "hub"
    shutil.copytree(FIXTURES, broken)
    path = broken / "hub_session.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["route"] = "GET /hub/nope"
    path.write_text(json.dumps(document), encoding="utf-8")
    monkeypatch.setitem(globals(), "FIXTURES", broken)
    with pytest.raises(AssertionError, match="hub/nope"):
        test_every_hub_fixture_parses_and_names_one_get_route_of_the_spec()


def _resolve(document: dict, dotted: str):
    value = document
    for part in dotted.split("."):
        value = value[part]
    return value


def test_a_login_box_used_by_the_running_active_project_reads_in_use_never_unclosed():
    """Spec 4.1.8 and 4.6.4: `unclosed` needs an `active.json` and NO running active child."""
    documents = _documents()
    rows = documents["GET /hub/projects"]["response"]["projects"]
    running = {row["project_id"] for row in rows
               if row["state"] == "running" and row["working"] == "active"}
    boxes = documents["GET /hub/setup"]["response"]["logins"]
    assert running and boxes, "control: the fixture has a running active project and a box"
    for box in boxes:
        assert box["state"] in {"free", "in_use", "unclosed"}, box
        assert box["state"] != "unclosed", box
        if set(box["used_by"]) & running:
            assert box["state"] == "in_use", box


def test_the_exclude_names_are_the_lines_of_the_block_of_section_9_2_and_marked_illustrative():
    document = _documents()[OPERATION]
    assert _resolve(document, "response.result.exclude_names") == BLOCK_LINES
    assert "response.result.exclude_names" in document[ILLUSTRATIVE]


def test_every_illustrative_path_names_a_value_that_exists():
    named = 0
    for route, document in _documents().items():
        for dotted in document.get(ILLUSTRATIVE, []):
            _resolve(document, dotted)
            named += 1
    assert named >= 1
