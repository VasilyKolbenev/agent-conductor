"""The one mutation that gives a run its plan, and the read that answers with it.

A run's graph reaches the browser through two doors and no others: one POST
that writes the plan once, and the existing run read, which grew a computed
`graph` half rather than a second read route. Everything else about the surface
is unchanged on purpose -- the same transport checks, the same containment
gate, the same identifier-only signal, and the same three answers the store's
own append semantics already give (created, exact retry, conflict).

The alpha cut is one immutable graph per run. Editing, versioning, templates and
a run list are a later slice, so a second plan is a question this product cannot
answer and is refused rather than stored beside the first.
"""
from __future__ import annotations

import json
import os

import pytest

from conductor.command.api_contracts import ERROR_STATUS
from conductor.command.graph_definition import GraphDefinition

from tests.test_command_adapters import FakeAdapter
from tests.test_command_http_api import (
    NOW,
    RUN_ID,
    api,
    encode,
    get_headers,
    post_headers,
)

GRAPH_PATH = f"/command/runs/{RUN_ID}/graph"


def graph_body(**changes):
    """A plan whose one acting step stands behind a gate, as every plan must."""
    body = {
        "graph_id": "graph-001",
        "nodes": [
            {"node_id": "plan", "kind": "task", "title": "Plan the change",
             "stage": "design", "resources": []},
            {"node_id": "human-gate", "kind": "gate", "title": "Confirm Do",
             "gate_id": "gate-do", "resources": []},
            {"node_id": "apply", "kind": "task", "title": "Do", "stage": "do",
             "instance_id": "claude-dev", "capability": "dispatch",
             "arguments": {"work_item_id": "work-001"}, "resources": []},
        ],
        "edges": [
            {"from_node": "plan", "to_node": "human-gate"},
            {"from_node": "human-gate", "to_node": "apply"},
        ],
    }
    body.update(changes)
    return body


def post_graph(subject, body, **header_changes):
    return subject.handle(
        "POST", GRAPH_PATH, post_headers(body, **header_changes), encode(body))


def read_run(subject):
    return subject.handle("GET", f"/command/runs/{RUN_ID}", get_headers())


def journal(store):
    return (store.run_path(RUN_ID) / "records.jsonl").read_bytes()


# -- created, exact retry, conflict, and no fourth answer ----------------------


def test_a_run_that_had_no_plan_now_follows_this_one(tmp_path):
    subject, store, events = api(tmp_path)
    response = post_graph(subject, graph_body())
    assert response.status == 201
    assert response.payload["graph_id"] == "graph-001"
    assert response.payload["run_id"] == RUN_ID
    assert response.payload["created_at"] == NOW
    stored = [row.value for row in store.read(RUN_ID).records
              if row.kind == "graph_definition"]
    assert [row.as_dict() for row in stored] == [response.payload]
    assert events == [RUN_ID]


def test_the_same_plan_under_the_same_id_appends_nothing_and_answers_200(tmp_path):
    """The retry answers with the created_at the FIRST write settled.

    A repeat that read the clock again would mint a second identity's worth of
    facts under one id, and the store would then have to call the retry a
    conflict -- which is the store being right about a lie this route told.
    """
    ticks = iter([NOW, "2026-08-13T13:00:00Z"])
    subject, store, events = api(tmp_path, clock=lambda: next(ticks))
    first = post_graph(subject, graph_body())
    before = journal(store)

    again = post_graph(subject, graph_body())

    assert (again.status, again.payload) == (200, first.payload)
    assert again.payload["created_at"] == NOW
    assert journal(store) == before
    assert events == [RUN_ID]


def test_the_same_id_carrying_a_different_plan_is_a_conflict(tmp_path):
    subject, store, events = api(tmp_path)
    post_graph(subject, graph_body())
    before = journal(store)
    moved = graph_body()
    moved["nodes"][0]["title"] = "Plan it differently"

    refused = post_graph(subject, moved)

    assert (refused.status, refused.payload["error"]["code"]) == (
        ERROR_STATUS["record_conflict"], "record_conflict")
    assert journal(store) == before
    assert events == [RUN_ID]


def test_a_second_plan_under_a_second_id_is_refused_not_stored_beside_it(tmp_path):
    """One run carries one graph; two would leave every reader guessing."""
    subject, store, events = api(tmp_path)
    post_graph(subject, graph_body())
    before = journal(store)

    refused = post_graph(subject, graph_body(graph_id="graph-002"))

    assert (refused.status, refused.payload["error"]["code"]) == (
        ERROR_STATUS["record_conflict"], "record_conflict")
    assert journal(store) == before
    assert events == [RUN_ID]


# -- the body is closed, and the server owns what the server owns --------------


@pytest.mark.parametrize("body", [
    {**graph_body(), "run_id": RUN_ID},
    {**graph_body(), "created_at": NOW},
    {**graph_body(), "schema_version": 2},
    {**graph_body(), "surprise": 1},
    {key: value for key, value in graph_body().items() if key != "edges"},
], ids=["run_id", "created_at", "schema_version", "unknown", "missing-edges"])
def test_the_plan_body_is_exactly_three_caller_owned_facts(tmp_path, body):
    subject, store, _ = api(tmp_path)
    before = journal(store)
    refused = post_graph(subject, body)
    assert (refused.status, refused.payload["error"]["code"]) == (
        ERROR_STATUS["contract_invalid"], "contract_invalid")
    assert journal(store) == before


@pytest.mark.parametrize("change", [
    {"nodes": []},
    {"edges": [{"from_node": "plan", "to_node": "ghost"}]},
    {"graph_id": "not a graph id"},
], ids=["no-nodes", "edge-to-nothing", "unusable-id"])
def test_a_document_the_graph_contract_refuses_never_reaches_the_store(
        tmp_path, change):
    subject, store, _ = api(tmp_path)
    before = journal(store)
    refused = post_graph(subject, graph_body(**change))
    assert refused.payload["error"]["code"] == "contract_invalid"
    assert journal(store) == before


def test_an_acting_step_that_no_gate_guards_is_refused_by_the_contract(tmp_path):
    """The base contract's rule, reaching the wire unchanged."""
    subject, store, _ = api(tmp_path)
    before = journal(store)
    ungated = graph_body(edges=[
        {"from_node": "plan", "to_node": "apply"},
        {"from_node": "plan", "to_node": "human-gate"}])
    refused = post_graph(subject, ungated)
    assert refused.payload["error"]["code"] == "contract_invalid"
    assert journal(store) == before


def test_an_uncontained_run_route_refuses_before_any_plan_is_written(tmp_path):
    """The containment gate runs before the store does, on this route too."""
    subject, store, events = api(tmp_path)
    path = store.run_path(RUN_ID) / "records.jsonl"
    try:
        os.link(path, tmp_path / "foreign-journal")
    except OSError as error:
        pytest.skip(f"hard links unavailable: {error}")
    before = path.read_bytes()

    refused = post_graph(subject, graph_body())

    assert (refused.status, refused.payload["error"]["code"]) == (
        ERROR_STATUS["route_unsafe"], "route_unsafe")
    assert path.read_bytes() == before and events == []


# -- a plan may only name work this run and this build can carry out -----------


def test_a_node_naming_an_instance_the_frozen_config_lacks_is_refused(tmp_path):
    subject, store, _ = api(tmp_path)
    before = journal(store)
    body = graph_body()
    body["nodes"][2]["instance_id"] = "ghost-instance"

    refused = post_graph(subject, body)

    assert (refused.status, refused.payload["error"]["code"]) == (
        ERROR_STATUS["service_refused"], "service_refused")
    assert refused.payload["error"]["detail"] == {
        "run_id": RUN_ID, "instance_id": "ghost-instance"}
    assert journal(store) == before


def test_a_node_naming_work_the_bound_adapter_cannot_do_is_refused(tmp_path):
    """A stored plan whose every proposal would be refused is not a plan."""
    subject, store, _ = api(tmp_path, adapters=[FakeAdapter(capabilities=("observe",))])
    before = journal(store)

    refused = post_graph(subject, graph_body())

    assert (refused.status, refused.payload["error"]["code"]) == (
        ERROR_STATUS["capability_unsupported"], "capability_unsupported")
    assert journal(store) == before


def test_a_step_that_does_no_work_is_held_to_no_capability(tmp_path):
    """Most of a plan is steps; only some of them act."""
    subject, _, _ = api(tmp_path, adapters=[FakeAdapter(capabilities=("observe",))])
    unbound = graph_body(
        nodes=[{"node_id": "plan", "kind": "task", "title": "Plan the change",
                "stage": "design", "resources": []}],
        edges=[])
    assert post_graph(subject, unbound).status == 201


def test_the_arguments_of_a_node_are_left_to_the_capabilitys_own_door(tmp_path):
    """The graph contract proves `arguments` is a JSON object and stops there.

    The propose door judges the payload against the capability's closed schema.
    Judging it here too would be two doors over one value, which is how they
    come to disagree -- and this plan carries a partial dispatch payload that
    the propose door, not this one, is the place to refuse.
    """
    subject, _, _ = api(tmp_path)
    assert post_graph(subject, graph_body()).status == 201


# -- the same transport, containment and signal as every other mutation --------


def test_the_graph_route_is_a_mutation_like_every_other(tmp_path):
    subject, store, _ = api(tmp_path)
    body = graph_body()
    before = journal(store)
    cases = {
        "csrf_denied": post_graph(subject, body, token="stale-token"),
        "same_origin_denied": post_graph(subject, body, origin="http://evil.test"),
        "malformed_request": subject.handle(
            "POST", GRAPH_PATH, post_headers(body), b"not json"),
        "method_not_allowed": subject.handle("GET", GRAPH_PATH, get_headers()),
    }
    for code, response in cases.items():
        assert (response.status, response.payload["error"]["code"]) == (
            ERROR_STATUS[code], code), code
    assert journal(store) == before


def test_the_graph_route_declares_its_body_length_before_reading_one(tmp_path):
    """Framing is held on the exact route, exactly as the other POSTs are."""
    subject, _, _ = api(tmp_path)
    headers = post_headers(graph_body())
    assert subject.body_length(GRAPH_PATH, headers) == len(encode(graph_body()))


def test_a_refused_signal_is_never_published_and_a_created_one_is_identifiers(
        tmp_path):
    subject, _, events = api(tmp_path)
    post_graph(subject, graph_body(), token="stale-token")
    assert events == []
    post_graph(subject, graph_body())
    post_graph(subject, graph_body())
    assert events == [RUN_ID]


# -- the run read answers with the plan, its digest, and the run's position ----


def test_the_run_read_carries_the_plan_its_digest_and_a_computed_runtime(tmp_path):
    subject, _, _ = api(tmp_path)
    written = post_graph(subject, graph_body()).payload

    payload = read_run(subject).payload

    assert set(payload) == {"run", "config", "records", "warnings", "graph"}
    graph = payload["graph"]
    assert graph["definition"] == written
    assert graph["definition_digest"] == GraphDefinition.from_dict(written).digest()
    assert graph["runtime"]["graph_id"] == "graph-001"
    assert [row["node_id"] for row in graph["runtime"]["nodes"]] == [
        "plan", "human-gate", "apply"]
    assert {row["phase"] for row in graph["runtime"]["nodes"]} == {"idle"}


def test_a_run_that_follows_no_plan_still_answers_the_graph_key(tmp_path):
    subject, _, _ = api(tmp_path)
    assert read_run(subject).payload["graph"] == {
        "definition": None, "definition_digest": None, "runtime": None}


def test_the_definition_on_the_wire_is_the_record_the_journal_holds(tmp_path):
    """One document, answered twice by the same read -- never two spellings."""
    subject, _, _ = api(tmp_path)
    post_graph(subject, graph_body())
    payload = read_run(subject).payload
    wrapped = [row for row in payload["records"]
               if row["record_type"] == "graph_definition"]
    assert [row["record"] for row in wrapped] == [payload["graph"]["definition"]]
    assert json.dumps(payload["graph"], sort_keys=True)  # plain JSON, no proxies
