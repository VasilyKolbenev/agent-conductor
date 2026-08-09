"""Smoke tests for the packaged panel (Task 14) — served HTML references the protocol.

Smoke is the whole claim, and the module is named for it. What runs is the real
server and the real handler, so the panel is genuinely *served*; what is then
checked is the **text of the response** and the **source of the script**. No
browser parses it, no DOM is built, nothing is rendered. These guards therefore
catch a surface being deleted, an id being dropped, a contract token being
renamed — and they do not establish that any of it works in a browser. A
behaviour claim about the rendered panel is post-alpha work, carried in §10 of
the plan.
"""
import re
import urllib.request
from datetime import datetime, timezone

from conductor import merge
from tests.test_merge_review import MAP, lane
from tests.test_panel_cascade import (
    PANEL, free_names, function_body, panel_html, script)
from tests.test_server import start
from tests.test_store import write_project, good_lane

NOW = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)


def _fetch_panel(root):
    srv, base = start(root)
    try:
        with urllib.request.urlopen(base + "/", timeout=5) as r:
            return r.read().decode()
    finally:
        srv.shutdown()
        # Not in the mandated snippet: prevents socket leaks across the suite —
        # same documented teardown-hygiene deviation Task 13 made.
        srv.server_close()


def test_panel_serves_and_references_state(tmp_path):
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    html = _fetch_panel(root)
    for token in ("state.json", "EventSource", "id=\"map\"", "id=\"queue\"",
                  "id=\"findings\"", "id=\"warnings\"", "prefers-color-scheme"):
        assert token in html


def test_panel_has_all_tooling_ids(tmp_path):
    # The full id contract promised to future tooling (plan Task 14, delta 5).
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    html = _fetch_panel(root)
    for element_id in ("map", "cycle", "kpis", "queue", "findings", "feed", "warnings"):
        assert f'id="{element_id}"' in html


def test_panel_pins_review_vocabulary_tokens(tmp_path):
    # Pin the mandated vocabulary so dropping a chip state or the uncovered
    # hint cannot slip through green (quality-review follow-up).
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    html = _fetch_panel(root)
    for token in ("suspended", "disagreement", "uncovered", "no reviewer assigned",
                  "contested_by", "December — "):
        assert token in html


def test_panel_findings_scannable_title_and_card_fields(tmp_path):
    # C6.2: title is the scannable table column; claim moves into the expanded
    # card alongside the new detail and evidence fields, each with a label.
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    html = _fetch_panel(root)
    assert '<th>title</th>' in html
    assert '<th>claim</th>' not in html
    for label in ('"Claim"', '"Detail"', '"Evidence"'):
        assert label in html


def test_panel_a11y_and_live_title_markers(tmp_path):
    # Reduced-motion support and the live document title are part of the delta list.
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    html = _fetch_panel(root)
    assert "prefers-reduced-motion" in html
    assert "waiting on you" in html


def test_panel_attention_zone_and_agents_block(tmp_path):
    # C6.3: the action loop — attention zone, agents block, copy decision brief.
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    html = _fetch_panel(root)
    for token in ('id="attention"', 'id="agents"', "Reply to:", "Copy decision brief",
                  "Nothing needs you right now.", "No lanes yet."):
        assert token in html


def test_panel_pins_decision_brief_contract_tokens(tmp_path):
    # Pin test: the copy-brief instruction tail is a protocol contract with
    # agents (remove wait -> events.jsonl ok line -> conduct validate).
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    html = _fetch_panel(root)
    for token in ("Decision needed: ", "events.jsonl", "conduct validate."):
        assert token in html


def test_panel_never_says_anything_was_approved(tmp_path):
    # Guard carried from the owner's "silence is never consent" requirement.
    # Protocol v1 has no decision receipt: nothing the panel can read tells it
    # a human approved anything, so the panel must never say one did. Banned
    # is the past participle — the CLAIM of a recorded state; it subsumes the
    # named phrasings "Human approved" and "Everything approved". "approval"
    # and "approve" stay available for asking, which is all v1 can express.
    #
    # Narrower than the name suggests: this renders one fixture, so it catches
    # static wording and whatever this state reaches, not every branch.
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    assert "approved" not in _fetch_panel(root).lower()


def test_panel_titles_the_document_december_and_counts_the_queue(tmp_path):
    html = _fetch_panel(write_project(tmp_path, lanes={"claude": good_lane()}))
    assert "<title>December</title>" in html
    assert 'document.title = "December — " + (Number(k.queue) || 0) + " waiting on you"' in html


def _arguments_of(name: str, source: str) -> list[str]:
    """Return the argument text of every call to ``name`` in ``source``."""
    out = []
    for match in re.finditer(re.escape(name) + r"\(", source):
        depth, i = 1, match.end()
        while depth:
            depth += (source[i] == "(") - (source[i] == ")")
            i += 1
        out.append(source[match.end():i - 1])
    return out


def test_panel_shell_carries_the_mark_the_wordmark_and_an_honest_last_update(tmp_path):
    html = _fetch_panel(write_project(tmp_path, lanes={"claude": good_lane()}))
    assert 'aria-label="December"' in html          # the mark, inline SVG
    assert 'class="mark__dot"' in html              # the one red dot
    assert 'class="wordmark">December<' in html
    # "honest" is the load-bearing word in this test's name, and pinning the
    # whole expression against the raw file was still a substring assertion: it
    # survived `ago(new Date())` in the live line with the pinned expression
    # kept alive in a comment beside it. So the assertion is made against the
    # shell's *code* — function_body strips comments before counting braces —
    # and it holds a relation as well: the shell ages exactly one thing, and
    # the thing it ages is the state document's own timestamp.
    assert _arguments_of("ago", function_body("renderShell")) == \
        ["parseTs(s.generated_at)"]


def _shell_markup(served: str) -> str:
    header = re.search(r'<header class="shell".*?</header>', served, re.S)
    assert header, "the panel no longer serves a <header class=\"shell\">"
    return re.sub(r"<!--.*?-->", " ", header.group(0), flags=re.S)


def test_panel_shell_names_no_run_and_no_other_invented_identifier(tmp_path):
    # Plan §8.2: protocol v1 has no run identity, so the shell may not display
    # one, nor a session number, nor a build label, nor anything else it made
    # up. A list of banned phrasings cannot say that — "Session 4718 · build
    # 2026.08.05-a3f9 · run 41" walks straight through one. So the check is
    # positive instead: the shell's static markup is allowed to spell exactly
    # two things, and every other word in it has to come from state.json
    # through the two functions checked below.
    served = _fetch_panel(write_project(tmp_path, lanes={"claude": good_lane()}))
    text = re.sub(r"<[^>]+>", "\x00", _shell_markup(served))
    assert [run.strip() for run in text.split("\x00") if run.strip()] == \
        ["December", "connecting…"]


def test_rendershell_reads_only_the_state_fields_and_spells_only_the_words_named_here():
    # The other half of the shell's promise, on the writing side. renderShell
    # may read these fields of the state document and no others, and may spell
    # these words and no others; anything else in the shell would be the panel
    # asserting something the data cannot support.
    #
    # The name used to say "the shell prints only…", which is a claim about
    # output. Two sets are extracted from the *source* of one function and
    # compared. A field read through a computed key, or a word built by
    # concatenation, is outside both sets and outside this test.
    body = function_body("renderShell")
    assert set(re.findall(r"\bs\.([A-Za-z_$][\w$]*)", body)) == \
        {"project", "generated_at", "invariants"}
    assert set(re.findall(r'"([^"]*)"', body)) == \
        {"", " · ", "· ", "last update ", " · invariants: ", " ok", "projInfo"}


def test_setlive_spells_only_the_string_literals_named_here():
    # setLive owns the one remaining piece of shell text. Same treatment and the
    # same limit: the string literals in its source are named, so a third cannot
    # appear unnoticed — and a string assembled at runtime is not a literal and
    # is not seen here.
    body = function_body("setLive")
    assert set(re.findall(r'"([^"]*)"', body)) == \
        {"dot", "liveText", "dot", " dot--down", "live", "connection lost — retrying", ""}


def test_panel_introduces_no_new_innerhtml(tmp_path):
    # Lane authors are untrusted input. This used to allow one occurrence — the
    # comment stating the ban — and assert that the comment's words were
    # present, which a comment rewritten to mean the exact opposite satisfied
    # while keeping the words. No assertion about prose can be made by matching
    # prose, so the panel stopped naming the API at all and the ban is held by
    # absence: the name occurs nowhere, comment or code. The rewrite that used
    # to pass now fails, because writing it means writing the word.
    assert "innerHTML" not in panel_html()


def test_every_test_module_the_panel_points_a_reader_at_exists():
    # The panel's comments send a reader to five test modules by path. This
    # repository has already paid once for a reference that stopped resolving
    # (commit 97f8325), and this round moved guards into two more files.
    named = set(re.findall(r"tests/test_panel_\w+\.py", panel_html()))
    assert named, "the panel no longer points at the guards that hold its claims"
    for path in sorted(named):
        assert (PANEL.parents[3] / path).exists(), path


def test_the_served_panel_source_carries_the_interaction_ring_and_its_rule(tmp_path):
    # The file-size waiver's third condition: every surface keeps a smoke test
    # here. .halo is the surface this slice added, and the cascade guards in
    # tests/test_panel_style.py reason about an element they assume is emitted,
    # so the served source has to carry both the emitter and the rule.
    #
    # The name used to say "the panel draws"; two substrings of the served text
    # are what is checked. This is a smoke test — it catches the ring being
    # deleted outright, and nothing subtler.
    html = _fetch_panel(write_project(tmp_path, lanes={"claude": good_lane()}))
    assert 'class: "halo"' in html
    assert ".halo{" in html


def _attention_table():
    """Parse the panel's project_status.state -> light level mapping."""
    body = re.search(r"const ATTENTION = \{([^}]*)\}", panel_html()).group(1)
    return dict(re.findall(r'(\w+):\s*"(\w+)"', body))


def test_every_light_level_the_panel_declares_names_a_real_project_state():
    # A level keyed on a state the merger cannot produce would be a reading of
    # a signal that does not exist.
    assert set(_attention_table()) <= merge.PROJECT_STATES
    assert set(_attention_table()) == {"blocked", "active"}


def test_attentionOf_reads_only_its_argument_and_the_declared_table():
    # The owner's own formulation of the invariant: the same state document has
    # to give the same light level whatever the time is. That is a statement
    # about what attentionOf is allowed to depend on, so it is checked as one —
    # the only names the expression may reach for are its own argument and the
    # declared table. A clock, a random source, a frame counter or any other
    # ambient reading would appear here as a free name and fail, without this
    # test having to know what any of them are called.
    expression = re.search(r"const attentionOf = (.*?);\n", panel_html(), re.S).group(1)
    assert free_names(expression, {"s"}) == {"ATTENTION"}, expression


def test_the_only_documentElement_in_the_script_is_renderShells_attention_assignment():
    # Purity is only worth having if nothing bypasses it. One writer, one
    # source: the light level the document wears is the value attentionOf
    # computed from the state document handed to renderShell.
    #
    # Counting one spelling was not that. A second writer using setAttribute
    # instead of dataset — a clock-keyed one, in render(), a line below the
    # call to renderShell — left the count at one and the suite green. So what
    # is held is a relation between the count and the place: the script names
    # `documentElement` exactly once, that one naming is renderShell's
    # assignment, and no string literal in the script names the attribute.
    body = function_body("renderShell")
    assert script().count("documentElement") == 1
    assert "document.documentElement.dataset.attention = attentionOf(s);" in body
    assert body.count("attentionOf(") == 1
    assert not [text for text in re.findall(r'"([^"]*)"', script())
                if "data-attention" in text or "attention" == text]


def test_the_lit_cards_are_named_in_the_markup_and_no_literal_spells_the_class():
    # The other half of the owner's invariant. "The same state with a different
    # clock gives the same classes and the same styles" is about two things:
    # which level the document wears, and which elements wear the lit material.
    # The level was guarded three ways and the set was guarded by nothing, so
    # `$("agents").classList.toggle("lit", Date.now() % 2 === 0)` changed the
    # classes by the clock with every panel test green. The set is markup-
    # determined, so that is what is asserted — and separately, no string
    # literal in the script may spell the class.
    wearing = [ident for classes, ident in re.findall(r'class="([^"]*)" id="(\w+)"',
                                                      panel_html())
               if "lit" in classes.split()]
    assert wearing == ["queue", "alerts"], wearing
    written = [word for text in re.findall(r'"([^"]*)"', script()) for word in text.split()]
    assert "lit" not in written, written


def _level_for(state):
    return _attention_table().get(state["project_status"]["state"], "none")


def test_the_light_level_follows_the_project_status_the_merger_computes():
    # Three states built by the real merger, not by hand: a lane waiting on a
    # person, a lane simply working, and a project with no lanes at all. The
    # light level differs across them, which is what makes it a reading of the
    # data rather than decoration. _level_for re-implements the lookup in
    # Python, which is only honest because the two tests above pin the panel's
    # expression to exactly that lookup and to nothing else.
    waiting = merge.merge(MAP, None, [dict(lane("claude", "impl"), data={
        **lane("claude", "impl")["data"],
        "waits_on_human": [{"id": "w-1", "kind": "decision", "title": "Ship it?",
                            "why": "", "blocks": []}]})], [], 0, NOW)
    working = merge.merge(MAP, None, [lane("claude", "impl")], [], 0, NOW)
    empty = merge.merge(MAP, None, [], [], 0, NOW)

    assert (waiting["project_status"]["state"], _level_for(waiting)) == ("blocked", "high")
    assert (working["project_status"]["state"], _level_for(working)) == ("active", "low")
    assert (empty["project_status"]["state"], _level_for(empty)) == ("ready", "none")


def test_the_stylesheet_lights_only_the_low_and_high_levels():
    # Absence of attention is a real state and must look like one: no level, no
    # lift, no brighter contour. The CSS only lights `low` and `high`.
    html = panel_html()
    assert 'html[data-attention="low"] .lit' in html
    assert 'html[data-attention="high"] .lit' in html
    assert 'data-attention="none"' not in html


def test_panel_decision_first_section_order(tmp_path):
    # Attention (holding the queue) sits above agents, which sit above the map.
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    html = _fetch_panel(root)
    order = [html.index(f'id="{i}"')
             for i in ("attention", "queue", "agents", "map", "findings", "feed")]
    assert order == sorted(order)
