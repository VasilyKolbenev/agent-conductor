"""`GET` and `POST /command/workflows/<workflow_id>/flow`: the desk's one door for cycles.

The route reads a workflow as a flow and writes one: the draft under the same optimistic check as
`/draft`, a revision under the same lock as `/revisions`. What is proved here is the road itself;
the rules, the compiler and the budget it calls are held by their own files, and the transport
claims every route inherits are held where the table is (`test_command_studio_transport`).
"""
import json

import pytest

from conductor.command import flow_routes, graph_template
from conductor.command.adapters.process import ProcessRunner
from conductor.command.api_contracts import ERROR_STATUS
from conductor.command.contracts import canonical_json
from conductor.command.project_cycle import ProjectCycleStore
from conductor.command.workflow_draft import DraftRefused, draft_digest
from conductor.command.workflow_flow import compile_flow, import_template
from tests.test_command_run_routes import INSTANCE, PROVIDER, RUN_ID, a_run, journal_of
from tests.test_command_workflow_flow import chain, fixture_flow, review, step
from tests.test_command_workflow_routes import (
    NOW, api, code_of, durable_digest, get, post, seeded)

WORKFLOW_ID = "cycle-0a1b2c3d"


def flow_path(workflow_id=WORKFLOW_ID):
    return f"/command/workflows/{workflow_id}/flow"


def good():
    """Two steps and a human answer: publishable, one role, no checker to bind."""
    return chain(review("plan"), step("result", "human"))


def better():
    return chain(review("plan"), review("ideas", role_id="role-reviewer"), step("result", "human"))


def broken():
    return chain(review("plan"), step("do", "agent"), step("result", "human"))


def expecting(subject, workflow_id=WORKFLOW_ID):
    """What a client says about the draft it read: its digest, or that it read none."""
    digest = get(subject, flow_path(workflow_id)).payload["draft_digest"]
    return {"expected_absent": True} if digest is None else {"expected_digest": digest}


def write(subject, flow, *, workflow_id=WORKFLOW_ID, publish=None, source=None, **more):
    body = {"source": source or {"flow": flow}, "publish_revision": publish,
            **expecting(subject, workflow_id), **more}
    return post(subject, flow_path(workflow_id), body)


def revisions_on_disk(templates, workflow_id=WORKFLOW_ID):
    return list(templates.revisions(workflow_id))


def test_get_flow_of_an_unknown_workflow_answers_source_none(tmp_path):
    subject, *_ = api(tmp_path)
    answer = get(subject, flow_path())
    assert answer.status == 200
    assert answer.payload == {
        "workflow_id": WORKFLOW_ID, "source": "none", "draft_digest": None, "flow": None,
        "revision_flow": None, "diagnostics": [], "publishable": False, "budget": None,
        "latest_revision": None, "next_revision": 1, "published": None}
    assert list(answer.payload) == [
        "workflow_id", "source", "draft_digest", "flow", "revision_flow", "diagnostics",
        "publishable", "budget", "latest_revision", "next_revision", "published"]


def test_post_flow_saves_a_draft_under_the_draft_routes_expectation(tmp_path):
    subject, _store, templates, events = api(tmp_path)
    created = write(subject, good())
    assert created.status == 201 and created.payload["source"] == "draft"
    assert created.payload["flow"] == good() and created.payload["published"] is None
    stored = templates.load_draft(WORKFLOW_ID).settled()
    assert created.payload["draft_digest"] == draft_digest(stored)
    assert created.payload["budget"]["clean"]["actions"] == 1
    assert write(subject, good()).status == 200, "the same flow again is nothing new"
    # The digest this route hands out is the one `/draft` expects back.
    resaved = post(subject, f"/command/workflows/{WORKFLOW_ID}/draft",
                   {"document": stored, "expected_digest": created.payload["draft_digest"]})
    assert resaved.status == 200
    assert events == []


def test_a_write_names_the_draft_it_read_and_a_stale_or_wrong_claim_is_a_draft_conflict(tmp_path):
    subject, *_ = api(tmp_path)
    first = write(subject, good())
    stale = first.payload["draft_digest"]
    assert write(subject, better()).status == 200
    conflicts = [
        post(subject, flow_path(), {"source": {"flow": good()}, "expected_digest": stale}),
        post(subject, flow_path(), {"source": {"flow": good()}, "expected_absent": True}),
        post(subject, flow_path("cycle-fresh1"), {
            "source": {"flow": good()}, "expected_digest": stale})]
    assert [(row.status, code_of(row)) for row in conflicts] == [
        (ERROR_STATUS["draft_conflict"], "draft_conflict")] * 3


def test_a_write_needs_exactly_one_expectation_and_a_closed_body(tmp_path):
    subject, *_ = api(tmp_path)
    digest = "sha256:" + "0" * 64
    bodies = [
        {}, {"source": {"flow": good()}},
        {"source": {"flow": good()}, "expected_absent": True, "expected_digest": digest},
        {"source": {"flow": good()}, "expected_absent": False},
        {"source": {"flow": good()}, "expected_digest": "not a digest"},
        {"source": {"flow": good()}, "expected_absent": True, "extra": 1},
        {"source": {"flow": good(), "starter_id": "dalio-v5"}, "expected_absent": True},
        {"source": {"flow": "text"}, "expected_absent": True},
        {"source": {"copy_of": {"workflow_id": "w"}}, "expected_absent": True},
        {"source": {"copy_of": {"workflow_id": "w", "revision": 0}}, "expected_absent": True},
        {"source": {"flow": good()}, "expected_absent": True, "publish_revision": 0},
        {"source": {"flow": good()}, "expected_absent": True, "publish_revision": True},
        {"source": {"flow": good()}, "expected_absent": True, "binding": ["role"]},
        {"source": {"flow": good()}, "expected_absent": True, "binding": {"role x": "p"}}]
    for body in bodies:
        refused = post(subject, flow_path(), body)
        assert (refused.status, code_of(refused)) == (
            ERROR_STATUS["contract_invalid"], "contract_invalid"), body


def test_a_flow_the_form_refuses_is_contract_invalid_with_a_row_and_saves_nothing(tmp_path):
    subject, _store, _templates, events = seeded(tmp_path)
    before = durable_digest(tmp_path)
    flow = good()
    flow["steps"][0]["bogus"] = 1
    refused = write(subject, flow)
    assert (refused.status, code_of(refused)) == (422, "contract_invalid")
    assert refused.payload["diagnostics"] == [{
        "code": "flow_invalid", "severity": "error", "at": {"step_id": "plan"},
        "params": {"path": "flow.steps[0].bogus"}}]
    assert events == [] and durable_digest(tmp_path) == before


def test_a_flow_the_core_refuses_is_contract_invalid_with_rows_and_saves_nothing(tmp_path):
    subject, _store, _templates, _events = seeded(tmp_path)
    before = durable_digest(tmp_path)
    flow = good()
    flow["steps"][0]["role_id"] = "not an id!"
    refused = write(subject, flow)
    assert (refused.status, code_of(refused)) == (422, "contract_invalid")
    assert {"code": "id_invalid", "severity": "error", "at": {"step_id": "plan"},
            "params": {"field": "role_id"}} in refused.payload["diagnostics"]
    assert durable_digest(tmp_path) == before


def test_a_flow_with_rule_errors_is_kept_as_a_draft_and_its_rows_are_shown(tmp_path):
    subject, *_ = api(tmp_path)
    saved = write(subject, broken())
    assert saved.status == 201
    codes = [row["code"] for row in saved.payload["diagnostics"]]
    assert "dispatch_without_checker" in codes
    assert saved.payload["publishable"] is False


def test_publish_with_an_error_row_is_contract_invalid_with_diagnostics(tmp_path):
    subject, _store, templates, _events = api(tmp_path)
    refused = write(subject, broken(), publish=1)
    assert (refused.status, code_of(refused)) == (422, "contract_invalid")
    assert "dispatch_without_checker" in [row["code"] for row in refused.payload["diagnostics"]]
    assert revisions_on_disk(templates) == []
    assert templates.load_draft(WORKFLOW_ID) is None, "a refused publication saves no draft"


def test_a_publication_refused_for_error_rows_leaves_the_clients_expectation_valid(tmp_path):
    subject, *_ = api(tmp_path)
    held = expecting(subject)
    refused = post(subject, flow_path(), {
        "source": {"flow": broken()}, "publish_revision": 1, **held})
    assert (refused.status, code_of(refused)) == (422, "contract_invalid")
    # The client read no draft and was refused; what it held is still what stands, so the
    # next write with the same expectation is a save, never a conflict with itself.
    retried = post(subject, flow_path(), {"source": {"flow": good()}, **held})
    assert retried.status == 201 and retried.payload["source"] == "draft"


def test_a_candidate_the_constructor_refuses_is_refused_before_a_draft_is_saved(
        tmp_path, monkeypatch):
    subject, _store, templates, _events = api(tmp_path)
    row = {"code": "template_refused", "severity": "error", "at": None, "params": {}}

    def refusing(document, *, workflow_id, revision):
        raise DraftRefused((row,))

    monkeypatch.setattr(flow_routes, "publish_candidate", refusing)
    refused = write(subject, good(), publish=1)
    assert (refused.status, code_of(refused)) == (422, "contract_invalid")
    assert refused.payload["diagnostics"] == [row]
    assert templates.load_draft(WORKFLOW_ID) is None
    assert revisions_on_disk(templates) == []


def test_publish_writes_the_revision_and_takes_the_draft_away(tmp_path):
    subject, _store, templates, events = api(tmp_path)
    published = write(subject, good(), publish=1)
    assert published.status == 201
    assert published.payload["published"] == {"revision": 1, "created": True}
    assert published.payload["source"] == "published" and published.payload["draft_digest"] is None
    assert (published.payload["latest_revision"], published.payload["next_revision"]) == (1, 2)
    assert published.payload["flow"] == published.payload["revision_flow"] == good()
    assert templates.load_draft(WORKFLOW_ID) is None
    expected = {**compile_flow(good()), "template_id": WORKFLOW_ID, "revision": 1}
    assert canonical_json(templates.load(WORKFLOW_ID, 1).as_dict()) == canonical_json(
        graph_template.GraphTemplate.from_dict(expected).as_dict())
    assert events == []


def test_publishing_the_latest_document_again_answers_200_not_created(tmp_path):
    subject, _store, templates, _events = api(tmp_path)
    assert write(subject, good(), publish=1).status == 201
    for number in (2, 1):
        again = write(subject, good(), publish=number)
        assert again.status == 200
        assert again.payload["published"] == {"revision": 1, "created": False}
        assert templates.load_draft(WORKFLOW_ID) is None
    assert revisions_on_disk(templates) == [1]


def test_a_change_publishes_the_next_revision_and_leaves_the_older_one_alone(tmp_path):
    subject, _store, templates, _events = api(tmp_path)
    assert write(subject, good(), publish=1).status == 201
    first = templates.revision_path(WORKFLOW_ID, 1).read_bytes()
    second = write(subject, better(), publish=2)
    assert second.status == 201 and second.payload["published"] == {"revision": 2, "created": True}
    assert templates.revision_path(WORKFLOW_ID, 1).read_bytes() == first
    assert (second.payload["latest_revision"], second.payload["next_revision"]) == (2, 3)


def test_publish_number_that_skips_ahead_is_contract_invalid(tmp_path):
    subject, _store, templates, _events = api(tmp_path)
    refused = write(subject, good(), publish=3)
    assert (refused.status, code_of(refused)) == (422, "contract_invalid")
    assert revisions_on_disk(templates) == []


def test_publishing_an_old_number_with_a_different_document_is_the_revision_routes_conflict(
        tmp_path):
    subject, _store, templates, _events = api(tmp_path)
    assert write(subject, good(), publish=1).status == 201
    assert write(subject, better(), publish=2).status == 201
    other = chain(review("plan", purpose="Other."), step("result", "human"))
    refused = write(subject, other, publish=1)
    assert (refused.status, code_of(refused)) == (
        ERROR_STATUS["record_conflict"], "record_conflict")
    assert revisions_on_disk(templates) == [1, 2]
    assert templates.load_draft(WORKFLOW_ID) is None, "a refused publication saves no draft"
    # The same document at the same number, through the door that arbitrates revisions.
    door = post(subject, f"/command/workflows/{WORKFLOW_ID}/revisions", {
        "revision": 1, "document": compile_flow(other)})
    assert (door.status, code_of(door)) == (refused.status, code_of(refused))


def test_flow_state_carries_the_latest_revision_flow_beside_the_draft(tmp_path):
    subject, *_ = api(tmp_path)
    assert write(subject, good(), publish=1).status == 201
    drawn = write(subject, better())
    assert drawn.payload["source"] == "draft"
    assert drawn.payload["flow"] == better() and drawn.payload["revision_flow"] == good()
    read = get(subject, flow_path()).payload
    assert read == {**drawn.payload, "published": None}
    assert (read["latest_revision"], read["next_revision"]) == (1, 2)


def test_a_published_workflow_with_no_draft_reads_as_published_with_its_budget(tmp_path):
    subject, *_ = api(tmp_path)
    assert write(subject, fixture_flow("desk-standard"), publish=1).status == 201
    read = get(subject, flow_path()).payload
    assert read["source"] == "published" and read["publishable"] is True
    assert read["budget"]["worst"] == {"actions": 4, "seconds": 12600}
    assert read["diagnostics"] == []


def test_flow_tail_takes_no_revision_number(tmp_path):
    subject, *_ = api(tmp_path)
    assert write(subject, good(), publish=1).status == 201
    for refused in (get(subject, flow_path() + "/1"),
                    post(subject, flow_path() + "/1", {"source": {"flow": good()}})):
        assert (refused.status, code_of(refused)) == (404, "route_not_found")


@pytest.fixture
def shipped_desk(tmp_path, monkeypatch):
    """A bundled `desk-standard` starter, standing in until the product ships its own."""
    folder = tmp_path / "bundled"
    folder.mkdir()
    document = {**compile_flow(fixture_flow("desk-standard")),
                "template_id": "desk-standard", "revision": 1}
    (folder / "desk-standard.json").write_text(json.dumps(document), encoding="utf-8")
    monkeypatch.setattr(graph_template, "TEMPLATE_DIR", folder)
    return folder


def test_desk_ids_accept_only_their_own_starter(tmp_path, shipped_desk):
    subject, _store, templates, _events = api(tmp_path / "project")
    own = {"starter_id": "desk-standard"}
    other = post(subject, flow_path("desk-standard"), {
        "source": {"starter_id": "desk-short"}, "expected_absent": True})
    typed = post(subject, flow_path("desk-standard"), {
        "source": {"flow": good()}, "expected_absent": True})
    copied = post(subject, flow_path("desk-mine"), {
        "source": {"flow": good()}, "expected_absent": True})
    assert [(row.status, code_of(row)) for row in (other, typed, copied)] == [
        (422, "contract_invalid")] * 3
    assert templates.workflows() == ()
    accepted = write(subject, None, workflow_id="desk-standard", source=own, publish=1)
    assert accepted.status == 201 and accepted.payload["published"]["revision"] == 1
    assert accepted.payload["flow"] == fixture_flow("desk-standard")


def test_starter_and_copy_sources_open_without_loss(tmp_path):
    subject, _store, templates, _events = api(tmp_path)
    started = write(subject, None, source={"starter_id": "dalio-v5"}, publish=1)
    assert started.status == 201
    assert started.payload["flow"] == fixture_flow("dalio-v5")
    codes = {row["code"] for row in started.payload["diagnostics"]}
    assert codes == {"link_outside_desk", "loop_order", "rework_after_correction",
                     "worst_over_actions", "worst_over_time"}
    copied = write(subject, None, workflow_id="cycle-copy0001", source={
        "copy_of": {"workflow_id": WORKFLOW_ID, "revision": 1}}, publish=1)
    assert copied.status == 201 and copied.payload["flow"] == started.payload["flow"]
    assert compile_flow(copied.payload["flow"]) == compile_flow(started.payload["flow"])
    assert templates.revisions("cycle-copy0001") == (1,)


def test_a_copy_of_a_revision_the_project_does_not_hold_is_a_refusal_naming_it(tmp_path):
    subject, *_ = api(tmp_path)
    refused = post(subject, flow_path(), {
        "source": {"copy_of": {"workflow_id": "nowhere", "revision": 4}}, "expected_absent": True})
    assert (refused.status, code_of(refused)) == (
        ERROR_STATUS["service_refused"], "service_refused")
    assert refused.payload["error"]["detail"] == {"template_id": "nowhere", "revision": 4}


def test_a_starter_the_build_does_not_ship_is_contract_invalid(tmp_path):
    subject, *_ = api(tmp_path)
    refused = post(subject, flow_path(), {
        "source": {"starter_id": "no-such-starter"}, "expected_absent": True})
    assert (refused.status, code_of(refused)) == (422, "contract_invalid")


def test_a_binding_adds_its_warnings_to_the_answer_and_is_never_stored(tmp_path):
    subject, *_ = api(tmp_path)
    plain = write(subject, good())
    assert not [row for row in plain.payload["diagnostics"] if row["code"].startswith("role_")]
    bound = write(subject, good(), binding={"role-analyst": PROVIDER})
    assert bound.payload["diagnostics"] == []
    unassigned = write(subject, good(), binding={})
    assert [row["code"] for row in unassigned.payload["diagnostics"]] == ["role_unassigned"]
    unknown = write(subject, good(), binding={"role-analyst": "no-such-provider"})
    assert [row["code"] for row in unknown.payload["diagnostics"]] == ["role_unassigned"]
    after = get(subject, flow_path()).payload
    assert not [row for row in after["diagnostics"] if row["code"].startswith("role_")]


def test_a_refused_write_moves_no_durable_byte_and_no_frame(tmp_path):
    subject, _store, _templates, events = seeded(tmp_path)
    assert write(subject, good(), publish=1).status == 201
    assert write(subject, better(), publish=2).status == 201
    before = durable_digest(tmp_path)
    stale = "sha256:" + "1" * 64
    other = chain(review("plan", purpose="Other."), step("result", "human"))
    refusals = [
        post(subject, flow_path("cycle-other1"), {"source": {"flow": good()}}),
        post(subject, flow_path("cycle-other1"), {
            "source": {"flow": good()}, "expected_digest": stale}),
        write(subject, {"flow_version": 1}, workflow_id="cycle-other1"),
        write(subject, good(), workflow_id="cycle-other1", publish=5),
        write(subject, broken(), workflow_id="cycle-other1", publish=1),
        write(subject, broken(), publish=3),
        write(subject, other, publish=1)]
    assert [(row.status, code_of(row)) for row in refusals] == [
        (422, "contract_invalid"), (409, "draft_conflict"), (422, "contract_invalid"),
        (422, "contract_invalid"), (422, "contract_invalid"), (422, "contract_invalid"),
        (409, "record_conflict")]
    assert events == [] and durable_digest(tmp_path) == before


def test_editing_a_cycle_leaves_an_open_run_on_its_revision(tmp_path):
    subject, store, _templates, _events = api(tmp_path)
    assert write(subject, good(), publish=1).status == 201
    opened = post(subject, "/command/runs", a_run(
        workflow_id=WORKFLOW_ID, revision=1, assignments={"role-analyst": INSTANCE},
        mode="policy", automation_contract="bounded-run-v1"))
    assert opened.status == 201, opened.payload
    before = journal_of(store)
    assert write(subject, better(), publish=2).status == 201
    assert journal_of(store) == before, "publishing a newer revision touched an open run"
    frozen = get(subject, f"/command/runs/{RUN_ID}").payload["config"]["workflow"]
    assert frozen == {"id": WORKFLOW_ID, "revision": 1}


# --- the project's pinned cycle: the two routes (spec 7.10) -------------------------------------

CYCLE, PIN = "/command/project/cycle", "/command/project/cycle/pin"
ACTOR = "Вы: Василий"


def pinning(subject, workflow_id=WORKFLOW_ID, actor=ACTOR):
    return post(subject, PIN, {"workflow_id": workflow_id, "actor": actor})


def pin_file(store):
    return ProjectCycleStore(store.project_root).path


class Forbidden:
    """A collaborator the pin must never reach: any use of it fails the test."""

    def __getattr__(self, name):
        raise AssertionError(f"the pin routes reached for `{name}`")


def test_get_project_cycle_names_no_pin_before_one_is_set(tmp_path):
    subject, store, *_ = api(tmp_path)
    answer = get(subject, CYCLE)
    assert (answer.status, answer.payload) == (200, {"pinned": None})
    assert not pin_file(store).exists(), "a read creates nothing"


def test_pin_requires_a_published_workflow_and_null_unpins(tmp_path):
    subject, store, *_ = api(tmp_path)
    refused = pinning(subject)
    assert (refused.status, code_of(refused)) == (422, "contract_invalid")
    assert not pin_file(store).exists()
    assert write(subject, good(), publish=1).status == 201
    pinned = pinning(subject)
    assert (pinned.status, pinned.payload) == (200, {"pinned": {
        "workflow_id": WORKFLOW_ID, "latest_revision": 1, "set_by": ACTOR, "set_at": NOW}})
    assert get(subject, CYCLE).payload == pinned.payload
    assert write(subject, better(), publish=2).status == 201
    assert get(subject, CYCLE).payload["pinned"]["latest_revision"] == 2
    unpinned = pinning(subject, None)
    assert (unpinned.status, unpinned.payload) == (200, {"pinned": None})
    assert get(subject, CYCLE).payload == {"pinned": None}


def test_pin_repeat_writes_nothing_and_records_the_actor(tmp_path):
    later = ["2026-09-28T13:50:00Z"]
    subject, store, *_ = api(tmp_path, clock=lambda: later[0])
    assert write(subject, good(), publish=1).status == 201
    assert pinning(subject).status == 200
    before = pin_file(store).read_bytes()
    later[0] = "2026-09-28T16:50:00Z"
    assert pinning(subject).status == 200
    assert pin_file(store).read_bytes() == before
    assert pinning(subject, actor="Вы: Анна").payload["pinned"]["set_by"] == "Вы: Анна"
    assert get(subject, CYCLE).payload["pinned"]["set_at"] == "2026-09-28T16:50:00Z"


@pytest.mark.parametrize("body", [
    {}, {"workflow_id": WORKFLOW_ID}, {"actor": ACTOR},
    {"workflow_id": WORKFLOW_ID, "actor": ACTOR, "extra": 1},
    {"workflow_id": "not an id", "actor": ACTOR}, {"workflow_id": WORKFLOW_ID, "actor": ""}])
def test_a_pin_body_that_is_not_exactly_a_workflow_and_an_actor_is_contract_invalid(
        tmp_path, body):
    subject, store, *_ = api(tmp_path)
    assert write(subject, good(), publish=1).status == 201
    refused = post(subject, PIN, body)
    assert (refused.status, code_of(refused)) == (422, "contract_invalid")
    assert not pin_file(store).exists()


def test_the_pin_routes_reach_no_driver_no_policy_and_no_process(tmp_path, monkeypatch):
    """Where no driver exists (the `view` server of spec 4.3.1) the pin still answers alike.

    The stand-in for that mode until it is built: the collaborators a driver-bearing server has
    are replaced by objects that fail on any use, and nothing may be started.
    """
    subject, store, _templates, events = api(tmp_path)
    assert write(subject, good(), publish=1).status == 201
    monkeypatch.setattr(ProcessRunner, "run", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("the pin started a process")))
    subject._policy, subject._runtime = Forbidden(), Forbidden()
    assert pinning(subject).status == 200 and get(subject, CYCLE).status == 200
    assert pinning(subject, None).status == 200
    assert events == [] and not list(store.runs_root.glob("*")), "no run was opened or touched"


def test_the_cycle_paths_under_project_are_the_two_cycle_tails_and_nothing_wider(tmp_path):
    subject, *_ = api(tmp_path)
    assert write(subject, good(), publish=1).status == 201
    for path in ("/command/project/", "/command/project/cycle/",
                 "/command/project/cycle/pin/x", "/command/project/cycles",
                 "/command/project/auto-continue", "/command/project/cycle/../cycle"):
        assert code_of(get(subject, path)) == "route_not_found", path
    wrong = [post(subject, CYCLE, {}), get(subject, PIN)]
    assert [(row.status, code_of(row)) for row in wrong] == [(405, "method_not_allowed")] * 2
