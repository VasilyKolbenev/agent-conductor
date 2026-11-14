"""A task can use the workflow its author publishes in a separate Studio tab."""
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import expect

from browser_tests.desk_hold import close_context
from browser_tests.test_desk_wizard_host import wizard_url
from browser_tests.test_studio_lifecycle import _publish, _save_draft, _start_from_starter


def _catalog_response(response):
    return urlsplit(response.url).path == "/command/workflows"


@pytest.mark.parametrize("lang,width", [("ru", 375), ("en", 1280)])
def test_publish_and_choose_a_personal_cycle_without_losing_the_task(
        chromium, wizard_url, lang, width):
    context = chromium.new_context(viewport={"width": width, "height": 820})
    try:
        desk = context.new_page()
        posts = []
        context.on("request", lambda req: posts.append(urlsplit(req.url).path)
                   if req.method == "POST" else None)
        desk.goto(f"{wizard_url}#new=task&lang={lang}")
        form = desk.locator("#deskWizard")
        goal = "Check this year's results\nKeep the original totals."
        note = "Use the annual totals from both sheets."
        form.locator('[data-focus="wizard:brief"]').fill(goal)
        form.locator('[data-focus="wizard:next"]').click()
        expect(form.locator('[data-answer="goal"]')).to_contain_text(goal)
        options = form.locator('[data-guide-details="optional"]')
        options.locator("summary").click()
        form.locator('[data-focus="wizard:add:plan"]').click()
        material = options.locator('[data-card][data-kind="plan"]')
        material.locator('input[name="title"]').fill("Annual report")
        material.locator('textarea[name="content"]').fill(note)
        form.locator('[data-focus="wizard:git:run_without_git"]').click()
        form.locator('[data-focus="wizard:next"]').click()
        choose = form.locator('[data-guide-details="choose"]')
        if not choose.evaluate("item => item.open"):
            choose.locator("summary").click()
        build = form.locator('[data-card-id="build"]')
        link = build.get_by_role("link")
        expect(link).to_be_visible()
        # A catalog response redraws the card. Measure both live children in one DOM read.
        bounds = form.evaluate("""mount => {
            const card = mount.querySelector('[data-card-id="build"]');
            const link = card.querySelector('a').getBoundingClientRect();
            const note = card.querySelector('small').getBoundingClientRect();
            return {link: link.toJSON(), note: note.toJSON()};
        }""")
        assert all(box["width"] > 0 and box["height"] > 0 for box in bounds.values()), bounds
        assert bounds["note"]["top"] >= bounds["link"]["bottom"], bounds
        with context.expect_page() as opened:
            link.click()
        editor = opened.value
        query = parse_qs(urlsplit(editor.url).fragment)
        assert query["screen"] == ["workflow"] and query["lang"] == [lang]
        assert editor.evaluate("window.opener === null")
        expect(editor.locator("#screenWorkflow")).to_be_visible()
        workflow_id = "colleague-custom"
        _start_from_starter(editor, workflow_id)
        _save_draft(editor)
        reread = build.locator('[data-focus="wizard:cycle:refresh-catalog"]')
        with desk.expect_response(_catalog_response):
            reread.click()
        custom = choose.locator(f'[data-card-id="{workflow_id}"]')
        expect(custom).to_have_count(0)
        _publish(editor)
        expect(editor.locator('.studio-canvas__banner[data-document="published"]')).to_be_visible()
        editor.close()
        desk.route("**/command/workflows", lambda route: route.fulfill(
            status=503, json={"error": "offline"}), times=1)
        with desk.expect_response(_catalog_response) as refused:
            reread.click()
        assert refused.value.status == 503
        expect(build.get_by_role("status")).to_be_visible()
        expect(custom).to_have_count(0)
        with desk.expect_response(_catalog_response) as fresh:
            reread.click()
        expect(custom).to_be_visible()
        rows = fresh.value.json()["workflows"]
        assert [row["latest_revision"] for row in rows if row["workflow_id"] == workflow_id] == [1]
        custom.locator(f'[data-focus="wizard:cycle:choose:{workflow_id}"]').click()
        expect(custom).to_have_attribute("data-chosen", "true")
        expect(custom.get_by_text("ревизия 1" if lang == "ru" else "revision 1",
                                  exact=True)).to_be_visible()
        form.locator('[data-focus="wizard:ask:edit-files"]').click()
        source = form.locator('[data-focus="wizard:git:run_without_git"]')
        expect(source).to_have_attribute("aria-checked", "true")
        if not options.evaluate("item => item.open"):
            options.locator("summary").click()
        expect(material.locator('input[name="title"]')).to_have_value("Annual report")
        expect(material.locator('textarea[name="content"]')).to_have_value(note)
        form.locator('[data-focus="wizard:ask:edit-goal"]').click()
        expect(form.locator('[data-focus="wizard:brief"]')).to_have_value(goal)
        assert all(path == "/command/project/task-draft" or path.startswith("/command/workflows/")
                   for path in posts), sorted(set(posts))
        base = wizard_url.partition("/panel/")[0]
        assert desk.request.get(f"{base}/command/runs").json()["runs"] == []
        assert desk.request.get(f"{base}/command/tasks").json()["tasks"] == []
    finally:
        close_context(context)
