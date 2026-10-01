"""The one write the desk's boot module hands on: the continue-after flag's door.

The boot module writes nothing (`test_desk_source.py` holds that); the continue-after flag is a
person's decision, and its write lives in `desk-flag.js`, which reaches the transport's mutation
door ONCE and names ONE target. Each check below is a function over TEXT, and the table of broken
doors feeds it every defect it claims to refuse, so a check that silently stopped biting reds
here rather than in a review.
"""
from __future__ import annotations

import re

import pytest

from tests.test_desk_source import PANEL, _edit
from tests.test_panel_cascade import strip_comments

FLAG_DOOR = PANEL / "desk-flag.js"
#: The modules that may call the mutation door: the transport that owns it and the doors that each
#: name their own closed list of targets (the queue's is held by `test_desk_queue_door_source.py`,
#: and the run writer's single shared-door call by `test_desk_source.py`).
DOORS = ("desk-transport.js", "desk-flag.js", "desk-queue.js", "desk-flow-host.js",
         "desk-run-write-host.js")
#: Everything else that reaches the wire or a session, which the flag's door does not do.
FLAG_OTHER_DOORS = (r"\bfetch\s*\(", r"\bmethod\s*:", r'"POST"', r"\bXMLHttpRequest\b",
                    r"\bsendBeacon\b", r"\bdropSession\b", r"\bopenStream\b", r"\bEventSource\b")


def flag_door_faults(source: str) -> list[str]:
    """Every way the flag's door reaches further than its one write and its one read.

    Args:
        source: The text of `desk-flag.js`.

    Returns:
        One sentence per fault; empty when it calls the mutation door once, for one target.
    """
    code = strip_comments(source)
    targets = re.findall(r'\.submit\(\s*"([A-Za-z]+)"', code)
    faults = []
    if targets != ["autoContinue"]:
        faults.append(f"the mutation door is called for {targets}, not for autoContinue once")
    if len(re.findall(r"\bsubmit\b", code)) != 1:
        faults.append("the word submit is written other than at the one call")
    faults += [f"reaches another door: {found.group(0)}" for pattern in FLAG_OTHER_DOORS
               for found in re.finditer(pattern, code)]
    read = set(re.findall(r"\bpath\.([A-Za-z]+)\(", code))
    faults += [f"reads a route the flag does not own: path.{name}"
               for name in sorted(read - {"autoContinue"})]
    return faults


FLAG_BROKEN = {
    "a second target": (
        _edit('"autoContinue", null', '"autoContinue", null);\n  door.submit("tasks", null'),
        "not for autoContinue once"),
    "another target": (_edit('submit("autoContinue"', 'submit("tasks"'), "not for autoContinue"),
    "a door of its own": (lambda text: text + '\nfetch("/command/tasks");\n', "another door"),
    "a session drop": (lambda text: text + "\ndoor.dropSession();\n", "another door"),
    "a stream": (lambda text: text + "\nconst s = door.openStream();\n", "another door"),
    "a read of another route": (_edit("path.autoContinue()", "path.tasks()"),
                                "does not own"),
}


def test_the_flag_door_reaches_the_mutation_door_once_for_one_target_and_no_other_door():
    assert flag_door_faults(FLAG_DOOR.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize("edit,needle", list(FLAG_BROKEN.values()), ids=list(FLAG_BROKEN))
def test_the_flag_door_check_refuses_each_defect_and_names_it(edit, needle):
    faults = flag_door_faults(edit(FLAG_DOOR.read_text(encoding="utf-8")))
    assert faults, "a defective door was accepted"
    assert any(needle in fault for fault in faults), faults


def test_no_desk_module_but_the_transport_and_the_flag_door_names_the_mutation_door():
    """The boot module and every module that draws hand a press to a handler; none of them
    calls the transport's `submit`. The wizard's own modules are lane D2's and ask the host."""
    for path in sorted(PANEL.glob("desk*.js")):
        if path.name in DOORS or path.name.startswith("desk-wizard"):
            continue
        assert not re.search(r"\.submit\(", strip_comments(path.read_text(encoding="utf-8"))), (
            path.name)
