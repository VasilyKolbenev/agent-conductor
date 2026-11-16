"use strict";
import {element} from "./command-view.js";
import {localize} from "./studio-i18n.js";
import {answerFor, atlasEvidence, atlasTestSummary} from "./studio-atlas-inspector.js";
import {nextText} from "./arachnid-next-view.js";

const copy = (view, en, ru) => view.locale === "ru" ? ru : en;
const tr = (view, key) => localize(view, "atlas." + key);

export function recapIntent(message) {
  const away = /пока меня не было|за мо[её] отсутствие|что я пропустил|while i was (away|out)/i;
  const missed = /what (?:did|have) i miss|catch me up/i;
  const need = /где я нуж(?:ен|на)|где нуж(?:ен|на) я|что (?:нужно от меня|от меня требуется)/i;
  const attention = /(?:где|нужно ли) мо[её] решение|что требует моего внимания/i;
  return away.test(message) || missed.test(message) || need.test(message) || attention.test(message)
    || /where (?:am i needed|do you need me)|what needs my (?:input|decision)/i.test(message);
}

export const recapTitle = view => copy(view, "While I was away", "Пока меня не было");

export function recapStatus(view, next) {
  if (!next) return nextText(view.locale, "unreadable");
  const status = nextText(view.locale, next.kind, next.name);
  if (["result", "complete"].includes(next.kind)) {
    const terminal = view.detail?.records.some(({record_type, record}) =>
      record_type === "run_terminal" && record?.run_id === view.runId
      && record.state === "complete");
    if (terminal) return status + copy(view, ". No decision is pending.",
      ". Ваше решение не требуется.");
    return copy(view, "The plan is complete. No terminal record is available.",
      "План исчерпан. Запись о завершении запуска отсутствует.");
  }
  if (next.kind === "gate") return status + " · " + next.name;
  return next.why ? status + " · " + next.why : status;
}

function values(view, evidence) {
  const paths = evidence.files.slice(0, 3).map(file => file.path);
  if (paths.length && paths.length < evidence.files_total) paths.push("…");
  const count = evidence.files_total === null ? tr(view, "no_files")
    : copy(view, "Changed files: ", "Изменено файлов: ") + evidence.files_total;
  return [[count, ...paths].join(" · "), atlasTestSummary(view, evidence.tests),
    answerFor(view, "verdict", evidence)];
}

export function recapAnswer(view, status, evidence, otherwise) {
  const evidenceText = evidence ? values(view, evidence).join("\n") : otherwise;
  return [status, evidenceText].filter(Boolean).join("\n");
}

export function renderRecap(host, view, data, select) {
  const {next, action, scope, latest, read, tab, choice} = data;
  const body = element("section", {className: "inspect-body recap", "data-recap": "",
    "data-recap-action": action?.action_id ?? null,
    "data-recap-attempt": action?.attempt_id ?? null});
  body.append(element("h2", {tabindex: "-1", text: recapTitle(view)}));
  const attention = element("section", {className: "recap-attention"}, [
    element("h3", {text: copy(view, "Current run", "Сейчас в запуске")}),
    element("p", {text: recapStatus(view, next)}),
  ]);
  body.append(attention);
  const name = latest ? copy(view, "Latest recorded attempt", "Последняя записанная попытка")
    : copy(view, "Selected attempt", "Выбранная попытка");
  if (scope) body.append(element("p", {className: "recap-scope",
    text: name + " · " + scope + (action ? " · " + action.action_id : "")}));
  const note = text => element("p", {role: "status", text});
  const evidence = read?.phase === "ready" ? read.value : null;
  if (!evidence) {
    body.append(note(data.note));
  } else {
    const samples = values(view, evidence);
    const actions = element("div", {className: "recap-list",
      role: "group", "aria-label": copy(view, "Attempt evidence", "Материалы попытки")});
    for (const [index, key] of ["diff", "tests", "verdict"].entries()) {
      const label = key === "diff" ? "Diff" : tr(view, key);
      const button = element("button", {type: "button", "data-recap-open": key,
        "data-focus": "recap:" + key, "aria-pressed": String(tab === key)}, [
        element("strong", {text: label}), element("span", {text: samples[index]}),
        element("span", {"aria-hidden": "true", className: "recap-arrow", text: "↗"}),
      ]);
      button.addEventListener("click", () => select({tab: key}));
      actions.append(button);
    }
    body.append(actions);
    if (tab) {
      const panel = element("section", {className: "atlas-artifacts", id: "atlas-tab-panel",
        "aria-label": tr(view, tab)});
      atlasEvidence(panel, view, evidence, {...choice, tab}, select);
      body.append(panel);
    }
  }
  host.replaceChildren(body);
}
