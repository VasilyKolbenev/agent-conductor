"""An EventSource origin can be reused by a different project after disconnection."""
from contextlib import contextmanager, nullcontext
from threading import Thread
from urllib.parse import urlsplit

from playwright.sync_api import expect

from browser_tests.desk_hold import close_context
from browser_tests.test_studio_atlas import create_run
from conductor import demo, ownership, ownership_transition, server
from conductor.command.adapters import AdapterRegistry
from conductor.command.project_claim import Launch
from conductor.command.task_contracts import TaskRecord
from conductor.command.task_store import TaskStore
from tests.test_policy_runtime import NOW


@contextmanager
def archive(folder, title, *, activated=False):
    root = demo.materialize(folder)
    if activated:
        ownership_transition.activate(root, legacy_writers_stopped=True)
    with ownership.acquire_owner(root) if activated else nullcontext():
        TaskStore(root).create_task(TaskRecord("one", title, "one", NOW))
        create_run(root, "shared-run")
    with server.build(root, 0, registry=AdapterRegistry([]), launch=Launch(mode="view")) as http:
        thread = Thread(target=http.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{http.server_port}"
        finally:
            http.shutdown()
            thread.join(5)


class Switch:
    """One browser origin. Requests go to A then B; both serve real project records."""
    def __init__(self, page, origins, *, initial_open=True):
        self.page, self.origins, self.server = page, origins, 0
        self.identities = []
        signal = "setTimeout(() => this.dispatchEvent(new Event('open')), 0)"
        if not initial_open:
            signal = ""
        page.add_init_script("window.EventSource = class extends EventTarget {"
                             "constructor() { super(); window.testWire = this; " + signal
                             + "; } close() {} };")
        page.route("**/command/**", self.dispatch)

    def dispatch(self, route):
        path = urlsplit(route.request.url).path
        headers = {"X-Conduct-Project": route.request.headers["x-conduct-project"]
                   } if "x-conduct-project" in route.request.headers else {}
        response = self.page.request.get(self.origins[self.server] + path, headers=headers)
        try:
            if path == "/command/project":
                self.identities.append((self.server, response.status))
            route.fulfill(response=response)
        finally:
            response.dispose()

    def replace(self):
        self.page.evaluate("window.testWire.dispatchEvent(new Event('error'))")
        self.server = 1
        self.page.evaluate("window.testWire.dispatchEvent(new Event('open'))")


def test_replacing_unidentified_archive_on_reconnect_cannot_disclose_old_chat(chromium, tmp_path):
    with (archive(tmp_path / "a", "Archive Alpha") as a,
          archive(tmp_path / "b", "Archive Beta") as b):
        context = chromium.new_context(locale="en-US")
        page = context.new_page()
        wire = Switch(page, (a, b))
        try:
            page.goto(a + "/#session=shared-run&lang=en")
            expect(page.get_by_role("heading", name="Archive Alpha")).to_be_visible()
            field = page.locator("#command")
            field.fill("private conversation belonging to Alpha")
            field.press("Enter")
            field.fill("private draft belonging to Alpha")
            wire.replace()
            expect(page.get_by_role("heading", name="Archive Beta")).to_be_visible()
            expect(field).to_have_value("")
            expect(page.locator("#messages")).not_to_contain_text("belonging to Alpha")
            assert (1, 200) in wire.identities
        finally:
            close_context(context)


def test_reconnect_to_a_different_activated_identity_seals_the_window(chromium, tmp_path):
    with (archive(tmp_path / "a", "Project Alpha", activated=True) as a,
          archive(tmp_path / "b", "Project Beta", activated=True) as b):
        context = chromium.new_context(locale="en-US")
        page = context.new_page()
        wire = Switch(page, (a, b))
        try:
            page.goto(a + "/#session=shared-run&lang=en")
            expect(page.get_by_role("heading", name="Project Alpha")).to_be_visible()
            page.locator("#command").fill("belongs to Alpha")
            wire.replace()
            expect(page.locator("#notice")).to_contain_text("another project")
            expect(page.locator("#command")).to_be_disabled()
            expect(page.locator("#command")).to_have_value("")
            expect(page.locator("#sessions")).not_to_contain_text("Project Beta")
            assert (1, 409) in wire.identities
        finally:
            close_context(context)


def test_delayed_first_open_cannot_transfer_a_draft_to_another_archive(chromium, tmp_path):
    with (archive(tmp_path / "a", "Archive Alpha") as a,
          archive(tmp_path / "b", "Archive Beta") as b):
        context = chromium.new_context(locale="en-US")
        page = context.new_page()
        wire = Switch(page, (a, b), initial_open=False)
        try:
            page.goto(a + "/#session=shared-run&lang=en")
            page.wait_for_function("Boolean(window.testWire)")
            page.wait_for_load_state("networkidle")  # all initial HTTP reads have had their turn
            field = page.locator("#command")
            expect(field).to_be_disabled()
            expect(page.locator("#new")).to_be_disabled()
            page.evaluate("location.hash = 'new=1&lang=en'")
            expect(field).to_be_disabled()
            page.evaluate("location.hash = 'session=shared-run&lang=en'")
            wire.server = 1
            page.evaluate("window.testWire.dispatchEvent(new Event('open'))")
            expect(page.get_by_role("heading", name="Archive Beta")).to_be_visible()
            expect(field).to_have_value("")
            assert (1, 200) in wire.identities
        finally:
            close_context(context)
