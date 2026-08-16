"""The Cockpit's static resources are exact packaged, GET-only assets."""
from __future__ import annotations

import importlib.resources
import urllib.error
import urllib.request

from conductor import server
from tests.test_server import start
from tests.test_store import good_lane, write_project


ASSETS = {
    "/panel/command.css": "text/css; charset=utf-8",
    "/panel/command.js": "text/javascript; charset=utf-8",
    "/panel/command-projection.js": "text/javascript; charset=utf-8",
    "/panel/command-view.js": "text/javascript; charset=utf-8",
}
#: Every shape the split must never turn into a route: a guessed sibling, a
#: traversal, a query, a directory listing, a case fold, a trailing slash.
REFUSED = (
    "/panel/command.json", "/panel/../server.py", "/panel/command.js?cache=1",
    "/panel/command-view.js?v=2", "/panel/%2e%2e/server.py", "/panel/",
    "/panel/index.html", "/panel/COMMAND-VIEW.JS", "/panel/command-view.js/",
    "/panel/command-view.js.map", "/panel/command-projection.js%00.txt",
)


def _status(url, *, data=None):
    try:
        with urllib.request.urlopen(url, data=data, timeout=5) as response:
            return response.status, response.read(), dict(response.headers)
    except urllib.error.HTTPError as error:
        return error.code, error.read(), dict(error.headers)


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
            assert _status(base + target, data=b"{}")[0] == 404
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
    packaged = sorted(
        entry.name for entry in panel.iterdir()
        if entry.name.endswith((".js", ".css")))
    assert packaged == sorted(name for _, name in server.PANEL_ASSETS.values())
