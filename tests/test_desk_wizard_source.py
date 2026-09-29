"""Source guards for the wizard's modules: what they may reach, and what they may not.

The wizard's model is a pure reducer and its renderer builds text nodes from the
model's answers, so the source rules are narrow and worth stating once: no clock, no
randomness, no storage, no DOM in the model, no vendor name anywhere, nothing that
opens a wire, every function short, one closed table of events, and a renderer that
hands its host nothing but events from that table. These are guards over SOURCE TEXT;
what a browser draws is `browser_tests/test_desk_wizard*.py`.
"""
from __future__ import annotations

import re
from pathlib import Path

from tests.desk_wizard_node import run_js
from tests.js_exports import exported_names
from tests.test_graph_source import _code

PANEL = Path(__file__).resolve().parents[1] / "src" / "conductor" / "panel"
#: The wizard's pure modules, each with the one set of siblings it may import. Grown by the
#: commit that creates a module, in the same commit as its registry rows.
PURE = {"desk-wizard-model.js": {"./studio-tasks-model.js", "./desk-wizard-materials.js",
                                 "./desk-wizard-cycle.js", "./desk-wizard-roles.js",
                                 "./desk-wizard-base.js", "./desk-wizard-team.js"},
        "desk-wizard-base.js": {"./studio-tasks-model.js", "./desk-wizard-materials.js",
                                "./desk-wizard-roles.js"},
        "desk-wizard-team.js": {"./desk-wizard-base.js", "./desk-wizard-cycle.js",
                                "./desk-wizard-roles.js"},
        "desk-wizard-materials.js": set(), "desk-wizard-cycle.js": set(),
        "desk-wizard-roles.js": set()}
#: The renderer: it builds elements, so it reaches the view's helper and the words, and no store,
#: no transport and no other screen.
RENDERER = "desk-wizard.js"
DRAWN = {RENDERER: {"./command-view.js", "./studio-i18n.js", "./desk-wizard-model.js",
                    "./desk-wizard-copy.js"}}
#: Data only: the catalogue holds strings and nothing else.
DATA = ("desk-wizard-copy.js",)
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
#: The events only the host sends: the wizard never emits them from a control.
HOST_EVENTS = {"open", "answered"}


def _source(name: str) -> str:
    return (PANEL / name).read_text(encoding="utf-8")


def test_the_wizard_modules_import_only_the_siblings_each_is_granted():
    for name, granted in {**PURE, **DRAWN}.items():
        assert set(re.findall(IMPORTS, _source(name))) <= granted, name
    for name in PURE:
        assert set(re.findall(IMPORTS, _source(name))) == PURE[name], name
    assert re.findall(IMPORTS, _source(DATA[0])) == []


def test_the_wizard_modules_reach_no_clock_no_randomness_no_storage_and_no_dom():
    for name in [*PURE, *DRAWN]:
        code = _code(PANEL / name)
        for pattern in IMPURE:
            assert not re.search(pattern, code), (name, pattern)


def test_the_wizard_modules_name_no_harness_and_no_vendor_even_in_prose():
    for name in [*PURE, *DRAWN, *DATA]:
        text = _source(name).lower()
        for word in VENDOR_WORDS:
            assert not re.search(rf"\b{word}\b", text), (name, word)


def test_every_wizard_function_is_at_most_fifty_lines_and_every_file_under_the_cap():
    for name in [*PURE, *DRAWN, *DATA]:
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


def test_the_renderer_exports_mount_wizard_and_nothing_else():
    assert exported_names(_code(PANEL / RENDERER)) == ["mountWizard"]


def _emitted(code: str, events: list[str]) -> set[str]:
    """Every event type the renderer's source names, a template `x-${..}` as its whole family."""
    found = set(re.findall(r'send\(\{type: "([a-z-]+)"', code))
    for family in re.findall(r"send\(\{type: `([a-z]+-)\$\{", code):
        found |= {name for name in events if name.startswith(family)}
    return found


def test_the_renderer_hands_its_host_only_events_of_the_models_closed_table():
    events = run_js('console.log(JSON.stringify(wiz.EVENTS));')
    emitted = _emitted(_code(PANEL / RENDERER), events)
    assert emitted and emitted <= set(events), emitted - set(events)
    assert not emitted & HOST_EVENTS, "the host opens the wizard and answers its asks"


def test_the_renderer_can_cause_every_event_the_model_takes_but_the_hosts_own():
    """An event no control sends is a way to change the wizard that nobody can reach."""
    events = run_js('console.log(JSON.stringify(wiz.EVENTS));')
    emitted = _emitted(_code(PANEL / RENDERER), events)
    assert set(events) - HOST_EVENTS - emitted == set(), set(events) - HOST_EVENTS - emitted


def _blocks(source: str, tag_words: tuple[str, ...]) -> list[str]:
    """The attribute object of every `element(<tag>, {..})` whose tag names a control."""
    found = []
    for match in re.finditer(r"element\(([^,{]*?),\s*\{", source):
        if not any(f'"{word}"' in match.group(1) for word in tag_words):
            continue
        depth, at = 1, match.end()
        while depth and at < len(source):
            depth += {"{": 1, "}": -1}.get(source[at], 0)
            at += 1
        assert depth == 0, "unbalanced attribute object"
        found.append(source[match.end():at - 1])
    return found


def test_the_renderer_draws_no_radio_or_checkbox_input_the_focus_net_cannot_restore():
    """`restoreFocus` calls `setSelectionRange`, which a radio or a checkbox input refuses.

    A keyed one throws inside the host's redraw and drops the asks the same event made, so a
    choice is a button that says whether it is on (`role` radio or switch, `aria-checked`).
    """
    code = _code(PANEL / RENDERER)
    assert not re.search(r'type: "(?:radio|checkbox)"', code)
    assert "aria-checked" in code


def test_no_wizard_module_writes_the_focus_nets_scope_attribute():
    """`data-step` is the focus net's scope: `focusTarget` remembers the form around a control by
    it and `restoreFocus` looks for the successor only inside `[data-step="<that name>"]`.

    A wizard root that carried its own step name there sent the successor of "Next" looking
    inside the step it had just left, so pressing Next from the keyboard dropped focus to the
    page. The root says its step in its own attribute (`data-wizard-current`).
    """
    for name in [*PURE, *DRAWN, *DATA]:
        assert not re.search(r"\bdata-step\b", _code(PANEL / name)), name
    assert '"data-wizard-current": wizard.step' in _code(PANEL / RENDERER)


def test_every_control_the_renderer_builds_carries_a_focus_key():
    blocks = _blocks(_code(PANEL / RENDERER), ("button", "input", "textarea", "select"))
    assert len(blocks) >= 5
    assert all('"data-focus"' in block for block in blocks), [
        block[:60] for block in blocks if '"data-focus"' not in block]
