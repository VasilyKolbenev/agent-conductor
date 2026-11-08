"""A subscriber can leave their task open while connecting a harness on the same project."""
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import expect

from browser_tests.desk_hold import until
from browser_tests.test_desk_wizard_git_pin import active_project
from browser_tests.test_desk_wizard_host import wizard_url  # noqa: F401
from conductor import ownership_transition
from tests.test_store import good_lane, write_project


@pytest.mark.parametrize(("lang", "width"), [("ru", 375), ("en", 1280)])
def test_return_from_participant_setup_reloads_the_real_roster_without_losing_answers(chromium, tmp_path, lang, width):
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    ownership_transition.activate(root, legacy_writers_stopped=True)
    context = chromium.new_context(viewport={"width": width, "height": 900})
    try:
        page = context.new_page()
        posts = []
        page.on("request", lambda req: posts.append(urlsplit(req.url).path) if req.method == "POST" else None)
        with active_project(root, subscriptions=False) as port:
            page.goto(f"http://127.0.0.1:{port}/panel/desk.html#lang={lang}")
            page.locator("#deskNewTask").click()
            form = page.locator("#deskWizard")
            def key(name):
                return form.locator(f'[data-focus="wizard:{name}"]')
            goal, note = "Check the counter.", "Read both mixed rows."
            key("brief").fill(goal)
            form.locator('[data-guide-details="optional"] summary').click()
            key("add:plan").click()
            card = form.locator('[data-card][data-kind="plan"]')
            card.locator('input[name="title"]').fill("Sample")
            card.locator('textarea[name="content"]').fill(note)
            key("next").click()
            key("git:run_without_git").click()
            key("next").click()
            setup = form.locator("[data-participant-setup]")
            expect(setup).to_be_visible()
            expect(setup).to_contain_text("conduct providers --dir .")
            with context.expect_page() as opened:
                setup.get_by_role("link").click()
            instructions = opened.value
            expect(instructions.locator("#screenAgents")).to_be_visible()
            expect(instructions.locator("#screenAgents")).to_contain_text("conduct providers")
            instructions.close()
            expect(form.locator('[data-answer="goal"]')).to_contain_text(goal)
            expect(key("next")).to_be_disabled()
            expect(form.locator('[data-draft="saved"]')).to_be_visible()
            old_key = page.evaluate("history.state.deskTaskDraft.key")
            def roster(res):
                return res.request.method == "GET" and urlsplit(res.url).path == "/command/workflows"

            def draft_read(res):
                return urlsplit(res.url).path == "/command/project/task-draft" and res.request.post_data_json["op"] == "read"

            with page.expect_response(draft_read) as kept, page.expect_response(roster) as still_empty:
                key("ask:participants").click()
            assert kept.value.status == 200
            assert still_empty.value.json()["providers"] == []
            expect(setup).to_be_visible()
            assert page.evaluate("history.state.deskTaskDraft.key") == old_key
        with active_project(root, port, subscriptions=True):
            held = {}
            def hold_check(route):
                if route.request.post_data_json["op"] == "read" and not held:
                    response = route.fetch()
                    if response.status == 403 and response.json()["error"]["code"] == "csrf_denied":
                        route.fulfill(response=response)
                    else:
                        held["route"], held["response"] = route, response
                else:
                    route.continue_()
            page.route("**/command/project/task-draft", hold_check)
            with page.expect_response(roster) as changed:
                key("ask:participants").click()
            providers = changed.value.json()["providers"]
            assert len(providers) == 2 and all(row["auth"] == "subscription" for row in providers)
            expect(form.locator('[data-guide-role="checker"]')).to_contain_text("codex")
            expect(form.locator('[data-guide-role="executor"]')).to_contain_text("claude-code")
            expect(setup).to_have_count(0)
            expect(form.locator('[data-draft="saving"]')).to_be_visible()
            assert page.evaluate("""() => !window.dispatchEvent(new Event("beforeunload", {cancelable: true}))""")
            until(page, "restarted server answered the read of the old draft", lambda: "response" in held)
            assert held["response"].status == 404
            held["route"].fulfill(response=held["response"])
            page.wait_for_function("old => history.state?.deskTaskDraft?.key && history.state.deskTaskDraft.key !== old", arg=old_key)
            expect(form.locator('[data-draft="saved"]')).to_be_visible()
            page.reload()
            expect(key("brief")).to_have_value(goal)
            form.locator('[data-guide-details="optional"] summary').click()
            expect(card.locator('textarea[name="content"]')).to_have_value(note)
            key("next").click()
            expect(form.locator('[data-guide-role="checker"]')).to_contain_text("codex")
            key("next").click()
            key("prepare:go").click()
            expect(form.locator("[data-guide-executors]")).to_be_visible()
            assert any(path.endswith("/automation/preview") for path in posts)
            assert not any(path.endswith("/automation/authorize") for path in posts)
    finally:
        context.close()


@pytest.mark.parametrize("wizard_url", [True], indirect=True)
def test_a_failed_roster_read_stays_unknown_and_an_api_only_team_can_still_continue(chromium, wizard_url):
    page = chromium.new_page(viewport={"width": 375, "height": 850})
    try:
        path = "**/command/workflows"
        page.goto(wizard_url + "#lang=en")
        page.locator("#deskNewTask").click()
        box = page.locator("#deskWizard")
        def key(name):
            return box.locator(f'[data-focus="wizard:{name}"]')
        key("brief").fill("Check the sample.")
        key("next").click()
        key("git:run_without_git").click()
        key("next").click()
        optional = box.locator('[data-participant-setup="optional"]')
        optional.locator("summary").click()
        page.route(path, lambda route: route.fulfill(status=503, json={"error": {"code": "store_error"}}))
        key("ask:participants").click()
        expect(box.locator("[data-participant-setup]")).to_contain_text("not confirmed")
        page.unroute(path)
        key("ask:participants").click()
        expect(optional).to_be_visible()
        expect(optional.get_by_role("link")).not_to_be_visible()
        expect(box.locator('[data-guide-role="checker"]')).to_contain_text("codex")
        expect(key("next")).to_be_enabled()
        optional.locator("summary").click()
        expect(optional.get_by_role("link")).to_be_visible()
    finally:
        page.context.close()
