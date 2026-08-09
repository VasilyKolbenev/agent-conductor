"""Every door a project-controlled value can take into a printed command.

`test_doctor.py` measures behaviour: a corpus of one project per readiness
answer, payloads pushed through a role id, a lane author spelled as a flag,
and every printed line handed back to the CLI to prove argparse still takes
it. That covers the doors somebody thought to build a project for. It cannot
cover the door nobody thought of — and that is precisely the defect this file
exists for. `_spellable` guarded the role id while the lane author beside it
went into `conduct prompt --author` unread, and the corpus stayed green for as
long as it took someone to think of writing a lane named `-x`.

So nothing here builds a project. This file reads the module's own source,
finds the argv sites by walking it, and holds every one of them to one rule: a
token of a printed command is this module's own literal, the root the reader
themselves typed, or a value that went through `_spellable` first. A fourth
door added later is caught because it is in the source — not because the
corpus happened to grow a project that walks through it.

WHAT NOTHING HERE HOLDS. Whether `_spellable` is the right rule, and what any
command does once it parses, are not asked here: this file only asks that
every authored token is put to the predicate. The predicate's own content is
measured in `test_doctor.py`, by running every command the report prints.
Nor is this a reachability proof — a guarded token is one `_spellable` is
called on somewhere in the same function, which is what the module's shape
makes checkable, and not a claim that no branch can reach the tuple another
way.
"""
import ast
import string
from pathlib import Path

import pytest
from conductor import doctor

#: The module read as text, from the file the imported module actually came
#: from — so a worktree whose imports resolve elsewhere reads that elsewhere
#: rather than quietly measuring the source sitting next to this test.
SOURCE = Path(doctor.__file__).read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)

#: The call that contributes the reader's own project root to an argv. It is
#: also what makes an argv recognisable: every command this module prints
#: carries the root, so a tuple holding this star is a command line and a
#: tuple not holding one is not.
_ROOT_ARGS = "_dir_args"

#: The predicate a value out of the project's files has to pass before it may
#: be printed into a command.
_GUARD = "_spellable"

#: What a bundled constant may hold and still mean itself when it is pasted
#: bare. Owned here rather than imported from `doctor`: a guard that asks the
#: code under test which characters are safe agrees with it by construction,
#: and would go on agreeing while that set was widened.
BARE_ENOUGH = set(string.ascii_letters + string.digits + "-_.,:/@+=~\\")


def _shape(node):
    """One expression as a comparable shape, with line numbers left out."""
    return ast.dump(node)


def argv_sites():
    """Every argv tuple in the module, with the function that builds it.

    Yields:
        `(function name, tuple node)` for each tuple literal holding a
        `*_dir_args(...)` star. That star is the signature of a command line
        rather than an arbitrary tuple: `--dir` is how a printed command says
        which project it is about, and every one of them carries it.
    """
    for function in ast.walk(TREE):
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(function):
            if not isinstance(node, ast.Tuple):
                continue
            if any(isinstance(element, ast.Starred)
                   and isinstance(element.value, ast.Call)
                   and getattr(element.value.func, "id", None) == _ROOT_ARGS
                   for element in node.elts):
                yield function.name, node


def guarded_in(function_name):
    """Every expression `_spellable` is called on inside one function."""
    for function in ast.walk(TREE):
        if (isinstance(function, ast.FunctionDef)
                and function.name == function_name):
            return {_shape(call.args[0]) for call in ast.walk(function)
                    if isinstance(call, ast.Call)
                    and getattr(call.func, "id", None) == _GUARD
                    and call.args}
    return set()


def _dotted_value(node):
    """The runtime value behind `templates.DEFAULT`, or None if not a dotted name."""
    if not (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)):
        return None
    module = getattr(doctor, node.value.id, None)
    return getattr(module, node.attr, None)


def describe(function_name, element):
    """Which of the four kinds of argv token this element is, or None if it is a door.

    The four are the whole rule, and each carries its own reason. A string
    literal is a word this module wrote. The `*_dir_args(root)` star is the
    root the reader typed, which `_spelled` quotes when bare would not carry
    it. A guarded expression is a value out of the project's files that has
    been put to `_spellable`. A dotted name is a constant out of a bundled
    module — resolved here and required to need no quoting, rather than waved
    through because it looks like a constant.
    """
    if isinstance(element, ast.Constant) and isinstance(element.value, str):
        return "literal"
    if (isinstance(element, ast.Starred) and isinstance(element.value, ast.Call)
            and getattr(element.value.func, "id", None) == _ROOT_ARGS):
        return "the reader's own root"
    if _shape(element) in guarded_in(function_name):
        return "guarded"
    value = _dotted_value(element)
    if isinstance(value, str) and not set(value) - BARE_ENOUGH:
        return "bundled constant"
    return None


#: The doors that exist today, named so a walk that quietly stops finding
#: anything fails instead of passing over nothing. A floor and not a ceiling:
#: a new door is not required to be listed here, only to be guarded.
KNOWN_DOORS = {
    ("_start_advice", "role['id']"),
    ("_restart_advice", "lane['role']"),
    ("_restart_advice", "lane['author']"),
    ("_unheld_advice", "role_id"),
}


def authored_doors():
    """Every argv element that is neither a literal nor the reader's own root."""
    found = set()
    for function_name, argv in argv_sites():
        for element in argv.elts:
            if isinstance(element, ast.Constant) or isinstance(element, ast.Starred):
                continue
            found.add((function_name, ast.unparse(element)))
    return found


def test_every_value_a_printed_command_carries_is_a_literal_a_root_or_spellable():
    # The traversal, and the whole point of the file: every token of every
    # argv the module builds is accounted for by one of four kinds. An element
    # that is none of them is a value reaching a printed command by a path
    # nobody put a predicate on — which is what `--author` was.
    doors = []
    for function_name, argv in argv_sites():
        for element in argv.elts:
            if describe(function_name, element) is None:
                doors.append((function_name, ast.unparse(element),
                              element.lineno))
    assert not doors, f"unguarded value(s) reaching a printed command: {doors}"


def test_the_walk_finds_every_argv_the_module_builds():
    # Vacuity guard. Everything above is a statement about the set this walk
    # returns, so a walk that returned nothing would prove nothing and say it
    # loudly. The five verbs are every command the report can name, and the
    # known doors are the authored values that reach one today.
    verbs = {argv.elts[0].value for _, argv in argv_sites()
             if isinstance(argv.elts[0], ast.Constant)}
    assert verbs == {"init", "validate", "doctor", "prompt", "up"}, verbs
    assert KNOWN_DOORS <= authored_doors(), authored_doors()


@pytest.mark.parametrize("function_name,expression", sorted(KNOWN_DOORS))
def test_each_authored_value_is_put_to_the_predicate_in_its_own_function(
        function_name, expression):
    # One row per door, so a guard dropped from one of them names which. The
    # relation is between the tuple and the predicate, not between the test
    # and a remembered line number: the expression printed into the command
    # has to be the same expression `_spellable` was asked about.
    matching = [element for name, argv in argv_sites() if name == function_name
                for element in argv.elts
                if not isinstance(element, (ast.Constant, ast.Starred))
                and ast.unparse(element) == expression]
    assert matching, f"{expression} no longer reaches an argv in {function_name}"
    guarded = guarded_in(function_name)
    assert all(_shape(element) in guarded for element in matching), expression
