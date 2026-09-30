"""The bench page of the «Схема» browser tests, on the REAL flow routes.

`desk.js`, the boot module that will mount the panel and own the doors, does not exist yet. So
these tests open the desk's own page (`/panel/desk.html`) on a real server over a seeded project,
import the REAL model and the REAL renderer from it, and drive them with a host of a few lines
written here: it holds `state.schema`, reduces every event with the real `stepFlow`, redraws through
the real focus net, and PERFORMS each ask on the real routes with `fetch` and the session's token,
as the desk's transport will (`GET /command/workflows/<id>/flow`, `POST` the same path,
`GET /command/workflows`). The only stand-in is the wiring `desk.js` will do, and it is exactly what
this host reimplements; nothing on the wire is faked, so what a test reads back is what the server
holds.

Not a test module: pytest does not collect it (no `test_` prefix). The fixtures live here and each
test file imports them, because the conftest's surface is pinned by a guard.
"""
from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from playwright.sync_api import Browser, Page, expect

from browser_tests.desk_wizard_bench import desk_url  # noqa: F401  (the fixture, re-exported)

#: Evaluated once on the served page. `host.log` is every ask the model made, in order;
#: `host.answers` is what the server said to each; `host.lose` is the number of write answers to
#: swallow AFTER the write has landed (the answer is then `unknown`, as a dropped connection is).
HOST_JS = """
async () => {
  const model = await import("/panel/desk-flow-model.js");
  const {mountFlow} = await import("/panel/desk-flow.js");
  const edits = await import("/panel/desk-flow-edits.js");
  const quick = await import("/panel/desk-quickcycle.js");
  const shape = await import("/panel/desk-flow-shape.js");
  const focus = await import("/panel/studio-focus.js");
  const i18n = await import("/panel/studio-i18n.js");
  const host = {log: [], answers: [], state: null, mount: null, renders: 0, lose: 0, token: null,
    model, edits, quick, shape, i18n};
  //: The canvas is the Studio's, and so is the sheet that lays it out (the desk's own sheet does
  //: not style it yet): without it the edge layer would lie over the steps and swallow every press.
  const sheet = document.createElement("link");
  sheet.rel = "stylesheet";
  sheet.href = "/panel/studio.css";
  document.head.append(sheet);
  await new Promise((resolve) => { sheet.onload = resolve; sheet.onerror = resolve; });
  const enc = encodeURIComponent;
  const token = async () => {
    if (host.token === null) {
      host.token = (await (await fetch("/command/session")).json()).csrf_token;
    }
    return host.token;
  };
  const codeOf = (payload) => payload?.error?.code ?? "refused";
  const answer = async (response) => {
    const payload = await response.json().catch(() => null);
    return response.ok ? {status: "accepted", code: null, payload}
      : {status: "refused", code: codeOf(payload), payload};
  };
  const reads = {flowRead: (id) => `/command/workflows/${enc(id)}/flow`,
    workflows: () => "/command/workflows"};
  const wire = async (ask) => {
    try {
      if (ask.door === "read") {
        return await answer(await fetch(reads[ask.target](ask.subject), {cache: "no-store"}));
      }
      const response = await fetch(`/command/workflows/${enc(ask.subject)}/flow`, {method: "POST",
        body: JSON.stringify(ask.body), headers: {"Content-Type": "application/json",
          "X-Conduct-CSRF": await token()}});
      const result = await answer(response);
      if (host.lose > 0) {
        host.lose -= 1;
        return {status: "unknown", code: null, payload: null};
      }
      return result;
    } catch (_error) {
      return {status: "unknown", code: null, payload: null};
    }
  };
  const render = () => {
    const held = focus.focusTarget();
    host.renders += 1;
    mountFlow(host.mount, host.state, {onFlow: (event) => dispatch(event)});
    focus.restoreFocus(host.mount, held);
  };
  const perform = (ask) => {
    host.log.push(ask);
    wire(ask).then((result) => {
      host.answers.push({ask, result});
      dispatch({type: "answered", ask, result});
    });
  };
  const dispatch = (event) => {
    const step = model.stepFlow(host.state.schema, event);
    host.state = {...host.state, schema: step.state};
    render();
    step.asks.forEach(perform);
  };
  Object.assign(host, {dispatch, wire});
  host.start = ({locale, nonce}) => {
    document.getElementById("flowBench")?.remove();
    host.mount = document.createElement("div");
    host.mount.id = "flowBench";
    document.body.append(host.mount);
    Object.assign(host, {log: [], answers: [], renders: 0, lose: 0});
    host.state = {locale, schema: model.initialFlow({nonce})};
    dispatch({type: "cycles"});
  };
  host.setLocale = (locale) => { host.state = {...host.state, locale}; render(); };
  host.view = () => JSON.parse(JSON.stringify(model.flowView(host.state.schema)));
  host.say = (key, params) => i18n.message(host.state.locale, key, params || {});
  host.held = () => JSON.parse(JSON.stringify(host.state.schema.write.held));
  //: The last answer of a write or a read that the server really gave, as plain data.
  host.last = (name) => JSON.parse(JSON.stringify(
    host.answers.filter((row) => row.ask.name === name).at(-1)?.result?.payload ?? null));
  //: What the server holds for a cycle now, read by the test itself (another window).
  host.server = async (id) => (await wire({door: "read", target: "flowRead", subject: id})).payload;
  //: A write by another window: it names the digest it read and writes `flow` over the draft.
  host.other = async (id, flow) => {
    const state = await host.server(id);
    const body = {source: {flow}, publish_revision: null, binding: null,
      ...(state.draft_digest === null ? {expected_absent: true}
        : {expected_digest: state.draft_digest})};
    return wire({door: "write", target: "flow", subject: id, body});
  };
  window.host = host;
}
"""


class Flow:
    """One page with the host installed, in one language, with its problem log."""

    def __init__(self, page: Page, problems: list[str]) -> None:
        self.page = page
        self.problems = problems

    def call(self, method: str, *args: Any) -> Any:
        """One method of `window.host`, awaited."""
        return self.page.evaluate("([name, args]) => window.host[name](...args)",
                                  [method, list(args)])

    def start(self, locale: str = "en") -> None:
        """A panel with nothing opened, its nonce a fresh one (so its cycle ids are its own)."""
        self.call("start", {"locale": locale, "nonce": uuid.uuid4().hex})

    def open(self, workflow_id: str | None = None, title: str = "New cycle") -> str:
        """Open a cycle by id (a fresh `cycle-<8 hex>` when none is given) and wait for the read."""
        name = workflow_id or f"cycle-{uuid.uuid4().hex[:8]}"
        self.dispatch(type="open", workflowId=name, title=title)
        expect(self.root).to_have_attribute("data-flow-phase", "ready")
        return name

    def dispatch(self, **event: Any) -> None:
        self.call("dispatch", event)

    def say(self, key: str, **params: str) -> str:
        return self.call("say", key, params)

    def view(self) -> dict[str, Any]:
        return self.call("view")

    def held(self) -> dict[str, Any]:
        return self.call("held")

    def last(self, name: str) -> Any:
        return self.call("last", name)

    def server(self, workflow_id: str) -> dict[str, Any]:
        return self.call("server", workflow_id)

    def log(self) -> list[dict[str, Any]]:
        return self.page.evaluate("() => window.host.log.map((ask) => ({id: ask.id, "
                                  "name: ask.name, subject: ask.subject}))")

    @property
    def root(self):
        return self.page.locator("[data-flow]")

    def control(self, key: str):
        return self.page.locator(f'[data-focus="{key}"]')

    def settle(self, state: str = "saved") -> None:
        """Wait until the panel says its cycle is `state` (saved, by default)."""
        expect(self.root).to_have_attribute("data-flow-save", state)

    def add(self, kind: str) -> None:
        """Press a palette button: the step is added after the selected one and written."""
        self.page.locator(f'[data-add-kind="{kind}"]').click()
        self.settle()

    def select_step(self, step_id: str) -> None:
        self.page.locator(f'[data-node-id="{step_id}"]').click()
        expect(self.page.locator("[data-flow-inspector]")).to_have_attribute("data-selected",
                                                                               step_id)

    def type_into(self, key: str, text: str) -> None:
        """Type one character at a time, so every keystroke goes through the host's redraw."""
        field = self.control(key)
        field.click()
        field.press_sequentially(text)

    def set_field(self, key: str, text: str) -> None:
        """Replace a field's text and leave it: one typed text, one committed edit."""
        field = self.control(key)
        field.fill(text)
        field.blur()

    def diag_codes(self) -> list[str]:
        return self.page.eval_on_selector_all(
            "[data-flow-diag] li[data-diag]", "(nodes) => nodes.map((n) => n.dataset.diag)")


def watch(page: Page) -> list[str]:
    problems: list[str] = []

    def heard(message: Any) -> None:
        #: The browser logs a refusal it was sent on purpose (a conflict, a refused write).
        expected = "Failed to load resource" in message.text and any(
            f"status of {code}" in message.text for code in (409, 422))
        if message.type == "error" and not expected:
            problems.append(message.text)

    page.on("console", heard)
    page.on("pageerror", lambda error: problems.append(str(error)))
    return problems


@pytest.fixture(params=["en", "ru"])
def lang(request: pytest.FixtureRequest) -> str:
    """The reader's language: every test of the panel is run in both."""
    return str(request.param)


@pytest.fixture
def flow(chromium: Browser, desk_url: str, lang: str) -> Iterator[Flow]:  # noqa: F811
    """The desk's page with the real model, renderer and routes behind a small host."""
    context = chromium.new_context(viewport={"width": 1300, "height": 1600})
    try:
        page = context.new_page()
        page.set_default_timeout(8000)
        problems = watch(page)
        page.goto(f"{desk_url}/panel/desk.html", wait_until="load")
        page.evaluate(HOST_JS)
        bench = Flow(page, problems)
        bench.start(lang)
        yield bench
        assert problems == []
    finally:
        context.close()
