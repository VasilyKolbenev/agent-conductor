"""Handing a held request over never strands the reads its answer starts.

`test_studio_step_races.py` holds a write -- parks its answer, or holds the
request itself -- and then hands it over. The reverse browser gate went red on
that once: D's Confirm control was still shut fifteen seconds after its parked
answer was handed over, with no failed request and no console error on record.

The cause was the hand-over, not the product. The helper fulfilled the parked
answer and then REMOVED the page's only route, and removing a page's last route
turns Chromium's request interception off. The answer makes the window start
the run's confirming reads within milliseconds -- the same moment -- and a read
that interception paused across that switch is continued by neither side: it
never settles, and no request event for it need ever reach the client. Studio's
run refresh waits on that read and holds every later read of the run behind
it, and an answered write's entry leaves the map only when a read lands.

So no hand-over removes a route any more (`_let_through`): the holding route
gives way to one that passes requests on, and interception stays on, which is
how every request before the hand-over already ran.

The page here is not Studio, and on purpose. It does only what Studio's
accepted road does at that moment -- the instant a write's answer lands, it
starts two reads of the run -- against a server that answers at once, so the
race is met far more often than Studio's own render delay lets it be met. The
same calls on the same kind of page stranded a read in 71 of 400 and 62 of
300 releases that un-routed, and in none of 400 that let requests through.
"""
from __future__ import annotations

import sys
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from playwright.sync_api import Browser, Page, TimeoutError as BrowserTimeout

from browser_tests.test_studio_step_races import _park_the_answer, _release_parked

RUN = "run-release"
#: At the lowest stranding rate measured for an un-routing release -- 62 of
#: 300, about one in five -- eighty releases in a row all settle by luck with
#: a chance under one in a hundred million.
RELEASES = 80

PAGE = """<!doctype html><title>release</title><script>
window.stream = new EventSource('/events');
window.reads = {};
window.propose = async (index) => {
  const answer = await fetch('/command/runs/__RUN__/proposals', {method: 'POST',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify({index})});
  await answer.json();
  for (const name of ['__RUN__', '__RUN__/controls']) {
    const key = index + ' ' + name;
    window.reads[key] = 'pending';
    fetch('/command/runs/' + name, {cache: 'no-store'}).then((read) => read.json())
      .then(() => { window.reads[key] = 'settled'; },
            (error) => { window.reads[key] = 'refused: ' + error; });
  }
};
</script>""".replace("__RUN__", RUN)

#: Both reads the answer to release `index` started exist, and nothing is pending.
ENDED = ("index => Object.keys(window.reads).filter((key) =>"
         " key.startsWith(index + ' ')).length === 2 && Object.values(window.reads)"
         ".every((state) => state !== 'pending')")


class _Answering(BaseHTTPRequestHandler):
    """Answers at once: the page, a stream that stays open, reads and writes."""

    protocol_version = "HTTP/1.1"
    posts: list = []
    stopping = threading.Event()

    def log_message(self, *_args: object) -> None:      # stdlib name
        pass

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:      # stdlib name
        if self.path == "/":
            self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        elif self.path == "/events":
            self._stream()
        else:
            self._send(200, b'{"read": true}', "application/json")

    def do_POST(self) -> None:      # stdlib name
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self.posts.append(self.path)
        self._send(201, b'{"accepted": true}', "application/json")

    def _stream(self) -> None:
        """Hold one connection open the way Studio's stream does."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.close_connection = True
        self.end_headers()
        try:
            while not self.stopping.wait(0.5):
                self.wfile.write(b": open\n\n")
                self.wfile.flush()
        except OSError:
            pass


class _Quiet(ThreadingHTTPServer):
    """A reset connection is this module's SUBJECT, not a fault to report.

    Releasing a parked answer makes the page abandon its reads, and the stdlib
    prints that `ConnectionResetError` from a request thread. Those threads are
    daemons, so one was still writing to stderr while the interpreter finalized
    and Python aborted the process: "could not acquire lock for
    <_io.BufferedWriter name='<stderr>'> at interpreter shutdown". Both tests
    had passed and the module still exited 0xC0000409, which is how the normal
    browser gate went red at its 16th module on `582ac31`.

    The product's own server silences connection errors in exactly this place,
    and so does this one. Anything else is still reported.
    """

    def handle_error(self, request, client_address) -> None:      # stdlib name
        if not isinstance(sys.exc_info()[1], (ConnectionError, TimeoutError)):
            super().handle_error(request, client_address)


@pytest.fixture()
def answering() -> Iterator[tuple[str, list]]:
    """A server of its own, and the list of every write it answered."""
    posts: list = []
    stopping = threading.Event()
    handler = type("Answering", (_Answering,), {"posts": posts, "stopping": stopping})
    httpd = _Quiet(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}/", posts
    finally:
        stopping.set()
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def _opened(chromium: Browser, url: str) -> Page:
    page = chromium.new_context().new_page()
    page.goto(url, wait_until="load")
    page.wait_for_function("() => window.stream.readyState === 1")
    return page


def _propose_and_park(page: Page, index: int) -> list:
    """Send one write, and wait until its answer is parked."""
    parked = _park_the_answer(page, RUN, "proposals")
    page.evaluate("index => { window.propose(index); }", index)
    # The handler runs on the connection's next turn, which a bounded wait
    # hands it -- the same wait `_press_and_hold` gives its held request.
    for _ in range(200):
        if parked:
            break
        page.wait_for_timeout(5)
    assert len(parked) == 1, (index, parked)
    return parked


def test_a_long_run_of_releases_strands_no_read(
        chromium: Browser, answering: tuple[str, list]) -> None:
    """Every read that each handed-over answer started has settled."""
    url, posts = answering
    page = _opened(chromium, url)
    try:
        for index in range(RELEASES):
            parked = _propose_and_park(page, index)
            _release_parked(page, RUN, "proposals", parked)
            try:
                page.wait_for_function(ENDED, arg=index, timeout=3000)
            except BrowserTimeout as error:
                pending = page.evaluate(
                    "() => Object.entries(window.reads)"
                    ".filter(([, state]) => state === 'pending')")
                raise AssertionError(
                    f"release {index} of {RELEASES} stranded a read: {pending}") from error
        assert len(posts) == RELEASES
        assert set(page.evaluate("() => Object.values(window.reads)")) == {"settled"}
    finally:
        page.context.close()


def test_a_write_after_the_release_reaches_the_server(
        chromium: Browser, answering: tuple[str, list]) -> None:
    """A hand-over stops the HOLDING: the next write is answered, not parked."""
    url, posts = answering
    page = _opened(chromium, url)
    try:
        parked = _propose_and_park(page, 0)
        _release_parked(page, RUN, "proposals", parked)
        page.wait_for_function(ENDED, arg=0, timeout=3000)
        with page.expect_response(lambda answer: answer.url.endswith("/proposals"),
                                  timeout=5000) as answered:
            page.evaluate("() => { window.propose(1); }")
        assert answered.value.status == 201
        assert len(parked) == 1 and len(posts) == 2
    finally:
        page.context.close()
