"""The wire boundary, one fault at a time, on the document the route produced.

``test_graph_wire`` drives what the window DOES. This module drives what it
refuses, and it is split out of that file rather than allowed to push it past
the line cap. It borrows that module's server fixture and page helper for the
same reason ``test_panel_action_binding`` borrows the Cockpit's: one seeded
run, described in one place.

Nothing here is hand-built. Every case re-reads the real run through the real
route, applies its one fault to that fresh document, and asks the two
boundaries in turn -- so a case can only be refused for the fault it names,
and a fixture agreeing with itself cannot be mistaken for evidence.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Browser, Page

# ``wire_url`` is imported to be used as a fixture: the seeded server whose
# journal already holds the frozen plan and some records against it.
from browser_tests.test_graph_wire import (  # noqa: F401
    DURABLE_RUN,
    OTHER_RUN,
    _open,
    wire_url,
)

def test_the_runtime_word_screen_fires_and_spares_the_payload_it_must_spare(
        chromium: Browser, wire_url: str) -> None:
    """The screen in front of the write door, opened directly.

    It cannot fire on a body `graphRequestBody` builds today, because that
    body is assembled from a whitelist — which is the whole reason it exists
    and the whole reason it has to be proven here instead. A door nobody can
    open is not a door that works.

    The middle case is the one that would quietly break the product: every
    field of a capability's payload belongs to that capability's schema, and
    a walk that judged those keys too would refuse a plan the contract itself
    accepts. Production lifts the payload out by name before walking; so does
    this, and this is where that is checked.
    """
    page, _ = _open(chromium, wire_url)
    try:
        verdicts = page.evaluate(
            """async cases => {
                 const adapter = await import("./graph-adapter.js");
                 return cases.map(body => adapter.carriesRuntimeWord(body));
               }""",
            [
                {"graph_id": "g", "nodes": [{"node_id": "a", "kind": "task"}]},
                {"nodes": [{"node_id": "a", "phase": "idle"}]},
                {"nodes": [{"node_id": "a", "loop": {"bound": 2, "pass": 1}}]},
                {"nodes": [{"node_id": "a", "resources": [{"status": "ok"}]}]},
                {"nodes": [{"node_id": "a", "arguments": {
                    "phase": "x", "outcome": "succeeded"}}]},
            ])
        assert verdicts == [False, True, True, True, False]
    finally:
        page.context.close()
def _read(page: Page, run_id: str) -> dict:
    """The authoritative run read, as the production route answers it."""
    return page.evaluate(
        "id => fetch(`/command/runs/${id}`, {cache: 'no-store'})"
        ".then(answer => answer.json())", run_id)


_VERDICT = """
  async payload => {
    const adapter = await import("./graph-adapter.js");
    const store = await import("./graph-payload.js");
    const answer = adapter.adaptRunGraph(payload, []);
    if (answer.state !== "loaded") return `refused-at-adapter:${answer.state}`;
    return store.projectPayload(answer.payload) === null
      ? "refused-at-store" : "accepted";
  }
"""


def _fault(read: dict, path: tuple, changes: dict) -> dict:
    """Apply one change at one place and hand the whole document back.

    `changes` is a dict rather than keyword arguments because two of the wire's
    own field names -- `pass` among them -- are Python keywords, and a case
    that had to spell one differently would be testing a different key than
    the one it names.
    """
    target = read
    for step in path:
        target = target[step]
    target.update(changes)
    return read


#: One fault at a time, applied to the REAL document this server answers with.
#: The baseline is asserted accepted first, so a case can only be refused for
#: the fault it names -- and every name below is a mutation that must stay
#: refused for as long as the relation it cuts is a relation.
_WIRE_FAULTS = (
    ("one-graph-key-answered-null-on-its-own",
     lambda read: _fault(read, ("graph",), {"definition_digest": None})),
    ("a-digest-that-is-not-a-string",
     lambda read: _fault(read, ("graph",), {"definition_digest": 42})),
    ("a-schema-version-this-window-cannot-read",
     lambda read: _fault(read, ("graph", "definition"), {"schema_version": 3})),
    ("a-plan-about-another-run",
     lambda read: _fault(read, ("graph", "definition"), {"run_id": OTHER_RUN})),
    ("two-documents-naming-two-graphs",
     lambda read: _fault(read, ("graph", "runtime"), {"graph_id": "graph-x"})),
    ("an-unknown-key-on-the-plan",
     lambda read: _fault(read, ("graph", "definition"), {"provider": "claude"})),
    ("an-unknown-key-on-the-projection",
     lambda read: _fault(read, ("graph", "runtime"), {"digest": "sha256:x"})),
    ("a-plan-step-with-no-position",
     lambda read: read["graph"]["runtime"]["nodes"].pop() and read),
    ("a-position-for-a-step-no-plan-declares",
     lambda read: _fault(read, ("graph", "runtime", "nodes", 0),
                         {"node_id": "ghost"})),
    ("two-positions-for-one-step",
     lambda read: read["graph"]["runtime"]["nodes"].append(
         dict(read["graph"]["runtime"]["nodes"][0])) or read),
    ("a-runtime-phase-no-layer-owns",
     lambda read: _fault(read, ("graph", "runtime", "nodes", 0),
                         {"phase": "warming"})),
    # The first of these came back GREEN when it was written: the mapping READ
    # named fields, so a word out of place was DROPPED rather than refused,
    # and the drawing then claimed to be the whole document. Dropping is
    # repair. The adapter now screens every level before reading it, and
    # these five cases hold the class rather than the one instance found.
    ("a-decision-attached-to-a-step-that-is-no-gate",
     lambda read: _fault(read, ("graph", "runtime", "nodes", 0),
                         {"decision": "satisfied"})),
    ("a-pass-attached-to-a-step-that-is-no-loop",
     lambda read: _fault(read, ("graph", "runtime", "nodes", 0), {"pass": 1})),
    ("an-unknown-key-on-one-position",
     lambda read: _fault(read, ("graph", "runtime", "nodes", 0),
                         {"health": "ready"})),
    ("an-unknown-key-on-one-plan-step",
     lambda read: _fault(read, ("graph", "definition", "nodes", 0),
                         {"provider": "claude-code"})),
    ("an-unknown-key-inside-a-plan-steps-loop",
     lambda read: _fault(read, ("graph", "definition", "nodes", -1, "loop"),
                         {"pass": 1})),
    ("an-evidence-ref-that-is-not-an-identifier",
     lambda read: _fault(read, ("graph", "runtime", "nodes", 0),
                         {"evidence_refs": ["not an id!"]})),
    ("a-bound-reached-that-disagrees-with-the-plans-ceiling",
     lambda read: _fault(read, ("graph", "runtime", "nodes", -1),
                         {"bound_reached": True})),
    ("a-capability-this-window-carries-no-word-for",
     lambda read: _fault(read, ("graph", "definition", "nodes", 5),
                         {"capability": "teleport"})),
)


def test_each_wire_arm_refuses_its_own_single_fault(
        chromium: Browser, wire_url: str) -> None:
    """Refuse, never repair — on the document the real route produced.

    One page for the whole table, as the fixture boundary module does: each
    case re-reads the run, applies its one fault to that fresh document and
    asks the two boundaries in turn, so no case can be refused for the
    leftovers of the one before it.
    """
    page, _ = _open(chromium, wire_url)
    try:
        assert page.evaluate(_VERDICT, _read(page, DURABLE_RUN)) == "accepted", (
            "the unfaulted read must be accepted or no case below means anything")
        for name, apply in _WIRE_FAULTS:
            verdict = page.evaluate(_VERDICT, apply(_read(page, DURABLE_RUN)))
            assert verdict != "accepted", f"{name}: the boundary accepted it"
    finally:
        page.context.close()


#: The same discipline one layer in: each of these cuts the ONE-SOURCE rule
#: that keeps the plan and the run from being read as each other. They are
#: applied to the adapted payload, so the adapter has already agreed the two
#: wire documents are a pair -- what is on trial here is the store alone.
_PAYLOAD_FAULTS = (
    ("a-node-answering-from-both-documents",
     lambda payload: _fault(payload, ("nodes", 0), {"phase": "idle"})),
    ("a-node-answering-from-neither",
     lambda payload: _fault(payload, ("nodes", 0), {"runtime": None})),
    ("a-gate-whose-durable-answer-was-written-into-the-plans-key",
     lambda payload: _fault(payload, ("nodes", 4, "gate"),
                            {"state": "satisfied"})),
    ("a-loop-carrying-the-runs-pass-in-the-plans-key",
     lambda payload: _fault(payload, ("nodes", 7, "loop"), {"pass": 1})),
    ("an-evidence-row-invented-for-a-position-that-states-none",
     lambda payload: _fault(payload, ("nodes", 0), {"evidence": [
         {"evidence_id": "evidence-1", "kind": "result",
          "verification": "verified"}]})),
    ("a-durable-payload-with-no-digest",
     lambda payload: _fault(payload, ("provenance",), {"digest": None})),
    ("a-durable-payload-calling-itself-a-fixture",
     lambda payload: _fault(payload, ("provenance",), {"source": "fixture"})),
    ("a-fixture-payload-wearing-a-digest",
     lambda payload: _fault(payload, ("provenance",),
                            {"source": "fixture", "graphId": None})),
)


_ADAPT = """async payload => {
    const adapter = await import("./graph-adapter.js");
    return adapter.adaptRunGraph(payload, []).payload;
}"""
_PROJECT = """async payload => {
    const store = await import("./graph-payload.js");
    return store.projectPayload(payload) === null;
}"""


def test_the_store_refuses_a_fact_that_answers_from_two_sources(
        chromium: Browser, wire_url: str) -> None:
    """The one-source rule, cut one way at a time and never surviving."""
    page, _ = _open(chromium, wire_url)
    try:
        read = _read(page, DURABLE_RUN)
        assert page.evaluate(_PROJECT, page.evaluate(_ADAPT, read)) is False, (
            "the adapted payload must project or no case below means anything")
        for name, apply in _PAYLOAD_FAULTS:
            faulted = apply(page.evaluate(_ADAPT, read))
            assert page.evaluate(_PROJECT, faulted) is True, (
                f"{name}: the store accepted the fault")
    finally:
        page.context.close()
