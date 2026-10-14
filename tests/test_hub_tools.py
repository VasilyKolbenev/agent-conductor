"""The tools the hub page asks a person to pin (spec 8.8, 4.6.3, 4.6.4; lane H's handoff 4 and 5).

`GET /hub/setup` lists, for a tool that is not settled (`not_pinned`, or pinned and `changed`,
`too_old` or `unreadable`), the candidates the hub itself found: an id, the last folder and file
(`display`) and the version the tool said. `hub-tools.js` holds that as values: the rows of the
banner, and the notice that follows a press of «Закрепить». What it must never do:

- offer a candidate to a tool that is settled, or to a pin FILE that cannot be read (the owner has
  to fix the file first), or say a pin-file problem as the tool's VERSION;
- carry anything but the display and the version into the words, or a candidate whose id is not of
  the grammar `cand-<32 hex>`: the page never sees or sends a path, and the id goes to the pin route
  and nowhere else;
- say `hub.tool.restart_to_find` beside a tool that is anything but not pinned.
"""
from __future__ import annotations

from typing import Any

from conductor.hub import service
from tests.desk_wizard_node import run_js

MODULES = {"tools": "hub-tools.js", "copy": "hub-copy.js"}
CAND = "cand-4e1a9c07b25d4f3a8c61d09e7b2f5a13"
FILE_REASONS = ("corrupt", "unreadable", "unwritable")
PRELUDE = """
const show = (value) => console.log(JSON.stringify(value));
const cand = (over = {}) => ({candidate_id: d.cand, display: "Git\\\\cmd\\\\git.exe",
  version: "2.45.2", ...over});
const git = (over = {}) => ({state: "not_pinned", display: null, version: null,
  candidates: [cand()], ...over});
const gh = (over = {}) => ({state: "pinned", display: "GitHub CLI\\\\gh.exe", version: "2.47.1",
  candidates: [], ...over});
const setup = (tools = {}) => ({profile: "present", tools: {gh: gh(), git: git(), ...tools}});
const rows = (value, locale = "en") => tools.toolRows(value, locale);
const say = (locale, key, params) => copy.hubText(locale, key, params);
const refused = (code, detail = null) => ({status: "refused", code,
  payload: {error: {code, message: "", detail}}});
"""


def js(body: str, **data: Any) -> Any:
    return run_js(PRELUDE + body, {"cand": CAND, **data}, modules=MODULES)


def test_a_tool_that_is_not_pinned_is_one_row_with_its_candidates_and_the_hint():
    out = js("""
      show(["en", "ru"].map((locale) => ({rows: rows(setup(), locale),
        status: say(locale, "hub.tool.state.not_pinned", {tool: "git"}),
        hint: say(locale, "hub.tool.restart_to_find")})));
    """)
    for said in out:
        [row] = said["rows"]
        assert row == {"tool": "git", "state": "not_pinned", "text": said["status"],
                       "hint": said["hint"],
                       "candidates": [{"id": CAND, "text": "Git\\cmd\\git.exe · 2.45.2"}]}


def test_a_settled_tool_has_no_row_even_when_candidates_are_listed_beside_it():
    out = js("""
      show({settled: rows(setup({git: git({state: "pinned", display: "Git\\\\cmd\\\\git.exe",
        version: "2.45.2"})})), none: rows({profile: "present", tools: {}})});
    """)
    assert out == {"settled": [], "none": []}


def test_each_unsettled_state_says_its_own_words_and_offers_candidates_without_the_hint():
    out = js("""
      const stated = (state, over = {}) => rows(setup({gh: gh({state: "pinned"}),
        git: git({state, display: "Git\\\\cmd\\\\git.exe", version: "2.40.0", ...over})}))[0];
      show({changed: stated("changed"), tooOld: stated("too_old"), unreadable: stated("unreadable"),
        words: ["changed", "too_old", "unreadable", "not_pinned"].map(
          (state) => say("en", `hub.tool.state.${state}`, {tool: "git"}))});
    """)
    changed, too_old, unreadable = out["changed"], out["tooOld"], out["unreadable"]
    for row, state, text in ((changed, "changed", out["words"][0]),
                             (too_old, "too_old", out["words"][1]),
                             (unreadable, "unreadable", out["words"][2])):
        assert (row["state"], row["text"], row["hint"]) == (state, text, None), state
        assert row["candidates"] == [{"id": CAND, "text": "Git\\cmd\\git.exe · 2.45.2"}], state
    assert len(set(out["words"])) == 4


def test_a_pin_file_that_cannot_be_read_offers_nothing_and_is_not_said_as_the_version():
    out = js("""
      const file = rows(setup({git: git({state: "unreadable", display: null,
        candidates: [cand()]})}));
      show({file, said: ["en", "ru"].map((locale) => [
        rows(setup({git: git({state: "unreadable", display: null})}), locale)[0].text,
        say(locale, "hub.tool.pin_problem.unreadable"),
        copy.codeWords(locale, "tool_version_unreadable")])});
    """)
    [row] = out["file"]
    assert (row["state"], row["candidates"], row["hint"]) == ("unreadable", [], None)
    for text, wanted, version in out["said"]:
        assert text == wanted and version not in text


def test_nothing_but_the_display_and_the_version_of_a_candidate_reaches_the_words():
    out = js("""
      const dirty = cand({path: "C:\\\\Secret\\\\git.exe", executable: "C:\\\\Secret\\\\git.exe",
        command: "git --version"});
      show(rows(setup({git: git({candidates: [dirty], path: "C:\\\\Secret\\\\git.exe"})})));
    """)
    [row] = out
    assert set(row) == {"tool", "state", "text", "hint", "candidates"}
    assert set(row["candidates"][0]) == {"id", "text"}
    assert "Secret" not in str(out) and "--version" not in str(out)


def test_a_candidate_whose_id_is_not_of_the_grammar_is_not_offered_and_the_rest_are():
    out = js("""
      const bad = ["cand-xyz", "cand-" + "A".repeat(32), "cand-" + "a".repeat(31),
        "cand-" + "a".repeat(33), "cand-" + "a".repeat(32) + "\\n", "a".repeat(32), 7, null];
      show({offered: rows(setup({git: git({candidates: [...bad.map((one) =>
        cand({candidate_id: one})), cand(), cand({candidate_id: "cand-" + "b".repeat(32)})]})}))[0]
        .candidates.map((one) => one.id)});
    """)
    assert out["offered"] == [CAND, "cand-" + "b" * 32]


def test_a_setup_the_page_cannot_read_has_no_rows():
    out = js("""
      show([null, 7, "x", [], {}, {tools: null}, {tools: []}, {tools: {git: null, gh: 7}},
        {tools: {git: {state: "nonsense", candidates: [cand()]}}},
        {tools: {git: {state: "not_pinned", candidates: "x"}}}].map((value) => rows(value).length));
    """)
    assert out == [0, 0, 0, 0, 0, 0, 0, 0, 0, 1], "a bad list of candidates is no candidates"


def test_a_press_is_told_by_what_the_hub_answered_and_a_file_problem_is_never_the_version():
    out = js("""
      const said = (answer) => tools.pinNotice(answer);
      show({accepted: said({status: "accepted", code: null, payload: {state: "pinned"}}),
        lost: said({status: "unknown", code: null, payload: null}),
        changed: ["git_changed", "gh_changed"].map((code) => said(refused(code))),
        old: said(refused("git_too_old")),
        files: ["corrupt", "unreadable", "unwritable"].map((reason) =>
          said(refused("tool_version_unreadable", {reason}))),
        version: [said(refused("tool_version_unreadable")),
          said(refused("tool_version_unreadable", {reason: "odd"})),
          said(refused("tool_version_unreadable", {reason: 7}))],
        other: ["candidate_not_found", "contract_invalid", "csrf_denied"].map(
          (code) => said(refused(code)))});
    """)
    assert out["accepted"] == {"key": "hub.tool.pinned", "code": None}
    assert out["lost"] == {"key": "hub.notice.unknown", "code": None}
    assert out["changed"] == [{"key": "hub.tool.pin_changed", "code": None}] * 2
    assert out["old"] == {"key": "hub.tool.pin_too_old", "code": None}
    assert [one["key"] for one in out["files"]] == [
        f"hub.tool.pin_problem.{reason}" for reason in FILE_REASONS]
    assert all(one == {"key": "hub.notice.refused", "code": "tool_version_unreadable"}
               for one in out["version"])
    assert out["other"] == [{"key": "hub.notice.refused", "code": code}
                            for code in ("candidate_not_found", "contract_invalid", "csrf_denied")]


def test_a_pin_refused_for_a_changed_tool_says_to_restart_the_hub_and_sends_no_second_press():
    # The hub looks for candidates once in its life and a refusal refreshes none (lane H's
    # handoff, section 4): the offer that follows is the same, so no word may promise another.
    out = js("""
      show({keys: ["git_changed", "gh_changed"].map((code) => tools.pinNotice(refused(code)).key),
        said: ["en", "ru"].map((locale) => say(locale, "hub.tool.pin_changed"))});
    """)
    assert out["keys"] == ["hub.tool.pin_changed"] * 2
    english, russian = (text.lower() for text in out["said"])
    assert "restart the hub" in english and "перезапустите hub" in russian
    for promise in ("pin", "check"):
        assert promise not in english, promise
    for promise in ("закреп", "проверьте"):
        assert promise not in russian, promise


def test_the_pin_file_reasons_are_the_three_the_hub_puts_on_a_refusal():
    held = set(service.PIN_FILE_REASONS.values())
    page = js("show(tools.PIN_FILE_REASONS);")
    assert set(page) == held == set(FILE_REASONS) and len(page) == 3
    said = js("""
      show(["en", "ru"].map((locale) => d.reasons.map((reason) => [
        say(locale, `hub.tool.pin_problem.${reason}`)])));
    """, reasons=list(FILE_REASONS))
    assert all("version" not in text.lower() and "верси" not in text.lower()
               for per in said for [text] in per)
