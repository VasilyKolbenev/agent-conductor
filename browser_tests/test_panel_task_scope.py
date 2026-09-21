"""The Cockpit files a graphless run's work under that run's task, and only that one.

A run that follows no plan is proposed on from the Cockpit's composer, which used to
build dispatch and review arguments from the typed fields alone -- so on a run bound
to a task it could only send no scope, and the server rightly refuses that. The
scope is not something a person should type: it is the run's frozen task binding,
read from the same authoritative run read the Cockpit already makes, attached to
the body before the POST, and shown as fixed context by the task's name.

Driven in Chromium against the real server over real runs. Task beta's scope is NOT
its id, so nothing here can pass by sending one where the other belongs. Covered:
two tasks, dispatch and review, a run with no task, a task whose record does not
read, a switch while composing, late answers and a late read -- including a
Confirm answer landing after another proposal was made on the same run -- an
answer echoing a different payload, and a binding that does not read: refused
whole by the server, and judged by the Cockpit itself, to the task contract's own
length bound, when a payload carries one.
"""
from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from playwright.sync_api import Browser, Page, Route

from conductor import server
from conductor.command.adapters import AdapterRegistry
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.task_contracts import TaskRecord
from conductor.command.task_store import TaskStore

from tests.test_command_run_store import CONFIG, NOW, a_run
from tests.test_command_schema_doubles import DeepPlanAdapter
from tests.test_store import good_lane, write_project

TOKEN = "browser-only-process-token"
ALPHA, BETA, GHOST = "task-alpha", "task-beta", "task-ghost"
#: Each task's work scope. Beta's differs from its id on purpose.
SCOPES = {ALPHA: ALPHA, BETA: "scope-beta", GHOST: GHOST}
TITLES = {ALPHA: "Alpha login fix", BETA: "Beta search"}
#: run -> the task it froze. Ghost's task has no record, so its title cannot be read.
RUNS = {"run-alpha": ALPHA, "run-beta": BETA, "run-ghost": GHOST, "run-legacy": None}
BROKEN = "run-broken"
TYPED = {
    "dispatch": {"work_item_id": "work-001", "instruction_ref": "instruction-001",
                 "profile": "implement", "artifact_refs": ["artifact-001"],
                 "output_limit_profile": "small"},
    "review": {"work_item_id": "work-001", "target_artifact_refs": ["input-ref"],
               "result_artifact_ref": "review-result", "review_profile": "quality"},
}
NO_TASK = "No task: this run files its work without one."


def shown(task: str) -> str:
    return f"Task: {TITLES[task]} ({task})"


@contextmanager
def serve(tmp_path, adapters) -> Iterator[str]:
    """The Cockpit over two titled tasks, a bound task with no record, runs for
    each, a run with no task, and one whose frozen binding is half.

    The registry is the caller's: the module beside this one serves an adapter
    that declares one more capability, and a fixture's signature the reviewer's
    own reproducer imports does not change to say so.
    """
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    tasks = TaskStore(root)
    for task_id, title in TITLES.items():
        tasks.create_task(TaskRecord(task_id=task_id, title=title,
                                     work_scope=SCOPES[task_id], created_at=NOW))
    store = RunStore(root)
    frozen = {run_id: (CONFIG if task is None else
                       {**CONFIG, "task": {"id": task, "work_scope": SCOPES[task]}})
              for run_id, task in RUNS.items()}
    frozen[BROKEN] = {**CONFIG, "task": {"id": ALPHA}}
    for run_id, config in frozen.items():
        store.create_run(a_run(run_id=run_id, mode="confirm",
                               config_digest=snapshot_digest(config)), config)
    httpd = server.build(root, 0, registry=AdapterRegistry(adapters),
                         token_factory=lambda _size: TOKEN)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address
    try:
        yield f"http://{host}:{port}/panel/index.html"
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()
        assert not thread.is_alive(), "cockpit server did not stop"


@pytest.fixture
def cockpit_url(tmp_path) -> Iterator[str]:
    with serve(tmp_path, [DeepPlanAdapter()]) as url:
        yield url


class _Recorder:
    """Every proposal the page POSTs: its run and its body."""

    def __init__(self, page: Page) -> None:
        self.rows: list[tuple[str, dict]] = []
        page.on("request", self._take)

    def _take(self, request) -> None:
        if request.method == "POST" and request.url.endswith("/proposals"):
            run = request.url.split("/command/runs/")[1].split("/")[0]
            self.rows.append((run, json.loads(request.post_data)))


def _open(chromium: Browser, url: str) -> tuple[Page, _Recorder]:
    page = chromium.new_context().new_page()
    recorder = _Recorder(page)
    page.goto(url, wait_until="load")
    return page, recorder


def _load(page: Page, run_id: str) -> None:
    page.locator("#commandRunId").fill(run_id)
    page.get_by_role("button", name="Load run").click()


def _context(page: Page, state: str) -> str:
    context = page.locator(f'.command-task-context[data-task-state="{state}"]')
    context.wait_for()
    return context.text_content()


def _selected(page: Page) -> str:
    return page.locator(".command-summary .command-fact").first.text_content()


def _ready(page: Page) -> None:
    page.wait_for_function("() => document.querySelector('#commandCockpit')"
                           ".dataset.phase === 'ready'")


def _fill(page: Page, capability: str, rationale: str) -> None:
    form = page.locator(".command-proposal-form")
    form.locator('select[name="capability"]').select_option(capability)
    form.locator('input[name="scope"]').fill("src, tests")
    form.locator('input[name="rationale"]').fill(rationale)
    for name, value in TYPED[capability].items():
        control = form.locator(f'[name="argument:{name}"]')
        if control.evaluate("node => node.tagName") == "SELECT":
            control.select_option(value)
        else:
            control.fill(", ".join(value) if isinstance(value, list) else value)


def _compose(page: Page, capability: str, rationale: str = "Carry the work out.") -> None:
    _fill(page, capability, rationale)
    page.locator('.command-proposal-form button[type="submit"]').click()
    page.locator('[data-proposal-state="created"]').wait_for()


def _held(page: Page, pattern: str) -> tuple[list[Route], threading.Event]:
    """Hold the first request matching `pattern`; pass every later one through.

    A pass-through, never an unroute: unrouting a page's last route turns
    interception off under reads the page is starting."""
    held: list[Route] = []
    released = threading.Event()

    def hold(route: Route) -> None:
        if released.is_set() or held:
            route.continue_()
        else:
            held.append(route)

    page.route(pattern, hold)
    return held, released


def _until(page: Page, condition, attempts: int = 100) -> None:
    """Let Playwright deliver its pending events until `condition` holds.

    A sync-API route handler runs only while the test is inside a Playwright
    call, so this waits THROUGH one (`wait_for_timeout`) -- `time.sleep` would
    deliver nothing. Bounded, and a miss is a failure, never a pass."""
    for _attempt in range(attempts):
        if condition():
            return
        page.wait_for_timeout(20)
    assert condition(), "the awaited event never arrived"


# -- what a proposal carries ------------------------------------------------------


@pytest.mark.parametrize("task", [ALPHA, BETA])
@pytest.mark.parametrize("capability", ["dispatch", "review"])
def test_a_tasks_proposal_carries_exactly_its_frozen_scope(
        chromium: Browser, cockpit_url: str, capability: str, task: str) -> None:
    """The person sees the task by name and id and types no scope; the POST carries
    the frozen SCOPE -- beta's is not its id -- the server admits it, and a dispatch
    is confirmed end to end."""
    run = f"run-{task.removeprefix('task-')}"
    page, recorder = _open(chromium, cockpit_url)
    try:
        _load(page, run)
        assert _context(page, "bound") == shown(task)
        assert page.locator('[name="argument:work_scope"], [name="work_scope"]').count() == 0
        _compose(page, capability)
        assert [(sent, body["arguments"]) for sent, body in recorder.rows] == [
            (run, {**TYPED[capability], "work_scope": SCOPES[task]})]
        if capability == "dispatch":
            page.locator("#commandConfirmedBy").fill("release-owner")
            page.get_by_role("button", name="Confirm unchanged proposal").click()
            page.locator('[data-confirm-state="accepted"]').wait_for()
    finally:
        page.context.close()


def test_a_task_whose_record_does_not_read_is_still_named_and_still_scoped(
        chromium: Browser, cockpit_url: str) -> None:
    """The binding is frozen even when the task's record cannot be read: the
    context names the id and says so, and the proposal carries the scope."""
    page, recorder = _open(chromium, cockpit_url)
    try:
        _load(page, "run-ghost")
        assert _context(page, "bound") == f"Task: {GHOST} — its record cannot be read"
        _compose(page, "dispatch")
        assert [body["arguments"]["work_scope"] for _run, body in recorder.rows] == [GHOST]
    finally:
        page.context.close()


@pytest.mark.parametrize("capability", ["dispatch", "review"])
def test_a_run_without_a_task_sends_no_scope_at_all(
        chromium: Browser, cockpit_url: str, capability: str) -> None:
    """A legacy or task-less run files its work as it always did: the key is
    absent, not null, and the context says there is no task."""
    page, recorder = _open(chromium, cockpit_url)
    try:
        _load(page, "run-legacy")
        assert _context(page, "none") == NO_TASK
        _compose(page, capability)
        assert [(run, body["arguments"]) for run, body in recorder.rows] == [
            ("run-legacy", TYPED[capability])]
    finally:
        page.context.close()


def test_an_answer_echoing_another_scope_is_never_taken_for_the_proposal(
        chromium: Browser, cockpit_url: str) -> None:
    """Preview binds the payload that was composed: an answer whose arguments carry
    a different scope is an unknown outcome, never a snapshot to confirm."""
    page, _recorder = _open(chromium, cockpit_url)

    def replaced(route: Route) -> None:
        response = route.fetch()
        body = response.json()
        body["arguments"] = {**body["arguments"], "work_scope": SCOPES[BETA]}
        route.fulfill(response=response, json=body)

    try:
        _load(page, "run-alpha")
        _context(page, "bound")
        page.route("**/command/runs/run-alpha/proposals", replaced)
        _fill(page, "dispatch", "Answer rewritten.")
        page.locator('.command-proposal-form button[type="submit"]').click()
        page.locator('[data-proposal-state="outcome-unknown"]').wait_for()
        assert page.locator(".command-review-fact").count() == 0
    finally:
        page.context.close()


# -- switching, and answers that land late -----------------------------------------


def test_switching_to_another_task_while_composing_carries_nothing_across(
        chromium: Browser, cockpit_url: str) -> None:
    """A proposal made on task alpha's run is dropped when the person switches to
    task beta's; the next proposal goes to beta's run with beta's scope."""
    page, recorder = _open(chromium, cockpit_url)
    try:
        _load(page, "run-alpha")
        _context(page, "bound")
        _compose(page, "dispatch", rationale="Made on alpha.")
        assert page.locator(".command-review-fact").count() > 0

        _load(page, "run-beta")
        assert _context(page, "bound") == shown(BETA)
        assert page.locator(".command-review-fact").count() == 0
        _compose(page, "dispatch", rationale="Made on beta.")
        assert [(run, body["arguments"]["work_scope"]) for run, body in recorder.rows] == [
            ("run-alpha", SCOPES[ALPHA]), ("run-beta", SCOPES[BETA])]
    finally:
        page.context.close()


# -- a binding that does not read ------------------------------------------------


@pytest.mark.parametrize("tamper", ["half-binding", "joined-task-disagrees"])
def test_a_binding_the_cockpit_cannot_read_disables_proposing_until_it_reads_again(
        chromium: Browser, cockpit_url: str, tamper: str) -> None:
    """A run read carrying half a binding, or a task record naming another task,
    is not "no task": the composer is disabled and says why. The Reload action,
    outside the disabled form, reads the SELECTED run again -- not whatever has
    been typed into the run field since -- and the composer comes back.

    That nothing unreadable can be POSTed is held by the projection table below
    (no arguments at all for an unreadable binding) and by the disabled controls
    here; this test does not pretend a POST was possible.
    """
    page, _recorder = _open(chromium, cockpit_url)
    honest = threading.Event()

    def tampered(route: Route) -> None:
        if honest.is_set():
            route.continue_()
            return
        response = route.fetch()
        body = response.json()
        if tamper == "half-binding":
            body["config"]["task"] = {"id": ALPHA}
        else:
            body["task"] = {**body["task"], "id": BETA, "work_scope": SCOPES[BETA]}
        route.fulfill(response=response, json=body)

    try:
        page.route("**/command/runs/run-alpha", tampered)
        _load(page, "run-alpha")
        assert "cannot be read" in _context(page, "unreadable")
        form = page.locator(".command-proposal-form")
        assert form.locator("button[type=submit]").is_disabled()
        assert form.locator('input[name="rationale"]').is_disabled()

        honest.set()
        page.locator("#commandRunId").fill("run-beta")
        page.get_by_role("button", name="Reload run").click()
        assert _context(page, "bound") == shown(ALPHA)
        assert _selected(page) == "run: run-alpha"
        assert form.locator("button[type=submit]").is_enabled()
    finally:
        page.context.close()


_BOUND = {"id": ALPHA, "work_scope": ALPHA}
_JOINED = {**_BOUND, "title": TITLES[ALPHA], "unreadable": False}
_OTHER = {"id": ALPHA, "work_scope": "scope-x"}
_BINDINGS = [
    pytest.param({"config": {}, "task": None}, {"state": "none"}, id="no-task"),
    pytest.param({"config": {}}, {"state": "none"}, id="no-task-no-join"),
    pytest.param({"config": {"task": _BOUND}, "task": _JOINED},
                 {"state": "bound", "taskId": ALPHA, "workScope": ALPHA,
                  "title": TITLES[ALPHA]}, id="bound"),
    pytest.param({"config": {"task": _OTHER}, "task": {**_JOINED, **_OTHER}},
                 {"state": "bound", "taskId": ALPHA, "workScope": "scope-x",
                  "title": TITLES[ALPHA]}, id="bound-scope-is-not-the-id"),
    pytest.param({"config": {"task": _BOUND}, "task": {**_JOINED, "title": None,
                                                        "unreadable": True}},
                 {"state": "bound", "taskId": ALPHA, "workScope": ALPHA, "title": None},
                 id="bound-record-unreadable"),
    pytest.param({"config": {"task": _BOUND}, "task": {**_JOINED, "unreadable": True}},
                 {"state": "bound", "taskId": ALPHA, "workScope": ALPHA, "title": None},
                 id="a-title-beside-an-unreadable-record-is-not-shown"),
    pytest.param({"config": {"task": {"id": ALPHA}}, "task": _JOINED},
                 {"state": "unreadable"}, id="half-binding"),
    pytest.param({"config": {"task": {**_BOUND, "extra": 1}}, "task": _JOINED},
                 {"state": "unreadable"}, id="extra-key"),
    pytest.param({"config": {"task": {"id": ALPHA, "work_scope": "a/b"}},
                  "task": {**_JOINED, "work_scope": "a/b"}},
                 {"state": "unreadable"}, id="scope-not-an-id-though-both-halves-agree"),
    pytest.param({"config": {"task": {"id": "not an id", "work_scope": ALPHA}},
                  "task": {**_JOINED, "id": "not an id"}},
                 {"state": "unreadable"}, id="id-not-an-id-though-both-halves-agree"),
    pytest.param({"config": {"task": {"id": "t" * 64, "work_scope": ALPHA}},
                  "task": {**_JOINED, "id": "t" * 64}},
                 {"state": "bound", "taskId": "t" * 64, "workScope": ALPHA,
                  "title": TITLES[ALPHA]}, id="task-id-at-the-task-bound"),
    pytest.param({"config": {"task": {"id": "t" * 65, "work_scope": ALPHA}},
                  "task": {**_JOINED, "id": "t" * 65}},
                 {"state": "unreadable"}, id="task-id-past-the-task-bound"),
    pytest.param({"config": {"task": {"id": ALPHA, "work_scope": "s" * 64}},
                  "task": {**_JOINED, "work_scope": "s" * 64}},
                 {"state": "bound", "taskId": ALPHA, "workScope": "s" * 64,
                  "title": TITLES[ALPHA]}, id="scope-at-the-task-bound"),
    pytest.param({"config": {"task": {"id": ALPHA, "work_scope": "s" * 65}},
                  "task": {**_JOINED, "work_scope": "s" * 65}},
                 {"state": "unreadable"}, id="scope-past-the-task-bound"),
    pytest.param({"config": {"task": None}, "task": None},
                 {"state": "unreadable"}, id="null-binding"),
    pytest.param({"config": {"task": _BOUND}, "task": None},
                 {"state": "unreadable"}, id="bound-without-join"),
    pytest.param({"config": {"task": _BOUND}, "task": {**_JOINED, "id": BETA}},
                 {"state": "unreadable"}, id="join-names-another-id"),
    pytest.param({"config": {"task": _BOUND}, "task": {**_JOINED, "work_scope": BETA}},
                 {"state": "unreadable"}, id="join-names-another-scope"),
    pytest.param({"config": {}, "task": _JOINED}, {"state": "unreadable"},
                 id="join-without-binding"),
    pytest.param({"task": None}, {"state": "unreadable"}, id="no-config"),
]


@pytest.mark.parametrize("run, expected", _BINDINGS)
def test_the_cockpit_reads_a_binding_as_the_server_does_and_never_half_as_none(
        chromium: Browser, cockpit_url: str, run: dict, expected: dict) -> None:
    """The shipped projection, imported into a real engine and asked directly:
    absent is "none", exactly `{id, work_scope}` -- both ids -- agreeing with the
    joined record is "bound", and every other shape is "unreadable", which
    carries no arguments at all, while "none" carries them without a scope. Each
    unreadable row breaks ONE rule, so each rule is what refuses its row."""
    page, _recorder = _open(chromium, cockpit_url)
    try:
        answer = page.evaluate("""async (run) => {
          const m = await import("/panel/command-projection.js");
          const task = m.projectTaskBinding(run);
          return {task, dispatch: m.scopedArguments("dispatch", {work_item_id: "w"}, task),
                  stop: m.scopedArguments("stop", {reason: "user"}, task),
                  workBearing: [...m.WORK_BEARING]};
        }""", run)
        assert answer["task"] == expected
        assert answer["workBearing"] == ["dispatch", "review"]
        if expected["state"] == "unreadable":
            assert (answer["dispatch"], answer["stop"]) == (None, None)
        elif expected["state"] == "none":
            assert (answer["dispatch"], answer["stop"]) == ({"work_item_id": "w"},
                                                            {"reason": "user"})
        else:
            assert (answer["dispatch"], answer["stop"]) == (
                {"work_item_id": "w", "work_scope": expected["workScope"]},
                {"reason": "user"})
    finally:
        page.context.close()


def test_a_run_whose_frozen_binding_is_half_is_refused_whole_by_the_server(
        chromium: Browser, cockpit_url: str) -> None:
    """The real road never hands the Cockpit half a binding: the server refuses the
    run read as corrupt, and no composer is drawn to propose anything on it."""
    page, _recorder = _open(chromium, cockpit_url)
    try:
        _load(page, BROKEN)
        page.wait_for_function("() => document.querySelector('#commandCockpit')"
                               ".dataset.phase === 'refused'")
        assert page.locator("#commandCockpitStatus").text_content() == (
            "The run history is corrupt.")
        assert page.locator(".command-proposal-form").count() == 0
    finally:
        page.context.close()
