"""Colour measurements for the packaged panel, executed rather than asserted in prose.

The panel's palette is the owner's and is approved (plan §8.3, §8.4). What this
module measures is not the palette but the *shipped pairs*: which foreground the
panel actually puts on which background, what each of those measures, and
whether the states stay apart when colour is taken away. Every number lives here
rather than in a comment beside a token, because a number in a comment goes
stale the moment the token changes and says nothing when it does.

A pair is a pair of *composited* colours, not of tokens. Most of the panel's
status text sits on `color-mix(<status> N%, transparent)` over a card, so the
background is neither the token nor the card but the blend of the two — and the
first version of this module measured the token, which is how nine shipped pairs
went unmeasured. Nothing here is written by hand: a row names the element and
the surface it sits on, the tint strength is read out of the stylesheet through
the cascade in tests/test_panel_style.py, and the ratio is computed. Push a tint
from 14% to 92% and the number moves with it.

The tokens and the rules are parsed out of `src/conductor/panel/index.html`, so
changing a declaration there moves these results. That is the point.
"""
import re
from typing import NamedTuple

import pytest

from tests.test_panel_style import E, computed, panel_html, root_declarations

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


def surface(theme: str, chain: list) -> tuple[int, int, int]:
    """Composite every painted layer of an element chain, outermost first."""
    under = None
    for depth in range(1, len(chain) + 1):
        win = computed(chain[:depth])
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


def foreground(theme: str, chain: list, prop: str) -> tuple[int, int, int]:
    """Resolve the colour one element draws its own marks with."""
    win = computed(chain)
    if prop == "border-color" and "border-color" not in win:
        shorthand = win.get("border", "")
        found = re.search(r"var\(--[a-z0-9-]+\)|#[0-9a-fA-F]{3,6}", shorthand)
        assert found, f"no border colour in {shorthand!r}"
        return paint(theme, found.group(0), None)
    return paint(theme, win[prop], None)


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


def background(theme: str, spec) -> tuple[int, int, int]:
    """Resolve the background of a pair row, chain or gradient stop alike."""
    if isinstance(spec, Tint):
        return _mix_srgb(tokens(theme)[spec.token], spec.pct,
                         surface(theme, list(spec.under)))
    return surface(theme, list(spec))


# ── colorimetry ────────────────────────────────────────────────────────────
def _linear(channel: int) -> float:
    c = channel / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(rgb: tuple[int, int, int]) -> float:
    """Relative luminance per WCAG 2.1."""
    r, g, b = (_linear(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(fg: tuple[int, int, int], bg: tuple[int, int, int]) -> float:
    """Contrast ratio per WCAG 2.1, always >= 1."""
    a, b = luminance(fg), luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def _to_lab(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    r, g, b = (_linear(c) for c in rgb)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def delta_e(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    """CIE76 dE*ab between two sRGB colours.

    CIE76 is used because it is exactly defined and reproducible from the
    formula alone. It is not the most perceptually even metric available, and
    for the muted yellow-greens that fail and wait become under simulated
    dichromacy it tends to *understate* rather than overstate the gap — so the
    small number recorded below is a conservative reading of how close those
    two get, not a flattering one.
    """
    la, aa, ba = _to_lab(a)
    lb, ab, bb = _to_lab(b)
    return ((la - lb) ** 2 + (aa - ab) ** 2 + (ba - bb) ** 2) ** 0.5


# Viénot, Brettel & Mollon (1999) dichromat simulation, applied in linear RGB
# through the Hunt-Pointer-Estevez LMS space.
_RGB_LMS = ((0.31399022, 0.63951294, 0.04649755),
            (0.15537241, 0.75789446, 0.08670142),
            (0.01775239, 0.10944209, 0.87256922))
_LMS_RGB = ((5.47221206, -4.64196010, 0.16963708),
            (-1.12524190, 2.29317094, -0.16789520),
            (0.02980165, -0.19318073, 1.16364789))


def simulate_cvd(rgb: tuple[int, int, int], kind: str) -> tuple[int, int, int]:
    """Simulate how a dichromat sees an sRGB colour.

    Args:
        rgb: The colour as an sRGB triple.
        kind: ``"protanopia"`` (no L cone) or ``"deuteranopia"`` (no M cone).

    Returns:
        The simulated colour as an sRGB triple.
    """
    lin = [_linear(c) for c in rgb]
    lms = [sum(row[i] * lin[i] for i in range(3)) for row in _RGB_LMS]
    if kind == "protanopia":
        lms[0] = 1.05118294 * lms[1] - 0.05116099 * lms[2]
    elif kind == "deuteranopia":
        lms[1] = 0.95130920 * lms[0] + 0.04866992 * lms[2]
    else:
        raise ValueError(f"unknown deficiency: {kind}")
    out = [sum(row[i] * lms[i] for i in range(3)) for row in _LMS_RGB]

    def encode(c: float) -> int:
        c = min(1.0, max(0.0, c))
        s = 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
        return round(min(1.0, max(0.0, s)) * 255)

    return tuple(encode(c) for c in out)


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
    ("--faint", "--panel", "the hover ring around a node", NONTEXT_MIN),
]

# Pairs that do NOT clear their threshold on the owner's approved values. They
# are recorded here rather than fixed, because fixing them would mean editing a
# colour the owner approved (plan §8.3) and this slice does not renegotiate the
# palette. Pinning the measured ratio means the shortfall cannot deepen without
# the suite saying so, and cannot be deleted without the deletion showing up.
# All three are the light theme; the dark theme clears every pair it ships.
#
# --accent on --sunk is kept even though it is no longer a text pair: after the
# fix round the running pill's word runs on --ink, so the accent meets --sunk
# only as a contour and a 4px bar, where 3:1 governs and 4.50 clears. The
# measurement stays pinned because it is the owner's recorded number.
KNOWN_SHORTFALLS = {
    ("light", "--faint", "--ground"): 4.25,   # footer and shell hints, 10-12.5px
    ("light", "--faint", "--sunk"): 3.94,     # queue card meta and detail meta, ~10.5px
    ("light", "--accent", "--sunk"): 4.50,    # now a contour, not a word
}

THEMES = ("dark", "light")


# ── the composited pairs: what a reader's eye actually receives ────────────
HTML_LIT = E("html", **{"data-attention": "high"})
BODY = E("body")
CARD = E("div", "card")
LIT_CARD = E("div", "card", "lit")
DETAIL = E("div", "det")
MAP_SVG = [HTML_LIT, BODY, CARD, E("svg")]


def _pill(cls: str) -> list:
    return [HTML_LIT, BODY, CARD, DETAIL, E("span", "pill", "p--" + cls)]


def _vd(cls: str, where: str) -> list:
    inside = {"alert": [LIT_CARD, E("div", "alert")],
              "table": [CARD, E("table"), E("tr"), E("td")],
              "expanded": [CARD, E("table"), E("tr", "detail"), E("td")]}[where]
    return [HTML_LIT, BODY, *inside, E("span", "vd", "vd--" + cls)]


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
    for cls in ("ok", "bad", "wait", "idle"):
        for where in ("alert", "table", "expanded"):
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


SHIPPED = _chip_rows() + _node_rows() + [
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


def measure_shipped(theme: str, row: Shipped) -> float:
    """Composite one shipped row and return its contrast ratio."""
    return contrast(foreground(theme, row.fg, row.fg_prop), background(theme, row.bg))


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
RECORDED_COMPOSITES = {
    ("the idle node's contour against its own fill", "dark"): 1.37,
    ("the idle node's contour against its own fill", "light"): 1.24,
    ("the idle node's contour against the map card", "dark"): 1.33,
    ("the idle node's contour against the map card", "light"): 1.38,
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
    assert ratio < TEXT_MIN, f"{theme} {fg} on {bg} now clears {TEXT_MIN}:1 at {ratio:.2f}"
    assert round(ratio, 2) == KNOWN_SHORTFALLS[(theme, fg, bg)]


@pytest.mark.parametrize("theme", THEMES)
def test_every_contour_that_identifies_a_state_clears_the_non_text_threshold(theme):
    short = [(fg, bg, use, round(ratio, 2)) for fg, bg, use, ratio, floor
             in measure(theme, NONTEXT_PAIRS) if ratio < floor]
    assert not short, f"{theme}: below {NONTEXT_MIN}:1 — {short}"


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("row", SHIPPED, ids=lambda r: r.usage)
def test_every_mark_the_panel_composites_clears_the_threshold_that_governs_it(theme, row):
    # The composited half of the measurement contour. A chip's word is text and
    # answers to 4.5:1; its glyph and its border sit beside that word saying the
    # same thing, so 1.4.11's 3:1 is what governs them. Nothing is exempt: every
    # row below is resolved through the cascade, tint strengths included.
    if (row.usage, theme) in RECORDED_COMPOSITES:
        pytest.skip("recorded below threshold — see test_each_recorded_composite_...")
    ratio = measure_shipped(theme, row)
    assert ratio >= row.floor, f"{theme}: {row.usage} is {ratio:.2f}:1, floor {row.floor}"


@pytest.mark.parametrize("usage,theme", [k for k in RECORDED_COMPOSITES])
def test_each_recorded_composite_still_measures_what_it_was_recorded_at(usage, theme):
    # Two-sided, like the token shortfalls: it fails if the pair gets worse and
    # it fails if someone repairs it without moving the number recorded here.
    row = next(r for r in SHIPPED if r.usage == usage)
    ratio = measure_shipped(theme, row)
    assert ratio < row.floor, f"{theme}: {usage} now clears {row.floor} at {ratio:.2f}"
    assert round(ratio, 2) == RECORDED_COMPOSITES[(usage, theme)]


@pytest.mark.parametrize("theme", THEMES)
def test_no_chip_says_its_status_with_colour_alone(theme):
    # Moving chip words onto --ink is only safe because the status keeps two
    # other carriers. If a chip ever lost both, the word would be all that is
    # left and the colour channel would be gone entirely.
    for cls in ("pass", "fail", "blocked", "running", "idle"):
        chain = _pill(cls)
        glyph = foreground(theme, chain + [E("i", "gl")], "color")
        border = foreground(theme, chain, "border-color")
        word = foreground(theme, chain, "color")
        assert glyph != word and border != word, cls


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
# palette, recorded as facts; the palette is not reopened by them.
JND = 2.3
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
