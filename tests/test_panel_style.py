"""What the panel's stylesheet promises, held as relations over the cascade.

The claims here are the owner's two invariants and the rules of §4: status owns
the inner silhouette and interaction may not touch it; the light level is
conditional, data-keyed and never spends the accent; the material layer carries
no hue; the legend echoes the silhouettes; December Red stays on its reserved
roles. Each is written as an equality or an inequality between computed
profiles, so the sabotage that motivated the module — ``.node:hover
rect{stroke:var(--accent);rx:14px}`` — fails it, while rewriting a comment
cannot make it pass.

The cascade those profiles are computed through lives in
tests/test_panel_cascade.py, which also derives the set of elements that carry a
state at all. This module says what may be true of them.
"""
import re

import pytest

from tests.test_panel_cascade import (
    ENVIRONMENTS, INTERACTIONS, Element, Rule, carriers, computed, function_body,
    paint_profile, panel_html, rules, script, stylesheet, touched)

# ── the status vocabulary and the silhouette it owns ───────────────────────
def status_table() -> dict[str, dict[str, str]]:
    """Parse the panel's STATUS vocabulary — glyph, label and corner radius."""
    rows = re.findall(
        r'(\w+):\s*\{\s*cls:\s*"([^"]+)",\s*glyph:\s*"([^"]+)",'
        r'\s*label:\s*"([^"]+)",\s*rx:\s*(\d+)\s*\}', panel_html())
    assert rows, "the STATUS table is no longer shaped as this parser expects"
    return {key: {"cls": cls, "glyph": glyph, "label": label, "rx": rx}
            for key, cls, glyph, label, rx in rows}


STATUSES = ("pass", "fail", "blocked", "running", "idle", "contested")

# What a status is allowed to own: the shape, weight, pattern and paint of the
# contour drawn inside the node. If an interaction can move any of these, one
# status can be made to look like another.
SILHOUETTE = ("rx", "stroke", "stroke-width", "stroke-dasharray", "fill", "opacity")


# ── the map's nodes: the invariant where it was first written ──────────────
def node_chain(status: str, interaction: str | None = None) -> list[Element]:
    """Build the (group, status box) chain for one node in one state."""
    cls = status_table()[status]["cls"]
    group = Element("g", frozenset({"node", "node--" + cls}), frozenset(),
                    {"aria-pressed": "false"})
    return touched([group, Element("rect", frozenset({"box"}), frozenset(), {})],
                   interaction)


def box_profile(status: str, interaction: str | None = None,
                env: frozenset = frozenset()) -> dict[str, str]:
    """Return everything that decides how one status draws its contour."""
    win = computed(node_chain(status, interaction), env=env)
    profile = {prop: win.get(prop) for prop in SILHOUETTE}
    # rx arrives as a presentation attribute from STATUS.rx unless a rule
    # overrides it, and a rule overriding it is exactly the impersonation this
    # guards against — so the attribute is part of the profile. Read as a
    # number, because "14px" from a rule and 14 from the attribute are the same
    # corner and a comparison of the two spellings would say they are not.
    profile["rx"] = float(str(win.get("rx", status_table()[status]["rx"])).rstrip("px"))
    return profile


def halo_profile(status: str, interaction: str | None = None,
                 env: frozenset = frozenset()) -> dict[str, str]:
    """Return how the interaction ring is painted for one node state."""
    chain = node_chain(status, interaction)
    chain[-1] = chain[-1]._replace(classes=frozenset({"halo"}))
    win = computed(chain, env=env)
    return {prop: win.get(prop) for prop in ("stroke", "stroke-width", "fill")}


def interaction_is_drawn(status: str, interaction: str | None = None,
                         env: frozenset = frozenset()) -> bool:
    """Whether a node paints anything outside its status to say it is touched.

    Two carriers count: the outer ring, and the global focus outline that
    reaches the same group. "Drawn" means a real paint, not merely a different
    declaration — ``outline:none`` is a change and is also an invisible focus
    indicator, so a test asking only whether something *changed* would accept
    the one case a focus indicator must never be in.
    """
    ring = halo_profile(status, interaction, env).get("stroke")
    outline = computed(node_chain(status, interaction)[:1], env=env).get("outline", "none")
    return ring not in (None, "none") or "none" not in outline


@pytest.mark.parametrize("interaction", sorted(INTERACTIONS))
@pytest.mark.parametrize("status", STATUSES)
def test_a_node_draws_the_same_status_contour_whether_or_not_it_is_being_touched(
        status, interaction):
    # The invariant in one line: status owns the inner silhouette. Hovering,
    # focusing or selecting a node may add to it but may not repaint, reshape
    # or reweight it, so a failing node under the cursor is still a failing
    # node. Nothing here looks for the word "hover" — the two profiles are
    # computed through the cascade and compared, once per media environment the
    # stylesheet declares, because a rule that only applies in Winter Daylight
    # is still a rule that applies.
    for label, env in ENVIRONMENTS:
        assert box_profile(status, interaction, env) == box_profile(status, None, env), (
            f"{interaction} changed how {status} draws itself in {label}")


@pytest.mark.parametrize("interaction", sorted(INTERACTIONS))
def test_an_interaction_is_still_visible_even_though_it_cannot_touch_the_status(
        interaction):
    # The other half: separating the channels is only honest if the second
    # channel actually draws something. Hover and selection draw the ring;
    # focus is left to the global outline, which reaches the same group. Which
    # of the two carries a state is left open — what is held is that at rest
    # nothing is painted outside the status, and under every state something is.
    for label, env in ENVIRONMENTS:
        for status in STATUSES:
            assert not interaction_is_drawn(status, None, env), (status, label)
            assert interaction_is_drawn(status, interaction, env), (status, label)


@pytest.mark.parametrize("interaction", sorted(INTERACTIONS))
def test_the_interaction_ring_is_painted_the_same_whatever_the_status(interaction):
    # drawNodes says the ring takes its geometry from the status and its paint
    # never does. This is the paint half held as a relation: one ring paint
    # across six statuses, so the ring cannot become a second status carrier.
    for label, env in ENVIRONMENTS:
        painted = {tuple(sorted(halo_profile(s, interaction, env).items()))
                   for s in STATUSES}
        assert len(painted) == 1, (label, interaction, painted)


# ── the same invariant over every carrier, not only the map ────────────────
# Owner invariant 1 was written about map nodes but stated generally, and the
# general form is the one that holds: a chip's border, a queue card's left edge
# and the ring's current stage all say what state something is in. The carriers
# are derived in tests/test_panel_cascade.py from the stylesheet itself, so the
# next one comes under guard when it is declared rather than when it is noticed.
@pytest.mark.parametrize("interaction", sorted(INTERACTIONS))
def test_no_interaction_repaints_an_element_the_stylesheet_gives_a_state_to(interaction):
    # Owner invariant 1, general form: hover, focus and selection may add an
    # outer ring, a second contour or a surface of their own, and may not touch
    # the paint or the shape of anything carrying a state. Held over carriers
    # read out of the stylesheet rather than listed here, so a carrier the panel
    # grows next comes under guard the moment it is declared — which is how the
    # chips, the queue card's edge and the ring's current stage arrive.
    for carrier in carriers():
        for label, env in ENVIRONMENTS:
            assert paint_profile(carrier.chain, interaction, env) == \
                paint_profile(carrier.chain, None, env), (carrier.label, label, interaction)


def test_no_status_can_be_mistaken_for_another_once_colour_is_taken_away():
    # Strip the paint out of every profile and the six must still be six.
    shapes = {s: tuple((k, v) for k, v in sorted(box_profile(s).items())
                       if k not in ("stroke", "fill"))
              + (status_table()[s]["glyph"], status_table()[s]["label"])
              for s in STATUSES}
    assert len(set(shapes.values())) == len(STATUSES), shapes


@pytest.mark.parametrize("status", STATUSES)
def test_every_status_carries_a_glyph_and_a_spelt_out_label(status):
    row = status_table()[status]
    assert row["glyph"] and row["label"], status


def test_no_two_statuses_share_a_glyph_or_a_label():
    table = status_table()
    glyphs = [row["glyph"] for row in table.values()]
    labels = [row["label"] for row in table.values()]
    assert len(set(glyphs)) == len(glyphs)
    assert len(set(labels)) == len(labels)


def test_running_and_fail_differ_in_silhouette_and_not_only_in_hue():
    # The collision this slice exists to settle. In the light theme the running
    # contour is --accent #c92f42 and the fail contour is --fail #b42318, 1.24:1
    # apart, and before this slice both drew a 2.5px solid rounded rectangle. A
    # reader with the colour removed had nothing left. They are now a pill
    # (rx 14) and a square (rx 2), which survives any amount of colour loss.
    #
    # Held in every media environment, and the light one is the point: that is
    # where the two contours are the same red, so a rule scoped to Winter
    # Daylight is exactly where the silhouettes would quietly converge.
    for label, env in ENVIRONMENTS:
        running, fail = box_profile("running", None, env), box_profile("fail", None, env)
        assert running["rx"] != fail["rx"], f"{label}: same corner radius"
        assert running["stroke-width"] != fail["stroke-width"], label
    table = status_table()
    assert table["running"]["glyph"] != table["fail"]["glyph"]
    assert table["running"]["label"] != table["fail"]["label"]


def test_the_map_prints_the_status_word_inside_every_node():
    # The glyph alone would be a symbol to learn; the word next to it is what
    # makes the map readable without the legend and without colour. Scoped to
    # drawNodes on purpose: the same expression also lives in renderDetail, so
    # searching the whole file proves only that the detail card still has it.
    body = function_body("drawNodes")
    texts = re.findall(r'sv\("text",[^;]*?\)(?=,|\);)', body, re.S)
    assert len(texts) == 2, texts
    printed = " ".join(texts)
    assert "st.glyph" in printed and "st.label" in printed, printed
    assert "n.label || n.id" in printed, printed


def test_the_status_box_and_the_interaction_ring_are_two_elements_in_every_node():
    # The cascade guards above describe a node with a .box and a .halo. If
    # drawNodes stopped emitting either of them, those guards would be
    # reasoning about an element that is no longer drawn. "Every node" is the
    # load-bearing word: the cycle ring used to emit groups classed "node phase"
    # with a single .box and no ring, which made this name false and left the
    # ring's own boxes outside the node guards. So the second half holds the
    # class namespace — drawNodes is the only writer of the class "node".
    body = function_body("drawNodes")
    assert re.search(r'sv\("rect",\s*\{\s*class:\s*"halo"', body), body
    assert re.search(r'sv\("rect",\s*\{\s*class:\s*"box"', body), body
    written = [literal for literal in re.findall(r'class:\s*"([^"]*)"', script())
               if "node" in literal.split()]
    assert written == ["node node--"], written
    assert re.findall(r'class:\s*"([^"]*)"', body).count("node node--") == 1


# ── the light level: conditional, data-keyed, and never the accent ─────────
LIT_MATERIAL = ("--panel-lit", "--contour-lit", "--lift-1", "--lift-2")


def _light_rules() -> list[Rule]:
    return [r for r in rules() if "data-attention" in r.selector]


def _card(level: str, lit: bool) -> list[Element]:
    return [Element("html", frozenset(), frozenset(), {"data-attention": level}),
            Element("body"),
            Element("div", frozenset({"card", "lit"} if lit else {"card"}))]


LEVELS = ("none", "low", "high")


@pytest.mark.parametrize("label,env", ENVIRONMENTS,
                         ids=[label for label, _ in ENVIRONMENTS])
def test_a_card_can_only_reach_the_lit_material_through_the_light_level(label, env):
    # Absence of attention is a real state and has to look like one. The first
    # version of this asked for the substring "data-attention" in the selector,
    # which `html[data-attention] .lit` satisfies while matching at every level
    # including "none" — a panel lit permanently, the direction's central
    # prohibition, with the suite green. So the claim is held as a relation
    # instead: at level "none" a lit card is drawn exactly like a card that is
    # not lit at all, and at the two levels that mean something, it is not.
    unlit = computed(_card("none", lit=False), env=env)
    assert computed(_card("none", lit=True), env=env) == unlit, "the panel glows unasked"
    for level in ("low", "high"):
        assert computed(_card(level, lit=True), env=env) != unlit, level
    for level in LEVELS:
        assert computed(_card(level, lit=False), env=env) == unlit, level


def test_the_light_level_never_spends_the_accent():
    # Precision Cockpit light is carried by surface, contour and depth. This
    # reads whole rules, not first lines: the one multi-line light rule keeps
    # its border-color on a continuation, and a first-line scan cannot see it.
    assert _light_rules(), "no light-level rules found — the parser lost them"
    for rule in _light_rules():
        for prop, value in rule.decls.items():
            assert "--accent" not in value, (rule.selector, prop, value)
    # and the accent must not reach them second-hand, through the material.
    for rule in rules():
        for prop, value in rule.decls.items():
            if prop in LIT_MATERIAL:
                assert "--accent" not in value, (rule.selector, prop, value)


def root_declarations() -> tuple[dict[str, str], dict[str, str]]:
    """Return the dark `:root` declarations and the light-media overrides."""
    dark = next(r.decls for r in rules() if r.selector == ":root" and not r.context)
    light = next(r.decls for r in rules()
                 if r.selector == ":root" and "prefers-color-scheme:light" in r.context)
    return dark, light


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_the_material_layer_is_palette_mixes_plus_neutral_shadow_geometry(theme):
    # What the comment over the material block claims, held to. --panel-lit and
    # --contour-lit are mixes of palette tokens. --lift-1 and --lift-2 are not
    # colours at all: they are offsets plus one neutral, either pure black or
    # the rgb of --ink, which is why the layer introduces no hue.
    dark, light = root_declarations()
    decls = dict(dark, **light) if theme == "light" else dark
    for name in ("--panel-lit", "--contour-lit"):
        value = decls[name]
        assert re.fullmatch(r"color-mix\(in srgb,.*\)|var\(--[a-z-]+\)", value), value
        assert all(ref.startswith("--") for ref in re.findall(r"var\((--[\w-]+)\)", value))
    ink = decls["--ink"].lstrip("#")
    ink_rgb = tuple(int(ink[i:i + 2], 16) for i in (0, 2, 4))
    for name in ("--lift-1", "--lift-2"):
        value = decls[name]
        assert "var(" not in value, value
        shade = re.fullmatch(r"[\d\spx]+rgba\((\d+),(\d+),(\d+),\.\d+\)", value)
        assert shade, value
        assert tuple(int(c) for c in shade.groups()) in ((0, 0, 0), ink_rgb), value


# ── the map legend ─────────────────────────────────────────────────────────
def legend_keys() -> dict[str, dict[str, str]]:
    """Parse the map legend: one status word to the swatch style beside it."""
    block = re.search(r'<div class="legend">(.*?)</div>', panel_html(), re.S).group(1)
    out = {}
    for style, text in re.findall(r'<i style="([^"]*)"></i>\s*\S+\s*([a-z]+)', block, re.S):
        out[text] = dict(part.split(":", 1) for part in
                         (p.strip() for p in style.replace("\n", " ").split(";")) if part)
    assert len(out) == len(STATUSES), out
    return out


def test_the_legend_key_of_a_status_echoes_the_silhouette_that_status_draws():
    # The legend is the one place a --fail swatch and an --accent swatch stand
    # side by side, and as identical squares hue was all that separated them.
    # The relation held here is monotonic: a status with a rounder node draws a
    # rounder key, and two statuses with the same radius draw the same key.
    table, keys = status_table(), legend_keys()
    radius = {s: float(keys[s]["border-radius"].rstrip("px")) for s in STATUSES}
    corner = {s: float(table[s]["rx"]) for s in STATUSES}
    for a in STATUSES:
        for b in STATUSES:
            assert (corner[a] > corner[b]) == (radius[a] > radius[b]), (a, b)
            assert (corner[a] == corner[b]) == (radius[a] == radius[b]), (a, b)


def test_every_legend_key_draws_its_status_as_a_contour_and_not_as_a_flat_fill():
    # §4 reserves the accent for six roles and never for a large fill, so no key
    # may be a block of one token. contested keeps a fill because being two
    # colours at once is its signature — but it is a gradient of two tokens
    # inside a dashed contour, not a flat swatch, so the rule below still holds.
    # Asking that the background not begin with `var(` was a check on spelling:
    # `color-mix(in srgb,var(--accent) 100%,transparent)` is the same flat red
    # written differently. What a key may carry is stated positively instead.
    for status, style in legend_keys().items():
        assert "border-color" in style, status
        fill = style.get("background", "")
        if not fill:
            continue
        assert fill.startswith("linear-gradient("), (status, fill)
        assert len(set(re.findall(r"var\((--[\w-]+)\)", fill))) == 2, (status, fill)


# ── movement, and the accent's six roles ──────────────────────────────────
def animated() -> dict[str, str]:
    """Every selector the stylesheet animates, with the animation it declares."""
    return {f"{rule.context} {rule.selector}".strip(): rule.decls["animation"]
            for rule in rules() if "animation" in rule.decls}


# The panel's two movements, both pre-existing. §5 of the plan forbids
# permanent decorative animation and removing what is already here is DEC-UI-4's
# work — but this slice lays down a material layer, and a material layer is
# exactly the thing a throb or a shimmer gets attached to. Pinned two-sidedly:
# a new animation fails here, and so does deleting one without saying so.
MOVEMENT = {
    ".dot": "blink 2.4s ease-in-out infinite",
    ".pulse .box": "glow 2s ease-in-out infinite",
    ".dot--down": "none",
    "@media (prefers-reduced-motion:reduce) .dot": "none",
    "@media (prefers-reduced-motion:reduce) .pulse .box": "none",
}


def test_the_panel_moves_in_the_two_places_it_already_moved_and_nowhere_else():
    assert animated() == MOVEMENT
    declared = set(re.findall(r"@keyframes\s+([\w-]+)", stylesheet()))
    used = {value.split()[0] for value in animated().values() if value != "none"}
    assert declared == used, (declared, used)


# The six roles §4 reserves December Red for: the current Orbit stage, the
# travelled trajectory, human-control points, the primary action, focus and
# selection, and a small brand mark. Every place the stylesheet spends the
# accent is named here with the role it spends it on, so a new accent site
# cannot appear without someone deciding which role it is. Three of them are
# open questions carried to the owner rather than settled roles, and they say
# so: an honest map beats a tidy one.
ACCENT_ROLES = {
    ":focus-visible": "role 5 — focus, on every focusable element including a node",
    ".node[aria-pressed=\"true\"] .halo": "role 5 — selection, on the outer ring",
    ".phase--current .box": "role 1 — the current Orbit stage",
    ".mark__dot": "role 6 — the brand mark",
    ".copy": "role 4 — the primary action, the decision-brief button",
    ".copy:hover": "role 4 — the same button under the pointer",
    ".spark i": "OPEN — the KPI progress bar, carried to the owner",
    ".node--running .box": "OPEN — the running node's contour, carried to the owner",
    ".p--running": "OPEN — the running chip's tint and border, carried to the owner",
    ".p--running .gl": "OPEN — the running chip's glyph, carried to the owner",
    "legend key: running": "OPEN — the map legend's contour for running",
}


def test_every_place_the_panel_spends_the_accent_is_named_with_the_role_it_spends_it_on():
    spent = {rule.selector for rule in rules()
             for value in rule.decls.values() if "var(--accent)" in value}
    spent |= {f"legend key: {status}" for status, style in legend_keys().items()
              if any("var(--accent)" in value for value in style.values())}
    assert spent == set(ACCENT_ROLES), spent ^ set(ACCENT_ROLES)
