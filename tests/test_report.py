"""Guards for `conductor.report` — the deterministic Markdown report of one state.

Every guard here is written against a *relation* the report promises, not
against a word it happens to contain. The two that carry the most weight both
work by building a pair of documents that differ in exactly one respect and
demanding that the report tell them apart:

* a finding whose `review_state` is `agreed` with a role assigned to review its
  author, against the same `agreed` with nobody assigned. The merger writes the
  same five letters for both — a report that renders them alike has erased the
  vacuous-agreement disclosure DO-2 was opened for, and the guard reds;
* a document whose `review_state` contradicts its own verdicts. The report must
  print what the document says, because it is not a second merger. A report
  that recomputes anything reds on that pair.

The determinism claim is measured, not asserted: the same document is rendered
in three child interpreters under different hash seeds, time zones and locales,
and the three files are compared byte for byte.
"""
import ast
import copy
import json
import os
import subprocess
import sys
import tempfile
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


def a_map(roles=(), phases=(), project="p"):
    """A schema-valid map with one node and the roles a test needs."""
    return {"schema_version": 1, "project": project,
            "nodes": [{"id": "n", "label": "n", "kind": "artifact"}],
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


_RENDER_PROBE = """
import json, sys
from conductor import report
with open(sys.argv[1], encoding="utf-8") as handle:
    state = json.load(handle)
with open(sys.argv[2], "wb") as out:
    out.write(report.render(state).encode("utf-8"))
"""

#: Three environments that break a renderer reading anything but its argument:
#: a different hash seed reorders set iteration, a different zone moves any
#: call to the clock, a different locale reformats numbers and dates.
_HOSTILE_ENVIRONMENTS = (
    {"PYTHONHASHSEED": "0", "TZ": "UTC", "LC_ALL": "C"},
    {"PYTHONHASHSEED": "271828", "TZ": "Asia/Tokyo", "LC_ALL": "de_DE.UTF-8"},
    {"PYTHONHASHSEED": "999983", "TZ": "America/Sao_Paulo", "LC_ALL": "tr_TR.UTF-8"},
)


def test_the_render_ignores_the_hash_seed_the_time_zone_and_the_locale(tmp_path):
    # Several roles share every listed property but their id, and several
    # findings share a review state: any line built by walking a set instead of
    # the document reorders under a different hash seed, and the three renders
    # stop matching.
    state = merged(
        a_map([role("impl"), role("rev", ["impl"], stage="implement"), role("qa"),
               role("sec"), role("docs"), role("ops")]),
        [a_lane("claude", "impl",
                [a_finding(), a_finding("D-2"), a_finding("D-3"), a_finding("D-4")],
                waits=[{"id": "w-1", "kind": "decision", "title": "t",
                        "why": "w", "blocks": ["D-1"]}]),
         a_lane("codex", "rev",
                verdicts={"D-1": {"disposition": "confirmed", "note": "n"}})])
    document = tmp_path / "state.json"
    document.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    script = tmp_path / "probe.py"
    script.write_text(_RENDER_PROBE, encoding="utf-8")
    renders = []
    for index, environment in enumerate(_HOSTILE_ENVIRONMENTS):
        out = tmp_path / f"render-{index}.md"
        done = subprocess.run(
            [sys.executable, str(script), str(document), str(out)],
            stdin=subprocess.DEVNULL, capture_output=True, timeout=120,
            env={**os.environ, **environment, "PYTHONPATH": str(SRC_ROOT)})
        assert out.is_file(), done.stderr.decode("utf-8", "replace")
        renders.append(out.read_bytes())
    assert renders[0] and len(set(renders)) == 1


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


def test_agreed_with_nobody_assigned_to_review_it_is_not_rendered_as_checked():
    assigned, nobody = _agreed_pair()
    assert report.verify(only("D-1", assigned), assigned).verified is True
    assert report.verify(only("D-1", nobody), nobody).verified is False
    reviewed_text = section(report.render(assigned), "## Findings")
    vacuous_text = section(report.render(nobody), "## Findings")
    assert reviewed_text != vacuous_text, (
        "the report renders a checked finding and a vacuously agreed one alike")
    assert "no reviewer assigned" in vacuous_text   # §6's own wording for this row
    assert "no reviewer assigned" not in reviewed_text


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


# --- the known data defect the report must survive --------------------------


NON_STRING_WAIT = {"id": "w-1", "kind": "decision", "title": {"raw": 1},
                   "why": 7, "blocks": []}


def test_the_schema_still_lets_a_non_string_wait_title_through(tmp_path):
    # The precondition, pinned where the report's behaviour depends on it:
    # `schema._validate_lane_waits` checks a wait's id, kind and blocks and
    # never its title. Backlog item, another slice's to fix.
    data = a_lane("claude", waits=[NON_STRING_WAIT])["data"]
    assert schema.validate_lane(data, filename_stem="claude")[0] == []


def test_a_non_string_wait_title_is_never_rendered_as_the_authors_words(tmp_path):
    state = merged(a_map(), [a_lane("claude", waits=[NON_STRING_WAIT])])
    queue = section(report.render(state), "## Human queue")
    assert "### `w-1`" in queue                  # headed by the id the schema checks
    assert "{'raw': 1}" not in queue             # never a Python repr
    assert '{"raw": 1}' in line_starting(queue, "- Title:")   # shown as data, as JSON
    assert "non-string value" in line_starting(queue, "- Why:")


def test_the_report_command_survives_a_non_string_wait_title(tmp_path, capsys):
    body = json.dumps({"schema_version": 1, "author": "claude",
                       "updated": "2026-07-30T11:00:00+00:00",
                       "waits_on_human": [NON_STRING_WAIT]})
    root = write_project(tmp_path, lanes={"claude": body})
    assert main(["report", "--dir", str(root)]) == 0
    assert "### `w-1`" in capsys.readouterr().out


# --- no network -------------------------------------------------------------


#: Import roots that mean a module can reach off the machine, plus the two
#: process-spawning roots that could reach one indirectly.
NETWORKING_ROOTS = {"socket", "ssl", "http", "urllib", "urllib3", "asyncio",
                    "selectors", "select", "ftplib", "smtplib", "poplib",
                    "imaplib", "telnetlib", "xmlrpc", "requests", "httpx",
                    "aiohttp", "webbrowser", "subprocess", "multiprocessing"}

#: `sys.argv[2]` decides whether the child imports the module under measurement,
#: so the same script produces both the measurement and its baseline. The whole
#: of `sys.modules` is reported, not the growth: a networking module already
#: loaded when the probe started would vanish from a difference.
_MODULES_PROBE = """
import json, sys
if sys.argv[2] == "import":
    import conductor.report
with open(sys.argv[1], "w", encoding="utf-8") as out:
    json.dump({"loaded": sorted(sys.modules),
               "has_report": "conductor.report" in sys.modules}, out)
"""


def _root_of(dotted):
    return dotted.split(".", 1)[0]


def _modules_loaded(work, mode):
    """Every module name a child interpreter holds, with or without the import."""
    script, out = Path(work) / "probe.py", Path(work) / f"loaded-{mode}.json"
    script.write_text(_MODULES_PROBE, encoding="utf-8")
    done = subprocess.run(
        [sys.executable, str(script), str(out), mode], cwd=work,
        stdin=subprocess.DEVNULL, capture_output=True, timeout=120,
        env={**os.environ, "PYTHONPATH": str(SRC_ROOT)})
    assert out.is_file(), done.stderr.decode("utf-8", "replace")
    return json.loads(out.read_text(encoding="utf-8"))


def test_importing_the_report_loads_no_module_that_can_reach_the_network():
    with tempfile.TemporaryDirectory() as work:
        measured = _modules_loaded(work, "import")
        baseline = _modules_loaded(work, "skip")
    assert measured["has_report"], "the child never imported the module measured"
    assert not baseline["has_report"], "the baseline is not a baseline"
    # Asserted on the whole module table, then attributed: the first assertion
    # is the claim, the difference only says who to blame if it fails.
    reached = {n for n in measured["loaded"] if _root_of(n) in NETWORKING_ROOTS}
    assert reached == set(), (
        f"a child holding conductor.report also holds {sorted(reached)}; "
        f"of those, {sorted(reached - set(baseline['loaded']))} arrived with it")


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
    # The import-closure measurement above cannot see a deferred import inside
    # a function; this reads the source, where such an import would still be.
    imported = _imported_modules(REPORT_SOURCE)
    assert {name for name in imported if _root_of(name) in NETWORKING_ROOTS} == set()


# --- the report and the panel cannot describe different states --------------


def test_the_report_and_the_panel_are_handed_the_same_document(tmp_path):
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
