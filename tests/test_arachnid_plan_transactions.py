"""A lost write is reconciled; only an explicit main confirmation may send a grant."""
import copy
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


def legacy_document():
    """The pre-review-sources document, built from shipped data and literal old transforms."""
    source = next(row["document"] for row in starters() if row["starter_id"] == "dalio-v6")
    nodes = copy.deepcopy(source["nodes"])
    for node in nodes:
        if node["kind"] != "task":
            continue
        args = node["arguments"]
        if node["node_id"] == "do":
            args["profile"] = "implement-patch-v1"
            args["artifact_refs"] = ["artifact-plan", "artifact-brief"]
        elif "artifact-brief" not in args["target_artifact_refs"]:
            args["target_artifact_refs"].append("artifact-brief")
        node["timeout_seconds"] = 600
        node["attempt_bound"] = 1
    return {"schema_version": source["schema_version"], "title": "Dalio · Codex and Grok",
            "execution_contract": "bounded-run-v1", "nodes": nodes, "edges": source["edges"]}


def exercise(body, *, brief="Repair the counter"):
    data = {"case": "ok", "catalog": {"starters": starters(), "providers": PROVIDERS}, "git": GIT,
            "legacy": legacy_document()}
    setup = ACCEPTED.replace('text:"Repair the counter"', "text:" + json.dumps(brief))
    return run_js(setup + PORT + body, data, modules=MODULES)


def test_one_correction_is_frozen_in_the_same_workflow_before_and_after_the_grant():
    out = exercise("""
      const choice = {...req, allowCorrection:true};
      const prepared = await plan.prepareDalio(main,choice);
      const ids = [prepared.workflowId,prepared.taskId,prepared.runId];
      const bounds = rev.nodes.filter(n=>n.kind==="task").map(n=>[n.node_id,n.attempt_bound]);
      const onlyRead = {...main,submit(){throw Error("restore wrote")}};
      const saved = await plan.readDalioChoice(onlyRead,req);
      const start = writes.length;
      let conflict = null;
      try{await plan.prepareDalio(main,{...req,allowCorrection:false});}
      catch(e){conflict=e.message;}
      const changed = writes.length-start;
      const resumed = await plan.prepareDalio(main,req);
      const before = Boolean(grant);
      await plan.authorizeDalio(main,resumed,"owner");
      const reopened=await plan.restoreDalio(onlyRead,req);
      console.log(JSON.stringify({bounds,saved,conflict,changed,before,
        grants:writes.filter(v=>v==="automationAuthorize").length, ids,
        restored:[reopened.workflowId,reopened.taskId,reopened.runId],
        limits:prepared.terms.node_limits.map(r=>[r.node_id,r.max_attempts]),
        budget:[reopened.limits.max_actions,reopened.limits.max_total_task_seconds],
        equal:JSON.stringify(prepared.limits)===JSON.stringify(resumed.limits)}));
    """)
    stages = ("goal", "identify", "diagnose", "design", "do")
    bounds = [[node, 2 if node == "do" else 1] for node in stages]
    assert out["bounds"] == out["limits"] == bounds
    assert out["saved"] and out["conflict"] == "correction_conflict" and out["changed"] == 0
    assert not out["before"] and out["grants"] == 1
    assert out["budget"] == [6, 4800] and out["ids"] == out["restored"] and out["equal"]


def test_interrupted_draft_reopens_with_its_original_choice_and_incorrect_bounds_refuse():
    out = exercise("""
      const choice={...req,allowCorrection:true};
      const partial={...main,submit(name,subject,body){
        if(name==="revisions") return {status:"refused",code:"stopped"};
        return main.submit(name,subject,body);
      }};
      try{await plan.prepareDalio(partial,choice);}catch(e){if(e.message!=="stopped")throw e;}
      const saved=await plan.readDalioChoice(main,req);
      const node=draft.document.nodes.find(n=>n.node_id==="do");
      node.attempt_bound=3;
      let refused=null;
      try{await plan.prepareDalio(main,choice);}catch(e){refused=e.message;}
      console.log(JSON.stringify({saved,refused,rev,grant}));
    """)
    assert out == {"saved": True, "refused": "workflow_conflict", "rev": None, "grant": None}


def test_an_opt_in_cannot_expand_a_racing_single_pass_or_forge_its_preview():
    out = exercise("""
      // Both tabs reach expected_absent against the same empty workflow before either writes.
      let count=0, release, forged=null;
      const both=new Promise(resolve=>{release=resolve;});
      const race={...main, async submit(name,subject,body){
        if(name==="draft"){
          if(++count===2) release();
          await both;
          if(draft||rev) return {status:"refused", code:"draft_exists"};
        }
        return main.submit(name,subject,body);
      }};
      const [single,extra]=await Promise.allSettled([false,true].map(allowCorrection=>
        plan.prepareDalio(race,{...req,allowCorrection})));
      const saved=await plan.readDalioChoice(main,req);
      const prepared=single.value;
      const copy=structuredClone(prepared);
      copy.terms.max_actions=6; copy.terms.max_total_task_seconds=4800;
      try{await plan.authorizeDalio(main,copy,"owner");}
      catch(e){forged=e.message;}
      console.log(JSON.stringify({raced:extra.reason.message,forged,saved,revisionHeads,grant,
        original:prepared.terms.max_actions,attempts:writes.filter(w=>w==="automationAuthorize")}));
    """)
    assert out == {"raced": "workflow_conflict", "forged": "preview_changed", "saved": False,
                   "revisionHeads": 1, "grant": None, "original": 5, "attempts": []}


def test_raced_published_revision_cannot_change_the_chosen_mode_or_create_a_task():
    out = exercise("""
      const swapped={...main,async submit(name,subject,body){
        const result=await main.submit(name,subject,body);
        if(name==="revisions"){
          rev=structuredClone(rev);
          rev.nodes.find(n=>n.node_id==="do").attempt_bound=2;
        }
        return result;
      }};
      let error=null;
      try{await plan.prepareDalio(swapped,{...req,allowCorrection:false});}
      catch(e){error=e.message;}
      console.log(JSON.stringify({error,writes,task,grant}));
    """)
    assert out == {"error": "workflow_conflict", "writes": ["draft", "revisions"],
                   "task": None, "grant": None}


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


def test_coding_plan_reconciles_source_input_once_and_restore_keeps_its_bytes():
    out = exercise("""
      const first=await plan.prepareDalio(main,req);
      const again=await plan.prepareDalio(main,req);
      const sourceRows=target.records.filter(r=>r.record_type==="artifact"
        && r.record.artifact_ref==="source-context");
      const sourceText=sourceRows[0]?.record.content ?? null;
      const diagnosis=rev.nodes.find(n=>n.node_id==="diagnose");
      const before=JSON.stringify({rev,records:target.records});
      const automatic=writes.filter(name=>name==="automationAuthorize").length;
      await plan.authorizeDalio(main,again,"owner");
      const count=writes.length;
      const onlyRead={read:main.read,valid:main.valid,submit(){throw Error("restore wrote")}};
      const reopened=await plan.restoreDalio(onlyRead,req);
      console.log(JSON.stringify({sources:sourceRows.length,sourceText,
        refs:diagnosis.arguments.target_artifact_refs,automatic,
        unchanged:before===JSON.stringify({rev,records:target.records}),
        writesOnRestore:writes.length-count,
        grants:writes.filter(v=>v==="automationAuthorize").length,
        revisionHeads,same:first.runId===again.runId && reopened.runId===first.runId}));
    """, brief="Repair runstats/counts.py and tests/test_counts.py.")
    assert out["sources"] == 1
    assert out["sourceText"] == (
        '\n\nconduct.review-sources.v1\n["runstats/counts.py","tests/test_counts.py"]')
    assert out["refs"] == ["artifact-problems", "artifact-brief", "source-context"]
    assert out["automatic"] == out["writesOnRestore"] == 0
    assert out["grants"] == out["revisionHeads"] == 1
    assert out["same"] and out["unchanged"]


def test_literal_legacy_draft_and_revision_reopen_without_new_context_or_rewrites():
    out = exercise("""
      draft={document:structuredClone(d.legacy),digest:sha};
      const first=await plan.prepareDalio(main,req);
      const published=JSON.stringify(rev), inputs=JSON.stringify(target.records);
      const count=writes.length;
      const again=await plan.prepareDalio(main,req);
      const second=writes.slice(count);
      await plan.authorizeDalio(main,again,"owner");
      const beforeRestore=writes.length;
      const onlyRead={read:main.read,valid:main.valid,submit(){throw Error("restore wrote")}};
      const reopened=await plan.restoreDalio(onlyRead,req);
      console.log(JSON.stringify({context:target.records.filter(r=>r.record_type==="artifact"
        && r.record.artifact_ref==="source-context").length,
        literalInputs:Object.fromEntries(target.records.filter(r=>r.record_type==="artifact")
          .map(r=>[r.record.artifact_ref,r.record.content])),
        expected:JSON.stringify({...d.legacy,template_id:first.workflowId,revision:1})===published,
        unchanged:published===JSON.stringify(rev) && inputs===JSON.stringify(target.records),
        second,writesOnRestore:writes.length-beforeRestore,revisionHeads,
        same:first.runId===again.runId && reopened.runId===first.runId}));
    """, brief="Repair runstats/counts.py and tests/test_counts.py.")
    assert out.pop("literalInputs") == {
        "artifact-brief": "Repair runstats/counts.py and tests/test_counts.py.\n\nA checked count",
        "instruction-plan": (
            "Prepare a bounded patch for the accepted plan and brief. "
            "Modify only files in the task.\n\nconduct.patch-sources.v1\n"
            '["runstats/counts.py","tests/test_counts.py"]'),
    }
    assert out == {"context": 0, "expected": True, "unchanged": True,
                   "second": ["automationPreview"], "writesOnRestore": 0,
                   "revisionHeads": 1, "same": True}


def test_context_bytes_and_literal_legacy_graph_edits_still_refuse_without_a_grant():
    out = exercise("""
      const first=await plan.prepareDalio(main,req);
      const context=target.records.find(r=>r.record_type==="artifact"
        && r.record.artifact_ref==="source-context")?.record;
      const errors={};
      if(context){
        context.content="\\n\\nconduct.review-sources.v1\\n[\\"foreign.py\\"]";
        try{await plan.authorizeDalio(main,first,"owner");errors.input="accepted";}
        catch(error){errors.input=error.message;}
      }else errors.input="missing_context";
      draft={document:structuredClone(d.legacy),digest:sha};
      draft.document.nodes.find(n=>n.node_id==="diagnose").purpose="Foreign instruction";
      rev=null;target=null;task=null;seed=null;
      const before=writes.length;
      try{await plan.prepareDalio(main,req);errors.graph="accepted";}
      catch(error){errors.graph=error.message;}
      console.log(JSON.stringify({errors,writesAfterConflict:writes.length-before,grant}));
    """, brief="Repair runstats/counts.py and tests/test_counts.py.")
    assert out == {"errors": {"input": "input_conflict", "graph": "workflow_conflict"},
                   "writesAfterConflict": 0, "grant": None}
