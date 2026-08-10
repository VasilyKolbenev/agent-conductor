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

Scope, stated once and meant literally. Everything here reads the panel's
*source text*: the ``<style>`` block parsed into rules, the ``<script>`` block
read as characters. No browser runs, no DOM is built, nothing is rasterised. So
what these guards hold is what the panel *declares* — a structural property —
and not what a reader finally sees. The same behaviour written a different way
goes through: fourteen executed sabotages across two reviews did exactly that,
none of them by changing what the panel does. Closing that class needs
assertions on a rendered result, which §10 of the plan carries as post-alpha
work. Every name, docstring and comment below is written to that limit, and
none of them may promise past it.
"""
import re

import pytest

from tests.test_panel_cascade import (
    ENVIRONMENTS, INTERACTIONS, Element, Rule, carriers, computed, function_body,
    keyframe_properties, media_contexts, paint_profile, panel_html, rules, script,
    stylesheet, touched)

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
    """Return the declarations that decide one status's contour."""
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
    """Return the paint declarations the interaction ring wins in one state."""
    chain = node_chain(status, interaction)
    chain[-1] = chain[-1]._replace(classes=frozenset({"halo"}))
    win = computed(chain, env=env)
    return {prop: win.get(prop) for prop in ("stroke", "stroke-width", "fill")}


def interaction_is_declared(status: str, interaction: str | None = None,
                            env: frozenset = frozenset()) -> bool:
    """Whether the stylesheet declares a mark outside a node's status for a state.

    Two carriers count: the outer ring, and the global focus outline that
    reaches the same group. The declaration has to name a real paint rather than
    merely differ — ``outline:none`` differs and is also an invisible focus
    indicator, so a test asking only whether something *changed* would accept
    the one case a focus indicator must never be in. Whether a browser renders
    what is declared is outside this module; see the scope note above.
    """
    ring = halo_profile(status, interaction, env).get("stroke")
    outline = computed(node_chain(status, interaction)[:1], env=env).get("outline", "none")
    return ring not in (None, "none") or "none" not in outline


@pytest.mark.parametrize("interaction", sorted(INTERACTIONS))
@pytest.mark.parametrize("status", STATUSES)
def test_the_stylesheet_resolves_one_status_contour_for_a_node_touched_or_not(
        status, interaction):
    # The invariant in one line: status owns the inner silhouette. Hovering,
    # focusing or selecting a node may add to it but may not repaint, reshape
    # or reweight it, so a failing node under the cursor is still a failing
    # node. Nothing here looks for the word "hover" — the two profiles are
    # computed through the cascade and compared, once per media environment the
    # stylesheet declares, because a rule that only applies in Winter Daylight
    # is still a rule that applies.
    #
    # "Resolves" is the honest verb, and the name used to say "draws". What is
    # compared is two sets of winning *declarations*; no node is drawn here.
    for label, env in ENVIRONMENTS:
        assert box_profile(status, interaction, env) == box_profile(status, None, env), (
            f"{interaction} changed the contour declarations of {status} in {label}")


@pytest.mark.parametrize("interaction", sorted(INTERACTIONS))
def test_every_interaction_still_declares_a_mark_outside_the_status_it_may_not_touch(
        interaction):
    # The other half: separating the channels is only honest if the second
    # channel actually declares something. Hover and selection declare the ring;
    # focus is left to the global outline, which reaches the same group. Which
    # of the two carries a state is left open — what is held is that at rest no
    # paint is declared outside the status, and under every state one is.
    #
    # The name used to say "is still visible", which is a claim about a screen.
    # What is checked is a stroke declaration and an outline declaration, and
    # `interaction_is_declared` reads them out of the cascade model. A declared
    # ring that a browser fails to paint would pass here; that gap is §10 work.
    for label, env in ENVIRONMENTS:
        for status in STATUSES:
            assert not interaction_is_declared(status, None, env), (status, label)
            assert interaction_is_declared(status, interaction, env), (status, label)


@pytest.mark.parametrize("interaction", sorted(INTERACTIONS))
def test_the_interaction_rings_paint_declarations_are_one_set_across_every_status(
        interaction):
    # drawNodes says the ring takes its geometry from the status and its paint
    # never does. This is the paint half held as a relation: one set of ring
    # paint declarations across six statuses, so the ring cannot become a second
    # status carrier. The name says "declarations" because that is what is
    # compared — six dictionaries out of the cascade model, not six rings.
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
def test_no_interaction_changes_the_paint_declarations_of_a_state_carrier(interaction):
    # Owner invariant 1, general form: hover, focus and selection may add an
    # outer ring, a second contour or a surface of their own, and may not touch
    # the paint or the shape of anything carrying a state. Held over carriers
    # read out of the stylesheet rather than listed here, so a carrier the panel
    # grows next comes under guard the moment it is declared — which is how the
    # chips, the queue card's edge and the ring's current stage arrive.
    #
    # The name used to say "repaints an element", which is a claim about what
    # happens on a screen. Two declarations resolved by this model are compared,
    # and the carrier is a chain of elements this model built — not the DOM the
    # panel builds. The gap is real and was paid for: a carrier's *ancestor*
    # being repainted moves the carrier's own composited colour and is invisible
    # to this equality, which is how `tr.click:hover td{background:var(--sunk)}`
    # walked past it. tests/test_panel_contrast.py holds that half, by
    # arithmetic over full chains.
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


def test_drawnodes_writes_the_status_word_and_the_node_label_into_its_two_text_calls():
    # The glyph alone would be a symbol to learn; the word next to it is what
    # makes the map readable without the legend and without colour. Scoped to
    # drawNodes on purpose: the same expression also lives in renderDetail, so
    # searching the whole file proves only that the detail card still has it.
    #
    # The name used to say "the map prints", which claims something about what a
    # reader sees. This reads the source of one function and matches the
    # arguments of its two `sv("text", …)` calls. Live code that keeps those
    # substrings while producing nothing — `(st.glyph + " " + st.label) && ""`
    # is the executed sabotage — passes; that is the class §10 carries.
    body = function_body("drawNodes")
    texts = re.findall(r'sv\("text",[^;]*?\)(?=,|\);)', body, re.S)
    assert len(texts) == 2, texts
    printed = " ".join(texts)
    assert "st.glyph" in printed and "st.label" in printed, printed
    assert "n.label || n.id" in printed, printed


def test_the_status_box_and_the_interaction_ring_are_two_elements_in_every_node():
    # The cascade guards above describe a node with a .box and a .halo. If
    # drawNodes stopped emitting either of them, those guards would be
    # reasoning about an element that is no longer emitted. "Every node" is the
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


# ── the Orbit: four stage states, two connection forms ─────────────────────
# The Orbit is the panel's second graph and the first one drawn as HTML boxes
# rather than as SVG, so the same two questions are asked of it here as of the
# map above: can two states be told apart with the colour removed, and does the
# form that carries a state stay put when a pointer arrives. The chains below
# are the ones the script builds — a stage inside the field, a connection inside
# the field's SVG layer — and everything is resolved through the cascade model,
# which is a statement about declarations and not about a drawn shape.
TONES = ("neutral", "current", "waiting", "blocked")

# What a stage's silhouette is made of. Deliberately the same three properties
# the panel writes as longhands, so each can be resolved on its own: a state may
# own the weight, the pattern and the corner of its contour.
STAGE_SHAPE = ("border-width", "border-style", "border-radius")

ORBIT_FIELD = Element("div", frozenset({"orbit"}))


def stage_chain(tone: str, interaction: str | None = None) -> list[Element]:
    """Build the (field, stage) chain for one stage state."""
    return touched([ORBIT_FIELD, Element("div", frozenset({"orb", "orb--" + tone}))],
                   interaction)


def stage_shape(tone: str, interaction: str | None = None,
                env: frozenset = frozenset()) -> tuple:
    """Return one stage state's silhouette, with every colour left out."""
    win = computed(stage_chain(tone, interaction), env=env)
    return tuple(win.get(prop) for prop in STAGE_SHAPE)


def orbit_marks() -> dict[str, dict[str, str]]:
    """Parse the ORBIT_MARKS vocabulary — the chip each stage state spells."""
    block = re.search(r"const ORBIT_MARKS = \{(.*?)\n\};", panel_html(), re.S)
    assert block, "the panel no longer carries an ORBIT_MARKS table"
    rows = re.findall(r'(\w+):\s*\{\s*cls:\s*"([^"]+)",\s*glyph:\s*"([^"]+)",'
                      r'\s*label:\s*"([^"]+)"\s*\}', block.group(1))
    assert len(rows) == 4, rows
    return {key: {"cls": cls, "glyph": glyph, "label": label}
            for key, cls, glyph, label in rows}


def test_no_stage_state_can_be_mistaken_for_another_once_colour_is_taken_away():
    # §3: every state is carried by at least two channels. Take the colour out
    # of the four and the contours are still four different contours — a
    # one-pixel solid nine-radius box, the same box dashed, a two-pixel one, and
    # a two-pixel one with a sixteen-radius corner. Held in every media
    # environment, because a rule scoped to Winter Daylight is still a rule.
    for label, env in ENVIRONMENTS:
        shapes = {tone: stage_shape(tone, None, env) for tone in TONES}
        assert len(set(shapes.values())) == len(TONES), (label, shapes)


@pytest.mark.parametrize("interaction", sorted(INTERACTIONS))
@pytest.mark.parametrize("tone", TONES)
def test_the_stylesheet_resolves_one_stage_silhouette_touched_or_not(tone, interaction):
    # Owner invariant 1 on the Orbit's own carrier. The paint half is held for
    # every carrier the stylesheet declares by the general test above; this is
    # the shape half, spelt out for the four states the Orbit gives a stage,
    # because rounding a current stage's corner back to nine on hover would make
    # it read as a neutral one without repainting anything.
    for label, env in ENVIRONMENTS:
        assert stage_shape(tone, interaction, env) == stage_shape(tone, None, env), (
            f"{interaction} changed the silhouette declarations of {tone} in {label}")


def test_every_stage_mark_carries_a_glyph_and_a_spelt_out_label_of_its_own():
    # The second channel, and the one that survives any amount of colour loss.
    # Every mark a stage can carry spells a word beside its glyph, and no two
    # marks share either.
    marks = orbit_marks()
    assert set(marks) == {"current", "blocked", "waiting", "mismatch"}
    for key, row in marks.items():
        assert row["glyph"] and row["label"], key
    assert len({row["glyph"] for row in marks.values()}) == 4
    assert len({row["label"] for row in marks.values()}) == 4


def test_no_stage_mark_claims_a_phase_was_reached_finished_or_passed():
    # §2.2. Protocol v1 records no run history, so no word in this vocabulary
    # may assert one. Held as a property of what the words *say*: a mark is a
    # statement about right now — a lane is reporting here, a lane has gone
    # quiet, a person is being waited on, an assignment disagrees with a report
    # — and none of them is in the past tense.
    spoken = " ".join(row["label"] for row in orbit_marks().values()).lower()
    for claim in ("done", "complete", "completed", "finished", "passed", "reached",
                  "travelled", "traveled", "visited", "approved"):
        assert claim not in spoken.split(), (claim, spoken)


def _js_list(name: str) -> list[str]:
    """Parse one of the panel's declared string lists."""
    found = re.search(r"const " + name + r" = \[(.*?)\];", panel_html(), re.S)
    assert found, name
    return re.findall(r'"([^"]+)"', found.group(1))


def test_a_mismatch_is_read_out_in_a_chip_and_never_takes_a_stages_contour():
    # §2.3: the warning is non-blocking, and "non-blocking" has a shape here.
    # A mismatch is in the reading order, so it is always shown; it is not among
    # the marks that claim the contour, so the stage it sits on keeps the
    # silhouette it would have had; and the stylesheet declares no state for it
    # at all, so there is nothing for it to claim. All three, or a mismatch
    # could quietly start reading as a failure.
    assert "mismatch" in _js_list("MARK_ORDER")
    assert "mismatch" not in _js_list("TONES")
    assert _js_list("TONES") == ["current", "blocked", "waiting"]
    assert not [rule for rule in rules() if "orb--mismatch" in rule.selector]


def test_every_mark_a_stage_can_carry_is_in_the_reading_order():
    # The order decides what a reader sees; the vocabulary decides what exists.
    # A mark added to one and not the other would either never be drawn or be
    # drawn with no word to go with it.
    assert set(_js_list("MARK_ORDER")) == set(orbit_marks())


def connection_profile(kind: str, env: frozenset = frozenset()) -> dict[str, str]:
    """Resolve one form of the trajectory: a step, or the return to the first."""
    classes = {"trk"} | ({"trk--next"} if kind == "next" else set())
    return computed([ORBIT_FIELD, Element("svg"),
                     Element("path", frozenset(classes))], env=env)


def test_the_return_to_the_first_stage_differs_from_a_step_in_form_and_not_in_colour():
    # §2bis, the whole of what makes `next Run` honest. The connection that
    # closes the cycle has to be tellable from a step — the two mean different
    # things — and it may not be told apart by a status colour, because a status
    # colour would say something about the state of a pass the protocol cannot
    # record. So: same stroke, different dash, different arrow head.
    for label, env in ENVIRONMENTS:
        step, back = connection_profile("step", env), connection_profile("next", env)
        assert step["stroke"] == back["stroke"], label
        assert step.get("stroke-dasharray") != back.get("stroke-dasharray"), label
        assert step.get("marker-end") != back.get("marker-end"), label


def test_no_part_of_the_trajectory_is_painted_with_a_status_colour():
    # The other half: neutral means neutral. Neither form of the connection, nor
    # the arrow head, nor the label beside the return may spend the accent or any
    # of the three semantic tokens — an accented return would read as the current
    # step, and a --pass one would read as a lap completed.
    reserved = ("--accent", "--pass", "--wait", "--fail")
    for rule in rules():
        if not any(cls in rule.selector for cls in
                   (".trk", ".arw--orb", ".nextrun", ".lnk")):
            continue
        for prop, value in rule.decls.items():
            for token in reserved:
                assert token not in value, (rule.selector, prop, value)


def test_the_vertical_layout_tells_the_return_from_a_step_the_same_way():
    # The narrow layout draws its connections as bordered elements rather than
    # as arcs, and the same rule governs them: the return differs from a step by
    # its pattern, and both are drawn in the same neutral colour.
    link = [ORBIT_FIELD, Element("div", frozenset({"lnk"})), Element("i")]
    back = [ORBIT_FIELD, Element("div", frozenset({"lnk", "lnk--next"})), Element("i")]
    for label, env in ENVIRONMENTS:
        step, ret = computed(link, env=env), computed(back, env=env)
        assert step["border-left-color"] == ret["border-left-color"], label
        assert step["border-left-style"] != ret["border-left-style"], label
    # The name says "the vertical layout", and until now only the stylesheet was
    # read: nothing required drawOrbitColumn to write the class the rules above
    # are keyed on, and removing it left the whole suite green with the return
    # to the next Run drawn as an ordinary step. So the writer is read too, in
    # the same form the walk test below uses — the branch that recognises the
    # return is what emits the class, and the branch that emits a step does not.
    body = function_body("drawOrbitColumn")
    head, _, tail = body.partition('e.kind === "next"')
    assert tail, body
    assert "lnk--next" in re.findall(r'class:\s*"([^"]*)"', tail)[0].split()
    assert "lnk--next" not in head


STAGE = Element("div", frozenset({"orb", "orb--neutral"}))
WHO = Element("div", frozenset({"orb__who"}))

# Each part of the Orbit as the ancestors the panel actually gives it. Written
# as whole chains and not as one class, because the rules that style them are
# descendant rules: `.orb .orb__who` matches nothing when the model is handed an
# `.orb__who` with no `.orb` above it, and a guard reading `display` off that
# element resolves nothing and passes whatever the stylesheet says.
ORBIT_PARTS = {
    "stage": [ORBIT_FIELD, STAGE],
    "name": [ORBIT_FIELD, STAGE, Element("span", frozenset({"orb__name"}))],
    "marks": [ORBIT_FIELD, STAGE, Element("div", frozenset({"orb__marks"}))],
    "participants": [ORBIT_FIELD, STAGE, WHO],
    "harness": [ORBIT_FIELD, STAGE, WHO, Element("span", frozenset({"orb__hn"}))],
    "note": [ORBIT_FIELD, STAGE, WHO, Element("span", frozenset({"orb__note"}))],
    "vertical link": [ORBIT_FIELD, Element("div", frozenset({"lnk"}))],
    "return label": [ORBIT_FIELD, Element("span", frozenset({"nextrun"}))],
}


@pytest.mark.parametrize("interaction", [None, *sorted(INTERACTIONS)])
@pytest.mark.parametrize("part", sorted(ORBIT_PARTS))
def test_no_part_of_a_stage_is_declared_hidden_until_a_pointer_arrives(part,
                                                                      interaction):
    # §4: no hidden mandatory hover, in either layout. Every part of a stage —
    # its name, its marks, its participants, the connection labels — resolves
    # the same `display` with a pointer on it as without, and that value is
    # never `none`. The queue card's why-text is the panel's one disclosure and
    # it is not in this list; nothing in the Orbit may join it.
    resting = ORBIT_PARTS[part]
    chain = touched(resting, interaction)
    for label, env in ENVIRONMENTS:
        shown = computed(chain, env=env).get("display", "")
        assert shown != "none", (label, part, interaction)
        assert shown == computed(resting, env=env).get("display", ""), (label, part)


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
    # instead: at level "none" a lit card resolves exactly the declarations of a
    # card that is not lit at all, and at the two levels that mean something, it
    # does not.
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


def test_the_legend_key_of_a_status_echoes_the_silhouette_the_status_table_declares():
    # The legend is the one place a --fail swatch and an --accent swatch stand
    # side by side, and as identical squares hue was all that separated them.
    # The relation held here is monotonic: a status whose STATUS.rx is rounder
    # gets a key whose declared border-radius is rounder, and two statuses with
    # the same rx get keys with the same radius. Both numbers are read out of
    # the source — the STATUS table and the legend's inline styles.
    table, keys = status_table(), legend_keys()
    radius = {s: float(keys[s]["border-radius"].rstrip("px")) for s in STATUSES}
    corner = {s: float(table[s]["rx"]) for s in STATUSES}
    for a in STATUSES:
        for b in STATUSES:
            assert (corner[a] > corner[b]) == (radius[a] > radius[b]), (a, b)
            assert (corner[a] == corner[b]) == (radius[a] == radius[b]), (a, b)


def test_every_legend_key_declares_its_status_as_a_contour_and_not_as_a_flat_fill():
    # §4 reserves the accent for five roles and never for a large fill, so no key
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


# ── movement, and the accent's five roles ─────────────────────────────────
def animated() -> dict[str, str]:
    """Every selector the stylesheet animates, with the animation it declares.

    Any property in the ``animation`` family counts, not the shorthand alone.
    Reading the shorthand only was a hole with a shape: ``animation-name`` plus
    ``animation-iteration-count`` on two lines declares exactly the movement
    this table exists to enumerate, and would have appeared in it as nothing.
    """
    out: dict[str, str] = {}
    for rule in rules():
        family = {prop: value for prop, value in rule.decls.items()
                  if prop == "animation" or prop.startswith("animation-")}
        if not family:
            continue
        key = f"{rule.context} {rule.selector}".strip()
        out[key] = " ".join(value if prop == "animation" else f"{prop}:{value}"
                            for prop, value in sorted(family.items()))
    return out


def _root_values() -> dict[str, str]:
    dark, light = root_declarations()
    return dict(dark, **light)


def permanently_animated() -> set[str]:
    """Every selector the stylesheet gives an animation that never stops.

    ``infinite`` is looked for in the resolved value, custom properties
    included, because ``animation:throb 3s var(--forever)`` is the same
    permanent movement written where a scan of the declaration cannot see it.
    """
    values = _root_values()
    out = set()
    for key, declared in animated().items():
        text = declared
        for name in re.findall(r"var\((--[\w-]+)\)", declared):
            text += " " + values.get(name, "")
        if re.search(r"(?<![\w-])infinite(?![\w-])", text):
            out.add(key)
    return out


# Every movement the panel declares, and the whole of it. DEC-UI-4 left one:
# `.orb--arrived`, the ring a stage draws once when the panel has watched that
# stage become the current phase. `.dot` used to be the other — a 2.4 s loop
# behind which nothing happened — and the owner made it static on 2026-08-09,
# which is why no entry here repeats. Pinned two-sidedly: a new animation fails
# here, and so does deleting one without saying so.
MOVEMENT = {
    ".orb--arrived": "arrive .5s ease-out",
    "@media (prefers-reduced-motion:reduce) .orb--arrived": "none",
}


def test_the_stylesheet_animates_the_arrival_of_a_current_phase_and_nothing_else():
    # A declaration, not a movement: what is compared is the `animation` values
    # the cascade resolves, and the @keyframes names the stylesheet spells. The
    # second half is what makes the table's emptiness load-bearing in both
    # directions — a keyframes block nothing references fails here, so dead
    # movement cannot sit in the file waiting to be attached to something.
    # Which event puts the class on a stage is not decided by the stylesheet and
    # is not asked here; tests/test_panel_motion.py holds that half.
    assert animated() == MOVEMENT
    declared = set(re.findall(r"@keyframes\s+([\w-]+)", stylesheet()))
    used = {value.split()[0] for value in animated().values() if value != "none"}
    assert declared == used, (declared, used)


def test_no_animation_the_panel_declares_ever_repeats():
    # §5 forbids perpetual motion, and after DEC-UI-4 the panel declares none at
    # all: the one animation left runs once, on an event, and stops. The
    # executed sabotage this is written against is `@keyframes throb` plus
    # `.lit{animation:throb 3s ease-in-out infinite}`, a whole panel breathing.
    # Both the longhand spelling and an iteration count hidden behind a custom
    # property resolve here before the question is asked.
    assert permanently_animated() == set()


def test_the_current_stage_is_told_apart_without_any_movement_at_all():
    # The owner's first movement test, and the reason the pulse could be
    # deleted. What separates the current stage from every other one is its
    # contour weight, its corner and the word in its chip — all of them there
    # with animation switched off entirely.
    #
    # DEC-UI-4 gave the Orbit one animation, so "nothing here is animated" is no
    # longer the thing to assert. What is asserted instead is the relation that
    # sentence was standing in for: the four tones and the two connection forms
    # carry no animation at all, and the one class that does carry one moves no
    # property any of them is told apart by. A keyframes block that reached for
    # the contour, the corner or the paint would fail here — and so would
    # hanging an animation off `.orb--current` itself.
    moving = {key for key in animated()
              if any(part in key for part in (".orb", ".trk", ".lnk", ".nextrun"))}
    assert moving == {".orb--arrived",
                      "@media (prefers-reduced-motion:reduce) .orb--arrived"}, moving
    assert keyframe_properties("arrive") == {"box-shadow"}
    for tone in TONES:
        assert computed(stage_chain(tone)).get("box-shadow") is None, tone
    assert stage_shape("current") != stage_shape("neutral")
    assert orbit_marks()["current"]["glyph"] and orbit_marks()["current"]["label"]


def test_the_deleted_pulse_leaves_no_reference_anywhere_in_the_panel():
    # The class the old cycle ring put on its current phase. It has no writer
    # and no rule left, and a dead selector is a place a movement gets
    # reattached without anyone deciding to. Held by absence, which is the one
    # form a sabotage cannot satisfy while removing the thing.
    assert "pulse" not in panel_html()


def test_every_animation_the_stylesheet_declares_is_switched_off_by_reduced_motion():
    # A person who has asked their system for less movement gets none. Held as a
    # relation over the sheet rather than as a search for the media query: every
    # selector carrying a live animation must carry a second declaration, inside
    # the reduced-motion condition, that stops it. Adding an animated element
    # and forgetting the override fails here without this test knowing what the
    # element is called.
    reduce = [c for c in media_contexts() if "reduced-motion" in c]
    assert len(reduce) == 1, reduce
    stopped = {key[len(reduce[0]):].strip() for key, value in animated().items()
               if key.startswith(reduce[0]) and value == "none"}
    for key, value in animated().items():
        if key.startswith("@media") or value == "none":
            continue
        assert key in stopped, f"{key} keeps moving under reduced motion"


def test_a_reader_who_asked_for_less_movement_gets_the_arrival_instantly():
    # The owner's requirement for the one animation there is, resolved through
    # the cascade rather than read off the sheet: the stage that has just become
    # current animates for a reader who did not ask otherwise, declares no
    # animation at all for a reader who did, and is the same silhouette either
    # way. The third assertion is the point of the first two — what is switched
    # off is the movement, not the mark.
    reduce = frozenset(c for c in media_contexts() if "reduced-motion" in c)
    chain = [ORBIT_FIELD,
             Element("div", frozenset({"orb", "orb--current", "orb--arrived"}))]
    assert computed(chain)["animation"] == MOVEMENT[".orb--arrived"]
    assert computed(chain, env=reduce)["animation"] == "none"
    assert stage_shape("current", env=reduce) == stage_shape("current")


# The five roles §4 reserves December Red for: the current Orbit stage,
# human-control points, the primary action, focus and selection, and a small
# brand mark. Every place the stylesheet spends the accent is named here with
# the role it spends it on, so a new accent site cannot appear without someone
# deciding which role it is. Three of them are open questions carried to the
# owner rather than settled roles, and they say so: an honest map beats a tidy
# one.
#
# The list was six until 2026-08-10, when the owner reserved the travelled
# trajectory until a structural Run history exists (plan §8.6) and the roles
# after it moved up one. The table never had a row for it: nothing in the panel
# ever spent the accent there, and the guard above forbids it outright — which
# is the shape the contradiction had while the plan still counted it.
ACCENT_ROLES = {
    ":focus-visible": "role 4 — focus, on every focusable element including a node",
    ".node[aria-pressed=\"true\"] .halo": "role 4 — selection, on the outer ring",
    ".orb--current": "role 1 — the current Orbit stage, as its contour",
    ".vd--run": "role 1 — the same stage's chip, which spells the word beside it",
    ".vd--run .gl": "role 1 — that chip's glyph",
    ".mark__dot": "role 5 — the brand mark",
    ".copy": "role 3 — the primary action, the decision-brief button",
    ".copy:hover": "role 3 — the same button under the pointer",
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
