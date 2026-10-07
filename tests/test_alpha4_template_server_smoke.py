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

**The default cycle is what goes over the wire here, and that is a product fact
rather than a testing convenience.** `dalio-v2` binds `review` AND `dispatch`,
Codex CLI now carries both, and this file materializes the shipped revision
against the provider the factory resolved from a pinned executable -- not
against a `DeepPlanAdapter`, not against a double that serves every capability
by construction. If the default cycle cannot be published and materialized on
the real road a browser takes, this file is where that is discovered.

This is a REPLACEMENT for what stood here. While no catalogued provider served
`review`, the claim at the end of this file was that the frozen template could
be materialized against nothing and the route answered `capability_unsupported`.
That was true and is now false: the reason it named -- no resolver from an
artifact reference to its content -- was spent when `artifact_handoff` landed,
and the claim went with it rather than being left standing.

Revision 1 still publishes and still materializes; the route's question is
whether the bound adapters serve the plan's capabilities, and they do. What
makes revision 1 a replay witness rather than the default is a RUNTIME fact --
its review steps name no result artifact, so the transport refuses one before
any spawn -- and that is asserted where it happens, not here.

One smaller template is still published by the tests that are about route
mechanics rather than about the default cycle: a gate-then-dispatch pair, the
smallest document this product will build.
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
#: The shipped revision a run materializes from. Named once here so the two
#: tests that drive the default cycle over the socket cannot come to disagree
#: about which revision "the default" is.
DEFAULT_TEMPLATE = "dalio-v2"
#: The historical revision. It publishes and materializes exactly as the default
#: does -- the route asks whether the bound adapters serve the plan, and they
#: do. What keeps it a witness is a runtime refusal, asserted where it happens.
FROZEN_TEMPLATE = "dalio-v1"
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


def a_default_template(base, token, name=DEFAULT_TEMPLATE):
    """Publish the SHIPPED cycle through the route, and return it.

    Read with `load_template`, so what travels the wire is the file this build
    ships rather than a document assembled here to suit the roster.
    """
    template = load_template(name)
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
    """201 the first time and 200 for the same bytes, on the wire.

    The DEFAULT revision, because publishing is the first half of the road this
    file exists to prove and the shipped cycle is what really travels it.
    """
    with a_run_on_a_socket(tmp_path) as (_srv, base, token):
        document = load_template(DEFAULT_TEMPLATE).as_dict()
        assert request(base, "POST", "/command/templates",
                       token=token, body=document) == (201, document)
        assert request(base, "POST", "/command/templates",
                       token=token, body=document)[0] == 200


def test_a_browser_can_give_a_run_its_plan_and_read_it_back(tmp_path):
    """The write, the authoritative read, and the retry that writes nothing.

    The DEFAULT cycle, and a real provider: `server.build` resolved it from a
    pinned executable through the factory, so the availability this route
    consulted is the one this build established rather than a descriptor a test
    made up, and the plan that lands is the shipped `dalio-v2` rather than a
    document written to fit whatever the roster happens to serve.
    """
    with a_run_on_a_socket(tmp_path) as (_srv, base, token):
        template = a_default_template(base, token)

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


def test_the_default_cycle_is_materialized_by_a_real_catalogued_provider(
        tmp_path):
    """The Day 3 blocker, cleared, said by the route that used to meet it.

    This is the replacement for the claim that stood here: `dalio-v1` binds
    `review`, no catalogued provider served it, and the route answered 409
    `capability_unsupported` before a durable byte was written. Both halves have
    moved. `dalio-v2` is the default and it binds the same two controls; Codex
    CLI carries both; and the plan lands.

    Every step is the real one. The provider resolved through the factory from a
    pinned executable on this disk, the template is the file this build ships,
    the route is a loopback socket, and the definition is read back out of the
    run's own journal -- so nothing here is a double that would serve any
    capability asked of it.
    """
    with a_run_on_a_socket(tmp_path) as (srv, base, token):
        template = a_default_template(base, token)
        assert template.revision == 2
        assert {node.capability for node in template.steps()
                if node.capability is not None} == {"review", "dispatch"}

        status, plan = materialize(
            base, token, template, "graph-loopback-003")

        assert status == 201, plan
        # The plan is durable, and it is the one the route answered with.
        _status, recovered = request(base, "GET", f"/command/runs/{RUN_ID}")
        assert [row["record"] for row in recovered["records"]
                if row["record_type"] == "graph_definition"] == [plan]
        # Every step named a real instance, and the review steps carry the
        # result reference revision 2 exists to add.
        published = [node["arguments"]["result_artifact_ref"]
                     for node in plan["nodes"]
                     if node.get("capability") == "review"]
        assert published == [
            "artifact-goal", "artifact-problems", "artifact-causes",
            "artifact-plan"]
        # The provider really did resolve through the factory, so this is about
        # the roster and not about a registry that admits everything.
        assert [row.provider_id for row in srv.command_providers
                if row.available] == ["codex"]


def test_the_frozen_revision_still_materializes_and_is_a_witness_elsewhere(
        tmp_path):
    """Revision 1 is not refused by this route, and never was for its own sake.

    The route asks one question: do the adapters this run's frozen configuration
    binds serve the capabilities the plan names, with the payload family this
    API speaks. Revision 1 names the same two controls as revision 2, so the
    answer is yes and the plan lands.

    What makes revision 1 a replay witness instead of the default is a RUNTIME
    fact and not a route one: its review steps name no `result_artifact_ref`, so
    a review materialized from it has nowhere to publish and the transport
    refuses it before any spawn. That refusal is asserted where it happens --
    `test_command_attempt_ownership` and `test_command_codex_review` -- and
    asserting it here would be this file claiming a boundary it does not own.
    """
    with a_run_on_a_socket(tmp_path) as (_srv, base, token):
        frozen = a_default_template(base, token, FROZEN_TEMPLATE)
        assert frozen.revision == 1
        assert all("result_artifact_ref" not in node.arguments
                   for node in frozen.steps() if node.capability == "review")

        status, plan = materialize(base, token, frozen, "graph-loopback-004")

        assert status == 201, plan
