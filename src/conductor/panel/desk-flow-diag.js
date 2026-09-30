"use strict";
// The server's answer about a cycle, drawn: its counter and the rows of «Что мешает публикации»
// (spec 5.6.3, 7.4, 7.8).
//
// Nothing here is worked out. A number is the server's number (`plan_budget`), a row is the server's
// row with the wording the wizard already gives that code, and its address is the step or road the
// row names. The panel adds only the way from a row to its place (a «Показать» that selects the step
// or road) and the two fixes the spec gives a row a button for: «Поставить доработку раньше» for
// `loop_order` and «Заменить на „при успехе“» for an `always` road out of an agent. When the rows or
// the counter are older than the latest edit they say so, so nothing on screen claims more than the
// server said.
import {element} from "./command-view.js";
import {timeText} from "./desk-wizard-draw.js";
import {action, knownText, stepLabel} from "./desk-flow-draw.js";

const line = (name, text, extra = {}) => element("p", {[name]: "", text, ...extra});

/** The counter exactly as the server counted it; stale when an edit has gone out since. */
export function counterView(ctx) {
  const counter = ctx.view.counter;
  if (counter === null) return [element("p", {"data-flow-counter-none": "",
    text: ctx.t("wizard.budget.none")})];
  const row = (name, key, pair) => line(`data-counter-${name}`, ctx.t(key, {actions:
    String(pair.actions), time: timeText(ctx, pair.seconds)}),
  {"data-actions": String(pair.actions), "data-seconds": String(pair.seconds)});
  const limit = counter.limit === null ? [] : [line("data-counter-limit", ctx.t("wizard.budget.limit",
    {actions: String(counter.limit)}))];
  const stale = counter.stale ? [line("data-counter-stale", ctx.t("schema.counter.stale"))] : [];
  return [element("section", {className: "desk-flow__counter", "data-flow-counter": "",
    "data-stale": String(counter.stale)}, [element("h3", {text: ctx.t("wizard.budget.heading")}),
  row("clean", "wizard.budget.clean", counter.clean),
  row("worst", "wizard.budget.worst", counter.worst), ...limit, ...stale])];
}

function address(ctx, at) {
  if (at !== null && typeof at?.step_id === "string") {
    return {text: ctx.t("wizard.diag.at_step", {step: stepLabel(ctx, at.step_id)}),
      selection: {kind: "node", id: at.step_id}};
  }
  if (Array.isArray(at?.link) && at.link.length === 3) {
    const [from, to] = at.link.map(String);
    return {text: ctx.t("wizard.diag.at_link", {from: stepLabel(ctx, from),
      to: stepLabel(ctx, to)}), selection: {kind: "edge", id: `${from} ${to}`}};
  }
  return null;
}

//: The fixes a row may carry a button for, by what the row says and never by guessing.
function fixes(ctx, row, first) {
  const out = [];
  if (row.code === "loop_order" && first.has("loop_order") === false) {
    first.add("loop_order");
    out.push(action("schema:fix:rework-first", ctx.t("schema.fix.rework_first"),
      () => ctx.send({type: "edit", edit: {type: "reorder", reworkFirst: true}})));
  }
  const link = Array.isArray(row.at?.link) ? row.at.link.map(String) : null;
  const source = link === null ? undefined : ctx.view.flow?.steps.find((one) => one.step_id === link[0]);
  if (row.code === "link_outside_desk" && link?.[2] === "always" && source?.type === "agent") {
    out.push(action(`schema:fix:when-success:${link[0]}:${link[1]}`,
      ctx.t("schema.fix.when_success"), () => ctx.send({type: "edit", edit: {
        type: "set-edge-condition", fromId: link[0], toId: link[1], value: "success"}})));
  }
  return out;
}

function rowView(ctx, row, at, first) {
  const where = address(ctx, row.at);
  const text = knownText(ctx, `wizard.diag.${row.code}`, "", undefined) || ctx.t(
    "wizard.diag.unknown", {code: String(row.code)});
  const show = where === null ? [] : [action(`schema:diag:show:${at}`, ctx.t("schema.diag.show"),
    () => ctx.send({type: "select", selection: where.selection}))];
  return element("li", {"data-diag": row.code, "data-severity": row.severity}, [
    element("strong", {text: ctx.t(row.severity === "error" ? "wizard.diag.error"
      : "wizard.diag.warning")}), element("span", {text: ` ${text}`}),
    ...(where === null ? [] : [element("small", {text: ` ${where.text}`})]), ...show,
    ...fixes(ctx, row, first)]);
}

/** «Что мешает публикации»: the rows the server gave, in its order, each with its address. */
export function diagnosticsView(ctx) {
  const {rows, refused, stale} = ctx.view;
  const notes = [...(refused === null ? [] : [line("data-diag-refused", ctx.t("schema.diag.refused"))]),
    ...(stale && refused === null ? [line("data-diag-stale", ctx.t("schema.diag.stale"))] : [])];
  const first = new Set();
  const body = rows.length === 0 ? [element("p", {"data-diag-none": "",
    text: ctx.t("wizard.diag.none")})]
    : [element("ul", {}, rows.map((row, at) => rowView(ctx, row, at, first)))];
  return [element("section", {className: "desk-flow__diagnostics", "data-flow-diag": ""},
    [element("h3", {text: ctx.t("schema.diag.heading")}), ...notes, ...body])];
}
