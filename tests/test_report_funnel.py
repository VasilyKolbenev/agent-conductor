"""The one door out of the document, pinned by the shape of `conductor.report`.

A review closed forgery for the fields it named and left the neighbouring ones
open: authored prose was flattened onto its line and identifiers were not, so a
schema-valid finding `id` carrying line breaks and headings still printed three
`## What this report does not know` headings, two of them the author's. Fixing
the named fields again would leave the next site to be added open in its turn.

So the module has one door — `_from_document` — and these guards are written
against the module's own AST rather than against a list of fields. A rendering
site added later that *builds* a line out of a document value — an f-string, or
a string joined to a string — reds
`test_no_function_but_the_funnels_own_puts_a_document_value_into_an_f_string`
or the join guard beside it, without anybody remembering to extend a fixture,
and so does a second door written to look like the first, because that door's
own body would read the document without going through `_from_document`.

What the AST guards do *not* cover, and why:

* `findings[].detail` and `[].evidence` take the verbatim path through
  `_verbatim`, which is the point of those two fields. Their fence is measured
  in `tests/test_report.py`, by reading the rendered report the way CommonMark
  does;
* a value the *merger* folded into a string before the report saw it —
  `next_action.text` is built from a wait's `title`, a string whenever the
  document passed the schema — is a string in the document by the time it
  arrives, and the report renders it as one.
  `test_outside_the_contract_the_brief_still_carries_the_repr_the_merger_wrote`
  in `tests/test_report.py` pins that, and says so in its name;
* a site that does not build a line but *returns a document value as one* —
  appended or spliced into the list of lines a section returns, with no
  f-string and no join anywhere in it — is not a shape these guards read.
  `_unknown_lanes` returning each broken lane's own `error` text that way
  passes all five of them, and prints a second `## What this report does not
  know` when that text holds one. Only a rendered report shows that, and only
  for a document some fixture holds.

The behavioural half is `test_no_string_field_of_the_document_can_forge_a_heading`:
every string in a full document, one at a time, replaced by text that forges
headings. It is the measurement; the AST guards are what keep the two
line-building shapes from being outgrown by a field nobody added to a fixture.
"""
import ast
import json
from pathlib import Path

from conductor import report
from conductor.__main__ import main
from tests.test_report import (FORGERY, _gapless_state, _leaf_paths,
                               _with_a_sentinel_at)
from tests.test_store import write_project

SOURCE = Path(report.__file__).resolve()
TREE = ast.parse(SOURCE.read_text(encoding="utf-8"))

#: The door, and the three helpers that are its own parts rather than doors of
#: their own. `test_the_funnels_own_parts_are_reached_from_the_funnel_and_from
#: _nowhere_else` is what makes that description true: the parts may read a
#: value directly, because nothing outside the door can hand them one.
FUNNEL = {"_from_document", "_span", "_blank", "_one_line"}

#: Every function the module defines. A call to one of them carries no document
#: value onward by itself: whatever it returns, its own body is checked here.
MODULE_FUNCTIONS = {node.name for node in TREE.body
                    if isinstance(node, ast.FunctionDef)}

#: The one builtin that reduces a document list to something carrying none of
#: its text. Counts are how the section headings say how many of a thing there
#: are, and a count cannot forge a line.
COUNT = "len"


def _functions(only_outside_the_funnel=False):
    """The module's top-level function definitions."""
    return [node for node in TREE.body if isinstance(node, ast.FunctionDef)
            and not (only_outside_the_funnel and node.name in FUNNEL)]


def _carries(node, tainted):
    """Whether an expression can put a value taken from the document into text.

    Args:
        node: The expression to read.
        tainted: Names that can hold a value taken from the document.

    Returns:
        False for a constant, for a comparison (which yields a bool whatever it
        compared), for a count, and for a call to a function of this module —
        that function's own body is checked by the same guard. True when a
        tainted name is reachable any other way.
    """
    if node is None or isinstance(node, ast.Constant):
        return False
    if isinstance(node, ast.Name):
        return node.id in tainted
    if isinstance(node, ast.Compare):
        return False
    if isinstance(node, ast.Call):
        called = node.func.id if isinstance(node.func, ast.Name) else None
        if called == COUNT or called in MODULE_FUNCTIONS:
            return False
        parts = [node.func, *node.args, *(kw.value for kw in node.keywords)]
        return any(_carries(part, tainted) for part in parts)
    return any(_carries(child, tainted) for child in ast.iter_child_nodes(node))


def _bindings(node):
    """`(the expression bound, the targets it is bound to)`, or None."""
    if isinstance(node, ast.Assign):
        return node.value, node.targets
    if isinstance(node, (ast.AugAssign, ast.AnnAssign)):
        return node.value, [node.target]
    if isinstance(node, (ast.For, ast.comprehension)):
        return node.iter, [node.target]
    return None


def _tainted_names(func):
    """Every local of `func` that can hold a value taken from the document.

    Its parameters — the document arrives as one, always — and then whatever is
    bound from an expression carrying one, loop and comprehension targets
    included. Read to a fixed point, because a binding can precede the binding
    that taints what it read.
    """
    names = {arg.arg for arg in (*func.args.posonlyargs, *func.args.args,
                                 *func.args.kwonlyargs)}
    growing = True
    while growing:
        growing = False
        for node in ast.walk(func):
            bound = _bindings(node)
            if not bound or not _carries(bound[0], names):
                continue
            for target in bound[1]:
                for name in ast.walk(target):
                    if isinstance(name, ast.Name) and name.id not in names:
                        names.add(name.id)
                        growing = True
    return names


def _interpolations(func):
    """Every expression an f-string of `func` renders into its text."""
    for node in ast.walk(func):
        if isinstance(node, ast.JoinedStr):
            for part in node.values:
                if isinstance(part, ast.FormattedValue):
                    yield part.value


def test_no_function_but_the_funnels_own_puts_a_document_value_into_an_f_string():
    # The claim the module docstring makes, held by the module's shape rather
    # than by a list of fields: outside `_from_document` and its parts, every
    # value interpolated into a rendered line either came from the door or
    # never came from the document at all.
    direct = []
    for func in _functions(only_outside_the_funnel=True):
        tainted = _tainted_names(func)
        direct += [f"{func.name}: {ast.unparse(expr)}"
                   for expr in _interpolations(func) if _carries(expr, tainted)]
    assert direct == [], (
        "these sites render a document value without passing it through "
        f"`_from_document`: {direct}")


def _is_text(node):
    """Whether a node is a piece of rendered text — a string literal or f-string."""
    return isinstance(node, ast.JoinedStr) or (isinstance(node, ast.Constant)
                                               and isinstance(node.value, str))


def test_outside_the_funnel_a_line_is_built_by_an_f_string_and_by_nothing_else():
    # Without this the guard above would be a guard on an idiom rather than on
    # the module: `"### " + finding.get("id")` renders a document value into a
    # line and holds no f-string for the walk above to find. The module joins a
    # string to a string in exactly one place, and that place adds a newline to
    # a body already rendered.
    joins = []
    for func in _functions(only_outside_the_funnel=True):
        for node in ast.walk(func):
            if (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add)
                    and (_is_text(node.left) or _is_text(node.right))):
                joins.append(f"{func.name}: {ast.unparse(node)}")
    assert joins == ["render: body + '\\n'"]


def test_the_funnels_own_parts_are_reached_from_the_funnel_and_from_nowhere_else():
    # What makes `_span`, `_blank` and `_one_line` parts of the door rather
    # than three more doors, and what lets the guard above skip their bodies:
    # nothing outside the door can hand them a value to render.
    parts = FUNNEL - {"_from_document"}
    callers = {}
    for func in _functions():
        called = {node.func.id for node in ast.walk(func)
                  if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
        for part in called & parts:
            callers.setdefault(part, set()).add(func.name)
    assert callers == {"_one_line": {"_from_document"},
                       "_blank": {"_from_document"},
                       "_span": {"_from_document", "_blank"}}


def _heading_shape(text):
    """The heading structure a reader meets, with none of the document in it.

    A `## ` heading is written whole by the report and reads back verbatim; `#`
    and `###` carry a field value, so only their level is taken. A forged
    heading changes this either way: it arrives as an extra entry.

    Read the way CommonMark reads it, fences and all — `findings[].detail` and
    `[].evidence` are quoted verbatim on purpose, so a `##` line inside their
    fence is text the reader is shown and not a heading the reader meets. A
    scanner that counted raw lines would call the report's own promise a
    forgery, and would say nothing about the fence holding.
    """
    shape, fence = [], None
    for line in text.splitlines():
        closing = len(line) >= 3 and set(line) == {"`"}
        if fence is not None:
            fence = None if closing and len(line) >= len(fence) else fence
        elif closing:
            fence = line
        elif line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            shape.append(line if level == 2 else level)
    assert fence is None, "a fence opened in the report and never closed"
    return shape


def _at(state, path):
    """The value `path` names in `state`."""
    for step in path:
        state = state[step]
    return state


def test_no_string_field_of_the_document_can_forge_a_heading():
    # Universal over the document rather than over a list somebody maintains:
    # every string in a full state, one at a time, replaced by text that opens
    # two headings of its own. The report's headings are the report's.
    state = _gapless_state()
    shape = _heading_shape(report.render(state))
    assert len(shape) > 6, "the fixture is too thin to hold a guard"
    strings = [path for path in _leaf_paths(state)
               if isinstance(_at(state, path), str)]
    assert len(strings) > 30, "the fixture holds too few strings to be a universal"
    reached = 0
    for path in strings:
        forged = report.render(_with_a_sentinel_at(state, path, FORGERY))
        assert _heading_shape(forged) == shape, f"{'.'.join(map(str, path))} forged one"
        reached += "Nothing at all." in forged
    # Not vacuous: most of those forgeries were rendered, and rendered whole.
    # A report that dropped what it could not make safe would hold the headings
    # still for the emptiest of reasons. (The rest are `map` fields §6.1 records
    # and this report does not display, which is its own guard in test_report.)
    assert reached > len(strings) // 2, (
        f"only {reached} of {len(strings)} forgeries reached the reader at all")


#: The reviewer's own input, kept as they built it: a finding `id` that no
#: schema rule rejects, carrying line breaks, a heading that contradicts the
#: report's own, and a backtick to close the code span it renders into.
FORGED_ID = ("D-1`\n\n## What this report does not know\n\nNothing at all.\n\n"
             "## Findings\n\nnothing here\n\n### `x")


def test_a_finding_id_that_forges_headings_passes_validate_and_forges_none(
        tmp_path, capsys):
    # Through the commands, because that is how the review found it: the report
    # is only safe if what `conduct report` prints is safe, and a guard on
    # `render` alone would not have caught a CLI that rendered some other way.
    lane = json.dumps({"schema_version": 1, "author": "claude",
                       "updated": "2026-07-30T11:00:00+00:00",
                       "findings": [{"id": FORGED_ID, "title": "t",
                                     "severity": "blocker", "claim": "c",
                                     "detail": "d", "evidence": "e", "refs": []}]})
    root = write_project(tmp_path, lanes={"claude": lane})
    assert main(["validate", "--dir", str(root)]) == 0     # the schema still allows it
    capsys.readouterr()
    assert main(["report", "--dir", str(root)]) == 0
    printed = capsys.readouterr().out
    assert printed.count("\n## What this report does not know") == 1
    assert "\n## Findings\n" not in printed and "\nNothing at all." not in printed
    assert "\n### `x" not in printed
    # Reported, not swallowed: the id reaches the reader on one line, disclosed.
    assert "Nothing at all." in printed and "shown here as `\\n`" in printed
