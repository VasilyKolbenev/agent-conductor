"""Publishing a reusable plan, and giving one run its own copy of it.

Two closed documents, not one document with two shapes. §4.4's `/graph` stays
byte-compatible: it is not touched here, it gains no refusal here, and the
tests that own it are unchanged. What this file proves is the road beside it --
a revision published once and forever, and a run whose plan is materialized
from that revision by the production constructor and by nothing else.

The concurrency relations are the point of the durable half. Each is stated as
a SET of admissible outcomes rather than an order, because two racing clients
have no order: what is fixed is that exactly one of them created something,
that the other is told the truth, and that the bytes left behind are one
document rather than a mixture.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from conductor.command.adapters.provider import ProviderContract
from conductor.command.api_contracts import ERROR_STATUS
from conductor.command.graph_definition import GraphDefinition
from conductor.command.graph_template import GraphTemplate, load_template
from conductor.command.http_api import CommandApi, PRODUCT_COMMAND_BUDGET
from conductor.command.http_transport import CommandSession
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.template_store import TemplateStore

from tests.test_command_run_store import CONFIG, a_run
from tests.test_command_http_api import (
    NOW,
    PORT,
    RUN_ID,
    TOKEN,
    ids,
    post,
)
from tests.test_command_schema_doubles import DeepPlanAdapter
from conductor.command.adapters import AdapterRegistry

TEMPLATES_PATH = "/command/templates"
FROM_TEMPLATE_PATH = f"/command/runs/{RUN_ID}/graph/from-template"
#: The two adapters `CONFIG` binds its instances to. Written here rather than
#: read from the catalog: a test that took both sides from one production value
#: would agree with itself whatever that value became.
BOUND = ("claude-code", "codex")


def contracts(*, reachable=BOUND, known=BOUND):
    """Reviewed provider descriptors, as the factory hands them to the API.

    `availability` is a STATE, so an unreachable provider is described exactly
    as fully as a reachable one -- that is what makes the route's refusal a
    fact about transport rather than about which product it was.
    """
    return tuple(
        ProviderContract(
            provider_id=name, display_name=f"Provider {name}", vendor="test",
            version="fake-v1", capabilities=("observe", "review", "dispatch"),
            schema_pairs=[("review", "deep-arguments-v1"),
                          ("dispatch", "deep-arguments-v1")],
            lifecycle=("observe", "prepare", "execute", "verify"),
            availability="available" if name in reachable else "executable_absent",
            available=name in reachable)
        for name in known)


def api(tmp_path, *, providers=None, adapters=None, published=None,
        clock=lambda: NOW):
    """One API over a real run, a real template store, and reviewed providers."""
    store = RunStore(tmp_path)
    store.create_run(a_run(
        run_id=RUN_ID, mode="confirm", config_digest=snapshot_digest(CONFIG)),
        CONFIG)
    events = [] if published is None else published
    subject = CommandApi(
        store, AdapterRegistry([DeepPlanAdapter()] if adapters is None else adapters),
        session=CommandSession(PORT, TOKEN), budget=PRODUCT_COMMAND_BUDGET,
        clock=clock, ids=ids(), publish_run=events.append,
        providers=contracts() if providers is None else providers,
        templates=TemplateStore(tmp_path))
    return subject, store, events


def template_body(**changes):
    document = load_template("dalio-v1").as_dict()
    document.update(changes)
    return document


def from_template_body(**changes):
    template = load_template("dalio-v1")
    body = {
        "graph_id": "graph-from-template-001",
        "template_id": template.template_id,
        "revision": template.revision,
        "assignments": {role: "claude-dev" for role in template.roles},
    }
    body.update(changes)
    return body


def send(subject, path, body):
    return post(subject, path, body)


def status_of(subject, path, body):
    return send(subject, path, body).status


def code_of(response):
    return response.payload["error"]["code"]


# --- publishing a revision ---


def test_a_revision_is_published_once_and_restated_forever(tmp_path):
    """201 the first time, 200 for the same bytes, and no signal on either.

    No run is involved, so no run changed, so nothing is published. A frame is
    a claim that some run moved and neither of these did.
    """
    subject, _store, events = api(tmp_path)
    body = template_body()
    first = send(subject, TEMPLATES_PATH, body)
    assert first.status == 201
    again = send(subject, TEMPLATES_PATH, body)
    assert again.status == 200
    assert first.payload == again.payload == body
    assert events == []


def test_a_second_revision_saying_something_else_is_a_conflict(tmp_path):
    """An edit is a new revision; two plans may not wear one identity."""
    subject, _store, events = api(tmp_path)
    assert status_of(subject, TEMPLATES_PATH, template_body()) == 201
    edited = template_body()
    edited["nodes"][0]["title"] = "Goal, restated"
    refused = send(subject, TEMPLATES_PATH, edited)
    assert refused.status == ERROR_STATUS["record_conflict"]
    assert code_of(refused) == "record_conflict"
    assert events == []
    # And a NEW revision of the same edit is admitted.
    edited["revision"] = 2
    assert status_of(subject, TEMPLATES_PATH, edited) == 201


@pytest.mark.parametrize("field,value", [
    ("run_id", RUN_ID),
    ("created_at", NOW),
    ("provider_id", "claude-code"),
    ("instance_id", "claude-dev"),
])
def test_the_published_document_is_closed_to_the_words_it_does_not_own(
        tmp_path, field, value):
    """A template belongs to no run, carries no clock, and names no deployment."""
    subject, _store, events = api(tmp_path)
    refused = send(subject, TEMPLATES_PATH, template_body(**{field: value}))
    assert refused.status == ERROR_STATUS["contract_invalid"]
    assert events == []


def test_a_deployment_word_inside_a_node_is_refused_by_the_closed_document(tmp_path):
    """No by-name screen: an unknown key at any level is refused as unknown."""
    subject, _store, _events = api(tmp_path)
    body = template_body()
    body["nodes"][0]["instance_id"] = "claude-dev"
    assert status_of(subject, TEMPLATES_PATH, body) == \
        ERROR_STATUS["contract_invalid"]


# --- materializing one run's plan ---


def published(subject, body=None):
    assert status_of(subject, TEMPLATES_PATH, body or template_body()) == 201


def test_a_run_is_given_the_plan_the_production_constructor_builds(tmp_path):
    """The record is what `materialize` produces, and one frame says so."""
    subject, store, events = api(tmp_path)
    published(subject)
    created = send(subject, FROM_TEMPLATE_PATH, from_template_body())
    assert created.status == 201
    definition = GraphDefinition.from_dict(created.payload)
    assert definition.run_id == RUN_ID and definition.created_at == NOW
    assert {node.instance_id for node in definition.nodes
            if node.instance_id} == {"claude-dev"}
    # The stored record IS the answer, and the signal carries an identifier.
    stored = next(row.value for row in store.read(RUN_ID).records
                  if row.kind == "graph_definition")
    assert stored == definition
    assert events == [RUN_ID]


def test_the_plan_names_a_role_nowhere_and_a_deployment_only_where_a_run_does(
        tmp_path):
    """A template says roles; the record it becomes says instances."""
    subject, _store, _events = api(tmp_path)
    published(subject)
    created = send(subject, FROM_TEMPLATE_PATH, from_template_body())
    document = json.dumps(created.payload)
    assert '"role_id"' not in document and '"instance_id"' in document
    # And no provider or harness name reaches the durable record.
    for word in BOUND:
        assert word not in document


def test_an_exact_retry_answers_from_the_journal_and_consults_nothing(tmp_path):
    """The record is durable, so the answer may not depend on today's registry.

    The second API starts with NO adapters, NO provider descriptors and a
    different clock. A client whose reply was lost is entitled to the same
    answer anyway -- and to the `created_at` the first write settled.
    """
    subject, store, events = api(tmp_path)
    published(subject)
    first = send(subject, FROM_TEMPLATE_PATH, from_template_body())
    assert first.status == 201 and events == [RUN_ID]

    later = CommandApi(
        store, AdapterRegistry([]), session=CommandSession(PORT, TOKEN),
        budget=PRODUCT_COMMAND_BUDGET, clock=lambda: "2099-01-01T00:00:00Z",
        ids=ids(), publish_run=events.append, providers=(),
        templates=TemplateStore(tmp_path))
    retry = send(later, FROM_TEMPLATE_PATH, from_template_body())
    assert retry.status == 200
    assert retry.payload == first.payload
    assert retry.payload["created_at"] == NOW
    assert events == [RUN_ID], "a retry published a signal"


def test_a_second_plan_for_one_run_is_a_conflict_whichever_road_asks(tmp_path):
    """One run carries one graph, and the template road does not get a second."""
    subject, _store, events = api(tmp_path)
    published(subject)
    assert status_of(subject, FROM_TEMPLATE_PATH, from_template_body()) == 201
    other = send(subject, FROM_TEMPLATE_PATH,
                 from_template_body(graph_id="graph-from-template-002"))
    assert other.status == ERROR_STATUS["record_conflict"]
    assert events == [RUN_ID]


def test_the_same_graph_id_carrying_different_facts_is_a_conflict(tmp_path):
    """Same name, different plan: the retry test's opposite, and its neighbour."""
    subject, _store, events = api(tmp_path)
    published(subject)
    assert status_of(subject, FROM_TEMPLATE_PATH, from_template_body()) == 201
    document = template_body()
    document["revision"] = 2
    document["nodes"][0]["title"] = "Goal, restated"
    published(subject, document)
    differs = send(subject, FROM_TEMPLATE_PATH, from_template_body(revision=2))
    assert differs.status == ERROR_STATUS["record_conflict"]
    assert events == [RUN_ID]


def test_a_revision_this_build_does_not_hold_is_refused_with_no_path(tmp_path):
    """A fact about what this build has, said without naming its disk."""
    subject, store, events = api(tmp_path)
    refused = send(subject, FROM_TEMPLATE_PATH, from_template_body())
    assert refused.status == ERROR_STATUS["service_refused"]
    assert code_of(refused) == "service_refused"
    rendered = json.dumps(refused.payload)
    assert str(tmp_path) not in rendered and "templates" not in rendered
    assert events == [] and not _standing(store)


def test_a_binding_to_an_unreachable_provider_writes_nothing(tmp_path):
    """Availability is a STATE this build resolved, never a name it recognised.

    The refusal names the INSTANCE the caller chose. It does not name the
    adapter, because which product is behind an instance is not the fact and
    putting one in a rendered message is how a surface starts knowing vendors.
    """
    subject, store, events = api(tmp_path, providers=contracts(reachable=()))
    published(subject)
    refused = send(subject, FROM_TEMPLATE_PATH, from_template_body())
    assert refused.status == ERROR_STATUS["service_refused"]
    assert refused.payload["error"]["detail"]["instance_id"] == "claude-dev"
    for word in BOUND:
        assert word not in json.dumps(refused.payload)
    assert events == [] and not _standing(store)


def test_a_provider_this_build_never_heard_of_is_refused_the_same_way(tmp_path):
    """Unreachable and unknown are one rule, in one sentence, by design.

    A caller learns that the instance it named cannot be reached. It does not
    learn whether that is because the transport is missing or because this
    build has no such provider at all -- those are the same fact to a plan.
    """
    subject, store, events = api(tmp_path, providers=contracts(known=("codex",)))
    published(subject)
    refused = send(subject, FROM_TEMPLATE_PATH, from_template_body())
    unreachable = api(tmp_path / "other",
                      providers=contracts(reachable=()))[0]
    published(unreachable)
    other = send(unreachable, FROM_TEMPLATE_PATH, from_template_body())
    assert refused.payload == other.payload
    assert events == [] and not _standing(store)


def test_a_capability_the_bound_adapter_cannot_serve_writes_nothing(tmp_path):
    """Reachable is not servable: the pair door still has the last word."""
    subject, store, events = api(tmp_path, adapters=[])
    published(subject)
    refused = send(subject, FROM_TEMPLATE_PATH, from_template_body())
    assert refused.status in {ERROR_STATUS["capability_unsupported"],
                              ERROR_STATUS["service_refused"]}
    assert events == [] and not _standing(store)


@pytest.mark.parametrize("body,reason", [
    (from_template_body(created_at=NOW), "a caller may not set the clock"),
    (from_template_body(nodes=[]), "a second way to say what the revision says"),
    (from_template_body(revision="1"), "a revision is a number, not a numeral"),
    (from_template_body(revision=0), "a revision starts at one"),
])
def test_the_materialization_document_is_closed(tmp_path, body, reason):
    subject, store, events = api(tmp_path)
    published(subject)
    assert status_of(subject, FROM_TEMPLATE_PATH, body) == \
        ERROR_STATUS["contract_invalid"], reason
    assert events == [] and not _standing(store)


def test_a_binding_the_frozen_configuration_does_not_declare_writes_nothing(tmp_path):
    subject, store, events = api(tmp_path)
    published(subject)
    template = load_template("dalio-v1")
    refused = send(subject, FROM_TEMPLATE_PATH, from_template_body(
        assignments={role: "ghost-dev" for role in template.roles}))
    assert refused.status == ERROR_STATUS["service_refused"]
    assert events == [] and not _standing(store)


def _standing(store):
    return [row for row in store.read(RUN_ID).records
            if row.kind == "graph_definition"]


# --- the relations two racing clients are owed ---


def _race(calls):
    """Run two requests at once and return their outcomes, in no order."""
    with ThreadPoolExecutor(max_workers=2) as pool:
        return [future.result() for future in [pool.submit(call) for call in calls]]


def _outcome(subject, path, body):
    def call():
        try:
            return send(subject, path, body).status
        except Exception as error:  # a refusal travels as an exception
            return getattr(error, "status", None) or type(error).__name__
    return call


def test_two_identical_publications_leave_one_file_and_one_creator(tmp_path):
    """`{201, 200}`, and the exclusive create is what decides which is which."""
    subject, _store, events = api(tmp_path)
    body = template_body()
    results = _race([_outcome(subject, TEMPLATES_PATH, body)] * 2)
    assert sorted(results) == [200, 201]
    store = TemplateStore(tmp_path)
    assert store.revisions("template-dalio") == (1,)
    assert store.load("template-dalio", 1).as_dict() == body
    assert events == []


def test_two_different_publications_of_one_revision_leave_the_winner_untouched(
        tmp_path):
    """`{201, 409}`, and whichever won, the bytes on disk are ITS bytes."""
    subject, _store, _events = api(tmp_path)
    first, second = template_body(), template_body()
    second["nodes"][0]["title"] = "Goal, restated"
    results = _race([_outcome(subject, TEMPLATES_PATH, first),
                     _outcome(subject, TEMPLATES_PATH, second)])
    assert sorted(results) == [201, ERROR_STATUS["record_conflict"]]
    stored = TemplateStore(tmp_path).load("template-dalio", 1).as_dict()
    assert stored in (first, second)
    assert TemplateStore(tmp_path).revisions("template-dalio") == (1,)


def test_two_identical_materializations_leave_one_graph_and_one_signal(tmp_path):
    """`{201, 200}`, one `graph_definition`, and exactly one frame."""
    subject, store, events = api(tmp_path)
    published(subject)
    body = from_template_body()
    results = _race([_outcome(subject, FROM_TEMPLATE_PATH, body)] * 2)
    assert sorted(results) == [200, 201]
    assert len(_standing(store)) == 1
    assert events == [RUN_ID], "a retry published a second signal"


def test_two_different_materializations_leave_one_graph_and_one_conflict(tmp_path):
    """`{201, 409}` -- a run carries one graph however many clients ask."""
    subject, store, events = api(tmp_path)
    published(subject)
    results = _race([
        _outcome(subject, FROM_TEMPLATE_PATH, from_template_body()),
        _outcome(subject, FROM_TEMPLATE_PATH,
                 from_template_body(graph_id="graph-from-template-002"))])
    assert sorted(results) == [201, ERROR_STATUS["record_conflict"]]
    assert len(_standing(store)) == 1
    assert events == [RUN_ID]


def test_a_portal_on_the_template_route_is_a_route_refusal_and_not_a_fault(
        tmp_path):
    """A name whose content lies elsewhere is the caller's answer, not a crash.

    `route_unsafe` is what this product already says when a writable route
    reaches state it cannot account for, and a store that answered
    `store_error` would call a structural refusal a server fault -- a 500 for
    something the server understood perfectly well.

    Found by a sabotage run: the translation existed and nothing exercised it,
    because the mutation that was supposed to guard it named a test about the
    refusal TABLE rather than about this road.
    """
    project = tmp_path / "project"
    (project / "conductor").mkdir(parents=True)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    try:
        (project / "conductor" / "templates").symlink_to(
            elsewhere, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this machine does not permit creating a symbolic link")

    subject, _store, events = api(project)
    refused = send(subject, TEMPLATES_PATH, template_body())
    assert refused.status == ERROR_STATUS["route_unsafe"]
    assert code_of(refused) == "route_unsafe"
    rendered = json.dumps(refused.payload)
    for secret in (str(tmp_path), str(elsewhere), "templates"):
        assert secret not in rendered
    assert not list(elsewhere.iterdir()), "it wrote through the portal anyway"
    assert events == []


def test_a_revision_replaced_after_it_was_judged_never_reaches_the_journal(tmp_path):
    """What is appended is what was JUDGED, or nothing is appended.

    The gates ran on one read of the revision and the transaction appended a
    second, so a revision replaced between them put a plan nothing had judged
    into an immutable journal -- an unservable one, on a route whose contract
    promises zero durable bytes for exactly that fact.

    The seam names no gate on purpose. The file is replaced the moment it is
    READ, so ANY second read at all picks up the tampered bytes, whatever order
    the route judges things in. Two answers are admissible -- a refusal, or the
    snapshot already judged -- and a third is the defect.
    """
    subject, store, events = api(tmp_path)
    assert status_of(subject, TEMPLATES_PATH, template_body()) == 201

    tampered = template_body()
    for node in tampered["nodes"]:
        if node.get("capability") == "dispatch":
            node["capability"] = "ghost-capability"
    # Still a template this CONTRACT accepts: what no adapter serves is that
    # capability, which is the gates' business and not the document's.
    assert GraphTemplate.from_dict(tampered)

    path = TemplateStore(tmp_path).revision_path("template-dalio", 1)
    honest = subject._templates.load

    def swap(template_id, revision):
        loaded = honest(template_id, revision)
        path.unlink()
        path.write_text(json.dumps(tampered), encoding="utf-8", newline="\n")
        return loaded

    subject._templates.load = swap
    answer = send(subject, FROM_TEMPLATE_PATH, from_template_body())
    durable = [row.value for row in store.read(RUN_ID).records
               if row.kind == "graph_definition"]

    if answer.status == 201:
        assert len(durable) == 1
        assert {node.capability for node in durable[0].nodes
                if node.capability} == {"review", "dispatch"}
        assert events == [RUN_ID]
    else:
        assert answer.status >= 400, answer.payload
        assert durable == [] and events == []
