"use strict";
// Facts accompanying an optional recommendation. All time arithmetic belongs to the server.
export const DEPTH = Object.freeze(["quick", "balanced", "thorough"]);
export const BOUNDS = Object.freeze(["max_actions", "max_action_seconds",
  "max_total_task_seconds", "duration_seconds"]);

export function limitFields(terms) {
  return Object.fromEntries([...BOUNDS, "node_limits"].map((key) => [key, terms[key]]));
}
const whole = (n) => Number.isSafeInteger(n) && n >= 0;
const positive = (n) => whole(n) && n > 0;
const exact = (o, keys) => o !== null && typeof o === "object" && !Array.isArray(o)
  && Object.keys(o).length === keys.length && keys.every((key) => Object.hasOwn(o, key));

export function validRecommendation(info, terms) {
  const counts = ["base_seconds", "step_count", "checker_steps", "effect_steps", "resources", "input_bytes",
    "history_samples"];
  const steps = terms.node_limits.map((row) => row.node_id);
  return exact(info, [...counts, "depth", "status", "history", "limited_steps"])
    && DEPTH.includes(info.depth) && info.status === "preliminary"
    && counts.every((key) => whole(info[key])) && info.step_count === steps.length
    && info.checker_steps <= steps.length && info.effect_steps <= steps.length
    && Array.isArray(info.limited_steps) && info.limited_steps.every((id) => steps.includes(id))
    && new Set(info.limited_steps).size === info.limited_steps.length
    && Array.isArray(info.history) && info.history.every((row) =>
      exact(row, ["step_id", "samples", "min_seconds", "max_seconds"]) && steps.includes(row.step_id)
      && positive(row.samples) && positive(row.min_seconds) && positive(row.max_seconds)
      && row.max_seconds >= row.min_seconds)
    && new Set(info.history.map((row) => row.step_id)).size === info.history.length
    && info.history.reduce((sum, row) => sum + row.samples, 0) === info.history_samples;
}

export function guidanceHeadline(info, t) {
  return info.history_samples ? t("wizard.budget.measured", {count: String(info.history_samples)})
    : t("wizard.budget.no_history");
}

export function guidanceText(info, t, time) {
  const lines = [t("wizard.budget.basis", {steps: String(info.step_count),
    checked: String(info.checker_steps), work: String(info.effect_steps),
    size: String(Math.ceil(info.input_bytes / 1024))}),
    t("wizard.budget.baseline", {time: time(info.base_seconds)})];
  if (info.resources) lines.push(t("wizard.budget.resources", {count: String(info.resources)}));
  for (const row of info.history) {
    lines.push(t("wizard.budget.history", {step: row.step_id, count: String(row.samples),
      min: time(row.min_seconds), max: time(row.max_seconds)}));
  }
  if (info.limited_steps.length) lines.push(t("wizard.budget.limited",
    {steps: info.limited_steps.join(", ")}));
  return lines;
}
