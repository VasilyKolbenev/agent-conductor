"""Atlas connects an output to the exact document consumed in the selected run."""
from copy import deepcopy
from hashlib import sha256

import pytest

from tests.desk_node import run_js


def project(detail):
    return run_js("console.log(JSON.stringify(handoff.handoffData(d)))",
                  {"handoff": "arachnid-handoff-data.js"}, detail)


def world():
    records = []

    def add(kind, **row):
        records.append({"record_type": kind, "record": {"run_id": "run", **row}})

    def request(node, actor, capability, arguments, **extra):
        add("action_request", action_id=node + "-a", attempt_id=node + "-t", node_id=node,
            instance_id=actor, capability=capability, arguments=arguments, **extra)

    def result(node, actor):
        add("action_result", action_id=node + "-a", attempt_id=node + "-t",
            instance_id=actor, outcome="succeeded")

    def document(artifact_id, artifact_ref, content, **extra):
        add("artifact", artifact_id=artifact_id, artifact_ref=artifact_ref, content=content,
            media_type="text/markdown", **extra)

    request("diagnose", "researcher", "review", {"result_artifact_ref": "causes",
                                                 "target_artifact_refs": ["brief"]})
    document("diagnosis-1", "causes", "Counts cancelled rows.", source_action_id="diagnose-a")
    result("diagnose", "researcher")
    request("design", "planner", "review", {"result_artifact_ref": "plan",
                                           "target_artifact_refs": ["causes"]})
    document("plan-1", "plan", "Count only succeeded.", source_action_id="design-a",
             input_artifact_ids=["diagnosis-1"])
    result("design", "planner")
    document("revision-2", "plan", "Use unittest.")
    digest = "sha256:" + sha256(b"Use unittest.").hexdigest()
    add("run_authorization", authorization_id="grant", authorization_digest="sha256:" + "a" * 64,
        initial_input_bindings=[{"artifact_id": "revision-2", "artifact_ref": "plan",
                                 "content_digest": digest}])
    patch = {"profile": "implement-patch-v1", "artifact_refs": ["plan"]}
    request("do", "worker", "dispatch", patch,
            run_authorization_id="grant", run_authorization_digest="sha256:" + "a" * 64)
    result("do", "worker")
    return {"run": {"run_id": "run"}, "warnings": [], "config": {"instances": [
        {"id": "researcher", "adapter": "grok-build"}, {"id": "planner", "adapter": "codex"},
        {"id": "worker", "adapter": "codex"}]}, "records": records}


def test_explicit_consumed_id_and_bound_revision_reach_the_operator():
    data = project(world())
    link, = data["links"]
    assert data["runId"] == "run"
    assert link["source"] == {
        "adapter": "grok-build", "instanceId": "researcher", "nodeId": "diagnose",
        "actionId": "diagnose-a", "attemptId": "diagnose-t", "artifactId": "diagnosis-1",
        "artifactRef": "causes", "excerpt": "Counts cancelled rows."}
    assert link["target"]["artifactId"] == "plan-1"
    assert link["target"]["excerpt"] == "Count only succeeded."
    assert data["continuations"] == [{
        "fromArtifactId": "plan-1", "inputRef": "plan", "inputArtifactId": "revision-2",
        "kind": "different_revision", "target": {"adapter": "codex", "instanceId": "worker",
        "nodeId": "do", "actionId": "do-a", "attemptId": "do-t"}}]


@pytest.mark.parametrize(("index", "change"), [
    (1, {"run_id": "foreign"}), (1, {"source_action_id": "another-attempt"}),
    (2, {"attempt_id": "later"}), (4, {"input_artifact_ids": ["causes"]}),
    (4, {"input_artifact_ids": ["diagnosis-1", "diagnosis-1"]}),
    (4, {"media_type": "application/octet-stream"}), (4, {"content": "  "}),
    (5, {"instance_id": "other"}), (5, {"outcome": "verification_failed"}),
])
def test_unbound_or_failed_review_cannot_establish_the_link(index, change):
    detail = world()
    detail["records"][index]["record"].update(change)
    detail["records"].append({"record_type": "evidence", "record": {
        "run_id": "run", "verification": "verified", "verifier_instance_id": "worker"}})
    assert project(detail) == {"runId": "run", "links": [], "continuations": []}


@pytest.mark.parametrize("fault", ["duplicate", "header", "out_of_order", "warnings", "vendor"])
def test_ambiguous_or_out_of_order_sources_are_ineligible(fault):
    detail = world()
    if fault == "duplicate":
        detail["records"].append(deepcopy(detail["records"][1]))
    elif fault == "header":
        detail["config"]["instances"].insert(0, {"id": "planner", "adapter": "other"})
    elif fault == "out_of_order":
        detail["records"].insert(0, detail["records"].pop(3))
    elif fault == "warnings":
        detail["warnings"] = ["bad journal"]
    else:
        detail["config"]["instances"][1]["adapter"] = "another"
    assert project(detail)["links"] == []


@pytest.mark.parametrize("fault", ["ref", "input_id", "digest", "grant", "grant_digest", "attempt"])
def test_unbound_dispatch_leaves_the_direct_transfer_intact(fault):
    detail = world()
    grant, dispatch, result = [row["record"] for row in detail["records"][-3:]]
    if fault == "ref":
        dispatch["arguments"]["artifact_refs"] = ["brief"]
    elif fault == "input_id":
        grant["initial_input_bindings"][0]["artifact_id"] = "missing"
    elif fault == "digest":
        grant["initial_input_bindings"][0]["content_digest"] = "sha256:" + "0" * 64
    elif fault == "grant":
        dispatch["run_authorization_id"] = "later"
    elif fault == "grant_digest":
        dispatch["run_authorization_digest"] = "sha256:" + "f" * 64
    else:
        result["attempt_id"] = "wrong"
    model = project(detail)
    assert len(model["links"]) == 1 and model["continuations"] == []


def test_original_revision_can_be_pinned_to_dispatch():
    detail = world()
    grant = detail["records"][-3]["record"]
    digest = "sha256:" + sha256(b"Count only succeeded.").hexdigest()
    grant["initial_input_bindings"][0].update(artifact_id="plan-1", content_digest=digest)
    next_step, = project(detail)["continuations"]
    assert next_step["kind"] == "same_revision"


def test_two_consumed_diagnoses_keep_their_own_ids_and_one_downstream_attempt():
    detail = world()
    followup = deepcopy(detail["records"][:3])
    for entry in followup:
        item = entry["record"]
        if entry["record_type"] == "artifact":
            item.update(artifact_id="diagnosis-2", artifact_ref="more-causes",
                        source_action_id="other-action", content="Different diagnostic text.")
        else:
            item.update(action_id="other-action", attempt_id="other-attempt")
        if entry["record_type"] == "action_request":
            item["arguments"]["result_artifact_ref"] = "more-causes"
    detail["records"][3]["record"]["arguments"]["target_artifact_refs"].append("more-causes")
    detail["records"][4]["record"]["input_artifact_ids"].append("diagnosis-2")
    detail["records"][3:3] = followup
    output = project(detail)
    assert [link["source"]["artifactId"] for link in output["links"]] == [
        "diagnosis-1", "diagnosis-2"]
    assert [link["source"]["excerpt"] for link in output["links"]] == [
        "Counts cancelled rows.", "Different diagnostic text."]
    assert len(output["continuations"]) == 1


@pytest.mark.parametrize(("question", "source", "recipient"), [
    ("Что передал Кодексу Грок?", "grok-build", "codex"),
    ("Что передал Гроку Кодекс?", "codex", "grok-build"),
    ("Что получил Codex от Grok?", "grok-build", "codex"),
    ("What did Grok receive from Codex?", "codex", "grok-build"),
    ("What did Grok send to Codex?", "grok-build", "codex"),
    ("What was sent to Grok by Codex?", "codex", "grok-build"),
])
def test_chat_resolves_the_named_handoff_direction(question, source, recipient):
    result = run_js("console.log(JSON.stringify(ctx.handoffIntent(d, null)))",
                    {"ctx": "arachnid-handoff-context.js"}, question)
    assert result == {"kind": "transfer", "from": source, "to": recipient}


def test_only_a_remembered_handoff_answers_a_deictic_tests_question():
    result = run_js("""
      console.log(JSON.stringify([ctx.handoffIntent(d, null), ctx.handoffIntent(d, {})]))
    """, {"ctx": "arachnid-handoff-context.js"}, "Что из этого проверили тестами?")
    assert result == [{"kind": "clarify"}, {"kind": "tests"}]


def test_fix_followup_uses_the_recipient_of_the_remembered_handoff():
    kinds = run_js("""
      const context = {from: 'grok-build', to: 'codex'};
      const kind = (text, pin) => ctx.handoffIntent(text, pin)?.kind ?? null;
      console.log(JSON.stringify([...d.map(text => kind(text, context)), kind(d[0], null)]));
    """, {"ctx": "arachnid-handoff-context.js"}, [
        "А что именно Codex исправил?", "What exactly did Codex fix?", "Что изменил Грок?",
        "А что исправил Claude?", "А что исправил Kimi?"])
    assert kinds[:2] == ["changes", "changes"]
    assert kinds[2] not in (None, "changes")
    assert "changes" not in kinds[3:]
    assert kinds[-1] is None


def test_continuation_requires_the_same_input_node_action_and_attempt():
    row = {"inputArtifactId": "revision-2", "target": {
        "nodeId": "do", "actionId": "action-do", "attemptId": "attempt-2"}}
    pin, matches = run_js("""
      const pin = ctx.continuationPin(d);
      const cases = [pin, ...Object.keys(pin).map(key => ({...pin, [key]: "other"}))];
      console.log(JSON.stringify([pin, cases.map(p => ctx.sameContinuation(d, p))]));
    """, {"ctx": "arachnid-handoff-context.js"}, row)
    assert pin == {"inputId": "revision-2", "nodeId": "do", "actionId": "action-do",
                   "attemptId": "attempt-2"}
    assert matches == [True, False, False, False, False]
