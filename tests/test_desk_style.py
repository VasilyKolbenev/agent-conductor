"""desk.css, read through the panel's cascade model rather than grepped.

The desk is the window that replaces the Studio's five tabs, and its stylesheet
arrives under the Studio's discipline: nothing colour-bearing is written by hand
twice. Every rule that paints a mark is either a MEASURED row -- its declaration
resolved through the cascade under every media environment the sheet declares,
composited onto the surface its chain stands on, and held to its WCAG floor in
both themes -- or an EXEMPT with the reason written beside it. A new colour
fails the completeness check until it arrives with a row or a reason.

The palette is the approved concept's (`layout-v4` / `mostik.css`, the evergreen
ground and the lime "ion" accent, in the dark theme and its light pair), and it
is pinned here value by value: a token drifting off the concept reds, and so does
a third `:root` block or a manual `data-theme` block that stops being exactly the
measured system palette. Web fonts of the concept are not shipped: the panel
loads nothing from another origin, so the font stacks are system stacks.

Like `test_studio_style.py` this is a model of SOURCE TEXT. It renders nothing;
the rendered half is `browser_tests/test_desk_shell.py`. Each guard is a function
over the sheet's text, and the table of broken sheets further down feeds the
whole set every defect it claims to refuse, so a guard that silently stopped
biting reds here rather than in a review.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.test_panel_cascade import E, _COMPOUND, _TOKEN, computed, environments, rules
from tests.test_panel_colour import contrast
from tests.test_panel_contrast import NONTEXT_MIN, TEXT_MIN, _hex_to_rgb

PANEL = Path(__file__).resolve().parents[1] / "src" / "conductor" / "panel"
CSS = (PANEL / "desk.css").read_text(encoding="utf-8")
THEMES = ("dark", "light")
LINE_CAP = 800

#: The concept's colour tokens, verbatim (`mostik.css`, the approved layout-v4).
#: The dark theme is the default; the light pair carries every token again.
CONCEPT_DARK = {
    "--space": "#050908", "--ground": "#0a0f0d", "--panel": "#0e1512",
    "--line": "#24312a", "--line-strong": "#3a4a40", "--ink": "#eef4e8",
    "--muted": "#a3b1a9", "--faint": "#839187", "--ion": "#d4f99b",
    "--on-ion": "#10180b", "--amber": "#efc48b", "--on-amber": "#1b1305",
}
CONCEPT_LIGHT = {
    "--space": "#e7ece5", "--ground": "#eef1ed", "--panel": "#f8faf6",
    "--line": "#c7d1c8", "--line-strong": "#9aab9f", "--ink": "#18241c",
    "--muted": "#4e6055", "--faint": "#607568", "--ion": "#36520f",
    "--on-ion": "#f4f9ea", "--amber": "#8a6500", "--on-amber": "#fff7e2",
}
#: The token pairs the shell will paint text or marks with, each held to the
#: floor its use needs on both grounds. `--faint` is the concept's quiet text
#: and is held to the non-text floor only: on the light ground it does not reach
#: 4.5:1, so no text rule may spend it until it does.
PAIRS = (
    ("--ink", "--ground", TEXT_MIN), ("--ink", "--panel", TEXT_MIN),
    ("--muted", "--ground", TEXT_MIN), ("--muted", "--panel", TEXT_MIN),
    ("--ion", "--ground", TEXT_MIN), ("--ion", "--panel", TEXT_MIN),
    ("--amber", "--ground", TEXT_MIN), ("--amber", "--panel", TEXT_MIN),
    ("--on-ion", "--ion", TEXT_MIN), ("--on-amber", "--amber", TEXT_MIN),
    ("--faint", "--ground", NONTEXT_MIN),
)

# -- the chains the shell builds ---------------------------------------------
BODY = [E("body")]
SHELL = BODY + [E("div", "desk-shell")]
TOP = SHELL + [E("header", "desk-top")]
FOCUSED = ("focus-visible",)

#: selector (exactly as the parser reports it) -> the rows that measure it. A row
#: is (chain, mark property, floor, surface-token override or None); None
#: composites the surface by walking the chain's own backgrounds.
MEASURED = {
    "body": [(BODY, "color", TEXT_MIN, None)],
    ".desk-status": [(TOP + [E("p", "desk-status")], "color", TEXT_MIN, None)],
    ".desk-note": [(TOP + [E("p", "desk-note")], "color", TEXT_MIN, None)],
    ".desk-classic": [(TOP + [E("a", "desk-classic")], "color", TEXT_MIN, None)],
    # The one focus ring, measured on each ground a control in this shell stands on.
    ":focus-visible": [
        (BODY + [E("button", states=FOCUSED)], "outline", NONTEXT_MIN, "--space"),
        (SHELL + [E("button", states=FOCUSED)], "outline", NONTEXT_MIN, "--ground")],
}
# -- the rail: a caption, a sentence, and one button per task ---------------------
RAIL = SHELL + [E("nav", "desk-rail")]
LIST = RAIL + [E("div", "desk-rail__list")]
PRESSED = {"aria-pressed": "true"}
TASK = LIST + [E("button", "desk-task")]
TASK_ON = LIST + [E("button", "desk-task", **PRESSED)]


def _on_both(*tail, prop: str = "color", floor: float = TEXT_MIN) -> list[tuple]:
    """The same row on a resting task and on the pressed one, which stands on a panel."""
    return [(base + list(tail), prop, floor, None) for base in (TASK, TASK_ON)]


MEASURED[".desk-rail__head"] = [(RAIL + [E("h2", "desk-rail__head")], "color", TEXT_MIN, None)]
MEASURED[".desk-rail__none"] = [(RAIL + [E("p", "desk-rail__none")], "color", TEXT_MIN, None)]
MEASURED[".desk-task"] = _on_both()
MEASURED[".desk-task__state"] = _on_both(E("span", "desk-task__state"))
MEASURED[".desk-task__note"] = _on_both(E("span", "desk-task__note"))
for _tone in ("amber", "ion"):
    MEASURED[f'.desk-task__state[data-tone="{_tone}"]'] = _on_both(
        E("span", "desk-task__state", **{"data-tone": _tone}))
# -- the scene: the Studio's run deck, on the concept's grounds -------------------
CENTER = SHELL + [E("main", "desk-center")]
SCENE = CENTER + [E("section", "desk-scene")]
DECK = SCENE + [E("section", "studio-section", "studio-deck")]
HEAD = DECK + [E("div", "studio-deck__head")]
BODY_ROW = DECK + [E("div", "studio-deck__body")]
STAGE = BODY_ROW + [E("div", "studio-deck__scene")]
TRACE = STAGE + [E("section", "studio-trace")]
TRACE_INNER = TRACE + [E("div", "studio-trace__inner")]
FLEET = STAGE + [E("div", "studio-deck__fleet")]
RING = STAGE + [E("div", "studio-deck__fleet", **{"data-kind": "ring"})]
INSPECTOR = BODY_ROW + [E("section", "studio-deck__inspector")]
TRACE_PLANET = TRACE_INNER + [E("button", "studio-planet", "studio-trace__planet")]
TRACE_PLANET_ON = TRACE_INNER + [
    E("button", "studio-planet", "studio-trace__planet", **PRESSED)]
FLEET_PLANET = FLEET + [E("button", "studio-planet")]
FLEET_PLANET_ON = FLEET + [E("button", "studio-planet", **PRESSED)]
ORBS = (STAGE + [E("button", "studio-planet")], TRACE_PLANET, FLEET_PLANET)
ORBS_ON = (STAGE + [E("button", "studio-planet", **PRESSED)], TRACE_PLANET_ON,
           FLEET_PLANET_ON)


def _in(chains, *tail, prop: str = "color", floor: float = TEXT_MIN) -> list[tuple]:
    """The same row on each ground a mark can stand on."""
    return [(list(chain) + list(tail), prop, floor, None) for chain in chains]


MEASURED[".desk-scene__note"] = _in([SCENE], E("p", "desk-scene__note"))
MEASURED[".desk-scene__subject"] = _in([SCENE], E("p", "desk-scene__subject"))
MEASURED[".desk-scene__reload"] = _in([SCENE], E("button", "desk-scene__reload"))
MEASURED[".desk-scene .studio-deck h3"] = _in([DECK], E("h3"))
MEASURED['.desk-scene .studio-lens[aria-pressed="true"]'] = _in(
    [HEAD], E("div", "studio-lenses"), E("button", "studio-lens", **PRESSED),
    prop="border-bottom", floor=NONTEXT_MIN)
MEASURED[".desk-scene .studio-team-roster button"] = _in(
    [HEAD], E("nav", "studio-team-roster"), E("button"))
MEASURED[".desk-scene .studio-trace"] = _in([TRACE])
MEASURED[".desk-scene .studio-trace__inner svg path"] = _in(
    [TRACE_INNER], E("svg"), E("path", "studio-trace__link"), prop="stroke",
    floor=NONTEXT_MIN)
MEASURED['.desk-scene .studio-trace__inner svg [data-open="true"]'] = _in(
    [TRACE_INNER], E("svg"), E("path", "studio-trace__link", **{"data-open": "true"}),
    prop="stroke", floor=NONTEXT_MIN)
MEASURED[".desk-scene .studio-trace__inner svg text"] = _in(
    [TRACE_INNER], E("svg"), E("text"), prop="fill")
MEASURED[".desk-scene .studio-planet__orb"] = (
    _in(ORBS, E("span", "studio-planet__orb"))
    + _in(ORBS, E("span", "studio-planet__orb"), prop="border", floor=NONTEXT_MIN))
MEASURED['.desk-scene .studio-planet[aria-pressed="true"] .studio-planet__orb'] = (
    _in(ORBS_ON, E("span", "studio-planet__orb"))
    + _in(ORBS_ON, E("span", "studio-planet__orb"), prop="border", floor=NONTEXT_MIN))
MEASURED[".desk-scene .studio-planet__selection"] = _in(
    [TRACE_PLANET, FLEET_PLANET], E("span", "studio-planet__selection"))
MEASURED['.desk-scene .studio-planet[aria-pressed="true"] .studio-planet__selection'] = _in(
    [TRACE_PLANET_ON, FLEET_PLANET_ON], E("span", "studio-planet__selection"))
MEASURED['.desk-scene .studio-trace__step[aria-pressed="true"] .studio-trace__point'] = _in(
    [TRACE_INNER], E("button", "studio-trace__step", **PRESSED),
    E("span", "studio-trace__point"), prop="outline", floor=NONTEXT_MIN)
# A symbolic point: the step's word beside it carries the meaning at the text floor.
MEASURED['.desk-scene .studio-trace__step[data-word="needs_decision"] .studio-trace__point'] = _in(
    [TRACE_INNER], E("button", "studio-trace__step", **{"data-word": "needs_decision"}),
    E("span", "studio-trace__point"), floor=NONTEXT_MIN)
MEASURED[".desk-scene .studio-deck__route"] = _in(
    [FLEET], E("svg", "studio-deck__routes"), E("path", "studio-deck__route"),
    prop="stroke", floor=NONTEXT_MIN)
MEASURED[".desk-scene .studio-deck__route-label"] = _in(
    [FLEET], E("svg", "studio-deck__routes"), E("g", "studio-deck__route-label"),
    prop="stroke", floor=NONTEXT_MIN)
MEASURED[".desk-scene .studio-deck__routes marker path"] = _in(
    [FLEET], E("svg", "studio-deck__routes"), E("marker"), E("path"), prop="fill",
    floor=NONTEXT_MIN)
MEASURED[".desk-scene .studio-note"] = (
    _in([INSPECTOR], E("p", "studio-note"))
    + _in([FLEET_PLANET, RING + [E("button", "studio-planet")]], E("span", "studio-note"))
    + _in([FLEET + [E("button", "studio-deck__mark")]], E("span", "studio-note")))
MEASURED[".desk-scene .studio-step-flow__stage svg"] = _in(
    [INSPECTOR], E("section", "studio-step-flow__stage"), E("svg"), prop="stroke",
    floor=NONTEXT_MIN)
# -- the console: the actor line and its form, the queue block and the lines of a view ---
CONSOLE = SHELL + [E("aside", "desk-pult")]
ACTOR_LINE = CONSOLE + [E("p", "desk-pult__actor")]
ACTOR_FORM = CONSOLE + [E("form", "desk-pult__form")]
QUEUE = CONSOLE + [E("section", "desk-queue")]
QUEUE_LIST = QUEUE + [E("ul", "desk-queue__list")]
MEASURED[".desk-pult__head"] = [(CONSOLE + [E("h2", "desk-pult__head")], "color", TEXT_MIN, None)]
MEASURED[".desk-queue__head"] = [(QUEUE + [E("h3", "desk-queue__head")], "color", TEXT_MIN, None)]
MEASURED[".desk-pult__actor"] = [(ACTOR_LINE, "color", TEXT_MIN, None)]
MEASURED[".desk-pult__change"] = [
    (ACTOR_LINE + [E("button", "desk-pult__change")], "color", TEXT_MIN, None)]
MEASURED[".desk-pult__label"] = [
    (ACTOR_FORM + [E("label", "desk-pult__label")], "color", TEXT_MIN, None)]
MEASURED[".desk-pult__hint"] = [
    (ACTOR_FORM + [E("p", "desk-pult__hint")], "color", TEXT_MIN, None)]
MEASURED[".desk-pult__buttons button"] = [
    (ACTOR_FORM + [E("div", "desk-pult__buttons"), E("button")], "color", TEXT_MIN, None)]
MEASURED[".desk-queue__now"] = [(QUEUE + [E("p", "desk-queue__now")], "color", TEXT_MIN, None)]
MEASURED[".desk-queue__entry"] = [
    (QUEUE_LIST + [E("li", "desk-queue__entry")], "color", TEXT_MIN, None)]
MEASURED['.desk-queue__entry[data-tone="amber"]'] = [
    (QUEUE_LIST + [E("li", "desk-queue__entry", **{"data-tone": "amber"})],
     "color", TEXT_MIN, None)]
MEASURED[".desk-queue__none"] = [(QUEUE + [E("p", "desk-queue__none")], "color", TEXT_MIN, None)]
MEASURED[".desk-pult__flag"] = [(QUEUE + [E("p", "desk-pult__flag")], "color", TEXT_MIN, None)]
MEASURED[".desk-shell select"] = [
    (SHELL + [E("select")], prop, floor, None)
    for prop, floor in (("color", TEXT_MIN), ("border", NONTEXT_MIN))]
MEASURED[".desk-shell input"] = [
    (SHELL + [E("input")], prop, floor, None)
    for prop, floor in (("color", TEXT_MIN), ("border", NONTEXT_MIN))]
NEUTRAL = "neutral separator between regions; it identifies no state and carries no word"
EXEMPT = {
    ".desk-top": NEUTRAL, ".desk-rail": NEUTRAL, ".desk-summary": NEUTRAL,
    ".desk-pult": NEUTRAL,
    ".desk-scene .studio-trace__inner svg .studio-trace__horizon":
        "decorative horizon; the step words, glyphs and the measured route strokes carry the plan",
    ".desk-scene .studio-planet__orb::after":
        "decorative outer ring; the orb's own border and its selected state are measured",
    ".desk-scene .studio-step-flow__body":
        "neutral separator between stages; the icons and words identify each stage",
}
#: Which declarations are marks. `background` is not one: a surface is composited
#: under a mark rather than being one.
MARK_PROPS = ("color", "stroke", "fill", "outline", "border", "border-color",
              "border-top", "border-right", "border-bottom", "border-left",
              "border-bottom-color", "border-top-color")
COLOURFUL = re.compile(r"var\(--[\w-]+\)|#[0-9a-fA-F]{3,8}")
#: The closed set of states a rule may key on (spec 5.6.8): the studio's
#: `data-screen` is gone and `data-tone`, `data-state`, `data-view` and `data-lit`
#: come in. The scene's own modules write two more that repaint, `data-word` (what a
#: step or a participant stands at) and `data-open` (a road that is open): each paint
#: they win is a measured row above. `root` and `hidden` say what a thing is, not what
#: somebody did to it; `data-kind` and `data-duty` choose a shape or a dash, never a colour
#: of their own.
MODELLED = {"hover", "focus-visible", "aria-pressed", "aria-selected", "data-theme",
            "data-tone", "data-state", "data-view", "data-lit", "data-word", "data-open"}
INERT = {"root", "hidden", "data-kind", "data-duty"}
CONTROLS = tuple(
    [E("div", "desk-shell"), E(tag)] for tag in ("button", "select", "input", "textarea")
) + ([E("div", "desk-shell"), E("header", "desk-top"), E("a", "desk-classic")],
     # A disclosure's summary is a control the scene's inspector builds, in two places.
     [E("div", "desk-shell"), E("section", "desk-scene"),
      E("details", "studio-inspect-more"), E("summary")],
     [E("div", "desk-shell"), E("section", "desk-scene"),
      E("details", "studio-deck__about"), E("summary")])


def _wrap(css: str) -> str:
    return "<style>" + css + "</style><script></script>"


def root_blocks(sheet: str) -> list[dict[str, str]]:
    """Every ``--name:value`` map, one per ``:root{...}`` block, in order."""
    return [{name: value.strip() for name, value in
             re.findall(r"(--[a-z0-9-]+):([^;}]+)", block)}
            for block in re.findall(r":root\{(.*?)\}", sheet, re.DOTALL)]


def tokens(theme: str, sheet: str) -> dict[str, tuple[int, int, int]]:
    """The sheet's own colours for one theme; the light block overrides the dark."""
    dark, light = root_blocks(sheet)[:2]
    values = dark if theme == "dark" else {**dark, **light}
    return {key: _hex_to_rgb(value) for key, value in values.items() if value.startswith("#")}


def _paint(theme: str, value: str, sheet: str) -> tuple[int, int, int]:
    found = re.search(r"var\((--[\w-]+)\)|#[0-9a-fA-F]{6}", value)
    assert found, f"no colour in {value!r}"
    return tokens(theme, sheet)[found.group(1)] if found.group(1) else _hex_to_rgb(found.group(0))


def _surface(theme: str, chain: list, env: frozenset, sheet: str) -> tuple[int, int, int]:
    for depth in range(len(chain), 0, -1):
        win = computed(list(chain[:depth]), sheet, env)
        value = (win.get("background") or win.get("background-color", "")).strip()
        if value and value not in ("none", "transparent"):
            return _paint(theme, value, sheet)
    raise AssertionError(f"nothing under {chain} paints a surface")


def paint_faults(sheet: str) -> list[str]:
    """Every paint declaration that is neither a measured row nor a named exemption."""
    faults = []
    for rule in rules(sheet):
        marks = [prop for prop in rule.decls if prop in MARK_PROPS
                 and COLOURFUL.search(rule.decls[prop])]
        if marks and rule.selector not in MEASURED and rule.selector not in EXEMPT:
            faults.append(f"unmeasured paint: {rule.selector}")
    return faults


def row_faults(sheet: str) -> list[str]:
    """Rows or exemptions that name a selector the sheet no longer declares."""
    declared = {rule.selector for rule in rules(sheet)}
    named = [*MEASURED, *EXEMPT]
    faults = [f"row names no rule: {selector}" for selector in named
              if selector not in declared]
    return faults + [f"row is both measured and exempt: {s}" for s in MEASURED if s in EXEMPT]


def _rows(sheet: str):
    for theme in THEMES:
        for selector, specs in MEASURED.items():
            for spec in specs:
                for label, env in environments(theme, sheet):
                    yield theme, selector, spec, label, env


def _floor_fault(sheet: str, theme: str, selector: str, spec: tuple, label: str,
                 env: frozenset) -> str | None:
    chain, prop, floor, background = spec
    raw = computed(list(chain), sheet, env).get(prop)
    if not raw:
        return f"{label}: {selector} declares no {prop}"
    under = (tokens(theme, sheet)[background] if background
             else _surface(theme, chain, env, sheet))
    ratio = contrast(_paint(theme, raw, sheet), under)
    if ratio < floor:
        return f"{label}: {selector} is {ratio:.2f}:1, below its floor {floor}"
    return None


def floor_faults(sheet: str) -> list[str]:
    """Every measured row that misses its WCAG floor in some theme or environment."""
    found = (_floor_fault(sheet, *row) for row in _rows(sheet))
    return [fault for fault in found if fault]


def _manual_faults(sheet: str, automatic: list[dict[str, str]]) -> list[str]:
    faults = []
    for theme, expected in zip(THEMES, automatic):
        match = re.search(r':root\[data-theme="' + theme + r'"\]\{(.*?)\}', sheet, re.S)
        if match is None:
            faults.append(f"no manual {theme} theme block")
            continue
        actual = {name: value.strip()
                  for name, value in re.findall(r"(--[a-z0-9-]+):([^;}]+)", match[1])}
        if actual != expected or f"color-scheme:{theme}" not in match[1]:
            faults.append(f"manual {theme} block is not the measured system palette")
    return faults


def palette_faults(sheet: str) -> list[str]:
    """Two `:root` blocks, the concept's tokens verbatim, manual themes equal to them."""
    blocks = root_blocks(sheet)
    if len(blocks) != 2:
        return [f"{len(blocks)} :root blocks, expected exactly 2"]
    faults = []
    for label, block, concept in (("dark", blocks[0], CONCEPT_DARK),
                                  ("light", blocks[1], CONCEPT_LIGHT)):
        faults += [f"{label} {name} is not the concept's {value}"
                   for name, value in concept.items() if block.get(name) != value]
    return faults + _manual_faults(sheet, blocks)


def motion_faults(sheet: str) -> list[str]:
    """Motion only behind the reduced-motion door, and no `@keyframes` at all."""
    faults = [f"motion outside the reduced-motion door: {rule.selector}"
              for rule in rules(sheet)
              if ("transition" in rule.decls or "animation" in rule.decls)
              and "prefers-reduced-motion:no-preference" not in rule.context]
    return faults + (["the sheet declares @keyframes"] if "@keyframes" in sheet else [])


def _state_name(token: str) -> str | None:
    if token.startswith("::"):
        return None
    if token.startswith(":"):
        return token.lstrip(":").split("(")[0]
    return token[1:-1].partition("=")[0].strip() if token.startswith("[") else None


def selector_faults(sheet: str) -> list[str]:
    """Only modelled states, and only selector forms the cascade model can read."""
    faults = []
    for rule in rules(sheet):
        names = {_state_name(token) for token in _TOKEN.findall(rule.selector)} - {None}
        faults += [f"unmodelled state {name}: {rule.selector}"
                   for name in sorted(names - MODELLED - INERT)]
        if re.search(r"[>+~]", rule.selector) or not all(
                _COMPOUND.fullmatch(part) for part in rule.selector.split()):
            faults.append(f"selector form the cascade does not model: {rule.selector}")
    return faults


def target_faults(sheet: str) -> list[str]:
    """The 44px target floor on every control type, and the one focus ring."""
    faults = [f"{chain[-1].tag} is under the 44px target floor" for chain in CONTROLS
              if computed(list(chain), sheet).get("min-height") != "44px"]
    ring = computed([E("button", states=FOCUSED)], sheet)
    if ring.get("outline") != "2px solid var(--ion)" or ring.get("outline-offset") != "3px":
        faults.append(f"the focus ring is not 2px solid --ion at 3px: {ring.get('outline')}")
    return faults


def declared_media(css: str) -> list[tuple[str, int]]:
    """Every `@media` head of the sheet with the depth it stands at, by a scan of its text.

    This is deliberately not the cascade model's own list: that one is built from the
    contexts of the rules it parsed, so a media block with no rule in it, or one the model
    reads only as its innermost condition, would vanish from it and from every guard that
    walks it. The heads are found here by their spelling and their braces.
    """
    text = re.sub(r"/\*.*?\*/", " ", css, flags=re.DOTALL)
    return [("@media " + re.sub(r"[ \t\r\n]+", " ", found.group(1)).strip(),
             text[:found.start()].count("{") - text[:found.start()].count("}"))
            for found in re.finditer(r"@media\b([^{]*)\{", text)]


def media_faults(sheet: str, css: str) -> list[str]:
    """Every `@media` head the floor checks would silently not measure under."""
    walked = {re.sub(r"[ \t\r\n]+", " ", context).strip()
              for theme in THEMES for _label, conditions in environments(theme, sheet)
              for context in conditions}
    faults = []
    for head, depth in declared_media(css):
        if depth:
            faults.append(f"media block nested in another, which the cascade reads only as "
                          f"its innermost condition: {head}")
        if head not in walked:
            faults.append(f"media head no environment walks: {head}")
    return faults


def sheet_faults(css: str) -> list[str]:
    """Every way `css` fails the desk stylesheet's contract, as plain sentences."""
    sheet = _wrap(css)
    faults = (paint_faults(sheet) + row_faults(sheet) + floor_faults(sheet)
              + palette_faults(sheet) + motion_faults(sheet) + selector_faults(sheet)
              + target_faults(sheet) + media_faults(sheet, css))
    lines = len(css.splitlines())
    return faults + ([f"the sheet is {lines} lines, over the {LINE_CAP} cap"]
                     if lines > LINE_CAP else [])


def _swap(old: str, new: str):
    def apply(css: str) -> str:
        assert old in css, f"the sabotage target is gone from the sheet: {old!r}"
        return css.replace(old, new, 1)
    return apply


def _last(old: str, new: str):
    def apply(css: str) -> str:
        head, sep, tail = css.rpartition(old)
        assert sep, f"the sabotage target is gone from the sheet: {old!r}"
        return head + new + tail
    return apply


#: Each defect a guard claims to refuse: the edit that plants it in a copy of the
#: real sheet and a word its fault must contain, so a guard that refuses a sheet
#: for the WRONG reason does not pass for the right one.
BROKEN = {
    "an unmeasured colour": (lambda css: css + ".desk-extra{color:var(--ink)}\n",
                             "unmeasured paint"),
    "a row naming a rule that is gone": (_swap(".desk-note{", ".desk-notes{"),
                                         "row names no rule"),
    "a colour under its floor": (_swap(".desk-status{font-size:12.5px;color:var(--muted)}",
                                       ".desk-status{font-size:12.5px;color:var(--line)}"),
                                 "below its floor"),
    "a third :root block": (lambda css: css + ":root{--extra:#000000}\n", "root blocks"),
    "a token moved off the concept": (_swap("--ion:#d4f99b", "--ion:#d4f99c"), "concept"),
    "a manual theme block that drifted": (_last("--ink:#18241c", "--ink:#18241d"),
                                          "manual light"),
    "a keyframes block": (lambda css: css + "@keyframes spin{from{opacity:0}to{opacity:1}}\n",
                          "@keyframes"),
    "motion outside the reduced-motion door": (
        lambda css: css + ".desk-status{transition:opacity .2s}\n", "reduced-motion"),
    "a 40px control": (_swap("min-height:44px", "min-height:40px"), "44px"),
    "an unmodelled state": (lambda css: css + ".desk-note:focus-within{margin:0}\n",
                            "unmodelled state"),
    "a child combinator": (lambda css: css + ".desk-shell > p{margin:0}\n", "selector form"),
    "a focus ring drawn thin": (_swap("outline:2px solid var(--ion)",
                                      "outline:1px solid var(--ion)"), "focus ring"),
    "a sheet over the line cap": (lambda css: css + "\n" * LINE_CAP, "cap"),
    "a scene note under its floor": (
        _swap(".desk-scene .studio-note{font-size:12px;line-height:1.5;color:var(--muted);",
              ".desk-scene .studio-note{font-size:12px;line-height:1.5;color:var(--line);"),
        "below its floor"),
    "a trace road under its floor": (
        _swap(".desk-scene .studio-trace__inner svg path{fill:none;stroke:var(--faint)",
              ".desk-scene .studio-trace__inner svg path{fill:none;stroke:var(--line)"),
        "below its floor"),
    "an unmeasured scene colour": (
        lambda css: css + ".desk-scene .studio-extra{color:var(--ink)}\n", "unmeasured paint"),
    "a scene rule keyed on an attribute nobody modelled": (
        lambda css: css + '.desk-scene .studio-planet[data-mood="x"]{margin:0}\n',
        "unmodelled state data-mood"),
    "a scene summary under the 44px floor": (
        _swap(".desk-scene .studio-inspect-more summary{min-height:44px;",
              ".desk-scene .studio-inspect-more summary{min-height:40px;"), "summary"),
    "a media block with no rule in it": (
        lambda css: css + "@media (min-width:1200px){}\n", "no environment walks"),
    "a media block nested in another": (
        lambda css: css + "@media (min-width:1200px){@media (min-width:1300px){"
                          ".desk-note{margin:0}}}\n", "nested"),
}


def test_the_real_desk_sheet_meets_its_whole_contract():
    assert sheet_faults(CSS) == []


@pytest.mark.parametrize("edit,needle", list(BROKEN.values()), ids=list(BROKEN))
def test_the_desk_sheet_check_refuses_each_defect_and_names_it(edit, needle):
    faults = sheet_faults(edit(CSS))
    assert faults, "a defective sheet was accepted"
    assert any(needle in fault for fault in faults), faults


@pytest.mark.parametrize("theme", THEMES)
def test_every_concept_token_pair_clears_its_floor_in_both_themes(theme):
    palette = tokens(theme, _wrap(CSS))
    for foreground, ground, floor in PAIRS:
        ratio = contrast(palette[foreground], palette[ground])
        assert ratio >= floor, f"{theme}: {foreground} on {ground} is {ratio:.2f}:1, floor {floor}"


#: The `@media` heads the sheet declares, written out here by hand. A media condition that
#: arrives in the sheet has to be argued for on this line, and the walk below is held to
#: exactly these.
DECLARED_MEDIA = ["@media (max-width:900px)", "@media (prefers-color-scheme:light)"]


def test_the_desk_page_is_measured_in_every_media_environment_the_sheet_declares():
    """Calibration: a floor check that walked no environment would pass on nothing.

    The heads are read out of the sheet's text and are exactly the two written above; the
    cascade walk visits every one of them; and the number of rows the floor test measures
    is the product of the themes, the measured rows and the environments each theme has --
    the theme alone, then the theme with each other condition.
    """
    sheet = _wrap(CSS)
    assert sorted(head for head, _depth in declared_media(CSS)) == DECLARED_MEDIA
    assert {depth for _head, depth in declared_media(CSS)} == {0}
    assert media_faults(sheet, CSS) == []
    labels = [label for label, _env in environments("light", sheet)]
    assert labels == ["light", "light+max-width-900px"]
    specs = sum(len(rows) for rows in MEASURED.values())
    assert sum(1 for _ in _rows(sheet)) == len(THEMES) * specs * len(labels)
