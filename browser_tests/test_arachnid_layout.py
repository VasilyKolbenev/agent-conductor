"""Operator-controlled column widths on the real, read-only Arachnid project page."""
from contextlib import contextmanager

import pytest
from playwright.sync_api import expect

from browser_tests.test_arachnid_entry import project


KEY = "arachnid.panel-widths.v1"


@contextmanager
def workspace(browser, folder, *, storage=None):
    with project(folder / "read-only") as url:
        context = browser.new_context(viewport={"width": 1450, "height": 850})
        try:
            if storage:
                context.add_init_script(storage)
            page = context.new_page()
            writes = []
            page.on("request", lambda req: writes.append(req.method) if req.method == "POST"
                    else None)
            page.goto(url + "/#lang=en")
            expect(page.locator("#command")).to_be_visible()
            page.locator("#memory").click()
            expect(page.locator("#detail")).to_be_visible()
            yield page
            assert writes == []
        finally:
            context.close()


def width(page, pane):
    return page.locator("#" + pane).bounding_box()["width"]


def drag(page, pane, delta, *, release=True):
    box = page.locator("#" + pane).bounding_box()
    x = box["x"] + (box["width"] if pane == "sidebar" else 0)
    y = box["y"] + 160
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + delta, y + 25)
    if release:
        page.mouse.up()


def viewport(page, pixels):
    page.set_viewport_size({"width": pixels, "height": 850})
    assert page.evaluate("document.documentElement.scrollWidth === innerWidth")


def test_pointer_resizes_both_panes_and_keeps_the_draft_and_preferences(chromium, tmp_path):
    with workspace(chromium, tmp_path) as page:
        command = page.locator("#command")
        command.fill("remember this draft")
        left, right = width(page, "sidebar"), width(page, "detail")
        drag(page, "sidebar", 40)
        assert width(page, "sidebar") == left + 40
        drag(page, "detail", -75)
        assert width(page, "detail") == right + 75
        expect(command).to_be_focused()
        expect(command).to_have_value("remember this draft")
        page.locator("#theme").click()
        page.locator("#new").click()
        page.locator("#memory").click()
        assert width(page, "sidebar") == left + 40
        assert width(page, "detail") == right + 75
        page.reload()
        page.locator("#memory").click()
        assert width(page, "sidebar") == left + 40
        assert width(page, "detail") == right + 75
        assert page.evaluate("key => JSON.parse(localStorage.getItem(key))", KEY) == {
            "sessions": left + 40, "inspector": right + 75}


def test_keyboard_exposes_actual_bounds_and_restores_preferred_widths(chromium, tmp_path):
    with workspace(chromium, tmp_path) as page:
        left = page.locator("#resizeSessions")
        right = page.locator("#resizeInspector")
        assert width(page, "sidebar") == 240 and width(page, "detail") == 420
        for handle, controlled, name in [(left, "sidebar", "Resize sessions panel"),
                                         (right, "detail", "Resize inspector panel")]:
            expect(handle).to_have_attribute("role", "separator")
            expect(handle).to_have_attribute("aria-controls", controlled)
            expect(handle).to_have_attribute("aria-orientation", "vertical")
            expect(handle).to_have_accessible_name(name)
            expect(handle).to_have_attribute("tabindex", "0")
        left.press("Home")
        assert width(page, "sidebar") == 184
        left.press("ArrowRight")
        small = width(page, "sidebar") - 184
        left.press("Shift+ArrowRight")
        assert 0 < small < width(page, "sidebar") - 184 - small
        left.press("End")
        right.press("End")
        assert width(page, "sidebar") == 320 and width(page, "detail") == 720
        right.press("ArrowRight")
        assert width(page, "detail") < 720  # moving the right divider right narrows its pane
        right.press("End")
        viewport(page, 1024)
        expect(right).to_have_attribute("aria-valuemax", "344")
        expect(right).to_have_attribute("aria-valuenow", "344")
        assert width(page, "chat") == 360
        viewport(page, 701)
        expect(left).to_be_hidden()
        expect(right).to_have_attribute("aria-valuemin", "300")
        expect(right).to_have_attribute("aria-valuemax", "421")
        assert width(page, "chat") == 280
        viewport(page, 375)
        expect(left).to_be_hidden()
        expect(right).to_be_hidden()
        viewport(page, 1450)
        expect(right).to_have_attribute("aria-valuenow", "720")
        assert width(page, "sidebar") == 320 and width(page, "detail") == 720
        page.locator("#language").select_option("ru")
        expect(left).to_have_accessible_name("Изменить ширину сессий")
        expect(left).to_have_attribute("aria-valuetext", "320 пикс.")


@pytest.mark.parametrize("cancel", ["Escape", "pointercancel"])
def test_abandoned_drag_keeps_inspector_and_saved_sizes(chromium, tmp_path, cancel):
    with workspace(chromium, tmp_path) as page:
        command = page.locator("#command")
        command.fill("draft")
        handle = page.locator("#resizeInspector")
        if cancel == "pointercancel":
            handle.evaluate("""el => el.addEventListener('gotpointercapture',
                event => el.dataset.testPointer = event.pointerId, {once:true})""")
        drag(page, "detail", -60, release=False)
        assert width(page, "detail") == 480
        if cancel == "Escape":
            page.keyboard.press("Escape")
        else:
            # Playwright's mouse has no hardware-cancel gesture; dispatch the browser event.
            pointer = int(handle.get_attribute("data-test-pointer"))
            handle.dispatch_event("pointercancel", {"pointerId": pointer, "pointerType": "mouse"})
        page.mouse.up()
        assert width(page, "detail") == 420
        expect(command).to_be_focused()
        expect(command).to_have_value("draft")
        assert page.evaluate("key => localStorage.getItem(key)", KEY) is None


@pytest.mark.parametrize("init", [
    "localStorage.setItem('arachnid.panel-widths.v1', '{broken')",
    "localStorage.setItem('arachnid.panel-widths.v1',"
    " JSON.stringify({sessions:'bad',inspector:1e8}))",
    "localStorage.setItem('arachnid.panel-widths.v1',"
    " JSON.stringify({sessions:255,inspector:375,draft:'invalid field'}))",
    "Storage.prototype.setItem = () => { throw new DOMException('full','QuotaExceededError') }",
    "Object.defineProperty(window, 'localStorage',"
    " {get() { throw new DOMException('denied','SecurityError') }})",
])
def test_corrupt_or_unavailable_storage_does_not_block_resizing(chromium, tmp_path, init):
    with workspace(chromium, tmp_path, storage=init) as page:
        assert width(page, "sidebar") == 240 and width(page, "detail") == 420
        page.locator("#resizeInspector").press("Home")
        assert width(page, "detail") == 320
