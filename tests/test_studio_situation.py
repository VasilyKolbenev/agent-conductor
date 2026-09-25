"""Execute the closed S2 boundary against real Python readings and the store door."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest

from conductor.command.human_situation import CHECKED_REASONS, UNKNOWN_REASONS, HUMAN_STATES, GATE_WHY_NOT
from tests.test_human_situation import view, plan, gate, task, Journal, ended, routed_dalio, through_the_body
from tests.test_command_http_api import get_headers, RUN_ID, post, proposal_body, confirm_body
from tests.test_command_schema_doubles import DeepPlanAdapter
from tests.test_command_workflow_routes import api as workflow_api
from tests.human_situation_samples import READ_AT
from tests.test_studio_source import _js_array

PANEL = Path(__file__).resolve().parents[1] / "src/conductor/panel"
SITUATION = PANEL / "studio-situation.js"


def api(tmp_path, *, adapters=None, clock=lambda: READ_AT):
    """Open through Studio's real route, which freezes no legacy env metadata."""
    subject, store, _templates, events = workflow_api(
        tmp_path, adapters=adapters, clock=clock)
    opened = post(subject, "/command/runs", {
        "run_id": RUN_ID, "cycle_id": "situation-cycle", "mode": "confirm",
        "participants": [{"instance_id": "claude-dev", "provider_id": "claude-code", "model": None}],
        "workflow_id": None, "revision": None, "assignments": {}, "task_id": None})
    assert opened.status == 201, opened.payload
    return subject, store, events


def js(body):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is needed to execute the Studio value modules")
    source = (f"import * as situation from {json.dumps(SITUATION.as_uri())};\n"
        f"import {{EMPTY, reduce}} from {json.dumps((PANEL / 'studio-store.js').as_uri())};\n"
        f"import * as model from {json.dumps((PANEL / 'studio-model.js').as_uri())};\n" + body)
    # Through stdin: a document at the artifact bound outgrows a Windows command line.
    result = subprocess.run([node, "--input-type=module"], input=source,
        capture_output=True, text=True, encoding="utf-8", timeout=15, check=False)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def reading(kind):
    if kind == "no_plan":
        return view(None)
    journal, definition = Journal(), plan(gate("answer"))
    if kind == "pending":
        definition = routed_dalio()
    if kind == "warning":
        return view(None, warnings=("private diagnostic is not copied",))
    if kind == "queued":
        definition = plan(task("do"))
        journal.request("do")
    if kind in {"correction", "terminal", "contradiction"}:
        journal.decide("gate-answer", "approve")
    if kind == "terminal":
        ended(journal, definition)
    if kind == "contradiction":
        journal.decide("gate-answer", "reject", supersede=False)
    if kind == "lap_two":
        definition = routed_dalio()
        journal.did("goal")
        through_the_body(journal)
        journal.decide("gate-result", "request_changes")
        for node in ("identify", "diagnose", "design"):
            journal.did(node)
    return view(definition, journal)


@pytest.mark.parametrize("kind", ["no_plan", "required", "correction", "terminal",
    "contradiction", "warning", "queued", "lap_two"])
def test_real_server_reading_survives_whole_and_is_deeply_frozen(kind):
    value = reading(kind)
    payload = json.dumps(value)
    got = js(f"const value=situation.projectSituation({payload});"
        "console.log(JSON.stringify({value, frozen: value !== null && Object.isFrozen(value)"
        " && Object.isFrozen(value.checked) && Object.isFrozen(value.checked[0].sources)}));")
    assert got == {"value": value, "frozen": True}


def malformed(case):
    value = deepcopy(reading("required"))
    if case == "no_checked":
        del value["checked"]
    elif case == "empty_checked":
        value["checked"] = []
    elif case == "duplicate_reason":
        value["checked"][1] = deepcopy(value["checked"][0])
    elif case == "unknown_reason":
        value["checked"][0]["reason"] = "permission"
    elif case == "missing_reason":
        value["checked"].pop()
    elif case == "bad_count":
        value["checked"][0]["count"] = True
    elif case == "fractional_count":
        value["checked"][0]["count"] = 0.5
    elif case == "count_source_mismatch":
        value["checked"][0]["count"] = 2
    elif case == "unsafe_integer":
        value["checked"][0]["count"] = 2 ** 53
    elif case == "duplicate_source":
        value["checked"][0].update(count=2, sources=["answer", "answer"])
    elif case == "malformed_id":
        value["gates"][0]["gate_id"] = "../outside"
    elif case == "wrong_state":
        value["state"] = "not_required"
    elif case == "falsified_no_need":
        value["gates"][0].update(needs_decision=False, why_not="road_not_open")
        value["checked"][0].update(count=0, sources=[])
        value["state"] = "not_required"
    elif case == "authority_field":
        value["authorized"] = True
    elif case == "bad_instant":
        value["computed_at"] = "2026-02-30T00:00:00Z"
    elif case == "missing_unknown":
        value["unknown_sources"] = []
    elif case == "invented_reconcile":
        value["checked"][3].update(count=1, sources=["action-one"])
    elif case == "unknown_masked":
        value = reading("queued")
        value["state"], value["unknown_because"] = "not_required", []
    else:
        raise AssertionError(case)
    return value


@pytest.mark.parametrize("case", ["no_checked", "empty_checked", "duplicate_reason",
    "unknown_reason", "missing_reason", "bad_count", "fractional_count",
    "count_source_mismatch", "unsafe_integer", "duplicate_source", "malformed_id",
    "wrong_state", "falsified_no_need", "authority_field", "bad_instant", "missing_unknown",
    "invented_reconcile", "unknown_masked"])
def test_h7_malformed_reading_is_refused_whole_instead_of_repaired(case):
    good, bad = json.dumps(reading("required")), json.dumps(malformed(case))
    assert js(f"console.log(JSON.stringify([situation.projectSituation({good}) !== null,"
        f"situation.projectSituation({bad})]));") == [True, None]


def test_actual_store_read_door_refuses_a_listless_situation_and_keeps_unknown_visible(tmp_path):
    adapter = DeepPlanAdapter()
    subject, _store, _published = api(tmp_path, adapters=[adapter], clock=lambda: READ_AT)
    read = subject.handle("GET", f"/command/runs/{RUN_ID}", get_headers()).payload
    proposed = post(subject, f"/command/runs/{RUN_ID}/proposals", proposal_body())
    assert proposed.status == 201
    confirmed = post(subject, f"/command/runs/{RUN_ID}/actions", confirm_body(proposed.payload))
    assert confirmed.status == 201 and adapter.preparations == 0
    unknown = subject.handle("GET", f"/command/runs/{RUN_ID}", get_headers()).payload
    assert unknown["graph"]["situation"]["unknown_because"] == ["unobserved_request"]
    bad = deepcopy(read)
    del bad["graph"]["situation"]["checked"]
    values = json.dumps([read, unknown, bad])
    result = js(f"const values={values}; console.log(JSON.stringify(values.map(read => {{"
        "const state=reduce(EMPTY,{type:'run-loaded',read});"
        "return [state.runs.phase,state.runs.detail?.graph.situation.state ?? null];}))); ")
    assert result == [["ready", "not_required"], ["ready", "unknown"], ["failed", None]]


@pytest.mark.parametrize("kind", ["gate", "action", "proposal", "terminal"])
def test_a_situation_cannot_borrow_ids_from_another_run_read(tmp_path, kind):
    subject, _store, _published = api(tmp_path, clock=lambda: READ_AT)
    original = subject.handle("GET", f"/command/runs/{RUN_ID}", get_headers()).payload
    foreign = deepcopy(original)
    if kind == "gate":
        foreign["graph"]["situation"] = reading("required")
    elif kind == "action":
        foreign["graph"]["situation"] = reading("queued")
    else:
        value = foreign["graph"]["situation"]
        row = next(row for row in value["checked"] if row["reason"] == (
            "confirmation" if kind == "proposal" else "run_ended"))
        row.update(count=1, sources=["foreign-identity"])
        value["state"] = "required" if kind == "proposal" else "not_required"
    values = json.dumps([original, foreign])
    assert js(f"console.log(JSON.stringify({values}.map(p => situation.projectRunRead(p) !== null))); ") == [True, False]


def test_the_gate_list_covers_the_frozen_graph_and_rejects_a_substituted_pair(tmp_path):
    from tests.test_command_graph_route import graph_body, read_run, GRAPH_PATH
    subject, _store, _events = api(tmp_path)
    assert post(subject, GRAPH_PATH, graph_body()).status == 201
    read = read_run(subject).payload
    omitted, foreign = deepcopy(read), deepcopy(read)
    assert len(read["graph"]["situation"]["gates"]) == 1
    omitted["graph"]["situation"]["gates"] = []
    foreign["graph"]["situation"]["gates"][0].update(node_id="foreign-node", gate_id="foreign-gate")
    # Keep each mutant internally coherent so only the join can reject it.
    for candidate in (omitted, foreign):
        value = candidate["graph"]["situation"]
        checked = next(row for row in value["checked"] if row["reason"] == "gate_decision")
        checked["sources"] = [row["node_id"] for row in value["gates"] if row["needs_decision"]]
        checked["count"] = len(checked["sources"])
        value["state"] = "required" if any(row["count"] for row in value["checked"]
            if row["reason"] != "run_ended") else "not_required"
    values = json.dumps([read, omitted, foreign])
    got = js(f"const values={values}; console.log(JSON.stringify(["
        "values.map(p => situation.projectSituation(p.graph.situation) !== null),"
        "values.map(p => situation.projectRunRead(p) !== null)]));")
    assert got == [[True, True, True], [True, False, False]]


@pytest.mark.parametrize("kind,why", [("pending", "run_ended"), ("contradiction", "branch_closed")])
def test_reason_priority_cannot_claim_an_ending_or_hide_an_unknown_decision(kind, why):
    value = reading(kind)
    good = json.dumps(value)
    value["gates"][0]["why_not"] = why
    assert js(f"console.log(JSON.stringify([situation.projectSituation({good}) !== null,"
        f"situation.projectSituation({json.dumps(value)})])); ") == [True, None]


def test_situation_key_sets_and_vocabulary_match_the_python_producer():
    source = SITUATION.read_text(encoding="utf-8")
    value = reading("required")
    assert _js_array(source, "SITUATION_KEYS") == set(value)
    assert _js_array(source, "GATE_KEYS") == set(value["gates"][0])
    assert _js_array(source, "LAP_KEYS") == set(value["gates"][0]["lap"])
    assert _js_array(source, "REASON_KEYS") == set(value["checked"][0])
    assert set(re.findall(r"keys\([a-z.]+, ([A-Z_]+)\)", source)) == {
        "SITUATION_KEYS", "GATE_KEYS", "LAP_KEYS", "REASON_KEYS"}
    for name, expected in {"HUMAN_STATES": HUMAN_STATES, "CHECKED_REASONS": CHECKED_REASONS,
                          "UNKNOWN_REASONS": UNKNOWN_REASONS, "GATE_WHY_NOT": GATE_WHY_NOT}.items():
        match = re.search(rf"const {name} = Object.freeze\(\[(.*?)\]\);", source, re.S)
        assert match and tuple(re.findall(r'"([a-z_]+)"', match[1])) == expected


def test_list_row_refuses_missing_or_invented_human_state(tmp_path):
    subject, _store, _published = api(tmp_path, clock=lambda: READ_AT)
    payload = subject.handle("GET", "/command/runs", get_headers()).payload
    missing, invented = deepcopy(payload), deepcopy(payload)
    del missing["runs"][0]["human_state"]
    invented["runs"][0]["human_state"] = "authorized"
    values = json.dumps([payload, missing, invented])
    assert js(f"console.log(JSON.stringify({values}.map(p => model.projectRuns(p) !== null))); ") == [True, False, False]


def _with_document(tmp_path, content, kind="artifact", **extra):
    """A real server run read, plus one real artifact record of the given content."""
    from conductor.command.artifacts import ArtifactDocument

    subject, _store, _events = api(tmp_path)
    value = subject.handle("GET", f"/command/runs/{RUN_ID}", get_headers()).payload
    document = ArtifactDocument(
        artifact_id="artifact-review-1", artifact_ref="artifact-problems",
        run_id=RUN_ID, created_at=READ_AT, media_type="text/markdown",
        content="# Problems").as_dict()
    value["records"].append({"record_type": kind, "record": {**document, "content": content, **extra}})
    return value


def test_a_review_document_as_long_as_the_server_admits_is_read_and_carried_verbatim(tmp_path):
    """MEASURED live (23.09.2026): a real review wrote 14,336 characters, and the 4,096-character
    bound every other carried text keeps made the whole run -- and the Runs screen -- unreadable."""
    content = "# Problems\n" + "x" * 14325
    value = _with_document(tmp_path, content)
    carried = js(f"const value = {json.dumps(value)}; const read = situation.projectRunRead(value);"
                 "const state = reduce(EMPTY, {type: 'run-loaded', read: value});"
                 "console.log(JSON.stringify(read === null ? null : [read.records.at(-1).record.content,"
                 " Object.isFrozen(read.records.at(-1).record), state.runs.phase]));")
    assert carried == [content, True, "ready"]


BOUND_CASES = {
    "short": ("artifact", "# Problems", {}, True),
    "ascii_at_the_bound": ("artifact", "x" * 49152, {}, True),
    "multibyte_at_the_bound": ("artifact", "\u00e9" * 24576, {}, True),
    "one_byte_over_in_multibyte": ("artifact", "\u00e9" * 24576 + "x", {}, False),
    "ascii_over_the_bound": ("artifact", "x" * 49153, {}, False),
    "a_long_field_that_is_not_content": ("artifact", "# Problems", {"source_action_id": "a" * 5000}, False),
    "short_content_on_another_record_kind": ("evidence", "x" * 10, {}, True),
    "long_content_on_another_record_kind": ("evidence", "x" * 5000, {}, False),
}


@pytest.mark.parametrize("case", sorted(BOUND_CASES))
def test_only_an_artifacts_content_gets_the_artifacts_bound_counted_in_utf8_bytes(tmp_path, case):
    kind, content, extra, admitted = BOUND_CASES[case]
    value = _with_document(tmp_path, content, kind, **extra)
    read = js(f"console.log(JSON.stringify(situation.projectRunRead({json.dumps(value)}) !== null));")
    assert read is admitted
