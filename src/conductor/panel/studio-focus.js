"use strict";
// What a person had focused, typed and selected, carried across a render pass.
//
// Split out of `studio.js` at the line cap. It is render machinery rather than
// transport -- it reads the focused control before a pass and hands focus to
// the control that replaced it -- and it reaches no socket, no store and no
// other module. The boot module still takes the key before every pass and
// hands it back after; only the two functions live here.
//
// Every mounting module restores focus inside its own subtree. This is the
// net under all of them: it acts only when the pass ended with focus on the
// body, so it can never fight a module that already put focus back.
//
// It carries the person's WORDS and CARET as well as the key. A pass
// replaces the control, and the successor is drawn from the reducer, which
// holds what `change` committed: the letters typed since, and where the
// caret stood among them, would be lost or moved to the end (the fold
// review's R1/R5). A step field belongs to its original form: if that form
// vanished, even a now-unique sibling key must not take its caret (R4).

//: What a control's words belong to, read off the DOM they were typed into -- never off the
//: state the next pass draws: every `data-subject` above it (one step or connection of one
//: Workflow document, one run, one decision) and the `data-step` form around it. The same
//: field of every step shares one key, so a key alone cannot say whose words these are.
function ownerOf(node) {
  const chain = [];
  for (let at = node.parentElement; at; at = at.parentElement) {
    if (at.hasAttribute("data-subject")) chain.push(`subject:${at.getAttribute("data-subject")}`);
    if (at.hasAttribute("data-step")) chain.push(`step:${at.getAttribute("data-step")}`);
  }
  return JSON.stringify(chain);
}

export function focusTarget() {
  const active = document.activeElement;
  if (!active || active === document.body || !active.getAttribute) return null;
  const key = active.getAttribute("data-focus")
    || active.getAttribute("data-focus-key");
  if (!key) return null;
  const form = active.closest("[data-step]");
  const typed = typeof active.setSelectionRange === "function"
    && typeof active.value === "string";
  return {key, step: form === null ? null : form.getAttribute("data-step"), owner: ownerOf(active),
    value: typed ? active.value : null,
    start: typed ? active.selectionStart : null,
    end: typed ? active.selectionEnd : null};
}

//: `shell` is the Studio's outer frame, and the successor is looked for inside
//: it and nowhere else on the page.
export function restoreFocus(shell, held) {
  const active = document.activeElement;
  if (held === null || (active && active !== document.body)) return;
  const within = held.step === null ? "" : `[data-step="${held.step}"] `;
  const found = shell.querySelectorAll(
    `${within}[data-focus="${held.key}"], ${within}[data-focus-key="${held.key}"]`);
  if (found.length !== 1) return;
  const successor = found[0];
  const typing = held.value !== null && typeof successor.setSelectionRange === "function";
  // The same field of another thing is not handed the caret: the typing would go on into it.
  if (typing && ownerOf(successor) !== held.owner) return;
  successor.focus();
  if (!typing) return;
  // Controls that commit every input own their text in state. Restoring a
  // spent draft's old DOM value would resurrect text the state just cleared.
  if (successor.getAttribute("data-focus-value") !== "state"
      && successor.value !== held.value) successor.value = held.value;
  successor.setSelectionRange(held.start, held.end);
}

//: Words typed into a control that has not taken them yet. A check that refuses them keeps
//: them out of the store, so the next pass -- a language or theme switch, a frame -- would
//: draw the control empty. The shell marks a control on `input` and unmarks it on `change`
//: (studio.js); these carry every marked one across a pass into the control that replaced
//: it, and say `input` again so its own check speaks in the language of the new pass. Only
//: into a successor of the same owner: words refused in one step are not another step's.
export function typedValues(shell) {
  return [...shell.querySelectorAll("[data-typed]")].map((node) => ({
    key: node.getAttribute("data-focus") || node.getAttribute("data-focus-key"),
    owner: ownerOf(node), value: node.value,
  })).filter((row) => row.key && typeof row.value === "string");
}

export function restoreTyped(shell, rows) {
  for (const held of rows) {
    const found = [...shell.querySelectorAll(
      `[data-focus="${held.key}"], [data-focus-key="${held.key}"]`)]
      .filter((node) => ownerOf(node) === held.owner);
    if (found.length !== 1) continue;
    const successor = found[0];
    if (successor.getAttribute("data-focus-value") === "state" || successor.value === held.value) continue;
    successor.value = held.value;
    successor.setAttribute("data-typed", "");
    const said = document.createEvent("Event");
    said.initEvent("input", true, true);
    successor.dispatchEvent(said);
  }
}
