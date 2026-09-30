"""The door of the project's task queue reaches the wire only as far as it has been argued for.

The boot module writes nothing (`test_desk_source.py` holds that); a press on the queue is a
person's decision, and what it writes lives in `desk-queue.js`, which reaches the transport's
mutation door only at the calls named below and only for the targets it is given. Each check is a
function over TEXT, and the table of broken doors feeds it every defect it claims to refuse, so a
check that silently stopped biting reds here rather than in a review.
"""
from __future__ import annotations

import re

import pytest

from tests.test_desk_source import PANEL, _edit
from tests.test_panel_cascade import strip_comments

QUEUE_DOOR = PANEL / "desk-queue.js"
#: The targets of the mutation door the queue's door names, in the order it names them: the two
#: writes that change the order of what waits, and the control that frees a stopped holder's slot.
WRITTEN = ("queueOrder", "queueWithdraw", "automationControl", "queue",
           "automationPreview")
#: The routes it reads, and no other: the queue, and the automation of the holder.
READ = {"queue", "automation"}
#: Everything else that reaches the wire or a session, which the queue's door does not do.
OTHER_DOORS = (r"\bfetch\s*\(", r"\bmethod\s*:", r'"POST"', r"\bXMLHttpRequest\b",
               r"\bsendBeacon\b", r"\bdropSession\b", r"\bopenStream\b", r"\bEventSource\b")


def queue_door_faults(source: str) -> list[str]:
    """Every way the queue's door reaches further than it has been argued to.

    Args:
        source: The text of `desk-queue.js`.

    Returns:
        One sentence per fault; empty when it calls the mutation door exactly for `WRITTEN` and
        reads exactly the routes of `READ`.
    """
    code = strip_comments(source)
    targets = re.findall(r'\.submit\(\s*"([A-Za-z]+)"', code)
    faults = []
    if tuple(targets) != WRITTEN:
        faults.append(f"the mutation door is called for {targets}, not for {list(WRITTEN)}")
    if len(re.findall(r"\bsubmit\b", code)) != len(WRITTEN):
        faults.append("the word submit is written other than at the named calls")
    faults += [f"reaches another door: {found.group(0)}" for pattern in OTHER_DOORS
               for found in re.finditer(pattern, code)]
    read = set(re.findall(r"\bpath\.([A-Za-z]+)\(", code))
    faults += [f"reads a route the queue does not own: path.{name}"
               for name in sorted(read - READ)]
    return faults


BROKEN = {
    "a write nobody argued for": (
        lambda text: text + '\nconst later = () => door.submit("tasks", null, {});\n',
        "is called for"),
    "a write with another target": (
        _edit('submit("queueOrder"', 'submit("tasks"'), "is called for"),
    "a write that was dropped": (_edit('door.submit("queueWithdraw", runId, body)', "body"),
                                 "is called for"),
    "a write that is not named at the call": (
        _edit('door.submit("queueOrder", null, body)', "door.submit(target, null, body)"),
        "is called for"),
    "a door of its own": (lambda text: text + '\nfetch("/command/tasks");\n', "another door"),
    "a session drop": (lambda text: text + "\ndoor.dropSession();\n", "another door"),
    "a stream": (lambda text: text + "\nconst s = door.openStream();\n", "another door"),
    "a read of another route": (_edit("path.queue()", "path.tasks()"), "does not own"),
    "a read of the holder's whole run": (
        _edit("path.automation(runId)", "path.run(runId)"), "does not own"),
    "a control that names another target": (
        _edit('submit("automationControl"', 'submit("automationAuthorize"'), "is called for"),
    "a POST method": (lambda text: text + '\nconst OPTIONS = {method: "POST"};\n',
                      "another door"),
}


def test_the_queue_door_reaches_the_mutation_door_only_as_argued_and_no_other_door():
    assert queue_door_faults(QUEUE_DOOR.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize("edit,needle", list(BROKEN.values()), ids=list(BROKEN))
def test_the_queue_door_check_refuses_each_defect_and_names_it(edit, needle):
    faults = queue_door_faults(edit(QUEUE_DOOR.read_text(encoding="utf-8")))
    assert faults, "a defective door was accepted"
    assert any(needle in fault for fault in faults), faults


def test_the_queue_door_judges_what_it_reads_with_the_queue_model_and_nothing_else():
    code = strip_comments(QUEUE_DOOR.read_text(encoding="utf-8"))
    assert re.findall(r'^import .* from "([^"]+)";', code, re.MULTILINE) == [
        "./desk-transport.js", "./desk-queue-model.js"]
    assert "projectQueue" in code and "projectHolder(" in code
