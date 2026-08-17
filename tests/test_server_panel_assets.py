"""The Cockpit's static resources are exact packaged, GET-only assets."""
from __future__ import annotations

import importlib.resources
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import pytest

from conductor import server
from tests.test_server import start
from tests.test_store import good_lane, write_project


ROOT = Path(__file__).resolve().parents[1]
ASSETS = {
    "/panel/command.css": "text/css; charset=utf-8",
    "/panel/command.js": "text/javascript; charset=utf-8",
    "/panel/command-projection.js": "text/javascript; charset=utf-8",
    "/panel/command-view.js": "text/javascript; charset=utf-8",
}
#: Every shape the split must never turn into a route: a guessed sibling, a
#: traversal, a query, a directory listing, a case fold, a trailing slash —
#: and every ALPHA-2 Graph file, packaged but deliberately not served yet.
REFUSED = (
    "/panel/command.json", "/panel/../server.py", "/panel/command.js?cache=1",
    "/panel/command-view.js?v=2", "/panel/%2e%2e/server.py", "/panel/",
    "/panel/index.html", "/panel/COMMAND-VIEW.JS", "/panel/command-view.js/",
    "/panel/command-view.js.map", "/panel/command-projection.js%00.txt",
    "/panel/graph.html", "/panel/graph.css", "/panel/graph.js",
    "/panel/graph-store.js", "/panel/graph-view.js",
)
#: The ALPHA-2 Graph window ships in the package beside the Cockpit but is
#: served by no route: server.py is frozen until the runtime side hands over
#: its API fixtures, so the browser suite serves these files through its own
#: static server (browser_tests/test_graph_rendered.py) and the production
#: server refuses them above. The moment a graph route lands in PANEL_ASSETS,
#: its file must leave this exact list — the allowlist check below reddens on
#: a stale entry as it does on a missing one.
UNSERVED = ("graph.css", "graph.js", "graph-store.js", "graph-view.js")


def _status(url, *, data=None):
    try:
        with urllib.request.urlopen(url, data=data, timeout=5) as response:
            return response.status, response.read(), dict(response.headers)
    except urllib.error.HTTPError as error:
        return error.code, error.read(), dict(error.headers)


def _post_refusal(url):
    """POST one body to a GET-only asset and name the shape of the refusal.

    The handler answers 404 without draining the request body, so the refusal
    can reach the client as an aborted connection instead of a response. Both
    are refusals; the point of the caller is that neither serves a byte.
    """
    try:
        with urllib.request.urlopen(url, data=b"{}", timeout=5) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code
    except OSError:
        return "aborted"


def test_server_returns_only_the_four_exact_package_resources(tmp_path):
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
            assert _post_refusal(base + target) in (404, "aborted")
    finally:
        server_.shutdown()
        server_.server_close()
    after = {name: (panel / name).read_bytes() for name in before}
    assert after == before


def test_the_allowlist_is_exact_literals_and_never_a_derived_path():
    assert set(server.PANEL_ASSETS) == set(ASSETS)
    for target, (content_type, name) in server.PANEL_ASSETS.items():
        assert content_type == ASSETS[target]
        assert target == f"/panel/{name}"
        assert name and not set(name) & set("/\\%?:*")


def test_every_packaged_panel_script_and_style_is_an_allowlisted_asset():
    panel = importlib.resources.files("conductor") / "panel"
    names = {entry.name for entry in panel.iterdir()}
    assert set(UNSERVED) <= names, "stale UNSERVED entry names no packaged file"
    assert not set(UNSERVED) & {name for _, name in server.PANEL_ASSETS.values()}
    packaged = sorted(
        entry.name for entry in panel.iterdir()
        if entry.name.endswith((".js", ".css")) and entry.name not in UNSERVED)
    assert packaged == sorted(name for _, name in server.PANEL_ASSETS.values())


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
