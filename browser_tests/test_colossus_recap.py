"""The return-to-session summary opens evidence for the archived Do without running a task."""
import json
import re
import runpy
from pathlib import Path
from threading import Thread
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import expect

from browser_tests.desk_hold import close_context
from browser_tests.test_atlas_handoff import ask
from browser_tests.test_studio_atlas import atlas_url, evidence  # noqa: F401
from conductor import server
from conductor.command.adapters import AdapterRegistry
from conductor.command.project_claim import Launch


QUESTION = "Пока меня не было, что изменилось и где нужен я?"
PILOT = Path(__file__).resolve().parents[1] / "distribution" / "windows-pilot" / "pilot.py"
DO_PROOF = "/command/runs/demo-codex-grok/steps/do/actions/do-action"


@pytest.fixture
def archived_project(tmp_path):
    project = tmp_path / "project"
    # Use the same safe unpacker and offline project that a colleague receives.
    runpy.run_path(str(PILOT))["unpack"](project)
    return project


@pytest.fixture
def archived_pilot(archived_project):
    view = Launch(mode="view")
    with server.build(archived_project, 0, registry=AdapterRegistry([]), launch=view) as http:
        thread = Thread(target=http.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{http.server_port}/#session=demo-codex-grok&lang=ru"
        finally:
            http.shutdown()
            thread.join(5)


@pytest.mark.parametrize("width", [1440, 375])
def test_returning_operator_can_open_each_do_proof_from_chat(chromium, archived_pilot, width):
    context = chromium.new_context(viewport={"width": width, "height": 900})
    try:
        page = context.new_page()
        requests = []
        page.on("request", lambda req: requests.append((req.method, urlsplit(req.url).path)))
        page.goto(archived_pilot)
        expect(page.locator('#orbitHere [data-step="do"]')).to_be_visible()
        panel = page.locator("#inspection")
        ask(page, QUESTION)
        recap = panel.locator("[data-recap]")
        expect(recap).to_have_attribute("data-recap-action", "do-action")
        expect(recap).to_have_attribute("data-recap-attempt", "do-attempt")
        reply = page.locator("#messages .msg.atlas").last
        expect(reply).to_contain_text(re.compile("заверш[её]н|принят", re.I))
        for evidence, expected in (("diff", "-    return len(rows)"), ("tests", "всего 3"),
                                   ("verdict", "codex-checker")):
            action = panel.locator(f'[data-recap-open="{evidence}"]')
            expect(action).to_be_visible()
            action.press("Enter")
            body = panel.locator("#atlas-tab-panel")
            expect(body).to_be_visible()
            expect(body).to_contain_text(expected)
            if evidence == "tests":
                expect(body).to_contain_text("Внешняя проверка")
                expect(body.locator("[data-atlas-protocol]")).to_have_count(0)
        expect(page.locator("#messages .msg.user")).to_have_count(1)
        proof_requests = {path for _, path in requests if "/actions/" in path}
        assert proof_requests == {DO_PROOF}
        assert {method for method, _ in requests} == {"GET"}
    finally:
        close_context(context)


def test_recap_surfaces_waiting_result_gate_before_owner_decision(
        chromium, archived_project, archived_pilot):
    # Rewind the disposable pilot to the last real record before the owner's acceptance.
    records = archived_project / "conductor" / "runs" / "demo-codex-grok" / "records.jsonl"
    lines = records.read_bytes().splitlines(keepends=True)
    end = next(i for i, line in enumerate(lines)
               if json.loads(line)["record"].get("receipt_id") == "result-gate-receipt")
    records.write_bytes(b"".join(lines[:end]))
    # Recovery also reads persisted decisions, including ones beyond a torn journal.
    (records.parent / "decisions" / "result-gate-receipt.json").unlink()
    context = chromium.new_context()
    try:
        page = context.new_page()
        writes = []
        page.on("request", lambda req: writes.append(req.url) if req.method != "GET" else None)
        page.goto(archived_pilot)
        expect(page.locator('#orbitHere [data-step="do"]')).to_be_visible()
        ask(page, QUESTION)
        recap = page.locator("#inspection [data-recap]")
        expect(recap).to_have_attribute("data-recap-attempt", "do-attempt")
        expect(recap).to_contain_text(re.compile("Result Gate|gate-result", re.I))
        reply = page.locator("#messages .msg.atlas").last
        expect(reply).to_contain_text(re.compile("решени|подтверд|при[её]мк", re.I))
        expect(reply).not_to_contain_text(re.compile("цикл заверш[её]н|запуск заверш[её]н", re.I))
        assert writes == []
    finally:
        close_context(context)


def test_recap_keeps_the_selected_earlier_attempt(chromium, atlas_url):
    context = chromium.new_context(viewport={"width": 1280, "height": 850})
    try:
        page = context.new_page()
        page.route("**/steps/repair-counter/actions/*", lambda route: route.fulfill(
            json=evidence(route.request.url.rsplit("/", 1)[-1])))
        page.goto(atlas_url + "/#session=first&lang=en")
        page.locator('#orbitHere [data-step="repair-counter"]').click()
        panel = page.locator("#inspection")
        attempts = panel.locator("[data-atlas-attempt]")
        expect(attempts).to_have_value("action-first-2")
        attempts.select_option("action-first-1")
        expect(panel.locator('[data-atlas-diff="action-first-1.py"]')).to_be_visible()
        ask(page, "What did I miss, and where am I needed?")
        expect(panel.locator("[data-recap]")).to_have_attribute(
            "data-recap-attempt", "attempt-action-first-1")
        panel.locator('[data-recap-open="diff"]').click()
        expect(panel.locator("#atlas-tab-panel")).to_contain_text("+new-action-first-1")
        expect(panel).not_to_contain_text("action-first-2.py")
    finally:
        close_context(context)


def test_recap_refuses_proof_returned_for_a_different_attempt(chromium, archived_pilot):
    context = chromium.new_context()
    try:
        page = context.new_page()
        intercepted = []

        def foreign(route):
            proof = route.fetch().json()
            assert proof["attempt_id"] == "do-attempt"
            proof["attempt_id"] = "another-attempt"
            intercepted.append(proof["attempt_id"])
            route.fulfill(json=proof)

        page.route("**" + DO_PROOF, foreign)
        page.goto(archived_pilot)
        expect(page.locator('#orbitHere [data-step="do"]')).to_be_visible()
        ask(page, QUESTION)
        recap = page.locator("#inspection [data-recap]")
        expect(recap).to_have_attribute("data-recap-attempt", "do-attempt")
        expect(recap.get_by_role("status")).to_contain_text("не подтверждены")
        expect(recap.locator("[data-recap-open]")).to_have_count(0)
        expect(page.locator("#messages .msg.atlas").last).not_to_contain_text("codex-checker")
        assert intercepted == ["another-attempt"]
    finally:
        close_context(context)
