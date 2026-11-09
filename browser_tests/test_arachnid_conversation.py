"""The main project page keeps Atlas and selects exact attempt evidence on the orbit."""
from urllib.parse import urlsplit

from playwright.sync_api import expect

from browser_tests.desk_hold import close_context
from browser_tests.test_studio_atlas import atlas_url, evidence  # noqa: F401


def select(page, value):
    page.evaluate("(value) => { location.hash = value; }", value)


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
