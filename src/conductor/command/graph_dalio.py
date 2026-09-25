"""The Dalio template: the default graph's extra rules, and only its own.

``graph_definition`` holds what EVERY graph must be -- an acyclic arrangement of
tasks, gates and loops where anything that can act stands behind a gate. That is
the product's floor, and it is deliberately low: December Command exists to
build different multi-harness graphs, and a contract that demanded five named
stages made every one of them a Dalio graph.

So the template lives here, beside the graph rather than inside it. A graph
built to this shape satisfies both; a graph built to some other shape satisfies
the base contract alone and is no less valid for it.

What the template adds, and why each is a product rule rather than a structural
one:

- **five stages, one node each, all present.** The five are a method of working,
  not a data shape: goal, identify problems, diagnose root causes, design the
  plan, do. A reader numbers them by their order in ``DALIO_STAGES``.
- **exactly one bounded loop, home to identify.** Turning problems into progress
  is the whole point of the cycle; a second feedback relation would be a second
  cycle by another name, and returning anywhere else would skip the step that
  finds out what actually went wrong.
- **the effecting node is the one in the do stage.** The base contract already
  puts every acting node behind a gate. The template says WHICH node acts, so a
  Dalio graph cannot quietly grow a second place where work happens.

The template validates; it does not repair. A graph that fails it is returned to
whoever composed it, because a template that edited a plan to fit itself would
be deciding something a Human already decided.

**Revision 5 adds a correction road, and is judged by its own check.** The
independent checker's rejection of `do` is corrected by `do` itself, once, under
the same authorization: `do -> correct` on `on_failed`, a loop home to `do`. That
is a second loop, so revision 5 is NOT the one-loop shape above, and the check
above stays exactly as strict as it was for revisions 1-4 rather than being
widened to admit it. ``validate_dalio_correction_template`` holds revision 5 to
every rule above except the loop count, and to the shape of both loops: the
outer one still returns to identify through the human result decision, and the
correction loop is entered by `do`'s own failure and by nothing else.
"""
from __future__ import annotations

from .contracts import ContractError
from .graph_definition import DALIO_STAGES, GraphDefinition

#: The stage a Dalio loop reopens, and the only one it may.
FEEDBACK_STAGE = "identify"
#: The stage that owns the template's single effect-capable node.
EFFECT_STAGE = "do"
#: The human answer that reopens the outer cycle, and the only road into it.
REOPEN_CONDITION = "on_changes_requested"


class DalioTemplateError(ContractError):
    """A graph is well-formed, but it is not the Dalio default template."""


def _staged(definition: GraphDefinition) -> dict[str, str]:
    claimed = definition.stages()
    shared = sorted(stage for stage, names in claimed.items() if len(names) > 1)
    if shared:
        raise DalioTemplateError(
            f"stage(s) {shared!r} are claimed by more than one node; the Dalio "
            "template carries one node per stage")
    missing = [stage for stage in DALIO_STAGES if stage not in claimed]
    if missing:
        raise DalioTemplateError(
            f"graph is missing stage node(s) {missing!r}; the Dalio template "
            f"carries all of {list(DALIO_STAGES)!r}")
    return {stage: names[0] for stage, names in claimed.items()}


def _one_loop_home_to_identify(definition: GraphDefinition, staged: dict[str, str]) -> None:
    loops = [node for node in definition.nodes if node.loop is not None]
    if len(loops) != 1:
        raise DalioTemplateError(
            f"graph carries {len(loops)} loops; the Dalio template turns problems "
            "into progress through exactly one bounded cycle")
    loop = loops[0]
    assert loop.loop is not None
    if loop.loop.back_to != staged[FEEDBACK_STAGE]:
        raise DalioTemplateError(
            f"loop {loop.node_id!r} reopens {loop.loop.back_to!r}; the Dalio "
            f"template returns to the {FEEDBACK_STAGE!r} stage node "
            f"{staged[FEEDBACK_STAGE]!r}, where problems are found again")


def _only_do_acts(definition: GraphDefinition, staged: dict[str, str]) -> None:
    acting = sorted(node.node_id for node in definition.nodes if node.effecting)
    stray = [name for name in acting if name != staged[EFFECT_STAGE]]
    if stray:
        raise DalioTemplateError(
            f"node(s) {stray!r} can act; in the Dalio template only the "
            f"{EFFECT_STAGE!r} stage node {staged[EFFECT_STAGE]!r} changes the world")


def validate_dalio_template(definition: GraphDefinition) -> GraphDefinition:
    """Prove one well-formed graph is also the Dalio default; return it unchanged.

    The definition is handed back rather than rebuilt so a caller can write
    ``graph = validate_dalio_template(graph)`` without wondering whether the
    object it holds is still the one it composed.
    """
    if type(definition) is not GraphDefinition:
        raise DalioTemplateError(
            "the Dalio template validates exactly a GraphDefinition; a subclass "
            "may answer for itself and is not accepted here")
    staged = _staged(definition)
    _one_loop_home_to_identify(definition, staged)
    _only_do_acts(definition, staged)
    return definition


def is_dalio_template(definition: GraphDefinition) -> bool:
    """Whether a graph is the default template, without raising to find out."""
    try:
        validate_dalio_template(definition)
    except ContractError:
        return False
    return True


def _into(definition: GraphDefinition, node_id: str) -> list:
    return [edge for edge in definition.edges if edge.to_node == node_id]


def _two_loops_each_with_its_home(definition: GraphDefinition, staged: dict[str, str]) -> None:
    """Exactly two loops: the outer one home to identify, the correction one home to do."""
    loops = [node for node in definition.nodes if node.loop is not None]
    homes = sorted(node.loop.back_to for node in loops)
    expected = sorted((staged[FEEDBACK_STAGE], staged[EFFECT_STAGE]))
    if len(loops) != 2 or homes != expected:
        raise DalioTemplateError(
            f"graph carries loops home to {homes!r}; the corrected Dalio template carries "
            f"exactly two, home to {staged[FEEDBACK_STAGE]!r} and to {staged[EFFECT_STAGE]!r}")
    doer = staged[EFFECT_STAGE]
    nodes = {node.node_id: node for node in definition.nodes}
    outer = next(node for node in loops if node.loop.back_to == staged[FEEDBACK_STAGE])
    entries = _into(definition, outer.node_id)
    if len(entries) != 1 or entries[0].condition != REOPEN_CONDITION \
            or nodes[entries[0].from_node].kind != "gate":
        raise DalioTemplateError(
            f"loop {outer.node_id!r} must be entered only by a human gate's "
            f"{REOPEN_CONDITION!r} answer; the cycle reopens by decision, not by itself")
    correction = next(node for node in loops if node.loop.back_to == doer)
    entries = _into(definition, correction.node_id)
    if len(entries) != 1 or (entries[0].from_node, entries[0].condition) != (doer, "on_failed"):
        raise DalioTemplateError(
            f"loop {correction.node_id!r} must be entered only by {doer!r} failing; a "
            "correction that anything else can reach is not the correction of a rejection")
    if correction.loop.bound < 2:
        raise DalioTemplateError(
            f"loop {correction.node_id!r} is bounded at {correction.loop.bound}; a correction "
            "road that allows no second pass of the work corrects nothing")
    leaving = sorted((edge.condition, nodes[edge.to_node].kind)
                     for edge in definition.edges if edge.from_node == doer)
    if leaving != [("on_failed", "loop"), ("on_succeeded", "gate")]:
        raise DalioTemplateError(
            f"{doer!r} leaves by {leaving!r}; in the corrected Dalio template it reaches a human "
            "gate only on success and its correction loop only on failure")


def validate_dalio_correction_template(definition: GraphDefinition) -> GraphDefinition:
    """Prove one well-formed graph is the corrected Dalio default (revision 5); return it unchanged.

    Every rule of ``validate_dalio_template`` holds -- five stages, one node
    each, only `do` acts -- except that there are two loops, each checked for its
    home and its only way in, and `do`'s success and failure each have one road.
    """
    if type(definition) is not GraphDefinition:
        raise DalioTemplateError(
            "the Dalio template validates exactly a GraphDefinition; a subclass "
            "may answer for itself and is not accepted here")
    staged = _staged(definition)
    _two_loops_each_with_its_home(definition, staged)
    _only_do_acts(definition, staged)
    return definition


def is_dalio_correction_template(definition: GraphDefinition) -> bool:
    """Whether a graph is the corrected default (revision 5), without raising to find out."""
    try:
        validate_dalio_correction_template(definition)
    except ContractError:
        return False
    return True
