"use strict";
// The live desk's adapter for the existing six-step wizard. The reducer owns the chain and its
// asks; this host only supplies the shared transport, page identity, address and clock. A closed
// wizard has a new epoch, so a late read or write cannot reopen it or change another project.
import {path} from "./desk-transport.js";
import {initialWizard, openingFrom, resumeFrom, stepWizard} from "./desk-wizard-model.js";
import {wizardExit, wizardHash} from "./desk-wizard-run.js";
import {mountWizard} from "./desk-wizard.js";

const outcome = (code) => ({status: "refused", code});
const token = (nonce) => nonce().replaceAll("-", "").toLowerCase().slice(0, 32);
const changed = (change, key) => change.steps.some((step) => step.key === key);

export function createWizardHost({mount, trigger, door, locale, nonce, onForeign, onState,
  onHash, onExit}) {
  let wizard = null, epoch = 0, timer = null, entrance = null, requested = null;
  const live = (at) => at === epoch && wizard !== null;
  const refresh = () => onState();

  function render() {
    mount.hidden = wizard === null;
    trigger.hidden = wizard !== null || context?.foreign() === true;
    trigger.disabled = context?.mode() === null || context?.applied() === false;
    if (wizard === null) mount.replaceChildren();
    else mountWizard(mount, {locale: locale(), wizard}, {onWizard: dispatch,
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
    refresh();
    if (!live(at) || wizard !== step.state) return;
    const exit = wizardExit(wizard);
    if (exit !== null) {
      close({taskId: wizard.task.taskId, ...exit});
      return;
    }
    for (const ask of step.asks) void perform(ask, at, step.state);
  }

  async function open(keys, {actor, mode, tasks}) {
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
    const nonceValue = token(nonce);
    const taskId = resume?.taskId ?? `task-${nonceValue.slice(0, 24)}`;
    const task = tasks.find((row) => row.task_id === taskId);
    wizard = initialWizard({newTaskId: taskId, nonce: nonceValue, actor: actor ?? "",
      viewMode: mode === "view", starterId: resume?.starterId ?? start.starterId,
      ...(resume === null ? {} : {resume, taskWritten: true, title: task?.title ?? ""})});
    entrance = keys.new === "task" ? "new" : "prepare";
    timer = setInterval(() => dispatch({type: "tick", now: new Date().toISOString()}), 1000);
    dispatch({type: "open"});
    queueMicrotask(() => mount.querySelector('[data-focus="wizard:title"], '
      + '[data-focus="wizard:close"]')?.focus());
  }

  function openNew() {
    if (wizard !== null || context.foreign() || context.mode() === null
      || !context.applied()) return;
    onHash({new: "task"});
    void open({new: "task", starter: null}, {actor: context.actor(), mode: context.mode(),
      tasks: context.tasks()});
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
