"""Scene facts, exact newest-run ordering and late task navigation."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

PANEL = Path(__file__).resolve().parents[1] / "src/conductor/panel"


def js(body):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for Studio's pure model")
    imports = "\n".join(f"import * as {alias} from {json.dumps((PANEL / file).as_uri())};"
        for alias, file in [("scene", "studio-scene-model.js"),
            ("runs", "studio-taskruns.js"), ("flow", "studio-taskflow.js")])
    result = subprocess.run([node, "--input-type=module", "-e", imports + "\n" + body],
        capture_output=True, text=True, encoding="utf-8", timeout=15, check=False)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def detail():
    return {"run": {"run_id": "frozen"}, "records": [], "config": {"instances": [
        {"id": "shared", "adapter": "claude-code"}, {"id": "checker", "adapter": "claude-code"},
        {"id": "standby", "adapter": "codex"}]}, "graph": {"definition": {
            "nodes": [{"node_id": "b", "kind": "task", "instance_id": "shared"},
                {"node_id": "a", "kind": "task", "instance_id": "shared", "verifier_instance_id": "checker"},
                {"node_id": "g", "kind": "gate", "gate_id": "answer"}],
            "edges": [{"from_node": "a", "to_node": "b", "condition": "on_succeeded"},
                {"from_node": "b", "to_node": "g"}]}, "runtime": {"nodes": [
                    {"node_id": "a", "outcome": "verification_failed"}, {"node_id": "b"},
                    {"node_id": "g", "decision": "idle"}]},
            "schedule": {"run_state": "active", "nodes": [
                {"node_id": "a", "state": "settled"},
                {"node_id": "b", "state": "runnable", "opened_by": []},
                {"node_id": "g", "state": "blocked", "answerable": "supersede"}]},
            "situation": {"gates": [{"node_id": "g", "needs_decision": False,
                "why_not": "road_not_open", "standing_belongs_to_current_lap": False}]}}}


def test_one_frozen_instance_is_one_planet_with_distinct_checker_and_standby():
    result = js(f"console.log(JSON.stringify(scene.sceneOf({json.dumps(detail())}))); ")
    assert [step["nodeId"] for step in result["steps"]] == ["a", "b", "g"]
    assert [row["instanceId"] for row in result["participants"]] == ["shared", "checker", "standby"]
    assert result["participants"][0]["performs"] == ["a", "b"]
    assert result["participants"][1]["verifies"] == ["a"]
    assert result["participants"][2]["word"] == "unassigned"
    assert result["steps"][0]["word"] == "outcome_verification_failed"
    assert result["steps"][2]["word"] == "road_not_open"
    assert result["links"][0]["open"] is False
    assert result["positions"] == ["b"]


def test_gate_need_and_open_route_come_only_from_the_server_and_end_suppresses_positions():
    sample = detail()
    sample["graph"]["situation"]["gates"][0].update(needs_decision=True, why_not=None)
    sample["graph"]["schedule"]["nodes"][1]["opened_by"] = ["a"]
    result = js(f"const d={json.dumps(sample)}; const a=scene.sceneOf(d); "
        "d.graph.schedule.run_state='complete'; const b=scene.sceneOf(d); "
        "console.log(JSON.stringify([a.positions,a.links[0].open,b.positions]));")
    assert result == [["g", "b"], True, []]


def test_pending_request_overrides_idle_projection_without_claiming_running():
    sample = detail()
    sample["records"] = [{"record_type": "action_request", "record": {"action_id": "held", "node_id": "b"}}]
    result = js(f"console.log(JSON.stringify(scene.sceneOf({json.dumps(sample)}))); ")
    assert result["steps"][1]["word"] == "awaiting_result"
    assert result["participants"][0]["word"] == "awaiting_result"


def test_trace_expands_instead_of_overlapping_a_variable_team():
    sample = detail()
    sample["config"]["instances"] += [{"id": f"standby-{i}", "adapter": "codex"} for i in range(12)]
    result = js(f"console.log(JSON.stringify(scene.traceLayout(scene.sceneOf({json.dumps(sample)}),672)));")
    xs = [row["x"] for row in result["planets"]]
    assert len(xs) == 15 and all(b - a >= 164 for a, b in zip(xs, xs[1:]))
    assert result["width"] >= xs[-1] + 84


def test_newest_run_keeps_microseconds_and_has_a_deterministic_equal_instant_tie():
    result = js("""
      const row=(id,at)=>({run_id:id,task_id:'t',created_at:at,unreadable:false});
      const list=[row('older','2026-09-21T12:00:00.123001Z'),row('newer','2026-09-21T12:00:00.123002Z')];
      const a=runs.newestRun({phase:'ready',list},'t');
      const tied=[row('z','2026-09-21T12:00:00.1Z'),row('a','2026-09-21T12:00:00.100000+00:00')];
      const b=runs.newestRun({phase:'ready',list:tied},'t');
      console.log(JSON.stringify([a.row.run_id,b.row.run_id,runs.compareInstants(tied[0].created_at,tied[1].created_at)]));
    """)
    assert result == ["newer", "a", 0]


def test_unreadable_catalog_never_substitutes_an_older_success():
    result = js("""
      const readable={run_id:'old',task_id:'t',created_at:'2026-09-21T12:00:00Z',last_outcome:'succeeded'};
      const unreadable={run_id:'unknown',task_id:null,created_at:null,unreadable:true};
      console.log(JSON.stringify(runs.newestRun({phase:'ready',list:[readable,unreadable]},'t')));
    """)
    assert result == {"state": "unknown", "row": None}


def test_late_catalog_cannot_overwrite_a_manually_selected_run():
    result = js("""
      let held, navigation=0, opened=[];
      const state={tasks:{selectedId:null},runs:{phase:'ready',list:[
        {run_id:'newest',task_id:'t',created_at:'2026-09-21T12:00:00Z'}]}};
      const tasks=flow.taskFlow({state:()=>state,clearRun:()=>{navigation++;},
        runSelection:()=>navigation,loadRuns:()=>new Promise(resolve=>{held=resolve;}),
        dispatch:event=>{if(event.type==='task-chosen')state.tasks.selectedId=event.taskId;},
        refreshRun:id=>opened.push(id)});
      const pending=tasks.chooseTask('t'); navigation++; opened.push('chosen-by-human');
      held(); await pending; console.log(JSON.stringify(opened));
    """)
    assert result == ["chosen-by-human"]
