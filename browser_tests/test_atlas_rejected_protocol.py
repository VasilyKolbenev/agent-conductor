"""The rejected attempt keeps its exact diff, native transcript and typed findings."""
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import expect

from browser_tests.desk_hold import close_context
from browser_tests.test_studio_atlas import atlas_url, evidence  # noqa: F401


def rejected(action):
    row = evidence(action)
    row["outcome"] = "verification_failed"
    row["verdict"].update(status="rejected", reason="checker_rejected", findings=[{
        "kind": "verification_gap", "summary": "The required empty input check failed.",
        "path": "checks.py", "line": 4}])
    counts = {"total": 3, "failures": 1, "errors": 0, "skipped": 0}
    row["tests"].update(source="native", summary=counts, protocol={
        "version": 1, "binding": {"run": "first", "action": action,
            "attempt": "attempt-" + action, "instance": "maker", "grant": "grant",
            "grant_digest": "sha256:" + "2" * 64, "policy": "sha256:" + "3" * 64,
            "toolpin": "sha256:" + "4" * 64, "workspace_tree": "sha256:" + "5" * 64,
            "work_modes": "sha256:" + "7" * 64}, "policy": {"runner": "python-unittest-v1"},
        "argv": ["python.exe", "-I", "-m", "unittest"], "cwd": "work/item",
        "status": "failed", "process_status": "completed", "exit_code": 1,
        "output": "FAIL: test_empty\nRan 3 tests\nFAILED (failures=1)\n",
        "output_b64": "RkFJTDogdGVzdF9lbXB0eQo=", "output_sha256": "sha256:" + "6" * 64,
        "output_stream": "merged", "counts": counts, "truncated": False, "reason": None})
    return row


def test_rejected_attempt_shows_native_protocol_and_findings(chromium, atlas_url):
    context = chromium.new_context(viewport={"width": 1280, "height": 850})
    page = context.new_page()
    try:
        page.route("**/steps/repair-counter/actions/*", lambda route: route.fulfill(json=
            rejected(urlsplit(route.request.url).path.rsplit("/", 1)[-1])))
        page.goto(atlas_url + "/#screen=runs&task=one&run=first&lang=en")
        atlas = page.locator("#studioAtlas")
        atlas.locator("[data-atlas-step=repair-counter]").click()
        panel = atlas.locator("[data-atlas-inspector]")
        expect(panel).to_contain_text("+new-action-first-2")
        panel.locator("[data-atlas-tab=tests]").click()
        expect(panel).to_contain_text("Tests failed")
        expect(panel).to_contain_text('["python.exe","-I","-m","unittest"]')
        expect(panel).to_contain_text("work/item")
        expect(panel).to_contain_text("FAIL: test_empty")
        expect(panel).not_to_contain_text("External check")
        panel.locator("[data-atlas-tab=verdict]").click()
        expect(panel).to_contain_text("Snapshot rejected")
        expect(panel).to_contain_text("checker_rejected")
        expect(panel).to_contain_text("The required empty input check failed.")
        expect(panel).to_contain_text("checks.py:4")
    finally:
        close_context(context)


@pytest.mark.parametrize("field", ["run", "action", "attempt", "all_skipped"])
def test_invalid_native_protocol_is_not_displayed(chromium, atlas_url, field):
    context = chromium.new_context(viewport={"width": 1280, "height": 850})
    page = context.new_page()

    def respond(route):
        row = rejected(urlsplit(route.request.url).path.rsplit("/", 1)[-1])
        protocol = row["tests"]["protocol"]
        if field == "all_skipped":
            protocol.update(status="passed", exit_code=0)
            protocol["counts"].update(failures=0, skipped=3)
        else:
            protocol["binding"][field] = "foreign"
        route.fulfill(json=row)

    try:
        page.route("**/steps/repair-counter/actions/*", respond)
        page.goto(atlas_url + "/#screen=runs&task=one&run=first&lang=en")
        atlas = page.locator("#studioAtlas")
        atlas.locator("[data-atlas-step=repair-counter]").click()
        panel = atlas.locator("[data-atlas-inspector]")
        expect(panel).to_contain_text("could not be confirmed")
        expect(panel).not_to_contain_text("FAIL: test_empty")
        expect(panel).not_to_contain_text("new-action-first-2")
    finally:
        close_context(context)
