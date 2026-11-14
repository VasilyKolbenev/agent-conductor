"""The starter's two-step repository: one press, init, a read, then the empty first commit.

The seam (`desk-wizard-git-run.js`) is driven under Node with the real model underneath it, as in
`test_desk_wizard_git_run.py`. What the chain must keep of the slice's rules: never two requests at
once, never a second press while the first works, the second request only after the route's own
exact answer to the first AND a read that says the repository is there and nothing is pending,
nothing sent by itself after an answer the desk did not read, and the confirm waits behind the same
switch as every confirm. What is drawn is `browser_tests/test_desk_wizard_git_starter.py`.
"""
from __future__ import annotations

from typing import Any

from tests.desk_wizard_node import run_js
from tests.test_desk_wizard_git_run import DATA, MODULES, PRELUDE

#: What the chain adds to the seam's prelude. `readStep` answers the git read the model asked for
#: (the way the host does) and gives back the model's step, so the asks it handed out are visible;
#: `rows` is what the view would draw for each link.
CHAIN = """
const STARTER = "desk-starter-docs";
const starter = (name = "not_git", over = {}, door = true) =>
  opened({starterId: STARTER, ...over}, name, door);
const chain = (state) => drive(state, {type: "git-chain"});
const emptyReceipt = (() => {
  const found = copy(d.receipt);
  Object.assign(found.setup, {mode: "empty", paths_digest: null, file_count: 0});
  return found;
})();
const readStep = (state, name) => {
  const gone = fresh(state).find((ask) => ask.name === "git");
  const handed = {...state, asked: [...state.asked, gone.id]};
  const result = name === null ? refused("store_error") : ok({git: d.reads[name]});
  return wiz.stepWizard(handed, {type: "answered", ask: gone, result});
};
const writesOf = (step) => step.asks.filter((ask) => ask.door === "write").map((ask) => ask.id);
const rows = (state) => run.firstFacts(state).chain.rows.map((row) => [row.link, row.status]);
const between = () => land(chain(starter()), ok(d.init));
const second = () => readStep(between(), "unborn").state;
"""
GIT_EVENTS = ["git-start", "git-mode", "git-list", "git-preview", "git-init", "git-exclude",
              "git-confirm", "git-continue", "git-chain"]


def js(body: str) -> Any:
    return run_js(PRELUDE + CHAIN + body, DATA, modules=MODULES)


def test_the_chain_press_asks_for_init_alone_with_the_actor_and_a_press_numbered_id():
    out = js("""
      const state = chain(starter());
      const sending = state.git.sending;
      show({ask: sending.ask, link: sending.link, kind: sending.kind, stage: state.git.chain.stage,
        wanted: fresh(state).map((one) => one.id), result: state.git.result,
        chain: state.git.chain});
    """)
    ask = out["ask"]
    assert (ask["id"], ask["name"], ask["door"], ask["target"], ask["subject"]) == (
        "write:git:init:1", "git_init", "write", "gitSetup", None)
    assert ask["body"] == {"step": "init", "actor": "Anna"}
    assert (out["link"], out["kind"], out["stage"]) == ("first", "init", "init")
    assert out["wanted"] == ["write:git:init:1"], "the first link is the only thing asked"
    assert out["chain"] == {"stage": "init", "first": None, "second": None}


def test_every_git_event_is_a_no_op_at_each_of_the_three_stages_of_the_chain():
    out = js("""
      const events = %s;
      const stages = {init: chain(starter()), read: between(), commit: second()};
      const table = {};
      for (const [stage, state] of Object.entries(stages)) {
        table[stage] = {chain: state.git.chain.stage,
          same: events.map((type) => drive(state, {type, mode: "empty"}) === state),
          actor: wiz.reduceWizard(state, {type: "actor-edit", value: "Mallory"}) === state,
          reread: wiz.reduceWizard(state, {type: "reread", name: "git"}) === state,
          busy: wiz.closeBusy(state), warns: wiz.closeNeedsWarning(state),
          block: run.pressBlock(state, "chain")};
      }
      show(table);
    """ % GIT_EVENTS)
    assert [out[stage]["chain"] for stage in ("init", "read", "commit")] == [
        "init", "read", "commit"]
    for stage, row in out.items():
        assert row["same"] == [True] * len(GIT_EVENTS), stage
        assert row["actor"] and row["reread"], f"{stage}: the name and the read are fixed"
        assert row["busy"] and row["warns"], f"{stage}: closing asks first"
        assert row["block"] is not None, f"{stage}: a press is blocked with a word"


def test_the_second_link_waits_for_a_read_and_is_then_the_empty_confirm_with_no_preview():
    out = js("""
      const waiting = between();
      const step = readStep(waiting, "unborn");
      const sending = step.state.git.sending;
      show({stage: waiting.git.chain.stage, sending: waiting.git.sending,
        wants: fresh(waiting).map((one) => [one.id, one.name]),
        readDropped: waiting.reads.git === undefined, first: waiting.git.chain.first.status,
        after: step.state.git.chain.stage, ask: sending.ask, link: sending.link,
        kind: sending.kind, handed: step.asks.map((ask) => ask.id),
        previews: step.asks.filter((ask) => ask.name === "git_preview").length,
        seq: step.state.git.seq, result: step.state.git.result});
    """)
    assert out["stage"] == "read" and out["sending"] is None and out["first"] == "done"
    assert out["wants"] == [["read:git", "git"]], "after the first link only the read is asked"
    assert out["readDropped"] is True
    ask = out["ask"]
    assert (ask["id"], ask["name"], ask["door"], ask["target"]) == (
        "write:git:confirm:2", "git_confirm", "write", "gitSetup")
    assert ask["body"] == {"step": "first_commit", "mode": "empty", "paths_digest": None,
                           "actor": "Anna"}
    assert (out["after"], out["link"], out["kind"]) == ("commit", "second", "confirm")
    assert out["handed"] == ["write:git:confirm:2"] and out["previews"] == 0
    assert out["seq"] == 2 and out["result"] is None


def test_the_second_link_is_not_sent_when_the_read_says_anything_but_unborn_and_nothing_pending():
    out = js("""
      const waiting = between();
      const table = {};
      for (const name of ["not_git", "repo", "pending_unfinished", "pending_signature",
          "pending_unfinished_unborn", "pending_damaged", "unsafe", "not_active", null]) {
        const step = readStep(waiting, name);
        table[name ?? "failed"] = [step.state.git.chain.stage, step.state.git.sending,
          writesOf(step), step.state.git.chain.second];
      }
      show(table);
    """)
    assert len(out) == 9
    for name, row in out.items():
        assert row == ["over", None, [], None], name


def test_a_first_link_that_is_refused_lost_or_turned_away_ends_the_chain_and_no_read_starts_more():
    out = js("""
      const answers = {refused: reasonOf("unsafe_directory"),
        other_code: refused("tool_unavailable"), unknown: {status: "unknown"},
        store: refused("store_error"), stray: ok({stray: 1}), unsent: refused("route_not_found")};
      const table = {};
      for (const [name, result] of Object.entries(answers)) {
        const landed = land(chain(starter()), result);
        const wants = fresh(landed).map((one) => one.id);
        const after = wants.includes("read:git") ? readStep(landed, "unborn") : null;
        const facts = run.firstFacts(after === null ? landed : after.state);
        table[name] = [landed.git.chain.stage, landed.git.chain.first.status,
          landed.git.chain.second, landed.git.sending, wants,
          after === null ? [] : writesOf(after), facts.chain.rows[1].skipped,
          facts.chain.rows[1].status];
      }
      show(table);
    """)
    skipped = {"refused": "first_refused", "other_code": "first_refused", "unknown": "first_lost",
               "store": "first_lost", "stray": "first_lost", "unsent": "first_unsent"}
    status = {"refused": "refused", "other_code": "refused", "unknown": "lost", "store": "lost",
              "stray": "lost", "unsent": "unsent"}
    assert set(out) == set(skipped)
    for name, row in out.items():
        wants = [] if name == "unsent" else ["read:git"]
        assert row == ["over", status[name], None, None, wants, [], skipped[name], "skipped"], name


def test_a_lost_first_link_is_not_continued_by_a_read_that_shows_it_done():
    out = js("""
      const lost = land(chain(starter()), {status: "unknown"});
      const step = readStep(lost, "unborn");
      const facts = run.firstFacts(step.state);
      show({rows: facts.chain.rows.map((row) => [row.link, row.status, row.skipped]),
        verdict: facts.chain.rows[0].result.verdict, byHand: facts.chain.byHand,
        stage: facts.chain.stage, writes: writesOf(step), sending: step.state.git.sending,
        exit: step.state.git.chain.second});
    """)
    assert out["rows"] == [["init", "lost", None], ["commit", "skipped", "first_lost"]]
    assert out["verdict"] == "wizard.first.lost.done", "the read says it was done, and says only so"
    assert out["byHand"] is True and out["stage"] == "over"
    assert out["writes"] == [] and out["sending"] is None and out["exit"] is None


def test_the_chain_is_blocked_with_its_word_and_sends_nothing_when_it_may_not_go():
    out = js("""
      const base = starter();
      const cases = {
        ready: base,
        shut: {...base, git: {...base.git, open: false}},
        no_door: {...base, git: {...base.git, door: false}},
        view: opened({starterId: STARTER, viewMode: true}, "not_git"),
        nameless: opened({starterId: STARTER, actor: ""}, "not_git"),
        invalid_name: opened({starterId: STARTER, actor: "a b"}, "not_git"),
        reading: {...base, reads: {}},
        normal_mode: opened({}, "not_git"),
        ...Object.fromEntries(["unborn", "repo", "not_active", "unsafe", "pending_unfinished",
          "pending_signature"].map((name) => [name, starter(name)]))};
      const table = {};
      for (const [name, state] of Object.entries(cases)) {
        table[name] = [run.pressBlock(state, "chain"), chain(state) === state];
      }
      show(table);
    """)
    assert out["ready"] == [None, False]
    expected = {"shut": "confirm_door_closed", "no_door": "door_missing",
                "view": "project_not_active", "nameless": "actor_invalid",
                "invalid_name": "actor_invalid", "reading": "git_reading",
                "normal_mode": "not_offered", "unborn": "not_offered", "repo": "not_offered",
                "not_active": "not_offered", "unsafe": "not_offered",
                "pending_unfinished": "not_offered", "pending_signature": "not_offered"}
    for name, word in expected.items():
        assert out[name] == [word, True], name


def test_the_second_links_own_answer_is_its_own_row_and_the_first_stays_done():
    out = js("""
      const there = second();
      const facts = (state, name) => run.firstFacts(readStep(state, name).state);
      const done = land(there, ok(emptyReceipt));
      const identity = land(there, reasonOf("git_identity_missing"));
      const lost = land(there, {status: "unknown"});
      const signing = land(there, reasonOf("signing_required"));
      const named = facts(identity, "unborn");
      const awaiting = facts(signing, "pending_signature");
      show({done: [rows(done), done.git.chain.stage, done.git.chain.second.receipt.mode,
          fresh(done).map((one) => one.id)],
        identity: [rows(identity), named.chain.rows[1].result.notice,
          named.chain.rows[1].result.next, named.chain.byHand],
        lost: [rows(lost), facts(lost, "repo").chain.rows[1].result.verdict,
          facts(lost, "unborn").chain.rows[1].result.verdict,
          facts(lost, "pending_unfinished").chain.rows[1].result.verdict],
        signing: [rows(signing), awaiting.chain.byHand, awaiting.pending.state,
          awaiting.commands !== null, awaiting.chain.rows[1].result.action],
        writes: [identity, lost, signing].map((state) => fresh(state).map((one) => one.id))});
    """)
    assert out["done"] == [[["init", "done"], ["commit", "done"]], "over", "empty", ["read:git"]]
    assert out["identity"] == [[["init", "done"], ["commit", "refused"]],
                               "git_setup.reason.git_identity_missing",
                               "wizard.first.next.git_identity_missing", True]
    assert out["lost"] == [[["init", "done"], ["commit", "lost"]], "wizard.first.lost.done",
                           "wizard.first.lost.none", "wizard.first.lost.pending"]
    assert out["signing"] == [[["init", "done"], ["commit", "refused"]], False,
                              "awaiting_signature", True, "wait"]
    assert out["writes"] == [["read:git"]] * 3, "an answer asks for the read again and no write"


def test_the_rows_follow_the_press_from_working_to_done_and_the_busy_word_follows_them():
    out = js("""
      const pressed = chain(starter());
      const waiting = between();
      const there = second();
      const finished = land(there, ok(emptyReceipt));
      const table = [pressed, waiting, there, finished].map((state) => {
        const facts = run.firstFacts(state);
        return [facts.chain.stage, rows(state), facts.phase, facts.busy];
      });
      show(table);
    """)
    assert out == [
        ["init", [["init", "working"], ["commit", "todo"]], "busy", "init"],
        ["read", [["init", "done"], ["commit", "todo"]], "busy", "chain_read"],
        ["commit", [["init", "done"], ["commit", "working"]], "busy", "confirm"],
        ["over", [["init", "done"], ["commit", "done"]], "idle", None]]


def test_a_chain_pressed_again_after_a_stop_starts_a_new_chain_with_new_ids():
    out = js("""
      const stopped = land(chain(starter()), reasonOf("unsafe_directory"));
      const back = readStep(stopped, "not_git").state;
      const block = run.pressBlock(back, "chain");
      const again = chain(back);
      show({block, id: again.git.sending.ask.id, chain: again.git.chain,
        shown: run.firstFacts(back).chain.stage});
    """)
    assert out["block"] is None, "a stopped chain on a missing repository can be pressed again"
    assert out["id"] == "write:git:init:2"
    assert out["chain"] == {"stage": "init", "first": None, "second": None}
    assert out["shown"] == "over"


def test_any_other_git_press_after_the_chain_clears_its_rows():
    out = js("""
      const stopped = readStep(land(second(), reasonOf("git_identity_missing")), "unborn").state;
      const kept = run.firstFacts(stopped).chain !== null;
      const started = drive(stopped, {type: "git-start"});
      show({kept, cleared: started.git.chain === null, panel: started.git.panel,
        facts: run.firstFacts(started).chain});
    """)
    assert out == {"kept": True, "cleared": True, "panel": "first_commit", "facts": None}


def test_a_git_read_that_lands_when_no_chain_waits_leaves_the_state_alone():
    out = js("""
      const asked = wiz.stepWizard(starter(), {type: "reread", name: "git"});
      const step = wiz.stepWizard(asked.state, {type: "answered", ask: asked.asks[0],
        result: ok({git: d.reads.unborn})});
      show({asked: asked.asks.map((ask) => ask.id), chain: step.state.git.chain,
        sending: step.state.git.sending, writes: writesOf(step)});
    """)
    assert out == {"asked": ["read:git"], "chain": None, "sending": None, "writes": []}


def test_the_facts_say_whether_the_wizard_is_a_starter_and_have_no_chain_before_a_press():
    out = js("""
      const facts = (state) => run.firstFacts(state);
      show({starter: facts(starter()).starter, normal: facts(opened({}, "not_git")).starter,
        chain: facts(starter()).chain, connect: [facts(starter()).shown.connect,
          facts(opened({}, "not_git")).shown.connect],
        blocks: facts(starter()).blocks});
    """)
    assert out["starter"] is True and out["normal"] is False and out["chain"] is None
    assert out["connect"] == [True, True]
    assert out["blocks"]["chain"] is None and out["blocks"]["init"] is None


def test_a_failed_read_after_the_first_link_ends_the_chain_and_says_the_project_is_not_ready():
    out = js("""
      const step = readStep(between(), null);
      const facts = run.firstFacts(step.state);
      show({rows: facts.chain.rows.map((row) => [row.link, row.status, row.skipped]),
        byHand: facts.chain.byHand, writes: writesOf(step)});
    """)
    assert out["rows"] == [["init", "done", None], ["commit", "skipped", "read"]]
    assert out["byHand"] is False, "a project that could not be read offers nothing by hand"
    assert out["writes"] == []
