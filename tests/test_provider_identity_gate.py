"""No module may BRANCH on which provider it is talking to, except that provider's.

A vendor name in an `if` is how an orchestrator stops being an orchestrator.
Once one exists, the next provider needs an edit there too, and the one after
that; the catalog stops being the place a provider is added and becomes a list
that has to agree with branches scattered through the runtime.

So the rule is structural and it is checked by reading the code rather than by
asking it: a comparison against a catalogued provider id -- `==`, `!=`, `in`,
`not in`, or a `match` case -- may appear only in the concrete module that
provider's adapter class lives in. Everything else is provider-neutral, and a
new provider is a catalog entry plus its own module.

Neither side of the rule is written down twice. The identities come out of
`PROVIDER_CATALOG` itself, and the module each one is allowed in comes out of
`entry.adapter_class.__module__` -- so a provider added to the catalog carries
its own permission with it, and a provider REMOVED takes its permission away.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from conductor.command.providers import PROVIDER_CATALOG

from tests.provider_identity_source import (
    ROOT,
    SOURCE,
    _compared_strings,
    _module_name,
    _own_containers,
    _trees,
)

#: `harnesses.py` is presentation metadata -- the rows a Cockpit draws badges
#: from -- and not a provider module of execution. It carries vendor ids as
#: DATA for every product the December Command lists, which is its whole job,
#: and it must never branch on one either.
PRESENTATION = SOURCE / "harnesses.py"
#: The presentation module, named once so this file's tests and the exception
#: below cannot disagree about which module it is.
PRESENTATION_MODULE = "conductor.harnesses"
#: The ONE exception, and it names a SYMBOL rather than a module. `harnesses.py`
#: is the presentation catalogue; its `RECOMMENDED` is the short menu
#: `conduct init` offers by number, and asking whether an id is in that menu
#: decides what a first prompt shows, not what any provider does. It is not a
#: provider-identity set at all -- `cursor` is in it and is catalogued nowhere.
#:
#: A pair, because a module is too coarse to mean it: excusing
#: `conductor.harnesses` would excuse a `SPECIAL = ("claude-code",)` added to
#: that file tomorrow and imported into execution code, which is the exact
#: hardcode this gate exists to stop. Every other container in the tree is
#: followed to every string it holds, and a LITERAL carries no symbol at all,
#: so one written inside `harnesses.py` is still a stray there.
EXCUSED = frozenset({(PRESENTATION_MODULE, "RECOMMENDED")})


def _excused(origin: tuple[str, str]) -> bool:
    """Whether a stray is excused -- and only one named SYMBOL can excuse one.

    Not the READER: `conductor.init` gets no blanket permission. And not the
    MODULE either, which is the subtler of the two mistakes -- excusing
    `conductor.harnesses` excuses everything that file ever declares, so a
    `SPECIAL = ("claude-code",)` added tomorrow and imported into execution
    code would walk through a gate whose own docstring says it cannot.

    The pair is the ORIGINAL declaration, carried through every alias and
    re-export, so a rename on the way in changes nothing in either direction:
    `RECOMMENDED as MENU` stays excused, and `SPECIAL as RECOMMENDED` stays a
    stray. A literal carries no symbol at all, so its origin is `("", "")`.
    """
    return origin in EXCUSED


def _identities() -> dict[str, str]:
    """Every catalogued provider id, and the module allowed to compare it."""
    return {
        entry.provider_id: entry.adapter_class.__module__
        for entry in PROVIDER_CATALOG.values()
    }


def _an_identity() -> str:
    """One catalogued identity, read out of the catalog rather than spelled."""
    return sorted(_identities())[0]


def _probe(source: str, modules: dict[str, str] | None = None) -> list[str]:
    """Read one synthetic NEUTRAL module against synthetic neighbours.

    The identity always comes from the catalog; the modules around it are
    written here, because the gate must hold for shapes this tree does not
    contain yet -- no package under `src/` re-exports a string constant today,
    so the rule that follows one could not be exercised against the real tree
    at all. It is the same `_compared_strings` the gate loop calls, not a
    private re-implementation, so a refactor that quietly narrows the resolver
    reds these too.
    """
    trees = {name: ast.parse(text) for name, text in (modules or {}).items()}
    return [value for value, _, _ in _compared_strings(
        "conductor.command.neutral", ast.parse(source), trees=trees)]


def test_a_neutral_module_that_imports_an_identity_constant_is_still_caught():
    """Spelling the id as the name it was imported under is the same branch.

    The gate reads text, and text can name a provider without quoting it: one
    `from ... import` and the vendor id is a bare identifier that no search for
    a string literal will ever see.
    """
    identity = _an_identity()
    modules = {"pkg.leaf": f"ID = {identity!r}\n"}
    for spelling, used in (("ID", "ID"), ("ID as _pinned", "_pinned")):
        source = (f"from pkg.leaf import {spelling}\n"
                  f"def route(chosen):\n"
                  f"    return chosen == {used}\n")
        assert _probe(source, modules) == [identity], spelling


def test_a_neutral_module_that_reaches_an_identity_through_its_module_is_caught():
    """A vendor name in an `if` with extra dots is a vendor name in an `if`.

    Every way of holding the module and reaching in has to arrive at the same
    string, because a rule a rename walks around is not a rule. The dotted form
    is also the ONLY spelling a `match` case can compare with -- a bare name
    there is a capture pattern that matches everything -- so both are guarded.
    """
    identity = _an_identity()
    modules = {"pkg.leaf": f"ID = {identity!r}\n"}
    reaches = (("import pkg.leaf as _pinned\n", "_pinned.ID"),
               ("import pkg.leaf\n", "pkg.leaf.ID"),
               ("from pkg import leaf\n", "leaf.ID"))
    for header, reference in reaches:
        bodies = (f"def route(chosen):\n    return chosen != {reference}\n",
                  "def route(chosen):\n"
                  "    match chosen:\n"
                  f"        case {reference}:\n"
                  "            return True\n"
                  "    return False\n")
        for body in bodies:
            assert _probe(header + body, modules) == [identity], reference


def test_an_identity_re_exported_through_a_package_is_reached_through_it():
    """A package that passes a constant on is not a way around the rule.

    `from .adapters import KIMI_PROVIDER_ID` and `from .adapters.kimi_code
    import KIMI_PROVIDER_ID` name the same string, and a rule that saw only the
    second would be a rule about how many dots an author typed.
    """
    identity = _an_identity()
    modules = {"pkg.leaf": f"ID = {identity!r}\n",
               "pkg.__init__": "from pkg.leaf import ID\n"}
    source = ("from pkg import ID\n"
              "def route(chosen):\n"
              "    return chosen == ID\n")
    assert _probe(source, modules) == [identity]


def test_an_identity_held_as_a_class_constant_is_reached_through_its_class():
    """`ClaudeCodeAdapter.ADAPTER_ID` is a vendor id in an `if` too.

    Two adapter classes in one module spell the same attribute name and mean
    different providers, so the map is keyed by CLASS -- which is what makes
    following it safe rather than a guess.
    """
    identity = _an_identity()
    modules = {"pkg.leaf": f"class Driver:\n    ADAPTER_ID = {identity!r}\n"}
    source = ("from pkg.leaf import Driver\n"
              "def route(chosen):\n"
              "    return chosen == Driver.ADAPTER_ID\n")
    assert _probe(source, modules) == [identity]


def test_a_name_bound_inside_a_function_is_followed_to_the_string_it_holds():
    """One more step is still the same branch."""
    identity = _an_identity()
    modules = {"pkg.leaf": f"ID = {identity!r}\n"}
    source = ("from pkg.leaf import ID\n"
              "def route(chosen):\n"
              "    wanted = ID\n"
              "    return chosen == wanted\n")
    assert _probe(source, modules) == [identity]


def test_an_attribute_on_something_that_is_no_module_or_class_is_not_guessed():
    """The prefix must be a name THIS file bound, or the gate says nothing.

    `self._reviewed.ADAPTER_ID` names an object chosen at runtime, and no
    reader of the text can know which provider it holds. Looking a bare
    attribute name up across every module instead would answer with a provider
    it may not be -- confidently, and sometimes wrongly.
    """
    identity = _an_identity()
    modules = {"pkg.leaf": f"class Driver:\n    ADAPTER_ID = {identity!r}\n"}
    source = ("def route(self, chosen):\n"
              "    return chosen == self._reviewed.ADAPTER_ID\n")
    assert _probe(source, modules) == []


def test_a_container_is_followed_to_every_identity_it_holds():
    """`provider_id in IDS` is the same branch with the name one list away.

    The docstring at the top of this file promises `in` and `not in`, and a
    tuple was how you kept both while never writing a vendor name near either.
    Both spellings of the members are followed -- a quoted id, and a name bound
    to one -- because a rule that closed only the first would be a rule about
    quotation marks with an extra step.
    """
    identity = _an_identity()
    for member in (repr(identity), "ID"):
        modules = {"pkg.leaf": f"ID = {identity!r}\nIDS = ({member},)\n"}
        for verb in ("in", "not in"):
            source = ("from pkg.leaf import IDS\n"
                      "def route(chosen):\n"
                      f"    return chosen {verb} IDS\n")
            assert _probe(source, modules) == [identity], (member, verb)
    # And through the module rather than the name, which is the other spelling.
    modules = {"pkg.leaf": f"IDS = ({identity!r},)\n"}
    through = ("from pkg import leaf\n"
               "def route(chosen):\n"
               "    return chosen in leaf.IDS\n")
    assert _probe(through, modules) == [identity]


def test_a_container_holding_no_identity_is_no_finding_however_large():
    """The filter is the catalog, so an ordinary membership test is silent.

    This codebase runs dozens of `x not in SOME_SET` checks over capabilities,
    outcomes and phases. Following containers must not turn any of them into a
    finding, and what keeps them quiet is that their members are not
    catalogued provider ids rather than any special case for them.
    """
    modules = {"pkg.leaf": "STATES = ('running', 'succeeded', 'failed')\n"}
    source = ("from pkg.leaf import STATES\n"
              "def route(chosen):\n"
              "    return chosen not in STATES\n")
    found = _probe(source, modules)
    # Followed, really -- so this is not passing because the resolver is blind.
    assert found == ["running", "succeeded", "failed"]
    assert not [value for value in found if value in _identities()]


def _menu_trees(identity: str) -> dict[str, str]:
    """A presentation module that declares TWO containers, and a neutral reader.

    `SPECIAL` is the one this exception must not cover: a container a future
    edit could add to the real `harnesses.py`, holding a catalogued id, and
    imported into execution code. It is written here rather than added to the
    shipped file, because the gate has to hold for what that file does not
    contain yet.
    """
    return {PRESENTATION_MODULE: (f"RECOMMENDED = ({identity!r}, 'cursor')\n"
                                  f"SPECIAL = ({identity!r},)\n")}


def _reached(source: str, identity: str) -> list[tuple[str, tuple[str, str]]]:
    """What one synthetic neutral module branches on, with each word's origin."""
    trees = {name: ast.parse(body)
             for name, body in _menu_trees(identity).items()}
    return [(value, origin) for value, _, origin
            in _compared_strings("conductor.command.neutral", ast.parse(source),
                                 trees=trees)
            if value in _identities()]


def test_the_presentation_exception_names_one_symbol_and_not_one_module():
    """`harnesses.RECOMMENDED` is excused. `harnesses.SPECIAL` would not be.

    A module is too coarse to mean this exception. Excusing
    `conductor.harnesses` excuses everything that file ever declares, so a
    container added to it tomorrow and imported into execution code would walk
    through a gate whose docstring says it cannot -- and nothing here would
    have noticed, because today that file declares exactly one such container.
    """
    identity = _an_identity()
    assert len(EXCUSED) == 1, "one exception, and it stays one"
    assert EXCUSED == {(PRESENTATION_MODULE, "RECOMMENDED")}

    menu = ("from conductor.harnesses import RECOMMENDED\n"
            "def offer(chosen):\n"
            "    return chosen not in RECOMMENDED\n")
    assert _reached(menu, identity) == [
        (identity, (PRESENTATION_MODULE, "RECOMMENDED"))]
    assert all(_excused(origin) for _, origin in _reached(menu, identity))

    special = ("from conductor.harnesses import SPECIAL\n"
               "def route(chosen):\n"
               "    return chosen in SPECIAL\n")
    assert _reached(special, identity) == [
        (identity, (PRESENTATION_MODULE, "SPECIAL"))]
    assert not any(_excused(origin) for _, origin in _reached(special, identity))


#: One rebinding per shape a container can be copied through, all of them one
#: line long. The scalar side of the resolver has followed `NAME = OTHER` from
#: the start; a container that did not was the odd one out, not a limit.
_REBINDINGS = (
    ("at module level", "{symbol}\nMENU = {symbol}\n", "MENU"),
    ("inside a function", "{symbol}\n", "menu"),
    ("through a chain of three", "{symbol}\nFIRST = {symbol}\nSECOND = FIRST\n",
     "SECOND"),
)


def _rebound(symbol: str, shape: str, used: str, identity: str
             ) -> list[tuple[str, tuple[str, str]]]:
    """One synthetic module that copies a container and then branches on it."""
    head = f"from conductor.harnesses import {shape.format(symbol=symbol)}"
    body = ("def route(chosen):\n"
            + (f"    {used} = {symbol}\n" if used.islower() else "")
            + f"    return chosen in {used}\n")
    trees = {PRESENTATION_MODULE: ast.parse(
        f"RECOMMENDED = ({identity!r}, 'cursor')\nSPECIAL = ({identity!r},)\n")}
    return [(value, origin) for value, _, origin in _compared_strings(
        "conductor.command.neutral", ast.parse(head + body), trees=trees)
        if value in _identities()]


@pytest.mark.parametrize("name,shape,used", _REBINDINGS,
                         ids=[row[0] for row in _REBINDINGS])
def test_copying_a_container_to_another_name_carries_its_origin_unchanged(
        name, shape, used):
    """`MENU = SPECIAL` is the same branch, one line further away.

    An import alias could not steal the allowance, and a plain assignment must
    not either -- in EITHER direction. `RECOMMENDED` copied to any name stays
    excused, because the rule is about the declaration and not about the name
    a reader chose; `SPECIAL` copied to any name stays a stray, because one
    line is not a laundering step.
    """
    identity = _an_identity()
    kept = _rebound("RECOMMENDED", shape, used, identity)
    assert kept == [(identity, (PRESENTATION_MODULE, "RECOMMENDED"))], name
    assert all(_excused(origin) for _, origin in kept), name

    stray = _rebound("SPECIAL", shape, used, identity)
    assert stray == [(identity, (PRESENTATION_MODULE, "SPECIAL"))], name
    assert not any(_excused(origin) for _, origin in stray), name


#: Each of these declares a container under a name the module ALSO imported.
#: A rule that compared names would read every one of them as the import.
_SHADOWINGS = (
    ("branched on directly", "RECOMMENDED = ({id!r},)\n", "RECOMMENDED"),
    ("copied on to another name", "RECOMMENDED = ({id!r},)\nMENU = RECOMMENDED\n",
     "MENU"),
    ("declared inside a function", "", "RECOMMENDED"),
)


@pytest.mark.parametrize("name,body,used", _SHADOWINGS,
                         ids=[row[0] for row in _SHADOWINGS])
def test_redeclaring_an_imported_name_takes_the_allowance_back(name, body, used):
    """Two declarations spelled the same are still two declarations.

    A module that imports `RECOMMENDED` and then writes its own
    `RECOMMENDED = (...)` holds a LOCAL container -- and the local one is the
    one every later line reads. Deciding which of the two it is by comparing
    names reads the second as the first and hands an execution module the
    presentation menu's allowance, which is the whole exception given away in
    one line. Which branch BUILT the value is what tells them apart.
    """
    identity = _an_identity()
    inner = (f"    RECOMMENDED = ({identity!r},)\n"
             if name == "declared inside a function" else "")
    source = ("from conductor.harnesses import RECOMMENDED\n"
              + body.format(id=identity)
              + "def route(chosen):\n" + inner
              + f"    return chosen in {used}\n")
    trees = {PRESENTATION_MODULE: ast.parse(
        f"RECOMMENDED = ({identity!r}, 'cursor')\n")}
    found = [(value, origin) for value, _, origin in _compared_strings(
        "conductor.command.neutral", ast.parse(source), trees=trees)
        if value in _identities()]
    assert found == [(identity, ("conductor.command.neutral", "RECOMMENDED"))], name
    assert not any(_excused(origin) for _, origin in found), name


def test_an_aliased_scalar_reports_the_symbol_it_was_declared_as():
    """Provenance is the declaration for a scalar too, not the local spelling.

    A sabotage run found nothing standing behind this half. Containers carry
    their own origin and are guarded by that; the scalar side still reads it
    off the import, and binding the LOCAL name instead of the declared one
    passed every test in this file. Nothing in `EXCUSED` is a scalar today, so
    it hid no verdict -- but it is the same relation the last rounds were
    about, and an unguarded relation is how each of them started.
    """
    identity = _an_identity()
    trees = {"pkg.leaf": ast.parse(f"ID = {identity!r}\n")}
    for header, used in (("from pkg.leaf import ID\n", "ID"),
                         ("from pkg.leaf import ID as PINNED\n", "PINNED")):
        source = header + f"def route(chosen):\n    return chosen == {used}\n"
        found = [(value, origin) for value, _, origin in _compared_strings(
            "conductor.command.neutral", ast.parse(source), trees=trees)
            if value in _identities()]
        assert found == [(identity, ("pkg.leaf", "ID"))], used


def test_an_import_nobody_redeclared_keeps_the_allowance_it_arrived_with():
    """The other side of the same coin, so the fix cannot be 'excuse nothing'.

    Taking the allowance back from a redeclaration is only correct if leaving
    it alone is still possible -- otherwise the exception would have been
    deleted rather than made exact, and `conduct init` would read as a stray.
    """
    identity = _an_identity()
    trees = {PRESENTATION_MODULE: ast.parse(
        f"RECOMMENDED = ({identity!r}, 'cursor')\n")}
    for body, used in (("", "RECOMMENDED"), ("MENU = RECOMMENDED\n", "MENU")):
        source = ("from conductor.harnesses import RECOMMENDED\n" + body
                  + "def route(chosen):\n"
                  + f"    return chosen in {used}\n")
        found = [(value, origin) for value, _, origin in _compared_strings(
            "conductor.command.neutral", ast.parse(source), trees=trees)
            if value in _identities()]
        assert found == [(identity, (PRESENTATION_MODULE, "RECOMMENDED"))], used
        assert all(_excused(origin) for _, origin in found), used


def test_a_container_a_module_declared_itself_is_followed_when_it_is_copied():
    """No import needs to be involved for a rebinding to hide a container.

    The narrowest version of the same hole: declare the tuple in place, copy it
    once, branch on the copy. Its origin is this module's own declaration, so
    it is a stray -- and it is reported under the name it was DECLARED as, not
    the one it was branched on.
    """
    identity = _an_identity()
    source = (f"OWN = ({identity!r},)\n"
              "MENU = OWN\n"
              "def route(chosen):\n"
              "    return chosen in MENU\n")
    found = [(value, origin) for value, _, origin in _compared_strings(
        "conductor.command.neutral", ast.parse(source), trees={})
        if value in _identities()]
    assert found == [(identity, ("conductor.command.neutral", "OWN"))]
    assert not any(_excused(origin) for _, origin in found)


def test_renaming_a_symbol_on_the_way_in_moves_no_allowance_either_way():
    """The pair is the ORIGINAL declaration, so an alias launders nothing.

    Both directions matter and only one of them is obvious. `RECOMMENDED as
    MENU` must stay excused, or the rule would be about spelling. And `SPECIAL
    as RECOMMENDED` must stay a stray, or the allowance could be claimed by
    anything willing to type the right local name.
    """
    identity = _an_identity()
    kept = ("from conductor.harnesses import RECOMMENDED as MENU\n"
            "def offer(chosen):\n"
            "    return chosen not in MENU\n")
    assert _reached(kept, identity) == [
        (identity, (PRESENTATION_MODULE, "RECOMMENDED"))]

    stolen = ("from conductor.harnesses import SPECIAL as RECOMMENDED\n"
              "def route(chosen):\n"
              "    return chosen in RECOMMENDED\n")
    assert _reached(stolen, identity) == [
        (identity, (PRESENTATION_MODULE, "SPECIAL"))]
    assert not any(_excused(origin) for _, origin in _reached(stolen, identity))


def test_an_allowance_survives_a_package_re_export_but_does_not_spread():
    """Forwarding carries the original pair, and carries nothing else with it."""
    identity = _an_identity()
    trees = {name: ast.parse(body)
             for name, body in _menu_trees(identity).items()}
    trees["pkg.__init__"] = ast.parse(
        "from conductor.harnesses import RECOMMENDED, SPECIAL\n")
    for symbol, excused in (("RECOMMENDED", True), ("SPECIAL", False)):
        source = (f"from pkg import {symbol}\n"
                  "def route(chosen):\n"
                  f"    return chosen in {symbol}\n")
        found = [(value, origin) for value, _, origin in _compared_strings(
            "conductor.command.neutral", ast.parse(source), trees=trees)
            if value in _identities()]
        assert found == [(identity, (PRESENTATION_MODULE, symbol))], symbol
        assert all(_excused(origin) for _, origin in found) is excused, symbol


def test_a_literal_inside_the_presentation_module_is_still_a_stray():
    """An exception about a symbol cannot cover a value that came through none.

    `harnesses.py` may hold every vendor id as DATA -- that is its whole job --
    and it must still never branch on one. A literal written there carries no
    symbol, so it arrives with an empty origin and is excused by nothing.
    """
    identity = _an_identity()
    source = ("def offer(chosen):\n"
              f"    return chosen == {identity!r}\n")
    found = [(value, origin) for value, _, origin in _compared_strings(
        PRESENTATION_MODULE, ast.parse(source), trees=_trees())
        if value in _identities()]
    assert found == [(identity, ("", ""))]
    assert not any(_excused(origin) for _, origin in found)


def test_the_presentation_exception_is_reached_and_is_not_dead_code():
    """The real tree really uses it, and the real menu really holds an id.

    Both halves refuse to let this exception exist quietly: if the presentation
    module stops declaring a menu of catalogued ids, or no module ever branches
    on one, the exception excuses nothing and the test says to delete it.
    """
    identity = _an_identity()
    menu = _own_containers(_trees()[PRESENTATION_MODULE],
                           PRESENTATION_MODULE).get("RECOMMENDED")
    assert menu is not None and set(menu.held) & set(_identities()), (
        "the presentation menu holds no catalogued id, so this exception "
        "guards nothing -- remove it")
    reached = {(module, value)
               for module, tree in _trees().items()
               for value, _, origin in _compared_strings(module, tree)
               if value in _identities() and _excused(origin)}
    assert reached, ("no module branches on the presentation menu, so this "
                     "exception excuses nothing -- remove it")
    assert {module for module, _ in reached} != {PRESENTATION_MODULE}

    # And a container of the same shape somewhere else is not exempt.
    elsewhere = {"pkg.leaf": f"OFFERED = ({identity!r}, 'cursor')\n"}
    source = ("from pkg.leaf import OFFERED\n"
              "def route(chosen):\n"
              "    return chosen not in OFFERED\n")
    found = _compared_strings("conductor.command.neutral", ast.parse(source),
                              trees={name: ast.parse(body)
                                     for name, body in elsewhere.items()})
    assert [(value, origin) for value, _, origin in found
            if value in _identities()] == [(identity, ("pkg.leaf", "OFFERED"))]


def test_the_catalog_is_the_only_place_a_provider_is_declared():
    """Every catalogued provider names a module, and it is a real one."""
    identities = _identities()
    assert identities, "the provider catalog is empty"
    for provider_id, module in identities.items():
        assert module.startswith("conductor.command.adapters."), (
            f"{provider_id} is served from {module}, outside the adapters package")
        path = ROOT / "src" / Path(*module.split(".")).with_suffix(".py")
        assert path.is_file(), f"{provider_id} names a module that is not a file"


def test_no_module_branches_on_a_provider_identity_but_that_providers_own():
    """The gate. One comparison out of place fails it, and names where."""
    identities = _identities()
    strays: list[str] = []
    for module, tree in sorted(_trees().items()):
        path = SOURCE.parent / Path(*module.split(".")).with_suffix(".py")
        for value, line, origin in _compared_strings(module, tree):
            allowed = identities.get(value)
            if allowed is None or allowed == module:
                continue
            if _excused(origin):
                continue
            strays.append(
                f"{path.relative_to(ROOT)}:{line} branches on {value!r}, which "
                f"belongs to {allowed}")
    assert not strays, "provider identity leaked out of its own module:\n" + \
        "\n".join(strays)


def test_the_catalog_module_itself_declares_rather_than_branches():
    """`providers.py` may KEY on an identity; it may not decide with one.

    It is the one file that names every provider, because it is the catalog.
    That is data. The moment it grows `if provider_id == ...` it has become a
    dispatcher, and adding a provider stops being one entry.
    """
    path = SOURCE / "command" / "providers.py"
    module = _module_name(path)
    tree = _trees()[module]
    identities = set(_identities())
    branched = [f"line {line}: {value!r}"
                for value, line, _ in _compared_strings(module, tree)
                if value in identities]
    assert not branched, (
        "the catalog decides on an identity instead of declaring it:\n"
        + "\n".join(branched))
    # And the declaration really is there, so the check above is not passing on
    # a file that stopped naming providers at all. What is asserted is the
    # SHAPE -- one literal mapping entry per catalogued provider -- and not that
    # each key is a string literal: `kimi-code` is keyed by the constant its own
    # module exports, which is a better declaration than a second spelling.
    catalog = next(
        (node.value for node in ast.walk(tree)
         if isinstance(node, ast.Assign)
         and any(isinstance(target, ast.Name) and target.id == "PROVIDER_CATALOG"
                 for target in node.targets)), None)
    assert catalog is not None, "providers.py declares no PROVIDER_CATALOG"
    mapping = next((inner for inner in ast.walk(catalog)
                    if isinstance(inner, ast.Dict)), None)
    assert mapping is not None, "the catalog is not a literal mapping"
    assert len(mapping.keys) == len(identities), (
        f"the catalog literal carries {len(mapping.keys)} entries for "
        f"{len(identities)} catalogued providers")


def test_presentation_metadata_carries_vendor_rows_without_deciding_on_them():
    """The badge rows are data for every listed product, and branch on none."""
    module = _module_name(PRESENTATION)
    identities = set(_identities())
    branched = [f"line {line}: {value!r}"
                for value, line, _ in _compared_strings(module, _trees()[module])
                if value in identities]
    assert not branched, (
        "presentation metadata branches on a provider identity:\n"
        + "\n".join(branched))


@pytest.mark.parametrize("provider_id", sorted(_identities()))
def test_each_provider_may_decide_within_its_own_module(provider_id: str):
    """The permission is real, not vacuous: the module exists and is readable.

    A gate that allowed a module nobody could name would be a gate with a hole
    in it shaped like a typo.
    """
    module = _identities()[provider_id]
    path = ROOT / "src" / Path(*module.split(".")).with_suffix(".py")
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
