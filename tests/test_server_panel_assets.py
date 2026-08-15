"""The Cockpit's static resources are exact packaged, GET-only assets."""
from __future__ import annotations

import importlib.resources
import urllib.error
import urllib.request

from tests.test_server import start
from tests.test_store import good_lane, write_project


ASSETS = {
    "/panel/command.css": "text/css; charset=utf-8",
    "/panel/command.js": "text/javascript; charset=utf-8",
}


def _status(url, *, data=None):
    try:
        with urllib.request.urlopen(url, data=data, timeout=5) as response:
            return response.status, response.read(), dict(response.headers)
    except urllib.error.HTTPError as error:
        return error.code, error.read(), dict(error.headers)


def test_server_returns_only_the_two_exact_package_resources(tmp_path):
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    server, base = start(root)
    panel = importlib.resources.files("conductor") / "panel"
    try:
        for target, content_type in ASSETS.items():
            status, body, headers = _status(base + target)
            assert status == 200
            assert body == (panel / target.rsplit("/", 1)[1]).read_bytes()
            assert headers["Content-Type"] == content_type
            assert headers["Cache-Control"] == "no-store"
        for target in (
                "/panel/command.json", "/panel/../server.py",
                "/panel/command.js?cache=1"):
            assert _status(base + target)[0] == 404
    finally:
        server.shutdown()
        server.server_close()


def test_panel_assets_are_get_only_and_post_is_byte_inert(tmp_path):
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    server, base = start(root)
    panel = importlib.resources.files("conductor") / "panel"
    before = {name: (panel / name).read_bytes() for name in ("command.css", "command.js")}
    try:
        for target in ASSETS:
            assert _status(base + target, data=b"{}")[0] == 404
    finally:
        server.shutdown()
        server.server_close()
    after = {name: (panel / name).read_bytes() for name in before}
    assert after == before
