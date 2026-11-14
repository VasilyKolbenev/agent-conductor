"""A stopped task explains the independent verification refusal on its Desk scene."""
from pathlib import Path
import threading

import pytest
from playwright.sync_api import Browser, expect

from browser_tests.desk_hold import close_context
from browser_tests.desk_progress_bench import open_window
from conductor import server
from conductor.command.graph_definition import GraphDefinition
from conductor.command.graph_schedule import schedule
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.run_terminal import RunTerminal
from conductor.command.task_contracts import TaskRecord
from conductor.command.task_store import TaskStore
from conductor.command.verify_holds import DOER_NOTHING_CHANGED
from tests.desk_progress_seed import CHECKER, CREATED, DOER, Journal, _definition
from tests.test_command_graph_projection import a_result
from tests.test_command_run_store import a_run
from tests.test_store import good_lane, write_project


def seed_refusal(root: Path, task_id: str, reason: str) -> None:
    TaskStore(root).create_task(TaskRecord(task_id, task_id, task_id, CREATED))
    run_id = f"run-{task_id}"
    config = {"cycle": {"id": "default-orbit"}, "task": {"id": task_id, "work_scope": task_id},
              "instances": [{"id": DOER, "adapter": "claude-code"},
                            {"id": CHECKER, "adapter": "codex-cli"}]}
    store = RunStore(root)
    digest = snapshot_digest(config)
    store.create_run(a_run(run_id=run_id, mode="confirm", config_digest=digest,
                           created_at=CREATED), config)
    document = _definition(run_id).as_dict()
    next(node for node in document["nodes"] if node["node_id"] == "do")["failure_policy"] = "halt_run"
    plan = GraphDefinition.from_dict(document)
    store.append(plan)
    journal = Journal(store, run_id, digest, 100)
    journal.brief()
    journal.analyse()
    journal.decide("gate-confirm-do", "approve", "Reviewed the plan.")
    request = journal._start(next(node for node in plan.nodes if node.node_id == "do"))
    journal._observed(request)
    store.append(a_result(request, journal.index, run_id=run_id, outcome="verification_failed",
                          observed_at=journal.at(), detail=reason, evidence_refs=()))
    end = schedule(plan, tuple(row.value for row in store.read(run_id).records))
    assert end.run_state == "stalled"
    store.append(RunTerminal(terminal_id="terminal-failed", run_id=run_id, graph_id=plan.graph_id,
                             state=end.run_state, settled_nodes=end.settled,
                             unreachable_nodes=end.unreachable, recorded_at=journal.at()))


@pytest.fixture(scope="module")
def desk_url(tmp_path_factory):
    root = write_project(tmp_path_factory.mktemp("desk-refusal"), lanes={"claude": good_lane()})
    seed_refusal(root, "task-no-change", DOER_NOTHING_CHANGED)
    seed_refusal(root, "task-other", "different refusal with <untrusted text>")
    httpd = server.build(root, 0)
    worker = threading.Thread(target=httpd.serve_forever, daemon=True)
    worker.start()
    try:
        host, port = httpd.server_address[:2]
        yield f"http://{host}:{port}/panel/desk.html"
    finally:
        httpd.shutdown()
        worker.join(timeout=5)
        httpd.server_close()


@pytest.mark.parametrize(("lang", "width", "message"), [
    ("ru", 375, "Шаг «Do the work» остановлен. Исполнитель не изменил файлы, поэтому проверяющему нечего проверять."),
    ("en", 1280, "Step “Do the work” stopped. The participant made no file changes for the checker to verify."),
], ids=["ru-narrow", "en-desktop"])
def test_stopped_task_explains_why_the_checker_did_not_run(chromium: Browser, desk_url,
                                                           lang, width, message):
    window = open_window(chromium, desk_url, lang, task="task-no-change", width=width)
    try:
        scene = window.page.locator("#deskScene")
        explanation = scene.get_by_text(message, exact=True)
        expect(explanation).to_be_visible(timeout=2500)
        window.page.wait_for_function("""message => {
            const scene = document.querySelector('#deskScene');
            const el = [...scene.querySelectorAll('p')].find(p => p.textContent === message);
            const deck = scene.querySelector('.studio-deck');
            return el && deck && el.getBoundingClientRect().right <= innerWidth
              && el.getBoundingClientRect().bottom <= deck.getBoundingClientRect().top;
        }""", arg=message, timeout=2500)
        card = window.page.locator("#deskPult [data-desk-decision]")
        expect(card.locator("h2")).to_have_text(
            "Решение записано" if lang == "ru" else "Decision recorded", timeout=2500)
        window.page.locator('#deskRail [data-task-id="task-other"]').click()
        expect(scene.locator(".desk-scene__subject")).to_contain_text("task-other")
        expect(scene.get_by_text(message, exact=True)).to_have_count(0)
        assert "<untrusted text>" not in scene.inner_text()
        assert not window.problems
    finally:
        close_context(window.page.context)
