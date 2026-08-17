"""graph.css, read through the panel's cascade model rather than grepped.

The Graph window restates the December palette (tests/test_graph_source.py
holds the copy value-for-value), so the token arithmetic lives on the panel's
own tables and this module asks only the graph-specific questions: which pairs
THIS stylesheet ships, whether its motion sits behind the reduced-motion door,
whether its interactive states are ones the cascade model knows, and whether
its controls hold the 44px floor. Everything is resolved through
tests/test_panel_cascade.py against graph.css handed in as source, so a rule
added there tomorrow is read by the same machinery that reads the panel.
"""
import re
from pathlib import Path

import pytest

from conductor import harnesses
from tests.test_panel_cascade import E, _COMPOUND, _TOKEN, computed, rules
from tests.test_panel_colour import contrast
from tests.test_panel_contrast import NONTEXT_MIN, TEXT_MIN, _hex_to_rgb, _mix_srgb, tokens

PANEL = Path(__file__).resolve().parents[1] / "src" / "conductor" / "panel"
#: graph.css wrapped the way the cascade module reads a panel: one style block,
#: one (empty) script block.
GRAPH = ("<style>" + (PANEL / "graph.css").read_text(encoding="utf-8")
         + "</style><script></script>")
THEMES = ("dark", "light")

#: Every text pair the graph window puts on an opaque surface, as
#: (foreground token, background token, where). The backgrounds are tokens
#: because every graph surface is one — the only tint in this stylesheet is
#: the badge's 14% accent, measured separately below.
TEXT_PAIRS = [
    ("--ink", "--ground", "body copy on the page"),
    ("--muted", "--ground", "run facts and the shell notice"),
    ("--ink", "--panel", "card headings, chip words in the rail"),
    ("--muted", "--panel", "field labels, badge names in the rail"),
    ("--faint", "--panel", "section keys, notes, timeline instants"),
    ("--ink", "--sunk", "node titles, chip words on a node, input text"),
    ("--muted", "--sunk", "the after-line on a node, badge names on a node"),
    ("--muted", "--panel", "the none chip's word in the rail"),
]

#: Non-text marks: glyphs and contours that identify a state, and the two
#: structural strokes. WCAG 1.4.11's 3:1 governs them.
NONTEXT_PAIRS = [
    ("--pass", "--sunk", "pass glyphs and contours on a node"),
    ("--wait", "--sunk", "wait glyphs and contours on a node"),
    ("--fail", "--sunk", "fail glyphs and contours on a node"),
    ("--pass", "--panel", "pass glyphs and contours in the rail"),
    ("--wait", "--panel", "wait glyphs and contours in the rail"),
    ("--fail", "--panel", "fail glyphs and contours in the rail"),
    ("--faint", "--sunk", "the none chip's glyph on a node"),
    ("--faint", "--panel", "the none chip's glyph in the rail, the edge stroke"),
    ("--accent", "--ground", "the focus ring on the page"),
    ("--accent", "--panel", "the focus ring on a card"),
    ("--accent", "--sunk", "the focus ring on a node or an input"),
    ("--ink", "--sunk", "the selected node's contour"),
]


@pytest.mark.parametrize("theme", THEMES)
def test_every_graph_text_pair_clears_the_text_floor(theme):
    table = tokens(theme)
    short = [(fg, bg, use, round(contrast(table[fg], table[bg]), 2))
             for fg, bg, use in TEXT_PAIRS
             if contrast(table[fg], table[bg]) < TEXT_MIN]
    assert not short, f"{theme}: below {TEXT_MIN}:1 — {short}"


@pytest.mark.parametrize("theme", THEMES)
def test_every_graph_state_mark_clears_the_non_text_floor(theme):
    table = tokens(theme)
    short = [(fg, bg, use, round(contrast(table[fg], table[bg]), 2))
             for fg, bg, use in NONTEXT_PAIRS
             if contrast(table[fg], table[bg]) < NONTEXT_MIN]
    assert not short, f"{theme}: below {NONTEXT_MIN}:1 — {short}"


def test_the_after_line_is_muted_because_faint_ships_below_the_text_floor():
    # The one pair this window rejected: --faint on --sunk measures 3.9443:1
    # in the light theme (the panel's recorded shortfall), and the after-line
    # is a structural carrier, not a hint. Held from both sides: the shortfall
    # is real, and the carrier does not use the token that ships it.
    table = tokens("light")
    assert contrast(table["--faint"], table["--sunk"]) < TEXT_MIN
    win = computed([E("button", "g-node"), E("span", "g-node__from")], GRAPH)
    assert win["color"] == "var(--muted)"


@pytest.mark.parametrize("theme,field", [("dark", "accent_dark"),
                                         ("light", "accent_light")])
def test_the_monogram_stays_readable_over_every_accent_tint(theme, field):
    # The badge's surface is `color-mix(accent 14%, transparent)` over a card
    # or a node, so the worst monogram pair is --ink over the strongest
    # accent tint on the darker surface. Measured for every registry row: a
    # new accent lands with its own number, not with a hope.
    table = tokens(theme)
    for row in harnesses.as_payload():
        accent = _hex_to_rgb(row[field])
        for surface in ("--panel", "--sunk"):
            tinted = _mix_srgb(accent, 14, table[surface])
            ratio = contrast(table["--ink"], tinted)
            assert ratio >= TEXT_MIN, (
                f"{theme}: --ink over {row['id']} tint on {surface} is {ratio:.2f}:1")


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
    win = computed([E("button", states=("focus-visible",))], GRAPH)
    assert win.get("outline") == "2px solid var(--accent)"
    assert win.get("outline-offset") == "2px"


@pytest.mark.parametrize("chain", [
    [E("div", "command-field"), E("input")],
    [E("div", "command-field"), E("select")],
    [E("form", "g-compose"), E("button", type="submit")],
    [E("form", "g-decide"), E("button", type="submit")],
], ids=["input", "select", "compose-submit", "decide-submit"])
def test_every_form_control_declares_the_44px_minimum_target(chain):
    assert computed(chain, GRAPH).get("min-height") == "44px"
