"""Guards for `conductor.report` — the deterministic Markdown report of one state.

The guards that carry the most weight are written against a *relation* the
report promises rather than against a word it happens to contain. Several work
by building a pair of documents that differ in exactly one respect and
demanding that the report tell them apart:

* a finding whose `review_state` is `agreed` with a role assigned to review its
  author, against the same `agreed` with nobody assigned. The merger writes the
  same five letters for both — a report that renders them alike has erased the
  vacuous-agreement disclosure DO-2 was opened for, and the guard reds;
* a document whose `review_state` contradicts its own verdicts. The report must
  print what the document says, because it is not a second merger. A report
  that recomputes anything reds on that pair;
* a document carrying authored text that forges Markdown, against the same
  document carrying harmless text. The report's structure must be the same in
  both, because it is the report's and not the author's.

The determinism claim is measured, not asserted, in
`tests/test_report_determinism.py`, which renders the same document in child
interpreters and compares the files byte for byte. The claim guards that
replaced this module's former vocabulary guards — the canonical section
sentinels, the bare-prose sentinel sweep, the verification truth table —
live in `tests/test_report_claim_guards.py`.
"""
import ast
import copy
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import conductor
from conductor import merge, report, schema, store, validate
from conductor.__main__ import main
from tests.test_server import get, start
from tests.test_store import write_project

NOW = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)
SRC_ROOT = Path(conductor.__file__).resolve().parents[1]
REPORT_SOURCE = Path(report.__file__).resolve()


def role(rid, reviews=(), **extra):
    """A `cycle.roles` entry; `stage` only when a caller asks for it."""
    return {"id": rid, "harness": "cc", "reviews": list(reviews), **extra}


def a_map(roles=(), phases=(), project="p", nodes=("n",)):
    """A schema-valid map with the nodes and roles a test needs."""
    return {"schema_version": 1, "project": project,
            "nodes": [{"id": n, "label": n, "kind": "artifact"} for n in nodes],
            "cycle": {"phases": list(phases), "roles": list(roles)}}


def a_lane(author, role_id=None, findings=(), verdicts=None, waits=(), now=None,
           updated="2026-07-30T11:00:00+00:00"):
    """One loader-shaped lane entry, as `store.load` would hand it to the merger."""
    data = {"schema_version": 1, "author": author, "updated": updated,
            "findings": list(findings), "verdicts": verdicts or {},
            "waits_on_human": list(waits)}
    if role_id:
        data["role"] = role_id
    if now:
        data["now"] = now
    return {"author": author, "data": data, "error": None}


def a_finding(fid="D-1", evidence="e", **extra):
    """A schema-valid finding with every §6.1 text field populated."""
    return {"id": fid, "title": "t", "severity": "blocker", "claim": "defect",
            "detail": "d", "evidence": evidence, "refs": ["n"], **extra}


def merged(map_data, lanes, **kw):
    """Merge into a genuine `state.json` document at a fixed instant."""
    return merge.merge(map_data, None, list(lanes), [], 0, NOW, **kw)


def only(finding_id, state):
    """The one finding with this id, so a test never indexes by position."""
    return next(f for f in state["findings"] if f["id"] == finding_id)


def section(text, heading):
    """The rendered section starting at `heading`, up to the next `## ` heading."""
    start_at = text.index(heading)
    rest = text[start_at + len(heading):]
    end = rest.find("\n## ")
    return heading + (rest if end < 0 else rest[:end])


def line_starting(text, prefix):
    """The single line beginning with `prefix`; a test that finds two is wrong."""
    found = [ln for ln in text.splitlines() if ln.startswith(prefix)]
    assert len(found) == 1, f"expected one line starting {prefix!r}, got {found}"
    return found[0]


# --- determinism: the same document renders the same bytes ------------------


def test_the_same_document_renders_the_same_bytes_every_time():
    state = merged(a_map([role("impl"), role("rev", ["impl"])]),
                   [a_lane("claude", "impl", [a_finding()]),
                    a_lane("codex", "rev",
                           verdicts={"D-1": {"disposition": "confirmed", "note": "n"}})])
    # Round-tripped through JSON because that is how the panel receives it.
    again = json.loads(json.dumps(state, ensure_ascii=False))
    assert report.render(state).encode("utf-8") == report.render(again).encode("utf-8")


def test_the_only_timestamp_rendered_is_the_documents_own_generated_at():
    state = merged(a_map(), [])
    later = copy.deepcopy(state)
    later["generated_at"] = "2099-01-01T00:00:00+00:00"
    first, second = report.render(state), report.render(later)
    assert first != second, "the document's generated_at is not reaching the report"
    assert state["generated_at"] in first and later["generated_at"] in second
    # Nothing else moved: the two renders differ on that one line and no other.
    assert [a for a, b in zip(first.splitlines(), second.splitlines()) if a != b] == \
           [line_starting(first, "- `generated_at`")]


def test_the_verdicts_on_one_finding_render_in_an_order_the_document_lacks():
    # `verdicts` is a JSON object, and no serializer promises to preserve the
    # order of one — so the report sorts, and the sort has to be measured on a
    # finding carrying more than one verdict. Three, because with two the
    # document's order reversed IS the sorted order, and a sabotage that
    # reversed instead of sorting would pass unseen.
    state = merged(a_map([role("impl"), role("rev", ["impl"])]),
                   [a_lane("claude", "impl", [a_finding()]),
                    *(a_lane(who, "rev", verdicts={"D-1": {"disposition": "confirmed",
                                                           "note": who}})
                      for who in ("zed", "abe", "mia"))])
    recorded = list(only("D-1", state)["verdicts"])
    assert recorded == ["zed", "abe", "mia"], (
        "the document no longer carries an order the sort has to correct")
    rendered = [ln.split("`")[1] for ln in report.render(state).splitlines()
                if ln.startswith("  - `")]
    assert rendered == sorted(recorded)


# --- the report reads the document; it does not merge again -----------------


def test_the_review_state_rendered_is_the_documents_own_not_a_recomputation():
    state = merged(a_map([role("impl"), role("rev", ["impl"])]),
                   [a_lane("claude", "impl", [a_finding()]),
                    a_lane("codex", "rev",
                           verdicts={"D-1": {"disposition": "confirmed", "note": "n"}})])
    assert only("D-1", state)["review_state"] == "agreed"
    # A document that contradicts itself: a foreign refutation that §6 would
    # compute as `disagreement`, sitting under a `review_state` of `agreed`.
    doctored = copy.deepcopy(state)
    only("D-1", doctored)["verdicts"]["codex"] = {"disposition": "refuted",
                                                  "note": "n", "role": "rev"}
    assert (line_starting(report.render(doctored), "- `review_state`")
            == line_starting(report.render(state), "- `review_state`"))


def test_the_report_module_never_imports_the_merger_or_the_loader():
    # One merge, one implementation. A report that could load or merge could
    # drift from the panel; a report that can only read a dict cannot.
    assert _imported_modules(REPORT_SOURCE).isdisjoint(
        {"conductor.merge", "conductor.store", "conductor.validate", "conductor.server"})


def test_fields_the_protocol_does_not_define_are_tolerated_and_not_rendered():
    # §6.1: consumers must tolerate additional fields — tolerate, not display.
    state = merged(a_map(), [a_lane("claude", None, [a_finding()])])
    state["private_note"] = "SHOULD-NOT-APPEAR-TOP"
    only("D-1", state)["private_note"] = "SHOULD-NOT-APPEAR-FINDING"
    text = report.render(state)
    assert "SHOULD-NOT-APPEAR-TOP" not in text
    assert "SHOULD-NOT-APPEAR-FINDING" not in text


def _gapless_state():
    """A document that shows every §6.1 field the report reads, and no gap at all.

    Every value in it is distinct, because the sentinel sweeps over it — in
    `tests/test_report_claim_guards.py` and `tests/test_report_funnel.py` — ask
    whether a rendered line can be made to move: two findings agreeing on a
    field would keep each other's line on the page and read as unattributable.
    """
    roles = [role("impl", stage="implement"), role("rev", ["impl"], stage="review")]
    return merged(
        a_map(roles, phases=["implement", "review"], project="the-project",
              nodes=("n", "m")),
        [a_lane("claude", "impl",
                [a_finding("D-1", evidence="ev-one", title="first title",
                           claim="first claim", detail="det-one"),
                 a_finding("D-2", evidence="ev-two", title="second title",
                           claim="second claim", detail="det-two",
                           severity="note", refs=["m"])],
                now={"task": "t", "since": "2026-07-30T10:00:00+00:00",
                     "phase": "implement"},
                waits=[{"id": "w-1", "kind": "decision", "title": "the question",
                        "why": "the reason", "blocks": ["D-1"]}]),
         a_lane("zed", "rev", verdicts={
             "D-1": {"disposition": "confirmed", "note": "zed on one"},
             "D-2": {"disposition": "refuted", "note": "zed on two"}}),
         a_lane("abe", "rev", verdicts={
             "D-1": {"disposition": "confirmed", "note": "abe on one"},
             "D-2": {"disposition": "partial", "note": "abe on two"}})],
        extra_warnings=["lane codex: schema_version 2 is newer than 1"])


def _leaf_paths(value, path=()):
    """The path to every scalar in a document, keys and list indices alike."""
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _leaf_paths(item, (*path, key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _leaf_paths(item, (*path, index))
    else:
        yield path


def _with_a_sentinel_at(state, path, sentinel):
    """A copy of `state` with the one value at `path` replaced."""
    doc = copy.deepcopy(state)
    node = doc
    for step in path[:-1]:
        node = node[step]
    node[path[-1]] = sentinel
    return doc


def test_an_empty_document_reports_absence_instead_of_inventing_a_state():
    text = report.render({})
    for invented in merge.PROJECT_STATES | merge.STATUS_REASONS:
        assert invented not in text, f"the report named {invented!r} with no document"
    assert "`null`" in line_starting(text, "- Project state:")


# --- `agreed` is not `checked` ---------------------------------------------


def _agreed_pair():
    """Two documents whose finding is `agreed`, one with a reviewer and one without.

    They differ in a single character of the map: whether `rev.reviews` names
    the author's role. Everything the merger writes about the finding — the
    verdict, the confirming reviewer, the five letters of `review_state` — is
    the same in both.
    """
    lanes = [a_lane("claude", "impl", [a_finding()]),
             a_lane("codex", "rev",
                    verdicts={"D-1": {"disposition": "confirmed", "note": "n"}})]
    assigned = merged(a_map([role("impl"), role("rev", ["impl"])]), lanes)
    nobody = merged(a_map([role("impl"), role("rev", [])]), lanes)
    return assigned, nobody


def test_the_merger_writes_agreed_for_both_a_reviewed_and_an_unreviewed_finding():
    # The precondition every guard below rests on: the document does NOT
    # distinguish these two. If this ever fails, the pair has stopped testing
    # what it claims and the guards under it are measuring nothing.
    assigned, nobody = _agreed_pair()
    assert only("D-1", assigned)["review_state"] == "agreed"
    assert only("D-1", nobody)["review_state"] == "agreed"
    assert only("D-1", assigned)["verdicts"] == only("D-1", nobody)["verdicts"]


#: The exact sentence the report renders beside a finding a review confirmed.
#: Taken from `verify` rather than transcribed, so the guards below compare the
#: report against itself and cannot be satisfied by a reworded copy.
_VERIFIED_LABEL = report.verify(
    {"review_state": "agreed", "author": "a"},
    {"lanes": [{"author": "a", "role": "impl"}],
     "cycle": {"roles": [{"id": "rev", "reviews": ["impl"]}]}}).label


def test_the_checked_sentence_appears_once_per_finding_a_review_confirmed():
    # Across the whole review vocabulary, and by counting rather than by
    # looking: the number of findings the report calls checked is exactly the
    # number `verify` calls verified, so a label and its verdict cannot part.
    assigned, nobody = _agreed_pair()
    for state in (assigned, nobody, *_review_vocabulary_states()):
        text = report.render(state)
        verified = sum(1 for f in state["findings"]
                       if report.verify(f, state).verified)
        assert section(text, "## Findings").count(_VERIFIED_LABEL) == verified
        for finding in state["findings"]:
            assert report.verify(finding, state).label in text


def _review_vocabulary_states():
    """One document per remaining `review_state`, each built by the merger."""
    roles = [role("impl"), role("rev", ["impl"]), role("obs"), role("aud", ["obs"])]
    disputed = merged(a_map(roles), [
        a_lane("claude", "impl", [a_finding()]),
        a_lane("codex", "rev", verdicts={"D-1": {"disposition": "refuted",
                                                 "note": "no"}})])
    unreviewed = merged(a_map(roles), [a_lane("claude", "impl", [a_finding()]),
                                       a_lane("codex", "rev")])
    uncovered = merged(a_map(roles), [a_lane("bot", "obs", [a_finding("D-7")])])
    suspended = merged(a_map(roles), [a_lane("claude", "impl", [a_finding("D-9")]),
                                      a_lane("bot", "obs", [a_finding("D-9")])])
    assert [only("D-1", disputed)["review_state"],
            only("D-1", unreviewed)["review_state"],
            only("D-7", uncovered)["review_state"],
            suspended["findings"][0]["review_state"]] == \
        ["disagreement", "unreviewed", "uncovered", "suspended"]
    return disputed, unreviewed, uncovered, suspended


# --- evidence is authored text ---------------------------------------------


HOSTILE_EVIDENCE = (
    "```\nthis line would close a three-backtick fence\n```\n"
    "run: pytest -q -k 'report and not slow'\n"
    "   indented, and trailing spaces follow   \n"
    "* not a bullet    # not a heading    | not a table |\n"
    "a five-backtick run: ````` and a unicode check ✓ ✕ —\n"
)


def test_evidence_reaches_the_report_exactly_as_the_author_wrote_it():
    state = merged(a_map(), [a_lane("claude", None,
                                    [a_finding(evidence=HOSTILE_EVIDENCE)])])
    assert HOSTILE_EVIDENCE in report.render(state)


def test_long_evidence_is_quoted_whole_rather_than_shortened():
    long_evidence = "\n".join(f"line {n:04d} of a long reproduction log"
                              for n in range(2000))
    state = merged(a_map(), [a_lane("claude", None,
                                    [a_finding(evidence=long_evidence)])])
    assert long_evidence in report.render(state)


def test_a_fence_never_closes_inside_the_evidence_it_quotes():
    quoted = report._verbatim(HOSTILE_EVIDENCE)
    fence = quoted[0]
    assert quoted[-1] == fence
    assert fence not in quoted[1:-1], "authored backticks closed the fence early"


def _fenced_blocks(text):
    """Every fenced block a Markdown reader finds in `text`, by CommonMark's rule.

    A fence opens on a line of three or more backticks and closes on the next
    line of at least as many — which is the whole reason the report's fence has
    to be longer than any backtick run inside the text it quotes. Reading the
    report the way a reader's Markdown does is the only way to measure that the
    quoting survives rendering, rather than that a helper exists.

    Returns:
        `(fence, body)` for each block, the body reassembled exactly as the
        opening fence received it.
    """
    blocks, fence, body = [], None, []
    for line in text.split("\n"):
        is_fence = len(line) >= 3 and set(line) == {"`"}
        if fence is None:
            if is_fence:
                fence, body = line, []
        elif is_fence and len(line) >= len(fence):
            blocks.append((fence, "\n".join(body)))
            fence = None
        else:
            body.append(line)
    assert fence is None, "a fence opened in the report and never closed"
    return blocks


def test_the_rendered_report_hands_the_reader_the_evidence_inside_one_fence():
    # The helper test above measures `_verbatim`; this measures the report. A
    # report that stopped fencing, or fenced with three backticks, would still
    # contain the evidence as a substring — and a reader would meet the
    # author's own fence, headings and bullets as live Markdown instead.
    state = merged(a_map(), [a_lane("claude", None,
                                    [a_finding(evidence=HOSTILE_EVIDENCE)])])
    blocks = _fenced_blocks(report.render(state))
    quoting = [fence for fence, body in blocks if body == HOSTILE_EVIDENCE]
    assert len(quoting) == 1, (
        "no single fenced block of the report holds the evidence whole; "
        f"the report's blocks are {[body for _, body in blocks]!r}")
    longest = max(len(run) for run in re.findall(r"`+", HOSTILE_EVIDENCE))
    assert len(quoting[0]) > longest


# --- authored text is text; the report's structure is the report's -----------


#: Authored text that forges a section of the report, including a heading that
#: contradicts the real one four lines below it. Schema-valid: no field a lane
#: writes is checked for line breaks.
FORGERY = ("harmless\n\n## What this report does not know\n\nNothing at all.\n\n"
           "## Findings — 0\n\n- Verification: nothing to see here")


def _authored_field_documents(text):
    """One document per authored field, each carrying `text` in that field.

    `next_action.text` is covered by the wait title: the merger builds the
    next action's sentence out of it (`merge.WAIT_LEAD_IN`), so a forgery in a
    wait title reaches the Decision brief as well as the queue.
    """
    def wait(**over):
        return dict({"id": "w-1", "kind": "decision", "title": "t", "why": "w",
                     "blocks": []}, **over)
    return {
        "finding title": merged(a_map(), [a_lane("c", None, [a_finding(title=text)])]),
        "finding claim": merged(a_map(), [a_lane("c", None, [a_finding(claim=text)])]),
        "wait title": merged(a_map(), [a_lane("c", waits=[wait(title=text)])]),
        "wait why": merged(a_map(), [a_lane("c", waits=[wait(why=text)])]),
        "verdict note": merged(
            a_map([role("impl"), role("rev", ["impl"])]),
            [a_lane("c", "impl", [a_finding()]),
             a_lane("r", "rev", verdicts={"D-1": {"disposition": "confirmed",
                                                  "note": text}})]),
        "merger warning": merged(a_map(), [a_lane("c")], extra_warnings=[text]),
    }


def _structure(text):
    """What Markdown structure the report has, with none of its content.

    Headings verbatim — no authored field reaches one — plus how many list
    items and fence lines the report emits. Authored text may change what a
    line says; it may not change how many lines there are or what they are.
    """
    lines = text.splitlines()
    return ([ln for ln in lines if ln.startswith("#")],
            sum(1 for ln in lines if ln.lstrip().startswith("- ")),
            sum(1 for ln in lines if len(ln) >= 3 and set(ln) == {"`"}))


def test_the_authored_fields_rendered_in_a_bullet_forge_no_heading_list_item_or_fence():
    # Six fields, each rendered inside a bullet, each fed text that forges a
    # section — and the whole of the report's structure held still, not just
    # its headings. The claim over EVERY field of the document, headings only,
    # is `test_report_funnel.test_no_string_field_of_the_document_can_forge_a_
    # heading`; the two are halves of one guard and neither is the other.
    harmless = _authored_field_documents("harmless")
    forged = _authored_field_documents(FORGERY)
    for field, state in forged.items():
        text = report.render(state)
        assert _structure(text) == _structure(report.render(harmless[field])), (
            f"{field} changed the report's structure")
        # The forgery is still reported — neutralised, not swallowed. It reads
        # as the author's words inside a line, which is where it stays: the
        # section it tried to counterfeit is opened once, by the report.
        assert "Nothing at all." in text, field
        assert sum(1 for ln in text.splitlines()
                   if ln.startswith("## What this report does not know")) == 1, field


def test_the_line_breaks_a_field_holds_are_disclosed_rather_than_dropped():
    # Flattening is a change to the author's bytes, so the line says so.
    state = merged(a_map(), [a_lane("c", None, [a_finding(title="one\ntwo")])])
    title = line_starting(report.render(state), "- Title:")
    assert "one\\ntwo" in title and "line breaks" in title


# --- a field the document records is never reported as one it does not ------


def test_a_field_recorded_with_no_words_in_it_is_not_reported_as_missing():
    # Schema-valid: `schema._validate_lane_findings` checks that title and
    # evidence are strings and never that they say anything.
    state = merged(a_map(), [a_lane("c", None, [a_finding(title="  ", evidence="  ",
                                                          claim="")])])
    text = report.render(state)
    for line in (line_starting(text, "- Title:"), line_starting(text, "Evidence:"),
                 line_starting(text, "- Claim,")):
        assert "records this field" in line, line
        assert "no title in the document" not in line
        assert "no claim in the document" not in line
        assert "none recorded in the document" not in line
    assert "only whitespace" in line_starting(text, "- Title:")
    assert "empty string" in line_starting(text, "- Claim,")


def test_a_field_the_document_does_not_record_is_still_reported_as_missing():
    # The other half of the pair: the two cases must not have collapsed into
    # one. A hand-built document, because the merger substitutes "" for every
    # finding text field a lane omits.
    text = report.render({"findings": [{"id": "F"}], "project_status": {}})
    assert "(no title in the document)" == line_starting(
        text, "- Title:").removeprefix("- Title: ")
    assert "Evidence: none recorded in the document." in text
    assert "(no detail in the document)" in line_starting(text, "- Detail:")


# --- what the document does not know ---------------------------------------


def _gap_ridden_state():
    """A document showing every review gap, unstaged roles and an empty queue."""
    roles = [role("impl"), role("rev", ["impl"]), role("obs"), role("aud", ["obs"]),
             role("free", [])]
    return merged(a_map(roles), [
        a_lane("claude", "impl", [a_finding("D-1"), a_finding("D-9")]),
        a_lane("codex", "rev"),                       # holds rev, verdicts nothing
        a_lane("bot", "obs", [a_finding("D-7"), a_finding("D-9")]),
        a_lane("solo", "free", [a_finding("D-5")]),
        {"author": "torn", "data": None, "error": "lane torn: not json"}])


def test_the_unknown_section_names_every_gap_the_document_actually_shows():
    state = _gap_ridden_state()
    states = {f["id"]: f["review_state"] for f in state["findings"]}
    assert states == {"D-1": "unreviewed", "D-9": "suspended", "D-7": "uncovered",
                      "D-5": "agreed"}                      # what is being reported on
    unknown = section(report.render(state), "## What this report does not know")
    assert "`D-1`" in line_starting(unknown, "- Findings awaiting a verdict")
    assert "`D-7`" in line_starting(unknown, "- Findings whose reviewing role")
    assert "`D-5`" in line_starting(unknown, "- Findings agreed with no role")
    assert "`D-9`" in line_starting(unknown, "- Findings suspended")
    assert "`current_phase`" in line_starting(unknown, "- No lane declares")
    assert "`free`" in line_starting(unknown, "- Roles the map gives no")
    assert "`torn`" in line_starting(unknown, "- Lanes that could not be read")


def test_an_unknown_project_state_is_named_as_unknown():
    state = merge.merge(None, "map.toml unreadable", [], [], 0, NOW)
    assert state["project_status"]["state"] == "unknown"
    unknown = section(report.render(state), "## What this report does not know")
    assert "`map_unreadable`" in line_starting(unknown, "- The project state is")


def test_a_document_with_no_gaps_claims_none():
    state = merged(
        a_map([role("impl", stage="implement"), role("rev", ["impl"], stage="review")],
              phases=["implement", "review"]),
        [a_lane("claude", "impl", [a_finding()],
                now={"task": "t", "since": "2026-07-30T10:00:00+00:00",
                     "phase": "implement"},
                waits=[{"id": "w-1", "kind": "decision", "title": "t", "why": "w",
                        "blocks": []}]),
         a_lane("codex", "rev",
                verdicts={"D-1": {"disposition": "confirmed", "note": "n"}})])
    unknown = section(report.render(state), "## What this report does not know")
    assert "None of the gaps this report looks for" in unknown


# --- an empty queue is silence, not consent --------------------------------


def test_an_empty_queue_is_reported_as_an_absence_of_requests_not_a_decision():
    empty = merged(a_map(), [a_lane("claude")])
    waiting = merged(a_map(), [a_lane("claude", waits=[
        {"id": "w-1", "kind": "decision", "title": "t", "why": "w", "blocks": []}])])
    assert empty["human_queue"] == [] and len(waiting["human_queue"]) == 1
    empty_text, waiting_text = report.render(empty), report.render(waiting)
    assert "Silence is not consent" in empty_text
    assert "Silence is not consent" not in waiting_text
    # The absence is stated where absences are collected, not left to be inferred
    # from a section that renders as nothing.
    assert "- The human queue is empty" in section(
        empty_text, "## What this report does not know")


# --- the data defect the schema boundary now stops --------------------------


NON_STRING_WAIT = {"id": "w-1", "kind": "decision", "title": {"raw": 1},
                   "why": 7, "blocks": []}


def test_the_schema_rejects_a_non_string_wait_title_at_the_boundary():
    # The precondition the two outside-the-contract tests below rest on:
    # `schema._validate_lane_waits` rejects a non-string title, so a lane
    # holding one is invalid, and `store.load` breaks it before merge.
    data = a_lane("claude", waits=[NON_STRING_WAIT])["data"]
    errors = schema.validate_lane(data, filename_stem="claude")[0]
    assert any("title" in e and "'w-1'" in e for e in errors)


def test_outside_the_contract_a_merged_non_string_title_renders_as_data_not_prose():
    # `merge.merge` called directly, skipping the schema — input the pipeline
    # now refuses. The report's own door still holds for it: the value is
    # shown as JSON on the Title line, never as a sentence somebody wrote.
    state = merged(a_map(), [a_lane("claude", waits=[NON_STRING_WAIT])])
    queue = section(report.render(state), "## Human queue")
    assert "### `w-1`" in queue                  # headed by the id the schema checks
    assert "{'raw': 1}" not in queue             # never a Python repr
    assert '{"raw": 1}' in line_starting(queue, "- Title:")   # shown as data, as JSON
    assert "non-string value" in line_starting(queue, "- Why:")


def test_outside_the_contract_the_brief_still_carries_the_repr_the_merger_wrote():
    # The other half. `merge._next_action` renders a title as given — by
    # design, sanitising in the merger is refused — so hand merge a document
    # the schema would reject and the repr IS the text of `next_action.text`:
    # a string, indistinguishable from one a person wrote, that the report
    # cannot un-write. What stands between this repr and a reader is the
    # schema boundary the test above pins, not anything downstream of it.
    state = merged(a_map(), [a_lane("claude", waits=[NON_STRING_WAIT])])
    assert state["next_action"]["text"] == "Answer the decision: {'raw': 1}"
    brief = line_starting(report.render(state), "- Next action:")
    # The equality pins the whole line: the repr sits inside it and opens nothing.
    assert brief == "- Next action: Answer the decision: {'raw': 1}"


def test_the_report_command_breaks_a_non_string_wait_title_lane_at_the_boundary(
        tmp_path, capsys):
    # Through the commands the boundary is real: the lane fails validation in
    # `store.load`, the wait never reaches the queue, and the report says the
    # lane could not be read instead of printing the repr anywhere.
    body = json.dumps({"schema_version": 1, "author": "claude",
                       "updated": "2026-07-30T11:00:00+00:00",
                       "waits_on_human": [NON_STRING_WAIT]})
    root = write_project(tmp_path, lanes={"claude": body})
    assert main(["report", "--dir", str(root)]) == 0
    printed = capsys.readouterr().out
    assert "Lanes that could not be read" in printed
    assert "### `w-1`" not in printed
    assert "{'raw': 1}" not in printed


# --- no network -------------------------------------------------------------


#: Import roots that mean a module can reach off the machine, plus the two
#: process-spawning roots that could reach one indirectly.
NETWORKING_ROOTS = {"socket", "ssl", "http", "urllib", "urllib3", "asyncio",
                    "selectors", "select", "ftplib", "smtplib", "poplib",
                    "imaplib", "telnetlib", "xmlrpc", "requests", "httpx",
                    "aiohttp", "webbrowser", "subprocess", "multiprocessing"}


def _root_of(dotted):
    return dotted.split(".", 1)[0]


def _imported_modules(path):
    """Every module name the source at `path` imports, dotted and by root."""
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def test_the_report_source_names_no_networking_module_anywhere():
    # The import-closure measurement in tests/test_report_determinism.py cannot
    # see a deferred import inside a function that never runs; this reads the
    # source, where such an import would still be.
    imported = _imported_modules(REPORT_SOURCE)
    assert {name for name in imported if _root_of(name) in NETWORKING_ROOTS} == set()


# --- the report and the panel cannot describe different states --------------


def _without_the_stamp(text):
    """The report minus its one `generated_at` line.

    Two merges of an unchanged project differ on that field and no other — the
    server's own change detection drops it for the same reason
    (`Broker.refresh`), and the guard above proves the report puts it on
    exactly one line. It is what a document merged by the panel and a document
    merged by the command may legitimately not share.
    """
    return [ln for ln in text.splitlines() if not ln.startswith("- `generated_at`")]


def test_the_report_and_the_panel_are_handed_the_same_document(tmp_path, capsys):
    lane_body = json.dumps({
        "schema_version": 1, "author": "claude", "role": "impl",
        "updated": "2026-07-30T11:00:00+00:00",
        "findings": [a_finding()],
        "waits_on_human": [{"id": "w-1", "kind": "decision", "title": "t",
                            "why": "w", "blocks": ["D-1"]}]})
    # schema_version 2 is accepted with a loader-level warning (§5). It is in
    # the fixture on purpose: warnings reach the document only because both
    # callers pass `extra_warnings` through, and a project without one cannot
    # tell a caller that drops them from a caller that does not.
    reviewer_body = json.dumps({"schema_version": 2, "author": "codex", "role": "rev",
                                "updated": "2026-07-30T11:30:00+00:00"})
    map_toml = ('schema_version = 1\nproject = "p"\n'
                '[[nodes]]\nid = "n"\nlabel = "n"\nkind = "artifact"\n'
                '[[cycle.roles]]\nid = "impl"\nreviews = []\n'
                '[[cycle.roles]]\nid = "rev"\nreviews = ["impl"]\n')
    root = write_project(tmp_path, map_toml=map_toml,
                         lanes={"claude": lane_body, "codex": reviewer_body})
    srv, base = start(root)
    try:
        panel_state = json.loads(get(base + "/state.json")[1].decode("utf-8"))
    finally:
        srv.shutdown()
        srv.server_close()
    cli_state = validate.merged_state(store.load(root))
    # `generated_at` is the one field two merges of an unchanged project may
    # legitimately differ on — the server's own change detection drops it for
    # the same reason (`Broker.refresh`).
    stamp = NOW.isoformat()
    panel_state["generated_at"] = cli_state["generated_at"] = stamp
    assert panel_state == cli_state
    assert report.render(panel_state) == report.render(cli_state)
    # The document was rich enough for a divergence to have somewhere to show.
    rendered = report.render(cli_state)
    assert "### `D-1`" in rendered and "### `w-1`" in rendered
    assert cli_state["warnings"] and "## Merger warnings — 1" in rendered
    # And the command itself, not a transcription of what it does: everything
    # `conduct report` puts on stdout is the report of the document the panel
    # served. A command that dropped, added to or reworded any part of the
    # document on its way to the reader reds here and nowhere else.
    assert main(["report", "--dir", str(root)]) == 0
    printed = capsys.readouterr()
    assert printed.err == ""
    assert _without_the_stamp(printed.out) == _without_the_stamp(
        report.render(panel_state))
