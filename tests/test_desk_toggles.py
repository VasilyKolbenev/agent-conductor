"""The toggles of the desk's top bar, and the press made while the desk boots, under Node.

`desk-toggles.js` gets the page and the desk's operations as arguments, so the real module is run
here with stand-ins that write down what was asked of them. What a browser does with it is
`browser_tests/test_desk_boot_presses.py`'s; this file holds the rule of the choice itself: which
press is kept, which one replaces it, what the boot opens, and when the window of presses closes.
"""
from __future__ import annotations

from tests.desk_node import run_js

MODULES = {"toggles_module": "desk-toggles.js"}
#: The stand-ins: three buttons that keep what was set on them, a panel owner that keeps the open
#: panel, and a log of every operation the module asked of the desk, in order.
PRELUDE = """
const ids = {cycle: "deskFlowToggle", people: "deskPeopleToggle", run: "deskRunToggle"};
const nodes = {};
const byId = (id) => (nodes[id] ??= {hidden: false, expanded: null, listeners: [],
  addEventListener(type, listener) { if (type === "click") this.listeners.push(listener); },
  setAttribute(name, value) { if (name === "aria-expanded") this.expanded = value; }});
const log = [];
let open = null;
const panels = {isOpen: (name) => open === name,
  toggle: (name) => { log.push(["toggle", name]); open = open === name ? null : name; }};
const toggles = toggles_module.createToggles({byId, panels,
  closeContinue: () => log.push(["closeContinue"]), remember: () => log.push(["remember"]),
  render: () => { log.push(["render"]); toggles.draw(false); }});
const press = (name) => byId(ids[name]).listeners.forEach((listener) => listener());
const says = () => Object.fromEntries(Object.entries(ids).map(([name, id]) => [name,
  byId(id).expanded]));
"""


def _run(body: str):
    return run_js(PRELUDE + body, MODULES)


def test_a_press_while_the_desk_boots_is_drawn_and_asks_nothing_of_the_panels():
    answer = _run("""
press("people");
console.log(JSON.stringify({says: says(), log}));
""")
    assert answer["says"] == {"cycle": "false", "people": "true", "run": "false"}
    assert answer["log"] == [["closeContinue"], ["render"]]


def test_the_choice_the_boot_opens_is_the_last_press_and_none_when_there_was_none():
    answer = _run("""
const before = toggles.resolve("run");
console.log(JSON.stringify({before}));
""")
    assert answer["before"] == "run"
    answer = _run("""
press("cycle"); press("run");
console.log(JSON.stringify({chosen: toggles.resolve("people"), says: says()}));
""")
    assert answer["chosen"] == "run"
    assert answer["says"] == {"cycle": "false", "people": "false", "run": "true"}


def test_the_same_toggle_pressed_twice_is_a_choice_of_none_that_replaces_the_address():
    answer = _run("""
press("cycle"); press("cycle");
const none = toggles.resolve("people");
console.log(JSON.stringify({none, says: says()}));
""")
    assert answer["none"] is None
    assert answer["says"] == {"cycle": "false", "people": "false", "run": "false"}


def test_opening_the_block_while_the_desk_boots_replaces_a_pressed_toggle_and_is_what_opens():
    answer = _run("""
press("cycle");
log.length = 0;
toggles.choose("continue");
const drawn = says();
console.log(JSON.stringify({log, drawn, chosen: toggles.resolve("people")}));
""")
    assert answer["log"] == [["render"]]
    assert answer["drawn"] == {"cycle": "false", "people": "false", "run": "false"}
    assert answer["chosen"] == "continue"


def test_closing_the_block_while_the_desk_boots_is_a_choice_of_none_that_replaces_the_address():
    answer = _run("""
toggles.choose("continue");
toggles.choose(null);
console.log(JSON.stringify({chosen: toggles.resolve("people"), says: says()}));
""")
    assert answer["chosen"] is None


def test_the_last_of_a_block_and_a_press_made_while_the_desk_boots_is_the_choice():
    answer = _run("""
toggles.choose("continue");
press("run");
const pressed = toggles.resolve("people");
console.log(JSON.stringify({pressed}));
""")
    assert answer["pressed"] == "run"
    answer = _run("""
press("run");
toggles.choose("continue");
press("run");
press("run");
toggles.choose("continue");
console.log(JSON.stringify({chosen: toggles.resolve(null), says: says()}));
""")
    assert answer["chosen"] == "continue"
    assert answer["says"] == {"cycle": "false", "people": "false", "run": "false"}


def test_a_block_chosen_while_no_toggle_is_pressed_draws_nothing_again():
    answer = _run("""
toggles.choose("continue");
toggles.choose(null);
console.log(JSON.stringify({log}));
""")
    assert answer["log"] == []


def test_the_block_opened_after_the_boot_has_opened_its_panel_is_no_choice_of_the_toggles():
    answer = _run("""
press("cycle");
toggles.resolve(null);
open = "cycle";
log.length = 0;
toggles.choose("continue");
toggles.choose(null);
toggles.draw(false);
console.log(JSON.stringify({log, says: says()}));
""")
    assert answer["log"] == []
    assert answer["says"]["cycle"] == "true"


def test_a_third_press_of_the_same_toggle_chooses_it_again():
    answer = _run("""
press("run"); press("run"); press("run");
console.log(JSON.stringify({chosen: toggles.resolve(null)}));
""")
    assert answer["chosen"] == "run"


def test_after_the_boot_has_opened_its_panel_a_press_toggles_the_panel_and_writes_the_address():
    answer = _run("""
press("cycle");
toggles.resolve(null);
log.length = 0;
press("people");
press("people");
console.log(JSON.stringify({log, says: says()}));
""")
    assert answer["log"] == [["closeContinue"], ["toggle", "people"], ["remember"],
                             ["closeContinue"], ["toggle", "people"], ["remember"]]
    assert answer["says"]["people"] == "false"


def test_after_the_boot_the_toggles_say_the_panel_that_is_open_and_not_the_early_choice():
    answer = _run("""
press("cycle");
toggles.resolve("run");
open = "run";
toggles.draw(false);
console.log(JSON.stringify({says: says()}));
""")
    assert answer["says"] == {"cycle": "false", "people": "false", "run": "true"}


def test_a_desk_open_for_another_project_hides_every_toggle():
    answer = _run("""
toggles.draw(true);
const hidden = Object.values(ids).map((id) => byId(id).hidden);
toggles.draw(false);
console.log(JSON.stringify({hidden, shown: Object.values(ids).map((id) => byId(id).hidden)}));
""")
    assert answer == {"hidden": [True, True, True], "shown": [False, False, False]}


def test_the_boot_is_applied_only_once_it_says_it_has_finished_and_names_the_three_panels():
    answer = _run("""
const first = toggles.applied();
toggles.finish();
console.log(JSON.stringify({first, then: toggles.applied(), names: toggles.names}));
""")
    assert answer == {"first": False, "then": True, "names": ["cycle", "people", "run"]}
