"""A real SSE signal makes the desk read a new durable task without reloading."""
import threading

import pytest
from playwright.sync_api import expect

from conductor import server
from conductor.command.task_contracts import TaskRecord
from conductor.command.task_store import TaskStore
from tests.test_store import good_lane, write_project


@pytest.mark.parametrize("language", ["en", "ru"])
def test_the_real_stream_refreshes_tasks_and_recovers_missed_changes(
        tmp_path, chromium, language):
    root = write_project(tmp_path / "project", lanes={"claude": good_lane()})
    httpd = server.build(root, 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    context = chromium.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    errors, writes = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: writes.append(request.url)
            if request.method != "GET" else None)
    try:
        host, port = httpd.server_address[:2]
        page.goto(f"http://{host}:{port}/panel/desk.html#lang={language}")
        shell = page.locator("#deskShell")
        expect(shell).to_have_attribute("data-connection", "open")
        tasks = TaskStore(root)
        tasks.create_task(TaskRecord("task-live", "Arrived while open", "work-live",
                                      "2026-09-30T12:00:00Z"))
        httpd.clients.publish_state()
        expect(page.locator("#deskRail")).to_contain_text("Arrived while open")
        # Playwright's offline flag does not terminate an already open SSE socket.
        # Stop the real server instead, then bind a fresh server to the same port.
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()
        assert not thread.is_alive()
        expect(shell).to_have_attribute("data-connection", "closed", timeout=10000)
        tasks.create_task(TaskRecord("task-missed", "Arrived while disconnected", "work-missed",
                                      "2026-09-30T12:00:01Z"))
        httpd = server.build(root, port)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        expect(shell).to_have_attribute("data-connection", "open", timeout=15000)
        expect(page.locator("#deskRail")).to_contain_text("Arrived while disconnected")
        assert errors == [] and writes == []
    finally:
        context.close()
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()
        assert not thread.is_alive()
