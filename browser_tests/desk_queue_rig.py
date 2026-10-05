"""A real one-project server with a real queue, for the desk's queue tests (spec 4.4, 4.4.9).

Not a test module (pytest does not collect it). It is the recipe of `tests/test_policy_server.py`
carried to a browser: a project folder is activated (a real owner), then `server.build` serves it
with a real `PolicyDriver`, the real queue and its pump, the real routes and the desk's own panel
files. What is fake is only the adapters (two signing doubles that finish a step at once) and the
clock, a one-cell list a test moves to make a grant run out; both are named, neither is a
stand-in for a route. The project id is the owner's nonce, so a desk that names it is bound to a
server that really is that project.

A test makes its world in two moves. `seed` writes tasks and runs into the folder BEFORE it is
activated (a run is a bounded plan: a gate a person already approved, `do`, `next`, and, for a run
that must keep the slot, a FINAL gate nobody has decided, so the run waits there and its slot
reads busy). `running` then serves the folder. From there a person's acts are the wire's own:
`Project.call` goes through the server's CSRF door, and the helpers below it (`hold`, `enqueue`,
`decide`) are a few calls of it, never a write into a store.
"""
from __future__ import annotations

import http.client
import json
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from itertools import count
from pathlib import Path
from typing import Any

from conductor import ownership_transition, server
from conductor.command.adapters import AdapterRegistry
from conductor.command.artifacts import ArtifactDocument
from conductor.command.contracts import DecisionReceipt, RunEnvelope
from conductor.command.graph_definition import GraphDefinition, GraphEdge, GraphNode
from conductor.command.project_claim import Launch
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.task_contracts import TaskRecord
from conductor.command.task_store import TaskStore
from tests.queue_fixtures import CONFIG_TEMPLATE
from tests.test_command_http_api import TOKEN
from tests.test_policy_driver import Signing, ask
from tests.test_policy_runtime import ARGS, NOW, PD
from tests.test_store import good_lane, write_project

#: The instant a grant is written at, and one that is past its window (`ask()` asks for 300 s).
PAST_THE_WINDOW = "2026-08-11T12:10:00Z"
#: The id of the final gate of a run that keeps the slot, and the body that approves it.
FINAL_GATE = "gate-final"
#: How long a test waits for the server's own thread (the pump, the driver) to settle a state.
PATIENCE = 12.0


@dataclass(frozen=True)
class Seed:
    """One run of one task: `final_gate` makes it keep the slot once it has done its steps."""

    run_id: str
    task_id: str
    title: str
    final_gate: bool = False


def _node(node_id: str, task_id: str) -> GraphNode:
    return GraphNode(node_id, "task", node_id, instance_id="doer", capability="dispatch",
                     arguments={**ARGS, "work_scope": task_id}, timeout_seconds=30,
                     attempt_bound=2, verifier_instance_id="checker")


def _plan(seed: Seed) -> GraphDefinition:
    nodes = [GraphNode("gate", "gate", "Approve", gate_id="gate-id"),
             _node("do", seed.task_id), _node("next", seed.task_id)]
    edges = [GraphEdge("gate", "do", condition="on_approved"),
             GraphEdge("do", "next", condition="on_succeeded")]
    if seed.final_gate:
        nodes.append(GraphNode("final", "gate", "Accept", gate_id=FINAL_GATE))
        edges.append(GraphEdge("next", "final", condition="on_succeeded"))
    return GraphDefinition("graph", seed.run_id, NOW, nodes=tuple(nodes), edges=tuple(edges),
                           execution_contract="bounded-run-v1")


def _make_run(store: RunStore, seed: Seed) -> None:
    """The run of `seed`: a frozen configuration bound to its task, its plan, its instruction
    and the decision of the first gate, the way `tests/queue_fixtures.add_run` makes one."""
    config = {**CONFIG_TEMPLATE, "task": {"id": seed.task_id, "work_scope": seed.task_id}}
    store.create_run(RunEnvelope(seed.run_id, "cycle", NOW, snapshot_digest(config),
                                 mode="policy"), config)
    store.append(_plan(seed))
    store.append(ArtifactDocument(artifact_id="instruction-1", run_id=seed.run_id,
                                  artifact_ref="instructions", created_at=NOW,
                                  media_type="text/plain", content="Keep my task.\n"))
    store.append(DecisionReceipt("decision", seed.run_id, "gate-id", "approve", "owner", NOW,
                                 "Reviewed", ("gate-id",), snapshot_digest(config)))


def seed(root: Path, runs: list[Seed]) -> RunStore:
    """Write the tasks and the runs into the folder (before it is activated)."""
    tasks = TaskStore(root)
    for task_id, title in dict.fromkeys((one.task_id, one.title) for one in runs):
        tasks.create_task(TaskRecord(task_id=task_id, title=title, work_scope=task_id,
                                     created_at=NOW))
    store = RunStore(root)
    for one in runs:
        _make_run(store, one)
    return store


@dataclass
class Project:
    """A served project: its address, its clock cell and the calls a person makes to it."""

    httpd: server.ConductServer
    origin: str
    project_id: str
    ticks: list[str]
    calls: list[tuple[str, str]] = field(default_factory=list)

    def url(self, language: str = "en", *, extra: str = "") -> str:
        """The desk at its own address, bound to this project."""
        return (f"{self.origin}/panel/desk.html#project={self.project_id}&lang={language}"
                f"{extra}")

    def call(self, method: str, path: str, body: Any = None) -> tuple[int, Any]:
        """One request through the server's own door, with its session token."""
        encoded = None if body is None else json.dumps(body, separators=(",", ":")).encode()
        headers = {} if encoded is None else {
            "Origin": self.origin, "X-Conduct-CSRF": TOKEN, "Content-Type": "application/json"}
        connection = http.client.HTTPConnection("127.0.0.1", self.httpd.server_address[1],
                                                timeout=8)
        try:
            connection.request(method, path, body=encoded, headers=headers)
            response = connection.getresponse()
            self.calls.append((method, path))
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def queue(self) -> dict:
        status, payload = self.call("GET", "/command/queue")
        assert status == 200, payload
        return payload

    def automation(self, run_id: str) -> dict:
        status, payload = self.call("GET", f"/command/runs/{run_id}/automation")
        assert status == 200, payload
        return payload

    def wait(self, what: str, done: Callable[[], Any]) -> Any:
        """Poll a fact of the server until it holds (the pump and the driver are threads)."""
        deadline = time.monotonic() + PATIENCE
        while time.monotonic() < deadline:
            found = done()
            if found:
                return found
            time.sleep(0.05)
        raise AssertionError(f"the server never reached: {what}")


def _start_body(project: Project, run_id: str, authorization_id: str, by: str) -> dict:
    status, preview = project.call("POST", f"/command/runs/{run_id}/automation/preview", ask())
    assert status == 200, preview
    return {"authorization_id": authorization_id, "preview_digest": preview["preview_digest"],
            "terms": preview["terms"], "authorized_by": by, "supersedes": None}


def enqueue(project: Project, run_id: str, authorization_id: str, by: str = "vasya") -> dict:
    """Put a run in the queue under a fresh preauthorization (the card's "queue" press)."""
    body = {"run_id": run_id, "start": _start_body(project, run_id, authorization_id, by)}
    status, payload = project.call("POST", "/command/queue", body)
    assert status in (200, 201), payload
    return payload


def hold(project: Project, run_id: str, authorization_id: str, by: str = "vasya") -> None:
    """Authorize a run directly and wait until it sits at its final gate, holding the slot."""
    body = _start_body(project, run_id, authorization_id, by)
    status, payload = project.call("POST", f"/command/runs/{run_id}/automation/authorize", body)
    assert status == 201, payload
    project.wait(f"{run_id} waits at its final gate",
                 lambda: project.automation(run_id)["reason_code"] == "plan_waiting")


def publish(project: Project, run_id: str, artifact_id: str, content: str = "A new note.\n",
            ref: str = "instructions") -> None:
    """Publish a document to a run, as the wizard does: the run's terms change with its journal."""
    body = {"artifact_id": artifact_id, "artifact_ref": ref, "media_type": "text/markdown",
            "content": content}
    status, payload = project.call("POST", f"/command/runs/{run_id}/artifacts", body)
    assert status in (200, 201), payload


def decide(project: Project, run_id: str, action: str = "approve", by: str = "vasya") -> None:
    """Decide the final gate of a run, as its gate card does."""
    body = {"receipt_id": f"decision-{run_id}-{action}", "gate_id": FINAL_GATE, "action": action,
            "actor": by, "reason": "Reviewed the result.", "scope_refs": [],
            "evidence_refs": [], "supersedes": None}
    status, payload = project.call("POST", f"/command/runs/{run_id}/decisions", body)
    assert status in (200, 201), payload


#: The desk is settled when the shell says one of these (the same word every desk test waits for).
SETTLED = """() => ["ready", "refused", "failed"].includes(
  document.getElementById("deskShell").getAttribute("data-state"))"""
#: What a test asks of the console and the rail, in ONE evaluation: a fact and its sentence are
#: read together, so a redraw between two reads cannot make them disagree. `textContent`, because
#: the style draws some words in capitals.
FACTS = """() => {
  const text = (node) => (node ? node.textContent.trim() : null);
  const block = document.querySelector("#deskPult .desk-queue");
  const box = (node) => { const r = node.getBoundingClientRect(); return [r.width, r.height]; };
  return {
    block: block !== null, head: text(block && block.querySelector(".desk-queue__head")),
    now: text(block && block.querySelector(".desk-queue__now")),
    none: text(block && block.querySelector(".desk-queue__none")),
    notice: text(block && block.querySelector("[data-pult-notice]")),
    release: text(block && block.querySelector('[data-focus-key="queue:release"]')),
    skip: text(block && block.querySelector('[data-focus-key="queue:skip"]')),
    slotHint: text(block && block.querySelector("[data-pult-slot-hint]")),
    dialog: (() => {
      const dialog = block && block.querySelector("[data-pult-dialog]");
      if (!dialog) return null;
      return {kind: dialog.dataset.pultDialog,
        lines: [...dialog.querySelectorAll("p")].map(text),
        buttons: [...dialog.querySelectorAll("button")].map((button) => ({
          key: button.dataset.focusKey, text: text(button),
          disabled: button.disabled || button.getAttribute("aria-disabled") === "true",
          size: box(button)}))};
    })(),
    focus: document.activeElement ? document.activeElement.dataset.focusKey ?? null : null,
    entries: block === null ? [] : [...block.querySelectorAll(".desk-queue__entry")].map((row) => ({
      run: row.dataset.runId, state: row.dataset.queueState, tone: row.dataset.tone,
      text: [...row.querySelectorAll(":scope > span:not(.desk-queue__hint)")]
        .map((part) => part.textContent).join("").trim(),
      hint: text(row.querySelector(":scope > .desk-queue__hint")),
      buttons: [...row.querySelectorAll("button")].map((button) => ({
        key: button.dataset.focusKey, text: text(button), label: button.getAttribute("aria-label"),
        disabled: button.disabled || button.getAttribute("aria-disabled") === "true",
        size: box(button)}))})),
    rail: Object.fromEntries([...document.querySelectorAll("#deskRail [data-task-id]")].map(
      (row) => [row.dataset.taskId, text(row.querySelector(".desk-task__state"))])),
    shell: document.getElementById("deskShell").getAttribute("data-state")};
}"""


@dataclass
class Window:
    """One booted desk window on a served project and everything it said and asked."""

    page: Any
    problems: list[str] = field(default_factory=list)
    asked: list[tuple[str, str]] = field(default_factory=list)
    posted: list[tuple[str, Any]] = field(default_factory=list)

    def facts(self) -> dict:
        return self.page.evaluate(FACTS)

    def requests(self, method: str, path: str) -> int:
        return sum(1 for asked in self.asked if asked == (method, path))

    def name(self, who: str) -> None:
        """Give the console the name of the person at the page, as a person does."""
        self.page.locator('[data-focus-key="pult:actor-change"]').click()
        self.page.locator('[name="actor"]').fill(who)
        self.page.locator('[data-focus-key="pult:actor-save"]').click()

    def until(self, what: str, done: Callable[[], Any]) -> None:
        """Wait (pumping the page) until a fact of THIS side of the wire holds, e.g. that a
        route the test holds has been reached."""
        for _ in range(160):
            if done():
                return
            self.page.wait_for_timeout(50)
        raise AssertionError(f"the page never reached: {what}")

    def press(self, key: str, *, force: bool = False) -> None:
        """Press the control that carries this focus key, as a person does. `force` presses one
        that says it is unavailable: the page must then do nothing."""
        self.page.locator(f'#deskPult [data-focus-key="{key}"]').click(force=force)

    def order(self) -> list[str]:
        """The run ids of the entries the console draws, in the order it draws them."""
        return [row["run"] for row in self.facts()["entries"]]

    def errors(self, ignore: tuple[str, ...] = ()) -> list[str]:
        """The console errors that are not a failed request a test made on purpose."""
        return [one for one in self.problems if not any(word in one for word in ignore)]


def _note(window: Window, served: Project, request: Any) -> None:
    """Remember what the desk asked, and the body of each write it sent."""
    where = request.url.removeprefix(served.origin).split("#")[0]
    window.asked.append((request.method, where))
    if request.method == "POST":
        window.posted.append((where, request.post_data_json))


def open_desk(browser: Any, served: Project, language: str = "en", *, width: int = 1280,
              extra: str = "", before: Callable[[Any], None] | None = None) -> Window:
    """A desk on the project, waited until it is settled; `before` may route the page first."""
    context = browser.new_context(viewport={"width": width, "height": 900}, timezone_id="UTC")
    page = context.new_page()
    page.set_default_timeout(8000)
    window = Window(page)
    page.on("console", lambda message: window.problems.append(message.text)
            if message.type == "error" else None)
    page.on("pageerror", lambda error: window.problems.append(str(error)))
    page.on("request", lambda request: _note(window, served, request))
    # HTTP 204 ends the projection stream without a retry. A stream that opens refreshes every
    # read the desk made -- the queue among them, and again at each frame the server's own pump
    # and writes send -- so a count of the desk's reads, and a console drawn from the answer of a
    # write, would be judged beside the refreshes. Live updates and reconnect are judged in
    # test_desk_live_stream.py.
    page.route("**/events", lambda route: route.fulfill(status=204))
    if before is not None:
        before(page)
    page.goto(served.url(language, extra=extra), wait_until="load")
    page.wait_for_function(SETTLED, timeout=15000)
    return window


@contextmanager
def running(root: Path, *, mode: str = "active") -> Iterator[Project]:
    """Serve an already seeded folder as the project its owner is, in `mode`."""
    store = RunStore(root)
    doer, checker = Signing(store), Signing(store, adapter_id="codex-cli")
    ticks, ids = [NOW], count()
    ownership_transition.activate(root, legacy_writers_stopped=True)
    httpd = server.build(root, 0, registry=AdapterRegistry([doer, checker]),
                         clock=lambda: ticks[0], ids=lambda kind: f"{kind}-{next(ids)}",
                         token_factory=lambda _: TOKEN, launch=Launch(mode=mode))
    doer._store = checker._store = httpd.command_store
    policy = httpd.command_api._policy
    policy.provider_digest, policy.provider_facts = lambda config: PD, None
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        yield Project(httpd, origin, httpd.project_identity.project_id, ticks)
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=8)
        assert not thread.is_alive(), "the project server did not stop"


@contextmanager
def project(tmp_path: Path, runs: list[Seed], *, mode: str = "active") -> Iterator[Project]:
    """A project folder with `runs`, activated and served: the one call a test makes."""
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    seed(root, runs)
    with running(root, mode=mode) as served:
        yield served
