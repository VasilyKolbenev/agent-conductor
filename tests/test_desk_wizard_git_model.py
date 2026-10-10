"""The git block as the wizard's model carries it: the slice, the door, the vocabulary.

`tests/test_desk_wizard_git_run.py` drives the seam on its own. Here the REAL model stands round it.
"""
from __future__ import annotations

from typing import Any

from tests.desk_wizard_node import PRELUDE, fixture, run_js

MODULES = {"wiz": "desk-wizard-model.js", "g": "desk-wizard-git.js"}
DATA: dict[str, Any] = {"unborn": fixture("wizard", "git_unborn.json")}
#: A wizard that has read git, with the switch of the confirm shut or open.
STAND = PRELUDE + """
const onRead = (name, door = true, over = {}) => {
  const state = reply(opened(started({actor: "Anna", ...over})), "git", d[name]);
  return {...state, git: {...state.git, open: door}};
};
"""


def js(body: str) -> Any:
    return run_js(STAND + body, DATA, modules=MODULES)


def test_the_wizard_opens_with_the_git_slice_made_from_the_switch_literal():
    out = js("""
      const state = open({actor: "Anna"});
      show({git: state.git, literal: g.FIRST_COMMIT_CONFIRM_OPEN,
        frozen: Object.isFrozen(state.git)});
    """)
    assert out["git"] == {"open": out["literal"], "door": True, "panel": None, "mode": None,
                          "preview": None, "list": False, "seq": 0, "sending": None,
                          "result": None}
    assert isinstance(out["literal"], bool) and out["frozen"] is True


def test_a_host_whose_transport_has_no_door_for_the_setup_route_says_so_at_the_opening():
    out = js("""
      const opened_ = (setupDoor) => open({actor: "Anna", setupDoor}).git.door;
      const state = reply(opened(started({actor: "Anna", setupDoor: false})), "git", d.unborn);
      const shut = {...state, git: {...state.git, open: true}};
      const kinds = ["init", "exclude", "preview", "confirm", "continue"];
      show({named: [opened_(true), opened_(false), opened_(undefined)],
        blocks: kinds.map((kind) => wiz.pressBlock(shut, kind))});
    """)
    assert out["named"] == [True, False, True], "only an explicit false closes it"
    assert out["blocks"] == ["door_missing"] * 5


def test_the_models_exports_carry_the_block_vocabulary_and_its_facts():
    out = js("""
      const state = onRead("unborn");
      show({words: Object.keys(wiz.FIRST_WORDS).sort(), facts: typeof wiz.firstFacts,
        block: wiz.pressBlock(state, "confirm"), shown: wiz.firstFacts(state).shown});
    """)
    assert out["words"] == sorted(["why", "lost", "busy", "done", "unsent", "next", "codes",
                                   "manual", "warning", "pending", "mode"])
    assert out["facts"] == "function"
    assert out["block"] == "not_offered", "the confirm exists only inside the opened panel"
    assert out["shown"]["panel"] is False
