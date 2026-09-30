"use strict";
// The «Схема» panel, drawn: `mountFlow(mount, state, handlers)` and nothing else exported.
//
// It writes text nodes only (no markup is ever parsed), one `replaceChildren` per pass, and reads
// nothing but the state it is given: `state.schema` is the model's slice (`desk-flow-model.js`) and
// `state.locale` the language. It touches no wire, no storage and no clock. Every gesture goes out as
// one event of the model's closed table through `handlers.onFlow`; what the panel wants from a server
// is the model's business (an ask it returns), and the host that owns the doors performs it. A
// control that cannot be used says why beside it, never as a button that does nothing.
//
// The canvas is the Studio's (`studio-canvas.js`), fed a flow's projection (`desk-flow-graph.js`):
// its element outlives a pass, so the lens a person chose (the trace or the orbit) and the help they
// opened stay as they were. The inspector is `desk-flow-inspector.js`, the server's counter and rows
// are `desk-flow-diag.js`, and the pieces they share are `desk-flow-draw.js`.
import {element} from "./command-view.js";
import {noticeText} from "./studio-i18n.js";
import {mountCanvas} from "./studio-canvas.js";
import {flowGraph} from "./desk-flow-graph.js";
import {QUICK_KINDS} from "./desk-quickcycle.js";
import {ROLE_KINDS} from "./desk-flow-shape.js";
import {action, context, stepName, textControl, whenWord} from "./desk-flow-draw.js";
import {counterView, diagnosticsView} from "./desk-flow-diag.js";
import {inspector} from "./desk-flow-inspector.js";

const SVG = "http://www.w3.org/2000/svg";
const SAVE_LINES = Object.freeze(["pending", "saving", "saved", "refused", "conflict", "unknown"]);
//: The canvas's own element per mount, so a lens or an opened help survives a pass.
const CANVASES = new WeakMap();

// -- the head: which cycle, and where the list of cycles is --------------------------------

function sourceLine(ctx) {
  const view = ctx.view;
  if (view.workflowId === null) return [];
  const words = {draft: ctx.t("schema.source.draft"), none: ctx.t("schema.source.none"),
    published: ctx.t("schema.source.published", {revision: String(view.latest)})};
  const latest = view.source === "draft" && view.latest !== null
    ? ` · ${ctx.t("schema.source.latest", {revision: String(view.latest)})}` : "";
  return [element("p", {className: "desk-flow__source", "data-flow-source": view.source ?? "none"},
    [element("code", {text: view.workflowId}),
      element("span", {text: ` ${words[view.source ?? "none"]}${latest}`})])];
}

function optionLabel(ctx, row) {
  const title = typeof row.title === "string" && row.title !== "" ? row.title : row.workflow_id;
  if (row.unreadable === true) return ctx.t("schema.pick.unreadable", {title});
  if (row.has_draft === true) return ctx.t("schema.pick.draft", {title});
  return Number.isInteger(row.latest_revision) ? ctx.t("schema.pick.revision",
    {title, revision: String(row.latest_revision)}) : title;
}

function picker(ctx) {
  const {cycles, workflowId, flow} = ctx.view;
  const listed = cycles.some((row) => row.workflow_id === workflowId);
  const options = [element("option", {value: "", text: ctx.t("schema.pick.none")}),
    ...(flow !== null && !listed && workflowId !== null ? [element("option",
      {value: workflowId, text: ctx.t("schema.pick.new")})] : []),
    ...cycles.filter((row) => typeof row.workflow_id === "string").map((row) =>
      element("option", {value: row.workflow_id, text: optionLabel(ctx, row)}))];
  const select = element("select", {"data-focus": "schema:pick", name: "cycle"}, options);
  select.value = workflowId ?? "";
  select.addEventListener("change", () => {
    if (select.value !== "") ctx.send({type: "open", workflowId: select.value, title: ""});
  });
  const error = ctx.view.listError === null ? [] : [element("small", {"data-flow-list-error": "",
    text: ctx.t("schema.pick.error")})];
  return element("label", {className: "desk-flow__pick"},
    [element("span", {text: ctx.t("schema.pick.label")}), select, ...error]);
}

//: A starter by the name the product gives it; one it has no name for by the server's own title.
function starterName(ctx, row) {
  const names = {"desk-standard": "wizard.cycle.name_standard", "desk-short": "wizard.cycle.name_short",
    "desk-starter-docs": "wizard.cycle.name_starter_docs", "dalio-v5": "schema.starter.dalio_v5"};
  if (Object.hasOwn(names, row.starter_id)) return ctx.t(names[row.starter_id]);
  return typeof row.title === "string" && row.title !== "" ? row.title : row.starter_id;
}

function beginMenu(ctx) {
  const starters = ctx.view.starters.filter((row) => typeof row.starter_id === "string");
  const copy = ctx.view.copyable ? null : ctx.t("schema.write.copy_needs_revision");
  return element("div", {className: "desk-flow__begin", role: "group",
    "aria-label": ctx.t("schema.new.label")}, [
    action("schema:new:blank", ctx.t("schema.new.blank"), () => ctx.send({type: "new",
      from: "empty", title: ctx.t("schema.new.title")})),
    ...starters.map((row) => action(`schema:new:starter:${row.starter_id}`, ctx.t(
      "schema.new.from", {title: starterName(ctx, row)}), () => ctx.send({type: "new",
      from: "starter", id: row.starter_id}))),
    action("schema:new:copy", ctx.t("schema.new.copy"), () => ctx.send({type: "new",
      from: "copy"}), copy),
    action("schema:new:quick", ctx.t("schema.new.quick"), () => ctx.send({type: "quick-open"}))]);
}

// -- the toolbar and its lines -------------------------------------------------------------

function publishControl(ctx, closed) {
  const {publishWhy} = ctx.view, label = ctx.t("schema.publish");
  if (closed !== null) return [action("schema:publish", label, () => {}, closed)];
  if (publishWhy === "open") return [];
  if (publishWhy === null) {
    return [action("schema:publish", label, () => ctx.send({type: "publish-request"}))];
  }
  return [element("button", {type: "button", "data-focus": "schema:publish", disabled: "",
    "aria-disabled": "true", text: label}), element("small", {"data-flow-publish-why": "",
    text: ctx.t(`schema.publish.${publishWhy}`)})];
}

function toolbar(ctx) {
  const view = ctx.view;
  const closed = view.phase === "ready" && view.flow !== null ? null : ctx.t("schema.write.edit_wait");
  return element("div", {className: "desk-flow__toolbar", role: "group"}, [
    action("schema:check", ctx.t("schema.check"), () => ctx.send({type: "check"}), closed),
    action("schema:save", ctx.t("schema.save"), () => ctx.send({type: "save"}), closed),
    ...publishControl(ctx, closed),
    action("schema:pin", ctx.t("wizard.cycle.make_project"), () => {}, ctx.t("schema.pin.later"))]);
}

function publishedLine(ctx) {
  const done = ctx.view.published;
  if (done === null) return [];
  const key = done.created === true ? "created" : done.created === false ? "same" : "settled";
  return [element("p", {"data-flow-published": "", text: ctx.t(`schema.published.${key}`,
    {revision: String(done.revision)})})];
}

function lines(ctx) {
  const view = ctx.view;
  const say = (notice) => noticeText(ctx.state, notice);
  const save = SAVE_LINES.includes(view.save) ? ctx.t(`schema.saveline.${view.save}`) : "";
  const ready = !view.ready ? [] : [element("p", {"data-flow-ready": "", text: ctx.t(
    view.flow === null ? "schema.ready.none" : "schema.ready.note")})];
  return [element("p", {"data-flow-saveline": "", text: save}),
    element("p", {"data-flow-notice": "", role: "status", "aria-live": "polite",
      text: view.notice === null ? "" : say(view.notice)}),
    ...(view.status === null ? [] : [element("p", {"data-flow-status": "", text: say(view.status)})]),
    ...publishedLine(ctx), ...ready];
}

// -- the quick form and the review of a revision -------------------------------------------

function kindLabel(ctx, kind) {
  return kind === "custom" ? ctx.t("schema.kind.custom") : ctx.t(`wizard.role.${kind}`);
}

function quickForm(ctx) {
  const form = ctx.view.quick;
  if (form === null) return [];
  const rows = form.rows.map((kind, at) => element("li", {"data-quick-row": String(at)},
    [element("span", {text: kindLabel(ctx, kind)}), action(`schema:quick:remove:${at}`,
      ctx.t("schema.quick.remove"), () => ctx.send({type: "quick-remove", index: at}))]));
  const title = textControl({key: "schema:quick:title", name: "quick-title", multi: false,
    value: form.title, onInput: (value) => ctx.send({type: "quick-title", value}),
    onCommit: () => {}});
  return [element("section", {className: "desk-flow__quick", "data-flow-quick": ""}, [
    element("h3", {text: ctx.t("schema.quick.heading")}),
    element("label", {}, [element("span", {text: ctx.t("schema.field.flow_title")}), title]),
    element("div", {role: "group", "aria-label": ctx.t("schema.quick.add")},
      QUICK_KINDS.map((kind) => action(`schema:quick:add:${kind}`, kindLabel(ctx, kind),
        () => ctx.send({type: "quick-add", kind})))),
    element("p", {text: ctx.t("schema.quick.rows")}),
    rows.length === 0 ? element("p", {text: ctx.t("schema.quick.none")})
      : element("ol", {}, rows), element("small", {text: ctx.t("schema.quick.last")}),
    action("schema:quick:build", ctx.t("schema.quick.build"), () => ctx.send({type:
      "quick-build"})), action("schema:quick:close", ctx.t("schema.quick.close"),
      () => ctx.send({type: "quick-close"}))])];
}

function changeText(ctx, row) {
  const when = (word) => whenWord(ctx, word);
  const params = {flow_title: {before: row.before, after: row.after}, step_removed: {id: row.id},
    step_added: {id: row.id}, step_changed: {id: row.id, fields: (row.fields ?? []).join(", ")},
    link_removed: {from: row.from, to: row.to, when: when(row.when)},
    link_added: {from: row.from, to: row.to, when: when(row.when)},
    link_changed: {from: row.from, to: row.to, before: when(row.before), after: when(row.after)}};
  return ctx.t(`schema.change.${row.kind}`, params[row.kind] ?? {});
}

function reviewView(ctx) {
  const view = ctx.view;
  if (view.publishing === null) return [];
  const revision = String(view.publishing.revision);
  const first = view.latest === null ? [element("p", {text: ctx.t("schema.change.first")})] : [];
  const rows = view.review.length === 0 ? [element("p", {text: ctx.t("schema.change.none")})]
    : [element("ul", {}, view.review.map((row) => element("li", {"data-change": row.kind,
      text: changeText(ctx, row)})))];
  return [element("section", {className: "desk-flow__review", "data-flow-review": ""}, [
    element("h3", {text: ctx.t("schema.publish.heading", {revision})}), ...first, ...rows,
    action("schema:publish:confirm", ctx.t("schema.publish.confirm", {revision}),
      () => ctx.send({type: "publish-confirm"})), action("schema:publish:cancel",
      ctx.t("schema.publish.cancel"), () => ctx.send({type: "publish-cancel"}))])];
}

// -- the canvas ----------------------------------------------------------------------------

const ADD_KINDS = Object.freeze([...Object.keys(ROLE_KINDS), "decision", "loop"]);

function palette(ctx) {
  const edits = {decision: {type: "add", kind: "human"}, loop: {type: "add", kind: "loop"}};
  return ADD_KINDS.map((key) => ({key, text: ctx.t(`schema.add.${key}`),
    title: ctx.t("schema.add.hint"),
    edit: edits[key] ?? {type: "add", kind: "agent", roleKind: key}}));
}

function selectionOf(view) {
  const chosen = view.selection;
  if (chosen === null) return {};
  return chosen.kind === "step" ? {kind: "node", id: chosen.step.step_id}
    : {kind: "edge", id: `${chosen.link.from} ${chosen.link.to}`};
}

function canvasBlock(ctx, mount) {
  const view = ctx.view;
  let host = CANVASES.get(mount);
  if (host === undefined) {
    host = element("div", {className: "desk-flow__canvas", "data-flow-canvas": ""});
    CANVASES.set(mount, host);
  }
  host.setAttribute("aria-label", ctx.t("schema.canvas.label"));
  const graph = flowGraph(view.flow, {title: (step) => stepName(ctx, step),
    when: (word) => whenWord(ctx, word), waiting: ctx.t("schema.branch.waits"),
    severity: {error: ctx.t("wizard.diag.error"), warning: ctx.t("wizard.diag.warning")}}, view.rows);
  const state = {locale: ctx.state.locale, workflows: {draft: {nodes: graph.nodes,
    edges: graph.edges}, phase: "ready", diagnostics: [], selectedId: view.workflowId},
  canvas: {selection: selectionOf(view), pan: view.canvas.pan, zoom: view.canvas.zoom,
    palette: palette(ctx), banner: false}};
  mountCanvas(host, document.createElementNS(SVG, "svg"), state, {
    onEdit: (body) => ctx.send({type: "edit", edit: body}),
    onSelect: (selection) => ctx.send({type: "select", selection}),
    onView: (next) => ctx.send({type: "view", ...next}),
    onStatus: (notice) => ctx.send({type: "status", notice})});
  return host;
}

// -- the body ------------------------------------------------------------------------------

function notice(name, text, extra = {}) {
  return [element("p", {[name]: "", text, ...extra})];
}

function bodyOf(ctx, mount) {
  const view = ctx.view;
  if (view.phase === "failed") {
    return [...notice("data-flow-failed", ctx.t("schema.failed"), {"data-code": view.error ?? ""}),
      action("schema:retry", ctx.t("schema.retry"), () => ctx.send({type: "open",
        workflowId: view.workflowId, title: ""}))];
  }
  if (view.phase === "reading") return notice("data-flow-reading", ctx.t("schema.reading"));
  if (view.phase === "idle") return notice("data-flow-idle", ctx.t("schema.idle"));
  if (view.flow === null) return [];
  return [...(view.forks.length === 0 ? [] : notice("data-flow-branches",
    ctx.t("schema.branch.note"))), canvasBlock(ctx, mount), inspector(ctx), ...counterView(ctx),
  ...diagnosticsView(ctx)];
}

/** Draw the panel into `mount`: one pass, the whole of it. */
export function mountFlow(mount, state, handlers) {
  const ctx = context(state, handlers);
  const view = ctx.view;
  mount.replaceChildren(element("section", {className: "desk-flow", "data-flow": "",
    "data-flow-phase": view.phase, "data-flow-workflow": view.workflowId ?? "",
    "data-flow-save": view.save, "aria-label": ctx.t("schema.heading")}, [
    element("h2", {text: ctx.t("schema.heading")}), ...sourceLine(ctx), picker(ctx), beginMenu(ctx),
    toolbar(ctx), ...lines(ctx), ...quickForm(ctx), ...reviewView(ctx), ...bodyOf(ctx, mount)]));
}
