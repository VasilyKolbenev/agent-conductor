import json
import tomllib
from datetime import datetime, timezone

import pytest
from conductor import merge, prompts, schema, store, templates
from tests.test_merge_review import MAP, lane, finding

NOW = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)

#: A written map to hand `bootstrap_prompt`, for the tests whose claim is not
#: about which map it was. It takes the text and not just the path on purpose,
#: so there is no map-less call to make.
SCAFFOLD = templates.get(templates.DEFAULT)


def _template_block(text):
    """Extract the fenced starter-template JSON from a rendered role prompt."""
    return text.split("```json\n", 1)[1].split("\n```", 1)[0]


def test_bootstrap_prompt_names_the_contract_files():
    text = prompts.bootstrap_prompt(prompts.DEFAULT_MAP_PATH, SCAFFOLD)
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
    assert "conduct validate" in prompts.bootstrap_prompt(prompts.DEFAULT_MAP_PATH,
                                                          SCAFFOLD)


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


def test_deliver_hands_off_to_the_human_not_to_a_next_stage():
    # M15: deliver ends the Run — there is no next stage to be entitled to
    # anything, so the shared handoff header would be a false statement.
    deliver = prompts._stage_block("deliver")
    assert "the human accepting this Run" in deliver
    assert "next stage is entitled" not in deliver
    for stage in ("goal", "detect", "diagnose", "design"):
        assert "next stage is entitled" in prompts._stage_block(stage)


def test_deliver_never_tells_an_agent_to_record_its_own_verdicts():
    # C1: verdicts live in the REVIEWING role's lane. Writing them anywhere
    # else is either forbidden (another agent's lane) or void (a self-verdict
    # is excluded from every computation), so the contract must not ask.
    deliver = prompts._stage_block("deliver")
    assert "record the verdicts" not in deliver
    assert "Name the role that owes your findings a verdict" in deliver
    assert "waits_on_human entry of kind review" in deliver


def test_diagnose_offers_the_whole_disposition_vocabulary():
    # I2: `partial` is load-bearing — merge treats it as a disagreement
    # signal. An agent offered two options will not reach for the third.
    diagnose = prompts._stage_block("diagnose")
    for disposition in ("confirmed", "refuted", "partial"):
        assert disposition in diagnose


def test_role_prompt_names_who_reviews_this_role():
    # The reverse review edge, which the deliver contract depends on being
    # readable rather than guessed.
    state = merge.merge(STAGED_MAP, None, [], [], 0, NOW)
    assert "Your own findings are reviewed by: rev" in prompts.role_prompt(state, "impl")


def test_role_prompt_says_plainly_when_no_role_reviews_you():
    state = merge.merge(STAGED_MAP, None, [], [], 0, NOW)
    text = prompts.role_prompt(state, "rev")
    assert "nobody owes your findings a verdict" in text


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


# --- bootstrap_prompt: a deliverable someone redirects to a file ---

LONG_PATH = r"C:\Users\User\Projects\a-rather-long-repository-name\conductor\map.toml"


def _widest(text, skip=None):
    """The longest rendered line, ignoring any line holding `skip`."""
    lines = [l for l in text.split('\n') if not (skip and skip in l)]
    return max((len(l) for l in lines), default=0)


def test_the_bootstrap_prompt_stands_alone_when_redirected():
    # `conduct init > bootstrap.txt` yields this and nothing else, so it may
    # not lean on anything the CLI printed around it.
    text = prompts.bootstrap_prompt("conductor/map.toml", SCAFFOLD)
    for needed in ("conductor/map.toml", "schema_version", "[[nodes]]",
                   "[[cycle.roles]]", "conduct validate", "depends_on"):
        assert needed in text
    for dangling in ("above", "below", "the rules"):
        assert dangling not in text


@pytest.mark.parametrize("path", ["conductor/map.toml", LONG_PATH])
@pytest.mark.parametrize("name", [n for n, _ in templates.names()])
def test_the_bootstrap_prompt_stays_inside_the_width(path, name):
    # The path gets a line of its own precisely so an absolute one cannot
    # stretch the prose: it is unwrappable, and folding sentences around it
    # pushed two lines past 130 columns. Every template, because step 2 is now
    # one of three hand-wrapped variants and only one of them used to exist.
    text = prompts.bootstrap_prompt(path, templates.get(name))
    assert _widest(text, skip=path) <= prompts.WIDTH
    assert f"\n    {path}\n" in text          # alone on its line, never inline
    # `skip=path` must skip exactly one line. Without this the two assertions
    # above pass while the path is ALSO interpolated back into a sentence:
    # the standalone line still exists, and every line the re-interpolation
    # widened is skipped from the width check for containing the path.
    assert text.count(path) == 1


# --- step 2 is read off the map, so no template name can decide it ----------


def _relabelled(text, how_many=None):
    """A written map with its PLACEHOLDER labels filled in, as a person would.

    Args:
        text: A template's map text.
        how_many: How many labels to replace; None replaces every one, which
            is what a user who finished the job leaves behind.

    Returns:
        The rewritten map. Editing the file is the point: no template name
        changes here, so anything that answers by template name answers about
        a map that no longer exists.
    """
    done, out = 0, []
    for line in text.split("\n"):
        if (line.startswith(f'label = "{prompts.PLACEHOLDER_LABEL}')
                and (how_many is None or done < how_many)):
            line = f'label = "billing service {done}"'
            done += 1
        out.append(line)
    assert done == (how_many or done) and done, "the fixture replaced nothing"
    return "\n".join(out)


def test_a_map_whose_placeholders_a_person_replaced_is_not_called_a_placeholder():
    # The class, not the instance. `minimal` is only the map that happens to
    # arrive without placeholders; this one has none because someone did the
    # work, and the same sentence has to be true of it.
    edited = _relabelled(SCAFFOLD)
    assert prompts.placeholder_nodes(edited)[0] == 0
    text = prompts.bootstrap_prompt(prompts.DEFAULT_MAP_PATH, edited)
    assert prompts._STEP_NO_NODE_IS_A_PLACEHOLDER in text
    assert prompts._STEP_EVERY_NODE_IS_A_PLACEHOLDER not in text
    assert prompts._STEP_SOME_NODES_ARE_PLACEHOLDERS not in text


#: A valid map whose one label carries the marker without opening with it —
#: the shape `templates` never writes and a person easily does.
_MARKER_MID_LABEL = '''schema_version = 1
project = "shop"

[[nodes]]
id = "billing"
label = "billing (PLACEHOLDER - replace me)"
kind = "component"
'''


def test_a_label_carrying_the_marker_anywhere_in_it_is_counted_as_marked():
    # A prefix test called this label unmarked, and the prompt then printed
    # "no label is marked PLACEHOLDER" about a file where one plainly is —
    # a false sentence about the reader's own map, and `validate` accepts the
    # map, so nothing else would have said so.
    assert schema.validate_map(tomllib.loads(_MARKER_MID_LABEL))[0] == []
    assert prompts.placeholder_nodes(_MARKER_MID_LABEL) == (1, 1)
    text = prompts.bootstrap_prompt(prompts.DEFAULT_MAP_PATH, _MARKER_MID_LABEL)
    assert prompts._STEP_EVERY_NODE_IS_A_PLACEHOLDER in text
    assert prompts._STEP_NO_NODE_IS_A_PLACEHOLDER not in text


def test_a_half_replaced_map_is_told_only_some_of_its_nodes_are_placeholders():
    # The shape a map spends most of its life in. "Every block is a
    # placeholder" and "none is" are both false here, so a two-way answer
    # would be wrong exactly where a user is actually working.
    half = _relabelled(SCAFFOLD, how_many=2)
    placeholders, nodes = prompts.placeholder_nodes(half)
    assert 0 < placeholders < nodes
    text = prompts.bootstrap_prompt(LONG_PATH, half)
    assert prompts._STEP_SOME_NODES_ARE_PLACEHOLDERS in text
    assert prompts._STEP_EVERY_NODE_IS_A_PLACEHOLDER not in text
    assert prompts._STEP_NO_NODE_IS_A_PLACEHOLDER not in text
    assert _widest(text, skip=LONG_PATH) <= prompts.WIDTH


#: The imperative each step-2 variant exists to give, flattened to one line.
#: Held on the VERB, never on the negation clause around it: every assertion
#: that only pinned "Every [[nodes]] block in it is a placeholder" or "No
#: [[nodes]] block in it is a placeholder" survived a rewrite that kept the
#: clause word for word and told the agent to delete the real nodes, or to
#: leave the file exactly as it found it. The clause reports a fact; the
#: instruction is what a map either gets or does not.
_STEP_IMPERATIVES = {
    prompts._STEP_EVERY_NODE_IS_A_PLACEHOLDER:
        "Replace them with the real components of this project",
    prompts._STEP_SOME_NODES_ARE_PLACEHOLDERS:
        "Replace those with the real components of this project, check the "
        "rest still describe it",
    prompts._STEP_NO_NODE_IS_A_PLACEHOLDER:
        "Check every one against THIS project, replace what does not describe it",
}


def test_every_variant_of_step_two_carries_the_work_and_an_imperative_the_others_lack():
    # Two claims, and the second is why the first is not enough. No variant may
    # become an empty place: whichever is chosen, the agent is still told which
    # table it edits and what to add to it. And the variants must be told apart
    # by their instruction rather than by the sentence in front of it — being
    # different is a RELATION between the three, so it is asserted as one,
    # against every other variant rather than against a list someone typed.
    owed = "add one [[nodes]] block per further component you want reported on:"
    reached = set()
    for written in (SCAFFOLD, _relabelled(SCAFFOLD), _relabelled(SCAFFOLD, 2)):
        step = prompts._node_step(written)
        assert step.startswith("2. Open that file.")
        assert owed in " ".join(step.split())
        reached.add(step)
    assert reached == set(_STEP_IMPERATIVES), "a variant was never reached"
    for variant, imperative in _STEP_IMPERATIVES.items():
        flat = " ".join(variant.split())
        assert imperative in flat, imperative
        for other, elsewhere in _STEP_IMPERATIVES.items():
            if other is not variant:
                assert elsewhere not in flat, (imperative, elsewhere)
