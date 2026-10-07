"""Real server values cross the UI boundary; reads never become authority."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from conductor.command.http_api import CommandApi
from conductor.command.http_transport import CommandSession
from conductor.command.policy_view import automation_view
from tests.test_policy_runtime import ASK, approve, pause, setup
from tests.test_command_http_api import PORT, TOKEN, get_headers

PANEL = Path(__file__).resolve().parents[1] / "src/conductor/panel"


def js(body, payload):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for the real Studio modules")
    modules = {"model": "studio-automation-model.js", "flow": "studio-automation-flow.js",
               "boundary": "studio-situation.js", "draft": "studio-draft.js", "copy": "studio-i18n.js"}
    imports = "\n".join(f"import * as {key} from {json.dumps((PANEL / name).as_uri())};"
                        for key, name in modules.items())
    source = imports + "\nconst p=" + json.dumps(payload) + ";\n" + body
    result = subprocess.run([node, "--input-type=module", "-e", source], capture_output=True,
                            text=True, encoding="utf-8", timeout=15, check=False)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def wire(root):
    f = setup(root)
    api = CommandApi(f.store, f.registry, session=CommandSession(PORT, TOKEN),
                     budget=f.policy.budget, clock=f.policy.clock, ids=f.runtime._ids,
                     publish_run=lambda run: None)
    api._policy = f.policy
    reading = lambda: api.handle("GET", "/command/runs/run", get_headers()).payload
    initial = automation_view(f.policy, "run")
    preview = f.policy.preview("run", ASK)
    grant, body = approve(f)
    pause(f, grant)
    return {"read": reading(), "initial": initial, "preview": preview,
            "paused": automation_view(f.policy, "run"), "body": body}


def test_actual_marked_run_preview_and_paused_authority_are_admitted_without_mutating_frozen_config(tmp_path):
    result = js("""
      const before=JSON.stringify(p.read);
      const admitted=boundary.projectRunRead(p.read);
      console.log(JSON.stringify([Boolean(admitted), Boolean(model.projectAutomationPreview(p.preview,p.read)),
        Boolean(model.projectAutomation(p.paused,p.read)), JSON.stringify(p.read)===before,
        admitted?.config.automationContract]));
    """, wire(tmp_path))
    assert result == [True, True, True, True, "bounded-run-v1"]


@pytest.mark.parametrize("mutation", [
    "p.read.config.automation_contract=null", "p.read.config.automation_contract='future'",
    "p.read.run.mode='confirm'", "delete p.read.config.workflow",
    "p.preview.terms.config_digest='sha256:'+'0'.repeat(64)",
    "p.preview.terms.node_limits[0].node_id='another-step'",
    "p.preview.provider_facts={providers:[]}",
    "p.paused.control.authorization_digest='sha256:'+'0'.repeat(64)",
    "p.paused.remaining_actions+=1", "p.paused.next_node_id='missing-step'",
])
def test_foreign_or_falsified_authority_never_becomes_a_readable_permission(tmp_path, mutation):
    result = js(mutation + "; console.log(JSON.stringify([Boolean(boundary.projectRunRead(p.read)),"
                "Boolean(model.projectAutomationPreview(p.preview,p.read)),"
                "Boolean(model.projectAutomation(p.paused,p.read))]));", wire(tmp_path))
    assert not all(result)


def test_delayed_read_cannot_cross_run_or_disconnect_and_repeated_refreshes_are_serial(tmp_path):
    result = js("""
      let selected='run', ready=true, pending=[], writes=0, active=0, maximum=0;
      const f=flow.automationFlow({selected:()=>selected,ready:()=>ready,changed:()=>{},
        stop:()=>({abort(){}}),read:(id)=>new Promise(resolve=>{active++;maximum=Math.max(maximum,active);
          pending.push({id,resolve:(value)=>{active--;resolve(value)}})}),write:()=>{writes++}});
      const tick=()=>new Promise(resolve=>setImmediate(resolve));
      f.sync(p.read); f.edit('actor','Do not erase'); f.refresh(); f.refresh();
      selected='other';const other=structuredClone(p.read);other.run.run_id=selected;
      f.sync(other);pending.shift().resolve(p.initial);await tick();
      const second=pending.shift();second.resolve({...p.initial,run_id:'other'});await tick();
      const after=[f.snapshot().runId,f.snapshot().view.run_id];
      f.edit('actor','Other draft'); f.refresh();ready=false;f.disconnect();
      pending.shift().resolve({...p.initial,run_id:'other'});await tick();
      console.log(JSON.stringify({after,phase:f.snapshot().phase,actor:f.snapshot().draft.actor,maximum,writes}));
    """, wire(tmp_path))
    assert result == {"after": ["other", "other"], "phase": "disconnected", "actor": "Other draft",
                      "maximum": 1, "writes": 0}


def test_unknown_authorization_is_confirmed_only_by_matching_durable_terms(tmp_path):
    payload = wire(tmp_path)
    result = js("""
      let replies=p.initial,writes=[];
      const f=flow.automationFlow({selected:()=> 'run',ready:()=>true,changed:()=>{},
        stop:()=>({abort(){}}),read:async()=>replies,id:()=> 'grant',refreshRun:()=>{},
        write:async(target,id,body,carry,recover)=>{writes.push({target,body});
          if(target==='automationPreview')carry({status:'accepted',payload:p.preview});
          else {replies=p.paused;recover({status:'unknown'});}}});
      await f.sync(p.read);f.edit('actor','owner');await f.preview();await f.authorize();
      console.log(JSON.stringify({request:f.snapshot().request,notice:f.snapshot().notice,
        body:writes[1].body,targets:writes.map(row=>row.target)}));
    """, payload)
    assert result["request"] is None and result["notice"] == "recorded"
    assert result["body"] == payload["body"]
    assert result["body"]["authorization_id"] == "grant"
    assert result["body"]["authorized_by"] == "owner"
    assert result["targets"] == ["automationPreview", "automationAuthorize"]


def test_unknown_control_retry_keeps_identity_payload_and_actor_even_after_navigation(tmp_path):
    result = js("""
      let selected='run',writes=[],serial=0;
      const f=flow.automationFlow({selected:()=>selected,ready:()=>true,changed:()=>{},stop:()=>({abort(){}}),
        read:async()=>p.paused,id:()=>`control-${++serial}`,refreshRun:()=>{},
        write:async(target,id,body,carry,recover)=>{writes.push(structuredClone(body));recover({status:'unknown'})}});
      await f.sync(p.read);f.edit('actor','Original actor');await f.control('resume');
      f.clear();selected='away';selected='run';await f.sync(p.read);
      f.edit('actor','Changed actor');await f.retry();
      console.log(JSON.stringify({writes,serial,actor:f.snapshot().draft.actor,notice:f.snapshot().notice}));
    """, wire(tmp_path))
    assert result["writes"][0] == result["writes"][1]
    assert result["serial"] == 1 and result["actor"] == "Original actor"
    assert result["notice"] == "unknown"


def test_bounded_draft_preserves_only_an_explicit_valid_marker_and_both_locales_have_all_keys():
    result = js("""
      const legacy={schema_version:1,title:'User text',nodes:[],edges:[]};
      const marked={...legacy,execution_contract:'bounded-run-v1'};
      console.log(JSON.stringify([draft.draftFrom(legacy),draft.draftFrom(marked),
        draft.draftFrom({...legacy,execution_contract:null}),copy.validateMessages(copy.MESSAGES),
        copy.message('ru','automation.authorize'),copy.message('en','automation.authorize')]));
    """, {})
    assert "execution_contract" not in result[0]
    assert result[1]["execution_contract"] == "bounded-run-v1" and result[2] is None
    assert result[3:] == [True, "Разрешить ограниченный запуск", "Authorize bounded run"]


def test_real_provider_authority_facts_cross_the_preview_boundary_without_credentials(tmp_path):
    from conductor.command.adapters.provider import ProviderConfig
    from conductor.command.policy_providers import ProviderAuthority
    from tests.test_command_provider_contract import _contract
    f = setup(tmp_path)
    config = ProviderConfig("claude-code", "/opt/claude/bin/claude", "fake-claude-jsonl-v1",
                            env_allow=("ANTHROPIC_API_KEY",))
    authority = ProviderAuthority([config], [_contract(auth="api_key")], f.registry)
    f.policy.provider_digest = authority.digest
    f.policy.provider_facts = authority.facts
    payload = wire(tmp_path / "separate")
    payload["preview"] = f.policy.preview("run", ASK)
    result = js("""
      const accepted=Boolean(model.projectAutomationPreview(p.preview,p.read));
      p.preview.provider_facts.providers[0].config.credential='must never be displayed';
      console.log(JSON.stringify([accepted,model.projectAutomationPreview(p.preview,p.read)]));
    """, payload)
    assert result == [True, None]


def test_a_task_channel_fact_is_admitted_only_with_its_own_unit_scope_and_declared_channel(tmp_path):
    """Codex R2: the bound the grant freezes is read with its unit and scope, never as a bare number."""
    from conductor.command.adapters.provider import ProviderConfig
    from conductor.command.policy_providers import ProviderAuthority
    from tests.test_command_provider_contract import _contract
    f = setup(tmp_path)
    config = ProviderConfig("claude-code", "/opt/claude/bin/claude", "fake-claude-jsonl-v1",
                            env_allow=("ANTHROPIC_API_KEY",))
    authority = ProviderAuthority([config], [_contract(auth="api_key")], f.registry)
    f.policy.provider_digest = authority.digest
    f.policy.provider_facts = authority.facts
    payload = wire(tmp_path / "separate")
    payload["preview"] = f.policy.preview("run", ASK)
    result = js("""
      const row=p.preview.provider_facts.providers[0];
      const out=[row.task_channel===null, Boolean(model.projectAutomationPreview(p.preview,p.read))];
      const argv={channel:"argv",limit:32767,unit:"utf16_units",scope:"command_line"};
      const stdin={channel:"stdin",limit:262144,unit:"utf8_bytes",scope:"task"};
      const trial=(transport,value)=>{row.transport=transport; row.task_channel=value;
        return Boolean(model.projectAutomationPreview(p.preview,p.read));};
      out.push(trial({task_channel:"argv"},argv), trial({task_channel:"stdin"},stdin),
        trial({task_channel:"argv"},{...argv,unit:"utf8_bytes"}), trial({task_channel:"argv"},{...argv,scope:"task"}),
        trial({task_channel:"argv"},{...argv,limit:0}), trial({task_channel:"stdin"},argv),
        trial({},argv), trial({task_channel:"argv"},null), trial({task_channel:"argv"},{...argv,extra:1}));
      console.log(JSON.stringify(out));
    """, payload)
    assert result == [True, True, True, True, False, False, False, False, False, False, False]


def _drafted(definition):
    return js("console.log(JSON.stringify(model.automationDraft({graph: {definition: p}})));", definition)


def _limits(draft):
    return {row["node_id"]: (row["timeout_seconds"], row["max_attempts"]) for row in draft["node_limits"]}


def test_the_standard_draft_reserves_the_checker_and_shows_its_planned_correction_before_any_grant():
    from tests.test_command_graph_dalio import shipped

    draft = _drafted(shipped("dalio-v5").as_dict())
    assert _limits(draft) == {"goal": ("300", "1"), "identify": ("300", "1"), "diagnose": ("300", "1"),
                              "design": ("300", "1"), "do": ("300", "2")}
    # `do` and its checker reserve 2 x 300; five planned steps plus the one correction.
    assert (draft["max_actions"], draft["max_action_seconds"], draft["max_total_task_seconds"]) == (
        "6", "600", "2400")
    assert draft["duration_seconds"] == "3600" and draft["actor"] == ""


def test_a_plain_plan_is_drafted_without_a_checker_reservation_or_a_correction():
    from tests.test_command_graph_dalio import shipped

    draft = _drafted(shipped("dalio-v3").as_dict())
    assert set(_limits(draft).values()) == {("300", "1")}
    assert (draft["max_actions"], draft["max_action_seconds"], draft["max_total_task_seconds"]) == (
        "5", "300", "1500")


def test_the_draft_never_exceeds_a_frozen_timeout_or_attempt_bound():
    definition = {"nodes": [
        {"node_id": "do", "kind": "task", "capability": "dispatch", "instance_id": "doer",
         "verifier_instance_id": "checker", "timeout_seconds": 120, "attempt_bound": 1},
        {"node_id": "again", "kind": "loop", "loop": {"bound": 3, "back_to": "do"}}],
        "edges": [{"from_node": "do", "to_node": "again", "condition": "on_failed"}]}
    draft = _drafted(definition)
    assert _limits(draft) == {"do": ("120", "1")}
    assert (draft["max_actions"], draft["max_action_seconds"], draft["max_total_task_seconds"]) == (
        "1", "240", "240")


def test_a_persons_edited_budget_survives_a_reread_and_a_trip_to_another_run(tmp_path):
    result = js("""
      let selected='run';
      const f=flow.automationFlow({selected:()=>selected,ready:()=>true,changed:()=>{},stop:()=>({abort(){}}),
        read:async()=>p.paused,id:()=>'control-1',refreshRun:()=>{},write:async()=>{}});
      await f.sync(p.read);
      const drafted=f.snapshot().draft.max_actions;
      f.edit('max_actions','5');f.edit('timeout_seconds','45','do');
      await f.sync(p.read);
      const reread=[f.snapshot().draft.max_actions,f.snapshot().draft.node_limits[0].timeout_seconds];
      f.clear();selected='away';selected='run';await f.sync(p.read);
      console.log(JSON.stringify({drafted,reread,back:[f.snapshot().draft.max_actions,
        f.snapshot().draft.node_limits[0].timeout_seconds]}));
    """, wire(tmp_path))
    assert result["drafted"] != "5"
    assert result["reread"] == ["5", "45"] and result["back"] == ["5", "45"]
