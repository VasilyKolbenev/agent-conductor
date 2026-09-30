"""The write chain of the «Схема» (spec 7.1, 7.10, 5.6.3): a cycle is read and written only
through `GET/POST /command/workflows/<id>/flow`, one write at a time.

The chain is a pure function of its state and one event, in the shape of the wizard's model: an
event goes in, a state and the asks that are due come out, and the host that owns the doors
performs each ask and says how it was answered. The stand-ins here answer as the door does (its
`FlowState`, its `draft_conflict`, its `contract_invalid` with rows, a lost answer), so what is
asserted is what a server would hold. The tests run the packaged modules under Node.
"""
from __future__ import annotations

from typing import Any

from tests.desk_wizard_node import fixture, run_js

MODULES = {"write": "desk-flowwrite.js", "edits": "desk-flow-edits.js"}
DATA: dict[str, Any] = {"states": {
    "standard": fixture("flow", "desk-standard.flow-state.json"),
    "tester": fixture("flow", "desk-standard-tester.flow-state.json"),
    "dalio": fixture("flow", "dalio-v5.flow-state.json"),
    "none": fixture("wizard", "flow_state_none.json")}}
PRELUDE = """
const NONCE = "a1b2c3d4e5f60718293a4b5c6d7e8f90";
const D = (letter) => "sha256:" + letter.repeat(64);
const show = (value) => console.log(JSON.stringify(value));
const fresh = () => write.initialWrite({nonce: NONCE});
const fs = (name, id, over = {}) => ({...structuredClone(d.states[name]), workflow_id: id,
  ...over});
const send = (out, event) => write.stepWrite(out.state, event);
const begin = (id, name = "T") => send({state: fresh()}, {type: "open", workflowId: id,
  title: name});
const reply = (out, ask, payload, over = {}) => send(out, {type: "answered", ask,
  result: {status: over.status ?? "accepted", code: over.code ?? null, payload}});
//: The answer of a write that landed: the flow the write carried, under a new digest.
const landed = (ask, digest, over = {}) => fs("tester", ask.subject, {source: "draft",
  flow: ask.body.source.flow, draft_digest: digest, ...over});
const opened = (id = "cycle-x1", name = "tester") => {
  const first = begin(id, "New cycle");
  return {...reply(first, first.asks[0], fs(name, id)), first};
};
const title = (value, id = "do") => ({type: "set-field", nodeId: id, field: "title", value});
const asksOf = (out) => out.asks.map((ask) => [ask.id, ask.name, ask.door, ask.target,
  ask.subject]);
const stepOf = (flow, id) => flow.steps.find((row) => row.step_id === id);
const refusal = (code) => ({status: "refused", code});
"""
DOOR = ["schema_write", "write", "flow"]
READ = ["schema_read", "read", "flowRead"]


def js(body: str) -> Any:
    return run_js(PRELUDE + body, DATA, modules=MODULES)


def test_opening_reads_the_flow_state_and_shows_the_draft_or_the_last_revision_or_a_blank_flow():
    out = js("""
      const first = begin("cycle-x1", "New cycle");
      const draft = reply(first, first.asks[0], fs("tester", "cycle-x1"));
      const shipped = begin("desk-standard");
      const published = reply(shipped, shipped.asks[0], fs("standard", "desk-standard"));
      const blank = begin("cycle-n1", "Мой цикл");
      const none = reply(blank, blank.asks[0], fs("none", "cycle-n1"));
      show({asks: asksOf(first), body: first.asks[0].body, phase: first.state.phase,
        draft: [draft.state.phase, draft.state.digest, draft.state.held.steps.length,
          draft.state.dirty],
        published: [published.state.digest, published.state.held.steps.length,
          published.state.server.source],
        none: [none.state.phase, none.state.held, none.state.digest, none.state.fresh]});
    """)
    assert out["asks"] == [["read:schema:1", *READ, "cycle-x1"]]
    assert out["body"] is None and out["phase"] == "reading"
    assert out["draft"][0] == "ready" and out["draft"][1].startswith("sha256:")
    assert out["draft"][2:] == [6, False]
    assert out["published"] == [None, 4, "published"]
    assert out["none"] == ["ready", {"flow_version": 1, "title": "Мой цикл", "steps": [],
                                     "links": [], "ext": {}}, None, True]


def test_a_wrong_answer_fails_the_read_and_a_stale_ask_changes_nothing():
    out = js("""
      const first = begin("cycle-x1");
      const ask = first.asks[0];
      const bad = (payload, over) => reply(first, ask, payload, over).state;
      const wrong = bad(fs("tester", "cycle-other"));
      const bare = bad({workflow_id: "cycle-x1"});
      const refused = bad(null, refusal("project_mismatch"));
      const lost = bad(null, {status: "unknown"});
      const stale = send(first, {type: "answered", ask: {...ask, id: "read:schema:99"},
        result: {status: "accepted", code: null, payload: fs("tester", "cycle-x1")}});
      show({wrong: [wrong.phase, wrong.error], bare: [bare.phase, bare.error],
        refused: [refused.phase, refused.error], lost: [lost.phase, lost.error],
        stale: [stale.state === first.state, stale.asks.length]});
    """)
    assert out["wrong"] == ["failed", "answer_unreadable"]
    assert out["bare"] == ["failed", "answer_unreadable"]
    assert out["refused"] == ["failed", "project_mismatch"]
    assert out["lost"] == ["failed", "unknown"] and out["stale"] == [True, 0]


def test_the_answer_to_the_read_of_a_cycle_opened_before_changes_nothing_in_the_one_opened_after():
    out = js("""
      const first = begin("cycle-a1", "A");
      const second = send(first, {type: "open", workflowId: "cycle-b2", title: "B"});
      const late = reply(second, first.asks[0], fs("tester", "cycle-a1"));
      const right = reply(late, second.asks[0], fs("none", "cycle-b2"));
      show({ids: [first.asks[0].id, second.asks[0].id],
        late: [late.state === second.state, late.asks.length, late.state.phase,
          late.state.reading?.id ?? null],
        right: [right.state.workflowId, right.state.phase, right.state.held.steps.length]});
    """)
    assert out["ids"][0] != out["ids"][1], "no two reads of one page share an id"
    assert out["late"] == [True, 0, "reading", out["ids"][1]], "the second cycle still waits"
    assert out["right"] == ["cycle-b2", "ready", 0]


def test_a_read_asked_after_a_new_cycle_is_begun_has_an_id_no_earlier_read_of_the_page_had():
    out = js("""
      const first = begin("cycle-a1", "A");
      const began = send(first, {type: "new", from: "empty", title: "N"});
      const check = send(began, {type: "check"});
      const late = reply(check, first.asks[0], fs("tester", "cycle-a1"));
      show({ids: [first.asks[0].id, check.asks[0].id],
        late: [late.state === check.state, late.state.held.steps.length, late.state.workflowId]});
    """)
    assert out["ids"][0] != out["ids"][1], "a new cycle does not start the count again"
    assert out["late"] == [True, 0, "cycle-a1b2c3d4"], "the new cycle's check is not answered by A"


def test_an_answer_naming_another_cycle_than_the_one_open_changes_nothing_under_a_live_id():
    out = js("""
      const reading = begin("cycle-b2", "B");
      const foreign = {...reading.asks[0], subject: "cycle-a1"};
      const read = reply(reading, foreign, fs("tester", "cycle-a1"));
      const one = send(opened(), {type: "edit", edit: title("Mine")});
      const other = {...one.asks[0], subject: "cycle-other"};
      const wrote = reply(one, other, landed(other, D("1")));
      show({read: [read.state === reading.state, read.asks.length],
        write: [wrote.state === one.state, wrote.asks.length]});
    """)
    assert out == {"read": [True, 0], "write": [True, 0]}, "the subject is judged, not only the id"


def test_a_completed_edit_asks_one_write_with_the_last_digest_and_a_closed_body():
    out = js("""
      const ready = opened();
      const one = send(ready, {type: "edit", edit: title("Build")});
      const shipped = begin("cycle-c2");
      const fromShipped = reply(shipped, shipped.asks[0], fs("standard", "cycle-c2"));
      const two = send(fromShipped, {type: "edit", edit: title("Build")});
      const body = one.asks[0].body;
      show({asks: asksOf(one), keys: Object.keys(body).sort(), expected: body.expected_digest,
        digest: ready.state.digest, publish: body.publish_revision, binding: body.binding,
        source: Object.keys(body.source), sent: stepOf(body.source.flow, "do").title,
        state: [one.state.save, one.state.dirty, one.state.phase],
        absent: [Object.keys(two.asks[0].body).sort(), two.asks[0].body.expected_absent]});
    """)
    assert out["asks"] == [["write:schema:2", *DOOR, "cycle-x1"]]
    assert out["keys"] == ["binding", "expected_digest", "publish_revision", "source"]
    assert out["expected"] == out["digest"] and out["publish"] is None and out["binding"] is None
    assert out["source"] == ["flow"] and out["sent"] == "Build"
    assert out["state"] == ["saving", False, "ready"]
    assert out["absent"] == [["binding", "expected_absent", "publish_revision", "source"], True]


def test_the_next_edit_waits_for_the_write_in_flight_and_then_goes_out_with_the_new_digest():
    out = js("""
      const one = send(opened(), {type: "edit", edit: title("Build")});
      const two = send(one, {type: "edit", edit: title("Build again")});
      const first = reply(two, one.asks[0], landed(one.asks[0], D("1")));
      const second = reply(first, first.asks[0], landed(first.asks[0], D("2")));
      show({waiting: [two.asks.length, two.state.dirty, two.state.save],
        after_first: asksOf(first), expected: first.asks[0].body.expected_digest,
        carries: stepOf(first.asks[0].body.source.flow, "do").title,
        held_ahead: stepOf(first.state.held, "do").title,
        final: [second.state.save, second.state.dirty, second.asks.length, second.state.digest,
          stepOf(second.state.held, "do").title]});
    """)
    assert out["waiting"] == [0, True, "saving"], "one write in flight; the edit is kept for later"
    assert out["after_first"] == [["write:schema:3", *DOOR, "cycle-x1"]]
    assert out["expected"] == "sha256:" + "1" * 64
    assert out["carries"] == out["held_ahead"] == "Build again"
    assert out["final"] == ["saved", False, 0, "sha256:" + "2" * 64, "Build again"]


def test_an_older_answer_changes_nothing_and_the_servers_flow_lands_only_when_not_ahead():
    out = js("""
      const one = send(opened(), {type: "edit", edit: title("Build")});
      const alone = reply(one, one.asks[0], landed(one.asks[0], D("1"),
        {flow: {...one.asks[0].body.source.flow, title: "Canonical"}}));
      const stale = send(one, {type: "answered", ask: {...one.asks[0], id: "write:schema:99"},
        result: {status: "accepted", code: null, payload: landed(one.asks[0], D("1"))}});
      show({canonical: alone.state.held.title,
        stale: [stale.state === one.state, stale.asks.length]});
    """)
    assert out["canonical"] == "Canonical", "with nothing newer, the server's own flow is shown"
    assert out["stale"] == [True, 0]


def test_a_draft_conflict_on_a_standing_draft_reads_again_says_so_and_drops_the_unsaved_edit():
    out = js("""
      const one = send(opened(), {type: "edit", edit: title("Mine")});
      const clash = reply(one, one.asks[0], null, refusal("draft_conflict"));
      const theirs = fs("tester", "cycle-x1", {draft_digest: D("9"),
        flow: {...d.states.tester.flow, title: "Theirs"}});
      const seen = reply(clash, clash.asks[0], theirs);
      show({clash: [asksOf(clash), clash.state.save, clash.state.notice],
        seen: [seen.state.held.title, seen.state.digest, seen.state.dirty, seen.state.save,
          seen.asks.length]});
    """)
    assert out["clash"][0] == [["read:schema:3", *READ, "cycle-x1"]]
    assert out["clash"][1] == "conflict"
    assert out["clash"][2] == {"key": "schema.write.conflict"}, "«Цикл изменён в другом окне»"
    assert out["seen"] == ["Theirs", "sha256:" + "9" * 64, False, "conflict", 0]


def test_a_conflict_on_a_fresh_own_ids_first_write_takes_the_next_id_and_the_same_flow():
    out = js("""
      let now = begin("cycle-a1b2c3d4");
      now = reply(now, now.asks[0], fs("none", "cycle-a1b2c3d4"));
      let each = send(now, {type: "edit", edit: {type: "add", kind: "agent", roleKind: "analyst"}});
      const rows = [[each.asks[0].subject, each.asks[0].body.expected_absent,
        each.asks[0].body.expected_digest ?? null]];
      const first = JSON.stringify(each.asks[0].body.source.flow);
      let same = true;
      for (let at = 0; at < 4; at += 1) {
        each = reply(each, each.asks[0], null, refusal("draft_conflict"));
        if (each.asks.length === 0) break;
        same = same && JSON.stringify(each.asks[0].body.source.flow) === first;
        rows.push([each.asks[0].subject, each.asks[0].body.expected_absent]);
      }
      show({rows, same, end: [each.state.save, each.state.refusal, each.asks.length,
        each.state.workflowId]});
    """)
    assert [row[0] for row in out["rows"]] == ["cycle-a1b2c3d4", "cycle-e5f60718",
                                               "cycle-293a4b5c", "cycle-6d7e8f90"]
    assert out["rows"][0][1:] == [True, None] and out["same"] is True
    assert out["end"][0] == "refused" and out["end"][1]["code"] == "draft_conflict"
    assert out["end"][2] == 0, "after the four ids the desk stops and says so"


def test_a_lost_answer_is_read_and_settled_by_comparing_and_a_write_is_never_repeated_blind():
    out = js("""
      const one = send(opened(), {type: "edit", edit: title("Mine")});
      const sent = one.asks[0].body.source.flow;
      const lost = reply(one, one.asks[0], null, {status: "unknown"});
      const settle = (payload) => reply(lost, lost.asks[0], payload);
      const did = settle(fs("tester", "cycle-x1", {source: "draft", flow: sent,
        draft_digest: D("2")}));
      const didnt = settle(fs("tester", "cycle-x1"));
      const other = settle(fs("tester", "cycle-x1", {draft_digest: D("9"),
        flow: {...d.states.tester.flow, title: "Theirs"}}));
      show({lost: [asksOf(lost), lost.state.save],
        landed: [did.asks.length, did.state.save, did.state.digest, did.state.dirty],
        not_landed: [asksOf(didnt), didnt.asks[0].body.expected_digest,
          JSON.stringify(didnt.asks[0].body.source.flow) === JSON.stringify(sent),
          didnt.state.save],
        other: [other.asks.length, other.state.save, other.state.held.title]});
    """)
    assert out["lost"] == [[["read:schema:3", *READ, "cycle-x1"]], "unknown"]
    assert out["landed"] == [0, "saved", "sha256:" + "2" * 64, False]
    assert out["not_landed"][0] == [["write:schema:4", *DOOR, "cycle-x1"]]
    assert out["not_landed"][2:] == [True, "saving"]
    assert out["not_landed"][1].startswith("sha256:"), "written again under the read's digest"
    assert out["other"] == [0, "conflict", "Theirs"], "another window's draft is not overwritten"


def test_a_lost_answer_whose_settling_read_failed_too_is_read_again_before_the_next_write():
    out = js("""
      const ready = opened();
      const one = send(ready, {type: "edit", edit: title("Mine")});
      const sent = one.asks[0].body.source.flow;
      const lost = reply(one, one.asks[0], null, {status: "unknown"});
      const failed = reply(lost, lost.asks[0], null, {status: "unknown"});
      const next = send(failed, {type: "edit", edit: title("Next")});
      const checked = send(failed, {type: "check"});
      const saved = send(failed, {type: "save"});
      const did = reply(next, next.asks[0], fs("tester", "cycle-x1", {source: "draft", flow: sent,
        draft_digest: D("2")}));
      const didnt = reply(next, next.asks[0], fs("tester", "cycle-x1"));
      const written = (out) => [asksOf(out), out.asks[0]?.body?.expected_digest ?? null,
        out.asks[0]?.body?.source?.flow ? stepOf(out.asks[0].body.source.flow, "do").title : null];
      show({failed: [failed.state.lost !== null, failed.state.notice, failed.asks.length,
        failed.state.save], next: [asksOf(next), next.state.dirty], checked: asksOf(checked),
        saved: asksOf(saved), landed: written(did), not_landed: written(didnt),
        digests: [ready.state.digest, D("2")]});
    """)
    assert out["failed"] == [True, {"key": "schema.write.check_failed"}, 0, "unknown"]
    assert out["next"] == [[["read:schema:4", *READ, "cycle-x1"]], True], (
        "the flow is read and compared first: a write that may have landed is not written over")
    assert out["checked"] == [["read:schema:4", *READ, "cycle-x1"]]
    assert out["saved"] == [], "nothing is unsaved but the answer that was lost"
    assert out["landed"] == [[["write:schema:5", *DOOR, "cycle-x1"]], out["digests"][1], "Next"], (
        "what landed is kept and the next edit goes out under the digest the read gave")
    assert out["not_landed"] == [[["write:schema:5", *DOOR, "cycle-x1"]], out["digests"][0],
                                 "Next"], "what did not land is written again under its digest"


def test_a_lost_publication_whose_settling_read_failed_too_is_read_before_it_is_confirmed_again():
    out = js(SAVED + """
      const asked = send(saved, {type: "publish-request"});
      const confirm = send(asked, {type: "publish-confirm"});
      const lost = reply(confirm, confirm.asks[0], null, {status: "unknown"});
      const failed = reply(lost, lost.asks[0], null, {status: "unknown"});
      const again = send(failed, {type: "publish-confirm"});
      const waiting = send(lost, {type: "publish-confirm"});
      show({again: asksOf(again), waiting: asksOf(waiting), open: failed.state.publishing});
    """)
    assert out["again"] == [["read:schema:5", *READ, "cycle-x1"]], (
        "a publication whose answer was lost is not repeated blind")
    assert out["waiting"] == [], "while the settling read is out, a second confirm asks nothing"
    assert out["open"] == {"revision": 1}, "the review stays open: nothing is known yet"


def test_editing_a_shipped_cycle_writes_only_a_copy_under_a_new_cycle_id():
    out = js("""
      const shipped = begin("desk-standard");
      const ready = reply(shipped, shipped.asks[0], fs("standard", "desk-standard"));
      const one = send(ready, {type: "edit", edit: title("Mine")});
      const done = reply(one, one.asks[0], fs("tester", one.asks[0].subject,
        {flow: one.asks[0].body.source.flow, draft_digest: D("1"), source: "draft"}));
      const more = send(done, {type: "edit", edit: title("More")});
      const body = one.asks[0].body;
      show({ask: [one.asks[0].subject, body.expected_absent, body.expected_digest ?? null,
        Object.keys(body.source)], origin: one.state.origin,
        id: [ready.state.workflowId, one.state.workflowId],
        next: [more.asks[0].subject, more.asks[0].body.expected_digest],
        subjects: [one, more].map((out) => out.asks[0].subject)});
    """)
    assert out["ask"] == ["cycle-a1b2c3d4", True, None, ["flow"]]
    assert out["origin"] == {"workflowId": "desk-standard", "revision": 1}
    assert out["id"] == ["desk-standard", "cycle-a1b2c3d4"]
    assert out["next"] == ["cycle-a1b2c3d4", "sha256:" + "1" * 64]
    assert "desk-standard" not in out["subjects"]


def test_a_new_cycle_from_a_starter_or_a_copy_is_written_by_its_source_into_a_new_id():
    out = js("""
      const start = send({state: fresh()}, {type: "new", from: "starter", id: "dalio-v5"});
      const done = reply(start, start.asks[0], fs("dalio", start.asks[0].subject));
      const same = send({state: fresh()}, {type: "new", from: "starter", id: "desk-standard",
        same: true});
      const shipped = begin("desk-standard");
      const ready = reply(shipped, shipped.asks[0], fs("standard", "desk-standard"));
      const copy = send(ready, {type: "new", from: "copy"});
      const noCopy = send(opened("cycle-d1", "tester"), {type: "new", from: "copy"});
      const empty = send(ready, {type: "new", from: "empty", title: "Мой цикл"});
      show({start: [asksOf(start), start.asks[0].body, start.state.save],
        done: [done.state.phase, done.state.held.steps.length === d.states.dalio.flow.steps.length,
          done.state.digest.slice(0, 7), done.state.fresh],
        same: [same.asks[0].subject, same.asks[0].body.source],
        copy: [copy.asks[0].subject, copy.asks[0].body.source, copy.asks[0].body.expected_absent],
        no_copy: [noCopy.asks.length, noCopy.state.notice],
        empty: [empty.asks.length, empty.state.workflowId, empty.state.held.title,
          empty.state.held.steps.length, empty.state.fresh]});
    """)
    assert out["start"][0] == [["write:schema:1", *DOOR, "cycle-a1b2c3d4"]]
    assert out["start"][1] == {"source": {"starter_id": "dalio-v5"}, "expected_absent": True,
                               "publish_revision": None, "binding": None}
    assert out["start"][2] == "saving"
    assert out["done"] == ["ready", True, "sha256:", False]
    assert out["same"] == ["desk-standard", {"starter_id": "desk-standard"}]
    assert out["copy"] == ["cycle-a1b2c3d4", {"copy_of": {"workflow_id": "desk-standard",
                                                          "revision": 1}}, True]
    assert out["no_copy"] == [0, {"key": "schema.write.copy_needs_revision"}]
    assert out["empty"] == [0, "cycle-a1b2c3d4", "Мой цикл", 0, True]


def test_a_flow_built_elsewhere_is_written_into_a_new_cycle_under_a_new_id():
    out = js("""
      const built = d.states.tester.flow;
      const out = send({state: fresh()}, {type: "new", from: "flow", flow: built});
      const done = reply(out, out.asks[0], fs("tester", out.asks[0].subject));
      const none = send({state: fresh()}, {type: "new", from: "flow", flow: null});
      const body = out.asks[0].body;
      show({ask: [asksOf(out), Object.keys(body.source), body.expected_absent,
        JSON.stringify(body.source.flow) === JSON.stringify(built)],
        aliased: body.source.flow === built, state: [out.state.fresh, out.state.save],
        done: [done.state.phase, done.state.fresh, done.state.save], none: none.asks.length});
    """)
    assert out["ask"] == [[["write:schema:1", *DOOR, "cycle-a1b2c3d4"]], ["flow"], True, True]
    assert out["aliased"] is False, "the flow is copied, never shared with the caller"
    assert out["state"] == [True, "saving"] and out["done"] == ["ready", False, "saved"]
    assert out["none"] == 0, "no flow, nothing to write"


SAVED = """
const one = send(opened(), {type: "edit", edit: title("Build")});
const saved = reply(one, one.asks[0], landed(one.asks[0], D("1")));
"""


def test_a_publication_is_a_request_a_confirm_that_writes_the_next_revision_or_a_cancel():
    out = js(SAVED + """
      const asked = send(saved, {type: "publish-request"});
      const cancelled = send(asked, {type: "publish-cancel"});
      const again = send(cancelled, {type: "publish-request"});
      const confirm = send(again, {type: "publish-confirm"});
      const body = confirm.asks[0].body;
      const done = reply(confirm, confirm.asks[0], fs("tester", "cycle-x1", {source: "published",
        draft_digest: null, latest_revision: 1, next_revision: 2,
        published: {revision: 1, created: true}, flow: body.source.flow}));
      show({asked: [asked.asks.length, asked.state.publishing],
        cancelled: [cancelled.asks.length, cancelled.state.publishing],
        body: [body.publish_revision, body.expected_digest, Object.keys(body).sort()],
        done: [done.state.published, done.state.publishing, done.state.digest, done.state.save,
          done.state.server.next_revision],
        idle: send(saved, {type: "publish-confirm"}).asks.length});
    """)
    assert out["asked"] == [0, {"revision": 1}] and out["cancelled"] == [0, None]
    assert out["body"] == [1, "sha256:" + "1" * 64,
                           ["binding", "expected_digest", "publish_revision", "source"]]
    assert out["done"] == [{"revision": 1, "created": True}, None, None, "saved", 2]
    assert out["idle"] == 0, "a confirm with no request writes nothing"


def test_a_publication_waits_for_a_saved_flow_and_refuses_a_flow_the_server_calls_unpublishable():
    out = js(SAVED + """
      const busy = send(one, {type: "publish-request"});
      const blocked = send(reply(one, one.asks[0], landed(one.asks[0], D("1"),
        {publishable: false})), {type: "publish-request"});
      const held = send(saved, {type: "edit", edit: title("More")});
      const open = send(saved, {type: "publish-request"});
      const during = send(open, {type: "edit", edit: title("More")});
      show({busy: [busy.state.publishing, busy.state.notice],
        blocked: [blocked.state.publishing, blocked.state.notice], held: held.state.publishing,
        during: [during.asks.length, during.state.notice, during.state.publishing]});
    """)
    assert out["busy"] == [None, {"key": "schema.write.publish_wait"}]
    assert out["blocked"] == [None, {"key": "schema.write.publish_blocked"}]
    assert out["held"] is None
    assert out["during"] == [0, {"key": "schema.write.publish_open"}, {"revision": 1}]


def test_a_refusal_shows_the_servers_rows_and_only_a_save_or_a_new_edit_writes_again():
    out = js("""
      const row = {code: "flow_invalid", severity: "error", at: null,
        params: {path: "flow.steps[0]"}};
      const one = send(opened(), {type: "edit", edit: title("Mine")});
      const refused = reply(one, one.asks[0], {error: {code: "contract_invalid"},
        diagnostics: [row]}, refusal("contract_invalid"));
      const retry = send(refused, {type: "save"});
      const edited = send(refused, {type: "edit", edit: title("Fixed")});
      const down = reply(one, one.asks[0], null, refusal("server_stopping"));
      const unreadable = reply(one, one.asks[0], {workflow_id: "cycle-x1"});
      show({refused: [refused.state.save, refused.state.refusal, refused.asks.length,
        refused.state.dirty], retry: asksOf(retry), edited: asksOf(edited),
        down: [down.state.save, down.state.refusal],
        unreadable: [unreadable.state.save, unreadable.state.refusal.code],
        idle: send(opened(), {type: "save"}).asks.length});
    """)
    assert out["refused"][0] == "refused" and out["refused"][2:] == [0, True]
    assert out["refused"][1]["code"] == "contract_invalid"
    assert out["refused"][1]["diagnostics"][0]["code"] == "flow_invalid"
    assert out["retry"] == [["write:schema:3", *DOOR, "cycle-x1"]]
    assert out["edited"] == [["write:schema:3", *DOOR, "cycle-x1"]]
    assert out["down"] == ["refused", {"code": "server_stopping", "diagnostics": []}]
    assert out["unreadable"] == ["refused", "answer_unreadable"] and out["idle"] == 0


def test_check_reads_again_only_when_nothing_is_unsaved_and_never_replaces_an_unsaved_edit():
    out = js("""
      const ready = opened();
      const plain = send(ready, {type: "check"});
      const one = send(ready, {type: "edit", edit: title("Mine")});
      const early = send(one, {type: "check"});
      const two = send(early, {type: "edit", edit: title("Mine too")});
      const first = reply(two, one.asks[0], landed(one.asks[0], D("1")));
      const second = reply(first, first.asks[0], landed(first.asks[0], D("2")));
      const rows = [{code: "loop_order", severity: "warning", at: {step_id: "do-fix"},
        params: {}}];
      const read = reply(second, second.asks[0], fs("tester", "cycle-x1", {source: "draft",
        draft_digest: D("2"), flow: first.asks[0].body.source.flow, diagnostics: rows}));
      const failed = reply(second, second.asks[0], null, refusal("store_error"));
      show({plain: asksOf(plain), early: early.asks.length, first: asksOf(first),
        second: asksOf(second), read: [read.state.server.diagnostics.length,
        stepOf(read.state.held, "do").title, read.state.save],
        failed: [failed.state.notice, failed.state.save]});
    """)
    assert out["plain"] == [["read:schema:2", *READ, "cycle-x1"]]
    assert out["early"] == 0, "a write is in flight: the check waits"
    assert [row[1] for row in out["first"]] == ["schema_write"], "the queued edit goes first"
    assert out["second"] == [["read:schema:4", *READ, "cycle-x1"]]
    assert out["read"] == [1, "Mine too", "saved"]
    assert out["failed"][0] == {"key": "schema.write.check_failed"}


def test_no_edit_is_taken_while_the_flow_is_being_read_or_a_publication_is_being_confirmed():
    out = js("""
      const reading = begin("cycle-x1");
      const tried = send(reading, {type: "edit", edit: title("Mine")});
      const ready = opened();
      const nothing = send(ready, {type: "teleport"});
      show({reading: [tried.asks.length, tried.state.held, tried.state.notice],
        unknown: [nothing.state === ready.state, nothing.asks.length]});
    """)
    assert out["reading"] == [0, None, {"key": "schema.write.edit_wait"}]
    assert out["unknown"] == [True, 0], "an event that is not in the table changes nothing"


def test_every_body_the_chain_writes_is_a_member_of_the_closed_write_shape():
    out = js("""
      const shape = new Set(["source", "expected_digest", "expected_absent", "publish_revision",
        "binding"]);
      const bodies = [];
      const take = (out) => out.asks.filter((ask) => ask.door === "write")
        .forEach((ask) => bodies.push(ask.body));
      const ready = opened();
      const one = send(ready, {type: "edit", edit: title("Mine")});
      take(one);
      const saved = reply(one, one.asks[0], landed(one.asks[0], D("1")));
      const asked = send(saved, {type: "publish-request"});
      const confirm = send(asked, {type: "publish-confirm"});
      take(confirm);
      take(send({state: fresh()}, {type: "new", from: "starter", id: "dalio-v5"}));
      const fine = bodies.every((body) => Object.keys(body).every((key) => shape.has(key))
        && ("expected_digest" in body) !== ("expected_absent" in body)
        && Object.keys(body.source).length === 1 && body.binding === null);
      show({count: bodies.length, fine});
    """)
    assert out == {"count": 3, "fine": True}
