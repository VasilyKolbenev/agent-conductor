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


def _compared_strings(tree: ast.AST) -> list[tuple[str, int]]:
    """Every string constant this module BRANCHES on, with its line.

    A comparison and a `match` case are the two ways a value decides control
    flow on identity. A string used as a dict key, an argument, or a piece of
    declarative data is not one of them and is not reported.
    """
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            for side in [node.left, *node.comparators]:
                found.extend(_constants(side))
        elif isinstance(node, ast.MatchValue):
            found.extend(_constants(node.value))
    return found


def _constants(node: ast.AST) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for inner in ast.walk(node):
        if isinstance(inner, ast.Constant) and isinstance(inner.value, str):
            out.append((inner.value, inner.lineno))
    return out


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
    for path in sorted(SOURCE.rglob("*.py")):
        module = _module_name(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for value, line in _compared_strings(tree):
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
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    identities = set(_identities())
    branched = [f"line {line}: {value!r}"
                for value, line in _compared_strings(tree) if value in identities]
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
    tree = ast.parse(PRESENTATION.read_text(encoding="utf-8"),
                     filename=str(PRESENTATION))
    identities = set(_identities())
    branched = [f"line {line}: {value!r}"
                for value, line in _compared_strings(tree) if value in identities]
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
