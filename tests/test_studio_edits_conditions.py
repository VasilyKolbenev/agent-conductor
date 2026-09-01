"""The reducer's condition arm, and the successor computation it replaced.

Two source circuits, and both are about a window not deciding something the
server already decided:

- **the reducer judges the word before it edits.** A condition is one of eight,
  or it is the empty string that CLEARS -- and clearing writes the key out of
  the document rather than writing a null, because absent and null are one
  answer to this contract and a stored null is not canonical JSON. A window
  composing a document the server would rewrite under it is a window that has
  invented a ninth word.
- **the run read's successors come from Python.** `decisionRows.unblocks` used
  to map every out-edge of a gate and call each one unblocked, which was true
  only while no road could carry a condition. Afterwards it would have promised
  a person that approving opens a step their approval closes. There is ONE
  successor computation in this product and it is `graph_schedule`.

Source guards rather than rendered ones for the reason this suite already
applies to the edit vocabulary: what is asserted is that the window ASKS, and a
rendered test can pass while the window asks the wrong thing and happens to
agree on the fixture in front of it.
"""
from __future__ import annotations

import re

from tests.test_studio_canvas import PANEL, _code

EDITS = PANEL / "studio-edits.js"
RUNREAD = PANEL / "studio-runread.js"


def _arm(source: str, word: str) -> str:
    """One reducer arm's body, by the edit word it answers to."""
    found = re.search(rf'"{word}": \(draft, edit\) => \{{(.*?)\n  \}},',
                      source, re.DOTALL)
    assert found, f"the reducer has no arm for {word!r}"
    return found.group(1)


# -- the reducer judges the word before it edits -------------------------------


def test_the_condition_arm_refuses_a_word_the_contract_does_not_carry():
    """Judged against the vocabulary, not against a shape or a length."""
    body = _arm(_code(EDITS), "set-edge-condition")

    assert "EDGE_CONDITIONS.includes(edit.value)" in body, body
    assert 'edit.value !== ""' in body, body
    assert "draft: null" in body, body


def test_clearing_writes_the_key_OUT_rather_than_writing_a_null():
    """Absent and empty are one answer to `settled_edge_condition`, and a
    stored `"condition": null` is not canonical JSON -- the store refuses the
    line it would write."""
    body = _arm(_code(EDITS), "set-edge-condition")

    assert "const {condition, ...rest} = edge;" in body, body
    assert 'edit.value === "" ? rest :' in body, body
    assert "null" not in body.split("moved = moved")[0].replace(
        "draft: null", ""), body


def test_an_edit_that_changes_nothing_answers_null_rather_than_unsaved():
    """The reducer's own contract: an arm that moved nothing must say so, or
    the window marks a draft dirty that nobody edited."""
    body = _arm(_code(EDITS), "set-edge-condition")

    assert "let moved = false;" in body, body
    assert 'moved = moved || (condition || "") !== edit.value;' in body, body
    assert "already opens on that" in body, body


def test_the_arm_touches_only_the_road_the_edit_names():
    """One edit names one connection, in both directions."""
    body = _arm(_code(EDITS), "set-edge-condition")

    assert "edge.from_node !== edit.fromId || edge.to_node !== edit.toId" in body
    assert "return edge;" in body, body


# -- the successors come from the server's schedule ---------------------------


def test_the_run_read_takes_its_successors_from_the_schedule(tmp_path):
    """`unblocks` reads `graph.schedule`, and the edge list is not consulted."""
    source = _code(RUNREAD)
    rows = re.search(r"export function decisionRows\(detail\) \{(.*?)\n\}",
                     source, re.DOTALL).group(1)

    assert "const schedule = isObject(graph) ? graph.schedule : null;" in rows
    assert "opensOf(schedule, node.node_id)" in rows, rows
    # The edge list is still read for the plan's own facts, but never to decide
    # what a decision unblocks.
    assert "definition.edges" not in rows, rows


def test_a_build_answering_no_schedule_states_no_successors(tmp_path):
    """It does NOT fall back to the edge list, and it does answer with the roads.

    Guessing here is the exact failure this key exists to remove, and an empty
    reading is one a person can see is empty; a wrong one is not.

    The RETURN is pinned as well, and that is not formatting: this function's
    whole job is to hand back the row's own `opens`, and a body that keeps the
    lookup and answers `[]` passes every other assertion in this module while
    the Decisions screen silently stops naming what an answer unblocks. That
    defect was found by mutation and its load-bearing witness is the browser
    one -- `test_studio_routing` reads the rendered row. This is the cheap
    tripwire beside it, so the fast suite reds too.
    """
    source = _code(RUNREAD)
    body = re.search(r"function opensOf\(schedule, nodeId\) \{(.*?)\n\}",
                     source, re.DOTALL).group(1)

    assert "if (!isObject(schedule)) return [];" in body, body
    assert "edges" not in body, body
    assert "rows(schedule.nodes)" in body, body
    assert "return isObject(row) ? rows(row.opens).filter(isObject) : [];" in (
        body), body


def test_each_unblocked_step_carries_the_word_the_road_opens_on():
    """The one fact a bare edge list cannot state."""
    rows = re.search(r"export function decisionRows\(detail\) \{(.*?)\n\}",
                     _code(RUNREAD), re.DOTALL).group(1)

    assert 'condition: typeof row.condition === "string" ? row.condition : null'\
        in rows, rows
    assert "node_id: row.to_node" in rows, rows


def test_clearing_a_binding_clears_everything_that_depended_on_it():
    """Three fields go with the role, and the contract is why.

    `TemplateNode` refuses a verifier, an evidence requirement and a failure
    policy on a step that binds no role of its own -- a step that carries
    nothing out has nothing to verify and cannot fail. Leaving any of them
    behind would make a draft unsavable by CLEARING a field, and the person
    would meet it as a refusal about a control they did not touch.

    None of the three had a guard here before the policy arrived; adding one
    field without one would have widened a hole rather than closed it.
    """
    body = re.search(r"function withBinding\(node, name, value\) \{(.*?)\n\}",
                     _code(EDITS), re.DOTALL).group(1)

    for field in ("verifier_role_id", "required_evidence", "failure_policy"):
        assert f"delete next.{field};" in body, field
    # And they go only when the binding itself is being cleared.
    assert 'value === null || value === ""' in body, body
