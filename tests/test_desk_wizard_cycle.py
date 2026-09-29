"""The wizard model's step 3 ("Цикл"): cards, preselection, and the flow write.

The answers a real server will give are lane L's flow fixtures (`tests/fixtures/flow/`,
`FlowState` with its `Budget`) and the stand-in reads under `tests/fixtures/wizard/`. The
model draws nothing and computes no budget: every number on this step is one of those answers.
"""
from __future__ import annotations

import pytest

from tests.desk_wizard_node import PRELUDE, fixture, run_js

FLOWS = {"standard": fixture("flow", "desk-standard.flow-state.json"),
         "short": fixture("flow", "desk-short.flow-state.json"),
         "starter": fixture("flow", "desk-starter-docs.flow-state.json"),
         "tester": fixture("flow", "desk-standard-tester.flow-state.json"),
         "dalio": fixture("flow", "dalio-v5.flow-state.json")}
DATA = {"flows": FLOWS, "workflows": fixture("wizard", "workflows.json"),
        "runs": fixture("wizard", "runs.json"), "tasks": fixture("wizard", "tasks.json"),
        "pinned": fixture("wizard", "project_cycle.json"),
        "unpinned": fixture("wizard", "project_cycle_none.json"),
        "git": fixture("wizard", "git_repo.json"),
        "none": fixture("wizard", "flow_state_none.json")}
#: A wizard standing on the cycle step: `atCycle` has read the project's git (step 2 holds while
#: it is unread) and moved on, `settled` has read the three answers a preselection needs,
#: `answer` hands one ask's outcome back to the reducer,
#: `picks` chooses a card and answers its first read, so the write it made due is `asks[0]`.
CYCLE = PRELUDE + """
const atCycle = (over = {}) => run(reply(opened(started(over)), "git", d.git), {type: "next"});
const answer = (state, ask, result) => wiz.reduceWizard(state, {type: "answered", ask, result});
const ok = (payload) => ({status: "accepted", payload});
const settled = (pin = d.pinned, runs = d.runs, workflows = d.workflows) => {
  let state = opened(atCycle());
  for (const [name, payload] of [["workflows", workflows], ["runs", runs],
      ["cycle_read", pin], ["tasks", d.tasks]]) state = reply(state, name, payload);
  return state;
};
const chosen = (state, id) => wiz.stepWizard(state, {type: "cycle-choose", id});
const idsOf = (state) => wiz.cycleCards(state).map((card) => card.id);
const asksOf = (step) => step.asks.map((ask) => [ask.id, ask.name, ask.door, ask.target,
  ask.subject]);
const digest = "sha256:" + "a".repeat(64);
const drafted = (flow, over = {}) => ({...structuredClone(flow), source: "draft",
  draft_digest: digest, published: null, ...over});
const none = (id) => ({...structuredClone(d.none), workflow_id: id});
const lands = (step, payload) => wiz.stepWizard(step.state, {type: "answered",
  ask: step.asks[0], result: ok(payload)});
const picks = (id, seen = none(id)) => lands(chosen(
  reply(opened(atCycle()), "workflows", d.workflows), id), seen);
const inStarterMode = () => {
  const state = run(open({starterId: "desk-starter-docs"}),
    {type: "edit-title", value: "Notes"}, {type: "edit-idea", value: "An app."}, {type: "next"});
  return run(reply(opened(state), "git", d.git), {type: "next"});
};
"""


def test_cycle_cards_are_pinned_first_then_standard_short_saved_cycles_then_build_your_own():
    out = run_js(CYCLE + """
      const rows = (state) => wiz.cycleCards(state).map((card) =>
        [card.id, card.kind, card.pinned, card.published, card.title]);
      const shortPinned = structuredClone(d.pinned);
      shortPinned.pinned.workflow_id = "desk-short";
      show({pinned: rows(settled()), unpinned: rows(settled(d.unpinned)),
        short_pinned: idsOf(settled(shortPinned)),
        unread: idsOf(reply(opened(atCycle()), "workflows", null,
          {status: "refused", code: "store_error"}))});
    """, DATA)
    assert out["pinned"] == [
        ["cycle-7c1e5a90", "saved", True, True, "Standard with a tester"],
        ["desk-standard", "starter", False, True, None],
        ["desk-short", "starter", False, False, None],
        ["old-cycle", "saved", False, True, "Old cycle"],
        ["build", "build", False, False, None]]
    assert [row[0] for row in out["unpinned"]] == [
        "desk-standard", "desk-short", "cycle-7c1e5a90", "old-cycle", "build"]
    assert not any(row[2] for row in out["unpinned"])
    assert out["short_pinned"] == ["desk-short", "desk-standard", "cycle-7c1e5a90", "old-cycle",
                                   "build"]
    assert out["unread"] == ["desk-standard", "desk-short", "build"]


def test_desk_prefixed_workflows_are_never_saved_cycles_and_starter_docs_is_never_a_card():
    out = run_js(CYCLE + """
      const workflows = structuredClone(d.workflows);
      workflows.workflows.push({workflow_id: "desk-extra", title: "Extra", latest_revision: 1,
        revisions: [1], has_draft: false, unreadable: false});
      const ids = idsOf(settled(d.unpinned, d.runs, workflows));
      const starterDocsLast = structuredClone(d.runs);
      starterDocsLast.runs[1].workflow_id = "desk-starter-docs";
      const pinnedStarter = structuredClone(d.pinned);
      pinnedStarter.pinned.workflow_id = "desk-starter-docs";
      show({ids, last_run_on_starter_docs: wiz.preselection(
          settled(d.unpinned, starterDocsLast).reads).choice,
        pinned_starter_docs: wiz.preselection(settled(pinnedStarter).reads).choice});
    """, DATA)
    assert out["ids"] == ["desk-standard", "desk-short", "cycle-7c1e5a90", "old-cycle", "build"]
    assert out["last_run_on_starter_docs"] is None, "and no older run's cycle stands in for it"
    assert out["pinned_starter_docs"]["workflowId"] == "desk-standard"


def test_the_starter_mode_cycle_is_fixed_and_offers_no_choice_and_no_build_your_own():
    out = run_js(CYCLE + """
      const state = inStarterMode();
      const attempt = chosen(state, "desk-short");
      const read = wiz.wantedAsks(state).filter((ask) => ask.door === "read"
        && ask.name === "flow_read").map((ask) => [ask.id, ask.subject]);
      const written = land(state, none("desk-starter-docs"));
      show({step: state.step, cards: wiz.cycleCards(state).map((card) =>
          [card.id, card.kind, card.locked, card.canPin]),
        choice: state.cycle.choice, by: state.cycle.chosenBy,
        choose_ignored: attempt.state === state && attempt.asks.length === 0,
        read, writes_before_the_read: wiz.wantedAsks(state)
          .filter((ask) => ask.door === "write").length,
        ask_ids: wiz.wantedAsks(written).filter((ask) => ask.name === "flow")
          .map((ask) => [ask.id, ask.subject, ask.body.source])});
    """, DATA)
    assert out["step"] == "cycle"
    assert out["cards"] == [["desk-starter-docs", "starter", True, False]]
    assert out["choice"] == {"kind": "starter", "workflowId": "desk-starter-docs"}
    assert out["by"] == "starter" and out["choose_ignored"] is True
    assert out["read"] == [["read:flow:1", "desk-starter-docs"]]
    assert out["writes_before_the_read"] == 0
    assert out["ask_ids"] == [["write:flow:1", "desk-starter-docs",
                               {"starter_id": "desk-starter-docs"}]]


def test_preselection_takes_the_pinned_cycle_then_the_last_runs_workflow_and_names_the_source():
    out = run_js(CYCLE + """
      const found = (pin, runs = d.runs) => wiz.preselection(settled(pin, runs).reads);
      const noWorkflowRuns = structuredClone(d.runs);
      noWorkflowRuns.runs = noWorkflowRuns.runs.filter((run) => run.workflow_id === null);
      const deleted = structuredClone(d.runs);
      deleted.runs[1].workflow_id = "gone-cycle";
      const early = wiz.preselection(reply(opened(atCycle()), "workflows", d.workflows).reads);
      show({pinned: found(d.pinned), last_run: found(d.unpinned),
        nothing: found(d.unpinned, noWorkflowRuns), deleted: found(d.unpinned, deleted),
        early: [early.ready, early.choice],
        applied: [settled().cycle.choice, settled().cycle.chosenBy],
        applied_last: [settled(d.unpinned).cycle.choice, settled(d.unpinned).cycle.chosenBy]});
    """, DATA)
    assert out["pinned"] == {"ready": True, "pinnedUnread": False,
                             "choice": {"kind": "saved", "workflowId": "cycle-7c1e5a90"},
                             "source": {"kind": "pinned", "by": "Вы: Василий",
                                        "at": "2026-09-28T13:50:00Z", "task": None,
                                        "taskTitle": None, "workflowId": "cycle-7c1e5a90"}}
    assert out["last_run"] == {"ready": True, "pinnedUnread": False,
                               "choice": {"kind": "starter", "workflowId": "desk-standard"},
                               "source": {"kind": "last_run", "by": None,
                                          "at": "2026-09-28T13:50:00Z", "task": "task-b",
                                          "taskTitle": "Fix the login form",
                                          "workflowId": "desk-standard"}}
    assert out["nothing"]["choice"] is None and out["nothing"]["source"]["kind"] == "none"
    assert out["deleted"]["choice"] is None, "the newest run's cycle is gone: no stand-in"
    assert out["deleted"]["source"]["kind"] == "last_run_uncarded"
    assert out["early"] == [False, None]
    assert out["applied"] == [{"kind": "saved", "workflowId": "cycle-7c1e5a90"}, "preselection"]
    assert out["applied_last"] == [{"kind": "starter", "workflowId": "desk-standard"},
                                   "preselection"]


def test_the_newest_run_stays_the_last_run_when_its_cycle_is_not_a_card():
    """An older run's cycle must not stand in for the newest run's under the words "last run"."""
    out = run_js(CYCLE + """
      const newestOn = (workflowId) => {
        const runs = structuredClone(d.runs);
        runs.runs[1].workflow_id = workflowId;
        return runs;
      };
      const found = (workflowId, pin = d.unpinned) => wiz.preselection(
        settled(pin, newestOn(workflowId)).reads);
      const state = settled(d.unpinned, newestOn("desk-starter-docs"));
      show({docs: found("desk-starter-docs"), gone: found("gone-cycle"),
        pinned_still_wins: found("desk-starter-docs", d.pinned).source.kind,
        card_still_chosen: found("desk-short").choice,
        applied: [state.cycle.choice, state.cycle.chosenBy],
        gate: wiz.canAdvance(state).reason});
    """, DATA)
    stood_for = {"by": None, "at": "2026-09-28T13:50:00Z", "task": "task-b",
                 "taskTitle": "Fix the login form"}
    assert out["docs"]["choice"] is None and out["docs"]["ready"] is True
    assert out["docs"]["source"] == {"kind": "last_run_uncarded", "workflowId": "desk-starter-docs",
                                     **stood_for}
    assert out["gone"]["choice"] is None
    assert out["gone"]["source"] == {"kind": "last_run_uncarded", "workflowId": "gone-cycle",
                                     **stood_for}
    assert out["pinned_still_wins"] == "pinned"
    assert out["card_still_chosen"] == {"kind": "starter", "workflowId": "desk-short"}
    assert out["applied"] == [None, None], "nothing is chosen for the owner"
    assert out["gate"] == "cycle_none"


def test_an_unread_pinned_cycle_falls_back_to_the_last_run_and_says_nothing_false():
    out = run_js(CYCLE + """
      let state = opened(atCycle());
      for (const [name, payload] of [["workflows", d.workflows], ["runs", d.runs],
          ["tasks", d.tasks]]) state = reply(state, name, payload);
      const waiting = wiz.preselection(state.reads);
      const failed = reply(state, "cycle_read", null, {status: "refused", code: "store_error"});
      const lost = reply(state, "cycle_read", null, {status: "unknown"});
      const found = wiz.preselection(failed.reads);
      show({waiting: [waiting.ready, waiting.choice],
        failed: [found.ready, found.pinnedUnread, found.choice, found.source.kind],
        lost_unread: wiz.preselection(lost.reads).pinnedUnread,
        none_pinned_is_not_unread: wiz.preselection(settled(d.unpinned).reads).pinnedUnread,
        applied: [failed.cycle.choice.workflowId, failed.cycle.chosenBy]});
    """, DATA)
    assert out["waiting"] == [False, None]
    assert out["failed"] == [True, True, {"kind": "starter", "workflowId": "desk-standard"},
                             "last_run"]
    assert out["lost_unread"] is True and out["none_pinned_is_not_unread"] is False
    assert out["applied"] == ["desk-standard", "preselection"]


def test_choosing_a_card_asks_for_the_flow_with_no_publication():
    out = run_js(CYCLE + """
      const base = reply(opened(atCycle()), "workflows", d.workflows);
      const starter = chosen(base, "desk-short");
      const saved = chosen(base, "old-cycle");
      const unknown = chosen(base, "no-such-cycle");
      const build = chosen(base, "build");
      show({starter: asksOf(starter), starter_body: starter.asks[0].body,
        saved: asksOf(saved), saved_body: saved.asks[0].body, choice: starter.state.cycle.choice,
        by: starter.state.cycle.chosenBy, unknown_same: unknown.state === base,
        build_same: build.state === base, writes_before: wiz.wantedAsks(base)
          .filter((ask) => ask.door === "write").length});
    """, DATA)
    assert out["starter"] == [["read:flow:1", "flow_read", "read", "flowRead", "desk-short"]]
    assert out["starter_body"] is None, "a read carries no body"
    assert out["saved"] == [["read:flow:1", "flow_read", "read", "flowRead", "old-cycle"]]
    assert out["saved_body"] is None
    assert out["choice"] == {"kind": "starter", "workflowId": "desk-short"}
    assert out["by"] == "owner" and out["unknown_same"] and out["build_same"]
    assert out["writes_before"] == 0


def test_the_flow_write_uses_the_expectation_the_read_reported_and_the_drafts_digest_after():
    out = run_js(CYCLE + """
      const first = picks("desk-standard");
      const landed = answer(first.state, first.asks[0], ok(drafted(d.flows.standard)));
      const bound = wiz.flowWriteRequest(landed, {publish: null, binding: {"role-doer": "codex"}});
      const published = wiz.flowWriteRequest(landed, {publish: 2, binding: null});
      show({first: first.asks[0].body, bound: bound.body, published: published.body,
        id: bound.id, both_expectations: [bound.body, published.body].map(
          (body) => Object.keys(body).filter((key) => key.startsWith("expected_")))});
    """, DATA)
    assert out["first"]["expected_absent"] is True and "expected_digest" not in out["first"]
    assert out["bound"] == {"source": {"starter_id": "desk-standard"},
                            "expected_digest": "sha256:" + "a" * 64, "publish_revision": None,
                            "binding": {"role-doer": "codex"}}
    assert out["published"]["publish_revision"] == 2 and out["published"]["binding"] is None
    assert out["both_expectations"] == [["expected_digest"], ["expected_digest"]]
    assert out["id"] == "write:flow:1"


def test_a_ready_cycle_is_read_before_its_first_write_and_the_write_carries_what_the_read_said():
    out = run_js(CYCLE + """
      const read = chosen(reply(opened(atCycle()), "workflows", d.workflows), "desk-short");
      const published = {...structuredClone(d.flows.short), source: "published",
        draft_digest: null};
      const writes = (payload) => lands(read, payload).asks.map((ask) => [ask.id, ask.body]);
      show({read: asksOf(read), writes_before: wiz.wantedAsks(read.state)
          .filter((ask) => ask.door === "write").length,
        left_over: writes(drafted(d.flows.short)), none: writes(none("desk-short")),
        published: writes(published)});
    """, DATA)
    assert out["read"] == [["read:flow:1", "flow_read", "read", "flowRead", "desk-short"]]
    assert out["writes_before"] == 0, "no write goes out before the read has landed"
    source = {"starter_id": "desk-short"}
    standing = {"source": source, "expected_digest": "sha256:" + "a" * 64,
                "publish_revision": None, "binding": None}
    absent = {"source": source, "expected_absent": True, "publish_revision": None,
              "binding": None}
    assert out["left_over"] == [["write:flow:1", standing]]
    assert out["none"] == [["write:flow:1", absent]], "no draft and no revision"
    assert out["published"] == [["write:flow:1", absent]], "a revision is not a draft"


@pytest.mark.parametrize("mode", ["normal", "starter"])
def test_a_wizard_that_finds_a_left_over_draft_lands_idle_and_never_changed_elsewhere(mode):
    out = run_js(CYCLE + """
      const starter = d.mode === "starter";
      const id = starter ? "desk-starter-docs" : "desk-standard";
      const flow = drafted(starter ? d.flows.starter : d.flows.standard);
      const at = starter ? inStarterMode()
        : reply(opened(atCycle()), "workflows", d.workflows);
      const first = starter ? {state: at, asks: [flowAsk(at)]} : chosen(at, id);
      const second = lands(first, flow);
      const write = second.asks[0];
      const landed = answer(second.state, write, ok(flow));
      show({first: first.asks[0].name, write: [write.name, write.body.expected_digest,
          write.body.expected_absent], status: landed.cycle.status,
        gate: wiz.canAdvance(landed).reason, facts: wiz.cycleFacts(landed).status,
        flow_for: landed.cycle.flowFor, id});
    """, {**DATA, "mode": mode})
    assert out["first"] == "flow_read", "the draft is read before anything is written"
    assert out["write"] == ["flow", "sha256:" + "a" * 64, None]
    assert out["status"] == "idle" and out["facts"] == "idle"
    assert out["gate"] is None, "the step is complete once the write has landed"
    assert out["flow_for"] == out["id"]


def test_a_lost_flow_write_is_retried_by_reading_again_and_then_writing_in_starter_mode():
    out = run_js(CYCLE + """
      const later = "sha256:" + "c".repeat(64);
      const state = inStarterMode();
      const read = lands({state, asks: [flowAsk(state)]}, none("desk-starter-docs"));
      const lost = wiz.stepWizard(read.state, {type: "answered", ask: read.asks[0],
        result: {status: "unknown"}});
      const retry = wiz.stepWizard(lost.state, {type: "cycle-retry"});
      const reread = lands(retry, drafted(d.flows.starter, {draft_digest: later}));
      const landed = answer(reread.state, reread.asks[0],
        ok(drafted(d.flows.starter, {draft_digest: later})));
      show({lost: [lost.state.cycle.status, wiz.canAdvance(lost.state).reason, lost.asks.length],
        retry: [retry.state.cycle.status, asksOf(retry), retry.state.cycle.draft],
        write: [asksOf(reread), reread.asks[0].body.expected_digest,
          reread.asks[0].body.expected_absent],
        done: [landed.cycle.status, wiz.canAdvance(landed).reason]});
    """, DATA)
    assert out["lost"] == ["unknown", "flow_unknown", 0], "a lost answer leaves nothing to ask"
    assert out["retry"] == ["idle", [["read:flow:2", "flow_read", "read", "flowRead",
                                      "desk-starter-docs"]], None]
    assert out["write"] == [[["write:flow:2", "flow", "write", "flow", "desk-starter-docs"]],
                            "sha256:" + "c" * 64, None]
    assert out["done"] == ["idle", None]


@pytest.mark.parametrize("mode", ["normal", "starter"])
def test_a_moved_draft_is_retried_with_the_fresh_digest_and_the_locked_starter_can_do_it(mode):
    out = run_js(CYCLE + """
      const starter = d.mode === "starter";
      const id = starter ? "desk-starter-docs" : "desk-standard";
      const flow = starter ? d.flows.starter : d.flows.standard;
      const at = starter ? inStarterMode() : reply(opened(atCycle()), "workflows", d.workflows);
      const first = starter ? {state: at, asks: [flowAsk(at)]} : chosen(at, id);
      const write = lands(first, none(id));
      const conflict = wiz.stepWizard(write.state, {type: "answered", ask: write.asks[0],
        result: {status: "refused", code: "draft_conflict", payload: null}});
      const moved = lands(conflict, drafted(flow));
      const retry = wiz.stepWizard(moved.state, {type: "cycle-retry"});
      show({status: moved.state.cycle.status, gate: wiz.canAdvance(moved.state).reason,
        retry: [retry.state.cycle.status, asksOf(retry), retry.asks[0].body.expected_digest]});
    """, {**DATA, "mode": mode})
    assert out["status"] == "changed_elsewhere" and out["gate"] == "flow_changed_elsewhere"
    card = "desk-starter-docs" if mode == "starter" else "desk-standard"
    assert out["retry"] == ["idle", [["write:flow:2", "flow", "write", "flow", card]],
                            "sha256:" + "a" * 64]


def test_retry_is_ignored_unless_the_answer_was_lost_or_the_draft_moved():
    out = run_js(CYCLE + """
      const same = (state) => wiz.stepWizard(state, {type: "cycle-retry"}).state === state;
      const written = picks("desk-standard");
      const landed = answer(written.state, written.asks[0], ok(d.flows.standard));
      const refused = answer(written.state, written.asks[0],
        {status: "refused", code: "contract_invalid", payload: null});
      const conflict = wiz.stepWizard(written.state, {type: "answered", ask: written.asks[0],
        result: {status: "refused", code: "draft_conflict", payload: null}}).state;
      show({none_chosen: same(reply(opened(atCycle()), "workflows", d.workflows)),
        pending: same(written.state), idle: same(landed), refused: same(refused),
        conflict: same(conflict)});
    """, DATA)
    assert out == {"none_chosen": True, "pending": True, "idle": True, "refused": True,
                   "conflict": True}


def test_choosing_the_same_card_after_a_lost_answer_reads_again_before_it_writes():
    out = run_js(CYCLE + """
      const written = picks("desk-standard");
      const lost = wiz.stepWizard(written.state, {type: "answered", ask: written.asks[0],
        result: {status: "unknown"}});
      const again = chosen(lost.state, "desk-standard");
      show({status: lost.state.cycle.status, asks: asksOf(again),
        draft: again.state.cycle.draft});
    """, DATA)
    assert out["status"] == "unknown"
    assert out["asks"] == [["read:flow:2", "flow_read", "read", "flowRead", "desk-standard"]]
    assert out["draft"] is None, "the lost write may have landed: what stood is not known"


def test_a_saved_cycle_read_keeps_its_flow_and_its_digest_for_the_binding_write():
    out = run_js(CYCLE + """
      const flow = {...structuredClone(d.flows.tester), workflow_id: "old-cycle",
        source: "draft", draft_digest: digest, latest_revision: 3, next_revision: 4};
      const read = lands(chosen(reply(opened(atCycle()), "workflows", d.workflows),
        "old-cycle"), flow);
      const write = wiz.flowWriteRequest(read.state, {publish: null, binding: {"role-doer": "x"}});
      show({held: read.state.cycle.flowFor, draft: read.state.cycle.draft,
        expected: [write.body.expected_digest, write.body.expected_absent],
        source_flow: JSON.stringify(write.body.source.flow) === JSON.stringify(flow.flow)});
    """, DATA)
    assert out["held"] == "old-cycle"
    assert out["draft"] == {"for": "old-cycle", "digest": "sha256:" + "a" * 64, "generation": 1}
    assert out["expected"] == ["sha256:" + "a" * 64, None] and out["source_flow"] is True


def test_an_answer_that_is_not_a_flow_state_of_this_cycle_is_refused_and_not_stored():
    out = run_js(CYCLE + """
      const base = reply(opened(atCycle()), "workflows", d.workflows);
      const after = (id, payload) => {
        const state = lands(chosen(base, id), payload).state.cycle;
        return [state.status, state.draft, state.flow];
      };
      const noDraft = (id) => ({...none(id), source: "draft"});
      show({ready_none: after("desk-short", none("desk-short"))[0],
        saved_none: after("old-cycle", none("old-cycle")),
        other_workflow: after("desk-short", none("desk-standard")),
        flow_missing_on_a_draft: after("desk-short", noDraft("desk-short"))[0],
        no_diagnostics: after("desk-short", {...none("desk-short"), diagnostics: null})[0]});
    """, DATA)
    assert out["ready_none"] == "idle", "a ready cycle with no draft answers source none"
    assert out["saved_none"] == ["refused", None, None], "a saved cycle must have a flow"
    assert out["other_workflow"] == ["refused", None, None]
    assert out["flow_missing_on_a_draft"] == "refused"
    assert out["no_diagnostics"] == "refused"


def test_a_saved_cycle_is_read_first_and_written_only_with_its_own_flow():
    out = run_js(CYCLE + """
      const flow = {...structuredClone(d.flows.tester), workflow_id: "old-cycle",
        source: "published", draft_digest: null, latest_revision: 3, next_revision: 4};
      const picked = chosen(reply(opened(atCycle()), "workflows", d.workflows), "old-cycle");
      const before = wiz.flowWriteRequest(picked.state, {publish: null, binding: null});
      const read = wiz.stepWizard(picked.state, {type: "answered", ask: picked.asks[0],
        result: ok(flow)});
      const write = wiz.flowWriteRequest(read.state, {publish: null, binding: {"role-doer": "x"}});
      show({before, read_asks: read.asks.length, held: read.state.cycle.flowFor,
        source_is_the_flow: JSON.stringify(write.body.source.flow) === JSON.stringify(flow.flow),
        expected: [write.body.expected_absent, write.body.expected_digest],
        keys: Object.keys(write.body).sort(), subject: write.subject});
    """, DATA)
    assert out["before"] is None and out["read_asks"] == 0 and out["held"] == "old-cycle"
    assert out["source_is_the_flow"] is True
    assert out["expected"] == [True, None] and out["subject"] == "old-cycle"
    assert out["keys"] == ["binding", "expected_absent", "publish_revision", "source"]


def test_a_draft_conflict_answer_asks_for_a_reread_and_keeps_the_chosen_card():
    out = run_js(CYCLE + """
      const first = picks("desk-standard");
      const conflict = wiz.stepWizard(first.state, {type: "answered", ask: first.asks[0],
        result: {status: "refused", code: "draft_conflict", payload: null}});
      const reread = conflict.asks[0];
      const landed = wiz.stepWizard(conflict.state, {type: "answered", ask: reread,
        result: ok(drafted(d.flows.standard))});
      const retry = chosen(landed.state, "desk-standard");
      show({status: conflict.state.cycle.status, choice: conflict.state.cycle.choice,
        asks: asksOf(conflict), gate: wiz.canAdvance(conflict.state).reason,
        after_reread: [landed.state.cycle.status, landed.asks.length,
          landed.state.cycle.flow.draft_digest === "sha256:" + "a".repeat(64)],
        gate_after: wiz.canAdvance(landed.state).reason,
        retry: retry.asks[0].body.expected_digest, retry_status: retry.state.cycle.status});
    """, DATA)
    assert out["status"] == "conflict" and out["choice"]["workflowId"] == "desk-standard"
    assert out["asks"] == [["read:flow:1:reread", "flow_read", "read", "flowRead",
                            "desk-standard"]]
    assert out["gate"] == "flow_conflict"
    assert out["after_reread"] == ["changed_elsewhere", 0, True]
    assert out["gate_after"] == "flow_changed_elsewhere"
    assert out["retry"] == "sha256:" + "a" * 64 and out["retry_status"] == "idle"


def test_a_write_waits_for_the_one_in_flight_and_goes_with_the_fresh_digest():
    out = run_js(CYCLE + """
      const first = picks("desk-standard");
      const second = chosen(first.state, "desk-short");
      const read = lands(second, none("desk-short"));
      const late = wiz.stepWizard(read.state, {type: "answered", ask: first.asks[0],
        result: ok(drafted(d.flows.standard))});
      show({first: asksOf(first), second: asksOf(second), write_waits: read.asks.length,
        after_answer: asksOf(late), body: late.asks[0].body,
        stale_did_not_land: [late.state.cycle.flow, late.state.cycle.flowFor],
        settled: late.state.cycle.settled});
    """, DATA)
    assert out["first"] == [["write:flow:1", "flow", "write", "flow", "desk-standard"]]
    assert out["second"] == [["read:flow:2", "flow_read", "read", "flowRead", "desk-short"]]
    assert out["write_waits"] == 0
    assert out["after_answer"] == [["write:flow:2", "flow", "write", "flow", "desk-short"]]
    assert out["body"]["expected_absent"] is True, "another card's draft digest is not this card's"
    assert out["stale_did_not_land"] == [None, None]
    assert out["settled"] == ["read:flow:1", "read:flow:2", "write:flow:1"]


def test_the_cycle_step_shows_the_answers_budget_and_diagnostics_and_never_its_own_arithmetic():
    out = run_js(CYCLE + """
      const facts = (flow, workflowId) => {
        const written = picks(workflowId);
        return wiz.cycleFacts(answer(written.state, written.asks[0], ok(flow)));
      };
      const odd = structuredClone(d.flows.standard);
      odd.budget.clean.actions = 7;
      odd.budget.worst.seconds = 1;
      const tester = drafted(d.flows.tester);
      show({standard: facts(d.flows.standard, "desk-standard"),
        odd: facts(odd, "desk-standard").budget, tester: facts(tester, "desk-standard"),
        none: wiz.cycleFacts(settled(d.unpinned, {runs: []})),
        wanted: [d.flows.standard.budget, odd.budget]});
    """, {**DATA, "flows": {**FLOWS, "tester": {**FLOWS["tester"],
                                                "workflow_id": "desk-standard"}}})
    standard = FLOWS["standard"]
    assert out["standard"]["budget"] == standard["budget"]
    assert out["standard"]["diagnostics"] == [] and out["standard"]["publishable"] is True
    assert out["standard"]["revisions"] == {"latest": 1, "next": 2}
    assert out["odd"]["clean"]["actions"] == 7 and out["odd"]["worst"]["seconds"] == 1
    assert out["odd"] == out["wanted"][1] and out["odd"] != out["wanted"][0]
    assert [row["code"] for row in out["tester"]["diagnostics"]] == ["return_after_correction"]
    assert out["tester"]["diagnostics"] == FLOWS["tester"]["diagnostics"]
    assert out["none"]["budget"] is None and out["none"]["diagnostics"] == []


def test_a_published_card_offers_make_project_cycle_and_it_is_disabled_until_the_door_is_wired():
    out = run_js(CYCLE + """
      const cards = wiz.cycleCards(settled(d.unpinned));
      const pin = (id) => cards.find((card) => card.id === id).canPin;
      show({standard: pin("desk-standard"), short: pin("desk-short"), saved: pin("old-cycle"),
        build: pin("build"), pinned_card: wiz.cycleCards(settled()).find(
          (card) => card.pinned).canPin,
        later: wiz.isLater("make_project_cycle")});
    """, DATA)
    assert out == {"standard": True, "short": False, "saved": True, "build": False,
                   "pinned_card": False, "later": True}


def test_only_the_pinned_card_offers_unpin_and_it_is_disabled_until_the_door_is_wired():
    out = run_js(CYCLE + """
      const unpin = (state) => Object.fromEntries(wiz.cycleCards(state).map(
        (card) => [card.id, card.canUnpin]));
      show({pinned: unpin(settled()), unpinned: unpin(settled(d.unpinned)),
        starter: unpin(inStarterMode()), later: wiz.isLater("unpin_project_cycle")});
    """, DATA)
    assert out["pinned"] == {"cycle-7c1e5a90": True, "desk-standard": False, "desk-short": False,
                             "old-cycle": False, "build": False}
    assert not any(out["unpinned"].values()), "nothing is pinned, so nothing can be unpinned"
    assert out["starter"] == {"desk-starter-docs": False}, "a locked card offers nothing"
    assert out["later"] is True


def test_every_control_whose_door_is_not_wired_is_named_and_none_is_a_silent_no_op():
    out = run_js(CYCLE + """
      show({later: wiz.LATER, frozen: Object.isFrozen(wiz.LATER),
        wired: ["edit-title", "next", "material-add", "cycle-choose"].map(wiz.isLater)});
    """, DATA)
    assert out["later"] == ["connect_git", "first_commit", "run_without_git", "from_starter_docs",
                            "build_own", "make_project_cycle", "unpin_project_cycle", "prepare"]
    assert out["frozen"] is True and out["wired"] == [False] * 4


def test_the_cycle_step_is_complete_only_with_a_chosen_card_whose_flow_landed_and_is_publishable():
    out = run_js(CYCLE + """
      const base = reply(opened(atCycle()), "workflows", d.workflows);
      const asked = chosen(base, "desk-standard");
      const written = picks("desk-standard");
      const gate = (state) => wiz.canAdvance(state).reason;
      const bad = drafted(d.flows.standard, {publishable: false,
        diagnostics: [{code: "final_gate_missing", severity: "error", at: null, params: {}}]});
      const step = (result) => gate(wiz.reduceWizard(written.state,
        {type: "answered", ask: written.asks[0], result}));
      show({none: gate(base), pending: gate(written.state), read_pending: gate(asked.state),
        landed: step(ok(d.flows.standard)), unpublishable: step(ok(bad)),
        refused: step({status: "refused", code: "contract_invalid",
          payload: {diagnostics: bad.diagnostics}}),
        unknown: step({status: "unknown"}),
        wrong_workflow: gate(wiz.reduceWizard(written.state, {type: "answered",
          ask: written.asks[0], result: ok(d.flows.short)})),
        refusal: wiz.reduceWizard(written.state, {type: "answered", ask: written.asks[0],
          result: {status: "refused", code: "contract_invalid",
            payload: {diagnostics: bad.diagnostics}}}).cycle.refusal});
    """, DATA)
    assert out["none"] == "cycle_none" and out["pending"] == "flow_pending"
    assert out["read_pending"] == "flow_pending"
    assert out["landed"] is None and out["unpublishable"] == "flow_unpublishable"
    assert out["refused"] == "flow_refused" and out["unknown"] == "flow_unknown"
    assert out["wrong_workflow"] == "flow_refused"
    assert out["refusal"]["code"] == "contract_invalid"
    assert out["refusal"]["diagnostics"][0]["code"] == "final_gate_missing"


def test_next_is_enabled_only_when_moving_on_would_not_be_refused_and_names_the_failing_step():
    out = run_js(CYCLE + """
      const ready = () => land(settled(d.unpinned), drafted(d.flows.standard));
      const dropped = (state) => wiz.reduceWizard(state, {type: "reread", name: "git"});
      const gitAnswer = (state, result) => wiz.reduceWizard(state, {type: "answered",
        ask: askOf(state, "git"), result});
      const scenarios = {ready: ready(), git_dropped: dropped(ready()),
        both: dropped(settled(d.unpinned)),
        git_not_repo_root: gitAnswer(dropped(ready()), ok(d.roots)),
        git_unsupported: gitAnswer(dropped(ready()), ok(d.unsupported)),
        git_failed: gitAnswer(dropped(ready()), {status: "refused", code: "store_error"}),
        title_cleared: wiz.reduceWizard(ready(), {type: "edit-title", value: ""})};
      show(Object.fromEntries(Object.entries(scenarios).map(([name, state]) => {
        const gate = wiz.canAdvance(state), after = wiz.reduceWizard(state, {type: "next"});
        return [name, {ok: gate.ok, reason: gate.reason, step: gate.step,
          moved: after.step !== state.step}];
      })));
    """, {**DATA, "roots": fixture("wizard", "git_not_repo_root.json"),
          "unsupported": fixture("wizard", "git_unsupported.json")})
    assert out["ready"] == {"ok": True, "reason": None, "step": "cycle", "moved": True}
    for name, reason, step in (("git_dropped", "git_reading", "materials"),
                               ("both", "flow_pending", "cycle"),
                               ("git_not_repo_root", "git_stops", "materials"),
                               ("git_unsupported", "git_stops", "materials"),
                               ("git_failed", "git_failed", "materials"),
                               ("title_cleared", "title_invalid", "task")):
        assert out[name] == {"ok": False, "reason": reason, "step": step, "moved": False}, name
    assert all(row["ok"] == row["moved"] for row in out.values()), "Next never outruns moveTo"


def test_a_passed_step_whose_gate_fails_again_is_shown_as_needing_attention():
    out = run_js(CYCLE + """
      const ready = land(settled(d.unpinned), drafted(d.flows.standard));
      const lost = wiz.reduceWizard(ready, {type: "reread", name: "git"});
      const rows = (state) => wiz.stepStates(state).map((row) =>
        [row.step, row.status, row.reason]);
      show({ready: rows(ready), lost: rows(lost)});
    """, DATA)
    assert out["ready"][:4] == [["task", "done", None], ["materials", "done", None],
                                ["cycle", "current", None], ["roles", "ready", None]]
    assert out["lost"] == [["task", "done", None], ["materials", "attention", "git_reading"],
                           ["cycle", "current", None], ["roles", "blocked", "git_reading"],
                           ["prepare", "later", None], ["run", "later", None]]


def test_flow_asks_wait_for_the_cycle_step_and_the_cycle_step_publishes_the_next_revision():
    out = run_js(CYCLE + """
      let early = reply(opened(started()), "git", d.git);
      for (const [name, payload] of [["workflows", d.workflows], ["runs", d.runs],
          ["cycle_read", d.unpinned], ["tasks", d.tasks]]) early = reply(early, name, payload);
      const arrived = wiz.stepWizard(early, {type: "next"});
      const read = lands(arrived, none("desk-standard"));
      const landed = answer(read.state, read.asks[0], ok(drafted(d.flows.standard)));
      const rows = wiz.publications(landed, "en");
      show({early_choice: early.cycle.choice, early_asks: wiz.wantedAsks(early)
          .filter((ask) => ask.door === "write" || ask.name === "flow_read").length,
        on_arrival: asksOf(arrived), steps: rows.map((row) => row.step),
        before_the_flow_landed: wiz.publications(arrived.state, "en").map((row) => row.step),
        flow_write: rows.find((row) => row.step === "cycle")});
    """, DATA)
    assert out["early_choice"] == {"kind": "starter", "workflowId": "desk-standard"}
    assert out["early_asks"] == 0
    assert out["on_arrival"] == [
        ["read:flow:1", "flow_read", "read", "flowRead", "desk-standard"],
        ["read:run:task-b-r1", "previous_run", "read", "run", "task-b-r1"],
        ["read:revision:desk-standard:1", "previous_revision", "read", "revision",
         "desk-standard"]]
    assert out["steps"][:3] == ["task", "materials", "cycle"]
    assert out["before_the_flow_landed"] == ["task", "materials"]
    assert out["flow_write"] == {"step": "cycle", "writes": [
        {"link": 3, "target": "flow", "workflow_id": "desk-standard",
         "body": {"source": {"starter_id": "desk-standard"},
                  "expected_digest": "sha256:" + "a" * 64, "publish_revision": 2,
                  "binding": None}}]}
