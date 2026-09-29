"""The bench page of the wizard's browser tests.

`desk.js`, the boot module that will mount the wizard and own the doors, does not exist yet. So
these tests open any served page (the desk's own shell, `/panel/desk.html`), import the REAL
model and the REAL renderer from the server, and drive them with a host of a few lines written
here: it holds `state.wizard`, reduces every event with the real `stepWizard`, redraws through
the real focus net, logs each ask and answers it from a table the test hands over. The only
stand-in is the wiring `desk.js` will do, and it is exactly what this host reimplements.

Not a test module: pytest does not collect it (no `test_` prefix). The fixtures live here and
each test file imports them, because the conftest's surface is pinned by a guard.
"""
from __future__ import annotations

import threading
from collections.abc import Iterator
from typing import Any

import pytest
from playwright.sync_api import Browser, Page

from conductor import server
from tests.test_store import good_lane, write_project

#: Evaluated once on the served page. `host.log` is every ask the model made, in order; `auto`
#: maps an ask name to a result, or to a table of results by ask subject with "*" as default.
HOST_JS = """
async () => {
  const wiz = await import("/panel/desk-wizard-model.js");
  const {mountWizard} = await import("/panel/desk-wizard.js");
  const focus = await import("/panel/studio-focus.js");
  const i18n = await import("/panel/studio-i18n.js");
  const host = {log: [], auto: {}, closed: 0, renders: 0, state: null, mount: null, wiz, i18n};
  const settle = async () => { for (let at = 0; at < 8; at += 1) await Promise.resolve(); };
  const render = () => {
    const held = focus.focusTarget();
    host.renders += 1;
    mountWizard(host.mount, host.state, {onWizard: (event) => dispatch(event),
      onWizardClose: () => { host.closed += 1; }});
    focus.restoreFocus(host.mount, held);
  };
  const perform = (ask) => {
    host.log.push(ask);
    const rules = host.auto[ask.name];
    const result = rules && (rules[ask.subject] ?? rules["*"]);
    if (result) Promise.resolve().then(() => dispatch({type: "answered", ask, result}));
  };
  const dispatch = (event) => {
    const step = wiz.stepWizard(host.state.wizard, event);
    host.state = {...host.state, wizard: step.state};
    render();
    step.asks.forEach(perform);
    return settle();
  };
  host.dispatch = dispatch;
  host.open = async ({locale, opening, auto}) => {
    document.getElementById("wizardBench")?.remove();
    host.mount = document.createElement("div");
    host.mount.id = "wizardBench";
    document.body.append(host.mount);
    Object.assign(host, {log: [], auto: auto || {}, closed: 0, renders: 0});
    host.state = {locale, wizard: wiz.initialWizard({starterId: null, viewMode: false,
      newTaskId: "task-bench", ...opening})};
    return dispatch({type: "open"});
  };
  host.answer = (name, result, subject) => {
    const ask = host.log.filter((one) => one.name === name
      && (subject === undefined || one.subject === subject)).at(-1);
    if (!ask) throw new Error(`no ask named ${name} was made`);
    return dispatch({type: "answered", ask, result});
  };
  host.setLocale = (locale) => { host.state = {...host.state, locale}; render(); };
  host.snapshot = () => JSON.parse(JSON.stringify(host.state.wizard));
  host.asks = () => host.log.map((ask) => [ask.id, ask.name, ask.subject]);
  host.say = (key, params) => i18n.message(host.state.locale, key, params || {});
  window.host = host;
}
"""


def _watch(page: Page) -> list[str]:
    problems: list[str] = []
    page.on("console", lambda message: problems.append(message.text)
            if message.type == "error" else None)
    page.on("pageerror", lambda error: problems.append(str(error)))
    return problems


class Bench:
    """One page with the host installed, its problem log and its request log."""

    def __init__(self, page: Page, problems: list[str], requests: list[tuple[str, str]]) -> None:
        self.page = page
        self.problems = problems
        self.requests = requests

    def call(self, method: str, *args: Any) -> Any:
        """One method of `window.host`, awaited."""
        return self.page.evaluate("([name, args]) => window.host[name](...args)",
                                  [method, list(args)])

    def open(self, locale: str = "en", *, starter: str | None = None, view: bool = False,
             auto: dict[str, Any] | None = None, **opening: Any) -> None:
        """Open a wizard; `auto` answers the asks it makes as they are made."""
        self.call("open", {"locale": locale, "auto": auto or {},
                           "opening": {"starterId": starter, "viewMode": view, **opening}})

    def dispatch(self, **event: Any) -> None:
        self.call("dispatch", event)

    def answer(self, name: str, payload: Any = None, *, subject: str | None = None,
               status: str = "accepted", code: str | None = None) -> None:
        self.call("answer", name, {"status": status, "code": code, "payload": payload}, subject)

    def wizard(self) -> dict[str, Any]:
        return self.call("snapshot")

    def asks(self) -> list[list[str]]:
        return self.call("asks")

    def say(self, key: str, **params: str) -> str:
        return self.call("say", key, params)

    def root(self):
        return self.page.locator("[data-wizard]")

    def control(self, key: str):
        return self.page.locator(f'[data-focus="{key}"]')

    def text(self, selector: str) -> str:
        return self.page.locator(selector).inner_text()

    def type_into(self, key: str, text: str) -> None:
        """Type one character at a time, so every keystroke goes through the host's redraw."""
        field = self.control(key)
        field.click()
        field.press_sequentially(text)


@pytest.fixture(scope="session")
def desk_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """A real server over a seeded project; the wizard's modules are served from it."""
    root = write_project(tmp_path_factory.mktemp("desk-wizard"), lanes={"claude": good_lane()})
    httpd = server.build(root, 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address[:2]
    try:
        yield f"http://{host}:{port}"
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()
        assert not thread.is_alive(), "desk server did not stop"


@pytest.fixture
def bench(chromium: Browser, desk_url: str) -> Iterator[Bench]:
    """The desk's shell page with the real model and renderer behind a small host."""
    context = chromium.new_context(viewport={"width": 1100, "height": 1500})
    try:
        page = context.new_page()
        page.set_default_timeout(8000)
        problems = _watch(page)
        requests: list[tuple[str, str]] = []
        page.on("request", lambda request: requests.append((request.method, request.url)))
        page.goto(f"{desk_url}/panel/desk.html", wait_until="load")
        page.evaluate(HOST_JS)
        yield Bench(page, problems, requests)
    finally:
        context.close()
