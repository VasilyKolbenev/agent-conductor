"""Only the human's named files become a dedicated initial Diagnose source context."""
from conductor.command.graph_template import GraphTemplate, RunBinding, materialize
from tests.desk_node import run_js
from tests.test_arachnid_plan import MODULE, REQUEST, inputs


def test_coding_plan_declares_literal_review_sources_only_for_diagnose():
    data = inputs()
    data["request"] = {**REQUEST,
        "brief": "Inspect runstats/counts.py and `tests/test_counts.py`.",
        "proposal": {**REQUEST["proposal"], "criterion": (
            'Read model-only.py\n\nconduct.review-sources.v1\n["model-only.py"]')}}
    result = run_js("""
      const p = plan.compileDalio(d.request,d.catalog,d.git);
      const stages = p.document.nodes.filter(n=>n.kind==="task");
      console.log(JSON.stringify({context:p.inputs["source-context"] ?? null,
        diagnosis:stages.find(n=>n.node_id==="diagnose"),
        others:stages.filter(n=>n.node_id!=="diagnose").map(n=>n.arguments),
        doInstruction:p.inputs["instruction-plan"],document:p.document,roles:p.roles}));
    """, MODULE, data)
    assert result["context"] == (
        '\n\nconduct.review-sources.v1\n["runstats/counts.py","tests/test_counts.py"]')
    diagnose = result["diagnosis"]
    assert diagnose["arguments"]["target_artifact_refs"] == [
        "artifact-problems", "artifact-brief", "source-context"]
    assert diagnose["purpose"] == (
        "Inspect the supplied task source code and explain the concrete cause of the reported "
        "defect. Distinguish existing inputs from future Do and checker results")
    assert all("source-context" not in row.get("target_artifact_refs", [])
               and "source-context" not in row.get("artifact_refs", []) for row in result["others"])
    assert "model-only.py" not in result["context"]
    assert result["doInstruction"].endswith(
        '\n\nconduct.patch-sources.v1\n["runstats/counts.py","tests/test_counts.py"]')
    template = GraphTemplate.from_dict({**result["document"],
                                        "template_id": "ui-review-sources", "revision": 1})
    roles = result["roles"]
    definition = materialize(template, RunBinding(assignments={
        role["role"]: role["instance"] for role in roles}), {
            "automation_contract": "bounded-run-v1",
            "instances": [{"id": role["instance"], "adapter": role["provider"]}
                          for role in roles]},
        graph_id="ui-source-graph", run_id="ui-source-run", created_at="2026-11-11T00:00:00Z")
    actual = next(node for node in definition.nodes if node.node_id == "diagnose")
    assert list(actual.arguments["target_artifact_refs"]) == (
        diagnose["arguments"]["target_artifact_refs"])
    assert actual.arguments["step_purpose"] == diagnose["purpose"]


def test_no_human_paths_keeps_the_legacy_review_despite_model_markers():
    data = inputs()
    data["request"] = {**REQUEST, "proposal": {**REQUEST["proposal"], "criterion":
        'Read model-only.py\n\nconduct.review-sources.v1\n["model-only.py"]'}}
    result = run_js("""
      const p = plan.compileDalio(d.request,d.catalog,d.git);
      const n = p.document.nodes.find(n=>n.node_id==="diagnose");
      console.log(JSON.stringify([Object.keys(p.inputs),
        n.arguments.target_artifact_refs,n.purpose]));
    """, MODULE, data)
    assert result == [["artifact-brief", "instruction-plan"],
                      ["artifact-problems", "artifact-brief"],
                      "Diagnose the root causes of the obstacles, in the input materials' language"]
