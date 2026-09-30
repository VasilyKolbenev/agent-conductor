"""A real one-project server for the desk's feed and summary, and the windows that read it.

The production `server.build` over the project of `tests/desk_progress_seed.py`: four tasks,
three runs at three places, no provider configured and no agent running -- the single-project
server a person gets from `conduct up`. A window is a fresh browser context in a fixed time
zone (the desk says every time in the zone of the browser, so what a row says is a fact of the
page and not of the machine the test runs on), with every console error, uncaught error and
request of the page kept for the test that asks.

This is a helper and not a test module: the two fixtures are imported by the modules that use
them, and `open_window` is what they call.
"""
from __future__ import annotations

import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Browser, Page

from conductor import server
from tests.desk_progress_seed import seed_project
from tests.test_store import good_lane, write_project

#: The zone every window reads in, and the reads that say the desk has settled.
ZONE = "UTC"
SETTLED = """() => ["ready", "refused", "failed"].includes(
  document.getElementById("deskShell").getAttribute("data-state"))"""
SCENE_READY = """() => document.getElementById("deskScene").getAttribute("data-state") === "ready"
  && document.getElementById("deskScene").childElementCount > 0"""
#: The words the person's screen must never carry (spec 5.2).
RAW_TOKENS = r"\b(?:verification_failed|policy|created|ready|empty)\b"


@pytest.fixture(scope="session")
def progress_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """The desk at its own address over the seeded project."""
    root = write_project(tmp_path_factory.mktemp("desk-progress"), lanes={"claude": good_lane()})
    seed_project(root)
    httpd = server.build(root, 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address[:2]
    try:
        yield f"http://{host}:{port}/panel/desk.html"
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()
        assert not thread.is_alive(), "desk server did not stop"


@dataclass
class Window:
    """One booted desk window and everything it said and asked."""

    page: Page
    problems: list[str] = field(default_factory=list)
    asked: list[tuple[str, str]] = field(default_factory=list)


def open_window(browser: Browser, url: str, language: str, *, task: str | None = None,
                width: int = 1280, height: int = 900) -> Window:
    """Boot the desk in `language`; with `task`, the address chooses it and its run is drawn."""
    context = browser.new_context(viewport={"width": width, "height": height},
                                  timezone_id=ZONE)
    page = context.new_page()
    window = Window(page)
    page.on("console", lambda message: window.problems.append(message.text)
            if message.type == "error" else None)
    page.on("pageerror", lambda error: window.problems.append(str(error)))
    page.on("request", lambda request: window.asked.append(
        (request.method, urlsplit(request.url).path)))
    address = f"{url}#lang={language}" + ("" if task is None else f"&task={task}")
    page.goto(address, wait_until="load")
    page.wait_for_function(SETTLED)
    if task is not None:
        page.wait_for_function(SCENE_READY)
    return window


@pytest.fixture
def desk_in(chromium: Browser, progress_url: str) -> Iterator:
    """A factory of booted windows, each closed when the test is over."""
    opened: list[Window] = []

    def make(language: str = "en", *, task: str | None = None, width: int = 1280) -> Window:
        opened.append(open_window(chromium, progress_url, language, task=task, width=width))
        return opened[-1]

    yield make
    for window in opened:
        window.page.context.close()
