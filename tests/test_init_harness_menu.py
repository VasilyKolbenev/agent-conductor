"""The harness registry drives the wizard's menu, and only the id is written.

The DO-4 circuit, moved out of test_init.py whole when that file passed the
project's 800-line cap. The seam is one the file already carried as its own
section banner, and it is one question rather than a convenient length: every
test below is about the two values a harness now has — the id that lands in
`map.toml` and the display name that never may — and about the menu the
registry builds out of them. Nothing here reaches back into the sections that
stayed: no test below asks about templates, the scaffold, the stream contract
or the rendered width, and the only registry fact those sections still use is
`harnesses.RECOMMENDED` as a row count, which is a claim about the menu's
numbering rather than about what the registry vends. `_NO_REVIEWER` came with
this circuit because the sentinel is the last row of the very menu these tests
read, and no other test in the suite mentions it.

The tests about the `custom` row do both: they read the gloss out of
`_custom_row` and then run the wizard on what it says, so the sentence and the
behaviour are checked against each other rather than against a substring of the
sentence.

The five helpers this file works through — `_init_args`, `_scripted`,
`_unwrapped`, `_map_text` and `_harnesses` — are imported from test_init.py
rather than copied. A second `_scripted` would let the wizard's EOF contract
drift apart between the two files, and a second `_harnesses` would be a second
opinion about what `map.toml` says. The wizard is still never driven through
real stdin, and no test here spawns a process.
"""
import re

import pytest
import conductor.init
from conductor import harnesses, templates
from conductor.init import _NO_REVIEWER

from tests.test_init import (_harnesses, _init_args, _map_text, _scripted,
                             _unwrapped)


# --- DO-4: the harness registry drives the menu, and only the id is written ---


def test_the_menu_shows_the_product_name_and_writes_the_id(tmp_path, capsys):
    # Two values exist now, and exactly one of them may reach disk. The row
    # carries both so the user can see which is which before answering.
    assert conductor.init.run(_init_args(tmp_path), ask=_scripted(["p", "1", "1"])) == 0
    assert "claude-code — Claude Code" in _unwrapped(capsys.readouterr().err)
    written = _map_text(tmp_path)
    assert _harnesses(tmp_path)["implementer"] == "claude-code"
    assert "Claude Code" not in written        # the display name never lands


def test_a_typed_harness_lands_exactly_as_typed(tmp_path, capsys):
    # The registry is never matched against free text, in either direction: a
    # display name typed by hand stays a display name, and an unregistered id
    # is never helpfully rewritten into a registered one.
    assert conductor.init.run(_init_args(tmp_path),
                              ask=_scripted(["p", "Claude Code", "my own agent"])) == 0
    assert _harnesses(tmp_path)["implementer"] == "Claude Code"
    assert _harnesses(tmp_path)["reviewer"] == "my own agent"


def test_the_menu_offers_the_registry_and_claims_no_detection(tmp_path, capsys):
    assert conductor.init.run(_init_args(tmp_path), ask=_scripted(["p", "", ""])) == 0
    asked = _unwrapped(capsys.readouterr().err)
    for harness_id in harnesses.RECOMMENDED:                    # numbered rows
        assert f"{harness_id} — {harnesses.get(harness_id).display_name}" in asked
    for harness in harnesses.known():          # the rest, named on the custom row
        assert harness.id in asked
    for claim in ("detected", "installed on", "we found"):
        assert claim not in asked.lower()      # there is no detection, so say none


def test_the_wizard_menu_names_a_single_product(tmp_path, capsys):
    # Two brand names in one screen is a question the user has to answer
    # before they can answer ours. §9.1 of the P0 plan leaves it to the owner
    # whether the CLI carries December's terminology before the package is
    # renamed, so the wizard stays on the name the package already ships.
    assert conductor.init.run(_init_args(tmp_path), ask=_scripted(["p", "", ""])) == 0
    asked = _unwrapped(capsys.readouterr().err)
    assert "Conduct" in asked
    assert "December" not in asked


def test_the_custom_row_says_only_things_that_hold(tmp_path, capsys):
    # The gloss is the one place the wizard makes claims about ids it does not
    # number, and it ships to a user with no way to check them.
    value, gloss = conductor.init._custom_row()
    unnumbered = [h.id for h in harnesses.known()
                  if h.id not in harnesses.RECOMMENDED and h.id != harnesses.CUSTOM]
    assert value == harnesses.CUSTOM and unnumbered
    # The row names the id it writes. Choosing it and typing an id are two
    # different answers, and a gloss that only teaches typing leaves the user
    # to discover the first one from their own map.toml.
    assert value in gloss
    for harness_id in unnumbered:
        assert harness_id in gloss, harness_id
    for harness_id in harnesses.RECOMMENDED:      # numbered above, not here
        assert harness_id not in gloss, harness_id
    # Both directions, or the name is a lie. Inclusion alone leaves the leak
    # open: a `vendors()` that forgot to drop the custom row would put this
    # row's own id back among the ids you may type INSTEAD of it, and every
    # assertion above would still be green. Pinned over the one clause that
    # lists ids — the row's id legitimately appears earlier in the sentence.
    listed = gloss.split("also knows ", 1)[1].split(" — ", 1)[0]
    assert [item.strip() for item in listed.split(",")] == unnumbered
    # Primary menu: 1-3 recommended, 4 custom. With custom primary the whole
    # recommended list returns, so the reviewer's 4 is custom as well.
    assert conductor.init.run(_init_args(tmp_path), ask=_scripted(["p", "4", "4"])) == 0
    assert _harnesses(tmp_path)["implementer"] == harnesses.CUSTOM
    assert _harnesses(tmp_path)["reviewer"] == harnesses.CUSTOM


def _one_legal_gloss(number):
    """The single legal spelling of the custom row's gloss for this registry.

    Args:
        number: The menu token the gloss's exception example is worked with.

    Rebuilt from the same registry, the same example id and the number the
    menu prints — never read back out of `_custom_row`, which is the function
    under test. One spelling per registry is the point: a gloss guarded by its
    fragments survived three rewrites that kept every fragment, so the guard
    is now the whole sentence, and any other sentence is wrong by equality.
    """
    rest = ", ".join(h.id for h in harnesses.vendors()
                     if h.id not in harnesses.RECOMMENDED)
    typed = conductor.init._TYPED_EXAMPLE
    return (f" — anything else: this row writes the id {harnesses.CUSTOM}. "
            f"Conduct also knows {rest} — type any id, listed or not, and it "
            f"is written exactly as typed: type {typed} and get {typed}. "
            "The numbers this menu printed are the one exception: "
            f"answer {number} and get row {number}.")


def test_the_custom_row_gloss_has_exactly_one_legal_spelling_for_this_registry(
        tmp_path, capsys):
    # DO4-1. The fragments the other custom-row tests parse — the `also knows`
    # list, both worked examples — survived a third rewrite that kept every
    # one of them intact and wrapped them in sentences false in both clauses.
    # Fragments cannot guard the sentence around them, so the whole sentence
    # is the guard: rebuilt here from the registry, the example id and the
    # number the menu actually prints, and required to be EQUAL. A clause
    # inserted, dropped or negated fails this; a wizard that stops doing what
    # the examples show fails the two tests that run them.
    assert conductor.init.run(_init_args(tmp_path / "menu"),
                              ask=_scripted(["p"])) == 1      # menu, then EOF
    first = re.findall(r"^ {2}(\S+)\) ", capsys.readouterr().err,
                       re.MULTILINE)[0]
    _, gloss = conductor.init._custom_row()
    assert gloss == _one_legal_gloss(first)


def test_a_gloss_rewrite_that_keeps_every_parsed_fragment_fails_the_equality():
    # DO4-1, the reviewer's third diversion, kept as a regression. Every
    # fragment the parsing tests read survives below — the `also knows` list,
    # the dash after it, both worked examples with their outcomes — while the
    # sentences around them claim the opposite of what the wizard does: that
    # the listed ids are the ONLY strings the prompt preserves, that all else
    # is replaced with `custom`, and that the menu numbers are no exception. A
    # wizard run proves both clauses false, yet no fragment parse can see any
    # of it, which is how this shipped green once. The equality is the door
    # that class fails.
    rest = ", ".join(h.id for h in harnesses.vendors()
                     if h.id not in harnesses.RECOMMENDED)
    typed = conductor.init._TYPED_EXAMPLE
    sabotage = (
        f" — the ids Conduct also knows {rest} — are the ONLY strings the "
        f"prompt preserves; every other answer is silently replaced with "
        f"{harnesses.CUSTOM}, with one surviving exception soon to be "
        f"removed: type {typed} and get {typed}. The numbers this menu "
        "printed are no exception, and the old claim about them has not been "
        "true for two releases: answer 1 and get row 1.")
    unnumbered = [h.id for h in harnesses.known()
                  if h.id not in harnesses.RECOMMENDED and h.id != harnesses.CUSTOM]
    # Every fragment parse the suite aims at the real gloss succeeds on it...
    listed = sabotage.split("also knows ", 1)[1].split(" — ", 1)[0]
    assert [item.strip() for item in listed.split(",")] == unnumbered
    assert harnesses.CUSTOM in sabotage
    assert re.search(r"type (\S+) and get (\S+)\.", sabotage).groups() \
        == (typed, typed)
    assert re.search(r"answer (\S+) and get row (\S+)\.", sabotage).groups() \
        == ("1", "1")
    for harness_id in harnesses.RECOMMENDED:
        assert harness_id not in sabotage
    # ...and the equality is what refuses it. The last line is the door in the
    # suite, restated here so this regression stands alone: the shipped gloss
    # IS the one legal spelling the sabotage is not.
    assert sabotage != _one_legal_gloss("1")
    assert conductor.init._custom_row()[1] == _one_legal_gloss("1")


def test_the_custom_rows_typed_promise_is_true_of_what_gets_written(
        tmp_path, capsys):
    # The row's first claim: type an id and that id is what lands in map.toml.
    # Guarded by substring, that claim survived being rewritten into its own
    # negation — twice, by two reviewers, with the suite green both times. So
    # it is guarded by the wizard instead: the ids the row NAMES all go through
    # the prompt, and the example it demonstrates the promise with is read out
    # of the gloss and run as written. Naming an id the wizard would rewrite,
    # and demonstrating an outcome the wizard would not produce, are the same
    # lie in two clauses, and both fail here.
    _, gloss = conductor.init._custom_row()
    listed = gloss.split("also knows ", 1)[1].split(" — ", 1)[0]
    shown = re.search(r"type (\S+) and get (\S+)\.", gloss)
    assert shown, gloss             # the promise has to show its own case
    typed, promised = shown.groups()
    # REG1-02: the example must stay the UNREGISTERED half of the promise. The
    # claim is `listed or not`, the listed ids demonstrate the first half, and
    # a registry that ever gained a row under this id would leave the second
    # half demonstrated by nothing while every assertion here stayed green.
    assert harnesses.get(typed) is None
    named = [(item.strip(), item.strip()) for item in listed.split(",")]
    for index, (answer, expected) in enumerate(named + [(typed, promised)]):
        target = tmp_path / f"named-{index}"
        assert conductor.init.run(_init_args(target),
                                  ask=_scripted(["p", answer, "a-reviewer"])) == 0
        assert _harnesses(target)["implementer"] == expected, answer


def test_the_number_the_custom_row_excepts_chooses_that_row_instead(
        tmp_path, capsys):
    # The row's second claim, and the half a user is least able to check: a
    # legal harness id that happens to be a number the menu printed answers
    # with the ROW, not with itself, so the promise above needs its exception
    # or it would be false. The exception is demonstrated too, and the
    # demonstration is run against the menu the wizard actually printed —
    # a number the row excepts but the menu never printed would fail here,
    # and so would one that came back as itself after all.
    _, gloss = conductor.init._custom_row()
    shown = re.search(r"answer (\S+) and get row (\S+)\.", gloss)
    assert shown, gloss
    answer, row = shown.groups()
    assert answer == row, gloss                  # the same number, both times
    assert conductor.init.run(_init_args(tmp_path / "menu"),
                              ask=_scripted(["p"])) == 1      # menu, then EOF
    printed = dict(re.findall(r"^ {2}(\S+)\) (\S+)", capsys.readouterr().err,
                              re.MULTILINE))
    assert answer in printed, printed
    target = tmp_path / "excepted"
    assert conductor.init.run(_init_args(target),
                              ask=_scripted(["p", answer, "a-reviewer"])) == 0
    written = _harnesses(target)["implementer"]
    assert written == printed[answer]            # the row it numbers
    assert written != answer                     # so the exception is real


def test_none_means_a_harness_at_both_prompts_now(tmp_path, capsys):
    # The old sentinel WAS the word `none`, so it named a product at the first
    # prompt and removed a role at the second. Both prompts now agree, and the
    # sentinel is spelled so `templates.NAME_RE` refuses to accept it typed.
    with pytest.raises(templates.InvalidName):
        templates.check_name("harness id", _NO_REVIEWER)
    assert conductor.init.run(_init_args(tmp_path),
                              ask=_scripted(["p", "none", "none"])) == 0
    assert _harnesses(tmp_path) == {"scout": "none", "diagnostician": "none",
                                    "architect": "none", "implementer": "none",
                                    "reviewer": "none"}
