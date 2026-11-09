"use strict";
import {element} from "./command-view.js";
import {word} from "./arachnid-copy.js";
import {quotaSection} from "./studio-quotas.js";
import {projectQuotas} from "./studio-quotas-model.js";

export function harnesses(detail, providers, locale) {
  const groups = new Map();
  for (const instance of detail?.config?.instances || []) {
    if (!groups.has(instance.adapter)) groups.set(instance.adapter, []);
    groups.get(instance.adapter).push(instance);
  }
  const names = new Map(providers.map(p => [p.providerId, p.displayName]));
  const ids = detail ? [...groups.keys()] : [...names.keys()];
  const nodes = detail?.graph?.definition?.nodes || [];
  return ids.map(id => {
    const instances = groups.get(id) || [];
    const assigned = new Set(instances.map(i => i.id));
    const performs = nodes.filter(n => assigned.has(n.instance_id));
    const verifies = nodes.some(n => assigned.has(n.verifier_instance_id));
    const duty = performs.length > 1 ? word(locale, "executor") : performs[0]?.title;
    return {id, label: names.get(id) || id, instances,
      duty: [duty, verifies ? word(locale, "checker") : null].filter(Boolean).join(" · ")};
  });
}

const heading = text => element("h3", {text});
const line = text => element("p", {text});
function item(name, body) {
  return element("section", {className: "fact"}, [element("strong", {text: name}), line(body)]);
}

export function showHarnesses(host, rows, active, locale, detail) {
  const selected = active ? rows.filter(row => row.id === active) : rows;
  host.replaceChildren();
  if (!selected.length) host.append(line(word(locale, "noRoles")));
  for (const row of selected) {
    host.append(heading(row.label));
    for (const instance of row.instances) {
      const performs = (detail?.graph?.definition?.nodes || []).filter(n => n.instance_id === instance.id);
      const checks = (detail?.graph?.definition?.nodes || []).filter(n => n.verifier_instance_id === instance.id);
      const duties = [...performs.map(n => n.title || n.node_id),
        ...checks.map(n => (locale === "ru" ? "Проверка · " : "Check · ") + (n.title || n.node_id))];
      host.append(item(instance.id, [instance.model, ...duties].filter(Boolean).join(" · ")));
    }
  }
}

export function showMemory(host, detail, messages, locale) {
  host.replaceChildren();
  const records = detail?.records || [];
  const decisions = records.filter(r => r.record_type === "decision").map(r => r.record);
  const actions = records.filter(r => r.record_type === "action_result").map(r => r.record);
  if (decisions.length) {
    host.append(heading(word(locale, "decisions")));
    for (const d of decisions) host.append(item(d.gate_id, [d.actor, d.action, d.reason].filter(Boolean).join(" · ")));
  }
  if (actions.length) {
    host.append(heading(word(locale, "actions")));
    for (const a of actions) host.append(item(a.node_id || a.action_id, a.outcome));
  }
  if (messages.length) {
    host.append(heading(word(locale, "chat")));
    for (const m of messages) host.append(item(word(locale, m.role === "user" ? "you" : "atlas"), m.text));
  }
  if (!host.childElementCount) host.append(line(word(locale, "noHistory")));
}

export function showLimits(host, raw, locale, refresh) {
  if (!raw || typeof raw !== "object") { host.replaceChildren(line(word(locale, "projection"))); return; }
  const {hub_snapshot: snapshot, ...base} = raw;
  const projected = projectQuotas(base, {allowEmptySnapshots: Object.hasOwn(raw, "hub_snapshot")});
  if (!projected) { host.replaceChildren(line(word(locale, "projection"))); return; }
  host.replaceChildren(quotaSection({phase: "ready", payload: projected}, {refreshQuotas: refresh},
    {locale, hideStaleQuotas: true, manualQuotaRead: true}));
  if (snapshot === null) host.append(line(word(locale, "quotaArchive")));
  else if (typeof snapshot?.taken_at === "string") host.append(item(word(locale, "taken"), snapshot.taken_at));
}
