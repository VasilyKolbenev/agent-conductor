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
from playwright.sync_api import Browser, Page, expect

from conductor import server
from tests.desk_wizard_node import fixture
from tests.test_store import good_lane, write_project

#: Evaluated once on the served page. `host.log` is every ask the model made, in order; `auto`
#: maps an ask name to a result, or to a table of results by ask subject with "*" as default.
#: `host.fake`, when a test sets it, is asked first: a function of the ask that answers the ones
#: it knows (a door with a memory) and returns undefined for the rest, which fall to `auto`.
HOST_JS = """
async () => {
  const wiz = await import("/panel/desk-wizard-model.js");
  const {mountWizard} = await import("/panel/desk-wizard.js");
  const focus = await import("/panel/studio-focus.js");
  const i18n = await import("/panel/studio-i18n.js");
  const host = {log: [], auto: {}, fake: null, closed: 0, renders: 0, state: null, mount: null,
    wiz, i18n};
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
    const result = host.fake?.(ask) ?? (rules && (rules[ask.subject] ?? rules["*"]));
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


#: The fake flow door (see `Bench.door`). `host.standing` is the table of drafts it keeps, so a
#: test may read what stands after the wizard has written.
DOOR_JS = """
(data) => {
  const standing = {...data.drafts}, left = {lose: data.lose, race: data.race};
  window.host.standing = standing;
  window.host.fake = (ask) => {
    if (ask.name !== "flow" && ask.name !== "flow_read") return undefined;
    const held = standing[ask.subject] ?? null;
    const state = data.flows[ask.subject];
    const answer = (payload) => ({status: "accepted", code: null, payload});
    if (ask.name === "flow_read") {
      return answer(held === null ? {...data.none, workflow_id: ask.subject}
        : {...state, source: "draft", draft_digest: held});
    }
    if (left.race !== null) {
      standing[ask.subject] = left.race;
      left.race = null;
    }
    const sent = ask.body.expected_digest ?? null;
    const absent = ask.body.expected_absent === true;
    if (absent ? standing[ask.subject] != null : sent !== standing[ask.subject]) {
      return {status: "refused", code: "draft_conflict", payload: null};
    }
    standing[ask.subject] = state.draft_digest ?? "sha256:" + "a".repeat(64);
    if (left.lose > 0) {
      left.lose -= 1;
      return {status: "unknown", code: null, payload: null};
    }
    return answer({...state, source: "draft", draft_digest: standing[ask.subject]});
  };
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

    def bodies(self, name: str) -> list[Any]:
        """The body of every ask of one name, in the order they were made."""
        return self.page.evaluate(
            "(name) => window.host.log.filter((ask) => ask.name === name).map((ask) => ask.body)",
            name)

    def door(self, flows: dict[str, Any], drafts: dict[str, str | None], *, lose: int = 0,
             race: str | None = None) -> None:
        """Put a fake flow door in front of the answers: it judges `expected_*` like spec 7.1.3.

        `drafts` maps a workflow id to the digest of the draft standing for it (a missing id or
        null: none). A read answers the standing draft or `source: none`; a write whose
        expectation differs from what stands is a `draft_conflict`, and one that agrees leaves
        a new draft. `flows` maps a workflow id to the `FlowState` its write answers with.
        `lose` is how many writes are lost (answered `unknown`, though they land); `race` is the
        digest another window's draft takes between a read and the next write, which refuses it.
        """
        self.page.evaluate(DOOR_JS, {"flows": flows, "drafts": drafts, "lose": lose,
                                     "race": race,
                                     "none": fixture("wizard", "flow_state_none.json")})

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


def ok(payload: Any) -> dict[str, Any]:
    """An accepted answer, shaped like the one door's own."""
    return {"status": "accepted", "code": None, "payload": payload}


def no_draft(workflow_id: str) -> dict[str, Any]:
    """The answer of `GET …/flow` for a workflow with neither a draft nor a revision."""
    return ok({**fixture("wizard", "flow_state_none.json"), "workflow_id": workflow_id})


#: What the flow read answers for the ready cycles unless a test says otherwise: nothing stands.
NO_DRAFTS = {name: no_draft(name) for name in (
    "desk-standard", "desk-short", "desk-starter-docs")}


def wizard_reads(**over: Any) -> dict[str, Any]:
    """The table a host answers the opening reads from: every read the wizard makes at open.

    Each value is a result, or a table of results by ask subject with "*" as the default.
    Override a read by name; a plain result is wrapped as the default for every subject.
    """
    table: dict[str, Any] = {
        "git": ok(fixture("wizard", "git_repo.json")),
        "workflows": ok(fixture("wizard", "workflows.json")),
        "runs": ok(fixture("wizard", "runs.json")),
        "cycle_read": ok(fixture("wizard", "project_cycle_none.json")),
        "tasks": ok(fixture("wizard", "tasks.json")),
        "quotas": ok(fixture("wizard", "quotas.json")),
        "documents": ok(fixture("wizard", "documents.json")),
        "document": ok(fixture("wizard", "document.json")),
        "flow_read": NO_DRAFTS}
    table.update(over)
    return {name: {"*": value} if "status" in value else value for name, value in table.items()}


def to_step(bench: Bench, lang: str, step: str, *, starter: str | None = None,
            view: bool = False, reads: dict[str, Any] | None = None) -> None:
    """Open the wizard, fill step 1 and press Next until `step` is on screen.

    The answers must let every step on the way be left: for the cycle step the flow of the
    preselected card, for the roles step the harness roster and the quotas.
    """
    bench.open(lang, starter=starter, view=view, auto=reads or wizard_reads())
    bench.type_into("wizard:title", "Fix login")
    bench.type_into("wizard:idea" if starter else "wizard:brief", "Make it work.")
    for following in ("materials", "cycle", "roles"):
        if bench.root().get_attribute("data-step") == step:
            break
        expect(bench.control("wizard:next")).to_be_enabled()
        bench.control("wizard:next").click()
        expect(bench.root()).to_have_attribute("data-step", following)


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
