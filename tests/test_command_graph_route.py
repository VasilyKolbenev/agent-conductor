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
from contextlib import contextmanager

import pytest

from conductor.command.api_contracts import ERROR_STATUS
from conductor.command.graph_definition import GraphDefinition
from conductor.command.run_store import RunStore

from tests.alpha3_graph_artifacts import load
from tests.test_command_adapters import FakeAdapter
from tests.test_command_schema_doubles import (
    DeepDispatchAdapter,
    DeepPlanAdapter,
    MixedSchemaAdapter,
    ProcessDispatchAdapter,
    RetiredCapabilityAdapter,
)
from tests.test_command_http_api import (
    NOW,
    RUN_ID,
    api,
    encode,
    get_headers,
    post,
    post_headers,
    proposal_body,
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
             "arguments": {"work_item_id": "work-001",
                           "instruction_ref": "instruction-001",
                           "profile": "implement",
                           "artifact_refs": ["artifact-001"],
                           "output_limit_profile": "normal"},
             "resources": []},
        ],
        "edges": [
            {"from_node": "plan", "to_node": "human-gate"},
            {"from_node": "human-gate", "to_node": "apply"},
        ],
    }
    body.update(changes)
    return body


def graph_api(tmp_path, *, adapters=None, **changes):
    """A command API whose adapter DECLARES the argument family it serves.

    The default `FakeAdapter` declares no `argument_schemas` at all, which
    makes the registry's per-pair validation a no-op -- so a door that only
    consulted the global schema table passed every test while it let a plan no
    adapter could execute become durable. Every graph test starts from a
    double that says which family it speaks.
    """
    return api(
        tmp_path,
        adapters=[DeepDispatchAdapter()] if adapters is None else adapters,
        **changes)


def _stranger():
    """An adapter this run's frozen configuration binds to nothing at all."""
    return DeepDispatchAdapter(adapter_id="stranger")


def post_graph(subject, body, **header_changes):
    return subject.handle(
        "POST", GRAPH_PATH, post_headers(body, **header_changes), encode(body))


def read_run(subject):
    return subject.handle("GET", f"/command/runs/{RUN_ID}", get_headers())


def journal(store):
    return (store.run_path(RUN_ID) / "records.jsonl").read_bytes()


# -- created, exact retry, conflict, and no fourth answer ----------------------


def test_a_run_that_had_no_plan_now_follows_this_one(tmp_path):
    subject, store, events = graph_api(tmp_path)
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
    subject, store, events = graph_api(tmp_path, clock=lambda: next(ticks))
    first = post_graph(subject, graph_body())
    before = journal(store)

    again = post_graph(subject, graph_body())

    assert (again.status, again.payload) == (200, first.payload)
    assert again.payload["created_at"] == NOW
    assert journal(store) == before
    assert events == [RUN_ID]


def test_the_same_id_carrying_a_different_plan_is_a_conflict(tmp_path):
    subject, store, events = graph_api(tmp_path)
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
    subject, store, events = graph_api(tmp_path)
    post_graph(subject, graph_body())
    before = journal(store)

    refused = post_graph(subject, graph_body(graph_id="graph-002"))

    assert (refused.status, refused.payload["error"]["code"]) == (
        ERROR_STATUS["record_conflict"], "record_conflict")
    assert journal(store) == before
    assert events == [RUN_ID]


def an_api_over(root, *, adapters):
    """A second process over the same store, with a registry of its own."""
    from conductor.command.adapters import AdapterRegistry
    from conductor.command.http_api import CommandApi, PRODUCT_COMMAND_BUDGET
    from conductor.command.http_transport import CommandSession
    from conductor.command.run_store import RunStore
    from tests.test_command_http_api import PORT, TOKEN, ids

    return CommandApi(
        RunStore(root), AdapterRegistry(adapters),
        session=CommandSession(PORT, TOKEN), budget=PRODUCT_COMMAND_BUDGET,
        clock=lambda: "2026-08-13T14:00:00Z", ids=ids(),
        publish_run=lambda _run_id: None)


@pytest.mark.parametrize("body_changes,status,code", [
    ({}, 200, None),
    ({"graph_id": "graph-002"}, 409, "record_conflict"),
], ids=["exact-retry", "a-second-plan"])
def test_a_standing_graph_is_answered_from_the_journal_not_from_the_registry(
        tmp_path, body_changes, status, code):
    """A durable record's answer may not depend on mutable process state.

    Validating before looking made an exact retry a `service_refused`: a client
    whose reply was lost, retrying against a process that starts with a
    different registry, was refused a record it had already written. So the
    standing graph is looked for FIRST, and neither answer below consults an
    adapter, a capability schema or the frozen configuration at all.
    """
    subject, store, _ = graph_api(tmp_path)
    first = post_graph(subject, graph_body())
    assert first.status == 201
    before = journal(store)

    restarted = an_api_over(tmp_path, adapters=[])
    again = post_graph(restarted, graph_body(**body_changes))

    assert again.status == status
    if code is None:
        assert again.payload == first.payload
    else:
        assert again.payload["error"]["code"] == code
    assert journal(store) == before


# -- the body is closed, and the server owns what the server owns --------------


@pytest.mark.parametrize("body", [
    {**graph_body(), "run_id": RUN_ID},
    {**graph_body(), "created_at": NOW},
    {**graph_body(), "schema_version": 2},
    {**graph_body(), "surprise": 1},
    {key: value for key, value in graph_body().items() if key != "edges"},
], ids=["run_id", "created_at", "schema_version", "unknown", "missing-edges"])
def test_the_plan_body_is_exactly_three_caller_owned_facts(tmp_path, body):
    subject, store, _ = graph_api(tmp_path)
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
    subject, store, _ = graph_api(tmp_path)
    before = journal(store)
    refused = post_graph(subject, graph_body(**change))
    assert refused.payload["error"]["code"] == "contract_invalid"
    assert journal(store) == before


def test_an_acting_step_that_no_gate_guards_is_refused_by_the_contract(tmp_path):
    """The base contract's rule, reaching the wire unchanged."""
    subject, store, _ = graph_api(tmp_path)
    before = journal(store)
    ungated = graph_body(edges=[
        {"from_node": "plan", "to_node": "apply"},
        {"from_node": "plan", "to_node": "human-gate"}])
    refused = post_graph(subject, ungated)
    assert refused.payload["error"]["code"] == "contract_invalid"
    assert journal(store) == before


class _UnsafeUnderTheLock(RunStore):
    """A store whose route is aliased between the two containment checks.

    The window is real and narrow: a route checked before the store is opened
    can be made unsafe before the transaction re-checks it. That second check
    exists to close the race -- and driving it needs a deterministic hand, not
    a real one, so the alias appears the first time a transaction is opened,
    which on every mutating route is after the outer check and before the
    inner one.
    """

    alias = None

    @contextmanager
    def transaction(self):
        if self.alias is not None and not self.alias.exists():
            os.link(self.run_path(RUN_ID) / "records.jsonl", self.alias)
        with super().transaction():
            yield


def an_api_that_turns_unsafe(tmp_path):
    """A command API over a store that is aliased under its own lock."""
    from conductor.command.adapters import AdapterRegistry
    from conductor.command.http_api import CommandApi, PRODUCT_COMMAND_BUDGET
    from conductor.command.http_transport import CommandSession
    from conductor.command.run_store import snapshot_digest
    from tests.test_command_http_api import PORT, TOKEN, ids
    from tests.test_command_run_store import CONFIG, a_run

    store = _UnsafeUnderTheLock(tmp_path)
    store.create_run(a_run(
        run_id=RUN_ID, mode="confirm", config_digest=snapshot_digest(CONFIG)),
        CONFIG)
    events = []
    subject = CommandApi(
        store, AdapterRegistry([DeepDispatchAdapter()]),
        session=CommandSession(PORT, TOKEN), budget=PRODUCT_COMMAND_BUDGET,
        clock=lambda: NOW, ids=ids(), publish_run=events.append)
    return subject, store, events


@pytest.mark.parametrize("route,body", [
    ("graph", graph_body()),
    ("proposals", None),
    ("decisions", None),
])
def test_every_mutating_route_answers_route_unsafe_under_its_own_lock(
        tmp_path, route, body):
    """The second containment check must refuse like the first, not crash.

    It did not. A refusal is a frozen value and the generator transaction
    assigns `__traceback__` on its way out, which a frozen value refused -- so
    this exact path produced an untranslatable TypeError instead of one closed
    409. Every mutating route re-checks under the same lock, so every one of
    them is driven here, and each is read for the exact JSON envelope.
    """
    from tests.test_command_http_api import decision_body

    subject, store, events = an_api_that_turns_unsafe(tmp_path)
    try:
        os.link(store.run_path(RUN_ID) / "records.jsonl", tmp_path / "probe-link")
        (tmp_path / "probe-link").unlink()
    except OSError as error:
        pytest.skip(f"hard links unavailable: {error}")
    sent = {"graph": body, "proposals": proposal_body(),
            "decisions": decision_body()}[route]
    store.alias = tmp_path / "foreign-journal"
    before = journal(store)

    refused = post(subject, f"/command/runs/{RUN_ID}/{route}", sent)

    assert refused.status == ERROR_STATUS["route_unsafe"]
    assert refused.payload == {"error": {
        "code": "route_unsafe",
        "message": "run route is not structurally contained",
        "detail": {}}}
    assert journal(store) == before and events == []


def test_an_uncontained_run_route_refuses_before_any_plan_is_written(tmp_path):
    """The containment gate runs before the store does, on this route too."""
    subject, store, events = graph_api(tmp_path)
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
    subject, store, _ = graph_api(tmp_path)
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
    subject, store, _ = graph_api(tmp_path, adapters=[FakeAdapter(capabilities=("observe",))])
    before = journal(store)

    refused = post_graph(subject, graph_body())

    assert (refused.status, refused.payload["error"]["code"]) == (
        ERROR_STATUS["capability_unsupported"], "capability_unsupported")
    assert journal(store) == before


def test_a_step_that_does_no_work_is_held_to_no_capability(tmp_path):
    """Most of a plan is steps; only some of them act."""
    subject, _, _ = graph_api(tmp_path, adapters=[FakeAdapter(capabilities=("observe",))])
    unbound = graph_body(
        nodes=[{"node_id": "plan", "kind": "task", "title": "Plan the change",
                "stage": "design", "resources": []}],
        edges=[])
    assert post_graph(subject, unbound).status == 201


# -- a plan is judged by the capability's own schema before it is durable ------


SECRET = "APIKEY-SECRET-GRAPH"


@pytest.mark.parametrize("payload", [
    {"api_key": SECRET, "cwd": "C:/outside"},
    {"work_item_id": "work-001"},
    {"work_item_id": "work-001", "instruction_ref": "instruction-001",
     "profile": "implement", "artifact_refs": ["artifact-001"],
     "output_limit_profile": "normal", "env": SECRET},
    {"work_item_id": "work-001", "instruction_ref": "C:/outside/instruction",
     "profile": "implement", "artifact_refs": ["artifact-001"],
     "output_limit_profile": "normal"},
    {"work_item_id": "work-001", "instruction_ref": "instruction-001",
     "profile": "sudo", "artifact_refs": ["artifact-001"],
     "output_limit_profile": "normal"},
], ids=["a-secret-and-a-path", "half-a-payload", "one-field-too-many",
        "a-path-where-an-id-belongs", "a-word-outside-the-vocabulary"])
def test_a_payload_the_capability_schema_refuses_never_becomes_durable(
        tmp_path, payload):
    """A graph is immutable, so a payload admitted here is admitted forever.

    Without this door the route took any JSON object: a credential, an
    absolute path or an environment name became a durable record and went out
    on every later read, and the plan it described was one the propose door
    would refuse every time. Every field of every schema is a closed id or a
    closed vocabulary word, so calling the schema IS the screen.
    """
    subject, store, events = graph_api(tmp_path)
    before = journal(store)
    body = graph_body()
    body["nodes"][2]["arguments"] = payload

    refused = post_graph(subject, body)

    assert (refused.status, refused.payload["error"]["code"]) == (
        ERROR_STATUS["contract_invalid"], "contract_invalid")
    assert refused.payload["error"]["detail"] == {}
    assert journal(store) == before and events == []
    assert SECRET not in journal(store).decode("utf-8")
    assert SECRET not in json.dumps(read_run(subject).payload)


@pytest.mark.parametrize("adapter,label", [
    (ProcessDispatchAdapter, "another payload family behind the same name"),
    (FakeAdapter, "no declared family at all"),
    (MixedSchemaAdapter, "this capability swapped, another one left alone"),
])
def test_a_plan_the_bound_adapter_could_never_execute_is_refused(
        tmp_path, adapter, label):
    """The PAIR decides, not the capability name.

    Both adapters below declare `dispatch`. One serves it under
    `structured-process-v1`, whose payload is a different shape entirely; the
    other declares no argument family for it. Judging the plan against the
    global schema table said yes to both -- the route answered 201, the first
    proposal against that node answered `service_refused`, and the immutable
    plan stood in the journal with no way to edit or remove it.
    """
    subject, store, events = graph_api(tmp_path, adapters=[adapter()])
    before = journal(store)

    refused = post_graph(subject, graph_body())

    assert (refused.status, refused.payload["error"]["code"]) == (
        ERROR_STATUS["capability_unsupported"], "capability_unsupported"), label
    assert journal(store) == before and events == []
    assert not [row for row in store.read(RUN_ID).records
                if row.kind == "graph_definition"], "no graph became durable"


#: The node's own payload, and one no schema admits.
A_GOOD_PAYLOAD = graph_body()["nodes"][2]["arguments"]
A_BAD_PAYLOAD = {"api_key": "APIKEY-SECRET-GRAPH", "cwd": "C:/outside"}
#: A capability the frozen command API carries no argument schema for.
A_RETIRED_PAYLOAD = {"body": "hello"}
#: A capability the frozen API DOES carry, that these adapters do not serve.
A_STOP_PAYLOAD = {"target_attempt_id": "attempt-001", "reason": "user"}
#: The instance the run's frozen configuration actually declares.
BOUND = "claude-dev"


@pytest.mark.parametrize(
    "adapters,instance,capability,arguments,status,code", [
        ([DeepDispatchAdapter], BOUND, "dispatch", A_GOOD_PAYLOAD, 201, None),
        ([DeepDispatchAdapter], BOUND, "dispatch", A_BAD_PAYLOAD, 422,
         "contract_invalid"),
        ([FakeAdapter], BOUND, "dispatch", A_GOOD_PAYLOAD, 409,
         "capability_unsupported"),
        ([ProcessDispatchAdapter], BOUND, "dispatch", A_GOOD_PAYLOAD, 409,
         "capability_unsupported"),
        ([RetiredCapabilityAdapter], BOUND, "message", A_RETIRED_PAYLOAD, 409,
         "capability_unsupported"),
        # The product a diagonal misses: an unsupported pair is unsupported
        # whatever its payload says.
        ([FakeAdapter], BOUND, "dispatch", A_BAD_PAYLOAD, 409,
         "capability_unsupported"),
        ([ProcessDispatchAdapter], BOUND, "dispatch", A_BAD_PAYLOAD, 409,
         "capability_unsupported"),
        # A capability the frozen API carries and this adapter does not serve.
        ([DeepDispatchAdapter], BOUND, "stop", A_STOP_PAYLOAD, 409,
         "capability_unsupported"),
        # Composite cases: the BINDING is resolved first, so these answer about
        # the service and not about a capability.
        ([], BOUND, "dispatch", A_GOOD_PAYLOAD, 409, "service_refused"),
        ([DeepDispatchAdapter], "ghost-instance", "message", A_RETIRED_PAYLOAD,
         409, "service_refused"),
        # A stranger in the registry binds nothing here and changes nothing.
        ([_stranger], BOUND, "dispatch", A_GOOD_PAYLOAD, 409, "service_refused"),
    ], ids=["deep-valid", "deep-invalid", "schema-less", "structured-process",
            "retired-capability", "schema-less-and-invalid",
            "structured-process-and-invalid", "capability-not-served",
            "empty-registry", "ghost-instance-and-retired",
            "unrelated-stranger-only"])
def test_one_payload_gets_one_verdict_on_both_roads(
        tmp_path, adapters, instance, capability, arguments, status, code):
    """A plan and a proposal describe the same work; they may not disagree.

    They did, in three ways. A schema-less adapter refused the plan and took
    the proposal. A capability this API carries no schema for answered
    `contract_invalid` on one road and `capability_unsupported` on the other.
    And the composite cases below -- an empty registry, a ghost instance
    carrying a retired capability -- diverged because the proposal road decided
    the capability from a union of every registered manifest BEFORE it had read
    the run's frozen configuration, while the plan road resolves the binding
    first and asks about the pair afterwards.

    Every refusal is compared whole: the same status, the same code, the same
    message and the same detail. A word that matches while a detail does not is
    still two answers to one question.
    """
    subject, store, events = graph_api(
        tmp_path, adapters=[adapter() for adapter in adapters])
    body = graph_body()
    body["nodes"][2].update(
        instance_id=instance, capability=capability, arguments=arguments)
    accepted = status == 201

    written = post_graph(subject, body)
    proposed = post(subject, f"/command/runs/{RUN_ID}/proposals", {
        **proposal_body(), "instance_id": instance, "capability": capability,
        "arguments": arguments,
        **({"node_id": body["nodes"][2]["node_id"]} if accepted else {})})

    assert (written.status, proposed.status) == (status, status)
    if code is None:
        assert [row.kind for row in store.read(RUN_ID).records] == [
            "graph_definition", "action_proposal"]
        assert events == [RUN_ID, RUN_ID]
    else:
        assert written.payload["error"]["code"] == code
        assert written.payload == proposed.payload, "one question, one envelope"
        assert [row.kind for row in store.read(RUN_ID).records] == []
        assert events == []


def test_a_capability_no_argument_schema_carries_is_refused(tmp_path):
    """The adapter declaring it is not enough; the API must be able to type it."""
    subject, store, _ = graph_api(tmp_path)
    before = journal(store)
    body = graph_body()
    body["nodes"][2].update(capability="observe", arguments={})

    refused = post_graph(subject, body)

    assert (refused.status, refused.payload["error"]["code"]) == (
        ERROR_STATUS["capability_unsupported"], "capability_unsupported")
    assert journal(store) == before


def test_the_frozen_dalio_artifact_is_a_plan_this_route_accepts(tmp_path):
    """A default the product could not write through its own route is no default.

    Every capability node of the canonical template used to be refused by the
    capability schemas while the artifact shipped to the UI lane anyway. What
    is driven here is the FROZEN document on disk, not the builder that wrote
    it -- the bytes a consumer actually receives are the bytes proven writable.
    """
    subject, _, _ = graph_api(tmp_path, adapters=[DeepPlanAdapter()])
    frozen = load("alpha3_dalio_definition")["definition"]

    written = post_graph(subject, {
        "graph_id": frozen["graph_id"], "nodes": frozen["nodes"],
        "edges": frozen["edges"]})

    assert written.status == 201
    assert [row["node_id"] for row in written.payload["nodes"]] == [
        row["node_id"] for row in frozen["nodes"]]


def test_a_node_that_carries_the_nodes_own_payload_still_proposes(tmp_path):
    """One schema, two callers: what the plan may say, a proposal may repeat."""
    subject, _, _ = graph_api(tmp_path)
    assert post_graph(subject, graph_body()).status == 201

    node = graph_body()["nodes"][2]
    proposed = post(subject, f"/command/runs/{RUN_ID}/proposals", {
        **proposal_body(), "arguments": node["arguments"],
        "node_id": node["node_id"]})
    assert proposed.status == 201
    assert proposed.payload["node_id"] == node["node_id"]


# -- the same transport, containment and signal as every other mutation --------


def test_the_graph_route_is_a_mutation_like_every_other(tmp_path):
    subject, store, _ = graph_api(tmp_path)
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
    subject, _, _ = graph_api(tmp_path)
    headers = post_headers(graph_body())
    assert subject.body_length(GRAPH_PATH, headers) == len(encode(graph_body()))


def test_a_refused_signal_is_never_published_and_a_created_one_is_identifiers(
        tmp_path):
    subject, _, events = graph_api(tmp_path)
    post_graph(subject, graph_body(), token="stale-token")
    assert events == []
    post_graph(subject, graph_body())
    post_graph(subject, graph_body())
    assert events == [RUN_ID]


# -- the run read answers with the plan, its digest, and the run's position ----


def test_the_run_read_carries_the_plan_its_digest_and_a_computed_runtime(tmp_path):
    subject, _, _ = graph_api(tmp_path)
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
    subject, _, _ = graph_api(tmp_path)
    assert read_run(subject).payload["graph"] == {
        "definition": None, "definition_digest": None, "runtime": None,
        "schedule": None,
        # An empty MAP rather than a fifth null, and the difference is
        # honest: the four above are one document that is not there, and
        # this is a per-step reading over no steps.
        "success_criteria": {}}


def test_a_run_whose_journal_does_not_replay_is_given_no_projection_at_all(
        tmp_path):
    """A partial position read off a journal nobody could replay is a guess."""
    subject, store, _ = graph_api(tmp_path)
    post_graph(subject, graph_body())
    with (store.run_path(RUN_ID) / "records.jsonl").open("ab") as stream:
        stream.write(b'{"record_type":"graph_definition","record":{}}\n')

    refused = read_run(subject)

    assert (refused.status, refused.payload["error"]["code"]) == (
        ERROR_STATUS["run_corrupt"], "run_corrupt")
    assert "graph" not in refused.payload


@pytest.mark.parametrize("word", ["phase", "outcome", "pass", "attempt_id"])
def test_no_plan_a_browser_posts_can_carry_a_word_that_belongs_to_running(
        tmp_path, word):
    """The durable/runtime split, at the door a browser actually pushes on.

    These words are the projection's: computed, never stored. A plan that could
    carry one would be an immutable document changing while it is executed, and
    every reader would then have to ask which copy is true.

    What refuses it HERE is the node contract's closed field set, which admits
    no name of its own beyond the ten it declares -- the same refusal an
    ordinary typo gets. The by-name walk that refuses these words at any depth
    is a second door behind it, and its own witnesses are next door in
    `test_command_graph_definition.py`, over documents this closed body cannot
    reach.
    """
    subject, store, _ = graph_api(tmp_path)
    before = journal(store)
    body = graph_body()
    body["nodes"][0][word] = "whatever"

    refused = post_graph(subject, body)

    assert refused.payload["error"]["code"] == "contract_invalid"
    assert journal(store) == before


def test_the_definition_on_the_wire_is_the_record_the_journal_holds(tmp_path):
    """One document, answered twice by the same read -- never two spellings."""
    subject, _, _ = graph_api(tmp_path)
    post_graph(subject, graph_body())
    payload = read_run(subject).payload
    wrapped = [row for row in payload["records"]
               if row["record_type"] == "graph_definition"]
    assert [row["record"] for row in wrapped] == [payload["graph"]["definition"]]
    assert json.dumps(payload["graph"], sort_keys=True)  # plain JSON, no proxies
