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

export function focusTarget() {
  const active = document.activeElement;
  if (!active || active === document.body || !active.getAttribute) return null;
  const key = active.getAttribute("data-focus")
    || active.getAttribute("data-focus-key");
  if (!key) return null;
  const form = active.closest("[data-step]");
  const typed = typeof active.setSelectionRange === "function"
    && typeof active.value === "string";
  return {key, step: form === null ? null : form.getAttribute("data-step"),
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
  successor.focus();
  if (held.value === null
      || typeof successor.setSelectionRange !== "function") return;
  if (successor.value !== held.value) successor.value = held.value;
  successor.setSelectionRange(held.start, held.end);
}
