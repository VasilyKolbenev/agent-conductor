"""Reading one thing out of Python source: what a module BRANCHES on.

Split out of `test_provider_identity_gate.py` when that file crossed the line
cap, and split along the seam that was already there: this module answers what
a piece of source says, and knows nothing about providers, catalogues or which
answers are allowed. The rule reads these answers and judges them.

Nothing here imports `conductor`. It parses text, resolves the names that text
binds, and reports every string a comparison decides on -- with the
`(module, symbol)` each one was DECLARED under, so the rule next door can be
about a named symbol rather than about a file.
"""
from __future__ import annotations

import ast
from collections.abc import Iterator, Mapping
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "conductor"


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


@lru_cache(maxsize=None)
def _assignments(tree: ast.AST) -> tuple[tuple[int, list[ast.expr], ast.expr], ...]:
    """Every assignment outside a class body, in source order, kept per tree.

    The strings and the containers each read this, and a module's own bindings
    are re-settled once per importer -- so without keeping the walk, resolving
    one tree of fifty modules walked it tens of thousands of times.
    """
    rows = [row for row in map(_bindings, _outside_classes(tree)) if row]
    return tuple(sorted(rows, key=lambda row: row[0]))


@lru_cache(maxsize=None)
def _import_froms(tree: ast.AST) -> tuple[ast.ImportFrom, ...]:
    """Every `from ... import` a module writes, in the order it writes them."""
    return tuple(node for node in ast.walk(tree)
                 if isinstance(node, ast.ImportFrom))


def _declared_strings(tree: ast.AST,
                      seed: Mapping[str, str] | None = None) -> dict[str, str]:
    """Every `NAME = "literal"` a module binds outside a class, by name.

    Strings only, because a CONTAINER is a different shape and is followed
    separately by `_declared_containers` -- which reports every string it holds
    rather than one. Keeping the two apart is what lets a container carry its
    own provenance, and therefore what lets the presentation exception be about
    where a symbol came from instead of about which file is reading it.

    Function bodies are included, because `kimi = KIMI_PROVIDER_ID` followed by
    a comparison on `kimi` is the same branch with one more step in it. `seed`
    is what this module imported, so that step may cross the import -- and a
    name the module declares ITSELF is written over the seed, never under it.
    """
    declared: dict[str, str] = dict(seed or {})
    for _, targets, value in _assignments(tree):
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


def _container_of(value: ast.expr,
                  names: Mapping[str, str]) -> tuple[str, ...] | None:
    """The strings a literal CONTAINER holds, or nothing if it is not one.

    A tuple, list or set of constants, and the same wrapped in `frozenset(...)`,
    `set(...)`, `tuple(...)` or `list(...)` -- the spellings this codebase
    actually uses. A member may be a NAME as well as a literal, because
    `(_DEFAULT_PRIMARY,)` holds a vendor id exactly as `("claude-code",)` does,
    and the whole point of following a container is that neither spelling is a
    way out of the rule. Members that are neither are skipped rather than
    refused: a mixed container still reports the strings it does hold.
    """
    if (isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
            and value.func.id in {"frozenset", "set", "tuple", "list"}
            and value.args):
        return _container_of(value.args[0], names)
    if not isinstance(value, (ast.Tuple, ast.List, ast.Set)) or not value.elts:
        return None
    held = [item.value if isinstance(item, ast.Constant) else names[item.id]
            for item in value.elts
            if (isinstance(item, ast.Constant) and isinstance(item.value, str))
            or (isinstance(item, ast.Name) and item.id in names)]
    return tuple(held) or None


class Container(NamedTuple):
    """A container of strings, and the `(module, symbol)` it was DECLARED under.

    The origin travels WITH the value rather than being reconstructed from a
    name afterwards, and that is the whole of what makes shadowing safe. A name
    is not evidence: a module that imports `RECOMMENDED` and then writes its
    own `RECOMMENDED = (...)` has two different declarations spelled the same,
    and any rule that compared names would read the second as the first and
    hand a local container someone else's allowance.

    So a declaration written HERE takes this module's own pair, a copy takes
    whatever the value it copied is carrying, and an untouched import keeps the
    pair it arrived with -- three cases told apart by which branch built the
    value, never by what it is called.
    """

    held: tuple[str, ...]
    origin: tuple[str, str]


def _declared_containers(tree: ast.AST, names: Mapping[str, str], module: str,
                         seed: Mapping[str, Container] | None = None
                         ) -> dict[str, Container]:
    """Every container a module binds outside a class, by name.

    Two ways to bind one, and both are followed: a literal written in place,
    and a REBINDING of a container already in scope. The second walks chains of
    any length and reaches into function bodies, because the rows are read in
    source order over the same walk the strings use -- and because
    `menu = SPECIAL` two lines into a function is the same branch as the import
    it came from, with one more step in it.

    `seed` is what this module imported, so a rebinding may cross the import --
    and so may a SHADOWING, which is the case a name cannot describe. Writing
    `RECOMMENDED = (...)` in a module that imported `RECOMMENDED` replaces the
    imported value with a local one under the same spelling. Which branch built
    the value is the only thing that tells those apart, so the origin is decided
    here, where that is known, and carried on the value from then on.
    """
    found: dict[str, Container] = dict(seed or {})
    for _, targets, value in _assignments(tree):
        if (held := _container_of(value, names)) is not None:
            copied = None                  # declared HERE, whatever it is called
        elif isinstance(value, ast.Name) and value.id in found:
            copied = found[value.id]       # a copy, carrying what it copied
        else:
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                found[target.id] = (Container(held, (module, target.id))
                                    if copied is None else copied)
    return found


@lru_cache(maxsize=None)
def _own_containers(tree: ast.AST, module: str) -> Mapping[str, Container]:
    """`_declared_containers` against the module's own strings, kept per tree."""
    return MappingProxyType(_declared_containers(tree, _own_strings(tree), module))


class Offer(NamedTuple):
    """What one module offers under a name, and where each name came FROM.

    `origins` is what makes the presentation exception an exception about
    PROVENANCE rather than about which file happens to be reading. Each entry
    is the `(module, symbol)` a name was declared under, carried unchanged
    through every alias and re-export -- so neither forwarding nor a rename on
    the way in turns one symbol's allowance into another's, and a module that
    redeclares an imported name under that same name answers for its own.
    """

    strings: Mapping[str, str]
    classes: Mapping[str, Mapping[str, str]]
    containers: Mapping[str, Container]
    origins: Mapping[str, tuple[str, str]]


EMPTY_OFFER = Offer({}, {}, {}, {})


def _bind_imported(alias: ast.alias, target: str, source: Offer,
                   held: Offer) -> None:
    """Bind, under the name one alias binds locally, what `target` offers.

    `from m import C as D` binds the AS name, which is the whole trick a bypass
    uses. What a name MEANS is copied from the module that offered it; where the
    value CAME FROM is not, so a name reached through a re-export keeps the
    `(module, symbol)` of the declaration it was copied from, however many names
    and imports ago that was.

    `held` is the offer being built: its four tables are written into, which is
    why the same block reads a file's own imports and a package's re-exports.
    """
    local = alias.asname or alias.name
    for into, offered in ((held.strings, source.strings),
                          (held.classes, source.classes),
                          (held.containers, source.containers)):
        if alias.name in offered:
            into[local] = offered[alias.name]
            held.origins[local] = source.origins.get(
                alias.name, (target, alias.name))


def _exported_offer(module: str, trees: Mapping[str, ast.Module],
                    seen: frozenset[str] = frozenset()) -> Offer:
    """Everything a module offers under a name -- its own, and its re-exports.

    A package `__init__` that lists a constant in a `from . import` line hands
    it on under the PACKAGE's name, so `from .adapters import KIMI_PROVIDER_ID`
    is the same branch as importing it from the file that declares it.
    Following the re-export is what stops this being a rule about which
    spelling an author reached for. `seen` ends a cycle in the source text.
    """
    file_name = _file_of(module, trees)
    if file_name is None or module in seen:
        return EMPTY_OFFER
    tree = trees[file_name]
    strings: dict[str, str] = {}
    classes: dict[str, dict[str, str]] = {}
    containers: dict[str, Container] = {}
    origins: dict[str, tuple[str, str]] = {}
    held = Offer(strings, classes, containers, origins)
    for node in _import_froms(tree):
        target = _absolute(node, file_name)
        source = _exported_offer(target, trees, seen | {module})
        for alias in node.names:
            _bind_imported(alias, target, source, held)
    return _settled(module, tree, strings, classes, containers, origins)


@lru_cache(maxsize=None)
def _shipped_offer(module: str) -> Offer:
    """What one SHIPPED module offers, resolved once for the whole session."""
    return _exported_offer(module, _trees())


def _offered(module: str, trees: Mapping[str, ast.Module]) -> Offer:
    """What a module offers, by whatever route it offers it.

    Kept for the shipped tree, because every module in it is imported many
    times over and re-resolving each one per import statement is most of what
    this gate would otherwise spend its time doing. A synthetic probe map is
    small and short-lived, so it is simply computed.
    """
    return _shipped_offer(module) if trees is _trees() else _exported_offer(
        module, trees)


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


def _settled(module: str, tree: ast.AST, strings: dict[str, str],
             classes: dict[str, dict[str, str]],
             containers: dict[str, Container],
             origins: dict[str, tuple[str, str]]) -> Offer:
    """Lay a module's OWN bindings over what it imported, and settle provenance.

    Own declarations win, so a module that re-spells a name it imported answers
    for its own. What does NOT change is where a value came from: a container
    rebound to a new name keeps the `(module, symbol)` of the declaration it was
    copied from, however many names and imports ago that was.
    """
    own_strings = _declared_strings(tree, strings)
    own_containers = _declared_containers(tree, own_strings, module, containers)
    own_classes = _class_strings(tree)
    for name in _own_strings(tree):
        origins[name] = (module, name)
    for name in own_classes:
        origins[name] = (module, name)
    # Containers answer for themselves. Each one already knows whether it was
    # written here, copied from something, or imported untouched -- so nothing
    # is inferred from its name, which is exactly what a shadowing defeats.
    for name, container in own_containers.items():
        origins[name] = container.origin
    strings.update(own_strings)
    containers.update(own_containers)
    classes.update(own_classes)
    return Offer(strings, classes, containers, origins)


def _local_names(module: str, tree: ast.AST,
                 trees: Mapping[str, ast.Module]) -> tuple[Offer, dict[str, str]]:
    """What ONE file's names mean, and which modules its aliases point at.

    An import binds a name to something another file declared, so a comparison
    can spell an identity without spelling it. `import X as Y` and `from m
    import C as D` bind the AS name, which is the whole trick a bypass uses.
    A module's OWN declaration wins over anything it imported under that name.
    """
    strings: dict[str, str] = {}
    classes: dict[str, dict[str, str]] = {}
    containers: dict[str, Container] = {}
    origins: dict[str, tuple[str, str]] = {}
    held = Offer(strings, classes, containers, origins)
    modules: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.ImportFrom):
            target = _absolute(node, module)
            source = _offered(target, trees)
            for alias in node.names:
                _bind_imported(alias, target, source, held)
                if _file_of(f"{target}.{alias.name}", trees) is not None:
                    modules[alias.asname or alias.name] = f"{target}.{alias.name}"
    return _settled(module, tree, strings, classes, containers, origins), modules


def _referenced(node: ast.AST, local: Offer, modules: Mapping[str, str],
                trees: Mapping[str, ast.Module]
                ) -> list[tuple[str, int, tuple[str, str]]]:
    """Every string one operand reaches by NAME, with where that name came from.

    An `ast.Attribute` is only followed when its PREFIX is a name this file
    bound to a module or to a class. Looking a bare attribute name up across
    the whole tree instead would make `self._reviewed.ADAPTER_ID` -- a runtime
    fact no reader of the text can know -- resolve to a provider it may not be.
    """
    out: list[tuple[str, int, tuple[str, str]]] = []
    for inner in ast.walk(node):
        if isinstance(inner, ast.Name):
            reached = local
            key, origin = inner.id, local.origins.get(inner.id, ("", ""))
        elif isinstance(inner, ast.Attribute):
            prefix, _, key = _dotted(inner).rpartition(".")
            target = modules.get(prefix, "")
            if target:
                reached = _offered(target, trees)
                origin = reached.origins.get(key, (target, key))
            else:
                held = local.classes.get(prefix, {})
                reached = Offer(held, {}, {}, {})
                origin = (local.origins.get(prefix, ("", ""))[0], key)
        else:
            continue
        carried = reached.containers.get(key)
        for value in (*((reached.strings[key],) if key in reached.strings else ()),
                      *(carried.held if carried is not None else ())):
            out.append((value, inner.lineno, origin))
    return out


def _compared_strings(module: str, tree: ast.AST, *,
                      trees: Mapping[str, ast.Module] | None = None
                      ) -> list[tuple[str, int, tuple[str, str]]]:
    """Every string this module BRANCHES on, quoted or reached through a name.

    A comparison and a `match` case are the two ways a value decides control
    flow on identity. A string used as a dict key, an argument, or a piece of
    declarative data is not one of them and is not reported.

    A name is followed to the string it was bound to, because `provider_id ==
    KIMI_PROVIDER_ID` and `provider_id == "kimi-code"` are the same branch and
    an import is not a way out of the rule -- and a CONTAINER is followed to
    every string it holds, because `provider_id in IDS` is the same branch
    again with the vendor name one list further away. A name this module never
    bound to a literal stays silent: `entry.provider_id` is a runtime fact no
    reader of the text can know, and the gate says nothing rather than guessing.

    Each finding carries the `(module, symbol)` it was DECLARED under, or
    `("", "")` for a literal written in place, which is what lets the one
    exception be about a named symbol rather than about a whole file.

    What it still does not reach, written down rather than discovered later:
    a name fetched with `getattr(module, "NAME")`, and the KEYS of a mapping
    pattern -- `case {mod.ID: _}` puts a bare expression in
    `ast.MatchMapping.keys`, never wrapped in `MatchValue`, and that gap is as
    old as the literal half of this gate.
    """
    trees = _trees() if trees is None else trees
    local, modules = _local_names(module, tree, trees)
    found: list[tuple[str, int, tuple[str, str]]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            operands = [node.left, *node.comparators]
        elif isinstance(node, ast.MatchValue):
            operands = [node.value]
        else:
            continue
        for side in operands:
            found.extend(_constants(side))
            found.extend(_referenced(side, local, modules, trees))
    return found


def _constants(node: ast.AST) -> list[tuple[str, int, tuple[str, str]]]:
    """A string written in place, which came from no symbol at all."""
    out: list[tuple[str, int, tuple[str, str]]] = []
    for inner in ast.walk(node):
        if isinstance(inner, ast.Constant) and isinstance(inner.value, str):
            out.append((inner.value, inner.lineno, ("", "")))
    return out
