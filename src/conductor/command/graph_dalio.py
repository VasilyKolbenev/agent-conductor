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
"""
from __future__ import annotations

from .contracts import ContractError
from .graph_definition import DALIO_STAGES, GraphDefinition

#: The stage a Dalio loop reopens, and the only one it may.
FEEDBACK_STAGE = "identify"
#: The stage that owns the template's single effect-capable node.
EFFECT_STAGE = "do"


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
