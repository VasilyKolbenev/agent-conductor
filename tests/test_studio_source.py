"""Source-level contract for the Workflow Studio's shell and its boundary.

The Studio is a third entry beside the panel and the Graph window, and it
arrives under the same discipline they are held to: every file under the line
cap, one layering that cannot grow a cycle, one module allowed to touch the
socket, no markup string parsed anywhere, and every closed vocabulary a copy of
the Python layer that owns it rather than a second opinion about it.

This is the change-detection half. It reads SOURCE TEXT and says nothing about
what a browser renders -- the rendered half is the browser gate, and no name in
this module may claim otherwise.

Two guards here are deliberately not spelled the way the graph window spells
them, and both deviations are written down where they are made rather than left
for a reader to notice:

* the graph window bans the bare word ``document`` in its boundary modules. The
  Studio's wire carries a key literally NAMED ``document`` -- a workflow draft
  is one -- so that guard would be a guard against the domain rather than
  against the DOM. What is banned here is every way the global is USED.
* ``studio.html`` names its assets with root-relative ``/panel/`` paths rather
  than document-relative ones, because it is served at ``/`` and a relative
  name would resolve outside the packaged directory entirely. The property the
  graph window gets from being relative -- no scheme, no host, this origin's
  own packaged files and nothing else -- is asserted here directly.
"""
from __future__ import annotations

import re
from pathlib import Path

from conductor.command import (
    contracts,
    control_loop,
    graph_template,
    preview,
    run_store,
    studio_contracts,
    workflow_draft,
)
from conductor.command.adapters import provider

from tests.test_graph_source import _code

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "src" / "conductor" / "panel"
HTML = PANEL / "studio.html"
STYLE = PANEL / "studio.css"
MODEL = PANEL / "studio-model.js"
#: Every module of the Studio, spelled out so a new one cannot arrive without
#: passing every guard below. The partition test underneath holds this list to
#: the packaged directory in both directions.
MODULES = ("studio.js", "studio-store.js", "studio-view.js", "studio-model.js",
           "studio-canvas.js", "studio-inspector.js", "studio-runs.js",
           "studio-people.js", "studio-runread.js", "studio-review.js",
           "studio-layout.js", "studio-edits.js",
           "studio-sections.js")
#: The one transport module: every `fetch(`, the one stream, the session token
#: and the screen router. `graph.js` holds the same position in its window, and
#: the sealed-API guard below pins this one the same way.
BOOT = "studio.js"
IMPORTS = r'from "(\./[a-z-]+\.js)";'

#: What each module MAY import -- a permission table, not an obligation. The
#: frontend contract's own column is spelled "May import", and a module that
#: has not yet needed one of its permitted neighbours is not a fault; a module
#: reaching for one it was never granted is.
PERMITTED_IMPORTS = {
    "studio-model.js": frozenset(),
    "studio-edits.js": frozenset({"./studio-model.js"}),
    #: Projections over one run read, and nothing else. It imports nothing for
    #: the reason `studio-model.js` imports nothing: a pure computation that
    #: reached for a neighbour would be able to answer from something other
    #: than the payload it was given.
    #: Where a step sits and which connection joins which. Pure arithmetic,
    #: importing nothing for the boundary's own reason.
    "studio-layout.js": frozenset(),
    "studio-runread.js": frozenset(),
    #: What a publish would change, over two documents a read already
    #: carries. It imports nothing for the same reason: a comparison that
    #: could reach a neighbour could answer from something other than the
    #: two documents it was handed.
    "studio-review.js": frozenset(),
    "studio-store.js": frozenset({"./studio-model.js", "./studio-runread.js",
                                  "./studio-review.js", "./studio-edits.js"}),
    "studio-view.js": frozenset({"./command-view.js", "./command-projection.js",
                                 "./studio-model.js"}),
    "studio-canvas.js": frozenset({"./command-view.js",
                                   "./command-projection.js",
                                   "./studio-model.js",
                                   "./studio-layout.js"}),
    "studio-sections.js": frozenset({"./command-view.js",
                                     "./command-projection.js",
                                     "./studio-model.js"}),
    "studio-inspector.js": frozenset({"./command-view.js",
                                      "./command-projection.js",
                                      "./studio-model.js",
                                      "./studio-sections.js"}),
    "studio-runs.js": frozenset({"./command-view.js",
                                 "./command-projection.js",
                                 "./studio-model.js"}),
    "studio-people.js": frozenset({"./command-view.js",
                                   "./command-projection.js",
                                   "./studio-model.js"}),
    "studio.js": frozenset(
        {f"./{name}" for name in MODULES if name != BOOT}
        | {"./command-view.js", "./command-projection.js"}),
}

#: Forbidden in every Studio file, markup included. Lowercased before the
#: search, so a case fold cannot walk one past.
SEALED = ("innerhtml", "outerhtml", "insertadjacenthtml", "localstorage",
          "sessionstorage", "document.cookie", "console.", "eval(",
          "new function(", "import(", "importscripts", "xmlhttprequest",
          "websocket", "webtransport", "rtcpeerconnection", "sendbeacon")
#: Forbidden everywhere but the one transport module.
TRANSPORT = ("fetch(", "eventsource", "navigator.")
#: Every way a module can reach the DOM or the global object. Banned outright
#: in the boundary module: it is handed a payload and answers with a value, and
#: a single one of these would make it something else.
DOM_FORMS = ("document.", "document[", "window.", "globalThis.", "self.",
             "getelementbyid", "queryselector", "createelement",
             "createtextnode", "addeventlistener", "appendchild",
             "textcontent", "classlist", "dispatchevent")

#: The shell ids the frontend contract froze. Three slices are coding against
#: them in parallel, so a rename here is a rename in three other files.
SHELL_IDS = ("studioShell", "studioHeader", "studioNav", "studioMain",
             "studioStatus", "navOverview", "navWorkflow", "navRuns",
             "navDecisions", "navAgents", "screenOverview", "screenWorkflow",
             "screenRuns", "screenDecisions", "screenAgents",
             "workflowToolbar", "workflowCanvas", "workflowEdges",
             "workflowNodes", "workflowInspector", "workflowDiagnostics")
#: The five screens, in the product's own order, each with the word its nav
#: button carries.
SCREENS = ("overview", "workflow", "runs", "decisions", "agents")
#: The seven words a screen container may stand in. The plain-language sentence
#: is what a person reads; this is what a test asserts, and neither has to
#: parse the other.
SCREEN_STATES = ("empty", "loading", "ready", "stale", "refused", "failed",
                 "disconnected")
LINE_CAP = 800


def _paths() -> tuple[Path, ...]:
    return (HTML, STYLE) + tuple(PANEL / name for name in MODULES)


def test_the_contract_modules_resolve_inside_this_tree():
    """A silent import fallback to another checkout would void every claim."""
    for module in (contracts, run_store, studio_contracts, workflow_draft,
                   provider):
        resolved = Path(module.__file__).resolve()
        assert ROOT in resolved.parents, f"resolved outside this tree: {resolved}"


def test_the_comment_stripper_keeps_the_studio_code_and_drops_its_prose():
    """Every guard below reads `_code`, so `_code` is proven on these files.

    A stripper that ate the file would turn each of those guards green while
    proving nothing. The graph suite proves it on the graph window's files;
    this proves the same function on the Studio's, because a boundary module
    written in a different comment style is a different input to it.
    """
    model = _code(MODEL)
    assert "export function projectWorkflows(payload) {" in model
    assert "// ── closed vocabularies" not in model
    assert len(model.splitlines()) > 200, "the stripper removed running code"


def test_every_studio_file_sits_in_the_panel_under_the_line_cap():
    for path in _paths():
        assert path.is_file() and path.parent == PANEL, path
        lines = len(path.read_text(encoding="utf-8").splitlines())
        assert lines <= LINE_CAP, f"{path.name} is {lines} lines"


def test_the_packaged_studio_modules_are_exactly_the_ones_this_module_guards():
    """A tenth module cannot arrive and be guarded by nothing.

    The list above is what every other test here iterates, so a file that is
    not on it passes no guard at all. Held in both directions: a module added
    to the package without a line here reds, and a line here naming no file
    reds too.
    """
    packaged = {entry.name for entry in PANEL.iterdir()
                if entry.name.startswith("studio") and entry.name.endswith(".js")}
    assert packaged == set(MODULES)


def test_the_studio_module_graph_is_acyclic_and_stays_inside_its_permissions():
    """The layering, spelled as import permissions so a cycle cannot hide.

    Acyclicity is COMPUTED from the edges that are really there rather than
    inferred from the table: a permission table alone would allow a cycle the
    moment two modules were both permitted each other.
    """
    edges: dict[str, set[str]] = {}
    for name in MODULES:
        found = set(re.findall(IMPORTS, (PANEL / name).read_text(encoding="utf-8")))
        assert found <= PERMITTED_IMPORTS[name], (
            name, sorted(found - PERMITTED_IMPORTS[name]))
        edges[name] = {target[2:] for target in found if target[2:] in MODULES}
    seen: set[str] = set()
    stack: set[str] = set()

    def walk(node: str) -> None:
        assert node not in stack, f"import cycle through {node}"
        if node in seen:
            return
        stack.add(node)
        for target in sorted(edges[node]):
            walk(target)
        stack.discard(node)
        seen.add(node)

    for name in MODULES:
        walk(name)


def test_the_boundary_module_reaches_no_dom_and_opens_no_socket():
    """`studio-model.js` is handed a payload and answers with a value.

    The bare word ``document`` is not what is banned, and cannot be: this
    window's wire carries a key called ``document`` -- a workflow draft is one
    -- so banning the word would be banning the domain. Every way the GLOBAL is
    used is banned instead, which is the relation the graph window's own guard
    was after.
    """
    source = _code(MODEL).lower()
    for forbidden in DOM_FORMS:
        assert forbidden not in source, forbidden
    for forbidden in TRANSPORT:
        assert forbidden not in source, forbidden
    assert re.findall(IMPORTS, MODEL.read_text(encoding="utf-8")) == []


def test_the_wire_door_opens_in_the_boot_module_and_nowhere_else():
    """Transport is one file, and the sealed list is forbidden in all of them.

    A module that is still a placeholder passes this trivially, which is the
    honest answer: an empty file opens no door. It stops being trivial the
    moment the module is written, and that is when this guard starts paying.
    """
    everything = (_code(*(PANEL / name for name in MODULES))
                  + "\n" + HTML.read_text(encoding="utf-8")
                  + "\n" + STYLE.read_text(encoding="utf-8")).lower()
    for forbidden in SEALED:
        assert forbidden not in everything, forbidden
    quiet = _code(*(PANEL / name for name in MODULES if name != BOOT)).lower()
    for forbidden in TRANSPORT:
        assert forbidden not in quiet, forbidden


def test_the_shell_names_one_script_and_only_this_origin_s_packaged_files():
    """One module, one stylesheet, no inline anything, no foreign origin.

    Every reference is root-relative under /panel/: no scheme, no `//`, no
    traversal, so the served document reaches this origin's own packaged
    directory and nothing else. It cannot be document-relative -- the shell is
    served at `/` -- and the substitute is asserted rather than assumed.

    The list is exact as well as constrained, so a third reference has to be
    argued for here. Two of them are what this document LOADS; the third is
    where it SENDS a person, and that one is on the list because the Protocol
    v1 surfaces -- the map, the findings, the feed, the handoffs -- have not
    moved into this application and a route to them that only a `<noscript>`
    block carried was not a route anybody could take.
    """
    html = HTML.read_text(encoding="utf-8")
    assert html.count("<script") == 1
    assert "<style" not in html
    assert not re.search(r"\son[a-z]+=", html), "an inline handler is a script"
    refs = re.findall(r'(?:href|src)="([^"]*)"', html)
    assert refs == ["/panel/studio.css", "/panel/studio.js", "/panel/index.html"]
    for ref in refs:
        assert ref.startswith("/panel/")
        assert "//" not in ref and ".." not in ref and ":" not in ref
    # And every one of them is a route this server actually serves, so the
    # shell cannot send a person at a 404.
    from conductor.server import PANEL_ASSETS
    assert set(refs) <= set(PANEL_ASSETS), sorted(set(refs) - set(PANEL_ASSETS))
    assert '<link rel="stylesheet" href="/panel/studio.css">' in html
    assert '<script src="/panel/studio.js" type="module"></script>' in html


def test_the_shell_carries_the_ids_and_the_states_the_contract_froze():
    """The DOM contract three other slices are coding against, verbatim."""
    html = HTML.read_text(encoding="utf-8")
    for name in SHELL_IDS:
        assert html.count(f'id="{name}"') == 1, name
    assert html.count('role="tablist"') == 1
    assert html.count('role="tab"') == len(SCREENS)
    assert html.count('role="tabpanel"') == len(SCREENS)
    assert html.count('role="status"') == 1
    assert html.count('aria-live="polite"') == 1
    # The nav's five words, in the product's order, each on its own button.
    assert re.findall(r'data-screen="([a-z]+)"', html) == list(SCREENS)
    # Every screen stands in one of the seven states, and says so in the
    # attribute rather than only in prose.
    states = re.findall(r'data-state="([a-z]+)"', html)
    assert len(states) == len(SCREENS)
    assert set(states) <= set(SCREEN_STATES)
    # Exactly one screen is showing: the other four are hidden by the platform's
    # own attribute, not by a class this stylesheet would have to be trusted for.
    assert html.count("hidden id=") + html.count(" hidden\n") == len(SCREENS) - 1


def _js_list(source: str, name: str) -> set[str]:
    body = re.search(rf"{name} = Object\.freeze\(\s*\[(.*?)\]\)", source, re.DOTALL)
    assert body, name
    found = re.findall(r'"([a-z_]+)"', body.group(1))
    assert len(found) == len(set(found)), f"{name} repeats a word"
    return set(found)


def _js_array(source: str, name: str) -> set[str]:
    """A plain `const NAME = ["a", "b"];`, for a list that is not a vocabulary.

    `_js_list` reads the frozen vocabularies, which are exported and shared. The
    key sets a projection judges against are neither: they are local to one
    check, and reading them here does not oblige the module to publish them.
    """
    body = re.search(rf"{name} = \[(.*?)\];", source, re.DOTALL)
    assert body, name
    found = re.findall(r'"([a-z_]+)"', body.group(1))
    assert len(found) == len(set(found)), f"{name} repeats a key"
    return set(found)


def test_the_boundary_vocabularies_are_copies_of_the_layers_that_own_them():
    """Every closed word this window draws is a word the runtime can mint.

    Each is read OUT of the Python layer that owns it rather than written down
    a second time here, so a vocabulary that grows on the durable side reds
    this test until the copy grows with it.
    """
    source = MODEL.read_text(encoding="utf-8")
    assert _js_list(source, "CONTROL_MODES") == studio_contracts.CONTROL_MODES
    assert _js_list(source, "PROVIDER_AVAILABILITY") == provider.AVAILABILITY_STATES
    assert _js_list(source, "PROVIDER_IMPLEMENTATION") == \
        provider.IMPLEMENTATION_STATES
    assert _js_list(source, "DIAGNOSTIC_CODES") == workflow_draft.DIAGNOSTIC_CODES
    assert _js_list(source, "RUN_STATES") == contracts._RUN_STATES
    assert _js_list(source, "RESULT_OUTCOMES") == contracts._RESULT_OUTCOMES
    assert _js_list(source, "RECORD_KINDS") == set(run_store._RECORDS)
    assert _js_list(source, "ENVELOPE_KEYS") == contracts.RunEnvelope._FIELDS
    # The two availability vocabularies answer different questions and share no
    # value, so neither can ever be read as the other. Asserted on the COPIES,
    # because that is where a reader of this window would confuse them.
    assert not (_js_list(source, "PROVIDER_AVAILABILITY")
                & _js_list(source, "PROVIDER_IMPLEMENTATION"))
    # `verification_failed` is an outcome and it is not a success: a process
    # that exits 0 has finished, which is not the same as verified.
    assert "verification_failed" in _js_list(source, "RESULT_OUTCOMES")


def test_the_frozen_configs_this_product_writes_are_ones_the_boundary_admits():
    """Every road that freezes a configuration, held to what the window reads.

    This is the class behind a real defect rather than a hypothetical. The
    boundary demanded a cycle of exactly ``{id}`` -- the shape
    `studio_contracts.RunInput.snapshot` writes -- while `conduct preview` and
    the control loop both freeze ``{id, phases}`` through the same
    `RunStore.create_run` into the same runs directory. So the first run most
    people ever have was listed by the Studio and could not be opened, and its
    timeline, positions, decisions and participants went blank together.

    Three writers, and until now no pin: the other vocabularies above are each
    read out of the one Python object that owns them, but a frozen config has no
    single owner to read, so nothing noticed the disagreement. The relation is
    therefore asserted over every writer this build has, and a fourth road that
    freezes some other shape reds here rather than in a browser.
    """
    source = MODEL.read_text(encoding="utf-8")
    admitted = _js_array(source, "CYCLE_KEYS")
    required = _js_array(source, "CYCLE_REQUIRED")
    assert required <= admitted, "a required cycle key the boundary does not admit"
    # The same relation ONE LEVEL UP, which was the residual this pin left open
    # when it was written: it held the cycle and said nothing about the document
    # holding it, so a road adding a third top-level key could still reach a
    # browser before a test. The frozen workflow reference is that road.
    top_admitted = _js_array(source, "CONFIG_KEYS")
    top_required = _js_array(source, "CONFIG_REQUIRED")
    assert top_required <= top_admitted, "a required config key not admitted"
    written = [
        ("conduct preview", preview.FROZEN_CONFIG),
        ("the control loop", control_loop.FROZEN_CONFIG),
        # The Studio's own road, built the way the route builds it, so the third
        # writer is exercised rather than described.
        ("the open-run route", studio_contracts.RunInput(
            run_id="run-pin", cycle_id="cycle-pin", mode="confirm",
            participants=(studio_contracts.Participant(
                instance_id="instance-pin", provider_id="provider-pin",
                model=None),),
            workflow_id=None, revision=None,
            binding=graph_template.RunBinding.from_dict({"assignments": {}}),
        ).snapshot()),
    ]
    for who, config in written:
        cycle = set(config["cycle"])
        assert required <= cycle, f"{who} freezes a cycle missing {required - cycle}"
        assert cycle <= admitted, f"{who} freezes a cycle the window refuses: {cycle}"
        top = set(config)
        assert top_required <= top, f"{who} freezes a config missing {top_required - top}"
        assert top <= top_admitted, f"{who} freezes a config the window refuses: {top}"



def test_the_instant_grammar_is_the_copy_the_graph_window_already_answers_for():
    """One UTC grammar, not a third dialect of it.

    `studio-model.js` imports nothing by contract, so it cannot borrow the
    graph window's function -- but it may not diverge from it either. The
    regex literal is held character for character to the one the browser suite
    already runs against tests/fixtures/utc_instant_parity_corpus.json.
    """
    pattern = r"const UTC_INSTANT =\n  (/\^.*?\$/);"
    mine = re.search(pattern, MODEL.read_text(encoding="utf-8"), re.DOTALL)
    theirs = re.search(
        pattern, (PANEL / "graph-payload.js").read_text(encoding="utf-8"),
        re.DOTALL)
    assert mine and theirs, "the instant grammar moved out of its declaration"
    assert mine.group(1) == theirs.group(1)


def test_the_boundary_admits_the_provenance_the_open_run_route_freezes():
    """Both sides of "optional", which one key set cannot state on its own.

    A boundary that DEMANDED `workflow` would refuse every run `conduct preview`
    and the control loop write. A boundary that REFUSED it would refuse every
    run the Studio opens against a workflow. The test beside this one holds the
    first direction over the two roads that omit the key; this holds the second
    over the one road that writes it, built the way the route builds it.
    """
    source = MODEL.read_text(encoding="utf-8")
    admitted = _js_array(source, "CONFIG_KEYS")
    frozen = set(studio_contracts.RunInput(
        run_id="run-pin", cycle_id="cycle-pin", mode="confirm",
        participants=(studio_contracts.Participant(
            instance_id="instance-pin", provider_id="provider-pin", model=None),),
        workflow_id="workflow-pin", revision=1,
        binding=graph_template.RunBinding.from_dict({"assignments": {}}),
    ).snapshot())

    assert "workflow" in frozen, "the open-run route froze no provenance"
    assert frozen <= admitted, f"a config the window refuses: {frozen}"


def test_the_boundary_refuses_rather_than_repairs_and_says_which_it_does():
    """The one rule that decides between dropping a row and refusing a payload.

    It is about the READER, not the row: a row a user must be able to REACH is
    never dropped, and a row that only decorates may be. The rule is stated in
    the module and the arms are pinned by count, so an arm cannot quietly
    change sides while a rendered test still passes for another reason.
    """
    source = _code(MODEL)
    # Navigation and the run read REFUSE: a workflow, a run or a journal row
    # this window cannot read takes the whole payload with it rather than
    # leaving a shorter truth on screen.
    # 80 before the frozen workflow reference landed, 84 after it, 85 with the
    # project name and 86 with the publish review's `unchanged`. Every one of
    # the seven is navigation: a config whose key set this window does not know,
    # a config missing one of the two keys every writer supplies, a run whose
    # workflow reference is there and will not read, the two halves of a run
    # ROW's provenance, a project name this build could not have written, and a
    # workflow read whose `unchanged` is not a boolean.
    assert source.count("return null;") == 86
    assert source.count("return false;") == 6
    # Decoration DROPS: the provider roster, the starter offers, and the one
    # duplicate-identity arm the controls answer shares with them.
    assert source.count("continue;") == 11
    # The draft's third answer, so "no draft" and "unreadable draft" can never
    # be the same value -- and now the workflow reference's third answer too,
    # for the same reason: a run that froze none and a run whose reference is
    # malformed must not arrive at this window as the same value.
    assert source.count("return undefined;") == 5
    text = MODEL.read_text(encoding="utf-8")
    assert "never dropped" in text and "is dropped" in text
