"""The words of the feed and the summary: complete in both languages, and every key said.

`studio-i18n.js` spreads `desk-feed-copy.js` and `desk-summary-copy.js` into the one table, so the
parity guards of `tests/test_studio_i18n.py` already cover them as a whole. These read the `feed.`
and `summary.` keys alone and add what only the two regions can claim: each sentence has a
message in both languages with the same parameters, none reads the same in the two languages,
the renderer says every key the catalogue holds (the families it builds from a word of the
model included) and asks for no key the catalogue lacks, and the Studio's own words it borrows
-- an outcome, a duty, a finding's kind -- exist for every word the model can hand it.
"""
from __future__ import annotations

import re

import pytest

from tests.desk_node import PANEL, run_js

MODULES = {"i18n": "studio-i18n.js", "feed": "desk-feed-model.js", "words": "studio-runwords.js"}
#: Each region: the catalogue prefix and the module that draws the region.
REGIONS = {"feed": "desk-feed.js"}
QUOTED = re.compile(r'"((?:feed|summary)\.[a-z_.]+)"')
FAMILY = re.compile(r"`((?:feed|summary)\.[a-z_]+_)\$\{[^}]+\}`")


def catalogue(prefix: str) -> dict[str, dict[str, str]]:
    return run_js("""
      console.log(JSON.stringify(Object.fromEntries(Object.entries(i18n.MESSAGES)
        .filter(([key]) => key.startsWith(d + ".")))));
    """, MODULES, prefix)


@pytest.mark.parametrize("prefix", list(REGIONS))
def test_every_message_of_the_region_exists_in_both_languages_with_the_same_parameters(prefix):
    out = run_js("""
      const rows = Object.fromEntries(Object.entries(i18n.MESSAGES)
        .filter(([key]) => key.startsWith(d + ".")));
      const broken = {...rows, "x.y": {en: "{a}", ru: "{b}"}};
      console.log(JSON.stringify({count: Object.keys(rows).length,
        whole: i18n.validateMessages(rows), catches: i18n.validateMessages(broken)}));
    """, MODULES, prefix)
    assert out["count"] >= 8 and out["whole"] is True and out["catches"] is False


@pytest.mark.parametrize("prefix", list(REGIONS))
def test_no_message_of_the_region_reads_the_same_in_both_languages(prefix):
    same = [key for key, pair in catalogue(prefix).items() if pair["en"] == pair["ru"]]
    assert same == [], "a message that reads the same in both languages is untranslated"


def _said(prefix: str, module: str) -> set[str]:
    """The keys a renderer says: those it quotes and the families it builds from a word."""
    source = (PANEL / module).read_text(encoding="utf-8")
    words = run_js("""
      const checked = words.VERIFICATION_STATES.filter((word) => word !== "unverified");
      console.log(JSON.stringify({verdict: checked, decision: feed.DECISION_WORDS}));
    """, MODULES)
    stems = FAMILY.findall(source)
    assert all(stem.startswith(f"{prefix}.") for stem in stems), stems
    built = {f"{stem}{word}" for stem in stems for word in words[stem.split(".")[1][:-1]]}
    return set(QUOTED.findall(source)) | built


@pytest.mark.parametrize("prefix,module", list(REGIONS.items()))
def test_the_renderer_says_every_key_of_its_region_and_asks_for_none_the_catalogue_lacks(
        prefix, module):
    held = set(catalogue(prefix))
    said = {key for key in _said(prefix, module) if key.startswith(f"{prefix}.")}
    assert said == held, sorted(said ^ held)


def test_the_studio_words_the_feed_borrows_exist_for_every_word_the_model_can_hand_it():
    needed = run_js("""
      console.log(JSON.stringify([
        ...words.RESULT_OUTCOMES.map((w) => `scene.outcome_${w}`),
        "scene.duty_perform", "scene.duty_verify", "scene.gate", "scene.pass",
        "view.verification_note",
        ...["defect", "missing_requirement", "verification_gap"].map((k) => `feedback.${k}`)]
        .filter((key) => !Object.hasOwn(i18n.MESSAGES, key))));
    """, MODULES)
    assert needed == []
