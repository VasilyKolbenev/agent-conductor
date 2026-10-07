"use strict";
// The Bridge repeats admitted facts from the same run and quota cache.
import {element} from "./command-view.js";
import {localize} from "./studio-i18n.js";
import {compareInstants} from "./studio-taskruns.js";

function action(label, key, invoke) {
  const button = element("button", {type: "button", "data-focus": `bridge:${key}`, text: label});
  button.disabled = typeof invoke !== "function";
  if (invoke) button.addEventListener("click", invoke);
  return button;
}
function paragraph(text) { return element("p", {text}); }

function humanControl(state, handlers) {
  const detail = state.runs.detail, situation = detail?.graph?.situation;
  const fresh = state.connection === "open" && state.runs.phase === "ready" && situation;
  const value = fresh ? situation.state : "unknown";
  const box = element("section", {className: "studio-bridge__box", "data-human-state": value}, [
    element("h3", {text: localize(state, "bridge.title")}),
    element("h4", {text: localize(state, "bridge.attention")}),
    paragraph(localize(state, `bridge.${value}`)),
  ]);
  if (fresh) {
    box.append(paragraph(localize(state, "bridge.as_of", {at: situation.computed_at})));
    const checked = element("details", {}, [element("summary", {text: localize(state, "bridge.checked")})]);
    for (const row of situation.checked) {
      const text = localize(state, `bridge.${row.reason}`, row.reason === "run_ended" ? {} : {count: String(row.count)});
      checked.append(paragraph(row.reason === "run_ended" ? `${text} ${row.count}` : text));
      if (row.count && row.reason !== "run_ended") box.append(paragraph(text));
    }
    box.append(checked);
    if (value === "required" && situation.checked.some((row) => row.reason === "gate_decision" && row.count > 0)) {
      box.append(action(localize(state, "scene.open_decisions"),
        "decisions", () => handlers.showDecisions(detail.run.run_id)));
    }
  }
  return box;
}

function queue(state, handlers) {
  const box = element("section", {className: "studio-bridge__box"}, [
    element("h3", {text: localize(state, "bridge.queue")})]);
  if (state.connection !== "open" || state.runs.phase !== "ready") {
    box.append(paragraph(localize(state, "bridge.unknown"))); return box;
  }
  const runs = state.runs.list.filter((row) => !row.unreadable && row.human_state === "required")
    .sort((a, b) => -compareInstants(a.created_at, b.created_at) || a.run_id.localeCompare(b.run_id));
  if (!runs.length) box.append(paragraph(localize(state, "bridge.queue_empty")));
  for (const row of runs.slice(0, 5)) {
    const title = state.tasks.list.find((task) => task.task_id === row.task_id)?.title || row.run_id;
    box.append(action(title, `run:${row.run_id}`, () => handlers.onSelectTaskRun(row.task_id, row.run_id)));
  }
  if (runs.length > 5) box.append(paragraph(localize(state, "bridge.more", {count: String(runs.length - 5)})));
  return box;
}

function quotaRead(row, providers, state) {
  const box = element("article", {className: "studio-bridge__reading", "data-quota-bindings": row.binding_ids.join(" ")}, [
    element("h4", {text: row.binding_ids.map((id) => `${providers.get(id)} · ${id}`).join(", ")}),
  ]);
  if (row.account_status === "unknown") box.append(paragraph(localize(state, "bridge.usage_unknown")));
  if (row.state !== "observed") box.append(paragraph(localize(state, "bridge.usage_error")));
  if (row.freshness === "stale") box.append(paragraph(localize(state, "bridge.usage_stale")));
  if (row.deferred_at) box.append(paragraph(localize(state, "bridge.usage_deferred", {at: row.deferred_at})));
  if (Object.hasOwn(row, "balances")) {
    for (const balance of row.balances) box.append(paragraph(localize(state, "bridge.balance",
      {amount: balance.total_balance, currency: balance.currency})));
    box.append(paragraph(localize(state, "bridge.no_reset")));
  } else for (const window of row.windows) {
    box.append(element("strong", {text: `${window.limit_id} · ${window.window_id}`}));
    if (window.freshness === "stale") box.append(paragraph(localize(state, "bridge.usage_stale")));
    if (window.freshness === "reset_passed") box.append(paragraph(localize(state, "bridge.window_reset")));
    box.append(paragraph(window.remaining_percent === null || window.freshness === "reset_passed"
      ? localize(state, "bridge.usage_missing")
      : localize(state, "bridge.remaining", {value: String(window.remaining_percent)})));
    box.append(paragraph(window.resets_at === null ? localize(state, "bridge.usage_missing")
      : localize(state, "bridge.reset", {at: window.resets_at})));
  }
  if (row.source) box.append(paragraph(`${row.source.kind} · ${row.source.version} · ${row.observed_at || "—"}`));
  return box;
}

function compactQuota(row, providers, state) {
  const labels = row.binding_ids.map((id) => providers.get(id) || id).join(", ");
  const balance = (row.balances || []).map((value) => `${value.total_balance} ${value.currency}`).join(" · ");
  const remaining = (row.windows || []).filter((value) => value.remaining_percent !== null
    && value.freshness !== "reset_passed")
    .map((value) => `${value.remaining_percent}%`).join(" · ");
  const status = row.freshness === "stale" ? localize(state, "bridge.usage_stale")
    : balance || remaining || localize(state, "bridge.usage_missing");
  return element("details", {className: "studio-bridge__compact"}, [
    element("summary", {text: `${labels}: ${status}${row.deferred_at
      ? ` · ${localize(state, "bridge.deferred_short")}` : ""}`}), quotaRead(row, providers, state)]);
}

function usage(state, handlers) {
  const box = element("section", {className: "studio-bridge__box"}, [
    element("h3", {text: localize(state, "bridge.usage")})]);
  const {payload, phase} = state.quotas;
  if (!payload) box.append(paragraph(localize(state, "bridge.usage_missing")));
  else {
    if (phase !== "ready") box.append(paragraph(localize(state, "bridge.usage_stale")));
    const providers = new Map(payload.providers.map((row) => [row.provider_id, row.display_name]));
    box.append(paragraph(localize(state, "bridge.as_of", {at: payload.as_of})));
    for (const row of payload.snapshots) box.append(compactQuota(row, providers, state));
  }
  box.append(action(localize(state, "bridge.open_agents"), "agents", () => handlers.onScreen("agents")));
  return box;
}

export function mountBridge(mount, state, handlers) {
  mount.hidden = state.screen !== "runs";
  mount.replaceChildren(humanControl(state, handlers), queue(state, handlers), usage(state, handlers));
}
