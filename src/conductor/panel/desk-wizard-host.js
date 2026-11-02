"use strict";
// The live desk's adapter for the existing six-step wizard. The reducer owns the chain and its
// asks; this host only supplies the shared transport, page identity, address and clock. A closed
// wizard has a new epoch, so a late read or write cannot reopen it or change another project.
import {path} from "./desk-transport.js";
import {cycleCards, initialWizard, openingFrom, resumeFrom, stepWizard} from "./desk-wizard-model.js";
import {wizardExit, wizardHash} from "./desk-wizard-run.js";
import {mountWizard} from "./desk-wizard.js";
import {MATERIAL_LIMITS, documentCard, isDocumentRow, textCard} from "./desk-wizard-materials.js";
import {evolve} from "./desk-wizard-base.js";

const outcome = (code) => ({status: "refused", code});
const token = (nonce) => nonce().replaceAll("-", "").toLowerCase().slice(0, 32);
const changed = (change, key) => change.steps.some((step) => step.key === key);
const DRAFT_TASK = /^task-[a-z0-9]{8,24}$/;
const DRAFT_ID = /^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$/;
const draftKey = (project, task) => `desk.first-task.v1:${project}:${task}`;

// The history entry carries only the task and confirmed project IDs. Typed
// answers stay in this tab. There is deliberately no path from storage to a grant.
function dropDraft() {
  try {
    const pointer = history.state?.deskTaskDraft;
    if (!pointer) return;
    const {deskTaskDraft, ...rest} = history.state;
    history.replaceState(rest, "");
    if (/^[0-9a-f]{32}$/.test(pointer.project) && DRAFT_TASK.test(pointer.task)) {
      sessionStorage.removeItem(draftKey(pointer.project, pointer.task));
    }
  } catch (_error) { /* Storage is optional on restricted browser profiles. */ }
}

function readDraft(project) {
  try {
    const pointer = history.state?.deskTaskDraft;
    if (!project || pointer?.project !== project || !DRAFT_TASK.test(pointer.task)) return null;
    const held = JSON.parse(sessionStorage.getItem(draftKey(project, pointer.task)));
    if (!held || !["title", "brief", "hint"].every((field) => typeof held[field] === "string")) return null;
    return {...held, taskId: pointer.task};
  } catch (_error) { return null; }
}

function draftMaterials(rows, documents) {
  if (!Array.isArray(rows)) return [];
  return rows.slice(0, MATERIAL_LIMITS.count).flatMap((row, i) => {
    if (!row) return [];
    const key = `m${i + 1}`;
    if (["plan", "ideas", "scheme", "note"].includes(row.kind)) return [textCard(key, row)];
    const doc = Array.isArray(documents) && documents.find((item) => isDocumentRow(item)
      && item.doc_id === row.docId && item.git_oid === row.gitOid);
    return doc ? [{...documentCard(key, doc), mode: row.mode === "copy" ? "copy" : "link",
      edits: Array.isArray(row.edits) ? row.edits : []}] : [];
  });
}

function typedAnswers(wizard) {
  const {title, brief, hint} = wizard.task;
  return {title, brief, hint, titleEdited: wizard.titleEdited, guided: wizard.guided,
    withoutGit: wizard.materials.withoutGit, includeInstructions: wizard.materials.includeInstructions,
    items: wizard.materials.items.map((row) => row.kind === "project_doc"
      ? {kind: row.kind, docId: row.docId, gitOid: row.gitOid, mode: row.mode, edits: row.edits ?? []}
      : {kind: row.kind, title: row.title, content: row.content}),
    cycleId: wizard.cycle.choice?.workflowId ?? null,
    owner: wizard.roles.owner, instructions: wizard.roles.instructions};
}

function restoreAnswers(fresh, held, documents, offered) {
  const items = draftMaterials(held.items, documents).map((row, at) => ({...row, key: `m${at + 1}`}));
  const known = offered.find((row) => row.id === held.cycleId && row.kind !== "build");
  const restored = {guided: held.guided !== false, titleEdited: held.titleEdited === true,
    draftMaterialsMissing: Array.isArray(held.items) && items.length !== held.items.length,
    task: {...fresh.task, title: held.title, brief: held.brief, hint: held.hint},
    materials: {...fresh.materials, items, counter: items.length, withoutGit: held.withoutGit === true,
      includeInstructions: typeof held.includeInstructions === "boolean" ? held.includeInstructions : null}};
  if (!known) return evolve(fresh, restored);
  restored.cycle = {...fresh.cycle, choice: {kind: known.kind, workflowId: known.workflowId},
    chosenBy: "owner", generation: 1};
  const entries = (value) => value && typeof value === "object" && !Array.isArray(value)
    ? Object.entries(value).filter(([id]) => DRAFT_ID.test(id)) : [];
  const owner = entries(held.owner).filter(([, id]) => typeof id === "string" && DRAFT_ID.test(id));
  const instructions = [];
  for (const [id, item] of entries(held.instructions)) {
    if (!item || !["own", "task", "like"].includes(item.source) || typeof item.text !== "string") continue;
    if (item.source === "like" && (typeof item.like !== "string" || !DRAFT_ID.test(item.like))) continue;
    instructions.push([id, {source: item.source, like: item.source === "like" ? item.like : null,
      text: item.text, back: item.back === "task" ? "task" : "own"}]);
  }
  restored.roles = {owner: Object.fromEntries(owner), instructions: Object.fromEntries(instructions)};
  return evolve(fresh, restored);
}

export function createWizardHost({mount, trigger, door, locale, nonce, onForeign, onState,
  onHash, onExit}) {
  let wizard = null, epoch = 0, timer = null, entrance = null, requested = null;
  let project = null, lastDraft = null;
  function saveDraft() {
    if (!project || !wizard?.firstRunGuide) return;
    if (wizard.run.pressed) { dropDraft(); return; }
    const task = wizard.task.taskId;
    try {
      const value = JSON.stringify(typedAnswers(wizard));
      if (value === lastDraft) return;
      sessionStorage.setItem(draftKey(project, task), value);
      if (history.state?.deskTaskDraft?.task !== task || history.state?.deskTaskDraft?.project !== project) {
        history.replaceState({...history.state, deskTaskDraft: {project, task}}, "");
      }
      lastDraft = value;
    } catch (_error) { dropDraft(); lastDraft = null; }
  }
  const live = (at) => at === epoch && wizard !== null;
  const refresh = () => onState();

  function render() {
    mount.hidden = wizard === null;
    trigger.hidden = wizard !== null || context?.foreign() === true;
    trigger.disabled = context?.mode() === null || context?.applied() === false;
    if (wizard === null) mount.replaceChildren();
    else mountWizard(mount, {locale: locale(), wizard, canRestore: project !== null && lastDraft !== null}, {onWizard: dispatch,
      onWizardClose: close});
  }

  function hash(override) {
    if (wizard === null) return null;
    const progress = override === undefined ? wizardHash(wizard) : override;
    // Once preparation begins, the task id replaces the opening request. A starter keeps
    // `new` until the run link because desk-hash only accepts `starter` beside `new`.
    const keepStarter = wizard.mode.starterId !== null && (progress === null
      || progress?.starter === wizard.mode.starterId);
    const keepNew = entrance === "new" && (progress?.prepare !== "1"
      || keepStarter);
    return {...(keepNew ? {new: "task"} : {}),
      ...(keepStarter ? {starter: wizard.mode.starterId} : {}),
      ...(progress ?? {})};
  }

  function close(outcomeValue) {
    const wasOpen = wizard !== null;
    if (wasOpen) dropDraft();
    project = null; lastDraft = null;
    const finished = outcomeValue ?? null;
    epoch += 1;
    clearInterval(timer);
    timer = null;
    wizard = null;
    entrance = null;
    requested = null;
    if (wasOpen) refresh();
    if (finished !== null) onExit(finished);
  }

  function dispose() {
    close();
    epoch += 1;
    trigger.removeEventListener("click", openNew);
  }

  async function perform(ask, at, expected) {
    if (!live(at) || wizard !== expected) return;
    if (ask.hash) onHash(hash(ask.hash));
    if (!live(at) || wizard !== expected) return;
    let result;
    if (ask.door === "write") result = await door.submit(ask.target, ask.subject, ask.body);
    else {
      const route = path[ask.target];
      try {
        if (typeof route !== "function") throw new Error("route_not_found");
        result = {status: "accepted", payload: await door.readJson(
          route(ask.subject, ask.body?.revision))};
      } catch (error) {
        result = outcome(error instanceof Error ? error.message : "store_error");
      }
    }
    if (result.code === "project_mismatch") onForeign();
    if (live(at)) dispatch({type: "answered", ask, result});
  }

  function dispatch(event) {
    if (wizard === null) return;
    const at = epoch;
    const step = stepWizard(wizard, event);
    if (step.state === wizard) return;
    wizard = step.state;
    onHash(hash());
    if (!live(at) || wizard !== step.state) return;
    if (event.type !== "tick") saveDraft();
    refresh();
    if (!live(at) || wizard !== step.state) return;
    const exit = wizardExit(wizard);
    if (exit !== null) {
      close({taskId: wizard.task.taskId, ...exit});
      return;
    }
    for (const ask of step.asks) void perform(ask, at, step.state);
  }

  async function open(keys, {actor, mode, tasks}, restore = true) {
    close();
    const at = ++epoch;
    requested = {new: keys.new, prepare: keys.prepare, starter: keys.starter};
    let workflows;
    try { workflows = await door.readJson(path.workflows()); }
    catch (error) {
      if (error instanceof Error && error.message === "project_mismatch") onForeign();
      return;
    }
    if (at !== epoch) return;
    // The route sends starter documents; the reducer's hash gate takes their ids.
    const starters = Array.isArray(workflows?.starters)
      ? workflows.starters.map((row) => row?.starter_id).filter((id) => typeof id === "string")
      : [];
    const resume = resumeFrom(keys, starters);
    const start = openingFrom(keys, starters);
    const guide = resume === null && start.starterId === null;
    let held = null, documents = [];
    if (guide) {
      try {
        project = context.project?.() || null;
        held = restore ? readDraft(project) : null;
        if (Array.isArray(held?.items) && held.items.some((row) => row?.kind === "project_doc")) {
          documents = (await door.readJson(path.documents()))?.documents ?? [];
        }
      } catch (error) {
        if (error instanceof Error && error.message === "project_mismatch") { onForeign(); return; }
      }
      if (at !== epoch) return;
      if (!held) dropDraft();
    }
    const nonceValue = token(nonce);
    if (held && tasks.some((row) => row.task_id === held.taskId)) { dropDraft(); held = null; }
    const taskId = resume?.taskId ?? held?.taskId ?? `task-${nonceValue.slice(0, 24)}`;
    const task = tasks.find((row) => row.task_id === taskId);
    wizard = initialWizard({newTaskId: taskId, nonce: nonceValue, actor: actor ?? "",
      firstRunGuide: resume === null && start.starterId === null,
      viewMode: mode === "view", starterId: resume?.starterId ?? start.starterId,
      setupDoor: typeof path.gitSetup === "function",
      ...(resume === null ? {} : {resume, taskWritten: true, title: task?.title ?? ""})});
    if (held && !task) {
      const offered = cycleCards({...wizard, reads: {workflows: {status:"ok", payload:workflows}}});
      wizard = restoreAnswers(wizard, held, documents, offered);
    }
    entrance = keys.new === "task" ? "new" : "prepare";
    timer = setInterval(() => dispatch({type: "tick", now: new Date().toISOString()}), 1000);
    dispatch({type: "open"});
    queueMicrotask(() => (mount.querySelector(wizard?.guided ? '[data-focus="wizard:brief"]'
      : '[data-focus="wizard:title"]') ?? mount.querySelector('[data-focus="wizard:close"]'))?.focus());
  }

  function openNew() {
    if (wizard !== null || context.foreign() || context.mode() === null
      || !context.applied()) return;
    onHash({new: "task"});
    void open({new: "task", starter: null}, {actor: context.actor(), mode: context.mode(),
      tasks: context.tasks()}, false);
  }

  let context = null;
  function bind(next) { context = next; }
  async function navigate(change, keys) {
    if (keys.new !== "task" && keys.prepare !== "1") {
      if (wizard !== null || requested !== null) close();
      return;
    }
    if ((changed(change, "new") || changed(change, "starter")
      || changed(change, "prepare")) && (keys.new === "task" || keys.prepare === "1")) {
      await open(keys, {actor: context.actor(), mode: context.mode(), tasks: context.tasks()});
    } else if (changed(change, "task")) close();
  }

  function actor(value) {
    if (wizard !== null) dispatch({type: "actor-edit", value: value ?? ""});
  }

  trigger.addEventListener("click", openNew);
  return Object.freeze({render, hash, close, dispose, navigate, actor, bind,
    state: () => wizard});
}
