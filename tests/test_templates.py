import tomllib

import pytest

from conductor import schema, templates

ORBIT_PHASES = ["goal", "detect", "diagnose", "design", "deliver"]


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


def test_empty_declares_no_cycle_roles():
    data = _parsed("empty")
    assert data.get("cycle", {}).get("roles", []) == []
