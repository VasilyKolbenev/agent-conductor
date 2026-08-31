"""The Cockpit's static resources are exact packaged, GET-only assets."""
from __future__ import annotations

import importlib.resources
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from conductor import server
from conductor.command.http_transport import MAX_COMMAND_BODY_BYTES
from tests.test_server import start
from tests.test_store import good_lane, write_project


ROOT = Path(__file__).resolve().parents[1]
ASSETS = {
    "/panel/command.css": "text/css; charset=utf-8",
    "/panel/command.js": "text/javascript; charset=utf-8",
    "/panel/command-projection.js": "text/javascript; charset=utf-8",
    "/panel/command-view.js": "text/javascript; charset=utf-8",
    "/panel/graph.html": "text/html; charset=utf-8",
    "/panel/graph.css": "text/css; charset=utf-8",
    "/panel/graph.js": "text/javascript; charset=utf-8",
    "/panel/graph-payload.js": "text/javascript; charset=utf-8",
    "/panel/graph-store.js": "text/javascript; charset=utf-8",
    "/panel/graph-view.js": "text/javascript; charset=utf-8",
    "/panel/graph-adapter.js": "text/javascript; charset=utf-8",
    "/panel/graph-default.js": "text/javascript; charset=utf-8",
    # The Workflow Studio's stylesheet and boundary module. Its SHELL is not
    # here: studio.html is what `GET /` answers with, and a document with two
    # routes is a document a reader can reach by two names.
    "/panel/studio.css": "text/css; charset=utf-8",
    "/panel/studio-model.js": "text/javascript; charset=utf-8",
    "/panel/studio.js": "text/javascript; charset=utf-8",
    "/panel/studio-layout.js": "text/javascript; charset=utf-8",
    "/panel/studio-review.js": "text/javascript; charset=utf-8",
    "/panel/studio-edits.js": "text/javascript; charset=utf-8",
    "/panel/studio-sections.js": "text/javascript; charset=utf-8",
    "/panel/studio-artifacts.js": "text/javascript; charset=utf-8",
    "/panel/studio-transitions.js": "text/javascript; charset=utf-8",
    "/panel/studio-fields.js": "text/javascript; charset=utf-8",
    "/panel/studio-runread.js": "text/javascript; charset=utf-8",
    "/panel/studio-store.js": "text/javascript; charset=utf-8",
    "/panel/studio-view.js": "text/javascript; charset=utf-8",
    "/panel/studio-runform.js": "text/javascript; charset=utf-8",
    "/panel/studio-canvas.js": "text/javascript; charset=utf-8",
    "/panel/studio-inspector.js": "text/javascript; charset=utf-8",
    "/panel/studio-runs.js": "text/javascript; charset=utf-8",
    "/panel/studio-people.js": "text/javascript; charset=utf-8",
    # The classic panel, at the route that now reaches it. This target was a
    # deliberate 404 while `GET /` served index.html; the Studio took the front
    # door, so the near-miss that used to assert the 404 became this row.
    "/panel/index.html": "text/html; charset=utf-8",
}
#: Every shape the split must never turn into a route: a guessed sibling, a
#: traversal, a query, a directory listing, a case fold, a trailing slash, a
#: source-map URL, a null-byte suffix. The Graph window's own files are now
#: served, so each of those shapes is asserted against THEM too — a route that
#: became real is exactly the moment its near-misses stop being hypothetical.
REFUSED = (
    "/panel/command.json", "/panel/../server.py", "/panel/command.js?cache=1",
    "/panel/command-view.js?v=2", "/panel/%2e%2e/server.py", "/panel/",
    "/panel/COMMAND-VIEW.JS", "/panel/command-view.js/",
    "/panel/command-view.js.map", "/panel/command-projection.js%00.txt",
    "/panel/graph.json", "/panel/graph.htm", "/panel/graph-store.json",
    "/panel/graph.js?v=1", "/panel/graph.html?run=run-001",
    "/panel/graph.js.map", "/panel/graph-view.js.map",
    "/panel/../graph.js", "/panel/%2e%2e/graph.js", "/panel/GRAPH.JS",
    "/panel/Graph.html", "/panel/graph.js/", "/panel/graph-store.js%00.txt",
    "/panel/graph-runtime.js", "/panel/graph-wire.js",
    "/panel/graph-payload.json", "/panel/graph-payload.js?v=1",
    "/panel/graph-payload.js.map", "/panel/GRAPH-PAYLOAD.JS",
    # The classic panel's own near-misses. Its route became real in the same
    # commit that took the front door away from it, which is exactly the moment
    # every shape around it stopped being hypothetical.
    "/panel/index.json", "/panel/index.htm", "/panel/index.html?v=1",
    "/panel/index.html.map", "/panel/../index.html",
    "/panel/%2e%2e/index.html", "/panel/INDEX.HTML", "/panel/Index.html",
    "/panel/index.html/", "/panel/index.html%00.txt",
    # The Studio's shell is the entry `GET /` serves and has no /panel/ route
    # at all, so every spelling of it under this prefix is a 404 -- including
    # the correct one. A document reachable by two names is a document whose
    # relative links resolve differently depending on which one was used.
    "/panel/studio.html", "/panel/studio.htm", "/panel/studio.html?v=1",
    "/panel/STUDIO.HTML", "/panel/Studio.html", "/panel/studio.html/",
    # The Studio's stylesheet and boundary module.
    "/panel/studio.json", "/panel/studio.css?v=1", "/panel/studio.css.map",
    "/panel/../studio.css", "/panel/%2e%2e/studio.css", "/panel/STUDIO.CSS",
    "/panel/Studio.css", "/panel/studio.css/", "/panel/studio.css%00.txt",
    "/panel/studio-model.json", "/panel/studio-model.js?v=1",
    "/panel/studio-model.js.map", "/panel/../studio-model.js",
    "/panel/%2e%2e/studio-model.js", "/panel/STUDIO-MODEL.JS",
    "/panel/Studio-model.js", "/panel/studio-model.js/",
    "/panel/studio-model.js%00.txt", "/panel/studio-payload.js",
    # The three screen modules, each given the same nine shapes.
    "/panel/studio-canvas.json", "/panel/studio-canvas.js?v=1",
    "/panel/studio-canvas.js.map", "/panel/../studio-canvas.js",
    "/panel/%2e%2e/studio-canvas.js", "/panel/STUDIO-CANVAS.JS",
    "/panel/Studio-canvas.js", "/panel/studio-canvas.js/",
    "/panel/studio-canvas.js%00.txt",
    "/panel/studio-runs.json", "/panel/studio-runs.js?v=1",
    "/panel/studio-runs.js.map", "/panel/../studio-runs.js",
    "/panel/%2e%2e/studio-runs.js", "/panel/STUDIO-RUNS.JS",
    "/panel/Studio-runs.js", "/panel/studio-runs.js/",
    "/panel/studio-runs.js%00.txt",
    "/panel/studio-people.json", "/panel/studio-people.js?v=1",
    "/panel/studio-people.js.map", "/panel/../studio-people.js",
    "/panel/%2e%2e/studio-people.js", "/panel/STUDIO-PEOPLE.JS",
    "/panel/Studio-people.js", "/panel/studio-people.js/",
    "/panel/studio-people.js%00.txt",
    "/panel/studio-inspector.json", "/panel/studio-inspector.js?v=1",
    "/panel/studio-inspector.js.map", "/panel/../studio-inspector.js",
    "/panel/%2e%2e/studio-inspector.js", "/panel/STUDIO-INSPECTOR.JS",
    "/panel/Studio-inspector.js", "/panel/studio-inspector.js/",
    "/panel/studio-inspector.js%00.txt",
    # The transport module, the reducer and the shell view.
    "/panel/studio.js?v=1", "/panel/studio.js.map", "/panel/../studio.js",
    "/panel/%2e%2e/studio.js", "/panel/STUDIO.JS", "/panel/Studio.js",
    "/panel/studio.js/", "/panel/studio.js%00.txt",
    "/panel/studio-store.json", "/panel/studio-store.js?v=1",
    "/panel/studio-store.js.map", "/panel/../studio-store.js",
    "/panel/%2e%2e/studio-store.js", "/panel/STUDIO-STORE.JS",
    "/panel/Studio-store.js", "/panel/studio-store.js/",
    "/panel/studio-store.js%00.txt",
    "/panel/studio-view.json", "/panel/studio-view.js?v=1",
    "/panel/studio-view.js.map", "/panel/../studio-view.js",
    "/panel/%2e%2e/studio-view.js", "/panel/STUDIO-VIEW.JS",
    "/panel/Studio-view.js", "/panel/studio-view.js/",
    "/panel/studio-view.js%00.txt",
)
#: Packaged panel resources served by NO route. The Graph window's files left
#: this list when the route above became real; the partition check below is
#: what keeps the list honest either way — every packaged resource must be
#: allowlisted, named here, or be the entry the panel route itself serves, so
#: a new file cannot appear unserved and unnoticed.
UNSERVED: tuple[str, ...] = ()
#: studio.html is neither: `GET /` serves it through `_serve_panel`, not
#: through the asset allowlist, which is why it is refused under /panel/. The
#: file that used to hold this position, index.html, joined the allowlist in
#: the same commit — the entry moved, and one name still fills the slot.
PANEL_ROUTE_ENTRY = "studio.html"


def _status(url, *, data=None):
    try:
        with urllib.request.urlopen(url, data=data, timeout=5) as response:
            return response.status, response.read(), dict(response.headers)
    except urllib.error.HTTPError as error:
        return error.code, error.read(), dict(error.headers)


def _post_refusal(url):
    """POST one body to a GET-only asset and read the refusal it answers with.

    The exact 404 is the assertion. This helper used to accept a reset as an
    equal refusal, which proved only that no byte was served; a reader could
    not tell whether the route had answered at all. Returning "aborted" here is
    still what a reset would look like -- it is simply no longer accepted.
    """
    try:
        with urllib.request.urlopen(url, data=b"{}", timeout=5) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code
    except OSError:
        return "aborted"


class _CountedStream:
    """A request stream that reports what was TAKEN, computed by the test."""

    def __init__(self, payload: bytes) -> None:
        self.left = payload
        self.taken = b""

    def read(self, size: int) -> bytes:
        chunk, self.left = self.left[:size], self.left[size:]
        self.taken += chunk
        return chunk


class _RefusedPost:
    """Drive the real POST entry for a route this server does not own.

    `do_POST` touches only `path`, `headers`, `rfile`, `close_connection` and
    the refusal it sends, so those are all this stand-in carries -- and taking
    the method itself off `Handler` is what makes the WIRING part of the
    relation: a drain that exists but is never called reads as no drain here.
    """

    post = server.Handler.do_POST
    _drain_refused_body = server.Handler._drain_refused_body

    def __init__(self, pairs: tuple[tuple[str, str], ...], payload: bytes) -> None:
        self.path = "/panel/command.js"
        self.headers = SimpleNamespace(raw_items=lambda: pairs)
        self.rfile = _CountedStream(payload)
        self.close_connection = False
        self.answered: list[int] = []

    def _send_404(self) -> None:
        self.answered.append(404)


def test_server_returns_only_the_exact_package_resources_it_allowlists(tmp_path):
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    server_, base = start(root)
    panel = importlib.resources.files("conductor") / "panel"
    try:
        for target, content_type in ASSETS.items():
            status, body, headers = _status(base + target)
            assert status == 200
            assert body == (panel / target.rsplit("/", 1)[1]).read_bytes()
            assert headers["Content-Type"] == content_type
            assert headers["Cache-Control"] == "no-store"
        for target in REFUSED:
            assert _status(base + target)[0] == 404
    finally:
        server_.shutdown()
        server_.server_close()


def test_panel_assets_are_get_only_and_post_is_byte_inert(tmp_path):
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    server_, base = start(root)
    panel = importlib.resources.files("conductor") / "panel"
    names = tuple(target.rsplit("/", 1)[1] for target in ASSETS)
    before = {name: (panel / name).read_bytes() for name in names}
    try:
        for target in ASSETS:
            assert _post_refusal(base + target) == 404
    finally:
        server_.shutdown()
        server_.server_close()
    after = {name: (panel / name).read_bytes() for name in before}
    assert after == before


#: What a refused POST body may cost the connection. The first row is the only
#: one the door can measure; the rest are bodies whose length is not knowable --
#: none declared, a chunked stream, one over the ceiling, and one the client
#: never finishes -- and nothing may be consumed on a client's unmeasured word.
DRAINS = (
    ("a framed body is taken whole", (("Content-Length", "5"),), b"12345 and more",
     b"12345", False),
    ("no declared length", (), b"body nobody measured", b"", True),
    ("a chunked stream", (("Transfer-Encoding", "chunked"),), b"0\r\n\r\n", b"", True),
    ("a length over the ceiling",
     (("Content-Length", str(MAX_COMMAND_BODY_BYTES + 1)),), b"x" * 32, b"", True),
    ("a client that stops short", (("Content-Length", "8"),), b"four", b"four", True),
)


@pytest.mark.parametrize(
    "name,pairs,payload,taken,closes", DRAINS, ids=[row[0] for row in DRAINS])
def test_a_refused_post_consumes_exactly_what_its_framing_declares(
        name, pairs, payload, taken, closes):
    """The refused route drains through the command route's own bounded door.

    A route this server does not own still owes an ANSWER rather than a socket
    the client must interpret, and answering over an unread body is what leaves
    that to chance. So the body is consumed first -- but only ever as much as
    the SAME framing the command route trusts has measured, which is why the
    unmeasurable rows below take nothing at all and close instead.

    The witness is this test's own payload arithmetic: `_CountedStream` reports
    the bytes handed over, and the expected count is written out per row rather
    than asked of the code under test. Every row also asserts the refusal was
    ANSWERED, so no row can pass by refusing to reply at all.
    """
    refused = _RefusedPost(pairs, payload)
    refused.post()
    assert refused.rfile.taken == taken
    assert refused.close_connection is closes
    assert refused.answered == [404]


def test_the_allowlist_is_exact_literals_and_never_a_derived_path():
    assert set(server.PANEL_ASSETS) == set(ASSETS)
    for target, (content_type, name) in server.PANEL_ASSETS.items():
        assert content_type == ASSETS[target]
        assert target == f"/panel/{name}"
        assert name and not set(name) & set("/\\%?:*")


def test_every_packaged_panel_resource_is_served_named_unserved_or_the_entry():
    """The directory is PARTITIONED, so a new file cannot arrive unnoticed.

    Three answers and no fourth: a resource is on the allowlist, is named
    unserved on purpose, or is the entry `GET /` serves. A file that is none
    of those reds this test the moment it is packaged — which is the only
    reason an unserved list may be empty without the relation going slack.
    """
    panel = importlib.resources.files("conductor") / "panel"
    names = {entry.name for entry in panel.iterdir()}
    assert set(UNSERVED) <= names, "stale UNSERVED entry names no packaged file"
    served = {name for _, name in server.PANEL_ASSETS.values()}
    assert not set(UNSERVED) & served
    assert PANEL_ROUTE_ENTRY in names and PANEL_ROUTE_ENTRY not in served
    packaged = {
        entry.name for entry in panel.iterdir()
        if entry.name.endswith((".js", ".css", ".html"))}
    assert packaged == served | set(UNSERVED) | {PANEL_ROUTE_ENTRY}


def test_the_panel_route_answers_with_the_entry_and_with_no_other_document(
        tmp_path):
    """`GET /` serves the Studio's shell, byte for byte, and says which it is.

    Naming the entry in `PANEL_ROUTE_ENTRY` and partitioning the directory
    against it proves that some file is the entry; it does not prove which file
    the route hands over. Both documents are packaged, both are HTML and both
    carry a `<title>`, so a route pointed back at the classic panel answers 200
    with a title and every other test in this suite stays green — which is
    exactly what happened when this assertion was not here. The bytes are the
    assertion, and they are read from the packaged resource rather than
    described.
    """
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    server_, base = start(root)
    panel = importlib.resources.files("conductor") / "panel"
    try:
        status, body, headers = _status(base + "/")
        assert status == 200
        assert body == (panel / PANEL_ROUTE_ENTRY).read_bytes()
        assert headers["Content-Type"] == "text/html; charset=utf-8"
        assert headers["Cache-Control"] == "no-store"
    finally:
        server_.shutdown()
        server_.server_close()


def test_the_built_wheel_carries_exactly_the_panel_resources_the_server_serves(
        tmp_path):
    """A user receives the wheel, not the source tree — assert on the artifact."""
    wheel_module = pytest.importorskip("hatchling.builders.wheel")
    artifacts = list(
        wheel_module.WheelBuilder(str(ROOT)).build(directory=str(tmp_path)))
    assert len(artifacts) == 1
    with zipfile.ZipFile(artifacts[0]) as wheel:
        shipped = {
            name for name in wheel.namelist()
            if name.startswith("conductor/panel/")}
    panel = importlib.resources.files("conductor") / "panel"
    assert shipped == {
        f"conductor/panel/{entry.name}" for entry in panel.iterdir()
        if entry.is_file()}
    assert "conductor/panel/index.html" in shipped
    assert {
        f"conductor/panel/{name}" for _, name in server.PANEL_ASSETS.values()
    } < shipped
