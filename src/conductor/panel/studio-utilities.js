"use strict";
import {element, field} from "./command-view.js";
import {localize} from "./studio-i18n.js";

const builtin = [
  ["claude-code", "Claude Code"], ["codex", "Codex"], ["grok-build", "Grok Build"], ["kimi-code", "Kimi Code"],
];
const idPattern = /^[a-z0-9][a-z0-9_-]{0,47}$/;
const reserved = /^(con|prn|aux|nul|com[1-9]|lpt[1-9])$/;
const validId = value => typeof value === "string" && idPattern.test(value) && !reserved.test(value);
const fits = value => new TextEncoder().encode(value).length <= 8192;
const modes = ["manual", "stdio-v1"];
const states = ["pending", "claimed", "answered", "unknown"];
const heading = text => element("h3", {text});
function btn(text, act, disabled = false) {
  const button = element("button", {type: "button", text});
  button.disabled = disabled;
  button.addEventListener("click", act);
  return button;
}
function input(tag, value, changed, attrs = {}) {
  const node = element(tag, attrs);
  node.value = value;
  node.addEventListener("input", () => changed(node.value));
  return node;
}
function validRead(data) {
  if (!Array.isArray(data?.utilities) || !Array.isArray(data?.exchanges)) return false;
  const modesById = new Map();
  for (const u of data.utilities) {
    if (!u || !validId(u.utility_id) || typeof u.label !== "string" || !modes.includes(u.mode)
        || modesById.has(u.utility_id)) return false;
    modesById.set(u.utility_id, u.mode);
  }
  return data.exchanges.every(e => e && modesById.has(e.utility_id) && validId(e.exchange_id)
    && typeof e.text === "string" && states.includes(e.state)
    && (e.state === "answered" ? typeof e.reply === "string" : e.reply === null));
}

// Browser fields hold text and ids only. A write belongs to a click, never to a refresh or a mount.
export function utilityDrawer(dialog, door) {
  let projectMode = null, read = null, phase = "ready", selected = "", message = "", writing = false;
  let reading = 0, pending = null, fromRuns = false, renderedState = "", lastConnected = false;
  const attachment = {label: "", id: "", mode: "manual"};
  const drafts = new Map();
  const tr = (key, args) => localize({locale: door.locale()}, "utility." + key, args);
  const writable = () => !writing && door.connected() && projectMode === "active" && phase === "ready" && !!read;
  const tell = (key) => { message = key; const status = dialog.querySelector("[role=status]");
    if (status) status.textContent = key ? tr(key) : ""; };
  function choose(value) { selected = value; message = ""; draw(); }

  async function refresh() {
    const stamp = ++reading;
    phase = "loading"; message = ""; read = null; draw();
    try {
      const identity = await door.project();
      if (stamp !== reading || !dialog.open) return;
      if (!identity || !(identity.project_id === null || /^[a-f0-9]{32}$/.test(identity.project_id))
          || !["view", "active"].includes(identity.mode) || !door.bind(identity.project_id)) {
        throw new Error();
      }
      const data = await door.read();
      if (stamp !== reading || !dialog.open) return;
      if (!validRead(data)) throw new Error();
      projectMode = identity.project_id === null ? "unidentified" : identity.mode;
      read = data; phase = "ready";
      if (pending && confirmed(data, pending)) {
        if (pending.op === "attach") selected = "saved:" + pending.utility_id;
        if (pending.op === "send") drafts.delete("task:" + pending.utility_id);
        if (pending.op === "manual_reply") drafts.delete("reply:" + pending.exchange_id);
        pending = null;
      } else if (pending) {
        message = "write_error";
      }
    } catch (_) {
      if (stamp !== reading || !dialog.open) return;
      phase = "error";
    }
    draw();
  }
  function confirmed(data, cmd) {
    if (cmd.op === "attach") return data.utilities.some(u => u.utility_id === cmd.utility_id
      && u.label === cmd.label && u.mode === cmd.mode);
    const e = data.exchanges.find(x => x.utility_id === cmd.utility_id && x.exchange_id === cmd.exchange_id);
    if (cmd.op === "send") return e && e.text === cmd.text;
    if (cmd.op === "manual_reply") return e?.state === "answered" && e.reply === cmd.text;
    return e?.state === "unknown";
  }
  async function save(cmd) {
    if (!writable()) return;
    writing = true; pending = cmd; message = "pending_write"; draw();
    try { await door.post(cmd); } catch (_) { /* The read below determines what landed. */ }
    writing = false;
    if (dialog.open) await refresh();
  }
  function copy(text) {
    return btn(tr("copy"), async () => {
      try { await door.copy(text); tell("copied"); }
      catch (_) { tell("copy_error"); }
    });
  }
  function builtinSetup(main, id, name) {
    main.append(heading(name), element("h4", {text: tr("setup")}),
      element("p", {text: tr("stopped")}), element("code", {text: "conduct providers --dir ."}),
      element("p", {text: tr("provider", {id})}));
    if (id === "kimi-code") main.append(element("p", {text: tr("kimi")}));
  }
  function connect(main) {
    main.append(heading(tr("custom")));
    const form = element("form", {className: "utility-form"});
    const name = input("input", attachment.label, value => { attachment.label = value; }, {maxlength: "80", required: ""});
    const id = input("input", attachment.id, value => { attachment.id = value; },
      {maxlength: "48", required: "", placeholder: "my-cli"});
    const mode = element("select", {"aria-label": tr("mode")});
    for (const k of modes) mode.append(element("option", {value: k, text: tr(k === "manual" ? "manual" : "protocol")}));
    mode.value = attachment.mode;
    mode.addEventListener("change", () => { attachment.mode = mode.value; });
    const add = element("button", {type: "submit", text: tr("attach")});
    add.disabled = !writable();
    form.append(field(tr("name"), name), field(tr("id"), id), field(tr("mode"), mode), add);
    form.addEventListener("submit", event => {
      event.preventDefault();
      if (!validId(attachment.id) || !attachment.label.trim()) { tell("invalid"); return; }
      save({op: "attach", utility_id: attachment.id, label: attachment.label.trim(), mode: attachment.mode});
    });
    main.append(form);
  }
  function exchange(main, u, e) {
    const card = element("article", {className: "utility-exchange"});
    card.append(element("small", {text: tr(e.state)}), element("pre", {text: e.text}), copy(e.text));
    if (e.state === "answered") card.append(element("h4", {text: tr("external")}), element("pre", {text: e.reply}));
    if (u.mode === "manual" && e.state === "pending") {
      const key = "reply:" + e.exchange_id;
      const area = input("textarea", drafts.get(key) || "", value => drafts.set(key, value), {rows: "3"});
      card.append(field(tr("reply"), area), btn(tr("save"), () => {
        if (!area.value.trim()) { area.focus(); return; }
        if (!fits(area.value)) { tell("too_long"); return; }
        save({op: "manual_reply", utility_id: u.utility_id, exchange_id: e.exchange_id, text: area.value});
      }, !writable()));
    }
    if (u.mode === "stdio-v1" && e.state === "claimed") card.append(btn(tr("unknown_action"),
      () => save({op: "mark_unknown", utility_id: u.utility_id, exchange_id: e.exchange_id}), !writable()));
    main.append(card);
  }
  function utility(main, u) {
    main.append(heading(u.label), element("small", {text: tr(u.mode === "manual" ? "manual" : "protocol")}),
      element("p", {text: tr(u.mode === "manual" ? "manual_info" : "protocol_info")}));
    if (u.mode === "stdio-v1") {
      const command = "conduct utility-bridge --server " + door.origin + " --utility " + u.utility_id;
      main.append(element("code", {text: command}), copy(command));
    }
    const key = "task:" + u.utility_id;
    const area = input("textarea", drafts.get(key) || "", value => drafts.set(key, value), {rows: "3"});
    main.append(field(tr("draft"), area));
    if (fromRuns && door.question().trim()) main.append(btn(tr("atlas"), () => {
      area.value = door.question(); drafts.set(key, area.value); area.focus();
    }));
    main.append(btn(tr("send"), () => {
      if (!area.value.trim()) { area.focus(); return; }
      if (!fits(area.value)) { tell("too_long"); return; }
      const prior = pending?.op === "send" && pending.utility_id === u.utility_id && pending.text === area.value;
      save({op: "send", utility_id: u.utility_id, exchange_id: prior ? pending.exchange_id : door.newId(), text: area.value});
    }, !writable()));
    const rows = read.exchanges.filter(e => e.utility_id === u.utility_id);
    if (rows.length) main.append(heading(tr("history")));
    for (const e of rows.reverse()) exchange(main, u, e);
  }
  function draw() {
    if (!dialog.open) return;
    const nav = element("nav", {className: "utility-options", "aria-label": tr("title")});
    const main = element("section", {className: "utility-workspace"});
    function option(key, label) {
      const b = btn(label, () => choose(key));
      b.setAttribute("aria-pressed", String(key === selected)); nav.append(b);
    }
    nav.append(element("h3", {text: tr("builtin")}));
    for (const [id, label] of builtin) option(id, label);
    nav.append(element("h3", {text: tr("connected")})); option("custom", tr("custom"));
    for (const u of read?.utilities || []) option("saved:" + u.utility_id, u.label);
    const native = builtin.find(([id]) => id === selected);
    const saved = read?.utilities.find(u => selected === "saved:" + u.utility_id);
    if (native) builtinSetup(main, ...native);
    else if (selected === "custom") connect(main);
    else if (saved) utility(main, saved);
    else if (phase === "ready") main.append(element("p", {text: tr("empty")}));
    if (phase !== "ready") main.prepend(element("p", {text: tr(phase)}));
    const info = !door.connected() ? "offline" : projectMode === "unidentified" ? "unidentified"
      : projectMode === "view" ? "view" : null;
    const top = element("header", {className: "utility-heading"}, [
      element("h2", {id: "utilitiesTitle", text: tr("title")}),
      btn(tr("close"), () => dialog.close()),
    ]);
    if (info) main.prepend(element("small", {className: "utility-mode", text: tr(info)}));
    dialog.replaceChildren(top, element("div", {className: "utility-layout"}, [nav, main]),
      element("footer", {}, [element("span", {role: "status", text: message ? tr(message) : ""}),
        btn(tr("refresh"), refresh, writing || phase === "loading")]));
    lastConnected = door.connected();
    renderedState = door.locale() + "|" + lastConnected;
  }
  dialog.addEventListener("close", () => { reading += 1; phase = "ready"; read = null; });
  return {
    open(runs, id = null) {
      fromRuns = runs;
      if (id !== null && validId(id)) selected = "saved:" + id;
      dialog.showModal(); refresh();
    },
    sync() {
      if (!dialog.open) return;
      if (door.connected() && !lastConnected) { refresh(); return; }
      if (renderedState !== door.locale() + "|" + door.connected()) draw();
    },
  };
}
