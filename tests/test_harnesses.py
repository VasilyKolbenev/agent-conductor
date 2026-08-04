"""Tests for `conductor.harnesses` — the bundled known-harness registry.

Two separable promises, and the second is the one that matters. The first is
that the data is well formed: ids unique, monograms two characters, accents
real hex, documentation links present. The second is that none of it can
reach a merge rule — ADR 0001 §6 makes branding UI/adapter metadata and the
protocol carries only the harness string, so `state.json` must be identical
whether or not a project's harness happens to be listed here. The additivity
block below is the same shape `role.stage` uses in test_merge_queue_phase.py,
for the same reason: an equality that a fixture could quietly make vacuous is
worth less than an equality plus a test that the fixture still has teeth.
"""
import re

from conductor import harnesses, merge
from tests.test_merge_queue_phase import NOW, ROLES_MAP, rich_lanes

HEX_RE = re.compile(r"\A#[0-9a-f]{6}\Z")


# --- the data itself ---


def test_the_registry_lists_the_products_it_says_it_does():
    # Pinned by id, in wizard order: a reordering or a quiet deletion is a
    # decision about what December claims to know, not an implementation detail.
    assert [h.id for h in harnesses.known()] == [
        "claude-code", "codex", "cursor", "windsurf", "kimi-code",
        "qwen-code", "grok-build", "github-copilot", "custom"]

def test_deepseek_is_deliberately_absent():
    # Not because the integration story is missing — DeepSeek publishes models,
    # APIs and official guides for integrating them with third-party harnesses.
    # Because this registry lists HARNESS PRODUCTS, and DeepSeek identifies no
    # first-party public coding harness of its own; a third-party harness is
    # registered under its own product identity. Revisit if that changes. The
    # test exists so the row is a decision someone argues with, not a helpful
    # two-line edit.
    text = " ".join(f"{h.id} {h.display_name}" for h in harnesses.known()).lower()
    assert "deepseek" not in text
    assert harnesses.get("deepseek") is None

def test_the_registry_never_normalises_a_display_name_into_an_id():
    # No slugify, no case folding, no "they probably meant claude-code". A
    # lookup by display name is a miss, and a miss resolves to the neutral
    # badge under the string exactly as given.
    assert harnesses.get("Claude Code") is None
    resolved = harnesses.resolve("Claude Code")
    assert resolved.id == "Claude Code" and resolved.display_name == "Claude Code"
    assert resolved is not harnesses.get("claude-code")

def test_every_entry_is_complete_and_unambiguous():
    entries = harnesses.known()
    assert len({h.id for h in entries}) == len(entries)
    assert len({h.monogram for h in entries}) == len(entries)   # badges differ
    for harness in entries:
        assert harness.id and harness.display_name
        assert len(harness.monogram) == 2, harness.id
        assert HEX_RE.fullmatch(harness.accent_dark.lower()), harness.id
        assert HEX_RE.fullmatch(harness.accent_light.lower()), harness.id
        assert isinstance(harness.executable_hints, tuple)

def test_every_vendor_entry_carries_a_documentation_url():
    # `custom` is the exception and is meant to be: it names no vendor, so
    # there is no vendor documentation to link. Every other row must have one
    # — an entry we cannot point at is an entry we should not be claiming.
    for harness in harnesses.known():
        if harness.id == harnesses.CUSTOM:
            assert harness.docs == ""
        else:
            assert harness.docs.startswith("https://"), harness.id

def test_the_recommended_ids_are_registry_entries_and_exclude_custom():
    # The wizard numbers these. A recommended id with no entry would render a
    # row with no product behind it.
    assert harnesses.RECOMMENDED
    for harness_id in harnesses.RECOMMENDED:
        assert harnesses.get(harness_id) is not None
    assert harnesses.CUSTOM not in harnesses.RECOMMENDED


# --- the colours are validated as DATA, and only as data ---
# A hue-separation rule was written here and then removed on the owner's
# decision: an HSV gap does not scale with the registry, distorts colours users
# recognise, does nothing for colour-vision deficiency, and is not evidence
# that two things cannot be confused. Identity and status are separated by
# channel — monogram and swatch against glyph, text and chip — and the
# forbidden surfaces for a harness accent are listed in the module docstring
# and enforced structurally in DEC-UI, where the accent is applied. Do not
# reintroduce a colour-distance assertion here.


def test_both_themes_carry_a_well_formed_accent():
    for harness in harnesses.known():
        assert HEX_RE.fullmatch(harness.accent_dark.lower()), harness.id
        assert HEX_RE.fullmatch(harness.accent_light.lower()), harness.id
        assert harness.accent_dark != harness.accent_light, harness.id


# --- an unregistered harness: neutral and stable, never guessed ---


def test_an_unregistered_harness_resolves_to_a_neutral_badge():
    resolved = harnesses.resolve("in-house-sast")
    assert resolved.id == "in-house-sast"
    assert resolved.display_name == "in-house-sast"      # never invented
    assert resolved.monogram == "IH"                    # first two words
    assert resolved.docs == "" and resolved.executable_hints == ()
    custom = harnesses.get(harnesses.CUSTOM)
    assert resolved.accent_dark == custom.accent_dark    # the neutral badge
    assert resolved.accent_light == custom.accent_light

def test_resolving_a_registered_harness_returns_the_registry_entry():
    assert harnesses.resolve("claude-code") is harnesses.get("claude-code")

def test_the_fallback_monogram_is_stable_and_derived_from_the_string_alone():
    for value, monogram in [("kimi cli", "KC"), ("my_own_agent", "MO"),
                            ("gemini", "GE"), ("x", "X"), ("7", "7"),
                            ("(", "?")]:
        assert harnesses.resolve(value).monogram == monogram
    assert harnesses.resolve("gemini").monogram == harnesses.resolve("gemini").monogram


# --- additivity: the merger cannot tell a known harness from an unknown one ---


def _harnessed(map_data, primary, reviewer):
    """`ROLES_MAP` with its two harness labels replaced."""
    roles = [{**r, "harness": primary if r["id"] == "impl" else reviewer}
             for r in map_data["cycle"]["roles"]]
    return {**map_data, "cycle": {**map_data["cycle"], "roles": roles}}


def _without_harness(state):
    """`state` with every role's `harness` dropped — and nothing else touched.

    One key deep, like `without_stage`: a recursive scrub would also hide a
    harness label that had leaked into a lane, a finding or the action, which
    is exactly what this comparison exists to forbid.
    """
    roles = [{k: v for k, v in r.items() if k != "harness"}
             for r in state["cycle"]["roles"]]
    return {**state, "cycle": {**state["cycle"], "roles": roles}}


KNOWN_MAP = _harnessed(ROLES_MAP, "claude-code", "codex")
UNKNOWN_MAP = _harnessed(ROLES_MAP, "no-such-harness", "nor-is-this-one")


def test_the_additivity_fixture_has_something_to_protect():
    # The equality below is only as strong as the state it compares, and only
    # meaningful while one map is registered and the other is not.
    assert harnesses.get("claude-code") and harnesses.get("codex")
    assert harnesses.get("no-such-harness") is None
    state = merge.merge(KNOWN_MAP, None, rich_lanes(), [], 0, NOW)
    assert state["kpi"]["disagreements"] == 1 and state["kpi"]["queue"] == 1
    assert state["kpi"]["stale_lanes"] == 1
    assert state["map"]["nodes"][0]["status"] == "contested"

def test_being_in_the_registry_changes_nothing_but_the_label_itself():
    known = merge.merge(KNOWN_MAP, None, rich_lanes(), [], 0, NOW)
    unknown = merge.merge(UNKNOWN_MAP, None, rich_lanes(), [], 0, NOW)
    assert [r["harness"] for r in known["cycle"]["roles"]] != \
        [r["harness"] for r in unknown["cycle"]["roles"]]
    assert _without_harness(known) == _without_harness(unknown)

def test_being_in_the_registry_changes_no_merge_computed_value():
    # The equality above would catch all of these; naming them says which
    # promises DO-4 is making, so a regression reads as a broken promise.
    known = merge.merge(KNOWN_MAP, None, rich_lanes(), [], 0, NOW)
    unknown = merge.merge(UNKNOWN_MAP, None, rich_lanes(), [], 0, NOW)
    assert ([f["review_state"] for f in known["findings"]]
            == [f["review_state"] for f in unknown["findings"]] == ["disagreement"])
    assert known["project_status"] == unknown["project_status"]
    assert known["next_action"] == unknown["next_action"]
    assert known["human_queue"] == unknown["human_queue"]
    assert known["invariants"] == unknown["invariants"]
    assert known["kpi"] == unknown["kpi"]
    assert known["warnings"] == unknown["warnings"]

def test_the_registry_carries_no_lookup_of_its_own_hints():
    # `executable_hints` is documentation for a person reading the registry.
    # Its shape is data and nothing resolves it — the structural half of that
    # promise is the machine-probing ban in test_init.py, which now parses
    # this module too.
    for harness in harnesses.known():
        assert all(isinstance(hint, str) for hint in harness.executable_hints)
    assert harnesses.get("claude-code").executable_hints == ("claude",)
