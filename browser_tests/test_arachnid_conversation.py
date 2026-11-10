"""The main project page keeps Atlas and selects exact attempt evidence on the orbit."""
from dataclasses import replace
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import expect

from browser_tests.desk_hold import close_context
from browser_tests.test_studio_atlas import atlas_url, evidence  # noqa: F401
from conductor.command.run_store import RunStore
from conductor.command.studio_routes import recovered_payload
from conductor.command.task_store import TaskStore


def select(page, value):
    page.evaluate("(value) => { location.hash = value; }", value)


def test_pinned_scope_and_summary_follow_the_chosen_request(chromium, atlas_url, tmp_path):
    context = chromium.new_context(viewport={"width": 1440, "height": 860})
    page = context.new_page()
    writes = []
    reads = []
    root = tmp_path / "root"
    current = RunStore(root).read("first")
    assert current.records[-1].kind == "action_request"
    assert current.records[-1].value.action_id == "action-first-2"
    earlier = replace(current, records=current.records[:-1])
    page.on("request", lambda req: writes.append(req.method) if req.method != "GET" else None)

    def journal(route):
        route.fulfill(json=recovered_payload(revision, TaskStore(root),
                                            computed_at="2026-11-10T10:00:00Z"))

    def attempt(route):
        action = urlsplit(route.request.url).path.split("/")[-1]
        reads.append(action)
        row = evidence(action)
        if action == "action-first-1":
            row["files_total"] = 2
            row["tests"]["summary"].update(total=7, failures=1, errors=0, skipped=2)
        else:
            row.update(outcome=None, verdict=None, files_total=None, files=[], manifest_digest=None)
            row["tests"].update(status="not_recorded", summary=None, source=None)
        route.fulfill(json=row)

    try:
        revision = earlier
        page.route("**/command/runs/first", journal)
        page.route("**/steps/repair-counter/actions/*", attempt)
        page.goto(atlas_url + "/#session=first&lang=en")
        orbit = page.locator("#orbitHere [data-step=repair-counter]")
        expect(orbit).to_be_visible()
        field = page.locator("#command")
        scope = page.locator("#scopeHere select")
        field.fill("What changed?")
        field.press("Enter")
        expect(page.locator("#messages")).to_contain_text("Choose a step")
        assert reads == []
        orbit.click()
        summary = page.locator("#inspection .atlas-attempt-summary")
        facts = lambda key: summary.locator(f'[data-atlas-fact="{key}"]')
        expect(facts("files")).to_contain_text("Showing 1 of 2")
        expect(facts("files")).to_contain_text("action-first-1.py")
        expect(facts("tests")).to_contain_text("total 7, failures 1, errors 0, skipped 2")
        expect(facts("checker")).to_contain_text("checker")
        expect(facts("verdict")).to_have_text("Snapshot verified")
        field.fill("Which test?")
        field.press("Enter")
        reply = page.locator("#messages .msg.atlas").last
        expect(reply).to_contain_text("test_action_first_1")
        expect(reply.locator(".atlas-origin")).to_contain_text("Do")
        expect(reply.locator(".atlas-origin")).to_contain_text("1")
        revision = current
        select(page, "session=first&lang=en&theme=dark")
        pick = page.locator("#inspection [data-atlas-attempt]")
        expect(pick.locator("option")).to_have_count(2)
        expect(pick).to_have_value("action-first-1")
        expect(facts("tests")).to_contain_text("total 7")
        page.locator("#close").click()
        expect(scope.locator("option:checked")).to_contain_text("Do")
        page.locator("#limits").click()
        expect(scope.locator("option:checked")).to_contain_text("Do")
        orbit.click()
        pick.select_option("action-first-2")
        expect(facts("outcome")).to_contain_text("No result")
        expect(facts("files")).to_contain_text("no confirmed file snapshot")
        expect(facts("tests")).to_contain_text("No test report")
        expect(facts("checker")).not_to_contain_text("checker")
        expect(facts("verdict")).to_contain_text("No independent verdict")
        expect(reply.locator(".atlas-origin")).to_contain_text("1")
        revision = earlier
        select(page, "session=first&lang=en&theme=light")
        expect(page.locator("#inspection")).to_contain_text("selected attempt")
        expect(summary).to_have_count(0)
        expect(scope.locator("option:checked")).to_contain_text("2")
        expect(scope).to_be_visible()
        scope.select_option(label="Whole cycle")
        expect(page.locator("#detail")).to_be_hidden()
        assert not writes, writes
    finally:
        close_context(context)


def test_reset_scope_refuses_a_success_delivered_after_reset(chromium, atlas_url):
    context = chromium.new_context()
    page = context.new_page()
    try:
        page.add_init_script("""const normal = globalThis.fetch.bind(globalThis);
            globalThis.fetch = (url, options) =>
              String(url).endsWith("/actions/action-first-2") ? new Promise(resolve => {
                window.finishAttempt = v => resolve(new Response(JSON.stringify(v)));
              }) : normal(url, options);""")
        page.goto(atlas_url + "/#session=first&lang=en")
        page.locator("#orbitHere [data-step=repair-counter]").click()
        field = page.locator("#command")
        field.fill("Which test?")
        field.press("Enter")
        expect(page.locator("#messages .msg.atlas").last).to_contain_text("Reading this attempt")
        scope = page.locator("#scopeHere select")
        expect(scope).to_be_visible()
        scope.select_option(label="Whole cycle")
        page.evaluate("""async v => {
            window.finishAttempt(v);
            await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
        }""", evidence("action-first-2"))
        expect(page.locator("#messages")).not_to_contain_text("test_action_first_2")
        expect(page.locator("#inspection .atlas-attempt-summary")).to_have_count(0)
        expect(scope.locator("option:checked")).to_have_text("Whole cycle")
    finally:
        close_context(context)


def test_gate_sheet_returns_keyboard_to_the_visible_scope(chromium, atlas_url):
    context = chromium.new_context(viewport={"width": 375, "height": 850})
    page = context.new_page()
    try:
        page.goto(atlas_url + "/#session=first&lang=en")
        scope = page.locator("#scopeHere select")
        field = page.locator("#command")
        field.fill("leave this draft here")
        expect(page.locator("#orbitHere [data-step=authorize]")).to_have_count(0)
        scope.select_option("authorize")
        expect(page.locator("#inspection h2")).to_have_text("Authorize")
        page.locator("#close").focus()
        page.keyboard.press("Escape")
        expect(page.locator("#detail")).to_be_hidden()
        expect(scope).to_be_visible()
        expect(scope).to_be_focused()
        expect(scope).to_have_value("authorize")
        expect(field).to_have_value("leave this draft here")
    finally:
        close_context(context)


@pytest.mark.parametrize("lang,caption", [("en", "Execution IDs"), ("ru", "Идентификаторы")])
def test_identity_tracks_the_attempt_across_tabs_and_resize(chromium, atlas_url, lang, caption):
    context = chromium.new_context(viewport={"width": 1400, "height": 880})
    page = context.new_page()
    writes = []
    page.on("request", lambda req: writes.append(req.method) if req.method != "GET" else None)

    def respond(route):
        action = urlsplit(route.request.url).path.split("/")[-1]
        row = evidence(action)
        if action == "action-first-1":
            row["verdict"]["status"] = "mismatch"
            row["manifest_digest"] = "sha256:" + "2" * 64
        route.fulfill(json=row)

    try:
        page.route("**/steps/repair-counter/actions/*", respond)
        page.goto(atlas_url + "/#session=first&lang=" + lang)
        field = page.locator("#command")
        field.fill("keep the draft while I inspect")
        page.locator("#orbitHere [data-step=repair-counter]").click()
        panel = page.locator("#inspection")
        expect(panel.locator("[data-atlas-diff]")).to_contain_text("+new-action-first-2")
        ids = panel.locator("details").filter(has=page.locator("summary", has_text=caption))
        expect(ids.locator("summary")).to_be_visible()
        ids.locator("summary").click()
        expect(ids.locator("dd")).to_have_text(
            ["first", "repair-counter", "action-first-2", "attempt-action-first-2"])

        panel.locator("[data-atlas-attempt]").select_option("action-first-1")
        values = ["first", "repair-counter", "action-first-1", "attempt-action-first-1"]
        for tab, witness in (("diff", "+new-action-first-1"), ("tests", "test_action_first_1"),
                             ("verdict", "sha256:" + "2" * 64)):
            panel.locator("[data-atlas-tab=" + tab + "]").click()
            expect(ids).to_have_js_property("open", True)
            expect(ids.locator("dd")).to_have_text(values)
            expect(panel.locator("[role=tabpanel]")).to_contain_text(witness)
        field.focus()
        page.set_viewport_size({"width": 1040, "height": 720})
        expect(field).to_be_focused()
        expect(field).to_have_value("keep the draft while I inspect")
        expect(panel.locator("[role=tabpanel]")).to_contain_text("sha256:" + "2" * 64)
        expect(ids.locator("dd")).to_have_text(values)
        assert not writes, writes
    finally:
        close_context(context)


def test_root_orbit_changes_attempt_keeps_chat_and_routes_limit_query(chromium, atlas_url):
    context = chromium.new_context(viewport={"width": 1360, "height": 880})
    page = context.new_page()
    writes = []
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda req: writes.append(req.method) if req.method != "GET" else None)

    def respond(route):
        path = urlsplit(route.request.url).path.split("/")
        route.fulfill(json=evidence(path[-1], run=path[3]))

    try:
        page.route("**/steps/repair-counter/actions/*", respond)
        page.goto(atlas_url + "/#session=first&lang=en")
        orbit = page.locator("#orbitHere")
        node = orbit.locator('[data-step="repair-counter"]')
        expect(node).to_be_visible(timeout=5000)
        field = page.locator("#command")
        field.fill("draft stays here")
        node.focus()
        node.press("Enter")
        panel = page.locator("#inspection")
        expect(panel.locator("[data-atlas-diff]")).to_contain_text("new-action-first-2")
        expect(field).to_have_value("draft stays here")
        expect(field).to_be_visible()
        panel.locator("[data-atlas-attempt]").select_option("action-first-1")
        panel.locator("[data-atlas-tab=tests]").click()
        expect(panel).to_contain_text("action-first-1")
        expect(panel).not_to_contain_text("new-action-first-2")
        panel.locator("[data-atlas-tab=verdict]").click()
        expect(panel.locator("[role=tabpanel]")).to_contain_text("Snapshot verified")
        expect(panel.locator("[role=tabpanel]")).to_contain_text("checker")
        field.fill("Which test checks the fix?")
        field.press("Enter")
        expect(page.locator("#messages")).to_contain_text("test_action_first_1")
        field.fill("keep the first draft")
        select(page, "session=second&lang=en")
        expect(field).to_have_value("")
        expect(page.locator("#messages")).not_to_contain_text("test_action_first_1")
        select(page, "session=first&lang=en")
        expect(field).to_have_value("keep the first draft")
        expect(page.locator("#messages")).to_contain_text("test_action_first_1")
        field.fill("покажи лимиты")
        field.press("Enter")
        expect(page.locator("#detail")).to_be_visible()
        expect(page.locator("#inspection [data-atlas-diff]")).to_have_count(0)
        assert not writes and not errors, (writes, errors)
    finally:
        close_context(context)


def test_late_completed_read_is_ignored_after_the_operator_changes_session(chromium, atlas_url):
    context = chromium.new_context(viewport={"width": 1280, "height": 850})
    page = context.new_page()
    try:
        # A stale successful fetch must be harmless even when abort cannot cancel its delivery.
        page.add_init_script("""const normal = globalThis.fetch.bind(globalThis);
            globalThis.fetch = (url, options) =>
              String(url).endsWith("/actions/action-first-2") ? new Promise(resolve => {
                window.deliverOld = value => resolve(new Response(JSON.stringify(value),
                  {headers: {"Content-Type": "application/json"}}));
              }) : normal(url, options);""")
        page.route("**/actions/action-second-2",
                   lambda route: route.fulfill(json=evidence("action-second-2", run="second")))
        page.goto(atlas_url + "/#session=first&lang=en")
        page.locator("#orbitHere [data-step]").first.click()
        page.wait_for_function("typeof window.deliverOld === 'function'")
        select(page, "session=second&lang=en")
        page.locator("#orbitHere [data-step]").first.click()
        view = page.locator("#inspection [data-atlas-diff]")
        expect(view).to_contain_text("new-action-second-2")
        page.evaluate("""async old => {
            window.deliverOld(old);
            await new Promise(resolve =>
              requestAnimationFrame(() => requestAnimationFrame(resolve)));
        }""", evidence("action-first-2"))
        expect(view).to_contain_text("new-action-second-2")
        expect(page.locator("#inspection")).not_to_contain_text("new-action-first-2")
    finally:
        close_context(context)


def test_foreign_attempt_response_never_enters_conversation(chromium, atlas_url):
    context = chromium.new_context(viewport={"width": 1100, "height": 800})
    page = context.new_page()
    try:
        wrong = evidence("action-first-2")
        wrong["attempt_id"] = "other-attempt"
        page.route("**/steps/repair-counter/actions/*", lambda route: route.fulfill(json=wrong))
        page.goto(atlas_url + "/#session=first&lang=en")
        page.locator("#orbitHere [data-step]").first.click(timeout=5000)
        panel = page.locator("#inspection")
        expect(panel).to_contain_text("could not be confirmed")
        expect(panel).not_to_contain_text("new-action-first")
        field = page.locator("#command")
        field.fill("What changed?")
        field.press("Enter")
        expect(page.locator("#messages")).to_contain_text("could not be confirmed")
        expect(page.locator("#messages")).not_to_contain_text("new-action-first")
        select(page, "new=1&lang=en")
        expect(field).to_have_value("")
        expect(page.locator("#orbitHere [data-step]")).to_have_count(0)
    finally:
        close_context(context)


def test_narrow_evidence_sheet_returns_keyboard_to_the_selected_orbit_step(chromium, atlas_url):
    context = chromium.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    try:
        page.route("**/actions/action-first-2",
                   lambda route: route.fulfill(json=evidence("action-first-2")))
        page.goto(atlas_url + "/#session=first&lang=en")
        field = page.locator("#command")
        field.fill("keep this while I inspect")
        step = page.locator("#orbitHere [data-step=repair-counter]")
        step.focus()
        step.press("Enter")
        panel = page.locator("#inspection")
        expect(panel.locator("[data-atlas-diff]")).to_contain_text("new-action-first-2")
        expect(page.locator("#chat")).to_have_js_property("inert", True)
        page.locator("#close").focus()
        page.keyboard.press("Escape")
        expect(page.locator("#detail")).to_be_hidden()
        expect(step).to_be_focused()
        expect(field).to_have_value("keep this while I inspect")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    finally:
        close_context(context)
