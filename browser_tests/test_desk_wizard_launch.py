"""The wizard's step 6 ("Запуск"): the terms card and its buttons, in Russian and in English.

The chain of step 5 runs against the fake server of `desk_wizard_server.py`; the card's own doors
(the queue, the grant, the repeated preview, the two writes) are the fake of
`desk_wizard_queue.py`, which keeps a memory: a repeated write finds what stands, a lost answer
lands unheard, a refusal comes on demand and may leave another slot behind. The clock is the
test's: the wizard reads none, so a test moves it with `bench.tick` and waits for the read the
move causes before it moves it again. What is asserted is what the page says and does and what the
doors were sent; the model's own rules are `tests/test_desk_wizard_launch.py` and
`tests/test_desk_wizard_run_step.py`.
"""
from __future__ import annotations

import copy

import pytest
from playwright.sync_api import expect

from browser_tests import desk_wizard_queue as queue_door
from browser_tests import desk_wizard_server as server
from browser_tests.desk_wizard_bench import (  # noqa: F401
    NO_DRAFTS, bench, desk_url, ok, to_step, wizard_reads)
from tests.desk_wizard_node import fixture

LANGS = ("ru", "en")
FLOWS = {name: fixture("flow", f"{name}.flow-state.json") for name in (
    "desk-standard", "desk-short", "desk-starter-docs")}
STANDARD = fixture("wizard", "preview_standard.json")
CLOCK = "2026-09-29T10:00:30Z"
PLAIN = {"authorization_id", "authorized_by", "preview_digest", "supersedes", "terms"}
START = "wizard:launch:start"
ENQUEUE = "wizard:launch:enqueue"
SKIP = "wizard:launch:skip"
SKIP_YES = "wizard:launch:skip-confirm"
SKIP_NO = "wizard:launch:skip-cancel"
SKIP_ACK = "wizard:launch:skip-ack"
STEPS = ("enqueue", "order", "pause", "resume")


def drafts():
    """The reads the first four steps are drawn from, and the flows the drafts answer."""
    return wizard_reads(flow={name: ok(state) for name, state in FLOWS.items()},
                        flow_read=NO_DRAFTS)


def to_card(bench, lang, *, queue="queue_free", preview=None, actor="vasily", clock=CLOCK,
            view=False, **doors):
    """The wizard on step 6: prepared by the chain, the card drawn, the clock at `clock`.

    `view` opens the wizard on a project that is only being viewed (its git read says so).
    """
    reads = drafts()
    if view:
        reads = wizard_reads(flow={name: ok(state) for name, state in FLOWS.items()},
                             flow_read=NO_DRAFTS, git=ok(fixture("wizard", "git_not_active.json")))
    to_step(bench, lang, "prepare", view=view, reads=reads, opening={"actor": actor})
    server.install(bench, flows=FLOWS, preview=preview)
    queue_door.install(bench, queue=queue, preview=preview, **doors)
    bench.control("wizard:prepare:go").click()
    expect(bench.page.locator('[data-prepare="review"]')).to_be_visible()
    bench.control("wizard:next").click()
    expect(bench.root()).to_have_attribute("data-wizard-current", "run")
    bench.tick(clock)


def hm(bench, seconds):
    minutes = seconds // 60
    return bench.say("wizard.time.hm", hours=str(minutes // 60), minutes=str(minutes % 60))


def at(minutes, seconds=0):
    return f"2026-09-29T10:{minutes:02d}:{seconds:02d}Z"


def countdown(bench):
    return int(bench.page.locator("[data-countdown]").get_attribute("data-countdown"))


def repeats(bench, count):
    """Wait until the fake server has been asked `count` times for the terms again."""
    bench.page.wait_for_function("n => window.host.launchWorld.previews === n", arg=count)


def stored(bench):
    return bench.page.evaluate(
        "() => [window.localStorage.length, window.sessionStorage.length]")


def focused(bench):
    return bench.page.evaluate("() => document.activeElement?.dataset?.focus ?? null")


def why(bench, key):
    return bench.text(f'[data-blocked="{key}"] small')


@pytest.mark.parametrize("lang", LANGS)
def test_step_six_opens_only_from_a_prepared_run_and_next_says_why_before(bench, lang):
    to_step(bench, lang, "prepare", reads=drafts(), opening={"actor": "vasily"})
    server.install(bench, flows=FLOWS)
    queue_door.install(bench)
    assert bench.control("wizard:next").is_disabled()
    assert bench.text("[data-wizard-reason]") == bench.say("wizard.reason.prepare_not_done")
    assert bench.page.locator('[data-wizard-step="run"]').get_attribute("data-status") == "blocked"
    bench.control("wizard:prepare:go").click()
    expect(bench.page.locator('[data-prepare="review"]')).to_be_visible()
    assert bench.control("wizard:next").is_enabled()
    assert bench.page.locator('[data-wizard-step="run"]').get_attribute("data-status") == "ready"
    bench.control("wizard:next").click()
    expect(bench.root()).to_have_attribute("data-wizard-current", "run")
    assert bench.page.locator("[data-launch]").count() == 1
    assert bench.control("wizard:next").count() == 0, "the last step has no Next"
    bench.control("wizard:back").click()
    expect(bench.root()).to_have_attribute("data-wizard-current", "prepare")
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_the_card_draws_the_servers_numbers_line_by_line_for_the_standard_cycle(bench, lang):
    to_card(bench, lang)
    say = bench.say
    assert bench.text("[data-terms-actions]") == say("wizard.launch.actions", max="4", of="8")
    assert bench.text("[data-terms-clean]") == say(
        "wizard.budget.clean", actions="2", time=hm(bench, 5400))
    assert bench.text("[data-terms-worst]") == say(
        "wizard.budget.worst", actions="4", time=hm(bench, 12600))
    assert bench.text("[data-terms-time]") == say("wizard.launch.time", time=hm(bench, 12600))
    assert bench.text("[data-terms-window]") == say("wizard.launch.window", time=hm(bench, 16200))
    assert bench.page.locator("[data-warning]").count() == 0
    rows = bench.page.locator("[data-line=steps] [data-plan-step]")
    assert rows.evaluate_all("nodes => nodes.map(node => node.dataset.planStep)") == [
        "analyst", "do"]
    do = bench.text('[data-plan-step="do"]')
    for part in (say("wizard.role.doer"), "Codex CLI",
                 say("wizard.launch.step_attempts", count="3"),
                 say("wizard.launch.step_timeout", time=say("wizard.time.m", minutes="30"))):
        assert part in do, part
    assert say("wizard.role.analyst") in bench.text('[data-plan-step="analyst"]')
    assert "Claude Code" in bench.text('[data-plan-step="analyst"]')
    harnesses = bench.page.locator("[data-harness]").evaluate_all(
        "nodes => nodes.map(node => node.dataset.harness)")
    assert harnesses == ["claude-code", "codex"]
    assert say("wizard.launch.harness_version", name="Codex CLI (headless, experimental)",
               version="0.157.1") == bench.text('[data-harness="codex"]')
    receives = bench.page.locator("[data-line=receives] [data-receives]").evaluate_all(
        "nodes => nodes.map(node => node.dataset.receives)")
    assert receives == ["input:artifact-brief", "input:artifact-materials", "instruction:do"]
    assert bench.text('[data-receives="input:artifact-brief"]').startswith(
        say("wizard.launch.input_brief"))
    assert bench.text("[data-seed]") == say("wizard.launch.seed_copy", ref="main", commit="abc1234")
    assert countdown(bench) == 270
    assert bench.text("[data-countdown]") == say("wizard.launch.countdown", left="4:30")
    assert stored(bench) == [0, 0], "no browser storage"
    assert {method for method, _ in bench.requests} == {"GET"}
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_the_two_warnings_stand_under_the_actions_when_the_servers_numbers_say_so(bench, lang):
    over = copy.deepcopy(STANDARD)
    over["budget"]["clean"]["actions"] = 9
    over["budget"]["worst"]["actions"] = 10
    to_card(bench, lang, preview=over)
    warnings = bench.page.locator("[data-warning]")
    assert warnings.evaluate_all("nodes => nodes.map(node => node.dataset.warning)") == [
        "clean_over_actions", "worst_over_actions"]
    assert warnings.first.inner_text() == bench.say(
        "wizard.launch.warn.clean_over_actions", actions="9", limit="8")
    assert warnings.last.inner_text() == bench.say(
        "wizard.launch.warn.worst_over_actions", actions="10", limit="8")
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_the_countdown_follows_the_hosts_clock_and_at_zero_the_same_terms_are_asked_again(
        bench, lang):
    to_card(bench, lang)
    bench.tick(at(4, 59))
    assert countdown(bench) == 1
    assert queue_door.world(bench)["previews"] == 0
    before = bench.text("[data-line=actions]")
    bench.tick(at(5))
    repeats(bench, 1)
    assert countdown(bench) == 300, "the same digest keeps the card and restarts the countdown"
    assert bench.text("[data-countdown]") == bench.say("wizard.launch.countdown", left="5:00")
    assert bench.text("[data-line=actions]") == before
    assert bench.page.locator("[data-changed-note]").count() == 0
    assert bench.control(START).is_enabled()
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_after_six_repeats_in_a_row_the_owner_alone_refreshes_the_terms(bench, lang):
    to_card(bench, lang)
    for count in range(1, 7):
        bench.tick(at(5 * count))
        repeats(bench, count)
    assert bench.page.locator(f'[data-focus="wizard:launch:refresh"]').count() == 0
    bench.tick(at(35))
    assert queue_door.world(bench)["previews"] == 6, "a seventh repeat is not made by the desk"
    assert countdown(bench) == 0
    assert bench.text("[data-repeats-spent]") == bench.say("wizard.launch.repeats_spent")
    bench.control("wizard:launch:refresh").click()
    repeats(bench, 7)
    assert countdown(bench) == 300
    assert bench.page.locator("[data-repeats-spent]").count() == 0
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_another_digest_replaces_the_card_marks_what_changed_and_holds_the_buttons(bench, lang):
    change = {"preview_digest": "sha256:" + "5ca1ab1e" * 8, "terms": {"max_actions": 3}}
    to_card(bench, lang, overrides=[change])
    bench.tick(at(5))
    repeats(bench, 1)
    assert bench.text("[data-terms-actions]") == bench.say("wizard.launch.actions", max="3", of="8")
    assert bench.page.locator("[data-line=actions]").get_attribute("data-changed") == "true"
    assert bench.page.locator("[data-line=time]").get_attribute("data-changed") is None
    assert bench.text("[data-changed-note] p") == bench.say(
        "wizard.launch.changed", lines=bench.say("wizard.launch.line.actions"))
    assert bench.control(START).is_disabled()
    assert why(bench, START) == bench.say("wizard.launch.why.card_changed")
    bench.control("wizard:launch:seen").click()
    assert bench.page.locator("[data-changed-note]").count() == 0
    bench.control(START).click()
    expect(bench.page.locator('[data-launch-result="started"]')).to_be_visible()
    body = queue_door.world(bench)["authorize_bodies"][0]
    assert body["authorization_id"] == "auth-bench0000-2", "a new card is a new authorization"
    assert body["terms"]["max_actions"] == 3
    assert bench.problems == []


SLOTS = [
    ("queue_free", True, None, False, None),
    ("queue_busy_waiting", None, True, False, "queue"),
    ("queue_busy_running", None, True, False, "queue"),
    ("queue_stuck", None, True, True, "queue"),
    ("queue_view", "project_not_active", True, False, "queue_view"),
    ("queue_owner_required", None, None, False, "owner_required"),
    ("queue_server_stopping", None, None, False, "server_stopping"),
]


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("queue,start,enqueue,release,extra", SLOTS)
def test_each_row_of_the_slot_table_puts_the_buttons_it_names_on_screen(
        bench, lang, queue, start, enqueue, release, extra):
    to_card(bench, lang, queue=queue)
    assert bench.control(START).count() == (1 if start else 0)
    if start is True:
        assert bench.control(START).is_enabled()
        assert bench.control(START).inner_text() == bench.say("wizard.launch.start")
    if start == "project_not_active":
        assert bench.control(START).is_disabled()
        assert why(bench, START) == bench.say("wizard.launch.why.project_not_active")
    assert bench.control(ENQUEUE).count() == (1 if enqueue else 0)
    if enqueue:
        assert bench.control(ENQUEUE).is_enabled()
        assert bench.control(ENQUEUE).inner_text() == bench.say("wizard.launch.enqueue")
    assert (bench.page.locator("[data-launch-release]").count() == 1) is release
    if extra in ("queue", "queue_view"):
        assert bench.text("[data-launch-caption]") == bench.say(f"wizard.launch.caption_{extra}")
    if extra in ("owner_required", "server_stopping"):
        assert bench.text("[data-launch-why]") == bench.say(f"wizard.launch.why.{extra}")
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_starting_writes_one_authorization_of_exactly_five_keys_and_says_started(bench, lang):
    to_card(bench, lang)
    bench.control(START).click()
    expect(bench.page.locator('[data-launch-result="started"]')).to_have_text(
        bench.say("wizard.launch.result_started"))
    held = queue_door.world(bench)
    assert held["authorize_calls"] == 1 and held["enqueue_calls"] == 0
    body = held["authorize_bodies"][0]
    assert set(body) == PLAIN
    assert (body["authorized_by"], body["supersedes"]) == ("vasily", None)
    assert body["authorization_id"] == "auth-bench0000-1"
    assert body["preview_digest"] == STANDARD["preview_digest"]
    assert body["terms"] == STANDARD["terms"]
    assert bench.exit() == {"runId": "task-bench-r1", "stage": "started"}
    assert bench.control(START).count() == 0 and bench.control(ENQUEUE).count() == 0
    assert stored(bench) == [0, 0]
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_a_slot_taken_between_the_read_and_the_press_offers_the_queue_and_never_queues_itself(
        bench, lang):
    taken = {"state": "busy", "run_id": "task-a-r1", "reason_code": "plan_waiting"}
    to_card(bench, lang, refuse={"launch_authorize": {
        "code": "slot_busy", "count": 1, "detail": {"run_id": "task-a-r1"}, "slot": taken}})
    bench.control(START).click()
    expect(bench.page.locator('[data-launch-note="slot_busy"]')).to_have_text(
        bench.say("wizard.launch.note.slot_busy", holder="Add a search box"))
    assert bench.control(START).count() == 0
    assert bench.control(ENQUEUE).is_enabled()
    held = queue_door.world(bench)
    assert (held["authorize_calls"], held["enqueue_calls"]) == (1, 0)
    assert held["reads"]["queue"] == 2, "the queue is read again after the refusal"
    bench.control(ENQUEUE).click()
    expect(bench.page.locator('[data-launch-result="queued"]')).to_have_text(
        bench.say("wizard.launch.result_queued", position="1"))
    held = queue_door.world(bench)
    assert held["enqueue_calls"] == 1
    body = held["enqueue_bodies"][0]
    assert set(body) == {"run_id", "start"} and body["run_id"] == "task-bench-r1"
    assert set(body["start"]) == PLAIN
    assert held["queue"]["entries"][0]["state"] == "preauthorized"
    assert bench.exit() == {"runId": "task-bench-r1", "stage": "queued"}
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_a_replacement_grant_says_what_the_earlier_ones_spent(bench, lang):
    replacing = fixture("wizard", "preview_replacing.json")
    to_card(bench, lang, preview=replacing)
    expected = bench.say("wizard.launch.actions_spent", max=str(replacing["terms"]["max_actions"]),
                         of="8", spent=str(replacing["budget"]["spent"]["actions"]))
    assert bench.text("[data-terms-actions]") == expected
    assert bench.control(START).is_enabled()
    assert bench.page.locator("[data-exhausted]").count() == 0
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_an_exhausted_run_says_so_and_neither_button_can_be_pressed(bench, lang):
    exhausted = fixture("wizard", "preview_exhausted.json")
    to_card(bench, lang, preview=exhausted)
    spent = str(exhausted["budget"]["spent"]["actions"])
    assert bench.text("[data-exhausted]") == bench.say("wizard.launch.exhausted", spent=spent,
                                                       of="8")
    assert bench.control(START).is_disabled()
    assert why(bench, START) == bench.say("wizard.launch.why.exhausted")
    assert queue_door.world(bench)["authorize_calls"] == 0
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_in_a_viewed_project_start_is_disabled_and_the_queue_entry_keeps_the_wizard_open(
        bench, lang):
    to_card(bench, lang, queue="queue_view", view=True)
    assert bench.root().get_attribute("data-mode") == "view"
    assert bench.control(START).is_disabled()
    assert why(bench, START) == bench.say("wizard.launch.why.project_not_active")
    bench.control(ENQUEUE).click()
    expect(bench.page.locator('[data-launch-result="queued"]')).to_have_text(
        bench.say("wizard.launch.result_queued_view"))
    held = queue_door.world(bench)
    assert held["authorize_calls"] == 0, "a viewed project never authorizes"
    assert held["queue"]["entries"][0]["reason_code"] == "project_not_active"
    assert bench.exit() is None and bench.left() == [0, None]
    assert bench.text("[data-launch-flag]") == bench.say("wizard.launch.caption_queue_view")
    bench.control("wizard:launch:continue").click()
    assert bench.left() == [1, {"runId": "task-bench-r1", "stage": "continue"}]
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_a_lost_start_is_settled_by_the_reads_and_writes_nothing_twice(bench, lang):
    to_card(bench, lang, lose={"launch_authorize": 1})
    bench.control(START).click()
    expect(bench.page.locator('[data-launch-result="started"]')).to_be_visible()
    held = queue_door.world(bench)
    assert held["authorize_calls"] == 1 and len(held["grants"]) == 1
    assert (held["reads"]["queue"], held["reads"]["automation"]) == (2, 2)
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_a_lost_start_that_never_landed_is_pressed_again_with_the_same_authorization_id(
        bench, lang):
    to_card(bench, lang, drop={"launch_authorize": 1})
    bench.control(START).click()
    expect(bench.page.locator('[data-launch-note="not_written"]')).to_have_text(
        bench.say("wizard.launch.note.not_written"))
    assert bench.control(START).is_enabled()
    bench.control(START).click()
    expect(bench.page.locator('[data-launch-result="started"]')).to_be_visible()
    held = queue_door.world(bench)
    ids = {body["authorization_id"] for body in held["authorize_bodies"]}
    assert held["authorize_calls"] == 2 and ids == {"auth-bench0000-1"}
    assert len(held["grants"]) == 1
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("failing,reads", [
    (("launch_queue", "launch_automation"), (2, 2)), (("launch_automation",), (3, 2))])
def test_a_lost_start_whose_deciding_read_fails_says_it_cannot_tell_until_it_is_read_again(
        bench, lang, failing, reads):
    refuse = {name: {"code": "store_error", "count": 1, "after": 1} for name in failing}
    to_card(bench, lang, lose={"launch_authorize": 1}, refuse=refuse)
    bench.control(START).click()
    expect(bench.page.locator("[data-launch-unread]")).to_have_text(
        bench.say("wizard.launch.unknown_unread"))
    assert bench.page.locator('[data-launch-note="not_written"]').count() == 0
    assert bench.page.locator("[data-launch-result]").count() == 0
    if "launch_queue" in failing:
        assert bench.control(START).count() == 0
        assert bench.text("[data-launch-why]") == bench.say("wizard.launch.why.slot_unread")
    else:
        assert bench.control(START).is_disabled()
        assert why(bench, START) == bench.say("wizard.launch.why.lost_unread")
    reread = bench.control("wizard:launch:reread")
    assert reread.inner_text() == bench.say("wizard.launch.reread_lost")
    reread.click()
    expect(bench.page.locator('[data-launch-result="started"]')).to_be_visible()
    held = queue_door.world(bench)
    assert held["authorize_calls"] == 1 and len(held["grants"]) == 1, "nothing was sent twice"
    assert (held["reads"]["queue"], held["reads"]["automation"]) == reads
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_the_owners_name_is_held_to_the_id_grammar_and_survives_the_redraws_of_the_clock(
        bench, lang):
    to_card(bench, lang)
    field = bench.control("wizard:launch:actor")
    field.fill("bad name")
    assert bench.control(START).is_disabled()
    assert why(bench, START) == bench.say("wizard.launch.why.actor_invalid")
    field.fill("")
    bench.type_into("wizard:launch:actor", "Ann.K-2")
    bench.tick(at(1))
    bench.tick(at(1, 1))
    assert field.input_value() == "Ann.K-2" and focused(bench) == "wizard:launch:actor"
    assert bench.control(START).is_enabled()
    bench.control(START).click()
    expect(bench.page.locator('[data-launch-result="started"]')).to_be_visible()
    assert queue_door.world(bench)["authorize_bodies"][0]["authorized_by"] == "Ann.K-2"
    assert stored(bench) == [0, 0], "the name lives in memory only"
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_an_explanation_behind_an_info_mark_stays_open_while_the_clock_redraws(bench, lang):
    to_card(bench, lang)
    assert bench.page.locator("[data-info]").count() == 0
    bench.control("wizard:launch:info:time").click()
    assert bench.text('[data-info="time"]') == bench.say("wizard.launch.time_info")
    bench.control("wizard:launch:info:input:artifact-brief").click()
    assert bench.text('[data-info="input:artifact-brief"]') == bench.say(
        "wizard.launch.digest", digest="0badf00d0bad")
    bench.tick(at(1))
    bench.tick(at(1, 1))
    assert bench.page.locator("[data-info]").count() == 2
    bench.control("wizard:launch:info:time").click()
    assert bench.page.locator("[data-info]").count() == 1
    assert bench.problems == []


def skips(bench):
    """How many times each of the four writes of "skip ahead" was sent."""
    return queue_door.world(bench)["skips"]


def steps(bench):
    """The status the page gives each step of the press, in order."""
    return bench.page.locator("[data-skip-steps] [data-skip-step]").evaluate_all(
        "nodes => nodes.map(node => [node.dataset.skipStep, node.dataset.status])")


def press_skip(bench):
    bench.control(SKIP).click()
    bench.control(SKIP_YES).click()


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("queue,over,shown", [
    ("queue_busy_waiting", None, True),
    ("queue_busy_waiting", {"state": "running", "reason_code": None}, False),
    ("queue_busy_running", None, False),
    ("queue_stuck", None, False),
    ("queue_free", None, False),
    ("queue_view", None, False),
])
def test_skip_ahead_is_offered_only_beside_a_holder_that_waits_for_a_human(
        bench, lang, queue, over, shown):
    to_card(bench, lang, queue=queue, holder_over=over, view=queue == "queue_view")
    assert bench.control(SKIP).count() == (1 if shown else 0)
    if shown:
        assert bench.control(SKIP).is_enabled()
        assert bench.control(SKIP).inner_text() == bench.say("wizard.launch.skip")
        assert bench.control(ENQUEUE).is_enabled()
    assert sum(skips(bench).values()) == 0
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_the_press_opens_a_dialog_naming_the_holder_and_its_grants_end_and_writes_nothing(
        bench, lang):
    to_card(bench, lang, queue="queue_busy_waiting")
    bench.control(SKIP).click()
    assert bench.text("[data-skip-dialog] p") == bench.say(
        "wizard.launch.skip_dialog", task="Add a search box", until="2026-09-29 13:00 UTC")
    assert bench.control(ENQUEUE).count() == 0, "the ordinary buttons wait behind the dialog"
    assert bench.control(SKIP_YES).inner_text() == bench.say("wizard.launch.skip")
    assert bench.control(SKIP_NO).inner_text() == bench.say("wizard.launch.skip_cancel")
    assert sum(skips(bench).values()) == 0
    bench.control(SKIP_NO).click()
    assert bench.page.locator("[data-skip-dialog]").count() == 0
    assert bench.control(ENQUEUE).is_enabled() and bench.control(SKIP).is_enabled()
    assert sum(skips(bench).values()) == 0
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_one_press_puts_the_new_run_first_and_the_paused_holder_last_in_four_ordered_writes(
        bench, lang):
    to_card(bench, lang, queue="queue_with_entries")
    press_skip(bench)
    expect(bench.page.locator('[data-launch-result="queued"]')).to_have_text(
        bench.say("wizard.launch.result_queued", position="1"))
    held = queue_door.world(bench)
    sent = [row["name"].replace("launch_skip_", "") for row in held["skip_bodies"]]
    assert sent == list(STEPS), "each write once, in order"
    assert [(row["run_id"], row["kind"]) for row in held["queue"]["entries"]] == [
        ("task-bench-r1", "start"), ("task-c-r1", "start"), ("task-d-r1", "start"),
        ("task-a-r1", "resume")]
    assert (held["holder"]["state"], held["holder"]["control"]["control_id"]) == (
        "paused", "pause-bench0000-1")
    enqueue, order, pause, resume = (row["body"] for row in held["skip_bodies"])
    assert set(enqueue) == {"run_id", "start"} and set(enqueue["start"]) == PLAIN
    assert enqueue["start"]["authorization_id"] == "auth-bench0000-1"
    assert order == {"expected_revision": 8,
                     "run_ids": ["task-bench-r1", "task-c-r1", "task-d-r1"]}
    assert held["skip_bodies"][2]["subject"] == "task-a-r1"
    assert set(pause) == {"control_id", "authorization_id", "authorization_digest", "action",
                          "actor", "expected_control_id"}
    assert (pause["action"], pause["actor"], pause["expected_control_id"]) == (
        "pause", "vasily", None)
    assert resume["run_id"] == "task-a-r1"
    assert resume["resume"]["control_id"] == "resume-bench0000-1"
    assert resume["resume"]["expected_control_id"] == "pause-bench0000-1"
    assert steps(bench) == [[name, "done"] for name in STEPS]
    assert (held["authorize_calls"], held["enqueue_calls"]) == (0, 0), "no direct authorize"
    assert bench.exit() == {"runId": "task-bench-r1", "stage": "queued"}
    assert stored(bench) == [0, 0] and {method for method, _ in bench.requests} == {"GET"}
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_a_card_replaced_behind_the_dialog_closes_it_and_the_owner_looks_before_pressing_again(
        bench, lang):
    change = {"preview_digest": "sha256:" + "5ca1ab1e" * 8, "terms": {"max_actions": 3}}
    to_card(bench, lang, queue="queue_busy_waiting", overrides=[change])
    bench.control(SKIP).click()
    expect(bench.page.locator("[data-skip-dialog]")).to_be_visible()
    bench.tick(at(5))
    repeats(bench, 1)
    expect(bench.page.locator("[data-skip-dialog]")).to_have_count(0)
    assert bench.control(SKIP).is_disabled()
    assert why(bench, SKIP) == bench.say("wizard.launch.why.card_changed")
    bench.control("wizard:launch:seen").click()
    assert bench.control(SKIP).is_enabled()
    assert sum(skips(bench).values()) == 0
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_a_pause_that_is_refused_leaves_the_new_run_first_and_the_next_press_starts_at_the_pause(
        bench, lang):
    refuse = {"launch_skip_pause": {"code": "contract_invalid", "count": 1}}
    to_card(bench, lang, queue="queue_with_entries", refuse=refuse)
    press_skip(bench)
    reason = bench.say("wizard.launch.skip_stop.contract_invalid")
    expect(bench.page.locator('[data-skip-stop="contract_invalid"]')).to_have_text(
        bench.say("wizard.launch.skip_stopped", reason=reason))
    assert steps(bench) == [["enqueue", "done"], ["order", "done"], ["pause", "todo"],
                            ["resume", "todo"]]
    assert bench.text("[data-skip-stands]") == bench.say("wizard.launch.skip_stands_first")
    assert bench.text("[data-skip-again]") == bench.say("wizard.launch.skip_again")
    held = queue_door.world(bench)
    assert held["queue"]["entries"][0]["run_id"] == "task-bench-r1"
    assert held["holder"]["state"] == "waiting"
    assert bench.control(ENQUEUE).count() == 0 and bench.exit() is None
    bench.control(SKIP_ACK).click()
    assert bench.page.locator("[data-skip-stop]").count() == 0
    assert bench.control(SKIP).is_enabled()
    press_skip(bench)
    expect(bench.page.locator('[data-launch-result="queued"]')).to_be_visible()
    assert skips(bench) == {"enqueue": 1, "order": 1, "pause": 2, "resume": 1}
    controls = {row["body"]["control_id"] for row in queue_door.world(bench)["skip_bodies"]
                if row["name"] == "launch_skip_pause"}
    assert controls == {"pause-bench0000-1"}, "the same card, the same pause"
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_a_lost_answer_of_the_pause_is_settled_by_the_reads_and_writes_nothing_twice(bench, lang):
    to_card(bench, lang, queue="queue_with_entries", lose={"launch_skip_pause": 1})
    press_skip(bench)
    expect(bench.page.locator('[data-launch-result="queued"]')).to_be_visible()
    assert skips(bench) == {"enqueue": 1, "order": 1, "pause": 1, "resume": 1}
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_a_pause_that_never_landed_is_sent_again_without_repeating_the_earlier_steps(bench, lang):
    to_card(bench, lang, queue="queue_with_entries", drop={"launch_skip_pause": 1})
    press_skip(bench)
    expect(bench.page.locator('[data-launch-result="queued"]')).to_be_visible()
    assert skips(bench) == {"enqueue": 1, "order": 1, "pause": 2, "resume": 1}
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_a_queue_that_changes_twice_is_shown_as_it_stands_and_is_not_reordered_a_third_time(
        bench, lang):
    refuse = {"launch_skip_order": {"code": "queue_changed", "count": 2}}
    to_card(bench, lang, queue="queue_with_entries", refuse=refuse)
    press_skip(bench)
    expect(bench.page.locator('[data-skip-stop="queue_changed"]')).to_be_visible()
    assert skips(bench) == {"enqueue": 1, "order": 2, "pause": 0, "resume": 0}
    assert bench.text("[data-skip-queue] h4") == bench.say("wizard.launch.skip_queue")
    rows = bench.page.locator("[data-skip-queue] li").evaluate_all(
        "nodes => nodes.map(node => node.textContent)")
    assert rows == ["1. Refactor the api", "2. Write the release notes", "3. Fix login"]
    assert bench.page.locator("[data-skip-stands]").count() == 0
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_when_nothing_waits_in_the_queue_the_new_run_is_already_first_and_no_order_is_written(
        bench, lang):
    to_card(bench, lang, queue="queue_busy_waiting")
    press_skip(bench)
    expect(bench.page.locator('[data-launch-result="queued"]')).to_be_visible()
    assert skips(bench) == {"enqueue": 1, "order": 0, "pause": 1, "resume": 1}
    assert steps(bench) == [[name, "done"] for name in STEPS]
    assert bench.problems == []
