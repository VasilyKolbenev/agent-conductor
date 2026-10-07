"""What is left of a status when its colour is taken away.

Moved out of tests/test_panel_contrast.py whole when that file passed the
project's 800-line cap. Two of that file's own section banners came across —
`accent against fail` and `colour-vision deficiency` — together with the one
test they exist to justify, `test_no_chip_says_its_status_with_colour_alone`.

That is a seam and not a convenient cut, in both directions. Every other
measurement in test_panel_contrast.py is the distance between a MARK and the
SURFACE under it: a word on a card, a contour against its own fill, a chip on
the tint it is mixed into. Every measurement here is the distance between two
STATUS COLOURS — accent against fail, fail against wait — which is a different
question with a different answer, and the answer is that the distance is not
there. The light theme's fail and wait land inside the just-noticeable
difference under deuteranopia, so for those readers the colour channel carries
nothing at all, and the chip test is what holds the glyph and the border in
place as the carriers that are left. Read apart, the guard looks like a style
rule and the measurements look like trivia; read together they are one claim.

Nothing here touches a surface, a chain or a tint, so none of the compositing
machinery in the parent is used: `tokens` is the whole of what these tests
need from it, plus `foreground` and the two chip chains for the one test that
resolves a mark. Those are imported from tests/test_panel_contrast.py rather
than copied — a second copy of `_pill` or `_vd` would be a second opinion about
what the panel builds. The arithmetic is still tests/test_panel_colour.py's,
which knows nothing about the panel, and `JND`, `delta_e` and `simulate_cvd`
are now imported by this module alone.
"""
import pytest

from tests.test_panel_cascade import INTERACTIONS, E, touched
from tests.test_panel_colour import JND, contrast, delta_e, simulate_cvd
from tests.test_panel_contrast import THEMES, _pill, _vd, foreground, tokens


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
