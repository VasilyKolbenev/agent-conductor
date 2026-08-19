"""Derive the frozen ALPHA-3 graph artifact the Fable UI lane consumes.

Nothing here is hand-written. The canonical Dalio graph is BUILT through the
production contract -- so a document that survives this module is one the
contract accepts, and a contract change that would have rejected it reds here
rather than in a browser.

The document is written to ``tests/fixtures/alpha3_dalio_definition.json`` once
and then re-derived and compared on every run by
``tests/test_command_graph_definition.py``, so production drifting away from the
frozen shape reds instead of quietly handing the UI lane a stale one.

It carries exactly two things: the definition as the wire will spell it, and the
digest the contract computes for it. Runtime facts are absent on purpose -- the
projection is a separate document with a separate life, and splicing them here
would freeze the splice the Cockpit's own adapter is supposed to own.
"""
from __future__ import annotations

import json
from pathlib import Path

from conductor.command.contracts import canonical_json
from conductor.command.graph_dalio import validate_dalio_template
from conductor.command.graph_definition import (
    GraphDefinition,
    GraphEdge,
    GraphLoop,
    GraphNode,
    GraphResource,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
ARTIFACTS = ("alpha3_dalio_definition",)

#: Fixed so the derived document is reproducible: the same build twice is the
#: same bytes, which is what makes an equality pin meaningful.
CREATED_AT = "2026-08-19T09:00:00Z"
GRAPH_ID = "graph-dalio"
RUN_ID = "run-001"
INSTANCE_ID = "claude-dev"
#: The effecting capability, spelled as the wire spells it. The contract's own
#: ``EFFECTING_CAPABILITIES`` and the runtime's ``DISPATCH_CAPABILITY`` are
#: pinned equal by a test; this is the third reader of that one word.
DISPATCH = "dispatch"


def _task(node_id: str, title: str, stage: str, capability: str = "evidence",
          **changes) -> GraphNode:
    body = dict(node_id=node_id, kind="task", title=title, stage=stage,
                instance_id=INSTANCE_ID, capability=capability)
    body.update(changes)
    return GraphNode(**body)


def dalio_nodes() -> tuple[GraphNode, ...]:
    """Five stages, a Human gate before the one effecting step, a result gate.

    Do is the only node bound to an effecting capability, and the only road into
    it comes from the Confirm gate. The loop reopens the work at Identify and
    executes nothing itself: a new pass is a new proposal, a new Confirm and a
    new attempt, none of which this document may describe.
    """
    return (
        _task("goal", "Goal", "goal"),
        _task("identify", "Identify Problems", "identify"),
        _task("diagnose", "Diagnose Root Causes", "diagnose", capability="review"),
        _task("design", "Design the Plan", "design"),
        GraphNode(node_id="confirm-gate", kind="gate",
                  title="Human Gate - Confirm Do", gate_id="gate-confirm-do"),
        _task("do", "Do", "do", capability=DISPATCH,
              arguments={"work_item_id": "work-001", "instruction_ref": "instr-001"},
              resources=(GraphResource(kind="model", name="sonnet"),
                         GraphResource(kind="sandbox", name="project-root"))),
        GraphNode(node_id="result-gate", kind="gate", title="Result Gate",
                  gate_id="gate-result"),
        GraphNode(node_id="retry-loop", kind="loop",
                  title="Turn problems into progress",
                  loop=GraphLoop(bound=3, back_to="identify")),
    )


def dalio_edges() -> tuple[GraphEdge, ...]:
    """A strict chain. The one feedback relation is the loop's, not an edge."""
    return tuple(GraphEdge(from_node=a, to_node=b) for a, b in (
        ("goal", "identify"), ("identify", "diagnose"), ("diagnose", "design"),
        ("design", "confirm-gate"), ("confirm-gate", "do"),
        ("do", "result-gate"), ("result-gate", "retry-loop")))


def dalio_definition(**changes) -> GraphDefinition:
    """The canonical graph, built through the production contract."""
    body = dict(graph_id=GRAPH_ID, run_id=RUN_ID, created_at=CREATED_AT,
                nodes=dalio_nodes(), edges=dalio_edges())
    body.update(changes)
    return GraphDefinition(**body)


def canonical_dalio() -> GraphDefinition:
    """The canonical graph, proved to be the template it claims to be.

    The base contract no longer demands five stages of every graph, so the
    fixture's Dalio-ness is asserted HERE rather than assumed -- a canonical
    artifact that quietly stopped being the default template would otherwise
    ship unnoticed.
    """
    return validate_dalio_template(dalio_definition())


def definition_document() -> dict:
    """What the UI lane receives: the definition, and the digest of exactly it."""
    graph = canonical_dalio()
    return {
        "_comment": (
            "ALPHA-3 canonical graph DEFINITION, derived by "
            "tests/alpha3_graph_artifacts.py through the production contract. "
            "Immutable intent only: no pass, attempt, outcome, evidence, health, "
            "availability or execution status appears here, and none may be added "
            "-- the runtime projection is a separate document."),
        "definition": json.loads(canonical_json(graph)),
        "definition_digest": graph.digest(),
    }


def derive_all() -> dict[str, dict]:
    return {"alpha3_dalio_definition": definition_document()}


def load(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def write_all() -> None:
    for name, document in derive_all().items():
        (FIXTURES / f"{name}.json").write_text(
            json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8", newline="\n")


if __name__ == "__main__":                 # pragma: no cover -- derivation entry
    write_all()
