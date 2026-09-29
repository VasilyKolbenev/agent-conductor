"""The product's own top-level names and the block that keeps them out of a repository (spec 9.2).

`PRODUCT_TOP_NAMES` is derived from the constants that own each name. The guards here rebuild the
expected list from those owners, and from the provider catalog for the harness folders, so a
harness added to the catalog and forgotten in the module turns a test red (L14).
"""
import ast
import fnmatch
import importlib
from pathlib import Path

from conductor import ownership_records
from conductor.command import product_names as names
from conductor.command import work_layout
from conductor.command.adapters import harness_workspace
from conductor.command.providers import PROVIDER_CATALOG

SOURCE = Path(names.__file__).resolve().parent
ADAPTERS = SOURCE / "adapters"
#: Spelled from spec 9.2 and 8.1: the first five lines of the block, then one folder line and one
#: marker line per harness.
BLOCK_HEAD = ["/conductor/", "/conductor.v3/", "/.conduct*", "/work/", "/instructions/"]
#: The order spec 9.2 lists the harness modules in.
HARNESS_ORDER = ("claude_code", "codex_cli", "grok_build", "kimi_code", "dsh_harness")


def harness_names():
    """Every catalogued harness's (home folder, marker), read off its own adapter module."""
    modules = {entry.adapter_class.__module__ for entry in PROVIDER_CATALOG.values()}
    return {(module.HOME_DIR, module.MARKER_DIR)
            for module in map(importlib.import_module, sorted(modules))}


def test_product_top_names_are_rebuilt_from_the_constants_that_own_them():
    expected = [ownership_records.HOME, ownership_records.LEGACY, ownership_records.ACTIVE,
                f"{ownership_records.HOME}-retired-*", ".conduct-seed",
                work_layout.WORK_DIR, harness_workspace.INSTRUCTION_DIR]
    for home, marker in harness_names():
        expected += [home, marker]
    assert len(harness_names()) == len(PROVIDER_CATALOG) == 5
    assert sorted(names.PRODUCT_TOP_NAMES) == sorted(expected)


def test_every_module_that_declares_a_harness_home_is_a_catalogued_adapter_module():
    declaring = set()
    for path in sorted(ADAPTERS.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        assigned = {target.id for node in tree.body if isinstance(node, ast.Assign)
                    for target in node.targets if isinstance(target, ast.Name)}
        if {"HOME_DIR", "MARKER_DIR"} <= assigned:
            declaring.add(f"conductor.command.adapters.{path.stem}")
    catalogued = {entry.adapter_class.__module__ for entry in PROVIDER_CATALOG.values()}
    assert declaring == catalogued


def test_the_retired_pattern_is_the_name_ownership_transition_renames_to():
    source = (SOURCE.parent / "ownership_transition.py").read_text(encoding="utf-8")
    assert 'HOME + "-retired-"' in source
    assert names.RETIRED_PATTERN == f"{ownership_records.HOME}-retired-*"


def test_harness_folder_names_are_imported_and_never_spelled_in_the_module():
    source = Path(names.__file__).read_text(encoding="utf-8")
    for home, marker in harness_names():
        assert home not in source and marker not in source


def test_product_top_names_are_single_components_without_repeats():
    assert isinstance(names.PRODUCT_TOP_NAMES, tuple)
    assert len(set(names.PRODUCT_TOP_NAMES)) == len(names.PRODUCT_TOP_NAMES) == 17
    assert not [name for name in names.PRODUCT_TOP_NAMES if "/" in name or "\\" in name or not name]


def test_agent_instruction_names_are_the_six_of_spec_9_2():
    assert names.AGENT_INSTRUCTION_NAMES == (
        "AGENTS.md", "CLAUDE.md", ".claude/", ".codex/", ".grok/", ".kimi/")


def test_exclude_lines_are_the_single_spelling_of_spec_9_2():
    lines = list(names.EXCLUDE_LINES)
    assert lines[:5] == BLOCK_HEAD
    assert lines[5:7] == ["/.claude-home/", "/.claude-marker"]  # the example of spec 8.1
    tail = []
    for module_name in HARNESS_ORDER:
        module = importlib.import_module(f"conductor.command.adapters.{module_name}")
        tail += [f"/{module.HOME_DIR}/", f"/{module.MARKER_DIR}"]
    assert lines[5:] == tail


def test_the_exclude_lines_name_the_folder_and_marker_of_every_harness_exactly_once():
    lines = set(names.EXCLUDE_LINES)
    for home, marker in harness_names():
        assert f"/{home}/" in lines and f"/{marker}" in lines
    assert len(lines) == len(names.EXCLUDE_LINES)


def test_the_exclude_lines_cover_every_product_top_name():
    patterns = [line.strip("/") for line in names.EXCLUDE_LINES]
    for name in names.PRODUCT_TOP_NAMES:
        sample = name.replace("*", "x")
        assert any(fnmatch.fnmatchcase(sample, pattern) for pattern in patterns), name
