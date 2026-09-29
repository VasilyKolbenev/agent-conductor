"""Packaged panel assets: the exact allowlist the server serves and the entry page.

Extracted from `server.py` when that module neared its line cap. This module is
data only: it opens no file, binds no socket and reads no request, so the
handler in `server.py` stays the one reader of these resources.
"""
from __future__ import annotations

#: Every packaged Studio file that is SERVED. `studio.html` is deliberately
#: absent: `GET /` answers with it, and a second route would give one document
#: two. A module that is packaged and missing here fails the packaged-resource
#: partition test in tests/test_server_panel_assets.py.
_STUDIO_FILES = (
    "studio.css", "studio.js", "studio-model.js", "studio-layout.js", "studio-review.js",
    "studio-runread.js", "studio-edits.js", "studio-sections.js", "studio-artifacts.js",
    "studio-fields.js", "studio-transitions.js", "studio-store.js", "studio-view.js",
    "studio-runform.js", "studio-canvas.js", "studio-inspector.js", "studio-runs.js",
    "studio-runwords.js", "studio-runstep.js", "studio-runwrite.js", "studio-people.js",
    "studio-rundocs.js", "studio-rundraft.js", "studio-runwrites.js", "studio-toolbardraft.js",
    "studio-controls.js", "studio-isolation.js", "studio-focus.js", "studio-participants.js",
    "studio-tasks-model.js", "studio-tasks.js", "studio-taskflow.js",
    "studio-mounts.js", "studio-quotas-model.js", "studio-quotas.js", "studio-quotaflow.js",
    "studio-orbit.js", "studio-ceilings.js", "studio-situation.js",
    "studio-i18n.js", "studio-preferences.js", "studio-shell.js", "studio-runhead.js",
    "studio-scene-model.js", "studio-trace.js", "studio-taskruns.js", "studio-bridge.js",
    "studio-automation.js", "studio-automation-model.js", "studio-automation-providers.js",
    "studio-workflow-copy.js",
    "studio-workflow-detail-copy.js",
    "studio-view-copy.js",
    "studio-runform-copy.js",
    "studio-runs-copy.js",
    "studio-run-docs-copy.js",
    "studio-participant-copy.js",
    "studio-runstep-copy.js",
    "studio-feedback.js", "studio-feedback-model.js", "studio-feedback-copy.js", "studio-notice-copy.js",
    "studio-agents-copy.js", "studio-automation-flow.js", "studio-automation-copy.js", "studio-workflowwrite.js", "studio-draft.js")
_STUDIO_TYPES = {"css": "text/css; charset=utf-8",
                 "js": "text/javascript; charset=utf-8"}

#: The page `GET /` answers with: the Studio's shell, named by a literal here
#: so no request target can select it. It is not a `PANEL_ASSETS` key.
ENTRY_PAGE = "studio.html"

#: The desk's own files, registered by the desk's lane and served from the first
#: day. Written as literal rows -- route, content type, packaged name -- for the
#: reason the Studio's names are literals below: nothing in a route comes from a
#: request. `desk.html` is reachable here while `GET /` still answers
#: `ENTRY_PAGE`; the entry page switches to it in the slice that removes the
#: Studio's five tabs, and `hub` mounts this route both before and after. Every
#: row must also be a key of `PANEL_ASSETS`, which splices this table in.
DESK_ASSETS = {
    "/panel/desk.html": ("text/html; charset=utf-8", "desk.html"),
    # The wire doors the Studio's boot module and, later, the desk share.
    "/panel/desk-transport.js": ("text/javascript; charset=utf-8", "desk-transport.js"),
}

# Exact package resources, never a path derived from the request target.
PANEL_ASSETS = {
    "/panel/command.css": ("text/css; charset=utf-8", "command.css"),
    "/panel/command.js": ("text/javascript; charset=utf-8", "command.js"),
    "/panel/command-projection.js": (
        "text/javascript; charset=utf-8", "command-projection.js"),
    "/panel/command-view.js": (
        "text/javascript; charset=utf-8", "command-view.js"),
    # The Graph window, entry included. Seven literal names, each spelling
    # its own packaged file: the route is the key, never a fragment of the
    # request target, so a sibling, a query, a traversal or a source-map URL
    # is simply not in this mapping and falls to the 404 arm like any other
    # unknown path.
    "/panel/graph.html": ("text/html; charset=utf-8", "graph.html"),
    "/panel/graph.css": ("text/css; charset=utf-8", "graph.css"),
    "/panel/graph.js": ("text/javascript; charset=utf-8", "graph.js"),
    "/panel/graph-payload.js": (
        "text/javascript; charset=utf-8", "graph-payload.js"),
    "/panel/graph-store.js": (
        "text/javascript; charset=utf-8", "graph-store.js"),
    "/panel/graph-view.js": ("text/javascript; charset=utf-8", "graph-view.js"),
    "/panel/graph-adapter.js": (
        "text/javascript; charset=utf-8", "graph-adapter.js"),
    "/panel/graph-default.js": (
        "text/javascript; charset=utf-8", "graph-default.js"),
    # The Workflow Studio. Its shell is what `GET /` answers with, so — unlike
    # graph.html — studio.html is NOT on this list: it is the panel route's own
    # entry, and putting it here as well would give one document two routes.
    # Its stylesheet and its modules are ordinary allowlisted assets, and they
    # are BUILT from `_STUDIO_FILES` rather than written out twice each: the
    # route is `/panel/<name>` and the packaged file is `<name>`, which is a
    # naming rule and not a table. Written out, every module cost two lines
    # here and pushed this file over its own line cap the day the inspector was
    # split. The keys are still literals derived from literals — nothing in
    # them comes from a request — so the allowlist is exactly as closed as it
    # was when it was typed out.
    **{f"/panel/{name}": (_STUDIO_TYPES[name.rsplit(".", 1)[1]], name)
       for name in _STUDIO_FILES},
    # The desk: its own registry, spliced in whole.
    **DESK_ASSETS,
    # The classic panel. It kept its file name when the Studio took the front
    # door, and this is the route that now reaches it. It was a deliberate 404
    # until this line existed, which is exactly why its near-misses in
    # tests/test_server_panel_assets.py had to be re-decided in the same commit.
    "/panel/index.html": ("text/html; charset=utf-8", "index.html"),
}
