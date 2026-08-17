"""What every SSE frame is allowed to make the panel fetch, counted in a browser.

The panel receives exactly two frame shapes from the frozen stream: the legacy
``{"kind":"state"}`` and the additive identifier-only ``{"kind":"run"}``. Those
two shapes buy two different reads, and the difference is only observable as
network traffic — so this module counts the real GET requests Chromium issues
against the real loopback server rather than reading the dispatcher's source.

Four relations are pinned, one per frame class:

* a run signal buys the authoritative run and its controls, and nothing else —
  in particular it never re-reads ``/state.json``, which carries no command fact;
* a state signal buys ``/state.json`` *and* a re-read of the selected run;
* a frame the frozen contract never named buys nothing at all;
* the overflow substitution — the server's own answer to a full mailbox, where a
  dropped run signal is replaced by a state signal — still recovers the selected
  run, so a run whose signal was dropped cannot stay stale forever.

The overflow frame is not written by hand here. ``_overflow_frames`` drives the
production ``server._Mailbox`` past ``MAX_PENDING_RUNS`` and takes the bytes it
actually emits, and those bytes are what the page is made to receive.

It lives outside pytest's configured ``testpaths`` for the same reason as
``test_panel_rendered``: Playwright stays an explicit development/CI dependency.
"""
from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from playwright.sync_api import Browser, Page

from conductor import server
from conductor.command.adapters import AdapterRegistry
from conductor.command.run_store import RunStore, snapshot_digest

from tests.test_command_adapters import FakeAdapter
from tests.test_command_run_store import CONFIG, a_run
from tests.test_store import good_lane, write_project


RUN_ID = "run-cockpit-signals"
TOKEN = "browser-only-process-token"
STATE_FRAME = b'data: {"kind":"state"}\n\n'
SETTLE_MS = 500
BUDGET = 5.0


@pytest.fixture
def cockpit(tmp_path) -> Iterator[tuple[str, server.ConductServer]]:
    """Serve one confirm-mode run and hand the test the live signal broker."""
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    store = RunStore(root)
    store.create_run(
        a_run(run_id=RUN_ID, mode="confirm",
              config_digest=snapshot_digest(CONFIG)), CONFIG)
    httpd = server.build(
        root, 0, registry=AdapterRegistry([FakeAdapter()]),
        token_factory=lambda _size: TOKEN)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address
    try:
        yield f"http://{host}:{port}/", httpd
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()
        assert not thread.is_alive(), "cockpit server did not stop"


class _Counter:
    """Every GET the page issues, split into the two reads a frame may buy."""

    def __init__(self, page: Page) -> None:
        self.rows: list[tuple[str, str]] = []
        page.on("request", lambda request: self.rows.append(
            (request.method, request.url)))

    def _gets(self, needle: str) -> int:
        return sum(1 for method, url in self.rows
                   if method == "GET" and needle in url)

    def snapshot(self) -> tuple[int, int]:
        """(state document reads, authoritative selected-run reads)."""
        return self._gets("/state.json"), self._gets(f"/command/runs/{RUN_ID}")


@pytest.fixture
def loaded(chromium: Browser, cockpit) -> Iterator[tuple[Page, _Counter, server.ConductServer]]:
    """A page with the run selected and its first burst of traffic finished."""
    url, httpd = cockpit
    context = chromium.new_context()
    page = context.new_page()
    counter = _Counter(page)
    page.goto(url, wait_until="load")
    page.locator("#commandRunId").fill(RUN_ID)
    page.get_by_role("button", name="Load run").click()
    page.locator(".command-proposal-form").wait_for(state="visible")
    page.wait_for_timeout(SETTLE_MS)
    try:
        yield page, counter, httpd
    finally:
        context.close()


def _wait_until(page: Page, predicate, budget: float = BUDGET) -> bool:
    deadline = time.monotonic() + budget
    while time.monotonic() < deadline:
        if predicate():
            return True
        page.wait_for_timeout(50)
    return predicate()


@contextmanager
def _substituted(frame: bytes) -> Iterator[None]:
    """Stand one chosen frame in for the next genuine wake of any mailbox.

    The frozen server emits two shapes only, so a frame carrying anything else
    can reach the page only from a server that is hostile, newer or broken. The
    substitution happens inside the real ``drain`` — the same handler thread,
    the same socket, the same writer — so what is under test is the panel's
    reading of a real stream, not a hand-rolled EventSource.
    """
    original = server._Mailbox.drain
    pending = [frame]

    def drain(self):
        genuine = original(self)
        if pending and genuine:
            return (pending.pop(0),)
        return genuine

    server._Mailbox.drain = drain
    try:
        yield
    finally:
        server._Mailbox.drain = original


def _overflow_frames(selected: str) -> tuple[bytes, ...]:
    """Drive the production mailbox past its bound with `selected` arriving last."""
    mailbox = server._Mailbox()
    for index in range(server.MAX_PENDING_RUNS):
        mailbox.publish_run(f"filler-{index:04d}")
    mailbox.publish_run(selected)
    return mailbox.drain()


def test_a_run_signal_buys_the_authoritative_run_and_never_the_state_document(
        loaded) -> None:
    """An identifier-only signal carries no state fact, so it may read no state."""
    page, counter, httpd = loaded
    before = counter.snapshot()
    httpd.clients.publish_run(RUN_ID)
    assert _wait_until(page, lambda: counter.snapshot()[1] >= before[1] + 2)
    page.wait_for_timeout(SETTLE_MS)
    assert counter.snapshot() == (before[0], before[1] + 2)


def test_a_state_signal_rereads_the_state_document_and_the_selected_run(
        loaded) -> None:
    """The state frame is the only frame that reports both halves changed."""
    page, counter, httpd = loaded
    before = counter.snapshot()
    httpd.clients.publish_state()
    want = (before[0] + 1, before[1] + 2)
    assert _wait_until(page, lambda: counter.snapshot() == want)
    page.wait_for_timeout(SETTLE_MS)
    assert counter.snapshot() == want


@pytest.mark.parametrize("frame", [
    b'data: {"kind":"tombstone"}\n\n',
    b'data: {"kind":"run"}\n\n',
    b'data: {"kind":"run","run_id":"../escape"}\n\n',
    b'data: {"kind":null}\n\n',
    b'data: {}\n\n',
    b'data: [1,2,3]\n\n',
    b'data: not-json\n\n',
])
def test_a_frame_the_frozen_contract_never_named_moves_nothing(
        loaded, frame: bytes) -> None:
    """An unknown or malformed kind is ignored, not treated as a change report."""
    page, counter, httpd = loaded
    before = counter.snapshot()
    with _substituted(frame):
        httpd.clients.publish_state()
        page.wait_for_timeout(SETTLE_MS)
        assert counter.snapshot() == before
    # The same channel, the same budget: a frame the panel does know arrives and
    # is answered, so the silence above was inertness and not a slow stream.
    httpd.clients.publish_state()
    want = (before[0] + 1, before[1] + 2)
    assert _wait_until(page, lambda: counter.snapshot() == want)


def test_the_overflow_substitution_still_recovers_the_selected_run(
        loaded) -> None:
    """A full mailbox drops the selected run's signal; the state stand-in must not."""
    page, counter, httpd = loaded
    frames = _overflow_frames(RUN_ID)
    assert frames[0] == STATE_FRAME
    assert RUN_ID.encode("utf-8") not in b"".join(frames)

    before = counter.snapshot()
    with _substituted(frames[0]):
        httpd.clients.publish_state()
        assert _wait_until(page, lambda: counter.snapshot()[1] >= before[1] + 2)
    page.wait_for_timeout(SETTLE_MS)
    assert counter.snapshot() == (before[0] + 1, before[1] + 2)
