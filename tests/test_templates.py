import re
import tomllib
from datetime import datetime, timezone
from pathlib import Path

import pytest

from conductor import merge, prompts, schema, templates

ALL_TEMPLATES = ["default-orbit", "single-harness", "empty", "minimal"]

# `minimal` is the spec's own §2 example, vended verbatim from
# prompts.MAP_EXAMPLE so the spec and the scaffold cannot drift. Conventions we
# impose on the templates we author — PLACEHOLDER labels above all — stop at
# it deliberately: correcting the quotation to satisfy our own house style
# would defeat the point of quoting it.
AUTHORED_TEMPLATES = ["default-orbit", "single-harness", "empty"]

ORBIT_PHASES = ["goal", "detect", "diagnose", "design", "deliver"]
NOW = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)

PROTOCOL = Path(__file__).resolve().parents[1] / "spec" / "PROTOCOL.md"

#: A fenced TOML block's body, newline-terminated like the file it is written
#: to — which is why the extraction returns something a template can be
#: compared against with `==` and no fixing up.
_FENCE_RE = re.compile(r"^```toml\n(.*?)^```", re.M | re.S)


def _spec_section_2():
    """The text of PROTOCOL.md §2, from its heading to the next one."""
    text = PROTOCOL.read_text(encoding="utf-8")
    start = text.index("## 2. `map.toml`")
    return text[start:text.index("\n## ", start + 1)]


def _spec_section_2_map():
    """The one `map.toml` the spec shows in §2, as the file text it stands for."""
    return _FENCE_RE.search(_spec_section_2()).group(1)


def _lane(author, role, findings=(), verdicts=None):
    return {"author": author, "error": None,
            "data": {"schema_version": 1, "author": author, "role": role,
                     "updated": "2026-08-03T11:00:00+00:00",
                     "findings": list(findings), "verdicts": verdicts or {}}}


def _finding(fid="D-1"):
    return {"id": fid, "title": "t", "severity": "major", "claim": "defect",
            "detail": "d", "evidence": "e", "refs": ["placeholder-service"]}


def _parsed(name):
    return tomllib.loads(templates.get(name))


def _roles(data):
    return {r["id"]: r for r in data["cycle"]["roles"]}


def _paragraphs_of(text):
    """One rendered template's comments as unwrapped paragraphs.

    The prose IS the deliverable here, so tests must survive a rewrap. A
    paragraph ends at a blank comment line, a `# ---` rule, or any TOML line.
    """
    paragraphs, current = [], []
    for line in text.splitlines():
        body = line[1:].strip() if line.startswith("#") else ""
        if body and set(body) != {"-"}:
            current.append(body)
        elif current:
            paragraphs.append(" ".join(current))
            current = []
    if current:
        paragraphs.append(" ".join(current))
    return paragraphs


def _paragraphs(name):
    """The named template's comments, at its default values."""
    return _paragraphs_of(templates.get(name))


def _prose(name):
    """All of a template's comment text as one unwrapped string."""
    return " ".join(_paragraphs(name))


def _paragraphs_about(name, needle):
    return [p for p in _paragraphs(name) if needle in p]


@pytest.mark.parametrize("name", ALL_TEMPLATES)
def test_every_template_parses_as_toml(name):
    assert isinstance(_parsed(name), dict)


@pytest.mark.parametrize("name", ALL_TEMPLATES)
def test_every_template_validates_clean(name):
    # The acceptance bar: a vended template ships to every new project, so
    # "mostly valid" is a defect. Zero errors AND zero warnings.
    errors, warnings = schema.validate_map(_parsed(name))
    assert errors == [] and warnings == []


@pytest.mark.parametrize("name", ALL_TEMPLATES)
def test_every_template_declares_at_least_one_node(name):
    # Also closes the vacuous-all() hole in the placeholder-label test below.
    assert _parsed(name)["nodes"]


@pytest.mark.parametrize("name", AUTHORED_TEMPLATES)
def test_every_authored_template_node_label_announces_itself_as_a_placeholder(name):
    # The id prefix alone is not the guarantee: the label is what the panel
    # renders, so a plausible-looking label would let an unedited template pass
    # for a real map. `minimal` is exempt and stays exempt — it is the spec's
    # example quoted verbatim, and it is reachable only by asking for it by
    # name, never from `conduct init` with no arguments.
    assert all(n["label"].startswith("PLACEHOLDER") for n in _parsed(name)["nodes"])


@pytest.mark.parametrize("name", ALL_TEMPLATES)
def test_every_template_ends_in_exactly_one_newline(name):
    # A caller writes this text straight to map.toml. Anything that adds its
    # own trailing newline would leave a blank line in every user's map, and
    # anything that strips one would leave the file without a final newline.
    text = templates.get(name)
    assert text.endswith("\n") and not text.endswith("\n\n")


def test_names_lists_every_template_with_a_description_recommended_first():
    listed = templates.names()
    assert [name for name, _ in listed] == ALL_TEMPLATES
    assert listed[0][0] == templates.DEFAULT                 # vending order
    for _, description in listed:
        assert description and "\n" not in description       # one line each


def test_minimal_is_the_spec_example_verbatim_plus_its_missing_newline():
    # One sync point, quoted not copied: the spec's §2 example, the bootstrap
    # prompt and this template must never be able to say different things.
    assert templates.get("minimal") == prompts.MAP_EXAMPLE + "\n"


def test_the_minimal_template_is_the_protocol_spec_section_2_block_byte_for_byte():
    # The test above compares two expressions of ONE constant, so it stays green
    # while the constant drifts away from the document it claims to quote — and
    # it did drift: `minimal` shipped without the two `stage =` lines and the
    # phases comment §2 spends a paragraph explaining. The document is the other
    # party to the claim, so read it: the fenced block is parsed out of
    # spec/PROTOCOL.md here, not written down in this file, and a rewrite of
    # either side moves this expectation with it.
    block = _spec_section_2_map()
    assert templates.get("minimal") == block


def test_the_protocol_spec_section_2_holds_exactly_one_map_to_compare_against():
    # Guards the guard: an extraction that found nothing, or found the wrong
    # fence, would compare `minimal` against a stray block and pass on a
    # coincidence. The section must offer exactly one candidate.
    section = _spec_section_2()
    assert len(_FENCE_RE.findall(section)) == 1
    assert 'schema_version = 1' in _spec_section_2_map()


def test_default_names_the_recommended_template():
    # DO-3 groundwork: callers ask for DEFAULT rather than hardcoding a name
    # or trusting names() ordering.
    assert templates.DEFAULT == "default-orbit"
    assert templates.get(templates.DEFAULT)


def test_unknown_template_name_raises_and_names_the_known_ones():
    with pytest.raises(templates.UnknownTemplate) as exc:
        templates.get("orbital-decay")
    msg = str(exc.value)
    assert "orbital-decay" in msg
    for name in ALL_TEMPLATES:
        assert name in msg


# --- default-orbit: the recommended process, pinned ---


def test_default_orbit_declares_the_five_stages_in_order():
    assert _parsed("default-orbit")["cycle"]["phases"] == ORBIT_PHASES


def test_default_orbit_role_shape():
    roles = _roles(_parsed("default-orbit"))
    assert list(roles) == ["scout", "diagnostician", "architect", "implementer", "reviewer"]
    assert {rid: r["stage"] for rid, r in roles.items()} == {
        "scout": "detect", "diagnostician": "diagnose", "architect": "design",
        "implementer": "deliver", "reviewer": "deliver"}
    assert {rid: r["reviews"] for rid, r in roles.items()} == {
        "scout": [], "diagnostician": ["scout"], "architect": [],
        "implementer": [], "reviewer": ["implementer"]}


def test_default_orbit_stages_nobody_to_goal():
    # Goal is human-owned. A stage with no participant is intentional here.
    roles = _parsed("default-orbit")["cycle"]["roles"]
    assert "goal" not in {r["stage"] for r in roles}


def test_every_default_orbit_stage_has_a_prompt_contract():
    # The coupling the two halves of DO-2 were missing: renaming a phase in the
    # template (roles updated, map still valid, every other test green) would
    # otherwise silently turn the stage contracts off for the shipped default.
    for role in _parsed("default-orbit")["cycle"]["roles"]:
        assert prompts._stage_block(role["stage"]) != ""


def test_default_orbit_reviewer_reviews_implementer_on_another_harness():
    roles = _roles(_parsed("default-orbit"))
    assert roles["reviewer"]["reviews"] == ["implementer"]
    assert roles["reviewer"]["harness"] != roles["implementer"]["harness"]


def test_default_orbit_says_goal_is_human_owned_and_decisions_live_in_lanes():
    prose = _prose("default-orbit")
    assert "human-owned" in prose
    assert "waits_on_human" in prose


def test_default_orbit_does_not_claim_review_independence():
    # v1 expresses a review OBLIGATION; self-verdict exclusion gives only
    # minimal authorship separation. Scoped to the paragraph that makes the
    # claim, so the ban cannot forbid a legitimate use elsewhere.
    para = _paragraphs_about("default-orbit", "authorship separation")
    assert len(para) == 1
    assert "review obligation" in para[0]
    assert "It does not establish that a review is independent" in para[0]
    for oversell in ("proves", "guarantees", "ensures"):
        assert oversell not in para[0].lower()


def test_default_orbit_explains_the_shared_harness_product():
    harnesses = [r["harness"] for r in _parsed("default-orbit")["cycle"]["roles"]]
    assert harnesses.count("claude-code") == 3            # separate participants
    assert "not separate installations" in _prose("default-orbit")


def test_default_orbit_documents_the_fields_a_newcomer_must_edit():
    # The epistemic caveats were exhaustive while the editing semantics were
    # absent. Every field the template actually uses must be explained.
    prose = _prose("default-orbit")
    for field in ("id", "label", "kind", "depends_on", "harness", "stage", "reviews"):
        assert field in prose
    assert "free-form" in prose                           # kind
    assert "one [[nodes]] block per component" in prose
    assert "refs" in prose


def test_default_orbit_warns_that_invariants_are_not_enforced():
    para = _paragraphs_about("default-orbit", "INVARIANTS")
    assert len(para) == 1
    assert "does not enforce" in para[0]
    assert "no lane has reported a breach" in para[0]


def test_default_orbit_scopes_the_unread_claim_to_stage_not_phases():
    # D-1: `cycle.phases` IS read by the merger (now.phase membership,
    # current_phase). Only `stage` is unread by every merge rule.
    prose = _prose("default-orbit")
    assert "nothing is gated on reaching one" in prose
    assert "now.phase must name one of these" in prose
    # Found by the claim, not by the field table's column padding: a pure
    # reformat of that table must not read as a missing caveat.
    stage_para = _paragraphs_about("default-orbit", "no merge rule reads it")
    assert len(stage_para) == 1
    assert "stage" in stage_para[0]


def test_default_orbit_renaming_a_phase_alone_really_does_break_the_map():
    # The template warns that a phase rename must reach every role staged to
    # it. Prove the warning describes real behavior, not caution.
    data = _parsed("default-orbit")
    data["cycle"]["phases"] = ["goal", "recon", "diagnose", "design", "deliver"]
    errors, _ = schema.validate_map(data)
    assert any("stage 'detect'" in e for e in errors)


def test_default_orbit_editing_material_comes_before_the_epistemics():
    # I6: a reader who came to edit must reach the first editable role before
    # the material about what the protocol cannot promise.
    text = templates.get("default-orbit")
    assert text.index("[[cycle.roles]]") < text.index("DELIBERATELY DOES NOT CONTAIN")
    assert text.index("ARCHITECTURE") < text.index("PARTICIPANTS")


def test_default_orbit_nodes_are_obviously_placeholders():
    assert all("placeholder" in n["id"] for n in _parsed("default-orbit")["nodes"])
    assert "replace" in _prose("default-orbit").lower()


# --- single-harness and empty ---


def test_single_harness_has_one_role_and_no_reviewer():
    roles = _parsed("single-harness")["cycle"]["roles"]
    assert len(roles) == 1
    assert roles[0]["reviews"] == []
    assert "waits_on_human" in _prose("single-harness")


def test_single_harness_names_the_vacuous_agreed_state():
    # D-2: against a protocol whose headline is "silence is never consent",
    # the reassuring word is the one that must be said out loud.
    prose = _prose("single-harness")
    assert "`agreed`" in prose
    assert "vacuous truth, not consent" in prose
    assert "no reviewer assigned" in prose
    assert 'reviews = ["implementer"]' in prose


def test_single_harness_solo_finding_really_computes_as_agreed():
    # The disclosure above is only worth pinning if it is true end to end.
    state = merge.merge(_parsed("single-harness"), None,
                        [_lane("a", "implementer", [_finding()])], [], 0, NOW)
    assert state["findings"][0]["review_state"] == "agreed"


@pytest.mark.parametrize("name", ["default-orbit", "single-harness"])
def test_decision_ladder_is_stated_without_the_word_gate(name):
    # O-1/O-2: a reader who takes away the word "gate" goes looking for an
    # entity v1 does not have; and clearing the queue is not the same act as
    # recording the decision. Scoped to the waits_on_human paragraphs —
    # "nothing is gated on reaching one" is a true statement about phases.
    about = _paragraphs_about(name, "waits_on_human")
    assert about
    for para in about:
        # The noun, on a word boundary. Banning the substring would also ban
        # delegate, mitigate and aggregate — and "gated" is a fair verb.
        assert re.search(r"\bgates?\b", para, re.IGNORECASE) is None
    prose = _prose(name)
    assert "does not by itself record the decision" in prose
    assert 'append an `events.jsonl` event with `kind = "ok"`' in prose
    assert "Absence of a wait is not approval" in prose


def test_the_receipt_ladder_is_one_shared_claim_not_two_copies():
    # M7: a protocol version that ships receipts must be able to correct this
    # in one edit, so both templates render the identical paragraphs.
    orbit = _paragraphs_about("default-orbit", "structurally confirmed")
    solo = _paragraphs_about("single-harness", "structurally confirmed")
    assert len(orbit) == 1 and orbit == solo


def test_empty_declares_no_cycle_roles():
    assert _parsed("empty").get("cycle", {}).get("roles", []) == []


# --- O-3: a stage with no role staged to it is a first-class shape ---


def test_unassigned_goal_stage_needs_no_lane_and_warns_about_nothing():
    # Merged with no lanes at all: an unstaffed phase is not an error, not a
    # warning, and not a reason to withhold a normal "ready" status.
    data = _parsed("default-orbit")
    assert "goal" in data["cycle"]["phases"]
    state = merge.merge(data, None, [], [], 0, NOW)
    assert state["warnings"] == []
    assert state["project_status"]["state"] == "ready"


def test_unassigned_goal_stage_does_not_touch_review_state():
    # Review state follows the staffed roles only: scout's finding is owed a
    # verdict by diagnostician, and the empty goal stage has no say either way.
    data = _parsed("default-orbit")
    lanes = [_lane("a", "scout", [_finding()]), _lane("b", "diagnostician")]
    unreviewed = merge.merge(data, None, lanes, [], 0, NOW)
    assert unreviewed["findings"][0]["review_state"] == "unreviewed"
    lanes[1] = _lane("b", "diagnostician",
                     verdicts={"D-1": {"disposition": "confirmed", "note": "reproduced"}})
    agreed = merge.merge(data, None, lanes, [], 0, NOW)
    assert agreed["findings"][0]["review_state"] == "agreed"
    assert agreed["warnings"] == []


# --- DO-3: parameterisation, the values `conduct init` fills in ---

# Legal but awkward: one character, hyphens, digits, mixed case, dots,
# underscores, the real product names harnesses actually ship under (spaces
# and parentheses included), a non-ASCII name, and the longest the rule allows.
AWKWARD_NAMES = ["a", "A9", "my-app", "Web_App-2", "x.y.z", "Claude Code",
                 "Kimi Code", "Qwen Code (beta)", "C++ service", "Проект",
                 "a" * 64]

# Everything below either breaks the generated TOML outright or silently
# changes what it means. None of it may reach the file.
TOML_BREAKING = ['a"b', "a\\b", "a\nb", "a\rb", "a\tb", "a\x00b", "", " ",
                 "-leading", ".leading", "a" * 65, '"', "x] [y", "a#b", "a'b",
                 "a\x1bb", "a=b", "a,b", "a{b"]


@pytest.mark.parametrize("name", ALL_TEMPLATES)
def test_explicit_none_arguments_reproduce_the_template_verbatim(name):
    # The defaults are the contract every pre-DO-3 template test relies on.
    assert templates.get(name, project=None, primary=None,
                         reviewer=None) == templates.get(name)


@pytest.mark.parametrize("value", AWKWARD_NAMES)
@pytest.mark.parametrize("name", ALL_TEMPLATES)
def test_every_accepted_name_still_generates_a_clean_map(name, value):
    # generation -> tomllib -> validate_map must stay ([], []) for every input
    # the rule accepts: a name that passes validation and then breaks the file
    # would be the worst of both.
    text = templates.get(name, project=value, primary=value, reviewer="rev-2")
    errors, warnings = schema.validate_map(tomllib.loads(text))
    assert errors == [] and warnings == []
    assert text.endswith("\n") and not text.endswith("\n\n")


@pytest.mark.parametrize("bad", TOML_BREAKING)
@pytest.mark.parametrize("field", ["project", "primary", "reviewer"])
def test_toml_breaking_names_are_rejected_before_they_reach_the_file(bad, field):
    with pytest.raises(templates.InvalidName) as exc:
        templates.get("default-orbit", **{field: bad})
    msg = str(exc.value)
    assert repr(bad) in msg                     # says which value
    assert templates.NAME_RULE in msg           # and what is allowed instead
    assert ("project name" if field == "project" else "harness id") in msg


@pytest.mark.parametrize("bad, offender", [('my "app"', '"'), ("a\\b", "\\"),
                                           ("a\nb", "\n"), ("a=b", "="),
                                           ("a\x00b", "\x00")])
def test_the_rejection_names_the_character_that_failed(bad, offender):
    # "invalid input" is not actionable. The message must say which field,
    # which character, and what the allowed format is.
    with pytest.raises(templates.InvalidName) as exc:
        templates.get("default-orbit", project=bad)
    msg = str(exc.value)
    assert "project name" in msg
    assert repr(offender) in msg
    assert templates.NAME_RULE in msg


def test_parameterisation_carries_the_names_into_the_map():
    data = tomllib.loads(templates.get("default-orbit", project="my-app",
                                       primary="kimi", reviewer="qwen"))
    assert data["project"] == "my-app"
    roles = _roles(data)
    assert roles["implementer"]["harness"] == "kimi"
    assert roles["reviewer"]["harness"] == "qwen"
    assert {r["harness"] for r in data["cycle"]["roles"]} == {"kimi", "qwen"}


def test_swapping_the_two_default_harnesses_does_not_collapse_them():
    # A naive sequential replace would rewrite claude-code -> codex and then
    # every codex -> claude-code, leaving one harness everywhere.
    roles = _roles(tomllib.loads(templates.get("default-orbit", primary="codex",
                                               reviewer="claude-code")))
    assert roles["implementer"]["harness"] == "codex"
    assert roles["reviewer"]["harness"] == "claude-code"


def test_single_harness_takes_the_primary_and_has_no_use_for_a_reviewer():
    text = templates.get("single-harness", primary="kimi", reviewer="qwen")
    assert _roles(tomllib.loads(text))["implementer"]["harness"] == "kimi"
    assert "qwen" not in text


def test_project_name_reaches_every_template():
    for name in ALL_TEMPLATES:
        assert tomllib.loads(templates.get(name, project="my-app"))["project"] == "my-app"


def test_a_renamed_harness_is_renamed_in_the_prose_that_counts_it():
    # The template states a fact about its own values. Substituting the values
    # and leaving the sentence would ship a file that contradicts itself.
    assert '"claude-code" appears three times' in templates.get("default-orbit")
    text = templates.get("default-orbit", primary="kimi", reviewer="qwen")
    assert "claude-code" not in text
    assert '"kimi" appears three times' in text


def test_minimal_is_parameterised_too_inline_comments_and_all():
    # get("minimal", ...) is public and was covered only for validity, never
    # for the values landing — and it is the one template whose assignments
    # carry trailing comments, so it is exactly where a swap would miss.
    text = templates.get("minimal", project="my-app", primary="kimi", reviewer="qwen")
    data = tomllib.loads(text)
    assert data["project"] == "my-app"
    assert _roles(data)["implementer"]["harness"] == "kimi"
    assert _roles(data)["reviewer"]["harness"] == "qwen"
    assert "# informational" in text          # the inline comment survives
    assert "claude-code" not in text and "codex" not in text


@pytest.mark.parametrize("name", ALL_TEMPLATES)
def test_a_reformatted_assignment_raises_instead_of_shipping_a_wrong_map(
        name, monkeypatch):
    # Exact-text matching is what preserves inline comments; the price is that
    # one extra space would make the swap a silent no-op, handing the user a
    # committed map naming a harness they never chose. It must fail loudly.
    original = templates.get(name)
    marker = 'project = "web-app"' if name == "minimal" else 'project = "your-project"'
    broken = original.replace(marker, marker.replace(" = ", "  = "), 1)
    monkeypatch.setitem(templates._TEMPLATES, name, (broken, "d"))
    for call in (lambda: templates.get(name), lambda: templates.get(name, project="p")):
        with pytest.raises(templates.TemplateOutOfSync) as exc:
            call()                            # unparameterised too: caught early
        msg = str(exc.value)
        assert name in msg and marker.replace(" = ", "  = ") in msg
        assert "_SWAPPABLE" in msg            # says how to fix it


def test_the_counted_sentence_is_counted_not_asserted():
    # The number is derived from the role blocks that actually carry the
    # harness, so the sentence cannot outlive an edit to the template.
    assert '"claude-code" appears three times' in templates.get("default-orbit")
    both = templates.get("default-orbit", primary="kimi", reviewer="kimi")
    assert '"kimi" appears five times' in both


# Every way the paragraph could name a number. The derived count owns the only
# one it is allowed to carry.
NUMBER_WORDS = ("once", "twice", "one", "two", "three", "four", "five", "six")


@pytest.mark.parametrize("reviewer, counted", [("qwen", "three times"),
                                               ("kimi", "five times")])
def test_the_counted_paragraph_carries_exactly_one_number(reviewer, counted):
    # Deriving the first sentence while the rest went on asserting the old
    # number left the paragraph reading "five times ... three ... three ...
    # three" — wrong before, and visibly self-contradicting after. The
    # continuation now carries no number at all, so it is true at any count.
    text = templates.get("default-orbit", primary="kimi", reviewer=reviewer)
    para = [p for p in _paragraphs_of(text) if '"kimi" appears' in p]
    assert len(para) == 1
    assert counted in para[0]
    for word in NUMBER_WORDS:
        if word not in counted:
            assert re.search(rf"\b{word}\b", para[0]) is None, word


def test_the_count_is_not_frozen_at_three_or_five(monkeypatch):
    # Move one implementing role onto the reviewing harness: the primary now
    # appears twice, and a re-frozen literal would say otherwise.
    moved = templates.get("default-orbit").replace(
        'harness = "claude-code"', 'harness = "codex"', 1)
    monkeypatch.setitem(templates._TEMPLATES, "default-orbit", (moved, "d"))
    text = templates.get("default-orbit", primary="kimi", reviewer="qwen")
    assert '"kimi" appears twice below' in text
    para = [p for p in _paragraphs_of(text) if '"kimi" appears' in p][0]
    for word in ("three", "five", "once"):
        assert re.search(rf"\b{word}\b", para) is None


def test_one_harness_for_both_roles_withdraws_the_different_product_claim():
    # The default's reviewer runs a different product; a user who picks the
    # same one for both must not be told otherwise by their own map.
    text = templates.get("default-orbit", primary="kimi", reviewer="kimi")
    assert "different harness product" not in text
    assert "same harness product" in text
    assert '"kimi" appears five times' in text     # three primary + two reviewing
    errors, warnings = schema.validate_map(tomllib.loads(text))
    assert errors == [] and warnings == []
