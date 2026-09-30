"""A failure that is marked expected must say which failure it excuses, and must be strict.

A witness written before the code it judges is marked `xfail(strict=True)` (the house precedent:
the drain witnesses, the view door). Two holes make such a marker lie. Without `strict`, the
day the code lands the test turns XPASS and nobody is told to remove the marker. Without
`raises`, any other exception (a typo, an import that broke, a fixture that moved) is excused
as if it were the failure the marker was written for, and the witness keeps reporting "still
waiting" while it tests nothing. This file reads every test module of the repository and
refuses a marker that leaves either hole open, and it carries the cases that show the refusal
can say no.
"""
from __future__ import annotations

import ast
from collections.abc import Iterable
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TEST_ROOTS = (REPO / "tests", REPO / "browser_tests")


def _is_xfail_marker(node: ast.expr) -> bool:
    """`<anything>.mark.xfail`, the decorator written with or without its call."""
    target = node.func if isinstance(node, ast.Call) else node
    return (isinstance(target, ast.Attribute) and target.attr == "xfail"
            and isinstance(target.value, ast.Attribute) and target.value.attr == "mark")


def _keyword(call: ast.expr, name: str) -> ast.expr | None:
    if not isinstance(call, ast.Call):
        return None
    return next((kw.value for kw in call.keywords if kw.arg == name), None)


def _flaw(marker: ast.expr) -> str | None:
    """What is wrong with one marker, in a few words, or None when it is whole."""
    strict, raises = _keyword(marker, "strict"), _keyword(marker, "raises")
    if not (isinstance(strict, ast.Constant) and strict.value is True):
        return "is not strict"
    if raises is None:
        return "does not name the exception it excuses (raises=)"
    return None


def flawed_markers(source: str, where: str = "<source>") -> list[str]:
    """Every xfail marker of `source` that is not strict or names no `raises`."""
    found = []
    for node in ast.walk(ast.parse(source)):
        decorators = getattr(node, "decorator_list", ())
        for marker in (d for d in decorators if _is_xfail_marker(d)):
            flaw = _flaw(marker)
            if flaw is not None:
                found.append(f"{where}:{marker.lineno}: the xfail marker {flaw}")
    return found


def _scan(paths: Iterable[Path]) -> list[str]:
    found: list[str] = []
    for path in paths:
        relative = path.relative_to(REPO).as_posix()
        found += flawed_markers(path.read_text(encoding="utf-8"), relative)
    return found


def test_every_xfail_marker_of_the_repository_is_strict_and_names_what_it_excuses():
    paths = sorted(p for root in TEST_ROOTS if root.is_dir() for p in root.rglob("*.py"))
    assert paths, "no test module was read, so nothing was judged"
    assert _scan(paths) == []


def test_a_marker_without_strict_or_without_raises_is_flagged_and_a_whole_one_is_not():
    whole = "@pytest.mark.xfail(strict=True, raises=AssertionError, reason='later')\ndef t(): ...\n"
    bare = "@pytest.mark.xfail\ndef t(): ...\n"
    loose = "@pytest.mark.xfail(reason='later')\ndef t(): ...\n"
    no_raises = "@pytest.mark.xfail(strict=True, reason='later')\ndef t(): ...\n"
    not_strict = "@pytest.mark.xfail(strict=False, raises=AssertionError)\ndef t(): ...\n"
    assert flawed_markers(whole) == []
    assert [len(flawed_markers(s)) for s in (bare, loose, no_raises, not_strict)] == [1] * 4
    assert "raises" in flawed_markers(no_raises)[0] and "strict" in flawed_markers(loose)[0]


def test_a_marker_on_a_class_or_an_async_test_is_judged_like_any_other():
    source = ("@pytest.mark.xfail(strict=True)\nclass Suite:\n"
              "    @pytest.mark.xfail(reason='later')\n    async def t(self): ...\n")
    assert len(flawed_markers(source)) == 2
