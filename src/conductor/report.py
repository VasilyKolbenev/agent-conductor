"""Deterministic Markdown reports and handoffs from one merged `state.json`.

`render(state)` is a pure function of the document it is handed: the same dict
renders the same bytes, on any machine, at any time, under any locale. Nothing
here reads the clock, the environment, the network or the disk — the report has
no inputs besides its argument, and no module-level import that could acquire
one.

`handoff(state, author)` applies the same rule to one lane. It groups that
lane's existing §6.1 fields with the findings it authored and human requests
whose `sources` name it. It does not add capability placeholders: model,
prompt, skills and runtime controls are not fields in Protocol v1, so they are
not headings in the packet.

**It does not merge.** `state.json` is the merger's output (PROTOCOL.md §6) and
this module only reads it, so the report and the panel cannot disagree about
what a project's state is: they render the same document. Field values are
copied, never recomputed; the counts and the groupings come from the document's
own lists. Where a line reads more than one field — `Verification` under each
finding — the line names the fields §6 states the rule over: `review_state` and
`cycle.roles[].reviews`. The author's lane `role`, which `verify()` looks up to
join those two, is not named there.

Four ways a report like this could lie, and what is done about each:

1. **`agreed` is not `checked`.** §6's review-state table makes `agreed`
   vacuous for a finding whose author's role is reviewed by nobody: no
   obligation exists, so none is unmet. `verify()` separates that case out and
   `Verification.verified` is False for it. The predicate is the one §6 states —
   the author's lane role against the roles named in `cycle.roles[].reviews` —
   and the phrase "no reviewer assigned" is §6's own wording for the row.
2. **Evidence is authored text.** `findings[].evidence` was written by a person
   or an agent, and this report quotes it whole, inside a fence long enough that
   nothing in it needs escaping. It is never summarised and never truncated, so
   there is no truncation the report could fail to disclose. `detail` is quoted
   the same way when it has words in it. Every *other* value the document holds
   — authored prose and identifier alike, a finding's `title`, a wait's `id`, a
   verdict's `disposition` — reaches the reader through `_from_document`, which
   puts it on the one line it is rendered into and says so when that changed the
   author's bytes. What a document value cannot do is add a line, close the code
   span around itself, or open a heading, a list or a fence this report never
   wrote. It can still quote a sentence this report also writes: nothing here
   escapes inline markup.
3. **Absence is not an answer.** Everything the document does not know gets a
   line of its own under "What this report does not know" — an `unknown`
   project state, unreviewed and uncovered findings, vacuous agreement, a
   missing `current_phase` (§6.1: absent, never null), roles with no `stage`,
   unreadable lanes, and an empty queue. An empty queue is the absence of a
   request, not a record that anything was agreed.
4. **Recorded and empty is not missing.** A field the document records with no
   words in it — an empty string, or whitespace — is reported as recorded and
   empty. "None recorded in the document" is kept for the field the document
   does not record at all, because the other reading is a false statement about
   the document that wrote the field.

Points 2 and 4 rest on one structural fact rather than on remembering them at
each rendering site: `_from_document` is the only path from the document to a
rendered line, in either shape the report has. `tests/test_report_funnel.py`
reads this module's AST and reds when a line is *built* out of a document value
anywhere else — an f-string, or a string joined to a string. Returning a
document value as a line of its own is not a shape that reading sees; only a
rendered report shows it. That test's docstring says which is which.

Ordering is taken from the document: lists render in the order the merger built
them. `findings[].verdicts` is the one exception — it is a JSON object, whose
order no serializer promises to preserve, so its authors are sorted. No set is
ever iterated, so a different hash seed cannot reorder a line.
"""
from __future__ import annotations

import json
import re
from typing import NamedTuple


class Verification(NamedTuple):
    """How much review a finding's `review_state` actually stands on.

    Attributes:
        verified: True only when the document shows a review that confirmed
            the finding. Vacuous agreement — `agreed` with no role assigned to
            review the author's role — is False, as is every other state.
        label: One clause naming what the document shows, for rendering.
    """

    verified: bool
    label: str


#: Every `review_state` other than `agreed`, none of which is a check passing.
#: `agreed` is absent on purpose: it is the only value whose meaning depends on
#: a second field, and `verify()` resolves it.
_UNVERIFIED = {
    "disagreement": Verification(
        False, "disputed — another lane recorded a refuted or partial verdict"),
    "unreviewed": Verification(
        False, "not reviewed — a role that owes a verdict has not given one"),
    "uncovered": Verification(
        False, "no reviewer available — a reviewing role exists in the map but "
               "no lane holds it"),
    "suspended": Verification(
        False, "suspended — the finding id is claimed by more than one lane, so "
               "verdict attribution is ambiguous"),
}


#: The two shapes a value taken from the document is rendered in: a sentence of
#: the report's own prose, or a code span. `_from_document` builds both, and
#: nothing else in this module builds either.
_PROSE = "prose"
_SPAN = "span"

#: Said beside a value whose line breaks were flattened. The substitution
#: changes the document's bytes, so it cannot pass unstated.
_FLATTENED = (" — the document records this field with line breaks in it, shown "
              "here as `\\n`: the field renders on one line, so its text cannot "
              "open a heading or a list of its own")

#: For a field reached only when the document records it, and records it null.
#: Not an absence either: JSON null is what the document chose to write.
_RECORDED_NULL = "(the document records this field as `null`)"


def _one_line(text: str) -> tuple[str, str]:
    """Put text on one line, and say beside it when that changed its bytes.

    A line break in a value would end the line the value is rendered into, and
    everything after it would be read as Markdown this report never wrote — a
    heading, a list item, a fence. Line breaks are shown as the two characters
    `\\n` instead.

    Args:
        text: The value's text, as the document records it.

    Returns:
        `(the one line, what to disclose beside it)`. The disclosure is empty
        when the text held no line break and the line is the document's bytes.
    """
    if "\n" not in text and "\r" not in text:
        return text, ""
    flat = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n")
    return flat, _FLATTENED


def _span(text: str) -> str:
    """Wrap one line in a code span that line cannot reshape.

    CommonMark closes a code span at the first backtick run as long as the run
    that opened it, so the fence here is one backtick longer than the longest
    run inside it. CommonMark also strips one space from each end of a span
    that has one at both ends, so text beginning or ending with a backtick or a
    space is padded to survive that strip byte for byte.
    """
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * (longest + 1)
    pad = " " if text.strip(" ") and (text[0] in "` " or text[-1] in "` ") else ""
    return f"{fence}{pad}{text}{pad}{fence}"


def _blank(text: str) -> str:
    """Say what a field holds when the document records it with no words in it.

    Not an absence. The document records the field, so reporting it as missing
    would be a false statement about the document that wrote it.
    """
    if not text:
        return "(the document records this field as an empty string)"
    return ("(the document records this field, and it holds only whitespace: "
            f"{_span(json.dumps(text))})")


def _from_document(value: object, shape: str, absent: str | None = None) -> str:
    """The one door out of the document: every value the report prints uses it.

    Four things a value could do to the report are handled here, once, instead
    of at each site that renders one: a line break that would end the line it
    renders into, a backtick run that would close the code span around it, a
    field the document records with no words in it, and a value that is not a
    string. Four cases the report must not confuse, and only the second is an
    absence: text, a field the document does not record, a field it records
    empty, and a non-string. A non-string never renders as prose — it is
    reported as JSON, so no value the merger stored as data can read as a
    sentence somebody wrote.

    Values this function is not given cannot be protected by it:
    `findings[].detail` and `[].evidence` take the verbatim path through
    `_verbatim` by design, and a value the *merger* has already folded into a
    string — `next_action.text` is built from a wait's unvalidated `title`
    (`merge._next_action`) — arrives here as text and is rendered as text.

    Args:
        value: The document's value for the field.
        shape: `_PROSE` to render it as a sentence, `_SPAN` as a code span.
        absent: What `_PROSE` says when the document does not record the field
            at all. `_SPAN` needs none: it renders a missing field as `null`,
            which is what the document's own JSON would have said.

    Returns:
        One line, safe to place wherever the report renders a line.
    """
    if shape == _PROSE:
        if value is None:
            return absent
        if not isinstance(value, str):
            return ("(not a sentence: the document records a non-string value "
                    f"{_from_document(value, _SPAN)})")
        if not value.strip():
            return _blank(value)
        flat, disclosed = _one_line(value)
        return flat + disclosed
    text = (value if isinstance(value, str) and value
            else json.dumps(value, ensure_ascii=False, sort_keys=True))
    flat, disclosed = _one_line(text)
    return _span(flat) + disclosed


def _id_list(value: object) -> str:
    """Render a list of ids as code spans in document order; tolerate non-lists."""
    if isinstance(value, list):
        return ", ".join(_from_document(v, _SPAN) for v in value) if value else "none"
    return _from_document(value, _SPAN)


def _verbatim(text: str) -> list[str]:
    """Fence `text` so it reaches the reader byte for byte.

    The fence is one backtick longer than the longest backtick run inside the
    text, so no authored content can close it early and nothing needs escaping.

    Args:
        text: The authored text to quote whole.

    Returns:
        The fenced lines, opening and closing fence included.
    """
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    return [fence, *text.split("\n"), fence]


def _reviewed_roles(state: dict) -> list:
    """Every role that some role is declared to review (`cycle.roles[].reviews`).

    A list rather than a set: it is only ever tested for membership, and a list
    cannot reorder a rendered line when the hash seed changes.
    """
    out = []
    for role in (state.get("cycle") or {}).get("roles") or []:
        for reviewed in role.get("reviews") or []:
            out.append(reviewed)
    return out


def _author_role(finding: dict, state: dict) -> object:
    """The `role` of the lane that authored `finding`, or None if it has none."""
    for lane in state.get("lanes") or []:
        if lane.get("author") == finding.get("author"):
            return lane.get("role")
    return None


def verify(finding: dict, state: dict) -> Verification:
    """Say what review the document actually shows behind one finding's state.

    Reads `review_state` together with `cycle.roles[].reviews` and the author's
    lane `role`. No merge rule is re-run: a finding whose document says
    `agreed` is reported as agreed, and the second field only decides whether
    that agreement rests on an assigned reviewer or on nobody.

    Args:
        finding: One entry of `state["findings"]`.
        state: The whole `state.json` dict the finding came from.

    Returns:
        A `Verification`. `verified` is True only for `agreed` whose author's
        role some role is declared to review.
    """
    review_state = finding.get("review_state")
    if review_state != "agreed":
        return _UNVERIFIED.get(review_state) or Verification(
            False, f"unrecognised review state {_from_document(review_state, _SPAN)} "
                   "— this report makes no claim about it")
    if _author_role(finding, state) in _reviewed_roles(state):
        return Verification(
            True, "agreed — every role assigned to review it gave a verdict and "
                  "every verdict from another lane confirms it")
    return Verification(
        False, "agreed with no reviewer assigned — no role is declared to review "
               "this author's role, so nothing was checked and the agreement is "
               "vacuous")


def _header(state: dict) -> list[str]:
    """The title and the two document-level facts a reader needs first."""
    return [
        f"# Conduct report — "
        f"{_from_document(state.get('project'), _PROSE, '(unnamed project)')}",
        "",
        "Source: one `state.json` document, the merger's output. Every value is "
        "copied from it, never recomputed; the counts and groupings below are drawn "
        "from that document and from nothing else.",
        "",
        f"- `generated_at`, as the document records it: "
        f"{_from_document(state.get('generated_at'), _SPAN)}",
        f"- `schema_version`: {_from_document(state.get('schema_version'), _SPAN)}",
    ]


def _decision_brief(state: dict) -> list[str]:
    """`project_status` and `next_action`, each field named as the document names it."""
    status = state.get("project_status") or {}
    action = state.get("next_action")
    out = [
        "## Decision brief",
        "",
        f"- Project state: {_from_document(status.get('state'), _SPAN)}, "
        f"reason {_from_document(status.get('reason'), _SPAN)}",
        f"- Detail: "
        f"{_from_document(status.get('detail'), _PROSE, '(no detail in the document)')}",
    ]
    if isinstance(action, dict):
        out += [
            f"- Next action: "
            f"{_from_document(action.get('text'), _PROSE, '(no text in the document)')}",
            f"  - kind {_from_document(action.get('kind'), _SPAN)}, "
            f"ref {_from_document(action.get('ref'), _SPAN)}",
        ]
    else:
        out.append(
            f"- Next action: {_from_document(action, _SPAN)} — the merger names no "
            "next move. That is the absence of a computed action, not a finding "
            "that the work is done.")
    return out


def _queue_item(item: dict) -> list[str]:
    """One `human_queue` entry, headed by its id — never by its title.

    `schema._validate_lane_waits` constrains a wait's `id`, `kind` and
    `blocks`, and `title` is not among them. Heading a section with an
    unvalidated `title` is how a Python `repr` becomes a heading, so the title
    is reported as a field. The `id` it is headed by is constrained only to be
    a non-empty string — nothing says what may be inside one, which is why the
    heading takes it through `_from_document` like everything else.
    """
    return [
        f"### {_from_document(item.get('id'), _SPAN)} — "
        f"kind {_from_document(item.get('kind'), _SPAN)}",
        "",
        f"- Title: "
        f"{_from_document(item.get('title'), _PROSE, '(the lane recorded no title)')}",
        f"- Why: "
        f"{_from_document(item.get('why'), _PROSE, '(the lane recorded no reason)')}",
        f"- Blocks: {_id_list(item.get('blocks'))}",
        f"- Reported by: {_id_list(item.get('sources'))}",
        "",
    ]


def _queue(state: dict) -> list[str]:
    """The human queue, or an empty queue said plainly enough to not read as consent."""
    queue = state.get("human_queue") or []
    if not queue:
        return [
            "## Human queue — empty",
            "",
            "No lane records a request waiting on a person.",
            "",
            "An empty queue is the absence of a request. It is not a record that any "
            "question was put and answered, and nothing in this report becomes agreed "
            "because nobody objected to it.",
        ]
    out = [f"## Human queue — {len(queue)} waiting on a person", ""]
    for item in queue:
        out += _queue_item(item)
    return out


def _verdicts(finding: dict) -> list[str]:
    """Every recorded verdict on one finding, authors sorted, notes quoted.

    A verdict that records a `note` gets a note line whatever the note holds:
    an empty one is a note the reviewer wrote nothing into, not a note nobody
    wrote, and the two must not read alike. A verdict recording no `note` at
    all gets no line.
    """
    verdicts = finding.get("verdicts")
    if not isinstance(verdicts, dict) or not verdicts:
        return ["- Verdicts: none recorded"]
    out = ["- Verdicts:"]
    for author in sorted(verdicts, key=str):   # a JSON object carries no order to take
        entry = verdicts[author] if isinstance(verdicts[author], dict) else {}
        own = (" — self-verdict, ignored for `review_state` (§6)"
               if author == finding.get("author") else "")
        out.append(f"  - {_from_document(author, _SPAN)} "
                   f"(role {_from_document(entry.get('role'), _SPAN)}): "
                   f"{_from_document(entry.get('disposition'), _SPAN)}{own}")
        if "note" in entry:                    # a recorded null reaches `_RECORDED_NULL`
            out.append(f"    - note, as written: "
                       f"{_from_document(entry.get('note'), _PROSE, _RECORDED_NULL)}")
    return out


def _evidence(finding: dict) -> list[str]:
    """`detail` and `evidence` quoted whole — no summary, no truncation.

    Both take the same two paths, because the two fields make the same promise:
    text with words in it is fenced whole, and everything else — recorded and
    empty, recorded as something that is not a string, not recorded at all —
    goes through `_from_document`, which tells those three apart.
    """
    out = [""]
    detail = finding.get("detail")
    if isinstance(detail, str) and detail.strip():
        out += ["Detail, as the author wrote it:", "", *_verbatim(detail), ""]
    else:
        out += [f"Detail: "
                f"{_from_document(detail, _PROSE, 'none recorded in the document')}.",
                ""]
    evidence = finding.get("evidence")
    if isinstance(evidence, str) and evidence.strip():
        out += ["Evidence, as the author wrote it — quoted whole, not summarised:",
                "", *_verbatim(evidence), ""]
    else:
        out += [f"Evidence: "
                f"{_from_document(evidence, _PROSE, 'none recorded in the document')}.",
                ""]
    return out


def _finding(finding: dict, state: dict) -> list[str]:
    """One finding: its own fields, what review stands behind it, its evidence."""
    out = [
        f"### {_from_document(finding.get('id'), _SPAN)} — "
        f"severity {_from_document(finding.get('severity'), _SPAN)} — "
        f"reported by {_from_document(finding.get('author'), _SPAN)}",
        "",
        f"- Title: "
        f"{_from_document(finding.get('title'), _PROSE, '(no title in the document)')}",
        f"- `review_state`, as the document records it: "
        f"{_from_document(finding.get('review_state'), _SPAN)}",
        f"- Verification (read from `review_state` and `cycle.roles[].reviews`): "
        f"{verify(finding, state).label}",
        f"- Claim, the author's own label: "
        f"{_from_document(finding.get('claim'), _PROSE, '(no claim in the document)')}",
        f"- Refs: {_id_list(finding.get('refs'))}",
    ]
    return out + _verdicts(finding) + _evidence(finding)


def _findings(state: dict) -> list[str]:
    """Every finding in document order, or the honest reading of having none."""
    findings = state.get("findings") or []
    if not findings:
        return [
            "## Findings — none",
            "",
            "No lane reports an open finding. That is what the lanes say; it is not "
            "a record that anything was checked.",
        ]
    out = [f"## Findings — {len(findings)}", ""]
    for finding in findings:
        out += _finding(finding, state)
    return out


def _unknown_status(state: dict) -> list[str]:
    """The line for an `unknown` project state, when that is what the document says."""
    status = state.get("project_status") or {}
    if status.get("state") != "unknown":
        return []
    return [f"- The project state is `unknown` "
            f"(reason {_from_document(status.get('reason'), _SPAN)}): "
            f"{_from_document(status.get('detail'), _PROSE, '(no detail in the document)')}"]


#: Each `review_state` whose findings the unknown section names, and the clause
#: naming it. A table rather than four literals inline, so the clause a line
#: renders is the report's own text and reaches it from nowhere else.
_REVIEW_GAPS = (
    ("unreviewed", "awaiting a verdict from a role that owes one"),
    ("uncovered", "whose reviewing role exists in the map but no lane holds"),
    ("agreed",
     "agreed with no role declared to review their author — vacuous, not a check"),
    ("suspended", "suspended: the id is claimed by more than one lane"),
)


def _unknown_review(state: dict) -> list[str]:
    """One line per way a finding's review standing is not a check that passed."""
    findings = state.get("findings") or []
    out = []
    for review_state, why in _REVIEW_GAPS:
        group = [f for f in findings if f.get("review_state") == review_state]
        if review_state == "agreed":       # only the vacuous half of `agreed`
            group = [f for f in group if not verify(f, state).verified]
        if group:
            out.append(f"- Findings {why}: "
                       f"{_id_list([f.get('id') for f in group])}")
    return out


def _unknown_cycle(state: dict) -> list[str]:
    """A missing `current_phase` and roles the map gives no `stage`."""
    cycle = state.get("cycle") or {}
    out = []
    if "current_phase" not in cycle:
        out.append("- No lane declares a current phase, so the document has none. "
                   "`current_phase` is absent, not null (§6.1), and the cycle in the "
                   "panel renders statically.")
    unstaged = [r.get("id") for r in cycle.get("roles") or [] if "stage" not in r]
    if unstaged:
        out.append(f"- Roles the map gives no `stage`: {_id_list(unstaged)}. Where "
                   "each should work is not recorded.")
    return out


def _unknown_lanes(state: dict) -> list[str]:
    """Lanes the loader could not read, whose contents are therefore absent."""
    broken = [ln.get("author") for ln in state.get("lanes") or [] if ln.get("broken")]
    if not broken:
        return []
    return [f"- Lanes that could not be read: {_id_list(broken)}. Nothing they would "
            "have reported is in this document."]


def _unknown_queue(state: dict) -> list[str]:
    """The empty queue, stated as an absence of requests rather than of questions."""
    if state.get("human_queue"):
        return []
    return ["- The human queue is empty. No request is recorded as waiting — and none "
            "is recorded as answered. Silence is not consent."]


def _unknown(state: dict) -> list[str]:
    """Everything the document does not know, gathered into a section of its own."""
    items = (_unknown_status(state) + _unknown_review(state) + _unknown_cycle(state)
             + _unknown_lanes(state) + _unknown_queue(state))
    out = ["## What this report does not know", ""]
    if not items:
        return out + ["None of the gaps this report looks for is present in the "
                      "document."]
    return out + items


def _warnings(state: dict) -> list[str]:
    """The merger's own warnings, in the order it recorded them."""
    warnings = state.get("warnings") or []
    if not warnings:
        return ["## Merger warnings — none", "",
                "The merger recorded no warning about this document."]
    return ([f"## Merger warnings — {len(warnings)}", ""]
            + [f"- {_from_document(w, _PROSE, '(empty warning)')}" for w in warnings])


#: Every section, in the order they are rendered. One list so that adding a
#: section cannot forget to render it and cannot change the joining rule.
_SECTIONS = (_header, _decision_brief, _queue, _findings, _unknown, _warnings)


def render(state: dict) -> str:
    """Render one `state.json` document as a Markdown report.

    Pure: the only input is `state`. The same document renders the same bytes —
    no clock, no locale, no environment, no network, no disk. The document's
    own `generated_at` is the single timestamp shown, and it is shown as
    recorded.

    Args:
        state: A `state.json` dict per PROTOCOL.md §6.1. Additional fields are
            tolerated and not rendered; missing fields are reported as missing
            rather than substituted, and a field the document records empty is
            reported as recorded and empty.

    Returns:
        The report as Markdown text, ending in exactly one newline.
    """
    blocks = [section(state) for section in _SECTIONS]
    body = "\n\n".join("\n".join(block).strip("\n") for block in blocks if block)
    return body + "\n"


def handoff(state: dict, author: str) -> str:
    """Render the current packet for one lane, from §6.1 fields only.

    The packet is a grouping, not a new state projection. Lane metadata is
    copied from `lanes[]`; harness, stage and review obligations come from the
    matching `cycle.roles[]` row; findings are selected by `author`; human
    requests are selected by `sources`. Their order is the document's order.
    Nothing is inferred from a missing row or field, and nothing reads the
    clock, disk, environment or network.

    Args:
        state: A merged `state.json` dict per Protocol v1 §6.1.
        author: The exact `lanes[].author` to hand off from.

    Returns:
        A Markdown packet ending in exactly one newline.

    Raises:
        KeyError: No lane in the document records that author.
    """
    lanes = state.get("lanes") or []
    lane = next((item for item in lanes if item.get("author") == author), None)
    if lane is None:
        raise KeyError(author)

    role_id = lane.get("role")
    roles = (state.get("cycle") or {}).get("roles") or []
    role = next((item for item in roles if item.get("id") == role_id), {})
    now = lane.get("now") if isinstance(lane.get("now"), dict) else {}
    findings = [item for item in state.get("findings") or []
                if item.get("author") == author]
    waits = [item for item in state.get("human_queue") or []
             if author in (item.get("sources") or [])]

    out = [
        f"# Conduct handoff — {_from_document(author, _PROSE, '(unknown author)')}",
        "",
        f"Project: "
        f"{_from_document(state.get('project'), _PROSE, '(unnamed project)')}",
        "",
        "## Lane",
        "",
        f"- Author: {_from_document(lane.get('author'), _SPAN)}",
        f"- Role: {_from_document(role_id, _SPAN)}",
        f"- Harness: {_from_document(role.get('harness'), _SPAN)}",
        f"- Assigned stage: {_from_document(role.get('stage'), _SPAN)}",
        f"- Reviews roles: {_id_list(role.get('reviews'))}",
        f"- Updated: {_from_document(lane.get('updated'), _SPAN)}",
        f"- Stale: {_from_document(lane.get('stale'), _SPAN)}",
        f"- Broken: {_from_document(lane.get('broken'), _SPAN)}",
        f"- Current task: "
        f"{_from_document(now.get('task'), _PROSE, '(not recorded in state.json)')}",
        f"- Runtime phase: {_from_document(now.get('phase'), _SPAN)}",
        f"- Task since: {_from_document(now.get('since'), _SPAN)}",
    ]
    if lane.get("error") is not None:
        out.append(f"- Lane error: "
                   f"{_from_document(lane.get('error'), _PROSE, _RECORDED_NULL)}")

    out += ["", f"## Findings from this lane — {len(findings)}", ""]
    if findings:
        for finding in findings:
            out += _finding(finding, state)
    else:
        out.append("No finding in the document names this lane as its author.")

    out += ["", f"## Human requests from this lane — {len(waits)}", ""]
    if waits:
        for item in waits:
            out += _queue_item(item)
    else:
        out.append("No human-queue item in the document names this lane as a source.")

    return "\n".join([*out, ""])
