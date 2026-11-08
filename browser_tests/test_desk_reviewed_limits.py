"""A colleague changes the server's suggested bounds on the same prepared task."""
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import expect

from browser_tests.test_desk_wizard_host import wizard_url  # noqa: F401


@pytest.mark.parametrize(("lang", "width"), [("ru", 375), ("en", 1280)])
@pytest.mark.parametrize("wizard_url", [True], indirect=True)
def test_edit_desk_bounds_before_authorizing_the_reviewed_terms(chromium, wizard_url, lang, width):
    context = chromium.new_context(viewport={"width": width, "height": 900})
    try:
        page = context.new_page()
        posts, errors = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda req: posts.append(urlsplit(req.url).path) if req.method == "POST" else None)
        page.goto(f"{wizard_url}#lang={lang}")
        page.locator("#deskNewTask").click()
        form = page.locator("#deskWizard")

        def field(key):
            return form.locator(f'[data-focus="wizard:{key}"]')

        field("brief").fill("Review the counter and its tests.")
        field("next").click()
        field("git:run_without_git").click()
        field("next").click()
        field("next").click()
        preview_path = "/automation/preview"
        def is_preview(response):
            return response.request.method == "POST" and urlsplit(response.url).path.endswith(preview_path)

        with page.expect_response(is_preview) as initial:
            field("prepare:go").click()
        recommended = initial.value.json()
        terms = recommended["terms"]
        run_path = urlsplit(initial.value.url).path.removesuffix(preview_path)
        first_run = page.request.get(initial.value.url.split("/automation/preview")[0]).json()
        task, run = first_run["config"]["task"]["id"], terms["run_id"]
        link = form.get_by_role("button", name="Изменить лимиты в Studio" if lang == "ru" else "Edit limits in Studio")
        expect(link).to_be_visible()
        link.click()

        limits = page.locator(f'[data-automation="{run}"]')
        total = limits.locator('[data-focus="automation:run:max_actions"]')
        expect(total).to_be_visible()
        expect(total).to_be_focused()
        assert parse_qs(urlsplit(page.url).fragment)["task"] == [task]
        assert parse_qs(urlsplit(page.url).fragment)["run"] == [run]
        transfer = page.evaluate("history.state.deskLimitEditor")
        assert set(transfer) == {"project", "embed", "task", "run", "bounds"}
        assert transfer["bounds"] == {key: terms[key] for key in (
            "max_actions", "max_action_seconds", "max_total_task_seconds", "duration_seconds", "node_limits")}
        for name in ("max_actions", "max_action_seconds", "max_total_task_seconds", "duration_seconds"):
            expect(limits.locator(f'[data-focus="automation:run:{name}"]')).to_have_value(str(terms[name]))
        for row in terms["node_limits"]:
            for key in ("timeout_seconds", "max_attempts"):
                expect(limits.locator(f'[data-focus="automation:{row["node_id"]}:{key}"]')).to_have_value(str(row[key]))
        assert posts.count(run_path + preview_path) == 1
        expect(limits.locator("[data-automation-preview]")).to_have_count(0)
        assert not any(path.endswith("/automation/authorize") for path in posts)
        page.go_back()
        expect(page.locator("#deskWizard")).to_be_hidden()
        expect(page.locator(f'#deskScene [data-deck-run="{run}"]')).to_be_visible()
        page.go_forward()
        expect(total).to_have_value(str(terms["max_actions"]))
        assert posts.count(run_path + preview_path) == 1
        total.fill("0")
        expect(limits.locator("[data-invalid-bounds]")).to_be_visible()
        expect(limits.locator('[data-focus="automation:preview"]')).to_be_disabled()
        changed = terms["max_actions"] - 1
        assert changed > 0
        total.fill(str(changed))
        expect(limits.locator("[data-invalid-bounds]")).to_have_count(0)
        with page.expect_response(is_preview) as adjusted:
            limits.locator('[data-focus="automation:preview"]').click()
        assert adjusted.value.status == 200
        updated = adjusted.value.json()
        assert updated["terms"]["max_actions"] == changed
        assert updated["preview_digest"] != recommended["preview_digest"]
        expect(limits.locator("[data-automation-preview]")).to_be_visible()
        # An edit retires even an already reviewed custom preview.
        changed -= 1
        assert changed > 0
        total.fill(str(changed))
        expect(limits.locator("[data-automation-preview]")).to_have_count(0)
        expect(limits.locator('[data-focus="automation:authorize"]')).to_have_count(0)
        with page.expect_response(is_preview) as reviewed:
            limits.locator('[data-focus="automation:preview"]').click()
        assert reviewed.value.status == 200
        previous = updated
        updated = reviewed.value.json()
        assert updated["preview_digest"] != previous["preview_digest"]
        assert updated["terms"]["max_actions"] == changed
        assert not any(path.endswith("/automation/authorize") for path in posts)
        assert not any(row["record_type"] == "run_authorization" for row in page.request.get(
            adjusted.value.url.removesuffix(preview_path)).json()["records"])
        limits.locator('[data-focus="automation:run:actor"]').fill("colleague-demo")
        with page.expect_response(lambda res: res.url.endswith("/automation/authorize")) as allowed:
            limits.locator('[data-focus="automation:authorize"]').click()
        assert allowed.value.status == 201, allowed.value.json()
        sent = allowed.value.request.post_data_json
        assert allowed.value.request.headers["x-conduct-project"] == transfer["project"]
        assert sent["terms"] == updated["terms"] and sent["preview_digest"] == updated["preview_digest"]
        rows = page.request.get(allowed.value.url.removesuffix("/automation/authorize")).json()["records"]
        grants = [row["record"] for row in rows if row["record_type"] == "run_authorization"]
        assert len(grants) == 1 and grants[0]["max_actions"] == changed
        limits.get_by_role("link", name="Вернуться в Desk" if lang == "ru" else "Return to Desk").click()
        expect(page.locator("#deskWizard")).to_be_hidden()
        assert parse_qs(urlsplit(page.url).fragment)["run"] == [run]
        expect(page.locator(f'#deskScene [data-deck-run="{run}"]')).to_be_visible()
        assert posts.count(run_path + "/automation/authorize") == 1
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert errors == []
    finally:
        context.close()
