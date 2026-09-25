"use strict";
// Provider facts belong to the same server preview whose digest binds them.
import {exactKeys, isId, isPlainObject} from "./studio-model.js";

const object = (row, keys) => isPlainObject(row) && exactKeys(row, keys);
const text = (value) => typeof value === "string" && value.length <= 8192 && !value.includes("\0");
const texts = (value) => Array.isArray(value) && value.every(text);
const count = (value) => Number.isSafeInteger(value) && value > 0;
const CONFIG = ["provider_id", "executable", "protocol", "env_allow", "entrypoint", "auth", "auth_home"];
const CONTRACT = ["provider_id", "display_name", "vendor", "version", "capabilities", "schema_pairs",
  "lifecycle", "availability", "available", "implementation", "auth", "vendor_sandbox"];
const MANIFEST = ["adapter_id", "display_name", "vendor", "version", "capabilities", "docs_url"];
// The bound a task is refused at before its claim, with the unit and scope that bound measures
// (policy_providers._task_channel); the channel must be the one the transport profile declares.
const CHANNELS = {argv: ["utf16_units", "command_line"], stdin: ["utf8_bytes", "task"]};
//: One task-channel fact's closed shape, read alike by the grant review and the run's controls.
export function taskChannelShape(value) {
  return object(value, ["channel", "limit", "unit", "scope"]) && Object.hasOwn(CHANNELS, value.channel)
    && count(value.limit) && value.unit === CHANNELS[value.channel][0]
    && value.scope === CHANNELS[value.channel][1];
}
function channel(row) {
  const value = row.task_channel, declared = row.transport.task_channel;
  if (value === null) return declared === undefined;
  return taskChannelShape(value) && declared === value.channel;
}

function json(value, depth = 0) {
  if (depth > 16) return false;
  if (value === null || typeof value === "boolean") return true;
  if (typeof value === "string") return text(value);
  if (typeof value === "number") return Number.isFinite(value);
  if (Array.isArray(value)) return value.length <= 1024 && value.every((row) => json(row, depth + 1));
  return isPlainObject(value) && Object.keys(value).length <= 128
    && Object.entries(value).every(([key, row]) => text(key) && json(row, depth + 1));
}
function provider(row) {
  if (!object(row, ["config", "contract", "manifest", "transport", "output_limits", "file_budget", "input_limits",
        "task_channel"])
      || !object(row.config, CONFIG) || !object(row.contract, CONTRACT) || !object(row.manifest, MANIFEST)
      || !isPlainObject(row.transport) || !isPlainObject(row.output_limits) || !count(row.file_budget)
      || !object(row.input_limits, ["frame", "stdin", "instruction"])
      || !Object.values(row.input_limits).every(count) || !channel(row)) return false;
  const config = row.config, contract = row.contract, manifest = row.manifest;
  if (!isId(config.provider_id) || contract.provider_id !== config.provider_id || manifest.adapter_id !== config.provider_id
      || !["executable", "protocol", "entrypoint", "auth_home"].every((key) => text(config[key]))
      || !["api_key", "subscription"].includes(config.auth) || !texts(config.env_allow)
      || !config.env_allow.every((key) => /^[A-Za-z_][A-Za-z0-9_]*$/.test(key))) return false;
  if (!["display_name", "vendor", "version"].every((key) => text(contract[key]) && text(manifest[key]))
      || !texts(contract.capabilities) || !texts(contract.lifecycle) || !texts(manifest.capabilities)
      || !text(manifest.docs_url) || contract.available !== true || contract.availability !== "available"
      || contract.auth !== config.auth || !text(contract.implementation)) return false;
  return json(row) && Object.values(row.output_limits).every(count);
}
export function validProviderFacts(value, detail) {
  if (value === null) return true; // An injected seam supplies no configuration claim.
  if (!object(value, ["providers"]) || !Array.isArray(value.providers) || !value.providers.every(provider)) return false;
  const found = value.providers.map((row) => row.config.provider_id);
  const expected = [...new Set(detail.config.instances.map((row) => row.adapter))].sort();
  return found.join("\0") === expected.join("\0");
}
