"""Source-level contract for the modules that WIRE the Studio together.

`test_studio_source.py` holds the whole package to one shape -- the line cap,
the layering, the sealed API list and the shell's frozen ids. This module holds
the integrator's own files to what only they can be held to:

* the reducer touches no DOM and no wire, so a rule about the SCREEN can never
  quietly become a rule about the browser it is running in;
* the view writes DOM and never reaches the network, so the one module that can
  write a durable record stays the one module a reader has to audit for it;
* the boot module is that one module, and it is pinned by COUNT rather than by
  presence: a second `fetch(` is a second door, and a door nobody counted is a
  door nobody reviewed;
* the mounting modules and the shell agree about ids, vocabularies and state
  words by construction rather than by three people remembering the same table.

Two guards here read source text and are change-detectors rather than proofs;
both say so in their own names. Everything else is a relation between two
artifacts, so it reds when either side moves.

The DOM ban is spelled the way `test_studio_source` spells it and for the same
reason: this window's wire carries a key literally named ``document`` -- a
workflow draft is one -- so what is banned is every way the GLOBAL is used, and
the reducer reads that key into a local rather than through a member chain that
would be indistinguishable from it.
"""
from __future__ import annotations

import re
from pathlib import Path

from tests.test_graph_source import _code

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "src" / "conductor" / "panel"
HTML = PANEL / "studio.html"
STORE = PANEL / "studio-store.js"
#: The edit vocabulary and its arms moved here when the reducer reached the line
#: cap. The three copies below are still held equal; what changed is which file
#: the reducer's copy lives in.
EDITS = PANEL / "studio-edits.js"
VIEW = PANEL / "studio-view.js"
#: The form that opens a run left the shell view when that file reached the line
#: cap. It is the same SURFACE -- a module handed a state and a handler table
#: that answers with DOM -- so every guard below that is about what the view may
#: touch reads both files rather than the one the code used to live in.
RUNFORM = PANEL / "studio-runform.js"
#: What the view builds a run form out of, and what the Overview's readiness
#: card asks the same question with. Both are read out of the module below by
#: name, so the split cannot quietly leave the view importing neither.
VIEW_SURFACE = (VIEW, RUNFORM)
BOOT = PANEL / "studio.js"
CANVAS = PANEL / "studio-canvas.js"
INSPECTOR = PANEL / "studio-inspector.js"
#: The inspector's controls and its copy of the edit vocabulary moved here when
#: that module reached the line cap. The three copies are still held equal.
SECTIONS = PANEL / "studio-sections.js"
#: The field primitives, split off the sections when THAT module reached the
#: cap. It carries `commit` -- the one writer of a `set-field` edit -- so it is
#: exactly the file a fourth copy of the vocabulary would appear in.
FIELDS = PANEL / "studio-fields.js"
#: Inputs and outputs, split off the sections before THAT module reached the cap
#: a second time. It builds controls like its neighbour, so it is exactly as
#: eligible to grow a fourth copy of the edit vocabulary, and is read below for
#: that reason.
ARTIFACTS = PANEL / "studio-artifacts.js"
RUNS = PANEL / "studio-runs.js"
PEOPLE = PANEL / "studio-people.js"
#: The files this slice owns. Every guard below iterates this tuple, so a new
#: file cannot join the integrator without passing all of them -- which is what
#: `studio-runform.js` did when the shell view reached the line cap.
MINE = (STORE, VIEW, RUNFORM, BOOT)
LINE_CAP = 800

#: The frontend contract's "May import" column for these rows, verbatim. It is
#: a PERMISSION table: a module that has not needed one of its neighbours is not
#: a fault, and one reaching for a neighbour it was never granted is.
PERMITTED = {
    "studio-store.js": frozenset({"./studio-model.js", "./studio-runread.js",
                                  "./studio-review.js", "./studio-edits.js"}),
    "studio-view.js": frozenset({"./command-view.js", "./command-projection.js",
                                 "./studio-model.js", "./studio-runform.js"}),
    #: The run form sits BELOW the view and never reaches back up: the view
    #: imports it, and a permission to import the view is what would let the
    #: pair close into a cycle, so it is not granted.
    "studio-runform.js": frozenset({"./command-view.js", "./studio-model.js"}),
    "studio.js": frozenset({
        "./command-view.js", "./command-projection.js", "./studio-model.js",
        "./studio-store.js", "./studio-view.js", "./studio-canvas.js",
        "./studio-inspector.js", "./studio-runs.js", "./studio-people.js"}),
}
IMPORTS = r'from "(\./[a-z-]+\.js)";'

#: Banned in all three, markup case-folded away first.
SEALED = ("innerhtml", "outerhtml", "insertadjacenthtml", "localstorage",
          "sessionstorage", "document.cookie", "console.", "eval(",
          "new function(", "import(", "importscripts", "xmlhttprequest",
          "websocket", "webtransport", "rtcpeerconnection", "sendbeacon")
#: Every way a module reaches the DOM or the global object.
DOM_FORMS = ("document.", "document[", "window.", "globalThis.", "self.",
             "getelementbyid", "queryselector", "createelement",
             "createtextnode", "addeventlistener", "appendchild",
             "textcontent", "classlist", "dispatchevent")
#: Banned everywhere but the boot module.
TRANSPORT = ("fetch(", "eventsource", "navigator.", "settimeout(",
             "setinterval(")
#: What the boot module carries, exactly. A door is counted, not merely
#: permitted: a second `fetch(` is a second door, and one nobody counted is one
#: nobody reviewed.
DOOR_COUNTS = (("fetch(", 2), ("new EventSource(", 1), ('method: "POST"', 1))
#: The four targets the one mutation door may name.
WRITE_TARGETS = frozenset({"draft", "revisions", "runs", "decisions"})
#: Ids `studio.html` declares that nothing mounts into BY NAME, and why. Each
#: is a container the stylesheet owns; a new id that mounts nothing must be
#: argued for here rather than left unnoticed. The five nav buttons are not on
#: this list: they are reached as a GROUP through the tablist, which is what
#: makes their number the markup's fact rather than a list kept in two places.
STRUCTURAL_IDS = frozenset({
    "studioShell",      # the outer frame, reached once by the boot module
    "studioHeader",     # a layout row; its three slots are what is written
    "studioMain",       # the screen well; the screens inside it are written
    "workflowCanvas",   # the pan/zoom viewport; the canvas draws in its layers
})
#: How the boot module reaches every nav button at once.
TABLIST_QUERY = 'byId("studioNav").querySelectorAll("[data-screen]")'
#: The seven words a screen container may stand in.
SCREEN_STATES = frozenset({"empty", "loading", "ready", "stale", "refused",
                           "failed", "disconnected"})
#: Where a token may be read, and the sinks it may never meet on one line.
TOKEN_NAMES = ("csrfToken", "csrf_token", "session.token")
TOKEN_SINKS = ("textContent", "setAttribute", "element(", "dataset",
               "localStorage", "sessionStorage", "cookie", "encodeURIComponent",
               "querySelector", "append(", "/command", "?", "location.")


def _expressions(source: str) -> str:
    """This code with string LITERALS blanked and interpolations kept.

    The DOM and transport guards are about a GLOBAL being used, and a global is
    used through an identifier -- never inside a quoted sentence. Reading the
    raw text made ``window.`` in "Live changes reach this window." indis-
    tinguishable from ``window.fetch``: the guard reds on an honest sentence and
    a rewrite that avoids the word buys nothing. So the sentences come out and
    the expressions stay, INCLUDING the ``${...}`` of a template literal, which
    is code that happens to sit inside quotes.
    """
    out: list[str] = []
    at, end = 0, len(source)
    while at < end:
        char = source[at]
        if char in "\"'":
            at = _past_quoted(source, at + 1, char, end) + 1
            out.append('""')
            continue
        if char == "`":
            at = _past_template(source, at + 1, end, out)
            out.append('""')
            continue
        out.append(char)
        at += 1
    return "".join(out)


def _past_quoted(source: str, at: int, quote: str, end: int) -> int:
    """The index of the closing quote, honouring one level of backslash escape."""
    while at < end and source[at] != quote:
        at += 2 if source[at] == "\\" else 1
    return at


def _past_template(source: str, at: int, end: int, out: list[str]) -> int:
    """The index past a template literal, appending each ``${...}`` it carries.

    Split out of `_expressions` so neither reader nests past the project's
    four-level limit -- and because "where does this literal end" and "what code
    is embedded in it" really are two questions.
    """
    while at < end:
        if source[at] == "\\":
            at += 2
            continue
        if source[at] == "$" and source[at + 1:at + 2] == "{":
            at += 2
            start, depth = at, 1
            while at < end and depth:
                depth += {"{": 1, "}": -1}.get(source[at], 0)
                at += 1
            out.append(source[start:at - 1])
            continue
        if source[at] == "`":
            return at + 1
        at += 1
    return at


def _ids(path: Path) -> set[str]:
    return set(re.findall(r'id="([A-Za-z0-9_-]+)"', path.read_text(encoding="utf-8")))


def _frozen_list(source: str, name: str) -> list[str]:
    body = re.search(rf"{name} = Object\.freeze\(\s*\[(.*?)\]\)", source, re.DOTALL)
    assert body, name
    return re.findall(r'"([a-z_-]+)"', body.group(1))


def _frozen_keys(source: str, name: str) -> set[str]:
    body = re.search(rf"{name} = Object\.freeze\(\{{(.*?)\n\}}\)", source, re.DOTALL)
    assert body, name
    return set(re.findall(r"^\s{2}([a-z_]+):", body.group(1), re.MULTILINE))


def test_the_comment_stripper_keeps_this_slice_s_code_and_drops_its_prose():
    """Every guard below reads `_code`, so `_code` is proven on THESE files.

    A stripper that ate one of them would turn each of those guards green while
    proving nothing -- and these three are written in a different comment style
    from the graph window's, so they are a different input to it.
    """
    boot = _code(BOOT)
    assert "const stream = new EventSource(\"/events\");" in boot
    assert "// This is the ONLY module of the Studio" not in boot
    assert len(boot.splitlines()) > 300, "the stripper removed running code"
    store = _code(STORE)
    assert "export function reduce(state, event) {" in store
    assert "//: The seven words a screen container may stand in" not in store


def test_the_expression_reader_keeps_the_code_and_drops_the_sentences():
    """The instrument every DOM and transport guard below reads, calibrated.

    An auditor that answered "" for every file would turn each of those guards
    green while proving nothing, and one that kept quoted prose would red on a
    sentence about a window. It is proven on a known case both ways here,
    including the one shape that matters: code inside a template literal is
    code, and it survives.
    """
    kept = _expressions('const a = "reach this window."; window.x = `${b.c}`;')
    assert "window.x" in kept and "b.c" in kept
    assert "reach this" not in kept
    view = _expressions(_code(VIEW))
    assert "export function mountShell(mounts, state, handlers) {" in view
    assert "Live changes reach this window." not in view
    assert len(view.splitlines()) == len(_code(VIEW).splitlines())


def test_every_file_the_integrator_owns_sits_in_the_panel_under_the_line_cap():
    for path in MINE:
        assert path.is_file() and path.parent == PANEL, path
        lines = len(path.read_text(encoding="utf-8").splitlines())
        assert lines <= LINE_CAP, f"{path.name} is {lines} lines"


def test_they_import_only_what_the_contract_grants_them_and_make_no_cycle():
    """The layering, spelled as permissions, with acyclicity COMPUTED.

    A permission table alone would allow a cycle the moment two modules were
    both permitted each other, so the edges that are really there are walked.
    """
    edges: dict[str, set[str]] = {}
    for path in MINE:
        found = set(re.findall(IMPORTS, path.read_text(encoding="utf-8")))
        assert found <= PERMITTED[path.name], (
            path.name, sorted(found - PERMITTED[path.name]))
        edges[path.name] = {target[2:] for target in found}
    seen: set[str] = set()
    stack: set[str] = set()

    def walk(node: str) -> None:
        assert node not in stack, f"import cycle through {node}"
        if node in seen or node not in edges:
            return
        stack.add(node)
        for target in sorted(edges[node]):
            walk(target)
        stack.discard(node)
        seen.add(node)

    for name in edges:
        walk(name)


def test_the_reducer_reaches_no_dom_and_no_wire():
    """`studio-store.js` is handed a payload and answers with a value.

    The bare word ``document`` is not what is banned and cannot be: a workflow
    draft IS one, and the reducer carries the key by that name. Every way the
    GLOBAL is used is banned instead, which is the relation this is after -- and
    it holds only because the reducer reads that key into a local rather than
    through a member chain no guard could tell from the global's.
    """
    source = _expressions(_code(STORE)).lower()
    for forbidden in DOM_FORMS:
        assert forbidden not in source, forbidden
    for forbidden in TRANSPORT:
        assert forbidden not in source, forbidden


def test_the_view_writes_dom_through_the_builder_and_never_reaches_the_wire():
    """The shell chrome builds nodes through `command-view.element` alone.

    Banning the DOM globals here is not decoration: a module that can reach
    `document` can reach `document.cookie`, and one that reaches the network
    can write a durable record from a screen nobody audits for it.

    Read over the whole view SURFACE rather than over one file. The claim is
    about what the view may touch, and the run form is the view -- so a guard
    that kept reading `studio-view.js` alone would have stopped covering the
    code the moment it moved next door, which is precisely when a split is at
    its most dangerous.
    """
    for path in VIEW_SURFACE:
        source = _expressions(_code(path)).lower()
        for forbidden in TRANSPORT:
            assert forbidden not in source, (path.name, forbidden)
        for forbidden in ("document.", "window.", "globalthis."):
            assert forbidden not in source, (path.name, forbidden)
        assert 'from "./command-view.js"' in path.read_text(encoding="utf-8")


def test_the_wire_door_is_the_boot_module_and_it_carries_exactly_these_doors():
    """One transport module, and its doors counted rather than merely allowed."""
    quiet = _expressions(_code(*(path for path in MINE if path != BOOT))).lower()
    for forbidden in TRANSPORT:
        assert forbidden not in quiet, forbidden
    boot = _code(BOOT)
    for door, count in DOOR_COUNTS:
        assert boot.count(door) == count, (door, boot.count(door))


def test_none_of_the_files_the_integrator_owns_reaches_a_sealed_api():
    everything = _code(*MINE).lower()
    for forbidden in SEALED:
        assert forbidden not in everything, forbidden


def test_every_id_the_boot_module_mounts_into_is_one_the_shell_declares():
    """Derived from `studio.html`, in both directions.

    Read out of the markup rather than copied here: a hand-written list would
    agree with a shell that had been renamed underneath it. The reverse
    direction is the one that pays -- an id the shell declares and nothing
    mounts into is dead markup, so it must be argued for in STRUCTURAL_IDS.
    """
    boot = _code(BOOT)
    declared = _ids(HTML)
    mounted = set(re.findall(r'byId\("([A-Za-z0-9_-]+)"\)', boot))
    assert mounted, "the boot module names no mount at all"
    assert mounted <= declared, sorted(mounted - declared)
    # The nav buttons are reached as a group, and the query that reaches them
    # is asserted rather than assumed -- otherwise "reached as a group" would
    # excuse five ids nothing touches.
    assert TABLIST_QUERY in boot
    nav = {name for name in declared if name.startswith("nav")}
    assert len(nav) == 5, sorted(nav)
    accounted = mounted | nav | STRUCTURAL_IDS
    assert declared == accounted, sorted(declared ^ accounted)


def test_the_boot_module_names_one_mount_per_screen_and_per_state_line():
    """Five screens, five state lines, five nav buttons -- and no sixth.

    The shell's own markup is the authority on how many there are, so a screen
    added to it without a mount here reds rather than rendering nothing.
    """
    declared = _ids(HTML)
    screens = {name for name in declared if name.startswith("screen")}
    states = {name for name in declared if name.startswith("state")
              and name != "studioStatus"}
    boot = _code(BOOT)
    assert len(screens) == 5 and len(states) == 5
    for name in screens | states:
        assert f'byId("{name}")' in boot, name
    html = HTML.read_text(encoding="utf-8")
    assert set(re.findall(r'data-state="([a-z]+)"', html)) <= SCREEN_STATES


def test_the_mutation_door_names_exactly_four_write_targets():
    """One door, one closed list, and every name on it a real path.

    The list is what makes a write to anything else unrepresentable rather
    than screened out afterwards, so it is held against the path table beside
    it: a target with no path could never have been reachable, and a path the
    list forgot is a door with no name.
    """
    boot = _code(BOOT)
    named = set(_frozen_list(boot, "WRITE_TARGETS"))
    assert named == WRITE_TARGETS, sorted(named ^ WRITE_TARGETS)
    for target in named:
        assert re.search(rf"^\s+{target}: \(", boot, re.MULTILINE), target
    assert boot.count("WRITE_TARGETS.includes(") == 1
    assert boot.count("async function submit(") == 1


def test_the_session_token_is_read_in_one_place_and_meets_no_sink():
    """The token goes into a request header and nowhere else.

    Not a claim about intent: every line of running code that mentions it is
    checked against the sinks that would put it on screen, in a URL or in
    storage. A line doing both is what this reds on, so writing the token into
    the status region -- or onto a query string -- cannot pass.
    """
    boot = _code(BOOT)
    lines = [line for line in boot.splitlines()
             if any(name in line for name in TOKEN_NAMES)]
    assert lines, "the boot module never handles a session token"
    for line in lines:
        for sink in TOKEN_SINKS:
            assert sink not in line, (sink, line.strip())
    assert boot.count('"X-Conduct-CSRF": session.token') == 1
    assert boot.count("let csrfToken") == 1
    # The shell's own markup carries no token-shaped attribute either, so a
    # future render cannot inherit one from the document it started in.
    assert "csrf" not in HTML.read_text(encoding="utf-8").lower()


def test_the_reducer_never_grants_write_readiness_by_writing_it_down():
    """Readiness is an ANSWER, so it is never a literal in the reducer.

    `writeReady: true` spelled anywhere would be this window deciding it may
    write without a read having said so -- the exact defect the graph window's
    reducer records beside its own declaration.
    """
    source = _code(STORE)
    assert "writeReady: true" not in source
    assert "writeReady: false" in source
    assert source.count("writeReady: event.ready === true") == 1


def test_the_three_edit_vocabularies_are_one_vocabulary():
    """The reducer, the canvas and the inspector name the same closed edits.

    The module table forbids the reducer importing either surface, so the three
    copies are held equal here instead. A word added to one and not the others
    is a control writing an edit nothing applies.
    """
    edits = _code(EDITS)
    types = _frozen_list(edits, "EDIT_TYPES")
    assert types == _frozen_list(_code(CANVAS), "EDIT_TYPES")
    assert types == _frozen_list(_code(SECTIONS), "EDIT_TYPES")
    fields = _frozen_list(edits, "EDIT_FIELDS")
    assert fields == _frozen_list(_code(SECTIONS), "EDIT_FIELDS")
    # And every edit word has an arm: the vocabulary IS the door.
    for word in types:
        assert re.search(rf'^\s+("{word}"|{word})[:,]', edits, re.MULTILINE), word
    # The reducer no longer declares either list, so the three copies cannot
    # quietly become four while this guard reads only three of them. The field
    # primitives are checked for the same reason and it is not hypothetical
    # there: `commit` lives in that file, and a word list beside the writer is
    # exactly where a fourth copy would look like it belonged.
    named = ((_code(STORE), "the reducer"), (_code(INSPECTOR), "the frame"),
             (_code(FIELDS), "the field primitives"),
             (_code(ARTIFACTS), "the inputs and outputs section"))
    for name in ("EDIT_TYPES", "EDIT_FIELDS"):
        for source, where in named:
            assert f"const {name}" not in source, (
                f"{name} is declared in {where} again; three copies, not four")


def test_every_screen_says_the_same_seven_words():
    """One state vocabulary across the shell, the runs screen and the people.

    Three modules render a banner and each carries its own sentences; what may
    not differ is WHICH words exist, because a browser test asserts the machine
    word and a person reads the sentence beside it.
    """
    for path in (VIEW, RUNS, PEOPLE):
        assert _frozen_keys(_code(path), "PHASE_SENTENCES") == SCREEN_STATES, path
    assert set(_frozen_list(_code(STORE), "PHASES")) == SCREEN_STATES


def test_the_reducer_and_the_shell_name_the_same_five_screens():
    """The nav's data-screen words are the reducer's own vocabulary."""
    html = HTML.read_text(encoding="utf-8")
    assert re.findall(r'data-screen="([a-z]+)"', html) \
        == _frozen_list(_code(STORE), "SCREENS")
