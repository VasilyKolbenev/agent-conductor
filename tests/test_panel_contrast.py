"""Colour measurements for the packaged panel, executed rather than asserted in prose.

The panel's palette is the owner's and is approved (plan §8.3, §8.4). What this
module measures is not the palette but the *shipped pairs*: which foreground the
panel actually puts on which background, what each of those measures, and whether
the states stay apart when colour is taken away. Every number lives here rather
than in a comment beside a token, because a number in a comment goes stale the
moment the token changes and says nothing when it does.

The tokens are parsed out of `src/conductor/panel/index.html`, so changing a
declaration there moves these results. That is the point.
"""
import re
from pathlib import Path

import pytest

PANEL = Path(__file__).resolve().parents[1] / "src" / "conductor" / "panel" / "index.html"

# WCAG 2.1 thresholds. 1.4.3 normal text; 1.4.11 non-text and large text.
TEXT_MIN = 4.5
NONTEXT_MIN = 3.0


# ── parsing the declarations out of the panel ──────────────────────────────
def panel_html() -> str:
    """Return the packaged panel source."""
    return PANEL.read_text(encoding="utf-8")


def _declarations(block: str) -> dict[str, str]:
    return {m.group(1): m.group(2).strip()
            for m in re.finditer(r"(--[a-z0-9-]+)\s*:\s*([^;}]+)", block)}


def _root_blocks(html: str) -> tuple[str, str]:
    """Return the dark `:root` body and the light-media `:root` body."""
    light = re.search(r"@media\s*\(prefers-color-scheme:light\)\s*\{:root\{(.*?)\}\}",
                      html, re.S)
    dark = re.search(r"^:root\{(.*?)\n\}", html, re.S | re.M)
    if not (light and dark):
        raise AssertionError("panel no longer declares both :root blocks as expected")
    return dark.group(1), light.group(1)


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
    dark_body, light_body = _root_blocks(panel_html())
    decls = _declarations(dark_body)
    if theme == "light":
        decls.update(_declarations(light_body))
    elif theme != "dark":
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

    CIE76 is the conservative choice here: it is exactly defined, and it tends to
    *overstate* the difference between saturated reds, so a small value from it is
    strong evidence that two colours have genuinely converged.
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
# not because the combination is possible.
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
    ("--faint", "--sunk", "queue card meta", TEXT_MIN),
    ("--accent", "--panel", "jump links, copy button, running pill", TEXT_MIN),
    ("--accent", "--sunk", "running pill in the detail card", TEXT_MIN),
    ("--pass", "--panel", "KPI value, pass chips", TEXT_MIN),
    ("--pass", "--sunk", "pass chips in sunk rows", TEXT_MIN),
    ("--wait", "--panel", "KPI value, blocked chips", TEXT_MIN),
    ("--wait", "--sunk", "queue card kind label", TEXT_MIN),
    ("--fail", "--panel", "KPI value, lane errors, fail chips", TEXT_MIN),
    ("--fail", "--sunk", "contested note, fail chips", TEXT_MIN),
]

# Non-text pairs that WCAG 1.4.11 covers: each of these contours is the thing
# that identifies a state, so 3:1 applies to it. Card and table borders are not
# in this table — they enclose content rather than identify a control, and the
# panel has always drawn them faint on purpose.
NONTEXT_PAIRS = [
    ("--accent", "--sunk", "running node contour, focus ring", NONTEXT_MIN),
    ("--pass", "--sunk", "pass node contour", NONTEXT_MIN),
    ("--wait", "--sunk", "blocked node contour", NONTEXT_MIN),
    ("--fail", "--sunk", "fail node contour", NONTEXT_MIN),
]

# Pairs that do NOT clear their threshold on the owner's approved values. They
# are recorded here rather than fixed, because fixing them would mean editing a
# colour the owner approved (plan §8.3) and this slice does not renegotiate the
# palette. Pinning the measured ratio means the shortfall cannot deepen without
# the suite saying so, and cannot be deleted without the deletion showing up.
# All three are the light theme; the dark theme clears every pair it ships.
KNOWN_SHORTFALLS = {
    ("light", "--faint", "--ground"): 4.25,   # footer and shell hints, 10-12.5px
    ("light", "--faint", "--sunk"): 3.94,     # queue card meta and detail meta, ~10.5px
    ("light", "--accent", "--sunk"): 4.50,    # the running pill in the detail card
}

THEMES = ("dark", "light")


def measure(theme: str, pairs: list) -> list[tuple[str, str, str, float, float]]:
    """Measure every pair of one table in one theme.

    Args:
        theme: ``"dark"`` or ``"light"``.
        pairs: Rows of ``(fg token, bg token, usage, threshold)``.

    Returns:
        Rows of ``(fg, bg, usage, ratio, threshold)``.
    """
    t = tokens(theme)
    return [(fg, bg, use, contrast(t[fg], t[bg]), floor) for fg, bg, use, floor in pairs]


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
def test_every_text_pair_clears_the_normal_text_threshold_except_the_three_recorded_ones(theme):
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
@pytest.mark.parametrize("surface", ["--panel", "--sunk"])
@pytest.mark.parametrize("token", ["--fail", "--wait"])
def test_fail_and_wait_are_each_legible_on_both_card_surfaces(theme, surface, token):
    # Required explicitly by the slice: each of fail and wait against each of
    # panel and sunk, in both themes. All eight clear the threshold.
    t = tokens(theme)
    ratio = contrast(t[token], t[surface])
    assert ratio >= TEXT_MIN, f"{theme}: {token} on {surface} is {ratio:.2f}:1"


@pytest.mark.parametrize("theme", THEMES)
def test_a_lit_card_reads_as_lit_because_its_contour_gains_real_contrast(theme):
    # The light level has to be visible to mean anything. In both themes the lit
    # contour roughly doubles the contrast the resting contour has against the
    # same surface — that, plus the depth, is what "lit" is made of. No accent
    # and no hue change is involved.
    t = tokens(theme)
    resting = contrast(t["--line"], t["--panel-lit"])
    lit = contrast(t["--contour-lit"], t["--panel-lit"])
    assert lit > resting * 1.5, f"{theme}: lit contour {lit:.2f} vs resting {resting:.2f}"


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


# ── the states must survive colour being removed entirely ──────────────────
def _status_table() -> dict[str, dict[str, str]]:
    """Parse the panel's STATUS vocabulary — the glyph, label and silhouette."""
    rows = re.findall(
        r'(\w+):\s*\{\s*cls:\s*"([^"]+)",\s*glyph:\s*"([^"]+)",'
        r'\s*label:\s*"([^"]+)",\s*rx:\s*(\d+)\s*\}', panel_html())
    assert rows, "the STATUS table is no longer shaped as this parser expects"
    return {key: {"cls": cls, "glyph": glyph, "label": label, "rx": rx}
            for key, cls, glyph, label, rx in rows}


def _contour(cls: str) -> tuple[str, str]:
    """Return the (stroke-width, stroke-dasharray) the panel draws for one status."""
    html = panel_html()
    block = re.search(r"\.node--" + cls + r" rect\{(.*?)\}", html, re.S)
    body = block.group(1) if block else ""
    width = re.search(r"stroke-width:\s*([\d.]+)", body)
    dash = re.search(r"stroke-dasharray:\s*([^;}]+)", body)
    return (width.group(1) if width else "1.5",      # .node rect base
            dash.group(1).strip() if dash else "none")


def _signature(status: str) -> tuple[str, str, str, str, str]:
    row = _status_table()[status]
    width, dash = _contour(row["cls"])
    return row["glyph"], row["label"], row["rx"], width, dash


@pytest.mark.parametrize("status", ["pass", "fail", "blocked", "running", "idle",
                                    "contested"])
def test_every_status_carries_a_glyph_and_a_spelt_out_label(status):
    row = _status_table()[status]
    assert row["glyph"] and row["label"], status


def test_no_two_statuses_share_a_glyph_or_a_label():
    table = _status_table()
    glyphs = [r["glyph"] for r in table.values()]
    labels = [r["label"] for r in table.values()]
    assert len(set(glyphs)) == len(glyphs)
    assert len(set(labels)) == len(labels)


def test_running_and_fail_differ_in_silhouette_and_not_only_in_hue():
    # The collision this slice exists to settle. In the light theme the running
    # contour is --accent #c92f42 and the fail contour is --fail #b42318, 1.24:1
    # apart, and before this slice both drew a 2.5px solid rounded rectangle. A
    # reader with the colour removed had nothing left. They are now a pill
    # (rx 14) and a square (rx 2), which survives any amount of colour loss.
    running, fail = _signature("running"), _signature("fail")
    assert running[2] != fail[2], "running and fail draw the same corner radius"
    assert running[0] != fail[0] and running[1] != fail[1]


def test_work_in_progress_waiting_and_failure_are_all_three_tellable_apart_without_colour():
    # running / blocked / fail is the trio the slice must keep separable with
    # colour switched off. Each carries a different glyph, a different word, and
    # a different contour signature (radius, weight, dash pattern).
    signatures = {s: _signature(s) for s in ("running", "blocked", "fail")}
    colourless = {s: (sig[0], sig[1], sig[2], sig[3], sig[4])
                  for s, sig in signatures.items()}
    assert len(set(colourless.values())) == 3, colourless
    for a, b in (("running", "blocked"), ("running", "fail"), ("blocked", "fail")):
        shape_a, shape_b = colourless[a][2:], colourless[b][2:]
        assert shape_a != shape_b, f"{a} and {b} draw the same contour: {shape_a}"


def test_the_map_prints_the_status_word_inside_every_node():
    # The glyph alone would be a symbol to learn; the word next to it is what
    # makes the map readable without the legend and without colour.
    assert 'st.glyph + " " + st.label' in panel_html()
