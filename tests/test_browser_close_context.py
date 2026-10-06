"""A window whose route handlers fetch is closed through `close_context`, and only through it.

A handler that calls `route.fetch()` is a call in flight until the answer is back. A context closed
under it disposes the request context, the fetch raises "Request context disposed" in the handler,
and Playwright raises that in the NEXT synchronous call of the process: the first call of the next
test, which then fails for a reason that is none of its own (CI run 37324577294, Windows).
`browser_tests/desk_hold.close_context` unroutes every page and the context with `ignoreErrors`
and then closes. The suppression is strictly at closing and of the window being closed:
`browser_tests/test_desk_hold.py` shows that a fetch that fails in a window that is still open is
heard by the test, and that closing another window does not hide it.

This is the change-detection half. It reads the source of every browser module with a handler that
fetches (a call of `.fetch(`, or a `Hold` given a `rewrite`, which fetches to rewrite) and refuses a
direct `context.close()` or `page.context.close()` in it. A window made by a rig, a helper module
that opens windows for the test modules that import it (a module that is not a test and calls
`.new_context(`), has the handlers of those modules: a rig that a fetching module imports is read
the same way, and must itself close what it opens through `close_context`, because a window nobody
closes is closed by the per-test reaper of the conftest with a plain `close()`. That reaper is the
net for a window a test left open and the one place besides the helper that closes directly (in a
copy of itself that the gate's own tests run alone, so it cannot import the helper); no window of
a fetching module is meant to reach it. Two files are therefore exempt, each for a stated reason:
`desk_hold.py` defines the helper, and `conftest.py` holds the reaper.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

BROWSER = Path(__file__).resolve().parents[1] / "browser_tests"
EXEMPT = ("desk_hold.py", "conftest.py")
WINDOWS = ("context", "ctx")
#: The words on the line of a close that is meant to be raw: the one test that shows what the
#: helper replaces.
ON_PURPOSE = "raw close on purpose"


def fetches(tree: ast.Module) -> bool:
    """Whether a module installs a route handler that fetches."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "fetch":
            return True
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Attribute) and target.attr == "rewrite"
                for target in node.targets):
            return True
    return False


def raw_closes(tree: ast.Module) -> list[int]:
    """The lines that close a context directly: `context.close()`, `ctx.close()`,
    `<anything>.context.close()`."""
    found = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "close" and not node.args):
            continue
        owner = node.func.value
        if (isinstance(owner, ast.Name) and owner.id in WINDOWS) or (
                isinstance(owner, ast.Attribute) and owner.attr == "context"):
            found.append(node.lineno)
    return found


def calls(tree: ast.Module, name: str) -> bool:
    """Whether a module calls a function or a method of this name."""
    return any(isinstance(node, ast.Call) and (
        (isinstance(node.func, ast.Name) and node.func.id == name)
        or (isinstance(node.func, ast.Attribute) and node.func.attr == name))
        for node in ast.walk(tree))


def imports(tree: ast.Module) -> set[str]:
    """The browser modules a module imports, as file names: `from browser_tests.x import y` and
    `from browser_tests import x`."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.ImportFrom) and node.module):
            continue
        parts = node.module.split(".")
        if parts[0] == "browser_tests" and len(parts) > 1:
            found.add(f"{parts[1]}.py")
        elif node.module == "browser_tests":
            found.update(f"{alias.name}.py" for alias in node.names)
    return found


def scope(sources: dict[str, str]) -> tuple[set[str], set[str]]:
    """The modules the rule reads: those with a fetching handler, and the rigs they import. A rig
    is a module that is not a test and opens windows (a call of `.new_context(`); the windows of
    one are the windows of every module that imports it."""
    trees = {name: ast.parse(text) for name, text in sources.items() if name not in EXEMPT}
    fetching = {name for name, tree in trees.items() if fetches(tree)}
    imported = set().union(*(imports(trees[name]) for name in fetching))
    rigs = {name for name, tree in trees.items()
            if not name.startswith("test_") and calls(tree, "new_context")
            and (name in fetching or name in imported)}
    return fetching, rigs


def faults(sources: dict[str, str]) -> tuple[list[str], int]:
    """Every direct close of a window in a module whose handlers fetch or in a rig such a module
    imports, and every such module that opens windows and never closes one through the helper
    (its windows would be left to the reaper's plain `close()`).

    Args:
        sources: The text of each browser module, by file name.

    Returns:
        One sentence per fault, and the number of modules the scan read.
    """
    found: list[str] = []
    fetching, rigs = scope(sources)
    for name in sorted(fetching | rigs):
        text = sources[name]
        tree = ast.parse(text)
        rows = text.splitlines()
        found += [f"{name}:{line}: closes a window with a fetching handler directly"
                  for line in raw_closes(tree) if ON_PURPOSE not in rows[line - 1]]
        if calls(tree, "new_context") and not calls(tree, "close_context"):
            found.append(f"{name}: opens windows and never closes one through close_context")
    return found, len(fetching | rigs)


def _real() -> dict[str, str]:
    return {path.name: path.read_text(encoding="utf-8") for path in sorted(BROWSER.glob("*.py"))}


def test_no_fetching_module_or_rig_closes_a_window_directly_or_leaves_one_to_the_reaper():
    found, reading = faults(_real())
    assert reading >= 15, "the scan found too few fetching modules to be reading the tree"
    assert found == []


def test_the_rigs_that_fetching_modules_open_their_windows_through_are_read():
    _fetching, rigs = scope(_real())
    assert {"desk_queue_rig.py", "desk_progress_bench.py"} <= rigs


FETCHING = "def handler(route):\n    return route.fetch()\n"
PLANTED = {
    "a context closed by name": (FETCHING + "def test_a(context):\n    context.close()\n", 1),
    "a context closed through its page": (
        FETCHING + "def test_a(page):\n    page.context.close()\n", 1),
    "a context closed through a window": (
        FETCHING + "def test_a(window):\n    window.page.context.close()\n", 1),
    "a context closed under another name": (FETCHING + "def test_a(ctx):\n    ctx.close()\n", 1),
    "a hold that rewrites fetches": (
        "def test_a(desk, context):\n    desk.run_read.rewrite = lambda body: body\n"
        "    context.close()\n", 1),
}


@pytest.mark.parametrize("source,count", list(PLANTED.values()), ids=list(PLANTED))
def test_the_check_refuses_each_planted_direct_close(source, count):
    found, reading = faults({"test_desk_x.py": source})
    assert (len(found), reading) == (count, 1), found


@pytest.mark.parametrize("source", [
    FETCHING + "from browser_tests.desk_hold import close_context\n"
    "def test_a(context):\n    close_context(context)\n",
    "def test_a(context):\n    context.close()\n",
    FETCHING + "def test_a(page):\n    page.close()\n",
], ids=["the helper", "a module that does not fetch", "a page is not a window"])
def test_the_check_accepts_what_is_not_a_direct_close_of_a_fetching_window(source):
    assert faults({"test_desk_x.py": source})[0] == []


def test_a_close_that_says_it_is_raw_on_purpose_is_the_one_a_test_may_keep():
    kept = FETCHING + f"def test_a(context):\n    context.close()  # {ON_PURPOSE}\n"
    assert faults({"test_desk_x.py": kept}) == ([], 1)


OPENS = "def open_desk(browser):\n    return browser.new_context()\n"
HELPER = "from browser_tests.desk_hold import close_context\n"
USES = FETCHING + "from browser_tests import desk_x_rig as rig\n"
RIGS = {
    "a rig that never closes": ({"desk_x_rig.py": OPENS, "test_desk_x.py": USES}, 1),
    "a rig that closes directly": ({
        "desk_x_rig.py": OPENS + HELPER + "def shut(context):\n    context.close()\n"
                         "    close_context(context)\n",
        "test_desk_x.py": USES}, 1),
    "a rig imported by name": ({
        "desk_x_rig.py": OPENS,
        "test_desk_x.py": FETCHING + "from browser_tests.desk_x_rig import open_desk\n"}, 1),
    "a fetching module that opens a window and never closes it": ({
        "test_desk_x.py": FETCHING + "def test_a(chromium):\n    chromium.new_context()\n"}, 1),
}


@pytest.mark.parametrize("sources,count", list(RIGS.values()), ids=list(RIGS))
def test_the_check_refuses_a_rig_whose_windows_are_left_to_the_reaper_or_closed_directly(
        sources, count):
    assert len(faults(sources)[0]) == count, faults(sources)


CLOSING_RIG = OPENS + HELPER + "def shut(context):\n    close_context(context)\n"
READ = {
    "a rig that closes through the helper": ({
        "desk_x_rig.py": CLOSING_RIG, "test_desk_x.py": USES}, 2),
    "a rig no fetching module imports": ({
        "desk_x_rig.py": OPENS, "test_desk_x.py": "from browser_tests import desk_x_rig\n"}, 0),
    "a module of the rig that does not fetch": ({
        "desk_x_rig.py": CLOSING_RIG, "test_desk_x.py": USES,
        "test_desk_y.py": "from browser_tests import desk_x_rig\n"}, 2),
}


@pytest.mark.parametrize("sources,reading", list(READ.values()), ids=list(READ))
def test_the_check_reads_a_rig_when_a_fetching_module_imports_it_and_accepts_one_that_closes(
        sources, reading):
    assert faults(sources) == ([], reading)


def test_the_helper_and_the_reaper_are_the_only_exceptions_and_close_directly():
    assert faults({"desk_hold.py": FETCHING + "def f(context):\n    context.close()\n",
                   "conftest.py": FETCHING + "def f(context):\n    context.close()\n"}) == ([], 0)
    sources = _real()
    for name in EXEMPT:
        assert raw_closes(ast.parse(sources[name])), f"{name} no longer closes a context itself"
