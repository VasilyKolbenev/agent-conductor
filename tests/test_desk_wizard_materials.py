"""The wizard model's step 2 ("Материалы"): git reading, material cards, limits, closing.

Same discipline as `test_desk_wizard_model.py`: the real module under Node, a state in
and a state out, the git answers taken from `tests/fixtures/wizard/` (spec 6.2.1 and 9.5).
"""
from __future__ import annotations

import pytest

from tests.desk_wizard_node import PRELUDE, fixture, run_js

GIT_STATES = ("repo", "unborn", "not_git", "not_repo_root", "unsupported", "unsafe_directory",
              "unavailable", "not_active")
DATA = {
    "git": {name: fixture("wizard", f"git_{name}.json") for name in GIT_STATES},
    "documents": fixture("wizard", "documents.json"),
    "truncated": fixture("wizard", "documents_truncated.json"),
    "document": fixture("wizard", "document.json"),
}
SPEC = "d-1f0a9c3e5b7d2468a1f0a9c3e5b7d246"
#: Helpers for a state that has read the project's documents and holds some cards.
CARDS = PRELUDE + """
const withDocuments = (state) => {
  const asked = wiz.stepWizard(state, {type: "material-add", kind: "project_doc"});
  return reply(asked.state, "documents", d.documents);
};
const addDoc = (state, docId = "d-1f0a9c3e5b7d2468a1f0a9c3e5b7d246") =>
  wiz.reduceWizard(state, {type: "material-add", kind: "project_doc", docId});
const note = (title = "Idea", content = "Some text.") => [
  {type: "material-add", kind: "note", title, content}];
const keys = (state) => state.materials.items.map((item) => item.key);
"""


def test_materials_body_has_exactly_the_closed_keys_of_each_kind():
    out = run_js(CARDS + """
      let state = opened();
      for (const kind of ["plan", "ideas", "scheme", "note"]) {
        state = run(state, {type: "material-add", kind, title: kind, content: `text of ${kind}`});
      }
      state = addDoc(withDocuments(state));
      state = run(state, {type: "material-mode", key: keys(state).at(-1), mode: "copy"});
      state = reply(state, "document", d.document, {subject: d.document.doc_id});
      const link = addDoc(withDocuments(opened()), "d-2e1b0d4f6c8e3579b2e1b0d4f6c8e357");
      const body = wiz.materialsBody(state, "en");
      show({top: Object.keys(body).sort(), lang: body.lang,
        kinds: body.items.map((item) => [item.kind, Object.keys(item).sort()]),
        link: wiz.materialsBody(link, "ru").items.map((item) => Object.keys(item).sort())});
    """, DATA)
    text = ["content", "kind", "title"]
    assert out["top"] == ["items", "lang"] and out["lang"] == "en"
    assert out["kinds"] == [["plan", text], ["ideas", text], ["scheme", text], ["note", text],
                            ["project_doc", ["content", "doc_id", "git_oid", "kind", "mode"]]]
    assert out["link"] == [["doc_id", "git_oid", "kind", "mode"]]


def test_no_wizard_body_carries_a_path_root_or_dir_key():
    out = run_js(CARDS + """
      const walk = (value, found = []) => {
        if (Array.isArray(value)) value.forEach((row) => walk(row, found));
        else if (value !== null && typeof value === "object") {
          for (const [key, row] of Object.entries(value)) { found.push(key); walk(row, found); }
        }
        return found;
      };
      let state = addDoc(withDocuments(opened()));
      state = run(state, {type: "material-mode", key: keys(state)[0], mode: "copy"}, ...note());
      const asks = wiz.wantedAsks(state);
      show({body: walk(wiz.materialsBody(state, "ru")),
        publications: walk(wiz.publications(state, "en")), asks: walk(asks),
        held_in_the_card: state.materials.items[0].path});
    """, DATA)
    for found in (out["body"], out["publications"], out["asks"]):
        assert found and not {"path", "root", "dir"} & set(found)
    assert out["held_in_the_card"] == "docs/spec.md", "the card shows the path; no body sends it"


def test_the_thirteenth_material_is_refused_and_the_twelfth_is_accepted():
    out = run_js(CARDS + """
      let state = opened();
      const counts = [];
      for (let at = 0; at < 13; at += 1) {
        state = run(state, ...note(`t${at}`, `c${at}`));
        counts.push([state.materials.items.length, state.materials.refusal]);
      }
      const freed = run(state, {type: "material-remove", key: keys(state)[0]});
      const again = run(freed, ...note("t13", "c13"));
      show({twelfth: counts[11], thirteenth: counts[12],
        after_removal: [freed.materials.items.length, freed.materials.refusal],
        after_add: [again.materials.items.length, again.materials.refusal]});
    """, DATA)
    assert out == {"twelfth": [12, None], "thirteenth": [12, "too_many_materials"],
                   "after_removal": [11, None], "after_add": [12, None]}


def test_a_document_over_the_byte_limit_is_flagged_and_the_hint_offers_a_link():
    out = run_js(CARDS + """
      const huge = "я".repeat(30000);
      const plain = run(opened(), ...note("Long", huge));
      let copy = addDoc(withDocuments(opened()));
      const key = keys(copy)[0];
      copy = run(copy, {type: "material-mode", key, mode: "copy"});
      copy = reply(copy, "document", {...d.document, content: huge}, {subject: d.document.doc_id});
      const linked = run(copy, {type: "material-mode", key, mode: "link"});
      show({plain: wiz.materialsEstimate(plain), plain_gate: wiz.canAdvance(plain).reason,
        copy: wiz.materialsEstimate(copy), copy_gate: wiz.canAdvance(copy).reason,
        linked: wiz.materialsEstimate(linked), linked_gate: wiz.canAdvance(linked).reason, key});
    """, DATA)
    assert out["plain"]["overBytes"] is True and out["plain"]["hint"] is None
    assert out["plain"]["bytes"] > 49152 and out["plain_gate"] == "materials_over_bytes"
    assert out["copy"]["overBytes"] is True and out["copy"]["hint"] == "make_link"
    assert out["copy"]["linkable"] == [out["key"]]
    assert out["copy_gate"] == "materials_over_bytes"
    assert out["linked"]["overBytes"] is False and out["linked"]["hint"] is None
    assert out["linked_gate"] is None


def test_a_project_document_as_a_link_carries_no_text_and_as_a_copy_carries_its_text():
    out = run_js(CARDS + """
      const first = addDoc(withDocuments(opened()));
      const key = keys(first)[0];
      const item = (state) => wiz.materialsBody(state, "en").items[0];
      const asked = wiz.stepWizard(first, {type: "material-mode", key, mode: "copy"});
      const waiting = {gate: wiz.canAdvance(asked.state).reason, body: item(asked.state)};
      const filled = reply(asked.state, "document", d.document, {subject: d.document.doc_id});
      const back = wiz.stepWizard(filled, {type: "material-mode", key, mode: "link"});
      const again = wiz.stepWizard(back.state, {type: "material-mode", key, mode: "copy"});
      show({link: item(first), link_card: first.materials.items[0].content,
        asks: asked.asks.map((ask) => [ask.name, ask.door, ask.target, ask.subject, ask.body]),
        waiting, copy: item(filled), gate_with_text: wiz.canAdvance(filled).reason,
        relinked: item(back.state), no_new_ask: again.asks.length,
        text_kept: item(again.state).content});
    """, DATA)
    oid = "1111111111111111111111111111111111111111"
    assert out["link"] == {"kind": "project_doc", "doc_id": SPEC, "git_oid": oid, "mode": "link"}
    assert out["link_card"] == ""
    assert out["asks"] == [["document", "read", "document", SPEC, None]]
    assert out["waiting"]["gate"] == "material_incomplete"
    assert out["copy"] == {"kind": "project_doc", "doc_id": SPEC, "git_oid": oid,
                           "mode": "copy", "content": DATA["document"]["content"]}
    assert out["gate_with_text"] is None
    assert out["relinked"] == out["link"]
    assert out["no_new_ask"] == 0 and out["text_kept"] == DATA["document"]["content"]


@pytest.mark.parametrize("refusal", [
    {"status": "refused", "code": "document_not_text"},
    {"status": "refused", "code": "materials_refused",
     "payload": {"detail": {"reason": "document_not_text"}}},
])
def test_a_document_the_server_calls_not_text_cannot_be_taken_as_a_copy(refusal):
    out = run_js(CARDS + """
      const first = addDoc(withDocuments(opened()));
      const key = keys(first)[0];
      const asked = wiz.stepWizard(first, {type: "material-mode", key, mode: "copy"});
      const refused = reply(asked.state, "document", d.refusal.payload,
        {subject: d.document.doc_id, status: d.refusal.status, code: d.refusal.code});
      const retry = wiz.stepWizard(refused, {type: "material-mode", key, mode: "copy"});
      show({mode: refused.materials.items[0].mode, blocked: refused.materials.items[0].blocked,
        retry_mode: retry.state.materials.items[0].mode, retry_asks: retry.asks.length,
        retry_refusal: retry.state.materials.refusal});
    """, {**DATA, "refusal": refusal})
    assert out == {"mode": "link", "blocked": "document_not_text", "retry_mode": "link",
                   "retry_asks": 0, "retry_refusal": "document_not_text"}


def test_git_reading_names_each_of_the_eight_states_with_its_text_and_exit():
    out = run_js(CARDS + """
      const reading = (name) => wiz.gitReading(reply(opened(), "git", d.git[name]));
      show(Object.fromEntries(Object.keys(d.git).map((name) => [name, reading(name)])));
    """, DATA)
    none = {"params": {}, "blocks": False, "stop": None, "command": None, "exits": []}
    assert out == {
        "repo": {**none, "state": "repo", "sentence": "repo",
                 "params": {"ref": "main", "commit": "abc1234", "dirty": 3}},
        "unborn": {**none, "state": "unborn", "sentence": "unborn", "exits": ["first_commit"]},
        "not_git": {**none, "state": "not_git", "sentence": "not_git",
                    "exits": ["connect_git", "run_without_git"]},
        "not_repo_root": {**none, "state": "not_repo_root", "sentence": "not_repo_root",
                          "blocks": True, "stop": "git_stops"},
        "unsupported": {**none, "state": "unsupported", "sentence": "unsupported",
                        "params": {"names": ["work"]}, "blocks": True, "stop": "git_stops"},
        "unsafe_directory": {**none, "state": "unsafe_directory",
                             "sentence": "unsafe_directory", "command": "safe_directory"},
        "unavailable": {**none, "state": "unavailable", "sentence": "unavailable",
                        "command": "pin_git"},
        "not_active": {**none, "state": "not_active", "sentence": "not_active",
                       "exits": ["connect_git"]},
    }


def test_git_reading_says_it_is_reading_or_could_not_read_and_never_guesses_a_state():
    out = run_js(CARDS + """
      const failed = reply(opened(), "git", null, {status: "refused", code: "store_error"});
      const lost = reply(opened(), "git", null, {status: "unknown"});
      const shown = (state) => {
        const facts = wiz.gitReading(state);
        return [facts.state, facts.sentence, facts.exits, facts.blocks];
      };
      show({not_yet_asked: shown(started()), reading: shown(opened()), failed: shown(failed),
        lost: shown(lost), code: failed.reads.git.code});
    """, DATA)
    assert out["not_yet_asked"] == ["reading", "reading", [], False]
    assert out["reading"] == ["reading", "reading", [], False]
    assert out["failed"] == ["failed", "failed", ["reread"], False]
    assert out["lost"] == ["failed", "failed", ["reread"], False]
    assert out["code"] == "store_error"


@pytest.mark.parametrize("mode", ["normal", "starter", "view"])
def test_not_repo_root_and_unsupported_stop_the_wizard_in_every_mode(mode):
    out = run_js(CARDS + """
      const state = (name) => {
        const base = d.mode === "starter"
          ? run(open({starterId: "desk-starter-docs"}), {type: "edit-title", value: "Notes"},
              {type: "edit-idea", value: "An app."}, {type: "next"})
          : started({viewMode: d.mode === "view"});
        return reply(opened(base), "git", d.git[name]);
      };
      const gate = (name) => wiz.canAdvance(state(name)).reason;
      show({root: gate("not_repo_root"), unsupported: gate("unsupported"),
        blocks: [wiz.gitReading(state("not_repo_root")).blocks,
          wiz.gitReading(state("unsupported")).blocks]});
    """, {**DATA, "mode": mode})
    assert out == {"root": "git_stops", "unsupported": "git_stops", "blocks": [True, True]}


def test_starter_mode_without_git_stops_and_offers_only_connect_git():
    out = run_js(CARDS + """
      const starter = () => run(open({starterId: "desk-starter-docs"}),
        {type: "edit-title", value: "Notes"}, {type: "edit-idea", value: "An app."},
        {type: "next"});
      const at = (name, base = starter()) => reply(opened(base), "git", d.git[name]);
      const view = run(open({starterId: "desk-starter-docs", viewMode: true}),
        {type: "edit-title", value: "Notes"}, {type: "edit-idea", value: "An app."},
        {type: "next"});
      const facts = (state) => {
        const row = wiz.gitReading(state);
        return [row.exits, row.blocks, wiz.canAdvance(state).reason];
      };
      show({not_git: facts(at("not_git")), unborn: facts(at("unborn")),
        repo: facts(at("repo")), reading: facts(opened(starter())),
        normal_not_git: facts(reply(opened(), "git", d.git.not_git)),
        in_view: facts(reply(opened(view), "git", d.git.not_active)),
        in_view_without_git: facts(reply(opened(view), "git", d.git.not_git))});
    """, DATA)
    assert out["not_git"] == [["connect_git"], True, "starter_needs_git"]
    assert out["unborn"] == [["first_commit"], True, "starter_needs_git"]
    assert out["repo"] == [[], False, None]
    assert out["reading"] == [[], True, "starter_needs_git"]
    assert out["normal_not_git"] == [["connect_git", "run_without_git"], False, None]
    assert out["in_view"] == [["connect_git"], False, None]
    assert out["in_view_without_git"][1:] == [False, None]


def test_in_view_mode_git_reads_not_active_and_the_project_document_kind_is_unavailable():
    out = run_js(CARDS + """
      const view = opened(started({viewMode: true}));
      const active = opened();
      const picked = wiz.stepWizard(view, {type: "material-add", kind: "project_doc"});
      const plan = run(view, ...note("Plan", "Steps."));
      show({before_any_answer: wiz.gitReading(view).state, kinds: wiz.availableKinds(view),
        active_kinds: wiz.availableKinds(active), picker_ignored: picked.state === view,
        asks: picked.asks.length, documents_asked: wiz.wantedAsks(view).some(
          (ask) => ask.name === "documents"), others_work: plan.materials.items.length});
    """, DATA)
    assert out["before_any_answer"] == "not_active"
    assert out["kinds"] == ["plan", "ideas", "scheme", "note"]
    assert out["active_kinds"] == ["plan", "ideas", "scheme", "note", "project_doc"]
    assert out["picker_ignored"] is True and out["asks"] == 0
    assert out["documents_asked"] is False and out["others_work"] == 1


def test_the_project_instructions_row_needs_found_files_and_defaults_to_the_last_seeds_choice():
    out = run_js(CARDS + """
      const row = (name, edit) => {
        const git = structuredClone(d.git[name]);
        if (edit) edit(git.git);
        return wiz.agentInstructionsRow(reply(opened(), "git", git));
      };
      const found = reply(opened(), "git", d.git.repo);
      const toggled = run(found, {type: "include-instructions", value: true});
      const back = run(toggled, {type: "include-instructions", value: false});
      show({found: wiz.agentInstructionsRow(found), toggled: wiz.agentInstructionsRow(toggled),
        back: wiz.agentInstructionsRow(back),
        seed_said_include: row("repo", (git) => { git.agent_instructions.default_include = true; }),
        none_found: row("unborn"), in_view: row("not_active"),
        unread: wiz.agentInstructionsRow(opened()),
        bad_value_ignored: run(found, {type: "include-instructions", value: "yes"}) === found});
    """, DATA)
    assert out["found"] == {"found": 4, "include": False, "default": False}
    assert out["toggled"] == {"found": 4, "include": True, "default": False}
    assert out["back"] == {"found": 4, "include": False, "default": False}
    assert out["seed_said_include"] == {"found": 4, "include": True, "default": True}
    assert out["none_found"] is None and out["in_view"] is None and out["unread"] is None
    assert out["bad_value_ignored"] is True


def test_starter_documents_material_is_marked_as_the_owners_edit():
    out = run_js(CARDS + """
      const from = run(opened(), {type: "material-add", kind: "note", source: "starter_docs",
        title: "Plan", content: "# Plan"}, ...note("Mine", "My text."));
      const items = (lang) => wiz.materialsBody(from, lang).items.map((item) => item.title);
      show({ru: items("ru"), en: items("en"),
        sources: from.materials.items.map((item) => item.source)});
    """, DATA)
    assert out["ru"] == ["Plan · из стартовых документов · правка владельца", "Mine"]
    assert out["en"] == ["Plan · from the starter documents · owner's edit", "Mine"]
    assert out["sources"] == ["starter_docs", None]


def test_the_document_picker_asks_for_the_list_once_lists_what_is_left_and_refuses_a_repeat():
    out = run_js(CARDS + """
      const asked = wiz.stepWizard(opened(), {type: "material-add", kind: "project_doc"});
      const twice = wiz.stepWizard(asked.state, {type: "material-add", kind: "project_doc"});
      const read = reply(asked.state, "documents", d.documents);
      const added = addDoc(read);
      const repeated = addDoc(added);
      const truncated = reply(asked.state, "documents", d.truncated);
      const failed = reply(asked.state, "documents", null,
        {status: "refused", code: "store_error"});
      const stranger = wiz.reduceWizard(read, {type: "material-add", kind: "project_doc",
        docId: "d-00000000000000000000000000000000"});
      const rows = (state) => wiz.documentPicker(state);
      show({asks: asked.asks.map((ask) => [ask.id, ask.target]), twice: twice.asks.length,
        before: rows(asked.state).status, listed: rows(read).documents.map((row) => row.path),
        open_after_add: rows(added).open, added_flag: rows(added).documents.map((row) => row.added),
        refusal: repeated.materials.refusal, count: repeated.materials.items.length,
        truncated: rows(truncated).truncated, failed: rows(failed).status,
        reask: wiz.stepWizard(failed, {type: "reread", name: "documents"}).asks
          .map((ask) => ask.id),
        stranger: [stranger.materials.items.length, stranger.materials.refusal]});
    """, DATA)
    assert out["asks"] == [["read:documents", "documents"]] and out["twice"] == 0
    assert out["before"] == "reading"
    assert out["listed"] == ["docs/spec.md", "README.md", "notes/todo.txt"]
    assert out["open_after_add"] is False and out["added_flag"] == [True, False, False]
    assert (out["refusal"], out["count"]) == ("already_added", 1)
    assert out["truncated"] is True and out["failed"] == "failed"
    assert out["reask"] == ["read:documents"]
    assert out["stranger"] == [0, "doc_unknown"]


def test_the_document_picker_closes_without_adding_anything_and_asks_nothing_more():
    out = run_js(CARDS + """
      const picked = wiz.stepWizard(opened(), {type: "material-add", kind: "project_doc"});
      const closed = wiz.stepWizard(picked.state, {type: "picker-close"});
      const twice = wiz.stepWizard(closed.state, {type: "picker-close"});
      show({open: [wiz.documentPicker(picked.state).open, wiz.documentPicker(closed.state).open],
        items: closed.state.materials.items.length, asks: closed.asks.length,
        twice_same: twice.state === closed.state});
    """, DATA)
    assert out == {"open": [True, False], "items": 0, "asks": 0, "twice_same": True}


def test_the_materials_step_is_complete_only_with_finished_cards_within_the_limits():
    out = run_js(CARDS + """
      const base = opened();
      const gate = (...events) => wiz.canAdvance(run(base, ...events)).reason;
      show({none: gate(), blank_content: gate({type: "material-add", kind: "plan", title: "P"}),
        blank_title: gate({type: "material-add", kind: "plan", content: "x"}),
        finished: gate(...note()), scheme: gate({type: "material-add", kind: "scheme",
          title: "Flow", content: "flowchart TD"}),
        edited: gate({type: "material-add", kind: "note"},
          {type: "material-edit", key: "m1", field: "title", value: "T"},
          {type: "material-edit", key: "m1", field: "content", value: "C"}),
        unknown_key_ignored: wiz.reduceWizard(base,
          {type: "material-edit", key: "zz", field: "title", value: "T"}) === base,
        unknown_kind_ignored: wiz.reduceWizard(base,
          {type: "material-add", kind: "diary", title: "T", content: "C"}) === base});
    """, DATA)
    assert out["none"] is None and out["blank_content"] == "material_incomplete"
    assert out["blank_title"] == "material_incomplete" and out["finished"] is None
    assert out["scheme"] is None and out["edited"] is None
    assert out["unknown_key_ignored"] is True and out["unknown_kind_ignored"] is True


def test_closing_with_materials_asks_for_confirmation_and_keeping_them_cancels_the_close():
    out = run_js(CARDS + """
      const empty = opened();
      const held = run(empty, ...note());
      const asked = wiz.reduceWizard(held, {type: "close-request"});
      const kept = wiz.reduceWizard(asked, {type: "close-cancel"});
      show({empty_warns: wiz.closeNeedsWarning(empty), held_warns: wiz.closeNeedsWarning(held),
        empty_request_same: wiz.reduceWizard(empty, {type: "close-request"}) === empty,
        closing: [asked.closing, kept.closing],
        items_kept: kept.materials.items.length,
        cancel_when_not_closing_same: wiz.reduceWizard(held, {type: "close-cancel"}) === held});
    """, DATA)
    assert out == {"empty_warns": False, "held_warns": True, "empty_request_same": True,
                   "closing": ["confirm", None], "items_kept": 1,
                   "cancel_when_not_closing_same": True}


def test_materials_publish_the_composed_body_and_a_seed_request_that_waits_for_a_later_slice():
    out = run_js(CARDS + """
      const state = run(opened(), ...note("Idea", "Try X."));
      const rows = wiz.publications(state, "en");
      show({steps: rows.map((row) => row.step), materials: rows[1]});
    """, DATA)
    assert out["steps"] == ["task", "materials"]
    assert out["materials"] == {"step": "materials", "writes": [
        {"link": 2, "target": "seed", "later": True},
        {"link": 5, "target": "materials", "ref": "artifact-materials",
         "body": {"lang": "en", "items": [{"kind": "note", "title": "Idea",
                                           "content": "Try X."}]}}]}
