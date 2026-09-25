"use strict";
// Display admitted cache observations as text, never as an execution promise.
import {localize as L} from "./studio-i18n.js";
import {element} from "./command-view.js";

const REASONS = Object.freeze(["no_data", "source_error", "not_authenticated", "not_supported", "malformed_payload"]);
const PHASES = Object.freeze(["empty", "loading", "failed", "disconnected"]);

function line(label, value) {
  return element("div", {className: "studio-quota__fact"}, [
    element("dt", {text: label}), element("dd", {text: value})]);
}
function timestamp(value, state) { return value === null ? L(state, "agents.quota_unavailable") : value.replace("T", " ").replace("Z", " UTC"); }
function percentage(value, state) { return value === null ? L(state, "agents.quota_unavailable") : `${value}%`; }

function windowCard(row, state) {
  // Past its own reset the figures describe a window that has already restarted: never a remainder.
  const reset = row.freshness === "reset_passed";
  const figure = (value) => reset ? L(state, "agents.quota_unavailable") : percentage(value, state);
  return element("section", {className: "studio-quota__window", "data-quota-window": row.window_id}, [
    element("h4", {text: `${row.limit_id} · ${row.window_id}`}),
    element("p", {className: "studio-quota__status", text: reset ? L(state, "agents.quota_reset_window")
      : row.freshness === "stale" ? L(state, "agents.quota_stale_window") : L(state, "agents.quota_current")}),
    element("dl", {}, [line(L(state, "agents.quota_used"), figure(row.used_percent)),
      line(L(state, "agents.quota_remaining"), figure(row.remaining_percent)),
      line(L(state, "agents.quota_resets"), timestamp(row.resets_at, state)), line(L(state, "agents.quota_starts"), timestamp(row.starts_at, state)),
      line(L(state, "agents.quota_window"), row.duration_minutes === null ? L(state, "agents.quota_unavailable") : L(state, "agents.quota_minutes", {minutes: String(row.duration_minutes)}))]),
  ]);
}

function balanceCard(row, state) {
  return element("section", {className: "studio-quota__window", "data-quota-currency": row.currency}, [
    element("h4", {text: row.currency}), element("dl", {}, [
      line(L(state, "agents.quota_total"), `${row.total_balance} ${row.currency}`),
      line(L(state, "agents.quota_granted"), `${row.granted_balance} ${row.currency}`),
      line(L(state, "agents.quota_topped"), `${row.topped_up_balance} ${row.currency}`),
    ]),
  ]);
}

function snapshotCard(row, providers, state) {
  const names = row.binding_ids.map((id) => `${providers.get(id)} (${id})`).join(", ");
  const box = element("article", {className: "studio-quota", "data-quota-bindings": row.binding_ids.join(" ")}, [
    element("h3", {text: names}),
    element("p", {text: row.account_status === "unknown"
      ? L(state, "agents.quota_unknown_account")
      : L(state, "agents.quota_verified")}),
    element("dl", {}, [line(L(state, "agents.quota_source"), row.source ? `${row.source.kind} · ${row.source.version}` : L(state, "agents.quota_unavailable")),
      line(L(state, "agents.quota_observed"), timestamp(row.observed_at, state)),
      line(L(state, "agents.quota_freshness"), row.freshness === "current" ? L(state, "agents.quota_current")
        : row.freshness === "stale" ? L(state, "agents.quota_stale") : L(state, "agents.quota_no_observation"))]),
  ]);
  if (row.deferred_at) box.append(element("p", {className: "studio-quota__status", "data-quota-deferred": "",
    text: L(state, "agents.quota_deferred", {at: timestamp(row.deferred_at, state)})}));
  if (row.state !== "observed") box.append(element("p", {className: "studio-quota__status",
    text: L(state, row.state === "error" ? "agents.quota_error" : "agents.quota_no_data_prefix", {reason: L(state, `agents.quota_${REASONS.includes(row.reason) ? row.reason : "source_error"}`)})}));
  if (Object.hasOwn(row, "balances")) {
    box.append(element("dl", {}, [line(L(state, "agents.quota_funds"), row.is_available === null
      ? L(state, "agents.quota_unavailable") : row.is_available ? L(state, "agents.quota_yes") : L(state, "agents.quota_no")), line(L(state, "agents.quota_reset"), L(state, "agents.quota_reset_na"))]));
    box.append(...row.balances.map((balance) => balanceCard(balance, state)));
  } else box.append(...row.windows.map((window) => windowCard(window, state)));
  return box;
}

export function quotaSection(quotas, handlers, state = {}) {
  const button = element("button", {type: "button", "data-focus-key": "quota-read", text: L(state, "agents.quota_refresh")});
  button.addEventListener("click", () => handlers.refreshQuotas());
  const box = element("section", {id: "studioQuotas", className: "studio-quotas", "data-phase": quotas.phase}, [
    element("h2", {text: L(state, "agents.quota_title")}),
    element("p", {text: L(state, "agents.quota_intro")}), button,
  ]);
  if (quotas.phase !== "ready") box.append(element("p", {role: "status", text: L(state, `agents.quota_${PHASES.includes(quotas.phase) ? quotas.phase : "failed"}`)}));
  if (!quotas.payload) return box;
  const payload = quotas.payload;
  box.append(element("p", {text: L(state, "agents.quota_cache", {at: timestamp(payload.as_of, state), seconds: String(payload.max_age_seconds)})}));
  if (quotas.phase !== "ready") box.append(element("p", {text: L(state, "agents.quota_previous")}));
  const providers = new Map(payload.providers.map((row) => [row.provider_id, row.display_name]));
  box.append(element("div", {className: "studio-quotas__grid"}, payload.snapshots.map((row) => snapshotCard(row, providers, state))));
  if (!payload.providers.length) box.append(element("p", {text: L(state, "agents.quota_empty_catalog")}));
  return box;
}
