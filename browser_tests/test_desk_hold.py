"""A window closed with a route handler's fetch in flight leaves nothing for the next test.

A handler that calls `route.fetch()` is a call in flight until the answer is back. When the
context is closed under it the request context is disposed, the fetch raises, and Playwright
raises that in the next synchronous call of the process: the first call of the NEXT test, which
fails for a reason that is none of its own. These tests force the fetch to be in flight (the
upstream's answer is withheld until the test lets it go) and judge the call that comes after.
"""
from __future__ import annotations

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from playwright.sync_api import Browser, BrowserContext, Error

from browser_tests import desk_queue_rig as rig
from browser_tests.desk_hold import close_context, until

PAGE = b"<!doctype html><title>probe</title>"


class _Slow:
    """A loopback server whose answer to `/slow` is not sent until `release()`, which may also
    drop the connection instead of answering: the fetch of a handler then fails."""

    def __init__(self) -> None:
        self.asked = threading.Event()
        self._go = threading.Event()
        self._drop = False
        slow = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if self.path == "/slow":
                    slow.asked.set()
                    slow._go.wait(10)
                    if slow._drop:
                        self.close_connection = True
                        return
                body = b"{}" if self.path == "/slow" else PAGE
                self.send_response(200)
                self.send_header("Content-Type", "text/html" if self.path != "/slow"
                                 else "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except OSError:
                    pass  # the client is gone: the answer has nobody left to read it

            def log_message(self, *args) -> None:
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/"
        self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self._thread.start()

    def release(self, drop: bool = False) -> None:
        self._drop = drop
        self._go.set()

    def stop(self) -> None:
        self.release()
        self.httpd.shutdown()
        self._thread.join(timeout=5)
        self.httpd.server_close()


@pytest.fixture
def slow() -> Iterator[_Slow]:
    server = _Slow()
    try:
        yield server
    finally:
        server.stop()


def _window_with_a_fetch_in_flight(chromium: Browser, slow: _Slow) -> BrowserContext:
    """A window whose handler is fetching `/slow` and whose answer has not been sent."""
    context = chromium.new_context()
    page = context.new_page()
    page.route("**/slow", lambda route: route.fulfill(response=route.fetch()))
    page.goto(slow.url)
    page.evaluate("() => { fetch('/slow').catch(() => {}); }")
    for _ in range(160):
        if slow.asked.is_set():
            break
        page.wait_for_timeout(50)
    assert slow.asked.is_set(), "the handler's fetch never reached the upstream"
    return context


def test_a_window_closed_as_it_is_leaves_the_error_of_the_fetch_for_the_next_call(
        chromium: Browser, slow: _Slow):
    context = _window_with_a_fetch_in_flight(chromium, slow)
    context.close()  # raw close on purpose: the form `close_context` replaces
    slow.release()
    with pytest.raises(Error, match="Request context disposed"):
        chromium.new_context().new_page().close()


def test_a_window_closed_through_close_context_leaves_nothing_for_the_next_call(
        chromium: Browser, slow: _Slow):
    context = _window_with_a_fetch_in_flight(chromium, slow)
    close_context(context)
    slow.release()
    chromium.new_context().new_page().close()


def _pumped(context: BrowserContext) -> None:
    """Make synchronous calls for a while: an error Playwright holds for the process is raised in
    the first of them."""
    page = context.pages[0]
    for _ in range(160):
        page.wait_for_timeout(50)


def test_an_error_of_a_fetch_in_a_window_that_is_still_open_reaches_the_test(
        chromium: Browser, slow: _Slow):
    """`close_context` ignores the errors of the handlers of the window it closes and of no other:
    a fetch that fails in a live window (its upstream drops the connection) is an error the test
    must hear."""
    context = _window_with_a_fetch_in_flight(chromium, slow)
    try:
        slow.release(drop=True)
        with pytest.raises(Error, match="hang up|ECONNRESET|socket"):
            _pumped(context)
    finally:
        close_context(context)


def test_closing_one_window_through_close_context_does_not_hide_the_error_of_an_open_one(
        chromium: Browser, slow: _Slow):
    live = _window_with_a_fetch_in_flight(chromium, slow)
    other = chromium.new_context()
    other.new_page()
    try:
        close_context(other)
        slow.release(drop=True)
        with pytest.raises(Error, match="hang up|ECONNRESET|socket"):
            _pumped(live)
    finally:
        close_context(live)


def test_a_window_that_is_already_closed_is_closed_again_without_an_error(chromium: Browser):
    context = chromium.new_context()
    context.new_page()
    close_context(context)
    close_context(context)


def test_a_window_the_queue_rig_opened_is_closed_with_its_project_and_leaves_nothing_behind(
        chromium: Browser, slow: _Slow, tmp_path: Path):
    """The queue modules never close their windows themselves: the rig closes each one through
    `close_context` when its project ends, and not the reaper of the conftest with a plain
    `close()`. A handler of the window is fetching when the project ends."""
    with rig.project(tmp_path, [rig.Seed("task-a-r1", "task-a", "Alpha")]) as served:
        window = rig.open_desk(chromium, served)
        window.page.route("**/slow", lambda route: route.fulfill(response=route.fetch()))
        window.page.evaluate("(url) => { fetch(url, {mode: 'no-cors'}).catch(() => {}); }",
                             f"{slow.url}slow")
        until(window.page, "the handler's fetch reached the upstream", slow.asked.is_set)
    assert window.page.is_closed(), "the window is closed when its project ends"
    slow.release()
    chromium.new_context().new_page().close()
