"""The files the hub serves under `/hub/<name>` (spec 4.6.3): one literal allowlist.

`HUB_ASSETS` maps a route to `(content type, packaged file name)`, the shape of `PANEL_ASSETS`, and
it is exactly the import closure of `hub.js` plus its stylesheet: the page's own files and the four
modules the desk shares with it. The entry page `hub.html` is not a row: `GET /` answers it.

The rows here are the page's (spec 12.4): the lane that writes the page (D2) adds the rows of any
file the page gains, and the lane that owns the rest of this package serves them.
`tests/test_hub_source.py` holds the registry equal to the closure, so a file nobody imports cannot
be served and a file the page needs cannot be left out.
"""
from __future__ import annotations

from types import MappingProxyType

_JS = "text/javascript; charset=utf-8"
_CSS = "text/css; charset=utf-8"

#: Route -> (content type, file name in `conductor/panel/`). Read-only: a contract a caller can edit
#: in place is not one.
HUB_ASSETS = MappingProxyType({
    "/hub/hub.css": (_CSS, "hub.css"),
    "/hub/hub.js": (_JS, "hub.js"),
    "/hub/hub-copy.js": (_JS, "hub-copy.js"),
    "/hub/hub-frame.js": (_JS, "hub-frame.js"),
    "/hub/hub-rail.js": (_JS, "hub-rail.js"),
    "/hub/hub-stub.js": (_JS, "hub-stub.js"),
    # The four modules the desk and the hub share: they import only each other.
    "/hub/desk-hash.js": (_JS, "desk-hash.js"),
    "/hub/desk-status.js": (_JS, "desk-status.js"),
    "/hub/desk-status-copy.js": (_JS, "desk-status-copy.js"),
    "/hub/desk-time.js": (_JS, "desk-time.js"),
})
