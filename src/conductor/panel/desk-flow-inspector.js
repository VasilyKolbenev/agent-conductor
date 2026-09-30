"use strict";
// The inspector of the «Схема»: the rows of a step, a gate, a loop, a road or the cycle itself, and
// the actions on them (spec 5.6.3, 7.2.1, 7.7).
//
// It draws what `desk-flow-fields.js` says and sends what the person does as one event of the
// model's closed table: a typed letter is `field-input`, leaving the field is `field-commit`, a
// choice is committed at once, an action is one `edit` of the flow's vocabulary. The raw fields of the
// old Studio are the «Расширенные поля» fold: a key the step holds is shown as JSON, with «Применить»
// and «Вернуть вычисленное»; a key it does not hold says the compiler computes it and is written only
// when a value is applied. The copies of the edit vocabulary below are held equal to the flow's edits
// and to the canvas's by `tests/test_desk_flow_guards.py`: a word added to one and not the others is a
// control writing an edit nothing applies.
import {element} from "./command-view.js";
import {clearEdit, extCount, flowRows, roadWords, stepRows} from "./desk-flow-fields.js";
import {draftKey} from "./desk-flow-model.js";
import {isLoop} from "./desk-flow-shape.js";
import {action, knownText, stepLabel, stepName, textControl, whenWord} from "./desk-flow-draw.js";

//: The canvas's nine words, and every name a `set-field` may carry (copies; see the header).
export const EDIT_TYPES = Object.freeze(["add", "connect", "delete-edge", "delete-node",
  "duplicate", "move", "reorder", "set-edge-condition", "set-field"]);
export const EDIT_FIELDS = Object.freeze(["arguments", "attempt_bound", "back_to", "bound",
  "capability", "execution_contract", "failure_policy", "flow_title", "gate_id",
  "instruction_from", "missing_artifact_policy", "passes", "purpose", "reads",
  "required_evidence", "resources", "review_profile", "rework", "role_id", "stage",
  "success_requires", "timeout_seconds", "title", "verifier_role_id"]);

function edit(ctx, body) {
  if (!EDIT_TYPES.includes(body.type)) throw new Error("not a word of the edit vocabulary");
  ctx.send({type: "edit", edit: body});
}

const typed = (ctx, nodeId, row) => ctx.view.drafts[draftKey(nodeId, row.field)]?.text ?? row.text;

// -- the controls ------------------------------------------------------------------------

function optionText(ctx, field, value) {
  if (field === "capability") return knownText(ctx, `schema.capability.${value}`, value);
  if (field === "review_profile") return ctx.t(`schema.profile.${value === "" ? "none" : value}`);
  if (field === "instruction_from" && value === "") return ctx.t("schema.profile.none");
  if (field === "instruction_from" || field === "back_to") return stepLabel(ctx, value);
  if (field === "execution_contract") {
    return ctx.t(value === "none" ? "schema.contract.none" : "schema.contract.bounded");
  }
  return value;
}

function selectControl(ctx, row, nodeId) {
  const select = element("select", {"data-focus": `schema:field:${row.field}`, name: row.field},
    row.options.map((value) => element("option", {value, text: optionText(ctx, row.field, value)})));
  select.value = typed(ctx, nodeId, row);
  select.addEventListener("change", () => ctx.send({type: "field-commit", nodeId,
    field: row.field, text: select.value}));
  return select;
}

function textField(ctx, row, nodeId) {
  const json = row.control === "json";
  return textControl({key: `schema:field:${row.field}`, name: row.field,
    multi: json || row.control === "area", rows: json ? 6 : 3, value: typed(ctx, nodeId, row),
    onInput: (text) => ctx.send({type: "field-input", nodeId, field: row.field, text}),
    onCommit: (text) => {
      if (!json || text.trim() !== "") {
        ctx.send({type: "field-commit", nodeId, field: row.field, text});
      }
    }});
}

function hintFor(ctx, row, step) {
  if (row.field !== "timeout_seconds") return [];
  const key = step.verifier_role_id ? "schema.hint.timeout_checked" : "schema.hint.timeout_plain";
  return [element("small", {"data-hint": row.field, text: ctx.t(key)})];
}

function rowView(ctx, row, nodeId, step) {
  const control = row.control === "select" ? selectControl(ctx, row, nodeId)
    : textField(ctx, row, nodeId);
  return element("label", {className: "desk-flow__field", "data-field": row.field},
    [element("span", {text: ctx.t(`schema.field.${row.field}`)}), control,
      ...(step === null ? [] : hintFor(ctx, row, step))]);
}

// -- the advanced fields -----------------------------------------------------------------

function extRow(ctx, row, nodeId) {
  const control = textField(ctx, row, nodeId);
  const apply = action(`schema:ext:apply:${row.field}`, ctx.t(row.set ? "schema.ext.apply"
    : "schema.ext.set"), () => ctx.send({type: "field-commit", nodeId, field: row.field,
    text: control.value}));
  const reset = row.set ? [action(`schema:ext:reset:${row.field}`, ctx.t("schema.ext.reset"),
    () => edit(ctx, clearEdit(nodeId, row.field)))] : [];
  const computed = row.set ? [] : [element("small", {"data-ext-computed": "",
    text: ctx.t("schema.ext.computed")})];
  return element("div", {className: "desk-flow__ext", "data-ext-row": row.field,
    "data-set": String(row.set)}, [element("label", {}, [element("span",
    {text: ctx.t(`schema.field.${row.field}`)}), control]), ...computed, apply, ...reset]);
}

//: A fold whose openness the model keeps. The press on its heading is the model's to answer, not the
//: browser's: the page's own toggle would come a moment later, and a pass that ran in between would
//: draw the fold shut again over what the person had just opened.
function fold(ctx, key, count, children) {
  const open = ctx.view.sections[key] === true;
  const details = element("details", {className: "desk-flow__fold", "data-fold": key});
  details.open = open;
  const heading = element("summary", {"data-focus": `schema:fold:${key}`, text: count > 0
    ? ctx.t("schema.section.ext_count", {count: String(count)}) : ctx.t("schema.section.ext")});
  heading.addEventListener("click", (event) => {
    event.preventDefault();
    ctx.send({type: "section", key, open: !open});
  });
  details.append(heading, ...children);
  return details;
}

// -- a step ------------------------------------------------------------------------------

function sections(rows) {
  const order = [];
  for (const row of rows) if (!order.includes(row.section)) order.push(row.section);
  return order.map((name) => [name, rows.filter((row) => row.section === name)]);
}

function stepActions(ctx, step) {
  const id = step.step_id, flow = ctx.view.flow;
  const band = flow.steps.filter((one) => isLoop(one) === isLoop(step));
  const at = band.findIndex((one) => one.step_id === id);
  const behind = ctx.view.forks.some((fork) => fork.branches.some((branch) => branch.number > 1
    && branch.steps.includes(id)));
  const move = (key, index) => action(`schema:step:${key}`, ctx.t(`schema.step.${key}`),
    () => edit(ctx, {type: "reorder", nodeId: id, index}));
  return element("div", {className: "desk-flow__actions", role: "group"}, [
    action("schema:step:duplicate", ctx.t("schema.step.duplicate"),
      () => edit(ctx, {type: "duplicate", nodeId: id})),
    ...(at > 0 ? [move("earlier", at - 1)] : []),
    ...(at < band.length - 1 ? [move("later", at + 1)] : []),
    ...(behind ? [action("schema:step:branch-first", ctx.t("schema.step.branch_first"),
      () => edit(ctx, {type: "reorder", nodeId: id, branchFirst: true}))] : []),
    action("schema:step:delete", ctx.t("schema.step.delete"),
      () => edit(ctx, {type: "delete-node", nodeId: id}))]);
}

function stepPanel(ctx) {
  const step = ctx.view.selection.step, id = step.step_id;
  const all = stepRows(ctx.view.flow, step).filter((row) => EDIT_FIELDS.includes(row.field));
  const body = sections(all.filter((row) => row.section !== "ext")).map(([name, rows]) =>
    element("section", {"data-section": name}, [element("h4", {text: ctx.t(`schema.section.${name}`)}),
      ...rows.map((row) => rowView(ctx, row, id, step))]));
  const ext = all.filter((row) => row.section === "ext");
  return [element("h3", {text: stepName(ctx, step)}), ...body, stepActions(ctx, step),
    ...(ext.length === 0 ? [] : [fold(ctx, "ext", extCount(step),
      ext.map((row) => extRow(ctx, row, id)))])];
}

// -- a road ------------------------------------------------------------------------------

//: A select of words: choosing one writes it; the row's empty option is a label and writes nothing.
function wordSelect(ctx, link, spec) {
  const select = element("select", {"data-focus": spec.key, name: spec.name}, [
    ...(spec.blank === null ? [] : [element("option", {value: "", text: spec.blank})]),
    ...spec.words.map((word) => element("option", {value: word, text: whenWord(ctx, word)}))]);
  select.value = spec.value;
  select.addEventListener("change", () => {
    if (select.value !== "") edit(ctx, {type: "set-edge-condition", fromId: link.from,
      toId: link.to, value: select.value});
  });
  return select;
}

const labelled = (ctx, name, key, control) => element("label", {className: "desk-flow__field",
  "data-field": name}, [element("span", {text: ctx.t(key)}), control]);

//: The road's own «Расширенные поля»: every word the desk does not draw by default, and the way back
//: to the ordinary word of the step the road leaves (there is none for a loop or a route).
function roadFold(ctx, link, words) {
  const other = wordSelect(ctx, link, {key: "schema:field:when-extra", name: "when-extra",
    words: words.extra, blank: ctx.t("schema.road.ordinary"), value: words.outside ? link.when : ""});
  const back = words.outside && words.home !== null ? [action("schema:road:home",
    ctx.t("schema.road.home"), () => edit(ctx, {type: "set-edge-condition", fromId: link.from,
      toId: link.to, value: words.home}))] : [];
  return fold(ctx, "road", words.outside ? 1 : 0, [labelled(ctx, "when-extra",
    "schema.field.when_extra", other), ...back]);
}

function roadPanel(ctx) {
  const link = ctx.view.selection.link, flow = ctx.view.flow;
  const words = roadWords(flow, link);
  const main = wordSelect(ctx, link, {key: "schema:field:when", name: "when", words: words.main,
    blank: words.outside ? ctx.t("schema.road.extended") : null,
    value: words.outside ? "" : link.when});
  const source = flow.steps.find((one) => one.step_id === link.from);
  const success = link.when === "always" && source?.type === "agent"
    ? [action("schema:road:success", ctx.t("schema.fix.when_success"), () => edit(ctx,
      {type: "set-edge-condition", fromId: link.from, toId: link.to, value: "success"}))] : [];
  return [element("h3", {text: ctx.t("schema.road.between", {from: stepLabel(ctx, link.from),
    to: stepLabel(ctx, link.to)})}), labelled(ctx, "when", "schema.field.when", main), ...success,
  roadFold(ctx, link, words),
  action("schema:road:delete", ctx.t("schema.road.delete"),
    () => edit(ctx, {type: "delete-edge", fromId: link.from, toId: link.to}))];
}

// -- the cycle ---------------------------------------------------------------------------

function flowPanel(ctx) {
  const rows = flowRows(ctx.view.flow).filter((row) => EDIT_FIELDS.includes(row.field));
  const [name, contract] = [rows[0], rows[1]];
  return [element("p", {"data-inspector-none": "", text: ctx.t("schema.inspector.none")}),
    element("h3", {text: ctx.t("schema.section.flow")}), rowView(ctx, name, null, null),
    fold(ctx, "flow", Object.keys(ctx.view.flow.ext).length, [rowView(ctx, contract, null, null)])];
}

/** The inspector of what is selected: a step, a road, or (nothing selected) the cycle itself. */
export function inspector(ctx) {
  const chosen = ctx.view.selection;
  const kind = chosen === null ? "flow" : chosen.kind;
  const name = kind === "step" ? chosen.step.step_id
    : kind === "road" ? `${chosen.link.from} ${chosen.link.to}` : "";
  return element("aside", {className: "desk-flow__inspector", "data-flow-inspector": "",
    "data-selected": name, "data-subject": `${kind}:${name}`,
    "aria-label": ctx.t("schema.inspector.label")},
  {flow: flowPanel, step: stepPanel, road: roadPanel}[kind](ctx));
}
