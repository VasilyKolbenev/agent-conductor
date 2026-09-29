"""Source guards for the «Схема» modules: what they may reach, and what they may not.

The edits, the write chain and the panel's model are pure functions of plain values, and the drawing
builds text nodes from what the model says, so the source rules are narrow and worth stating once:
no clock, no randomness, no storage, no DOM in a pure module, no vendor name anywhere, nothing that
opens a wire, every function short, one closed table of edits. These are guards over SOURCE TEXT;
what a browser draws is `browser_tests/test_desk_flow*.py`.
"""
from __future__ import annotations

import re
from pathlib import Path

from tests.desk_wizard_node import run_js
from tests.test_graph_source import _code

PANEL = Path(__file__).resolve().parents[1] / "src" / "conductor" / "panel"
#: The pure modules, each with the one set of siblings it may import. Grown by the commit that
#: creates a module, in the same commit as its registry rows.
PURE = {"desk-flow-shape.js": set(),
        "desk-flow-loops.js": {"./desk-flow-shape.js"},
        "desk-flow-branches.js": {"./desk-flow-shape.js"},
        "desk-flow-edits.js": {"./desk-flow-shape.js", "./desk-flow-loops.js",
                               "./desk-flow-branches.js"},
        "desk-flowwrite.js": {"./desk-flow-edits.js", "./desk-flow-shape.js"}}
#: Modules that draw. None yet: the drawing lands with the panel.
DRAWN: dict[str, set[str]] = {}
#: Data only.
DATA: tuple[str, ...] = ()
IMPORTS = r'from "(\./[a-z-]+\.js)";'
FUNCTION_CAP = 50
#: A clock, a random source, storage and the DOM: what a pure module must never reach for. The timer
#: names are here for the reason the clock is: a delay is a clock.
IMPURE = (r"\bDate\b", r"Math\.random", r"\bcrypto\b", "localStorage", "sessionStorage",
          r"\bdocument\s*[.\[]", r"\bwindow\s*[.\[]", r"fetch\(", "setTimeout", "setInterval",
          "requestAnimationFrame", r"\bperformance\b", r"\bnavigator\b", "innerHTML",
          r"console\.")
#: Names of the harnesses this product drives, and of their makers: a cycle names roles, never a
#: harness, so no module of the editor names one, even in prose.
VENDOR_WORDS = ("claude", "codex", "grok", "kimi", "qwen", "deepseek", "anthropic", "openai",
                "gemini", "dsh")


def _source(name: str) -> str:
    return (PANEL / name).read_text(encoding="utf-8")


def test_the_flow_modules_import_only_the_siblings_each_is_granted():
    for name, granted in {**PURE, **DRAWN}.items():
        assert set(re.findall(IMPORTS, _source(name))) <= granted, name
    for name in PURE:
        assert set(re.findall(IMPORTS, _source(name))) == PURE[name], name


def test_the_flow_modules_reach_no_clock_no_randomness_no_storage_and_no_dom():
    for name in PURE:
        code = _code(PANEL / name)
        for pattern in IMPURE:
            assert not re.search(pattern, code), (name, pattern)


def test_the_flow_modules_name_no_harness_and_no_vendor_even_in_prose():
    for name in [*PURE, *DRAWN, *DATA]:
        text = _source(name).lower()
        for word in VENDOR_WORDS:
            assert not re.search(rf"\b{word}\b", text), (name, word)


def test_every_flow_function_is_at_most_fifty_lines_and_every_file_under_the_cap():
    for name in [*PURE, *DRAWN, *DATA]:
        source = _source(name)
        assert len(source.splitlines()) <= 800, name
        for match in re.finditer(r"^(?:export )?function \w+\([^)]*\) \{\n(.*?)^\}$", source,
                                 re.MULTILINE | re.DOTALL):
            length = match.group(0).count("\n") + 1
            assert length <= FUNCTION_CAP, (name, match.group(0).splitlines()[0], length)


def test_the_write_chains_events_are_one_closed_table_and_the_list_is_its_keys():
    code = _code(PANEL / "desk-flowwrite.js")
    assert len(re.findall(r"^const HANDLERS = \{", code, re.MULTILINE)) == 1
    assert "export const WRITE_EVENTS = Object.freeze(Object.keys(HANDLERS));" in code
    assert "Object.hasOwn(HANDLERS, event?.type)" in code, "an inherited key must not be an event"


def test_the_edits_are_one_closed_table_whose_keys_are_the_edit_words():
    code = _code(PANEL / "desk-flow-edits.js")
    table = re.search(r"^const EDITS = Object\.freeze\(\{(.*?)\}\);$", code,
                      re.MULTILINE | re.DOTALL)
    assert table is not None and len(re.findall(r"^const EDITS = ", code, re.MULTILINE)) == 1
    keys = [part.split(":")[0].strip().strip('"') for part in table.group(1).split(",")
            if part.strip()]
    words = run_js("console.log(JSON.stringify(edits.EDIT_TYPES));",
                   modules={"edits": "desk-flow-edits.js"})
    assert sorted(keys) == sorted(words), "one arm per word, and no arm for another"
    assert "Object.hasOwn(EDITS, edit.type)" in code, "an inherited key must not be an edit"
