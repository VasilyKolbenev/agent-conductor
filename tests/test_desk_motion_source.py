"""The JavaScript half of the motion guard (spec 5.5, D11): movement is rare, one-shot and optional.

The stylesheet half has stood since the desk's first slice (`tests/test_desk_style.py`: no
`@keyframes`, no `transition` or `animation` outside the reduced-motion door). The transitions are
not drawn by a stylesheet: they are Web Animations played by `desk-motion.js` over a layer that
survives the redraw of the regions. So the spec's three sentences are held here over the panel's
SCRIPTS, as text:

- every `animate` stands behind the reduced-motion check: it is called only inside `play`, after a
  top-level `if (!motionAllowed()) return`, and `motionAllowed` is the negation of the one media
  query, `(prefers-reduced-motion: reduce)`, read at the moment of the call and never kept;
- `setTimeout`, `getComputedStyle` and `matchMedia` are reached only by the modules a registry
  names, each with its reason, and a registry row that no longer spends its name is a fault too.
  The timer of the motion module is one function, `later`, so a second clock cannot hide in the
  module the registry admits;
- no `@keyframes` in any stylesheet, page or script of the panel, no `animation` or `transition`
  set from a script, no animation built by hand round the gate of `animate`, no infinite or
  repeated animation, and no timing that ends after 1.2 s.

What the text cannot say, a browser says (`browser_tests/test_desk_motion.py`): that nothing plays
under the reduced-motion preference and that the timings reach the page as written. Nothing in
this file reads a CSS property whose name a script builds at run time (`style[name]`, a computed
key): the check reads the spellings that stand in the source.

Every check below is a function over text, and the table at the end feeds each one the defect it
claims to refuse, so a check that stopped biting reds here and not in a review.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from tests.desk_node import run_js
from tests.studio_partition import PREFIXES
from tests.test_graph_source import _code

PANEL = Path(__file__).resolve().parents[1] / "src" / "conductor" / "panel"
MOTION = "desk-motion.js"
MODEL = "desk-motion-model.js"
#: The longest any one movement may last, delay included (spec 5.5: «не больше 1,2 с»).
FX_MAX_MS = 1200
#: The only query the reduced-motion check may read.
REDUCE = "(prefers-reduced-motion: reduce)"

#: Who may arm a timer, and why. A module that is not here may not name `setTimeout`.
TIMERS = {
    MOTION: "how long a plaque stays on the glass, armed in `later` and nowhere else",
    "desk-transport.js": "the deadline of a read",
    "desk-people-host.js": "the minute between two refreshes of the limits",
    "hub.js": "the hub page's reconnect, its operation follower and its clock",
    "studio.js": "the old shell's refresh of the limits (retired with the shell)",
}
#: Who may read the computed style of an element. Nobody does: the motion module colours its layer
#: with the page's own tokens (`var(--ion)`), so no value has to be read back out of the cascade.
STYLE_READS: dict[str, str] = {}
#: Who may ask the platform for a media query.
MEDIA = {
    MOTION: "the reduced-motion preference, read at each play",
    "studio.js": "the old shell's colour scheme (retired with the shell)",
}
#: Who may call `animate`: the one module that plays transitions.
ANIMATORS = {MOTION: "the one module that plays a transition, in the one function `play`"}
#: The name the one function that animates is called, and the one that gates it.
PLAY, GATE, HOME = "play", "motionAllowed", "later"
#: The single function each registry module may arm its timer in, where the registry is narrower
#: than the module.
TIMER_HOME = {MOTION: HOME}

FAMILIES = {
    "setTimeout": (r"\bsetTimeout\b", TIMERS),
    "getComputedStyle": (r"\bgetComputedStyle\b", STYLE_READS),
    "matchMedia": (r"\bmatchMedia\b", MEDIA),
    "animate": (r"\banimate\b", ANIMATORS),
}
FUNCTION = re.compile(r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\(")
CHECK = re.compile(r"\bif\s*\(\s*!\s*" + GATE + r"\s*\(\s*\)\s*\)\s*return\b")
NEGATED_QUERY = re.compile(
    r"\breturn\s*!\s*(?:window\s*\.\s*)?matchMedia\s*\(\s*REDUCE\s*\)\s*\.\s*matches\b")
#: A CSS motion property by any spelling a script can give it: `transition`, `transitionDuration`,
#: `transition-delay`, `animationName`, `webkitTransition`, `-webkit-animation`. What follows the
#: word is a camelCase or a hyphenated part, so `transition_id` and `transitions` are not it.
MOTION_PROPERTY = (r"(?:(?:-(?:webkit|moz|ms|o)-)?(?:transition|animation)"
                   r"|(?:webkit|Webkit|moz|Moz|ms|O)(?:Transition|Animation))"
                   r"(?:[A-Z]\w*|-[a-z][\w-]*)?")
QUOTE = "[\"'`]"
#: The ways to hand a node a CSS transition or animation without `animate`, read over the code with
#: its strings in, because a style written as text is a string: `node.style.transition = ..`, a
#: write through an alias of the style, a bracket on the style, `setProperty`, and the property as
#: a key, in an object (`{transition: ..}`, `{"animation-name": ..}`) or in a text of CSS
#: (`cssText`, `setAttribute("style", ..)`, `insertRule`).
SCRIPT_MOTION = re.compile("|".join((
    r"\.style\s*\??\.\s*" + MOTION_PROPERTY,
    r"\.\s*" + MOTION_PROPERTY + r"\s*(?:\+|\|\||&&|\?\?)?=(?!=)",
    r"\[\s*" + QUOTE + MOTION_PROPERTY + QUOTE + r"\s*\]",
    r"\bsetProperty\s*\(\s*" + QUOTE + MOTION_PROPERTY,
    r"(?<![\w$.-])" + QUOTE + "?" + MOTION_PROPERTY + QUOTE + r"?\s*:",
)))
#: The property as a shorthand key, `{transition}`. A sentence ("motion, transition, and sound")
#: reads the same in a string, so it counts only when it stands outside every literal.
SHORTHAND_KEY = re.compile(r"[{,]\s*(?:transition|animation)\s*(?=[,}])")
LOOPING = re.compile(r"\bInfinity\b|\biterations\b|\bdirection\s*:")
#: The other ways to start a Web Animation than `animate`: an animation built by hand. `animate`
#: is the one door, so a second would be a way round its gate.
BY_HAND = re.compile(r"\bKeyframeEffect\b|\bnew\s+Animation\b|\bgetAnimations\b")
SHEETS = ("*.css", "*.html", "*.js")


def sources() -> dict[str, str]:
    """The text of every script of the panel's pages, comments out, by file name."""
    return {path.name: _code(path) for path in sorted(PANEL.glob("*.js"))
            if path.name.startswith(PREFIXES)}


def _matching(text: str, at: int, opener: str, closer: str) -> int:
    """The index of the bracket that closes the one at `at` (literals are already blanked)."""
    depth = 0
    for index in range(at, len(text)):
        depth += (text[index] == opener) - (text[index] == closer)
        if depth == 0:
            return index
    raise ValueError(f"unbalanced {opener} at {at}")


def blank(code: str) -> str:
    """The code with the inside of every string literal replaced by spaces, length kept.

    Braces and parentheses inside a sentence must not be counted, and the index of a word must
    be the same in the code and in its blanked copy. A template literal keeps its `${...}`.
    """
    out, at, end = [], 0, len(code)
    while at < end:
        char = code[at]
        if char in "\"'`":
            at = _blank_literal(code, at, out)
        else:
            out.append(char)
            at += 1
    return "".join(out)


def _blank_literal(code: str, at: int, out: list[str]) -> int:
    """Append the literal that opens at `at` blanked; the index just past it."""
    quote, end = code[at], len(code)
    out.append(quote)
    at += 1
    while at < end and code[at] != quote:
        if code[at] == "\\":
            out.append("  ")
            at += 2
        elif quote == "`" and code.startswith("${", at):
            shut = _matching(code, at + 1, "{", "}")
            out.append("  " + blank(code[at + 2:shut]) + " ")
            at = shut + 1
        else:
            out.append("\n" if code[at] == "\n" else " ")
            at += 1
    out.append(quote)
    return at + 1


def functions(text: str) -> list[tuple[str, int, int]]:
    """Every declared function as (name, index of its opening brace, index of its closing one)."""
    found = []
    for match in FUNCTION.finditer(text):
        shut = _matching(text, match.end() - 1, "(", ")")
        brace = text.index("{", shut)
        found.append((match.group(1), brace, _matching(text, brace, "{", "}")))
    return found


def home_of(text: str, at: int) -> tuple[str, int, int] | None:
    """The innermost declared function whose body holds the index `at`, if any."""
    inside = [one for one in functions(text) if one[1] < at < one[2]]
    return min(inside, key=lambda one: one[2] - one[1]) if inside else None


def animate_faults(code: str) -> list[str]:
    """Every `animate` that is not played by `play` behind a top-level reduced-motion check."""
    text = blank(code)
    faults = []
    for hit in re.finditer(FAMILIES["animate"][0], code):
        home = home_of(text, hit.start())
        if home is None:
            faults.append("animate outside every function")
            continue
        name, brace, _end = home
        if name != PLAY:
            faults.append(f"animate in {name}, which is not {PLAY}")
            continue
        checks = [one for one in CHECK.finditer(text, brace, hit.start())
                  if text.count("{", brace, one.start()) == text.count("}", brace, one.start()) + 1]
        if not checks:
            faults.append(f"animate in {PLAY} stands behind no top-level {GATE} check")
    return faults


def gate_faults(code: str) -> list[str]:
    """The check must be the negation of the one reduce query, asked afresh at each call."""
    text = blank(code)
    gate = [one for one in functions(text) if one[0] == GATE]
    if len(gate) != 1:
        return [f"{len(gate)} functions called {GATE}, expected one"]
    _name, brace, end = gate[0]
    faults = []
    if not NEGATED_QUERY.search(text[brace:end]):
        faults.append(f"{GATE} is not `return !matchMedia(REDUCE).matches`")
    declared = re.findall(r"\bconst\s+REDUCE\s*=\s*\"([^\"]*)\"\s*;", code)
    if declared != [REDUCE]:
        faults.append(f"REDUCE is not the one query {REDUCE!r}: {declared}")
    return faults


def use_faults(files: dict[str, str]) -> list[str]:
    """Every name used outside its registry, and every registry row that spends nothing."""
    faults = []
    for family, (pattern, registry) in FAMILIES.items():
        users = {name for name, code in files.items() if re.search(pattern, code)}
        faults += [f"{family} used by {name}, which no registry row admits"
                   for name in sorted(users - set(registry))]
        faults += [f"{family} registry row {name} is not spent"
                   for name in sorted(set(registry) - users)]
    return faults


def timer_faults(files: dict[str, str]) -> list[str]:
    """In a module whose registry row names a home function, the timer is armed there alone."""
    faults = []
    for name, home in TIMER_HOME.items():
        code = files.get(name, "")
        text = blank(code)
        for hit in re.finditer(FAMILIES["setTimeout"][0], code):
            found = home_of(text, hit.start())
            if found is None or found[0] != home:
                faults.append(f"{name} arms a timer outside {home}")
    return faults


def sets_motion(code: str) -> bool:
    """Whether a script hands a node a CSS transition or animation, by any spelling of it."""
    if SCRIPT_MOTION.search(code):
        return True
    return bool(SHORTHAND_KEY.search(code) and SHORTHAND_KEY.search(blank(code)))


def motion_faults(files: dict[str, str]) -> list[str]:
    """The sentences of the spec as faults, over a set of scripts."""
    faults = use_faults(files) + timer_faults(files)
    if MOTION in files:
        faults += animate_faults(files[MOTION]) + gate_faults(files[MOTION])
    for name, code in files.items():
        if sets_motion(code):
            faults.append(f"{name} sets an animation or a transition from a script")
        if BY_HAND.search(code):
            faults.append(f"{name} builds an animation by hand, round the gate of `animate`")
        if "@keyframes" in code.lower():
            faults.append(f"{name} writes @keyframes")
        if name in (MOTION, MODEL) and LOOPING.search(code):
            faults.append(f"{name} repeats or loops a movement")
    return faults


def timing_faults(table: dict[str, dict[str, int]], cap: int) -> list[str]:
    """Every movement of the table that ends after `cap` ms, delay included, or is not finite."""
    faults = []
    for name, one in table.items():
        duration, delay = one.get("duration"), one.get("delay")
        if not all(isinstance(value, int) and value >= 0 for value in (duration, delay)):
            faults.append(f"timing {name} is not a pair of whole milliseconds")
        elif duration == 0 or duration + delay > cap:
            faults.append(f"timing {name} ends at {duration + delay} ms, over {cap} ms"
                          if duration else f"timing {name} lasts no time")
    return faults


def table_faults(names: set[str], code: str) -> list[str]:
    """The movements of the table against the movements the module names (`TIMINGS.<name>`).

    A row nothing plays spends nothing, like a registry row that is not spent; a movement the
    module plays that the table lacks has no cap held on it.
    """
    played = set(re.findall(r"\bTIMINGS\.(\w+)", code))
    return ([f"movement {name} is in the table and nothing plays it"
             for name in sorted(names - played)]
            + [f"movement {name} is played and the table holds no timing for it"
               for name in sorted(played - names)])


def test_the_motion_module_is_there_and_plays_everything_through_one_gated_function():
    files = sources()
    assert MOTION in files and MODEL in files, "the transitions module is not packaged"
    assert len(re.findall(FAMILIES["animate"][0], files[MOTION])) == 1, (
        "the module animates in more or fewer places than the one function")
    assert len(re.findall(r"(?<!function )(?<![\w.])play\(", files[MOTION])) >= 6, (
        "the scan found too few movements to be reading the module")
    assert animate_faults(files[MOTION]) == []
    assert gate_faults(files[MOTION]) == []


def test_every_use_of_a_timer_a_style_read_or_a_media_query_is_one_a_registry_row_admits():
    files = sources()
    assert len(files) > 100, "the scan found too few scripts to be reading the panel"
    assert use_faults(files) == []
    assert timer_faults(files) == []


def test_the_whole_panel_passes_the_motion_guard():
    assert motion_faults(sources()) == []


def test_no_stylesheet_page_or_script_writes_keyframes():
    found = [path.name for pattern in SHEETS for path in PANEL.glob(pattern)
             if path.name.startswith(PREFIXES)
             and "@keyframes" in path.read_text(encoding="utf-8").lower()]
    assert found == []


def test_every_movement_of_the_table_is_finite_and_ends_inside_the_cap():
    if shutil.which("node") is None:
        pytest.fail("Node is required to read the timing table of the motion model")
    shown = run_js("console.log(JSON.stringify({cap: m.FX_MAX_MS, table: m.TIMINGS}));",
                   {"m": MODEL})
    assert shown["cap"] == FX_MAX_MS
    assert len(shown["table"]) >= 8
    assert timing_faults(shown["table"], FX_MAX_MS) == []


def test_each_registry_row_names_a_packaged_module_and_a_reason():
    packaged = {path.name for path in PANEL.glob("*.js")}
    for registry in (TIMERS, STYLE_READS, MEDIA, ANIMATORS):
        assert set(registry) <= packaged
        assert all(reason.strip() for reason in registry.values())
    assert not STYLE_READS, "nobody reads a computed style; a row needs an argument first"


# -- the table: each defect the checks claim to refuse, and a word its fault must carry ---------

GOOD = f"""
const REDUCE = "{REDUCE}";
function motionAllowed() {{ return !window.matchMedia(REDUCE).matches; }}
function play(node, frames) {{
  if (!motionAllowed()) return Promise.resolve(false);
  return node.animate(frames, {{duration: 400}}).finished;
}}
function later(call, ms) {{ return setTimeout(call, ms); }}
"""


REAL = sources()


def _on(source: str) -> dict[str, str]:
    """The real panel's scripts with the motion module replaced by `source`."""
    return {**REAL, MOTION: source}


def _beside(name: str, source: str) -> dict[str, str]:
    """The real panel's scripts with one module's text replaced."""
    return {**REAL, name: source}


#: Each way a script can hand a node a CSS transition or animation without `animate`, as the one
#: line of script that does it. The check is a family of shapes, and every shape has its row.
SCRIPT_MOTION_LINES = {
    "a transition set by Object.assign on a style":
        'Object.assign(n.style, {transition: "opacity 1s"});',
    "a transition longhand as an object key":
        'Object.assign(n.style, {transitionDuration: "1s"});',
    "a quoted transition key": 'Object.assign(n.style, {"transition-delay": "1s"});',
    "a vendor-prefixed transition as an object key":
        'Object.assign(n.style, {WebkitTransition: "a"});',
    "a vendor-prefixed transition on the style": 'n.style.webkitTransition = "a";',
    "a transition as a shorthand key":
        'const transition = "a"; Object.assign(n.style, {transition});',
    "an animation set by Object.assign on a style":
        'Object.assign(n.style, {animationName: "spin"});',
    "a transition in cssText": 'n.style.cssText = "opacity: 0; transition: opacity 1s";',
    "an animation in cssText": 'n.style.cssText = "animation: spin 1s";',
    "a transition through setAttribute on the style": 'n.setAttribute("style", "transition: a");',
    "a transition in a rule inserted into a sheet":
        'sheet.insertRule(".a { transition: all 1s }");',
    "a transition through a bracket on the style": 'n.style["transition"] = "a";',
    "an animation through a bracket on the style": 'n.style["animation-name"] = "spin";',
    "a transition through setProperty": 'n.style.setProperty("transition", "a");',
    "a transition written through an alias of the style": 'const s = n.style; s.transition = "a";',
    "a transition added through an alias of the style":
        'const s = n.style; s.transition += ", opacity 1s";',
    "a transition property read off a style": "copy.style.cssText = n.style.transition;",
}

DEFECTS = {
    "an animate with no check": (
        _on(GOOD.replace("  if (!motionAllowed()) return Promise.resolve(false);\n", "")),
        "stands behind no"),
    "a check after the animate": (
        _on(GOOD.replace(
            "  if (!motionAllowed()) return Promise.resolve(false);\n  return node.animate("
            "frames, {duration: 400}).finished;",
            "  const run = node.animate(frames, {duration: 400}).finished;\n"
            "  if (!motionAllowed()) return Promise.resolve(false);\n  return run;")),
        "stands behind no"),
    "a check that only guards a branch": (
        _on(GOOD.replace(
            "  if (!motionAllowed()) return Promise.resolve(false);\n  return node.animate(",
            "  if (frames) { if (!motionAllowed()) return Promise.resolve(false); }\n"
            "  return node.animate(")),
        "stands behind no"),
    "an animate in another function of the module": (
        _on(GOOD + "function spin(node) { return node.animate([], {duration: 1}); }\n"),
        "not play"),
    "an animate at the top of the module": (
        _on(GOOD + "document.body.animate([], {duration: 1});\n"), "outside every function"),
    "an animate in another module": (
        _beside("desk-rail.js", REAL["desk-rail.js"] + "\nrow.animate([], {});\n"),
        "no registry row admits"),
    "an animate spelled with a bracket": (
        _on(GOOD + "function spin(n) { return n['animate']([], {}); }\n"), "animate"),
    "a gate that is not the negation": (
        _on(GOOD.replace("return !window", "return window")), "not `return !matchMedia"),
    "a gate on another query": (
        _on(GOOD.replace(REDUCE, "(prefers-reduced-motion: no-preference)")), "REDUCE is not"),
    "a gate that keeps its answer": (
        _on(GOOD.replace("return !window.matchMedia(REDUCE).matches;", "return QUIET;")),
        "not `return !matchMedia"),
    "a second timer in the module": (
        _on(GOOD + "function again(call) { return setTimeout(call, 5); }\n"), "outside later"),
    "a timer in another module": (
        _beside("desk-rail.js", REAL["desk-rail.js"] + "\nsetTimeout(f, 1);\n"),
        "setTimeout used by desk-rail.js"),
    "a timer spelled through the window": (
        _beside("desk-feed.js", REAL["desk-feed.js"] + "\nwindow.setTimeout(f, 1);\n"),
        "setTimeout used by desk-feed.js"),
    "a computed style read": (
        _on(GOOD + "const tone = getComputedStyle(document.body);\n"), "getComputedStyle"),
    "a media query in another module": (
        _beside("desk-pult.js", REAL["desk-pult.js"] + "\nwindow.matchMedia('(a)');\n"),
        "matchMedia used by desk-pult.js"),
    "a registry row nobody spends": (
        {name: code for name, code in REAL.items() if name != "hub.js"}, "not spent"),
    "keyframes in a script": (
        _on(GOOD + "const sheet = '@keyframes spin {}';\n"), "@keyframes"),
    "an animation set from a script": (
        _on(GOOD + "function paint(n) { n.style.animation = 'spin 1s'; }\n"),
        "animation or a transition"),
    "a transition set from a script": (
        _beside("desk-feed.js", REAL["desk-feed.js"] + "\nrow.style.transition = 'a';\n"),
        "animation or a transition"),
    **{name: (_on(GOOD + f"function paint(n) {{ {line} }}\n"), "animation or a transition")
       for name, line in SCRIPT_MOTION_LINES.items()},
    "a movement that never ends": (
        _on(GOOD.replace("{duration: 400}", "{duration: 400, iterations: Infinity}")),
        "repeats or loops"),
    "an animation built by hand in the motion module": (
        _on(GOOD + "const run = new Animation(new KeyframeEffect(document.body, [], 1));\n"),
        "by hand"),
    "a keyframe effect in another module": (
        _beside("desk-rail.js", REAL["desk-rail.js"] + "\nnew KeyframeEffect(row, [], 1);\n"),
        "by hand"),
}


@pytest.mark.parametrize("files,word", list(DEFECTS.values()), ids=list(DEFECTS))
def test_the_guard_refuses_each_defect_and_names_it(files, word):
    faults = motion_faults(files)
    assert faults, "a defective panel was accepted"
    assert any(word in fault for fault in faults), faults


def test_the_guard_accepts_the_shape_it_asks_for():
    assert animate_faults(GOOD) == [] and gate_faults(GOOD) == []
    assert timer_faults(_on(GOOD)) == []


TIMINGS_DEFECTS = {
    "a movement over the cap": ({"a": {"duration": 1100, "delay": 200}}, "ends at 1300"),
    "a movement that lasts no time": ({"a": {"duration": 0, "delay": 0}}, "lasts no time"),
    "a movement without a delay": ({"a": {"duration": 400}}, "whole milliseconds"),
    "a movement of a fraction": ({"a": {"duration": 400.5, "delay": 0}}, "whole milliseconds"),
}


@pytest.mark.parametrize("table,word", list(TIMINGS_DEFECTS.values()), ids=list(TIMINGS_DEFECTS))
def test_the_timing_check_refuses_each_defect_and_names_it(table, word):
    faults = timing_faults(table, FX_MAX_MS)
    assert any(word in fault for fault in faults), faults


def test_the_timing_check_accepts_a_movement_that_ends_exactly_at_the_cap():
    assert timing_faults({"a": {"duration": 1000, "delay": 200}}, FX_MAX_MS) == []


# -- the same defects planted in the REAL module, so a clean answer is not an empty one ----------

CHECK_LINE = "  if (!motionAllowed()) return Promise.resolve(false);\n"
TIMER_FUNCTION = "function later(call, ms) {\n  return setTimeout(call, ms);\n}\n"
GATE_LINE = "return !window.matchMedia(REDUCE)"
MUTATIONS = {
    "its reduced-motion check taken out": (
        lambda text: text.replace(CHECK_LINE, ""), "stands behind no"),
    "a second function that animates": (
        lambda text: text + "\nfunction spin(n) { return n.animate([], {duration: 1}); }\n",
        "not play"),
    "its gate turned round": (
        lambda text: text.replace(GATE_LINE, "return window.matchMedia(REDUCE)"),
        "not `return !matchMedia"),
    "a second timer": (
        lambda text: text + "\nfunction hurry(call) { return setTimeout(call, 1); }\n",
        "outside later"),
    "its timer armed outside later": (
        lambda text: text.replace(TIMER_FUNCTION, "function later(call) {\n  return call;\n}\n")
        + "\nsetTimeout(() => 0, 1);\n", "outside later"),
    "a movement made to repeat": (
        lambda text: text.replace('fill: "forwards"', 'fill: "forwards", iterations: Infinity'),
        "repeats or loops"),
    "a computed style read": (
        lambda text: text + "\nconst here = getComputedStyle(document.body);\n",
        "getComputedStyle"),
    "its layer styled with a transition": (
        lambda text: text.replace('{position: "fixed", inset: "0",',
                                  '{transition: "opacity 1s", position: "fixed", inset: "0",'),
        "animation or a transition"),
    "a mark given a transition in cssText": (
        lambda text: text + '\nfunction ease(n) { n.style.cssText = "transition: opacity 1s"; }\n',
        "animation or a transition"),
}


@pytest.mark.parametrize("plant,word", list(MUTATIONS.values()), ids=list(MUTATIONS))
def test_the_guard_refuses_the_real_motion_module_with_each_defect_planted_in_it(plant, word):
    real = REAL[MOTION]
    planted = plant(real)
    assert planted != real, "the defect did not land in the module: its text moved"
    faults = motion_faults(_on(planted))
    assert any(word in fault for fault in faults), faults
    assert motion_faults(_on(real)) == []


#: Lines that share a word with a CSS motion property and set none: another trade's `transition`
#: (a workflow step's id, a section), the frame loop, an event name, a label, a local variable.
OTHER_USES = (
    "step.transition_id = next;",
    "const record = {transition_id: next, transitions: []};",
    'import {transitionSection} from "./studio-transitions.js";',
    "const frame = requestAnimationFrame(tick);",
    "cancelAnimationFrame(frame);",
    'node.addEventListener("transitionend", done);',
    "const animation = frames.length;",
    'const label = ["Transitions", "Переходы"];',
    'const note = "Turns off motion, transition, animation, and sound.";',
    "if (event.animationName === name) done();",
)


def test_the_motion_guard_passes_lines_that_only_share_a_word_with_a_motion_property():
    refused = [line for line in OTHER_USES if motion_faults(_on(GOOD + line + "\n"))]
    assert refused == []


def test_the_table_holds_exactly_the_movements_the_module_plays():
    if shutil.which("node") is None:
        pytest.fail("Node is required to read the timing table of the motion model")
    shown = run_js("console.log(JSON.stringify(Object.keys(m.TIMINGS)));", {"m": MODEL})
    assert table_faults(set(shown), sources()[MOTION]) == []


TABLE_DEFECTS = {
    "a movement nothing plays": ({"a", "b"}, "play(x, f, TIMINGS.a);", "nothing plays it"),
    "a movement the table lacks": ({"a"}, "play(x, f, TIMINGS.a); play(y, f, TIMINGS.z);",
                                   "holds no timing"),
}


@pytest.mark.parametrize("names,code,word", list(TABLE_DEFECTS.values()), ids=list(TABLE_DEFECTS))
def test_the_table_check_refuses_each_defect_and_names_it(names, code, word):
    assert any(word in fault for fault in table_faults(names, code))


def test_the_real_timing_table_with_one_movement_made_longer_is_refused():
    if shutil.which("node") is None:
        pytest.fail("Node is required to read the timing table of the motion model")
    shown = run_js("console.log(JSON.stringify(m.TIMINGS));", {"m": MODEL})
    shown["comet"] = {**shown["comet"], "duration": shown["comet"]["duration"] + 600}
    assert any("ends at" in fault for fault in timing_faults(shown, FX_MAX_MS))
