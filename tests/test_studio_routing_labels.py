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

    The sentence is DECLARED in `studio-runwords.js` and spent here. It moved
    there when a second screen had to say it -- the Decisions screen, about a
    gate that cannot be answered yet -- and one rule written out in two files
    is one rule that can be said two ways. What this holds is unchanged: the
    Runs screen states the AND-only rule where a step is blocked, and states
    nothing weaker anywhere.
    """
    runs = _code(PANEL / "studio-runs.js")
    words = _code(PANEL / "studio-runwords.js")
    sentence = re.search(r'ALL_ROADS = "(.+?)";', words, re.DOTALL)
    assert sentence, "no module declares the join rule"
    assert sentence.group(1).replace('"\n  + "', "").startswith(
        "ALL incoming roads must open")
    assert "ALL_ROADS," in runs, "the Runs screen no longer reads the join rule"
    assert "note(ALL_ROADS)" in _plan_standing(runs)
    assert "waiting for a predecessor" not in runs.lower()


def _plan_standing(runs: str) -> str:
    """The body of the one function that says where a step stands.

    Read by name and by SIGNATURE, and the miss is an assertion rather than an
    ``AttributeError`` on ``None``: this reader used to end in one, so a
    renamed parameter reported "'NoneType' has no attribute 'group'" instead of
    naming the function it could not find.

    The signature is pinned because it is the guard's own subject. It has twice
    been the wrong document: a `phase`, then the whole runtime row. Neither can
    answer the question below -- the phase reports the node's CURRENT action,
    and the current action is the LAST proposal or request naming it. What is
    handed in now is the ANSWER, computed from the records next door.
    """
    body = re.search(
        r"function planStanding\(item, standing, flying\) \{(.*?)\n\}",
        runs, re.DOTALL)
    assert body is not None, (
        "studio-runs.js declares no planStanding(item, standing, flying)")
    return body.group(1)


def test_a_blocked_step_with_nothing_else_to_say_says_which_of_the_two_it_is():
    """The bare `plan: blocked` chip, and the two situations behind it.

    A `blocked` row naming no road, awaiting no document and with attempts left
    is one of exactly two things and `graph_schedule` produces no third: an
    attempt on it has not answered (`attempt_in_flight`), or a halt rewrote
    every runnable row to blocked (`_stop_runnable`). Before this the row drew
    the word and stopped, and a person could not tell a worker that is running
    from a run that has stopped.

    Both sentences are held, and so is what CHOOSES between them.
    """
    runs = _code(PANEL / "studio-runs.js")
    owed = re.search(r"function stillOwed\(flying\) \{(.*?)\n\}", runs,
                     re.DOTALL)
    assert owed is not None, "studio-runs.js says nothing about a bare blocked"
    said = owed.group(1)
    assert "An attempt on this step is still in flight; the plan offers it " \
        "again \"\n      + \"only after that attempt answers." in said, said
    assert "Nothing further is offered in this run: it was halted." in said
    # And it is REACHED: a sentence nothing calls is a row that still says
    # nothing. The call sits on the branch where no road and no document is
    # named, which is the branch that used to fall through.
    assert "} else if (!awaited.length) {\n      item.append(note(stillOwed(" \
        "flying)));" in _plan_standing(runs)


def test_an_attempt_is_in_flight_by_the_records_and_never_by_the_phase():
    """The runtime phase answers a different question, and it answered it twice.

    `graph_projection._current_action` is the LAST proposal or request naming a
    node, and the phase reports how far THAT got. So `observed` is answered for
    an attempt whose result has already landed -- and a proposal appended over
    an unanswered request, which the propose door admits because it holds no
    schedule check, pushes the phase back to `proposed` while a worker is still
    executing. The screen said the run had been halted while its worker ran.

    What is asked now is `graph_schedule.attempt_in_flight`'s own question,
    spelled the same way: a request naming this step whose `action_id` no
    result closes. Judged by `action_id` and never by "some request, some
    result" -- two attempts on one step are two identities, and the weaker rule
    would call the second finished the moment the first reported.

    Held on the reader AND on the screen that spends it, because they fail
    apart: a correct reader nothing calls leaves the same wrong sentence up.
    """
    read = _code(PANEL / "studio-runread.js")
    body = re.search(
        r"export function attemptInFlight\(detail, nodeId\) \{(.*?)\n\}",
        read, re.DOTALL)
    assert body is not None, "no module reads an attempt out of the records"
    said = body.group(1)
    assert 'row.record_type === "action_result"' in said, said
    assert 'row.record_type === "action_request"' in said, said
    assert "row.record.node_id === nodeId" in said, said
    assert "!answered.has(row.record.action_id)" in said, said
    # The phase and the outcome are not consulted anywhere in it.
    for gone in (".phase", ".outcome", "IN_FLIGHT"):
        assert gone not in said, gone

    runs = _code(PANEL / "studio-runs.js")
    assert 'import {attemptInFlight} from "./studio-runread.js";' in runs
    # The RUNTIME row's id, never the plan node's: a runtime row the definition
    # does not name arrives with an empty node, and an absent id would match
    # every unbound request in the journal.
    assert "planStanding(item, plan, attemptInFlight(detail, runtime.node_id));" \
        in runs, runs
    # And the phase-based reading is gone from this screen entirely.
    assert "IN_FLIGHT" not in runs, "the phase list survived the correction"
    assert "function inFlight(" not in runs


def test_a_settled_step_says_the_plan_offers_it_nothing_further():
    """`plan: settled` is not `plan: waiting`, and the row now says which.

    The word alone reads as a position rather than as an ending, and the one
    thing that reopens a settled step is a loop -- so that is stated, because
    it is the only road back and a person looking for one would otherwise look
    for a control that is never coming.
    """
    body = _plan_standing(_code(PANEL / "studio-runs.js"))
    assert 'standing.state === "settled"' in body, body
    assert "This step has settled; the plan offers it no further " in body
    assert "attempt unless a loop reopens it." in body


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
