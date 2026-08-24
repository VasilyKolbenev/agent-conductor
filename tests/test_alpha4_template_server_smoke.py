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
build resolved from a pinned executable on disk, not a descriptor a test made up.

**Two templates are published here, and which one each test uses is a product
fact rather than a testing convenience.** The frozen `dalio-v1` binds `review`,
and since Codex CLI became a real transport no catalogued provider serves it --
the roster is five real transports and every one carries `dispatch` alone,
because an honest `review` needs an artifact's CONTENT and this build has no
resolver that turns a reference into one. So `dalio-v1` can be materialized
against nothing, and that is asserted as its own claim at the end of this file:
the route answers `capability_unsupported`, which is the Day 3 blocker showing up
exactly where it should.

The route mechanics still have to be proved, so the tests that need a plan
publish their own gate-then-dispatch template through the same route a browser
would. It is the smallest document this product will build -- an effect-capable
step must stand BEHIND a gate, never beside one -- and every provider in the
roster can serve it.
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager

import pytest

from conductor import server
from conductor.command.adapters.codex_cli import CODEX_PROTOCOL
from conductor.command.adapters.provider import ProviderConfig
from conductor.command.contracts import RunEnvelope
from conductor.command.graph_template import GraphTemplate, load_template
from conductor.command.run_store import snapshot_digest

from tests.test_store import good_lane, write_project

RUN_ID = "run-loopback-001"
NOW = "2026-08-21T09:00:00Z"
#: One instance, bound to the provider the config below pins. The adapter name
#: is the CONFIGURATION's word: no test here decides anything by it.
CONFIG = {
    "cycle": {"id": "default-orbit", "phases": ["goal", "detect", "design"]},
    "instances": [{"id": "solo-node", "adapter": "codex"}],
}


def serving(root, *, providers=(), registry=None):
    srv = server.build(root, port=0, providers=providers, registry=registry,
                       clock=lambda: NOW)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def pinned(tmp_path):
    """One provider config whose executable really is on this disk.

    The factory stats an operator's ABSOLUTE pin and nothing else -- it never
    searches a PATH -- so a file that exists is the whole difference between a
    provider this build can reach and one it cannot.
    """
    executable = tmp_path / "codex-executable"
    executable.write_text("", encoding="utf-8", newline="\n")
    return [ProviderConfig(
        provider_id="codex", executable=str(executable.resolve()),
        protocol=CODEX_PROTOCOL)]


#: The smallest template this product will build, and the one every provider in
#: the roster can serve. A dispatch step is effect-capable, so it must stand
#: BEHIND a gate rather than beside one -- a single task node with no gate ahead
#: of it is refused at construction, which is where this document's shape came
#: from. It is published through the same route a browser would use, so the plan
#: tests below still drive the factory road end to end.
DISPATCH_ONLY = {
    "schema_version": 1,
    "template_id": "template-one-dispatch",
    "revision": 1,
    "title": "One dispatch",
    "nodes": [
        {"kind": "gate", "node_id": "confirm-gate", "title": "Human Gate",
         "gate_id": "gate-confirm-do", "resources": []},
        {"kind": "task", "node_id": "do", "title": "Do", "stage": "do",
         "role_id": "role-implementer", "capability": "dispatch",
         "arguments": {
             "work_item_id": "work-001",
             "instruction_ref": "instruction-plan",
             "profile": "implement",
             "artifact_refs": ["artifact-plan"],
             "output_limit_profile": "normal"},
         "resources": [{"kind": "sandbox", "name": "project-root"}]},
    ],
    "edges": [{"from_node": "confirm-gate", "to_node": "do"}],
}


def a_servable_template(base, token):
    """Publish the dispatch-only template through the route, and return it."""
    template = GraphTemplate.from_dict(DISPATCH_ONLY)
    assert request(base, "POST", "/command/templates",
                   token=token, body=template.as_dict())[0] == 201
    return template


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
    srv, base = serving(root, providers=pinned(tmp_path))
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
    this build established rather than a descriptor a test made up. The template
    is the dispatch-only one this file publishes, because the frozen one binds a
    control no catalogued provider serves -- see the module docstring, and the
    claim that holds that refusal at the end of this file.
    """
    with a_run_on_a_socket(tmp_path) as (_srv, base, token):
        template = a_servable_template(base, token)

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
        template = a_servable_template(base, token)
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


def test_the_frozen_template_cannot_be_materialized_by_any_catalogued_provider(
        tmp_path):
    """The Day 3 blocker, over a real socket, said by the route that meets it.

    `dalio-v1` is FROZEN and binds `dispatch` AND `review`. Every provider this
    build catalogues is now a real transport carrying `dispatch` alone, so a
    Dalio plan can be materialized against none of them: the route answers 409
    `capability_unsupported` before a single durable byte is written.

    Neither side of that is a defect to be smoothed. The template is a product
    decision already made, and the missing control is a fact about durable
    artifact handoff not existing yet. What would be a defect is either one
    quietly changing to make the other fit -- so this is driven end to end, on
    the factory road a real operator takes, and the day a real `review` lands
    this is the test that says what to reopen.
    """
    with a_run_on_a_socket(tmp_path) as (srv, base, token):
        template = load_template("dalio-v1")
        assert request(base, "POST", "/command/templates",
                       token=token, body=template.as_dict())[0] == 201

        with pytest.raises(urllib.error.HTTPError) as refused:
            materialize(base, token, template, "graph-loopback-003")

        assert refused.value.code == 409
        assert json.loads(refused.value.read())["error"]["code"] == \
            "capability_unsupported"
        # And nothing durable was written for the refusal.
        _status, recovered = request(base, "GET", f"/command/runs/{RUN_ID}")
        assert [row for row in recovered["records"]
                if row["record_type"] == "graph_definition"] == []
        # The provider really did resolve through the factory, so this refusal
        # is about the roster and not about an empty registry.
        assert [row.provider_id for row in srv.command_providers
                if row.available] == ["codex"]
