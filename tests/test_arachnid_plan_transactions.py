"""A lost write is reconciled; only an explicit main confirmation may send a grant."""
import json

from conductor.command.workflow_draft import starters
from tests.desk_wizard_node import run_js
from tests.test_arachnid_advisor import ACCEPTED
from tests.test_arachnid_plan import GIT, PROVIDERS


MODULES = {"atlas": "arachnid-advisor.js", "plan": "arachnid-plan.js",
           "digest": "desk-wizard-digest.js"}
PORT = """
const req = {advisorId: restored.runId, projectId:project, proposal:restored.proposal,
  brief:args.text, actor:"owner", locale:"en"};
const sha = "sha256:" + "d".repeat(64);
let draft=null, rev=null, target=null, task=null, seed=null, grant=null, allow=true;
let writes=[], revisionHeads=0;
function check(x) { if(!x) throw Error("unexpected_port"); }
const main = {
  valid:()=>allow,
  async read(url) {
    if (url.includes(req.advisorId)) return io.readJson(url);
    if (url==="/command/project") return {project_id:project,mode:"active"};
    if (url==="/command/workflows") return d.catalog;
    if (url==="/command/project/git") return d.git;
    if (url==="/command/tasks") return {tasks:task?[task]:[]};
    if (url.endsWith("/preparation")) return {task,seed};
    if (url.endsWith("/revisions/1")) return {document:rev};
    if (url.startsWith("/command/workflows/"))
      return {draft,revisions:rev?[1]:[],publishable:!!draft,
        diagnostics:[],unreadable_revisions:[]};
    if (url==="/command/runs") return {runs:target?[target.run]:[]};
    if (url.endsWith("/automation"))
      return {run_id:target.run.run_id,authorization:grant,spent_actions:0,active_action_id:null};
    if (url.startsWith("/command/runs/")) return structuredClone(target);
    throw Error("unexpected_read");
  },
  async submit(name, subject, body) {
    writes.push(name);
    if (name==="draft") draft={document:body.document,digest:sha};
    else if(name==="revisions") { check(draft.digest===body.reviewed_digest);
      rev={...draft.document,template_id:subject,revision:1};draft=null;revisionHeads++; }
    else if(name==="tasks") task=body;
    else if(name==="seed") seed={...body,task_id:subject,work_scope:subject,
      base_commit:body.expect_commit,state:"seeded"};
    else if(name==="runs") {
      const nodes=rev.nodes.map(node=>{
        const {role_id,verifier_role_id,...n}=node;
        if(role_id){ n.instance_id=body.assignments[role_id];
          n.arguments={...node.arguments,work_scope:task.task_id};
          if(n.purpose) n.arguments.step_purpose=n.purpose; }
        if(verifier_role_id) n.verifier_instance_id=body.assignments[verifier_role_id];
        return n;
      });
      const instances=body.participants.map(p=>({id:p.instance_id,adapter:p.provider_id,
        ...(p.model?{model:p.model}:{})}));
      target={run:{run_id:body.run_id,cycle_id:body.cycle_id,mode:"policy",config_digest:sha},
        warnings:[],config:{automation_contract:"bounded-run-v1",instances,
          task:{id:task.task_id,work_scope:task.task_id}, workflow:{id:rev.template_id,revision:1}},
        records:[wrapper("graph_definition",{run_id:body.run_id,execution_contract:"bounded-run-v1",
          nodes,edges:rev.edges})]};
    } else if(name==="artifacts") target.records.push(wrapper("artifact",
      {...body,run_id:subject,source_action_id:null}));
    else if(name==="automationPreview") return accepted({terms:{...body,run_id:subject,
      graph_digest:sha,config_digest:sha,source_prefix_digest:sha,provider_config_digest:sha},
      preview_digest:sha,patch_steps:["do"],valid_until:new Date(Date.now()+120000).toISOString()});
    else if(name==="automationAuthorize") {
      const {duration_seconds,...fields}=body.terms;
      check(body.preview_digest===sha);
      grant={...fields,authorized_by:body.authorized_by,authorization_id:body.authorization_id,
        authorized_at:"2026-11-09T01:00:00Z",expires_at:"2026-11-09T03:00:00Z"};
    } else throw Error("unexpected_write");
    return {status:"unknown"};
  }
};
"""


def exercise(body, *, brief="Repair the counter"):
    data = {"case": "ok", "catalog": {"starters": starters(), "providers": PROVIDERS}, "git": GIT}
    setup = ACCEPTED.replace('text:"Repair the counter"', "text:" + json.dumps(brief))
    return run_js(setup + PORT + body, data, modules=MODULES)


def test_restore_of_an_older_instruction_keeps_its_original_source_scope():
    out = exercise("""
      const first=await plan.prepareDalio(main,req);
      const instruction=target.records.find(r=>r.record.artifact_ref==="instruction-plan").record;
      instruction.content=instruction.content.split("\\n\\nconduct.patch-sources.v1")[0];
      instruction.artifact_id=digest.documentId(target.run.run_id,
        "instruction-plan","text/plain",instruction.content);
      let refused=null;
      try{await plan.authorizeDalio(main,first,"owner");}catch(e){refused=e.message;}
      const old=await plan.prepareDalio(main,req);
      await plan.authorizeDalio(main,old,"owner");
      const reopened=await plan.restoreDalio(main,req);
      console.log(JSON.stringify({first:first.sourcePaths,refused,restored:reopened.sourcePaths}));
    """, brief="Repair runstats/counts.py and tests/test_counts.py.")
    assert out == {"first": ["runstats/counts.py", "tests/test_counts.py"],
                   "refused": "input_conflict", "restored": []}


def test_lost_responses_reconcile_drafts_seeds_inputs_and_grants_under_the_same_ids():
    out = exercise("""
      const first=await plan.prepareDalio(main,req), again=await plan.prepareDalio(main,req);
      const before=writes.slice();
      if(await plan.observeDalio(main,first,"owner")!==null) throw Error("premature");
      const launched=await plan.authorizeDalio(main,again,"owner");
      const count=writes.length, recovered=await plan.observeDalio(main,first,"owner");
      if(writes.length!==count || recovered.authorization_id!==grant.authorization_id)
        throw Error("recovery_wrote");
      const repeated=await plan.authorizeDalio(main,first,"owner");
      const reloaded=await plan.prepareDalio(main,req);
      console.log(JSON.stringify({before,grants:writes.filter(v=>v==='automationAuthorize').length,
        revisionHeads,phase:launched.phase,repeated:repeated.phase,reloaded:reloaded.phase,
        same:first.runId===again.runId && reloaded.runId===first.runId}));
    """)
    assert out["before"] == ["draft", "revisions", "tasks", "seed", "runs", "artifacts",
                             "artifacts", "automationPreview", "automationPreview"]
    assert out["grants"] == out["revisionHeads"] == 1 and out["same"]
    assert out["phase"] == out["repeated"] == out["reloaded"] == "authorized"


def test_changed_input_graph_commit_and_session_refuse_without_a_grant():
    out = exercise("""
      const first=await plan.prepareDalio(main,req);
      const fails=async f=>{try{await f();return "ok"}catch(e){return e.message}};
      const call=()=>plan.authorizeDalio(main,first,"owner");
      const raw=target.records.at(-1).record.content;
      target.records.at(-1).record.content="foreign";
      const file=await fails(call); target.records.at(-1).record.content=raw;
      const checker=target.records[0].record.nodes.find(n=>n.node_id==="do");
      checker.verifier_instance_id=checker.instance_id;
      const graph=await fails(call); checker.verifier_instance_id="instance-role-checker";
      const base=d.git.git.head.commit;d.git.git.head.commit="f".repeat(40);
      const head=await fails(call);d.git.git.head.commit=base;
      allow=false;const lost=await fails(call);
      console.log(JSON.stringify({file,graph,head,lost,grant}));
    """)
    assert out == {"file": "input_conflict", "graph": "run_conflict", "head": "source_changed",
                   "lost": "session_changed", "grant": None}


def test_advice_for_another_brief_or_session_cannot_touch_the_project():
    out = exercise("""
      const refuses=async request=>{
        try{await plan.prepareDalio(main,request);return "ok"}catch(e){return e.message}
      };
      const another=await refuses({...req,brief:"a different task"});
      const session=await refuses({...req,sessionId:"new/another"});
      const forged=await refuses({...req,proposal:{...req.proposal,criterion:"foreign"}});
      console.log(JSON.stringify({another,session,forged,writes}));
    """)
    assert out == {"another": "proposal_invalid", "session": "proposal_invalid",
                   "forged": "proposal_invalid", "writes": []}


def test_restore_reads_existing_grant_even_when_head_language_and_availability_change():
    out = exercise("""
      const onlyRead={read:main.read,valid:main.valid,submit(){throw Error("restore wrote")}};
      const absent=await plan.restoreDalio(onlyRead,req);
      const first=await plan.prepareDalio(main,req);
      const inert=await plan.restoreDalio(onlyRead,req);
      await plan.authorizeDalio(main,first,"owner");
      d.git.git.head.commit="f".repeat(40);d.catalog.providers=[];
      const before=writes.length;
      const found=await plan.restoreDalio(onlyRead,{...req,locale:"ru",sessionId:source});
      console.log(JSON.stringify({absent,inert,phase:found.phase,sha:found.baseCommit,
        original:first.runId===found.runId,grant:found.authorization.authorization_id,
        expected:grant.authorization_id,additionalWrites:writes.length-before}));
    """)
    assert out["absent"] is None and out["inert"] is None
    assert out["phase"] == "authorized" and out["sha"] == GIT["git"]["head"]["commit"]
    assert out["original"] and out["grant"] == out["expected"] and out["additionalWrites"] == 0
