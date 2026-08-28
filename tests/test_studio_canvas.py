"""Source-level contract for the Studio canvas and the node inspector.

The house model, restated: the fast suite reads SOURCE. Whether a step is drawn
where the layout put it, whether a drag lands, whether a disabled control looks
disabled -- those are rendered claims and they live in ``browser_tests/``. What
this module proves is the shape the two files have to keep for those claims to
be worth making at all:

- both are pure DOM writers: the sealed API list, the module table's import
  lists, and one ``mount.replaceChildren`` per mount so a second render of the
  same state cannot leave the first one's nodes behind;
- every closed vocabulary they consume equals the PYTHON layer that owns it,
  read from that layer rather than typed twice into this file. The module table
  forbids the inspector importing the canvas, so the two carry duplicate copies
  on purpose -- and the duplicates are held to each other here as well;
- the workflow/run partition: nothing either surface can write names a
  provider, a model, an adapter or an instance. That is
  ``graph_template.DEPLOYMENT_ONLY_FIELDS`` read from the contract, not a list
  spelled a second time;
- the completeness rule: every field with no durable home says so on screen in
  one voice, and the set of those fields is pinned so one going quiet is a red.

The module is named ``test_studio_*`` deliberately. ``tests/test_panel_smoke.py``
machine-checks that ``index.html``'s file-size waiver names exactly the set of
``test_panel_*.py`` modules in the tree, so a ``test_panel_``-prefixed name here
would red a guard that has nothing to do with this surface.
"""
from __future__ import annotations

import re
from pathlib import Path

from conductor.command import contract_values, graph_definition, graph_projection
from conductor.command.adapters import base as adapter_base
from conductor.command.adapters import provider as provider_module
from conductor.command.graph_template import DEPLOYMENT_ONLY_FIELDS, TemplateNode
from conductor.command.providers import PROVIDER_CATALOG

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "src" / "conductor" / "panel"
CANVAS = PANEL / "studio-canvas.js"
INSPECTOR = PANEL / "studio-inspector.js"
STUDIO_FILES = (CANVAS, INSPECTOR)
IMPORTS = r'from "(\./[a-z-]+\.js)";'
_LINE_COMMENT = re.compile(r"^[ \t]*//.*$", re.MULTILINE)
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def _code(*paths: Path) -> str:
    """These files without their prose.

    A guard that reads the whole file cannot tell a DOM call from a sentence
    about one. `tests/test_graph_source.py` proves the same stripper on the
    graph window's files; it is proven again below on these, because a
    stripper that ate the file would turn every check that follows green.
    """
    stripped = [_LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("",
                path.read_text(encoding="utf-8"))) for path in paths]
    return "\n".join(stripped)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _js_ordered(source: str, name: str) -> list[str]:
    """One frozen array literal, in the order it is written."""
    body = re.search(rf"{name} = Object\.freeze\(\s*\[(.*?)\]\)", source, re.DOTALL)
    assert body, name
    return re.findall(r'"([a-z0-9_-]+)"', body.group(1))


def _js_function(source: str, name: str) -> str:
    """One exported top-level function body, from its brace to column zero."""
    body = re.search(rf"export function {name}\(state\) \{{\n(.*?)\n\}}\n",
                     source, re.DOTALL)
    assert body, name
    return body.group(1)


def _attribute_blocks(source: str, tag: str) -> list[str]:
    """Every attribute object handed to ``element("<tag>", {...})``.

    Brace-counted rather than matched with a lazy `.*?`: these objects carry
    template literals, and `${key}` closes a brace a lazy match would stop at,
    which would let a control with no `data-focus` slip past this guard by the
    accident of having an interpolated attribute earlier in the object.
    """
    found = []
    for match in re.finditer(rf'element\("{tag}",\s*\{{', source):
        depth, at = 1, match.end()
        while depth and at < len(source):
            depth += {"{": 1, "}": -1}.get(source[at], 0)
            at += 1
        assert depth == 0, f"unbalanced attribute object for {tag}"
        found.append(source[match.end():at - 1])
    return found


def test_the_comment_stripper_keeps_the_code_and_drops_the_prose():
    """Every guard below reads `_code`, so `_code` itself is proven first."""
    canvas = _code(CANVAS)
    assert "export function mountCanvas(mount, svg, state, handlers) {" in canvas
    assert "// The one thing this file refuses to do" not in canvas
    assert len(canvas.splitlines()) > 300, "the stripper removed running code"
    inspector = _code(INSPECTOR)
    assert "export function mountInspector(mount, state, handlers) {" in inspector
    assert "//: The six sections, in the one order" not in inspector


def test_the_contract_modules_resolve_inside_this_tree():
    """A silent import fallback to another checkout would void every claim."""
    module = Path(graph_definition.__file__).resolve()
    assert ROOT in module.parents, f"conductor resolved outside this tree: {module}"


def test_both_studio_files_sit_in_the_panel_under_the_line_cap():
    for path in STUDIO_FILES:
        assert path.is_file() and path.parent == PANEL
        assert len(_text(path).splitlines()) <= 800, path.name


#: What each of these two files may reach for, in the order it spells them. The
#: canvas gained the model when it crossed the line cap and its pure layout half
#: moved next door; the inspector has not needed it. Both remain leaves in the
#: sense that matters: neither can reach the other, and neither can reach a
#: module that reaches back.
_ALLOWED_IMPORTS = {
    "studio-canvas.js": ["./command-view.js", "./studio-model.js"],
    "studio-inspector.js": ["./command-view.js"],
}


def test_each_module_imports_exactly_what_the_module_table_allows_it():
    """The decomposition, spelled as import lists so a cycle cannot hide.

    The inspector may not reach the canvas, which is why the two carry duplicate
    vocabulary copies and why the next test holds them equal. Neither may reach
    a module that could reach back: `studio-model.js` imports nothing at all,
    which is what makes it a safe neighbour for the canvas rather than a step
    toward a cycle.
    """
    for path in STUDIO_FILES:
        assert re.findall(IMPORTS, _text(path)) == _ALLOWED_IMPORTS[path.name], path.name
    assert "from './" not in _code(*STUDIO_FILES)


def test_the_two_files_carry_the_same_copy_of_every_shared_vocabulary():
    canvas, inspector = _code(CANVAS), _code(INSPECTOR)
    for name in ("NODE_KINDS", "STAGE_NAMES", "EDIT_TYPES"):
        assert _js_ordered(canvas, name) == _js_ordered(inspector, name), name
    # Two surfaces reading two different documents at once is the confusion
    # this screen exists to refuse, so the READING is duplicated verbatim.
    assert _js_function(canvas, "canvasDocument") == _js_function(
        inspector, "inspectedDocument")


def test_every_closed_vocabulary_equals_the_python_layer_that_owns_it():
    """Read off the owning module, never typed a second time into this file."""
    canvas, inspector = _code(CANVAS), _code(INSPECTOR)
    assert set(_js_ordered(canvas, "NODE_KINDS")) == graph_definition.NODE_KINDS
    assert set(_js_ordered(inspector, "RESOURCE_KINDS")) == (
        graph_definition.RESOURCE_KINDS)
    # The ORDER is the vocabulary's own fact here: both files number a stage by
    # its index, so re-spelling the tuple re-numbers the product.
    for source in (canvas, inspector):
        assert _js_ordered(source, "STAGE_NAMES") == list(
            graph_definition.DALIO_STAGES)
    assert _js_ordered(canvas, "NODE_PHASES") == list(graph_projection.NODE_PHASES)
    assert _js_ordered(canvas, "GATE_STATES") == list(graph_projection.GATE_STATES)
    bound = re.search(r"LOOP_BOUND = Object\.freeze\(\{min: (\d+), max: (\d+)\}\)",
                      inspector)
    assert bound and (int(bound.group(1)), int(bound.group(2))) == (
        graph_definition.MIN_LOOP_BOUND, graph_definition.MAX_LOOP_BOUND)
    resources = re.search(r"MAX_RESOURCES = (\d+);", inspector)
    assert resources and int(resources.group(1)) == graph_definition.MAX_RESOURCES
    # The id grammar, held two-sidedly: the JS anchors are `^`/`$` and Python's
    # is `\Z`, and everything between them must be the same characters.
    grammar = re.search(r"ID_PATTERN = /\^(.*)\$/;", inspector)
    assert grammar and grammar.group(1) + r"\Z" == contract_values._ID_RE.pattern


def test_a_review_step_is_told_apart_by_a_capability_this_build_declares():
    """`review` is a word an adapter contract owns, not a label invented here."""
    canvas = _code(CANVAS)
    named = re.search(r'REVIEW_CAPABILITY = "([a-z]+)";', canvas)
    assert named and named.group(1) in adapter_base.CAPABILITIES


def test_every_step_kind_is_told_apart_by_a_shape_and_a_word_not_a_colour():
    """A glyph is a shape carried in text, so it survives a missing stylesheet.

    Both halves must be present and both must be distinct: two kinds sharing a
    glyph, or sharing a label, would leave the difference to `studio.css` alone
    -- which is the colour-only failure the panel's own style suite refuses.
    """
    canvas = _code(CANVAS)
    marks = dict(re.findall(
        r'(\w+): Object\.freeze\(\{glyph: "(.)", label: "[^"]+"\}\)', canvas))
    labels = dict(re.findall(
        r'(\w+): Object\.freeze\(\{glyph: ".", label: "([^"]+)"\}\)', canvas))
    assert set(marks) == graph_definition.NODE_KINDS
    assert len(set(marks.values())) == len(marks)
    assert len(set(labels.values())) == len(labels)
    review = re.search(r'REVIEW_MARK = Object\.freeze\(\{\s*glyph: "(.)", '
                       r'label: "([^"]+)"\}\)', canvas)
    assert review and review.group(1) not in marks.values()
    assert review.group(2) not in labels.values()


def test_no_workflow_edit_can_name_a_deployment(  # noqa: D103 - stated below
):
    """A workflow names roles. Every deployment word is refused by vocabulary.

    ``DEPLOYMENT_ONLY_FIELDS`` is read from the template contract rather than
    re-listed, so a word ADDED there closes this door here on the same day.
    Two directions are checked: no editable field is spelled one of them, and
    no such word appears as a literal anywhere either file can write.
    """
    inspector = _code(INSPECTOR)
    fields = set(_js_ordered(inspector, "EDIT_FIELDS"))
    assert not fields & DEPLOYMENT_ONLY_FIELDS
    # Every editable field is one a template step could carry, or one of the
    # two flat spellings of the loop's own pair.
    assert fields <= (set(TemplateNode._FIELDS) | {"loop_bound", "loop_back_to"})
    writable = re.findall(r'commit\(form, "([a-z_]+)"', inspector)
    assert set(writable) <= fields
    for word in DEPLOYMENT_ONLY_FIELDS:
        assert f'"{word}"' not in _code(*STUDIO_FILES), word


def test_capability_choices_come_from_the_payload_and_never_from_a_provider_id():
    """No provider-name switch, and no capability list written down here.

    The roster is the source: `capabilityRoster` reads `state.providers` and
    the PROVEN `controls` each row declares. So a capability name appearing as
    a literal in the inspector would be a second, silent roster.
    """
    inspector, canvas = _code(INSPECTOR), _code(CANVAS)
    literals = set(re.findall(r'"([a-z_-]+)"', inspector))
    assert not literals & adapter_base.CAPABILITIES
    # The canvas names exactly one, and only to tell a review step apart.
    assert (set(re.findall(r'"([a-z_-]+)"', canvas)) & adapter_base.CAPABILITIES
            ) == {"review"}
    for source in (inspector, canvas):
        assert "switch (" not in source and "switch(" not in source
    for provider_id in PROVIDER_CATALOG:
        assert provider_id not in _code(*STUDIO_FILES), provider_id
    assert "state.providers" in inspector
    assert set(re.findall(r"row\.(availability|implementation)", inspector)) == {
        "availability", "implementation"}
    for name in ("AVAILABILITY_STATES", "IMPLEMENTATION_STATES"):
        for word in getattr(provider_module, name):
            assert f'"{word}"' not in inspector, word


def test_the_mount_api_is_exactly_the_two_signatures_slice_d_wires():
    """Frozen by the frontend contract; a fourth argument is a renegotiation."""
    assert ("export function mountCanvas(mount, svg, state, handlers) {"
            in _code(CANVAS))
    assert ("export function mountInspector(mount, state, handlers) {"
            in _code(INSPECTOR))
    # One replace per mount: a render that appended would stack a second copy
    # of every control on the second call with the same state.
    assert _code(CANVAS).count("mount.replaceChildren(") == 1
    assert _code(INSPECTOR).count("mount.replaceChildren(") == 1
    # Neither module defines a handler; both only call the ones handed in.
    for source in (_code(CANVAS), _code(INSPECTOR)):
        assert "handlers.on" not in source
    assert set(re.findall(r'call\((?:context\.)?handlers, "(\w+)"', _code(CANVAS))) == {
        "onSelect", "onView", "onEdit", "onStatus"}
    assert set(re.findall(r'call\(\w*\.?handlers, "(\w+)"', _code(INSPECTOR))) == {
        "onSelect", "onEdit", "onStatus"}


def test_both_modules_are_pure_dom_writers_with_the_sealed_api_shut():
    """No transport, no clock, no storage, and no markup string, anywhere."""
    sealed = _code(*STUDIO_FILES).lower()
    for forbidden in ("fetch(", "eventsource", "xmlhttprequest", "websocket",
                      "webtransport", "rtcpeerconnection", "sendbeacon",
                      "import(", "importscripts", "innerhtml", "outerhtml",
                      "insertadjacenthtml", "localstorage", "sessionstorage",
                      "document.cookie", "settimeout", "setinterval",
                      "console.", "eval(", "new function"):
        assert forbidden not in sealed, forbidden
    # The whole file, comments included, for the one class of API that a
    # sentence about it is as good as a call: no markup is parsed here.
    whole = "\n".join(_text(path) for path in STUDIO_FILES).lower()
    for forbidden in ("innerhtml", "outerhtml", "insertadjacenthtml"):
        assert forbidden not in whole, forbidden


def test_every_control_either_module_writes_can_be_focused_after_a_re_render():
    """Focus intent survives a render, the way `graph.js:127-150` keeps it.

    The mechanism is one attribute: the key is read off `document.activeElement`
    before the pass and handed to the control's successor after it. A control
    with no `data-focus` is a keyboard Human dropped to the top of the document
    by their own edit, so every focusable this module writes must carry one.
    """
    for path in STUDIO_FILES:
        source = _code(path)
        assert "function focusKey(mount)" in source
        assert "function restoreFocus(mount, key)" in source
        assert source.count("restoreFocus(mount, key)") >= 1
        for tag in ("button", "input", "select"):
            for block in _attribute_blocks(source, tag):
                assert '"data-focus"' in block, f"{path.name}: {tag}: {block[:80]}"
        for block in _attribute_blocks(source, "div"):
            if "tabindex" in block:
                assert '"data-focus"' in block, f"{path.name}: {block[:80]}"
    # The one focusable this module builds outside `element()`: the edge's own
    # hit path, which is an SVG node and so is built with createElementNS.
    canvas = _code(CANVAS)
    assert 'hit.setAttribute("tabindex", "0")' in canvas
    assert 'hit.setAttribute("data-focus"' in canvas


def test_the_canvas_offers_a_keyboard_road_beside_every_pointer_one():
    """A pointer-only affordance is a bug in this surface, so it is counted.

    The add keys are derived from the step vocabulary rather than listed, so a
    fourth kind cannot arrive with no key beside it.
    """
    canvas = _code(CANVAS)
    adds = dict(re.findall(r'(\w+): "(\w+)"', re.search(
        r"function keyAdds\(key\) \{\s*return \{(.*?)\}", canvas,
        re.DOTALL).group(1)))
    assert set(adds.values()) == graph_definition.NODE_KINDS
    legend = re.search(r'const KEY_LEGEND = (.*?);\n', canvas, re.DOTALL).group(1)
    for key in list(adds) + ["Alt+Up/Down", "Shift+arrows", "Delete", "Esc",
                             "arrows move the selection", "d duplicates",
                             "+ and − zoom, 0 resets"]:
        assert key in legend, key
    # Every keyed operation is reachable without one: selection, view, add,
    # delete, duplicate and reorder all go through the same closed vocabulary
    # the palette, the view bar and the inspector use.
    assert set(re.findall(r'type: "([a-z-]+)"', canvas)) <= set(
        _js_ordered(canvas, "EDIT_TYPES")) | {"button"}


def test_the_step_a_cell_holds_is_the_size_the_stylesheet_gives_it():
    """The layout and the paint must agree, so the agreement is machine-held.

    `studio.css` is another slice's file, and a cell wider than the rule it
    draws into leaves a step floating inside its slot with its port off the
    edge -- a defect no source read of either file alone can see.
    """
    css = (PANEL / "studio.css").read_text(encoding="utf-8")
    declared = re.search(r"\.studio-node\{[^}]*width:(\d+)px", css)
    floor = re.search(r"\.studio-nodes \.studio-node\{min-height:(\d+)px\}", css)
    cell = re.search(r"CELL = Object\.freeze\(\{width: (\d+), height: (\d+), "
                     r"gapX: (\d+), gapY: (\d+)\}\)", _code(CANVAS))
    assert declared and floor and cell
    assert int(cell.group(1)) == int(declared.group(1))
    # A rule that declares a MINIMUM lets a step grow, so the cell may not be
    # shorter than it and the row gap is what absorbs the growth.
    assert int(cell.group(2)) >= int(floor.group(1))
    assert int(cell.group(4)) > 0


def test_the_edge_layer_rides_inside_the_one_transformed_stage():
    """Two layers, ONE transform, so a click lands on what the Human sees.

    `studio.css` leaves `#workflowEdges` in normal flow, so an edge layer left
    where the markup puts it draws a band above the steps rather than behind
    them; and two independently transformed siblings would have to be kept in
    step by hand, which is a drift a pointer finds before a reader does.
    """
    canvas = _code(CANVAS)
    assert "stage.append(svg);" in canvas
    assert canvas.count("stage.style.transform =") == 1
    assert "svg.style.transform" not in canvas
    for line in ('svg.style.position = "absolute";', 'svg.style.left = "0";',
                 'svg.style.top = "0";'):
        assert line in canvas, line
    # The drawn line is inert and its wide twin carries the interaction, so a
    # press on the background is a pan wherever the SVG lies -- which, since it
    # fills the whole drawing, is everywhere.
    assert 'path.setAttribute("pointer-events", "none");' in canvas
    assert 'hit.setAttribute("pointer-events", "stroke");' in canvas
    assert 'const HELD = "[data-node-id],[data-port],[data-edge]";' in canvas


def test_the_canvas_says_which_document_it_is_showing_and_never_mixes_two():
    """Definition and runtime are two documents, and the screen says which.

    The run's words may only be written inside the container that carries the
    literal label `run`, and the banner must state the join this build actually
    has -- a step id -- because a materialized plan records no workflow
    identity (`studio_routes.run_row` says the same from the other side).
    """
    canvas = _code(CANVAS)
    assert re.findall(r'"data-document": ([a-z.]+)', canvas) == ["shown.kind"]
    kinds = set(re.findall(r'return \{kind: "(\w+)",', canvas))
    assert kinds == {"draft", "published", "none"}
    runtime = re.search(r"function runStrip\(row\) \{(.*?)\n\}", canvas,
                        re.DOTALL).group(1)
    assert 'text: "run"' in runtime
    for word in ("phase", "outcome", "decision", "pass"):
        assert f"row.{word}" in runtime, word
    # Every runtime word is written by that one function and by no other.
    outside = canvas.replace(runtime, "")
    for word in ("row.phase", "row.outcome", "row.bound_reached"):
        assert word not in outside, word
    assert "a step id is the only join" in _text(CANVAS)
    assert "records no workflow identity" in canvas


def test_a_published_revision_is_immutable_on_both_surfaces():
    """One `editable` flag, granted by one word, and it is `draft`."""
    for source in (_code(CANVAS), _code(INSPECTOR)):
        assert 'editable: shown.kind === "draft"' in source or (
            'editable = shown.kind === "draft"' in source)
    assert "control.disabled = true" in _code(INSPECTOR)
    assert 'disabled: context.editable ? null : ""' in _code(CANVAS)


#: Every field of the six sections that has no durable home in this build. The
#: list is the report: a field named here SAYS so where it would have been, and
#: a field that stops saying so -- or a new one that quietly appears -- reds.
UNSUPPORTED_FIELDS = (
    "Purpose / description",
    "Timeout",
    "Retry / attempt bound",
    "Output budget",
    "Required input artifacts",
    "Produced artifacts",
    "Handoff mapping",
    "Missing-artifact behaviour",
    "Verifier",
    "Evidence requirements",
    "Success criteria",
    "Verification failure policy",
    "Edge conditions",
    "Decision routing",
    "Condition",
)


def test_every_field_with_no_durable_home_says_so_in_one_voice():
    """A control that writes inert data is forbidden; so is one that vanishes.

    One helper writes the sentence, so there is exactly one spelling of it and
    a reader learns the same thing everywhere. The labels are pinned because a
    field quietly dropping off the screen is the failure mode this rule exists
    for, and it is invisible by construction.
    """
    inspector = _code(INSPECTOR)
    assert inspector.count("not supported by this harness") == 1
    assert inspector.count('"data-unsupported"') == 1
    found = re.findall(r'unsupported\(box, "([^"]+)"', inspector)
    # Held as a set with the length beside it, in both directions: a field that
    # stops saying so goes missing, a new one that quietly appears is unnamed,
    # and one said twice under one label is a duplicate row on screen.
    assert set(found) == set(UNSUPPORTED_FIELDS)
    assert len(found) == len(UNSUPPORTED_FIELDS) == len(set(UNSUPPORTED_FIELDS))


def test_the_inspector_renders_the_six_sections_in_the_one_fixed_order():
    """Six, in this order, and anything else is a panel rather than a section."""
    inspector = _code(INSPECTOR)
    sections = _js_ordered(inspector, "SECTIONS")
    assert sections == ["general", "assignment", "execution", "artifacts",
                        "verification", "transitions"]
    assert re.findall(r'sectionOf\("([a-z]+)"', inspector) == sections
    appended = re.search(r"mount\.append\(generalSection(.*?)\);", inspector,
                         re.DOTALL).group(1)
    assert re.findall(r"(\w+)Section\(form\)", "generalSection(form)" + appended) == [
        "general", "assignment", "execution", "artifact", "verification",
        "transition"]
    # The step's own actions and the edge panel are NOT sections: the six are
    # counted by `data-section`, and a seventh would break that count.
    assert re.findall(r'panelOf\("([a-z]+)"', inspector) == ["actions", "edge"]


def test_the_inspector_reads_a_run_only_through_records_a_contract_validated():
    """Assignment shows a run's binding; it can never write one.

    The three model states are kept apart the way `graph-view.appendDeployment`
    keeps them: a pinned model, a configuration that pinned none, and a
    configuration this window could not read.
    """
    inspector = _code(INSPECTOR)
    word = re.search(r"function modelWord\(instance\) \{(.*?)\n\}", inspector,
                     re.DOTALL).group(1)
    assert "unreadable" in word and "none pinned" in word
    assert "String(instance.model)" in word
    # Every read of a run is labelled with the run it came from.
    sources = re.findall(r'`the (?:frozen configuration|plan|projection|durable '
                         r'records|envelope) of run \$\{run\.runId\}', inspector)
    assert len(sources) >= 5
    assert "Process exit 0 proves the process finished, not that the work" in (
        _text(INSPECTOR))


def test_every_edited_word_is_judged_before_it_is_written():
    """A control that posts a body for the server to reject is not validated.

    The grammars are the contract's own: the id pattern above is held to
    `contract_values._ID_RE`, and the loop bound to the definition's own range.
    """
    inspector = _code(INSPECTOR)
    checks = set(re.findall(r"^  (\w+): \(value\)", re.search(
        r"const CHECKS = Object\.freeze\(\{(.*?)\n\}\);", inspector,
        re.DOTALL).group(1), re.MULTILINE))
    assert checks == {"title", "role_id", "gate_id"}
    assert "if (judge()) return;" in inspector
    bound = re.search(r"bound\.addEventListener\(\"change\", \(\) => \{(.*?)\n  \}\)",
                      inspector, re.DOTALL).group(1)
    assert "Number.isInteger(value)" in bound
    assert "LOOP_BOUND.min" in bound and "LOOP_BOUND.max" in bound
    assert "return;" in bound.split("commit(")[0]
