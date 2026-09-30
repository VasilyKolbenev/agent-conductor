"""The Cockpit's static resources are exact packaged, GET-only assets."""
from __future__ import annotations

import ast
import importlib.resources
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from conductor import server, server_assets
from conductor.command.http_transport import MAX_COMMAND_BODY_BYTES
from conductor.hub.assets import HUB_ASSETS
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
    "/panel/studio-situation.js": "text/javascript; charset=utf-8",
    "/panel/studio-i18n.js": "text/javascript; charset=utf-8",
    "/panel/studio-preferences.js": "text/javascript; charset=utf-8",
    "/panel/studio-shell.js": "text/javascript; charset=utf-8",
    "/panel/studio-automation-model.js": "text/javascript; charset=utf-8",
    "/panel/studio-automation-providers.js": "text/javascript; charset=utf-8",
    "/panel/studio-automation-flow.js": "text/javascript; charset=utf-8",
    "/panel/studio-workflow-copy.js": "text/javascript; charset=utf-8",
    "/panel/studio-workflow-detail-copy.js": "text/javascript; charset=utf-8",
    "/panel/studio-view-copy.js": "text/javascript; charset=utf-8",
    "/panel/studio-runform-copy.js": "text/javascript; charset=utf-8",
    "/panel/studio-runs-copy.js": "text/javascript; charset=utf-8",
    "/panel/studio-run-docs-copy.js": "text/javascript; charset=utf-8",
    "/panel/studio-participant-copy.js": "text/javascript; charset=utf-8",
    "/panel/studio-runstep-copy.js": "text/javascript; charset=utf-8",
    "/panel/studio-feedback.js": "text/javascript; charset=utf-8",
    "/panel/studio-feedback-model.js": "text/javascript; charset=utf-8",
    "/panel/studio-feedback-copy.js": "text/javascript; charset=utf-8",
    "/panel/studio-notice-copy.js": "text/javascript; charset=utf-8",
    "/panel/studio-agents-copy.js": "text/javascript; charset=utf-8",
    "/panel/studio-automation-copy.js": "text/javascript; charset=utf-8",
    "/panel/studio-automation.js": "text/javascript; charset=utf-8",
    "/panel/studio-workflowwrite.js": "text/javascript; charset=utf-8",
    "/panel/studio-draft.js": "text/javascript; charset=utf-8",
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
    "/panel/studio-canvas-edges.js": "text/javascript; charset=utf-8",
    "/panel/studio-canvas-flow.js": "text/javascript; charset=utf-8",
    "/panel/studio-inspector.js": "text/javascript; charset=utf-8",
    "/panel/studio-runs.js": "text/javascript; charset=utf-8",
    "/panel/studio-runwords.js": "text/javascript; charset=utf-8",
    "/panel/studio-runstep.js": "text/javascript; charset=utf-8",
    "/panel/studio-runwrite.js": "text/javascript; charset=utf-8",
    "/panel/studio-people.js": "text/javascript; charset=utf-8",
    "/panel/studio-rundocs.js": "text/javascript; charset=utf-8",
    "/panel/studio-rundraft.js": "text/javascript; charset=utf-8",
    "/panel/studio-runwrites.js": "text/javascript; charset=utf-8",
    "/panel/studio-toolbardraft.js": "text/javascript; charset=utf-8",
    "/panel/studio-controls.js": "text/javascript; charset=utf-8",
    "/panel/studio-isolation.js": "text/javascript; charset=utf-8",
    "/panel/studio-focus.js": "text/javascript; charset=utf-8",
    "/panel/studio-participants.js": "text/javascript; charset=utf-8",
    "/panel/studio-orbit.js": "text/javascript; charset=utf-8",
    "/panel/studio-ceilings.js": "text/javascript; charset=utf-8",
    "/panel/studio-tasks.js": "text/javascript; charset=utf-8",
    "/panel/studio-tasks-model.js": "text/javascript; charset=utf-8",
    "/panel/studio-taskflow.js": "text/javascript; charset=utf-8",
    "/panel/studio-mounts.js": "text/javascript; charset=utf-8",
    "/panel/studio-scene-model.js": "text/javascript; charset=utf-8",
    "/panel/studio-trace.js": "text/javascript; charset=utf-8",
    "/panel/studio-taskruns.js": "text/javascript; charset=utf-8",
    "/panel/studio-bridge.js": "text/javascript; charset=utf-8",
    "/panel/studio-runhead.js": "text/javascript; charset=utf-8",

    "/panel/studio-quotas-model.js": "text/javascript; charset=utf-8",
    "/panel/studio-quotas.js": "text/javascript; charset=utf-8",
    "/panel/studio-quotaflow.js": "text/javascript; charset=utf-8",
    # The desk's page, at its own address from the first day: the hub mounts
    # this route before `GET /` ever switches to it, and `GET /` still answers
    # studio.html, so the two documents are told apart by route alone.
    "/panel/desk.html": "text/html; charset=utf-8",
    "/panel/desk.css": "text/css; charset=utf-8",
    "/panel/desk.js": "text/javascript; charset=utf-8",
    # The wire doors, moved out of the Studio's boot module for the desk to share.
    "/panel/desk-transport.js": "text/javascript; charset=utf-8",
    # The desk's own words, RU and EN.
    "/panel/desk-copy.js": "text/javascript; charset=utf-8",
    # The word of a task row and the strings that say it.
    "/panel/desk-status.js": "text/javascript; charset=utf-8",
    "/panel/desk-status-copy.js": "text/javascript; charset=utf-8",
    # The grammar of the desk's hash, shared with the hub's page.
    "/panel/desk-hash.js": "text/javascript; charset=utf-8",
    # Embed mode: whether a hub frames the desk, and the one message it says.
    "/panel/desk-embed.js": "text/javascript; charset=utf-8",
    # The time of an instant, short and exact: shared with the hub's page.
    "/panel/desk-time.js": "text/javascript; charset=utf-8",
    # The task-queue read judged against its shape.
    "/panel/desk-queue-model.js": "text/javascript; charset=utf-8",
    # The continue-after flag judged against its shape, and the runs a person may mark.
    "/panel/desk-flag-model.js": "text/javascript; charset=utf-8",
    # The one read and the one write of that flag.
    "/panel/desk-flag.js": "text/javascript; charset=utf-8",
    # The reads that say whether a task was closed.
    "/panel/desk-closing.js": "text/javascript; charset=utf-8",
    # The summary's counters, tasks and people.
    "/panel/desk-summary-model.js": "text/javascript; charset=utf-8",
    # The journal of a run read as the rows of the feed, and the words that say them.
    "/panel/desk-feed-model.js": "text/javascript; charset=utf-8",
    "/panel/desk-feed-copy.js": "text/javascript; charset=utf-8",
    # The regions the desk draws.
    "/panel/desk-rail.js": "text/javascript; charset=utf-8",
    "/panel/desk-scene.js": "text/javascript; charset=utf-8",
    "/panel/desk-feed.js": "text/javascript; charset=utf-8",
    "/panel/desk-pult.js": "text/javascript; charset=utf-8",
    # The wizard's pure model: the lane that writes the wizard registers its own rows.
    "/panel/desk-wizard-model.js": "text/javascript; charset=utf-8",
    "/panel/desk-wizard-materials.js": "text/javascript; charset=utf-8",
    "/panel/desk-wizard-cycle.js": "text/javascript; charset=utf-8",
    "/panel/desk-wizard-roles.js": "text/javascript; charset=utf-8",
    "/panel/desk-wizard-base.js": "text/javascript; charset=utf-8",
    "/panel/desk-wizard-team.js": "text/javascript; charset=utf-8",
    "/panel/desk-wizard-digest.js": "text/javascript; charset=utf-8",
    "/panel/desk-wizard-input.js": "text/javascript; charset=utf-8",
    "/panel/desk-wizard-prep.js": "text/javascript; charset=utf-8",
    "/panel/desk-wizard-launch.js": "text/javascript; charset=utf-8",
    "/panel/desk-wizard-skip.js": "text/javascript; charset=utf-8",
    "/panel/desk-wizard-run.js": "text/javascript; charset=utf-8",
    "/panel/desk-wizard-draw.js": "text/javascript; charset=utf-8",
    "/panel/desk-wizard-prepare-view.js": "text/javascript; charset=utf-8",
    "/panel/desk-wizard-card.js": "text/javascript; charset=utf-8",
    "/panel/desk-wizard-copy.js": "text/javascript; charset=utf-8",
    "/panel/desk-wizard.js": "text/javascript; charset=utf-8",
    "/panel/desk-flow-shape.js": "text/javascript; charset=utf-8",
    "/panel/desk-flow-loops.js": "text/javascript; charset=utf-8",
    "/panel/desk-flow-branches.js": "text/javascript; charset=utf-8",
    "/panel/desk-flow-edits.js": "text/javascript; charset=utf-8",
    "/panel/desk-flowwrite.js": "text/javascript; charset=utf-8",
    "/panel/desk-quickcycle.js": "text/javascript; charset=utf-8",
    "/panel/desk-flow-graph.js": "text/javascript; charset=utf-8",
    "/panel/desk-flow-fields.js": "text/javascript; charset=utf-8",
    "/panel/desk-flow-model.js": "text/javascript; charset=utf-8",
    "/panel/desk-flow-copy.js": "text/javascript; charset=utf-8",
    "/panel/desk-flow-draw.js": "text/javascript; charset=utf-8",
    "/panel/desk-flow-diag.js": "text/javascript; charset=utf-8",
    "/panel/desk-flow-inspector.js": "text/javascript; charset=utf-8",
    "/panel/desk-flow.js": "text/javascript; charset=utf-8",
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
    "/panel/studio-situation.js?v=1", "/panel/studio-situation.js.map",
    "/panel/STUDIO-SITUATION.JS", "/panel/studio-situation.js/",
    "/panel/%2e%2e/studio-situation.js",
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
    # The desk page's near-misses (spec 5.6.9). Its route is real from the day
    # its file is packaged, so every neighbouring spelling -- a wrong suffix, a
    # query, a case fold, a trailing slash, an encoded traversal -- is asserted
    # a 404 in the same commit rather than left to be found later.
    "/panel/desk.htm", "/panel/desk.html?v=1", "/panel/DESK.HTML",
    "/panel/Desk.html", "/panel/desk.html/", "/panel/%2e%2e/desk.html",
    # The desk's stylesheet, given the same nine shapes as the Studio's own.
    "/panel/desk.json", "/panel/desk.css?v=1", "/panel/desk.css.map",
    "/panel/../desk.css", "/panel/%2e%2e/desk.css", "/panel/DESK.CSS",
    "/panel/Desk.css", "/panel/desk.css/", "/panel/desk.css%00.txt",
    # The desk's boot module: a guessed sibling and the eight spellings around it.
    "/panel/desk-boot.js", "/panel/desk.js?v=1", "/panel/desk.js.map",
    "/panel/../desk.js", "/panel/%2e%2e/desk.js", "/panel/DESK.JS",
    "/panel/Desk.js", "/panel/desk.js/", "/panel/desk.js%00.txt",
    # The wire doors module, given the same nine shapes as the Studio's own.
    "/panel/desk-transport.json", "/panel/desk-transport.js?v=1",
    "/panel/desk-transport.js.map", "/panel/../desk-transport.js",
    "/panel/%2e%2e/desk-transport.js", "/panel/DESK-TRANSPORT.JS",
    "/panel/Desk-transport.js", "/panel/desk-transport.js/",
    "/panel/desk-transport.js%00.txt",
    # The desk's catalogue, the same nine shapes again.
    "/panel/desk-copy.json", "/panel/desk-copy.js?v=1", "/panel/desk-copy.js.map",
    "/panel/../desk-copy.js", "/panel/%2e%2e/desk-copy.js", "/panel/DESK-COPY.JS",
    "/panel/Desk-copy.js", "/panel/desk-copy.js/", "/panel/desk-copy.js%00.txt",
    # The two status modules, the same nine shapes each.
    "/panel/desk-status.json", "/panel/desk-status.js?v=1", "/panel/desk-status.js.map",
    "/panel/../desk-status.js", "/panel/%2e%2e/desk-status.js", "/panel/DESK-STATUS.JS",
    "/panel/Desk-status.js", "/panel/desk-status.js/", "/panel/desk-status.js%00.txt",
    "/panel/desk-status-copy.json", "/panel/desk-status-copy.js?v=1",
    "/panel/desk-status-copy.js.map", "/panel/../desk-status-copy.js",
    "/panel/%2e%2e/desk-status-copy.js", "/panel/DESK-STATUS-COPY.JS",
    "/panel/Desk-status-copy.js", "/panel/desk-status-copy.js/",
    "/panel/desk-status-copy.js%00.txt",
    # The address module, the same nine shapes.
    "/panel/desk-hash.json", "/panel/desk-hash.js?v=1", "/panel/desk-hash.js.map",
    "/panel/../desk-hash.js", "/panel/%2e%2e/desk-hash.js", "/panel/DESK-HASH.JS",
    "/panel/Desk-hash.js", "/panel/desk-hash.js/", "/panel/desk-hash.js%00.txt",
    # The embed module, the same nine shapes.
    "/panel/desk-embed.json", "/panel/desk-embed.js?v=1", "/panel/desk-embed.js.map",
    "/panel/../desk-embed.js", "/panel/%2e%2e/desk-embed.js", "/panel/DESK-EMBED.JS",
    "/panel/Desk-embed.js", "/panel/desk-embed.js/", "/panel/desk-embed.js%00.txt",
    # The time module, the same nine shapes.
    "/panel/desk-time.json", "/panel/desk-time.js?v=1", "/panel/desk-time.js.map",
    "/panel/../desk-time.js", "/panel/%2e%2e/desk-time.js", "/panel/DESK-TIME.JS",
    "/panel/Desk-time.js", "/panel/desk-time.js/", "/panel/desk-time.js%00.txt",
    # The queue model, the same nine shapes.
    "/panel/desk-queue-model.json", "/panel/desk-queue-model.js?v=1",
    "/panel/desk-queue-model.js.map", "/panel/../desk-queue-model.js",
    "/panel/%2e%2e/desk-queue-model.js", "/panel/DESK-QUEUE-MODEL.JS",
    "/panel/Desk-queue-model.js", "/panel/desk-queue-model.js/",
    "/panel/desk-queue-model.js%00.txt",
    # The flag model, the same nine shapes.
    "/panel/desk-flag-model.json", "/panel/desk-flag-model.js?v=1",
    "/panel/desk-flag-model.js.map", "/panel/../desk-flag-model.js",
    "/panel/%2e%2e/desk-flag-model.js", "/panel/DESK-FLAG-MODEL.JS",
    "/panel/Desk-flag-model.js", "/panel/desk-flag-model.js/",
    "/panel/desk-flag-model.js%00.txt",
    # The flag's door, the same nine shapes.
    "/panel/desk-flag.json", "/panel/desk-flag.js?v=1", "/panel/desk-flag.js.map",
    "/panel/../desk-flag.js", "/panel/%2e%2e/desk-flag.js", "/panel/DESK-FLAG.JS",
    "/panel/Desk-flag.js", "/panel/desk-flag.js/", "/panel/desk-flag.js%00.txt",
    # The feed's model, the same nine shapes.
    "/panel/desk-feed-model.json", "/panel/desk-feed-model.js?v=1",
    "/panel/desk-feed-model.js.map", "/panel/../desk-feed-model.js",
    "/panel/%2e%2e/desk-feed-model.js", "/panel/DESK-FEED-MODEL.JS",
    "/panel/Desk-feed-model.js", "/panel/desk-feed-model.js/",
    "/panel/desk-feed-model.js%00.txt",
    # The closing reads, the same nine shapes.
    "/panel/desk-closing.json", "/panel/desk-closing.js?v=1", "/panel/desk-closing.js.map",
    "/panel/../desk-closing.js", "/panel/%2e%2e/desk-closing.js", "/panel/DESK-CLOSING.JS",
    "/panel/Desk-closing.js", "/panel/desk-closing.js/", "/panel/desk-closing.js%00.txt",
    # The summary's model, the same nine shapes.
    "/panel/desk-summary-model.json", "/panel/desk-summary-model.js?v=1",
    "/panel/desk-summary-model.js.map", "/panel/../desk-summary-model.js",
    "/panel/%2e%2e/desk-summary-model.js", "/panel/DESK-SUMMARY-MODEL.JS",
    "/panel/Desk-summary-model.js", "/panel/desk-summary-model.js/",
    "/panel/desk-summary-model.js%00.txt",
    # The feed's words and the feed itself, the same nine shapes each.
    "/panel/desk-feed-copy.json", "/panel/desk-feed-copy.js?v=1",
    "/panel/desk-feed-copy.js.map", "/panel/../desk-feed-copy.js",
    "/panel/%2e%2e/desk-feed-copy.js", "/panel/DESK-FEED-COPY.JS",
    "/panel/Desk-feed-copy.js", "/panel/desk-feed-copy.js/", "/panel/desk-feed-copy.js%00.txt",
    "/panel/desk-feed.json", "/panel/desk-feed.js?v=1", "/panel/desk-feed.js.map",
    "/panel/../desk-feed.js", "/panel/%2e%2e/desk-feed.js", "/panel/DESK-FEED.JS",
    "/panel/Desk-feed.js", "/panel/desk-feed.js/", "/panel/desk-feed.js%00.txt",
    # The rail, the same nine shapes.
    "/panel/desk-rail.json", "/panel/desk-rail.js?v=1", "/panel/desk-rail.js.map",
    "/panel/../desk-rail.js", "/panel/%2e%2e/desk-rail.js", "/panel/DESK-RAIL.JS",
    "/panel/Desk-rail.js", "/panel/desk-rail.js/", "/panel/desk-rail.js%00.txt",
    # The scene, the same nine shapes.
    "/panel/desk-scene.json", "/panel/desk-scene.js?v=1", "/panel/desk-scene.js.map",
    "/panel/../desk-scene.js", "/panel/%2e%2e/desk-scene.js", "/panel/DESK-SCENE.JS",
    "/panel/Desk-scene.js", "/panel/desk-scene.js/", "/panel/desk-scene.js%00.txt",
    # The console, the same nine shapes.
    "/panel/desk-pult.json", "/panel/desk-pult.js?v=1", "/panel/desk-pult.js.map",
    "/panel/../desk-pult.js", "/panel/%2e%2e/desk-pult.js", "/panel/DESK-PULT.JS",
    "/panel/Desk-pult.js", "/panel/desk-pult.js/", "/panel/desk-pult.js%00.txt",
)
#: Packaged panel resources served by NO route. The Graph window's files left
#: this list when the route above became real; the partition check below is
#: what keeps the list honest either way — every packaged resource must be
#: allowlisted, named here, or be the entry the panel route itself serves, so
#: a new file cannot appear unserved and unnoticed.
#:
#: The hub page's own files are served by the hub (its registry, and its `GET /` for the entry
#: page), never by this project server: they are named here, from the registry, so a file the hub
#: gains is accounted for without a second list. The four modules the hub shares with the desk are
#: served here too and are not listed.
UNSERVED: tuple[str, ...] = tuple(sorted(
    {name for _, name in HUB_ASSETS.values() if name.startswith("hub")} | {"hub.html"}))
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


def test_the_allowlist_is_exactly_the_expected_routes_each_named_for_a_plain_file():
    """The route set, the content types and the spelling of each name; not packaging.

    That every named file is packaged is the claim of the partition test below
    and of the served-bytes and wheel tests: a row for a file that is not there
    leaves this test green and reds those.
    """
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


def test_the_desk_page_is_served_at_its_own_address_while_the_front_door_still_answers_the_studio(
        tmp_path):
    """Two documents, two routes: the desk is reachable and `GET /` has not moved.

    The hub mounts `/panel/desk.html` from the first day, before the entry page
    switches to the desk. Serving the desk page proves nothing about the front
    door, and the front door still answering the Studio's shell proves nothing
    about the desk, so both are read off the wire in one place and compared to
    the packaged bytes, and to each other -- a route table that pointed both at
    one file would satisfy each half alone.
    """
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    server_, base = start(root)
    panel = importlib.resources.files("conductor") / "panel"
    try:
        desk_status, desk_body, desk_headers = _status(base + "/panel/desk.html")
        entry_status, entry_body, _ = _status(base + "/")
    finally:
        server_.shutdown()
        server_.server_close()
    assert desk_status == 200 and entry_status == 200
    assert desk_body == (panel / "desk.html").read_bytes()
    assert desk_headers["Content-Type"] == "text/html; charset=utf-8"
    assert entry_body == (panel / "studio.html").read_bytes()
    assert entry_body != desk_body
    assert server_assets.ENTRY_PAGE == "studio.html"


def _module_level_literal(source: str, name: str):
    """The value `source` assigns to `name` at its top level, if it was written out.

    `ast.literal_eval` refuses anything computed -- a comprehension, a name, a
    call, a `**` splice -- so a value that comes back is a literal in the text.
    """
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == name
                for target in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} is not assigned at module level")


def test_a_registry_that_is_computed_is_not_read_as_a_literal():
    computed = 'DESK_ASSETS = {f"/panel/{n}": ("text/css", n) for n in ("a.css",)}'
    for source in (computed, "DESK_ASSETS = {**OTHER_ASSETS}",
                   'DESK_ASSETS = {"/panel/a.css": ("text/css", NAME)}'):
        with pytest.raises(ValueError):
            _module_level_literal(source, "DESK_ASSETS")
    with pytest.raises(AssertionError):
        _module_level_literal("OTHER = {}", "DESK_ASSETS")
    written = 'DESK_ASSETS = {"/panel/a.css": ("text/css", "a.css")}'
    assert _module_level_literal(written, "DESK_ASSETS") == {
        "/panel/a.css": ("text/css", "a.css")}


def test_the_desk_registry_is_a_literal_slice_of_the_panel_allowlist():
    """`DESK_ASSETS` is written out row by row, and each row is the allowlist's own.

    Literal is read off the source text of `server_assets.py`, not off the
    imported dict: a registry built by a comprehension imports to the same
    mapping, and only the text can say it was not written out.
    """
    source = Path(server_assets.__file__).read_text(encoding="utf-8")
    assert _module_level_literal(source, "DESK_ASSETS") == server_assets.DESK_ASSETS
    assert server_assets.DESK_ASSETS, "the desk registry is empty"
    for route, row in server_assets.DESK_ASSETS.items():
        assert server.PANEL_ASSETS.get(route) == row, route
        _, name = row
        assert route == f"/panel/{name}"
        assert name.startswith("desk") and not set(name) & set("/\\%?:*")
    registered = {name for _, name in server_assets.DESK_ASSETS.values()}
    assert server_assets.ENTRY_PAGE not in registered


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
