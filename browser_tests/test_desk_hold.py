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

import pytest
from playwright.sync_api import Browser, BrowserContext, Error

from browser_tests.desk_hold import close_context

PAGE = b"<!doctype html><title>probe</title>"


class _Slow:
    """A loopback server whose answer to `/slow` is not sent until `release()`."""

    def __init__(self) -> None:
        self.asked = threading.Event()
        self._go = threading.Event()
        slow = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if self.path == "/slow":
                    slow.asked.set()
                    slow._go.wait(10)
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

    def release(self) -> None:
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
    context.close()
    slow.release()
    with pytest.raises(Error, match="Request context disposed"):
        chromium.new_context().new_page().close()


def test_a_window_closed_through_close_context_leaves_nothing_for_the_next_call(
        chromium: Browser, slow: _Slow):
    context = _window_with_a_fetch_in_flight(chromium, slow)
    close_context(context)
    slow.release()
    chromium.new_context().new_page().close()
