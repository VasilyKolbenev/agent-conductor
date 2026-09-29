"""The contributor map names the desk's modules, in both languages, and only real ones.

`docs/architecture.md` and `docs/architecture.ru.md` open each change with a table of "source to
read first". The desk is a new place to change and its modules are many, so the map is held to
the packaged directory in both directions: a desk module that exists and is not named reds, and
a link to one that does not exist reds. The wizard's modules belong to the lane that writes the
wizard, and the transport has a row of its own, so both are left out of the comparison.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "src" / "conductor" / "panel"
DOCS = (ROOT / "docs" / "architecture.md", ROOT / "docs" / "architecture.ru.md")
#: A link to a desk module, as the map writes one.
LINK = re.compile(r"\]\(\.\./src/conductor/panel/(desk(?:-[a-z]+)*\.js)\)")
#: The transport's own row and the wizard's family are documented elsewhere.
LEFT_OUT = re.compile(r"desk-transport\.js|desk-wizard(?:-[a-z]+)?\.js")


def packaged_desk_modules(panel: Path) -> frozenset[str]:
    """The desk's `.js` modules in `panel`, without the two families documented apart."""
    return frozenset(path.name for path in panel.glob("desk*.js")
                     if not LEFT_OUT.fullmatch(path.name))


def map_faults(text: str, packaged: frozenset[str]) -> list[str]:
    """Every way the contributor map disagrees with the packaged desk modules.

    Args:
        text: One language's architecture page.
        packaged: Output of `packaged_desk_modules`.

    Returns:
        One sentence per fault; empty when the map names exactly the packaged modules.
    """
    named = frozenset(name for name in LINK.findall(text) if not LEFT_OUT.fullmatch(name))
    faults = [f"a packaged desk module is not in the map: {name}"
              for name in sorted(packaged - named)]
    return faults + [f"the map links a desk module that is not packaged: {name}"
                     for name in sorted(named - packaged)]


def test_the_packaged_desk_modules_are_a_real_and_non_empty_set():
    packaged = packaged_desk_modules(PANEL)
    assert {"desk.js", "desk-rail.js", "desk-scene.js", "desk-status.js"} <= packaged
    assert "desk-transport.js" not in packaged and "desk-wizard.js" not in packaged


@pytest.mark.parametrize("doc", DOCS, ids=[path.name for path in DOCS])
def test_the_contributor_map_names_every_packaged_desk_module_and_no_other(doc):
    text = doc.read_text(encoding="utf-8")
    assert map_faults(text, packaged_desk_modules(PANEL)) == []


def test_both_languages_name_the_same_desk_modules():
    named = [frozenset(LINK.findall(doc.read_text(encoding="utf-8"))) for doc in DOCS]
    assert named[0] == named[1] and named[0]


def test_the_map_check_refuses_a_missing_module_and_a_module_that_does_not_exist():
    packaged = frozenset({"desk.js", "desk-rail.js"})
    whole = "[a](../src/conductor/panel/desk.js) [b](../src/conductor/panel/desk-rail.js)"
    assert map_faults(whole, packaged) == []
    assert map_faults("[a](../src/conductor/panel/desk.js)", packaged) == [
        "a packaged desk module is not in the map: desk-rail.js"]
    ghost = whole + " [c](../src/conductor/panel/desk-time.js)"
    assert map_faults(ghost, packaged) == [
        "the map links a desk module that is not packaged: desk-time.js"]
    assert map_faults("", packaged) != []
