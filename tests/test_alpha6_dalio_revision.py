"""Revision 2 of the Dalio cycle is DERIVED from revision 1, and both are pinned.

Revision 1 is a historical witness: runs materialized from it, the ALPHA-3
definition fixture carries its shape, and a replay must reproduce it exactly.
Revision 2 is the same cycle with one field added -- each thinking step now
names where its own output is published, which is what makes the artifact chain
real instead of implied.

Two things have to hold at once, and neither is worth much alone:

- **revision 1 never moves.** Its canonical document is the thing past runs
  replay against;
- **revision 2 is revision 1 plus exactly one field per review step.** Written by
  hand it would drift -- a reworded title, a reordered key, a resource row
  dropped -- and the drift would be invisible, because nothing else compares the
  two. So the derivation is performed HERE, from the shipped revision 1, and the
  shipped revision 2 must equal what it produces.

**What is compared is the CANONICAL DOCUMENT, not the file's raw bytes**, and
the distinction is the contract's rather than a convenience. Every reader of a
template goes through `GraphTemplate.from_dict`, and every durable comparison
downstream -- the store's own refusal to rewrite a revision, the digest a run
records -- is over `canonical_json`. Key order and whitespace in the file are
therefore not part of what a revision IS, and a guard that pinned them would be
pinning something no consumer can observe. What it does catch is any change to
the document a consumer reads.

The digests are SPELLED, and they are digests of that canonical form. Derived
from the files they would move with the files, and a revision changing without a
review is exactly what they exist to catch.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from conductor.command.contracts import canonical_json
from conductor.command.graph_template import TEMPLATE_DIR, load_template

#: node_id -> where that step publishes. Read off revision 1's own chain: the
#: next review's source is this one's result, which is what the cycle already
#: said in prose and now says in data.
RESULTS = {
    "goal": "artifact-goal",
    "identify": "artifact-problems",
    "diagnose": "artifact-causes",
    "design": "artifact-plan",
}

#: Each revision's CANONICAL document, digested and pinned. A change to either
#: is a review decision; a reordered key in the file is not a change at all.
REVISION_ONE_DIGEST = "79776b1ecbbfb71c3e5d84d32292f3e2522c31ae67c7a62a1f39455194d13f50"
REVISION_TWO_DIGEST = "25b4772a53df720149989d7a2be57bc16d0e00d58922724495ae32bb789c6cab"


def _document(name: str) -> dict:
    return json.loads((TEMPLATE_DIR / f"{name}.json").read_text(encoding="utf-8"))


def _digest(document: dict) -> str:
    return hashlib.sha256(canonical_json(document).encode("utf-8")).hexdigest()


def derive_revision_two() -> dict:
    """Revision 1, plus one field per review step, and nothing else touched.

    The insertion point is deliberate: the result reference is written directly
    after the sources it is produced FROM, so the arguments read in the order the
    step happens rather than in the order a dict was built.
    """
    document = _document("dalio-v1")
    document["revision"] = 2
    for node in document["nodes"]:
        if node.get("capability") != "review":
            continue
        arguments = node["arguments"]
        rebuilt = {}
        for key, value in arguments.items():
            rebuilt[key] = value
            if key == "target_artifact_refs":
                rebuilt["result_artifact_ref"] = RESULTS[node["node_id"]]
        node["arguments"] = rebuilt
    return document


def test_revision_two_is_exactly_revision_one_plus_one_field_per_review(tmp_path):
    """The shipped revision 2 IS the derivation, as a canonical document.

    This is the guard that stops revision 2 becoming a second, independently
    edited cycle. If the two ever have to differ by more than the added field,
    that is a product decision and this test is where it is made.
    """
    shipped = _document("dalio-v2")

    assert shipped == derive_revision_two()
    assert canonical_json(shipped) == canonical_json(derive_revision_two())


def test_both_revisions_carry_the_canonical_document_they_were_reviewed_with():
    """Spelled digests over the CANONICAL document, so a revision cannot change
    without changing this file. Reordered keys or reflowed whitespace in the
    file are not changes to what any consumer reads, and are not pinned."""
    assert _digest(_document("dalio-v1")) == REVISION_ONE_DIGEST, (
        "REVISION 1 MOVED -- it is a historical witness and past runs replay "
        "against this canonical document")
    assert _digest(_document("dalio-v2")) == REVISION_TWO_DIGEST


def test_the_two_revisions_are_one_template_at_two_numbers():
    """One identity, two revisions. A new cycle would be a new template id."""
    one, two = load_template("dalio-v1"), load_template("dalio-v2")

    assert one.template_id == two.template_id == "template-dalio"
    assert (one.revision, two.revision) == (1, 2)
    assert one.roles == two.roles
    assert [node.node_id for node in one.steps()] == [
        node.node_id for node in two.steps()]


def test_the_artifact_chain_closes_in_revision_two_and_is_absent_from_one():
    """What the added field buys, asserted as the chain it makes.

    Each thinking step publishes what the next one reads, and the last publishes
    what the acting step is given. Revision 1 names no outputs at all -- which is
    why a review materialized from it cannot be run, and why it stays a replay
    witness rather than the default.
    """
    published = []
    consumed = []
    for node in load_template("dalio-v2").steps():
        if node.capability != "review":
            continue
        published.append(node.arguments["result_artifact_ref"])
        consumed.append(tuple(node.arguments["target_artifact_refs"]))

    assert len(published) == 4
    for index in range(len(published) - 1):
        assert consumed[index + 1] == (published[index],), (
            f"the chain breaks between step {index} and {index + 1}")
    assert consumed[0] == ("artifact-brief",)
    assert published[-1] == "artifact-plan"

    for node in load_template("dalio-v1").steps():
        if node.capability == "review":
            assert "result_artifact_ref" not in node.arguments
