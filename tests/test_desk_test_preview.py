"""The public desk projection admits and attributes owner-bound local-test previews."""
from tests.desk_wizard_node import fixture, run_js
from tests.test_studio_automation import wire


def packet(tmp_path):
    value = wire(tmp_path)
    value["preview"]["budget"] = fixture("wizard", "preview_standard.json")["budget"]
    value["plan"] = {"runner": "python-unittest-v1", "start": "checks",
        "pattern": "test_*.py", "timeout_seconds": 60, "toolchain": {
            "install": "C:\\trusted\\harnesses\\python\\3.12.14", "entry": "python.exe",
            "runtime_digest": "sha256:" + "9" * 64}}
    return value


PREPARE = """
const detail = d.read, packet = d.preview;
const node = detail.graph.definition.nodes.find(n => n.capability);
node.arguments.profile = "implement-patch-v1";
const binding = packet.terms.instruction_bindings[0];
const document = detail.records.find(r => r.record_type === "artifact"
  && r.record.artifact_id === binding.artifact_id).record;
document.content = "Do.\\n\\nconduct.test-plan.v1\\n" + JSON.stringify(d.plan);
packet.patch_steps = [node.node_id];
packet.test_steps = [{node_id: node.node_id, policy: d.plan,
  policy_digest: packet.preview_digest, toolpin_digest: packet.preview_digest}];
const launch = read => ({preview:packet, reads:{run:read}});
const card = read => desk.cardFacts(launch(read), {roles:{}}).steps[0];
"""


def test_desk_admits_test_steps_and_matches_the_frozen_instruction(tmp_path):
    data = packet(tmp_path)
    result = run_js(PREPARE + """
      const projected = desk.projectPreview(packet, "run");
      const actual = card({status:"ok",payload:detail});
      const absent = card(null);
      const stale = structuredClone(detail); stale.graph.definition_digest = "stale";
      console.log(JSON.stringify([Boolean(projected), actual.tests,
        absent.tests, absent.testsUnavailable, card({status:"ok",payload:stale}).tests]));
    """, data, modules={"desk": "desk-wizard-launch.js"})
    assert result == [True, data["plan"], None, True, None]


def test_desk_refuses_foreign_or_malformed_test_rows_and_hides_unbound_policy(tmp_path):
    result = run_js(PREPARE + """
      const admits = value => Boolean(desk.projectPreview(value, "run"));
      const row = packet.test_steps[0];
      const foreign = structuredClone(detail);
      foreign.records.find(r => r.record_type === "artifact"
        && r.record.artifact_id === binding.artifact_id).record.content = "Different instruction";
      console.log(JSON.stringify([
        admits({...packet,test_steps:[{...row,node_id:"other"}]}),
        admits({...packet,test_steps:[row,row]}),
        admits({...packet,test_steps:[{...row,unexpected:true}]}),
        admits({...packet,test_steps:[{...row,policy:{...row.policy,runner:"shell"}}]}),
        card({status:"ok",payload:foreign}).tests,
        card({status:"ok",payload:foreign}).testsUnavailable]));
    """, packet(tmp_path), modules={"desk": "desk-wizard-launch.js"})
    assert result == [False, False, False, False, None, True]
