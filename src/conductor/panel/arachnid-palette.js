"use strict";
import {element} from "./command-view.js";
import {word} from "./arachnid-copy.js";

const groups = [
  ["paletteSessions", ["session"]], ["paletteHarnesses", ["harness", "utility"]],
  ["paletteSteps", ["step"]], ["paletteWorkspace", ["limits", "memory"]],
];
const key = row => JSON.stringify([row.kind, row.scope, row.id]);
const normalize = text => String(text ?? "").toLowerCase().replaceAll("ё", "е").trim();

function matches(row, words) {
  const aliases = Array.isArray(row.keywords) ? row.keywords : [row.keywords];
  const text = normalize([row.label, row.detail, row.id, ...aliases].join(" "));
  return words.every(needle => text.includes(needle));
}
function rank(row, query) {
  if (query && normalize(row.label) === query) return 0;
  if (query && normalize(row.id) === query) return 1;
  return 2;
}
function caret(node) {
  if (!node || node.tagName !== "INPUT" && node.tagName !== "TEXTAREA") return null;
  return node.selectionStart === null ? null :
    [node.selectionStart, node.selectionEnd, node.selectionDirection];
}

// Navigation only. The caller supplies the current project projection and confirms the exact key.
export function attachPalette(dialog, door) {
  const doc = dialog.ownerDocument, events = door.stop(), options = {signal: events.signal};
  const input = dialog.querySelector("#paletteInput");
  const results = dialog.querySelector("#paletteResults");
  const empty = dialog.querySelector("#paletteEmpty");
  const closeButton = dialog.querySelector("#paletteClose");
  let origin = null, selection = null, active = null, rendered = [], signature = null;

  function highlight(index, scroll = false) {
    for (const [i, item] of rendered.entries()) {
      item.button.setAttribute("aria-selected", String(i === index));
    }
    const item = rendered[index];
    active = item?.key || null;
    if (!item) { input.removeAttribute("aria-activedescendant"); return; }
    empty.hidden = true;
    input.setAttribute("aria-activedescendant", item.button.id);
    if (scroll) item.button.scrollIntoView({block: "nearest"});
  }

  function paint(reset = false, refused = false) {
    if (!dialog.open) return;
    const previous = active, query = normalize(input.value);
    const terms = query.split(/\s+/).filter(Boolean);
    const catalog = door.catalog().filter(row => matches(row, terms));
    const next = JSON.stringify([door.locale(), terms,
      catalog.map(row => [key(row), row.label, row.detail])]);
    if (!reset && !refused && signature === next) return;
    signature = next;
    const parts = doc.createDocumentFragment();
    rendered = [];
    // Keep each group together and put the group with the best match first.
    const compare = (a, b) => rank(a, query) - rank(b, query);
    const sections = groups.map(([label, kinds]) =>
      [label, catalog.filter(row => kinds.includes(row.kind)).sort(compare)])
      .filter(([, entries]) => entries.length)
      .sort((a, b) => compare(a[1][0], b[1][0]));
    for (const [label, entries] of sections) {
      const name = word(door.locale(), label);
      const group = element("div", {role: "group", "aria-label": name, className: "palette-group"});
      group.append(element("div", {className: "palette-group-label", "aria-hidden": "true",
        text: name}));
      for (const row of entries) {
        const index = rendered.length;
        const option = element("div", {role: "option", className: "palette-option",
          id: dialog.id + "-option-" + index, "data-palette-kind": row.kind},
          [element("span", {text: row.label})]);
        if (row.detail) option.append(element("small", {text: row.detail}));
        const id = key(row);
        option.addEventListener("mousedown", event => { event.preventDefault(); });
        option.addEventListener("click", () => choose(id));
        rendered.push({button: option, key: id});
        group.append(option);
      }
      parts.append(group);
    }
    results.replaceChildren(parts);
    const index = refused ? -1 : reset ? 0 : rendered.findIndex(row => row.key === previous);
    highlight(index);
    const changed = refused || previous !== null && !reset && index < 0;
    empty.hidden = rendered.length > 0 && !changed;
    if (!empty.hidden) empty.textContent = word(door.locale(),
      changed && rendered.length ? "paletteChanged" : "paletteEmpty");
  }
  function choose(id) {
    if (!dialog.open || id === null) return;
    const row = door.catalog().find(candidate => key(candidate) === id);
    if (!row || !matches(row, normalize(input.value).split(/\s+/).filter(Boolean))) {
      paint(false, true); return;
    }
    // The destination can take focus only after it stops being inert.
    dialog.close();
    if (door.choose(row) === true) return;
    dialog.showModal();
    active = null; paint(false, true); input.focus();
  }

  function open(trigger) {
    if (events.signal.aborted) return false;
    if (dialog.open) { input.focus(); return true; }
    if (doc.querySelector("dialog[open], #workspace[data-resizing]")) return false;
    origin = trigger || doc.activeElement;
    selection = caret(origin);
    input.value = ""; active = null;
    dialog.showModal(); paint(true);
    input.focus({preventScroll: true});
    return true;
  }
  function dismiss() {
    if (!dialog.open) return;
    dialog.close();
    door.restore(origin);
    if (selection && origin === doc.activeElement) origin.setSelectionRange(...selection);
    origin = selection = null;
  }
  dialog.addEventListener("cancel", event => { event.preventDefault(); dismiss(); }, options);
  dialog.addEventListener("keydown", event => {
    if (event.isComposing || event.keyCode === 229) return;
    if (event.key === "Escape") {
      event.preventDefault(); event.stopPropagation(); dismiss(); return;
    }
    if (event.target !== input || event.altKey || event.ctrlKey || event.metaKey) return;
    const length = rendered.length;
    if (event.key === "Enter") { event.preventDefault(); choose(active); return; }
    if (!length || !["ArrowDown", "ArrowUp"].includes(event.key)) return;
    event.preventDefault();
    const at = rendered.findIndex(row => row.key === active);
    const index = event.key === "ArrowDown" ? (at + 1) % length : (at <= 0 ? length - 1 : at - 1);
    highlight(index, true);
  }, options);
  input.addEventListener("input", () => { results.scrollTop = 0; paint(true); }, options);
  closeButton.addEventListener("click", dismiss, options);
  doc.addEventListener("keydown", event => {
    if (event.defaultPrevented || event.isComposing || event.keyCode === 229 || event.repeat
        || event.altKey || event.shiftKey || event.ctrlKey === event.metaKey) return;
    if (event.code !== "KeyK" && event.key.toLowerCase() !== "k") return;
    if (open(doc.activeElement)) event.preventDefault();
  }, options);
  function dispose() {
    events.abort();
    if (dialog.open) dialog.close();
    rendered = []; active = origin = selection = null;
  }
  return {open, refresh: () => paint(), dispose};
}
