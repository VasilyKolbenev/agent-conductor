"use strict";
// Acceptance belongs to the selected task/run, not to whether its centre panel is open.
// The server owns eligibility and Git facts; this host only presents exact preview terms.
//
// After the commit come two more presses of the same kind (spec 9.7): the push to GitHub and the
// pull request. Each has its own record, the second shows only once the first has one, and no
// outside action is ever repeated by this host: an answer that is not known leaves "Check again",
// which asks the server to look (`check: true`) and never to act.
import {element} from "./command-view.js";
import {localize, MESSAGES} from "./studio-i18n.js";
import {path} from "./desk-transport.js";

const DIGEST = /^sha256:[0-9a-f]{64}$/;
const text = (locale, key, params) => localize({locale: locale()}, key, params);
const word = (locale, kind, value) => text(locale,
  Object.hasOwn(MESSAGES, `desk.accept.${kind}.${value}`)
    ? `desk.accept.${kind}.${value}` : "desk.accept.other");
const line = (label, value) => element("p", {className: "desk-accept__fact"}, [
  element("strong", {text: label}), document.createTextNode(` ${value ?? "—"}`)]);

// -- the two steps after the commit ---------------------------------------------------------
const TARGET = Object.freeze({push: "acceptPush", pr: "acceptPullRequest"});
const RECORD = Object.freeze({push: "push", pr: "pull_request"});
// The second word of `pr_mismatch`: why a pull request is not the sent commit's own.
const MISMATCH = Object.freeze({
  remote_head_moved: "desk.accept.pr.mismatch.remote_head_moved",
  other_head: "desk.accept.pr.mismatch.other_head",
  other_base: "desk.accept.pr.mismatch.other_base",
  cross_repository: "desk.accept.pr.mismatch.cross_repository"});
// After these refusals of the push it is not known whether the branch is there; after these the
// look found it absent, so sending again is safe. Every other refusal is final: the terms are
// read again. A pull request is unknown only when its creation could not be confirmed.
const PUSH_UNKNOWN = Object.freeze(["push_unconfirmed", "push_auth_failed"]);
const PUSH_ABSENT = Object.freeze(["push_timed_out", "git_failed", "git_timed_out"]);
const PR_UNKNOWN = Object.freeze(["pr_create_failed", "push_auth_failed"]);
const WORKING = Object.freeze(["previewing", "sending", "checking"]);
const LOGIN = "gh auth login --hostname github.com --web";
const PULL_URL = new RegExp("^https://github\\.com/[A-Za-z0-9][A-Za-z0-9-]{0,38}/"
  + "[A-Za-z0-9._-]{1,100}/pull/[0-9]+$");
const newPush = () => ({phase: "idle", confirming: false, error: null, login: false,
  remotes: [], terms: null});
const newPr = () => ({phase: "idle", confirming: false, error: null, login: false,
  fields: null});
const shellWord = (value) => /^[A-Za-z0-9._/:@=+-]+$/.test(value) ? value
  : `'${value.replaceAll("'", "'\\''")}'`;
const str = (value) => String(value ?? "");
const githubRemotes = (answer) => (answer?.git?.remotes ?? [])
  .filter((row) => typeof row?.github === "string" && row.github && typeof row.name === "string")
  .map((row) => row.name);
const branchOf = (answer) => {
  const ref = answer?.git?.head?.ref;
  return typeof ref === "string" && ref.startsWith("refs/heads/") ? ref.slice(11) : "main";
};
// The terms are the ones asked for: this commit, this branch, this remote, a whole digest.
const sameTerms = (terms, commit, remote) => terms?.commit === commit.commit
  && terms.remote === remote && terms.ref === `refs/heads/${commit.branch}`
  && DIGEST.test(terms.push_digest)
  && ["repo", "push_url", "command"].every((name) => typeof terms[name] === "string");
const outcome = (step, reason) => {
  if (step === "pr") return PR_UNKNOWN.includes(reason) ? "unknown" : "refused";
  if (PUSH_UNKNOWN.includes(reason)) return "unknown";
  return PUSH_ABSENT.includes(reason) ? "absent" : "refused";
};

export function createAcceptHost({door, binding, locale, onChange, onForeign, openDetails}) {
  let selected = null, task = null, detailStamp = null, epoch = 0, disposed = false;
  let facts = null, preview = null, confirming = false, phase = "idle", error = null;
  let branch = "", title = "", documents = null, actor = null, optionsRevision = 0;
  let availableDocs = [], rereading = false;
  let push = newPush(), pr = newPr(), headBranch = "main";
  const pult = element("section", {className: "desk-accept"});
  const detail = element("section", {className: "desk-accept desk-accept--detail"});
  // While the selected run is read again the desk draws the earlier read as "stale": an answer
  // to this host's own request still belongs to that run, so it may land, but nothing is asked
  // or confirmed until the new read has landed and shown the run unchanged.
  function current(ticket, write = false) {
    const now = binding();
    return !disposed && ticket === epoch && !now.foreign
      && (now.ready || (rereading && !write))
      && now.runId === selected && now.taskId === task
      && (!write || (now.mode === "active" && now.connection === "open"));
  }
  function reset() {
    facts = preview = null; confirming = false; phase = "idle"; error = null;
    branch = title = ""; documents = null; availableDocs = []; optionsRevision += 1;
    push = newPush(); pr = newPr(); headBranch = "main";
  }
  // Nothing confirmed stands once the facts are read again or the person who signs is another.
  function unconfirm() {
    confirming = false; push = {...push, confirming: false}; pr = {...pr, confirming: false};
  }
  function notice(code, reason) {
    if (reason && Object.hasOwn(MESSAGES, `accept.reason.${reason}`)) {
      return text(locale, `accept.reason.${reason}`);
    }
    return text(locale, Object.hasOwn(MESSAGES, `error.${code}`)
      ? `error.${code}` : "desk.accept.failed");
  }
  async function read() {
    if (selected === null || !current(epoch)) return;
    const ticket = epoch, runId = selected;
    phase = "reading"; error = null; preview = null; unconfirm();
    void Promise.resolve().then(() => { if (current(ticket)) onChange(); });
    try {
      const answer = await door.readJson(path.accept(runId));
      if (!current(ticket)) return;
      facts = answer; phase = "ready";
    } catch (failure) {
      if (!current(ticket)) return;
      if (failure?.message === "project_mismatch") { onForeign(); return; }
      facts = null; phase = "failed"; error = notice(failure?.message);
    }
    onChange();
  }
  function sync(desk) {
    if (disposed) return;
    const detail = desk.run.detail;
    const shown = detail?.config?.task?.id === desk.taskId ? detail?.run?.run_id ?? null : null;
    const value = desk.run.phase === "ready" ? shown : null;
    // The run held is read again: what stands is kept until the read lands and says if it changed.
    rereading = desk.run.phase === "stale" && shown !== null && shown === selected
      && desk.taskId === task;
    const records = detail?.records ?? [];
    const last = records.at(-1);
    const stamp = value === null ? null : `${detail?.run?.status ?? ""}/${records.length}/`
      + `${last?.sequence ?? last?.record_id ?? last?.record_type ?? ""}`;
    if (!rereading && (value !== selected || desk.taskId !== task || stamp !== detailStamp)) {
      epoch += 1; selected = value; task = desk.taskId; detailStamp = stamp; reset();
      if (value !== null) {
        const nodes = desk.run.detail?.graph?.definition?.nodes ?? [];
        const refs = new Set(nodes.filter((node) => node.capability === "review")
          .map((node) => node.arguments?.result_artifact_ref).filter(Boolean));
        if (desk.run.detail?.config?.workflow?.workflow_id === "desk-starter-docs") {
          for (const ref of ["artifact-brief", "artifact-plan", "artifact-ideas",
            "artifact-scheme"]) refs.add(ref);
        }
        const artifacts = desk.run.detail?.records ?? [];
        availableDocs = [...refs].filter((ref) => artifacts.some((row) =>
          row.record_type === "artifact" && row.record?.artifact_ref === ref));
      }
      if (value !== null) void read();
    }
    if (actor !== desk.actor) unconfirm();
    actor = desk.actor;
  }
  async function makePreview() {
    const ticket = epoch, runId = selected;
    if (!current(ticket, true) || phase !== "ready" || !facts || facts.basis?.refused
        || facts.commit || !actor) return;
    const body = {};
    if (branch.trim()) body.branch = branch.trim();
    if (title.trim()) body.title = title.trim();
    if (documents !== null) body.documents = documents;
    const revision = optionsRevision;
    phase = "previewing"; preview = null; confirming = false; error = null; onChange();
    let answer;
    try { answer = await door.submit("acceptPreview", runId, body); }
    catch (_failure) { answer = {status: "unknown"}; }
    if (!current(ticket) || revision !== optionsRevision) return;
    if (answer.code === "project_mismatch") { onForeign(); return; }
    const value = answer.payload?.accept;
    if (answer.status === "accepted" && value?.run_id === runId
        && value.task_id === task && DIGEST.test(value.accept_digest)) {
      preview = value; phase = "preview";
      availableDocs = [...new Set([...availableDocs,
        ...(value.documents ?? []).map((row) => row.artifact_ref)])];
    } else {
      phase = answer.status === "unknown" ? "unknown" : "ready";
      error = answer.status === "unknown" ? text(locale, "desk.accept.unknown_preview")
        : notice(answer.code, answer.payload?.error?.detail?.reason);
    }
    onChange();
  }
  async function commit() {
    const ticket = epoch, runId = selected, digest = preview?.accept_digest;
    const signer = actor;
    if (!confirming || phase !== "preview" || !DIGEST.test(digest)
        || !current(ticket, true) || !signer) return;
    phase = "committing"; confirming = false; error = null; onChange();
    let answer;
    try { answer = await door.submit("acceptCommit", runId,
      {accept_digest: digest, actor: signer}); }
    catch (_failure) { answer = {status: "unknown"}; }
    if (!current(ticket)) return;
    if (answer.code === "project_mismatch") { onForeign(); return; }
    if (answer.status === "accepted" && answer.payload?.commit?.accept_digest === digest) {
      facts = {...facts, commit: answer.payload.commit};
      phase = "ready"; preview = null;
    } else {
      phase = answer.status === "unknown" ? "unknown" : "ready";
      preview = null;
      error = answer.status === "unknown" ? text(locale, "desk.accept.unknown_commit")
        : notice(answer.code, answer.payload?.error?.detail?.reason);
    }
    onChange();
  }
  // -- the push and the pull request after the commit (spec 9.7) -----------------------------
  const setStep = (step, patch) => {
    if (step === "push") push = {...push, ...patch}; else pr = {...pr, ...patch};
  };
  // A press on either step is a write for the run held, by a named person, on facts that are read.
  const writable = (ticket) => phase === "ready" && Boolean(actor) && current(ticket, true);
  function refusalText(answer) {
    const detail = answer.payload?.error?.detail;
    if (detail?.reason === "pr_mismatch" && Object.hasOwn(MISMATCH, detail.mismatch)) {
      return text(locale, MISMATCH[detail.mismatch]);
    }
    return notice(answer.code, detail?.reason);
  }
  // What the owner may edit before the pull request, and what it starts as (the owner edits it).
  function defaults() {
    const commit = facts.commit;
    return {base: headBranch, draft: false,
      title: text(locale, "desk.accept.pr.default_title", {run: str(selected)}),
      body: text(locale, "desk.accept.pr.default_body", {run: str(selected),
        actor: str(commit.requested_by), branch: str(commit.branch), commit: str(commit.commit),
        count: str(commit.file_count)})};
  }
  const fieldsOf = () => pr.fields ?? defaults();
  const fieldsFit = (fields) => Boolean(fields.base.trim() && fields.title.trim());
  function prCommand(fields) {
    const argv = ["gh", "pr", "create", "--repo", facts.push.remote_repo, "--base",
      fields.base.trim(), "--head", facts.push.ref.replace(/^refs\/heads\//, ""), "--title",
      fields.title.trim(), "--body-file", "-"];
    return (fields.draft ? [...argv, "--draft"] : argv).map(shellWord).join(" ");
  }
  async function pushTerms(chosen) {
    const ticket = epoch, runId = selected, commit = facts?.commit;
    if (!writable(ticket) || !commit || !["idle", "choosing"].includes(push.phase)) return;
    push = {...push, phase: "previewing", error: null}; onChange();
    let remote = chosen, names = null, branch = "main";
    if (remote === undefined) {
      try {
        const answer = await door.readJson(path.git());
        names = githubRemotes(answer); branch = branchOf(answer);
      } catch (failure) {
        if (!current(ticket)) return;
        if (failure?.message === "project_mismatch") { onForeign(); return; }
      }
      if (!current(ticket)) return;
      headBranch = branch;
      if (names?.length !== 1) { chooseRemote(names); return; }
      remote = names[0];
    }
    await askTerms(ticket, runId, commit, remote);
  }
  function chooseRemote(names) {
    if (names === null || names.length === 0) {
      push = {...push, phase: "idle", error: text(locale, names === null
        ? "desk.accept.push.remotes_failed" : "desk.accept.push.no_remote")};
    } else push = {...push, phase: "choosing", remotes: names, error: null};
    onChange();
  }
  async function askTerms(ticket, runId, commit, remote) {
    let answer;
    try { answer = await door.submit(TARGET.push, runId,
      {acceptance_id: commit.acceptance_id, remote, preview: true}); }
    catch (_failure) { answer = {status: "unknown"}; }
    if (!current(ticket)) return;
    if (answer.code === "project_mismatch") { onForeign(); return; }
    const terms = answer.payload?.push_terms;
    if (answer.status === "accepted" && sameTerms(terms, commit, remote)) {
      push = {...push, phase: "terms", terms, error: null};
    } else {
      push = {...push, phase: "idle", terms: null, error: answer.status === "refused"
        ? refusalText(answer) : text(locale, "desk.accept.push.unknown_terms")};
    }
    onChange();
  }
  // The body of one press, exactly what the card showed, or null when the card cannot say it.
  function stepBody(step, signer, check) {
    const record = step === "push" ? facts?.commit : facts?.push;
    if (!record || !signer) return null;
    let body;
    if (step === "push") {
      const terms = push.terms;
      if (!terms || terms.commit !== record.commit) return null;
      body = {acceptance_id: record.acceptance_id, remote: terms.remote,
        push_digest: terms.push_digest, actor: signer};
    } else {
      const fields = fieldsOf();
      if (!fieldsFit(fields)) return null;
      body = {acceptance_id: record.acceptance_id, base: fields.base.trim(),
        title: fields.title.trim(), body: fields.body, draft: fields.draft, actor: signer};
    }
    return check ? {...body, check: true} : body;
  }
  // A step is pressed from the stage that offers the press: the first send only after its review,
  // "send again" only after a look found nothing there, and the check only after an unknown answer.
  function mayPress(step, check) {
    const state = step === "push" ? push : pr;
    if (check) return state.phase === "unknown";
    if (state.phase === "absent") return true;
    return state.confirming && state.phase === (step === "push" ? "terms" : "idle");
  }
  function review(step) {
    const state = step === "push" ? push : pr;
    const here = step === "push" ? state.phase === "terms"
      : state.phase === "idle" && fieldsFit(fieldsOf());
    if (!writable(epoch) || !here) return;
    setStep(step, {confirming: true}); onChange();
  }
  function back(step) { setStep(step, {confirming: false}); onChange(); }
  async function send(step, check) {
    const ticket = epoch, runId = selected, body = stepBody(step, actor, check);
    if (!body || !writable(ticket) || !mayPress(step, check)) return;
    setStep(step, {phase: check ? "checking" : "sending", confirming: false, error: null,
      login: false});
    onChange();
    let answer;
    try { answer = await door.submit(TARGET[step], runId, body); }
    catch (_failure) { answer = {status: "unknown"}; }
    if (!current(ticket)) return;
    if (answer.code === "project_mismatch") { onForeign(); return; }
    settle(step, answer, check);
    onChange();
  }
  // The record the answer brings must be the one this card asked for.
  function recordFits(step, record) {
    if (step === "push") {
      return record?.acceptance_id === facts.commit.acceptance_id
        && record.commit === facts.commit.commit
        && record.push_digest === push.terms?.push_digest && typeof record.remote_oid === "string";
    }
    return record?.acceptance_id === facts.push.acceptance_id
      && record.head_oid === facts.push.commit && Number.isInteger(record.number)
      && record.number > 0 && typeof record.url === "string";
  }
  function settle(step, answer, check) {
    const key = RECORD[step];
    const record = answer.status === "accepted" ? answer.payload?.[key] : undefined;
    if (record === null && check) { setStep(step, {phase: "absent", error: null}); return; }
    if (record !== undefined && recordFits(step, record)) {
      facts = {...facts, [key]: record};
      setStep(step, {phase: "idle", error: null, login: false}); return;
    }
    const refusal = answer.status === "refused";
    const reason = answer.payload?.error?.detail?.reason;
    const kind = refusal ? outcome(step, reason) : "unknown";
    const said = refusal ? refusalText(answer) : null;
    if (kind !== "refused") setStep(step, {phase: kind, error: said});
    else if (step === "push") setStep(step, {phase: "idle", error: said, terms: null});
    else setStep(step, {phase: "idle", error: said, login: reason === "gh_not_logged_in"});
  }
  function editPr(name, value) {
    if (pr.phase !== "idle" && pr.phase !== "absent") return;
    pr = {...pr, fields: {...fieldsOf(), [name]: value}, confirming: false}; onChange();
  }
  function button(label, action, disabled = false, where = "detail") {
    const node = element("button", {type: "button", text: text(locale, label),
      "data-focus-key": `accept:${where}:${label}`});
    node.disabled = disabled; node.addEventListener("click", action); return node;
  }
  function editField(key, value, set) {
    const input = element("input", {type: "text", value, autocomplete: "off",
      "data-focus-key": key, "data-focus-value": "state"});
    input.disabled = phase === "committing";
    input.addEventListener("input", () => {
      if (phase === "committing") return;
      set(input.value); optionsRevision += 1; preview = null;
      confirming = false; if (phase === "preview" || phase === "previewing") phase = "ready";
    });
    return element("label", {className: "desk-accept__field"}, [
      element("span", {text: text(locale, key)}), input]);
  }
  function previewContent(target) {
    const value = preview;
    target.append(line(text(locale, "desk.accept.base"), value.base?.commit),
      line(text(locale, "desk.accept.branch"), value.branch),
      line(text(locale, "desk.accept.author"),
        `${value.author?.name ?? ""} <${value.author?.email ?? ""}>`),
      line(text(locale, "desk.accept.digest"), value.accept_digest),
      element("h4", {text: text(locale, "desk.accept.files")}));
    const files = element("ul");
    for (const row of value.files ?? []) files.append(element("li", {
      text: `${word(locale, "state", row.state)} · ${row.path} · ${row.mode}`}));
    target.append(files);
    if (value.skipped?.length) {
      target.append(element("h4", {text: text(locale, "desk.accept.skipped")}));
      for (const row of value.skipped) target.append(line(row.path,
        word(locale, "skip", row.reason)));
    }
    if (value.warnings?.length) target.append(line(text(locale, "desk.accept.warnings"),
      value.warnings.map((warning) => word(locale, "warning", warning)).join(", ")));
    target.append(element("h4", {text: text(locale, "desk.accept.message")}),
      element("pre", {text: value.message ?? ""}),
      element("h4", {text: text(locale, "desk.accept.patch")}),
      element("pre", {text: value.patch?.text ?? ""}));
    if (value.patch?.truncated) target.append(element("p", {
      text: text(locale, "desk.accept.truncated")}));
  }
  function draw(target, desk, full) {
    target.replaceChildren(element("h3", {text: text(locale, "desk.accept.heading")}));
    target.setAttribute("data-subject", `${task ?? "none"}/${selected ?? "none"}`);
    if (selected === null) { target.append(element("p", {
      text: text(locale, "desk.accept.no_run")})); return; }
    if (phase === "reading") target.append(element("p", {
      text: text(locale, "desk.accept.reading")}));
    // The run held is read again: the controls below are off until the new read has landed.
    if (rereading) target.append(element("p", {role: "status",
      text: text(locale, "desk.run.updating")}));
    if (facts?.commit) {
      target.append(line(text(locale, "desk.accept.branch"), facts.commit.branch),
        line(text(locale, "desk.accept.commit"), facts.commit.commit));
      if (full) drawSteps(target, desk); else drawSummary(target);
      return;
    }
    if (facts?.basis?.refused) target.append(element("p", {
      text: notice("accept_refused", facts.basis.refused)}));
    if (desk.mode === "view") target.append(element("p", {
      text: text(locale, "desk.run.view_blocked")}));
    if (error) target.append(element("p", {role: "status", text: error}));
    if (!full) {
      if (phase === "previewing" || phase === "committing") target.append(element("p", {
        text: text(locale, "desk.accept.working")}));
      if (phase === "unknown" || phase === "failed" || phase === "ready") {
        target.append(button("desk.accept.refresh", read, false, "pult"));
      }
      target.append(button("desk.accept.open", openDetails, !facts, "pult"));
      return;
    }
    if (phase === "unknown" || phase === "failed" || phase === "ready") {
      target.append(button("desk.accept.refresh", read));
    }
    if (!facts) return;
    if (facts.basis?.refused) {
      target.append(button("desk.accept.preview", makePreview, true));
      return;
    }
    if (facts.commit) return;
    if (full) {
      target.append(editField("desk.accept.branch", branch, (v) => { branch = v; }),
        editField("desk.accept.title", title, (v) => { title = v; }));
      if (availableDocs.length) {
        target.append(element("h4", {text: text(locale, "desk.accept.documents")}));
        for (const ref of availableDocs) {
          const check = element("input", {type: "checkbox",
            "data-focus-key": `accept:document:${ref}`});
          check.disabled = phase === "committing";
          check.checked = documents === null ? facts.kind === "documents"
            : documents.includes(ref);
          check.addEventListener("change", () => {
            if (phase === "committing") return;
            const selected = documents === null
              ? facts.kind === "documents" ? [...availableDocs] : [] : [...documents];
            documents = check.checked ? [...new Set([...selected, ref])]
              : selected.filter((item) => item !== ref);
            optionsRevision += 1; preview = null; confirming = false;
            phase = "ready"; onChange();
          });
          const shown = preview?.documents?.find((row) => row.artifact_ref === ref);
          target.append(element("label", {className: "desk-accept__choice"}, [check,
            document.createTextNode(shown?.path ?? ref)]));
        }
      }
    }
    const blocked = desk.mode !== "active" || !actor || !current(epoch, true);
    if (!actor) target.append(element("p", {text: text(locale, "desk.accept.actor")}));
    if (phase === "ready" || phase === "preview") {
      target.append(button("desk.accept.preview", makePreview, blocked));
    }
    if (phase === "previewing" || phase === "committing") target.append(element("p", {
      text: text(locale, "desk.accept.working")}));
    if (phase !== "preview" || !preview) return;
    previewContent(target);
    if (!confirming) target.append(button("desk.accept.review", () => {
      if (!current(epoch, true) || phase !== "preview") return;
      confirming = true; onChange();
    }, blocked));
    else target.append(element("p", {text: text(locale, "desk.accept.confirm_text", {
      digest: preview.accept_digest, actor})}),
      button("desk.accept.commit_action", commit, blocked),
      button("desk.accept.cancel", () => { confirming = false; onChange(); }));
  }
  // The compact card tells the standing records and leaves the steps to the details.
  function drawSummary(target) {
    if (facts.push) target.append(line(text(locale, "desk.accept.push.sent"),
      facts.push.remote_repo));
    if (facts.pull_request) {
      target.append(line(text(locale, "desk.accept.pr.number"), `#${facts.pull_request.number}`));
    } else target.append(button("desk.accept.open", openDetails, false, "pult"));
  }
  function drawSteps(target, desk) {
    const blocked = desk.mode !== "active" || !actor || phase !== "ready"
      || !current(epoch, true);
    if (desk.mode === "view") target.append(element("p", {
      text: text(locale, "desk.run.view_blocked")}));
    else if (!actor) target.append(element("p", {text: text(locale, "desk.accept.actor")}));
    drawPush(target, blocked);
    if (facts.push) drawPr(target, blocked);
  }
  function waiting(target) {
    target.append(element("p", {text: text(locale, "desk.accept.working")}));
  }
  function drawPush(target, blocked) {
    target.append(element("h4", {text: text(locale, "desk.accept.push.heading")}));
    const row = facts.push;
    if (row) {
      target.append(line(text(locale, "desk.accept.push.sent"), row.remote_repo),
        line(text(locale, "desk.accept.push.ref"), row.ref),
        line(text(locale, "desk.accept.push.remote_oid"), row.remote_oid));
      return;
    }
    target.append(element("p", {text: text(locale, "desk.accept.push.effect")}));
    if (push.terms) termsFacts(target, push.terms);
    if (push.error) target.append(element("p", {role: "status", text: push.error}));
    if (WORKING.includes(push.phase)) waiting(target); else pushControls(target, blocked);
  }
  function termsFacts(target, terms) {
    target.append(line(text(locale, "desk.accept.push.remote"), terms.remote),
      line(text(locale, "desk.accept.push.repo"), terms.repo),
      line(text(locale, "desk.accept.push.url"), terms.push_url),
      line(text(locale, "desk.accept.push.ref"), terms.ref),
      line(text(locale, "desk.accept.push.oid"), terms.commit),
      line(text(locale, "desk.accept.push.digest"), terms.push_digest),
      element("h4", {text: text(locale, "desk.accept.command")}),
      element("pre", {text: terms.command}));
  }
  function remoteButton(name, blocked) {
    const node = element("button", {type: "button", "data-focus-key": `accept:push:remote:${name}`,
      text: text(locale, "desk.accept.push.remote_action", {remote: name})});
    node.disabled = blocked; node.addEventListener("click", () => pushTerms(name));
    return node;
  }
  function pushControls(target, blocked) {
    const press = (label, action, off = blocked) => button(label, action, off, "push");
    if (push.phase === "choosing") {
      target.append(element("p", {text: text(locale, "desk.accept.push.choose")}));
      for (const name of push.remotes) target.append(remoteButton(name, blocked));
    } else if (push.phase === "terms" && !push.confirming) {
      target.append(press("desk.accept.review", () => review("push")));
    } else if (push.phase === "terms") {
      const terms = push.terms;
      target.append(element("p", {text: text(locale, "desk.accept.push.confirm_text", {
        commit: terms.commit.slice(0, 7), repo: terms.repo, ref: terms.ref,
        digest: terms.push_digest, actor: str(actor)})}),
        press("desk.accept.push.action", () => send("push", false)),
        press("desk.accept.push.back", () => back("push"), false));
    } else if (push.phase === "unknown") {
      target.append(element("p", {text: text(locale, "desk.accept.push.unknown")}),
        press("desk.accept.check", () => send("push", true)));
    } else if (push.phase === "absent") {
      if (!push.error) target.append(element("p", {
        text: text(locale, "desk.accept.push.absent")}));
      target.append(press("desk.accept.push.again", () => send("push", false)));
    } else target.append(press("desk.accept.push.terms", () => pushTerms()));
  }
  function prField(tag, key, value, set, locked) {
    const input = element(tag, {"data-focus-key": key, "data-focus-value": "state",
      autocomplete: "off", type: tag === "input" ? "text" : null});
    input.value = value; input.disabled = locked;
    input.addEventListener("input", () => set(input.value));
    return element("label", {className: "desk-accept__field"}, [
      element("span", {text: text(locale, key)}), input]);
  }
  function draftBox(fields, locked) {
    const box = element("input", {type: "checkbox", "data-focus-key": "desk.accept.pr.draft"});
    box.checked = fields.draft; box.disabled = locked;
    box.addEventListener("change", () => editPr("draft", box.checked));
    return element("label", {className: "desk-accept__choice"}, [box,
      document.createTextNode(text(locale, "desk.accept.pr.draft"))]);
  }
  function drawPr(target, blocked) {
    target.append(element("h4", {text: text(locale, "desk.accept.pr.heading")}));
    if (facts.pull_request) { prRecord(target, facts.pull_request); return; }
    target.append(element("p", {text: text(locale, "desk.accept.pr.effect")}));
    if (pr.error) target.append(element("p", {role: "status", text: pr.error}));
    if (pr.login) target.append(line(text(locale, "desk.accept.login"), LOGIN));
    const fields = fieldsOf(), locked = pr.phase !== "idle" && pr.phase !== "absent";
    target.append(
      prField("input", "desk.accept.pr.base", fields.base, (v) => editPr("base", v), locked),
      prField("input", "desk.accept.pr.title", fields.title, (v) => editPr("title", v), locked),
      prField("textarea", "desk.accept.pr.body", fields.body, (v) => editPr("body", v), locked),
      draftBox(fields, locked), element("h4", {text: text(locale, "desk.accept.command")}),
      element("pre", {text: prCommand(fields)}));
    if (WORKING.includes(pr.phase)) waiting(target); else prControls(target, blocked, fields);
  }
  function prControls(target, blocked, fields) {
    const press = (label, action, off = blocked) => button(label, action, off, "pr");
    const off = blocked || !fieldsFit(fields);
    if (pr.phase === "unknown") {
      target.append(element("p", {text: text(locale, "desk.accept.pr.unknown")}),
        press("desk.accept.check", () => send("pr", true)));
    } else if (pr.phase === "absent") {
      if (!pr.error) target.append(element("p", {text: text(locale, "desk.accept.pr.absent")}));
      target.append(press("desk.accept.pr.again", () => send("pr", false), off));
    } else if (!pr.confirming) {
      target.append(press("desk.accept.review", () => review("pr"), off));
    } else {
      target.append(element("p", {text: text(locale, "desk.accept.pr.confirm_text", {
        repo: facts.push.remote_repo, head: facts.push.ref.replace(/^refs\/heads\//, ""),
        base: fields.base.trim(), actor: str(actor)})}),
        press("desk.accept.pr.action", () => send("pr", false)),
        press("desk.accept.pr.back", () => back("pr"), false));
    }
  }
  function prRecord(target, row) {
    const link = PULL_URL.test(row.url) ? element("a", {href: row.url, target: "_blank",
      rel: "noopener noreferrer", text: row.url}) : document.createTextNode(str(row.url));
    target.append(line(text(locale, "desk.accept.pr.number"), `#${row.number}`),
      element("p", {className: "desk-accept__fact"}, [
        element("strong", {text: text(locale, "desk.accept.pr.link")}),
        document.createTextNode(" "), link]),
      line(text(locale, "desk.accept.pr.base"), row.base));
    if (row.mismatch) target.append(element("p", {role: "status", text: row.mismatch.head_oid
      !== row.head_oid ? text(locale, "desk.accept.pr.moved", {oid: str(row.mismatch.head_oid)})
      : text(locale, "desk.accept.pr.differs")}));
    target.append(element("p", {text: text(locale, "desk.accept.pr.merge")}));
  }
  function render(desk, open) {
    sync(desk);
    draw(pult, desk, false);
    if (open) draw(detail, desk, true);
  }
  function dispose() { disposed = true; epoch += 1; reset(); pult.remove(); detail.remove(); }
  return Object.freeze({pult, detail, render, dispose});
}
