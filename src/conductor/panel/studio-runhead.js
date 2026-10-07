"use strict";
// The Runs header of one read run: its name, a line of where it stands and whether a person is
// needed, and the one main action (port spec §5.1). Presentation only: every word restates the
// same fresh run read, and every action is an existing door or a move of focus to one.
import {element} from "./command-view.js";
import {localize} from "./studio-i18n.js";
import {offeredControl} from "./studio-runstep.js";

const rows = (value) => Array.isArray(value) ? value : [];
const POSITIONS = Object.freeze(["open", "complete", "stalled"]);
const FOCUSABLE = "button:not([disabled]),select:not([disabled]),input:not([disabled]),"
  + "textarea:not([disabled]),summary";

//: The situation only when this read is live and whole: a closed stream or an older read says nothing.
function freshSituation(state, detail) {
  const situation = detail?.graph?.situation;
  return state.connection === "open" && state.runs.phase === "ready" && situation ? situation : null;
}
function needed(situation, reason) {
  return situation.checked.find((row) => row.reason === reason && row.count > 0) || null;
}
function recordsOf(detail, kind) {
  return rows(detail.records).filter((row) => row.record_type === kind).map((row) => row.record || {});
}
function titleOf(detail, nodeId) {
  return rows(detail.graph?.definition?.nodes).find((row) => row.node_id === nodeId)?.title || nodeId;
}

//: The run's last result succeeded AND every evidence it names was verified; an ended run alone is no result.
function verifiedResult(detail) {
  const last = recordsOf(detail, "action_result").at(-1);
  const evidence = new Map(recordsOf(detail, "evidence").map((row) => [row.evidence_id, row]));
  return last?.outcome === "succeeded" && rows(last.evidence_refs).length > 0
    && last.evidence_refs.every((id) => evidence.get(id)?.verification === "verified");
}

//: What each position row draws, asked of the row's own rule (`offeredControl`) with the rows joined
//: exactly as the Runs screen joins them, in the order it draws them. The header never keeps a second
//: copy of that rule, so it can only point at a form the screen really draws.
const DRAWS = Object.freeze({propose: "propose", repropose: "propose", confirm: "confirm"});
function offers(detail) {
  const planned = new Map(rows(detail.graph?.definition?.nodes).map((node) => [node.node_id, node]));
  const standing = new Map(rows(detail.graph?.schedule?.nodes).map((row) => [row.node_id, row]));
  return rows(detail.graph?.runtime?.nodes).map((runtime) => ({node: runtime.node_id, offer: offeredControl(
    planned.get(runtime.node_id) || {}, runtime, standing.get(runtime.node_id) || null, detail)}));
}

//: The first row of the §5.1 table that holds. A need for a person is acted on only while the read
//: says a person IS needed; an unknown or missing situation is read again, never guessed at.
export function runAction(state, detail) {
  const situation = freshSituation(state, detail);
  if (situation === null) return {key: "refresh"};
  if (situation.state === "required") {
    if (needed(situation, "gate_decision")) return {key: "decide"};
    const confirm = needed(situation, "confirmation");
    if (confirm) {
      // A proposal waits in Confirm AND in Propose; only the form the row draws is a door. A run whose
      // mode confirms nothing gets the sentence, and a legacy proposal the row re-proposes gets Propose.
      const proposal = recordsOf(detail, "action_proposal").find((row) => row.proposal_id === confirm.sources[0]);
      const row = offers(detail).find((item) => item.node === proposal?.node_id);
      if (row && DRAWS[row.offer]) return {key: DRAWS[row.offer], node: row.node};
      if (row?.offer === "proposals_only") return {key: "awaiting", node: row.node};
    }
    const document = needed(situation, "input_document");
    if (document) return {key: "document", node: document.sources[0]};
    if (needed(situation, "reconcile")) return {key: "reconcile"};
    if (needed(situation, "attempt_bound")) return {key: "workflow"};
  }
  if (needed(situation, "run_ended") && verifiedResult(detail)) return {key: "result"};
  if (situation.state === "not_required") {
    const row = offers(detail).find((item) => DRAWS[item.offer] === "propose");
    if (row) return {key: "propose", node: row.node};
  }
  return {key: "refresh"};
}

function situationLine(state, detail) {
  const situation = freshSituation(state, detail);
  const schedule = detail.graph?.schedule?.run_state;
  const position = situation !== null && needed(situation, "run_ended") ? "ended"
    : POSITIONS.includes(schedule) ? schedule : "position_unknown";
  const human = situation === null ? [localize(state, "bridge.unknown")]
    : [localize(state, `bridge.${situation.state}`), ...situation.checked
      .filter((row) => row.reason !== "run_ended" && row.count > 0)
      .map((row) => localize(state, `bridge.${row.reason}`, {count: String(row.count)}))];
  return element("p", {className: "studio-runs__situation", "data-run-situation": situation?.state || "unknown"}, [
    element("strong", {text: localize(state, `runhead.${position}`)}),
    element("span", {text: ` · ${human.join(" · ")}`})]);
}

export function runHeading(state, detail, title) {
  return element("div", {className: "studio-runs__heading"}, [
    element("h2", {text: title}), situationLine(state, detail)]);
}

//: The chosen run's cycle, read off its own frozen configuration and plan: which process and revision,
//: who carries it, and each loop's OWN bound and return -- never one number for loops that differ.
export function cycleCard(state, detail, crewOpen) {
  const config = detail.config || {}, nodes = rows(detail.graph?.definition?.nodes);
  const workflow = config.workflow, instances = rows(config.instances);
  const named = workflow ? rows(state.workflows?.list).find((row) => row.workflow_id === workflow.id) : null;
  const loops = nodes.filter((node) => node.kind === "loop" && node.loop);
  const crew = element("details", {"data-cycle-crew": ""}, [
    element("summary", {text: localize(state, "cycle.roster")}),
    element("ul", {}, instances.map((row) => element("li", {"data-cycle-member": row.id,
      text: `${row.id} · ${row.adapter}`}))),
    element("p", {text: localize(state, "cycle.frozen")})]);
  crew.open = crewOpen;
  return element("section", {className: "studio-bridge__box studio-cycle-card", "data-cycle-run": detail.run.run_id}, [
    element("h3", {text: localize(state, "cycle.title")}),
    element("strong", {text: workflow ? localize(state, "cycle.process",
      {title: named?.title || workflow.id, revision: String(workflow.revision)}) : localize(state, "runs.copy_14")}),
    element("p", {text: localize(state, "cycle.crew", {count: String(instances.length),
      gates: String(nodes.filter((node) => node.kind === "gate").length)})}),
    ...(loops.length ? loops.map((node) => element("p", {"data-cycle-loop": node.node_id,
      text: localize(state, "cycle.loop", {title: node.title || node.node_id, bound: String(node.loop.bound),
        step: titleOf(detail, node.loop.back_to)})})) : [element("p", {text: localize(state, "cycle.no_loops")})]),
    crew]);
}

function focusIn(selector) {
  return () => {
    const target = document.querySelector(`#bodyRuns ${selector}`);
    if (!target) return;
    target.scrollIntoView({block: "center"});
    const control = target.matches(FOCUSABLE) ? target : target.querySelector(FOCUSABLE);
    if (control) control.focus({preventScroll: true});
  };
}

//: The main action of a chosen run, in the header slot. `reconcile` and `awaiting` are sentences, not
//: buttons: this window cannot reconcile, nor confirm in a run whose mode withholds confirmation, and a
//: control that could not would be a false door.
export function runPrimary(state, handlers, detail) {
  const chosen = runAction(state, detail), runId = detail.run.run_id;
  const title = chosen.node ? titleOf(detail, chosen.node) : null;
  const text = localize(state, `runhead.${chosen.key}`, title === null ? undefined : {title});
  if (["reconcile", "awaiting"].includes(chosen.key)) {
    return element("p", {className: "studio-hint", "data-run-action": chosen.key, text});
  }
  const door = (name, argument) => typeof handlers[name] === "function" ? () => handlers[name](argument) : null;
  const invoke = {
    decide: door("showDecisions", runId),
    confirm: focusIn(`[data-step="confirm:${chosen.node}"]`),
    document: focusIn('[data-section="documents"]'),
    workflow: door("onScreen", "workflow"),
    result: focusIn(".studio-artifacts"),
    propose: focusIn(`[data-step="propose:${chosen.node}"]`),
    refresh: door("onRefreshRun"),
  }[chosen.key];
  const control = element("button", {className: "studio-btn", type: "button", "data-run-action": chosen.key,
    "data-focus": chosen.key === "refresh" ? "action:onRefreshRun" : `action:run-${chosen.key}`, text});
  if (invoke === null) control.disabled = true;
  else control.addEventListener("click", invoke);
  return control;
}
