"""Source-level contract for the Graph window, now that it is on the wire.

These guards were written while the window had no wire at all, and they said
in as many words that the arrival of one would require revising them
deliberately rather than letting them drift. It arrived, and they were: what
used to be "this surface opens no network door" is now "the door is one file
and these are the only two it opens", and what used to be "the adapter names
no wire form" is now "it names exactly one, by a version the durable contract
actually mints".

What did not move is the shape of the argument. The whole surface is still
proven to parse no markup string, to keep the store, the adapter and the
default fixture free of both the DOM and the socket, to restate every closed
vocabulary as an exact copy of the layer that owns it, and to hold the
submitted plan against the durable contract's own list of words a plan may
never carry. The behavioural halves live in the browser suite
(``browser_tests/test_graph_wire.py`` for the wire, ``test_graph_boundary``
for the payload arms); this file is the change-detection half.
"""
from __future__ import annotations

import re
from dataclasses import fields
from pathlib import Path

from conductor.command import contracts, graph_definition, graph_projection

from tests.test_command_run_store import CONFIG

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "src" / "conductor" / "panel"
HTML = PANEL / "graph.html"
STORE = PANEL / "graph-store.js"
PAYLOAD = PANEL / "graph-payload.js"
VIEW = PANEL / "graph-view.js"
BOOT = PANEL / "graph.js"
ADAPTER = PANEL / "graph-adapter.js"
DEFAULT = PANEL / "graph-default.js"
STYLE = PANEL / "graph.css"
SCRIPTS = (PAYLOAD, STORE, VIEW, BOOT, ADAPTER, DEFAULT)
SOURCE = "\n".join(path.read_text(encoding="utf-8") for path in SCRIPTS)
IMPORTS = r'from "(\./[a-z-]+\.js)";'
#: Line comments must NOT be matched with DOTALL — `.` would cross newlines
#: and swallow the file. Block comments must be, because they span lines.
_LINE_COMMENT = re.compile(r"^[ \t]*//.*$", re.MULTILINE)
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def _code(*paths: Path) -> str:
    """These files without their prose.

    A guard that reads the whole file cannot tell a DOM call from a sentence
    about one: it reds on an honest comment and stays green on a call spelled
    a little differently. The relation these tests are after is about CODE,
    so the comments come out first and the guard reads what runs. The stripper
    is proven on this suite's own files below: it must leave the code that
    runs and remove the sentences about it, or every check built on it is a
    check of an empty string.
    """
    stripped = [_LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("",
                path.read_text(encoding="utf-8"))) for path in paths]
    return "\n".join(stripped)


def test_the_comment_stripper_keeps_the_code_and_drops_the_prose():
    """Every guard below reads `_code`, so `_code` itself is proven first.

    A stripper that ate the file would turn each of those guards green while
    proving nothing — the exact failure a `.*` crossing a newline produces.
    """
    boot = _code(BOOT)
    assert "window.conductGraph = Object.freeze({" in boot
    assert "// dispatch stays module-internal" not in boot
    assert len(boot.splitlines()) > 200, "the stripper removed running code"
    payload = _code(PAYLOAD)
    assert "export function projectPayload(payload) {" in payload
    assert "//: Where this graph came from" not in payload


def test_the_contract_module_resolves_inside_this_tree():
    """A silent import fallback to another checkout would void every claim."""
    module = Path(contracts.__file__).resolve()
    assert ROOT in module.parents, f"conductor resolved outside this tree: {module}"


def test_graph_window_files_sit_in_the_panel_under_the_line_cap():
    for path in (HTML, PAYLOAD, STORE, VIEW, BOOT, ADAPTER, DEFAULT, STYLE):
        assert path.is_file() and path.parent == PANEL
        assert len(path.read_text(encoding="utf-8").splitlines()) <= 800


def test_the_graph_module_graph_is_acyclic_and_the_boundary_stays_pure():
    """The layering, spelled as import lists so a cycle cannot hide in one.

    The boundary was split out of the reducer when that file reached its cap,
    and the seam they always had is now a file edge: the payload module knows
    the vocabularies and the projections, the store knows the STATE, and the
    store depends on the boundary while the boundary knows nothing of it.
    """
    assert re.findall(IMPORTS, PAYLOAD.read_text(encoding="utf-8")) == [
        "./command-projection.js"]
    assert sorted(re.findall(IMPORTS, STORE.read_text(encoding="utf-8"))) == [
        "./command-projection.js", "./graph-payload.js"]
    assert sorted(re.findall(IMPORTS, VIEW.read_text(encoding="utf-8"))) == [
        "./command-view.js", "./graph-payload.js"]
    assert sorted(re.findall(IMPORTS, BOOT.read_text(encoding="utf-8"))) == [
        "./command-projection.js", "./graph-adapter.js", "./graph-default.js",
        "./graph-payload.js", "./graph-store.js", "./graph-view.js"]
    # The adapter imports nothing: it is the outermost shell of the boundary
    # and may depend on no inner layer, so no mapping can smuggle a projection.
    # The default fixture imports nothing either: it is data with a name.
    assert re.findall(IMPORTS, ADAPTER.read_text(encoding="utf-8")) == []
    assert re.findall(IMPORTS, DEFAULT.read_text(encoding="utf-8")) == []
    for pure in (PAYLOAD, STORE, ADAPTER, DEFAULT):
        source = _code(pure)
        assert "document" not in source
        assert "window." not in source
        assert "getElementById" not in source


def test_the_default_fixture_ships_an_empty_registry():
    """Vendor rows arrive from the one registry as data, never as a second
    copy inside the default — the rendered half lives in the boot test."""
    assert "registry: [],\n" in DEFAULT.read_text(encoding="utf-8")


def test_the_adapter_names_the_internal_schema_and_the_one_wire_form_it_reads():
    """The panel-internal shape is not the wire contract, and says so.

    The wire has since landed, so the adapter now DOES name a wire form —
    exactly one, announced by version. The pin that used to prove no mapping
    existed is replaced by the pin that proves the mapping speaks a version
    the durable contract actually mints, rather than a guess at one.
    """
    source = ADAPTER.read_text(encoding="utf-8")
    assert "NOT the wire" in source
    assert "INTERNAL_SCHEMA = 1" in source
    schema = next(field for field in fields(graph_definition.GraphDefinition)
                  if field.name == "schema_version")
    assert f"WIRE_SCHEMA = {schema.default};" in source
    assert "definition.schema_version !== WIRE_SCHEMA" in source


def test_the_adapter_is_the_only_module_that_knows_a_wire_spelling():
    """One boundary, and it is checkable by grep because it is one file.

    Every name below belongs to a document the runtime side froze. If one
    appears in the store, the view, the default or the boot file, the mapping
    has leaked out of the seam it was promised to stay inside — and the layer
    that learned it would then have to be revised whenever the wire moves.
    """
    inside, outside = _code(ADAPTER), _code(PAYLOAD, STORE, VIEW, BOOT, DEFAULT)
    for spelling in ("definition_digest", "from_node", "to_node",
                     "schema_version", "graph_id"):
        assert spelling in inside, spelling
        assert spelling not in outside, spelling


def test_the_submitted_plan_is_screened_against_the_runtime_words_themselves():
    """The plan this window offers a run is screened by the REAL list.

    A plan that reaches the journal can never be edited, so the screen sits
    in front of the door rather than in a test describing it. The copy here
    is held to `graph_definition.RUNTIME_ONLY_FIELDS` value for value, and to
    the same payload exemption production applies, so the screen cannot fall
    behind the contract it is screening for.
    """
    source = ADAPTER.read_text(encoding="utf-8")
    body = re.search(r"RUNTIME_ONLY_FIELDS = Object\.freeze\(\s*\[(.*?)\]\)",
                     source, re.DOTALL)
    assert body, "the adapter states no runtime-word list"
    assert set(re.findall(r'"([a-z_]+)"', body.group(1))) == \
        set(graph_definition.RUNTIME_ONLY_FIELDS)
    assert f'EXEMPT_FIELD = "{graph_definition.EXEMPT_FIELD}"' in source
    # And the screen is WIRED: the body is read back before it is returned,
    # so a plan carrying a run's word is refused rather than described.
    assert "return carriesRuntimeWord(body) ? null : body;" in source


def test_the_wire_door_opens_in_the_boot_file_and_nowhere_else():
    """Reading and writing are transport, and transport is one file.

    The store, the adapter, the default fixture and the markup stay wire-free
    and DOM-free: a payload's SHAPE is the adapter's business and a socket is
    the boot file's. Everything else on this list is forbidden everywhere,
    for the reason it always was — no markup string is ever parsed here, and
    no facts are kept anywhere a contract did not validate them.
    """
    html = HTML.read_text(encoding="utf-8")
    sealed = (_code(PAYLOAD, STORE, VIEW, ADAPTER, DEFAULT) + "\n" + html).lower()
    for forbidden in ("fetch(", "eventsource", "xmlhttprequest", "websocket",
                      "webtransport", "rtcpeerconnection", "sendbeacon"):
        assert forbidden not in sealed, forbidden
    lowered = (_code(*SCRIPTS) + "\n" + html).lower()
    for forbidden in ("xmlhttprequest", "websocket", "webtransport",
                      "rtcpeerconnection", "sendbeacon",
                      "import(", "importscripts", "navigator.",
                      "innerhtml", "outerhtml", "insertadjacenthtml",
                      "localstorage", "sessionstorage", "document.cookie",
                      "settimeout", "setinterval", "console."):
        assert forbidden not in lowered, forbidden
    # The two doors the boot file DOES open, named so that a third cannot
    # arrive unremarked: one read/write door and one stream.
    boot = _code(BOOT)
    assert boot.count("fetch(") == 3
    assert boot.count("new EventSource(") == 1
    assert "from '" not in SOURCE  # imports stay double-quoted and countable
    assert '<link rel="stylesheet" href="graph.css">' in html
    assert '<script src="graph.js" type="module"></script>' in html
    assert html.count("<script") == 1
    # Every asset this entry names is RELATIVE. An absolute one would bind the
    # packaged document to one mount point, and the served copy and the
    # packaged copy would stop being the same file.
    assert re.findall(r'(?:href|src)="([^"]*)"', html) == [
        "graph.css", "graph.js"]


def test_the_one_mutation_target_is_the_graph_route_and_it_is_a_literal():
    """One route this window may POST to, visible at one call site.

    The Cockpit's Confirm and propose doors are not weakened by this window
    because this window has no path to them: `/proposals` and `/actions`
    appear nowhere in it, and the only method it ever sends is the one below.
    """
    boot = BOOT.read_text(encoding="utf-8")
    assert boot.count('method: "POST"') == 1
    assert '`/command/runs/${encodeURIComponent(runId)}/graph`' in boot
    for forbidden in ("/proposals", "/actions", "/decisions", '"PUT"',
                      '"DELETE"', '"PATCH"'):
        assert forbidden not in boot, forbidden


def _tokens(css: str) -> list[dict[str, str]]:
    """Every `--name:value` map, one per `:root{...}` block, in order."""
    blocks = re.findall(r":root\{(.*?)\}", css, re.DOTALL)
    return [dict(re.findall(r"(--[a-z0-9-]+):([^;}]+)", block))
            for block in blocks]


def test_the_graph_palette_is_a_value_for_value_copy_of_the_december_palette():
    panel_blocks = _tokens((PANEL / "index.html").read_text("utf-8"))
    graph_blocks = _tokens(STYLE.read_text("utf-8"))
    # Exactly one dark and one light block each — a third override block
    # would drift the effective palette while the first-two check stays green.
    assert len(panel_blocks) == 2 and len(graph_blocks) == 2
    panel_dark, panel_light = panel_blocks
    graph_dark, graph_light = graph_blocks
    required = {"--ground", "--panel", "--sunk", "--line", "--ink", "--muted",
                "--faint", "--accent", "--pass", "--wait", "--fail"}
    assert required <= set(graph_dark) and required <= set(graph_light)
    for name, value in graph_dark.items():
        assert value == panel_dark[name], name
    for name, value in graph_light.items():
        assert value == panel_light[name], name


def _js_ordered(source: str, name: str) -> list[str]:
    body = re.search(
        rf"{name} = Object\.freeze\(\s*\[(.*?)\]\)", source, re.DOTALL)
    assert body, name
    return re.findall(r'"([a-z_]+)"', body.group(1))


def _js_list(source: str, name: str) -> set[str]:
    return set(_js_ordered(source, name))


def test_the_boundary_vocabularies_are_copies_of_the_layers_that_own_them():
    store = PAYLOAD.read_text(encoding="utf-8")
    projection = (PANEL / "command-projection.js").read_text(encoding="utf-8")
    assert _js_list(store, "HEALTH_STATES") == contracts.HEALTH_STATES
    assert _js_list(store, "VERIFICATION_STATES") == contracts._VERIFICATION_STATES
    # Two layers own this one vocabulary and both are copied whole: the run
    # projection's position words (idle … running … observed) and the result
    # outcomes a receipt may carry. `observed` is a position and `succeeded`
    # is an outcome, and the window keeps both words so it never has to turn
    # one into the other.
    assert _js_list(store, "NODE_PHASES") == (
        set(graph_projection.NODE_PHASES) | contracts._RESULT_OUTCOMES)
    assert "observed" in _js_list(store, "NODE_PHASES")
    decisions = dict(re.findall(r'(\w+): "(\w+)",\n', re.search(
        r"DECISION_ACTIONS = Object\.freeze\(\{(.*?)\}\)", store,
        re.DOTALL).group(1)))
    assert set(decisions) == contracts._DECISION_ACTIONS
    projected = dict(re.findall(r'(\w+): "(\w+)",\n', re.search(
        r"DECISION_STATES = Object\.freeze\(\{(.*?)\}\)", projection,
        re.DOTALL).group(1)))
    assert decisions == projected
    capability_keys = set(re.findall(
        r"^  (\w+): Object\.freeze\(\[", re.search(
            r"CAPABILITY_FIELDS = Object\.freeze\(\{(.*?)\n\}\);", projection,
            re.DOTALL).group(1), re.MULTILINE))
    assert _js_list(store, "CAPABILITY_NAMES") == capability_keys
    kinds = re.search(r'\["kinds", "enum-list", \[(.*?)\]\]', projection).group(1)
    assert _js_list(store, "EVIDENCE_KINDS") == set(re.findall(r'"(\w+)"', kinds))
    # `pending` is this window's word for the projection's `idle`, and
    # `unknown` is the projection's own refusal to choose between two
    # standing receipts. Neither is a decision, and neither may be dropped:
    # a gate the journal cannot answer for must still have a word to draw.
    assert _js_list(store, "GATE_STATES") == (
        {"pending", "unknown"} | set(decisions.values()))
    # Harness-level availability: the December Command's own three words, and
    # no fourth invented beside them.
    assert _js_list(store, "AVAILABILITY_STATES") == {
        "available", "experimental", "unavailable"}
    # The step model: task, gate, and the explicit bounded loop — the only
    # sanctioned shape of a cycle. Resources are the Command's six words.
    assert _js_list(store, "NODE_KINDS") == {"task", "gate", "loop"}
    assert _js_list(store, "RESOURCE_KINDS") == {
        "model", "tool", "skill", "session", "sandbox", "filesystem"}
    # The five semantic stages, Dalio's five steps in the Command's fixing:
    # a stage is not a phase, no sixth word may appear beside these, and the
    # ORDER is the vocabulary's fact — the view numbers stages by index.
    assert _js_ordered(store, "STAGE_NAMES") == [
        "goal", "identify", "diagnose", "design", "do"]


def test_local_only_actions_say_so_where_they_land():
    """The decision and composition arms carry their honesty in the notice."""
    store = STORE.read_text(encoding="utf-8")
    assert store.count("Nothing was executed") == 2
    assert store.count("Composition refused") == 2
    assert '"window-only"' in store
    # The load notice and the run-facts suffix carry the same honesty for
    # the boot path; the rendered halves live in the browser boot test.
    assert "Nothing here reaches a server" in store
    assert "· fixture" in BOOT.read_text(encoding="utf-8")
    view = VIEW.read_text(encoding="utf-8")
    assert "Nothing is executed or sent" in view


def test_the_docs_field_is_https_gated_at_both_boundary_and_anchor():
    """The one registry field that becomes an href keeps the index.html gate."""
    store = PAYLOAD.read_text(encoding="utf-8")
    assert 'row.docs.startsWith("https://")' in store
    view = VIEW.read_text(encoding="utf-8")
    assert 'row.docs.startsWith("https://")' in view
    anchor = re.search(r'element\("a", \{(.*?)\}\)', view, re.DOTALL).group(1)
    assert 'rel: "noreferrer noopener"' in anchor
    assert 'target: "_blank"' in anchor


def test_every_refusal_arm_of_the_store_is_pinned_by_count():
    """Deleting any boundary arm must red this file, not only the browser gate.

    The behavioural half lives in browser_tests/test_graph_rendered.py
    (one-fault payloads); this is the change-detection half, so an arm cannot
    vanish while the many-fault payload still refuses for another reason.
    """
    store = PAYLOAD.read_text(encoding="utf-8")
    assert store.count("return null;") == 49
    assert store.count("return false;") == 27
    # The adapter is a boundary too, and its refusals come in two spellings
    # because it decides in two places: `pairState` answers with a word about
    # the pair, and the walk over the nodes answers with the refusal value.
    adapter = ADAPTER.read_text(encoding="utf-8")
    assert adapter.count("return refused();") == 8
    # The seventh arm rejects a mismatched bounded execution contract.
    assert adapter.count("return GRAPH_REFUSED;") == 7
    # The level screens: each answers false for a key its level has no
    # mapping for, so nothing is ever dropped on the way in.
    assert adapter.count("return false;") == 7
    # The resource cap shares its return with the array check, so the arm is
    # pinned by its own spelling beside the behavioural over-limit case.
    assert "const RESOURCE_LIMIT = 16;" in store
    assert "rows.length > RESOURCE_LIMIT" in store
    # Two projections refuse by DROPPING a row rather than by refusing the
    # payload -- the registry's, and the deployment's -- so their arms are
    # pinned by their own spelling: deleting one reds this line, not only the
    # rendered drop-row test in the browser suite. Seven arms belong to the
    # registry and six to the deployment, and a row this window drops is a row
    # whose harness draws neutrally or whose instance shows no deployment,
    # which is a true statement about how much was readable.
    assert store.count("continue;") == 13


def test_the_shipped_default_binds_only_instances_a_run_can_declare():
    """A default a Human cannot save is a default that does not work.

    "Start from the default" builds a local draft and the Save button sends it
    to the immutable graph route, which holds every node's `instance_id`
    against the run's FROZEN CONFIGURATION. An instance no configuration
    declares is answered `service_refused` and nothing is written -- so the
    fixture's instance ids are a product constraint, not decoration.

    This was learned rather than reasoned: a correction that gave each step its
    own instance named two the canonical configuration does not declare, and
    four wire tests went red on the save. They are the end-to-end proof and
    they run in the browser gate; this is the two-second one, so the next
    person to edit the fixture finds out before a gate does.

    The deployment rows are held to the same list from the other side, so a
    fixture cannot describe a deployment for an instance no step names.
    """
    declared = {row["id"] for row in CONFIG["instances"]}
    document = DEFAULT.read_text(encoding="utf-8")
    bound = set(re.findall(r'binding: \{instance_id: "([^"]+)"', document))
    described = set(re.findall(r'\{instance_id: "([^"]+)", adapter_id:', document))

    assert bound, "the default binds no instance at all, so this proves nothing"
    assert bound <= declared, sorted(bound - declared)
    assert described == bound, sorted(described ^ bound)
