"use strict";
// The live desk's adapter for the existing six-step wizard. The reducer owns the chain and its
// asks; this host only supplies the shared transport, page identity, address and clock. A closed
// wizard has a new epoch, so a late read or write cannot reopen it or change another project.
import {path} from "./desk-transport.js";
import {deskHash, preferenceHash, readDeskHash, readPreferences} from "./desk-hash.js";
import {limitFields} from "./studio-budget-guidance.js";
import {cycleCards, initialWizard, openingFrom, restoreAnswers, resumeFrom, stepWizard} from "./desk-wizard-model.js";
import {wizardExit, wizardHash} from "./desk-wizard-run.js";
import {mountWizard} from "./desk-wizard.js";
import {createAdvicePanel} from "./desk-advice-panel.js";

const outcome = (code) => ({status: "refused", code});
const token = (nonce) => nonce().replaceAll("-", "").toLowerCase().slice(0, 32);
const changed = (change, key) => change.steps.some((step) => step.key === key);
const DRAFT_TASK = /^task-[a-z0-9]{8,24}$/;
const DRAFT_KEY = /^[0-9a-f]{32}$/;
function pointer(project) {
  const p = history.state?.deskTaskDraft;
  return p?.project === project && DRAFT_KEY.test(p.key) ? p : null;
}
function forgetPointer() {
  if (!history.state?.deskTaskDraft) return;
  const {deskTaskDraft, ...rest} = history.state;
  history.replaceState(rest, "");
}

function typedAnswers(wizard) {
  const {title, brief, hint} = wizard.task;
  return {title, brief, hint, titleEdited: wizard.titleEdited, guided: wizard.guided,
    ...(wizard.budgetChosen ? {budgetDepth: wizard.budgetDepth} : {}),
    withoutGit: wizard.materials.withoutGit, includeInstructions: wizard.materials.includeInstructions,
    items: wizard.materials.items.map((row) => row.kind === "project_doc"
      ? {kind: row.kind, docId: row.docId, gitOid: row.gitOid, mode: row.mode, edits: row.edits ?? []}
      : {kind: row.kind, title: row.title, content: row.content}),
    cycleId: wizard.cycle.choice?.workflowId ?? null,
    ...(wizard.cycle.choice?.revision ? {cycleRevision: wizard.cycle.choice.revision} : {}),
    owner: wizard.roles.owner, instructions: wizard.roles.instructions, models: wizard.roles.models ?? {}};
}


export function createWizardHost({mount, trigger, door, locale, nonce, onForeign, onState,
  onHash, onExit, advisorPanel = null}) {
  let wizard = null, epoch = 0, timer = null, entrance = null, requested = null;
  let project = null, editor = null, opening = false, unavailable = false, checkingRoster = null;
  const valid = (draft) => draft === editor && epoch === draft.epoch && context.project?.() === draft.project;
  const draftCall = (draft, op, data) => door.submit("taskDraft", null,
    {project: draft.project, op, ...data});
  function discard(draft) {
    if (draft?.key && context.project?.() === draft.project) {
      void draftCall(draft, "discard", {key: draft.key, base: draft.revision, edit: draft.edit ?? null});
    }
  }
  function dropDraft() {
    const draft = editor;
    editor = null;
    forgetPointer();
    discard(draft);
  }
  async function flush(draft) {
    if (draft.busy || !valid(draft) || draft.stopped || draft.want === draft.saved) return;
    draft.busy = true;
    draft.status = "saving";
    refresh();
    try {
      if (!draft.key) {
        const opened = await draftCall(draft, "open", {task: draft.task});
        if (opened.status !== "accepted" || !DRAFT_KEY.test(opened.payload?.key)) throw new Error();
        draft.key = opened.payload.key;
        if (!valid(draft)) return;
        history.replaceState({...history.state, deskTaskDraft: {project: draft.project, key: draft.key}}, "");
      }
      while (valid(draft) && draft.want !== draft.saved) {
        const sent = draft.want;
        draft.edit = token(nonce);
        const answer = await draftCall(draft, "save", {key: draft.key, base: draft.revision, edit: draft.edit,
          answers: JSON.parse(sent)});
        if (answer.status !== "accepted" || answer.payload?.revision !== draft.revision + 1) {
          draft.stopped = answer.code === "draft_conflict" || answer.code === "route_not_found";
          throw new Error();
        }
        draft.revision = answer.payload.revision;
        draft.saved = sent;
      }
      draft.status = "saved";
    } catch (_error) {
      draft.status = "memory_only";
    } finally {
      draft.busy = false;
      if (valid(draft)) refresh();
      else discard(draft);
    }
  }
  function saveDraft() {
    if (!wizard?.firstRunGuide) return;
    if (wizard.run.pressed) { if (editor) dropDraft(); return; }
    if (!editor) return;
    const next = JSON.stringify(typedAnswers(wizard));
    if (next === editor.want) return;
    editor.want = next;
    void flush(editor);
  }
  function gitSourceRead(state) {
    if (!editor || !valid(editor) || wizard.run.pressed) return;
    if (state === "unavailable") {
      editor.gitUnavailable = true;
    } else if (editor.gitUnavailable && (state === "repo" || state === "unborn")) {
      // A running server never changes its Git-pin verdict. The newly started
      // server also has a fresh draft store. Save this tab's answers under a new key.
      saveInNewStore();
    }
  }
  function saveInNewStore() {
    editor = {project: editor.project, task: editor.task, epoch, revision: 0, key: null,
      status: "saving", saved: null, want: JSON.stringify(typedAnswers(wizard))};
    forgetPointer();
    void flush(editor);
  }
  async function checkCurrentDraft(readable) {
    const draft = editor;
    if (!draft || !valid(draft) || wizard.run.pressed) return;
    if (readable && !draft.key) { saveInNewStore(); return; }
    const read = () => draftCall(draft, "read", {key: draft.key});
    let reply = null;
    // A process restart rotates the token as well as its transient store. This
    // operation only checks whether the old draft still exists.
    if (readable && draft.key) {
      try {
        reply = await read();
        if (reply.status === "refused" && reply.code === "csrf_denied" && valid(draft)) reply = await read();
      } catch (_error) { /* The copy on the server could not be confirmed. */ }
    }
    if (!valid(draft) || wizard.run.pressed) return;
    draft.checking = false;
    if (reply?.status === "refused" && reply.code === "route_not_found") saveInNewStore();
    else {
      if (reply?.status !== "accepted") draft.status = "memory_only";
      else if (!draft.busy && !draft.stopped) draft.status = draft.want === draft.saved
        && reply.payload?.revision === draft.revision ? "saved" : "memory_only";
      refresh();
    }
  }
  function warnOnUnload(event) {
    if ((editor && (editor.checking || editor.status === "memory_only" || editor.want !== editor.saved)) || (!editor && wizard?.firstRunGuide
      && !wizard.run.pressed && (wizard.task.brief || wizard.task.title || wizard.materials.items.length))) {
      event.preventDefault();
      event.returnValue = "";
    }
  }
  window.addEventListener("beforeunload", warnOnUnload);
  function enterStudioOnForward() {
    if (["/", "/panel/studio.html"].includes(location.pathname) && history.state?.deskLimitEditor) location.reload();
  }
  window.addEventListener("popstate", enterStudioOnForward);

  const live = (at) => at === epoch && wizard !== null;
  const refresh = () => onState();
  function writeAdvice(target, subject, body) {
    if (!wizard || context.foreign() || context.mode() !== "active"
        || !["flow", "tasks", "runs", "artifacts", "automationPreview", "automationAuthorize", "decisions"].includes(target)) {
      return Promise.resolve(outcome("advice_unavailable"));
    }
    return door.submit(target, subject, body);
  }
  const advice = createAdvicePanel({door: {readJson: (url) => door.readJson(url), write: writeAdvice},
    refresh, dispatch, draft: () => wizard, locale,
    actor: () => context?.actor()});

  function render() {
    mount.hidden = wizard === null;
    trigger.hidden = wizard !== null || context?.foreign() === true;
    trigger.disabled = context?.mode() === null || context?.applied() === false;
    if (wizard === null) mount.replaceChildren();
    else mountWizard(mount, {locale: locale(), wizard, draftStatus: editor?.checking ? "saving" : editor?.status
      ?? (unavailable ? "restore_failed" : "memory_only")}, {onWizard: dispatch,
      onWizardClose: close, onEditLimits: context.project?.() && !context.foreign() ? editLimits : null,
      advisorPanel: context.project?.() && !context.foreign() ? (advisorPanel ?? advice.panel) : null, onQuestionDone: () => {
        render();
        mount.querySelector('[data-guide-details^="reply-"] textarea, [data-focus="wizard:next"]')?.focus();
      }});
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
    advice.close();
    const wasOpen = wizard !== null;
    if (wasOpen) dropDraft();
    project = null; unavailable = false;
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
    window.removeEventListener("beforeunload", warnOnUnload);
    window.removeEventListener("popstate", enterStudioOnForward);
    trigger.removeEventListener("click", openNew);
  }

  function editLimits() {
    const terms = wizard?.launch.preview?.terms;
    if (!terms || !context.project?.() || context.foreign() || wizard.launch.phase !== "review") return;
    const task = wizard.task.taskId, run = wizard.run.runId;
    const selection = {task, run, project: context.project(), embed: readDeskHash(location.hash).embed};
    const appearance = {...readPreferences(location.hash, locale()), locale: locale()};
    const back = preferenceHash(deskHash(selection), appearance);
    const studio = preferenceHash(`#${new URLSearchParams({screen: "runs", task, run})}`, appearance);
    // Leave the old grant card before navigating. Only editable numbers follow
    // this tab; Studio must get a fresh server preview before it can grant them.
    const draft = {...selection, bounds: limitFields(terms)};
    close();
    history.replaceState(null, "", back);
    history.pushState({deskLimitEditor: draft}, "", "/panel/studio.html" + studio);
    location.reload();
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
    if (live(at)) {
      dispatch({type: "answered", ask, result});
      if (ask.name === "git" && result.status === "accepted" && live(at)) {
        gitSourceRead(result.payload?.git?.state);
      }
      if (ask.name === "workflows" && checkingRoster === at) {
        checkingRoster = null;
        if (live(at)) void checkCurrentDraft(result.status === "accepted");
      }
    }
  }

  function dispatch(event) {
    if (wizard === null) return;
    const at = epoch;
    const step = stepWizard(wizard, event);
    if (step.state === wizard) return;
    if (event.type === "reread" && event.name === "workflows") {
      checkingRoster = at;
      if (editor) editor.checking = true;
    }
    const focusQuestion = step.state.guided && step.state.step !== wizard.step
      && ["next", "back", "goto"].includes(event.type);
    wizard = step.state;
    onHash(hash());
    if (!live(at) || wizard !== step.state) return;
    if (event.type !== "tick") saveDraft();
    refresh();
    if (!live(at) || wizard !== step.state) return;
    if (focusQuestion) {
      const prompt = wizard.step === "task" ? '[data-focus="wizard:brief"]' : "[data-ask-prompt]";
      mount.querySelector(prompt)?.focus();
    }
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
    let held = null, documents = [], restoreNotice = null;
    if (guide) {
      try {
        project = context.project?.() || null;
        const p = restore && project && mode === "active" ? pointer(project) : null;
        if (p) {
          const answer = await draftCall(p, "read", {key: p.key});
          if (at !== epoch || context.project?.() !== p.project) return;
          if (answer.status === "accepted" && DRAFT_TASK.test(answer.payload?.task)
              && Number.isSafeInteger(answer.payload.revision) && answer.payload.answers) {
            held = {...answer.payload.answers, taskId: answer.payload.task};
            editor = {project, epoch: at, task: held.taskId, key: p.key, revision: answer.payload.revision,
              saved: JSON.stringify(answer.payload.answers), status: "saved"};
          } else if (answer.code === "route_not_found") restoreNotice = "unavailable";
          else unavailable = true;
        }
        if (Array.isArray(held?.items) && held.items.some((row) => row?.kind === "project_doc")) {
          documents = (await door.readJson(path.documents()))?.documents ?? [];
        }
      } catch (error) {
        if (error instanceof Error && error.message === "project_mismatch") { onForeign(); return; }
      }
      if (at !== epoch) return;
      if (!held && !unavailable) forgetPointer();
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
    if (!editor && !unavailable && guide && project && mode === "active") {
      editor = {project, epoch: at, task: taskId, key: null, revision: 0, status: restoreNotice ?? "empty"};
    }
    if (editor) editor.saved = editor.want = JSON.stringify(typedAnswers(wizard));
    entrance = keys.new === "task" ? "new" : "prepare";
    timer = setInterval(() => {
      dispatch({type: "tick", now: new Date().toISOString()});
      void advice.tick();
    }, 1000);
    dispatch({type: "open"});
    queueMicrotask(() => (mount.querySelector(wizard?.guided ? '[data-focus="wizard:brief"]'
      : '[data-focus="wizard:title"]') ?? mount.querySelector('[data-focus="wizard:close"]'))?.focus());
  }

  function openNew() {
    if (opening || wizard !== null || context.foreign() || context.mode() === null
      || !context.applied()) return;
    onHash({new: "task"});
    opening = true;
    void open({new: "task", starter: null}, {actor: context.actor(), mode: context.mode(),
      tasks: context.tasks()}, false).finally(() => { opening = false; });
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
