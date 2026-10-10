"""Source guards of the git block: the one switch, the one target, honest words, text as text.

Each guard is a function of source text that returns the faults it finds, so the same function is
run on the real modules (and finds none) and on planted strings (and finds the planted fault): a
guard that has never been seen to fail proves nothing. What a press does is
`tests/test_desk_wizard_git_run.py`; what is drawn is in `browser_tests/test_desk_wizard_git*.py`.
"""
from __future__ import annotations

import re
from pathlib import Path

from tests.desk_wizard_node import PANEL, run_js
from tests.test_graph_source import _code

ROOT = Path(__file__).resolve().parents[1]
SWITCH_MODULE = "desk-wizard-git.js"
MODEL = "desk-wizard-model.js"
BLOCK = ("desk-wizard-git.js", "desk-wizard-git-run.js", "desk-wizard-git-copy.js")
MODULES = {"i18n": "studio-i18n.js"}
SWITCH = "FIRST_COMMIT_CONFIRM_OPEN"
#: How the route's own switch is spelled in lane L's module; the desk never opens before it.
ROUTE = ROOT / "src" / "conductor" / "command" / "git_setup.py"


def _code_of(name: str) -> str:
    return _code(PANEL / name)


def switch_faults(sources: dict[str, str]) -> list[str]:
    """A switch that is not one boolean literal, or is read in more than the one place."""
    faults = []
    own = sources.get(SWITCH_MODULE, "")
    declared = re.findall(rf"^export const {SWITCH} = (true|false);$", own, re.MULTILINE)
    if len(declared) != 1:
        faults.append(f"the switch is not declared exactly once as a boolean literal: {declared}")
    if own.count(SWITCH) != 1:
        faults.append("the module that declares the switch also reads it")
    for name, code in sources.items():
        if name != SWITCH_MODULE and name != MODEL and SWITCH in code:
            faults.append(f"{name} names the switch")
    readers = len(re.findall(rf"\b{SWITCH}\b", sources.get(MODEL, "")))
    if readers > 2:
        faults.append(f"the model reads the switch in {readers - 1} places")
    return faults


def target_faults(sources: dict[str, str]) -> list[str]:
    """Any write target other than the one setup route, or a second endpoint named in the block."""
    faults = []
    for name, code in sources.items():
        for target in re.findall(r'target: "(\w+)"', code):
            if target != "gitSetup":
                faults.append(f"{name} asks target {target}")
        if re.search(r"/command/", code):
            faults.append(f"{name} names an endpoint")
    return faults


def word_faults(catalogue: dict[str, tuple[str, str]]) -> list[str]:
    """A busy, lost or unsent word that promises progress or names a verdict it does not know."""
    banned_en = re.compile(r"cancel|fail|error|abort", re.IGNORECASE)
    banned_ru = re.compile(r"отмен|ошибк|не удалось|сбой", re.IGNORECASE)
    faults = []
    for key, (en, ru) in catalogue.items():
        if not key.startswith(("wizard.first.busy.", "wizard.first.lost.", "wizard.first.unsent.")):
            continue
        if "%" in en or "%" in ru or re.search(r"\d", en + ru):
            faults.append(f"{key} carries a figure")
        if banned_en.search(en) or banned_ru.search(ru):
            faults.append(f"{key} says cancelled or failed")
    return faults


def markup_faults(sources: dict[str, str]) -> list[str]:
    """Any way a text could reach the page as markup."""
    pattern = re.compile(r"innerHTML|outerHTML|insertAdjacentHTML|createContextualFragment"
                         r"|DOMParser|document\.write|[<\"']progress", re.IGNORECASE)
    return [f"{name}: {found.group(0)}" for name, code in sources.items()
            for found in pattern.finditer(code)]


def command_faults(code: str) -> list[str]:
    """`signCommands` must take `signing` alone and never name the stored terms."""
    found = re.search(r"export function signCommands\(([^)]*)\) \{\n(.*?)^\}$", code,
                      re.MULTILINE | re.DOTALL)
    if found is None:
        return ["signCommands is not declared as an exported function"]
    faults = []
    if found.group(1).strip() != "signing":
        faults.append(f"signCommands takes {found.group(1)!r}")
    if re.search(r"\bterms\b", found.group(2)):
        faults.append("signCommands reads the stored terms")
    return faults


def _sources() -> dict[str, str]:
    return {name: _code_of(name) for name in (*BLOCK, MODEL)}


def test_the_switch_is_one_boolean_literal_with_one_declaration_and_at_most_one_reader():
    assert switch_faults(_sources()) == []


def test_the_switch_guard_names_a_second_reader_a_missing_literal_and_a_non_boolean():
    real = _sources()
    second = {**real, "desk-wizard-git-run.js": real["desk-wizard-git-run.js"] + f"\n{SWITCH}"}
    assert switch_faults(second) == ["desk-wizard-git-run.js names the switch"]
    wide = {**real, MODEL: real[MODEL] + f"\nconst a = {SWITCH}; const b = {SWITCH}; {SWITCH};"}
    assert any("the model reads the switch" in fault for fault in switch_faults(wide))
    text = real[SWITCH_MODULE].replace(f"{SWITCH} = false;", f"{SWITCH} = 0;")
    assert any("not declared" in fault for fault in switch_faults({**real, SWITCH_MODULE: text}))
    both = real[SWITCH_MODULE] + f"\nexport const {SWITCH} = true;"
    assert switch_faults({**real, SWITCH_MODULE: both})


def test_the_desk_never_opens_the_confirm_while_the_route_it_guards_is_closed():
    """One direction only: lane L may delete or flip its switch first; the desk is flipped after.

    The guard fails exactly when the desk's literal is true and the route still names its own
    switch as false, which is the one state where a press would reach a door that answers 422. A
    route whose switch is true, or gone, constrains nothing: the flip is the tech lead's.
    """
    route = ROUTE.read_text(encoding="utf-8")
    desk = _code_of(SWITCH_MODULE)
    closed = re.search(r"^_CONFIRM_OPEN\s*=\s*False\b", route, re.MULTILINE) is not None
    open_desk = re.search(rf"^export const {SWITCH} = true;$", desk, re.MULTILINE) is not None
    assert not (open_desk and closed), "the desk's switch is open and the route's is closed"


def test_the_one_direction_guard_fails_for_an_open_desk_beside_a_closed_route_only():
    def fails(route: str, desk: str) -> bool:
        closed = re.search(r"^_CONFIRM_OPEN\s*=\s*False\b", route, re.MULTILINE) is not None
        opened = re.search(rf"^export const {SWITCH} = true;$", desk, re.MULTILINE) is not None
        return opened and closed
    shut, open_, gone = "_CONFIRM_OPEN = False\n", "_CONFIRM_OPEN = True\n", "x = 1\n"
    desk_open, desk_shut = f"export const {SWITCH} = true;", f"export const {SWITCH} = false;"
    assert fails(shut, desk_open) is True
    assert [fails(shut, desk_shut), fails(open_, desk_open), fails(gone, desk_open),
            fails(open_, desk_shut), fails(gone, desk_shut)] == [False] * 5


def test_the_block_asks_only_the_one_setup_target_and_names_no_endpoint_of_its_own():
    assert target_faults({name: _code_of(name) for name in BLOCK}) == []
    planted = {"x.js": 'const ask = {target: "gitSetup"}; const other = {target: "seed"};',
               "y.js": 'const path = "/command/project/git/setup";'}
    assert target_faults(planted) == ["x.js asks target seed", "y.js names an endpoint"]


def test_no_busy_lost_or_unsent_word_carries_a_figure_or_calls_an_unknown_outcome_a_verdict():
    out = run_js("""
      console.log(JSON.stringify(Object.fromEntries(Object.entries(i18n.MESSAGES).map(
        ([key, row]) => [key, [row.en, row.ru]]))));
    """, modules=MODULES)
    assert any(key.startswith("wizard.first.busy.") for key in out)
    assert word_faults(out) == []
    planted = {"wizard.first.busy.confirm": ("Working, 60% done", "Работаем"),
               "wizard.first.lost.head": ("The request was cancelled", "Запрос отменён"),
               "wizard.first.unsent.route_not_found": ("It is fine", "Не удалось отправить"),
               "wizard.first.next.git_failed": ("It failed 3 times", "Сбой")}
    assert word_faults(planted) == [
        "wizard.first.busy.confirm carries a figure",
        "wizard.first.lost.head says cancelled or failed",
        "wizard.first.unsent.route_not_found says cancelled or failed"]


def test_the_store_error_notice_is_never_the_words_of_a_lost_answer():
    for name in BLOCK:
        assert "error.store_error" not in _code_of(name), name


def test_no_module_of_the_block_can_put_a_text_on_the_page_as_markup_or_draws_a_progress_bar():
    assert markup_faults({name: _code_of(name) for name in BLOCK}) == []
    planted = {"v.js": "node.innerHTML = text;", "w.js": 'element("progress", {})'}
    assert markup_faults(planted) == ["v.js: innerHTML", 'w.js: "progress']


def test_the_sign_commands_take_signing_alone_and_never_the_stored_terms():
    assert command_faults(_code_of(SWITCH_MODULE)) == []
    bad_arity = "export function signCommands(signing, terms) {\n  return null;\n}\n"
    bad_read = ("export function signCommands(signing) {\n"
                "  return `git update-ref ${terms.target_ref}`;\n}\n")
    assert command_faults(bad_arity) != [] and command_faults(bad_read) != []
    assert command_faults("") == ["signCommands is not declared as an exported function"]
