from datetime import datetime, timezone

from conductor import merge, prompts
from tests.test_merge_review import MAP, lane, finding

NOW = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)


def test_bootstrap_prompt_names_the_contract_files():
    text = prompts.bootstrap_prompt()
    for token in ("map.toml", "conductor/", "schema_version", "nodes", "roles"):
        assert token in text


def test_role_prompt_is_state_aware():
    ls = [lane("claude", "impl", [finding("D-1"), finding("D-2")]),
          lane("codex", "rev", verdicts={"D-1": {"disposition": "confirmed", "note": ""}})]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    text = prompts.role_prompt(state, "rev")
    assert "conductor/lanes/" in text and '"verdicts"' in text
    pending_section = text.split("awaiting your verdict")[1]
    assert "D-2" in pending_section        # still owed
    assert "D-1" not in pending_section    # already verdicted — must NOT be re-asked


def test_role_prompt_unknown_role_raises():
    state = merge.merge(MAP, None, [], [], 0, NOW)
    try:
        prompts.role_prompt(state, "ghost")
        assert False
    except prompts.UnknownRole as exc:
        msg = str(exc)
        for rid in ("impl", "rev", "sec"):   # message must name the known roles
            assert rid in msg


def test_role_prompt_unknown_role_empty_cycle_says_none_declared():
    bare = {"schema_version": 1, "project": "p",
            "nodes": [{"id": "n", "label": "n", "kind": "artifact"}]}
    state = merge.merge(bare, None, [], [], 0, NOW)
    try:
        prompts.role_prompt(state, "ghost")
        assert False
    except prompts.UnknownRole as exc:
        assert "none declared" in str(exc)


def test_role_prompt_renders_every_pending_id():
    # Pin test (behavior already correct at introduction): the pending section
    # must render ALL owed ids, one "- <id>" line each, not just pending[0].
    ls = [lane("claude", "impl", [finding("D-1"), finding("D-2")]),
          lane("codex", "rev", verdicts={"D-1": {"disposition": "confirmed", "note": ""}})]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    tail = prompts.role_prompt(state, "sec").split("awaiting your verdict")[1]
    assert "- D-1" in tail and "- D-2" in tail    # sec verdicted nothing: owes both


def test_bootstrap_prompt_tells_agent_to_validate():
    assert "conduct validate" in prompts.bootstrap_prompt()


def test_map_example_has_no_row_field():
    # ADR 0001: row is deleted from normative v1 — the vended example must not teach it.
    assert "row" not in prompts.MAP_EXAMPLE


def test_role_prompt_prefills_role_in_lane_template():
    state = merge.merge(MAP, None, [], [], 0, NOW)
    text = prompts.role_prompt(state, "rev")
    assert '"role": "rev"' in text
    assert "implementer" not in text       # spec placeholder fully replaced


def test_role_prompt_mission_names_reviewed_roles():
    state = merge.merge(MAP, None, [], [], 0, NOW)
    assert "impl" in prompts.role_prompt(state, "rev").splitlines()[0]


def test_role_prompt_pending_appears_exactly_once_and_empty_is_explicit():
    state = merge.merge(MAP, None, [], [], 0, NOW)
    text = prompts.role_prompt(state, "rev")
    assert text.count("awaiting your verdict") == 1
    assert "(none)" in text.split("awaiting your verdict")[1]
