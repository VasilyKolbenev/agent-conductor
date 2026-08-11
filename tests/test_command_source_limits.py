"""Source-shape guard for the command package: functions stay within the size cap.

This is a meta-test, not a behavioural one.  It parses every module of
``src/conductor/command`` with :mod:`ast` and asserts no function or method spans
more than ``MAX_FUNCTION_LINES`` source lines, counted from its ``def`` line
through its last line.  ``_read_journal`` sits exactly on the cap; a function that
grows past it -- for instance three split reconcile helpers merged back into one
68-line method -- turns this red rather than sliding back in unmeasured.
"""
from __future__ import annotations

import ast
from pathlib import Path

import conductor.command


MAX_FUNCTION_LINES = 50


def _command_sources() -> list[Path]:
    package = Path(conductor.command.__file__).resolve().parent
    return sorted(package.rglob("*.py"))


def test_every_function_in_the_command_package_stays_within_the_size_cap():
    sources = _command_sources()
    assert sources, "no command-package sources were discovered"
    oversize: list[str] = []
    for path in sources:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                span = node.end_lineno - node.lineno + 1
                if span > MAX_FUNCTION_LINES:
                    oversize.append(f"{path.name}:{node.name} spans {span} lines")
    assert oversize == [], (
        f"functions exceed {MAX_FUNCTION_LINES} lines: {oversize}")
