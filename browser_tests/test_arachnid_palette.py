"""Keyboard navigation in real Arachnid does not change the draft or write to a project."""
import re
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import expect

from browser_tests.desk_hold import close_context
from browser_tests.test_studio_atlas import atlas_url, evidence  # noqa: F401


@pytest.mark.parametrize(("lang", "width"), [("en", 1440), ("ru", 375)])
def test_workspace_search_returns_caret_and_opens_scoped_step(chromium, atlas_url, lang, width):
    context = chromium.new_context(viewport={"width": width, "height": 850})
    page = context.new_page()
    writes = []
    page.on("request", lambda r: writes.append(r.method) if r.method == "POST" else None)
    page.route("**/steps/repair-counter/actions/*", lambda r: r.fulfill(
        json=evidence(urlsplit(r.request.url).path.rsplit("/", 1)[-1])))
    try:
        page.goto(atlas_url + "/#session=first&lang=" + lang)
        expect(page.locator("#orbitHere [data-step]")).to_be_visible()
        opener = page.locator("#paletteOpen")
        expect(opener).to_be_visible()
        command = page.locator("#command")
        command.fill("draft inside Atlas")
        command.evaluate("e => e.setSelectionRange(2, 7)")
        command.press("Control+k")
        palette, query = page.locator("#palette"), page.locator("#paletteInput")
        expect(palette).to_be_visible()
        expect(query).to_be_focused()
        query.fill("not-a-workspace-result-9841")
        expect(page.locator("#paletteEmpty")).to_be_visible()
        query.press("Escape")
        expect(palette).to_be_hidden()
        expect(command).to_be_focused()
        expect(command).to_have_value("draft inside Atlas")
        assert command.evaluate("e => [e.selectionStart,e.selectionEnd]") == [2, 7]
        opener.click()
        query.fill("repair-counter")
        step = palette.locator('[role=option][data-palette-kind=step]')
        expect(step).to_have_count(1)
        query.press("Enter")
        expect(palette).to_be_hidden()
        inspector = page.locator("#inspection")
        expect(inspector).to_contain_text("new-action-first-2")
        inspector.locator("[data-atlas-attempt]").focus()
        page.keyboard.press("Meta+k")
        expect(query).to_be_focused()
        query.press("Escape")
        expect(page.locator("#detail")).to_be_visible()
        expect(inspector.locator("[data-atlas-attempt]")).to_be_focused()
        expect(command).to_have_value("draft inside Atlas")
        assert not writes
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    finally:
        close_context(context)


def open_catalog(page, atlas_url, rows):
    # The canonical editor has no shell shortcuts. Exercise the exported palette door alone.
    page.goto(atlas_url + "/panel/studio.html")
    page.evaluate("""async entries => {
        const {attachPalette} = await import('/panel/arachnid-palette.js');
        const dialog = document.createElement('dialog');
        for (const [tag,id] of [['input','paletteInput'],['div','paletteResults'],
            ['p','paletteEmpty'],['button','paletteClose']]) {
            const node = document.createElement(tag); node.id = id; dialog.append(node);
        }
        dialog.id = 'palette'; document.body.append(dialog);
        window.entries = entries;
        window.selected = [];
        const palette = attachPalette(dialog, {
            catalog: () => entries, choose: row => {selected.push([row.scope,row.id]);return true;},
            restore: () => {}, locale: () => 'en', stop: () => new AbortController()
        });
        palette.open(document.activeElement);
    }""", rows)


def test_exact_step_is_selected_before_a_matching_gate_or_session(chromium, atlas_url):
    context = chromium.new_context()
    page = context.new_page()
    try:
        open_catalog(page, atlas_url, [
            {"kind": "session", "scope": "project", "id": "docs", "label": "Document the fix"},
            {"kind": "step", "scope": "first", "id": "gate", "label": "Human Gate – Confirm Do"},
            {"kind": "step", "scope": "first", "id": "do", "label": "Do"},
        ])
        query = page.locator("#paletteInput")
        query.fill(" do ")
        options = page.locator("#paletteResults").get_by_role("option")
        expect(options).to_have_count(3)
        expect(options.first).to_have_text("Do")
        expect(options.first).to_have_attribute("aria-selected", "true")
        query.press("Enter")
        assert page.evaluate("selected") == [["first", "do"]]
    finally:
        close_context(context)


def test_scoped_option_disappearing_at_activation_never_selects_its_namesake(chromium, atlas_url):
    context = chromium.new_context()
    page = context.new_page()
    try:
        open_catalog(page, atlas_url, [{"kind": "step", "id": "do", "label": "Do", "scope": "old"}])
        query = page.locator("#paletteInput")
        expect(query).to_be_focused()
        query.fill("do")
        page.evaluate("() => { entries[0].scope = 'new'; }")
        query.press("Enter")
        expect(page.locator("#palette")).to_be_visible()
        assert page.evaluate("selected") == []
        query.press("ArrowDown")
        query.press("Enter")
        assert page.evaluate("selected") == [["new", "do"]]
        expect(page.locator("#palette")).to_be_hidden()
    finally:
        close_context(context)


def test_navigation_and_shortcuts_respect_existing_dialogs(chromium, atlas_url):
    context = chromium.new_context(viewport={"width": 921, "height": 850})
    page = context.new_page()
    writes = []
    page.on("request", lambda r: writes.append(r.method) if r.method == "POST" else None)
    try:
        page.goto(atlas_url + "/#session=first&lang=en&theme=light")
        expect(page.locator("#orbitHere [data-step]")).to_be_visible()
        palette, query = page.locator("#palette"), page.locator("#paletteInput")
        command = page.locator("#command")
        command.fill("draft")
        command.press("Control+Alt+k")
        expect(palette).to_be_hidden()
        command.dispatch_event("keydown", {"code": "KeyK", "key": "k", "ctrlKey": True,
                                            "isComposing": True})
        expect(palette).to_be_hidden()
        page.locator("#attach").click()
        expect(page.locator("#studioUtilities")).to_be_visible()
        page.keyboard.press("Control+k")
        expect(palette).to_be_hidden()
        page.locator("#studioUtilities").get_by_role("button", name="Close").click()
        lead = page.locator("#lead").input_value()

        def choose(text, kind):
            page.locator("#paletteOpen").click()
            query.fill(text)
            palette.locator(f'[role=option][data-palette-kind="{kind}"]').click()
            expect(palette).to_be_hidden()

        choose("codex", "harness")
        expect(page.locator("#inspection")).to_contain_text("maker")
        expect(page.locator("#lead")).to_have_value(lead)
        choose("history", "memory")
        expect(page.locator("#detail")).to_be_visible()
        choose("quota", "limits")
        expect(page.locator("#detail")).to_be_visible()
        choose("second", "session")
        expect(page).to_have_url(re.compile("session=second"))
        expect(command).to_have_value("")
        assert not writes
    finally:
        close_context(context)
