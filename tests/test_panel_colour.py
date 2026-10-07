"""Colorimetry: WCAG contrast, CIE76 difference and dichromat simulation.

A self-contained circuit. Nothing here reads the panel, imports a pair table or
knows what a status is — the input is an sRGB triple and the output is a number,
which is why it can be checked against published values rather than against
itself. tests/test_panel_contrast.py resolves the panel's declarations into
triples and hands them to these functions.

Split out of that module on 2026-08-07 under the owner's rule of 2026-08-04: a
file over 800 lines gives up the self-contained circuit inside it rather than
growing. The pair tables and their thresholds stayed behind; the arithmetic
came here, where it stops being re-read every time a surface is added.
"""
import pytest


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
    dichromacy it tends to *understate* rather than overstate the gap — so a
    small number read from it is a conservative reading of how close those two
    get, not a flattering one.
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


# A difference under about 2.3 is the standard just-noticeable-difference floor:
# below it, two colours are the same colour.
JND = 2.3

BLACK, WHITE = (0, 0, 0), (255, 255, 255)


def test_the_contrast_formula_agrees_with_the_values_wcag_publishes():
    # The extremes the specification itself names, so the arithmetic is checked
    # against something outside this repository rather than against a pin.
    assert round(contrast(BLACK, WHITE), 2) == 21.0
    assert contrast(WHITE, WHITE) == 1.0
    # #767676 on white is the canonical worst-case grey that just clears 4.5:1.
    assert 4.5 <= contrast((0x76, 0x76, 0x76), WHITE) < 4.6


@pytest.mark.parametrize("pair", [(BLACK, WHITE), ((228, 73, 85), (16, 20, 27)),
                                  ((201, 47, 66), (233, 237, 241))])
def test_contrast_reads_the_same_whichever_colour_is_called_the_foreground(pair):
    fg, bg = pair
    assert contrast(fg, bg) == contrast(bg, fg)


def test_luminance_rises_with_every_channel_and_spans_zero_to_one():
    assert luminance(BLACK) == 0.0
    assert round(luminance(WHITE), 6) == 1.0
    assert luminance((128, 0, 0)) < luminance((128, 128, 0)) < luminance((128, 128, 128))


def test_the_colour_difference_of_a_colour_from_itself_is_zero():
    for rgb in (BLACK, WHITE, (201, 47, 66), (138, 101, 0)):
        assert delta_e(rgb, rgb) == 0.0
    # And a difference the eye is meant to notice reads above the JND floor.
    assert delta_e((201, 47, 66), (36, 122, 75)) > JND * 10


@pytest.mark.parametrize("kind", ["protanopia", "deuteranopia"])
def test_a_dichromat_simulation_leaves_greys_alone_and_flattens_reds_and_greens(kind):
    # Neutral colours have no chromatic information to lose, so they survive;
    # a red and a green that differ strongly move toward each other.
    for grey in (BLACK, WHITE, (128, 128, 128)):
        assert max(abs(a - b) for a, b in zip(simulate_cvd(grey, kind), grey)) <= 2
    plain = delta_e((200, 30, 30), (30, 160, 30))
    seen = delta_e(simulate_cvd((200, 30, 30), kind), simulate_cvd((30, 160, 30), kind))
    assert seen < plain


def test_the_simulation_rejects_a_deficiency_it_has_no_matrix_for():
    with pytest.raises(ValueError):
        simulate_cvd(WHITE, "tritanopia")
