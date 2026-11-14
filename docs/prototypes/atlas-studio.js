"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const tags = {
    plus: "M12 5v14M5 12h14",
    close: "M6 6l12 12M18 6L6 18",
    menu: "M4 6h16M4 12h16M4 18h16",
    workspace: "M4 4h16v16H4zM9 4v16",
    sidebar: "M3 5h18v14H3zM15 5v14",
    atlas: "M12 2l2.3 7.7L22 12l-7.7 2.3L12 22l-2.3-7.7L2 12l7.7-2.3z",
    terminal: "M4 5h16v14H4zM7 9l3 3-3 3M12 15h4",
    grok: "M4 17L19 4M7 20L20 7M4 15a7 7 0 0 1 10-9M19 11a7 7 0 0 1-10 8",
    memory: "M6 6h12v13H6zM3 9h3M3 13h3M18 9h3M18 13h3M9 3v3M13 3v3",
    meter: "M3 17a9 9 0 0 1 18 0M12 16l5-6M6 17h2M16 17h2",
    sun: "M12 3v2m0 14v2M3 12h2m14 0h2M6 6l1.5 1.5m9 9L18 18M6 18l1.5-1.5m9-9L18 6"
      + "M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0",
    up: "M12 19V5m-6 6 6-6 6 6",
    chat: "M4 5h16v12H9l-5 4z",
    check: "m5 12 4 4L19 6",
    orbit: "M20 7c2.1 4-3.5 10.5-10 12-7 1.5-9-2.6-5-7.5S17 1.8 20 7Z"
      + "m-6 5a2 2 0 1 1-4 0 2 2 0 0 1 4 0",
    file: "M5 3h9l5 5v13H5zM14 3v6h5",
    diff: "M4 8h7m-3.5-3.5v7M14 16h7",
    shield: "M12 3l8 3v6c0 5-5 8-8 10-3-2-8-5-8-10V6zM8 12l3 3 5-6"
  };
  function icon(name) {
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    const path = document.createElementNS(ns, "path");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("class", "glyph");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("fill", "none");
    path.setAttribute("d", tags[name]);
    path.setAttribute("stroke", "currentColor");
    path.setAttribute("stroke-width", "1.65");
    path.setAttribute("stroke-linecap", "round");
    path.setAttribute("stroke-linejoin", "round");
    svg.append(path);
    return svg;
  }
  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function button(text, cls, action) {
    const node = el("button", cls, text);
    node.type = "button";
    node.onclick = action;
    return node;
  }
  function marked(mark, text, cls, action) {
    const node = button("", cls, action);
    node.append(icon(mark), el("span", "", text));
    return node;
  }
  document.querySelectorAll("[data-icon]").forEach(node => node.append(icon(node.dataset.icon)));

  const steps = [
    {id: "goal", label: "Цель", who: "Codex",
      result: "Определить, какие строки должны попадать в счётчик."},
    {id: "identify", label: "Проблема", who: "Codex",
      result: "Счётчик включал все строки независимо от результата."},
    {id: "diagnose", label: "Диагноз", who: "Grok",
      result: "Причина — return len(rows). Изначально был проверен только пустой ввод."},
    {id: "design", label: "План", who: "Codex",
      result: "Ограничить изменение реализацией счётчика и его тестами."},
    {id: "do", label: "Do", who: "Codex",
      result: "Применить изменение и передать точные байты отдельному проверяющему."}
  ];
  const testLabels = [
    ["test_empty_input_is_zero", "Пустой ввод"],
    ["test_mixed_input_counts_only_two_successes", "Смешанные исходы"],
    ["test_other_outcomes_and_missing_outcome_are_excluded", "Исключение неуспешных исходов"],
    ["test_non_dictionary_rows_are_excluded", "Другие типы строк"],
    ["test_invalid_outcome_types_are_excluded", "Тип значения outcome"],
    ["test_outcome_case_and_whitespace_must_match", "Регистр и пробелы"],
    ["test_input_and_nested_objects_are_unchanged", "Исходные объекты"]
  ];
  const mixed = testLabels[1][0], excluded = testLabels[2][0];
  const fileNames = Object.keys(ATLAS_EVIDENCE.files);
  const testFile = "tests/test_counts.py";
  const proofQuestion = "Какой тест подтверждает исправление?";
  const angles = [-162, -108, -53, 10, 67].map(deg => deg * Math.PI / 180);
  const mobile = matchMedia("(max-width:700px)");
  const drawer = matchMedia("(max-width:920px)");

  function session(title, kind = "draft") {
    return {
      title, kind, lead: "Codex", draft: "", messages: [], panel: null, step: "do", tab: "diff",
      file: fileNames[0], test: mixed, scroll: 0, returnKey: null
    };
  }
  const sessions = [session("Исправить счётчик", "record"), session("Проверить отчёт", "sample")];
  const blank = session("Новая сессия");
  let active = sessions[0], origin = null;
  const archive = () => active.kind === "record";
  const stepButton = id => $("orbitHere").querySelector('[data-step="' + id + '"]');

  function syncInert() {
    const sheet = mobile.matches && !$("detail").hidden;
    const navOpen = drawer.matches && $("sidebar").classList.contains("open");
    $("chat").inert = sheet || navOpen;
    $("sidebar").inert = sheet && !navOpen;
    $("detail").inert = navOpen;
  }
  function nav(open) {
    $("sidebar").classList.toggle("open", open);
    $("menu").setAttribute("aria-expanded", String(open));
    syncInert();
    if (open) $("new").focus();
  }
  $("menu").onclick = () => nav(true);
  $("navClose").onclick = () => { nav(false); $("menu").focus(); };
  mobile.addEventListener("change", syncInert);
  drawer.addEventListener("change", () => nav(false));

  function rail() {
    const list = $("sessions");
    sessions.forEach((s, i) => {
      const item = list.children[i] || marked("chat", s.title, "session", () => choose(s));
      item.setAttribute("aria-current", String(s === active));
      if (!item.isConnected) list.append(item);
    });
  }
  function choose(s) {
    const wasNavigating = $("sidebar").classList.contains("open");
    active.draft = $("command").value;
    active.scroll = $("scroll").scrollTop;
    active = s;
    origin = null;
    nav(false);
    rail();
    $("title").textContent = s === blank ? "С чем поработаем?" : s.title;
    $("crumb").textContent = s.title;
    $("lead").value = s.lead;
    $("command").value = s.draft;
    const sample = s.kind === "sample";
    $("contextLabel").textContent = archive() ? "Далио  /  Архив  /  08.11.2026"
      : sample ? "Учебная сессия" : "Локальный черновик";
    $("brief").hidden = !archive();
    $("brief").querySelector("p").textContent = archive()
      ? "Исправь счётчик. Он включает неудачные запуски в число успешных." : "";
    $("intro").textContent = archive()
      ? "Grok нашёл причину. Codex исправил подсчёт и передал изменения независимому "
        + "проверяющему. Все пять шагов завершены."
      : sample ? "Сессия с примером итогового отчёта."
        : "Опиши задачу своими словами. В этом макете черновик остаётся в сессии.";
    $("orbitHere").replaceChildren();
    $("resultHere").replaceChildren();
    if (archive()) drawOrbit();
    chatMessages();
    quick();
    paintPanel();
    $("scroll").scrollTop = s.scroll;
    if (drawer.matches && s.panel) $("close").focus({preventScroll: true});
    else if (wasNavigating) $("menu").focus({preventScroll: true});
  }
  $("new").onclick = () => { choose(blank); $("command").focus(); };
  $("lead").onchange = () => { active.lead = $("lead").value; };
  $("theme").onclick = () => {
    const theme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = theme;
    $("theme").setAttribute("aria-pressed", String(theme === "light"));
  };
  function chatMessages() {
    const log = $("messages");
    log.replaceChildren();
    for (const [who, text] of active.messages) {
      const line = el("div", "message" + (who === "Вы" ? " mine" : ""));
      line.append(el("b", "", who), document.createTextNode(text));
      log.append(line);
    }
  }
  function drawOrbit() {
    const box = el("section", "orbit");
    box.setAttribute("role", "group");
    box.setAttribute("aria-label", "Орбита Далио");
    const header = el("div", "orbit-header");
    header.append(icon("orbit"), el("h2", "", "Орбита Далио"), el("span", "mono", "5 / 5 шагов"));
    const stage = el("div", "stage");
    stage.append($("orbital-plane").content.cloneNode(true));
    // Same ellipse, centre and rotation as the diagram in the HTML template.
    const tilt = -9 * Math.PI / 180;
    steps.forEach(({id, label, who}, index) => {
      const angle = angles[index];
      const x = 220 * Math.cos(angle), y = 65 * Math.sin(angle);
      const node = button("", "node", () => openStep(id, node));
      node.dataset.step = id;
      node.setAttribute("aria-label", id === "do" ? "Do · Исполнение" : label);
      const description = "Шаг " + (index + 1) + " из 5 · " + who + " · Завершён";
      node.setAttribute("aria-description", description);
      node.title = label + " · Завершён";
      node.style.left = ((300 + x * Math.cos(tilt) - y * Math.sin(tilt)) / 6) + "%";
      node.style.top = ((110 + x * Math.sin(tilt) + y * Math.cos(tilt)) / 2.2) + "%";
      const caption = el("span", "node-label", label);
      caption.append(el("small", "node-role", who));
      node.append(el("i", "planet"), caption);
      stage.append(node);
    });
    const footer = el("div", "orbit-footer"), status = el("span");
    status.append(el("i", "pin-dot"), document.createTextNode("Результат принят"));
    footer.append(status, el("span", "orbit-legend", ATLAS_EVIDENCE.run));
    box.append(header, stage, footer);
    $("orbitHere").append(box);
    const result = button("", "result-summary", () => openStep("do", result));
    result.setAttribute("aria-label", "Открыть результат Do");
    const label = el("span", "summary-label");
    label.append(icon("diff"), document.createTextNode("Результат Do"));
    result.append(label, el("span", "summary-stat", "2 файла"),
      el("span", "summary-stat", "7 тестов"), el("span", "summary-arrow", "↗"));
    $("resultHere").append(result);
  }
  function quick() {
    const askForProof = () => {
      $("command").value = proofQuestion;
      $("send").requestSubmit();
    };
    const items = archive()
      ? [["check", proofQuestion, askForProof], ["meter", "Лимиты", b => tool("Лимиты", b)]]
      : [["orbit", "План цикла", b => tool("План", b)],
        ["memory", "Память", b => tool("Память", b)]];
    $("quick").replaceChildren();
    for (const [mark, label, action] of items) {
      const b = marked(mark, label, "", () => action(b));
      $("quick").append(b);
    }
  }
  function show(panel, control) {
    active.panel = panel;
    origin = control;
    nav(false);
    paintPanel();
    $("close").focus({preventScroll: true});
  }
  function openStep(id, control) {
    active.step = id;
    active.returnKey = id;
    show("step", control);
  }
  function tool(name, control) {
    active.returnKey = null;
    show(name, control);
  }
  document.querySelectorAll("[data-tool]").forEach(b => {
    b.onclick = () => tool(b.dataset.tool, b);
  });
  function close() {
    const fallback = active.returnKey && stepButton(active.returnKey);
    active.panel = null;
    paintPanel();
    const focus = origin?.isConnected && origin.getClientRects().length ? origin : fallback;
    (focus || $("command")).focus();
    origin = null;
  }
  $("close").onclick = close;
  document.addEventListener("keydown", event => {
    if (event.key !== "Escape") return;
    if ($("sidebar").classList.contains("open")) {
      nav(false);
      $("menu").focus();
    } else if (!$("detail").hidden) close();
  });

  function heading(root, title, subtitle, mark) {
    const header = el("div", "detail-heading"), badge = el("i", "vendor"), words = el("div");
    badge.append(icon(mark));
    words.append(el("h2", "", title), el("span", "eye", subtitle));
    header.append(badge, words);
    root.append(header);
  }
  function paintPanel() {
    const pane = $("detail"), root = $("inspection");
    pane.hidden = !active.panel;
    $("workspace").classList.toggle("with-detail", !pane.hidden);
    syncInert();
    $("orbitHere").querySelectorAll(".node").forEach(b => {
      const selected = active.panel === "step" && active.step === b.dataset.step;
      b.setAttribute("aria-pressed", String(selected));
    });
    const arc = $("orbitHere").querySelector(".selected-arc");
    if (arc) {
      const index = active.panel === "step" ? steps.findIndex(s => s.id === active.step) : -1;
      arc.toggleAttribute("hidden", index < 1);
      if (index > 0) {
        const point = a => (300 + 220 * Math.cos(a)) + " " + (110 + 65 * Math.sin(a));
        arc.setAttribute("d", "M " + point(angles[index - 1]) + " A 220 65 0 0 1 "
          + point(angles[index]));
      }
    }
    root.replaceChildren();
    root.scrollTop = 0;
    if (pane.hidden) return;
    if (active.panel !== "step") {
      utility(root);
      return;
    }
    const step = steps.find(s => s.id === active.step);
    const title = step.id === "do" ? "Do · Исполнение" : step.label;
    heading(root, title, step.who + "  /  Запись прогона", "orbit");
    if (step.id === "do") {
      tabs(root);
      return;
    }
    const body = el("div", "inspect-body");
    body.append(el("h3", "", "Результат шага"), el("p", "", step.result));
    body.append(marked("diff", "Открыть Do", "pill", () => openStep("do", stepButton("do"))));
    root.append(body);
  }

  const tabLabels = [
    ["diff", "Изменения", "2"], ["tests", "Тесты", "7"], ["check", "Проверка", ""]
  ];
  function tabs(root) {
    const bar = el("div", "tabs");
    bar.setAttribute("role", "tablist");
    bar.setAttribute("aria-label", "Артефакты Do");
    tabLabels.forEach(([key, label, count], index) => {
      const tab = button(label, "", () => {
        active.tab = key;
        paintPanel();
        $("tab-" + key).focus();
      });
      tab.id = "tab-" + key;
      tab.setAttribute("role", "tab");
      tab.setAttribute("aria-selected", String(active.tab === key));
      tab.setAttribute("aria-controls", "artifact");
      tab.tabIndex = active.tab === key ? 0 : -1;
      if (count) {
        const badge = el("span", "count", count);
        badge.setAttribute("aria-hidden", "true");
        tab.append(badge);
      }
      tab.onkeydown = event => {
        const order = {ArrowRight: (index + 1) % 3, ArrowLeft: (index + 2) % 3, Home: 0, End: 2};
        if (!Object.hasOwn(order, event.key)) return;
        event.preventDefault();
        $("tab-" + tabLabels[order[event.key]][0]).click();
      };
      bar.append(tab);
    });
    const body = el("section", "inspect-body");
    body.id = "artifact";
    body.setAttribute("role", "tabpanel");
    body.setAttribute("aria-labelledby", "tab-" + active.tab);
    root.append(bar, body);
    if (active.tab === "diff") diff(body);
    else if (active.tab === "tests") tests(body);
    else verification(body);
  }

  function codeLine(source, old, fresh) {
    const sign = source[0], line = el("div", sign === "+" ? "plus" : sign === "-" ? "minus" : "");
    const code = el("code");
    code.append(document.createTextNode(sign));
    const tokens = /("(?:[^"\\]|\\.)*"|\b(?:def|return|for|in|if|and|import|from|class|with)\b)/g;
    for (const token of source.slice(1).split(tokens)) {
      if (token.startsWith('"')) code.append(el("span", "syntax-string", token));
      else if (/^(def|return|for|in|if|and|import|from|class|with)$/.test(token)) {
        code.append(el("span", "syntax-keyword", token));
      } else code.append(document.createTextNode(token));
    }
    line.append(el("i", "", old), el("i", "", fresh), code);
    return line;
  }
  function diff(body) {
    const head = el("div", "statline");
    head.append(el("span", "", "Файлы снимка"), el("span", "mono", "+68  −2"));
    body.append(head);
    for (const name of fileNames) {
      const {lines} = ATLAS_EVIDENCE.files[name];
      const row = button("", "file-row", () => {
        active.file = name;
        paintPanel();
        document.querySelector('.file-row[aria-pressed="true"]').focus();
      });
      row.setAttribute("aria-label", name);
      row.setAttribute("aria-pressed", String(active.file === name));
      const stats = el("small");
      const added = lines.filter(s => s.startsWith("+")).length;
      const removed = lines.filter(s => s.startsWith("-")).length;
      stats.append(el("span", "ins", "+" + added), document.createTextNode("  "),
        el("span", "del", "−" + removed));
      row.append(icon("file"), el("code", "", name), stats);
      body.append(row);
    }
    const box = el("div", "codebox"), title = el("div", "diff-head");
    title.append(el("span", "", active.file), el("span", "", "Python"));
    const code = el("div", "diff-lines");
    code.tabIndex = 0;
    code.setAttribute("aria-label", "Содержимое diff");
    let old = 0, fresh = 0;
    for (const source of ATLAS_EVIDENCE.files[active.file].lines) {
      const before = source[0] === "+" ? "" : ++old;
      const after = source[0] === "-" ? "" : ++fresh;
      code.append(codeLine(source, before, after));
    }
    box.append(title, code);
    body.append(box);
    const card = el("div", "check-card");
    card.append(el("strong", "", "✓  Независимая проверка"),
      el("p", "", "Отдельный Codex подтвердил снимок двух файлов."));
    body.append(card);
  }
  function sourceFor(name) {
    const source = ATLAS_EVIDENCE.files[testFile].lines
      .filter(s => s[0] !== "-").map(s => s.slice(1));
    const start = source.findIndex(s => s.startsWith("    def " + name + "("));
    const end = source.findIndex((s, i) => i > start && s.startsWith("    def "));
    return source.slice(start, end < 0 ? source.length : end).join("\n").trimEnd();
  }
  function tests(body) {
    const card = el("div", "check-card");
    card.append(el("strong", "", "7 / 7 прошли"),
      el("p", "", "Отдельный прогон результата · Windows AppContainer"));
    const source = sourceFor(active.test);
    const name = testLabels.find(([id]) => id === active.test)[1];
    const selected = el("div", "test-proof");
    selected.append(el("span", "eyebrow", testFile), el("h3", "", name),
      el("code", "digest", active.test));
    const assertion = source.split("\n").find(line => line.includes("self.assert"));
    selected.append(el("code", "assertion", assertion.trim()));
    if (active.test === mixed) {
      selected.append(el("p", "",
        "12 входных строк. До исправления счётчик возвращал 12, после — 2."));
    }
    const full = el("details", "source-detail");
    full.append(el("summary", "", "Исходный код теста"), el("pre", "test-source", source));
    body.append(card, selected, full, el("h3", "", "Все тесты"));
    testLabels.forEach(([id, label]) => {
      const row = marked("check", label, "test-row", () => {
        active.test = id;
        paintPanel();
        document.querySelector('.test-row[aria-pressed="true"]').focus();
      });
      row.setAttribute("aria-pressed", String(id === active.test));
      body.append(row);
    });
  }
  function verification(body) {
    const card = el("div", "check-card");
    card.append(el("strong", "", "✓  Verified"), el("p", "", "Codex · instance-role-checker"));
    body.append(card, el("h3", "", "Что проверено"),
      el("p", "", "Проверяющий получил снимок изменений. Семь тестов результата прошли отдельно."),
      el("h3", "", "SHA-256 снимка"), el("code", "digest", ATLAS_EVIDENCE.manifest),
      el("h3", "", "Решение владельца"),
      el("p", "", "codex-test · approve · 8 ноября 2026, 20:29 МСК"));
  }

  function memoryText() {
    if (archive()) {
      return "Критерий задачи — считать только строки с точным исходом succeeded. "
        + "Источник — принятая задача счётчика.";
    }
    if (active.kind === "sample") {
      return "В отчёт включаются принятые результаты за неделю. Источник — учебная сессия.";
    }
    return active.messages[0]?.[1] || "В этой сессии пока нет решений.";
  }
  function utility(root) {
    const name = active.panel, body = el("div", "inspect-body");
    const marks = {
      Grok: "grok", Codex: "terminal", План: "orbit", Память: "memory", Лимиты: "meter"
    };
    heading(root, name, active.title, marks[name]);
    if (name === "Лимиты") {
      for (const vendor of ["Codex", "Grok"]) {
        const row = el("div", "check-card");
        row.append(el("b", "", vendor), el("p", "", "Нет показаний"));
        body.append(row);
      }
    } else if (name === "Память") {
      body.append(el("h3", "", "Контекст сессии"), el("p", "", memoryText()));
    } else if (name === "План") {
      steps.forEach((step, index) => {
        const title = (index + 1) + ". " + step.label;
        if (archive()) {
          body.append(button(title + " · " + step.who, "file-row",
            () => openStep(step.id, stepButton(step.id))));
        } else body.append(el("p", "", title));
      });
    } else if (archive()) {
      const id = name === "Grok" ? "diagnose" : "do";
      const result = id === "diagnose" ? steps[2].result
        : "Исполнитель и отдельный проверяющий Do.";
      body.append(el("h3", "", "Роль в записи"), el("p", "", result));
      body.append(marked("orbit", "Открыть шаг", "pill", () => openStep(id, stepButton(id))));
    } else {
      body.append(el("p", "", "В этой сессии нет записанных действий харнесса."));
    }
    root.append(body);
  }
  function reply(text, answer) {
    active.messages.push(["Вы", text], ["Атлас", answer]);
    chatMessages();
    $("scroll").scrollTop = $("scroll").scrollHeight;
  }
  function answerDo(text, tab, answer) {
    active.tab = tab;
    reply(text, answer);
    openStep("do", $("command"));
  }
  $("send").onsubmit = event => {
    event.preventDefault();
    const input = $("command"), text = input.value.trim();
    if (!text) return;
    const query = text.toLocaleLowerCase("ru");
    input.value = "";
    active.draft = "";
    if (archive() && /тест|провер.*исправ/.test(query)) {
      active.test = /исключ|failed/.test(query) ? excluded : mixed;
      const answer = active.test === mixed
        ? "Тест mixed_input проверяет 12 строк. Ожидается 2 успешных исхода; "
          + "прежняя реализация возвращала 12. Справа видна проверка и доступен исходный код."
        : "Тест исключения исходов проверяет failed, unknown, verification_failed "
          + "и записи без outcome. В каждом случае ожидается 0.";
      answerDo(text, "tests", answer);
      return;
    }
    if (archive() && /изменени|изменил|изменилось|diff|дифф|патч/.test(query)) {
      answerDo(text, "diff", "В снимке Do два файла: реализация счётчика и её тесты. "
        + "Открыл изменения этой попытки.");
      return;
    }
    if (archive() && /принима|принят|вердикт|заключени/.test(query)) {
      answerDo(text, "check", "Это архив принятого результата. Отдельный Codex подтвердил снимок. "
        + "Решение записано от имени codex-test.");
      return;
    }
    if (archive() && /причин|диагноз/.test(query)) {
      reply(text, steps[2].result);
      openStep("diagnose", input);
      return;
    }
    const panels = [["лимит", "Лимиты"], ["памят", "Память"], ["план", "План"],
      ["grok", "Grok"], ["codex", "Codex"]];
    const desired = panels.find(([key]) => query === key
      || query.startsWith("покажи " + key) || query.startsWith("открой " + key));
    if (desired) {
      reply(text, "Открыл панель «" + desired[1] + "».");
      tool(desired[1], input);
      return;
    }
    if (active === blank) {
      const next = session(text);
      sessions.push(next);
      choose(next);
      reply(text, "Предлагаю Далио. План и участники доступны в панелях этой учебной сессии.");
      return;
    }
    reply(text, "В макете можно открыть план, лимиты, память или участника. "
      + "В сессии счётчика можно спросить о тесте исправления.");
  };
  if (location.hash === "#do") {
    active.panel = "step";
    active.returnKey = "do";
  }
  choose(active);
})();
