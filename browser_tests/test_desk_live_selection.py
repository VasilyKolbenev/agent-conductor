"""A reconnect confirms the current selection only after its fresh run read lands."""
from urllib.parse import urlsplit

from playwright.sync_api import expect

from browser_tests.desk_hold import close_context
from browser_tests.test_desk_rail_scene import seeded_url  # noqa: F401


def test_reconnect_waits_for_the_selected_read_then_confirms_a_fresh_answer(chromium, seeded_url):
    context = chromium.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    errors, held = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.add_init_script("""(() => {
      const Native = window.EventSource;
      window.__streamCount = 0;
      window.EventSource = class extends Native {
        constructor(...args) { super(...args); window.__stream = this; window.__streamCount += 1; }
      };
      window.__held = [];
    })();""")

    def hold(route):
        held.append(route)
        page.evaluate("path => window.__held.push(path)", urlsplit(route.request.url).path)

    def release(index):
        route = held[index]
        route.fulfill(response=route.fetch())

    run = "/command/runs/run-fix-new"
    try:
        page.goto(f"{seeded_url}#lang=en&task=task-fix")
        shell = page.locator("#deskShell")
        expect(shell).to_have_attribute("data-connection", "open")
        expect(page.locator("#deskScene")).to_have_attribute("data-state", "ready")
        page.route("**/command/tasks", hold, times=1)
        page.route(f"**{run}", hold)
        # Bootstrap used a native EventSource. Close its socket to prevent unrelated native
        # frames while delivering the same error/open events at a controlled selection boundary.
        page.evaluate("""() => {
          window.__stream.close();
          window.__stream.dispatchEvent(new Event("error"));
          window.__stream.dispatchEvent(new Event("open"));
          window.__connections = [];
          const shell = document.getElementById("deskShell");
          window.__observer = new MutationObserver(() => {
            window.__connections.push(shell.dataset.connection);
          });
          window.__observer.observe(shell, {attributes: true, attributeFilter: ["data-connection"]});
        }""")
        page.wait_for_function("window.__held.length === 1")
        assert page.evaluate("window.__held") == ["/command/tasks"]
        # Re-select the drawn task while the reconnect's lists are held. Its old detail stays
        # visible as stale; this pending user read must not let the reconnect announce live.
        page.locator('#deskRail [data-task-id="task-fix"]').click()
        page.wait_for_function("window.__held.length === 2")
        assert page.evaluate("window.__held[1]") == run
        expect(page.locator("#deskScene")).to_have_attribute("data-state", "stale")
        release(0)
        release(1)
        # The user answer is insufficient: reconnect owes another read for the current choice.
        # Observing this request is the barrier, not an elapsed-time guess about a late answer.
        page.wait_for_function("window.__held.length === 3")
        assert page.evaluate("window.__held[2]") == run
        expect(shell).to_have_attribute("data-connection", "connecting")
        assert "open" not in page.evaluate("window.__connections")
        expect(page.locator('#deskRail [data-task-id="task-fix"]')).to_have_attribute(
            "aria-pressed", "true")
        release(2)
        expect(shell).to_have_attribute("data-connection", "open")
        expect(page.locator("#deskScene")).to_have_attribute("data-state", "ready")
        assert page.evaluate("window.__streamCount") == 1
        assert errors == []
    finally:
        close_context(context)
