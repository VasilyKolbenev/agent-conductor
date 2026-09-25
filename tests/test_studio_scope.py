"""Every name a Studio module CALLS is one it declares or one it imports.

This module exists because of a defect, and the defect is worth stating: when
the inspector was split in two, three helpers moved to the new file and
`edgePanel` stayed behind still calling them. `unsupported`, `call` and
`editable` were no longer in its scope. Nothing in the fast suite noticed.

Nothing COULD, with the guards that existed. Every other source guard here asks
whether a file contains or does not contain some text; none of them resolves a
name. `node --input-type=module` does not help either -- it evaluates a module's
top level, so it proves the imports resolve and the constants build, and says
nothing about a function body that is never called during evaluation. The break
surfaced in Chromium, one gate and eight minutes later, as three timeouts on an
inspector panel that silently threw.

So the class is: a name that was in scope before a move and is not after it. It
will recur, because the panel is still being re-layered and every split moves
functions away from the helpers they call. This closes it at the cheapest place
-- source text, in the fast suite, before a browser is ever started.

WHAT THIS IS NOT. It is not a type checker and not a linter, and it does not
model block scope: it asks whether a called name EXISTS in the file -- as a
declaration at any depth, a parameter, or an import -- because the class being
closed is a name that left the file entirely. Forgiving a name declared in one
function and called in another is the price of not writing a second JavaScript
implementation inside a test suite, and it is cheap: that shape is a runtime
error the browser gate still catches, while the shape this closes was invisible
to everything until Chromium ran it.

The roster of globals it forgives is written out rather than inferred, so a
module reaching for a NEW one has to come here and say why.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.test_graph_source import _code
from tests.test_studio_source import MODULES, PANEL
from tests.test_studio_wiring import _expressions

#: What the platform provides. Written out rather than taken from a library:
#: a roster this file does not state is a global this suite has not agreed to.
GLOBALS = frozenset({
    # value constructors and namespaces
    "Array", "Boolean", "Date", "Error", "JSON", "Map", "Math", "Number",
    "Object", "Promise", "RegExp", "Set", "String", "Symbol", "WeakMap",
    # the DOM the panel is allowed to touch
    "document", "window", "EventSource", "URL", "URLSearchParams",
    # the two the attempt-id digest needs: bytes of a name, and 64-bit
    # arithmetic that does not lose its top bits
    "TextEncoder", "BigInt",
    # standard functions
    "isNaN", "parseFloat", "parseInt", "structuredClone", "fetch",
    "encodeURIComponent", "decodeURIComponent",
    # the read door's deadline (studio.js `readJson`): one timer per GET, the
    # abort it fires, and clearing that timer once the read settles. Admitted
    # for the boot module alone -- `DEADLINE` below holds every other module out
    "AbortController", "setTimeout", "clearTimeout",
    # words a call-shaped regex sees that are not calls at all
    "if", "for", "while", "switch", "catch", "return", "typeof", "function",
    "await", "new", "else", "do", "of", "in", "case", "throw",
})
# Native layout observation is needed by the two modules that draw against a
# measured box: the orbit, and the participants strip that now sizes itself the
# same way. Keep this narrower than GLOBALS: a name admitted here is admitted
# for the module that argued for it and for no other, so a third module
# reaching for an observer has to come here and be written down. It is a name
# per module, never a wildcard and never a module-wide forgiveness -- a typo
# or any other foreign global is still reported in these modules too.
# Browser witnesses exercise construction, redraw, resizing and teardown.
MODULE_GLOBALS = {
    "studio-trace.js": frozenset({"ResizeObserver"}),
    "studio-orbit.js": frozenset({"ResizeObserver"}),
    "studio-participants.js": frozenset({"ResizeObserver"}),
}
#: A call is `name(`, with the name not preceded by a dot -- `a.map(` is a
#: method on a value and says nothing about this module's scope.
_CALL = re.compile(r"(?<![.\w$])([A-Za-z_$][\w$]*)\s*\(")
#: Every way this codebase introduces a name, at ANY indentation. Block scope is
#: deliberately not modelled: the question here is whether a name exists in the
#: file at all, because the class being closed is a name that moved OUT of it.
#: Forgiving a name declared in one function and called in another is the price,
#: and it is worth paying -- the alternative is a scope resolver, which is a
#: second JavaScript implementation living in the test suite.
_DECLARED = (
    re.compile(r"(?:export\s+)?function\s+([A-Za-z_$][\w$]*)"),
    re.compile(r"(?:export\s+)?class\s+([A-Za-z_$][\w$]*)"),
    re.compile(r"(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)"),
)
#: Names a body is handed rather than declares: destructurings, the parameter
#: lists of both function spellings, and the bare parameter of a short arrow.
#: `replaceNode(draft, nodeId, make)` calls `make`, and a resolver that did not
#: count parameters would report every callback this codebase passes.
_BOUND = (
    re.compile(r"(?:const|let|var)\s*\{([^}]*)\}\s*="),
    re.compile(r"function\s*[A-Za-z_$][\w$]*\s*\(([^)]*)\)"),
    re.compile(r"\(([^()]*)\)\s*=>"),
    re.compile(r"(?<![.\w$])([A-Za-z_$][\w$]*)\s*=>"),
)
_METHOD_DECLARATION = re.compile(
    r"(?m)^[ \t]*(?:async[ \t]+)?([A-Za-z_$][\w$]*)[ \t]*\([^;{}\n]*\)[ \t]*\{")
_IMPORTED = re.compile(r"import\s*\{([^}]*)\}\s*from", re.S)


def _names_in_scope(source: str) -> set[str]:
    """Top-level declarations plus everything the module imported by name."""
    found: set[str] = set()
    for pattern in _DECLARED:
        found.update(pattern.findall(source))
    for pattern in _BOUND:
        for clause in pattern.findall(source):
            for part in clause.split(","):
                name = part.split(":")[-1].split("=")[0].strip().lstrip(".")
                if re.fullmatch(r"[A-Za-z_$][\w$]*", name):
                    found.add(name)
    for clause in _IMPORTED.findall(source):
        for part in clause.split(","):
            name = part.split(" as ")[-1].strip()
            if name:
                found.add(name)
    return found


#: A regular-expression literal, in the only positions this codebase writes one:
#: after `=`, `(`, `,`, `[`, `:` or `return`. Blanked before names are read,
#: because `/(\d{2})T(\d{2})/` contains `T(` and nothing else in this module can
#: tell that from a call.
_REGEX_LITERAL = re.compile(
    r"(?<=[=(,\[:])\s*/(?![/*])(?:\\.|\[[^\]]*\]|[^/\n\\])+/[gimsuy]*")


def _scannable(source: str) -> str:
    r"""This code with literals blanked, ready for names to be read out of it.

    `_expressions` next door does the blanking, and it is reused rather than
    rewritten -- its quote, escape and template scanning is the hard part and
    there must not be two of them. It is reused with one correction: it keeps
    the `${...}` of a template and DROPS the prose between two of them, so
    `` `loop ${at} reopens ${show(x)}` `` comes back as `atshow(x)` -- a name
    that never existed, reported as missing. Separating every brace before the
    blanking runs is enough, because a space can only ever split a name and
    never join two, and any space that lands inside a literal is blanked with
    the literal around it.

    Regular-expression literals go too: `/(\d{2})T(\d{2})/` contains `T(`.
    """
    spaced = source.replace("${", "${ ").replace("}", "} ")
    return _REGEX_LITERAL.sub(" ", _expressions(spaced))


def _called(source: str) -> set[str]:
    """Every bare name this module calls, method calls excluded."""
    declarations = {match.start(1) for match in _METHOD_DECLARATION.finditer(source)}
    return {match.group(1) for match in _CALL.finditer(source)
            if match.start(1) not in declarations}


def _unreachable(source: str, module: str) -> list[str]:
    source = _scannable(source)
    return sorted(_called(source) - _names_in_scope(source) - GLOBALS
                  - MODULE_GLOBALS.get(module, frozenset()))


@pytest.mark.parametrize("name", MODULES)
def test_every_name_a_module_calls_is_one_it_can_reach(name):
    """The guard the inspector split needed and did not have."""
    unreachable = _unreachable(_code(PANEL / name), name)

    assert not unreachable, (
        f"{name} calls {unreachable}, which it neither declares nor imports; "
        "a move left them behind")


def test_resize_observer_is_admitted_module_by_module_and_forgives_no_unknown_name():
    """The admission is per module in BOTH directions, and it forgives one name.

    One identical source, read as each module in turn: the two that argued for
    an observer reach it, every other module does not, and in the admitted
    modules a typo of the same name and an absent helper are both still
    reported. The table itself is held to one name per module, so the next
    entry cannot quietly be a wildcard or a module-wide forgiveness.
    """
    source = "function watch() { new ResizeObserver(() => 0); missingHelper(); }"
    for observer in ("studio-orbit.js", "studio-participants.js", "studio-trace.js"):
        assert _unreachable(source, observer) == ["missingHelper"], observer
        assert _unreachable(source.replace("ResizeObserver", "ResizeObserverTypo"),
                            observer) == ["ResizeObserverTypo", "missingHelper"]
    blind = set(MODULES) - set(MODULE_GLOBALS)
    assert set(MODULE_GLOBALS) < set(MODULES) and blind, sorted(MODULE_GLOBALS)
    for module in blind:
        assert _unreachable(source, module) == [
            "ResizeObserver", "missingHelper"], module
    assert all(names == frozenset({"ResizeObserver"})
               for names in MODULE_GLOBALS.values()), MODULE_GLOBALS
    # And every admission is SPENT: a module listed here that never calls the
    # name it was admitted for is a forgiveness nobody argued for, which is the
    # one widening the rest of this test cannot see -- each of its claims holds
    # over one identical synthetic source and none of them reads the module.
    unspent = {module: sorted(name for name in names
                              if name not in _code(PANEL / module))
               for module, names in MODULE_GLOBALS.items()}
    assert not any(unspent.values()), unspent


def test_this_guard_catches_the_break_that_produced_it():
    """Calibration. A resolver nobody has driven on a known case proves nothing.

    The exact shape of the defect: a function that calls three helpers the
    module does not have. If this ever stops failing, the guard above has
    stopped resolving names and every module it passes is unchecked.
    """
    broken = '''import {element} from "./command-view.js";
function edgePanel(mount, form, id) {
  const box = panelOf("edge", "Connection");
  unsupported(box, "Condition", "no home");
  box.append(editable(element("button", {}), form));
  call(form.handlers, "onEdit", {});
}
'''
    unreachable = sorted(
        _called(_scannable(broken)) - _names_in_scope(broken) - GLOBALS)

    assert unreachable == ["call", "editable", "panelOf", "unsupported"]


def test_the_scanner_does_not_weld_two_interpolations_into_a_name():
    """The second calibration, and the subtler of the two.

    A template that interpolates twice with prose between them produced a name
    from the tail of one and the head of the next. It reported `atshow` as
    missing from a module that calls `show` and reads `at` -- a false positive
    that would have been "fixed" by loosening the guard rather than by looking
    at it.
    """
    template = "const line = `loop ${at} reopens ${show(back)}`;"

    assert "atshow" not in _scannable(template)
    assert "show" in _called(_scannable(template))


def test_the_scanner_reads_no_call_out_of_a_regular_expression():
    """The other one: a regex is not a call, however much it looks like one."""
    pattern = r"const UTC = /^(\d{4})-(\d{2})T(\d{2})$/;"

    assert "T" not in _called(_scannable(pattern))


def test_this_guard_forgives_what_a_module_really_can_reach():
    """The over-correction control: it must not red on an honest module.

    A guard that reported everything would be turned off within a week, and the
    parametrised test above would then be covering nothing at all.
    """
    honest = '''import {element, field} from "./command-view.js";
import {CEILINGS as ceilings} from "./studio-model.js";
const LIMIT = 3;
function rows(value) { return Array.isArray(value) ? value : []; }
export function build(value) {
  if (rows(value).length > LIMIT) return null;
  return element("p", {text: String(Object.keys(ceilings).length)});
}
'''
    assert not (_called(_scannable(honest)) - _names_in_scope(honest)
                - GLOBALS)


def test_the_roster_of_globals_is_one_this_suite_agreed_to():
    """A global nobody wrote down is a name that silences the guard by accident.

    Held as a size and a spot check rather than a second copy of the list: what
    matters is that it stays small and deliberate, so a module reaching for
    something exotic has to come here and argue for it.
    """
    assert len(GLOBALS) < 50, sorted(GLOBALS)
    assert "eval" not in GLOBALS and "Function" not in GLOBALS


#: The three names only the boot module's read door may reach. A roster entry
#: forgives a name in EVERY module, so this holds these three back to one.
DEADLINE = re.compile(r"(?<![.\w$])(AbortController|setTimeout|clearTimeout)\b")


def test_the_deadline_globals_are_reached_by_the_boot_module_alone():
    """The roster admits a timer, its abort and its clearing for one door.

    Only the boot module owns a socket to bound. A second module reaching for
    a timer would be a second clock nobody reviewed, and the shared roster
    would let it past the resolver silently -- so the admission is held to the
    module it was made for, in both directions, and calibrated on a planted
    timer first so an empty scan cannot pass for a clean one.
    """
    planted = _scannable("function stall() { return setTimeout(() => 0, 5); }")
    assert DEADLINE.findall(planted) == ["setTimeout"]
    for name in MODULES:
        reached = sorted(set(DEADLINE.findall(_scannable(_code(PANEL / name)))))
        if name == "studio.js":
            assert reached == ["AbortController", "clearTimeout", "setTimeout"]
        else:
            assert reached == [], (name, reached)


def test_class_methods_are_declarations_but_bare_missing_calls_still_fail():
    source = """class Preferences {
  constructor(door) { this.door = door; }
  paint() { this.door.paint(); absentHelper(); }
  dispose() { this.door.remove(); }
}
function make(door) { return new Preferences(door); }
"""
    assert _unreachable(source, "studio-preferences.js") == ["absentHelper"]
    # A method declaration does not introduce a bare callable outside it.
    assert _unreachable(source + "\npaint();", "studio-preferences.js") == [
        "absentHelper", "paint"]
