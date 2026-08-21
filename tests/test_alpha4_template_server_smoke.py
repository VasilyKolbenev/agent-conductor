"""The two template routes over a real loopback socket, in a real server.

Every other test of this vertical calls `CommandApi` directly, which proves the
route authority and nothing about whether a browser can reach it. A route that
exists in the allowlist and is unreachable over HTTP is a route the table
advertises and the server answers `route_not_found` for -- so this drives the
whole thing the way the Cockpit would: fetch the session token, publish a
revision, materialize a run's plan, then read it back and watch the signal
arrive on the event stream.

The provider is real too. `server.build` resolves an operator's provider config
through the factory, so the availability this route consults is the one this
build resolved from a pinned executable on disk, not a descriptor a test made
up.
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager

import pytest

from conductor import server
from conductor.command.adapters.provider import ProviderConfig
from conductor.command.contracts import RunEnvelope
from conductor.command.graph_template import load_template
from conductor.command.run_store import snapshot_digest

from tests.test_store import good_lane, write_project

RUN_ID = "run-loopback-001"
NOW = "2026-08-21T09:00:00Z"
#: One instance, bound to the provider the config below pins. The adapter name
#: is the CONFIGURATION's word: no test here decides anything by it.
CONFIG = {
    "cycle": {"id": "default-orbit", "phases": ["goal", "detect", "design"]},
    "instances": [{"id": "solo-node", "adapter": "claude-code"}],
}


def serving(root, providers):
    srv = server.build(root, port=0, providers=providers, clock=lambda: NOW)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def pinned(tmp_path):
    """One provider config whose executable really is on this disk.

    The factory stats an operator's ABSOLUTE pin and nothing else -- it never
    searches a PATH -- so a file that exists is the whole difference between a
    provider this build can reach and one it cannot.
    """
    executable = tmp_path / "claude-executable"
    executable.write_text("", encoding="utf-8", newline="\n")
    return [ProviderConfig(
        provider_id="claude-code", executable=str(executable.resolve()),
        protocol="fake-claude-jsonl-v1")]


def request(base, method, path, *, token=None, body=None, host=None):
    host = host or base.removeprefix("http://")
    headers = {"Host": host}
    data = None
    if body is not None:
        data = json.dumps(body, separators=(",", ":")).encode("utf-8")
        headers.update({
            "Origin": f"http://{host}", "X-Conduct-CSRF": token,
            "Content-Type": "application/json",
            "Content-Length": str(len(data)),
        })
    call = urllib.request.Request(base + path, data=data, headers=headers,
                                  method=method)
    with urllib.request.urlopen(call, timeout=10) as answer:
        return answer.status, json.loads(answer.read() or b"null")


@contextmanager
def a_run_on_a_socket(tmp_path):
    """A served project with one run, and the token a browser would hold.

    Everything a Cockpit needs before it can ask for anything: a bound socket,
    a resolved provider whose executable really is on this disk, one run whose
    frozen configuration names an instance, and the CSRF token fetched from the
    route that hands it out.
    """
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    srv, base = serving(root, pinned(tmp_path))
    try:
        srv.command_store.create_run(
            RunEnvelope(run_id=RUN_ID, cycle_id="default-orbit", created_at=NOW,
                        config_digest=snapshot_digest(CONFIG), mode="confirm"),
            CONFIG)
        status, session = request(base, "GET", "/command/session")
        assert status == 200
        yield srv, base, session["csrf_token"]
    finally:
        srv.shutdown()
        srv.server_close()


def materialize(base, token, template, graph_id):
    return request(base, "POST", f"/command/runs/{RUN_ID}/graph/from-template",
                   token=token, body={
                       "graph_id": graph_id,
                       "template_id": template.template_id,
                       "revision": template.revision,
                       "assignments": {role: "solo-node"
                                       for role in template.roles}})


def test_a_browser_can_publish_a_revision_over_a_socket(tmp_path):
    """201 the first time and 200 for the same bytes, on the wire."""
    with a_run_on_a_socket(tmp_path) as (_srv, base, token):
        document = load_template("dalio-v1").as_dict()
        assert request(base, "POST", "/command/templates",
                       token=token, body=document) == (201, document)
        assert request(base, "POST", "/command/templates",
                       token=token, body=document)[0] == 200


def test_a_browser_can_give_a_run_its_plan_and_read_it_back(tmp_path):
    """The write, the authoritative read, and the retry that writes nothing.

    The provider is real: `server.build` resolved it from a pinned executable
    through the factory, so the availability this route consulted is the one
    this build established rather than a descriptor a test made up.
    """
    with a_run_on_a_socket(tmp_path) as (_srv, base, token):
        template = load_template("dalio-v1")
        assert request(base, "POST", "/command/templates",
                       token=token, body=template.as_dict())[0] == 201

        status, plan = materialize(base, token, template, "graph-loopback-001")
        assert status == 201, plan
        assert plan["run_id"] == RUN_ID and plan["created_at"] == NOW

        status, recovered = request(base, "GET", f"/command/runs/{RUN_ID}")
        assert status == 200
        stored = [row["record"] for row in recovered["records"]
                  if row["record_type"] == "graph_definition"]
        assert stored == [plan]
        assert recovered["graph"]["definition"] == plan

        # An exact retry is answered from the journal, not written again.
        assert materialize(base, token, template, "graph-loopback-001") == \
            (200, plan)


def test_the_materialization_signal_reaches_the_event_stream(tmp_path):
    """One append, one identifier-only frame, on the wire a browser listens to."""
    with a_run_on_a_socket(tmp_path) as (_srv, base, token):
        template = load_template("dalio-v1")
        assert request(base, "POST", "/command/templates",
                       token=token, body=template.as_dict())[0] == 201
        stream = urllib.request.urlopen(base + "/events", timeout=10)
        try:
            assert stream.readline().startswith(b"data:")   # the greeting
            assert materialize(
                base, token, template, "graph-loopback-002")[0] == 201
            frame = _next_frame(stream)
        finally:
            stream.close()
        assert frame["run_id"] == RUN_ID
        # Identifier only: a frame says WHICH run moved, never what it now says.
        assert "record" not in frame and "nodes" not in frame


def _next_frame(stream):
    """The next non-blank SSE payload, or a failure that says what was missing."""
    while True:
        line = stream.readline()
        assert line, "the stream closed before the frame arrived"
        if line.strip().startswith(b"data:"):
            payload = json.loads(line.split(b":", 1)[1])
            if payload.get("kind") == "run":
                return payload


def test_the_template_route_belongs_to_no_run_and_answers_only_to_post(tmp_path):
    """The one command route with no run id in it, and it is a POST alone."""
    with a_run_on_a_socket(tmp_path) as (_srv, base, _token):
        with pytest.raises(urllib.error.HTTPError) as refused:
            request(base, "GET", "/command/templates")
        assert refused.value.code == 405
