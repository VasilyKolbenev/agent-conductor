"""The refusal `server_stopping` and the door that says it (spec 4.1.6 step 1, 11.1).

While a server drains toward a stop, every command POST is answered `409
server_stopping` and nothing is executed; reads and the event stream go on. The
door is tested here on a real server whose `draining` flag the test sets by hand,
so it stands on its own: the drain that sets the flag is judged by
`tests/test_server_drain.py`. The second half is the rule of 11.1: a new code goes
into EVERY place of the vocabulary in one commit, and this file is the "test of
the code" that names each place that can be read from Python or from a file.
"""
from __future__ import annotations

import http.client
import json
import re
from pathlib import Path
from threading import Thread

import pytest

from conductor import server
from conductor.command.adapters import AdapterRegistry
from conductor.command.api_contracts import ERROR_STATUS, _FIXED_MESSAGES
from tests._drain_harness import post_paths
from tests.alpha1_live_extensions import REFUSALS
from tests.test_cockpit_command_api_freeze import EXPECTED_ERRORS
from tests.test_store import good_lane, write_project

REPO = Path(__file__).resolve().parents[1]
PANEL = REPO / "src" / "conductor" / "panel"
CODE = "server_stopping"


@pytest.fixture
def serving(tmp_path):
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    subject = server.build(root, 0, registry=AdapterRegistry())
    loop = Thread(target=subject.serve_forever, daemon=True)
    loop.start()
    yield subject
    subject.shutdown()
    subject.server_close()
    loop.join(10)


def _request(subject, method: str, path: str, body: dict | None = None):
    port = subject.server_address[1]
    headers, encoded = {}, None
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        if method == "POST":
            connection.request("GET", "/command/session")
            token = json.loads(connection.getresponse().read())["csrf_token"]
            encoded = json.dumps({} if body is None else body).encode("utf-8")
            headers = {"Origin": f"http://127.0.0.1:{port}", "X-Conduct-CSRF": token,
                       "Content-Type": "application/json"}
        connection.request(method, path, body=encoded, headers=headers)
        response = connection.getresponse()
        return response.status, json.loads(response.read()), response.will_close
    finally:
        connection.close()


def test_a_new_server_is_not_draining(serving):
    assert serving.draining is False


def test_every_command_post_is_refused_server_stopping_while_the_server_drains(serving):
    serving.draining = True
    paths = post_paths()
    assert paths, "control: the frozen table has POST rows"
    for path in paths:
        status, payload, _ = _request(serving, "POST", path)
        assert (status, payload["error"]["code"]) == (409, CODE), path
        assert payload["error"]["message"] == _FIXED_MESSAGES[CODE]
        assert payload["error"]["detail"] == {}


def test_reads_and_the_event_stream_route_still_answer_while_the_server_drains(serving):
    serving.draining = True
    for path in ("/command/session", "/state.json", "/harnesses.json"):
        assert _request(serving, "GET", path)[0] == 200, path
    # The stream has no end, so only its head is read: getresponse() stops after the headers.
    connection = http.client.HTTPConnection("127.0.0.1", serving.server_address[1], timeout=10)
    try:
        connection.request("GET", "/events")
        stream = connection.getresponse()
        assert stream.status == 200
        assert stream.getheader("Content-Type") == "text/event-stream"
    finally:
        connection.close()


def test_a_server_that_is_not_draining_never_says_server_stopping(serving):
    for path in post_paths():
        status, payload, _ = _request(serving, "POST", path)
        assert payload.get("error", {}).get("code") != CODE, (path, status)


def test_a_post_to_no_command_route_is_still_a_404_while_draining(serving):
    serving.draining = True
    connection = http.client.HTTPConnection("127.0.0.1", serving.server_address[1], timeout=10)
    try:
        connection.request("POST", "/not-a-route", body=b"{}",
                           headers={"Content-Type": "application/json"})
        assert connection.getresponse().status == 404
    finally:
        connection.close()


# -- 11.1: the code stands in every place of the vocabulary -----------------------


def test_server_stopping_stands_in_every_place_of_the_command_vocabulary_that_python_can_read():
    assert ERROR_STATUS[CODE] == 409                    # place 1
    assert _FIXED_MESSAGES[CODE].strip()                # place 2
    assert EXPECTED_ERRORS[CODE] == (409, "lifecycle")  # place 5
    assert REFUSALS[CODE] == 409                        # place 6


def test_server_stopping_stands_in_the_canon_the_labels_and_both_languages_of_the_notice():
    canon = (REPO / "docs" / "specs" / "2026-08-13-cockpit-command-api.md").read_text(
        encoding="utf-8")
    assert re.search(rf'"code": "{CODE}",\s+"status": 409,\s+"source": "lifecycle"', canon)  # 4
    labels = (PANEL / "command-projection.js").read_text(encoding="utf-8")
    assert re.search(rf"^  {CODE}: ", labels, re.MULTILINE)                              # 7
    notice = (PANEL / "studio-notice-copy.js").read_text(encoding="utf-8")
    found = re.search(rf'"error\.{CODE}": \["([^"]+)", "([^"]+)"\]', notice)              # 8
    assert found and all(found.groups()) and found.group(1) != found.group(2)
