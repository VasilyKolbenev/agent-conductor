"""A warning that never refuses a publish, and the interaction it names.

`attempt_bound` and a loop's `bound` are each correct on their own and can
contradict each other. The bound is spent per step across the WHOLE run --
every `action_request` naming that step, never reset per lap -- while a loop
asks the step to settle once per lap. So an effecting step whose bound is below
its loop's bound can settle fewer times than the loop needs, and the last lap
can never complete: the run stalls, which is a real word this build produces.

Neither number is wrong, so nothing refuses them. What the product owes is to
SAY so, once, before the revision is published -- and to keep saying yes to the
publish, because the document is legal and the judgement belongs to whoever
drew it.

Three claims, and the third is the one most likely to be undone by someone
trying to help:

- the sentence is exact, and it is `may`, not `will`;
- it fires on the interaction and on nothing else -- not on a bound alone, not
  on a loop alone, not on a step outside the body, not on a step that cannot
  act;
- **`publishable` stays true while it stands.** A warning is not a diagnostic.
  `DIAGNOSTIC_CODES` is unchanged, and a build that folded warnings into the
  publish gate would have turned advice into a refusal.
"""
from __future__ import annotations

import pytest

from conductor.command.graph_definition import GraphEdge, GraphLoop
from conductor.command.graph_template import GraphTemplate, TemplateNode
from conductor.command.template_store import TemplateStore
from conductor.command.workflow_draft import (
    BOUND_WARNING,
    DIAGNOSTIC_CODES,
    WorkflowDraft,
    publish_warnings,
    workflow_state,
)

WORKFLOW = "warned"
NOW = "2026-08-31T09:00:00Z"


def a_document(*, attempt_bound=None, loop_bound=3, capability="dispatch",
               inside=True) -> dict:
    """A gate, one step behind it, and a loop that reopens the gate.

    The step is effecting by default and sits inside the loop's body; the two
    keyword arguments are what each witness moves.
    """
    steps = [
        TemplateNode(node_id="gate", kind="gate", title="Gate",
                     gate_id="gate-1"),
        TemplateNode(node_id="do", kind="task", title="Do",
                     role_id=None if capability is None else "doer",
                     capability=capability, attempt_bound=attempt_bound),
        TemplateNode(node_id="again", kind="loop", title="Again",
                     loop=GraphLoop(bound=loop_bound, back_to="gate")),
    ]
    edges = [GraphEdge(from_node="gate", to_node="do"),
             GraphEdge(from_node="do", to_node="again")]
    if not inside:
        # The loop reopens ITSELF's predecessor only, so `do` hangs off the
        # gate and reaches the loop by no road: it is in no body.
        edges = [GraphEdge(from_node="gate", to_node="do"),
                 GraphEdge(from_node="gate", to_node="again")]
    template = GraphTemplate(template_id=WORKFLOW, revision=1, title="Warned",
                             nodes=tuple(steps), edges=tuple(edges))
    document = template.as_dict()
    for name in ("template_id", "revision"):
        document.pop(name)
    return document


def warnings_for(**changes) -> list[str]:
    return publish_warnings(a_document(**changes), workflow_id=WORKFLOW,
                            revision=1)


# -- the sentence, and that it is the owner's own words -----------------------


def test_the_warning_is_the_one_sentence_this_build_emits():
    """Pinned word for word. `may`, never `will`: whether the step is reached on
    every pass depends on the conditions its roads carry, and a branch can end
    the run before the bounded step is asked for again."""
    assert BOUND_WARNING == (
        "Attempt bound may be exhausted before the loop's final pass.")
    assert warnings_for(attempt_bound=2) == [BOUND_WARNING]


# -- it fires on the interaction and on nothing else --------------------------


def test_a_bound_below_the_loops_bound_is_warned_about():
    assert warnings_for(attempt_bound=2, loop_bound=3) == [BOUND_WARNING]


@pytest.mark.parametrize("attempt_bound, loop_bound", [(3, 3), (4, 3), (9, 2)])
def test_a_bound_at_or_above_the_loops_bound_is_not(attempt_bound, loop_bound):
    """The step can settle every lap the loop asks for, so there is nothing to
    say."""
    assert warnings_for(attempt_bound=attempt_bound,
                        loop_bound=loop_bound) == []


def test_a_step_that_names_no_bound_is_not_warned_about():
    """A step naming no ceiling constrains nothing -- which is what every plan
    written before ceilings existed says."""
    assert warnings_for(attempt_bound=None) == []


def test_a_step_that_cannot_act_is_not_warned_about():
    """The interaction is about EFFECTING work. A review step's bound is a
    ceiling like any other and stalls nothing an operator cannot retry."""
    assert warnings_for(attempt_bound=1, capability="review") == []


def test_a_step_outside_every_loop_body_is_not_warned_about():
    """A bound only meets a loop's bound where the loop reopens the step."""
    assert warnings_for(attempt_bound=1, inside=False) == []


def test_a_document_that_does_not_construct_warns_about_nothing():
    """Its diagnostics are the answer; advice about a revision that cannot
    exist would be noise on top of an error."""
    broken = a_document(attempt_bound=1)
    broken["edges"] = [{"from_node": "gate", "to_node": "nowhere"}]

    assert publish_warnings(broken, workflow_id=WORKFLOW, revision=1) == []


# -- a warning never refuses a publish ----------------------------------------


def test_a_draft_carrying_the_warning_is_still_publishable(tmp_path):
    """The whole point. A warning is advice; only a diagnostic stops a publish.

    `publishable` is asserted true WITH the warning standing, and the
    diagnostics list is asserted empty beside it -- so a build that folded the
    two together would red here rather than quietly refusing a legal document.
    """
    templates = TemplateStore(tmp_path)
    templates.save_draft(WorkflowDraft(
        workflow_id=WORKFLOW, saved_at=NOW,
        document=a_document(attempt_bound=1)))

    state = workflow_state(templates, WORKFLOW)

    assert state["warnings"] == [BOUND_WARNING]
    assert state["diagnostics"] == []
    assert state["publishable"] is True


def test_the_warning_is_not_a_diagnostic_code():
    """Two vocabularies, and this one stays the size it was."""
    assert DIAGNOSTIC_CODES == {"template_refused", "contract_refused"}
    assert BOUND_WARNING not in DIAGNOSTIC_CODES


def test_a_workflow_with_no_draft_states_no_warnings(tmp_path):
    """An empty list rather than an absent key: a reader that had to tell "no
    warnings" from "old server" by the shape would be guessing."""
    state = workflow_state(TemplateStore(tmp_path), "nobody-drew")

    assert state["warnings"] == []
    assert state["publishable"] is False
