"""The desk's own words: complete in both languages, and every key the page names resolves.

`studio-i18n.js` spreads `desk-copy.js` into the one table, so the parity guards of
`tests/test_studio_i18n.py` already cover it as a whole. These read the `desk.` keys alone
and add what only the desk page can claim: it names no word it has no message for, in
either language, and no message says the same thing in the two languages unless it is a
name.
"""
from __future__ import annotations

import re

from tests.desk_node import PANEL, run_js

MODULES = {"i18n": "studio-i18n.js"}
PAGE_KEY = r'data-i18n(?:-label)?="([a-z_.]+)"'


def test_every_desk_message_exists_in_russian_and_english_with_the_same_parameters():
    out = run_js("""
      const keys = Object.keys(i18n.MESSAGES).filter((key) => key.startsWith("desk."));
      const rows = Object.fromEntries(keys.map((key) => [key, i18n.MESSAGES[key]]));
      const broken = {...rows, "desk.x": {en: "{a}", ru: "{b}"}};
      const same = keys.filter((key) => rows[key].en === rows[key].ru);
      console.log(JSON.stringify({count: keys.length, whole: i18n.validateMessages(rows),
        catches: i18n.validateMessages(broken), same}));
    """, MODULES)
    assert out["count"] >= 8
    assert out["whole"] is True and out["catches"] is False
    assert out["same"] == [], "a message that reads the same in both languages is untranslated"


def test_every_key_the_desk_page_names_resolves_in_both_languages():
    """The keys of the page's own markup, and the ones the boot module says by name."""
    keys = re.findall(PAGE_KEY, (PANEL / "desk.html").read_text(encoding="utf-8"))
    keys += re.findall(r'message\(locale\(\), "(desk\.[a-z_.]+)"\)',
                       (PANEL / "desk.js").read_text(encoding="utf-8"))
    # Two controls may use the same label; the key still has one translation.
    assert len(keys) >= 8 and len(set(keys)) >= 8, keys
    rendered = run_js("""
      console.log(JSON.stringify(d.map((key) => i18n.LOCALES.map(
        (locale) => i18n.message(locale, key)))));
    """, MODULES, keys)
    assert all(len(pair) == 2 and all(pair) and pair[0] != pair[1] for pair in rendered)
    assert all(key.startswith("desk.") for key in keys)


def test_every_desk_key_is_said_by_the_page_or_a_desk_module_and_none_says_a_missing_key():
    """No orphan word, and no module asking the catalogue for a word it lacks."""
    catalogue = run_js("""
      console.log(JSON.stringify(Object.keys(i18n.MESSAGES).filter(
        (key) => key.startsWith("desk."))));
    """, MODULES)
    # Decisions reuse Studio's renderer, which says the Desk-specific Pult words.
    sources = [(PANEL / "desk.html").read_text(encoding="utf-8"),
               (PANEL / "studio-people.js").read_text(encoding="utf-8")] + [
        path.read_text(encoding="utf-8") for path in sorted(PANEL.glob("desk*.js"))
        if path.name != "desk-copy.js"]
    said = {key for source in sources for key in re.findall(r'"(desk\.[a-z_.]+)"', source)}
    said |= {key for key in re.findall(PAGE_KEY, sources[0])}
    dynamic = {
        "desk.connection.": ("open", "connecting", "closed"),
        "desk.people.": ("empty", "loading", "failed"),
        "desk.quota.": ("empty", "loading", "failed", "disconnected", "no_data"),
    }
    for prefix, phases in dynamic.items():
        assert any(f"`{prefix}${{" in source for source in sources), prefix
        said.update(prefix + phase for phase in phases)
    assert said == set(catalogue), sorted(said ^ set(catalogue))


def test_the_catalogue_says_the_regions_the_spec_names_in_russian():
    out = run_js("""
      console.log(JSON.stringify(Object.fromEntries(
        Object.keys(d).map((key) => [key, i18n.MESSAGES[key]?.ru ?? null]))));
    """, MODULES, {"desk.classic": "Прежняя панель", "desk.pult.label": "Ваш пульт",
                   "desk.feed.label": "Ход работы"})
    assert out == {"desk.classic": "Прежняя панель", "desk.pult.label": "Ваш пульт",
                   "desk.feed.label": "Ход работы"}
