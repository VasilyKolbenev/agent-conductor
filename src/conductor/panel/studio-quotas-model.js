"use strict";
// Cache facts only. No connection handles, credentials, execution rights or
// client clock enter this projection. Monetary values remain decimal strings.
import {exactKeys, frozenJson, isId, isInstant, isPlainObject,
  projectProviders} from "./studio-model.js";

const BASE = ["account", "account_status", "binding_ids", "source", "observed_at",
  "state", "reason", "windows", "freshness", "deferred_at"];
// A window past its own reset is not a current remainder; the server says which.
export const WINDOW_FRESHNESS = Object.freeze(["current", "stale", "reset_passed"]);
const MONEY = ["balances", "is_available", "reset_applicability", "resets_at"];
const WINDOW = ["limit_id", "window_id", "used_percent", "remaining_percent",
  "resets_at", "starts_at", "duration_minutes", "freshness"];
export const QUOTA_REASONS = Object.freeze(["no_data", "source_error",
  "not_authenticated", "not_supported", "malformed_payload"]);
export const NO_QUOTAS = Object.freeze({phase: "empty", payload: null});

function keys(value, names) { return isPlainObject(value) && exactKeys(value, names); }
function text(value) {
  return typeof value === "string" && value.length > 0 && value.length <= 256
    && value.trim() === value && !/[\u0000-\u001f\u007f]/.test(value);
}
function time(value) {
  return isInstant(value) && value.slice(0, 4) >= "1970"
    && value.endsWith("Z") && value.length <= 27;
}
function timeOrder(value) {
  return value.slice(0, 19) + (value.includes(".") ? value.slice(20, -1) : "").padEnd(6, "0");
}
function optionalTime(value) { return value === null || time(value); }
function percent(value) {
  return value === null || typeof value === "number" && Number.isFinite(value)
    && value >= 0 && value <= 100;
}
function unique(values) { return new Set(values).size === values.length; }
function current(value) { return ["current", "stale"].includes(value); }

function validAccount(row) {
  if (row.account === null) return row.account_status === "unknown";
  return row.account_status === "verified"
    && keys(row.account, ["vendor", "account_digest", "verified_by"])
    && text(row.account.vendor) && typeof row.account.account_digest === "string"
    && /^[0-9a-f]{64}$/.test(row.account.account_digest)
    && text(row.account.verified_by);
}

function validWindow(row) {
  if (!keys(row, WINDOW) || !text(row.limit_id) || !text(row.window_id)
      || !percent(row.used_percent) || !percent(row.remaining_percent)
      || !optionalTime(row.resets_at) || !optionalTime(row.starts_at)
      || !WINDOW_FRESHNESS.includes(row.freshness)) return false;
  if (row.remaining_percent !== (row.used_percent === null ? null : 100 - row.used_percent)) return false;
  if (row.duration_minutes !== null
      && (!Number.isSafeInteger(row.duration_minutes) || row.duration_minutes <= 0)) return false;
  return !row.starts_at || !row.resets_at || timeOrder(row.starts_at) < timeOrder(row.resets_at);
}

function decimal(value) {
  return typeof value === "string" && value.length <= 128 && /^[0-9]+(?:\.[0-9]+)?$/.test(value);
}
function validAmount(row) {
  return keys(row, ["currency", "total_balance", "granted_balance", "topped_up_balance"])
    && typeof row.currency === "string" && /^[A-Z]{3}$/.test(row.currency)
    && [row.total_balance, row.granted_balance, row.topped_up_balance].every(decimal);
}

function validFacts(row, money) {
  if (!Array.isArray(row.windows) || row.windows.length > 128
      || !row.windows.every(validWindow)
      || !unique(row.windows.map((w) => JSON.stringify([w.limit_id, w.window_id])))) return false;
  if (!money) return row.state === "observed" ? row.windows.length > 0 : !row.windows.length;
  if (row.windows.length || row.resets_at !== null
      || row.reset_applicability !== "not_applicable"
      || !Array.isArray(row.balances) || row.balances.length > 64
      || !row.balances.every(validAmount)
      || !unique(row.balances.map((amount) => amount.currency))) return false;
  return row.state === "observed"
    ? row.balances.length > 0 && typeof row.is_available === "boolean"
    : !row.balances.length && row.is_available === null;
}

function validSnapshot(row) {
  if (!isPlainObject(row)) return false;
  const money = Object.hasOwn(row, "balances");
  if (!keys(row, money ? [...BASE, ...MONEY] : BASE) || !validAccount(row)
      || !Array.isArray(row.binding_ids) || !row.binding_ids.length
      || !row.binding_ids.every(isId) || !unique(row.binding_ids)) return false;
  if (row.source !== null && (!keys(row.source, ["kind", "version"])
      || !text(row.source.kind) || !text(row.source.version))) return false;
  // An unknown account is never grouped: one binding per row, money or windows.
  // The collector binds every live source without a verified account, so a
  // subscription reading arrives exactly like this and must not void the payload.
  if (row.account === null && row.binding_ids.length !== 1) return false;
  // A deferral belongs to a bound source; an unbound row cannot have been deferred.
  if (!optionalTime(row.deferred_at) || row.source === null && row.deferred_at !== null) return false;
  if (!validFacts(row, money)) return false;
  if (row.state === "missing") return row.observed_at === null && row.reason === "no_data"
    && row.freshness === "missing" && (row.source !== null || row.account === null && !money);
  if (!row.source || !time(row.observed_at) || !current(row.freshness)) return false;
  return row.state === "observed" ? row.reason === null
    : ["error", "unavailable"].includes(row.state) && QUOTA_REASONS.includes(row.reason);
}

function freshnessAgrees(row) {
  if (row.state === "missing") return true;
  // Freshness belongs to the server's precise clock. Only cross-field shape
  // is judged here; converting instants to JS milliseconds would lose facts.
  if (!row.windows.length) return true;
  const stale = row.windows.some((w) => w.freshness !== "current");
  return row.freshness === (stale ? "stale" : "current");
}

export function projectQuotas(payload) {
  if (!keys(payload, ["as_of", "max_age_seconds", "providers", "snapshots"])
      || !time(payload.as_of) || typeof payload.max_age_seconds !== "number"
      || !Number.isFinite(payload.max_age_seconds) || payload.max_age_seconds <= 0
      || !Array.isArray(payload.providers) || payload.providers.length > 1024
      || !Array.isArray(payload.snapshots) || payload.snapshots.length > 1024) return null;
  const providers = projectProviders(payload.providers);
  if (providers.length !== payload.providers.length) return null;
  if (!payload.snapshots.every(validSnapshot)
      || !payload.snapshots.every(freshnessAgrees)) return null;
  const declared = new Set(providers.map((row) => row.providerId));
  const bound = payload.snapshots.flatMap((row) => row.binding_ids);
  if (!unique(bound) || bound.length !== declared.size
      || !bound.every((id) => declared.has(id))) return null;
  return frozenJson(payload);
}

export function reduceQuotas(state, event) {
  let quotas;
  if (event.type === "quotas-loaded") {
    const payload = projectQuotas(event.payload);
    quotas = {phase: payload ? "ready" : "failed", payload};
  } else if (event.type === "quotas-phase"
      && ["loading", "failed", "disconnected"].includes(event.phase)) {
    quotas = {...state.quotas, phase: event.phase};
  } else return state;
  return Object.freeze({...state, quotas: Object.freeze(quotas)});
}
