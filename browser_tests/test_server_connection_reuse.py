"""What one real page boot costs this server in TCP connections.

Two different pieces of evidence are owed for this repair and this is the
second. `tests/test_server_http_framing.py` proves on a socket that a
connection is kept and that two answers on it do not run into each other;
that is about correctness. This is about the QUANTITY the reverse gate
actually failed on: a boot that opened a fresh connection per request drove
Windows out of socket buffer space, and one Studio module then failed to load
with `net::ERR_NO_BUFFER_SPACE`.

So this counts, on a real server serving a real Chromium: connections
ACCEPTED, against requests ANSWERED, for one boot of the shipped shell. It is
a product measurement, not a proxy -- the count comes from the server's own
accept path and its own request loop, and the page is booted the way every
other module in this gate boots one.
"""
from __future__ import annotations

import threading
from collections.abc import Iterator

import pytest
from playwright.sync_api import Browser

from conductor import server
from tests.test_store import good_lane, write_project

#: The shell's own module graph is what makes a boot expensive: measured at 34
#: requests before this repair. A ceiling well under that, and well above the
#: six a browser opens per origin, is what says the connections were REUSED
#: rather than that the page got smaller.
CONNECTION_CEILING = 12
#: And the floor on the other side, so a boot that silently stopped fetching
#: its modules cannot pass by asking for nothing.
REQUEST_FLOOR = 20


class _Counted(server.Handler):
    """The shipped handler, counting the requests it answers on a connection."""

    requests = 0

    def handle_one_request(self) -> None:      # BaseHTTPRequestHandler name
        type(self).requests += 1
        super().handle_one_request()


@pytest.fixture()
def counted(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[str, type]]:
    """A real server whose accepts and requests are both counted."""
    root = write_project(tmp_path_factory.mktemp("reuse"),
                         lanes={"claude": good_lane()})
    httpd = server.build(root, 0)
    httpd.RequestHandlerClass = _Counted
    accepted = []
    verifying = httpd.verify_request

    def verify_request(request, address):
        accepted.append(address)
        return verifying(request, address)

    httpd.verify_request = verify_request
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    _Counted.requests = 0
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}/", accepted
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def test_one_boot_reuses_its_connections_instead_of_opening_one_per_request(
        chromium: Browser, counted) -> None:
    """The measurement the gate's red was made of.

    Before this repair the server answered HTTP/1.0, so every response ended by
    hanging up and a single boot cost 34 accepted connections. The gate opens
    hundreds of pages per run, and that churn -- not port exhaustion, which was
    excluded by measurement -- is what ran the machine out of socket buffers.

    Asserted as a RELATION rather than an exact number: the boot must really
    ask for its modules, and the connections it opened must carry several
    requests each. An exact count would break on a module added to the shell
    and would say nothing more than this does.
    """
    url, accepted = counted
    context = chromium.new_context()
    page = context.new_page()
    try:
        page.goto(url, wait_until="load")
        page.wait_for_function(
            "() => document.getElementById('studioPrimary').children.length > 0")

        answered = _Counted.requests
        connections = len({address for address in accepted})
        assert answered >= REQUEST_FLOOR, (
            f"the boot asked for only {answered} things; it is not booting")
        assert connections <= CONNECTION_CEILING, (
            f"{connections} connections for {answered} requests")
        assert answered >= connections * 2, (
            f"{answered} requests over {connections} connections is not reuse")
    finally:
        context.close()
