"""Atlas chat follows a recorded Grok/Codex handoff to its exact Do, tests and patch."""
import json
from pathlib import Path

import pytest
from playwright.sync_api import expect

from browser_tests.desk_hold import close_context
from browser_tests.test_studio_atlas import atlas_url  # noqa: F401
from conductor.command.run_store import RunStore
from conductor.command.studio_routes import recovered_payload
from conductor.command.task_store import TaskStore
from tests.test_arachnid_handoff_data import world


QUESTION = "Что Grok передал Codex?"
FOLLOWUP = "Что из этого проверили тестами?"
CHANGES = "А что именно Codex исправил?"


def handoff_read(root, action="action-first-2"):
    """The served store supplies the graph and requests. Attach the recorded artifact chain."""
    detail = recovered_payload(RunStore(root).read("first"), TaskStore(root),
                               computed_at="2026-11-10T10:00:00Z")
    sample = world()
    detail["config"]["instances"].extend(sample["config"]["instances"][:2])
    rows = sample["records"]
    for row in rows:
        row["record"]["run_id"] = "first"
    request, result = rows[-2]["record"], rows[-1]["record"]
    original = next(r["record"] for r in detail["records"]
                    if r["record"].get("action_id") == action)
    request.update(node_id="repair-counter", action_id=action,
                   attempt_id="attempt-" + action, instance_id="maker")
    result.update(action_id=request["action_id"], attempt_id=request["attempt_id"],
                  instance_id=request["instance_id"])
    # Keep the store's complete request and the slot of its previous attempt.
    original.update(request)
    index = next(i for i, r in enumerate(detail["records"]) if r["record"] is original)
    detail["records"][index:index] = rows[:-2]
    detail["records"].append(rows[-1])
    return detail


def ask(page, text):
    field = page.locator("#command")
    field.fill(text)
    field.press("Enter")


def native_protocol(action="action-first-2"):
    fixture = Path(__file__).parents[1] / "tests/fixtures/atlas-accepted-native.json"
    row = json.loads(fixture.read_text(encoding="utf-8"))
    row.update(action_id=action, attempt_id="attempt-" + action)
    row["tests"]["protocol"]["binding"].update(action=action, attempt=row["attempt_id"])
    return row


@pytest.mark.parametrize("width", [1440, 375])
def test_three_questions_show_the_handoff_then_tests_then_the_patch_with_its_tests(
        chromium, atlas_url, tmp_path, width):
    context = chromium.new_context(viewport={"width": width, "height": 900})
    page = context.new_page()
    writes, requests = [], []
    page.on("request", lambda r: writes.append(r.method) if r.method != "GET" else None)
    # The later Do is also Codex; only the older Do received this plan.
    journal = handoff_read(tmp_path / "root", "action-first-1")
    proof = native_protocol("action-first-1")

    def attempt(route):
        requests.append(route.request.url.rsplit("/", 1)[-1])
        route.fulfill(json=proof)

    page.route("**/command/runs/first", lambda route: route.fulfill(json=journal))
    page.route("**/steps/repair-counter/actions/*", attempt)
    try:
        page.goto(atlas_url + "/#session=first&lang=ru")
        expect(page.locator('#orbitHere [data-step="repair-counter"]')).to_be_attached()
        ask(page, QUESTION)
        panel = page.locator("#inspection")
        source = panel.locator('[data-handoff-node="source"]')
        source.press("Enter")
        expect(panel.locator('[data-handoff-proof="source"]')).to_contain_text("diagnosis-1")
        expect(panel).to_contain_text("Counts cancelled rows.")
        panel.locator('[data-handoff-node="target"]').press("Enter")
        expect(panel.locator('[data-handoff-proof="target"]')).to_contain_text("plan-1")
        expect(panel).to_contain_text("Count only succeeded.")
        expect(panel.locator('[data-handoff-revision="different_revision"]')).to_be_visible()
        panel.locator('[data-handoff-node="input"]').click()
        expect(panel.locator('[data-handoff-proof="input"]')).to_contain_text("revision-2")
        page.locator("#close").click()
        ask(page, FOLLOWUP)
        tests = panel.locator('[data-handoff-tests]')
        expect(tests).to_have_attribute("data-handoff-action", "action-first-1")
        expect(tests).to_have_attribute("data-handoff-attempt", "attempt-action-first-1")
        reply = page.locator("#messages .msg.atlas").last
        expect(reply).to_contain_text("test_empty_input_is_zero")
        expect(reply).to_contain_text("test_skips_non_dictionaries_and_inexact_outcomes")
        expect(reply).to_contain_text("Связи отдельных выводов с тестами не записаны")
        expect(tests).to_contain_text("Для отдельных выводов связь с тестами не записана.")
        tests.locator('[data-handoff-protocol] summary').press("Enter")
        expect(tests.locator('[data-handoff-protocol]')).to_contain_text("Ran 3 tests")
        if width == 375:
            page.locator("#close").click()
        ask(page, CHANGES)
        changes = panel.locator('[data-handoff-view="changes"]')
        diff = changes.locator('[data-atlas-diff="runstats/counts.py"]')
        expect(diff).to_be_visible()
        expect(diff).to_contain_text("-    return len(rows)")
        predicate = 'if isinstance(row, dict) and row.get("outcome") == "succeeded"'
        expect(diff).to_contain_text(predicate)
        expect(reply).to_contain_text("runstats/counts.py")
        expect(reply).to_contain_text("len(rows)")
        expect(reply).to_contain_text(predicate)
        related = changes.locator("[data-handoff-tests]")
        expect(related).to_have_attribute("data-handoff-action", "action-first-1")
        expect(related).to_have_attribute("data-handoff-attempt", "attempt-action-first-1")
        expect(related.locator("[data-handoff-case]")).to_have_count(3)
        expect(related.get_by_role("button", name="test_empty_input_is_zero",
                                   exact=False)).to_be_visible()
        changes.locator('[data-focus="atlas:file:tests/test_counts.py"]').click()
        expect(changes.locator('[data-atlas-diff="tests/test_counts.py"]')).to_contain_text(
            "+        self.assertEqual(count_succeeded(rows), 2)")
        expect(related).to_contain_text("test_skips_non_dictionaries_and_inexact_outcomes")
        expect(page.locator("#messages .msg.user")).to_have_count(3)
        assert requests and set(requests) == {"action-first-1"}
        assert writes == []
    finally:
        close_context(context)


def test_switching_sessions_during_read_never_paints_or_replies_with_foreign_tests(
        chromium, atlas_url, tmp_path):
    context = chromium.new_context(viewport={"width": 1440, "height": 850})
    page = context.new_page()
    journal = handoff_read(tmp_path / "root")
    page.route("**/command/runs/first", lambda route: route.fulfill(json=journal))
    page.add_init_script("""const fetchNormally = window.fetch.bind(window);
        window.fetch = (url, options) => String(url).endsWith('/actions/action-first-2')
        ? new Promise(done => { window.deliverFirst = row =>
          done(new Response(JSON.stringify(row), {headers: {'Content-Type':'application/json'}}));
        })
        : fetchNormally(url, options);""")
    try:
        page.goto(atlas_url + "/#session=first&lang=ru")
        expect(page.locator('#orbitHere [data-step="repair-counter"]')).to_be_attached()
        ask(page, QUESTION)
        expect(page.locator('[data-handoff-view="handoff"]')).to_be_visible()
        page.locator("#close").click()
        ask(page, FOLLOWUP)
        page.wait_for_function("typeof window.deliverFirst === 'function'")
        ask(page, CHANGES)
        page.locator("#close").click()
        page.locator('[data-session="run/second"]').click()
        expect(page.locator("#messages")).not_to_contain_text(QUESTION)
        page.evaluate("row => window.deliverFirst(row)", native_protocol())
        page.evaluate("() => new Promise(requestAnimationFrame)")
        expect(page.locator('[data-handoff-tests]')).to_have_count(0)
        expect(page.locator('[data-atlas-diff]')).to_have_count(0)
        ask(page, FOLLOWUP)
        expect(page.locator("#messages .msg.atlas").last).to_contain_text("Выберите запуск")
        expect(page.locator("#messages")).not_to_contain_text("Ran 3 tests")
        page.locator('[data-session="run/first"]').click()
        expect(page.locator("#messages")).to_contain_text(QUESTION)
        expect(page.locator("#messages")).not_to_contain_text("len(rows)")
        expect(page.locator('[data-handoff-tests]')).to_have_count(0)
    finally:
        close_context(context)


def test_followup_refuses_a_protocol_for_an_earlier_attempt(chromium, atlas_url, tmp_path):
    context = chromium.new_context()
    page = context.new_page()
    journal = handoff_read(tmp_path / "root")
    page.route("**/command/runs/first", lambda route: route.fulfill(json=journal))
    old = native_protocol()
    old["tests"]["protocol"]["binding"]["attempt"] = "attempt-action-first-1"
    page.route("**/steps/repair-counter/actions/action-first-2", lambda r: r.fulfill(json=old))
    try:
        page.goto(atlas_url + "/#session=first&lang=ru")
        expect(page.locator('#orbitHere [data-step="repair-counter"]')).to_be_attached()
        ask(page, QUESTION)
        expect(page.locator('[data-handoff-view="handoff"]')).to_be_visible()
        page.locator("#close").click()
        ask(page, FOLLOWUP)
        expect(page.locator("#inspection")).to_contain_text("Сведения об этой попытке недоступны")
        expect(page.locator('[data-handoff-tests]')).to_have_count(0)
        expect(page.locator("#inspection")).not_to_contain_text("Ran 3 tests")
        ask(page, CHANGES)
        expect(page.locator("#messages .msg.atlas").last).to_contain_text(
            "Доказательства этой попытки не подтверждены")
        expect(page.locator("#inspection [data-atlas-diff]")).to_have_count(0)
        expect(page.locator("#inspection [data-handoff-case]")).to_have_count(0)
    finally:
        close_context(context)


def test_closing_retains_the_handoff_but_selecting_the_whole_cycle_releases_it(
        chromium, atlas_url, tmp_path):
    context = chromium.new_context()
    page = context.new_page()
    journal = handoff_read(tmp_path / "root")
    page.route("**/command/runs/first", lambda route: route.fulfill(json=journal))
    requests = []

    def attempt(route):
        requests.append(route.request.url)
        route.fulfill(json=native_protocol())

    page.route("**/steps/repair-counter/actions/action-first-2", attempt)
    try:
        page.goto(atlas_url + "/#session=first&lang=ru")
        expect(page.locator('#orbitHere [data-step="repair-counter"]')).to_be_attached()
        ask(page, QUESTION)
        expect(page.locator('[data-handoff-view="handoff"]')).to_be_visible()
        page.locator("#close").click()
        ask(page, FOLLOWUP)
        expect(page.locator("[data-handoff-tests]")).to_have_attribute(
            "data-handoff-attempt", "attempt-action-first-2")
        page.locator("[data-atlas-scope]").select_option("")
        ask(page, FOLLOWUP)
        expect(page.locator("#messages .msg.atlas").last).to_contain_text("Выберите запуск")
        expect(page.locator("[data-handoff-tests]")).to_have_count(0)
        assert len(requests) == 1
    finally:
        close_context(context)
