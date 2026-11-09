"""The Atlas plan uses the shipped template and real server policy terms."""
from conductor.command.workflow_draft import starters
from tests.desk_node import run_js


MODULE = {"plan": "arachnid-plan-model.js"}
REQUEST = {
    "advisorId": "advice-" + "a" * 20, "projectId": "5" * 32,
    "brief": "Fix the counter for mixed results.", "actor": "owner", "locale": "en",
    "proposal": {"criterion": "mixed results give two", "question": None,
                 "cycle_id": "dalio-v6", "roles": {}, "depth": "balanced"},
}
PROVIDERS = [
    {"provider_id": "codex", "offered": True, "availability": "available", "auth": "subscription",
     "task_road": "boundary", "model_pin_supported": True, "controls": ["review", "dispatch"]},
    {"provider_id": "grok-build", "offered": True, "availability": "available",
     "auth": "subscription", "task_road": "review_only", "controls": ["review"]},
]
GIT = {"git": {"state": "repo", "head": {"commit": "a" * 40}}}


def inputs():
    return {"request": REQUEST, "catalog": {"starters": starters(), "providers": PROVIDERS},
            "git": GIT}


def test_shipped_do_is_compiled_for_verified_patch_and_each_stage_keeps_the_brief():
    result = run_js("""
      const p = plan.compileDalio(d.request, d.catalog, d.git);
      const tasks = p.document.nodes.filter(n => n.kind === 'task');
      console.log(JSON.stringify({nodes: tasks, roles: p.roles, limits: p.limits,
        stageRoles: plan.dalioOutline().stageRoles,
        gates: p.document.nodes.filter(n => n.kind === 'gate').map(n => n.gate_id),
        originalProfile: d.catalog.starters.find(s => s.starter_id === 'dalio-v6')
                         .document.nodes.find(n => n.node_id === 'do').arguments.profile}));
    """, MODULE, inputs())
    stages = result["nodes"]
    assert [n["node_id"] for n in stages] == ["goal", "identify", "diagnose", "design", "do"]
    assert {n["node_id"]: n["role_id"] for n in stages} == result["stageRoles"]
    assert all(n["attempt_bound"] == 1 and n["timeout_seconds"] == 600 for n in stages)
    assert all("artifact-brief" in n["arguments"]["target_artifact_refs"] for n in stages[:4])
    assert stages[-1]["arguments"]["profile"] == "implement-patch-v1"
    assert stages[-1]["arguments"]["artifact_refs"] == ["artifact-plan", "artifact-brief"]
    assert stages[-1]["verifier_role_id"] != stages[-1]["role_id"]
    assert result["originalProfile"] == "implement"
    assert result["gates"] == ["gate-confirm-do", "gate-result"]
    assert result["limits"]["max_total_task_seconds"] == 3600
    roles = {row["role"]: row for row in result["roles"]}
    assert roles["role-diagnostician"]["provider"] == "grok-build"
    assert roles["role-diagnostician"]["model"] is None
    assert roles["role-checker"]["instance"] != roles["role-implementer"]["instance"]


def test_missing_source_and_ineligible_provider_do_not_compile():
    codes = run_js("""
      const compile = (catalog, git) => {
        try { plan.compileDalio(d.request, catalog, git); return 'compiled'; }
        catch (error) { return error.message; }
      };
      const [codex,grok] = d.catalog.providers;
      const wrong = structuredClone(d.catalog);
      const nodes = wrong.starters.find(s=>s.starter_id==='dalio-v6').document.nodes;
      nodes.find(n=>n.node_id==="diagnose").role_id = "role-thinker";
      console.log(JSON.stringify([
        compile(d.catalog, {git:{state:'unborn'}}),
        compile({...d.catalog, providers:[codex, {...grok, auth:'api_key'}]}, d.git),
        compile({...d.catalog, providers:[{...codex, controls:['review']}, grok]}, d.git),
        compile({...d.catalog, providers:[codex]}, d.git), compile(wrong,d.git)]));
    """, MODULE, inputs())
    assert codes == ["source_required", "provider_unavailable", "provider_unavailable",
                     "provider_unavailable", "starter_unavailable"]
