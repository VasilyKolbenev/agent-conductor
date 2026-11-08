"""The Studio's actual preview route supplies a recommendation and still permits manual editing."""
from playwright.sync_api import expect

from browser_tests.desk_hold import close_context
from browser_tests.desk_wizard_bench import bench, desk_url
from browser_tests.test_desk_wizard_launch import to_card
from browser_tests.test_studio_automation_browser import _open, bounded_project
from tests.test_task_preparation import Project


def test_depth_then_manual_bound_reaches_server_without_authorizing(chromium, bounded_project):
    project, adapter = bounded_project
    page, window = _open(chromium, project)
    try:
        page.set_viewport_size({"width": 375, "height": 812})
        page.get_by_role("button", name="Read this run", exact=True).click()
        box = page.locator('[data-automation="run"]')
        choose = box.locator('[data-focus="automation:budget_depth"]')
        with page.expect_response(lambda r: r.url.endswith("/automation/preview")) as quick:
            choose.select_option("quick")
        assert quick.value.status == 200
        assert quick.value.request.post_data_json == {"recommendation": {"depth": "quick"}}
        expect(box.locator('[data-budget-guidance="quick"]')).to_contain_text("No comparable")
        with page.expect_response(lambda r: r.url.endswith("/automation/preview")) as thorough:
            choose.select_option("thorough")
        assert thorough.value.status == 200
        expect(box.locator('[data-budget-guidance="thorough"]')).to_be_visible()
        box.get_by_role("button", name="Edit limits").click()
        seconds = box.locator('[data-focus="automation:run:duration_seconds"]')
        seconds.fill("7200")
        with page.expect_response(lambda r: r.url.endswith("/automation/preview")) as custom:
            box.locator('[data-focus="automation:preview"]').click()
        assert custom.value.request.post_data_json["duration_seconds"] == 7200
        assert "recommendation" not in custom.value.request.post_data_json
        assert custom.value.status == 200, custom.value.json()
        assert window.writes("/automation/authorize") == 0 and adapter.execute_calls == 0
    finally:
        close_context(page.context)


def test_desk_card_renders_the_server_budget_and_edits_just_the_preview(bench, tmp_path):
    project = Project(tmp_path / "product")
    run = project.open_run(1, task_id="task-bench")
    project.publish(run, "artifact-brief", "artifact-materials", "instruction-do")
    first, quick = (project.policy.preview(run, {"recommendation": {"depth": depth}})
                    for depth in ("balanced", "quick"))
    bench.page.set_viewport_size({"width": 375, "height": 812})
    to_card(bench, "ru", preview=first, overrides=[quick], clock=first["previewed_at"])
    panel = bench.page.locator('[data-budget-guidance="balanced"]')
    expect(panel).to_contain_text("Сопоставимых замеров пока нет")
    bench.control("wizard:budget:why").click()
    expect(panel).to_contain_text("Исходный запас на участника")
    bench.control("wizard:budget:quick").click()
    expect(bench.page.locator('[data-budget-guidance="quick"]')).to_be_visible()
    assert bench.bodies("launch_preview")[-1] == {"recommendation": {"depth": "quick"}}
    assert bench.bodies("launch_authorize") == []
