"""Source guards for the wizard's modules: what they may reach, and what they may not.

The wizard's model is a pure reducer and its renderer builds text nodes from the
model's answers, so the source rules are narrow and worth stating once: no clock, no
randomness, no storage, no DOM in the model, no vendor name anywhere, nothing that
opens a wire, every function short, and one closed table of events. These are guards
over SOURCE TEXT; what a browser draws is `browser_tests/test_desk_wizard.py`.
"""
from __future__ import annotations

import re
from pathlib import Path

from tests.test_graph_source import _code

PANEL = Path(__file__).resolve().parents[1] / "src" / "conductor" / "panel"
#: The wizard's pure modules, each with the one set of siblings it may import. Grown by the
#: commit that creates a module, in the same commit as its registry rows.
PURE = {"desk-wizard-model.js": {"./studio-tasks-model.js", "./desk-wizard-materials.js",
                                 "./desk-wizard-cycle.js"},
        "desk-wizard-materials.js": set(), "desk-wizard-cycle.js": set()}
IMPORTS = r'from "(\./[a-z-]+\.js)";'
FUNCTION_CAP = 50
#: A clock, a random source, storage and the DOM: what a pure module must never reach for.
#: The timer names are here for the reason the clock is: a delay is a clock.
IMPURE = (r"\bDate\b", r"Math\.random", r"\bcrypto\b", "localStorage", "sessionStorage",
          r"\bdocument\s*[.\[]", r"\bwindow\s*[.\[]", r"fetch\(", "setTimeout", "setInterval",
          "requestAnimationFrame", r"\bperformance\b", r"\bnavigator\b", "innerHTML",
          r"console\.")
#: Names of the harnesses this product drives, and of their makers: the wizard reads which
#: harness is offered from the roster's own facts and never names one in code.
VENDOR_WORDS = ("claude", "codex", "grok", "kimi", "qwen", "deepseek", "anthropic", "openai",
                "gemini", "dsh")


def _source(name: str) -> str:
    return (PANEL / name).read_text(encoding="utf-8")


def test_the_wizard_models_import_only_the_siblings_each_is_granted():
    for name, granted in PURE.items():
        assert set(re.findall(IMPORTS, _source(name))) == granted, name


def test_the_wizard_models_reach_no_clock_no_randomness_no_storage_and_no_dom():
    for name in PURE:
        code = _code(PANEL / name)
        for pattern in IMPURE:
            assert not re.search(pattern, code), (name, pattern)


def test_the_wizard_modules_name_no_harness_and_no_vendor_even_in_prose():
    for name in PURE:
        text = _source(name).lower()
        for word in VENDOR_WORDS:
            assert not re.search(rf"\b{word}\b", text), (name, word)


def test_every_wizard_function_is_at_most_fifty_lines_and_every_file_under_the_cap():
    for name in PURE:
        source = _source(name)
        assert len(source.splitlines()) <= 800, name
        for match in re.finditer(r"^(?:export )?function \w+\([^)]*\) \{\n(.*?)^\}$", source,
                                 re.MULTILINE | re.DOTALL):
            length = match.group(0).count("\n") + 1
            assert length <= FUNCTION_CAP, (name, match.group(0).splitlines()[0], length)


def test_the_events_are_one_closed_table_whose_keys_are_the_event_list():
    source = _code(PANEL / "desk-wizard-model.js")
    assert "export const EVENTS = Object.freeze(Object.keys(HANDLERS));" in source
    assert len(re.findall(r"^const HANDLERS = \{", source, re.MULTILINE)) == 1
    assert "Object.hasOwn(HANDLERS, event.type)" in source, "an inherited key must not be a handler"
