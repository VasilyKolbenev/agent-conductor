"""The routing labels that left the completeness register, and not the screen.

Split out of ``test_studio_completeness.py`` when that module crossed the
project's line cap, and along that module's own seam rather than a convenient
line. Its census has three steps, and step 2 is the one that produces files:
when a field becomes real its label leaves ``UNSUPPORTED_FIELDS``, and a
POSITIVE witness has to arrive in its place holding that it did not leave the
screen with it. Deleting a control entirely would satisfy the census, and those
witnesses are the only thing that refuses it.

The four here are one circuit -- the routing vocabulary reaching a person:

- a road out of a step offers the words that step's own kind can produce;
- the edge panel offers the SAME control, exported rather than rebuilt;
- decision routing is a READING of the roads already drawn, never a second
  authority over one edge;
- and the two Runs-screen sentences that stop the plan from being read as
  something it does not say -- joins are AND-only, and `complete` is not a pass.

They are source guards for this suite's standing reason: what is asserted is
that the window ASKS the right layer, and a rendered test can pass while the
window asks the wrong one and happens to agree with the fixture in front of it.
The rendered halves live in ``browser_tests/test_studio_routing.py``.
"""
from __future__ import annotations

import re

from tests.test_studio_canvas import INSPECTOR, PANEL, _code


def test_a_connection_offers_the_words_its_own_source_can_produce():
    """`Edge conditions` became a control, one per road out of the step.

    The words offered are the family the SOURCE's kind can produce, read from
    the vocabulary rather than typed beside the control -- and a step that
    carries out no work is offered none at all, because the contract refuses a
    condition on its roads and a select whose every use is refused on save is
    worse than no select.
    """
    inspector = _code(*INSPECTOR)
    control = re.search(r"function conditionControl\(form, edge\) \{(.*?)\n\}",
                        inspector, re.DOTALL).group(1)
    assert "conditionWords(form.node)" in control, control
    assert "carries out no work" in control, control
    assert 'element("select"' in control, control
    assert 'type: "set-edge-condition"' in control, control
    assert "editable(control, form)" in control, control
    words = re.search(r"function conditionWords\(node\) \{(.*?)\n\}",
                      inspector, re.DOTALL).group(1)
    assert 'node.kind === "task" && !node.capability' in words, words
    assert "CONDITIONS_BY_KIND[node.kind]" in words, words


def test_the_edge_panel_offers_that_same_control_and_not_a_second_one():
    """`Condition` became the SAME select, exported rather than rebuilt.

    Two surfaces building one control from two copies of one vocabulary is how
    they come to offer different words for one road.
    """
    inspector = _code(*INSPECTOR)
    assert "edgeConditionRow(box, form, parts[0], parts[1]);" in inspector
    body = re.search(
        r"export function edgeConditionRow\(box, form, fromId, toId\) \{(.*?)\n\}",
        inspector, re.DOTALL).group(1)
    assert "conditionWords(source)" in body, body
    assert 'type: "set-edge-condition"' in body, body
    assert "editable(control, form)" in body, body
    # A road this drawing does not carry is SAID, never offered a control.
    assert "does not carry that road" in body, body


def test_decision_routing_became_a_reading_and_not_a_second_control():
    """It states where each answer sends the run, off the roads already drawn.

    A control here would be a second authority over one edge. The reading is
    derived from the node's own out-edges, and the three cases a person can
    actually be in are each said: a gate that routes, a gate whose every answer
    opens the same step, and a step that is not a gate at all.
    """
    inspector = _code(*INSPECTOR)
    body = re.search(r"function decisionRouting\(box, form\) \{(.*?)\n\}",
                     inspector, re.DOTALL).group(1)
    assert 'form.node.kind !== "gate"' in body, body
    assert "only a gate's answer routes" in body, body
    assert "every answer opens" in body, body
    assert 'typeof edge.condition === "string"' in body, body
    # Read-only: it writes no edit of any kind.
    assert "onEdit" not in body, body
    assert "decisionRouting(box, form);" in inspector


def test_a_blocked_join_says_that_ALL_incoming_roads_are_required():
    """Joins are AND-only, and the screen may not imply otherwise.

    "Waiting for a predecessor" reads as ANY. A person told that would expect
    the step to start as soon as one branch arrived, and would read the plan as
    doing something it never does.
    """
    runs = _code(PANEL / "studio-runs.js")
    sentence = re.search(r'const ALL_ROADS = "([^"]+)"', runs)
    assert sentence, "the Runs screen no longer states the join rule"
    assert sentence.group(1).startswith("ALL incoming roads must open")
    body = re.search(r"function planStanding\(item, standing\) \{(.*?)\n\}",
                     runs, re.DOTALL).group(1)
    assert "note(ALL_ROADS)" in body, body
    assert "waiting for a predecessor" not in runs.lower()


def test_the_plan_word_is_never_drawn_as_a_success():
    """`complete` says the plan has nothing left to open, never that it worked.

    A run that exhausted every retry and a run that was approved reach the same
    word, so the chip is the neutral channel and the two facts that tell them
    apart are stated beside it.
    """
    runs = _code(PANEL / "studio-runs.js")
    body = re.search(r"function planWord\(graph\) \{(.*?)\n\}",
                     runs, re.DOTALL).group(1)
    assert 'chip("none", word)' in body, body
    assert 'chip("pass"' not in body, body
    assert "bound reached" in body, body
    assert "Last gate answer" in body and "Last outcome" in body, body
    assert "does NOT mean the run " in runs
