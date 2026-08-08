"""A deterministic Markdown report of one merged `state.json`, for a pull request.

`render(state)` is a pure function of the document it is handed: the same dict
renders the same bytes, on any machine, at any time, under any locale. Nothing
here reads the clock, the environment, the network or the disk — the report has
no inputs besides its argument, and no module-level import that could acquire
one.

**It does not merge.** `state.json` is the merger's output (PROTOCOL.md §6) and
this module only reads it, so the report and the panel cannot disagree about
what a project's state is: they render the same document. Field values are
copied, never recomputed; the counts and the groupings come from the document's
own lists. Where a line reads more than one field — `Verification` under each
finding — the line says which fields it read.

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
   the same way. Every *other* authored field — a finding's `title` and `claim`,
   a wait's `title` and `why`, `project_status.detail`, `next_action.text`, a
   verdict `note`, a merger warning — renders inside a bullet, where a line
   break would end that bullet and let what follows open a heading, a list or a
   fence this report never wrote. `_one_line` puts those fields on the one line
   they are rendered into and says so. It does not escape inline markup, and it
   cannot stop an authored field from quoting a sentence this report also
   writes: what an authored field cannot do is add a line.
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


def _code(value: object) -> str:
    """Render any JSON value as a code span, strings bare and the rest as JSON."""
    if isinstance(value, str):
        return f"`{value}`"
    return f"`{json.dumps(value, ensure_ascii=False, sort_keys=True)}`"


def _one_line(text: str) -> str:
    """Put authored text on the one line it is rendered into.

    Every authored field but `findings[].evidence` and `findings[].detail` is
    rendered inside a bullet or a sentence. A line break in one of them would
    end that line, and everything after it would be read as Markdown this
    report never wrote — a heading, a list item, a fence. Line breaks are shown
    as the two characters `\\n` instead, and the line says so: the substitution
    changes the author's bytes, so it cannot pass unstated.

    Args:
        text: The authored text, as the document records it.

    Returns:
        `text` unchanged when it holds no line break; otherwise one line, with
        the substitution disclosed on it.
    """
    if "\n" not in text and "\r" not in text:
        return text
    shown = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n")
    return (f"{shown} — the document records this field with line breaks in it, "
            "shown here as `\\n`: the field renders on one line, so its text "
            "cannot open a heading or a list of its own")


def _blank(text: str) -> str:
    """Say what an authored field holds when it holds no words.

    Not an absence. The document records the field, so reporting it as missing
    would be a false statement about the document that wrote it.
    """
    if not text:
        return "(the document records this field as an empty string)"
    return ("(the document records this field, and it holds only whitespace: "
            f"`{json.dumps(text)}`)")


def _authored(value: object, absent: str) -> str:
    """Render an authored string as prose, or say what the document holds instead.

    Four cases the report must not confuse: text, a field the document does not
    record, a field it records with no words in it, and a field holding
    something that is not a string. Only the second is an absence and only it
    gets `absent`. A value that is not a string is never rendered as prose; it
    is reported as JSON in a code span, so a Python `repr` can never pass for a
    sentence somebody wrote. `waits_on_human[].title` and `[].why` reach this
    function unvalidated — `schema._validate_lane_waits` checks a wait's `id`,
    `kind` and `blocks` and not those two.

    Args:
        value: The document's value for the field.
        absent: What to say when the document does not record the field.

    Returns:
        The author's own text on one line, or a statement about the field.
    """
    if isinstance(value, str):
        return _one_line(value) if value.strip() else _blank(value)
    if value is None:
        return absent
    return ("(not a sentence: the document records a non-string value "
            f"{_code(value)})")


def _id_list(value: object) -> str:
    """Render a list of ids as code spans in document order; tolerate non-lists."""
    if isinstance(value, list):
        return ", ".join(_code(v) for v in value) if value else "none"
    return _code(value)


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
            False, f"unrecognised review state {_code(review_state)} — this report "
                   "makes no claim about it")
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
        f"# Conduct report — {_authored(state.get('project'), '(unnamed project)')}",
        "",
        "Source: one `state.json` document, the merger's output. Every value is "
        "copied from it, never recomputed; the counts and groupings below are drawn "
        "from that document and from nothing else.",
        "",
        f"- `generated_at`, as the document records it: {_code(state.get('generated_at'))}",
        f"- `schema_version`: {_code(state.get('schema_version'))}",
    ]


def _decision_brief(state: dict) -> list[str]:
    """`project_status` and `next_action`, each field named as the document names it."""
    status = state.get("project_status") or {}
    action = state.get("next_action")
    out = [
        "## Decision brief",
        "",
        f"- Project state: {_code(status.get('state'))}, "
        f"reason {_code(status.get('reason'))}",
        f"- Detail: {_authored(status.get('detail'), '(no detail in the document)')}",
    ]
    if isinstance(action, dict):
        out += [
            f"- Next action: "
            f"{_authored(action.get('text'), '(no text in the document)')}",
            f"  - kind {_code(action.get('kind'))}, ref {_code(action.get('ref'))}",
        ]
    else:
        out.append(
            f"- Next action: {_code(action)} — the merger names no next move. That is "
            "the absence of a computed action, not a finding that the work is done.")
    return out


def _queue_item(item: dict) -> list[str]:
    """One `human_queue` entry, headed by its id — never by its title.

    `id` and `kind` are the only fields of a wait the schema constrains; `title`
    is not among them. Heading a section with an unvalidated `title` is how a
    Python `repr` becomes a heading, so the title is reported as a field.
    """
    return [
        f"### {_code(item.get('id'))} — kind {_code(item.get('kind'))}",
        "",
        f"- Title: {_authored(item.get('title'), '(the lane recorded no title)')}",
        f"- Why: {_authored(item.get('why'), '(the lane recorded no reason)')}",
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
    """Every recorded verdict on one finding, authors sorted, notes quoted."""
    verdicts = finding.get("verdicts")
    if not isinstance(verdicts, dict) or not verdicts:
        return ["- Verdicts: none recorded"]
    out = ["- Verdicts:"]
    for author in sorted(verdicts, key=str):   # a JSON object carries no order to take
        entry = verdicts[author] if isinstance(verdicts[author], dict) else {}
        own = (" — self-verdict, ignored for `review_state` (§6)"
               if author == finding.get("author") else "")
        out.append(f"  - {_code(author)} (role {_code(entry.get('role'))}): "
                   f"{_code(entry.get('disposition'))}{own}")
        note = entry.get("note")
        if isinstance(note, str) and note.strip():
            out.append(f"    - note, as written: {_one_line(note)}")
    return out


def _evidence(finding: dict) -> list[str]:
    """`detail` and `evidence` quoted whole — no summary, no truncation."""
    out = [""]
    detail = finding.get("detail")
    if isinstance(detail, str) and detail.strip():
        out += ["Detail, as the author wrote it:", "", *_verbatim(detail), ""]
    evidence = finding.get("evidence")
    if isinstance(evidence, str) and evidence.strip():
        out += ["Evidence, as the author wrote it — quoted whole, not summarised:",
                "", *_verbatim(evidence), ""]
    else:
        # `_authored` for the rest: a recorded-but-empty `evidence` is not a
        # missing one, and neither is a value that is not a string.
        out += [f"Evidence: {_authored(evidence, 'none recorded in the document')}.",
                ""]
    return out


def _finding(finding: dict, state: dict) -> list[str]:
    """One finding: its own fields, what review stands behind it, its evidence."""
    out = [
        f"### {_code(finding.get('id'))} — severity {_code(finding.get('severity'))} "
        f"— reported by {_code(finding.get('author'))}",
        "",
        f"- Title: {_authored(finding.get('title'), '(no title in the document)')}",
        f"- `review_state`, as the document records it: "
        f"{_code(finding.get('review_state'))}",
        f"- Verification (read from `review_state` and `cycle.roles[].reviews`): "
        f"{verify(finding, state).label}",
        f"- Claim, the author's own label: "
        f"{_authored(finding.get('claim'), '(no claim in the document)')}",
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
    return [f"- The project state is {_code('unknown')} "
            f"(reason {_code(status.get('reason'))}): "
            f"{_authored(status.get('detail'), '(no detail in the document)')}"]


def _unknown_review(state: dict) -> list[str]:
    """One line per way a finding's review standing is not a check that passed."""
    findings = state.get("findings") or []
    groups = (
        ("awaiting a verdict from a role that owes one",
         [f for f in findings if f.get("review_state") == "unreviewed"]),
        ("whose reviewing role exists in the map but no lane holds",
         [f for f in findings if f.get("review_state") == "uncovered"]),
        ("agreed with no role declared to review their author — vacuous, not a check",
         [f for f in findings if f.get("review_state") == "agreed"
          and not verify(f, state).verified]),
        ("suspended: the id is claimed by more than one lane",
         [f for f in findings if f.get("review_state") == "suspended"]),
    )
    out = []
    for why, group in groups:
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
            + [f"- {_authored(w, '(empty warning)')}" for w in warnings])


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
