"""The toggles of the desk's top bar, and the press made while the desk boots, under Node.

`desk-toggles.js` gets the page and the desk's operations as arguments, so the real module is run
here with stand-ins that write down what was asked of them. What a browser does with it is
`browser_tests/test_desk_boot_presses.py`'s; this file holds the rule of the choice itself: which
press is kept, which one replaces it, what the boot opens, and when the window of presses closes.
"""
from __future__ import annotations

from tests.desk_node import run_js

MODULES = {"toggles_module": "desk-toggles.js", "hash": "desk-hash.js"}
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
const boot = hash.readDeskHash(d?.first ?? "");
const toggles = toggles_module.createToggles({byId, panels,
  closeContinue: () => log.push(["closeContinue"]), remember: () => log.push(["remember"]),
  render: () => { log.push(["render"]); toggles.draw(false); },
  first: boot, moves: hash.navigationChange});
const hear = (fragment) => toggles.hear(hash.readDeskHash(fragment));
const press = (name) => byId(ids[name]).listeners.forEach((listener) => listener());
const says = () => Object.fromEntries(Object.entries(ids).map(([name, id]) => [name,
  byId(id).expanded]));
"""


def _run(body: str, first: str = ""):
    """Run `body` against the toggles of a desk whose address at boot was `first`."""
    return run_js(PRELUDE + body, MODULES, {"first": first})


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


# -- a hash that arrives while the desk boots --------------------------------------------------

BOOKMARK = "#task=a&panel=people&lang=en"


def test_a_hash_of_the_language_alone_heard_while_the_desk_boots_leaves_the_press():
    answer = _run("""
press("cycle");
log.length = 0;
hear("#lang=ru");
console.log(JSON.stringify({log, chosen: toggles.resolve("people"), says: says()}));
""", BOOKMARK)
    assert answer["log"] == []
    assert answer["chosen"] == "cycle"
    assert answer["says"] == {"cycle": "true", "people": "false", "run": "false"}


def test_a_hash_that_names_a_panel_replaces_the_press_before_it_and_the_panel_the_address_named():
    answer = _run("""
press("people");
log.length = 0;
hear("#panel=run&lang=en");
console.log(JSON.stringify({log, says: says(), chosen: toggles.resolve("people")}));
""", BOOKMARK)
    assert answer["log"] == [["render"]]
    assert answer["says"] == {"cycle": "false", "people": "false", "run": "false"}
    assert answer["chosen"] == "run"


def test_a_hash_that_moves_the_task_and_names_no_panel_is_a_choice_of_none():
    answer = _run("""
press("cycle");
hear("#task=b&lang=en");
console.log(JSON.stringify({chosen: toggles.resolve("people")}));
""", BOOKMARK)
    assert answer["chosen"] is None
    answer = _run("""
console.log(JSON.stringify({chosen: toggles.resolve("people")}));
""", BOOKMARK)
    assert answer["chosen"] == "people"


def test_a_hash_that_only_repeats_what_the_address_said_moves_nothing_and_keeps_the_press():
    answer = _run("""
press("cycle");
hear("#task=a&panel=people&lang=ru");
console.log(JSON.stringify({chosen: toggles.resolve("people")}));
""", BOOKMARK)
    assert answer["chosen"] == "cycle"


def test_a_hash_is_judged_against_the_hash_heard_before_it_and_not_against_the_first_address():
    answer = _run("""
hear("#task=a&panel=run&lang=en");
press("cycle");
hear("#task=a&panel=run&lang=ru");
console.log(JSON.stringify({chosen: toggles.resolve("people")}));
""", BOOKMARK)
    assert answer["chosen"] == "cycle", "the second hash repeats the first: it named nothing new"


def test_a_press_made_after_a_hash_that_names_a_panel_is_the_panel_and_toggles_from_none():
    answer = _run("""
hear("#panel=run&lang=en");
press("run");
const once = toggles.resolve("people");
console.log(JSON.stringify({once}));
""", BOOKMARK)
    assert answer["once"] == "run"
    answer = _run("""
hear("#panel=run&lang=en");
press("run"); press("run");
console.log(JSON.stringify({chosen: toggles.resolve("people")}));
""", BOOKMARK)
    assert answer["chosen"] is None


def test_the_block_opened_after_a_hash_that_names_a_panel_is_the_choice():
    answer = _run("""
press("cycle");
hear("#panel=run&lang=en");
toggles.choose("continue");
console.log(JSON.stringify({chosen: toggles.resolve("people")}));
""", BOOKMARK)
    assert answer["chosen"] == "continue"


def test_a_hash_heard_after_the_boot_has_opened_its_panel_changes_no_choice():
    answer = _run("""
press("cycle");
toggles.resolve("people");
open = "cycle";
log.length = 0;
hear("#panel=run&lang=en");
toggles.draw(false);
console.log(JSON.stringify({log, says: says()}));
""", BOOKMARK)
    assert answer["log"] == []
    assert answer["says"] == {"cycle": "true", "people": "false", "run": "false"}


def test_a_hash_says_how_many_choices_were_made_when_it_arrived_and_whether_it_was_decided():
    answer = _run("""
const none = hear("#lang=ru");
press("cycle");
const one = hear("#lang=ru");
toggles.choose("continue");
const two = hear("#lang=ru");
toggles.resolve(null);
toggles.choose(null);
press("run");
const three = hear("#lang=ru");
console.log(JSON.stringify({none, one, two, three}));
""", BOOKMARK)
    assert answer == {"none": {"asked": 0, "decided": True}, "one": {"asked": 1, "decided": True},
                      "two": {"asked": 2, "decided": True},
                      "three": {"asked": 4, "decided": False}}


def test_the_panel_of_a_hash_heard_while_the_desk_boots_is_not_asked_again_when_the_boot_is_over():
    answer = _run("""
const change = hash.navigationChange(boot, hash.readDeskHash("#task=b&panel=run&lang=en"));
const ticket = hear("#task=b&panel=run&lang=en");
console.log(JSON.stringify({change, after: toggles.after(ticket, change)}));
""", BOOKMARK)
    keys = [step["key"] for step in answer["change"]["steps"]]
    assert keys == ["task", "panel"]
    assert [step["key"] for step in answer["after"]["steps"]] == ["task"]
    assert "panel" not in answer["after"]["reset"]
    assert answer["after"]["reset"] == answer["change"]["reset"], "what is not the panel stays"


def test_a_hash_heard_while_the_desk_boots_that_repeats_the_address_is_not_asked_its_panel_either():
    """The router compares with what is drawn: the person's panel, not the address's."""
    answer = _run("""
press("cycle");
const same = "#task=a&panel=people&lang=ru";
const ticket = hear(same);
const change = hash.navigationChange(hash.readDeskHash("#task=a&panel=cycle"),
  hash.readDeskHash(same));
console.log(JSON.stringify({change, after: toggles.after(ticket, change),
  chosen: toggles.resolve("people")}));
""", BOOKMARK)
    assert [step["key"] for step in answer["change"]["steps"]] == ["panel"]
    assert answer["after"]["steps"] == []
    assert answer["chosen"] == "cycle"


def test_a_hash_heard_after_the_boot_asks_its_panel_until_the_person_chooses_after_it():
    answer = _run("""
toggles.resolve("people");
const change = hash.navigationChange(boot, hash.readDeskHash("#task=b&panel=run&lang=en"));
const ticket = hear("#task=b&panel=run&lang=en");
const before = toggles.after(ticket, change);
press("cycle");
const later = toggles.after(ticket, change);
console.log(JSON.stringify({change, before, later}));
""", BOOKMARK)
    assert answer["before"] == answer["change"], "no choice since the hash: the change is whole"
    assert [step["key"] for step in answer["later"]["steps"]] == ["task"]


def test_the_panel_a_task_change_resets_is_spared_when_the_person_chose_after_it_arrived():
    answer = _run("""
toggles.resolve("people");
const change = hash.navigationChange(boot, hash.readDeskHash("#task=b&lang=en"));
const ticket = hear("#task=b&lang=en");
toggles.choose("continue");
console.log(JSON.stringify({change, after: toggles.after(ticket, change)}));
""", BOOKMARK)
    assert "panel" in answer["change"]["reset"]
    assert "panel" not in answer["after"]["reset"]
    assert [step["key"] for step in answer["after"]["steps"]] == ["task"]


def test_a_hash_heard_while_the_desk_boots_that_moves_the_task_and_names_no_panel_closes_it():
    answer = _run("""
hear("#task=b&lang=en");
const closed = log.filter((entry) => entry[0] === "closeContinue").length;
hear("#task=b&lang=ru");
hear("#panel=run&lang=ru");
console.log(JSON.stringify({closed, total: log.filter((e) => e[0] === "closeContinue").length}));
""", BOOKMARK)
    assert answer == {"closed": 1, "total": 1}, "a language and a named panel close nothing here"
