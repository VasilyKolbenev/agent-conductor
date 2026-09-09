"""Every key set the window judges against, held to the route that fills it.

This closes a CLASS, and it is worth saying how the class behaved, because it
was silent every time. `studio-model.js` judges each payload with `exactKeys`:
a document carrying a key the window was never told about is refused WHOLE
rather than half-read, which is the right rule and the reason the window can
never show a shorter truth than the server sent.

The cost of that rule is that adding a key to a route breaks every read of it
until the boundary is widened to match -- and it breaks quietly, because the
window's answer is "this payload is not one I can read", which looks like an
empty screen and not like an error. It has now happened three times in this
branch's own history:

- the frozen `cycle`, where a boundary demanding `{id}` refused the
  `{id, phases}` that `conduct preview` and the control loop both write, so the
  first run most people ever have was listed and could not be opened;
- `RUN_ROW_KEYS`, when the run row learned which workflow a run followed, so
  every row was refused and the Runs list came up empty;
- `WORKFLOW_KEYS`, when the workflow read learned `unchanged`, so the Studio
  silently stopped showing published revisions while the whole fast suite
  stayed green and only the browser gate noticed.

Three cases, three fixes, one class. What follows is the class: every payload a
Studio route answers with is built HERE, by the production route, against a real
store, and its key set is compared with the array the window judges it by. A
fourth key added to a fifth route reds in the fast suite instead of in a browser.

The key sets are read out of the JavaScript rather than copied, so this file
cannot drift from the boundary either; and `_js_array` refuses a repeated key,
so a set that grew a duplicate is caught on the way in.
"""
from __future__ import annotations

import re

import pytest

from conductor.command.graph_template import GraphTemplate
from conductor.command.run_store import RunStore
from conductor.command.studio_contracts import Participant, RunInput
from conductor.command.template_store import TemplateStore
from conductor.command import studio_routes
from conductor.command.workflow_draft import saved_draft, workflow_state
from conductor.command.graph_template import RunBinding

from tests.test_studio_source import MODEL, _js_array

WORKFLOW = "parity-flow"
RUN_ID = "parity-run"


def _model_source() -> str:
    return MODEL.read_text(encoding="utf-8")


def _project(tmp_path):
    (tmp_path / "conductor").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _document():
    return {
        "schema_version": 1,
        "title": "Parity flow",
        "nodes": [{"node_id": "step-one", "kind": "task", "title": "Step one",
                   "resources": []}],
        "edges": [],
    }


def _published(tmp_path):
    templates = TemplateStore(_project(tmp_path))
    settled = dict(_document(), template_id=WORKFLOW, revision=1)
    templates.save(GraphTemplate.from_dict(settled))
    return templates


def _run(tmp_path, *, workflow_id=None, revision=None):
    store = RunStore(_project(tmp_path))
    asked = RunInput(
        run_id=RUN_ID, cycle_id="parity-cycle", mode="confirm",
        participants=(Participant(instance_id="dev", provider_id="claude-code",
                                  model=None),),
        workflow_id=workflow_id, revision=revision,
        binding=RunBinding.from_dict({"assignments": {}}))
    snapshot = asked.snapshot()
    store.create_run(asked.build(snapshot, "2026-01-01T00:00:00Z"), snapshot)
    return store


# -- the top-level payloads --------------------------------------------------


def test_the_workflows_payload_is_exactly_what_the_window_admits(tmp_path):
    _, payload = studio_routes.list_workflows(
        TemplateStore(_project(tmp_path)), (), "a-project")

    assert set(payload) == _js_array(_model_source(), "WORKFLOWS_KEYS")


def test_the_workflow_read_payload_is_exactly_what_the_window_admits(tmp_path):
    """The read that broke silently when it learned one boolean."""
    templates = _published(tmp_path)
    saved_draft(templates, WORKFLOW, _document(),
                lambda: "2026-01-01T00:00:00Z")

    payload = workflow_state(templates, WORKFLOW)

    assert set(payload) == _js_array(_model_source(), "WORKFLOW_KEYS")


def test_the_window_judges_the_shape_of_the_warnings_it_admits(tmp_path):
    """A key admitted is not a key judged, and the two are different guards.

    `WORKFLOW_KEYS` above says the window will not refuse a payload for
    carrying `warnings`. This says it refuses one whose warnings are not
    SENTENCES -- which is what they are: prose a person reads, with no code and
    nothing acting on them. Without this, widening the key set would have been
    enough to make the boundary accept any shape at all under that name, and
    the refusal-count guard next door cannot see the difference because the
    `return null;` it counts is still there either way.
    """
    source = _model_source()
    body = re.search(r"export function projectWorkflow\(payload\) \{(.*?)\n\}",
                     source, re.DOTALL).group(1)

    assert "Array.isArray(payload.warnings)" in body, body
    assert 'typeof row === "string"' in body, body
    # And what it hands on is frozen, like every other list this window carries.
    assert "warnings: frozenList(payload.warnings)," in body, body
def test_the_revision_read_payload_is_exactly_what_the_window_admits(tmp_path):
    _, payload = studio_routes.read_revision(_published(tmp_path), WORKFLOW, 1)

    assert set(payload) == _js_array(_model_source(), "REVISION_KEYS")


def test_the_runs_listing_payload_is_exactly_what_the_window_admits(tmp_path):
    store = _run(tmp_path)

    _, payload = studio_routes.list_runs(store, ())

    assert set(payload) == _js_array(_model_source(), "RUNS_KEYS")


def test_the_run_row_is_exactly_what_the_window_admits(tmp_path):
    """The row that broke silently when it learned which plan a run followed."""
    store = _run(tmp_path, workflow_id=WORKFLOW, revision=1)

    row = studio_routes.run_row(store, RUN_ID)

    assert set(row) == _js_array(_model_source(), "RUN_ROW_KEYS")


def test_an_unreadable_run_row_carries_the_same_keys_as_a_readable_one(tmp_path):
    """Both shapes, because the window judges them with ONE key set.

    A row that dropped keys when the run could not be read would be a second
    shape for one array, and "unreadable" and "absent" would arrive on screen
    as the same answer.
    """
    store = RunStore(_project(tmp_path))
    store.runs_root.mkdir(parents=True, exist_ok=True)
    (store.runs_root / "ghost").mkdir()

    row = studio_routes.run_row(store, "ghost")

    assert row["unreadable"] is True
    assert set(row) == _js_array(_model_source(), "RUN_ROW_KEYS")


# -- the nested documents ----------------------------------------------------


def test_the_frozen_config_a_run_writes_stays_inside_what_the_window_admits(
        tmp_path):
    """Required-plus-optional, so BOTH directions are asserted.

    The cycle taught this: a set that demands every key refuses the writers that
    omit an optional one, and a set that admits none refuses the writer that
    supplies it.
    """
    source = _model_source()
    required = _js_array(source, "CONFIG_REQUIRED")
    admitted = _js_array(source, "CONFIG_KEYS")
    store = _run(tmp_path, workflow_id=WORKFLOW, revision=1)

    config = store.read(RUN_ID).config

    assert required <= set(config) <= admitted


def test_the_draft_shape_a_read_answers_with_is_what_the_window_admits(tmp_path):
    templates = _published(tmp_path)
    saved_draft(templates, WORKFLOW, _document(),
                lambda: "2026-01-01T00:00:00Z")

    draft = workflow_state(templates, WORKFLOW)["draft"]

    assert set(draft) == _js_array(_model_source(), "DRAFT_KEYS")


def test_a_workflow_row_in_the_listing_is_what_the_window_admits(tmp_path):
    templates = _published(tmp_path)

    _, payload = studio_routes.list_workflows(templates, (), None)

    assert payload["workflows"], "the fixture published nothing to list"
    for row in payload["workflows"]:
        assert set(row) == _js_array(_model_source(), "WORKFLOW_ROW_KEYS")


def test_a_starter_offer_is_what_the_window_admits(tmp_path):
    _, payload = studio_routes.list_workflows(
        TemplateStore(_project(tmp_path)), (), None)

    assert payload["starters"], "this build ships no starter to check"
    for row in payload["starters"]:
        assert set(row) == _js_array(_model_source(), "STARTER_KEYS")


def test_every_route_that_carries_a_provider_row_sends_what_the_window_admits(
        tmp_path):
    """The producer's own row, against the array the window judges it by.

    This is the witness that was missing, and its absence cost the whole roster.
    `provider_projection` gained a seventh name; the window's array still held
    six; `exactKeys` therefore dropped EVERY row on all three routes, the Agents
    screen said no provider was configured, and a published workflow could not
    bind the installed harness. Nothing red: the pair below compares one JS list
    with another JS rebuild, and neither side of that comparison can see a key
    added on the SERVER.

    So the comparison is made against the real payload, on every route that
    carries the array -- one of them passing is not the class, because the three
    are separate call sites and only their shared projection makes them agree.
    """
    from conductor.command.adapters.provider import provider_projection

    from tests.test_command_provider_contract import _contract

    admitted = _js_array(_model_source(), "PROVIDER_KEYS")
    roster = (_contract(),)
    payloads = [
        studio_routes.list_workflows(_published(tmp_path), roster, None)[1],
        studio_routes.list_runs(_run(tmp_path), roster)[1],
        # The controls route reaches the same projection by its own road, and
        # its rows land beside the isolation standings.
        {"providers": provider_projection(roster)},
    ]

    for payload in payloads:
        assert payload["providers"], "a provider-bearing route sent no rows"
        for row in payload["providers"]:
            assert set(row) == admitted


def test_the_store_hands_every_admitted_provider_key_back_to_the_screen():
    """A row the boundary admitted and the store rebuilt must lose nothing.

    The window reads a wire row, keeps a camel-cased copy, and then writes a
    wire-worded row back for the screen. That rebuild is a second, silent key
    set: a field the boundary admits and the rebuild forgets reaches the screen
    as "not stated", and every guard on either side of it stays green -- which
    is exactly what happened to the login a provider row pins.
    """
    store = (MODEL.parent / "studio-store.js").read_text(encoding="utf-8")
    body = store[store.index("function wireProviders("):]
    body = body[:body.index("\n}")]
    rebuilt = set(re.findall(r"([a-z_]+):", body))
    assert rebuilt == _js_array(_model_source(), "PROVIDER_KEYS")


def test_every_key_set_the_window_judges_by_is_checked_by_this_module():
    """The census, so a new exactKeys set cannot be added unwatched.

    Without this, the class stays open in the one direction that matters: a
    SIXTH route with a seventh key set would be judged by an array nothing
    compares against a payload, and the next silent refusal would look exactly
    like the last three.

    Sets deliberately not driven here are named with the reason, so the list is
    a decision rather than an oversight.
    """
    # BOTH boundary modules, because the census is about the window and not
    # about one file: the controls route's key sets moved to `studio-controls`
    # when the model reached its line cap, and a census that still read only the
    # model would have quietly stopped watching them -- which is the exact
    # failure this test exists to prevent, one refactor later.
    source = _model_source() + (
        MODEL.parent / "studio-controls.js").read_text(encoding="utf-8")
    judged = set(__import__("re").findall(r"exactKeys\([a-z]+, ([A-Z_]+)\)",
                                          source))
    checked = {"WORKFLOWS_KEYS", "WORKFLOW_KEYS", "REVISION_KEYS", "RUNS_KEYS",
               "RUN_ROW_KEYS", "DRAFT_KEYS", "WORKFLOW_ROW_KEYS",
               "STARTER_KEYS", "PROVIDER_KEYS"}
    #: Driven by their own suites against real payloads, not skipped:
    #: CONTROLS_KEYS and
    #: CONTROL_ROW_KEYS by the controls route's, RUN_READ_KEYS and
    #: RECORD_ROW_KEYS and DIAGNOSTIC_KEYS and RUN_WORKFLOW_KEYS by the run
    #: read's and the run-identity module's.
    #: FACT_KEYS, STANDING_KEYS and STANDING_WITH_VENDOR belong to the isolation
    #: answer and are driven by the controls route's own suites and the browser
    #: witness, against real payloads.
    elsewhere = {"CONTROLS_KEYS", "CONTROL_ROW_KEYS",
                 "RUN_READ_KEYS", "RECORD_ROW_KEYS", "DIAGNOSTIC_KEYS",
                 "RUN_WORKFLOW_KEYS", "FACT_KEYS", "STANDING_KEYS",
                 "STANDING_WITH_VENDOR"}
    #: PROVIDER_KEYS is no longer named here. It was, and the exemption was the
    #: defect: "driven by the provider projection's tests" meant one JS list
    #: compared with another JS rebuild, which cannot see a key the SERVER
    #: added. It is driven above, against the real payload of every route that
    #: carries the row.

    assert judged == checked | elsewhere, (
        "a key set the window judges by is neither checked here nor named as "
        f"checked elsewhere: {sorted(judged - checked - elsewhere)}")
