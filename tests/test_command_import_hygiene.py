"""No module of the command package imports one name twice in one statement.

`api_contracts` carried `_safe_id` twice in the list it re-exports from `api_refusals`: the second
copy did nothing and said, to the next reader, that two different things were being brought in.
The interpreter accepts it and no test noticed; this walks every module of the package so the
next copy is found where it is made.
"""
from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

import conductor.command as command

PACKAGE = Path(command.__file__).resolve().parent


def repeated_names(source):
    """Every `(line, name)` an import statement of this source lists more than once."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.ImportFrom, ast.Import)):
            counts = Counter(alias.asname or alias.name for alias in node.names)
            found += [(node.lineno, name) for name, times in counts.items() if times > 1]
    return sorted(found)


def test_the_walk_names_a_name_listed_twice_and_passes_a_list_that_repeats_none():
    twice = "from .x import (\n    a,\n    b,\n    a,\n)\nimport os, os\n"
    assert repeated_names(twice) == [(1, "a"), (6, "os")]
    assert repeated_names("from .x import a, b\nimport os, sys\nfrom .y import a\n") == []


def test_no_module_of_the_command_package_imports_a_name_twice_in_one_statement():
    modules = sorted(PACKAGE.rglob("*.py"))
    assert len(modules) > 100, "the walk found the package"
    found = {str(path.relative_to(PACKAGE)): repeated_names(path.read_text(encoding="utf-8"))
             for path in modules}
    assert {path: rows for path, rows in found.items() if rows} == {}
