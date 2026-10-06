"""A wait on a desk or hub document goes on waiting while the element it reads is absent.

A frame that was just mounted, or a page whose location was just replaced, runs the wait's
predicate in a document that has not drawn the desk yet. A predicate that dereferences an element
there throws, and a wait whose predicate throws ENDS (the call raises) instead of waiting on:
that was the macOS failure of CI run 37324577294. The browser half is
`browser_tests/test_desk_settled.py`, which runs the old form and the shared forms in a frame that
is not the desk. This file is the change-detection half: it reads the SOURCE of every predicate the
desk and hub modules of `browser_tests/` pass to a wait, with the constants and helpers they pass
it through resolved, and refuses

- a lookup (`getElementById`, `querySelector`, `closest`, `find`, `at`) whose result is dereferenced
  without `?.`: absent, it is a TypeError;
- a negated optional chain (`!el?.disabled`): absent, it is TRUE, so the wait would end as if the
  control had been seen enabled. Ask `=== false` instead.

The classic pages (Studio, graph, composer) are not in scope: their elements are the static markup
of a page the test loaded with `wait_until="load"`, a state in which "the page is not there yet"
cannot be observed.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

BROWSER = Path(__file__).resolve().parents[1] / "browser_tests"
#: The modules whose waits are held to the rule: the ones that boot a desk or mount it in a hub.
SCOPE = ("test_desk_", "desk_", "test_hub_", "hub_")
#: A module that holds the old, unguarded form on purpose, to show what it does in a frame that
#: is not the desk.
DEMONSTRATION = "test_desk_settled.py"
#: Each call that waits, and where its predicate is among its positional arguments.
WAITERS = {"wait_for_function": 0, "wait_hub": 2}
LOOKUPS = ("getElementById", "querySelector", "closest", "find", "at", "namedItem")
#: What `desk_settled.shell_is(word)` builds, as the one helper whose calls are resolved.
SHELL_WORD = 'document.getElementById("deskShell")?.getAttribute("data-state")'


def balanced(text: str, start: int) -> int:
    """The index just after the parenthesis group that opens at `start`, or -1."""
    depth, quote = 0, None
    for index in range(start, len(text)):
        char = text[index]
        if quote:
            if char == quote and text[index - 1] != "\\":
                quote = None
        elif char in "\"'`":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index + 1
    return -1


def wait_faults(js: str) -> list[str]:
    """Every way a predicate throws, or is satisfied, while the element it reads is absent.

    Args:
        js: The text of one predicate.

    Returns:
        One sentence per fault, each quoting the predicate around it; empty when it is guarded.
    """
    faults = []
    for name in LOOKUPS:
        for found in re.finditer(rf"\.{name}\s*\(", js):
            end = balanced(js, found.end() - 1)
            after = js[end:end + 3].lstrip() if end >= 0 else ""
            if after.startswith(".") and not after.startswith("?."):
                faults.append(f"dereferences {name}(...) without ?.: "
                              f"{js[max(0, found.start() - 20):end + 20]!r}")
    for found in re.finditer(r"!\s*document\.(?:getElementById|querySelector)\s*\(", js):
        end = balanced(js, found.end() - 1)
        if end >= 0 and js[end:end + 2] == "?.":
            faults.append(f"negates an optional chain, which is true while the element is "
                          f"absent: {js[found.start():end + 20]!r}")
    return faults


def _constants(tree: ast.Module) -> dict[str, ast.expr]:
    return {node.targets[0].id: node.value for node in tree.body
            if isinstance(node, ast.Assign) and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)}


def _imports(tree: ast.Module) -> dict[str, tuple[str, str]]:
    return {(alias.asname or alias.name): (node.module.split(".")[-1] + ".py", alias.name)
            for node in tree.body
            if isinstance(node, ast.ImportFrom) and node.module
            and node.module.startswith("browser_tests")
            for alias in node.names}


class Predicates:
    """The predicates of a set of browser modules, resolved from their source text."""

    def __init__(self, sources: dict[str, str]) -> None:
        trees = {name: ast.parse(text) for name, text in sources.items()}
        self.constants = {name: _constants(tree) for name, tree in trees.items()}
        self.imports = {name: _imports(tree) for name, tree in trees.items()}
        self.trees = trees

    def text(self, node: ast.expr, module: str, depth: int = 0) -> str | None:
        """The JavaScript an expression builds, or None when it cannot be said from the source."""
        if depth > 8:
            return None
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.JoinedStr):
            parts = [part.value if isinstance(part, ast.Constant)
                     else (self.text(part.value, module, depth + 1) or "<?>")
                     for part in node.values]
            return "".join(parts)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left = self.text(node.left, module, depth + 1)
            right = self.text(node.right, module, depth + 1)
            return None if left is None or right is None else left + right
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == "shell_is" and len(node.args) == 1:
            word = self.text(node.args[0], module, depth + 1)
            return None if word is None else f'() => {SHELL_WORD} === "{word}"'
        if isinstance(node, ast.Name):
            return self._name(node.id, module, depth)
        return None

    def _name(self, name: str, module: str, depth: int) -> str | None:
        if name in self.constants.get(module, {}):
            return self.text(self.constants[module][name], module, depth + 1)
        other, original = self.imports.get(module, {}).get(name, (None, None))
        if other in self.constants and original in self.constants[other]:
            return self.text(self.constants[other][original], other, depth + 1)
        return None

    def waits(self) -> list[tuple[str, int, str | None]]:
        """Every wait: (module, line, its predicate's text, None when unresolved).

        A helper that passes its own parameter on is not a wait of its own: its callers are.
        """
        found = []
        for module, tree in self.trees.items():
            self._visit(tree, module, frozenset(), found)
        return found

    def _visit(self, node: ast.AST, module: str, params: frozenset[str], found: list) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            params = params | {arg.arg for arg in node.args.args + node.args.kwonlyargs}
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else (
                func.id if isinstance(func, ast.Name) else None)
            at = WAITERS.get(name)
            if at is not None and len(node.args) > at:
                given = node.args[at]
                if not (isinstance(given, ast.Name) and given.id in params):
                    found.append((module, node.lineno, self.text(given, module)))
        for child in ast.iter_child_nodes(node):
            self._visit(child, module, params, found)


def in_scope() -> dict[str, str]:
    return {path.name: path.read_text(encoding="utf-8")
            for path in sorted(BROWSER.glob("*.py"))
            if path.name.startswith(SCOPE) and path.name != DEMONSTRATION}


def scan(sources: dict[str, str]) -> tuple[list[str], list[str], int]:
    """The faults, the waits that could not be resolved, and how many waits were read."""
    faults, unresolved, read = [], [], 0
    for module, line, js in Predicates(sources).waits():
        read += 1
        if js is None:
            unresolved.append(f"{module}:{line}")
        else:
            faults += [f"{module}:{line}: {fault}" for fault in wait_faults(js)]
    return faults, unresolved, read


def test_no_wait_on_a_desk_or_hub_document_throws_or_ends_while_its_element_is_absent():
    faults, unresolved, read = scan(in_scope())
    assert read > 150, "the scan found too few waits to be reading the modules"
    assert unresolved == [], "a wait whose predicate cannot be read from source"
    assert faults == []


#: Each predicate the check claims to refuse, and a word its fault must contain.
UNGUARDED = {
    "the shell dereferenced": (
        '() => document.getElementById("deskShell").getAttribute("data-state") === "ready"',
        "getElementById"),
    "a lookup of a selector": (
        '() => document.querySelector("#deskScene [data-deck-run]").dataset.deckRun === "r"',
        "querySelector"),
    "a guarded first operand does not guard the second": (
        '() => document.querySelector("#a")?.dataset.x === "y"'
        ' && document.getElementById("deskScene").childElementCount > 0', "getElementById"),
    "the last message of a host that has none": (
        "() => window.__messages.at(-1).data.run_id === 'r'", "at("),
    "a match found in a list": (
        "() => [...document.querySelectorAll('a')].find((a) => a.id === 'x').hidden", "find("),
    "a closest": ("() => document.activeElement.closest('#a').hidden", "closest"),
    "a negated optional chain": (
        "() => !document.querySelector('[name=save]')?.disabled", "negates"),
}
GUARDED = [
    '() => document.getElementById("deskShell")?.getAttribute("data-state") === "ready"',
    "() => window.__messages.at(-1)?.data.run_id === 'r'",
    "() => document.querySelector('[name=save]')?.disabled === false",
    "() => document.querySelectorAll('#hubDesk iframe').length === 0",
    "() => !document.querySelector('[data-gone]')",
]


@pytest.mark.parametrize("predicate,word", list(UNGUARDED.values()), ids=list(UNGUARDED))
def test_the_check_refuses_each_unguarded_form_and_names_it(predicate, word):
    faults = wait_faults(predicate)
    assert faults, "an unguarded predicate was accepted"
    assert any(word in fault for fault in faults), faults


@pytest.mark.parametrize("predicate", GUARDED)
def test_the_check_accepts_the_guarded_forms(predicate):
    assert wait_faults(predicate) == []


def test_the_scan_reads_a_constant_a_helper_and_an_import_through_to_the_predicate():
    caller = "\n".join([
        "from browser_tests.desk_a import RAW",
        "def test_a(page):",
        "    page.wait_for_function(RAW)",
        "def test_b(page):",
        "    page.wait_for_function(f'''() => {1}''')",
        "def test_c(one):",
        "    wait_hub(one, 'x', '() => document.getElementById(\"y\").hidden')",
    ])
    sources = {"desk_a.py": 'RAW = """() => document.getElementById("x").hidden"""\n',
               "test_desk_b.py": caller}
    faults, unresolved, read = scan(sources)
    assert (read, unresolved) == (3, [])
    assert [fault.split(":")[0] for fault in faults] == ["test_desk_b.py", "test_desk_b.py"]


def test_the_scan_says_a_predicate_it_cannot_read_instead_of_passing_it():
    sources = {"test_desk_a.py": "def test_a(page):\n    page.wait_for_function(built())\n"}
    assert scan(sources) == ([], ["test_desk_a.py:2"], 1)


def test_a_helper_that_passes_its_own_parameter_on_is_not_a_wait_of_its_own():
    helper = "def wait(page, js):\n    page.wait_for_function(js)\n"
    assert scan({"test_desk_a.py": helper}) == ([], [], 0)


def test_the_demonstration_of_the_old_form_is_the_only_module_left_out():
    left_out = [path.name for path in BROWSER.glob("*.py")
                if path.name.startswith(SCOPE) and path.name not in in_scope()]
    assert left_out == [DEMONSTRATION]
