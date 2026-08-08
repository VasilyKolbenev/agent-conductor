"""Colour measurements for the packaged panel, executed rather than asserted in prose.

The panel's palette is the owner's and is approved (plan §8.3, §8.4). What this
module measures is not the palette but the *shipped pairs*: which foreground the
panel's declarations put on which background, what each of those measures, and
whether the states stay apart when colour is taken away. Every number lives here
rather than in a comment beside a token, because a number in a comment goes
stale the moment the token changes and says nothing when it does.

A pair is a pair of *composited* colours, not of tokens. Most of the panel's
status text sits on `color-mix(<status> N%, transparent)` over a card, so the
background is neither the token nor the card but the blend of the two — and the
first version of this module measured the token, which is how nine shipped pairs
went unmeasured. Nothing here is written by hand: a row names the element and
the surface it sits on, the tint strength is read out of the stylesheet through
the cascade in tests/test_panel_cascade.py, and the ratio is computed. Push a
tint from 14% to 92% and the number moves with it.

A pair is also a pair the declarations produce in any state, not only at rest.
Hover, focus and selection redeclare paints, and a redeclared paint is a new
pair — which is how `.jump:hover` shipped an accent on a lit card that no table
here had ever measured. Every row below is therefore re-resolved under each
interactive state, and the ones that actually change colour become rows of
their own.

The arithmetic lives in tests/test_panel_colour.py, which knows nothing about
the panel. The tokens and the rules are parsed out of
`src/conductor/panel/index.html`, so changing a declaration there moves these
results. That is the point.

What a ratio here is a ratio of. Every number below is computed from the
panel's *declarations*, resolved through the cascade model in
tests/test_panel_cascade.py. Nothing is rendered and nothing is sampled off a
screen: a row names a chain of elements, this module composites the paints the
model says win for that chain, and reports the arithmetic. That is a strong
statement about what the stylesheet asks for and not a statement about what a
browser produces — a rule this model cannot express, or an element chain the
panel builds and no row here names, is invisible to all of it. `tr.click` was
exactly that until 2026-08-08. Assertions on a rendered result are §10
post-alpha work; the names below stay inside the source-level claim.
"""
import re
from typing import NamedTuple

import pytest

from tests.test_panel_cascade import (
    INTERACTIONS, E, computed, environments, panel_html, script, touched)
from tests.test_panel_colour import JND, contrast, delta_e, simulate_cvd
from tests.test_panel_style import root_declarations

# WCAG 2.1 thresholds. 1.4.3 normal text; 1.4.11 non-text and large text.
TEXT_MIN = 4.5
NONTEXT_MIN = 3.0


# ── resolving the declarations into colours ────────────────────────────────
def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    h = value.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _mix_srgb(a: tuple[int, int, int], pct: float,
              b: tuple[int, int, int]) -> tuple[int, int, int]:
    """CSS `color-mix(in srgb, a pct%, b)` — a componentwise mix in gamma sRGB."""
    f = pct / 100.0
    return tuple(round(f * x + (1 - f) * y) for x, y in zip(a, b))


_MIX = re.compile(r"color-mix\(in srgb,\s*var\((--[a-z0-9-]+)\)\s*([\d.]+)%\s*,"
                  r"\s*var\((--[a-z0-9-]+)\)\s*\)")


def tokens(theme: str) -> dict[str, tuple[int, int, int]]:
    """Resolve every colour token of one theme to RGB.

    Args:
        theme: Either ``"dark"`` or ``"light"``.

    Returns:
        Mapping of token name (with the leading dashes) to an sRGB triple.
    """
    dark, light = root_declarations()
    if theme == "light":
        decls = dict(dark, **light)
    elif theme == "dark":
        decls = dict(dark)
    else:
        raise ValueError(f"unknown theme: {theme}")

    out: dict[str, tuple[int, int, int]] = {}
    for name, raw in decls.items():
        if raw.startswith("#"):
            out[name] = _hex_to_rgb(raw)
    for name, raw in decls.items():           # one level of derivation is all we use
        if name in out:
            continue
        if m := _MIX.fullmatch(raw.strip()):
            src, pct, base = m.group(1), float(m.group(2)), m.group(3)
            if src in out and base in out:
                out[name] = _mix_srgb(out[src], pct, out[base])
        elif (m := re.fullmatch(r"var\((--[a-z0-9-]+)\)", raw.strip())) and m.group(1) in out:
            out[name] = out[m.group(1)]
    return out


_PAINT_MIX = re.compile(r"color-mix\(in srgb,\s*var\((--[a-z0-9-]+)\)\s*([\d.]+)%\s*,\s*(.+)\)")


def paint(theme: str, value: str, under: tuple | None) -> tuple[int, int, int]:
    """Resolve one CSS paint value to sRGB, compositing over ``under`` if it is
    partly transparent.

    Args:
        theme: ``"dark"`` or ``"light"``.
        value: The declaration as written in the stylesheet.
        under: The colour already on the surface, or ``None`` if nothing is.

    Returns:
        The composited sRGB triple.
    """
    value = value.strip()
    table = tokens(theme)
    if m := re.fullmatch(r"var\((--[a-z0-9-]+)\)", value):
        return table[m.group(1)]
    if value.startswith("#"):
        return _hex_to_rgb(value)
    if m := _PAINT_MIX.fullmatch(value):
        src, pct, rest = m.group(1), float(m.group(2)), m.group(3).strip()
        if rest == "transparent":
            assert under is not None, f"{value} has nothing to composite over"
            return _mix_srgb(table[src], pct, under)
        return _mix_srgb(table[src], pct, paint(theme, rest, under))
    raise AssertionError(f"the panel paints with a form this resolver cannot read: {value}")


_SURFACE_PROPS = ("background", "background-color", "fill")


def surface(theme: str, chain: list, env: frozenset = frozenset()) -> tuple[int, int, int]:
    """Composite every painted layer of an element chain, outermost first."""
    under = None
    for depth in range(1, len(chain) + 1):
        win = computed(chain[:depth], env=env)
        value = next((win[p] for p in _SURFACE_PROPS if p in win), None)
        if value is None or value in ("none", "transparent"):
            continue
        layer = paint(theme, value, under)
        alpha = float(win.get("opacity", 1))
        if alpha < 1:
            assert under is not None, "a translucent layer with nothing beneath it"
            layer = _mix_srgb(layer, alpha * 100, under)
        under = layer
    assert under is not None, f"nothing in {chain} paints a surface"
    return under


def foreground(theme: str, chain: list, prop: str,
               env: frozenset = frozenset()) -> tuple[int, int, int]:
    """Resolve the colour one element draws its own marks with.

    The element's own ``opacity`` is applied here, as :func:`surface` already
    applies it to a background. In SVG ``opacity`` dims the whole element —
    stroke as well as fill — so a mark on a translucent element is composited
    over what lies beneath that element, which is its ancestors' surface rather
    than its own. Reading opacity on the background side only recorded four
    composites the panel never rasterises.

    Args:
        theme: ``"dark"`` or ``"light"``.
        chain: Ancestors outermost first; the element itself last.
        prop: The property carrying the mark — ``color``, ``fill``, ``stroke``…
        env: The ``@media`` conditions that are true.

    Returns:
        The composited sRGB triple of the mark.
    """
    win = computed(chain, env=env)
    if prop == "border-color" and "border-color" not in win:
        shorthand = win.get("border", "")
        found = re.search(r"var\(--[a-z0-9-]+\)|#[0-9a-fA-F]{3,6}", shorthand)
        assert found, f"no border colour in {shorthand!r}"
        mark = paint(theme, found.group(0), None)
    else:
        mark = paint(theme, win[prop], None)
    alpha = float(win.get("opacity", 1))
    if alpha < 1:
        mark = _mix_srgb(mark, alpha * 100, surface(theme, list(chain[:-1]), env))
    return mark


class Tint(NamedTuple):
    """A background the panel paints outside CSS — an SVG gradient stop."""

    token: str
    pct: float
    under: tuple


def gradient_stops() -> list[tuple[str, float]]:
    """Read the contested node's two-tone fill out of mapDefs."""
    block = re.search(r'sv\("linearGradient".*?\}\)\)', panel_html(), re.S)
    stops = re.findall(r"stop-color:var\((--[a-z0-9-]+)\);stop-opacity:([\d.]+)",
                       block.group(0))
    assert len(stops) == 2, stops
    return [(token, float(alpha) * 100) for token, alpha in stops]


def background(theme: str, spec, env: frozenset = frozenset()) -> tuple[int, int, int]:
    """Resolve the background of a pair row, chain or gradient stop alike."""
    if isinstance(spec, Tint):
        return _mix_srgb(tokens(theme)[spec.token], spec.pct,
                         surface(theme, list(spec.under), env))
    return surface(theme, list(spec), env)


# ── the pairs the panel actually ships ─────────────────────────────────────
# Each row is (foreground token, background token, where it is used, threshold).
# A row exists here because the panel puts that foreground on that background,
# not because the combination is possible. Rows here are opaque token on opaque
# token; everything the panel tints lives in SHIPPED below.
TEXT_PAIRS = [
    ("--ink", "--ground", "body copy on the page", TEXT_MIN),
    ("--ink", "--panel", "card headings and rows", TEXT_MIN),
    ("--ink", "--panel-lit", "card headings on a lit card", TEXT_MIN),
    ("--ink", "--sunk", "detail card and queue cards", TEXT_MIN),
    ("--muted", "--ground", "the shell strip", TEXT_MIN),
    ("--muted", "--panel", "table cells, agent tasks", TEXT_MIN),
    ("--muted", "--panel-lit", "alert text on a lit card", TEXT_MIN),
    ("--muted", "--sunk", "queue why-text, finding detail", TEXT_MIN),
    ("--faint", "--ground", "footer, shell hints", TEXT_MIN),
    ("--faint", "--panel", "column keys, hints", TEXT_MIN),
    ("--faint", "--panel-lit", "hints on a lit card", TEXT_MIN),
    ("--faint", "--sunk", "queue card meta, detail meta, finding field keys", TEXT_MIN),
    ("--accent", "--panel", "the copy-brief button", TEXT_MIN),
    ("--pass", "--panel", "KPI value", TEXT_MIN),
    ("--wait", "--panel", "KPI value", TEXT_MIN),
    ("--wait", "--sunk", "queue card kind label", TEXT_MIN),
    ("--fail", "--panel", "KPI value, lane errors", TEXT_MIN),
    ("--fail", "--sunk", "the contested note in the detail card", TEXT_MIN),
]

# Non-text pairs that WCAG 1.4.11 covers: each of these contours is the thing
# that identifies a state, so 3:1 applies to it. Card and table borders are not
# in this table — they enclose content rather than identify a control, and the
# panel has always drawn them faint on purpose.
NONTEXT_PAIRS = [
    ("--accent", "--sunk", "running node contour, focus ring, the KPI spark", NONTEXT_MIN),
    ("--pass", "--sunk", "pass node contour", NONTEXT_MIN),
    ("--wait", "--sunk", "blocked node contour", NONTEXT_MIN),
    ("--fail", "--sunk", "fail node contour", NONTEXT_MIN),
    ("--accent", "--panel", "the selection ring around a node", NONTEXT_MIN),
    ("--faint", "--panel", "the hover ring around a node and around a findings row",
     NONTEXT_MIN),
    ("--faint", "--sunk", "the hover ring around a queue card", NONTEXT_MIN),
]

# Pairs that do NOT clear their threshold on the owner's approved values. They
# are recorded here rather than fixed, because fixing them would mean editing a
# colour the owner approved (plan §8.3) and this slice does not renegotiate the
# palette. Pinning the measured ratio means the shortfall cannot deepen without
# the suite saying so, and cannot be deleted without the deletion showing up.
# All three are the light theme; the dark theme clears every pair it ships.
#
# --accent on --sunk is kept even though it is no longer a text pair: the
# running pill's word runs on --ink and the current phase's label now does too,
# so the accent meets --sunk as a contour and a 4px bar and nowhere else, where
# 3:1 governs and 4.4972 clears. The measurement stays pinned because it is the
# owner's recorded number.
#
# Recorded to four places, not two. This is the one row where the second decimal
# answers the question: rounded to 4.50 it reads as clearing 4.5:1, and 4.4972
# does not. Rounding up hid exactly the difference that decided whether the
# phase label could stay on the accent — it could not.
KNOWN_SHORTFALLS = {
    ("light", "--faint", "--ground"): 4.2462,  # footer and shell hints, 10-12.5px
    ("light", "--faint", "--sunk"): 3.9443,    # queue card meta, detail meta, ~10.5px
    ("light", "--accent", "--sunk"): 4.4972,   # a contour and a 4px bar, not a word
}

THEMES = ("dark", "light")


# ── the composited pairs, resolved from the declarations ───────────────────
HTML_LIT = E("html", **{"data-attention": "high"})
BODY = E("body")
CARD = E("div", "card")
LIT_CARD = E("div", "card", "lit")
DETAIL = E("div", "det")
MAP_SVG = [HTML_LIT, BODY, CARD, E("svg")]


def _pill(cls: str) -> list:
    return [HTML_LIT, BODY, CARD, DETAIL, E("span", "pill", "p--" + cls)]


# Where a `.vd` chip is written, as the script writes it. "table" is the feed's
# row, which carries no class; "findings row" is the findings table's row, which
# the script builds as `el("tr", { class: "click", … })`. Modelling both rows as
# a bare `<tr>` is how `tr.click:hover td{background:var(--sunk)}` shipped: the
# rule that repainted the surface under every chip in the row could not match
# any chain this module built, so nothing here could see it.
def _vd(cls: str, where: str) -> list:
    inside = {"alert": [LIT_CARD, E("div", "alert")],
              "table": [CARD, E("table"), E("tr"), E("td")],
              "findings row": [CARD, E("table"), E("tr", "click"), E("td")],
              "expanded": [CARD, E("table"), E("tr", "detail"), E("td")],
              # An Orbit stage is a chip's fourth home, and its own surface is
              # --sunk rather than the card's --panel, which moves every tint
              # the chips are mixed into.
              "orbit stage": [CARD, E("div", "orbit"), E("div", "orb", "orb--neutral"),
                              E("div", "orb__marks")]}[where]
    return [HTML_LIT, BODY, *inside, E("span", "vd", "vd--" + cls)]


VD_PLACES = ("alert", "table", "findings row", "expanded", "orbit stage")


def _tr_classes() -> set[frozenset]:
    """The class sets the panel's script writes on a ``<tr>``, read from source.

    Each ``el("tr", {…})`` call is located and the first string literal of its
    ``class:`` entry is taken, so a row built as ``"detail" + (open ? " on" : "")``
    reports the class it always has. A source read, not a read of a built row.
    """
    out, src = set(), script()
    for match in re.finditer(r'el\("tr",\s*\{', src):
        depth, i = 1, match.end()
        while depth:
            depth += (src[i] == "{") - (src[i] == "}")
            i += 1
        found = re.search(r'class:\s*"([^"]*)"', src[match.end():i - 1])
        out.add(frozenset(found.group(1).split()) if found else frozenset())
    return out


def _node(cls: str, part: str) -> list:
    group = E("g", "node", "node--" + cls)
    return [*MAP_SVG, group, {"box": E("rect", "box"), "id": E("text", "id"),
                              "word": E("text")}[part]]


BANNER = [HTML_LIT, BODY, E("div", "banner")]
CONTESTED_FILL = [*MAP_SVG, E("g", "node", "node--contested")]


class Shipped(NamedTuple):
    """One composited pair: a mark, the surface under it, and its threshold."""

    usage: str
    fg: list
    fg_prop: str
    bg: object
    floor: float


def _chip_rows() -> list[Shipped]:
    rows = []
    for cls, sem in (("pass", "pass"), ("fail", "fail"), ("blocked", "wait"),
                     ("running", "accent"), ("contested", "fail"), ("idle", "faint")):
        chain = _pill(cls)
        rows += [
            Shipped(f"the {cls} pill's word in the detail card", chain, "color",
                    chain, TEXT_MIN),
            Shipped(f"the {cls} pill's glyph, next to its own word", chain + [E("i", "gl")],
                    "color", chain, NONTEXT_MIN),
            Shipped(f"the {cls} pill's border against the detail card", chain,
                    "border-color", chain[:-1], NONTEXT_MIN),
        ]
    for cls in ("ok", "bad", "wait", "idle", "run"):
        for where in VD_PLACES:
            chain = _vd(cls, where)
            rows += [
                Shipped(f"the {cls} chip's word in the {where}", chain, "color",
                        chain, TEXT_MIN),
                Shipped(f"the {cls} chip's glyph in the {where}", chain + [E("i", "gl")],
                        "color", chain, NONTEXT_MIN),
                Shipped(f"the {cls} chip's border in the {where}", chain, "border-color",
                        chain[:-1], NONTEXT_MIN),
            ]
    return rows


def _node_rows() -> list[Shipped]:
    rows = []
    for cls in ("pass", "fail", "blocked", "running", "idle"):
        rows += [
            Shipped(f"the node name on a {cls} node", _node(cls, "id"), "fill",
                    _node(cls, "box"), TEXT_MIN),
            Shipped(f"the status word inside a {cls} node", _node(cls, "word"), "fill",
                    _node(cls, "box"), TEXT_MIN),
            Shipped(f"the {cls} node's contour against its own fill",
                    _node(cls, "box"), "stroke", _node(cls, "box"), NONTEXT_MIN),
            Shipped(f"the {cls} node's contour against the map card",
                    _node(cls, "box"), "stroke", MAP_SVG, NONTEXT_MIN),
        ]
    for token, pct in gradient_stops():
        half = Tint(token, pct, tuple(CONTESTED_FILL))
        rows += [
            Shipped(f"the node name over the {token[2:]} half of a contested node",
                    _node("contested", "id"), "fill", half, TEXT_MIN),
            Shipped(f"the status word over the {token[2:]} half of a contested node",
                    _node("contested", "word"), "fill", half, TEXT_MIN),
            Shipped(f"the contested contour over its {token[2:]} half",
                    _node("contested", "box"), "stroke", half, NONTEXT_MIN),
        ]
    return rows


ORBIT_FIELD = [HTML_LIT, BODY, CARD, E("div", "orbit")]
ORBIT_TRACK = [*ORBIT_FIELD, E("svg")]


def _stage(tone: str) -> list:
    return [*ORBIT_FIELD, E("div", "orb", "orb--" + tone)]


def _orbit_rows() -> list[Shipped]:
    # The Orbit. A stage's contour is what identifies its state at a glance, so
    # 1.4.11's 3:1 governs it, and it is measured twice: against the stage's own
    # --sunk surface and against the --panel card the field sits on. The two
    # connection forms are measured the same way — they are the trajectory, and
    # a reader who cannot see them cannot see the cycle.
    rows = []
    for tone in ("neutral", "current", "waiting", "blocked"):
        chain = _stage(tone)
        rows += [
            Shipped(f"a {tone} stage's name inside its own box",
                    chain + [E("span", "orb__name")], "color", chain, TEXT_MIN),
            Shipped(f"a {tone} stage's contour against its own surface", chain,
                    "border-color", chain, NONTEXT_MIN),
            Shipped(f"a {tone} stage's contour against the Orbit card", chain,
                    "border-color", ORBIT_FIELD, NONTEXT_MIN),
            Shipped(f"a role id on a {tone} stage",
                    chain + [E("div", "orb__who")], "color", chain, TEXT_MIN),
            Shipped(f"the harness string on a {tone} stage",
                    chain + [E("div", "orb__who"), E("span", "orb__hn")], "color",
                    chain, TEXT_MIN),
            Shipped(f"the participant note on a {tone} stage",
                    chain + [E("div", "orb__who"), E("span", "orb__note")], "color",
                    chain, TEXT_MIN),
        ]
    for classes, what in ((("trk",), "a step of the trajectory"),
                          (("trk", "trk--next"), "the return to the first stage")):
        chain = [*ORBIT_TRACK, E("path", *classes)]
        rows.append(Shipped(f"{what} against the Orbit card", chain, "stroke",
                            ORBIT_FIELD, NONTEXT_MIN))
    rows.append(Shipped("the arrow head that gives a step its direction",
                        [*ORBIT_TRACK, E("path", "arw", "arw--orb")], "fill",
                        ORBIT_FIELD, NONTEXT_MIN))
    rows.append(Shipped("the next-Run label beside the return",
                        ORBIT_FIELD + [E("span", "nextrun")], "color", ORBIT_FIELD,
                        TEXT_MIN))
    rows.append(Shipped("the vertical link between two stacked stages",
                        ORBIT_FIELD + [E("div", "lnk"), E("i")], "border-left-color",
                        ORBIT_FIELD, NONTEXT_MIN))
    return rows


SHIPPED = _chip_rows() + _node_rows() + _orbit_rows() + [
    Shipped("the warnings headline on the banner tint", BANNER + [E("button", "banner__head")],
            "color", BANNER, TEXT_MIN),
    Shipped("the warnings glyph on the banner tint",
            BANNER + [E("button", "banner__head"), E("i", "gl")], "color", BANNER,
            NONTEXT_MIN),
    Shipped("the expand hint on the banner tint",
            BANNER + [E("button", "banner__head"), E("span", "banner__hint")], "color",
            BANNER, TEXT_MIN),
    Shipped("a warning line on the banner tint", BANNER + [E("ul", "banner__list")],
            "color", BANNER, TEXT_MIN),
    Shipped("the banner's border against the page", BANNER, "border-color",
            [HTML_LIT, BODY], NONTEXT_MIN),
    Shipped("the see-findings link on a lit alert card",
            [HTML_LIT, BODY, LIT_CARD, E("div", "alert"), E("button", "jump")], "color",
            [HTML_LIT, BODY, LIT_CARD], TEXT_MIN),
    Shipped("the copy-brief button on a queue card",
            [HTML_LIT, BODY, LIT_CARD, E("li", "ask"), E("button", "copy")], "color",
            [HTML_LIT, BODY, LIT_CARD, E("li", "ask"), E("button", "copy")], TEXT_MIN),
]


def measure(theme: str, pairs: list) -> list[tuple[str, str, str, float, float]]:
    """Measure every pair of one token table in one theme.

    Args:
        theme: ``"dark"`` or ``"light"``.
        pairs: Rows of ``(fg token, bg token, usage, threshold)``.

    Returns:
        Rows of ``(fg, bg, usage, ratio, threshold)``.
    """
    t = tokens(theme)
    return [(fg, bg, use, contrast(t[fg], t[bg]), floor) for fg, bg, use, floor in pairs]


def measure_shipped(theme: str, row: Shipped, env: frozenset = frozenset()) -> float:
    """Composite one shipped row and return its contrast ratio."""
    return contrast(foreground(theme, row.fg, row.fg_prop, env),
                    background(theme, row.bg, env))


# ── the pairs interaction creates ──────────────────────────────────────────
def _touch(spec, interaction: str):
    """Put one interactive state on a chain or on the chain under a tint."""
    if isinstance(spec, Tint):
        return spec._replace(under=tuple(touched(spec.under, interaction)))
    return touched(spec, interaction)


def _interactive_rows() -> list[Shipped]:
    """Every shipped row that an interactive state repaints, as its own row.

    Derived rather than listed: each row is re-resolved under hover, focus and
    selection, and a row appears here only when the resolved colours actually
    move. So a rule added to `:hover` tomorrow brings its own measurement with
    it, and a resting row that no interaction touches costs nothing.
    """
    rows = []
    for row in SHIPPED:
        for interaction in sorted(INTERACTIONS):
            touched_row = row._replace(
                usage=f"{row.usage} — under {interaction}",
                fg=_touch(row.fg, interaction), bg=_touch(row.bg, interaction))
            moved = False
            for theme in THEMES:
                for _, env in environments(theme):
                    resting = (foreground(theme, row.fg, row.fg_prop, env),
                               background(theme, row.bg, env))
                    now = (foreground(theme, touched_row.fg, touched_row.fg_prop, env),
                           background(theme, touched_row.bg, env))
                    moved = moved or now != resting
            if moved:
                rows.append(touched_row)
    return rows


# Composited pairs that do not clear the threshold their row names, recorded
# with the measurement instead of being asserted or dropped.
#
# All four are the idle node's contour, which is --line: the same neutral
# enclosure the panel draws around every card, deliberately faint. What
# identifies an idle node is the dash pattern, the dimmed fill, the "·" glyph
# and the word "idle" — none of which is a contrast question — so the stroke
# here encloses rather than identifies, the case the non-text table already
# excludes for card borders. Recorded so the reasoning is visible and the
# numbers cannot drift; the pin is two-sided, as for the token shortfalls.
#
# The numbers moved on 2026-08-07 and the shapes did not. `.node--idle .box`
# carries `opacity:.65`, and in SVG that dims the stroke as well as the fill;
# foreground() read it on the fill side only, so these four recorded the ratio
# between a full-strength contour and a correctly dimmed surface — a pair the
# panel never rasterises. Reading opacity on both sides is what changed them.
RECORDED_COMPOSITES = {
    ("the idle node's contour against its own fill", "dark"): 1.22,
    ("the idle node's contour against its own fill", "light"): 1.11,
    ("the idle node's contour against the map card", "dark"): 1.18,
    ("the idle node's contour against the map card", "light"): 1.23,
}


@pytest.mark.parametrize("theme", THEMES)
def test_every_token_the_panel_declares_resolves_to_a_colour(theme):
    t = tokens(theme)
    for name in ("--ground", "--panel", "--sunk", "--line", "--ink", "--muted", "--faint",
                 "--accent", "--pass", "--wait", "--fail", "--panel-lit", "--contour-lit"):
        assert name in t, f"{theme}: {name} did not resolve"


@pytest.mark.parametrize("theme", THEMES)
def test_the_palette_in_the_panel_is_still_the_one_the_owner_approved(theme):
    # The values are the owner's (plan §8.3, §8.4). Pinned so a redesign cannot
    # quietly restyle an approved decision.
    approved = {
        "dark": {"--ground": "#07090D", "--panel": "#10141B", "--sunk": "#0B0E14",
                 "--line": "#262D38", "--ink": "#F3F6F8", "--muted": "#B9C2CC",
                 "--faint": "#7F8A98", "--accent": "#E44955", "--pass": "#3fa86a",
                 "--wait": "#c9971f", "--fail": "#e0703a"},
        "light": {"--ground": "#f3f5f7", "--panel": "#ffffff", "--sunk": "#e9edf1",
                  "--line": "#d5dce4", "--ink": "#11161d", "--muted": "#4e5965",
                  "--faint": "#697684", "--accent": "#c92f42", "--pass": "#247a4b",
                  "--wait": "#8a6500", "--fail": "#b42318"},
    }[theme]
    t = tokens(theme)
    for name, value in approved.items():
        assert t[name] == _hex_to_rgb(value), f"{theme}: {name} moved off the approved value"


@pytest.mark.parametrize("theme", THEMES)
def test_every_text_pair_of_two_opaque_tokens_clears_the_threshold_or_is_recorded(theme):
    short = [(fg, bg, use, round(ratio, 2)) for fg, bg, use, ratio, floor
             in measure(theme, TEXT_PAIRS)
             if ratio < floor and (theme, fg, bg) not in KNOWN_SHORTFALLS]
    assert not short, f"{theme}: below {TEXT_MIN}:1 and not recorded — {short}"


@pytest.mark.parametrize("theme,fg,bg", [k for k in KNOWN_SHORTFALLS])
def test_each_recorded_shortfall_still_measures_what_it_was_recorded_at(theme, fg, bg):
    # These three are open questions for the owner, not settled results. The
    # assertion is two-sided on purpose: it fails if the shortfall gets worse,
    # and it fails if someone repairs it without moving the number here.
    t = tokens(theme)
    ratio = contrast(t[fg], t[bg])
    assert ratio < TEXT_MIN, f"{theme} {fg} on {bg} now clears {TEXT_MIN}:1 at {ratio:.4f}"
    assert round(ratio, 4) == KNOWN_SHORTFALLS[(theme, fg, bg)]


@pytest.mark.parametrize("theme", THEMES)
def test_every_contour_that_identifies_a_state_clears_the_non_text_threshold(theme):
    short = [(fg, bg, use, round(ratio, 2)) for fg, bg, use, ratio, floor
             in measure(theme, NONTEXT_PAIRS) if ratio < floor]
    assert not short, f"{theme}: below {NONTEXT_MIN}:1 — {short}"


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("row", SHIPPED, ids=lambda r: r.usage)
def test_every_mark_the_declarations_composite_to_clears_the_threshold_governing_it(
        theme, row):
    # The composited half of the measurement contour. A chip's word is text and
    # answers to 4.5:1; its glyph and its border sit beside that word saying the
    # same thing, so 1.4.11's 3:1 is what governs them. Nothing is exempt: every
    # row below is resolved through the cascade, tint strengths included, and
    # once for every media environment the stylesheet declares — a rule that
    # only applies below 1000px still declares something a reader has to read.
    #
    # The name used to say "the panel composites", which reads as a claim about
    # rasterised output. The compositing is this module's arithmetic over the
    # declarations the cascade model resolves; a mark on a chain no row names is
    # not measured at all, and that is the limit the module docstring states.
    if (row.usage, theme) in RECORDED_COMPOSITES:
        pytest.skip("recorded below threshold — see test_each_recorded_composite_...")
    for label, env in environments(theme):
        ratio = measure_shipped(theme, row, env)
        assert ratio >= row.floor, (
            f"{label}: {row.usage} is {ratio:.2f}:1, floor {row.floor}")


# Which shipped marks an interactive state repaints. Empty, and the emptiness
# is the result: hover declares the map's outer ring, the queue card's outer
# ring and the findings row's outer ring, focus declares the outline, selection
# declares the ring — all of them outside every mark measured above. One hover
# does move a colour rather than add a ring: `.copy:hover` takes the copy
# button's border from --line to --accent. It leaves the button's word alone,
# and the border encloses the control rather than identifying a state, which is
# the line NONTEXT_PAIRS already draws — so no measured mark moves under it.
# `.jump:hover` used to be in this list at 4.33:1 against a lit card, which is
# what the list is for. Two-sided for the marks the tables above name: an
# interaction that repaints one of them appears here and fails until it is
# measured and named.
REPAINTED_BY_INTERACTION = ()


def test_the_only_marks_an_interaction_repaints_are_the_ones_recorded_here():
    assert tuple(row.usage for row in _interactive_rows()) == REPAINTED_BY_INTERACTION


def test_every_row_class_the_script_writes_is_a_row_this_module_measures():
    # The list above is only as wide as the chains this module builds, and the
    # chains are hand-written. This closes the gap the shipped defect went
    # through: the findings table's row is `el("tr", { class: "click", … })`, the
    # chip chains modelled it as a bare `<tr>`, and so `tr.click:hover` matched
    # nothing here. Read out of the script rather than listed, so the next row
    # class the panel starts writing has to arrive with a chain of its own.
    modelled = {frozenset(el.classes) for where in VD_PLACES
                for el in _vd("ok", where) if el.tag == "tr"}
    assert _tr_classes() <= modelled, _tr_classes() - modelled


@pytest.mark.parametrize("interaction", sorted(INTERACTIONS))
@pytest.mark.parametrize("where", VD_PLACES)
def test_no_interaction_moves_the_surface_a_status_chip_is_mixed_into(where, interaction):
    # The targeted form of the rule the findings row broke. A chip's background
    # is `color-mix(<status> N%, transparent)`, so the surface beneath it is
    # part of the chip's own colour and of every ratio measured against it:
    # `tr.click:hover td{background:var(--sunk)}` moved that surface for ten
    # marks at once, and in Winter Daylight it took the wait chip's glyph from
    # 4.2759:1 to 3.6919:1 — above the 3:1 that governs a glyph, and still a
    # sixth of the contrast of a mark that identifies a state. Held as an
    # equality of composited colours, so the interaction cannot move the surface
    # in either direction, and held over the cell as well as over the chip: a
    # rule repainting either one fails here by arithmetic, not by spelling.
    for cls in ("ok", "bad", "wait", "idle"):
        chain = _vd(cls, where)
        for theme in THEMES:
            for label, env in environments(theme):
                for depth in (len(chain), len(chain) - 1):
                    assert background(theme, _touch(chain[:depth], interaction), env) == \
                        background(theme, chain[:depth], env), (cls, where, label, theme)


@pytest.mark.parametrize("interaction", sorted(INTERACTIONS))
@pytest.mark.parametrize("theme", THEMES)
def test_every_mark_an_interaction_repaints_clears_its_threshold_too(theme, interaction):
    # WCAG exempts no state, and this is the round that moved the accent onto
    # :hover — `.jump:hover{color:var(--accent)}` shipped an accent on a lit
    # card at 12.5px in no table at all. A pointer resting on an element is
    # still the element, so every row above is measured again under it.
    for row in SHIPPED:
        if (row.usage, theme) in RECORDED_COMPOSITES:
            continue
        held = row._replace(fg=_touch(row.fg, interaction), bg=_touch(row.bg, interaction))
        for label, env in environments(theme):
            ratio = measure_shipped(theme, held, env)
            assert ratio >= row.floor, (
                f"{label}: {row.usage} under {interaction} is {ratio:.2f}:1, "
                f"floor {row.floor}")


@pytest.mark.parametrize("usage,theme", [k for k in RECORDED_COMPOSITES])
def test_each_recorded_composite_still_measures_what_it_was_recorded_at(usage, theme):
    # Two-sided, like the token shortfalls: it fails if the pair gets worse and
    # it fails if someone repairs it without moving the number recorded here.
    row = next(r for r in SHIPPED if r.usage == usage)
    ratio = measure_shipped(theme, row)
    assert ratio < row.floor, f"{theme}: {usage} now clears {row.floor} at {ratio:.2f}"
    assert round(ratio, 2) == RECORDED_COMPOSITES[(usage, theme)]


@pytest.mark.parametrize("interaction", [None, *sorted(INTERACTIONS)])
@pytest.mark.parametrize("theme", THEMES)
def test_no_chip_says_its_status_with_colour_alone(theme, interaction):
    # Moving chip words onto --ink is only safe because the status keeps two
    # other carriers. If a chip ever lost both, the word would be all that is
    # left and the colour channel would be gone entirely. Held under the pointer
    # as well as at rest: a hover rule collapsing the glyph onto the word colour
    # takes the same carrier away, and used to do it with this test passing.
    for build, classes in ((_pill, ("pass", "fail", "blocked", "running", "idle")),
                           (lambda c: _vd(c, "alert"), ("ok", "bad", "wait", "idle"))):
        for cls in classes:
            chain = touched(build(cls), interaction)
            glyph = foreground(theme, chain + touched([E("i", "gl")], interaction), "color")
            border = foreground(theme, chain, "border-color")
            word = foreground(theme, chain, "color")
            assert glyph != word and border != word, (cls, interaction)


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("surf", ["--panel", "--sunk"])
@pytest.mark.parametrize("token", ["--fail", "--wait"])
def test_fail_and_wait_are_each_legible_on_both_card_surfaces(theme, surf, token):
    # Required explicitly by the slice: each of fail and wait against each of
    # panel and sunk, in both themes. All eight clear the threshold.
    t = tokens(theme)
    ratio = contrast(t[token], t[surf])
    assert ratio >= TEXT_MIN, f"{theme}: {token} on {surf} is {ratio:.2f}:1"


# The lit contour against the lit surface, measured rather than left out. It is
# below 1.4.11's 3:1 in both themes and is recorded that way: the light level is
# an emphasis on a card that already says everything it says in words, so no
# information is lost if a reader cannot see the contour change. Whether that
# reasoning is accepted is the owner's call, and it is written down here so the
# call can be made on a number.
LIT_CONTOUR = {"dark": 2.39, "light": 2.18}


@pytest.mark.parametrize("theme", THEMES)
def test_the_lit_contour_is_measured_and_recorded_below_the_non_text_threshold(theme):
    t = tokens(theme)
    ratio = contrast(t["--contour-lit"], t["--panel-lit"])
    assert round(ratio, 2) == LIT_CONTOUR[theme]
    assert ratio < NONTEXT_MIN, f"{theme}: {ratio:.2f} now clears {NONTEXT_MIN}"


# How much brighter the lit contour is than the resting one against the same
# surface. Written as two numbers because "roughly doubles" was true of one
# theme and not of the other, and an assertion of `> 1.5` was quietly weaker
# than the sentence above it.
LIT_GAIN = {"dark": 1.96, "light": 1.58}


@pytest.mark.parametrize("theme", THEMES)
def test_a_lit_card_reads_as_lit_because_its_contour_gains_real_contrast(theme):
    t = tokens(theme)
    resting = contrast(t["--line"], t["--panel-lit"])
    lit = contrast(t["--contour-lit"], t["--panel-lit"])
    assert round(lit / resting, 2) == LIT_GAIN[theme]


# ── accent against fail, measured rather than estimated ────────────────────
# Plan §8.3 carried a coordinator's *estimate* of roughly 1.24:1 between the
# light accent and the light fail. Measured, it is 1.2425:1 — the estimate was
# right, and it is now a computation instead of a recollection.
ACCENT_FAIL_RATIO = {"dark": 1.22, "light": 1.24}


@pytest.mark.parametrize("theme", THEMES)
def test_accent_and_fail_are_nearly_the_same_lightness_in_both_themes(theme):
    t = tokens(theme)
    ratio = contrast(t["--accent"], t["--fail"])
    assert round(ratio, 2) == ACCENT_FAIL_RATIO[theme]
    assert ratio < 1.3, "the two reds are close enough that lightness cannot separate them"


# ── colour-vision deficiency ───────────────────────────────────────────────
# The CIE76 dE*ab between fail and wait as a dichromat sees them. A difference
# under about 2.3 is the standard just-noticeable-difference floor: below it the
# two are the same colour. These are measurements of the owner's approved
# palette, recorded as facts; the palette is not reopened by them. The floor
# itself and the arithmetic live in tests/test_panel_colour.py.
CVD_FAIL_WAIT = {
    ("dark", "protanopia"): 19.9,
    ("dark", "deuteranopia"): 11.1,
    ("light", "protanopia"): 17.3,
    ("light", "deuteranopia"): 1.5,
}


@pytest.mark.parametrize("theme,kind", [k for k in CVD_FAIL_WAIT])
def test_the_measured_distance_between_fail_and_wait_under_cvd_is_what_was_recorded(theme, kind):
    t = tokens(theme)
    measured = delta_e(simulate_cvd(t["--fail"], kind), simulate_cvd(t["--wait"], kind))
    assert round(measured, 1) == CVD_FAIL_WAIT[(theme, kind)]


def test_fail_and_wait_become_the_same_colour_under_deuteranopia_in_the_light_theme():
    # The strongest evidence in this module that the glyph/text/shape rule is
    # load-bearing rather than decorative. Under deuteranopia the light theme's
    # fail #b42318 and wait #8a6500 both render near #707000/#737300 — apart by
    # less than the just-noticeable difference. For those users, colour carries
    # nothing here and every bit of the distinction is carried by the glyph and
    # the spelt-out label.
    t = tokens("light")
    measured = delta_e(simulate_cvd(t["--fail"], "deuteranopia"),
                       simulate_cvd(t["--wait"], "deuteranopia"))
    assert measured < JND, f"measured {measured:.2f}"


def test_fail_and_wait_stay_apart_under_protanopia_in_both_themes():
    for theme in THEMES:
        t = tokens(theme)
        measured = delta_e(simulate_cvd(t["--fail"], "protanopia"),
                           simulate_cvd(t["--wait"], "protanopia"))
        assert measured > JND * 4, f"{theme}: {measured:.2f}"
