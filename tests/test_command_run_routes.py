"""Opening a run from a workflow, and seeing every run this project holds.

``POST /command/runs`` is the one route on this surface where a browser's
request becomes a run's frozen configuration, so its authority argument is the
whole of what makes the Studio safe to expose: a browser names an instance, a
CONFIGURED provider and at most a model, and there is nowhere in that vocabulary
for an adapter binding of its own, a filesystem path, an argv, an environment
value or a credential. Those are not screened out afterwards; the words do not
exist. The tests below spend that claim rather than restating it -- each
forbidden word is submitted, at the top level and inside a participant, and the
closed key set refuses it.

``GET /command/runs`` is the opposite kind of claim: it stores nothing, derives
every field from the run's own durable records, and lists a run it cannot read
rather than omitting it. A run you cannot see is worse than a run you cannot
read, so a deliberately corrupted journal is planted and the row is asserted.

The document, the API factory and the transport helpers come from the two
modules beside this one, so all three drive the SAME workflow through the same
door. There is deliberately no ``conftest.py`` in this repository.
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
from conductor.command.api_contracts import ERROR_STATUS, NO_PROVIDERS_MESSAGE
from conductor.command.graph_definition import GraphDefinition
from conductor.command.graph_template import GraphTemplate, RunBinding, materialize
from conductor.command.run_store import snapshot_digest
from conductor.command.studio_contracts import CONTROL_MODES, MAX_RUN_PARTICIPANTS
from conductor.command.template_store import TemplateStore

from tests.test_command_workflow_draft import INCOMPLETE, WORKFLOW, a_document
from tests.test_command_workflow_routes import (
    HOST,
    NOW,
    SHIPPED,
    api,
    code_of,
    contracts,
    durable_digest,
    get,
    post,
    post_headers,
)
from tests.test_store import good_lane, write_project

RUN_ID = "run-studio-001"
ROLE = "role-implementer"
INSTANCE = "solo-node"
GATE = "gate-confirm-do"
#: The provider every participant below names. It is a provider id AND the
#: adapter the double registers, which is what a real deployment looks like:
#: the server builds the frozen binding from the provider the browser chose.
PROVIDER = "claude-code"


def a_run(**changes):
    """One request to open a run: exactly the seven caller-owned facts."""
    body = {
        "run_id": RUN_ID,
        "cycle_id": "default-orbit",
        "mode": "confirm",
        "participants": [
            {"instance_id": INSTANCE, "provider_id": PROVIDER, "model": None}],
        "workflow_id": WORKFLOW,
        "revision": 1,
        "assignments": {ROLE: INSTANCE},
    }
    body.update(changes)
    return body


def a_project(tmp_path, **changes):
    """An API whose store already holds revision 1 of the workflow."""
    subject, store, templates, events = api(tmp_path, **changes)
    # 200 when a previous API in this test already published it: the store
    # arbitrates, and identical bytes are the request already satisfied.
    assert post(subject, f"/command/workflows/{WORKFLOW}/revisions",
                {"revision": 1, "document": a_document()}).status in {200, 201}
    events.clear()
    return subject, store, templates, events


def journal_of(store, run_id=RUN_ID):
    """Every durable byte of one run, as one comparable value."""
    root = store.run_path(run_id)
    return {path.name: path.read_bytes()
            for path in sorted(root.rglob("*")) if path.is_file()}


def records_of(store, run_id=RUN_ID):
    return [row.kind for row in store.read(run_id).records]


# --- who may be named, and what this build resolved -----------------------


def test_a_provider_this_build_did_not_resolve_is_refused_by_the_name_asked_for(
        tmp_path):
    """A browser may CHOOSE among configured providers; it may never introduce one.

    The id is the caller's own word echoed back, so nothing about this build's
    roster leaks: a provider that is configured and unavailable and a provider
    nobody configured are refused in one sentence, which is the same rule the
    plan road already spends.
    """
    subject, store, _templates, events = a_project(tmp_path)
    before = durable_digest(tmp_path)
    refused = post(subject, "/command/runs", a_run(participants=[
        {"instance_id": INSTANCE, "provider_id": "ghost-provider",
         "model": None}]))
    assert (refused.status, code_of(refused)) == (
        ERROR_STATUS["service_refused"], "service_refused")
    assert refused.payload["error"]["detail"] == {"provider_id": "ghost-provider"}
    assert not store.run_path(RUN_ID).exists()
    assert durable_digest(tmp_path) == before and events == []

    # Configured-but-unreachable is refused by the same rule and the same
    # sentence, so a caller cannot tell which of the two it met. The roster is
    # NOT empty here -- one other provider is available -- which is what keeps
    # this the per-provider refusal rather than the no-configuration one.
    unreachable, _s, _t, _e = a_project(
        tmp_path / "other", providers=contracts(reachable=("codex",)))
    same = post(unreachable, "/command/runs", a_run())
    assert same.payload["error"]["message"] == (
        f"provider {PROVIDER!r} is not one this build resolved as available")
    assert same.payload["error"]["detail"] == {"provider_id": PROVIDER}


def test_an_empty_roster_is_a_different_situation_and_a_different_instruction(
        tmp_path):
    """Two user situations that must never share one sentence.

    Nobody has written a provider configuration yet, versus a configuration that
    does not carry the id this caller asked for. A person told "provider 'x' is
    not available" when the answer is "there are none at all" goes looking for a
    typo. So the empty roster is answered FIRST and separately, it carries no id
    to name, and it says exactly which file to write.
    """
    empty, store, _templates, events = a_project(tmp_path, providers=())
    fresh = post(empty, "/command/runs", a_run())
    named, _s, _t, _e = a_project(tmp_path / "other")
    unknown = post(named, "/command/runs", a_run(participants=[
        {"instance_id": INSTANCE, "provider_id": "ghost", "model": None}]))

    assert fresh.payload != unknown.payload, (
        "the two situations were answered with one sentence")
    assert fresh.payload["error"]["message"] == NO_PROVIDERS_MESSAGE
    assert fresh.payload["error"]["detail"] == {}
    assert unknown.payload["error"]["message"] != NO_PROVIDERS_MESSAGE
    assert unknown.payload["error"]["detail"] == {"provider_id": "ghost"}
    # The actionable one names the operator's own project-relative file; the
    # other names no file at all, because there is nothing to go and edit.
    assert "conductor/providers.json" in fresh.payload["error"]["message"]
    assert "providers.json" not in unknown.payload["error"]["message"]
    for answer in (fresh, unknown):
        assert str(tmp_path) not in json.dumps(answer.payload)
    assert not store.run_path(RUN_ID).exists() and events == []


def test_the_empty_roster_is_answered_before_any_provider_is_looked_up(tmp_path):
    """Order matters here: the id a caller named must not decide the sentence."""
    empty, _store, _templates, _events = a_project(tmp_path, providers=())
    for provider in (PROVIDER, "ghost", "another-ghost"):
        refused = post(empty, "/command/runs", a_run(participants=[
            {"instance_id": INSTANCE, "provider_id": provider, "model": None}]))
        assert refused.payload["error"]["message"] == NO_PROVIDERS_MESSAGE
        assert refused.payload["error"]["detail"] == {}


def test_a_roster_where_nothing_resolved_gets_the_same_instruction_as_no_roster(
        tmp_path):
    """Deliberate, and pinned so that changing it has to be a decision.

    "Available" is a resolved STATE, so a project whose providers are all
    declared and none reachable has resolved no available provider -- which is
    what the sentence says, word for word. The reader is sent to the same file,
    which is where an unreachable pin is corrected as well as where a missing
    declaration is added, so the instruction is right for both.
    """
    nothing_resolved, _store, _templates, _events = a_project(
        tmp_path, providers=contracts(reachable=()))
    refused = post(nothing_resolved, "/command/runs", a_run())
    assert refused.payload["error"]["message"] == NO_PROVIDERS_MESSAGE
    assert refused.payload["error"]["detail"] == {}


def test_a_binding_this_build_cannot_serve_writes_no_durable_byte(tmp_path):
    """A plan is judged WHOLE before one byte of the run is written.

    The registry holds no adapter at all here, so the plan the revision would
    materialize names work nothing can carry out -- and the run is not created
    either, because a run and its plan are opened in one call and neither
    survives the other's refusal.
    """
    subject, store, _templates, events = a_project(tmp_path, adapters=[])
    before = durable_digest(tmp_path)
    refused = post(subject, "/command/runs", a_run())
    assert refused.status in {ERROR_STATUS["capability_unsupported"],
                              ERROR_STATUS["service_refused"]}
    assert not store.run_path(RUN_ID).exists()
    assert durable_digest(tmp_path) == before and events == []


def test_a_revision_this_build_does_not_hold_is_refused_and_creates_nothing(
        tmp_path):
    subject, store, _templates, events = a_project(tmp_path)
    before = durable_digest(tmp_path)
    refused = post(subject, "/command/runs", a_run(revision=7))
    assert (refused.status, code_of(refused)) == (
        ERROR_STATUS["service_refused"], "service_refused")
    assert refused.payload["error"]["detail"] == {
        "template_id": WORKFLOW, "revision": 7}
    assert not store.run_path(RUN_ID).exists()
    assert durable_digest(tmp_path) == before and events == []


# --- the vocabulary a browser may speak ------------------------------------


@pytest.mark.parametrize("word", [
    "adapter", "adapter_id", "executable", "argv", "env", "environment",
    "path", "cwd", "token", "api_key", "config", "instances", "graph",
])
def test_the_run_request_has_no_word_for_a_binding_a_path_or_a_credential(
        tmp_path, word):
    """Not screened out afterwards -- the key set is closed, so it cannot be said.

    Submitted at BOTH levels, because a closed envelope with an open participant
    row would be a vocabulary with a hole in exactly the place that decides what
    the server spawns.
    """
    subject, store, _templates, events = a_project(tmp_path)
    before = durable_digest(tmp_path)

    top = post(subject, "/command/runs", a_run(**{word: "anything at all"}))
    inner = post(subject, "/command/runs", a_run(participants=[{
        "instance_id": INSTANCE, "provider_id": PROVIDER, "model": None,
        word: "anything at all"}]))
    for refused in (top, inner):
        assert (refused.status, code_of(refused)) == (
            ERROR_STATUS["contract_invalid"], "contract_invalid"), word
    assert not store.run_path(RUN_ID).exists()
    assert durable_digest(tmp_path) == before and events == []


@pytest.mark.parametrize("mode", [
    "godmode", "CONFIRM", "auto", "", "observe ", None, 1, True, ["confirm"]])
def test_a_mode_outside_the_closed_vocabulary_is_refused(tmp_path, mode):
    """There is no spelling of authority a browser can reach that the durable
    envelope cannot hold."""
    subject, store, _templates, events = a_project(tmp_path)
    refused = post(subject, "/command/runs", a_run(mode=mode))
    assert (refused.status, code_of(refused)) == (
        ERROR_STATUS["contract_invalid"], "contract_invalid")
    assert not store.run_path(RUN_ID).exists() and events == []


@pytest.mark.parametrize("mode", sorted(CONTROL_MODES))
def test_every_mode_the_contract_names_opens_a_run_that_records_it(tmp_path, mode):
    """The other direction, derived from the enum rather than listed.

    A mode added to ``ControlMode`` and refused here would be a closed
    vocabulary this API had quietly narrowed.
    """
    subject, store, _templates, _events = a_project(tmp_path)
    opened = post(subject, "/command/runs",
                  a_run(run_id=f"run-{mode}", mode=mode))
    assert opened.status == 201, opened.payload
    assert opened.payload["run"]["mode"] == mode
    assert store.read(f"run-{mode}").envelope.mode.value == mode


@pytest.mark.parametrize("body,reason", [
    (a_run(workflow_id=None), "a revision of nothing"),
    (a_run(revision=None), "a workflow with no revision"),
    (a_run(revision="1"), "a revision is a number, not a numeral"),
    (a_run(revision=0), "a revision starts at one"),
    (a_run(participants=[]), "a run binds at least one participant"),
    (a_run(participants=[
        {"instance_id": INSTANCE, "provider_id": PROVIDER, "model": None},
        {"instance_id": INSTANCE, "provider_id": PROVIDER, "model": None}]),
     "one instance is named once"),
    (a_run(assignments={ROLE: INSTANCE}, workflow_id=None, revision=None),
     "a binding for a workflow that was never named"),
    (a_run(participants=[
        {"instance_id": INSTANCE, "provider_id": PROVIDER, "model": ""}]),
     "a model is an id or it is absent"),
])
def test_the_run_document_is_closed_to_what_it_cannot_mean(tmp_path, body, reason):
    subject, store, _templates, events = a_project(tmp_path)
    refused = post(subject, "/command/runs", body)
    assert (refused.status, code_of(refused)) == (
        ERROR_STATUS["contract_invalid"], "contract_invalid"), reason
    assert not store.run_path(RUN_ID).exists() and events == []


def test_a_run_may_not_bind_more_participants_than_a_template_can_have_roles(
        tmp_path):
    subject, _store, _templates, _events = a_project(tmp_path)
    crowd = [{"instance_id": f"instance-{index}", "provider_id": PROVIDER,
              "model": None} for index in range(MAX_RUN_PARTICIPANTS + 1)]
    assert post(subject, "/command/runs", a_run(participants=crowd)).status == \
        ERROR_STATUS["contract_invalid"]


# --- what one call writes ---------------------------------------------------


def test_a_run_named_with_a_revision_is_given_that_revisions_plan_in_one_call(
        tmp_path):
    """One run, one graph, materialized from THAT revision by the one constructor.

    The record is compared against what ``materialize`` produces from the stored
    revision, the server-built snapshot and the caller's binding -- so what the
    route answered is what the production door builds, not a document this test
    described.
    """
    subject, store, templates, events = a_project(tmp_path)
    opened = post(subject, "/command/runs", a_run())
    assert opened.status == 201, opened.payload

    assert opened.payload["config"] == {
        "cycle": {"id": "default-orbit"},
        "instances": [{"id": INSTANCE, "adapter": PROVIDER}],
        # The plan this run froze itself to follow, inside the document
        # `config_digest` is taken over, so provenance and digest are one fact.
        "workflow": {"id": WORKFLOW, "revision": 1}}
    assert opened.payload["run"]["config_digest"] == \
        snapshot_digest(opened.payload["config"])

    recovered = store.read(RUN_ID)
    stored = [row.value for row in recovered.records
              if row.kind == "graph_definition"]
    assert len(stored) == 1, "a run carries exactly one plan"
    assert stored[0].as_dict() == opened.payload["graph"]
    expected = materialize(
        templates.load(WORKFLOW, 1), _binding(), opened.payload["config"],
        graph_id=stored[0].graph_id, run_id=RUN_ID, created_at=NOW)
    assert stored[0] == expected
    assert GraphDefinition.from_dict(opened.payload["graph"]) == expected

    # A plan names instances; a template names roles, and the record says so.
    rendered = json.dumps(opened.payload["graph"])
    assert '"role_id"' not in rendered and '"instance_id"' in rendered
    assert events == [RUN_ID]


def _binding():
    return RunBinding.from_dict({"assignments": {ROLE: INSTANCE}})


def _second_read_answers_another_revision(subject, templates):
    """Make the store answer the judged revision once, another one for ever.

    The substitution has to be a document the store could really hold, so it is
    the judged revision's own bytes with one step's title and work item changed
    -- a stored revision carries the identity a draft has not got yet, and a
    replacement built from the draft shape would be refused for the wrong
    reason. Answers with the judged revision and the live list of reads, so a
    caller can assert on the plan AND on how many times the route asked.
    """
    judged = templates.load(WORKFLOW, 1)
    later = json.loads(json.dumps(judged.as_dict()))
    for node in later["nodes"]:
        if node["node_id"] == "do":
            node["title"] = "Do work nobody approved"
            node["arguments"] = dict(node["arguments"], work_item_id="work-999")
    replaced = GraphTemplate.from_dict(later)
    assert replaced.as_dict() != judged.as_dict(), "the two reads are one document"

    reads = []

    def the_judged_one_then_another(workflow_id, revision):
        reads.append((workflow_id, revision))
        return judged if len(reads) == 1 else replaced

    subject._templates.load = the_judged_one_then_another
    return judged, reads


def test_a_revision_replaced_after_it_was_judged_is_not_the_one_the_run_follows(
        tmp_path):
    """What was JUDGED is what is appended -- on the road a browser actually takes.

    Every gate this route runs -- the roster, the revision, the plan the bound
    adapters must be able to serve -- is spent on ONE read of the revision. A
    second read inside the transaction would let a revision replaced between
    the two put a plan nothing had judged into a journal that is immutable
    afterwards: work no operator approved, or a binding no adapter can carry
    out, standing as this run's law with no route to correct it. Publishing a
    revision and building a graph from a template both hold this line already;
    opening a run is the road the Studio itself uses and it held nothing.

    The store is made to answer the judged revision once and a DIFFERENT
    publishable one for ever after, so a second read cannot go unseen. Both
    proofs the substitution offers are taken, and the CONTENT one is asserted
    first: a call count says only that the route asked twice, while the plan's
    own steps say which answer this run is now bound to, and that is the fact a
    person loses.
    """
    subject, store, templates, events = a_project(tmp_path)
    judged, reads = _second_read_answers_another_revision(subject, templates)
    opened = post(subject, "/command/runs", a_run())
    assert opened.status == 201, opened.payload

    durable = [row.value for row in store.read(RUN_ID).records
               if row.kind == "graph_definition"]
    assert len(durable) == 1, "a run carries exactly one plan"
    steps = [(node.title, node.arguments.get("work_item_id"))
             for node in durable[0].nodes]
    assert steps == [(node["title"], node.get("arguments", {}).get("work_item_id"))
                     for node in a_document()["nodes"]], (
        "the run follows a plan built from a revision nothing judged")

    expected = materialize(
        judged, _binding(), opened.payload["config"],
        graph_id=durable[0].graph_id, run_id=RUN_ID, created_at=NOW)
    assert durable[0] == expected
    assert GraphDefinition.from_dict(opened.payload["graph"]) == expected
    assert reads == [(WORKFLOW, 1)], (
        "the revision was read again between the gate and the write")
    assert events == [RUN_ID]


def test_a_run_that_names_no_workflow_is_opened_with_no_plan_at_all(tmp_path):
    """Half a reference is refused; NEITHER half is a run with no plan yet."""
    subject, store, _templates, events = a_project(tmp_path)
    opened = post(subject, "/command/runs",
                  a_run(workflow_id=None, revision=None, assignments={}))
    assert opened.status == 201 and opened.payload["graph"] is None
    assert records_of(store) == []
    assert events == [RUN_ID]


def test_an_identical_repeat_answers_the_standing_run_and_moves_no_byte(tmp_path):
    """A client whose reply was lost is entitled to the same answer.

    The second API starts with a different clock, a different id generator and
    NO providers at all: what it is asking about is already durable, so the
    answer may not depend on what this process can reach today.
    """
    subject, store, _templates, events = a_project(tmp_path)
    first = post(subject, "/command/runs", a_run())
    assert first.status == 201 and events == [RUN_ID]
    standing = journal_of(store)

    later, _store, _templates, more = a_project(
        tmp_path, providers=(), clock=lambda: "2099-01-01T00:00:00Z")
    retry = later.handle(
        "POST", "/command/runs", post_headers(a_run()),
        json.dumps(a_run(), separators=(",", ":")).encode("utf-8"))
    assert retry.status == 200
    assert retry.payload == first.payload
    assert retry.payload["run"]["created_at"] == NOW
    assert journal_of(store) == standing
    assert more == [], "a retry published a signal"


def test_a_different_configuration_under_one_run_id_is_a_conflict(tmp_path):
    """A run identity is written once, so a second open IS it or contradicts it."""
    subject, store, _templates, events = a_project(tmp_path)
    assert post(subject, "/command/runs", a_run()).status == 201
    standing = journal_of(store)

    for changed in (a_run(cycle_id="another-orbit"),
                    a_run(mode="observe"),
                    a_run(participants=[{"instance_id": INSTANCE,
                                         "provider_id": "codex",
                                         "model": None}]),
                    a_run(participants=[{"instance_id": INSTANCE,
                                         "provider_id": PROVIDER,
                                         "model": "some-model"}])):
        refused = post(subject, "/command/runs", changed)
        assert (refused.status, code_of(refused)) == (
            ERROR_STATUS["record_conflict"], "record_conflict"), changed
    assert journal_of(store) == standing
    assert events == [RUN_ID]


def test_two_participants_in_either_order_are_one_request(tmp_path):
    """The snapshot is sorted by instance id, so an order is not a change."""
    subject, store, _templates, events = a_project(tmp_path)
    rows = [{"instance_id": INSTANCE, "provider_id": PROVIDER, "model": None},
            {"instance_id": "second-node", "provider_id": "codex",
             "model": "a-model"}]
    first = post(subject, "/command/runs", a_run(
        participants=rows, workflow_id=None, revision=None, assignments={}))
    assert first.status == 201
    again = post(subject, "/command/runs", a_run(
        participants=list(reversed(rows)), workflow_id=None, revision=None,
        assignments={}))
    assert (again.status, again.payload) == (200, first.payload)
    assert [row["id"] for row in first.payload["config"]["instances"]] == \
        ["second-node", INSTANCE]
    assert events == [RUN_ID]


def test_opening_a_run_announces_it_exactly_once(tmp_path):
    """A frame is a claim that a run moved; creating one is such a move.

    The retry is not, the refusal is not, and a workflow publish is not -- so
    all four are driven and the whole list of frames is asserted.
    """
    subject, _store, _templates, events = a_project(tmp_path)
    post(subject, f"/command/workflows/{WORKFLOW}/draft", INCOMPLETE["a cycle"])
    post(subject, "/command/runs", a_run(mode="nonsense"))
    assert post(subject, "/command/runs", a_run()).status == 201
    assert post(subject, "/command/runs", a_run()).status == 200
    get(subject, "/command/runs")
    assert events == [RUN_ID]


# --- seeing every run this project holds ------------------------------------


def test_the_listing_names_every_run_and_derives_each_field_from_the_records(
        tmp_path):
    """Nothing here is stored, so every field is asserted against its source."""
    subject, store, _templates, _events = a_project(tmp_path)
    assert post(subject, "/command/runs", a_run()).status == 201
    assert post(subject, "/command/runs", a_run(
        run_id="run-studio-002", mode="observe", workflow_id=None,
        revision=None, assignments={})).status == 201

    listed = get(subject, "/command/runs")
    assert listed.status == 200
    rows = {row["run_id"]: row for row in listed.payload["runs"]}
    assert sorted(rows) == ["run-studio-001", "run-studio-002"]

    recovered = store.read(RUN_ID)
    definition = next(row.value for row in recovered.records
                      if row.kind == "graph_definition")
    assert rows[RUN_ID] == {
        "run_id": RUN_ID, "unreadable": False,
        "cycle_id": recovered.envelope.cycle_id,
        "created_at": recovered.envelope.created_at,
        "mode": recovered.envelope.mode.value,
        "envelope_status": recovered.envelope.status,
        "graph_id": definition.graph_id,
        "undecided_gates": 1, "open_actions": 0, "last_outcome": None,
        "workflow_id": WORKFLOW, "revision": 1}
    # A run with no plan has no gates to be undecided about, and says 0 rather
    # than null: null is what an unreadable run answers. It also froze no
    # workflow reference, so both halves of the provenance are null together.
    assert rows["run-studio-002"]["graph_id"] is None
    assert rows["run-studio-002"]["workflow_id"] is None
    assert rows["run-studio-002"]["revision"] is None
    assert rows["run-studio-002"]["undecided_gates"] == 0
    assert rows["run-studio-002"]["mode"] == "observe"
    # The roster travels beside the runs, because a user with no runs at all
    # can reach this route and can never reach a per-run one.
    assert [row["provider_id"] for row in listed.payload["providers"]] == \
        [PROVIDER, "codex"]


def test_the_creation_time_word_is_named_so_no_reader_takes_it_for_a_position(
        tmp_path):
    """A ``RunEnvelope`` is immutable, so its status is what the run was OPENED
    as and never where it now stands. The key is spelled with ``envelope_`` in
    front of it for exactly that reason, and there is deliberately no derived
    overall phase word: the journal does not carry one, and a word invented
    here would be a guess a reader trusts."""
    subject, store, _templates, _events = a_project(tmp_path)
    assert post(subject, "/command/runs", a_run()).status == 201
    row = get(subject, "/command/runs").payload["runs"][0]

    assert row["envelope_status"] == store.read(RUN_ID).envelope.status
    assert "status" not in row and "phase" not in row
    assert set(row) == {
        "run_id", "unreadable", "cycle_id", "created_at", "mode",
        "envelope_status", "graph_id", "undecided_gates", "open_actions",
        "last_outcome", "workflow_id", "revision"}


def test_a_run_whose_journal_does_not_replay_is_listed_with_its_own_marker(
        tmp_path):
    """A run you cannot see is worse than a run you cannot read.

    The corruption is planted in the durable journal itself, so what is
    exercised is the real replay refusal rather than a patched reader -- and the
    healthy run beside it keeps every derived field, which is the half that
    proves the listing did not simply give up.
    """
    subject, store, _templates, _events = a_project(tmp_path)
    assert post(subject, "/command/runs", a_run()).status == 201
    assert post(subject, "/command/runs", a_run(
        run_id="run-corrupt", workflow_id=None, revision=None,
        assignments={})).status == 201
    (store.run_path("run-corrupt") / "records.jsonl").write_text(
        "this is not a durable record\n", encoding="utf-8", newline="\n")

    rows = {row["run_id"]: row
            for row in get(subject, "/command/runs").payload["runs"]}
    assert sorted(rows) == ["run-corrupt", RUN_ID]
    assert rows["run-corrupt"] == {
        "run_id": "run-corrupt", "unreadable": True, "cycle_id": None,
        "created_at": None, "mode": None, "envelope_status": None,
        "graph_id": None, "undecided_gates": None, "open_actions": None,
        "last_outcome": None, "workflow_id": None, "revision": None}
    assert rows[RUN_ID]["unreadable"] is False
    assert rows[RUN_ID]["graph_id"] is not None


def test_a_name_that_is_not_a_run_id_is_not_a_run(tmp_path):
    """The directories ARE the record, so a name this store could never open
    names no run -- and a half-built staging directory is one of those."""
    subject, store, _templates, _events = a_project(tmp_path)
    assert post(subject, "/command/runs", a_run()).status == 201
    (store.runs_root / ".run-half-built.tmp").mkdir()
    (store.runs_root / "has space").mkdir()
    (store.runs_root / "loose.txt").write_text("x", encoding="utf-8",
                                               newline="\n")
    assert [row["run_id"] for row in
            get(subject, "/command/runs").payload["runs"]] == [RUN_ID]


def test_a_decision_moves_the_derived_gate_count_and_nothing_else(tmp_path):
    """The derived fields come from the JOURNAL, so a durable act must move them.

    A listing computed from anything else would report the same number after a
    decision landed, which is the failure this claim exists to catch.
    """
    subject, store, _templates, _events = a_project(tmp_path)
    assert post(subject, "/command/runs", a_run()).status == 201
    assert get(subject, "/command/runs").payload["runs"][0][
        "undecided_gates"] == 1

    decided = post(subject, f"/command/runs/{RUN_ID}/decisions", {
        "receipt_id": "decision-001", "gate_id": GATE, "action": "approve",
        "actor": "release-owner", "reason": "Reviewed the durable plan.",
        "scope_refs": ["src"], "evidence_refs": [], "supersedes": None})
    assert decided.status == 201, decided.payload
    assert "decision" in records_of(store)

    row = get(subject, "/command/runs").payload["runs"][0]
    assert row["undecided_gates"] == 0
    assert row["open_actions"] == 0 and row["last_outcome"] is None


def test_listing_runs_moves_no_durable_byte(tmp_path):
    """A read repairs nothing either: the replay is ``read``, not ``recover``."""
    subject, store, _templates, events = a_project(tmp_path)
    assert post(subject, "/command/runs", a_run()).status == 201
    assert post(subject, "/command/runs", a_run(
        run_id="run-corrupt", workflow_id=None, revision=None,
        assignments={})).status == 201
    (store.run_path("run-corrupt") / "records.jsonl").write_text(
        "not a record\n", encoding="utf-8", newline="\n")
    events.clear()

    before = durable_digest(tmp_path)
    for _repeat in range(3):
        assert get(subject, "/command/runs").status == 200
        assert subject.handle(
            "GET", f"/command/runs/{RUN_ID}", (("Host", HOST),)).status == 200
    assert durable_digest(tmp_path) == before and events == []


def test_a_project_with_no_runs_answers_an_empty_list_and_the_roster(tmp_path):
    """The state every project starts in, and it is not a refusal.

    A person with no runs at all can reach this route and can never reach a
    per-run one, which is why the provider roster travels here.
    """
    subject, _store, _templates, _events = api(tmp_path)
    listed = get(subject, "/command/runs")
    assert listed.status == 200 and listed.payload["runs"] == []
    assert [row["provider_id"] for row in listed.payload["providers"]] == \
        [PROVIDER, "codex"]
    assert TemplateStore(tmp_path).workflows() == ()


# --- the same road over a real loopback socket ------------------------------
#
# Every test above calls `CommandApi` directly, which proves the route
# authority and nothing about whether a browser can reach it: a route that
# exists in the allowlist and is unreachable over HTTP is a route the table
# advertises and the server answers `route_not_found` for. So the last claim in
# this file is driven the way a Cockpit would drive it -- a real server, a real
# socket, the CSRF token the session route handed out, and a provider the
# factory resolved from an executable pinned on this disk.


def pinned(tmp_path):
    """One provider config whose executable really is on this disk.

    The factory stats an operator's ABSOLUTE pin and nothing else, so a file
    that exists is the whole difference between a provider this build can reach
    and one it cannot.
    """
    executable = tmp_path / "codex-executable"
    executable.write_text("", encoding="utf-8", newline="\n")
    return [ProviderConfig(provider_id="codex",
                           executable=str(executable.resolve()),
                           protocol=CODEX_PROTOCOL)]


@contextmanager
def a_served_project(tmp_path):
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    srv = server.build(root, port=0, providers=pinned(tmp_path),
                       clock=lambda: NOW)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        status, session = request(base, "GET", "/command/session")
        assert status == 200
        yield srv, base, session["csrf_token"]
    finally:
        srv.shutdown()
        srv.server_close()


def request(base, method, path, *, token=None, body=None):
    """One real HTTP call; a refusal comes back as a status, not an exception."""
    host = base.removeprefix("http://")
    headers = {"Host": host}
    data = None
    if body is not None:
        data = json.dumps(body, separators=(",", ":")).encode("utf-8")
        headers.update({"Origin": f"http://{host}", "X-Conduct-CSRF": token,
                        "Content-Type": "application/json",
                        "Content-Length": str(len(data))})
    call = urllib.request.Request(base + path, data=data, headers=headers,
                                  method=method)
    try:
        with urllib.request.urlopen(call, timeout=10) as answer:
            return answer.status, json.loads(answer.read() or b"null")
    except urllib.error.HTTPError as refused:
        return refused.code, json.loads(refused.read() or b"null")


def test_a_browser_can_draw_a_workflow_and_open_a_run_from_it_over_a_socket(
        tmp_path):
    """The whole Studio road on the wire a browser really takes.

    The provider resolved through the factory from a pinned executable, so the
    availability the run route consulted is the one this build established
    rather than a descriptor a test made up.
    """
    with a_served_project(tmp_path) as (srv, base, token):
        listed = request(base, "GET", "/command/workflows")
        assert listed[0] == 200 and listed[1]["workflows"] == []
        assert [row["starter_id"] for row in listed[1]["starters"]] == \
            sorted(SHIPPED)

        assert request(base, "POST", f"/command/workflows/{WORKFLOW}/draft",
                       token=token, body=a_document())[0] == 201
        # A publish names WHICH draft it reviewed, and a browser gets that
        # digest the only way there is: off the read it drew the review from.
        read = request(base, "GET", f"/command/workflows/{WORKFLOW}")[1]
        status, document = request(
            base, "POST", f"/command/workflows/{WORKFLOW}/revisions",
            token=token, body={"revision": 1,
                               "reviewed_digest": read["draft"]["digest"]})
        assert status == 201, document
        assert request(base, "GET", f"/command/workflows/{WORKFLOW}/revisions/1"
                       ) == (200, {"workflow_id": WORKFLOW, "revision": 1,
                                   "document": document})

        status, opened = request(base, "POST", "/command/runs", token=token, body={
            "run_id": "run-over-the-socket", "cycle_id": "default-orbit",
            "mode": "confirm",
            "participants": [{"instance_id": INSTANCE, "provider_id": "codex",
                              "model": None}],
            "workflow_id": WORKFLOW, "revision": 1,
            "assignments": {ROLE: INSTANCE}})
        assert status == 201, opened
        assert opened["graph"]["run_id"] == "run-over-the-socket"
        assert [row.provider_id for row in srv.command_providers
                if row.available] == ["codex"]

        status, runs = request(base, "GET", "/command/runs")
        assert status == 200
        assert [row["run_id"] for row in runs["runs"]] == ["run-over-the-socket"]
        assert runs["runs"][0]["unreadable"] is False

        # And an unfinished drawing is refused the publish, on the wire.
        assert request(base, "POST", "/command/workflows/half-drawn/draft",
                       token=token, body=INCOMPLETE["a dangling edge"])[0] == 201
        # The echo is supplied so the refusal this reaches is the DRAWING's own
        # and not the earlier one for naming no reviewed draft.
        half = request(base, "GET", "/command/workflows/half-drawn")[1]
        status, refused = request(
            base, "POST", "/command/workflows/half-drawn/revisions",
            token=token, body={"revision": 1,
                               "reviewed_digest": half["draft"]["digest"]})
        assert status == ERROR_STATUS["contract_invalid"]
        assert refused["diagnostics"][0]["code"] == "template_refused"
