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
finds every command line by walking it, and holds each to two rules. It is
spliced with the reader's own root — which is the sentence the rest rests on,
so it is measured and not assumed. And every token of it is this module's own
literal, that root, or a value that went through `_spellable` first. The one
helper those sites spell the root with is read the same way: every printed
command passes through it, so a value woven into what it returns would reach
all of them at once while appearing at no site at all. A fourth door added
later is caught because it is in the source — not because the corpus happened
to grow a project that walks through it.

A command line is recognised by the verb it opens on, read from the CLI's own
source, and not by the root star it carries. Both halves of that matter. A
tuple found by its star could never be a tuple missing one, so "every command
carries the root" would have been true by the way the walk was written rather
than by anything the module does; and a command built with no root at all —
`("prompt", "--role", role_id)` — would have been no tuple this file had ever
heard of, its authored token held to nothing.

WHAT NOTHING HERE HOLDS. Whether `_spellable` is the right rule, and what any
command does once it parses, are not asked here: this file only asks that
every authored token is put to the predicate. The predicate's own content is
measured in `test_doctor.py`, by running every command the report prints.
Nor is this a reachability proof — a guarded token is one `_spellable` is
called on somewhere in the same function, which is what the module's shape
makes checkable, and not a claim that no branch can reach the tuple another
way. Nor is the root followed further back than the site: it is recognised as
the first parameter of the function the site stands in, unrebound, and what a
CALLER passes into that parameter is not read here. And a command line is a
TUPLE LITERAL opening on a LITERAL verb: one assembled some other way — the
verb held in a variable, the tuple returned by a call or glued together from
fragments — is not found by that rule, and the floor below is what notices the
walk going quiet.
"""
import ast
import string
from pathlib import Path

import pytest
from conductor import __main__ as cli
from conductor import doctor

#: The module read as text, from the file the imported module actually came
#: from — so a worktree whose imports resolve elsewhere reads that elsewhere
#: rather than quietly measuring the source sitting next to this test.
SOURCE = Path(doctor.__file__).read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def _verbs():
    """Every word `conduct` has a subcommand for, read out of the CLI's source.

    Read rather than listed: the set that decides which tuples this file walks
    must be the CLI's own, so a subcommand added there is one a command tuple
    can open on here without an edit to keep in step.
    """
    source = Path(cli.__file__).read_text(encoding="utf-8")
    return frozenset(node.args[0].value for node in ast.walk(ast.parse(source))
                     if isinstance(node, ast.Call)
                     and getattr(node.func, "attr", None) == "add_parser"
                     and node.args and isinstance(node.args[0], ast.Constant))


#: What makes a tuple a command line, and the reason the walk below is not
#: hung on the root star: a command built with no root at all would be
#: invisible to a walk looking for that star, and is exactly the tuple this
#: file must not miss.
VERBS = _verbs()

#: The call that splices the reader's own project root into a command. Every
#: command this module prints carries it — a convention this file rests on and
#: MEASURES, rather than a fact read off today's source: the tuples are found
#: by their verb, and each is then held to carrying exactly one of these stars.
#: What the star stands for is read too: the tuple that call returns is walked
#: below and held to the same rule as the sites it is spliced into.
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
    """Every command line the module builds, with the function that builds it.

    Yields:
        `(function name, tuple node)` for each tuple literal whose first
        element is a literal verb — a word `conduct` has a subcommand for.
        That is the CLI's own definition of a command line, and it is what a
        tuple is recognised by here: a tuple opening on `prompt` is a command
        whether or not it carries a root, so one built without a root is found
        and reported rather than walked past.
    """
    for function in ast.walk(TREE):
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(function):
            if (isinstance(node, ast.Tuple) and node.elts
                    and isinstance(node.elts[0], ast.Constant)
                    and node.elts[0].value in VERBS):
                yield function.name, node


def root_stars(argv):
    """Every `*_dir_args(...)` element of one command tuple, whatever it was given."""
    return [element for element in argv.elts
            if isinstance(element, ast.Starred)
            and isinstance(element.value, ast.Call)
            and getattr(element.value.func, "id", None) == _ROOT_ARGS]


def root_args_body():
    """What `_dir_args` takes, and every element of every tuple its body builds.

    The star above stands for this tuple, and no site holds it: it is where
    `--dir` and the root are put together, and the one tuple every printed
    command with a root of its own is spliced from.

    Returns:
        `(the parameter names, the tuple elements)`. Every place a signature
        can take a value is counted — positional-only, ordinary, keyword-only,
        and `*args`/`**kwargs`, the last two spelled with their stars so a
        widening there cannot read as an ordinary name. The body only — a
        return annotation like `tuple[str, ...]` is a tuple to `ast` and none
        of this module's business.
    """
    for function in ast.walk(TREE):
        if (isinstance(function, ast.FunctionDef)
                and function.name == _ROOT_ARGS):
            signature = function.args
            takes = [argument.arg for argument in
                     (*signature.posonlyargs, *signature.args,
                      *signature.kwonlyargs)]
            takes += [f"*{extra.arg}" for extra in (signature.vararg,)
                      if extra is not None]
            takes += [f"**{extra.arg}" for extra in (signature.kwarg,)
                      if extra is not None]
            return (takes,
                    [element for statement in function.body
                     for node in ast.walk(statement)
                     if isinstance(node, ast.Tuple) for element in node.elts])
    return [], []


def _own_scope(function):
    """Every node of one function's body that its OWN scope holds.

    A nested `def` or `lambda` is yielded but not descended into: what its
    body binds it binds inside itself, under a name of its own. A
    comprehension IS descended into, because a walrus in one binds in the
    scope AROUND it — only the loop variables below are the comprehension's.
    """
    stack = list(function.body)
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.Lambda)):
            stack.extend(ast.iter_child_nodes(node))


def _binds(node):
    """Every name one node binds, read off the field its form keeps the name in.

    An assignment, a `for` target and a walrus all store to an `ast.Name`.
    Everything else that binds — `def`, `class`, `except ... as`,
    `import ... as`, a match pattern — keeps the name in a `name` or `asname`
    field, and is read that way rather than from a list of statements, so a
    binding form nobody enumerated here still lands in the set.
    """
    if isinstance(node, ast.Name):
        return {node.id} if isinstance(node.ctx, ast.Store) else set()
    if isinstance(node, (ast.Global, ast.Nonlocal)):
        return set(node.names)
    return {bound for field in ("name", "asname")
            for bound in (getattr(node, field, None),) if isinstance(bound, str)}


def rebound_in(function):
    """Every name one function binds in its own scope, its parameters aside."""
    own = list(_own_scope(function))
    loop_variables = {id(name) for node in own
                      if isinstance(node, (ast.ListComp, ast.SetComp,
                                           ast.DictComp, ast.GeneratorExp))
                      for generator in node.generators
                      for name in ast.walk(generator.target)
                      if isinstance(name, ast.Name)}
    return {bound for node in own if id(node) not in loop_variables
            for bound in _binds(node)}


def root_parameter(function_name):
    """The name one function was handed its root in — its first parameter, if it still holds it.

    Returns:
        The first parameter's name, or None when the function has no parameter
        or binds that name again in its OWN scope. A rebound name is not the
        root the caller passed: `root = role["harness"]` before a site leaves
        the site spelled exactly as it was while meaning something else. Own
        scope and not anywhere below it: a comprehension's loop variable and a
        name assigned inside a nested `def` are different names that happen to
        be spelled the same, and counting those would turn every star in such
        a function into a door over code that rebinds nothing.
    """
    for function in ast.walk(TREE):
        if (isinstance(function, ast.FunctionDef)
                and function.name == function_name):
            takes = (*function.args.posonlyargs, *function.args.args)
            if not takes:
                return None
            first = takes[0].arg
            return None if first in rebound_in(function) else first
    return None


def spliced_root(function_name, element):
    """The name for a star that splices in the site's own root, or None if it does not.

    The whole rule, and the one the site can be read for: the call must be
    `_dir_args`, handed exactly one value in a place this file can name, and
    that value must be the name the enclosing function was given its root in.
    Anything else — an expression, a local bound to something out of the
    project's files, an extra argument — is a value reaching a printed command
    by a path nothing put a predicate on.

    One value in a place this file can name is either a lone positional or a
    lone keyword whose name is `_dir_args`'s own first parameter: `root=root`
    hands over exactly what `(root)` does, and refusing it would redden legal
    code. `*args` and `**kwargs` at the call are neither — the values in them
    are not countable from here, so they are not read as the root.
    """
    call = element.value
    if not (isinstance(call, ast.Call)
            and getattr(call.func, "id", None) == _ROOT_ARGS):
        return None
    if len(call.args) + len(call.keywords) != 1:
        return None
    if call.keywords:
        keyword = call.keywords[0]
        if keyword.arg is None or keyword.arg != root_parameter(_ROOT_ARGS):
            return None
        argument = keyword.value
    else:
        argument = call.args[0]
    root = root_parameter(function_name)
    if not (root is not None and isinstance(argument, ast.Name)
            and argument.id == root):
        return None
    return "the reader's own root"


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
    it; what earns it that name is not the shape of the call but its argument,
    which `spliced_root` holds to being the very name the enclosing function
    was handed its root in and still holds — so a local bound to a value out
    of the project's files is a door here and not a root, however plainly it
    is spelled. What the call returns is held to the same rule below. A
    guarded expression is a value out of the project's files that has been put
    to `_spellable`. A dotted name is a constant out of a bundled module —
    resolved here and required to need no quoting, rather than waved through
    because it looks like a constant.
    """
    if isinstance(element, ast.Constant) and isinstance(element.value, str):
        return "literal"
    if isinstance(element, ast.Starred):
        return spliced_root(function_name, element)
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
    """Every argv element that is neither a literal nor a spliced tuple.

    The floor's raw material, and deliberately blunter than `describe`: a star
    is skipped here whatever it was handed, because whether it stands for the
    reader's root is the question `describe` answers and this one only counts
    the values that stand in an argv by name.
    """
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
    # Two things end up in this list and the message says so, because a star
    # is rejected for its CALL FORM and not for the value in it: a splice this
    # file cannot count the arguments of is refused without any claim about
    # what was passed.
    assert not doors, (
        "value(s) reaching a printed command by a path nothing guards, or "
        f"spliced by a call this file cannot read as the root: {doors}")


def test_every_command_line_the_module_builds_is_spliced_with_the_readers_root():
    # The rule the file rests on, held rather than assumed. Every token of a
    # command is accounted for above by the function it stands in — so a
    # command carrying no root is a command whose tokens were never put to
    # anything, because nothing spliced it out of the one helper the walk
    # reads. Naming a project on the command line is also what keeps a printed
    # `conduct init` from scaffolding into whatever directory a reader happens
    # to be standing in.
    miscounted = [(name, len(root_stars(argv)), ast.unparse(argv), argv.lineno)
                  for name, argv in argv_sites() if len(root_stars(argv)) != 1]
    # The count is reported, not translated into a story about it: with two
    # stars in a tuple, "built without the reader's root" would have been the
    # opposite of what happened.
    assert not miscounted, (
        "every command must splice the reader's root exactly once; these "
        f"carry the number named beside them: {miscounted}")


def test_the_tuple_the_root_star_stands_for_holds_that_root_and_nothing_else():
    # The other half of the traversal, and the half a site cannot show. Every
    # element above that is a star is called "the reader's own root" on the
    # strength of what one function returns, so that function is read: it may
    # put this module's own literals and the single value it was handed into
    # its tuple, and nothing else. A value spliced in there would be printed by
    # every command carrying a root while standing at none of the sites — which
    # is exactly the shape of door the sites cannot see.
    takes, elements = root_args_body()
    # One value in, so one value out — counted over the whole signature, so a
    # second way in opened anywhere in it is a widening this line reports.
    assert len(takes) == 1, takes
    literals = {element.value for element in elements
                if isinstance(element, ast.Constant)
                and isinstance(element.value, str)}
    doors = [(ast.unparse(element), element.lineno) for element in elements
             if not (isinstance(element, ast.Constant)
                     and isinstance(element.value, str))
             and not (isinstance(element, ast.Name) and [element.id] == takes)]
    assert not doors, f"value(s) reaching every printed command unread: {doors}"
    # Vacuity guard, for the same reason as the one below: a walk that stopped
    # finding this tuple would report no doors and mean nothing by it. `--dir`
    # is the flag those commands are spliced with.
    assert literals == {"--dir"}, literals


def test_the_walk_finds_every_argv_the_module_builds():
    # Vacuity guard. Everything above is a statement about the set this walk
    # returns, so a walk that returned nothing would prove nothing and say it
    # loudly — and the walk now turns on a set read out of another file, which
    # is one more way for it to come back empty. The five verbs are every
    # command the report can name — `demo` is the subcommand it never names —
    # and the known doors are the authored values that reach one today.
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
