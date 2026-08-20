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
from collections.abc import Iterator, Mapping
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType

import pytest

from conductor.command.providers import PROVIDER_CATALOG

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "conductor"
#: `harnesses.py` is presentation metadata -- the rows a Cockpit draws badges
#: from -- and not a provider module of execution. It carries vendor ids as
#: DATA for every product the December Command lists, which is its whole job,
#: and it must never branch on one either.
PRESENTATION = SOURCE / "harnesses.py"


def _identities() -> dict[str, str]:
    """Every catalogued provider id, and the module allowed to compare it."""
    return {
        entry.provider_id: entry.adapter_class.__module__
        for entry in PROVIDER_CATALOG.values()
    }


def _module_name(path: Path) -> str:
    return ".".join(path.relative_to(SOURCE.parent).with_suffix("").parts)


@lru_cache(maxsize=1)
def _trees() -> dict[str, ast.Module]:
    """Every source module under `src/conductor`, parsed once, keyed by name.

    Shared, because resolving one file's imports means reading the file it
    imported FROM -- without this the gate would re-parse the tree once per
    import statement in it.
    """
    return {_module_name(path): ast.parse(
        path.read_text(encoding="utf-8"), filename=str(path))
        for path in sorted(SOURCE.rglob("*.py"))}


def _outside_classes(node: ast.AST) -> Iterator[ast.AST]:
    """Every node below this one, never descending into a class body.

    A class body is walked separately and keyed by its class, because two
    classes in one module spell `ADAPTER_ID` and each means a different
    provider; merging them into one flat map would be lying about which.
    """
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.ClassDef):
            continue
        yield child
        yield from _outside_classes(child)


def _bindings(node: ast.AST) -> tuple[int, list[ast.expr], ast.expr] | None:
    """One assignment as (line, targets, value), or nothing if it is not one."""
    if isinstance(node, ast.Assign):
        return node.lineno, list(node.targets), node.value
    if isinstance(node, ast.AnnAssign) and node.value is not None:
        return node.lineno, [node.target], node.value
    return None


def _declared_strings(tree: ast.AST,
                      seed: Mapping[str, str] | None = None) -> dict[str, str]:
    """Every `NAME = "literal"` a module binds outside a class, by name.

    Strings only, and that limit is the point. A name bound to a TUPLE or a set
    is a CONTAINER, and a module asking whether an id is in one has decided
    nothing about any single provider -- `harnesses.RECOMMENDED` is an
    onboarding list, and `templates._SHIPPED` is one document. Widening this to
    containers would make every `x not in SOME_SET` in the tree a finding.

    Function bodies are included, because `kimi = KIMI_PROVIDER_ID` followed by
    a comparison on `kimi` is the same branch with one more step in it. `seed`
    is what this module imported, so that step may cross the import -- and a
    name the module declares ITSELF is written over the seed, never under it.
    """
    declared: dict[str, str] = dict(seed or {})
    rows = [row for row in map(_bindings, _outside_classes(tree)) if row]
    for _, targets, value in sorted(rows, key=lambda row: row[0]):
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            text = value.value
        elif isinstance(value, ast.Name) and value.id in declared:
            text = declared[value.id]      # a re-spelling, followed one hop
        else:
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                declared[target.id] = text
    return declared


@lru_cache(maxsize=None)
def _own_strings(tree: ast.AST) -> Mapping[str, str]:
    """`_declared_strings` with nothing seeded, kept per parsed module.

    Resolving one file's imports reads the file it imported FROM, and the same
    handful of modules are imported all over this tree; without this the gate
    re-walks each of them once per import statement pointing at it.
    """
    return MappingProxyType(_declared_strings(tree))


@lru_cache(maxsize=None)
def _class_strings(tree: ast.AST) -> dict[str, dict[str, str]]:
    """Every `NAME = "literal"` a CLASS body binds, keyed by the class name.

    `ClaudeCodeAdapter.ADAPTER_ID` is a vendor id in an `if` exactly as much as
    the quoted string is, and keying by class is what tells it apart from the
    identical attribute name on the adapter beside it.
    """
    out: dict[str, dict[str, str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        found = {
            target.id: value.value
            for row in node.body
            if (binding := _bindings(row)) is not None
            for _, targets, value in [binding]
            if isinstance(value, ast.Constant) and isinstance(value.value, str)
            for target in targets if isinstance(target, ast.Name)
        }
        if found:
            out[node.name] = found
    return out


def _absolute(node: ast.ImportFrom, module: str) -> str:
    """The module a `from ... import` names, with a relative one made absolute."""
    if not node.level:
        return node.module or ""
    parts = module.split(".")[:-1]
    parts = parts[:len(parts) - node.level + 1]
    return ".".join([*parts, node.module]) if node.module else ".".join(parts)


def _file_of(module: str, trees: Mapping[str, ast.Module]) -> str | None:
    """The tree key for a module, whether it is a file or a package."""
    for candidate in (module, f"{module}.__init__"):
        if candidate in trees:
            return candidate
    return None


def _exported(module: str, trees: Mapping[str, ast.Module],
              seen: frozenset[str] = frozenset()) -> dict[str, str]:
    """Every string a module offers under a name -- its own and its re-exports.

    A package `__init__` that lists a constant in a `from . import` line hands
    it on under the PACKAGE's name, so `from .adapters import KIMI_PROVIDER_ID`
    is the same branch as importing it from the file that declares it.
    Following the re-export is what stops this being a rule about which
    spelling an author reached for. `seen` ends a cycle in the source text.
    """
    file_name = _file_of(module, trees)
    if file_name is None or module in seen:
        return {}
    tree = trees[file_name]
    names = dict(_own_strings(tree))
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        source = _exported(_absolute(node, file_name), trees, seen | {module})
        for alias in node.names:
            if alias.name in source:
                names.setdefault(alias.asname or alias.name, source[alias.name])
    return names


def _exported_classes(module: str, trees: Mapping[str, ast.Module],
                      seen: frozenset[str] = frozenset()) -> dict[str, dict[str, str]]:
    """Class constants a module offers, its own and the classes it re-exports."""
    file_name = _file_of(module, trees)
    if file_name is None or module in seen:
        return {}
    tree = trees[file_name]
    found = dict(_class_strings(tree))
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        source = _exported_classes(_absolute(node, file_name), trees, seen | {module})
        for alias in node.names:
            if alias.name in source:
                found.setdefault(alias.asname or alias.name, source[alias.name])
    return found


@lru_cache(maxsize=None)
def _shipped_offer(module: str) -> tuple[Mapping[str, str],
                                         Mapping[str, Mapping[str, str]]]:
    """What one SHIPPED module offers, resolved once for the whole session."""
    trees = _trees()
    return (MappingProxyType(_exported(module, trees)),
            MappingProxyType(_exported_classes(module, trees)))


def _offered(module: str, trees: Mapping[str, ast.Module]
             ) -> tuple[Mapping[str, str], Mapping[str, Mapping[str, str]]]:
    """The strings and class constants a module offers, by whatever route.

    Kept for the shipped tree, because every module in it is imported many
    times over and re-resolving each one per import statement is most of what
    this gate would otherwise spend its time doing. A synthetic probe map is
    small and short-lived, so it is simply computed.
    """
    if trees is _trees():
        return _shipped_offer(module)
    return _exported(module, trees), _exported_classes(module, trees)


def _dotted(node: ast.AST) -> str:
    """`a.b.C` as one dotted string; empty when anything else is in the chain."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return ""
    parts.append(node.id)
    return ".".join(reversed(parts))


def _local_names(module: str, tree: ast.AST,
                 trees: Mapping[str, ast.Module]) -> tuple[dict[str, str],
                                                           dict[str, str],
                                                           dict[str, dict[str, str]]]:
    """What ONE file's names mean: strings, module aliases, and class aliases.

    An import binds a name to something another file declared, so a comparison
    can spell an identity without spelling it. `import X as Y` and `from m
    import C as D` bind the AS name, which is the whole trick a bypass uses.
    A module's OWN declaration wins over anything it imported under that name.
    """
    names: dict[str, str] = {}
    modules: dict[str, str] = {}
    classes: dict[str, dict[str, str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.ImportFrom):
            target = _absolute(node, module)
            offered, classed = _offered(target, trees)
            for alias in node.names:
                local = alias.asname or alias.name
                if alias.name in offered:
                    names[local] = offered[alias.name]
                if alias.name in classed:
                    classes[local] = classed[alias.name]
                if _file_of(f"{target}.{alias.name}", trees) is not None:
                    modules[local] = f"{target}.{alias.name}"
    classes.update(_class_strings(tree))
    return _declared_strings(tree, names), modules, classes


def _referenced(node: ast.AST, names: Mapping[str, str], modules: Mapping[str, str],
                classes: Mapping[str, Mapping[str, str]],
                trees: Mapping[str, ast.Module]) -> list[tuple[str, int]]:
    """Every string one operand reaches by NAME, through a local, module or class.

    An `ast.Attribute` is only followed when its PREFIX is a name this file
    bound to a module or to a class. Looking a bare attribute name up across
    the whole tree instead would make `self._reviewed.ADAPTER_ID` -- a runtime
    fact no reader of the text can know -- resolve to a provider it may not be.
    """
    out: list[tuple[str, int]] = []
    for inner in ast.walk(node):
        if isinstance(inner, ast.Name):
            value = names.get(inner.id, "")
        elif isinstance(inner, ast.Attribute):
            prefix, _, attr = _dotted(inner).rpartition(".")
            target = modules.get(prefix, "")
            value = (_offered(target, trees)[0].get(attr, "") if target
                     else classes.get(prefix, {}).get(attr, ""))
        else:
            continue
        if value:
            out.append((value, inner.lineno))
    return out


def _compared_strings(module: str, tree: ast.AST, *,
                      trees: Mapping[str, ast.Module] | None = None
                      ) -> list[tuple[str, int]]:
    """Every string this module BRANCHES on, quoted or reached through a name.

    A comparison and a `match` case are the two ways a value decides control
    flow on identity. A string used as a dict key, an argument, or a piece of
    declarative data is not one of them and is not reported.

    A name is followed to the string it was bound to, because `provider_id ==
    KIMI_PROVIDER_ID` and `provider_id == "kimi-code"` are the same branch and
    an import is not a way out of the rule. A name this module never bound to a
    literal stays silent: `entry.provider_id` is a runtime fact no reader of
    the text can know, and the gate says nothing rather than guessing.

    What it still does not reach, written down rather than discovered later:
    a name fetched with `getattr(module, "NAME")`, and the KEYS of a mapping
    pattern -- `case {mod.ID: _}` puts a bare expression in
    `ast.MatchMapping.keys`, never wrapped in `MatchValue`, and that gap is as
    old as the literal half of this gate.
    """
    trees = _trees() if trees is None else trees
    names, modules, classes = _local_names(module, tree, trees)
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            operands = [node.left, *node.comparators]
        elif isinstance(node, ast.MatchValue):
            operands = [node.value]
        else:
            continue
        for side in operands:
            found.extend(_constants(side))
            found.extend(_referenced(side, names, modules, classes, trees))
    return found


def _constants(node: ast.AST) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for inner in ast.walk(node):
        if isinstance(inner, ast.Constant) and isinstance(inner.value, str):
            out.append((inner.value, inner.lineno))
    return out


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
    return [value for value, _ in _compared_strings(
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


def test_a_name_bound_to_a_container_of_ids_is_no_branch_on_any_one_of_them():
    """A menu is not a decision about a product.

    An onboarding list holds ids and deciding whether one is IN it decides
    nothing about any of them. This is the limit that keeps the rule narrow:
    resolving containers would make every `x not in SOME_SET` in this codebase
    a finding, and there are dozens.
    """
    identity = _an_identity()
    modules = {"pkg.leaf": f"OFFERED = ({identity!r}, 'cursor')\n"}
    source = ("from pkg.leaf import OFFERED\n"
              "def route(chosen):\n"
              "    return chosen not in OFFERED\n")
    assert _probe(source, modules) == []


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
        for value, line in _compared_strings(module, tree):
            allowed = identities.get(value)
            if allowed is None or allowed == module:
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
                for value, line in _compared_strings(module, tree)
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
                for value, line in _compared_strings(module, _trees()[module])
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
