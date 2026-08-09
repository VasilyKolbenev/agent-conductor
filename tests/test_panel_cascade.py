"""The panel's stylesheet and script, parsed into a cascade the guards can reason on.

Every guard built on this module is written against a *relation* between
declarations rather than against the presence of a word. A test that greps the
source for ``:hover`` passes as soon as the string exists and says nothing about
what the rule does; a test that computes the winning declarations for an element
with and without an interactive state says exactly the thing the panel promises.

So this module builds a small cascade: it parses the ``<style>`` block into
rules, computes specificity, matches selectors against described elements, reads
each rule in the ``@media`` condition it was declared under, and returns the
declarations that win. It also derives, from the stylesheet itself, the set of
elements the panel gives a state to — because a hand-written list of carriers is
how the chips ended up outside the guard that their own prose claimed to be in.

The panel's source is read here (:func:`panel_html`, :func:`script`) and the
other panel modules import it from this one. That is deliberate rather than
convenient: this module owns the parsing, and a second copy of a stylesheet
parser in a colour module would be worse than one directed import.

What this cascade is and is not. It is a model of the panel's *source text*,
built by parsing characters; it is not a browser and it does not render
anything. ``computed`` returns the declarations this model says would win, for
an element this model was handed — which is a structural fact about the
stylesheet, not a fact about a pixel. Every guard built on it inherits that
limit, so no name or docstring in these modules may claim a rendered result.
Sabotages that keep the behaviour and change the spelling pass here by design;
§10 of the plan carries the post-alpha work that would catch them.
"""
import re
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

import pytest

PANEL = Path(__file__).resolve().parents[1] / "src" / "conductor" / "panel" / "index.html"


@lru_cache(maxsize=1)
def panel_html() -> str:
    """Return the packaged panel source."""
    return PANEL.read_text(encoding="utf-8")


# A comment is not code, and a guard that reads source has to say so. The
# lexer below walks string literals first, so an apostrophe or a `/*` inside a
# quoted string is left alone; everything that is genuinely a comment becomes a
# space. Without this, every source-reading guard in this repository can be
# walked through by leaving the guarded expression in a comment beside the line
# that no longer does it — which is how two of them were walked through.
_LEXEME = re.compile(r'"(?:[^"\\\n]|\\.)*"'
                     r"|'(?:[^'\\\n]|\\.)*'"
                     r"|`(?:[^`\\]|\\.)*`"
                     r"|/\*.*?\*/"
                     r"|//[^\n]*", re.S)


def strip_comments(source: str) -> str:
    """Return ``source`` with comments blanked and string literals untouched."""
    return _LEXEME.sub(lambda m: m.group(0) if m.group(0)[0] in "\"'`" else " ", source)


@lru_cache(maxsize=4)
def script(html: str | None = None) -> str:
    """Return the panel's script block, comments removed."""
    block = re.search(r"<script>(.*)</script>", html or panel_html(), re.S)
    assert block, "the panel no longer carries a single inline <script> block"
    return strip_comments(block.group(1))


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


@lru_cache(maxsize=4)
def stylesheet(html: str | None = None) -> str:
    """Return the panel's CSS with comments removed."""
    block = re.search(r"<style>(.*?)</style>", html or panel_html(), re.S)
    assert block, "the panel no longer carries a single inline <style> block"
    return re.sub(r"/\*.*?\*/", " ", block.group(1), flags=re.S)


@lru_cache(maxsize=4)
def rules(html: str | None = None) -> tuple[Rule, ...]:
    """Parse the panel's stylesheet into one :class:`Rule` per selector."""
    out: list[Rule] = []
    _collect(stylesheet(html), "", out)
    return tuple(out)


def media_contexts(html: str | None = None) -> tuple[str, ...]:
    """Every ``@media`` condition the stylesheet declares, as written."""
    return tuple(sorted({rule.context for rule in rules(html) if rule.context}))


def light_context(html: str | None = None) -> str:
    """The one media condition that selects the Winter Daylight theme."""
    found = [c for c in media_contexts(html) if "prefers-color-scheme:light" in c]
    assert len(found) == 1, found
    return found[0]


def environments(theme: str = "dark", html: str | None = None) -> list[tuple]:
    """Every media environment the stylesheet can be read in, for one theme.

    Args:
        theme: ``"dark"`` or ``"light"``; the light theme is itself a context.
        html: Panel source override, for tests that mutate it.

    Returns:
        ``(label, active conditions)`` pairs — the theme alone, then the theme
        together with each other condition the stylesheet declares.
    """
    light = light_context(html)
    base = frozenset({light}) if theme == "light" else frozenset()
    short = lambda c: re.sub(r"[^a-z0-9]+", "-", c[len("@media"):].strip()).strip("-")
    return [(theme, base)] + [(f"{theme}+{short(c)}", base | {c})
                              for c in media_contexts(html) if c != light]


ENVIRONMENTS = [pair for theme in ("dark", "light") for pair in environments(theme)]


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


def computed_keyed(chain: list[Element], html: str | None = None,
                   env: frozenset = frozenset()) -> dict[str, tuple]:
    """Resolve the winning declarations, each with the cascade key that won it.

    Args:
        chain: Ancestors outermost first; the element itself last.
        html: Panel source override, for tests that mutate it.
        env: The ``@media`` conditions that are true. A rule declared inside a
            condition takes part only when that condition is in this set —
            without which a rule that applies in one theme or at one width is
            invisible whenever an unconditional rule follows it in the file,
            and that is exactly where a real one would sit.

    Returns:
        Mapping of property to ``((specificity, order), value)``.
    """
    won: dict[str, tuple] = {}
    for rule in rules(html):
        if rule.context and rule.context not in env:
            continue
        if not _selector_matches(rule.selector, chain):
            continue
        key = (specificity(rule.selector), rule.order)
        for prop, value in rule.decls.items():
            if prop not in won or won[prop][0] <= key:
                won[prop] = (key, value)
    return won


def computed(chain: list[Element], html: str | None = None,
             env: frozenset = frozenset()) -> dict[str, str]:
    """Resolve the declarations that win for the last element of ``chain``."""
    return {prop: value for prop, (_, value) in computed_keyed(chain, html, env).items()}


def test_the_stylesheet_uses_only_the_selector_forms_this_cascade_models():
    # The cascade above understands descendant combinators and nothing else.
    # If the panel ever grows a `>`, `+` or `~`, every guard built on it would
    # start passing by failing to match, so the model has to say so out loud.
    for rule in rules():
        assert not re.search(r"[>+~]", rule.selector), rule.selector
        for compound in rule.selector.split():
            assert _COMPOUND.fullmatch(compound), rule.selector




# Every way the panel can say "this element is being interacted with". The
# closing test below proves the stylesheet contains no other.
INTERACTIONS = {
    "hover": (frozenset({"hover"}), {}),
    "focus": (frozenset({"focus-visible", "focus"}), {}),
    "selected": (frozenset(), {"aria-pressed": "true"}),
}


_INTERACTION_TOKENS = {"hover", "focus", "focus-visible", "aria-pressed"}


def touched(chain, interaction: str | None) -> list[Element]:
    """Put one interactive state on every element of a chain, as a pointer does."""
    if interaction is None:
        return list(chain)
    states, attrs = INTERACTIONS[interaction]
    return [el._replace(states=el.states | states, attrs={**el.attrs, **attrs})
            for el in chain]




# ── every carrier of a state, derived from the stylesheet ──────────────────
# Owner invariant 1 is not about map nodes. It is about anything the panel
# gives a state to: a chip's border, a queue card's left edge, the ring's
# current stage. Listing those by hand is how the chips ended up outside the
# guard while the panel's own prose called their border a status carrier — so
# the list below is read out of the stylesheet instead.
SEMANTIC = ("--pass", "--wait", "--fail")

# What "how this element reads" means: its own paint plus the shape properties
# a silhouette is made of. The four border sides are resolved from whichever
# shorthand won them, which is what `border-color` on :hover quietly overrode.
PAINTS = ("color", "background", "background-color", "fill", "stroke",
          "stroke-width", "stroke-dasharray", "rx", "opacity")
_SIDES = ("top", "right", "bottom", "left")
_COLOUR = re.compile(r"var\(--[\w-]+\)|color-mix\(.*\)|#[0-9a-fA-F]{3,8}"
                     r"|\btransparent\b|\bcurrentColor\b")
_VARIANT = re.compile(r"\.([a-z]+)--([a-z]+)")


def _border_sides(prop: str) -> tuple[str, ...] | None:
    """Which border sides a declaration paints, or ``None`` if it paints none."""
    if prop in ("border", "border-color"):
        return _SIDES
    parts = prop.split("-")
    if parts[0] == "border" and len(parts) in (2, 3) and parts[1] in _SIDES \
            and (len(parts) == 2 or parts[2] == "color"):
        return (parts[1],)
    return None


def paint_profile(chain, interaction: str | None = None, env: frozenset = frozenset(),
                  html: str | None = None) -> dict[str, str]:
    """Return every declaration that decides how an element reads."""
    keyed = computed_keyed(touched(chain, interaction), html, env)
    profile = {prop: value for prop, (_, value) in keyed.items() if prop in PAINTS}
    sides: dict[str, tuple] = {}
    for prop, (key, value) in keyed.items():
        which = _border_sides(prop)
        found = which and _COLOUR.search(value)
        if not found:
            continue
        for side in which:
            if side not in sides or sides[side][0] <= key:
                sides[side] = (key, found.group(0))
    profile.update({f"border-{side}-color": value for side, (_, value) in sides.items()})
    return profile


def _interactive(selector: str) -> bool:
    names = set()
    for token in _TOKEN.findall(selector):
        if token.startswith("::"):
            continue
        if token.startswith(":"):
            names.add(token.lstrip(":").split("(")[0])
        elif token.startswith("["):
            names.add(token[1:-1].partition("=")[0].strip())
    return bool(names & _INTERACTION_TOKENS)


def _classes_of(compound: str) -> set[str]:
    m = _COMPOUND.fullmatch(compound)
    assert m, compound
    return {t[1:] for t in _TOKEN.findall(m.group(2) or "") if t.startswith(".")}


@lru_cache(maxsize=4)
def class_companions(html: str | None = None) -> dict[str, frozenset]:
    """For each ``base--`` family, the classes the panel writes beside it.

    Read out of the panel's own class lists — the markup's ``class="…"`` and the
    script's ``class:`` literals — so an element is modelled the way the panel
    builds it. ``class: "pill p--" + st.cls`` is what makes ``.pill`` reach a
    ``.p--fail`` chip, and no test here knows that by heart.
    """
    lists = re.findall(r'class="([^"]*)"', html or panel_html())
    lists += re.findall(r'"([^"\n]*)"', script(html))
    out: dict[str, set] = {}
    for words in (text.split() for text in lists):
        for word in words:
            m = re.fullmatch(r"([a-z]+)--([a-z]*)", word)
            if m:
                out.setdefault(m.group(1), set()).update(
                    w for w in words if w != word and re.fullmatch(r"[a-z][\w-]*", w))
    styled = {cls for rule in rules(html) for compound in rule.selector.split()
              for cls in _classes_of(compound)}
    for base in {base for rule in rules(html)
                 for base, _ in _VARIANT.findall(rule.selector)}:
        if base in styled:
            out.setdefault(base, set()).add(base)
    return {base: frozenset(companions) for base, companions in out.items()}


def _element_of(compound: str, html: str | None = None) -> Element:
    """Build the element one selector compound describes, companions included."""
    classes = _classes_of(compound)
    companions = class_companions(html)
    for cls in list(classes):
        base, sep, _ = cls.partition("--")
        if sep:
            classes |= set(companions.get(base, ()))
    return Element(_COMPOUND.fullmatch(compound).group(1) or "*",
                   frozenset(classes), frozenset(), {})


class Carrier(NamedTuple):
    """One element the stylesheet gives a state to."""

    label: str
    chain: tuple


@lru_cache(maxsize=4)
def carriers(html: str | None = None) -> tuple[Carrier, ...]:
    """Every element the stylesheet marks with a state, derived from the sheet.

    Two sources, both structural. A *family* is any ``.base--variant`` class the
    stylesheet writes; each variant, the bare base, and every descendant the
    sheet styles under them is a carrier. A *semantic edge* is any rule painting
    with --pass, --wait or --fail, which covers carriers that have no variants
    at all — the queue card's --wait left edge is one.

    Descendants come from non-interactive selectors only. ``.halo`` is styled
    solely by interactive rules, and that is exactly what makes it the
    interaction channel rather than something a status owns.
    """
    families: dict[str, set[str]] = {}
    for rule in rules(html):
        for base, variant in _VARIANT.findall(rule.selector):
            families.setdefault(base, set()).add(variant)

    tails: dict[str, set[tuple]] = {}
    for rule in rules(html):
        if _interactive(rule.selector):
            continue
        compounds = rule.selector.split()
        head = _classes_of(compounds[0])
        for base in families:
            if base in head or any(cls.startswith(base + "--") for cls in head):
                tails.setdefault(base, set()).add(tuple(compounds[1:]))

    out: dict[str, Carrier] = {}
    for base, variants in sorted(families.items()):
        for cls in [f"{base}--{v}" for v in sorted(variants)] + [base]:
            head = _element_of("." + cls, html)
            for tail in sorted(tails.get(base, {()})):
                label = " ".join(("." + cls, *tail))
                out[label] = Carrier(label, (head, *(_element_of(c, html) for c in tail)))
    for rule in rules(html):
        if _interactive(rule.selector) or not any(
                token in value for value in rule.decls.values() for token in SEMANTIC):
            continue
        out.setdefault(rule.selector, Carrier(
            rule.selector, tuple(_element_of(c, html) for c in rule.selector.split())))
    return tuple(out.values())


def test_every_state_the_stylesheet_declares_appears_in_the_carrier_set():
    # What is done with the carriers is tests/test_panel_style.py's business;
    # this is the derivation saying what it found. Two ways it could silently
    # narrow: a family whose element this module cannot build, and a compound
    # that names a tag beside a carrier class — the cascade would then refuse to
    # match the untagged element the carrier list builds, and every assertion
    # made about that carrier would pass without testing anything.
    guarded = {cls for carrier in carriers() for cls in carrier.chain[0].classes}
    declared = {f"{base}--{variant}" for rule in rules()
                for base, variant in _VARIANT.findall(rule.selector)}
    assert declared <= guarded, declared - guarded
    for rule in rules():
        for compound in rule.selector.split():
            tag = _COMPOUND.fullmatch(compound).group(1)
            if tag:
                assert not (_classes_of(compound) & guarded), rule.selector
    # And the shapes the invariant is really about are in there, by name.
    # `.orb--current` and `.trk--next` are the Orbit's two: the stage the panel
    # marks as current, and the one connection that must never read as a status.
    for label in (".node--fail .box", ".p--fail", ".vd--bad .gl",
                  ".orb--current", ".trk--next", ".ask"):
        assert label in {carrier.label for carrier in carriers()}, label



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


def function_body(name: str, html: str | None = None) -> str:
    """Return the source of one top-level ``function``, comments removed.

    Comments are gone before the braces are counted, so an expression left in a
    comment beside the line that no longer evaluates it is not source any more.
    """
    src = script(html)
    start = src.index("function " + name + "(")
    depth, i = 0, src.index("{", start)
    j = i
    while j < len(src):
        depth += (src[j] == "{") - (src[j] == "}")
        j += 1
        if depth == 0:
            return src[i + 1:j - 1]
    raise AssertionError(f"{name} is not a balanced function body")



_JS_WORDS = {"return", "typeof", "new", "null", "true", "false", "undefined", "in",
             "of", "void", "delete", "instanceof", "const", "let", "for", "if", "else",
             "while", "break", "continue", "function", "this"}


def free_names(source: str, bound: set[str]) -> set[str]:
    """Identifiers a fragment of JavaScript reads from outside itself.

    String literals, property reads and the keys of object literals are removed
    first — none of them is a name the fragment reaches for — so what is left is
    what it does reach for. Everything a caller declares as ``bound`` —
    parameters, locals, loop variables, the properties an object literal
    declares — is subtracted, and what remains is the fragment's dependence on
    the world around it. A test written against this asks what a function is
    *allowed to depend on* without having to know what the forbidden
    dependencies are called.

    The identifier pattern refuses to start inside a word, or `1e-9` would
    report a dependence on something called `e`.
    """
    source = re.sub(r'"[^"]*"|\'[^\']*\'|`[^`]*`', " ", source)   # string literals
    source = re.sub(r"\.\s*[A-Za-z_$][\w$]*", " ", source)        # property reads
    source = re.sub(r"([{,]\s*)[A-Za-z_$][\w$]*\s*:", r"\1", source)   # literal keys
    return set(re.findall(r"(?<![\w$])[A-Za-z_$][\w$]*", source)) - bound - _JS_WORDS


def test_the_parser_reads_every_rule_of_the_panel_to_its_closing_brace():
    # The parser is the foundation every claim below stands on, so it says out
    # loud what it found: the multi-line light rule whose second line used to be
    # invisible, and a rule inside a media query, both complete.
    found = {r.selector: r for r in rules()}
    high = found['html[data-attention="high"] .lit']
    assert set(high.decls) == {"background", "box-shadow", "border-color"}
    assert found[".grid--split"].context.startswith("@media")

