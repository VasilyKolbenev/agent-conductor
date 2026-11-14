"use strict";
import {element} from "./command-view.js";

const labels = {
  apply_patch: ["Apply the patch", "Применить патч"],
  run_tests: ["Run the pinned unittest suite", "Запустить закреплённые тесты unittest"],
  independent_check: ["Send the diff and test report to the independent checker",
    "Передать diff и протокол тестов независимому проверяющему"],
  result_gate: ["Submit the result for final acceptance",
    "Передать результат на финальную приёмку"],
};
const help = [
  'Try “Add before tests: check empty input”, “Edit step 2: …” or “Remove step 2”.',
  'Например: «Добавь перед тестами проверку пустого списка», «Измени шаг 2: …», «Убери шаг 2».',
];
const pick = (pair, locale) => pair[locale === "ru" ? 1 : 0];
const line = (row, locale) => row.id ? pick(labels[row.id], locale)
  + (row.note ? " — " + row.note : "") : row.custom;
export function reviewIntent(text) {
  return /прошл|предыдущ|принят|prior|previous|last task|accepted/i.test(text)
    && /провер|ревью|review|verif|check/i.test(text);
}
export function newReview(source) {
  const steps = source.kind === "operator" ? source.steps.map(row => ({custom: row.label}))
    : source.steps.map(id => ({id}));
  return {source, version: 1, steps};
}
export function editReview(plan, raw, locale) {
  const text = raw.trim();
  const message = (en, ru) => ({plan, text: pick([en, ru], locale)});
  const nominee = text.match(/^(?:проверяющий|проверяющим|checker|reviewer)\s*[:—]\s*(.+)$/iu);
  if (nominee) {
    const value = nominee[1].trim();
    if (value === plan.source.doer?.instanceId || !/^[\p{L}\d][\p{L}\d ._-]{0,63}$/u.test(value))
      return message("Name a separate checker.", "Укажи отдельного проверяющего.");
    return {plan: {...plan, nominee: value, version: plan.version + 1},
      text: pick(["Recorded your nomination.", "Записал твоего кандидата."], locale)};
  }
  const steps = plan.steps.slice();
  const added = text.match(/^(?:добавь(?:те)?|добавить|add|insert)\s+(.+)$/iu);
  const edit = /^(?:измени|замени|edit|replace)\s+(?:шаг|step)\s+/iu;
  const change = edit.test(text)
    && text.replace(edit, "").match(/^(\d+)(?:\s+на\s+|\s*:\s*)(.+)$/iu);
  const remove = text.match(/^(?:убери|удали|remove|delete)\s+(?:шаг|step)\s+(\d+)[.!]?$/iu);
  const before = /^(?:перед|before)\s+/iu;
  const anchors = /^(тестами|проверяющим|при[её]мкой|tests|checker|acceptance)[:\s]+(.+)$/iu;
  const numbered = /^(?:перед\s+шагом|before\s+step)\s+(\d+)(?:\s*:\s*|\s+)(.+)$/iu;
  if (added) {
    const arg = added[1], number = arg.match(numbered);
    const where = before.test(arg) && arg.replace(before, "").match(anchors);
    if (!where && !number && /^(?:перед|после|before|after)\s+/iu.test(arg))
      return message(...help);
    const match = where?.[1].toLowerCase();
    const anchor = ["тестами", "tests"].includes(match) ? "run_tests"
      : ["проверяющим", "checker"].includes(match) ? "independent_check" : "result_gate";
    const append = !number && !where && plan.source.kind === "operator";
    const pos = number ? Number(number[1]) - 1 : append ? steps.length
      : steps.findIndex(row => row.id === anchor);
    const value = (number?.[2] ?? where?.[2] ?? arg).trim();
    if (!value || value.length > 320 || steps.length >= 20 || pos < 0
        || (!append && pos >= steps.length))
      return message("Invalid step or plan too long.", "Проверь номер шага и длину дополнения.");
    steps.splice(pos, 0, {custom: value});
  } else if (change || remove) {
    const i = Number((change || remove)[1]) - 1;
    if (!steps[i]) return message("No such step.", "В плане нет такого шага.");
    if (remove && steps[i].id && !steps[i].note) return message(
      "This check is required; its instructions can be edited.",
      "Это обязательная проверка. Можно уточнить её условия.");
    if (remove && steps[i].id) steps[i] = {id: steps[i].id};
    else if (remove) steps.splice(i, 1);
    else if (change[2].trim() && change[2].trim().length <= 320)
      steps[i] = steps[i].id ? {id: steps[i].id, note: change[2].trim()}
        : {custom: change[2].trim()};
    else return message(...help);
  } else return message(...help);
  return {plan: {...plan, steps, version: plan.version + 1},
    text: pick(["Updated your proposal.", "Обновил твой план."], locale)};
}

export function reviewCard(plan, locale, href, use) {
  const tr = (en, ru) => pick([en, ru], locale);
  const s = plan.source, list = plan.steps.map(row => line(row, locale));
  const manual = s.kind === "operator";
  const previous = manual ? s.author : s.checker.adapter + " · " + s.checker.instanceId;
  const reviewer = plan.nominee || previous;
  const title = tr("Review plan", "План проверки") + " · v" + plan.version;
  const steps = element("ol", {className: "review-steps"}, list.map((text, i) =>
    element("li", {"data-kind": plan.steps[i].id || "operator", text})));
  const source = element("a", {className: "review-source", href: href.session,
    target: "_blank", rel: "noopener", text: manual ? s.taskTitle : s.runId});
  const proof = element("a", {href: href.attempt, target: "_blank", rel: "noopener",
    text: manual ? tr("Accepted check record", "Принятая запись проверок")
      : tr("Do attempt and protocol", "Попытка Do и протокол")});
  const summary = manual ? tr("Suggested reviewer: ", "Предлагаю проверяющего: ")
    : tr("Independent checker proposed: ", "Предлагаю независимого проверяющего: ");
  const reason = manual ? tr("The operator confirmed the first task: ",
    "Проверки первой задачи подтвердил(а) ") + previous
    : tr("Previously verified by ", "В прошлом запуске проверял ") + previous
    + tr("; tests recorded: ", "; в протоколе тестов: ") + s.tests.total + ".";
  const plain = [title, ...list.map((v, i) => (i + 1) + ". " + v), summary + reviewer,
    tr("Source: ", "Источник: ") + (manual ? s.taskTitle + " / " + s.runId + " / " + s.documentId
      : s.runId + " / " + s.nodeId + " / " + s.attemptId)].join("\n");
  const card = element("section", {
    className: "review-proposal", "data-revision": String(plan.version)}, [
    element("h3", {text: title}), steps, element("p", {text: summary + reviewer}),
    element("p", {className: "review-meta", text: reason}),
    ...(plan.nominee ? [element("small", {text: tr("Operator nomination; availability not checked.",
      "Кандидат оператора; доступность для этой роли ещё не проверена.")})] : []),
    element("div", {}, [element("span", {text: tr("Source: ", "Источник: ")}), source,
      element("span", {text: " · "}), proof]),
    element("details", {}, [element("summary", {
      text: tr("Plan text to copy", "Текст плана для копирования")}),
      element("pre", {text: plain})]),
    element("small", {text: tr("Draft in this tab. Nothing has been scheduled.",
      "Черновик в этой вкладке. Ничего не запущено.")}),
  ]);
  if (use) {
    const b = element("button", {type: "button", className: "atlas-refresh",
      text: tr("Use in a task brief", "Перенести в текст задачи")});
    b.addEventListener("click", () => use(plain)); card.append(b);
  }
  return card;
}
export const reviewHelp = locale => pick(help, locale);
