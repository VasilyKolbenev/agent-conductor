"use strict";
import {projectWorkflow as projectLegacyWorkflow} from "./studio-model.js";
// Immutable drawing copies and the explicit shape of a new revision.
export const WORKFLOW_SCHEMA = 1;
function isObject(value) { return Boolean(value) && typeof value === "object" && !Array.isArray(value); }
function rows(value) { return Array.isArray(value) ? value : []; }
export function frozenCopy(value) {
  if (Array.isArray(value)) return Object.freeze(value.map(frozenCopy));
  if (!isObject(value)) return value;
  const out = {};
  for (const key of Object.keys(value)) {
    Object.defineProperty(out, key, {configurable: false, enumerable: true,
      value: frozenCopy(value[key]), writable: false});
  }
  return Object.freeze(out);
}
export function draftFrom(value) {
  if (!isObject(value)) return null;
  const marked = Object.hasOwn(value, "execution_contract");
  if (marked && value.execution_contract !== "bounded-run-v1") return null;
  return frozenCopy({schema_version: WORKFLOW_SCHEMA,
    title: typeof value.title === "string" && value.title ? value.title : "Untitled workflow",
    nodes: rows(value.nodes).filter(isObject), edges: rows(value.edges).filter(isObject),
    ...(marked ? {execution_contract: value.execution_contract} : {})});
}

export function projectWorkflow(payload) {
  const valid = (document) => !isObject(document) || !Object.hasOwn(document, "execution_contract")
    || document.execution_contract === "bounded-run-v1";
  return valid(payload?.published) && valid(payload?.draft?.document) ? projectLegacyWorkflow(payload) : null;
}
