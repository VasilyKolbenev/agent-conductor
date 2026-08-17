"""graph.css, read through the panel's cascade model rather than grepped.

Nothing colour-bearing here is written by hand twice. Every rule of graph.css
that paints a mark (a color, a stroke, an outline, a status border) must
appear either in MEASURED — where its declaration is resolved through the
cascade under every media environment the stylesheet declares, composited
onto the surface its chain stands on, and held to its WCAG floor — or in
EXEMPT with the reason written beside it. A repainted rule therefore moves a
measured number, a media-scoped override is measured inside its own
environment, and a new colour declaration fails the completeness test until
it arrives with a row or a reason. The badge tint strength is read out of
the stylesheet, so pushing 14% to 60% moves the monogram measurement with
it. The token values themselves are the panel's (tests/test_graph_source.py
pins the copy value-for-value), so the arithmetic runs on the panel's own
tables from tests/test_panel_contrast.py.
"""
import re
from pathlib import Path

import pytest

from conductor import harnesses
from tests.test_panel_cascade import E, _COMPOUND, _TOKEN, computed, environments, rules
from tests.test_panel_colour import contrast
from tests.test_panel_contrast import NONTEXT_MIN, TEXT_MIN, _hex_to_rgb, _mix_srgb, tokens

PANEL = Path(__file__).resolve().parents[1] / "src" / "conductor" / "panel"
#: graph.css wrapped the way the cascade module reads a panel: one style
#: block, one (empty) script block.
GRAPH = ("<style>" + (PANEL / "graph.css").read_text(encoding="utf-8")
         + "</style><script></script>")
THEMES = ("dark", "light")

# ── the chains the graph window actually builds ────────────────────────────
BODY = [E("body")]
SHELL = BODY + [E("header", "shell")]
CARD = BODY + [E("section", "card")]
FIELD = CARD + [E("div", "g-field-scroll"), E("div", "g-field")]
NODE = FIELD + [E("button", "g-node")]
FOCUSED = ("focus-visible",)


def _chip(*variant: str) -> object:
    return E("span", "g-chip", *variant)


def _rows_on(base: list, *tail, prop: str = "color",
             floor: float = TEXT_MIN, bg: str | None = None) -> tuple:
    return (base + list(tail), prop, floor, bg)


#: selector (exactly as the parser reports it) → the rows that measure it.
#: A row is (chain, mark property, floor, surface-token override or None);
#: None composites the surface by walking the chain's own backgrounds.
MEASURED = {
    "body": [_rows_on(BODY)],
    "h3": [_rows_on(CARD, E("h3"))],
    ".empty": [_rows_on(CARD, E("p", "empty"))],
    ".shell .mono": [_rows_on(SHELL, E("span", "mono"))],
    ".g-notice": [_rows_on(SHELL, E("p", "g-notice"))],
    ".hb__n": [_rows_on(NODE, E("span", "hb"), E("span", "hb__n")),
               _rows_on(CARD, E("span", "hb"), E("span", "hb__n"))],
    ".hb__d": [_rows_on(CARD, E("li", "g-palette__row"), E("a", "hb__d"))],
    ".g-chip": [_rows_on(NODE, _chip()), _rows_on(CARD, _chip())],
    ".g-chip--none": [_rows_on(NODE, _chip("g-chip--none")),
                      _rows_on(CARD, _chip("g-chip--none"))],
    ".g-chip--none .gl": [
        _rows_on(NODE, _chip("g-chip--none"), E("i", "gl"), floor=NONTEXT_MIN),
        _rows_on(CARD, _chip("g-chip--none"), E("i", "gl"), floor=NONTEXT_MIN)],
    ".g-edge": [_rows_on(FIELD, E("svg"), E("path", "g-edge"),
                         prop="stroke", floor=NONTEXT_MIN)],
    '.g-node[aria-pressed="true"]': [
        (FIELD + [E("button", "g-node", **{"aria-pressed": "true"})],
         "border-color", NONTEXT_MIN, None),
        (FIELD + [E("button", "g-node", **{"aria-pressed": "true"})],
         "border-color", NONTEXT_MIN, "--panel")],
    ".g-node__from": [_rows_on(NODE, E("span", "g-node__from"))],
    ".g-det__meta": [_rows_on(CARD, E("p", "g-det__meta"))],
    ".g-note": [_rows_on(CARD, E("p", "g-note"))],
    ".g-timeline__at": [_rows_on(CARD, E("span", "g-timeline__at"))],
    ".command-field": [_rows_on(CARD, E("div", "command-field"))],
    ".command-field input": [_rows_on(CARD, E("div", "command-field"), E("input"))],
    ".command-field select": [_rows_on(CARD, E("div", "command-field"), E("select"))],
    ":focus-visible": [
        (BODY + [E("button", states=FOCUSED)], "outline", NONTEXT_MIN, "--ground"),
        (CARD + [E("button", states=FOCUSED)], "outline", NONTEXT_MIN, "--panel"),
        (NODE[:-1] + [E("button", "g-node", states=FOCUSED)],
         "outline", NONTEXT_MIN, "--sunk")],
}
for _status in ("pass", "wait", "fail"):
    MEASURED[f".g-chip--{_status}"] = [
        _rows_on(NODE, _chip(f"g-chip--{_status}"),
                 prop="border-color", floor=NONTEXT_MIN),
        _rows_on(CARD, _chip(f"g-chip--{_status}"),
                 prop="border-color", floor=NONTEXT_MIN)]
    MEASURED[f".g-chip--{_status} .gl"] = [
        _rows_on(NODE, _chip(f"g-chip--{_status}"), E("i", "gl"), floor=NONTEXT_MIN),
        _rows_on(CARD, _chip(f"g-chip--{_status}"), E("i", "gl"), floor=NONTEXT_MIN)]

#: Colour-bearing selectors that are deliberately not contrast rows, each
#: with its reason on the record.
EXEMPT = {
    ".card": "the card border encloses content; it identifies no state",
    ".shell": "the shell rule is the same neutral enclosure, drawn as a rule",
    ".g-node": "the node's resting border is the neutral enclosure; its "
               "states arrive in chips, never in this contour",
    ".hb__m": "measured by the tint test below; its border is the identity "
              "swatch whose accents tests/test_harness_accent_contrast.py "
              "already holds against every surface",
    '.g-compose button[type="submit"]': "the submit border encloses the "
        "control; its word runs on the inherited --ink the input row measures",
    '.g-decide button[type="submit"]': "the same enclosure on the other form",
}

_MARK_PROPS = ("color", "stroke", "fill", "outline", "border", "border-color",
               "border-top", "border-right", "border-bottom", "border-left")
_COLOURFUL = re.compile(r"var\(--(?!hb\b)[\w-]+\)|#[0-9a-fA-F]{3,8}")


def test_every_paint_declaration_is_a_measured_row_or_named_exempt():
    # The closing test the hand-written table could not offer: a new or
    # repainted colour declaration must arrive with a row or a reason.
    for rule in rules(GRAPH):
        marks = [prop for prop in rule.decls if prop in _MARK_PROPS
                 and _COLOURFUL.search(rule.decls[prop])]
        if not marks:
            continue
        assert rule.selector in MEASURED or rule.selector in EXEMPT, rule.selector


def _mark_value(win: dict, prop: str) -> str | None:
    if prop == "border-color":
        return win.get("border-color") or win.get("border")
    return win.get(prop)


def _paint(theme: str, value: str) -> tuple[int, int, int]:
    found = re.search(r"var\((--[\w-]+)\)|#[0-9a-fA-F]{6}", value)
    assert found, f"no colour in {value!r}"
    if found.group(1):
        return tokens(theme)[found.group(1)]
    return _hex_to_rgb(found.group(0))


def _surface(theme: str, chain: list, env: frozenset) -> tuple[int, int, int]:
    for depth in range(len(chain), 0, -1):
        win = computed(list(chain[:depth]), GRAPH, env)
        value = (win.get("background") or win.get("background-color", "")).strip()
        if value and value not in ("none", "transparent"):
            return _paint(theme, value)
    raise AssertionError(f"nothing under {chain} paints a surface")


@pytest.mark.parametrize("theme", THEMES)
def test_every_derived_row_clears_its_floor_in_every_environment(theme):
    for selector, specs in MEASURED.items():
        for chain, prop, floor, bg in specs:
            for label, env in environments(theme, GRAPH):
                raw = _mark_value(computed(list(chain), GRAPH, env), prop)
                assert raw, (selector, label)
                fg = _paint(theme, raw)
                under = tokens(theme)[bg] if bg else _surface(theme, chain, env)
                ratio = contrast(fg, under)
                assert ratio >= floor, (
                    f"{label}: {selector} is {ratio:.2f}:1, floor {floor}")


def _badge_tint_percent() -> float:
    win = computed(CARD + [E("span", "hb"), E("span", "hb__m")], GRAPH)
    found = re.fullmatch(
        r"color-mix\(in srgb,\s*var\(--hb\)\s*([\d.]+)%,\s*transparent\)",
        win["background"].strip())
    assert found, win["background"]
    return float(found.group(1))


@pytest.mark.parametrize("theme,field", [("dark", "accent_dark"),
                                         ("light", "accent_light")])
def test_the_monogram_stays_readable_over_every_accent_tint(theme, field):
    # The badge's surface is the accent tint the stylesheet declares —
    # the strength is read out of the sheet, so pushing it moves this
    # number — over a card or a node. Measured for every registry row.
    percent = _badge_tint_percent()
    table = tokens(theme)
    for row in harnesses.as_payload():
        accent = _hex_to_rgb(row[field])
        for surface in ("--panel", "--sunk"):
            tinted = _mix_srgb(accent, percent, table[surface])
            ratio = contrast(table["--ink"], tinted)
            assert ratio >= TEXT_MIN, (
                f"{theme}: --ink over {row['id']} tint on {surface} is {ratio:.2f}:1")


def test_the_after_line_is_muted_because_faint_ships_below_the_text_floor():
    # The one pair this window rejected: --faint on --sunk measures 3.9443:1
    # in the light theme (the panel's recorded shortfall), and the after-line
    # is a structural carrier, not a hint. Checked in every environment, so a
    # media-scoped repaint cannot re-ship the shortfall where the line is
    # actually visible.
    table = tokens("light")
    assert contrast(table["--faint"], table["--sunk"]) < TEXT_MIN
    chain = NODE + [E("span", "g-node__from")]
    for _, env in environments("light", GRAPH):
        assert computed(chain, GRAPH, env)["color"] == "var(--muted)"


def test_every_motion_the_graph_declares_sits_behind_the_reduced_motion_door():
    moved = [rule.selector for rule in rules(GRAPH)
             if ("transition" in rule.decls or "animation" in rule.decls)
             and "prefers-reduced-motion:no-preference" not in rule.context]
    assert not moved, moved
    assert "@keyframes" not in GRAPH


def test_the_graph_stylesheet_declares_only_modelled_interactive_states():
    # The same closed set the panel proves for itself: any other interactive
    # selector would sit outside every guard in this module.
    modelled = {"hover", "focus-visible", "aria-pressed"}
    # `type` keys on what a control is, not on a person touching it.
    inert = {"root", "hidden", "type"}
    for rule in rules(GRAPH):
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


def test_the_graph_stylesheet_uses_only_selector_forms_the_cascade_models():
    for rule in rules(GRAPH):
        assert not re.search(r"[>+~]", rule.selector), rule.selector
        for compound in rule.selector.split():
            assert _COMPOUND.fullmatch(compound), rule.selector


def test_focus_visible_declares_a_ring_the_focus_tests_can_stand_on():
    win = computed([E("button", states=FOCUSED)], GRAPH)
    assert win.get("outline") == "2px solid var(--accent)"
    assert win.get("outline-offset") == "2px"


@pytest.mark.parametrize("chain", [
    [E("div", "command-field"), E("input")],
    [E("div", "command-field"), E("select")],
    [E("form", "g-compose"), E("button", type="submit")],
    [E("form", "g-decide"), E("button", type="submit")],
    [E("li", "g-palette__row"), E("a", "hb__d")],
], ids=["input", "select", "compose-submit", "decide-submit", "docs-anchor"])
def test_every_form_control_declares_the_44px_minimum_target(chain):
    assert computed(chain, GRAPH).get("min-height") == "44px"
