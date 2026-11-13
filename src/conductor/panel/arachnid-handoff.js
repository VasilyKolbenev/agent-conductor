"use strict";
import {element} from "./command-view.js";
import {answerFor, atlasDiff, atlasTestSummary} from "./studio-atlas-inspector.js";

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

// Read the after-side of a single hunk. A gap or a different definition ends the excerpt.
function caseExcerpt(files, c) {
  if (!c.assertion) return null;
  const file = files.find(f => f.path === c.path && f.diff_status === "available");
  let number = null, body = [], indent = -1;
  for (const line of file?.lines || []) {
    if (line.startsWith("@@")) {
      const header = /^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@/.exec(line);
      number = header ? Number(header[1]) : null;
      body = []; indent = -1; continue;
    }
    if (number === null || !/^[+ ]/.test(line)) continue;
    const source = line.slice(1), trimmed = source.trimStart();
    const depth = source.length - trimmed.length;
    if (trimmed && depth <= indent) { body = []; indent = -1; }
    const def = /^(?:async\s+)?def\s+([^\s(]+)\s*\(/.exec(trimmed);
    if (def) {
      body = [];
      indent = def[1] === c.name ? depth : -1;
    }
    if (indent >= 0) body.push(source);
    if (number++ === c.line) {
      return source.trim() === c.assertion && body.length > 2 && body.length <= 24
        && body.every(row => row.length <= 320) ? body.join("\n") : null;
    }
  }
  return null;
}

// These are transcript quotes. A short method name can occur in multiple modules or classes.
function reportedCases(t) {
  if (t.source !== "native") return [];
  return t.protocol.output.split(/\r?\n/).filter(line =>
    /^test_\S+ \([^()]+\) \.\.\. (?:ok|FAIL|ERROR|skipped .+|expected failure|unexpected success)$/
      .test(line));
}

function reportNote(w, t, named) {
  if (t.source === "external") return w("Only totals were recorded in the external report.",
    "Во внешнем отчёте записаны только общие счётчики.");
  if (t.source !== "native") return "";
  if (named.length) return w("Named results are quoted from unittest output.",
    "Поимённые результаты приведены из вывода unittest.");
  const quiet = t.protocol.output.split(/\r?\n/).every(s => !s.trim() || /^[-.sFxEu]+$/.test(s)
    || /^(?:Ran \d+ tests? in \S+s|OK(?: \(.*\))?|conduct\.test-result\.v1 \{.*\})$/.test(s));
  return quiet ? w("No named results in the output.", "Поимённых результатов в выводе нет.")
    : w("See the full output for details.", "Подробности — в полном выводе.");
}

export function handoffCasesAnswer(locale, data) {
  const w = word(locale), t = data.tests, named = reportedCases(t);
  const lines = t.cases.map(c => c.name + " · " + (c.assertion ||
    w("Assertion unavailable.", "Строка проверки недоступна.")));
  return [w("From the test source", "В коде тестов"), ...lines,
    w("Attempt report", "Протокол попытки") + " · " + atlasTestSummary({locale}, t),
    reportNote(w, t, named)].filter(Boolean).join("\n");
}

function casesPanel(host, locale, w, data) {
  const t = data.tests;
  const section = element("section", {className: "handoff-case-proof", "data-handoff-cases": "",
    "data-handoff-action": data.action_id, "data-handoff-attempt": data.attempt_id});
  const source = element("section", {className: "handoff-results", "data-case-source": ""},
    [text("h3", w("In the test source", "В коде тестов"))]);
  for (const [i, c] of t.cases.entries()) {
    const card = element("article", {className: "handoff-source-case", "data-handoff-case": c.name},
      [text("h4", c.name), text("code", c.path + ":" + c.line, "handoff-ref"),
        text("pre", c.assertion || w("Assertion unavailable.", "Строка проверки недоступна."))]);
    const excerpt = caseExcerpt(data.files, c);
    if (excerpt) card.append(element("details", {"data-case-example": String(i)}, [
      element("summary", {"data-focus": "case-example:" + i,
        text: w("Show source through the assertion", "Показать код до проверки")}),
      text("pre", excerpt)]));
    source.append(card);
  }
  if (!t.cases.length) source.append(text("p", w("No test locations recorded.",
    "Места проверок в коде не записаны.")));
  section.append(source, runPanel(locale, w, t)); host.append(section);
}

function runPanel(locale, w, t, title = w("In the attempt report", "В протоколе попытки")) {
  const named = reportedCases(t);
  const run = element("section", {className: "handoff-results", "data-case-run": ""},
    [text("h3", title), text("p", atlasTestSummary({locale}, t))]);
  const note = reportNote(w, t, named);
  if (note) run.append(text("p", note));
  for (const line of named) run.append(element("pre", {"data-case-observation": "", text: line}));
  if (t.source === "native") run.append(protocol(w, t.protocol));
  return run;
}

function oldProof(c, files) {
  const p = c.old_length;
  if (!p || !Number.isSafeInteger(p.actual) || p.actual < 0 || !Number.isSafeInteger(p.expected)
      || !Number.isSafeInteger(p.line) || p.line < 1 || !c.assertion
      || typeof p.function !== "string" || !p.function || typeof p.expression !== "string"
      || !/^len\([\p{ID_Start}_][\p{ID_Continue}]*\)$/u.test(p.expression)
      || !files.some(f => f.path === p.path && f.state === "modified"
        && f.diff_status === "available")
      || !files.some(f => f.path === c.path && f.diff_status === "available")) return null;
  return p;
}

function oldEffect(w, p) {
  if (!p) return w("Insufficient evidence", "Недостаточно данных");
  return p.actual === p.expected ? w("Would not catch it", "Не обнаружил бы")
    : w("Would catch it", "Обнаружил бы");
}

export function handoffOldAnswer(locale, data) {
  const w = word(locale), t = data.tests;
  const rows = t.cases.map(c => ({name: c.name, p: oldProof(c, data.files)}));
  const known = rows.filter(r => r.p), caught = known.filter(({p}) => p.actual !== p.expected);
  const counts = known.length ? w("Would catch the bug: ", "Обнаружили бы ошибку: ")
    + caught.length + w(" of ", " из ") + known.length
    : w("The available source does not establish the old result.",
      "По доступному коду прежний результат не определён.");
  return [w("Source comparison", "Сравнение по коду") + " · " + counts,
    ...rows.map(({name, p}) => name + " · " + (p ? p.expression + " = " + p.actual
      + w(", expected ", ", ожидалось ") + p.expected + " · " + oldEffect(w, p) : oldEffect(w, p))),
    w("Post-patch Do report", "Протокол Do после правки") + " · " + atlasTestSummary({locale}, t)]
    .join("\n");
}

function oldPanel(host, locale, w, data) {
  const section = element("section", {className: "handoff-case-proof", "data-handoff-old-tests": "",
    "data-handoff-action": data.action_id, "data-handoff-attempt": data.attempt_id});
  const source = element("section", {className: "handoff-results"},
    [text("h3", w("By the code before the patch", "По коду до правки")),
      text("p", w("Static comparison without running the old code.",
        "Расчёт без выполнения старого кода."))]);
  for (const c of data.tests.cases) {
    const p = oldProof(c, data.files);
    const row = element("article", {className: "handoff-source-case", "data-old-row": c.name},
      [text("h4", c.name), text("code", c.path + ":" + c.line, "handoff-ref")]);
    if (p) {
      const values = element("dl", {className: "handoff-compare-values"}, [
        text("dt", p.expression), element("dd", {"data-old-actual": "", text: String(p.actual)}),
        text("dt", w("Expected", "Ожидалось")),
        element("dd", {"data-old-expected": "", text: String(p.expected)})]);
      row.append(values, text("code", p.path + ":" + p.line, "handoff-ref"));
    }
    row.append(element("p", {"data-old-effect": "", text: oldEffect(w, p)}));
    source.append(row);
  }
  if (!data.tests.cases.length) source.append(text("p",
    w("No test locations recorded.", "Места проверок в коде не записаны.")));
  section.append(source, runPanel(locale, w, data.tests,
    w("Post-patch Do report", "Протокол Do после правки"))); host.append(section);
}

function checkerDecision(locale, data) {
  const w = word(locale), result = data.verdict;
  if (result?.status !== "verified") return answerFor({locale}, "verdict", data);
  const checker = w("Independent checker ", "Независимый проверяющий ")
    + result.adapter_id + " (" + result.instance_id + ")";
  if (data.manifest_digest) return checker
    + w(" verified the snapshot of this Do attempt.", " подтвердил снимок этой попытки Do.");
  return checker + w(" accepted this Do attempt's result. The snapshot ID was not recorded.",
    " принял результат этой попытки Do. Идентификатор снимка не записан.");
}

function checkerRationale(locale, data) {
  if (data.verdict?.status === "rejected") {
    return data.verdict.findings.map(f => f.summary).join("\n");
  }
  if (data.verdict?.status !== "verified") return "";
  return word(locale)("The checker recorded no separate rationale.",
    "Отдельное обоснование проверяющего не записано.");
}

export function handoffVerdictAnswer(locale, data) {
  const w = word(locale), result = [checkerDecision(locale, data)];
  if (data.verdict?.status === "verified" && data.manifest_digest && data.files_total !== null) {
    result.push(answerFor({locale}, "diff", data));
  }
  if (data.tests.status === "recorded") {
    result.push(w("Test report for this attempt", "Протокол тестов этой попытки") + " · "
      + atlasTestSummary({locale}, data.tests));
  }
  return [...result, checkerRationale(locale, data)].filter(Boolean).join("\n");
}

function verdictPanel(host, locale, w, data, next) {
  const section = element("section", {className: "handoff-results", "data-handoff-verdict": "",
    "data-handoff-action": data.action_id, "data-handoff-attempt": data.attempt_id});
  const rationale = checkerRationale(locale, data);
  section.append(text("h3", checkerDecision(locale, data)));
  if (rationale) section.append(text("p", rationale, "handoff-caveat"));
  if (data.manifest_digest) {
    section.append(text("h4", w("Snapshot of this attempt", "Снимок этой попытки")),
      text("p", answerFor({locale}, "diff", data)),
      text("code", data.manifest_digest, "handoff-ref"));
  }
  section.append(text("h4", w("Test report for this attempt", "Протокол тестов этой попытки")),
    text("p", atlasTestSummary({locale}, data.tests)));
  if (data.tests.source === "native") section.append(protocol(w, data.tests.protocol));
  section.append(identity(w, next.target, [[w("Input document", "Входной документ"),
    next.inputArtifactId]]));
  host.append(section);
}

function proofPanel(host, locale, w, runId, next, choice, callbacks) {
  const data = choice.evidence;
  if (!next || choice.phase !== "ready" || !data || data.run_id !== runId
      || data.action_id !== next.target.actionId
      || data.attempt_id !== next.target.attemptId || data.node_id !== next.target.nodeId) {
    host.append(text("p", choice.phase === "loading" && next
      ? w("Reading the attempt…", "Читаю попытку…")
      : w("No matching attempt evidence available.", "Сведения об этой попытке недоступны.")));
    return;
  }
  if (choice.view === "verdict") {
    verdictPanel(host, locale, w, data, next);
    return;
  }
  if (choice.view === "cases") { casesPanel(host, locale, w, data); return; }
  if (choice.view === "old-tests") { oldPanel(host, locale, w, data); return; }
  const t = data.tests, panel = element("section", {className: "handoff-results",
    "data-handoff-tests": "", "data-handoff-action": data.action_id,
    "data-handoff-attempt": data.attempt_id});
  if (choice.view === "changes") {
    const pair = element("div", {className: "handoff-changes"});
    const patch = element("section", {className: "handoff-patch atlas-artifacts"},
      [element("header", {className: "handoff-patch-heading"}, [text("h3", w("Patch", "Патч")),
        text("span", atlasTestSummary({locale}, t))])]);
    atlasDiff(patch, {locale}, data, choice, ({file}) => callbacks.file(file));
    pair.append(patch, panel);
    host.append(pair);
  } else host.append(panel);
  const scope = next.kind === "different_revision"
    ? w("Tested work used a different plan revision.",
      "На проверенном шаге использовалась другая редакция плана.")
    : w("Tested work used the handoff revision.",
      "На проверенном шаге использовалась редакция из передачи.");
  panel.append(text("h3", w("Tests for this attempt", "Тесты этой попытки")),
    element("p", {"data-handoff-revision": next.kind, text: scope}),
    identity(w, next.target, [[w("Input document", "Входной документ"), next.inputArtifactId]]));
  if (choice.view !== "changes") panel.append(text("p", atlasTestSummary({locale}, t)));
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
}

export function renderHandoff(host, locale, model, choice, callbacks) {
  const w = word(locale), proof = choice.view !== "handoff";
  const active = host.contains(document.activeElement) ? document.activeElement : null;
  const focus = active?.dataset.focus;
  const details = host.querySelector("[data-handoff-protocol]");
  const link = model.links[choice.linkIndex];
  const next = model.continuations[choice.continuationIndex];
  const bound = link && next?.fromArtifactId === link.target.artifactId ? next : null;
  const scope = JSON.stringify([model.runId, link?.target.artifactId,
    bound?.target.actionId, bound?.target.attemptId]);
  const sameScope = host.firstElementChild?.dataset.handoffScope === scope;
  const keepProtocol = details?.open && sameScope;
  const examples = sameScope ? [...host.querySelectorAll("[data-case-example][open]")]
    .map(el => el.dataset.caseExample) : [];
  const title = {changes: w("Changes and tests", "Изменения и тесты"),
    verdict: w("Independent verdict", "Независимый вердикт"),
    cases: w("What the tests check", "Что проверяют тесты"),
    "old-tests": w("Which tests would catch the bug?", "Какие тесты обнаружили бы ошибку?"),
    tests: w("Test evidence", "Сведения о тестах"),
    handoff: w("Harness handoff", "Передача работы")}[choice.view];
  const panel = element("section", {className: "handoff-panel", "data-handoff-scope": scope,
    "data-handoff-view": choice.view}, [text("h2", title)]);
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
    if (proof && !bound && options.length) {
      panel.append(text("p", w("Select the next action to inspect its attempt.",
        "Выберите следующее действие, чтобы открыть его попытку.")));
    } else if (proof) proofPanel(panel, locale, w, model.runId, bound, choice, callbacks);
    else handoff(panel, w, link, bound, options, choice, callbacks);
  } else panel.append(text("p", model.links.length
    ? w("Select a recorded handoff.", "Выберите записанную передачу.")
    : w("No handoff identified by exact input document ID.",
      "Передача по точному идентификатору входного документа не найдена.")));
  const p = panel.querySelector("[data-handoff-protocol]");
  if (p && keepProtocol) p.open = true;
  for (const el of panel.querySelectorAll("[data-case-example]")) {
    el.open = examples.includes(el.dataset.caseExample);
  }
  if (focus) [...panel.querySelectorAll("[data-focus]")].find(b => b.dataset.focus === focus)
    ?.focus({preventScroll: true});
}
