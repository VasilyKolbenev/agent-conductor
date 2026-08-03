import json
import tomllib
from datetime import datetime, timezone

from conductor import merge, prompts, schema, store
from tests.test_merge_review import MAP, lane, finding

NOW = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)


def _template_block(text):
    """Extract the fenced starter-template JSON from a rendered role prompt."""
    return text.split("```json\n", 1)[1].split("\n```", 1)[0]


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


def test_map_example_validates_clean():
    # The example is vended verbatim by `conduct init`, so anything wrong in it
    # ships to every new project. Parse it for real and put it through the same
    # validator the user's own map faces — a role staged onto a phase absent
    # from cycle.phases, say, would otherwise never be caught here.
    errors, warnings = schema.validate_map(tomllib.loads(prompts.MAP_EXAMPLE))
    assert errors == [] and warnings == []


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


# --- C6.1 prompts v2: strict-JSON starter template, lifecycle, enriched pending ---


def test_role_prompt_template_is_copy_safe_strict_json():
    # The heart of C6.1: an agent that copies the vended template verbatim
    # (only swapping the updated placeholder) must produce a VALID lane.
    state = merge.merge(MAP, None, [], [], 0, NOW)
    text = prompts.role_prompt(state, "rev", author="codex")
    block = _template_block(text)
    swapped = block.replace("REPLACE-WITH-CURRENT-UTC-ISO8601",
                            "2026-07-30T12:00:00+00:00")
    parsed = json.loads(swapped)                     # strict JSON — no // comments
    errors, _ = schema.validate_lane(parsed, filename_stem="codex")
    assert errors == []


def test_role_prompt_has_no_commented_spec_template():
    # The old PROTOCOL.md §3 excerpt carried // comments and fictional example
    # data (D-2, smoke, w-config) — none of it may leak into the vended prompt.
    state = merge.merge(MAP, None, [], [], 0, NOW)
    text = prompts.role_prompt(state, "rev", author="codex")
    assert "//" not in text
    assert "2026-07-29" not in text                  # stale example timestamp
    assert "w-config" not in text


def test_role_prompt_author_fills_lane_path_and_template():
    state = merge.merge(MAP, None, [], [], 0, NOW)
    text = prompts.role_prompt(state, "rev", author="codex")
    assert "conductor/lanes/codex.json" in text
    assert '"author": "codex"' in text


def test_role_prompt_without_author_uses_placeholder_never_claude():
    state = merge.merge(MAP, None, [], [], 0, NOW)
    text = prompts.role_prompt(state, "rev")
    assert "<your-author-id>" in text
    assert "claude" not in text                      # no hardcoded author anywhere
    assert "REPLACE-WITH-CURRENT-UTC-ISO8601" in text
    # The swap instruction must name the author placeholder too — "copy it
    # verbatim" alone would leave <your-author-id> in the file and filename.
    assert "with your author id" in text
    assert "file name" in text


def test_author_placeholder_can_never_become_a_real_lane():
    # Load-bearing pin: the angle brackets must never match store.AUTHOR_RE.
    # Respelled regex-legal (e.g. your_author_id), a verbatim no-author copy
    # would silently become a valid lane named after the placeholder.
    assert store.AUTHOR_RE.fullmatch(prompts._AUTHOR_PLACEHOLDER) is None
    state = merge.merge(MAP, None, [], [], 0, NOW)
    block = _template_block(prompts.role_prompt(state, "rev"))
    swapped = block.replace("REPLACE-WITH-CURRENT-UTC-ISO8601",
                            "2026-07-30T12:00:00+00:00")
    errors, _ = schema.validate_lane(json.loads(swapped), filename_stem="codex")
    assert errors                                    # author swap stays mandatory


def test_role_prompt_states_lifecycle_contract():
    state = merge.merge(MAP, None, [], [], 0, NOW)
    text = prompts.role_prompt(state, "rev")
    for token in ("temp file", "NEVER edit another agent's lane",
                  "conduct validate", "events.jsonl", '"kind": "ok"',
                  '"ts": '):                         # the event line's required shape
        assert token in text


# --- DO-2: stage-aware lifecycle contracts ---

STAGED_MAP = {"schema_version": 1, "project": "p",
              "nodes": [{"id": "n", "label": "n", "kind": "artifact"}],
              "cycle": {"phases": ["goal", "detect", "diagnose", "design", "deliver"],
                        "roles": [{"id": "scout", "harness": "cc", "reviews": [],
                                   "stage": "detect"},
                                  {"id": "impl", "harness": "cc", "reviews": [],
                                   "stage": "deliver"},
                                  {"id": "rev", "harness": "cx", "reviews": ["impl"]}]}}

CUSTOM_MAP = {"schema_version": 1, "project": "p",
              "nodes": [{"id": "n", "label": "n", "kind": "artifact"}],
              "cycle": {"phases": ["recon", "ship"],
                        "roles": [{"id": "impl", "harness": "cc", "reviews": [],
                                   "stage": "recon"}]}}


def test_role_prompt_renders_the_stage_contract_for_a_staged_role():
    state = merge.merge(STAGED_MAP, None, [], [], 0, NOW)
    text = prompts.role_prompt(state, "scout", author="codex")
    assert "Stage: detect" in text
    assert "What is actually true right now?" in text
    assert "unverified" in text                      # the detect contract's own word


def test_role_prompt_stage_contracts_differ_per_stage():
    state = merge.merge(STAGED_MAP, None, [], [], 0, NOW)
    scout = prompts.role_prompt(state, "scout", author="codex")
    impl = prompts.role_prompt(state, "impl", author="codex")
    assert "Stage: deliver" in impl and "Stage: detect" not in impl
    assert "Stage: detect" in scout and "Stage: deliver" not in scout


def test_role_prompt_omits_the_stage_block_for_an_unstaged_role():
    state = merge.merge(STAGED_MAP, None, [], [], 0, NOW)
    text = prompts.role_prompt(state, "rev", author="codex")
    assert "Stage:" not in text


def test_role_prompt_omits_the_stage_block_for_a_custom_phase_name():
    # A project with its own phases is legal (spec §2): the stage is valid but
    # is not an Orbit stage. Degrade silently — never render a wrong contract.
    state = merge.merge(CUSTOM_MAP, None, [], [], 0, NOW)
    text = prompts.role_prompt(state, "impl", author="codex")
    assert "Stage:" not in text
    assert "recon" not in text


def test_role_prompt_keeps_the_generic_lifecycle_alongside_the_stage_block():
    state = merge.merge(STAGED_MAP, None, [], [], 0, NOW)
    text = prompts.role_prompt(state, "scout", author="codex")
    assert "Lifecycle:" in text
    assert "NEVER edit another agent's lane" in text


def test_role_prompt_ordering_trap_holds_with_a_stage_block():
    # The pending section must stay LAST and appear exactly once, whatever
    # else is injected above it.
    state = merge.merge(STAGED_MAP, None, [], [], 0, NOW)
    text = prompts.role_prompt(state, "impl", author="codex")
    assert text.count("awaiting your verdict") == 1
    tail = text.split("awaiting your verdict")[1]
    assert "Stage:" not in tail and "Lifecycle:" not in tail


def test_every_orbit_stage_has_a_contract_with_a_question_and_owed_lines():
    for stage in ("goal", "detect", "diagnose", "design", "deliver"):
        block = prompts._stage_block(stage)
        assert block.startswith(f"Stage: {stage} ")
        assert block.rstrip().endswith(".")
        assert block.count("\n- ") >= 4               # the contract it owes


def test_stage_block_is_empty_for_absent_and_unknown_stages():
    assert prompts._stage_block(None) == ""
    assert prompts._stage_block("recon") == ""
    assert prompts._stage_block("") == ""


def test_role_prompt_pending_block_is_enriched():
    ls = [lane("claude", "impl", [finding("D-1"), finding("D-2")]),
          lane("codex", "rev", verdicts={"D-1": {"disposition": "confirmed", "note": ""}})]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    tail = prompts.role_prompt(state, "rev").split("awaiting your verdict")[1]
    assert "- D-2: t" in tail                        # id plus title
    assert "severity: blocker" in tail
    assert "author: claude" in tail
    assert "evidence: e" in tail
    assert "refs: n" in tail
    assert "D-1" not in tail                         # already verdicted — not re-asked
