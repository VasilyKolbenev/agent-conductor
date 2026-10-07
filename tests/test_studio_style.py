"""studio.css, read through the panel's cascade model rather than grepped.

The Studio is a third entry beside the panel and the Graph window, and its
stylesheet arrives under the Graph window's discipline: nothing colour-bearing
is written by hand twice. Every rule that paints a mark must appear either in
MEASURED -- where its declaration is resolved through the cascade under every
media environment the sheet declares, composited onto the surface its chain
stands on, and held to its WCAG floor in both themes -- or in EXEMPT with the
reason written beside it. A new colour declaration fails the completeness test
until it arrives with a row or a reason.

The owner approved a distinct command-deck palette for Studio. Its own tokens
are measured; the classic panel and Graph are unchanged. The arithmetic is
tests/test_panel_colour.py's, which knows nothing about any of them.

What this module is and is not: it is a model of SOURCE TEXT, built by parsing
characters. It renders nothing and samples nothing. Every claim here is a claim
about what the stylesheet asks for; the rendered half is the browser gate.
"""
import re
from pathlib import Path

import pytest

from tests.test_panel_cascade import E, _COMPOUND, _TOKEN, computed, environments, rules
from tests.test_panel_colour import contrast
from tests.test_panel_contrast import NONTEXT_MIN, TEXT_MIN, _hex_to_rgb

PANEL = Path(__file__).resolve().parents[1] / "src" / "conductor" / "panel"
#: studio.css wrapped the way the cascade module reads a panel: one style
#: block, one (empty) script block.
STUDIO = ("<style>" + (PANEL / "studio.css").read_text(encoding="utf-8")
          + "</style><script></script>")
THEMES = ("dark", "light")

# ── the chains the shell actually builds ───────────────────────────────────
BODY = [E("body")]
SHELL = BODY + [E("div", "studio-shell")]
HEADER = SHELL + [E("header", "studio-header")]
NAV = SHELL + [E("nav", "studio-nav")]
TAB = NAV + [E("button", "studio-tab")]
MAIN = SHELL + [E("main", "studio-main")]
SCREEN = MAIN + [E("div", "studio-workspace"), E("section", "studio-screen")]
CARD = SCREEN + [E("div", "studio-card")]
CANVAS = SCREEN + [E("div", "studio-canvas")]
NODES = CANVAS + [E("div", "studio-nodes")]
NODE = NODES + [E("button", "studio-node")]
CHROME = NODES + [E("div", "studio-canvas__chrome")]
PALETTE = CHROME + [E("div", "studio-palette")]
VIEW = CHROME + [E("div", "studio-view")]
PRIMARY = HEADER + [E("div", "studio-primary")]
FOCUSED = ("focus-visible",)
SELECTED = {"aria-selected": "true"}
PRESSED = {"aria-pressed": "true"}
DECK = SCREEN + [E("section", "studio-section", "studio-deck")]
PLANET = DECK + [E("button", "studio-planet")]
ORBIT = NODES + [E("section", "studio-orbit")]
ROLE_ORB = ORBIT + [E("div", "studio-orbit__fleet"),
                    E("button", "studio-planet", "studio-orbit__role", **PRESSED)]
QUOTAS = SCREEN + [E("section", "studio-quotas")]
QUOTA = QUOTAS + [E("div", "studio-quotas__grid"), E("article", "studio-quota")]
QUOTA_WINDOW = QUOTA + [E("section", "studio-quota__window")]


def _chip(*variant: str) -> object:
    return E("span", "studio-chip", *variant)


def _rows_on(base: list, *tail, prop: str = "color",
             floor: float = TEXT_MIN, bg: str | None = None) -> tuple:
    return (base + list(tail), prop, floor, bg)


#: selector (exactly as the parser reports it) → the rows that measure it.
#: A row is (chain, mark property, floor, surface-token override or None);
#: None composites the surface by walking the chain's own backgrounds.
MEASURED = {
    "body": [_rows_on(BODY)],
    ".studio-preference select": [_rows_on(HEADER, E("div", "studio-preferences"),
        E("label", "studio-preference"), E("select"))],
    ".studio-quotas": [_rows_on(QUOTAS)],
    ".studio-quotas button": [_rows_on(QUOTAS, E("button"))],
    ".studio-quota__fact dt": [
        _rows_on(base, E("dl"), E("div", "studio-quota__fact"), E("dt"))
        for base in (QUOTA, QUOTA_WINDOW)],
    ".studio-quota__status": [
        _rows_on(base, E("p", "studio-quota__status"))
        for base in (QUOTA, QUOTA_WINDOW)],
    # The one focus ring, measured on each of the three surfaces a control in
    # this shell can stand on. A ring nobody can see is not a ring.
    ":focus-visible": [
        (BODY + [E("button", states=FOCUSED)], "outline", NONTEXT_MIN, "--ground"),
        (CARD + [E("button", states=FOCUSED)], "outline", NONTEXT_MIN, "--panel"),
        (CARD + [E("input", states=FOCUSED)], "outline", NONTEXT_MIN, "--sunk"),
        (PRIMARY + [E("button", "studio-btn", states=FOCUSED)],
         "outline", NONTEXT_MIN, "--ink")],
    ".studio-conn": [_rows_on(HEADER, E("p", "studio-conn"))],
    ".studio-elsewhere": [_rows_on(HEADER, E("a", "studio-elsewhere"))],
    ".studio-tab": [_rows_on(TAB)],
    ".studio-tab:hover": [_rows_on(NAV, E("button", "studio-tab",
                                          states=("hover",)))],
    '.studio-tab[aria-selected="true"]': [
        _rows_on(NAV, E("button", "studio-tab", **SELECTED)),
        (NAV + [E("button", "studio-tab", **SELECTED)],
         "border-bottom-color", NONTEXT_MIN, None)],
    ".studio-state": [_rows_on(SCREEN, E("p", "studio-state"))],
    ".studio-hint": [_rows_on(SCREEN, E("p", "studio-hint"))],
    # The empty sentence lands both on the page ground (the noscript arm) and
    # inside a card, and both surfaces are measured.
    ".studio-empty": [_rows_on(SHELL, E("p", "studio-empty")),
                      _rows_on(CARD, E("p", "studio-empty"))],
    ".studio-status": [_rows_on(SHELL, E("p", "studio-status"))],
    ".studio-card h3": [_rows_on(CARD, E("h3"))],
    ".studio-protocol": [_rows_on(CARD, E("span", "studio-protocol")),
                         _rows_on(SCREEN, E("span", "studio-protocol"))],
    ".studio-chip": [_rows_on(CARD, _chip()), _rows_on(SCREEN, _chip()),
                     _rows_on(NODE, _chip())],
    ".studio-chip--none": [_rows_on(CARD, _chip("studio-chip--none")),
                           _rows_on(SCREEN, _chip("studio-chip--none"))],
    ".studio-chip--none .studio-glyph": [
        _rows_on(CARD, _chip("studio-chip--none"), E("i", "studio-glyph"),
                 floor=NONTEXT_MIN),
        _rows_on(SCREEN, _chip("studio-chip--none"), E("i", "studio-glyph"),
                 floor=NONTEXT_MIN)],
    ".studio-field": [_rows_on(CARD, E("label", "studio-field")),
                      _rows_on(SCREEN, E("div", "studio-field"))],
    ".studio-field input": [_rows_on(CARD, E("div", "studio-field"), E("input"))],
    ".studio-field select": [_rows_on(CARD, E("div", "studio-field"), E("select"))],
    ".studio-field textarea": [
        _rows_on(CARD, E("div", "studio-field"), E("textarea"))],
    ".studio-edge": [_rows_on(CANVAS, E("svg", "studio-edges"),
                              E("path", "studio-edge"),
                              prop="stroke", floor=NONTEXT_MIN)],
    # The selected step's contour, measured on the node's own surface and on
    # the canvas it stands in -- the two grounds the line is drawn between.
    '.studio-node[aria-pressed="true"]': [
        (NODES + [E("button", "studio-node", **PRESSED)],
         "border-color", NONTEXT_MIN, None),
        (NODES + [E("button", "studio-node", **PRESSED)],
         "border-color", NONTEXT_MIN, "--sunk")],
    ".studio-node__meta": [_rows_on(NODE, E("span", "studio-node__meta"))],
    ".studio-diag__code": [_rows_on(CARD, E("div", "studio-diag"),
                                    E("span", "studio-diag__code"))],
    ".studio-primary .studio-btn": [
        _rows_on(PRIMARY, E("button", "studio-btn")),
        _rows_on(PRIMARY, E("button", "studio-btn"), prop="border-color",
                 floor=NONTEXT_MIN, bg="--ground")],
    ".studio-primary .studio-btn:hover": [
        _rows_on(PRIMARY, E("button", "studio-btn", states=("hover",)),
                 prop="border-color", floor=NONTEXT_MIN, bg=surface)
        for surface in ("--ground", "--ink")],
    ".studio-view__level": [_rows_on(VIEW, E("p", "studio-view__level"))],
}
MEASURED[".studio-planet__orb"] = [
    _rows_on(PLANET, E("span", "studio-planet__orb")),
    _rows_on(PLANET, E("span", "studio-planet__orb"),
             prop="border", floor=NONTEXT_MIN)]
MEASURED['.studio-planet[aria-pressed="true"] .studio-planet__orb'] = [
    _rows_on(DECK, E("button", "studio-planet", **PRESSED),
             E("span", "studio-planet__orb"), prop=prop, floor=floor)
    for prop, floor in (("color", TEXT_MIN), ("border", NONTEXT_MIN))]
MEASURED[".studio-planet__selection"] = [
    _rows_on(PLANET, E("span", "studio-planet__selection"))]
MEASURED['.studio-planet[aria-pressed="true"] .studio-planet__selection'] = [
    _rows_on(DECK, E("button", "studio-planet", **PRESSED),
             E("span", "studio-planet__selection"))]
MEASURED[".studio-run__meta"] = [_rows_on(SCREEN, E("span", "studio-run__meta"))]
MEASURED['.studio-lens[aria-pressed="true"]'] = [
    _rows_on(CHROME, E("div", "studio-lenses"), E("button", "studio-lens", **PRESSED),
             prop="border-bottom", floor=NONTEXT_MIN)]
MEASURED['.studio-orbit__step[aria-pressed="true"]'] = [
    _rows_on(ORBIT, E("section", "studio-orbit__duties"), E("div", "studio-orbit__steps"),
             E("button", "studio-orbit__step", **PRESSED), prop="outline", floor=NONTEXT_MIN)]
MEASURED['.studio-planet[aria-pressed="true"] .studio-planet__orb'].extend([
    _rows_on(ROLE_ORB, E("span", "studio-planet__orb"), prop=prop, floor=floor)
    for prop, floor in (("color", TEXT_MIN), ("border", NONTEXT_MIN))])
MEASURED['.studio-planet[aria-pressed="true"] .studio-planet__selection'].append(
    _rows_on(ROLE_ORB, E("span", "studio-planet__selection")))
MEASURED[".studio-fact__k"] = [_rows_on(SCREEN, E("span", "studio-fact__k"))]
MEASURED[".studio-deck__route"] = [
    _rows_on(DECK, E("div", "studio-deck__fleet"), E("svg", "studio-deck__routes"),
             E("path", "studio-deck__route"), prop="stroke", floor=NONTEXT_MIN)]
MEASURED[".studio-deck__route-label"] = [
    _rows_on(DECK, E("div", "studio-deck__fleet"), E("svg", "studio-deck__routes"),
             E("g", "studio-deck__route-label"), prop="stroke", floor=NONTEXT_MIN)]
MEASURED[".studio-step-flow__stage svg"] = [
    _rows_on(DECK, E("section", "studio-deck__inspector"),
             E("section", "studio-step-flow__stage"), E("svg"),
             prop="stroke", floor=NONTEXT_MIN, bg="--panel")]
MEASURED[".studio-deck__routes marker path"] = [
    _rows_on(DECK, E("svg", "studio-deck__routes"), E("marker"), E("path"),
             prop="fill", floor=NONTEXT_MIN)]
MEASURED['.studio-run[aria-pressed="true"]'] = [
    _rows_on(SCREEN, E("button", "studio-run", **PRESSED),
             prop="border-bottom", floor=NONTEXT_MIN)]
# Actual shared field() labels, schema arguments, and bare form controls all
# belong to this shell. Measure the controls on the page and inside a card so
# a missing class cannot restore a browser-default white field in dark mode.
for _field in ("command-field", "command-arg"):
    MEASURED[f".studio-shell .{_field}"] = [
        _rows_on(base, E("label", _field)) for base in (SCREEN, CARD)]
for _control in ("input", "select", "textarea"):
    MEASURED[f".studio-shell {_control}"] = [
        _rows_on(base, E(_control)) for base in (SCREEN, CARD)]
for _class, _base in (("studio-action", CARD), ("studio-palette__add", PALETTE),
                       ("studio-view__button", VIEW)):
    MEASURED[f".{_class}"] = [_rows_on(_base, E("button", _class))]
    MEASURED[f".{_class}:hover"] = [
        _rows_on(_base, E("button", _class, states=("hover",)),
                 prop="border-color", floor=NONTEXT_MIN)]
MEASURED[".studio-btn:hover"] = [
    _rows_on(CARD, E("button", "studio-btn", states=("hover",)),
             prop="border-color", floor=NONTEXT_MIN)]
for _class in ("studio-canvas__phase", "studio-canvas__diagnostics",
               "studio-canvas__runnote", "studio-palette__note",
               "studio-canvas__keys", "studio-canvas__positions"):
    MEASURED[f".{_class}"] = [_rows_on(CHROME, E("p", _class))]
for _class in ("studio-note", "studio-context", "studio-unsupported",
               "studio-inspector__empty"):
    MEASURED[f".{_class}"] = [_rows_on(CARD, E("p", _class))]
for _status in ("pass", "wait", "fail"):
    MEASURED[f".studio-chip--{_status}"] = [
        _rows_on(CARD, _chip(f"studio-chip--{_status}"),
                 prop="border-color", floor=NONTEXT_MIN),
        _rows_on(SCREEN, _chip(f"studio-chip--{_status}"),
                 prop="border-color", floor=NONTEXT_MIN)]
    MEASURED[f".studio-chip--{_status} .studio-glyph"] = [
        _rows_on(CARD, _chip(f"studio-chip--{_status}"), E("i", "studio-glyph"),
                 floor=NONTEXT_MIN),
        _rows_on(SCREEN, _chip(f"studio-chip--{_status}"), E("i", "studio-glyph"),
                 floor=NONTEXT_MIN)]

#: Colour-bearing selectors that are deliberately not contrast rows, each with
#: its reason on the record.
# Real Bridge and trace chains, with their own surfaces and state attributes.
RUN_MAIN = SHELL + [E("main", "studio-main", **{"data-screen": "runs"})]
TASK_ROW = RUN_MAIN + [E("aside"), E("div", "studio-task-bar"),
    E("nav", "studio-task-rail"), E("button", "studio-task-row", **PRESSED)]
BRIDGE = RUN_MAIN + [E("aside", "studio-bridge"), E("section", "studio-bridge__box")]
TRACE = DECK + [E("div", "studio-deck__body"), E("div", "studio-deck__scene"),
    E("section", "studio-trace")]
TRACE_INNER = TRACE + [E("div", "studio-trace__inner")]
MEASURED[".studio-task-row"] = [_rows_on(TASK_ROW)]
MEASURED['.studio-task-row[aria-pressed="true"]'] = [_rows_on(TASK_ROW)]
MEASURED['.studio-bridge__box'] = [_rows_on(BRIDGE)]
MEASURED['.studio-trace'] = [_rows_on(TRACE)]
MEASURED['.studio-trace__inner svg path'] = [_rows_on(TRACE_INNER,
    E("svg"), E("path", "studio-trace__link"), prop="stroke", floor=NONTEXT_MIN)]
MEASURED['.studio-trace__inner svg [data-open="true"]'] = [_rows_on(TRACE_INNER,
    E("svg"), E("path", "studio-trace__link", **{"data-open": "true"}), prop="stroke", floor=NONTEXT_MIN)]
MEASURED['.studio-trace__inner svg text'] = [_rows_on(TRACE_INNER,
    E("svg"), E("text"), prop="fill")]
MEASURED['.studio-trace__step[aria-pressed="true"] .studio-trace__point'] = [_rows_on(TRACE_INNER,
    E("button", "studio-trace__step", **PRESSED), E("span", "studio-trace__point"),
    prop="outline", floor=NONTEXT_MIN)]
for _word in ("needs_decision", "outcome_verification_failed", "outcome_failed"):
    MEASURED[f'.studio-trace__step[data-word="{_word}"] .studio-trace__point'] = [_rows_on(TRACE_INNER,
        E("button", "studio-trace__step", **{"data-word": _word}), E("span", "studio-trace__point"),
        floor=NONTEXT_MIN)]  # symbolic point; the adjacent status word uses the text floor

MEASURED[".studio-team-roster button"] = [_rows_on(DECK,
    E("div", "studio-deck__head"),
    E("nav", "studio-team-roster"), E("button"))]

EXEMPT = {
    '.studio-main[data-screen="runs"] .studio-task-bar': "Neutral separator between the task rail and scene; no status is encoded.",
    '.studio-bridge__box button': "Neutral row divider; each control retains its text and focus ring.",
    '.studio-bridge__reading': "Neutral separator between independent quota contexts.",
    '.studio-trace__inner svg .studio-trace__horizon': "Decorative horizon; step words, glyphs and measured route strokes carry the plan.",
    ".studio-quota": "neutral enclosure; source, freshness and funds are explicit text",
    ".studio-quota__window": "neutral separator; each balance or window has a heading",
    ".studio-step-flow__body": "neutral separators; words and icons identify every stage",
    ".studio-planet__orb::after": "decorative outer orbit; selected border remains measured",
    ".studio-orbit__fleet::before": "decorative role-group ring, not a route or state carrier",
    ".studio-run": "neutral run-list separator; selection is independently measured",
    ".studio-deck": "neutral separators; participant selection has its own measured ring",
    ".studio-header": "the rule under the header is a neutral separator; it "
                      "identifies no state and carries no word",
    ".studio-nav": "the same neutral separator under the tablist; which tab is "
                   "current is said by the underline above this line, and that "
                   "one is measured",
    ".studio-card": "the card border encloses content; it identifies no state",
    ".studio-btn": "the button border encloses the control; its word runs on "
                   "the inherited --ink that the input row measures on the "
                   "same --sunk surface",
    ".studio-canvas": "the well's border encloses the drawing; the steps and "
                      "edges inside it carry every state, and each is measured",
    ".studio-node": "the step's resting border is the neutral enclosure; its "
                    "kind arrives as a contour STYLE and a word, and its "
                    "selected state as the measured --ink contour",
}

#: Which declarations are marks. `background` is deliberately not one: a
#: surface is composited under a mark rather than being one, and every row
#: above resolves its surface by walking the chain's own backgrounds.
_MARK_PROPS = ("color", "stroke", "fill", "outline", "border", "border-color",
               "border-top", "border-right", "border-bottom", "border-left",
               "border-bottom-color", "border-top-color")
_COLOURFUL = re.compile(r"var\(--[\w-]+\)|#[0-9a-fA-F]{3,8}")
#: The token names the three copies of the December palette must all carry.
REQUIRED_TOKENS = {"--ground", "--panel", "--sunk", "--line", "--ink",
                   "--muted", "--faint", "--accent", "--pass", "--wait",
                   "--fail"}


def test_every_paint_declaration_is_a_measured_row_or_named_exempt():
    # The closing test a hand-written table cannot offer: a new or repainted
    # colour declaration must arrive with a row or a reason.
    for rule in rules(STUDIO):
        marks = [prop for prop in rule.decls if prop in _MARK_PROPS
                 and _COLOURFUL.search(rule.decls[prop])]
        if not marks:
            continue
        assert rule.selector in MEASURED or rule.selector in EXEMPT, rule.selector


def test_every_measured_and_exempt_selector_is_one_the_stylesheet_declares():
    """Held from the other side, so a deleted rule cannot leave a live row.

    A table naming a selector that no longer exists measures nothing and says
    so to nobody: the floor test would keep resolving an inherited value and
    keep passing. Both tables are therefore closed against the sheet itself.
    """
    declared = {rule.selector for rule in rules(STUDIO)}
    assert set(MEASURED) <= declared, sorted(set(MEASURED) - declared)
    assert set(EXEMPT) <= declared, sorted(set(EXEMPT) - declared)
    assert not set(MEASURED) & set(EXEMPT)


def _mark_value(win: dict, prop: str) -> str | None:
    if prop == "border-color":
        return win.get("border-color") or win.get("border")
    if prop == "border-bottom-color":
        return (win.get("border-bottom-color") or win.get("border-bottom")
                or win.get("border"))
    return win.get(prop)


def _paint(theme: str, value: str) -> tuple[int, int, int]:
    found = re.search(r"var\((--[\w-]+)\)|#[0-9a-fA-F]{6}", value)
    assert found, f"no colour in {value!r}"
    if found.group(1):
        return tokens(theme)[found.group(1)]
    return _hex_to_rgb(found.group(0))


def _surface(theme: str, chain: list, env: frozenset) -> tuple[int, int, int]:
    for depth in range(len(chain), 0, -1):
        win = computed(list(chain[:depth]), STUDIO, env)
        value = (win.get("background") or win.get("background-color", "")).strip()
        if value and value not in ("none", "transparent"):
            return _paint(theme, value)
    raise AssertionError(f"nothing under {chain} paints a surface")


@pytest.mark.parametrize("theme", THEMES)
def test_every_derived_row_clears_its_floor_in_every_environment(theme):
    for selector, specs in MEASURED.items():
        for chain, prop, floor, bg in specs:
            for label, env in environments(theme, STUDIO):
                raw = _mark_value(computed(list(chain), STUDIO, env), prop)
                assert raw, (selector, label)
                fg = _paint(theme, raw)
                under = tokens(theme)[bg] if bg else _surface(theme, chain, env)
                ratio = contrast(fg, under)
                assert ratio >= floor, (
                    f"{label}: {selector} is {ratio:.2f}:1, floor {floor}")


def _root_blocks(css: str) -> list[dict[str, str]]:
    """Every ``--name:value`` map, one per ``:root{...}`` block, in order."""
    blocks = re.findall(r":root\{(.*?)\}", css, re.DOTALL)
    return [dict(re.findall(r"(--[a-z0-9-]+):([^;}]+)", block))
            for block in blocks]


def tokens(theme: str) -> dict[str, tuple[int, int, int]]:
    """Read Studio itself; measuring the classic palette could bless invisible UI."""
    dark, light = _root_blocks(STUDIO)
    assert theme in THEMES
    values = dark if theme == "dark" else dict(dark, **light)
    return {key: _hex_to_rgb(value.strip()) for key, value in values.items()
            if value.strip().startswith("#")}


def test_the_command_deck_palette_is_complete_in_both_declared_themes():
    blocks = _root_blocks(STUDIO)
    assert len(blocks) == 2
    for block in blocks:
        assert REQUIRED_TOKENS | {"--ion"} <= set(block)
    for theme in THEMES:
        assert REQUIRED_TOKENS | {"--ion"} <= set(tokens(theme))
    # The accent is an outline, the ion colour is content/selection. Measuring
    # them as one token would lose contrast on the inverse primary button.
    assert tokens("dark")["--ion"] != tokens("dark")["--accent"]


def test_every_motion_the_studio_declares_sits_behind_the_reduced_motion_door():
    moved = [rule.selector for rule in rules(STUDIO)
             if ("transition" in rule.decls or "animation" in rule.decls)
             and "prefers-reduced-motion:no-preference" not in rule.context]
    assert not moved, moved
    assert "@keyframes" not in STUDIO


def test_the_studio_stylesheet_declares_only_modelled_interactive_states():
    """The closed set, with one deliberate extension over the graph window's.

    `aria-selected` is the tablist's own spelling of the state `aria-pressed`
    spells for a toggle button, and the shell's nav is a real tablist. It is
    MODELLED here rather than admitted to the inert list, because it is not
    inert: it repaints, and every paint it wins is a MEASURED row above. The
    inert names key on what a thing IS, never on somebody touching it.
    """
    modelled = {"hover", "focus-visible", "aria-pressed", "aria-selected", "data-theme", "data-screen", "data-open", "data-word"}
    # Participant count and DOM position choose geometry, never repaint a state.
    inert = {"root", "hidden", "data-count", "nth-child", "data-kind", "data-duty"}
    for rule in rules(STUDIO):
        for token in _TOKEN.findall(rule.selector):
            if token.startswith("::"):
                continue
            if token.startswith(":"):
                name = token.lstrip(":").split("(")[0]
            elif token.startswith("["):
                name = token[1:-1].partition("=")[0].strip()
            else:
                continue
            assert name in modelled or name in inert, rule.selector


def test_the_studio_stylesheet_uses_only_selector_forms_the_cascade_models():
    for rule in rules(STUDIO):
        assert not re.search(r"[>+~]", rule.selector), rule.selector
        for compound in rule.selector.split():
            assert _COMPOUND.fullmatch(compound), rule.selector


def test_focus_visible_declares_a_ring_the_focus_tests_can_stand_on():
    win = computed([E("button", states=FOCUSED)], STUDIO)
    assert win.get("outline") == "2px solid var(--accent)"
    assert win.get("outline-offset") == "2px"


def test_the_current_tab_is_told_apart_by_more_than_the_colour_it_takes():
    """No meaning carried by colour alone, proven as a difference.

    Take the colour away and the current tab is still the current tab: the
    word is heavier and the underline is drawn. A change that left only the
    hue behind would red this, which a grep for `font-weight` would not.
    """
    resting = computed(TAB, STUDIO)
    current = computed(NAV + [E("button", "studio-tab", **SELECTED)], STUDIO)
    assert current.get("font-weight") != resting.get("font-weight")
    assert _mark_value(current, "border-bottom-color") != \
        _mark_value(resting, "border-bottom-color")
    assert "transparent" in (resting.get("border-bottom") or "")


@pytest.mark.parametrize("chain", [
    [E("div", "studio-field"), E("input")],
    [E("div", "studio-field"), E("select")],
    [E("div", "studio-field"), E("textarea")],
    [E("button", "studio-btn")],
    [E("div", "studio-shell"), E("button", "studio-tab")],
    [E("div", "studio-shell"), E("button")],
    [E("div", "studio-shell"), E("select")],
    [E("div", "studio-shell"), E("textarea")],
], ids=["input", "select", "textarea", "button", "tab", "any-button",
        "any-select", "any-textarea"])
def test_every_form_control_declares_the_44px_minimum_target(chain):
    assert computed(chain, STUDIO).get("min-height") == "44px"


def test_the_step_wins_its_own_height_against_the_shell_wide_target_floor():
    """The floor is a MINIMUM, and a rule that lost to it would ship a stub.

    The 44px target is declared over every button in the shell, which is what
    closes the floor by construction -- and it is also what a step's own height
    has to beat on specificity rather than on source order. Measured, so the
    day somebody re-spells either rule this says which one won.
    """
    assert computed(NODE, STUDIO).get("min-height") == "112px"


@pytest.mark.parametrize("control", ["input", "select", "textarea"])
@pytest.mark.parametrize("classes", [(), ("command-field",), ("command-arg",),
                                     ("studio-field", "command-field")])
def test_every_studio_form_control_declares_a_themed_bounded_surface(control, classes):
    chain = CARD + ([E("label", *classes)] if classes else []) + [E(control)]
    for _, env in environments("dark", STUDIO) + environments("light", STUDIO):
        win = computed(chain, STUDIO, env)
        assert win.get("color") == "var(--ink)"
        assert win.get("background") == "var(--sunk)"
        assert win.get("max-width") == "100%"
        assert win.get("min-width") == "0"
        assert win.get("min-height") == "44px"


def test_primary_action_and_canvas_controls_have_explicit_visual_hierarchy():
    primary = computed(PRIMARY + [E("button", "studio-btn")], STUDIO)
    assert primary.get("background") == "var(--ink)"
    assert primary.get("color") == "var(--ground)"
    for base, classname in ((PALETTE, "studio-palette__add"),
                            (VIEW, "studio-view__button")):
        win = computed(base + [E("button", classname)], STUDIO)
        assert win.get("min-height") == "44px"
        assert win.get("min-width") == "44px"
        assert win.get("background") == "var(--panel)"
        assert win.get("border") == "1px solid var(--line)"
    help_summary = CHROME + [E("details", "studio-canvas__help"), E("summary")]
    assert computed(help_summary, STUDIO).get("min-height") == "44px"


def test_overview_layout_preserves_reading_order_without_hiding_cards():
    overview = SCREEN + [E("div", "studio-body", "studio-overview")]
    assert computed(overview, STUDIO).get("display") == "grid"
    assert computed(overview, STUDIO).get("grid-template-columns") == "minmax(0,1fr)"
    for _, env in environments("dark", STUDIO):
        for name in ("latest", "attention", "blocked", "ready", "context"):
            chain = overview + [E("section", "studio-card", f"studio-overview__{name}")]
            win = computed(chain, STUDIO, env)
            assert win.get("display") != "none"
            assert "order" not in win and "grid-row" not in win


def test_manual_theme_tokens_are_exactly_the_measured_system_palettes():
    """Explicit selection changes precedence, never introduces unmeasured colours."""
    automatic = _root_blocks(STUDIO)
    for theme, expected in zip(THEMES, automatic):
        match = re.search(r':root\[data-theme="' + theme + r'"\]\{(.*?)\}', STUDIO, re.S)
        assert match is not None
        actual = dict(re.findall(r"(--[a-z0-9-]+):([^;}]+)", match[1]))
        assert actual == expected
        assert "color-scheme:" + theme in match[1]
