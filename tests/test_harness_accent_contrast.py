"""Every registry accent, measured against the surfaces the panel actually paints.

The accents in `conductor.harnesses` are OURS — the module says so, and says
why: no official logo is bundled and no brand colour is copied out of a source
we cannot verify. That freedom is exactly what makes measuring them necessary.
A vendor's colour at least arrives with a vendor's own contrast work behind it;
a colour we chose arrives with none, so the only thing standing between a new
row and an unreadable badge is a number computed here.

What is measured is a *pair*, and the background half is the panel's, not a
constant restated in this file. `tokens()` resolves the shipped declarations out
of `src/conductor/panel/index.html`, so a surface that moves there moves these
results — a copy of `--sunk` pinned in this module would go on passing while the
panel drew the badge on something else. The arithmetic comes from
tests/test_panel_colour.py, which knows nothing about either subject.

Reading this module does not make the accents a status colour. ADR 0001 §6
separates identity from status BY CHANNEL: the accent carries identity through
the monogram and a small local swatch, and is forbidden on the node outline, the
edges, the progress path, the primary action, the focus ring and every status
glyph. Nothing here relaxes that, and no hue-distance rule belongs here either —
the registry docstring records why one was considered and rejected. The question
this module asks is narrower and is the one a number can answer: whatever
surface the badge lands on, can it be read.
"""
import pytest

from conductor import harnesses
from tests.test_panel_colour import contrast
from tests.test_panel_contrast import tokens

#: WCAG 2.1 1.4.3, normal text. The badge could answer to 1.4.11's 3:1 if it
#: were only ever a swatch, but the monogram is a glyph a reader reads, so the
#: text floor is what governs — and holding the swatch to the same number costs
#: nothing, since every shipped row clears it. DEC-UI-3 is therefore free to
#: draw the accent as the monogram, as a swatch, or as both.
TEXT_MIN = 4.5

#: Every opaque surface the panel puts a card or a card's inset on, so every
#: surface a badge can come to rest against. `--panel-lit` is included because
#: the attention level repaints cards under it and a badge does not move.
SURFACES = ("--panel", "--sunk", "--ground", "--panel-lit")

THEMES = (("dark", "accent_dark"), ("light", "accent_light"))


def _rgb(value: str) -> tuple[int, int, int]:
    """One `#rrggbb` registry accent as an sRGB triple."""
    digits = value.lstrip("#")
    return tuple(int(digits[i:i + 2], 16) for i in (0, 2, 4))


def _worst(harness_id: str, theme: str, field: str) -> float:
    """The lowest ratio one accent reaches over all four surfaces of a theme."""
    table = tokens(theme)
    accent = _rgb(getattr(harnesses.get(harness_id), field))
    return min(contrast(accent, table[surface]) for surface in SURFACES)


@pytest.mark.parametrize("theme,field", THEMES)
@pytest.mark.parametrize("surface", SURFACES)
@pytest.mark.parametrize("harness", harnesses.known(), ids=lambda h: h.id)
def test_every_registry_accent_is_legible_on_every_surface_of_its_own_theme(
        harness, surface, theme, field):
    # The whole registry, not only the newest rows: a floor that only the last
    # entry had to clear is a floor the next entry can be added underneath.
    # `custom` and the neutral pair are in here too — an unregistered harness
    # gets a badge drawn the same way and has the same right to be read.
    ratio = contrast(_rgb(getattr(harness, field)), tokens(theme)[surface])
    assert ratio >= TEXT_MIN, (
        f"{harness.id}: {theme} accent on {surface} is {ratio:.2f}:1")


#: The measurement of record for REG-1, kept as numbers because "it clears the
#: floor" is the weaker half of what was checked. Each is the worst of the four
#: surfaces in that theme — the light rows meet it on `--sunk`, the dark rows on
#: `--panel-lit`. Two-sided, in the style tests/test_panel_contrast.py uses for
#: the panel's own pairs: this fails if a value is dimmed and it fails if a
#: value is brightened without the number being moved with it, so an accent
#: cannot be quietly restyled after the owner has read these.
REG_1_WORST = {
    ("gemini-cli", "dark"): 8.85,
    ("gemini-cli", "light"): 5.32,
    ("opencode", "dark"): 7.85,
    ("opencode", "light"): 6.18,
}


@pytest.mark.parametrize("harness_id,theme", [k for k in REG_1_WORST])
def test_each_new_accent_still_measures_what_reg_1_recorded_for_it(harness_id, theme):
    field = dict(THEMES)[theme]
    assert round(_worst(harness_id, theme, field), 2) == REG_1_WORST[(harness_id, theme)]


@pytest.mark.parametrize("harness_id", ["gemini-cli", "opencode"])
def test_neither_new_accent_is_the_badge_reserved_for_a_harness_we_do_not_know(harness_id):
    # The neutral pair means "this file knows nothing about this product". A
    # registered row wearing it would say the opposite of what registering it
    # was for, and no shape test above would notice: the pair is well-formed
    # hex, it differs between themes, and it clears the floor comfortably.
    harness = harnesses.get(harness_id)
    assert harness.accent_dark != harnesses.NEUTRAL_DARK
    assert harness.accent_light != harnesses.NEUTRAL_LIGHT
