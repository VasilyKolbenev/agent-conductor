"""Actual typed checker findings cross the strict read door as text, never authority."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import pytest
from conductor.command.http_api import CommandApi
from conductor.command.http_transport import CommandSession
from tests.test_policy_feedback import fixture, first_rejection
from tests.test_command_http_api import PORT, TOKEN, get_headers
from tests.test_studio_agents_i18n import DOM

PANEL = Path(__file__).resolve().parents[1] / "src/conductor/panel"


def reading(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch)
    first_rejection(f)
    api = CommandApi(f.store, f.registry, session=CommandSession(PORT, TOKEN),
        budget=f.policy.budget, clock=f.policy.clock, ids=f.runtime._ids,
        publish_run=lambda run: None)
    response = api.handle("GET", "/command/runs/run", get_headers())
    assert response.status == 200, response.payload
    return response.payload


def js(value, body):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required to execute the Studio decoder")
    source = "\n".join(f"import * as {alias} from {json.dumps((PANEL/name).as_uri())};"
        for alias, name in (("boundary", "studio-situation.js"), ("view", "studio-feedback.js"),
                            ("feedback", "studio-feedback-model.js")))
    source += DOM + "\nconst p=" + json.dumps(value) + ";\n" + body
    result = subprocess.run([node, "--input-type=module", "-e", source],
        capture_output=True, text=True, encoding="utf-8", timeout=15, check=False)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_actual_rejected_runtime_record_survives_whole_without_mutation(tmp_path, monkeypatch):
    value = reading(tmp_path, monkeypatch)
    result = js(value, """
      const before=JSON.stringify(p), admitted=boundary.projectRunRead(p);
      const row=p.records.find(x=>x.record_type==='correction_feedback').record;
      console.log(JSON.stringify({admitted:Boolean(admitted), unchanged:JSON.stringify(p)===before,
        typed:feedback.validFeedback(row), finds:row.payload.findings.length}));
    """)
    assert result == {"admitted": True, "unchanged": True, "typed": True, "finds": 1}


def test_foreign_sources_and_malformed_findings_refuse_the_whole_run_read(tmp_path, monkeypatch):
    value = reading(tmp_path, monkeypatch)
    result = js(value, """
      const accepted=Boolean(boundary.projectRunRead(p));
      const changes=[r=>r.source_action_id='foreign', r=>r.source_attempt_id='foreign',
        r=>r.checker_instance_id='doer', r=>r.checker_adapter_id='foreign',
        r=>r.authorization_digest='sha256:'+'0'.repeat(64),
        r=>r.payload.findings=[], r=>r.payload.findings[0].summary=' ',
        r=>r.payload.findings[0].summary='x'.repeat(8192),
        r=>r.payload.findings[0].path='../foreign', r=>r.payload.findings[0].line=0,
        r=>r.payload.findings[0].extra='not admitted',r=>r.payload.protocol='free-prose'];
      const negatives=changes.map(change=>{const copy=structuredClone(p);
        change(copy.records.find(x=>x.record_type==='correction_feedback').record);
        return boundary.projectRunRead(copy)===null;});
      const unknown=structuredClone(p);
      unknown.records.find(x=>x.record_type==='action_proposal').record.feedback_ids=['foreign'];
      console.log(JSON.stringify({accepted, negatives, missing:boundary.projectRunRead(unknown)===null}));
    """)
    assert result["accepted"] and result["missing"] and all(result["negatives"])
    assert len(result["negatives"]) == 12


@pytest.mark.parametrize("locale,label", [("en", "Independent check findings"), ("ru", "Замечания независимой проверки")])
def test_findings_are_literal_text_with_runtime_attribution_and_no_authorizing_controls(tmp_path, monkeypatch, locale, label):
    value = reading(tmp_path, monkeypatch)
    record = next(row["record"] for row in value["records"] if row["record_type"] == "correction_feedback")
    record["payload"]["findings"][0]["summary"] = "<img src=x> User finding неизменно"
    result = js(value, """
      const rows=view.feedbackFindings(p,'do',{locale:LOCALE});
      const text=rows.map(row=>row.textContent).join(' '), nodes=rows.flatMap(all);
      console.log(JSON.stringify({text,controls:nodes.filter(x=>['button','input','form'].includes(x.tag)).length,
        html:nodes.some(x=>x.tag==='img')}));
    """.replace("LOCALE", json.dumps(locale)))
    assert label in result["text"] and record["payload"]["findings"][0]["summary"] in result["text"]
    assert record["source_action_id"] in result["text"] and "checker" in result["text"]
    assert record["result_manifest_digest"] in result["text"]
    assert result["controls"] == 0 and result["html"] is False


@pytest.mark.parametrize("length", [5000, 9000])
def test_a_checker_finding_past_other_texts_bound_is_read_up_to_the_feedback_payload_bound(
        tmp_path, monkeypatch, length):
    """One finding may run past 4,096 characters while the payload keeps its 8,192 bytes."""
    value = reading(tmp_path, monkeypatch)
    result = js(value, f"""
      p.records.find(x=>x.record_type==='correction_feedback').record.payload.findings[0].summary='s'.repeat({length});
      const read=boundary.projectRunRead(p);
      console.log(JSON.stringify(read === null ? null : read.records.find(x=>x.recordType==='correction_feedback')
        .record.payload.findings[0].summary.length));
    """)
    assert result == (length if length == 5000 else None)
