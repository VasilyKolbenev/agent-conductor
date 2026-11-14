"""What the hub page says of an operation it follows after a press (spec 4.1.8, 4.6.4, 8.7).

A press of «Восстановить», of «Восстановить вход» or of «Применить профиль» is answered `202
{operation_id}`; the page follows `GET /hub/operations/<id>` and says how the row ends. `hub-ops.js`
holds that as values: a row to the sentence it is told in, and a follower that reads the row by id
through a door and a scheduler it is handed (so the sequences are run here with a fake of each, no
browser and no clock). The rules are lane H's handoff (`H-to-D2-hub-handlers-live.md`):

- a failed `recover` / `recover_login` row says the sentence of its `detail.reason`
  (`hub.reason.<kind>.<reason>`), never the bare words of `hub.code.recovery_required` or
  `hub.state.recovery_required`, and a reason the closed list does not know is the `not_proven`
  sentence, never restart advice;
- a failed `providers` row whose reason is `recovery_required` says `hub.reason.recovery_required`;
- nothing a command printed is ever said: the page reads one closed word and no text;
- the same operation again (a login recovery pressed twice answers the SAME id) opens no second row.
"""
from __future__ import annotations

from typing import Any

from conductor.hub import refusals
from tests.desk_wizard_node import run_js

MODULES = {"ops": "hub-ops.js", "copy": "hub-copy.js"}
KINDS = ("recover", "recover_login")
RESTART_CODE = {"recover": "recovery_required", "recover_login": "login_recovery_required"}
REASONS = ("restart_needed", "prepare_needed", "other_environment", "not_proven")
PRELUDE = """
const show = (value) => console.log(JSON.stringify(value));
const row = (kind, over = {}) => ({operation_id: "operation-" + "1".repeat(32), kind, source: null,
  state: "failed", step: kind, project_id: null, code: null, detail: null, result: null, ...over});
const say = (locale, key, params) => copy.hubText(locale, key, params);
const note = (value, locale = "en") => ops.operationNote(value, locale);
const clause = (locale, code) => copy.codeWords(locale, code);
const every = (kinds, reasons, call) => kinds.forEach((kind) => reasons.forEach((reason) =>
  ["en", "ru"].forEach((locale) => call(kind, reason, locale))));
"""
#: The follower under Node: a door that answers what the test queued (or holds the read until the
#: test lets it go), a scheduler that only records, and the two hooks the page gives it.
FOLLOWER = """
const calls = [], timers = [], settled = [], changes = [], held = [];
const queue = [];
const door = {
  read: (name, params) => {
    calls.push([name, params.operation]);
    const next = queue.shift();
    if (typeof next !== "function") return Promise.resolve(next);
    return new Promise((resolve) => held.push(() => resolve(next())));
  },
  schedule: (call, ms) => {
    const timer = {call, ms, live: true};
    timers.push(timer);
    return timer;
  },
  cancel: (timer) => { if (timer) timer.live = false; },
  changed: () => { changes.push(1); },
  settled: (event) => { settled.push(event); },
};
const flow = ops.createFollower(door);
const ID = "operation-" + "1".repeat(32), ID2 = "operation-" + "2".repeat(32);
const ok = (payload) => ({status: "accepted", code: null, payload});
const flush = () => new Promise((resolve) => setTimeout(resolve, 0));
const live = () => timers.filter((timer) => timer.live);
const rows = (locale = "en") => flow.rows(locale).map((one) => [one.id, one.kind, one.subject,
  one.phase, one.text]);
"""


def js(body: str, **data: Any) -> Any:
    return run_js(PRELUDE + body, data, modules=MODULES)


def follow(body: str, **data: Any) -> Any:
    return js(FOLLOWER + body, **data)


# -- a row, told in a sentence -------------------------------------------------------------------


def test_the_reasons_a_recovery_can_carry_are_the_closed_list_the_hub_holds():
    held = set(refusals.OPERATION_DETAIL_REASONS) - {"recovery_required"}
    page = js("show(ops.RECOVERY_REASONS);")
    assert set(page) == held == set(REASONS) and len(page) == len(REASONS)
    for word in held:
        assert refusals.OPERATION_DETAIL_REASONS[word] == frozenset(RESTART_CODE.values()), word
    for kind, code in RESTART_CODE.items():
        assert code in refusals.OPERATION_CODES_BY_STEP[kind], kind


def test_a_failed_recovery_that_carries_a_reason_says_the_sentence_of_that_reason():
    out = js("""
      const said = {};
      every(d.kinds, d.reasons, (kind, reason, locale) => {
        const got = note(row(kind, {code: d.restart[kind], detail: {reason}}), locale);
        said[[kind, reason, locale].join("/")] = [got.phase, got.text,
          say(locale, `hub.reason.${kind}.${reason}`)];
      });
      show(said);
    """, kinds=KINDS, reasons=REASONS, restart=RESTART_CODE)
    assert len(out) == 16
    for key, (phase, text, wanted) in out.items():
        assert (phase, text) == ("failed", wanted), key
    assert len({text for _phase, text, _wanted in out.values()}) == 16, (
        "each kind, reason and language has a sentence of its own")


def test_the_bare_words_of_a_restart_are_never_said_for_a_recovery_that_carries_a_reason():
    out = js("""
      const bare = (locale) => [say(locale, "hub.state.recovery_required"),
        clause(locale, "recovery_required"), clause(locale, "login_recovery_required")];
      const found = [];
      every(d.kinds, d.reasons, (kind, reason, locale) => {
        const text = note(row(kind, {code: d.restart[kind], detail: {reason}}), locale).text;
        bare(locale).filter((words) => text.includes(words)).forEach(
          (words) => found.push([kind, reason, words]));
      });
      show({found, bare: bare("en")});
    """, kinds=KINDS, reasons=REASONS, restart=RESTART_CODE)
    assert out["found"] == [], out["found"]
    assert all(len(words) > 20 for words in out["bare"]), "the check compares real sentences"


def test_a_reason_the_closed_list_does_not_know_is_the_not_proven_sentence_never_restart_advice():
    out = js("""
      const odd = [null, {}, {reason: "reboot_twice"}, {reason: 7}, "restart_needed",
        {reason: "restart_needed ", extra: 1}, {Reason: "restart_needed"}];
      const said = {};
      every(d.kinds, ["any"], (kind, _any, locale) => {
        const code = d.restart[kind];
        said[kind + "/" + locale] = {
          unknown: odd.map((detail) => note(row(kind, {code, detail}), locale).text),
          proven: say(locale, `hub.reason.${kind}.not_proven`),
          restart: say(locale, `hub.reason.${kind}.restart_needed`)};
      });
      show(said);
    """, kinds=KINDS, restart=RESTART_CODE)
    for key, said in out.items():
        assert set(said["unknown"]) == {said["proven"]}, key
        assert said["proven"] != said["restart"], key


def test_a_recovery_that_failed_for_another_code_says_the_clause_of_that_code():
    out = js("""
      const cases = [["recover", "recovery_refused", null],
        ["recover", "transition_conflict", null], ["recover", "ownership_lost", null],
        ["recover", "subprocess_failed", null], ["recover_login", "login_owner_busy", null],
        ["recover_login", "login_ownership_invalid", null],
        ["recover_login", "login_context_required", null],
        ["recover", "recovery_refused", {reason: "restart_needed"}],
        ["recover_login", "login_owner_busy", {reason: "prepare_needed"}],
        ["recover", null, null]];
      show(["en", "ru"].map((locale) => cases.map(([kind, code, detail]) => [
        note(row(kind, {code, detail}), locale).text,
        say(locale, "hub.op.failed", {reason: clause(locale, code)})])));
    """)
    for pairs in out:
        for text, wanted in pairs:
            assert text == wanted


def test_a_failed_profile_copy_names_the_recovery_it_needs_and_otherwise_says_its_code():
    out = js("""
      const needs = (locale) => note(row("providers", {code: "subprocess_failed",
        detail: {reason: "recovery_required"}}), locale).text;
      const codes = ["profile_absent", "profile_invalid", "owner_busy", "stop_uncertain",
        "start_timeout", "subprocess_failed"];
      show({needs: ["en", "ru"].map(needs),
        wanted: ["en", "ru"].map((locale) => say(locale, "hub.reason.recovery_required")),
        subprocess: ["en", "ru"].map((locale) => clause(locale, "subprocess_failed")),
        codes: ["en", "ru"].map((locale) => codes.map((code) => [
          note(row("providers", {code}), locale).text,
          say(locale, "hub.op.failed", {reason: clause(locale, code)})])),
        elsewhere: note(row("providers", {code: "owner_busy",
          detail: {reason: "restart_needed"}})).text,
        owner: say("en", "hub.op.failed", {reason: clause("en", "owner_busy")})});
    """)
    assert out["needs"] == out["wanted"]
    assert all(said not in needed for said, needed in zip(out["subprocess"], out["needs"]))
    for pairs in out["codes"]:
        assert all(text == wanted for text, wanted in pairs)
    assert out["elsewhere"] == out["owner"], "a reason beside a code that H does not pair with it"


def test_a_row_is_running_done_or_failed_and_a_row_the_page_cannot_read_is_none():
    out = js("""
      const kinds = ["recover", "recover_login", "providers"];
      show({running: kinds.map((kind) => note(row(kind, {state: "running"}))),
        done: kinds.map((kind) => note(row(kind, {state: "succeeded"}))),
        ru: kinds.map((kind) => note(row(kind, {state: "succeeded"}), "ru").text),
        none: [note(row("add", {state: "running"})), note(row("recover", {state: "cancelled"})),
          note(row("recover", {state: "paused"})), note(row("recover", {state: undefined})),
          note(null), note("failed"), note([]), note(row("nope", {state: "failed"}))]});
    """)
    assert [(one["phase"], one["key"]) for one in out["running"]] == [
        ("running", "hub.op.running")] * 3
    assert [(one["phase"], one["key"]) for one in out["done"]] == [
        ("done", "hub.op.done.recover"), ("done", "hub.op.done.recover_login"),
        ("done", "hub.op.done.providers")]
    assert len(set(out["ru"])) == 3 and all(any("а" <= char <= "я" for char in text.lower())
                                             for text in out["ru"])
    assert out["none"] == [None] * 8


def test_nothing_a_command_printed_reaches_the_sentence():
    out = js("""
      const planted = {message: "C:\\\\Users\\\\boss\\\\secret", stderr: "secret", path: "secret",
        result: {path: "secret"}};
      const texts = [];
      for (const locale of ["en", "ru"]) {
        texts.push(note(row("recover", {code: "recovery_required", ...planted,
          detail: {reason: "restart_needed", text: "secret", path: "C:\\\\secret"}}), locale));
        texts.push(note(row("recover", {code: "ownership_lost", ...planted}), locale));
        texts.push(note(row("providers", {code: "subprocess_failed", ...planted,
          detail: {reason: "recovery_required", text: "secret"}}), locale));
      }
      show(texts);
    """)
    for said in out:
        assert set(said) == {"phase", "key", "text"}
        assert "secret" not in str(said) and "boss" not in str(said)


# -- the follower: one row per operation, read by id ---------------------------------------------


def test_a_press_is_read_at_once_and_again_while_the_operation_runs():
    out = follow("""
      queue.push(ok(row("recover", {state: "running"})), ok(row("recover", {state: "running"})));
      const started = flow.follow("recover", ID, "web-app");
      await flush();
      const first = {calls: calls.length, rows: rows(), timers: live().map((timer) => timer.ms)};
      live()[0].call();
      await flush();
      show({started, first, calls, second: {calls: calls.length, rows: rows(),
        timers: live().map((timer) => timer.ms)}});
    """)
    assert out["started"] is True
    assert out["calls"] == [["operation", "operation-" + "1" * 32]] * 2
    running = [["operation-" + "1" * 32, "recover", "web-app", "running",
                "The hub is working on it…"]]
    assert out["first"]["rows"] == out["second"]["rows"] == running
    assert out["first"]["calls"] == 1 and out["second"]["calls"] == 2
    assert out["first"]["timers"] == out["second"]["timers"] and len(out["first"]["timers"]) == 1
    assert 1000 <= out["first"]["timers"][0] <= 10000, "a slow net under the stream's frames"


def test_the_same_operation_again_opens_no_second_row_and_asks_for_no_second_read():
    out = follow("""
      queue.push(ok(row("recover_login", {state: "running"})));
      const first = flow.follow("recover_login", ID, "claude-code");
      const again = flow.follow("recover_login", ID, "claude-code");
      await flush();
      show({first, again, calls: calls.length, rows: rows(), changes: changes.length});
    """)
    assert (out["first"], out["again"]) == (True, False)
    assert out["calls"] == 1 and len(out["rows"]) == 1


def test_two_different_operations_are_two_rows_each_read_by_its_own_id():
    out = follow("""
      queue.push(ok(row("recover", {state: "running"})),
        ok(row("recover_login", {state: "running"})));
      flow.follow("recover", ID, "web-app");
      flow.follow("recover_login", ID2, "claude-code");
      await flush();
      show({calls, rows: rows().map((one) => [one[0], one[1], one[2]])});
    """)
    assert out["calls"] == [["operation", "operation-" + "1" * 32],
                            ["operation", "operation-" + "2" * 32]]
    assert [row[1] for row in out["rows"]] == ["recover", "recover_login"]


def test_a_frame_reads_the_operation_at_once_and_takes_over_from_the_timer():
    out = follow("""
      queue.push(ok(row("recover", {state: "running"})), ok(row("recover", {state: "running"})));
      flow.follow("recover", ID, "web-app");
      await flush();
      const before = live().length;
      const first = timers[0];
      flow.touch(ID);
      await flush();
      show({before, calls: calls.length, firstLive: first.live, live: live().length,
        nobody: (flow.touch(ID2), await flush(), calls.length)});
    """)
    assert out["before"] == 1 and out["calls"] == 2
    assert out["firstLive"] is False and out["live"] == 1, "one timer stands, never two"
    assert out["nobody"] == 2, "a frame for an operation nobody follows reads nothing"


def test_a_frame_during_a_read_asks_for_one_more_read_when_it_lands_never_two_at_once():
    out = follow("""
      queue.push(() => ok(row("recover", {state: "running"})),
        ok(row("recover", {state: "running"})));
      flow.follow("recover", ID, "web-app");
      await flush();
      flow.touch(ID);
      flow.touch(ID);
      await flush();
      const during = calls.length;
      held.shift()();
      await flush();
      show({during, after: calls.length, live: live().length});
    """)
    assert (out["during"], out["after"], out["live"]) == (1, 2, 1)


def test_a_lost_answer_is_read_again_and_is_never_a_verdict():
    out = follow("""
      queue.push({status: "unknown", code: null, payload: null},
        ok(row("recover", {state: "succeeded"})));
      flow.follow("recover", ID, "web-app");
      await flush();
      const lost = {rows: rows(), settled: settled.length, timers: live().length};
      live()[0].call();
      await flush();
      show({lost, rows: rows(), settled});
    """)
    assert out["lost"]["settled"] == 0 and out["lost"]["timers"] == 1
    assert [row[3] for row in out["lost"]["rows"]] == ["running"]
    assert out["rows"] == [] and out["settled"] == [
        {"kind": "recover", "phase": "done", "key": "hub.op.done.recover"}]


def test_a_read_the_hub_refuses_ends_the_follow_as_not_reported_and_never_as_failed():
    # The hub keeps 50 rows and forgets them on a restart (spec 4.6.4): its answer is then
    # `operation_not_found` and the outcome shows in the project's row. How it ended is not known.
    out = follow("""
      const codes = ["operation_not_found", "refused", "host_denied"];
      codes.forEach((code) => queue.push({status: "refused", code, payload: null}));
      codes.forEach((_code, at) => flow.follow("recover", "operation-" + String(at + 1).repeat(32),
        "web-app"));
      await flush();
      const word = (locale) => { try { return say(locale, "hub.op.unreported"); } catch (_e) {
        return null; } };
      show({rows: rows(), ru: rows("ru"), settled, timers: live().length,
        calls: calls.length, said: word("en"), saidRu: word("ru"),
        failed: codes.map((code) => say("en", "hub.op.failed", {reason: clause("en", code)}))});
    """)
    assert [row[3] for row in out["rows"]] == ["unreported"] * 3, "the verdict is not failed"
    assert out["settled"] == [{"kind": "recover", "phase": "unreported", "key": None}] * 3
    assert out["timers"] == 0 and out["calls"] == 3, "an ended row is not read again"
    assert out["said"] and out["saidRu"], "the page has its own words for it, in both languages"
    assert [row[4] for row in out["rows"]] == [out["said"]] * 3
    assert [row[4] for row in out["ru"]] == [out["saidRu"]] * 3
    for text in (out["said"].lower(), out["saidRu"].lower()):
        assert "did not finish" not in text and "не завершилось" not in text
    assert all(failed not in out["said"] for failed in out["failed"])


def test_a_succeeded_operation_leaves_no_row_and_a_failed_one_stays_until_it_is_dismissed():
    out = follow("""
      queue.push(ok(row("recover", {state: "succeeded"})),
        ok(row("recover_login", {state: "failed", code: "login_recovery_required",
          detail: {reason: "prepare_needed"}})));
      flow.follow("recover", ID, "web-app");
      flow.follow("recover_login", ID2, "claude-code");
      await flush();
      const stands = rows(), russian = rows("ru");
      flow.dismiss(ID2);
      show({stands, russian, left: rows(), settled, timers: live().length,
        sentence: say("en", "hub.reason.recover_login.prepare_needed"),
        sentenceRu: say("ru", "hub.reason.recover_login.prepare_needed")});
    """)
    [row] = out["stands"]
    assert row == ["operation-" + "2" * 32, "recover_login", "claude-code", "failed",
                   out["sentence"]]
    assert out["russian"][0][4] == out["sentenceRu"], "the sentence follows the language"
    assert out["left"] == [] and out["timers"] == 0
    assert out["settled"] == [{"kind": "recover", "phase": "done", "key": "hub.op.done.recover"},
                              {"kind": "recover_login", "phase": "failed", "key": None}]


def test_an_answer_that_lands_after_the_row_was_dismissed_changes_nothing():
    out = follow("""
      queue.push(() => ok(row("recover", {state: "failed", code: "ownership_lost"})));
      flow.follow("recover", ID, "web-app");
      await flush();
      flow.dismiss(ID);
      held.shift()();
      await flush();
      show({rows: rows(), settled, timers: live().length});
    """)
    assert out == {"rows": [], "settled": [], "timers": 0}


def test_a_row_the_page_cannot_read_ends_the_operation_as_failed_with_no_word_of_its_own():
    out = follow("""
      queue.push(ok({kind: "add", state: "running"}));
      flow.follow("recover", ID, "web-app");
      await flush();
      show({rows: rows(), settled, unknown: clause("en", null)});
    """)
    assert [(row[3], row[4]) for row in out["rows"]] == [
        ("failed", f"Did not finish: {out['unknown']}.")]
    assert out["settled"] == [{"kind": "recover", "phase": "failed", "key": None}]
