"use strict";
import {element} from "./command-view.js";
import {localize} from "./studio-i18n.js";
const word = (state, key, params) => localize(state, `feedback.${key}`, params);
export function feedbackFindings(detail, nodeId, state) {
  const rows = detail.records.filter((row) => row.record_type === "correction_feedback"
    && row.record.source_node_id === nodeId);
  return rows.map(({record}) => element("section", {"data-correction-feedback": record.feedback_id}, [
    element("h4", {text: word(state, "title")}),
    element("p", {text: word(state, "source", {action: record.source_action_id, attempt: record.source_attempt_id,
      checker: record.checker_instance_id, adapter: record.checker_adapter_id, lap: String(record.source_lap)})}),
    element("p", {text: word(state, "meaning")}),
    element("ul", {}, record.payload.findings.map((finding) => element("li", {}, [
      element("strong", {text: word(state, finding.kind)}), element("p", {text: finding.summary}),
      ...(finding.path === null ? [] : [element("p", {text: finding.line === null
        ? finding.path : `${finding.path}:${finding.line}`})]),
    ]))),
    element("details", {}, [element("summary", {text: word(state, "provenance")}),
      element("pre", {text: JSON.stringify({feedback_id: record.feedback_id, authorization_id: record.authorization_id,
        authorization_digest: record.authorization_digest, recorded_at: record.recorded_at,
        result_manifest_digest: record.result_manifest_digest, result_manifest: record.result_manifest}, null, 2)})]),
  ]));
}
