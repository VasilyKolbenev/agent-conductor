"use strict";
import {canonicalJson} from "./command-projection.js";
import {exactKeys, isDigest, isId, isPlainObject} from "./studio-model.js";

// A desk preview precedes its run read: admit only closed rows on the reviewed patch steps.
export function validTestRows(packet) {
  if (packet.test_steps === undefined) return true;
  const rows = packet.test_steps, planned = packet.terms.node_limits.map(row => row.node_id);
  if (!Array.isArray(rows) || !rows.length || !Array.isArray(packet.patch_steps)) return false;
  const names = rows.map(row => row?.node_id);
  if (new Set(names).size !== names.length || canonicalJson(names)
      !== canonicalJson(planned.filter(id => names.includes(id)))) return false;
  return rows.every(row => {
    if (!isPlainObject(row) || !exactKeys(row,
      ["node_id", "policy", "policy_digest", "toolpin_digest"]) || !isId(row.node_id)
        || !packet.patch_steps.includes(row.node_id) || !isDigest(row.policy_digest)
        || !isDigest(row.toolpin_digest)) return false;
    const p = row.policy, t = p?.toolchain;
    return isPlainObject(p) && exactKeys(p,
      ["runner", "toolchain", "start", "pattern", "timeout_seconds"])
      && p.runner === "python-unittest-v1" && isPlainObject(t)
      && exactKeys(t, ["install", "entry", "runtime_digest"])
      && t.entry === "python.exe" && isDigest(t.runtime_digest)
      && typeof t.install === "string" && t.install.length > 0 && t.install.length <= 1024
      && !t.install.includes("\0") && typeof p.start === "string" && p.start.length > 0
      && p.start.length <= 320 && !p.start.includes("\0") && typeof p.pattern === "string"
      && p.pattern.length > 0 && p.pattern.length <= 160 && !/[\\/:\0\r\n]/.test(p.pattern)
      && Number.isSafeInteger(p.timeout_seconds) && p.timeout_seconds >= 1
      && p.timeout_seconds <= 86400;
  });
}

// Compare display facts with the exact human instruction already bound by the grant.
export function validTestSteps(packet, detail) {
  if (!validTestRows(packet)) return false;
  const expected = [];
  for (const binding of packet.terms.instruction_bindings) {
    const document = (detail.records ?? []).find(row => row.record_type === "artifact"
      && row.record.artifact_id === binding.artifact_id)?.record;
    if (!document?.content?.includes("conduct.test-plan.v1")) continue;
    const marker = "\n\nconduct.test-plan.v1\n";
    if (document.source_action_id !== undefined && document.source_action_id !== null
        || document.content.split(marker).length !== 2) return false;
    try {
      const encoded = document.content.split(marker)[1].split("\n\nconduct.patch-sources.v1\n")[0];
      const policy = JSON.parse(encoded);
      const node = detail.graph.definition.nodes.find(row => row.node_id === binding.node_id);
      const limit = packet.terms.node_limits.find(row => row.node_id === binding.node_id);
      if (node?.arguments?.profile !== "implement-patch-v1" || !isPlainObject(policy)
          || !exactKeys(policy, ["runner", "toolchain", "start", "pattern", "timeout_seconds"])
          || policy.runner !== "python-unittest-v1" || !isPlainObject(policy.toolchain)
          || !exactKeys(policy.toolchain, ["install", "entry", "runtime_digest"])
          || policy.toolchain.entry !== "python.exe" || !isDigest(policy.toolchain.runtime_digest)
          || typeof policy.toolchain.install !== "string" || !policy.toolchain.install
          || typeof policy.start !== "string" || !policy.start
          || typeof policy.pattern !== "string" || !policy.pattern
          || !limit || !Number.isSafeInteger(policy.timeout_seconds)
          || policy.timeout_seconds < 1 || policy.timeout_seconds > 86400) return false;
      policy.toolchain.install = policy.toolchain.install.replaceAll("\\", "/");
      expected.push({node_id: binding.node_id, policy});
    } catch { return false; }
  }
  if (!expected.length) return packet.test_steps === undefined;
  return Array.isArray(packet.test_steps) && packet.test_steps.length === expected.length
    && packet.test_steps.every((row, index) => {
      if (!isPlainObject(row) || !exactKeys(row,
        ["node_id", "policy", "policy_digest", "toolpin_digest"])
        || row.node_id !== expected[index].node_id || !isDigest(row.policy_digest)
        || !isDigest(row.toolpin_digest)) return false;
      const policy = structuredClone(row.policy);
      if (typeof policy?.toolchain?.install !== "string") return false;
      policy.toolchain.install = policy.toolchain.install.replaceAll("\\", "/");
      return canonicalJson(policy) === canonicalJson(expected[index].policy);
    });
}
