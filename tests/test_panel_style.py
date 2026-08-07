"""The panel's stylesheet, parsed into whole rules rather than scanned as text.

A guard over CSS written as a search through the file is a guard over a string.
`re.findall(r"html\\[data-attention=[^\\n]*")` reads the first line of a rule and
stops: the panel's one multi-line light rule keeps `border-color` on its second
line, so a light level that painted itself December Red passed that check
untouched. And a check that a declaration is absent from a *selector* cannot see
a new rule that hands the same declaration to everyone unconditionally.

So this module parses. It turns the ``<style>`` block into one :class:`Rule` per
selector, with the declarations that rule actually carries, and every claim below
is expressed over those rules instead of over the source text.

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


def root_declarations() -> tuple[dict[str, str], dict[str, str]]:
    """Return the dark `:root` declarations and the light-media overrides."""
    dark = next(r.decls for r in rules() if r.selector == ":root" and not r.context)
    light = next(r.decls for r in rules()
                 if r.selector == ":root" and "prefers-color-scheme:light" in r.context)
    return dark, light


def test_the_parser_reads_every_rule_of_the_panel_to_its_closing_brace():
    # The parser is the foundation every claim below stands on, so it says out
    # loud what it found: the multi-line light rule whose second line used to be
    # invisible, and a rule inside a media query, both complete.
    found = {r.selector: r for r in rules()}
    high = found['html[data-attention="high"] .lit']
    assert set(high.decls) == {"background", "box-shadow", "border-color"}
    assert found[".grid--split"].context.startswith("@media")


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
        if rule.selector == ":root":
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
