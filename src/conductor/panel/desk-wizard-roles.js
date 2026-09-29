"use strict";
// Step 4, "Роли и указания": who does what, and what each dispatch step is told.
//
// Pure functions over the reads and the flow the model hands over, importing nothing: the roles
// a flow names, which harnesses may take each, a suggestion for the ones the owner leaves alone,
// and the instruction fields a cycle asks for. The harness facts come from the roster's own rows
// (`controls`, and the two facts still owed, `task_channel` and `offered`); no harness is named
// here, and a row that does not say it is offered is not offered.
export const ROLE_KINDS = Object.freeze(["analyst", "designer", "diagnostician", "reviewer",
  "doer", "tester", "checker"]);
//: The closed words the suggestion and the quota reading can say, each with a message.
export const NOTES = Object.freeze(["new_role", "argv_not_fit", "none_eligible",
  "unknown_quota", "independent_pick", "previous_unavailable"]);
export const QUOTA_REASONS = Object.freeze(["no_data", "stale", "source_error"]);
//: The rows the server adds when a binding is sent for diagnostics (spec 7.4): the wizard does
//: not go on while any stands.
export const BINDING_CODES = Object.freeze(["role_unassigned", "role_capability_unsupported",
  "checker_cannot_verify"]);
export const ARGV_LIMIT = 32767;

function record(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function addOnce(list, value) {
  if (typeof value === "string" && !list.includes(value)) list.push(value);
}

// -- roles -------------------------------------------------------------------------------

//: A role's kind is read off its name (`role-<kind>` or `role-<kind>-<n>`); any other name is
//: the owner's own role (spec 7.2.2).
export function roleKind(roleId) {
  const found = /^role-([a-z]+)(?:-\d+)?$/.exec(typeof roleId === "string" ? roleId : "");
  return found && ROLE_KINDS.includes(found[1]) ? found[1] : "custom";
}

function agentSteps(flow) {
  return (Array.isArray(flow?.steps) ? flow.steps : []).filter((step) => record(step)
    && step.type === "agent" && typeof step.role_id === "string");
}

export function dispatchSteps(flow) {
  return agentSteps(flow).filter((step) => step.capability === "dispatch");
}

//: Every role a flow names, of both duties: a step's own role carries it out and its verifier
//: confirms it, and a run must assign both. Those who carry out come first, in step order;
//: roles that only verify follow.
export function rolesOf(flow) {
  const roles = new Map();
  const touch = (id) => {
    if (!roles.has(id)) roles.set(id, {role_id: id, kind: roleKind(id), needs: [], steps: [],
      verifies: []});
    return roles.get(id);
  };
  for (const step of agentSteps(flow)) {
    const role = touch(step.role_id);
    role.steps.push(step.step_id);
    addOnce(role.needs, step.capability);
  }
  for (const step of agentSteps(flow)) {
    if (typeof step.verifier_role_id !== "string") continue;
    const checker = touch(step.verifier_role_id);
    addOnce(checker.needs, "review");
    addOnce(checker.verifies, step.role_id);
  }
  return [...roles.values()];
}

// -- the roster and the quotas -----------------------------------------------------------

function providerRows(providers) {
  return (Array.isArray(providers) ? providers : []).filter((row) => record(row)
    && typeof row.provider_id === "string");
}

//: The harnesses the wizard may offer, from the provider rows as the server projects them
//: (`provider_id`, `display_name`, `availability`, `implementation`, `auth`, `controls`,
//: `vendor_sandbox`): the roads a harness has are its `controls`. Two facts the wizard needs are
//: not on that row yet and are owed by the server: `offered` (the owner's list for this version)
//: and `task_channel` (how the harness is fed). A row that is not `offered` is dropped whole, so
//: nothing downstream can name it.
export function rosterOf(providers) {
  return providerRows(providers).filter((row) => row.offered === true).map((row) => {
    const channel = record(row.task_channel) ? row.task_channel : null;
    return {id: row.provider_id,
      name: typeof row.display_name === "string" ? row.display_name : row.provider_id,
      available: row.availability === "available",
      roads: (Array.isArray(row.controls) ? row.controls : [])
        .filter((one) => typeof one === "string"),
      channel: typeof channel?.channel === "string" ? channel.channel : null};
  });
}

//: Whether the roster can be used, and if not, which of two different things is true: `none`, the
//: server named no harness this version offers, or `pending`, a row lacks one of the two facts the
//: server still owes (a boolean `offered`, and the `task_channel` key, null being an answer), so
//: nothing can be said about who is offered. Saying "none" for "not yet served" would be false.
export function rosterState(providers) {
  const rows = providerRows(providers);
  if (rows.length === 0) return "none";
  const described = (row) => typeof row.offered === "boolean" && Object.hasOwn(row, "task_channel");
  if (!rows.every(described)) return "pending";
  return rosterOf(providers).length === 0 ? "none" : "ready";
}

export function offersFor(role, roster) {
  return roster.filter((row) => row.available && role.needs.every((need) => row.roads.includes(need)));
}

//: What is left of a harness's limit, or that it is not known. A reading that is missing,
//: errored or stale is unknown and never a remainder; several windows report the tightest one.
export function quotaOf(payload, id) {
  const none = (reason) => ({known: false, remaining: null, kind: null, reason});
  const rows = Array.isArray(payload?.snapshots) ? payload.snapshots : [];
  const row = rows.find((one) => Array.isArray(one?.binding_ids) && one.binding_ids.includes(id));
  if (!row || row.state === "missing") return none("no_data");
  if (row.state !== "observed") return none("source_error");
  if (row.freshness !== "current") return none("stale");
  const windows = Array.isArray(row.windows) ? row.windows : [];
  if (windows.length > 0) {
    if (windows.some((one) => one.freshness !== "current")) return none("stale");
    if (!windows.every((one) => Number.isFinite(one.remaining_percent))) return none("no_data");
    return {known: true, kind: "percent", reason: null,
      remaining: Math.min(...windows.map((one) => one.remaining_percent))};
  }
  const money = Array.isArray(row.balances) && row.balances.length > 0 && row.is_available === true;
  return money ? {known: true, remaining: null, kind: "balance", reason: null}
    : none("no_data");
}

// -- the suggestion ----------------------------------------------------------------------

//: Whether an instruction and its inputs fit a command line (32 767 UTF-16 units, spec 6.3).
export function argvFit(instruction, inputChars) {
  const chars = String(instruction).length + inputChars;
  return {chars, limit: ARGV_LIMIT, fits: chars <= ARGV_LIMIT};
}

function rankOf(quota) {
  if (!quota.known) return 0;
  return quota.remaining === null ? 500 : 1000 + quota.remaining;
}

function pick(role, ctx) {
  const eligible = offersFor(role, ctx.roster), notes = [];
  const owned = ctx.fixed[role.role_id];
  if (typeof owned === "string" && eligible.some((row) => row.id === owned)) {
    return {provider: owned, by: "owner", notes};
  }
  const carries = role.needs.includes("dispatch");
  const fits = argvFit("", ctx.chars[role.role_id] ?? 0).fits;
  const fitting = eligible.filter((row) => row.channel !== "argv" || !carries || fits);
  if (fitting.length < eligible.length) notes.push("argv_not_fit");
  if (fitting.length === 0) return {provider: null, by: null, notes: [...notes, "none_eligible"]};
  const before = ctx.previous[role.role_id];
  if (fitting.some((row) => row.id === before)) return {provider: before, by: "previous", notes};
  if (ctx.hasPrevious && before === undefined) {
    return {provider: null, by: null, notes: [...notes, "new_role"]};
  }
  if (before !== undefined) notes.push("previous_unavailable");
  return choose(role, fitting, ctx, notes);
}

function choose(role, fitting, ctx, notes) {
  let candidates = fitting;
  if (role.verifies.length > 0) {
    const used = new Set(role.verifies.map((verified) => ctx.assignment[verified]));
    const fresh = fitting.filter((row) => !used.has(row.id));
    if (fresh.length > 0 && fresh.length < fitting.length) notes.push("independent_pick");
    if (fresh.length > 0) candidates = fresh;
  }
  const ranked = [...candidates].sort((left, right) => rankOf(quotaOf(ctx.quotas, right.id))
    - rankOf(quotaOf(ctx.quotas, left.id)) || ctx.roster.indexOf(left) - ctx.roster.indexOf(right));
  if (!quotaOf(ctx.quotas, ranked[0].id).known) notes.push("unknown_quota");
  return {provider: ranked[0].id, by: "suggestion", notes};
}

//: A harness for every role the owner has not settled (spec 6.3, D8): the owner's own pick
//: first, then what the last run of this cycle used, then the harness with the most left, a
//: verifier on a different one from the steps it verifies, an argv harness for a doer only if
//: the inputs fit. When a last run was read, a role it did not have is left for the owner.
export function suggest(roles, providers, quotas, previous, context = {}) {
  const ctx = {roster: rosterOf(providers), quotas, previous: previous ?? {}, assignment: {},
    fixed: context.fixed ?? {}, chars: context.chars ?? {},
    hasPrevious: context.hasPrevious === true};
  const out = {assignment: {}, by: {}, notes: {}};
  for (const role of roles) {
    const found = pick(role, ctx);
    ctx.assignment[role.role_id] = found.provider;
    out.assignment[role.role_id] = found.provider;
    out.by[role.role_id] = found.by;
    out.notes[role.role_id] = found.notes;
  }
  return out;
}

// -- the last run of this cycle ----------------------------------------------------------

//: The newest readable run that followed this workflow, from the runs read.
export function previousRun(runsRead, workflowId) {
  const rows = runsRead && runsRead.status === "ok" ? runsRead.payload?.runs : null;
  const usable = (Array.isArray(rows) ? rows : []).filter((row) => record(row)
    && row.unreadable !== true && row.workflow_id === workflowId
    && Number.isSafeInteger(row.revision) && typeof row.created_at === "string"
    && typeof row.run_id === "string");
  return usable.reduce((best, row) => (best === null || row.created_at > best.created_at
    ? row : best), null);
}

//: Role to harness for a finished run, joined by node id over three sources (spec 7.10): the
//: revision's nodes name the roles, the frozen plan's nodes name the instances, and the
//: configuration says which harness each instance is.
export function assignmentFrom(revisionNodes, planNodes, instances) {
  const planned = new Map((Array.isArray(planNodes) ? planNodes : [])
    .filter((node) => record(node)).map((node) => [node.node_id, node]));
  const harness = (id) => (Array.isArray(instances) ? instances : [])
    .find((row) => record(row) && row.id === id)?.adapter ?? null;
  const found = {};
  for (const node of Array.isArray(revisionNodes) ? revisionNodes : []) {
    const plan = record(node) ? planned.get(node.node_id) : undefined;
    if (!plan) continue;
    for (const [role, instance] of [[node.role_id, plan.instance_id],
        [node.verifier_role_id, plan.verifier_instance_id]]) {
      const id = typeof role === "string" && typeof instance === "string" ? harness(instance) : null;
      if (id !== null && !Object.hasOwn(found, role)) found[role] = id;
    }
  }
  return found;
}

// -- the instruction fields --------------------------------------------------------------

function entryOf(step, entries) {
  if (Object.hasOwn(entries, step.step_id)) return entries[step.step_id];
  if (typeof step.instruction_from === "string") {
    return {source: "like", like: step.instruction_from, text: ""};
  }
  const doer = roleKind(step.role_id) === "doer";
  return {source: doer ? "task" : "own", like: null, text: ""};
}

//: One field for each dispatch step of the chosen cycle, in step order. The doer's text is the
//: task's, labelled as such, until the owner writes it apart; a tester or a custom step starts
//: empty; "like step X" is offered only where the wizard may write the flow (a cycle the product
//: does not own), only to a step with no "like" of its own, and never to one others already
//: follow (spec 6.2.4).
export function fieldsOf(flow, entries, taskText, owned) {
  const steps = dispatchSteps(flow);
  const held = new Map(steps.map((step) => [step.step_id, entryOf(step, entries)]));
  return steps.map((step) => {
    const entry = held.get(step.step_id);
    const sharedWith = steps.filter((one) => held.get(one.step_id).source === "like"
      && held.get(one.step_id).like === step.step_id).map((one) => one.step_id);
    const choices = owned && sharedWith.length === 0 ? steps.filter((one) =>
      one.step_id !== step.step_id && held.get(one.step_id).source !== "like")
      .map((one) => one.step_id) : [];
    const kind = roleKind(step.role_id);
    return {step_id: step.step_id, title: step.title ?? null, role_id: step.role_id,
      kind: kind === "doer" || kind === "tester" ? kind : "custom",
      required: entry.source !== "like", source: entry.source, like: entry.like,
      sharedWith, costNote: entry.source === "like", likeChoices: choices,
      text: entry.source === "task" ? taskText : entry.source === "own" ? entry.text : ""};
  });
}
