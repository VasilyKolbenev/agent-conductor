"use strict";
// Onboarding state transitions. Only hub.js supplies the HTTP door and timer.

export function createOnboarding(ctx) {
  return Object.freeze({
    close: () => closeAdd(ctx), source: (value) => chooseSource(ctx, value),
    choose: (purpose) => chooseFolder(ctx, purpose), cancel: () => cancelFolder(ctx),
    submit: () => submitFolder(ctx),
    github: () => github(ctx), repositories: (owner) => repositories(ctx, owner),
    repository: (repo) => repository(ctx, repo), cancelClone: () => cancelClone(ctx),
  });
}

function closeAdd(ctx) {
  const {state, write, render} = ctx;
  const add = state.add;
  if (add.mode === "picking" && add.pickId) {
    write("pickCancel", {pick: add.pickId}, {});
  }
  add.epoch += 1;
  add.open = false;
  add.pickId = null;
  render();
}

function chooseSource(ctx, source) {
  const {state, write, render} = ctx;
  if (state.add.mode === "running") return;
  const pick = state.add.pickId;
  Object.assign(state.add, {source, epoch: state.add.epoch + 1, pickId: null,
    mode: source === "folder" ? "choose" : "picked", folder: "", name: "",
    project: null, consent: false, result: null, error: null, repo: "", github: null, cancelling: false});
  if (pick) write("pickCancel", {pick}, {});
  render();
  if (source === "github") github(ctx);
}

async function chooseFolder(ctx, purpose = "project") {
  const {state, write, render, IDS} = ctx;
  const add = state.add;
  const epoch = ++add.epoch;
  if (add.github) Object.assign(add.github, {listing: false});
  if (purpose === "project") Object.assign(add, {folder: null, project: null,
    name: "", consent: false, error: null, result: null});
  Object.assign(add, {mode: "picking", pickId: null, pickPurpose: purpose});
  render();
  const answer = await write("pickFolder", {}, {purpose});
  if (add.epoch !== epoch || !add.open) {
    const latePick = answer.payload?.pick_id;
    if (answer.status === "accepted" && IDS.pick.test(String(latePick))) {
      await write("pickCancel", {pick: latePick}, {});
    }
    return;
  }
  if (answer.status !== "accepted" || !IDS.pick.test(String(answer.payload?.pick_id))) {
    Object.assign(add, {mode: add.source !== "folder" ? "picked" : "choose",
      error: answer.code ?? "unknown"});
    render();
    return;
  }
  add.pickId = answer.payload.pick_id;
  pollPick(ctx, epoch);
}

async function pollPick(ctx, epoch) {
  const {state, read, write, render, refresh, isObject, schedule} = ctx;
  const add = state.add;
  if (add.epoch !== epoch || !add.open || !add.pickId) return;
  const answer = await read("dialog", {pick: add.pickId});
  if (add.epoch !== epoch || !add.open) return;
  const row = answer.payload;
  if (answer.status !== "accepted" || !isObject(row)) {
    Object.assign(add, {mode: add.source !== "folder" ? "picked" : "choose",
      error: answer.code ?? "unknown"});
  } else if (row.state === "open") {
    schedule(() => pollPick(ctx, epoch), 500);
    return;
  } else if (row.state === "picked" && typeof row.folder === "string") {
    if (add.pickPurpose === "projects_home") {
      const saved = await write("projectsHome", {}, {pick_id: add.pickId});
      if (add.epoch !== epoch || !add.open) return;
      Object.assign(add, {mode: "picked", pickId: null,
        error: saved.status === "accepted" ? null : saved.code ?? "unknown"});
      if (saved.status === "accepted" && state.setup) state.setup.projects_home = saved.payload.projects_home;
      refresh("setup");
      render();
      return;
    }
    Object.assign(add, {mode: "picked", folder: row.folder, name: row.folder,
      project: row.project, error: null});
  } else {
    Object.assign(add, {mode: add.source !== "folder" ? "picked" : "choose",
      error: row.code ?? row.state});
  }
  render();
}

async function cancelFolder(ctx) {
  const {state, write, render} = ctx;
  const add = state.add, pick = add.pickId;
  add.epoch += 1;
  Object.assign(add, {mode: add.source !== "folder" ? "picked" : "choose",
    pickId: null, error: null});
  render();
  if (pick) await write("pickCancel", {pick}, {});
}

async function submitFolder(ctx) {
  const {state, write, render, IDS} = ctx;
  const add = state.add;
  if (add.mode !== "picked" || (add.source === "folder" ? !add.pickId : !add.folder)
      || (add.source === "github" && (!REPO.test(add.repo) || add.github?.state !== "ok"))
      || !add.name.trim()
      || (add.project === "legacy" && !add.consent)) return;
  const epoch = ++add.epoch;
  add.mode = "running";
  add.step = "admit";
  add.error = null;
  render();
  const body = add.source !== "folder"
    ? {source: add.source, folder: add.folder, name: add.name,
      ...(add.source === "github" ? {repo: add.repo} : {})}
    : {source: "folder", pick_id: add.pickId,
    name: add.name, legacy_writers_stopped: add.project !== "activated" &&
      (add.project !== "legacy" || add.consent)};
  const answer = await write("projectAdd", {}, body);
  if (add.epoch !== epoch || !add.open) return;
  if (answer.status !== "accepted" || !IDS.operation.test(String(answer.payload?.operation_id))) {
    Object.assign(add, {mode: "picked", error: answer.code ?? "unknown"});
    render();
    return;
  }
  add.operationId = answer.payload.operation_id;
  pollAdd(ctx, epoch);
}

async function pollAdd(ctx, epoch) {
  const {state, read, render, refresh, select, isObject, IDS, schedule, invalidateProjects} = ctx;
  const add = state.add;
  if (add.epoch !== epoch || !add.open || !add.operationId) return;
  const answer = await read("operation", {operation: add.operationId});
  if (add.epoch !== epoch || !add.open) return;
  const row = answer.payload;
  if (answer.status !== "accepted" || !isObject(row)) {
    Object.assign(add, {mode: "failed", error: answer.code ?? "unknown"});
  } else {
    Object.assign(add, {step: row.step, result: row.result});
    if (row.state === "running") {
      render();
      schedule(() => pollAdd(ctx, epoch), 500);
      return;
    }
    add.mode = row.state === "succeeded" ? "done" : row.state === "cancelled" ? "cancelled" : "failed";
    add.error = row.state === "failed" ? row.code : null;
    invalidateProjects();
    refresh("projects");
    if (row.state === "succeeded" && IDS.project.test(String(row.project_id))) {
      select({project_id: row.project_id, task_id: null, run_id: null, gate_id: null},
        add.source === "scratch" ? {new: "task", starter: "desk-starter-docs"} : {});
    }
  }
  render();
}

const REPO = /^[A-Za-z0-9][A-Za-z0-9-]{0,38}\/[A-Za-z0-9._-]{1,100}$/;
const FOLDER = /^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$/;
const alive = (ctx, epoch) => ctx.state.add.open && ctx.state.add.epoch === epoch
  && ctx.state.add.source === "github";

async function github(ctx) {
  const add = ctx.state.add, epoch = ++add.epoch;
  add.github = {state: "loading", repos: [], owner: ""};
  ctx.render();
  const answer = await ctx.read("githubStatus");
  if (!alive(ctx, epoch)) return;
  add.github = {...add.github, ...(answer.status === "accepted" && ctx.isObject(answer.payload)
    && typeof answer.payload.state === "string"
    ? answer.payload : {state: "failed"})};
  ctx.render();
  if (add.github.state === "ok") repositories(ctx, "");
}

async function repositories(ctx, owner) {
  const add = ctx.state.add;
  if (add.github?.state !== "ok" || add.mode !== "picked"
      || (owner !== "" && !ctx.IDS.owner.test(owner))) return;
  const epoch = ++add.epoch;
  Object.assign(add.github, {listing: true, owner, listError: null});
  ctx.render();
  const answer = await ctx.read(owner ? "githubOwner" : "githubRepos", owner ? {owner} : {});
  if (!alive(ctx, epoch)) return;
  Object.assign(add.github, {listing: false,
    repos: answer.status === "accepted" && Array.isArray(answer.payload?.repos)
      ? answer.payload.repos.slice(0, 200) : [],
    truncated: answer.payload?.truncated === true,
    listError: answer.status === "accepted" ? null : answer.code ?? "unknown"});
  ctx.render();
}

function repository(ctx, repo) {
  const add = ctx.state.add;
  if (add.mode !== "picked") return;
  add.repo = repo;
  if (REPO.test(repo)) {
    const leaf = repo.split("/")[1];
    if (!add.folder && FOLDER.test(leaf)) add.folder = leaf;
    if (!add.name) add.name = leaf.slice(0, 64);
  }
  ctx.render();
}

async function cancelClone(ctx) {
  const add = ctx.state.add, epoch = add.epoch;
  if (add.source !== "github" || add.mode !== "running" || add.step !== "clone"
      || !add.operationId || add.cancelling) return;
  add.cancelling = true;
  ctx.render();
  const result = await ctx.write("operationCancel", {operation: add.operationId}, {});
  if (add.epoch !== epoch || !add.open) return;
  add.cancelling = false;
  if (result.status !== "accepted") add.error = result.code ?? "unknown";
  ctx.render();
}
