"use strict";
import {element} from "./command-view.js";
import {localize} from "./studio-i18n.js";
import {cycleCards} from "./desk-wizard-model.js";
import {assignmentView} from "./desk-wizard-team.js";
import {quotaOf} from "./desk-wizard-roles.js";
import {grantAdvice, observeAdvice, prepareAdvice, recordAdviceChoice, requestFor, suggestionFrom} from "./desk-advice-run.js";

const words = (lang, key) => localize({locale: lang}, "advice."+key);

function subscribed(w) {
  const rows = w.reads.workflows?.payload?.providers ?? [];
  return rows.filter((p) => p.auth === "subscription" && p.offered === true && p.availability === "available"
    && ["boundary","review_only"].includes(p.task_road) && p.controls?.includes("review"));
}

function inputOf(w, lang, question) {
  const cycles = cycleCards(w).filter((c) => c.kind !== "build" && !c.locked);
  const roles = assignmentView(w);
  return {language: lang, task: w.task.brief, current_criterion: w.task.hint, question,
    cycles: [...new Set(cycles.map((c) => c.id))], current_cycle: w.cycle.choice?.workflowId ?? null,
    current_revision: w.cycle.choice?.revision ?? null, depth: w.budgetDepth ?? "balanced",
    current_roles: Object.fromEntries(roles.map((r) => [r.role_id,r.provider ?? null])),
    role_options: Object.fromEntries(roles.map((r) => [r.role_id, r.offers.map((p) => p.id)]))};
}

function button(key, text, handler, disabled = false) {
  const cls = key === "open" || key === "close" ? key : "action";
  const node = element("button", {type: "button", className: "desk-advice__"+cls,
    "data-focus": "advisor:"+key, ["data-advice-"+key]: "", text});
  node.disabled = disabled;
  node.addEventListener("click", handler);
  return node;
}

function field(key, label, value, update, limit) {
  const input = element("input", {type: "text", maxlength: String(limit), "data-focus": "advisor:"+key,
    "data-focus-value": "state", ["data-advice-"+key]: ""});
  input.value = value;
  input.addEventListener("input", () => update(input.value));
  return element("label", {}, [label, input]);
}

export function createAdvicePanel({door, refresh, draft, dispatch, locale, actor}) {
  let open = false, provider = "", model = "", question = "", owner = "";
  let disclosure = {model: false, sent: false};
  let stage = null, request = null, reading = false, generation = 0;
  function reset() {
    generation += 1;
    reading = false;
    stage = request = null;
  }
  function close() {
    reset();
    open = false;
    disclosure = {model: false, sent: false};
    provider = model = question = owner = "";
  }
  function chosen(w) {
    const available = subscribed(w);
    return provider ? available.find((p) => p.provider_id === provider) : available[0];
  }
  function identity(w) {
    if (!w) return null;
    const selected = chosen(w);
    if (!selected || !w.task.brief.trim()) return null;
    return requestFor(w.task.taskId, selected.provider_id, selected.model_pin_supported ? model.trim() : "",
      inputOf(w, locale(), question.trim()));
  }
  function valid(at, req) {
    return generation === at && open && draft() && identity(draft())?.id === req.id;
  }
  function setError(error) {
    const key = error.message === "answer_invalid" ? "invalid"
      : error.message === "advice_unsuccessful" ? "failed"
      : error.message === "advice_stopped" ? "stopped" : "refusal";
    const code = /^[a-z_]{1,64}$/.test(error.message) ? error.message : null;
    stage = {phase: "error", key, code};
  }
  function showAnswer(value, req) {
    if (value.phase !== "result") { stage = value; return; }
    if (value.choice === "reject") { stage = {phase: "declined"}; return; }
    if (!owner.trim() && typeof value.actor === "string") owner = value.actor;
    stage = {...value, suggestion: suggestionFrom(value.content, JSON.parse(req.content))};
  }
  async function update(op) {
    const req = identity(draft());
    if (!req) return;
    const preview = stage?.preview;
    reset();
    const at = generation;
    request = req;
    stage = {phase: "busy"};
    refresh();
    try {
      const value = op === "prepare" ? await prepareAdvice(door, req, words(locale(),"title"))
        : await grantAdvice(door, req, preview, owner.trim(), () => valid(at, req));
      if (!valid(at, req)) return;
      showAnswer(value, req);
    } catch (error) {
      if (valid(at, req)) setError(error);
      else if (op === "grant" && error.message === "preview_changed" && at === generation && open) {
        stage = {phase: "withdrawn"};
        refresh();
      }
    } finally {
      if (valid(at, req)) refresh();
    }
  }
  async function tick() {
    const at = generation, req = request;
    if (reading || stage?.phase !== "running" || !valid(at, req)) return;
    reading = true;
    try {
      const next = await observeAdvice(door, req);
      if (valid(at, req)) showAnswer(next, req);
    } catch (error) {
      if (valid(at, req)) setError(error);
    } finally {
      if (at === generation) { reading = false; refresh(); }
    }
  }
  function edit(set) {
    reset();
    set();
    refresh();
  }
  async function decide(action) {
    const w = draft();
    if (!w || !request || identity(w)?.id !== request.id || !stage?.suggestion) return;
    const {suggestion: proposal, content} = stage, at = generation, req = request;
    stage = {phase: "busy"};
    refresh();
    try {
      await recordAdviceChoice(door, req, content, owner.trim(), action,
        action === "reject" ? words(locale(),"decline") : "", () => valid(at, req));
    } catch (error) {
      if (valid(at, req)) { setError(error); refresh(); }
      return;
    }
    if (!valid(at, req)) return;
    reset();
    if (action === "reject") { stage = {phase: "declined"}; refresh(); return; }
    stage = {phase: "applied"};
    dispatch({type: "edit-hint", value: proposal.criterion});
    if (proposal.cycle_id && proposal.cycle_id !== w.cycle.choice?.workflowId)
      dispatch({type: "cycle-choose", id: proposal.cycle_id});
    for (const [role, id] of Object.entries(proposal.roles))
      dispatch({type: "role-assign", role_id: role, provider_id: id});
    if (proposal.depth) dispatch({type: "launch-budget", depth: proposal.depth});
    refresh();
  }
  function details(label, children, key) {
    const node = element("details", {}, [element("summary", {text: label}), ...children]);
    node.open = disclosure[key];
    node.addEventListener("toggle", () => {
      if (node.isConnected) disclosure[key] = node.open;
    });
    return node;
  }
  function setupFields(w, list, selected, t) {
    const select = element("select", {"data-focus": "advisor:provider"});
    for (const row of list) {
      select.append(element("option", {value: row.provider_id, text: row.display_name ?? row.provider_id}));
    }
    if (!selected) select.prepend(element("option", {value: "", text: "—"}));
    select.value = selected?.provider_id ?? "";
    select.addEventListener("change", () => edit(() => { provider = select.value; model = ""; }));
    const fields = [element("label", {}, [t("provider"), select])];
    if (!selected) return fields;
    fields.push(field("question", t("question"), question, (value) => edit(() => { question = value; }), 1000));
    if (selected.model_pin_supported) {
      fields.push(details(t("advanced"), [field("model", t("model"), model,
        (value) => edit(() => { model = value; }), 128)], "model"));
    }
    return fields;
  }
  function previewCard(t, quota) {
    const input = JSON.parse(request.content);
    const sent = details(t("sent"), [element("p", {text: t("inputs")}), element("p", {text: input.task}),
      ...(input.current_criterion ? [element("p", {text: input.current_criterion})] : []),
      ...(input.question ? [element("p", {text: input.question})] : []),
      element("p", {text: t("cycle")+" · "+input.cycles.join(", ")}),
      ...Object.entries(input.role_options).map(([role, ids]) => element("p", {text: role+" · "+ids.join(", ")}))], "sent");
    if (Date.parse(stage.preview.valid_until) <= Date.now()) {
      return [sent, element("p", {text: t("expired")}), button("prepare", t("prepare"), () => void update("prepare"))];
    }
    const exhausted = quota.kind === "percent" && quota.remaining <= 0;
    return [element("p", {text: request.provider+" · "+(request.model || t("default_model"))}), sent,
      ...(exhausted ? [element("p", {role: "status", text: t("exhausted")})] : []),
      field("actor", t("actor"), owner, (value) => { owner = value; refresh(); }, 128),
      button("grant", t("grant"), () => void update("grant"), exhausted || !owner.trim())];
  }
  function resultCard(t) {
    const proposal = stage.suggestion;
    const canSign = /^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$/.test(owner.trim());
    return [element("strong", {text: t("criterion")}), element("p", {text: proposal.criterion}),
      ...(proposal.question ? [element("p", {text: proposal.question})] : []),
      ...(proposal.cycle_id ? [element("p", {text: t("cycle")+" · "+proposal.cycle_id})] : []),
      ...(proposal.depth ? [element("p", {text: t("depth")+" · "+t(proposal.depth)})] : []),
      ...Object.entries(proposal.roles).map(([role, id]) => element("p", {text: role+" · "+id})),
      field("actor", t("sign"), owner, (value) => { owner = value; refresh(); }, 128),
      ...(!canSign ? [element("p", {text: t("sign_hint")})] : []),
      button("apply", t("apply"), () => void decide("approve"), !canSign),
      button("decline", t("decline"), () => void decide("reject"), !canSign)];
  }
  function stageCard(t, quota, current) {
    const phase = current ? stage?.phase : null;
    if (phase === "preview") return previewCard(t, quota);
    if (phase === "result") return resultCard(t);
    if (phase === "busy" || phase === "running") {
      const key = phase === "busy" ? "preparing" : stage.waiting ? "waiting" : "working";
      return [element("p", {role: "status", text: t(key)})];
    }
    const notes = [];
    if (!current && stage?.phase === "withdrawn") notes.push(element("p", {role:"status", text:t("withdrawn")}));
    if (!current) notes.push(element("p", {role: "status", text: t("changed")}));
    if (phase === "error") {
      notes.push(element("p", {role: "alert", text: t(stage.key)}));
      if (stage.key === "invalid" || stage.key === "failed")
        return [...notes, element("p", {text: t("new_question")})];
      if (stage.key === "stopped") return notes;
      if (stage.code) notes.push(element("details", {}, [element("summary", {text: t("diagnostics")}),
        element("code", {text: stage.code})]));
    }
    if (phase === "applied") notes.push(element("p", {role: "status", text: t("applied")}));
    if (phase === "declined") notes.push(element("p", {role: "status", text: t("declined")}));
    return [...notes, button("prepare", t("prepare"), () => void update("prepare"))];
  }
  function panel(w) {
    if (!w.task.brief.trim() || w.mode.view || w.run.pressed || w.task.written) return null;
    const t = (key) => words(locale(), key);
    if (!open && !subscribed(w).length) return null;
    if (!open) return button("open", t("open"), () => {
      open = true; owner = actor() ?? ""; refresh();
    });
    const box = element("section", {"data-launch-advice": "", className: "desk-advice desk-wizard__dialog",
      "data-advice-run": request?.id ?? "", "aria-label": t("open")});
    box.append(button("close", t("close"), () => { close(); refresh(); }));
    const list = subscribed(w), selected = chosen(w);
    if (!list.length) { box.append(element("p", {text: t("none")})); return box; }
    box.append(...setupFields(w, list, selected, t));
    if (!selected) return box;
    const quota = quotaOf(w.reads.quotas?.payload, selected.provider_id);
    const remainder = quota.kind === "percent" ? quota.remaining+"%"
      : t(quota.kind === "balance" ? "balance" : "unknown");
    box.append(element("p", {text: t("left")+" · "+remainder}),
      element("p", {text: t("cost")}), ...stageCard(t, quota, !request || identity(w)?.id === request.id));
    if (request) {
      const hash = new URLSearchParams({screen: "runs", task: request.id, run: request.id, lang: locale()});
      box.append(element("a", {href: "/#"+hash, target: "_blank", rel: "noopener", text: t("inspect")}));
    }
    return box;
  }
  return {panel, close, tick};
}
