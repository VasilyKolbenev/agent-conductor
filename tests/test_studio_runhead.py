"""The Runs header's main action (port spec §5.1), chosen from one run read by the shipped module."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

MODULE = Path(__file__).resolve().parents[1] / "src/conductor/panel/studio-runhead.js"
REASONS = ["gate_decision", "confirmation", "input_document", "reconcile", "attempt_bound", "run_ended"]


def _situation(state, **counts):
    return {"state": state, "checked": [
        {"reason": reason, "count": len(counts.get(reason, [])), "sources": counts.get(reason, [])}
        for reason in REASONS]}


def _detail(situation, *, mode="confirm", records=(), runnable=("goal",), proposed=()):
    nodes = [{"node_id": "goal", "title": "Goal", "kind": "task", "instance_id": "a", "capability": "review"},
             {"node_id": "do", "title": "Do", "kind": "task", "instance_id": "b", "capability": "dispatch"}]
    return {"run": {"run_id": "run-1", "mode": mode}, "records": list(records), "graph": {
        "definition": {"nodes": nodes},
        "schedule": {"run_state": "open", "nodes": [
            {"node_id": node["node_id"], "state": "runnable" if node["node_id"] in runnable else "blocked"}
            for node in nodes]},
        "runtime": {"nodes": [{"node_id": node["node_id"],
                               "phase": "proposed" if node["node_id"] in proposed else "idle"} for node in nodes]},
        "situation": situation}}


def _chosen(detail, *, connection="open", phase="ready"):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is needed for the Studio module")
    state = {"connection": connection, "runs": {"phase": phase}, "locale": "en"}
    source = (f"import * as m from {json.dumps(MODULE.as_uri())};"
              f"console.log(JSON.stringify(m.runAction({json.dumps(state)}, {json.dumps(detail)})));")
    done = subprocess.run([node, "--input-type=module", "-e", source], capture_output=True, text=True,
                          encoding="utf-8", timeout=15, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def _result(outcome, verification):
    return [{"record_type": "evidence", "record": {"evidence_id": "e1", "verification": verification}},
            {"record_type": "action_result", "record": {"outcome": outcome, "evidence_refs": ["e1"]}}]


@pytest.mark.parametrize(("situation", "records", "expected"), [
    (_situation("required", gate_decision=["result-gate"]), (), {"key": "decide"}),
    (_situation("required", input_document=["do"]), (), {"key": "document", "node": "do"}),
    (_situation("required", reconcile=["x"]), (), {"key": "reconcile"}),
    (_situation("required", attempt_bound=["do"]), (), {"key": "workflow"}),
    (_situation("not_required", run_ended=["t1"]), _result("succeeded", "verified"), {"key": "result"}),
    (_situation("not_required"), (), {"key": "propose", "node": "goal"}),
])
def test_each_row_of_the_table_is_the_main_action_its_read_calls_for(situation, records, expected):
    assert _chosen(_detail(situation, records=records)) == expected


def _waiting_on_do(mode, *, binding="proposal-v1", legacy_schema=False):
    """A proposal standing on `do`, as the server reads it: runnable, proposed, not yet requested."""
    proposal = {"proposal_id": "p1", "node_id": "do", "instance_id": "b", "capability": "dispatch",
                "preview_digest": "d1"}
    if binding is not None:
        proposal["input_binding"] = binding
    detail = _detail(_situation("required", confirmation=["p1"]), mode=mode, runnable=("do",), proposed=("do",),
                     records=[{"record_type": "action_proposal", "record": proposal}])
    if legacy_schema:
        detail["controls"] = {"instances": [{"instance_id": "b",
                                             "argument_schemas": {"dispatch": "deep-arguments-v1"}}]}
    return detail


@pytest.mark.parametrize(("mode", "legacy", "expected"), [
    ("confirm", False, {"key": "confirm", "node": "do"}),
    # Propose waits for a confirmation it cannot give: a sentence, never a Confirm door the row does not draw.
    ("propose", False, {"key": "awaiting", "node": "do"}),
    # A proposal made before material binding is re-proposed by the row, so the header proposes too.
    ("confirm", True, {"key": "propose", "node": "do"}),
    ("propose", True, {"key": "propose", "node": "do"}),
])
def test_a_waiting_proposal_leads_only_to_the_form_its_row_draws(mode, legacy, expected):
    detail = _waiting_on_do(mode, binding=None if legacy else "proposal-v1", legacy_schema=legacy)
    assert _chosen(detail) == expected


def test_the_first_holding_row_wins_so_a_waiting_decision_outranks_a_confirmation():
    situation = _situation("required", gate_decision=["result-gate"], confirmation=["p1"])
    assert _chosen(_detail(situation))["key"] == "decide"


@pytest.mark.parametrize("why", ["no_situation", "unknown_need", "closed_stream", "older_read",
                                 "unverified_result", "observe_mode", "already_proposed"])
def test_what_cannot_be_established_is_read_again_and_never_guessed(why):
    situation = _situation("not_required")
    detail, connection, phase = _detail(situation), "open", "ready"
    if why == "no_situation":
        detail["graph"]["situation"] = None
    elif why == "unknown_need":
        detail = _detail(_situation("unknown", gate_decision=["result-gate"]))
    elif why == "closed_stream":
        connection = "closed"
    elif why == "older_read":
        phase = "stale"
    elif why == "unverified_result":
        detail = _detail(_situation("not_required", run_ended=["t1"]), records=_result("succeeded", "unverified"),
                         runnable=())
    elif why == "observe_mode":
        detail = _detail(situation, mode="observe")
    else:
        detail = _detail(situation, proposed=("goal",))
    assert _chosen(detail, connection=connection, phase=phase) == {"key": "refresh"}
