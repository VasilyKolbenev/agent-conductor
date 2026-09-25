"use strict";
// The two screens about PEOPLE: what is waiting for a person's answer, and who
// this project's work is carried out by. Every node here is built from text; no
// markup string is ever parsed, nothing is fetched, and no clock is read.
//
// Decisions and Agents live in one file because they share one question --
// "who answers for this?" -- and because the join they both depend on is the
// same one, spelled the same way in both directions:
//
//   a PROVIDER row is about this BUILD and this MACHINE;
//   an INSTANCE row is about ONE RUN's frozen binding;
//   a consumer joins them by identity, never by a displayed label.
//
// The two answer different questions and are never merged into one table: a
// provider that is available says nothing about whether a run bound it, and a
// run that bound one says nothing about whether this machine can still reach
// it.
import {localize as L} from "./studio-i18n.js";
import {element} from "./command-view.js";
import {quotaSection} from "./studio-quotas.js";
//: The AND-join sentence, from the module that declares it. The Runs screen
//: says it about a step that is not offered and this screen says it about a
//: gate that cannot be answered yet; a second copy here would be a second
//: chance to say one rule two ways about one run. `STREAM_DOWN_REASON` moved
//: there for the same reason when the step control had to say it too: this
//: screen says it about recording an answer, that one about proposing and
//: confirming, and both mean one shut door.
import {ALL_ROADS, STREAM_DOWN_REASON} from "./studio-runwords.js";

// -- closed vocabularies, each a copy of exactly one Python owner ------------
//
// Held equal to their owners by tests/test_studio_runs.py, which reads this
// source and the Python module side by side.

//: contracts.gate_decision -- the four answers a Human may give a gate, and
//: the gate state each one CAUSES. There is no fifth answer and no default:
//: absence stays idle and is never read as a pass.
export const DECISION_ACTIONS = Object.freeze({
  approve: "satisfied",
  reject: "failed",
  request_changes: "changes_requested",
  waive: "waived",
});
//: What each answer means in the user's words, said beside the protocol word
//: and never instead of it.
export const DECISION_MEANINGS = Object.freeze({
  approve: "The work behind this gate is accepted and the plan may go on.",
  reject: "The work behind this gate is refused. The plan does not go on.",
  request_changes: "The work is sent back for changes. Say what must change.",
  waive: "The gate is set aside without judging the work. Say why.",
});
//: The two answers that cannot be given without a reason -- the rule is
//: contracts.DecisionReceipt's own, restated here so the control refuses
//: before the wire does rather than after.
export const REASON_REQUIRED = Object.freeze(["request_changes", "waive"]);
//: graph_projection.GATE_STATES. `idle` is "nobody has answered"; `unknown` is
//: the projection refusing to choose between two standing receipts.
export const GATE_STATES = Object.freeze(
  ["idle", "satisfied", "failed", "changes_requested", "waived", "unknown"]);
//: adapters.provider.AVAILABILITY_STATES -- the four resolved states of the
//: OPERATOR'S MACHINE. `available` is the only spawn-capable one.
export const AVAILABILITY_STATES = Object.freeze(
  ["available", "executable_absent", "unconfigured", "version_mismatch"]);
//: adapters.provider.IMPLEMENTATION_STATES -- the three states of THIS BUILD's
//: transport. A different question from availability, sharing no value with
//: it, so neither can be read as the other.
export const IMPLEMENTATION_STATES = Object.freeze(
  ["fixture_only", "real_experimental", "unproven"]);
//: What each machine state means, in the user's words.
export const AVAILABILITY_MEANINGS = Object.freeze({
  available: "This machine can start it.",
  executable_absent: "The pinned executable is not where the config says.",
  version_mismatch: "The executable is there and is not the pinned version.",
  unconfigured: "No provider configuration names it, so nothing was looked at.",
});
//: adapters.provider.CONTRACT_AUTH_STATES -- which login the operator's own row
//: pinned. A third question, sharing no value with the two above.
export const AUTH_STATES = Object.freeze(
  ["api_key", "subscription", "unpinned"]);
//: What each login state means, in the user's words. Each one says CONFIGURED,
//: because that is all a config file can say.
export const AUTH_MEANINGS = Object.freeze({
  api_key: "Configured to read a credential from the environment.",
  subscription: "Configured to use the vendor's own login, kept in its own directory.",
  unpinned: "No provider configuration names it, so no login was pinned.",
});
//: What each build state means, in the user's words.
export const IMPLEMENTATION_MEANINGS = Object.freeze({
  real_experimental: "This build talks to the real product, experimentally.",
  fixture_only: "This build answers from a fixture and starts nothing.",
  unproven: "This build claims nothing about how it would talk to it.",
});
//: operator_config -- the one file a person writes, and exactly the keys it
//: may carry. Three are required and four are optional; there is nowhere in it
//: for an argv, a cwd, a timeout, a URL or a secret VALUE. `auth_home` is a
//: DIRECTORY the vendor's own login command wrote, never a credential.
export const PROVIDER_CONFIG_FILE = "conductor/providers.json";
export const PROVIDER_CONFIG_REQUIRED = Object.freeze(
  ["executable", "protocol", "provider_id"]);
export const PROVIDER_CONFIG_OPTIONAL = Object.freeze(
  ["auth", "auth_home", "entrypoint", "env_allow"]);
export const PROVIDER_CONFIG_COMMAND = "conduct up";
//: The command that WRITES that file, so nobody has to. It is named before the
//: file below it: the file is what gets written, not what a person has to sit
//: down and compose.
export const PROVIDER_SETUP_COMMAND = "conduct providers";
//: The seven words a screen container may stand in, and the plain sentence
//: each one is said with.
export const PHASE_SENTENCES = Object.freeze({
  empty: "Nothing has been read yet.",
  loading: "Reading.",
  ready: "Read.",
  stale: "Shown from an earlier read; a newer one has not landed.",
  refused: "This read was refused. Nothing below is newer than the refusal.",
  failed: "This read failed. Nothing below is newer than the failure.",
  disconnected: "The live connection is down, so nothing here updates.",
});

const AVAILABILITY_CHANNEL = Object.freeze({
  available: "pass", executable_absent: "fail", version_mismatch: "fail",
  unconfigured: "none",
});
const IMPLEMENTATION_CHANNEL = Object.freeze({
  real_experimental: "wait", fixture_only: "none", unproven: "none",
});
//: Which login a row PINNED. Every state is neutral on purpose: a configured
//: login is not a working one, and a green chip here would say it was.
const AUTH_CHANNEL = Object.freeze({
  api_key: "none", subscription: "none", unpinned: "none",
});
const GATE_CHANNEL = Object.freeze({
  idle: "wait", satisfied: "pass", failed: "fail",
  changes_requested: "wait", waived: "none", unknown: "wait",
});
const CHANNEL_GLYPHS = Object.freeze({
  pass: "✓", wait: "●", fail: "✕", none: "·",
});
//: The id grammar, spelled for an HTML `pattern`. The escaped hyphen is
//: load-bearing: a browser compiles `pattern` with the RegExp `v` flag first,
//: where a bare trailing `-` in a class is a syntax error -- and a pattern that
//: fails to compile is IGNORED, not enforced.
const ID_PATTERN = "[A-Za-z0-9][A-Za-z0-9._\\-]{0,127}";
const ID_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
//: The reason field's ceiling on this surface, the same one the Graph window's
//: decision draft holds. It is a screen limit, not a contract one, and it is
//: written on the label so nobody's sentence is cut off in silence.
const REASON_LIMIT = 200;

const NOT_STATED = "not stated";

function show(value, state = null) {
  const missing = state === null ? NOT_STATED : L(state, "agents.not_stated");
  if (value === null || value === undefined || value === "") return missing;
  if (Array.isArray(value)) return value.length ? value.join(", ") : missing;
  return String(value);
}

function chip(channel, word) {
  const known = CHANNEL_GLYPHS[channel] ? channel : "none";
  return element("span", {className: `studio-chip studio-chip--${known}`}, [
    element("i", {className: "studio-chip__g", text: CHANNEL_GLYPHS[known]}),
    element("span", {text: word}),
  ]);
}

function fact(label, value) {
  return element("p", {className: "studio-fact"}, [
    element("span", {className: "studio-fact__k", text: label}),
    element("span", {className: "studio-fact__v", text: show(value)}),
  ]);
}

function localizedFact(state, key, value) {
  const shown = value === null || value === undefined || value === ""
    || (Array.isArray(value) && !value.length)
    ? L(state, "agents.not_stated") : show(value);
  return fact(L(state, key), shown);
}

function note(value) {
  return element("p", {className: "studio-note", text: value});
}

function protocolWord(value) {
  return element("span", {className: "studio-mono", text: value});
}

function section(title, children) {
  return element("section", {className: "studio-section"},
    [element("h3", {text: title}), ...children]);
}

function unsupported(label, why, state) {
  return element("p", {className: "studio-unsupported"}, [
    element("span", {className: "studio-fact__k", text: label}),
    element("span", {className: "studio-fact__v",
      text: L(state, "agents.not_recorded")}),
    element("span", {className: "studio-why", text: why}),
  ]);
}

function handlerOf(handlers, name) {
  const found = handlers ? handlers[name] : null;
  return typeof found === "function" ? found : null;
}

function banner(phase, state) {
  const word = PHASE_SENTENCES[phase] ? phase : "failed";
  return element("p", {className: `studio-banner studio-banner--${word}`}, [
    element("span", {text: L(state, `phase.${word}`)}), " ", protocolWord(word),
  ]);
}

function rows(value) { return Array.isArray(value) ? value : []; }

function object(value) {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value : null;
}

//: A control whose handler was not wired is DISABLED and says why. It never
//: disappears: a button that vanishes teaches a user the product cannot do the
//: thing, when what happened is that this screen was mounted without its wire.
function actionButton(handlers, name, label, argument, state) {
  const call = handlerOf(handlers, name);
  const button = element("button", {
    "data-focus-key": `action:${name}`, text: label, type: "button",
  });
  if (call === null) {
    button.disabled = true;
    button.title = L(state, "agents.handler_missing", {name});
    return button;
  }
  button.addEventListener("click", () => call(argument));
  return button;
}

function focusKey(mount) {
  const active = document.activeElement;
  if (!active || active === document.body) return null;
  if (!mount.contains(active) || !active.getAttribute) return null;
  return active.getAttribute("data-focus-key");
}

function restoreFocus(mount, key) {
  if (!key) return;
  const successor = mount.querySelector(`[data-focus-key="${key}"]`);
  if (successor) successor.focus();
}

// -- Decisions ----------------------------------------------------------------

function decisionKey(row) {
  return `${show(row.run_id)}/${show(row.gate_id)}`;
}

//: Which row the draft is addressing, as the raw string the reducer holds or
//: null. Never through `show`: an absent key would become the words "not
//: stated" and could then MATCH a row whose run and gate are both absent.
function draftKey(draft) {
  return typeof draft.key === "string" ? draft.key : null;
}

//: Why a person is being asked. The run's authority ladder says what may
//: happen without one; the gate says this step asks for one by name.
function whyAsked(row, state) {
  const carried = [note(L(state, "agents.gate_explainer"))];
  // The workflow author's own words about this step, when they wrote any. It
  // is stated as theirs rather than as this build's: everything else on this
  // screen is a fact the product derived, and an unattributed sentence beside
  // those would read as one more of them.
  if (typeof row.purpose === "string" && row.purpose) {
    carried.push(localizedFact(state, "agents.workflow_says", row.purpose));
  }
  if (typeof row.mode === "string") {
    carried.push(localizedFact(state, "agents.authority", row.mode));
  }
  return carried;
}

//: Where this answer sends the run, off the server's own schedule.
//
// The condition is shown when the road carries one, because otherwise this
// section overstates itself: a road reading `on_approved` becomes runnable when
// this gate is APPROVED and is closed by every other answer, and a person
// deciding is entitled to know which of the four they are being asked for.
// A road carrying none opens on any decided answer, and says nothing extra.
function whatItUnblocks(row, state) {
  const next = rows(row.unblocks);
  if (!next.length) {
    return note(L(state, "agents.unblocks_unknown"));
  }
  return element("ul", {className: "studio-unblocks"},
    next.map((step) => element("li", {}, [
      element("span", {text: show(step.title, state)}), " ",
      protocolWord(show(step.node_id)),
      ...(typeof step.condition === "string"
        ? [" ", protocolWord(L(state, "agents.opens_on", {condition: step.condition}))] : []),
    ])));
}

function receiptBlock(receipt, state) {
  return section(L(state, "agents.receipt_title"), [
    note(L(state, "agents.immutable")),
    localizedFact(state, "agents.receipt", receipt.receipt_id),
    localizedFact(state, "agents.answer", receipt.action),
    localizedFact(state, "agents.causes", DECISION_ACTIONS[receipt.action]),
    localizedFact(state, "agents.actor", receipt.actor),
    localizedFact(state, "agents.decided_at", receipt.decided_at),
    localizedFact(state, "agents.reason", receipt.reason),
    localizedFact(state, "agents.supersedes", receipt.supersedes),
    localizedFact(state, "agents.configuration", receipt.config_digest),
  ]);
}

function decisionButton(row, draft, handlers, state) {
  const key = decisionKey(row);
  const button = element("button", {
    "aria-pressed": key === draftKey(draft) ? "true" : "false",
    className: "studio-decision", "data-focus-key": `decision:${key}`,
    type: "button",
  }, [element("span", {className: "studio-decision__t", text: show(row.title, state)}), " ",
    element("span", {className: "studio-mono studio-decision__id", text: key}), " ",
    chip(GATE_CHANNEL[row.decision] || "none", L(state, "agents.gate_state", {decision: show(row.decision, state)}))]);
  const select = handlerOf(handlers, "selectDecision");
  if (select === null) {
    button.disabled = true;
    button.title = L(state, "agents.handler_missing", {name: "selectDecision"});
  } else button.addEventListener("click", () => select(key));
  return button;
}

//: What stops this draft being submitted, in the user's words, or null. The
//: rules are the receipt contract's own, asked here first so a control refuses
//: before the wire does rather than after.
function whyNotSubmittable(draft, state) {
  // Judged on the RAW draft values. `show` is a display function and turns an
  // absent value into the words "not stated", which every one of these tests
  // would then read as a filled-in answer.
  const action = draft.action;
  const actor = typeof draft.actor === "string" ? draft.actor : "";
  const reason = typeof draft.reason === "string" ? draft.reason : "";
  if (typeof action !== "string"
      || !Object.prototype.hasOwnProperty.call(DECISION_ACTIONS, action)) {
    return L(state, "agents.choose_answer");
  }
  if (!ID_RE.test(actor)) {
    return L(state, "agents.actor_hint");
  }
  if (REASON_REQUIRED.includes(action) && !reason.trim()) {
    return L(state, "agents.reason_required", {action});
  }
  return null;
}

function choiceControl(action, draft, edit, state) {
  const control = element("input", {
    "data-focus-key": `choice:${action}`, name: "decision-action",
    type: "radio", value: action,
  });
  control.checked = draft.action === action;
  if (edit === null) control.disabled = true;
  else control.addEventListener("change", () => edit({action}));
  return element("label", {className: "studio-choice"}, [
    control,
    element("span", {className: "studio-choice__a", text: action}), " ",
    element("span", {className: "studio-choice__m",
      text: L(state, `agents.decision_${action}`)}), " ",
    element("span", {className: "studio-choice__c",
      text: L(state, "agents.causes_state", {decision: DECISION_ACTIONS[action]})}),
  ]);
}

function textControl(name, key, draft, edit, label, attributes) {
  const control = element("input", Object.assign({
    autocomplete: "off", "data-focus-key": `field:${name}`, name,
    spellcheck: "false", type: "text",
  }, attributes));
  control.value = draft[key] === undefined || draft[key] === null
    ? "" : String(draft[key]);
  if (edit === null) control.disabled = true;
  else {
    control.addEventListener("change", () => {
      edit({[key]: control.value});
    });
  }
  return element("label", {className: "studio-field"}, [
    element("span", {text: label}), control,
  ]);
}

//: What an answer on a gate that already HAS one does, said before the
//: controls because it changes what pressing them means.
//
// A receipt still standing means one of two things and both are the same act:
// a loop sent the work back around, or the person is taking back what they
// just said. Either way this answer REPLACES that one rather than standing
// beside it, and it is posted as `supersedes` -- which is what keeps the gate
// readable instead of `unknown`. Spelled as a list so the form appends it the
// way it appends every other optional note.
function reopenedNote(row, state) {
  if (typeof row.standing !== "string") return [];
  return [note(L(state, "agents.reopened", {receipt: row.standing}))];
}

//: The four answers, minus the one this gate's plan refuses, plus what each
//: means and what a second answer would replace.
//
// A gate whose plan demands explicit human approval is not offered the one
// answer that would set it aside. Offering it and refusing the save would
// teach a person the product is broken; the plan said this before the run
// opened, so the screen says it here.
function answerChoices(row, draft, edit, state) {
  const choices = element("fieldset", {className: "studio-choices"},
    [element("legend", {text: L(state, "agents.answer_choices")})]);
  const demanded = typeof row.success_requires === "string";
  for (const action of Object.keys(DECISION_ACTIONS)) {
    if (demanded && action === "waive") continue;
    choices.append(choiceControl(action, draft, edit, state));
  }
  if (demanded) {
    choices.append(note(L(state, "agents.approval_required")));
  }
  for (const said of reopenedNote(row, state)) choices.append(said);
  return choices;
}

function decisionForm(row, draft, handlers, live, state) {
  const edit = handlerOf(handlers, "editDecision");
  const submit = handlerOf(handlers, "submitDecision");
  const form = element("form", {className: "studio-decide"});
  form.append(answerChoices(row, draft, edit, state),
    textControl("actor", "actor", draft, edit, L(state, "agents.actor"),
      {maxlength: "128", pattern: ID_PATTERN, required: ""}),
    textControl("reason", "reason", draft, edit,
      L(state, "agents.reason_limit", {limit: String(REASON_LIMIT)}),
      {maxlength: String(REASON_LIMIT)}));
  const stops = whyNotSubmittable(draft, state);
  const button = element("button", {
    "data-focus-key": "action:submitDecision",
    text: L(state, "agents.record_decision"), type: "submit",
  });
  button.disabled = stops !== null || submit === null || !live;
  if (!live) button.title = L(state, "agents.stream_down");
  form.append(button);
  // The dropped stream is said first: it is the one reason of the three that
  // no amount of typing here answers.
  if (!live) form.append(note(L(state, "agents.stream_down")));
  if (stops !== null) form.append(note(stops));
  if (submit === null) {
    form.append(note(L(state, "agents.submit_missing")));
  } else {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      if (whyNotSubmittable(draft, state) === null) submit(row);
    });
  }
  if (edit === null) {
    form.append(note(L(state, "agents.edit_missing")));
  }
  return form;
}

//: Whether this gate may be answered NOW: the write door's own verdict, read
//: off the run read rather than spelled again on this side of the wire.
//
// A run that has ENDED offers nothing at all, whatever any gate says: the
// write door refuses every record once a terminal stands. A gate whose
// recorded answers contradict each other is offered nothing either -- there is
// no current answer to replace and a receipt replacing none would be a third.
// Everything else is `answerable`, the door's own word served on the schedule
// row: `first` for an arrived gate nothing stands on, `supersede` where the
// standing answer may be replaced -- this lap's correction, or a reopened lap
// the plan has reached again -- and `none` where the door would refuse.
//
// This window used to spell the door's arms for itself and say "a receipt
// stands, so it may be replaced". The door says more: replacing lap one's
// approval on a gate that lap two has not carried the run to is not a
// correction, and it refused every form this screen offered there. One rule,
// living in one place, cannot drift from itself.
//
// It never reads the word `runnable`, and a source guard holds it to that. A
// halt rewrites every runnable row to blocked so nothing further is offered as
// WORK, and a decision is not work -- so a screen reading `runnable` explained
// a gate whose roads were all open by saying its roads had not opened.
function offersAnAnswer(row) {
  return row.ended !== true && row.decision !== "unknown"
    && (row.answerable === "first" || row.answerable === "supersede");
}

//: Why this gate is offering nothing, in the user's words. Five situations,
//: five sentences, and they are nothing alike -- one ends when the steps in
//: front of it finish, one never ends at all, and one has already ended.
function whyNotYet(row, state) {
  if (row.ended === true) {
    return note(L(state, "agents.ended", {plan: show(row.plan_word, state)}));
  }
  if (row.decision === "unknown") {
    return note(L(state, "agents.contradiction"));
  }
  if (row.state === null) {
    return note(L(state, "agents.schedule_missing"));
  }
  const waiting = rows(row.blocked_by).join(", ");
  if (waiting) {
    return note(L(state, "agents.waiting", {waiting}));
  }
  const closed = rows(row.closed_by).join(", ");
  if (closed) {
    return note(L(state, "agents.closed", {closed}));
  }
  if (row.reachable) {
    return note(L(state, "agents.halted"));
  }
  return note(L(state, "agents.unreachable"));
}

function decisionDetail(row, draft, handlers, live, state) {
  const receipt = object(row.receipt);
  const body = [
    element("h3", {text: show(row.title, state)}),
    localizedFact(state, "agents.step", row.node_id), localizedFact(state, "agents.gate", row.gate_id),
    localizedFact(state, "agents.run", row.run_id),
    chip(GATE_CHANNEL[row.decision] || "none", L(state, "agents.gate_state", {decision: show(row.decision, state)})),
    ...whyAsked(row, state),
    section(L(state, "agents.unblocks"),
      [whatItUnblocks(row, state)]),
  ];
  if (offersAnAnswer(row)) {
    body.push(decisionForm(row, draft, handlers, live, state));
  } else {
    body.push(whyNotYet(row, state));
  }
  if (receipt !== null) body.push(receiptBlock(receipt, state));
  else if (row.decision !== "idle") {
    body.push(note(L(state, "agents.receipt_missing")));
  }
  return element("div", {className: "studio-decisions__detail",
    "data-subject": `decision:${decisionKey(row)}`}, body);
}

function decisionList(decisions, draft, handlers, state) {
  const list = rows(decisions.list);
  const body = [banner(decisions.phase, state)];
  if (!list.length) {
    body.push(note(L(state, "agents.no_decisions")));
    return element("nav", {className: "studio-decisions__list",
      "aria-label": L(state, "agents.decisions")}, body);
  }
  const items = element("ul", {className: "studio-decisions__rows"});
  for (const row of list) {
    items.append(element("li", {}, [decisionButton(row, draft, handlers, state)]));
  }
  body.push(items);
  return element("nav", {className: "studio-decisions__list",
    "aria-label": L(state, "agents.decisions")}, body);
}

/**
 * Draw the Decisions screen: what is waiting for a person, and what answering
 * it causes.
 *
 * Safe to call repeatedly with the same state: the whole subtree is replaced
 * each pass and focus intent is carried across it.
 *
 * @param {Element} mount The screen container this module owns entirely.
 * @param {object} state The reducer's frozen value.
 * @param {object} handlers Callbacks this module invokes and never defines:
 *   `selectDecision(key)`, `editDecision(patch)`, `submitDecision(row)`.
 */
export function mountDecisions(mount, state, handlers) {
  const key = focusKey(mount);
  const whole = object(state) || {};
  const decisions = object(whole.decisions) || {};
  const draft = object(decisions.draft) || {};
  // The same question the write door itself asks, spelled the same way: an
  // OPEN stream, and nothing about a workflow. Anything else -- connecting,
  // closed, or a value this build does not know -- is not open, so the control
  // is shut and says why.
  const live = whole.connection === "open";
  const chosen = rows(decisions.list)
    .find((row) => decisionKey(row) === draftKey(draft)) || null;
  mount.replaceChildren(element("div", {className: "studio-decisions"}, [
    element("p", {className: "studio-lede", text:
      L(state, "agents.decisions_lede")}),
    decisionList(decisions, draft, handlers, state),
    chosen === null
      ? element("div", {className: "studio-decisions__detail"},
        [note(L(state, "agents.choose_gate"))])
      : decisionDetail(chosen, draft, handlers, live, state),
  ]));
  restoreFocus(mount, key);
}

// -- Agents -------------------------------------------------------------------

//: The empty roster is a first-class STATE, not an error: nobody has written a
//: provider configuration yet. It says the exact file, the exact keys, and the
//: exact command -- because "no participant" is only actionable if the next
//: action is spelled out.
function noProviders(handlers, state) {
  return section(L(state, "agents.no_provider"), [
    note(L(state, "agents.no_provider_explainer")),
    localizedFact(state, "agents.run_command", PROVIDER_SETUP_COMMAND),
    note(L(state, "agents.setup_explainer")),
    localizedFact(state, "agents.writes", PROVIDER_CONFIG_FILE),
    localizedFact(state, "agents.required_fields", PROVIDER_CONFIG_REQUIRED),
    localizedFact(state, "agents.optional_fields", PROVIDER_CONFIG_OPTIONAL),
    localizedFact(state, "agents.restart", PROVIDER_CONFIG_COMMAND),
    actionButton(handlers, "refreshAgents", L(state, "primary.agents"), null, state),
  ]);
}

function providerRow(row, state) {
  const availability = show(row.availability);
  const implementation = show(row.implementation);
  const auth = show(row.auth);
  // The name, the id and each fact with its meaning read apart, on screen and in the text a
  // reader is given: adjacent spans with no space between them run together (as on Decisions).
  return element("li", {className: "studio-provider"}, [
    element("span", {className: "studio-provider__n",
      text: show(row.display_name, state)}), " ",
    protocolWord(show(row.provider_id)), " ",
    chip(AVAILABILITY_CHANNEL[availability] || "none", availability), " ",
    element("span", {className: "studio-why",
      text: Object.hasOwn(AVAILABILITY_MEANINGS, availability)
        ? L(state, `agents.availability_${availability}`) : L(state, "agents.availability_unknown")}), " ",
    chip(IMPLEMENTATION_CHANNEL[implementation] || "none", implementation), " ",
    element("span", {className: "studio-why",
      text: Object.hasOwn(IMPLEMENTATION_MEANINGS, implementation)
        ? L(state, `agents.implementation_${implementation}`) : L(state, "agents.implementation_unknown")}), " ",
    chip(AUTH_CHANNEL[auth] || "none", auth), " ",
    element("span", {className: "studio-why",
      text: Object.hasOwn(AUTH_MEANINGS, auth)
        ? L(state, `agents.auth_${auth}`) : L(state, "agents.auth_unknown")}),
    localizedFact(state, "agents.proven_controls", row.controls),
  ]);
}

function providerSection(providers, handlers, state) {
  if (!providers.length) return noProviders(handlers, state);
  const list = element("ul", {className: "studio-providers"},
    providers.map((row) => providerRow(row, state)));
  return section(L(state, "agents.harnesses"), [
    note(L(state, "agents.provider_explainer")),
    list,
    actionButton(handlers, "refreshAgents", L(state, "primary.agents"), null, state),
  ]);
}

//: One participant: a binding a run FROZE. The provider roster is joined to it
//: by identity so a reader can see that a binding this run holds is one this
//: machine can no longer reach -- the one reading the two arrays exist for.
function participantRow(row, roster, state) {
  const providerId = show(row.provider_id || row.adapter_id);
  const known = roster.get(providerId) || null;
  const item = element("li", {className: "studio-participant"}, [
    element("span", {className: "studio-participant__i",
      text: show(row.instance_id)}),
    localizedFact(state, "agents.provider", providerId),
    localizedFact(state, "agents.model", Object.prototype.hasOwnProperty.call(row, "model")
      ? row.model : null),
  ]);
  if (!Object.prototype.hasOwnProperty.call(row, "model") || row.model === null) {
    item.append(note(L(state, "agents.model_unpinned")));
  }
  item.append(localizedFact(state, "agents.binding_controls", row.controls));
  if (row.run_id !== undefined) item.append(localizedFact(state, "agents.bound_run", row.run_id));
  if (known === null) {
    item.append(note(L(state, "agents.provider_unknown")));
  } else {
    item.append(chip(AVAILABILITY_CHANNEL[known.availability] || "none",
      L(state, "agents.machine_state", {availability: show(known.availability, state)})));
  }
  if (Array.isArray(row.role_ids)) {
    item.append(localizedFact(state, "agents.roles", row.role_ids));
  } else {
    item.append(unsupported(L(state, "agents.roles"),
      L(state, "agents.roles_unknown"), state));
  }
  return item;
}

function participantSection(agents, roster, state) {
  const participants = rows(agents.participants);
  if (!participants.length) {
    return section(L(state, "agents.participants"), [
      note(L(state, "agents.no_participants")),
    ]);
  }
  return section(L(state, "agents.participants"), [
    note(L(state, "agents.participant_explainer")),
    element("ul", {className: "studio-participants"},
      participants.map((row) => participantRow(row, roster, state))),
  ]);
}

/**
 * Draw the Agents screen: who can carry work on this machine, and who a run
 * actually bound.
 *
 * Safe to call repeatedly with the same state: the whole subtree is replaced
 * each pass and focus intent is carried across it.
 *
 * @param {Element} mount The screen container this module owns entirely.
 * @param {object} state The reducer's frozen value.
 * @param {object} handlers Callbacks this module invokes and never defines:
 *   `refreshAgents()`.
 */
export function mountAgents(mount, state, handlers) {
  const key = focusKey(mount);
  const whole = object(state) || {};
  const agents = object(whole.agents) || {};
  const providers = rows(whole.providers);
  const roster = new Map(providers.map((row) => [row.provider_id, row]));
  // The screen's heading is the one `studio.html` draws; this module draws no second.
  mount.replaceChildren(element("div", {className: "studio-agents"}, [
    element("p", {className: "studio-lede", text:
      L(state, "agents.agents_lede")}),
    banner(agents.phase, state),
    quotaSection(state.quotas, handlers, state),
    providerSection(providers, handlers, state),
    participantSection(agents, roster, state),
  ]));
  restoreFocus(mount, key);
}
