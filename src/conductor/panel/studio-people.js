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
import {element} from "./command-view.js";

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
//: What each build state means, in the user's words.
export const IMPLEMENTATION_MEANINGS = Object.freeze({
  real_experimental: "This build talks to the real product, experimentally.",
  fixture_only: "This build answers from a fixture and starts nothing.",
  unproven: "This build claims nothing about how it would talk to it.",
});
//: operator_config -- the one file a person writes, and exactly the keys it
//: may carry. Three are required and two are optional; there is nowhere in it
//: for an argv, a cwd, a timeout, a URL or a secret VALUE.
export const PROVIDER_CONFIG_FILE = "conductor/providers.json";
export const PROVIDER_CONFIG_REQUIRED = Object.freeze(
  ["executable", "protocol", "provider_id"]);
export const PROVIDER_CONFIG_OPTIONAL = Object.freeze(
  ["entrypoint", "env_allow"]);
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
//: Why the one write control on this screen is shut while the socket is down.
//: A decision write is gated on the STREAM being open -- not on any workflow's
//: readiness, because a decision is not about a workflow -- so a control that
//: stayed pressable while it is down would invite a press the door has already
//: decided to refuse, which is the two workflow write controls' behaviour and
//: not this one's. The reason is SAID here rather than left to a grey button:
//: a control that greys with no sentence teaches a person that the product
//: cannot do the thing, when what happened is that the line went down.
const STREAM_DOWN_REASON = "The live connection is down, so nothing can be "
  + "recorded until it is back. What you have typed here is kept.";

const NOT_STATED = "not stated";

function show(value) {
  if (value === null || value === undefined || value === "") return NOT_STATED;
  if (Array.isArray(value)) return value.length ? value.join(", ") : NOT_STATED;
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

function unsupported(label, why) {
  return element("p", {className: "studio-unsupported"}, [
    element("span", {className: "studio-fact__k", text: label}),
    element("span", {className: "studio-fact__v",
      text: "not recorded by this build"}),
    element("span", {className: "studio-why", text: why}),
  ]);
}

function handlerOf(handlers, name) {
  const found = handlers ? handlers[name] : null;
  return typeof found === "function" ? found : null;
}

function banner(phase) {
  const word = PHASE_SENTENCES[phase] ? phase : "failed";
  return element("p", {className: `studio-banner studio-banner--${word}`}, [
    element("span", {text: PHASE_SENTENCES[word]}), " ", protocolWord(word),
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
function actionButton(handlers, name, label, argument) {
  const call = handlerOf(handlers, name);
  const button = element("button", {
    "data-focus-key": `action:${name}`, text: label, type: "button",
  });
  if (call === null) {
    button.disabled = true;
    button.title = `This screen was mounted without a ${name} handler.`;
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
function whyAsked(row) {
  const carried = [note("A gate is a step the plan itself marks as needing a "
    + "person's answer. Nothing behind it is carried out until one is "
    + "recorded, and no amount of waiting changes that.")];
  // The workflow author's own words about this step, when they wrote any. It
  // is stated as theirs rather than as this build's: everything else on this
  // screen is a fact the product derived, and an unattributed sentence beside
  // those would read as one more of them.
  if (typeof row.purpose === "string" && row.purpose) {
    carried.push(fact("The workflow says", row.purpose));
  }
  if (typeof row.mode === "string") {
    carried.push(fact("This run's authority", row.mode));
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
function whatItUnblocks(row) {
  const next = rows(row.unblocks);
  if (!next.length) {
    return note("What becomes runnable is read off the plan's edges. This view "
      + "was not given them for this gate, so nothing here claims to know.");
  }
  return element("ul", {className: "studio-unblocks"},
    next.map((step) => element("li", {}, [
      element("span", {text: show(step.title)}),
      protocolWord(show(step.node_id)),
      ...(typeof step.condition === "string"
        ? [protocolWord(`opens on ${step.condition}`)] : []),
    ])));
}

function receiptBlock(receipt) {
  return section("The receipt this decision wrote", [
    note("A decision is immutable. It is corrected only by a later receipt "
      + "that supersedes it, and both stay in the journal."),
    fact("Receipt", receipt.receipt_id),
    fact("Answer", receipt.action),
    fact("Causes the gate to become", DECISION_ACTIONS[receipt.action]),
    fact("Decided by", receipt.actor),
    fact("Decided at", receipt.decided_at),
    fact("Reason", receipt.reason),
    fact("Supersedes", receipt.supersedes),
    fact("Against configuration", receipt.config_digest),
  ]);
}

function decisionButton(row, draft, handlers) {
  const key = decisionKey(row);
  const button = element("button", {
    "aria-pressed": key === draftKey(draft) ? "true" : "false",
    className: "studio-decision", "data-focus-key": `decision:${key}`,
    type: "button",
  }, [element("span", {className: "studio-decision__t", text: show(row.title)}),
    protocolWord(key),
    chip(GATE_CHANNEL[row.decision] || "none", `gate ${show(row.decision)}`)]);
  const select = handlerOf(handlers, "selectDecision");
  if (select === null) {
    button.disabled = true;
    button.title = "This screen was mounted without a selectDecision handler.";
  } else button.addEventListener("click", () => select(key));
  return button;
}

//: What stops this draft being submitted, in the user's words, or null. The
//: rules are the receipt contract's own, asked here first so a control refuses
//: before the wire does rather than after.
function whyNotSubmittable(draft) {
  // Judged on the RAW draft values. `show` is a display function and turns an
  // absent value into the words "not stated", which every one of these tests
  // would then read as a filled-in answer.
  const action = draft.action;
  const actor = typeof draft.actor === "string" ? draft.actor : "";
  const reason = typeof draft.reason === "string" ? draft.reason : "";
  if (typeof action !== "string"
      || !Object.prototype.hasOwnProperty.call(DECISION_ACTIONS, action)) {
    return "Choose one of the four answers.";
  }
  if (!ID_RE.test(actor)) {
    return "Type who is deciding, as a plain id: letters, digits, dot, "
      + "underscore or hyphen, up to 128 characters.";
  }
  if (REASON_REQUIRED.includes(action) && !reason.trim()) {
    return `A reason is required when the answer is ${action}.`;
  }
  return null;
}

function choiceControl(action, draft, edit) {
  const control = element("input", {
    "data-focus-key": `choice:${action}`, name: "decision-action",
    type: "radio", value: action,
  });
  control.checked = draft.action === action;
  if (edit === null) control.disabled = true;
  else control.addEventListener("change", () => edit({action}));
  return element("label", {className: "studio-choice"}, [
    control,
    element("span", {className: "studio-choice__a", text: action}),
    element("span", {className: "studio-choice__m",
      text: DECISION_MEANINGS[action]}),
    element("span", {className: "studio-choice__c",
      text: `causes: ${DECISION_ACTIONS[action]}`}),
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

function decisionForm(row, draft, handlers, live) {
  const edit = handlerOf(handlers, "editDecision");
  const submit = handlerOf(handlers, "submitDecision");
  const form = element("form", {className: "studio-decide"});
  const choices = element("fieldset", {className: "studio-choices"},
    [element("legend", {text: "Your answer, and what each one causes"})]);
  for (const action of Object.keys(DECISION_ACTIONS)) {
    choices.append(choiceControl(action, draft, edit));
  }
  form.append(choices,
    textControl("actor", "actor", draft, edit, "Decided by",
      {maxlength: "128", pattern: ID_PATTERN, required: ""}),
    textControl("reason", "reason", draft, edit,
      `Reason (up to ${REASON_LIMIT} characters)`,
      {maxlength: String(REASON_LIMIT)}));
  const stops = whyNotSubmittable(draft);
  const button = element("button", {
    "data-focus-key": "action:submitDecision",
    text: "Record this decision", type: "submit",
  });
  button.disabled = stops !== null || submit === null || !live;
  if (!live) button.title = STREAM_DOWN_REASON;
  form.append(button);
  // The dropped stream is said first: it is the one reason of the three that
  // no amount of typing here answers.
  if (!live) form.append(note(STREAM_DOWN_REASON));
  if (stops !== null) form.append(note(stops));
  if (submit === null) {
    form.append(note("This screen was mounted without a submitDecision "
      + "handler, so nothing here can be recorded."));
  } else {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      if (whyNotSubmittable(draft) === null) submit(row);
    });
  }
  if (edit === null) {
    form.append(note("This screen was mounted without an editDecision "
      + "handler, so these controls cannot take an answer."));
  }
  return form;
}

function decisionDetail(row, draft, handlers, live) {
  const receipt = object(row.receipt);
  const body = [
    element("h3", {text: show(row.title)}),
    fact("The step", row.node_id), fact("The gate", row.gate_id),
    fact("In run", row.run_id),
    chip(GATE_CHANNEL[row.decision] || "none", `gate ${show(row.decision)}`),
    ...whyAsked(row),
    section("What becomes runnable once this is answered",
      [whatItUnblocks(row)]),
  ];
  if (row.decision === "idle") {
    body.push(decisionForm(row, draft, handlers, live));
  } else {
    body.push(note("This gate has been answered. A decision is never edited; "
      + "answering again writes a receipt that supersedes this one."));
  }
  if (receipt !== null) body.push(receiptBlock(receipt));
  else if (row.decision !== "idle") {
    body.push(note("This view was not given the receipt behind that answer. "
      + "It is in the run's journal, on the Runs screen."));
  }
  return element("div", {className: "studio-decisions__detail"}, body);
}

function decisionList(state, draft, handlers) {
  const list = rows(state.list);
  const body = [banner(state.phase)];
  if (!list.length) {
    body.push(note("Nothing is waiting for you. When a run reaches a gate, "
      + "the step and its choices appear here."));
    return element("nav", {className: "studio-decisions__list",
      "aria-label": "Decisions"}, body);
  }
  const items = element("ul", {className: "studio-decisions__rows"});
  for (const row of list) {
    items.append(element("li", {}, [decisionButton(row, draft, handlers)]));
  }
  body.push(items);
  return element("nav", {className: "studio-decisions__list",
    "aria-label": "Decisions"}, body);
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
    element("h2", {text: "Decisions"}),
    element("p", {className: "studio-lede", text:
      "Every answer here becomes an immutable receipt in the run's own "
      + "journal. Nothing is executed by answering; a decision changes what "
      + "the plan is allowed to do next, and nothing else."}),
    decisionList(decisions, draft, handlers),
    chosen === null
      ? element("div", {className: "studio-decisions__detail"},
        [note("Choose a gate on the left to see why it is asking and what "
          + "each answer causes.")])
      : decisionDetail(chosen, draft, handlers, live),
  ]));
  restoreFocus(mount, key);
}

// -- Agents -------------------------------------------------------------------

//: The empty roster is a first-class STATE, not an error: nobody has written a
//: provider configuration yet. It says the exact file, the exact keys, and the
//: exact command -- because "no participant" is only actionable if the next
//: action is spelled out.
function noProviders(handlers) {
  return section("No provider is configured", [
    note("This build resolved no provider, so nothing on this machine can "
      + "carry out a step. That is a configuration this project does not have "
      + "yet, not a failure."),
    fact("Run this", PROVIDER_SETUP_COMMAND),
    note("It asks which harness you have, where it is on this machine, and "
      + "which environment variables it may read — NAMES only. It never asks "
      + "for a credential: a value is read from your environment when a step "
      + "runs and is written down nowhere."),
    fact("It writes", PROVIDER_CONFIG_FILE),
    fact("Each row carries", PROVIDER_CONFIG_REQUIRED),
    fact("And may also carry", PROVIDER_CONFIG_OPTIONAL),
    fact("Then restart with", PROVIDER_CONFIG_COMMAND),
    actionButton(handlers, "refreshAgents", "Read the roster again", null),
  ]);
}

function providerRow(row) {
  const availability = show(row.availability);
  const implementation = show(row.implementation);
  return element("li", {className: "studio-provider"}, [
    element("span", {className: "studio-provider__n",
      text: show(row.display_name)}),
    protocolWord(show(row.provider_id)),
    chip(AVAILABILITY_CHANNEL[availability] || "none", availability),
    element("span", {className: "studio-why",
      text: AVAILABILITY_MEANINGS[availability]
        || "This build does not describe that machine state."}),
    chip(IMPLEMENTATION_CHANNEL[implementation] || "none", implementation),
    element("span", {className: "studio-why",
      text: IMPLEMENTATION_MEANINGS[implementation]
        || "This build does not describe that transport state."}),
    fact("Capabilities it is proven to serve", row.controls),
  ]);
}

function providerSection(providers, handlers) {
  if (!providers.length) return noProviders(handlers);
  const list = element("ul", {className: "studio-providers"},
    providers.map(providerRow));
  return section("Harnesses this build and this machine can reach", [
    note("Two facts per row, and they answer different questions. What the "
      + "MACHINE resolved is whether the pinned executable is there; what the "
      + "BUILD claims is whether this version talks to the real product or "
      + "answers from a fixture. Neither is read off the other."),
    list,
    actionButton(handlers, "refreshAgents", "Read the roster again", null),
  ]);
}

//: One participant: a binding a run FROZE. The provider roster is joined to it
//: by identity so a reader can see that a binding this run holds is one this
//: machine can no longer reach -- the one reading the two arrays exist for.
function participantRow(row, roster) {
  const providerId = show(row.provider_id || row.adapter_id);
  const known = roster.get(providerId) || null;
  const item = element("li", {className: "studio-participant"}, [
    element("span", {className: "studio-participant__i",
      text: show(row.instance_id)}),
    fact("Carried by", providerId),
    fact("Model", Object.prototype.hasOwnProperty.call(row, "model")
      ? row.model : null),
  ]);
  if (!Object.prototype.hasOwnProperty.call(row, "model") || row.model === null) {
    item.append(note("No model was pinned for this instance, so whatever the "
      + "provider's own configuration decides is what runs. That is not a "
      + "default this screen chose."));
  }
  item.append(fact("Capabilities this binding may be asked for", row.controls));
  if (row.run_id !== undefined) item.append(fact("Frozen into run", row.run_id));
  if (known === null) {
    item.append(note("This build's roster carries no provider by that name, "
      + "so nothing here can say whether this machine could still start it."));
  } else {
    item.append(chip(AVAILABILITY_CHANNEL[known.availability] || "none",
      `on this machine: ${show(known.availability)}`));
  }
  if (Array.isArray(row.role_ids)) {
    item.append(fact("Roles it carries", row.role_ids));
  } else {
    item.append(unsupported("Roles it carries",
      "A materialized plan names instances, not roles: the role is a workflow "
      + "document's word and it is not carried into the run's plan."));
  }
  return item;
}

function participantSection(agents, roster) {
  const participants = rows(agents.participants);
  if (!participants.length) {
    return section("Participants", [
      note("No run in view binds anybody yet. A participant exists only "
        + "inside a run: opening one is what binds an instance to a provider "
        + "and freezes it for that run's whole life."),
    ]);
  }
  return section("Participants", [
    note("A participant is one instance a run bound to one provider, frozen "
      + "when the run was opened. It never changes afterwards, which is why "
      + "it can disagree with the roster above."),
    element("ul", {className: "studio-participants"},
      participants.map((row) => participantRow(row, roster))),
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
  mount.replaceChildren(element("div", {className: "studio-agents"}, [
    element("h2", {text: "Agents"}),
    element("p", {className: "studio-lede", text:
      "A workflow names roles. A run binds each role to a participant, and a "
      + "participant names one configured provider and at most one model. "
      + "Nothing in a workflow document may name a provider, a model or a "
      + "run."}),
    banner(agents.phase),
    providerSection(providers, handlers),
    participantSection(agents, roster),
  ]));
  restoreFocus(mount, key);
}
