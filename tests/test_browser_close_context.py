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
direct `context.close()` or `page.context.close()` in it. Two files are the exception, each for a
stated reason: `desk_hold.py` defines the helper, and `conftest.py` holds the per-test reaper,
which closes a window a test left open, in a copy of itself that the gate's own tests run alone.
The windows of the queue modules (`desk_queue_rig`) are left to that reaper; their desk ends its
stream (HTTP 204), so no read of the desk is there to overlap the close.
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


def faults(sources: dict[str, str]) -> tuple[list[str], int]:
    """Every direct close of a window in a module whose handlers fetch, and how many such modules
    were read.

    Args:
        sources: The text of each browser module, by file name.

    Returns:
        One sentence per fault, and the number of fetching modules the scan read.
    """
    found, reading = [], 0
    for name, text in sources.items():
        if name in EXEMPT:
            continue
        tree = ast.parse(text)
        if not fetches(tree):
            continue
        reading += 1
        rows = text.splitlines()
        found += [f"{name}:{line}: closes a window with a fetching handler directly"
                  for line in raw_closes(tree) if ON_PURPOSE not in rows[line - 1]]
    return found, reading


def _real() -> dict[str, str]:
    return {path.name: path.read_text(encoding="utf-8") for path in sorted(BROWSER.glob("*.py"))}


def test_no_browser_module_with_a_fetching_handler_closes_a_window_directly():
    found, reading = faults(_real())
    assert reading >= 15, "the scan found too few fetching modules to be reading the tree"
    assert found == []


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


def test_the_helper_and_the_reaper_are_the_only_exceptions_and_close_directly():
    assert faults({"desk_hold.py": FETCHING + "def f(context):\n    context.close()\n",
                   "conftest.py": FETCHING + "def f(context):\n    context.close()\n"}) == ([], 0)
    sources = _real()
    for name in EXEMPT:
        assert raw_closes(ast.parse(sources[name])), f"{name} no longer closes a context itself"
