"""What counts as success for a step: derived, served, and merely rendered.

Split out of ``test_studio_completeness`` when that module crossed the line cap
-- along the seam its own census draws, and for the reason that census keeps
producing files: a label leaving ``UNSUPPORTED_FIELDS`` owes a positive witness,
and the last one to leave owes three.

This is the last of the fifteen the mandate named, and the only one that did not
become a field. That is the ruling rather than a shortfall: success for a step is
already decided by rules this build enforces, so a control would have invited a
person to state something the runtime would then ignore. What was missing was
never storage -- it was SAYING what those rules are, beside the layer that runs
each one.

The three claims here are the whole of that, and the second is the one only a
source test can hold:

- the row renders the served sentences, so deleting it does not satisfy the
  census next door;
- the window composes NONE of the rules it states, because a JavaScript copy
  would be right until the day the rule moved;
- and no sentence promises a signature, because this product has none.
"""
from __future__ import annotations

import re

from tests.test_studio_canvas import INSPECTOR, _code
from tests.studio_source_messages import _code

def test_success_criteria_became_a_derived_reading_and_kept_its_place():
    """The last label to leave the register, and it left by becoming a READING.

    It is the only one of the fifteen that did not become a field, and that is
    the ruling rather than a shortfall: success for a step is already decided by
    rules this build enforces, so a control would have invited a person to state
    something the runtime would then ignore. What was missing was never storage
    -- it was SAYING what those rules are.

    So the row renders sentences the SERVER derived, each beside the layer that
    enforces it. Deleting the row entirely would satisfy the census next door,
    and this is what refuses that.
    """
    inspector = _code(*INSPECTOR)
    body = re.search(r"function successCriteria\(box, form\) \{(.*?)\n\}",
                     inspector, re.DOTALL).group(1)

    assert 'unsupported(box, "Success criteria"' not in inspector
    assert "successCriteria(box, form);" in inspector
    # It prints what it was served, with the source that came with it.
    assert "form.criteria" in body, body
    assert 'context(box, "Success criteria", row.text,' in body, body
    assert "row.source" in body, body


def test_the_window_composes_none_of_the_rules_it_states():
    """The other half of the ruling, and the one only a source test can hold.

    Every clause is a rule enforced in Python. A JavaScript copy would render
    identically and be right until the day the rule moved -- so the words those
    rules are stated in are refused in the Studio's own files. The window looks
    a sentence up; it does not know what the sentence means.
    """
    from conductor.command import success_criteria as owner

    inspector = _code(*INSPECTOR)
    # Fragments unique to the served clauses. A looser phrase would match an
    # innocent sentence elsewhere on the surface -- "must name a" appears in the
    # gate-id note -- and a guard that reds on a neighbour's prose teaches the
    # next reader to widen it rather than to look.
    for phrase in ("must be verified. A step that finished",
                   "Verified by ", "names as the step's verifier",
                   "The verification must name a",
                   "must stand, published by this"):
        assert phrase not in inspector, (
            f"the window composes {phrase!r} itself instead of rendering the "
            "sentence the server derived")
    # And the sentences really are the owner's, so the refusal above is about
    # something that exists rather than a phrase nobody uses.
    served = owner.criteria_rows(
        kind="task", capability="review", verifier="checker", doer="worker",
        required_evidence="digest",
        arguments={"result_artifact_ref": "artifact-verdict"})
    assert any("must be verified" in row["text"] for row in served), served
    assert any("Verified by checker" in row["text"] for row in served), served


def test_no_sentence_this_build_serves_promises_a_signature():
    """There is no cryptographic signature anywhere in this product.

    Not a key, not a certificate, nothing countersigned. A verification is an
    adapter's typed answer that this build accepted from one permitted identity.
    A screen that said "signed by" would hand a reader a guarantee nobody has,
    and the word is therefore held out of every sentence -- on both sides, so a
    future clause cannot introduce it quietly.
    """
    from conductor.command.success_criteria import FORBIDDEN_WORDS, criteria_rows

    shapes = [
        dict(kind="task", capability="review", verifier="checker",
             doer="worker", required_evidence="digest",
             arguments={"result_artifact_ref": "artifact-verdict"}),
        dict(kind="task", capability="dispatch", verifier=None, doer="worker",
             required_evidence=None, arguments={}),
        dict(kind="task", capability="review", verifier=None, doer=None,
             required_evidence=None, arguments={}),
    ]
    said = " ".join(row["text"] + " " + row["source"]
                    for shape in shapes for row in criteria_rows(**shape))

    assert said, "no sentence was produced, so this proves nothing"
    for word in FORBIDDEN_WORDS:
        assert word not in said.lower(), word
    assert "sign" not in said.lower(), said
