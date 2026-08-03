import tomllib
from datetime import datetime, timezone

import pytest

from conductor import merge, schema, templates

ORBIT_PHASES = ["goal", "detect", "diagnose", "design", "deliver"]
NOW = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)


def _lane(author, role, findings=(), verdicts=None):
    return {"author": author, "error": None,
            "data": {"schema_version": 1, "author": author, "role": role,
                     "updated": "2026-08-03T11:00:00+00:00",
                     "findings": list(findings), "verdicts": verdicts or {}}}


def _decision_blocks(name):
    """The contiguous comment blocks that explain `waits_on_human`."""
    blocks, current = [], []
    for line in templates.get(name).splitlines():
        if line.startswith("#"):
            current.append(line)
        elif current:
            blocks.append("\n".join(current))
            current = []
    if current:
        blocks.append("\n".join(current))
    return [b for b in blocks if "waits_on_human" in b]


def _finding(fid="D-1"):
    return {"id": fid, "title": "t", "severity": "major", "claim": "defect",
            "detail": "d", "evidence": "e", "refs": ["placeholder-service"]}


def _parsed(name):
    return tomllib.loads(templates.get(name))


def _roles(data):
    return {r["id"]: r for r in data["cycle"]["roles"]}


@pytest.mark.parametrize("name", ["default-orbit", "single-harness", "empty"])
def test_every_template_parses_as_toml(name):
    assert isinstance(_parsed(name), dict)


@pytest.mark.parametrize("name", ["default-orbit", "single-harness", "empty"])
def test_every_template_validates_clean(name):
    # The acceptance bar: a vended template ships to every new project, so
    # "mostly valid" is a defect. Zero errors AND zero warnings.
    errors, warnings = schema.validate_map(_parsed(name))
    assert errors == [] and warnings == []


@pytest.mark.parametrize("name", ["default-orbit", "single-harness", "empty"])
def test_every_template_declares_at_least_one_node(name):
    assert _parsed(name)["nodes"]


@pytest.mark.parametrize("name", ["default-orbit", "single-harness", "empty"])
def test_every_template_node_label_announces_itself_as_a_placeholder(name):
    # The id prefix alone is not the guarantee: the label is what the panel
    # renders, so a plausible-looking label would let an unedited template pass
    # for a real map. Pinned across all three.
    assert all(n["label"].startswith("PLACEHOLDER") for n in _parsed(name)["nodes"])


def test_names_lists_all_three_with_a_description():
    listed = templates.names()
    assert [name for name, _ in listed] == ["default-orbit", "single-harness", "empty"]
    for _, description in listed:
        assert description and "\n" not in description       # one line each


def test_unknown_template_name_raises_and_names_the_known_ones():
    with pytest.raises(templates.UnknownTemplate) as exc:
        templates.get("orbital-decay")
    msg = str(exc.value)
    assert "orbital-decay" in msg
    for name in ("default-orbit", "single-harness", "empty"):
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


def test_default_orbit_stages_all_name_declared_phases():
    data = _parsed("default-orbit")
    phases = data["cycle"]["phases"]
    for role in data["cycle"]["roles"]:
        assert role["stage"] in phases


def test_default_orbit_stages_nobody_to_goal():
    # Goal is human-owned. A stage with no participant is intentional here.
    roles = _parsed("default-orbit")["cycle"]["roles"]
    assert "goal" not in {r["stage"] for r in roles}


def test_default_orbit_reviewer_reviews_implementer_on_another_harness():
    roles = _roles(_parsed("default-orbit"))
    assert roles["reviewer"]["reviews"] == ["implementer"]
    assert roles["reviewer"]["harness"] != roles["implementer"]["harness"]


def test_default_orbit_says_goal_is_human_owned_and_gates_are_not_map_objects():
    text = templates.get("default-orbit")
    assert "human-owned" in text
    assert "waits_on_human" in text


def test_default_orbit_does_not_claim_review_independence():
    # v1 expresses a review OBLIGATION; self-verdict exclusion gives only
    # minimal authorship separation. The template must not oversell that.
    text = templates.get("default-orbit").lower()
    assert "obligation" in text
    assert "does not establish" in text
    for oversell in ("proves", "guarantees", "ensures"):
        assert oversell not in text


def test_default_orbit_explains_the_shared_harness_product():
    data = _parsed("default-orbit")
    harnesses = [r["harness"] for r in data["cycle"]["roles"]]
    assert harnesses.count("claude-code") == 3            # separate participants
    assert "not three installations" in templates.get("default-orbit")


def test_default_orbit_scopes_the_unread_claim_to_stage_not_phases():
    # Fix round 1, D-1: `cycle.phases` IS read by the merger (now.phase
    # membership, current_phase). Only `stage` is unread by every merge rule.
    text = templates.get("default-orbit")
    assert "It is `stage` below that no merge rule reads." in text
    assert "now.phase must name one of these" in text
    assert "nothing is gated on reaching one" in text


def test_default_orbit_renaming_a_phase_alone_really_does_break_the_map():
    # The template warns that a phase rename must reach every role staged to
    # it. Prove the warning describes real behavior, not caution.
    data = _parsed("default-orbit")
    data["cycle"]["phases"] = ["goal", "recon", "diagnose", "design", "deliver"]
    errors, _ = schema.validate_map(data)
    assert any("stage 'detect'" in e for e in errors)


def test_default_orbit_states_the_decision_ladder_without_the_word_gate():
    # Fix round 1, O-1/O-2: a reader who takes away the word "gate" goes
    # looking for an entity v1 does not have; and clearing the queue is not
    # the same act as recording the decision. Scoped to the comment blocks
    # that explain waits_on_human — "nothing is gated on reaching one", over
    # in the phases block, is a verified-true statement about phases.
    blocks = _decision_blocks("default-orbit")
    assert blocks
    for block in blocks:
        assert "gate" not in block.lower()
    text = templates.get("default-orbit")
    assert "Absence of a wait is not approval" in text
    assert 'kind = "ok"' in text and "closed wait id" in text


def test_default_orbit_nodes_are_obviously_placeholders():
    data = _parsed("default-orbit")
    assert all("placeholder" in n["id"] for n in data["nodes"])
    assert "replace" in templates.get("default-orbit").lower()


# --- single-harness and empty ---


def test_single_harness_has_one_role_and_no_reviewer():
    roles = _parsed("single-harness")["cycle"]["roles"]
    assert len(roles) == 1
    assert roles[0]["reviews"] == []
    assert "waits_on_human" in templates.get("single-harness")


def test_single_harness_names_the_vacuous_agreed_state():
    # Fix round 1, D-2: against a protocol whose headline is "silence is never
    # consent", the reassuring word is the one that must be said out loud.
    text = templates.get("single-harness")
    assert "`agreed`" in text
    assert "vacuous" in text
    assert "no reviewer assigned" in text
    assert 'reviews = ["implementer"]' in text


def test_single_harness_solo_finding_really_computes_as_agreed():
    # The disclosure above is only worth pinning if it is true end to end.
    data = _parsed("single-harness")
    state = merge.merge(data, None, [_lane("a", "implementer", [_finding()])], [], 0, NOW)
    assert state["findings"][0]["review_state"] == "agreed"


def test_single_harness_states_the_decision_ladder():
    blocks = _decision_blocks("single-harness")
    assert blocks
    for block in blocks:
        assert "gate" not in block.lower()
    text = templates.get("single-harness")
    assert 'kind = "ok"' in text and "closed wait id" in text
    assert "absence of a wait is not\n# approval" in text


# --- O-3: a stage with no role staged to it is a first-class shape ---


def test_unassigned_goal_stage_keeps_the_map_valid():
    errors, warnings = schema.validate_map(_parsed("default-orbit"))
    assert errors == [] and warnings == []
    assert "goal" in _parsed("default-orbit")["cycle"]["phases"]


def test_unassigned_goal_stage_needs_no_lane_and_warns_about_nothing():
    # Merged with no lanes at all: an unstaffed phase is not an error, not a
    # warning, and not a reason to withhold a normal "ready" status.
    state = merge.merge(_parsed("default-orbit"), None, [], [], 0, NOW)
    assert state["warnings"] == []
    assert state["project_status"]["state"] == "ready"
    assert not any("goal" in w for w in state["warnings"])


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


def test_empty_declares_no_cycle_roles():
    data = _parsed("empty")
    assert data.get("cycle", {}).get("roles", []) == []
