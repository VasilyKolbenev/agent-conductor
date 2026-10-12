"""What a press of the git block does to the wizard's state, one press and one request.

The seam (`desk-wizard-git-run.js`) is driven under Node with the real model underneath it: a
wizard is opened, the git read is answered from a stand-in, a press is made, its ask is read, and
the answer is landed. Nothing here is a browser; what is drawn is in
`browser_tests/test_desk_wizard_git*.py`. The rules this file holds: a press during a request
changes nothing (one press, one request); the confirm waits behind the switch; the continue is
built from the stored terms and the actor of now; a lost answer is read and never repeated; a
refusal is the route's closed word; the git read is the only thing the desk asks again by itself;
and a preview and its digest survive an unknown answer.
"""
from __future__ import annotations

from typing import Any

from tests.desk_wizard_node import fixture, run_js

MODULES = {"wiz": "desk-wizard-model.js", "run": "desk-wizard-git-run.js",
           "g": "desk-wizard-git.js"}
PENDING = ("unfinished", "unfinished_unborn", "empty", "signature", "signature_sha256",
           "damaged")


def _read(name: str) -> Any:
    return fixture("wizard", f"{name}.json")["git"]


DATA: dict[str, Any] = {
    "reads": {"unborn": _read("git_unborn"), "repo": _read("git_repo"),
              "not_git": _read("git_not_git"), "not_active": _read("git_not_active"),
              "unsafe": _read("git_unsafe_directory"),
              **{f"pending_{name}": _read(f"git_pending_{name}") for name in PENDING}},
    "preview": fixture("wizard", "setup_preview_snapshot.json"),
    "preview_empty": fixture("wizard", "setup_preview_empty.json"),
    "receipt": fixture("wizard", "setup_receipt_commit.json"),
    "init": fixture("wizard", "setup_receipt_init.json"),
}
#: A wizard on step 1 that has answered its git read; `drive` routes a git event to the seam's own
#: table and any other event to the model; `land` answers the press in flight; `fresh` is what the
#: model would ask now that was not asked before.
PRELUDE = """
const show = (value) => console.log(JSON.stringify(value));
const ok = (payload) => ({status: "accepted", code: null, payload});
const refused = (code, payload = null) => ({status: "refused", code, payload});
const reasonOf = (reason) => refused("git_setup_refused", {error: {code: "git_setup_refused",
  message: "x", detail: {reason}}});
const copy = (value) => JSON.parse(JSON.stringify(value));
const opened = (over = {}, name = "unborn", door = true) => {
  const first = wiz.stepWizard(wiz.initialWizard({starterId: null, viewMode: false,
    newTaskId: "task-t1", nonce: "n0nce0001", actor: "Anna", ...over}), {type: "open"}).state;
  const ask = wiz.wantedAsks(first).find((one) => one.name === "git");
  const read = wiz.reduceWizard(first, {type: "answered", ask,
    result: ok({git: d.reads[name]})});
  return {...read, git: g.initialGit(door)};
};
const drive = (state, ...events) => events.reduce((now, event) =>
  (Object.hasOwn(run.GIT_HANDLERS, event.type) ? run.GIT_HANDLERS[event.type](now, event)
    : wiz.reduceWizard(now, event)), state);
const land = (state, result) => run.landGit(state, state.git.sending.ask, result);
const fresh = (state) => {
  const seen = new Set();
  return [...wiz.wantedAsks(state), ...run.gitWanted(state)].filter((ask) =>
    !state.asked.includes(ask.id) && !seen.has(ask.id) && seen.add(ask.id));
};
const withRead = (state, name) => {
  const gone = fresh(state).find((ask) => ask.name === "git");
  const handed = {...state, asked: [...state.asked, gone.id]};
  return wiz.reduceWizard(handed, {type: "answered", ask: gone,
    result: ok({git: d.reads[name]})});
};
const ready = (over = {}, name = "unborn") => drive(opened(over, name),
  {type: "git-start"}, {type: "git-preview"});
const previewed = (over = {}, mode = null) => {
  let state = opened(over, "unborn", true);
  state = drive(state, {type: "git-start"});
  if (mode !== null) state = drive(state, {type: "git-mode", mode});
  state = drive(state, {type: "git-preview"});
  return land(state, ok(mode === "empty" || over.starterId ? d.preview_empty : d.preview));
};
"""


def js(body: str) -> Any:
    return run_js(PRELUDE + body, DATA, modules=MODULES)


def test_a_press_while_a_request_is_in_flight_changes_nothing_and_asks_nothing():
    out = js("""
      const busy = previewed();
      const sending = drive(busy, {type: "git-confirm"});
      const rows = ["git-start", "git-mode", "git-list", "git-preview", "git-init", "git-exclude",
        "git-confirm", "git-continue"].map((type) => {
        const after = drive(sending, {type, mode: "empty"});
        return [type, after === sending, fresh(after).length];
      });
      show({sendingKind: sending.git.sending.kind, rows,
        onlyOneAsk: fresh(sending).map((ask) => ask.id)});
    """)
    assert out["sendingKind"] == "confirm"
    assert out["rows"] == [[name, True, 1] for name in (
        "git-start", "git-mode", "git-list", "git-preview", "git-init", "git-exclude",
        "git-confirm", "git-continue")], "the one ask in flight is the only thing wanted"
    assert out["onlyOneAsk"] == ["write:git:confirm:2"]


def test_an_ask_names_its_press_so_a_second_press_never_reuses_a_first_ones_id():
    out = js("""
      let state = previewed();
      const ids = [];
      state = drive(state, {type: "git-preview"}); ids.push(state.git.sending.ask.id);
      state = land(state, ok(d.preview));
      state = drive(state, {type: "git-preview"}); ids.push(state.git.sending.ask.id);
      show({ids, seq: state.git.seq});
    """)
    assert out["ids"] == ["write:git:preview:2", "write:git:preview:3"] and out["seq"] == 3


def test_with_the_switch_closed_no_event_in_any_state_makes_a_confirm_ask():
    out = js("""
      const events = [{type: "git-confirm"}, {type: "git-continue"}];
      const states = {};
      for (const name of Object.keys(d.reads)) {
        let state = opened({}, name, false);
        state = drive(state, {type: "git-start"});
        const after = drive(state, ...events);
        states[name] = [after.git.sending === null, fresh(after).filter(
          (ask) => ask.name === "git_confirm").length];
      }
      const closed = previewed({}, null);
      const shut = {...closed, git: {...closed.git, open: false}};
      show({states, blocks: [run.pressBlock(shut, "confirm"), run.pressBlock(shut, "continue")]});
    """)
    assert all(row == [True, 0] for row in out["states"].values()), out["states"]
    assert out["blocks"] == ["confirm_door_closed", "confirm_door_closed"]


def test_with_the_door_open_the_confirm_ask_has_the_four_keys_and_the_previewed_digest():
    out = js("""
      const state = drive(previewed(), {type: "git-confirm"});
      const ask = state.git.sending.ask;
      show({ask, wanted: fresh(state).map((one) => one.id), blocked: run.pressBlock(state,
        "confirm")});
    """)
    ask = out["ask"]
    assert (ask["id"], ask["name"], ask["door"], ask["target"], ask["subject"]) == (
        "write:git:confirm:2", "git_confirm", "write", "gitSetup", None)
    assert ask["body"] == {"step": "first_commit", "mode": "snapshot", "actor": "Anna",
                           "paths_digest": DATA["preview"]["setup"]["paths_digest"]}
    assert out["wanted"] == ["write:git:confirm:2"] and out["blocked"] == "busy"


def test_an_empty_first_commit_is_confirmed_with_a_null_digest_after_its_own_preview():
    out = js("""
      const state = drive(previewed({}, "empty"), {type: "git-confirm"});
      show({body: state.git.sending.ask.body, preview: state.git.preview.paths_digest});
    """)
    assert out["body"] == {"step": "first_commit", "mode": "empty", "actor": "Anna",
                           "paths_digest": None}
    assert out["preview"].startswith("sha256:"), "the preview of an empty one keeps its digest"


def test_a_confirm_needs_a_preview_made_for_the_mode_chosen_now():
    out = js("""
      const start = drive(opened(), {type: "git-start"});
      const none = run.pressBlock(start, "confirm");
      const have = previewed();
      const switched = drive(have, {type: "git-mode", mode: "empty"});
      show({none, switchedBlock: run.pressBlock(switched, "confirm"),
        previewGone: switched.git.preview === null, back: drive(switched, {type: "git-mode",
        mode: "snapshot"}).git.preview, haveBlock: run.pressBlock(have, "confirm"),
        sameMode: drive(have, {type: "git-mode", mode: "snapshot"}) === have});
    """)
    assert out["none"] == "preview_missing" and out["switchedBlock"] == "preview_missing"
    assert out["previewGone"] is True and out["back"] is None
    assert out["haveBlock"] is None and out["sameMode"] is True


def test_the_starter_makes_only_an_empty_first_commit_and_never_offers_a_snapshot():
    out = js("""
      const start = drive(opened({starterId: "desk-starter-docs"}), {type: "git-start"});
      const wants = drive(start, {type: "git-mode", mode: "snapshot"});
      const normal = drive(opened(), {type: "git-start"});
      show({mode: start.git.mode, kept: wants === start, normal: normal.git.mode,
        facts: run.firstFacts(start).modes, normalModes: run.firstFacts(normal).modes});
    """)
    assert out["mode"] == "empty" and out["kept"] is True and out["normal"] == "snapshot"
    assert out["facts"] == ["empty"] and out["normalModes"] == ["snapshot", "empty"]


def test_the_continue_is_built_from_the_stored_terms_and_the_actor_of_now():
    out = js("""
      const state = opened({actor: "Anna"}, "pending_unfinished");
      const sent = drive(state, {type: "git-continue"});
      const empty = drive(opened({actor: "Anna"}, "pending_empty"), {type: "git-continue"});
      const ask = sent.git.sending.ask;
      show({body: ask.body, name: ask.name, id: ask.id, kind: sent.git.sending.kind,
        empty: empty.git.sending.ask.body, requestedBy: d.reads.pending_unfinished
          .first_commit_pending.terms.requested_by,
        previews: fresh(sent).filter((one) => one.name === "git_preview").length});
    """)
    stored = DATA["reads"]["pending_unfinished"]["first_commit_pending"]["terms"]
    assert out["body"] == {"step": "first_commit", "mode": "snapshot", "actor": "Anna",
                           "paths_digest": stored["paths_digest"]}
    assert out["requestedBy"] == "Owner" and out["body"]["actor"] != out["requestedBy"]
    assert (out["name"], out["id"], out["kind"]) == ("git_confirm", "write:git:continue:1",
                                                     "continue")
    assert out["empty"]["paths_digest"] is None and out["empty"]["mode"] == "empty"
    assert out["previews"] == 0, "a continue never demands a new preview"


def test_a_wait_for_a_signature_is_continued_by_the_same_body_and_shows_its_commands():
    out = js("""
      const state = opened({actor: "Anna"}, "pending_signature_sha256");
      const facts = run.firstFacts(state);
      const sent = drive(state, {type: "git-continue"});
      show({pending: facts.pending.state, commands: facts.commands, shown: facts.shown,
        body: sent.git.sending.ask.body, block: facts.blocks.continue});
    """)
    assert out["pending"] == "awaiting_signature" and out["shown"]["continue"] is True
    assert out["commands"]["update"].endswith(" " + "0" * 64)
    assert out["body"]["step"] == "first_commit" and out["body"]["actor"] == "Anna"
    assert out["block"] is None


def test_a_damaged_record_offers_no_continue_and_an_unreadable_one_neither():
    out = js("""
      const damaged = opened({}, "pending_damaged");
      const odd = copy(d.reads.unborn); odd.first_commit_pending = {state: "torn"};
      d.reads.odd = odd;
      const unreadable = opened({}, "odd");
      const rows = [damaged, unreadable].map((state) => {
        const facts = run.firstFacts(state);
        return [facts.pending.state, facts.shown.pending, facts.shown.continue,
          facts.blocks.continue, drive(state, {type: "git-continue"}) === state];
      });
      show(rows);
    """)
    assert out == [["damaged", True, False, "not_offered", True],
                   ["unreadable", True, False, "not_offered", True]]


def test_a_lost_answer_drops_the_git_read_and_asks_for_it_again_and_nothing_else():
    out = js("""
      const sent = drive(previewed(), {type: "git-confirm"});
      const lost = land(sent, {status: "unknown"});
      const wants = fresh(lost).map((ask) => [ask.id, ask.name]);
      show({readDropped: lost.reads.git === undefined, wants, sending: lost.git.sending,
        previewKept: lost.git.preview !== null, digest: lost.git.preview.paths_digest,
        result: [lost.git.result.status, lost.git.result.kind]});
    """)
    assert out["readDropped"] is True and out["sending"] is None
    assert out["wants"] == [["read:git", "git"]], "the read is the only thing asked again"
    assert out["previewKept"] is True, "an unknown answer does not demand a new preview"
    assert out["digest"] == DATA["preview"]["setup"]["paths_digest"]
    assert out["result"] == ["lost", "confirm"]


def test_every_answer_the_desk_did_not_read_is_lost_and_the_body_is_never_resent():
    out = js("""
      const kinds = [
        ["confirm", () => drive(previewed(), {type: "git-confirm"})],
        ["continue", () => drive(opened({}, "pending_unfinished"), {type: "git-continue"})],
        ["init", () => drive(opened({}, "not_git"), {type: "git-init"})],
        ["exclude", () => drive(opened({}, "exclude"), {type: "git-exclude"})]];
      d.reads.exclude = {...copy(d.reads.repo), exclude: "deferred"};
      const answers = [{status: "unknown"}, refused("store_error"), refused("csrf_denied"),
        refused("same_origin_denied"), refused("made_up"), reasonOf("not_a_reason"),
        ok({stray: 1}), ok(null)];
      const rows = [];
      for (const [kind, make] of kinds) {
        for (const result of answers) {
          const sent = make();
          const lost = land(sent, result);
          const posts = fresh(lost).filter((ask) => ask.door === "write").length;
          rows.push([kind, lost.git.result.status, lost.reads.git === undefined, posts,
            lost.git.sending]);
        }
      }
      show(rows);
    """)
    assert len(out) == 32
    assert all(row[1:] == ["lost", True, 0, None] for row in out), out


def test_the_read_after_a_lost_confirm_decides_between_pending_done_and_not_recorded():
    out = js("""
      const lost = land(drive(previewed(), {type: "git-confirm"}), {status: "unknown"});
      const verdict = (name) => run.firstFacts(withRead(lost, name)).result.verdict;
      const again = withRead(lost, "unborn");
      const facts = run.firstFacts(again);
      show({pending: verdict("pending_unfinished"), done: verdict("repo"),
        none: verdict("unborn"), awaiting: verdict("pending_signature"),
        other: verdict("not_git"), reading: run.firstFacts(lost).result.verdict,
        confirmAgain: facts.blocks.confirm, previewHeld: facts.preview !== null,
        shownConfirm: facts.shown.panel});
    """)
    assert out["pending"] == "wizard.first.lost.pending"
    assert out["done"] == "wizard.first.lost.done"
    assert out["none"] == "wizard.first.lost.none"
    assert out["awaiting"] == "wizard.first.lost.pending"
    assert out["other"] == "wizard.first.lost.other"
    assert out["reading"] == "wizard.first.lost.reading"
    assert out["confirmAgain"] is None and out["previewHeld"] is True
    assert out["shownConfirm"] is True, "the same confirm can be pressed again, on purpose"


def test_a_lost_connect_or_exclusion_is_read_back_the_same_way():
    out = js("""
      d.reads.exclude = {...copy(d.reads.repo), exclude: "deferred"};
      d.reads.excluded = {...copy(d.reads.repo), exclude: "written"};
      const init = land(drive(opened({}, "not_git"), {type: "git-init"}), {status: "unknown"});
      const exclude = land(drive(opened({}, "exclude"), {type: "git-exclude"}),
        {status: "unknown"});
      const verdict = (state, name) => run.firstFacts(withRead(state, name)).result.verdict;
      show({initDone: verdict(init, "unborn"), initRepo: verdict(init, "repo"),
        initNone: verdict(init, "not_git"), excludeDone: verdict(exclude, "excluded"),
        excludeNone: verdict(exclude, "exclude")});
    """)
    assert out == {"initDone": "wizard.first.lost.done", "initRepo": "wizard.first.lost.done",
                   "initNone": "wizard.first.lost.none",
                   "excludeDone": "wizard.first.lost.done",
                   "excludeNone": "wizard.first.lost.none"}


def test_a_lost_preview_needs_no_read_to_be_told_that_nothing_was_written():
    out = js("""
      const lost = land(ready(), {status: "unknown"});
      const facts = run.firstFacts(lost);
      show({verdict: facts.result.verdict, readStands: lost.reads.git !== undefined,
        wants: fresh(lost).map((ask) => ask.id), block: facts.blocks.preview});
    """)
    assert out["verdict"] == "wizard.first.lost.nothing_written"
    assert out["readStands"] is False, "the read is asked again after a lost preview too"
    assert out["wants"] == ["read:git"]


def test_the_exact_receipt_is_done_the_preview_is_spent_and_the_branch_shown_is_the_receipts():
    out = js("""
      const sent = drive(previewed(), {type: "git-confirm"});
      const receipt = copy(d.receipt); receipt.setup.target_ref = "refs/heads/other";
      const done = land(sent, ok(receipt));
      const facts = run.firstFacts(done);
      show({status: done.git.result.status, branch: done.git.result.receipt.target_ref,
        preview: done.git.preview, readDropped: done.reads.git === undefined,
        signature: done.git.result.receipt.signature, wants: fresh(done).map((ask) => ask.id),
        facts: [facts.result.status, facts.result.kind]});
    """)
    assert out["status"] == "done" and out["branch"] == "refs/heads/other"
    assert out["preview"] is None and out["readDropped"] is True
    assert out["wants"] == ["read:git"] and out["facts"] == ["done", "confirm"]


def test_a_landed_preview_is_kept_validated_and_asks_nothing_again():
    out = js("""
      const sent = ready();
      const done = land(sent, ok(d.preview));
      show({kind: sent.git.sending.kind, stands: done.git.preview !== null,
        result: done.git.result, readKept: done.reads.git !== undefined,
        wants: fresh(done).length, stale: done.git.preview.files.length});
    """)
    assert out["kind"] == "preview" and out["stands"] is True and out["result"] is None
    assert out["readKept"] is True and out["wants"] == 0 and out["stale"] == 4


def test_a_preview_for_another_mode_than_the_one_asked_is_lost_and_not_kept():
    out = js("""
      const sent = ready();
      const done = land(sent, ok(d.preview_empty));
      show({status: done.git.result.status, preview: done.git.preview});
    """)
    assert out == {"status": "lost", "preview": None}


def test_a_refusal_that_asks_for_a_new_preview_drops_the_old_one_and_the_confirm_waits_for_it():
    out = js("""
      const rows = ["paths_changed", "signing_ref_unsupported"].map((reason) => {
        const sent = drive(previewed(), {type: "git-confirm"});
        const refusedNow = land(sent, reasonOf(reason));
        const facts = run.firstFacts(withRead(refusedNow, "unborn"));
        return [reason, refusedNow.git.preview, facts.blocks.confirm, facts.result.action,
          facts.result.notice, facts.result.next, fresh(refusedNow).map((ask) => ask.id)];
      });
      show(rows);
    """)
    for reason, preview, block, action, notice, nxt, wants in out:
        assert preview is None and block == "preview_missing", reason
        assert action == "new_preview" and wants == ["read:git"], reason
        assert notice == f"git_setup.reason.{reason}"
        assert nxt == f"wizard.first.next.{reason}"
    assert [row[0] for row in out] == ["paths_changed", "signing_ref_unsupported"]


def test_a_locked_index_offers_the_same_press_again_and_asks_only_the_git_read_again():
    out = js("""
      const sent = drive(previewed(), {type: "git-confirm"});
      const locked = land(sent, reasonOf("index_locked"));
      const wants = fresh(locked).map((ask) => ask.id);
      const facts = run.firstFacts(wants.includes("read:git") ? withRead(locked, "unborn")
        : locked);
      show({action: facts.result.action, wants, readDropped: locked.reads.git === undefined,
        preview: locked.git.preview !== null, block: facts.blocks.confirm,
        sending: locked.git.sending});
    """)
    assert out == {"action": "retry", "wants": ["read:git"], "readDropped": True,
                   "preview": True, "block": None, "sending": None}


def test_every_answer_to_a_continue_asks_the_git_read_again_a_locked_index_included():
    out = js("""
      const rows = ["pending_unfinished", "pending_unfinished_unborn", "pending_signature"].map(
        (name) => {
          const landed = land(drive(opened({}, name), {type: "git-continue"}),
            reasonOf("index_locked"));
          return [name, run.firstFacts(landed).result.action, landed.reads.git === undefined,
            fresh(landed).map((ask) => ask.id)];
        });
      show(rows);
    """)
    assert out == [[name, "retry", True, ["read:git"]] for name in (
        "pending_unfinished", "pending_unfinished_unborn", "pending_signature")]


def test_a_timed_out_confirm_may_have_left_an_operation_so_the_read_is_asked_again():
    out = js("""
      const timed = land(drive(previewed(), {type: "git-confirm"}), reasonOf("git_timed_out"));
      show({action: run.firstFacts(timed).result.action, wants: fresh(timed).map((a) => a.id)});
    """)
    assert out == {"action": "retry", "wants": ["read:git"]}


def test_a_refusal_the_route_gave_is_its_closed_word_and_the_signature_wait_is_read():
    out = js("""
      const rows = g.GIT_SETUP_REASONS.map((reason) => {
        const landed = land(drive(previewed(), {type: "git-confirm"}), reasonOf(reason));
        const facts = run.firstFacts(landed);
        return [reason, facts.result.status, facts.result.notice, facts.result.next,
          facts.result.action];
      });
      const codes = g.GIT_SETUP_CODES.map((code) => {
        const landed = land(drive(previewed(), {type: "git-confirm"}), refused(code));
        const facts = run.firstFacts(landed);
        return [code, facts.result.status, facts.result.notice, facts.result.next];
      });
      show({rows, codes});
    """)
    for reason, status, notice, nxt, action in out["rows"]:
        assert status == "refused" and notice == f"git_setup.reason.{reason}"
        assert nxt == f"wizard.first.next.{reason}" and action
    assert [row[2] for row in out["codes"]] == [
        "error.project_not_active", "error.contract_invalid", "error.windows_path_too_long",
        "error.tool_unavailable"]
    assert all(row[1] == "refused" and row[3] is None for row in out["codes"])


def test_a_press_the_desks_own_door_turned_away_is_unsent_and_asks_nothing_again():
    out = js("""
      const rows = ["route_not_found", "project_mismatch"].map((code) => {
        const landed = land(drive(opened({}, "not_git"), {type: "git-init"}), refused(code));
        const facts = run.firstFacts(landed);
        return [code, facts.result.status, facts.result.notice, fresh(landed).length,
          landed.reads.git !== undefined, landed.git.sending];
      });
      show(rows);
    """)
    assert out == [["route_not_found", "unsent", "wizard.first.unsent.route_not_found", 0, True,
                    None],
                   ["project_mismatch", "unsent", "wizard.first.unsent.project_mismatch", 0, True,
                    None]]


def test_connecting_git_posts_the_init_body_for_not_git_and_for_nothing_else():
    out = js("""
      const sent = drive(opened({}, "not_git"), {type: "git-init"});
      const others = ["unborn", "repo", "not_active", "unsafe"].map((name) =>
        drive(opened({}, name), {type: "git-init"}).git.sending);
      const done = land(sent, ok(d.init));
      show({ask: sent.git.sending.ask.body, others, result: [done.git.result.status,
        done.git.result.kind], readDropped: done.reads.git === undefined,
        wants: fresh(done).map((ask) => ask.id)});
    """)
    assert out["ask"] == {"step": "init", "actor": "Anna"}
    assert out["others"] == [None] * 4
    assert out["result"] == ["done", "init"] and out["readDropped"] is True
    assert out["wants"] == ["read:git"]


def test_the_exclusion_step_is_offered_only_when_the_read_says_deferred():
    out = js("""
      const deferred = {...copy(d.reads.repo), exclude: "deferred"};
      const unborn = {...copy(d.reads.unborn), exclude: "deferred"};
      d.reads.deferred = deferred; d.reads.deferredUnborn = unborn;
      const rows = ["repo", "unborn", "not_git", "deferred", "deferredUnborn"].map((name) => {
        const state = opened({}, name);
        return [name, run.firstFacts(state).shown.exclude,
          drive(state, {type: "git-exclude"}).git.sending !== null];
      });
      const sent = drive(opened({}, "deferred"), {type: "git-exclude"});
      show({rows, body: sent.git.sending.ask.body});
    """)
    assert out["rows"] == [["repo", False, False], ["unborn", False, False],
                           ["not_git", False, False], ["deferred", True, True],
                           ["deferredUnborn", True, True]]
    assert out["body"] == {"step": "exclude", "actor": "Anna"}


def test_in_view_no_setup_event_asks_anything_and_the_block_says_why():
    out = js("""
      const events = ["git-start", "git-preview", "git-init", "git-exclude", "git-confirm",
        "git-continue"];
      d.reads.deferred = {...copy(d.reads.repo), exclude: "deferred"};
      const rows = {};
      for (const name of ["unborn", "not_git", "not_active", "deferred", "pending_unfinished"]) {
        const state = opened({viewMode: true}, name);
        rows[name] = events.map((type) => drive(state, {type}) === state);
      }
      const view = opened({viewMode: true}, "not_git");
      show({rows, blocks: Object.values(run.firstFacts(view).blocks), shown:
        run.firstFacts(view).shown.connect});
    """)
    assert all(all(row) for row in out["rows"].values()), out["rows"]
    assert set(out["blocks"]) <= {"project_not_active", "confirm_door_closed"}
    assert out["shown"] is False, "in view the exit is drawn disabled by the renderer, not here"


def test_a_desk_with_no_door_for_the_setup_route_blocks_every_press_before_anything_else():
    out = js("""
      const kinds = ["init", "exclude", "preview", "confirm", "continue"];
      const events = ["git-init", "git-exclude", "git-preview", "git-confirm", "git-continue"];
      d.reads.exclude = {...copy(d.reads.repo), exclude: "deferred"};
      const shut = (name) => {
        const state = drive(opened({}, name, true), {type: "git-start"});
        return {...state, git: {...state.git, door: false}};
      };
      const rows = {};
      for (const name of ["not_git", "unborn", "exclude", "pending_unfinished"]) {
        const state = shut(name);
        rows[name] = [kinds.map((kind) => run.pressBlock(state, kind)),
          events.map((type) => drive(state, {type}) === state)];
      }
      show(rows);
    """)
    for name, (blocks, unchanged) in out.items():
        assert blocks == ["door_missing"] * 5, name
        assert unchanged == [True] * 5, f"{name}: a press with no door asks nothing"


def test_a_press_needs_a_valid_name_and_a_preview_alone_does_not():
    out = js("""
      const rows = {};
      for (const actor of ["", "Анна", "a b", "x;y", "Anna"]) {
        const start = drive(opened({actor}, "unborn"), {type: "git-start"});
        rows[actor] = [null, drive(start, {type: "git-preview"}).git.sending !== null,
          run.pressBlock(start, "confirm")];
      }
      const notName = drive(opened({actor: "Anna"}, "not_git"), {type: "actor-edit", value: "B"});
      show({rows, edited: notName.launch.actor});
    """)
    assert out["rows"]["Anna"][1] is True
    for actor in ("", "Анна", "a b", "x;y"):
        assert out["rows"][actor][1] is True, "a preview carries no name"
    assert out["rows"][""][2] == "actor_invalid" and out["rows"]["x;y"][2] == "actor_invalid"
    assert out["rows"]["Anna"][2] == "preview_missing"
    assert out["edited"] == "B"


def test_the_git_block_asks_nothing_unless_a_press_is_in_flight():
    out = js("""
      let state = opened({}, "pending_unfinished");
      const events = [{type: "tick", now: "2026-10-09T12:00:00Z"}, {type: "reread", name: "git"},
        {type: "actor-edit", value: "Anna"}, {type: "close-request"}, {type: "close-cancel"}];
      const names = [];
      for (const event of events) {
        state = drive(state, event);
        names.push(fresh(state).filter((ask) => ask.door === "write").length);
      }
      show({names, wanted: run.gitWanted(state)});
    """)
    assert out["names"] == [0] * 5 and out["wanted"] == []


def test_a_stale_or_unknown_answer_changes_nothing():
    out = js("""
      const sent = ready();
      const other = {...sent.git.sending.ask, id: "write:git:preview:99"};
      const idle = opened();
      const early = run.landGit(idle, other, ok(d.preview));
      const wrong = run.landGit(sent, other, ok(d.preview));
      const after = land(sent, ok(d.preview));
      const twice = run.landGit(after, sent.git.sending.ask, ok(d.preview));
      show({early: early === idle, wrong: wrong === sent, twice: twice === after});
    """)
    assert out == {"early": True, "wrong": True, "twice": True}


def test_the_list_toggle_belongs_to_a_standing_preview_and_goes_with_it():
    out = js("""
      const none = drive(opened(), {type: "git-start"});
      const have = previewed();
      const shown = drive(have, {type: "git-list"});
      const switched = drive(shown, {type: "git-mode", mode: "empty"});
      show({none: drive(none, {type: "git-list"}) === none, on: shown.git.list,
        off: drive(shown, {type: "git-list"}).git.list, switched: switched.git.list});
    """)
    assert out == {"none": True, "on": True, "off": False, "switched": False}
