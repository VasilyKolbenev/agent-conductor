"""Claim guards for `conductor.report`: relations, canonical results, truth tables.

Six sentences of the report used to be guarded by vocabulary — a word list the
test owned, a substring, a sentinel sweep that read only lines with code spans.
§10 of `docs/plans/2026-08-03-p0-control-loop-and-december-ui.md` records six
diversions that stayed green against those guards. Each guard here holds one of
the three shapes that close them:

* a **relation** between two independently produced sides — a document the test
  built against the text the report rendered from it — never two sides computed
  by the same production function;
* a **canonical full result** — a section or a line held verbatim. Every such
  constant is a *change sentinel*, not a judge of meaning: it reds on an honest
  rewording exactly as on a hostile one, and a red asks a person to re-review
  the new text against the claim named beside the constant and then update the
  copy — never to weaken the guard around it;
* an **independent truth table** — inputs this file constructs, expected
  outputs this file owns as literals. Nothing on an expected side is read out
  of `verify()` or any other function of the module under test.

The fixture builders are shared with `tests/test_report.py`, which keeps the
behavioural guards; this module holds the claim guards that replaced the
vocabulary ones.
"""
import copy

from conductor import report
from tests.test_report import (_agreed_pair, _gapless_state, _leaf_paths,
                               _with_a_sentinel_at, a_finding, a_lane, a_map,
                               line_starting, merged, only, section)

#: §10 contour 1. The whole empty-queue section, verbatim — a change sentinel.
#: Any rewrite reds, consent-shaped or honest; the guard's message says what to
#: re-review before this copy may be updated. A word list cannot hold this
#: sentence: a vocabulary the test owns is still a vocabulary.
EMPTY_QUEUE_SECTION = (
    "## Human queue — empty\n"
    "\n"
    "No lane records a request waiting on a person.\n"
    "\n"
    "An empty queue is the absence of a request. It is not a record that any "
    "question was put and answered, and nothing in this report becomes agreed "
    "because nobody objected to it.\n"
)

#: §10 contour 4. The whole empty-findings section, held by the same mechanism
#: as the empty queue's: it makes the same promise for the same reason.
EMPTY_FINDINGS_SECTION = (
    "## Findings — none\n"
    "\n"
    "No lane reports an open finding. That is what the lanes say; it is not "
    "a record that anything was checked.\n"
)

#: The three rendered `Verification` lines the truth tables below expect, whole
#: — parenthetical included. Literals owned here, not read out of `verify()`:
#: the diversion §10.3 records moved `verify()` and its guard together, because
#: that guard's expected side was derived from the function it judged.
_VERIFICATION_PREFIX = ("- Verification (read from `review_state` and "
                        "`cycle.roles[].reviews`): ")
CHECKED_LINE = (_VERIFICATION_PREFIX
                + "agreed — every role assigned to review it gave a verdict and "
                  "every verdict from another lane confirms it")
VACUOUS_LINE = (_VERIFICATION_PREFIX
                + "agreed with no reviewer assigned — no role is declared to "
                  "review this author's role, so nothing was checked and the "
                  "agreement is vacuous")
UNREVIEWED_LINE = (_VERIFICATION_PREFIX
                   + "not reviewed — a role that owes a verdict has not given "
                     "one")

#: §10 contour 2. Every non-blank line the report renders from
#: `_gapless_state` outside verbatim fences that no document field can move —
#: the report's own fixed prose, counts as the fixture has them. A reviewed
#: allow-list, complete by assertion: a line that appears here states nothing
#: about the project, and a line that states project status or clearance must
#: be driven by a §6.1 field and so must never become a member.
STATIC_REPORT_LINES = frozenset({
    "## Decision brief",
    "## Findings — 2",
    "## Human queue — 1 waiting on a person",
    "## Merger warnings — 1",
    "## What this report does not know",
    "- Verdicts:",
    "Detail, as the author wrote it:",
    "Evidence, as the author wrote it — quoted whole, not summarised:",
    "Source: one `state.json` document, the merger's output. Every value is "
    "copied from it, never recomputed; the counts and groupings below are "
    "drawn from that document and from nothing else.",
})

SENTINEL = "S-E-N-T-I-N-E-L"


def _unfenced_lines(text):
    """Every non-blank line of a rendered report outside verbatim fences.

    Heading, bullet and bare paragraph alike: unlike the code-span sweep this
    replaced, a line needs no backtick — and no marker at all — to be swept.
    Fenced blocks are skipped by CommonMark's own rule, fence lines included:
    they quote `detail` and `evidence` byte for byte, so their lines move with
    those fields and are that relation's subject, not this one's.
    """
    kept, fence = set(), None
    for ln in text.splitlines():
        is_fence = len(ln) >= 3 and set(ln) == {"`"}
        if fence is None:
            if is_fence:
                fence = ln
            elif ln.strip():
                kept.add(ln)
        elif is_fence and len(ln) >= len(fence):
            fence = None
    assert fence is None, "a fence opened in the report and never closed"
    return kept


def test_the_empty_queue_section_renders_its_reviewed_text_verbatim():
    # Contour 1: the plan's diversion rewrote the section into consent — "came
    # back yes", "the way is clear to merge" — and a ten-word list stayed
    # green. The full canonical result cannot be talked around: there is no
    # wording of consent, or of anything else, that leaves these bytes intact.
    empty = merged(a_map(), [a_lane("claude")])
    assert empty["human_queue"] == []
    assert section(report.render(empty), "## Human queue") == EMPTY_QUEUE_SECTION, (
        "the empty-queue section changed. This guard is a change sentinel, not "
        "a judge of meaning: re-review the new text — does it still read an "
        "empty queue as silence, and never as consent? — and update "
        "EMPTY_QUEUE_SECTION only after that review.")


def test_the_empty_findings_section_renders_its_reviewed_text_verbatim():
    # Contour 4: this sentence had no guard at all, and "Every lane has looked
    # and every check has passed" would have shipped. Same mechanism as the
    # empty queue's, because it is the same promise: absence is not a check.
    none = merged(a_map(), [a_lane("claude")])
    assert none["findings"] == []
    assert section(report.render(none), "## Findings") == EMPTY_FINDINGS_SECTION, (
        "the empty-findings section changed. This guard is a change sentinel, "
        "not a judge of meaning: re-review the new text — does it still read "
        "an absence of findings as unverified silence, never as a passed "
        "check or a clearance? — and update EMPTY_FINDINGS_SECTION only after "
        "that review.")


def test_every_unfenced_rendered_line_moves_with_a_field_or_is_reviewed_static():
    # Contour 2: the replaced sweep read only lines carrying a code span, so
    # `- Release readiness: cleared to merge` in bare prose was never swept —
    # and a first widening to headings and bullets still passed the same
    # clearance rendered as a bare paragraph (review RG1-1). Here the relation
    # covers every non-blank line outside verbatim fences: each either moves
    # when some §6.1 field moves, or is one of the reviewed static lines above.
    state = _gapless_state()
    candidates = _unfenced_lines(report.render(state))
    assert len(candidates) > 25, "the fixture is too thin to hold a guard"
    static = candidates
    for path in _leaf_paths(state):
        moved = _unfenced_lines(report.render(_with_a_sentinel_at(state, path, SENTINEL)))
        static = {ln for ln in static if ln in moved}
    assert static == set(STATIC_REPORT_LINES), (
        "these rendered lines state something no document field can move, and "
        "they are not on the reviewed static list: "
        f"{sorted(static ^ set(STATIC_REPORT_LINES))}. A fixed line of the "
        "report's own prose joins STATIC_REPORT_LINES only after review; a "
        "line that asserts a status, a clearance or a sign-off must be driven "
        "by a field of the document.")


def test_a_reviewer_assigned_renders_the_checked_verdict_and_nobody_the_vacuous_one():
    # Contour 3: an independent truth table. The input side is two documents
    # the merger built from maps differing in one respect — whether any role
    # reviews the author's — and the expected side is two literals this file
    # owns. Neither side is read out of `verify()`, so inverting its vacuous
    # label around a preserved substring cannot move both sides together.
    assigned, nobody = _agreed_pair()
    checked = line_starting(section(report.render(assigned), "## Findings"),
                            "- Verification")
    vacuous = line_starting(section(report.render(nobody), "## Findings"),
                            "- Verification")
    assert checked == CHECKED_LINE, (
        "a finding whose author's role is reviewed no longer renders the "
        "reviewed checked verdict. If the wording changed on purpose, "
        "re-review it — does it still claim a real check, and only that? — "
        "then update CHECKED_LINE.")
    assert vacuous == VACUOUS_LINE, (
        "a finding agreed with nobody assigned to review its author no longer "
        "renders the reviewed vacuous verdict. If the wording changed on "
        "purpose, re-review it — does it still plainly deny that anything was "
        "checked? — then update VACUOUS_LINE.")
    assert checked != vacuous


def test_findings_render_in_the_documents_order_measured_on_an_order_no_sort_gives():
    # Contour 5: the docstring's ordering claim, measured. The document order
    # is chosen so that a forward sort by id, a reverse sort by id and a plain
    # reversal each produce something else — a deterministic re-sort cannot
    # hide behind the determinism battery here. The expected side is the
    # merger's own list; the measured side is read off the rendered text.
    state = merged(a_map(), [a_lane("claude", None,
                                    [a_finding("D-2"), a_finding("D-9"),
                                     a_finding("D-1")])])
    document_order = [f["id"] for f in state["findings"]]
    assert document_order == ["D-2", "D-9", "D-1"]
    for deranged in (sorted(document_order), sorted(document_order, reverse=True),
                     list(reversed(document_order))):
        assert document_order != deranged, (
            "the fixture's order is producible by a sort, so it can no longer "
            "tell document order from a re-sort")
    rendered = [ln.split("`")[1] for ln in report.render(state).splitlines()
                if ln.startswith("### `")]
    assert rendered == document_order, (
        f"the report rendered findings as {rendered}, but the document's own "
        f"order is {document_order}: lists must render in the order the "
        "merger built them")


def test_each_field_the_verification_line_names_moves_the_rendered_verdict():
    # Contour 6: the line says it is read from `review_state` and
    # `cycle.roles[].reviews`, and this guard makes that claim measurable
    # rather than quotable. Each named field is moved on its own, and the
    # rendered verdict must move to the reviewed literal for that row — the
    # right direction, not merely a different string. The canonical lines also
    # hold the parenthetical itself: a substring match on it would prove
    # nothing about what the verdict actually rests on.
    assigned, _ = _agreed_pair()
    base = line_starting(section(report.render(assigned), "## Findings"),
                         "- Verification")
    assert base == CHECKED_LINE
    reviews_moved = copy.deepcopy(assigned)
    rev = next(r for r in reviews_moved["cycle"]["roles"] if r["id"] == "rev")
    assert rev["reviews"] == ["impl"], "the fixture no longer assigns the reviewer"
    rev["reviews"] = []
    after_reviews = line_starting(section(report.render(reviews_moved), "## Findings"),
                                  "- Verification")
    assert after_reviews != base
    assert after_reviews == VACUOUS_LINE, (
        "taking the author's role out of cycle.roles[].reviews did not move "
        "the rendered verdict to the vacuous row")
    state_moved = copy.deepcopy(assigned)
    only("D-1", state_moved)["review_state"] = "unreviewed"
    after_state = line_starting(section(report.render(state_moved), "## Findings"),
                                "- Verification")
    assert after_state != base
    assert after_state == UNREVIEWED_LINE, (
        "moving review_state did not move the rendered verdict to the "
        "unreviewed row")
