"use strict";
import {element} from "./command-view.js";
import {answerFor, atlasTestSummary} from "./studio-atlas-inspector.js";

const text = (tag, value, cls = "") => element(tag, {className: cls, text: value});
const word = locale => (en, ru) => locale === "ru" ? ru : en;

function selectRecord(host, name, label, options, selected, choose) {
  if (!options.length || (options.length === 1 && options[0].index === selected)) return;
  const menu = element("select", {"data-handoff-select": name, "data-focus": "handoff:" + name});
  if (!options.some(row => row.index === selected)) {
    menu.append(element("option", {value: "-1", disabled: "", text: "—"}));
  }
  for (const row of options) {
    menu.append(element("option", {value: String(row.index), text: row.title}));
  }
  menu.value = String(selected);
  menu.addEventListener("change", () => choose(Number(menu.value)));
  host.append(element("label", {className: "handoff-picker"}, [text("span", label), menu]));
}

function node(key, endpoint, caption, choice, select) {
  const b = element("button", {type: "button", className: "handoff-node",
    "data-handoff-node": key, "data-focus": "handoff:" + key,
    "data-handoff-action": endpoint.actionId, "data-handoff-attempt": endpoint.attemptId,
    "data-handoff-artifact": endpoint.artifactId ?? null,
    "aria-pressed": String(choice === key)}, [
    text("small", endpoint.adapter), text("strong", endpoint.nodeId), text("span", caption),
  ]);
  b.addEventListener("click", () => select(key));
  return b;
}

function edge(label, relation) {
  const rail = element("div", {className: "handoff-edge", "data-relation": relation}, [
    text("span", label),
  ]);
  if (relation === "different_revision") return rail;
  const ns = "http://www.w3.org/2000/svg";
  const curve = document.createElementNS(ns, "svg");
  curve.setAttribute("viewBox", "0 0 100 25");
  curve.setAttribute("preserveAspectRatio", "none");
  curve.setAttribute("aria-hidden", "true");
  const path = document.createElementNS(ns, "path");
  path.setAttribute("d", "M0 20 C44 20 52 5 97 5 M87 1 L97 5 L87 10");
  path.setAttribute("vector-effect", "non-scaling-stroke");
  curve.append(path); rail.prepend(curve);
  return rail;
}

function identity(w, endpoint, extra = []) {
  const rows = [[w("Participant", "Участник"), endpoint.instanceId],
    [w("Action", "Действие"), endpoint.actionId], [w("Attempt", "Попытка"), endpoint.attemptId],
    ...extra];
  if (endpoint.artifactId) rows.unshift([w("Document", "Документ"), endpoint.artifactId]);
  return element("dl", {className: "handoff-ids"}, rows.flatMap(([label, value]) =>
    [text("dt", label), element("dd", {}, [text("code", value)])]));
}

function material(w, key, link, next) {
  const section = element("section", {className: "handoff-proof", "data-handoff-proof": key});
  if (key === "input" && next) {
    section.append(text("h3", w("Input bound to this action", "Вход, закреплённый за действием")),
      text("p", next.inputRef, "handoff-ref"), identity(w, next.target, [
        [w("Input document", "Входной документ"), next.inputArtifactId],
      ]));
    return section;
  }
  const source = key === "source", row = source ? link.source : link.target;
  section.append(text("h3", w("Recorded material", "Записанный материал")),
    text("p", row.artifactRef, "handoff-ref"), text("blockquote", row.excerpt ||
      w("No text excerpt available.", "Текстовая выдержка недоступна.")), identity(w, row));
  if (!source) section.append(text("p", w("Recorded input", "Вход по записи") +
    " · " + link.source.artifactId, "handoff-ref"));
  return section;
}

function handoff(host, w, link, next, options, choice, callbacks) {
  const key = ["source", "target", ...(next ? ["input"] : [])].includes(choice.selectedKey)
    ? choice.selectedKey : "target";
  const network = element("section", {className: "handoff-map",
    "aria-label": w("Document lineage", "Связи документов")});
  network.append(node("source", link.source, link.source.artifactRef,
    key, callbacks.select), edge(w("Recorded input", "Записанный вход"), "exact"),
  node("target", link.target, link.target.artifactRef, key, callbacks.select));
  if (next) {
    const same = next.kind === "same_revision";
    const relation = edge(same ? w("Same revision used", "Использована та же редакция")
      : w("Different revision used", "Использована другая редакция"), next.kind);
    relation.dataset.handoffRevision = next.kind;
    network.append(relation, node("input", next.target, next.inputRef, key, callbacks.select));
  }
  host.append(network, material(w, key, link, next));
  if (next) {
    const button = element("button", {type: "button", className: "handoff-tests-button",
      "data-handoff-read-tests": "", "data-focus": "handoff:tests",
      text: w("Show tests for this action", "Показать тесты этого действия")});
    button.addEventListener("click", callbacks.tests);
    host.append(button);
  } else host.append(text("p", options.length
    ? w("Select the next action.", "Выберите следующее действие.")
    : w("No subsequent action with a bound revision was found.",
      "Последующее действие с закреплённой редакцией не найдено.")));
}

function protocol(w, p) {
  const box = element("details", {className: "handoff-protocol", "data-handoff-protocol": ""});
  box.append(element("summary", {"data-focus": "handoff:protocol",
    text: w("Test command and output", "Команда и вывод тестов")}),
  text("pre", JSON.stringify(p.argv)), text("p", w("Exit code", "Код выхода") +
    " · " + (p.exit_code ?? "—")), text("pre", p.output));
  return box;
}

function testPanel(host, locale, w, runId, next, choice, callbacks) {
  const data = choice.evidence;
  if (!next || choice.phase !== "ready" || !data || data.run_id !== runId
      || data.action_id !== next.target.actionId
      || data.attempt_id !== next.target.attemptId || data.node_id !== next.target.nodeId) {
    host.append(text("p", choice.phase === "loading" && next
      ? w("Reading the attempt…", "Читаю попытку…")
      : w("No matching attempt evidence available.", "Сведения об этой попытке недоступны.")));
    return;
  }
  const t = data.tests, panel = element("section", {className: "handoff-results",
    "data-handoff-tests": "", "data-handoff-action": data.action_id,
    "data-handoff-attempt": data.attempt_id});
  const scope = next.kind === "different_revision"
    ? w("Tested work used a different plan revision.",
      "На проверенном шаге использовалась другая редакция плана.")
    : w("Tested work used the handoff revision.",
      "На проверенном шаге использовалась редакция из передачи.");
  panel.append(text("h3", w("Tests for this attempt", "Тесты этой попытки")),
    element("p", {"data-handoff-revision": next.kind, text: scope}),
    identity(w, next.target, [[w("Input document", "Входной документ"), next.inputArtifactId]]),
    text("p", atlasTestSummary({locale}, t)));
  if (t.summary) {
    const metrics = [[w("Total", "Всего"), t.summary.total], [w("Failures", "Падения"),
      t.summary.failures], [w("Errors", "Ошибки"), t.summary.errors], [w("Skipped", "Пропуски"),
      t.summary.skipped]];
    const maximum = Math.max(1, ...metrics.map(([, value]) => value));
    panel.append(element("dl", {className: "handoff-counts"}, metrics.map(([label, value]) =>
      element("div", {}, [text("dt", label), element("dd", {}, [text("strong", String(value)),
        element("meter", {min: "0", max: String(maximum), value: String(value),
          "aria-hidden": "true"})])]))));
  }
  if (t.source === "native") panel.append(protocol(w, t.protocol));
  if (t.cases.length) {
    panel.append(text("h4", w("Recorded test locations", "Записанные места тестов")));
    t.cases.forEach((c, i) => {
      const key = "case:" + i, open = choice.selectedKey === key;
      const button = element("button", {type: "button", className: "handoff-case",
        "data-handoff-case": String(i), "data-focus": "handoff:" + key,
        "aria-expanded": String(open), text: c.name + " · " + c.path + ":" + c.line});
      button.addEventListener("click", () => callbacks.select(open ? "check" : key));
      panel.append(button);
      if (open) panel.append(text("pre", c.assertion ||
        w("Assertion unavailable.", "Утверждение недоступно.")));
    });
  }
  panel.append(text("h4", w("Attempt verdict", "Вердикт попытки")),
    text("p", answerFor({locale}, "verdict", data)));
  if (data.verdict?.reason) panel.append(text("p", data.verdict.reason));
  panel.append(text("p", w("Individual findings have no recorded test mapping.",
    "Для отдельных выводов связь с тестами не записана."), "handoff-caveat"));
  host.append(panel);
}

export function renderHandoff(host, locale, model, choice, callbacks) {
  const w = word(locale), tests = choice.view === "tests";
  const active = host.contains(document.activeElement) ? document.activeElement : null;
  const focus = active?.dataset.focus;
  const details = host.querySelector("[data-handoff-protocol]");
  const link = model.links[choice.linkIndex];
  const next = model.continuations[choice.continuationIndex];
  const bound = link && next?.fromArtifactId === link.target.artifactId ? next : null;
  const scope = JSON.stringify([model.runId, link?.target.artifactId, bound?.target.actionId]);
  const keepProtocol = details?.open && host.firstElementChild?.dataset.handoffScope === scope;
  const panel = element("section", {className: "handoff-panel", "data-handoff-scope": scope,
    "data-handoff-view": choice.view}, [text("h2", tests ? w("Test evidence", "Сведения о тестах")
      : w("Harness handoff", "Передача работы"))]);
  host.replaceChildren(panel);
  selectRecord(panel, "link", w("Handoff", "Передача"), model.links.map((l, index) =>
    ({index, title: l.source.nodeId + " → " + l.target.nodeId + " · " + l.target.artifactId})),
  choice.linkIndex, callbacks.link);
  if (link) {
    const options = model.continuations.map((c, index) => ({c, index}))
      .filter(r => r.c.fromArtifactId === link.target.artifactId)
      .map(({c, index}) => ({index, title: c.target.nodeId + " · " + c.target.attemptId}));
    selectRecord(panel, "continuation", w("Next action", "Следующее действие"),
      options, choice.continuationIndex, callbacks.continuation);
    if (tests && !bound && options.length) {
      panel.append(text("p", w("Select the next action to read its tests.",
        "Выберите следующее действие, чтобы открыть его тесты.")));
    } else if (tests) testPanel(panel, locale, w, model.runId, bound, choice, callbacks);
    else handoff(panel, w, link, bound, options, choice, callbacks);
  } else panel.append(text("p", model.links.length
    ? w("Select a recorded handoff.", "Выберите записанную передачу.")
    : w("No handoff identified by exact input document ID.",
      "Передача по точному идентификатору входного документа не найдена.")));
  const p = panel.querySelector("[data-handoff-protocol]");
  if (p && keepProtocol) p.open = true;
  if (focus) [...panel.querySelectorAll("[data-focus]")].find(b => b.dataset.focus === focus)
    ?.focus({preventScroll: true});
}
