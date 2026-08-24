"""The adapter package's import graph is acyclic, and its public names survive.

Two properties that only a split can break, and this slice split twice: the
workspace door became provider-neutral, and the headless transport shed its
declarative half into ``harness_profile`` when it crossed the 800-line cap.

**Acyclic.** A cycle inside a package is not always an ImportError -- Python
tolerates one whenever the partially-initialised module happens to already carry
what the importer wants, and breaks later when an edit changes the order. So the
graph is read from the SOURCE rather than by importing and hoping: every relative
import in every module of the package becomes an edge, and the whole thing is
searched for a cycle. A latent cycle fails here rather than on the day a name
moves.

**Re-exported.** A provider module reaches the shared machinery through one import
site, and the split moved several of those names to a new home. Whether a name is
still reachable where it was is exactly what a downstream provider module depends
on, so the names each concrete adapter imports are listed and resolved.

Neither test imports a vendor tool, spawns anything, or can skip.
"""
from __future__ import annotations

import ast
from importlib import import_module
from pathlib import Path

import pytest

from conductor.command import adapters as adapter_package
from conductor.command.providers import PROVIDER_CATALOG

PACKAGE = Path(adapter_package.__file__).resolve().parent
PACKAGE_NAME = "conductor.command.adapters"

#: The names each concrete transport reaches the shared machinery through. They
#: are listed rather than derived so the list itself is a claim: these are the
#: seams a provider module is allowed to depend on, and a split that moved one
#: without a home fails here.
PUBLIC_SEAMS = {
    "conductor.command.adapters.headless_cli": (
        "DISPATCH_CAPABILITY", "ExecutablePin", "HarnessProfile",
        "HeadlessCliError", "HeadlessCliTransport", "OUTPUT_LIMIT",
        "TASK_CHANNEL_STDIN", "VERSION_TIMEOUT_SECONDS", "is_absolute",
        "reviewed_env_allow", "reviewed_pin_path", "_version_token"),
    "conductor.command.adapters.harness_profile": (
        "DISPATCH_CAPABILITY", "ExecutablePin", "HarnessProfile",
        "HeadlessCliError", "is_absolute", "reviewed_env_allow",
        "reviewed_pin_path"),
    "conductor.command.adapters.harness_workspace": (
        "HarnessWorkspace", "WorkspaceNotContained", "WORK_DIR",
        "INSTRUCTION_DIR", "HOME_LEAF_ABSENT", "HOME_LEAF_EMPTY",
        "HOME_LEAF_FILE", "HOME_LEAF_OTHER"),
}


def _modules() -> dict[str, ast.Module]:
    out: dict[str, ast.Module] = {}
    for path in sorted(PACKAGE.glob("*.py")):
        name = f"{PACKAGE_NAME}.{path.stem}" if path.stem != "__init__" \
            else PACKAGE_NAME
        out[name] = ast.parse(path.read_text(encoding="utf-8"))
    return out


def _initialisation_imports(tree: ast.Module) -> list[ast.ImportFrom]:
    """Only the imports that run when the module is INITIALISED.

    That is the whole question a cycle is about, and two very common patterns are
    deliberately not it:

    - an import inside a FUNCTION or method body is deferred until the call, and
      is the standard way to break a cycle on purpose. ``base.py`` uses one;
    - an import under ``if TYPE_CHECKING:`` never runs at all, and exists exactly
      so two modules can name each other's types without importing each other.
      ``deep_commands.py`` uses one.

    Counting either reports a cycle the interpreter never walks -- which is what
    the first two versions of this walker did, in turn.
    """
    found: list[ast.ImportFrom] = []

    def visit(body: list[ast.stmt]) -> None:
        for node in body:
            if isinstance(node, ast.ImportFrom):
                found.append(node)
            elif isinstance(node, ast.If):
                test = node.test
                if ((isinstance(test, ast.Name) and test.id == "TYPE_CHECKING")
                        or (isinstance(test, ast.Attribute)
                            and test.attr == "TYPE_CHECKING")):
                    visit(node.orelse)  # the runtime branch, if any
                    continue
                visit(node.body)
                visit(node.orelse)
            elif isinstance(node, ast.Try):
                visit(node.body)
                for handler in node.handlers:
                    visit(handler.body)
                visit(node.orelse)
                visit(node.finalbody)
            # A FunctionDef, AsyncFunctionDef or ClassDef body is NOT descended
            # into: nothing in it runs at import time.
    visit(tree.body)
    return found


def _edges() -> dict[str, set[str]]:
    """Every RUNTIME relative import inside the package, as a directed edge.

    ``from . import _procgroup`` names a SUBMODULE, not the package's own
    ``__init__`` -- reading it as the latter reports a cycle through the package
    root that the interpreter never takes, which is what the first version of
    this walker did.
    """
    trees = _modules()
    names = set(trees)
    graph: dict[str, set[str]] = {}
    for name, tree in trees.items():
        graph[name] = set()
        for node in _initialisation_imports(tree):
            if node.level != 1:
                continue
            if node.module:
                target = f"{PACKAGE_NAME}.{node.module}"
                if target in names:
                    graph[name].add(target)
                continue
            # `from . import A, B` -- each alias may be a submodule of its own.
            for alias in node.names:
                target = f"{PACKAGE_NAME}.{alias.name}"
                if target in names:
                    graph[name].add(target)
    return graph


def test_the_adapter_package_has_no_import_cycle():
    """Read from the source, because a tolerated cycle is still a cycle."""
    graph = _edges()
    assert len(graph) >= 10, f"only {len(graph)} modules were walked"
    assert any(graph.values()), "no relative imports were found, so nothing was read"

    state: dict[str, int] = {}
    trail: list[str] = []

    def walk(node: str) -> list[str] | None:
        state[node] = 1
        trail.append(node)
        for neighbour in sorted(graph.get(node, ())):
            if state.get(neighbour) == 1:
                return trail[trail.index(neighbour):] + [neighbour]
            if state.get(neighbour, 0) == 0:
                found = walk(neighbour)
                if found is not None:
                    return found
        trail.pop()
        state[node] = 2
        return None

    for node in sorted(graph):
        if state.get(node, 0) == 0:
            cycle = walk(node)
            assert cycle is None, "import cycle: " + " -> ".join(
                part.rsplit(".", 1)[-1] for part in cycle)


def test_every_module_of_the_package_imports_on_its_own():
    """Each in isolation, so no module depends on another being imported first."""
    for name in sorted(_modules()):
        assert import_module(name) is not None, f"{name} did not import"


@pytest.mark.parametrize("module,names", sorted(PUBLIC_SEAMS.items()))
def test_the_seams_a_provider_module_imports_are_still_reachable(module, names):
    """The split moved several of these; each must still resolve where it did."""
    reached = import_module(module)
    missing = [name for name in names if not hasattr(reached, name)]
    assert missing == [], f"{module} no longer offers {missing}"


def _transport_stems() -> tuple[str, ...]:
    """Every module a CATALOGUED transport lives in, derived from the catalog.

    Spelled out, this list went stale twice: `claude_code` was never added when
    Claude Code became real, and `codex_cli` would have been the third. Derived,
    a provider carries itself into the rule the day it is catalogued -- and one
    REMOVED from the catalog takes itself back out, which is the same shape the
    identity gate already uses for the same reason.
    """
    stems = sorted({
        entry.adapter_class.__module__.rsplit(".", 1)[-1]
        for entry in PROVIDER_CATALOG.values()})
    assert len(stems) >= 5, f"only {len(stems)} transport modules were derived"
    return tuple(stems)


def test_each_transport_module_reaches_the_base_through_one_import_site():
    """One site per provider, so a split cannot scatter a provider's dependencies.

    Not a style rule: the identity gate derives a provider's permitted module
    from its adapter class, and a provider that pulled the shared machinery from
    several places would make that one module harder to read whole -- which is
    the property the gate rests on.
    """
    for stem in _transport_stems():
        tree = ast.parse((PACKAGE / f"{stem}.py").read_text(encoding="utf-8"))
        sites = [
            node.module for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.level == 1
            and node.module in {"headless_cli", "harness_profile"}]
        assert sites == ["headless_cli"], (
            f"{stem} reaches the shared machinery through {sites}")
