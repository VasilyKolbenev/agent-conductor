"""The panel's stylesheet, parsed into rules and resolved through the cascade.

Every guard in this module is written against a *relation* between declarations
rather than against the presence of a word. A test that greps the source for
``:hover`` passes as soon as the string exists and says nothing about what the
rule does; a test that computes the winning declarations for a node with and
without an interactive state says exactly the thing the panel promises. The
sabotage that motivated this module — ``.node:hover rect{stroke:var(--accent);
rx:14px}`` — is invisible to the first kind of test and fails the second.

So the module builds a small cascade: it parses the ``<style>`` block into
rules, computes specificity, matches selectors against described elements, and
returns the declarations that win. Everything else here is a claim expressed in
terms of that.

The panel's own source is read here too (:func:`panel_html`), and the other two
panel modules import it from this one. That is deliberate rather than
convenient: this module owns the parsing, and duplicating a stylesheet parser
into a colour module would be worse than one directed import.
"""
import re
from pathlib import Path
from typing import NamedTuple

import pytest

PANEL = Path(__file__).resolve().parents[1] / "src" / "conductor" / "panel" / "index.html"


def panel_html() -> str:
    """Return the packaged panel source."""
    return PANEL.read_text(encoding="utf-8")


# ── the stylesheet, parsed ─────────────────────────────────────────────────
class Rule(NamedTuple):
    """One selector of one CSS rule, with the declarations it carries."""

    selector: str
    decls: dict[str, str]
    order: int
    context: str


class Element(NamedTuple):
    """An element as the cascade needs to see it, with no DOM behind it."""

    tag: str
    classes: frozenset[str] = frozenset()
    states: frozenset[str] = frozenset()
    attrs: dict[str, str] = {}


def E(tag: str, *classes: str, states: tuple = (), **attrs: str) -> Element:
    """Build an :class:`Element`; the terse form the pair tables read best in."""
    return Element(tag, frozenset(classes), frozenset(states), dict(attrs))


def _split_top_level(text: str, sep: str) -> list[str]:
    out, depth, cur = [], 0, []
    for ch in text:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == sep and depth == 0:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur))
    return out


def _declarations(body: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for chunk in _split_top_level(body, ";"):
        prop, sep, value = chunk.partition(":")
        if not sep:
            continue
        prop, value = prop.strip(), value.replace("!important", "").strip()
        if prop and value:
            out[prop] = value
    return out


def _collect(css: str, context: str, out: list[Rule]) -> None:
    i, n, prelude = 0, len(css), []
    while i < n:
        if css[i] != "{":
            prelude.append(css[i])
            i += 1
            continue
        head = "".join(prelude).strip()
        prelude = []
        depth, j = 1, i + 1
        while j < n and depth:
            depth += (css[j] == "{") - (css[j] == "}")
            j += 1
        body = css[i + 1:j - 1]
        if head.startswith("@"):
            if not head.startswith("@keyframes"):
                _collect(body, head, out)
        else:
            decls = _declarations(body)
            for sel in head.split(","):
                out.append(Rule(sel.strip(), decls, len(out), context))
        i = j


def stylesheet(html: str | None = None) -> str:
    """Return the panel's CSS with comments removed."""
    block = re.search(r"<style>(.*?)</style>", html or panel_html(), re.S)
    assert block, "the panel no longer carries a single inline <style> block"
    return re.sub(r"/\*.*?\*/", " ", block.group(1), flags=re.S)


def rules(html: str | None = None) -> list[Rule]:
    """Parse the panel's stylesheet into one :class:`Rule` per selector."""
    out: list[Rule] = []
    _collect(stylesheet(html), "", out)
    return out


# ── matching and specificity ───────────────────────────────────────────────
_TOKEN = re.compile(r"[.#][\w-]+|\[[^\]]*\]|::?[\w-]+(?:\([^)]*\))?")
_COMPOUND = re.compile(r"([a-z][\w-]*|\*)?((?:[.#][\w-]+|\[[^\]]*\]|"
                       r"::?[\w-]+(?:\([^)]*\))?)*)")


def specificity(selector: str) -> tuple[int, int, int]:
    """Return the (id, class, type) specificity triple of one selector."""
    ids = len(re.findall(r"#[\w-]+", selector))
    classes = (len(re.findall(r"\.[\w-]+", selector))
               + len(re.findall(r"\[[^\]]*\]", selector))
               + len(re.findall(r"(?<!:):[\w-]+", selector)))
    types = (len(re.findall(r"(?:^|[\s])([a-z][\w-]*)", selector))
             + len(re.findall(r"::[\w-]+", selector)))
    return ids, classes, types


def _compound_matches(compound: str, el: Element) -> bool:
    m = _COMPOUND.fullmatch(compound)
    if not m:
        return False
    tag, rest = m.group(1), m.group(2) or ""
    if tag and tag not in ("*", el.tag):
        return False
    for token in _TOKEN.findall(rest):
        if token.startswith("."):
            if token[1:] not in el.classes:
                return False
        elif token.startswith("#"):
            if el.attrs.get("id") != token[1:]:
                return False
        elif token.startswith("["):
            name, sep, value = token[1:-1].partition("=")
            name, value = name.strip(), value.strip().strip("\"'")
            if sep and el.attrs.get(name) != value:
                return False
            if not sep and name not in el.attrs:
                return False
        elif token.lstrip(":") not in el.states:
            return False
    return True


def _selector_matches(selector: str, chain: list[Element]) -> bool:
    compounds = selector.split()
    if not compounds or not _compound_matches(compounds[-1], chain[-1]):
        return False
    index = len(chain) - 2
    for compound in reversed(compounds[:-1]):
        while index >= 0 and not _compound_matches(compound, chain[index]):
            index -= 1
        if index < 0:
            return False
        index -= 1
    return True


def computed(chain: list[Element], html: str | None = None) -> dict[str, str]:
    """Resolve the declarations that win for the last element of ``chain``.

    Args:
        chain: Ancestors outermost first; the element itself last.
        html: Panel source override, for tests that mutate it.

    Returns:
        Mapping of property to winning value, by specificity then source order.
    """
    won: dict[str, tuple] = {}
    for rule in rules(html):
        if not _selector_matches(rule.selector, chain):
            continue
        key = (specificity(rule.selector), rule.order)
        for prop, value in rule.decls.items():
            if prop not in won or won[prop][0] <= key:
                won[prop] = (key, value)
    return {prop: value for prop, (_, value) in won.items()}


def test_the_stylesheet_uses_only_the_selector_forms_this_cascade_models():
    # The cascade above understands descendant combinators and nothing else.
    # If the panel ever grows a `>`, `+` or `~`, every guard built on it would
    # start passing by failing to match, so the model has to say so out loud.
    for rule in rules():
        assert not re.search(r"[>+~]", rule.selector), rule.selector
        for compound in rule.selector.split():
            assert _COMPOUND.fullmatch(compound), rule.selector


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

# Every way the panel can say "this element is being interacted with". The
# closing test below proves the stylesheet contains no other.
INTERACTIONS = {
    "hover": (frozenset({"hover"}), {}),
    "focus": (frozenset({"focus-visible", "focus"}), {}),
    "selected": (frozenset(), {"aria-pressed": "true"}),
}


def node_chain(status: str, interaction: str | None = None) -> list[Element]:
    """Build the (group, status box) chain for one node in one state."""
    states, attrs = INTERACTIONS[interaction] if interaction else (frozenset(), {})
    cls = status_table()[status]["cls"]
    group = Element("g", frozenset({"node", "node--" + cls}), states,
                    {"aria-pressed": "false", **attrs})
    return [group, Element("rect", frozenset({"box"}), states, {})]


def box_profile(status: str, interaction: str | None = None) -> dict[str, str]:
    """Return everything that decides how one status draws its contour."""
    win = computed(node_chain(status, interaction))
    profile = {prop: win.get(prop) for prop in SILHOUETTE}
    # rx arrives as a presentation attribute from STATUS.rx unless a rule
    # overrides it, and a rule overriding it is exactly the impersonation this
    # guards against — so the attribute is part of the profile.
    profile["rx"] = win.get("rx") or "attribute:" + status_table()[status]["rx"]
    return profile


def halo_profile(status: str, interaction: str | None = None) -> dict[str, str]:
    """Return how the interaction ring is painted for one node state."""
    chain = node_chain(status, interaction)
    chain[-1] = Element("rect", frozenset({"halo"}), chain[-1].states, {})
    win = computed(chain)
    return {prop: win.get(prop) for prop in ("stroke", "stroke-width", "fill")}


@pytest.mark.parametrize("interaction", sorted(INTERACTIONS))
@pytest.mark.parametrize("status", STATUSES)
def test_a_node_draws_the_same_status_contour_whether_or_not_it_is_being_touched(
        status, interaction):
    # The invariant in one line: status owns the inner silhouette. Hovering,
    # focusing or selecting a node may add to it but may not repaint, reshape
    # or reweight it, so a failing node under the cursor is still a failing
    # node. Nothing here looks for the word "hover" — the two profiles are
    # computed through the cascade and compared.
    assert box_profile(status, interaction) == box_profile(status), (
        f"{interaction} changed how {status} draws itself")


@pytest.mark.parametrize("interaction", sorted(INTERACTIONS))
def test_an_interaction_is_still_visible_even_though_it_cannot_touch_the_status(
        interaction):
    # The other half: separating the channels is only honest if the second
    # channel actually draws something. The ring has to change, on every
    # status, or "interaction has its own carrier" would be a way of saying
    # interaction is invisible.
    for status in STATUSES:
        assert halo_profile(status, interaction) != halo_profile(status), status


def test_no_status_can_be_mistaken_for_another_once_colour_is_taken_away():
    # Strip the paint out of every profile and the six must still be six.
    shapes = {s: tuple((k, v) for k, v in sorted(box_profile(s).items())
                       if k not in ("stroke", "fill"))
              + (status_table()[s]["glyph"], status_table()[s]["label"])
              for s in STATUSES}
    assert len(set(shapes.values())) == len(STATUSES), shapes


def test_the_stylesheet_declares_no_interactive_state_this_module_does_not_model():
    # The equality tests above are only as complete as the list of states they
    # try. Any other interactive selector in the stylesheet would sit outside
    # them, so its appearance has to break something.
    modelled = {"hover", "focus", "focus-visible", "aria-pressed"}
    # Selectors that key on something other than a person touching the element:
    # a document position, a visibility flag, a disclosure flag, and the light
    # level, which is read from state.json rather than from the pointer.
    inert = {"root", "last-child", "hidden", "aria-expanded", "data-attention"}
    for rule in rules():
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
    running, fail = box_profile("running"), box_profile("fail")
    assert running["rx"] != fail["rx"], "running and fail draw the same corner radius"
    assert running["stroke-width"] != fail["stroke-width"]
    table = status_table()
    assert table["running"]["glyph"] != table["fail"]["glyph"]
    assert table["running"]["label"] != table["fail"]["label"]


def function_body(name: str, html: str | None = None) -> str:
    """Return the source of one top-level ``function`` in the panel's script."""
    src = html or panel_html()
    start = src.index("function " + name + "(")
    depth, i = 0, src.index("{", start)
    j = i
    while j < len(src):
        depth += (src[j] == "{") - (src[j] == "}")
        j += 1
        if depth == 0:
            return src[i + 1:j - 1]
    raise AssertionError(f"{name} is not a balanced function body")


def test_the_status_box_and_the_interaction_ring_are_two_elements_in_every_node():
    # The cascade guards above describe a node with a .box and a .halo. If
    # drawNodes stopped emitting either of them, those guards would be
    # reasoning about an element that is no longer drawn.
    body = function_body("drawNodes")
    assert re.search(r'sv\("rect",\s*\{\s*class:\s*"halo"', body), body
    assert re.search(r'sv\("rect",\s*\{\s*class:\s*"box"', body), body


# ── the light level: conditional, data-keyed, and never the accent ─────────
LIT_MATERIAL = ("--panel-lit", "--contour-lit", "--lift-1", "--lift-2")


def _light_rules() -> list[Rule]:
    return [r for r in rules() if "data-attention" in r.selector]


def test_a_card_can_only_reach_the_lit_material_through_the_light_level():
    # Absence of attention is a real state and has to look like one. A rule
    # that hands out the lit surface, the lift or the brightened contour
    # without asking the light level would make the panel glow permanently,
    # which is the direction's central prohibition stated in reverse.
    for rule in rules():
        if rule.selector in (":root",) or rule.context.startswith("@media (prefers-color"):
            continue                       # the token declarations themselves
        spent = [prop for prop, value in rule.decls.items()
                 if any(token in value for token in LIT_MATERIAL)]
        if spent:
            assert "data-attention" in rule.selector, (rule.selector, spent)


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


def test_the_parser_reads_every_rule_of_the_panel_to_its_closing_brace():
    # The parser is the foundation every claim below stands on, so it says out
    # loud what it found: the multi-line light rule whose second line used to be
    # invisible, and a rule inside a media query, both complete.
    found = {r.selector: r for r in rules()}
    high = found['html[data-attention="high"] .lit']
    assert set(high.decls) == {"background", "box-shadow", "border-color"}
    assert found[".grid--split"].context.startswith("@media")


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
