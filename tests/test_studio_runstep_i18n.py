"""Locale changes display but cannot change a proposed or confirmed request."""
import json
import shutil
import subprocess

import pytest

from tests.test_studio_agents_i18n import DOM, PANEL


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_step_locale_retains_wire_facts_and_actor_refusal(locale):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for the localized rendering boundary")
    module = json.dumps((PANEL / "studio-runstep.js").as_uri())
    script = f"import {{stepControls}} from {module};\n" + DOM + """
      const locale=LOCALE, argument={item:'keep-item',instruction_ref:'keep-guide',
        artifact_refs:['keep-input'],literal:'User <b> {ref} Не переводить'};
      const node={node_id:'keep-node',instance_id:'keep-instance',capability:'dispatch',
        title:'User <b> {ref} title',arguments:argument,timeout_seconds:123};
      const proposal={proposal_id:'keep-proposal',preview_digest:'keep-preview',
        config_digest:'keep-config',node_id:node.node_id,instance_id:node.instance_id,
        capability:node.capability,arguments:argument,scope:['keep-scope'],
        input_binding:'proposal-v1',proposed_at:'2026-09-21T12:00:00Z',
        proposed_by:'keep-author',rationale:'User <b> {ref} reason',timeout_seconds:123};
      const detail={run:{run_id:'keep-run',mode:'confirm',workflow_id:'keep-workflow'},
        controls:{instances:[{instance_id:node.instance_id,controls:['dispatch']}]},records:[]};
      const state={locale,connection:'open',runs:{writes:{},step:{nodeId:node.node_id,
        generation:7,proposedBy:'keep-author',confirmedBy:'keep-confirmer',
        rationale:proposal.rationale}}};
      let submitted=null;
      const handlers={chooseStep(){},editStep(){},proposeStep:x=>submitted=x,
        confirmStep:x=>submitted=x};
      const cases=[];
      for(const phase of ['idle','proposed']) {
        detail.records=phase==='idle'?[]:[{record_type:'action_proposal',record:proposal}];
        const before=JSON.stringify({node,detail,state});
        const [form]=stepControls(node,{phase,attempt_ids:[]},{state:'runnable'},detail,state,handlers);
        form.events.submit({preventDefault(){}});
        cases.push({phase,text:form.textContent,submitted,
          unchanged:before===JSON.stringify({node,detail,state}),
          disabled:all(form).find(x=>x.tag==='button').disabled,
          html:all(form).some(x=>x.tag==='b'),
          inputs:all(form).filter(x=>x.tag==='input').map(x=>x.value)});
        const field=phase==='idle'?'proposedBy':'confirmedBy', old=state.runs.step[field];
        state.runs.step[field]='bad actor';submitted=null;
        const [refused]=stepControls(node,{phase,attempt_ids:[]},{state:'runnable'},detail,state,handlers);
        refused.events.submit({preventDefault(){}});
        cases.at(-1).refusal={text:refused.textContent,submitted,
          disabled:all(refused).find(x=>x.tag==='button').disabled};
        state.runs.step[field]=old;
      }
      console.log(JSON.stringify(cases));
    """.replace("LOCALE", json.dumps(locale))
    result = subprocess.run([node, "--input-type=module", "-e", script],
        capture_output=True, text=True, encoding="utf-8", timeout=15, check=False)
    assert result.returncode == 0, result.stderr
    proposed, confirmed = json.loads(result.stdout)
    argument = {"item": "keep-item", "instruction_ref": "keep-guide",
        "artifact_refs": ["keep-input"], "literal": "User <b> {ref} Не переводить"}
    common = {"runId": "keep-run", "nodeId": "keep-node", "generation": 7}
    assert proposed["submitted"] == {**common, "body": {
        "instance_id": "keep-instance", "attempt_id": "attempt-keep-node-0",
        "capability": "dispatch", "arguments": argument, "scope": ["src"],
        "proposed_by": "keep-author", "rationale": "User <b> {ref} reason",
        "timeout_seconds": 123, "node_id": "keep-node"}}
    assert confirmed["submitted"] == {**common, "body": {
        "proposal_id": "keep-proposal", "preview_digest": "keep-preview",
        "capability": "dispatch", "scope": ["keep-scope"],
        "config_digest": "keep-config", "confirmed_by": "keep-confirmer"}}
    assert ("Предложить этот шаг" if locale == "ru" else "Propose this step") in proposed["text"]
    assert ("Подтвердить это предложение" if locale == "ru" else "Confirm this proposal") in confirmed["text"]
    assert "User <b> {ref} reason" in proposed["inputs"]
    assert "User <b> {ref} reason" in confirmed["text"]
    for rendered in (proposed, confirmed):
        assert rendered["unchanged"] and not rendered["disabled"] and not rendered["html"]
        assert "keep-guide" in rendered["text"] and "keep-input" in rendered["text"]
        assert rendered["refusal"]["disabled"] and rendered["refusal"]["submitted"] is None
        assert ("не более 128 символов" if locale == "ru" else "up to 128 characters") in rendered["refusal"]["text"]
