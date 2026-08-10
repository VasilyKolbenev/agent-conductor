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
helper those sites spell the root with is read too, and more narrowly: every
printed command passes through it, so a value woven into what it RETURNS would
reach all of them at once while standing at no site at all. That helper is
therefore held to a single SHAPE — one `return`, of this module's own string
literals and the one name its signature takes, arranged in tuples and
conditionals — and every other shape is a door. Held as a shape and not as a
list of banned forms on purpose: a call, a `+`, an f-string, a comprehension, a
second helper and the form nobody has written yet are all out because they are
not the one allowed in, so this file does not have to have foreseen them. A
fourth door added later is caught because it is in the source — not because the
corpus happened to grow a project that walks through it.

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
CALLER passes into that parameter is not read here. That is the one level left
open, and left open deliberately — the root is the path the reader typed on
their own command line, which `_spelled` in `doctor.py` says in as many words
is a value this module does not defend against. And a command line is a
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
#: What the star stands FOR is read too, and by a rule narrower than a site's:
#: the helper must be one `return` of this module's literals and the single
#: name it takes, so nothing else can be in the tuple the star unpacks.
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


#: The one shape `_dir_args` is allowed to have, as the kinds of node it may
#: be built from. An allowlist and not a list of banned forms, which is the
#: whole mechanism: a call, a `+`, an f-string, a comprehension, a walrus, a
#: second helper — and every shape nobody has written yet — are doors by not
#: being in here, rather than by having been thought of. `ast.Compare` is in
#: because the default root is told apart by `root == "."`; a comparison
#: decides WHICH tuple comes back and puts nothing into one.
RETURNABLE = (ast.Return, ast.IfExp, ast.Compare, ast.Tuple, ast.Name,
              ast.Constant)


def root_args():
    """What `_dir_args` can be handed a value in, and the body that answers.

    The star above stands for what this function RETURNS, and no site holds
    it: it is where `--dir` and the root are put together, and the one tuple
    every printed command with a root of its own is spliced from.

    Returns:
        `(the parameter names, the body with a leading docstring dropped)`.
        Every place a signature can take a value is counted — positional-only,
        ordinary, keyword-only, and `*args`/`**kwargs`, the last two spelled
        with their stars so a widening there cannot read as an ordinary name.
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
            body = function.body
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                body = body[1:]
            return takes, body
    return [], []


def foreign_nodes(returned, takes):
    """Every node under one `return` that the one allowed shape does not admit.

    The shape entire: tuple literals and conditionals over them, whose
    elements are this module's own string literals and the single name the
    signature takes. Everything is measured against that and nothing against a
    catalogue of bad forms — so a value reaching the returned tuple through a
    call, a `+`, an f-string, a comprehension, a second helper or a shape this
    file has never seen is reported because it is not the allowed one, which
    is what stops this from being the same fix again one level further out.

    Args:
        returned: The single `return` statement `root_args` handed back.
        takes: Its parameter names. A `Name` is admitted only when the
            signature takes exactly that one name, so a widened signature
            cannot smuggle a second name into the tuple.

    Returns:
        `(unparsed node, line)` for each door, so a report names where. Nodes
        carrying no value of their own — an expression context, a comparison
        operator — are not read.
    """
    doors = []
    for node in ast.walk(returned):
        if not isinstance(node, (ast.expr, ast.stmt)):
            continue
        if (not isinstance(node, RETURNABLE)
                or (isinstance(node, ast.Name) and [node.id] != takes)
                or (isinstance(node, ast.Constant)
                    and not isinstance(node.value, str))):
            doors.append((ast.unparse(node), node.lineno))
    return doors


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
    # reads. What is held is the SPLICE IN THE SOURCE and not what any command
    # prints: `_dir_args` returns an empty tuple for the default root, as its
    # own docstring says, so a report about `.` prints commands naming no
    # project at all — including `conduct init`. That is the module's design
    # and this test neither holds it nor contradicts it.
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
    # strength of what one function RETURNS, so what it returns is what is
    # read here — and not the tuple literals that happen to lie in its body,
    # which a value glued on to the returned tuple by anything else walks
    # straight past. Such a value would be printed by every command carrying a
    # root while standing at none of the sites: exactly the door a site cannot
    # see. So the helper is held to ONE shape — one return, of literals and
    # the single name it takes — and everything else is reported, including
    # the forms nobody has written. That is the point of holding a shape
    # rather than banning a list: the list is what has to be extended each
    # time somebody finds one more way in.
    takes, body = root_args()
    # One value in, so one value out — counted over the whole signature, so a
    # second way in opened anywhere in it is a widening this line reports.
    assert len(takes) == 1, takes
    assert len(body) == 1 and isinstance(body[0], ast.Return), (
        f"{_ROOT_ARGS} is no longer one return, so what it hands back cannot "
        f"be read off a single expression: {[ast.unparse(s) for s in body]}")
    doors = foreign_nodes(body[0], takes)
    assert not doors, f"value(s) reaching every printed command unread: {doors}"
    # Vacuity guard, for the same reason as the one below: a walk that stopped
    # finding this tuple would report no doors and mean nothing by it. `--dir`
    # is the flag those commands are spliced with.
    literals = {element.value for node in ast.walk(body[0])
                if isinstance(node, ast.Tuple) for element in node.elts
                if isinstance(element, ast.Constant)
                and isinstance(element.value, str)}
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
