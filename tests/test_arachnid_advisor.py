"""The Atlas advisor has exactly one review subject and its own authority."""
from tests.desk_wizard_node import run_js


MODULES = {"atlas": "arachnid-advisor.js"}


def test_open_binds_input_to_a_new_session_and_admitted_subscription_without_a_write():
    result = run_js("""
      const codex = {provider_id:"codex", auth:"subscription", offered:true,
        availability:"available",task_road:"boundary",controls:["review","dispatch"],
        model_pin_supported:true};
      const grok = {...codex, provider_id:"grok-build", model_pin_supported:false};
      const args = {projectId:"a".repeat(32),sessionId:"new/1", text:"repair the counter",
        provider:"codex",model:"gpt-6.1-sol",input:{language:"en",providers:[codex,grok]}};
      const writes = [];
      const input = atlas.createArachnidAdvisor({valid:()=>true,refresh:()=>{},saveReference:()=>{},
        readJson:()=>{throw Error("unexpected read")},write:(...a)=>writes.push(a)});
      const first = input.open(args);
      const same = input.open(args);
      const next = input.open({...args,text:"different problem"});
      const other = input.open({...args,projectId:"b".repeat(32)});
      const denied = input.open({...args,input:{language:"en",
        providers:[{...codex,auth:"api_key"}]}});
      console.log(JSON.stringify([first.phase,first.runId,same.runId,next.runId,other.runId,
        first.brief,first.provider,first.model,denied.phase,denied.issue,writes.length]));
    """, modules=MODULES)
    phase, run, same, different, other, brief, provider, model, failure, issue, writes = result
    assert phase == "draft" and run == same and len({run, different, other}) == 3
    assert (brief, provider, model) == ("repair the counter", "codex", "gpt-6.1-sol")
    assert (failure, issue, writes) == ("failed", "advice_unavailable", 0)


def test_registry_caps_roles_and_never_infers_grok_from_its_installation_name():
    output = run_js("""
      const codex = {provider_id:"codex",auth:"subscription",offered:true,
        availability:"available",task_road:"review_only",controls:["review"],
        model_pin_supported:true};
      const a = atlas.createArachnidAdvisor({valid:()=>true,refresh(){},saveReference(){}});
      const open = rows => a.open({sessionId:"new/1",projectId:"c".repeat(32),text:"task",
        provider:"codex",model:"gpt-6.1-sol",input:{language:"en",providers:rows}});
      const missing = open([codex,{...codex,provider_id:"grok-build",offered:false}]);
      const full = open([{...codex,task_road:"boundary",controls:["review","dispatch"]},
        {...codex,provider_id:"grok-build"}]);
      console.log(JSON.stringify([missing.input.role_options,full.input.role_options,full.input]));
    """, modules=MODULES)
    missing, full, brief = output
    assert missing["role-implementer"] == [] and missing["role-diagnostician"] == []
    assert full["role-implementer"] == ["codex"] and full["role-diagnostician"] == ["grok-build"]
    assert full["role-checker"] == ["codex"] and brief["current_cycle"] == "dalio-v6"
    assert "c"*32 not in str(brief)


# The store double projects the flow actually published by the stock advisor. It intercepts a
# grant only after persistence; on the next read its effect exists although its answer was lost.
STORE = """
const project = "c".repeat(32), source = "new/1", pin = "gpt-6.1-sol";
const coder = {provider_id:"codex",auth:"subscription",offered:true,availability:"available",
  task_road:"boundary",controls:["dispatch","review"],model_pin_supported:true};
const args = {sessionId:source, projectId:project, text:"Repair the counter",provider:"codex",
  model:pin,input:{language:"en",providers:[coder,{...coder,provider_id:"grok-build"}]}};
let doc, run, auth, requestRef, live=true, grants=0, decisions=0, quota=95;
const accepted = payload => ({status:"accepted",payload});
const wrapper = (record_type,record) => ({record_type,record});
const io = {valid:(p,s)=>live && s===source && p===project, refresh(){},
  saveReference(ref){requestRef=ref;},
  async readJson(url) {
    if(url.endsWith("/command/quotas")) return {snapshots:[{binding_ids:["codex"],
      state:"observed",freshness:"current",
      windows:[{freshness:"current",remaining_percent:quota}]}]};
    if(url.endsWith("/revisions/1")) return {document:doc};
    if(url.includes("/workflows/")) return {draft:null,revisions:doc?[1]:[]};
    if(url.endsWith("/automation")) return {authorization:auth,state:auth?"running":"ready"};
    if(url.includes("/runs/")) return structuredClone(run);
    throw Error("unexpected_read");
  },
  async write(command,subject,b) {
    if (command==="flow") {
      const [s,g] = b.source.flow.steps;
      doc = {schema_version:1,title:b.source.flow.title,template_id:subject,revision:1,
        execution_contract:"bounded-run-v1",nodes:[
          {node_id:s.step_id,kind:"task",title:s.title,role_id:s.role_id,purpose:s.purpose,
           capability:s.capability,timeout_seconds:s.timeout_seconds,
           attempt_bound:s.ext.attempt_bound,arguments:s.ext.arguments,resources:[]},
          {node_id:g.step_id,kind:"gate",title:g.title,gate_id:g.ext.gate_id,
           success_requires:"human_approval",resources:[]}],
        edges:[{from_node:s.step_id,to_node:g.step_id,condition:"on_succeeded"}]};
    } else if (command==="runs" && !run) {
      const n=doc.nodes[0], node={...n,instance_id:"instance-advisor",
        arguments:{...n.arguments,work_scope:b.run_id,step_purpose:n.purpose}};
      run={run:{run_id:b.run_id,mode:"policy"},config:{task:{id:b.task_id,work_scope:b.task_id},
        workflow:{id:b.workflow_id,revision:b.revision},instances:[{id:"instance-advisor",
          adapter:"codex",model:pin}]},records:[wrapper("graph_definition",
          {nodes:[node,doc.nodes[1]],edges:doc.edges})],
        graph:{situation:{gates:[
          {gate_id:"advice-result",answerable:"first",needs_decision:true}]}}};
    } else if (command==="artifacts") run.records.push(wrapper("artifact",{...b,run_id:subject}));
    else if (command==="automationPreview") return accepted({terms:b,preview_digest:"digest",
      valid_until:new Date(Date.now()+60000).toISOString()});
    else if (command==="automationAuthorize") {
      grants++; auth={...b,...b.terms,run_id:subject,authorization_digest:"granted",
        authorized_at:"2026-01-01T00:00:00Z",expires_at:"2026-01-01T00:15:00Z"};
      run.records.push(wrapper("run_authorization",auth));
      return {status:"unknown"};
    } else if (command==="decisions") {decisions++;run.records.push(wrapper("decision",b));}
    else if (!["tasks","runs"].includes(command)) throw Error("unexpected_write");
    return accepted({});
  }};
"""


ACCEPTED = STORE + """
const a=atlas.createArachnidAdvisor(io), stages=[];
const snap=a.open(args); stages.push(snap.phase);
stages.push((await a.prepare()).phase);
quota=0; const zero=await a.grant("owner");
quota=95; const attempts=await Promise.all([a.grant("owner"),a.grant("owner")]);
stages.push(a.state().phase);
const b=atlas.createArachnidAdvisor(io);
stages.push((await b.restore(requestRef)).phase);
const sourceDoc=run.records.find(row=>row.record_type==="artifact").record;
if (d.case === "inflated") auth.max_actions=2;
const act={action_id:"A",run_id:snap.runId,node_id:"advise",attempt_id:"attempt-A",
  run_authorization_id:auth.authorization_id,run_authorization_digest:auth.authorization_digest,
  instance_id:"instance-advisor"};
run.records.push(wrapper("action_request",act),wrapper("action_result",{...act,
  outcome:d.case==="expired"?"failed":"succeeded",
  detail:"the Codex CLI login is not ready for an isolated attempt: expired"}));
const ans={criterion:"A checked count",question:null,cycle_id:"dalio-v6",
  roles:{"role-diagnostician":"grok-build"},depth:"balanced"};
run.records.push(wrapper("artifact",{run_id:snap.runId,artifact_ref:"draft-suggestion",
  media_type:"text/markdown",source_action_id:"A",content:JSON.stringify(ans),
  input_artifact_ids:[d.case==="forged"?"BAD":sourceDoc.artifact_id]}));
const done=await b.tick(); stages.push(done.phase);
await b.decide("approve");
const c=atlas.createArachnidAdvisor(io); const restored=await c.restore(requestRef);
"""


WIRE = ACCEPTED + """
console.log(JSON.stringify({stages,zero:[zero.phase,zero.issue],done:done.issue,
  restored:[restored.phase,restored.proposal?.criterion],grants,decisions}));
"""


def test_lost_grant_reload_and_acceptance_never_dispatch_twice():
    out = run_js(WIRE, {"case": "ok"}, modules=MODULES)
    assert out == {"stages": ["draft", "preview", "recover", "running", "result"],
                   "zero": ["preview", "quota_exhausted"], "done": None,
                   "restored": ["accepted", "A checked count"], "grants": 1, "decisions": 1}


def test_foreign_grant_wrong_lineage_and_expired_login_have_no_answer_or_retry():
    for case, error in (("forged", "advice_unsuccessful"), ("inflated", "run_conflict"),
                        ("expired", "advice_login_unavailable")):
        out = run_js(WIRE, {"case": case}, modules=MODULES)
        assert out["done"] == error and out["stages"][-1] == "failed"
        assert out["grants"] == 1 and out["decisions"] == 0 and out["restored"] == ["failed", None]


def test_session_switch_while_rereading_grant_never_sends_the_pending_paid_request():
    out = run_js(STORE + """
      const a=atlas.createArachnidAdvisor(io);
      a.open(args); await a.prepare();
      const original=io.readJson; let release, notify;
      const reached=new Promise(resolve=>notify=resolve);
      io.readJson=async url=>{
        if(url.endsWith("/automation")) {notify(); await new Promise(resolve=>release=resolve);}
        return original(url);
      };
      const pending=a.grant("owner");
      await reached;
      live=false; a.close(); release();
      await pending;
      console.log(JSON.stringify([grants,a.state().phase,a.state().brief]));
    """, modules=MODULES)
    assert out == [0, "idle", ""]


def test_recovery_checks_stored_source_and_never_adopts_another_drafts_report():
    out = run_js(STORE + """
      const a=atlas.createArachnidAdvisor(io);
      a.open(args); await a.prepare();
      const another=atlas.createArachnidAdvisor({...io,valid:()=>true});
      const own=atlas.planningSession(run,project);
      const foreign=atlas.planningSession(run,"d".repeat(32));
      const wrong=await another.restore({...requestRef,sessionId:"new/other"});
      const inp=run.records.find(r=>r.record_type==="artifact").record;
      const modified=JSON.parse(inp.content); modified.authorize=true;
      inp.content=JSON.stringify(modified);
      const broken=await a.restore({...requestRef,projectId:"1".repeat(32)});
      const corrupt=await another.restore(requestRef);
      console.log(JSON.stringify([own,foreign,atlas.planningSession(run,project),
        wrong.issue,broken.issue,corrupt.issue,grants,decisions]));
    """, modules=MODULES)
    assert out == ["new/1", None, None, "run_conflict", "run_conflict", "run_conflict", 0, 0]
