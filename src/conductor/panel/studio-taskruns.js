"use strict";
// Catalogue selection preserves every UTC fractional digit, without Date.
import {isInstant} from "./studio-model.js";

export function compareInstants(left, right) {
  if (!isInstant(left) || !isInstant(right)) throw new Error("Invalid UTC instant");
  const a = left.slice(0, 19), b = right.slice(0, 19);
  if (a !== b) return a < b ? -1 : 1;
  const fraction = (value) => value.slice(19).replace(/(?:Z|\+00:00)$/, "").replace(/^\./, "");
  const x = fraction(left), y = fraction(right), length = Math.max(x.length, y.length);
  const p = x.padEnd(length, "0"), q = y.padEnd(length, "0");
  return p === q ? 0 : p < q ? -1 : 1;
}

export function newestRun(runs, taskId) {
  if (runs.phase !== "ready") return {state: "unknown", row: null};
  // An unreadable journal hides both task identity and timestamp. An older
  // readable success cannot stand in for a newest run we cannot establish.
  if (runs.list.some((row) => row.unreadable || !isInstant(row.created_at))) {
    return {state: "unknown", row: null};
  }
  const selected = runs.list.filter((row) => taskId === undefined || row.task_id === taskId).sort((a, b) =>
    -compareInstants(a.created_at, b.created_at) || (a.run_id < b.run_id ? -1 : a.run_id > b.run_id ? 1 : 0));
  return {state: selected.length ? "known" : "none", row: selected[0] || null};
}
