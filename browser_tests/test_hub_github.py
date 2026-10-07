"""GitHub selection uses only the hub's public shapes, in both interface languages."""
import json

from playwright.sync_api import expect

from browser_tests.hub_bench import hub, hub_page, lang, ready, say  # noqa: F401


def connect(hub):
    hub.answer("/hub/github/status", {"state": "ok", "login": "owner", "login_command": None})
    hub.answer("/hub/github/repos", {"owner": None, "truncated": False, "repos": [
        {"full_name": "owner/example", "description": "A project", "visibility": "private",
         "updated_at": "2026-10-01T00:00:00Z", "archived": False, "fork": False}]})


def open_github(page):
    ready(page)
    page.page.locator('[data-focus="add-project"]').click()
    page.page.locator('[data-focus="source-github"]').click()


def test_repository_choice_and_cancel_use_exact_hub_bodies(hub_page, lang):
    page, hub = hub_page, hub_page.hub
    connect(hub)
    operation = "operation-" + "a" * 32
    hub.post_answers["/hub/projects"] = (202, {"operation_id": operation})
    hub.post_answers[f"/hub/operations/{operation}/cancel"] = (202, {"operation_id": operation})
    hub.answer(f"/hub/operations/{operation}", {"operation_id": operation, "kind": "add",
        "source": "github", "state": "running", "step": "clone", "project_id": None,
        "code": None, "result": None})
    open_github(page)
    page.page.locator('[data-focus="repo:owner/example"]').click()
    expect(page.page.locator('[data-focus="scratch-folder"]')).to_have_value("example")
    expect(page.page.locator('[data-focus="folder-name"]')).to_have_value("example")
    page.page.locator('[data-focus="folder-name"]').fill("My project")
    page.page.locator('[data-focus="folder-submit"]').click()
    with page.page.expect_response(lambda reply: reply.url.endswith(f"/{operation}/cancel")):
        page.page.locator('[data-focus="clone-cancel"]').click()
    assert hub.posts == [
        {"path": "/hub/projects", "body": {"source": "github", "repo": "owner/example",
            "folder": "example", "name": "My project"}},
        {"path": f"/hub/operations/{operation}/cancel", "body": {}}]
    hub.answer(f"/hub/operations/{operation}", {"operation_id": operation, "kind": "add",
        "source": "github", "state": "cancelled", "step": "clone", "project_id": None,
        "code": None, "result": None})
    expect(page.page.locator('[data-banner="folder-add"]')).to_contain_text(
        say(page, "hub.add.cancelled"))
    expect(page.page.locator('[data-focus="clone-cancel"]')).to_have_count(0)


def test_successful_clone_kept_after_admission_refusal(hub_page, lang):
    page, hub = hub_page, hub_page.hub
    connect(hub)
    operation = "operation-" + "b" * 32
    hub.post_answers["/hub/projects"] = (202, {"operation_id": operation})
    hub.answer(f"/hub/operations/{operation}", {"operation_id": operation, "kind": "add",
        "source": "github", "state": "failed", "step": "admit", "project_id": None,
        "code": "profile_invalid", "result": {"folder": "example", "cloned": True}})
    open_github(page)
    page.page.locator('[data-focus="repo:owner/example"]').click()
    page.page.locator('[data-focus="folder-submit"]').click()
    expect(page.page.locator('[data-banner="folder-add"]')).to_contain_text(
        say(page, "hub.add.cloned_not_added", folder="example"))
    expect(page.page.locator('[data-banner="folder-add"]')).not_to_contain_text("undefined")


def test_no_login_shows_terminal_instruction_and_does_not_write(hub_page, lang):
    page, hub = hub_page, hub_page.hub
    hub.answer("/hub/github/status", {"state": "not_logged_in", "login": None,
        "login_command": "gh auth login --hostname github.com --web"})
    open_github(page)
    expect(page.page.locator('[data-banner="folder-add"]')).to_contain_text(
        "gh auth login --hostname github.com --web")
    expect(page.page.locator('[data-focus="folder-submit"]')).to_be_disabled()
    assert hub.posts == [] and "/hub/github/repos" not in hub.gets


def test_late_github_status_cannot_replace_another_source_draft(hub_page, lang):
    page, hub = hub_page, hub_page.hub
    connect(hub)
    pending = []
    page.page.route("**/hub/github/status", lambda route: pending.append(route))
    open_github(page)
    expect(page.page.locator('[data-banner="folder-add"]')).to_contain_text(
        say(page, "hub.add.github_loading"))
    page.page.locator('[data-focus="source-scratch"]').click()
    page.page.locator('[data-focus="scratch-folder"]').fill("keep-folder")
    page.page.locator('[data-focus="folder-name"]').fill("Keep name")
    pending[0].fulfill(status=200, content_type="application/json",
        body=json.dumps({"state": "ok", "login": "late", "login_command": None}))
    expect(page.page.locator('[data-focus="scratch-folder"]')).to_have_value("keep-folder")
    expect(page.page.locator('[data-focus="folder-name"]')).to_have_value("Keep name")
    expect(page.page.locator('[data-focus="github-repo"]')).to_have_count(0)
    assert hub.posts == []
