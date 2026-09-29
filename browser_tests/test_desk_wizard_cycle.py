"""The wizard's step 3 ("Цикл") on the real renderer, in Russian and in English.

The flow answers are lane L's fixtures (`tests/fixtures/flow/`); the reads that choose a card
beforehand are the stand-ins under `tests/fixtures/wizard/`. The page shows the server's numbers
and never adds its own: every figure asserted below is a figure of a fixture.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import expect

from browser_tests.desk_wizard_bench import bench, desk_url, ok, to_step, wizard_reads  # noqa: F401
from tests.desk_wizard_node import fixture

LANGS = ("ru", "en")
FLOW = {name: fixture("flow", f"{name}.flow-state.json") for name in (
    "desk-standard", "desk-short", "desk-starter-docs", "desk-standard-tester")}
PINNED = fixture("wizard", "project_cycle.json")
DIGEST = "sha256:" + "a" * 64
#: What the server would answer for each card: a ready cycle's write, a saved cycle's read.
WRITES = {"desk-standard": ok(FLOW["desk-standard"]), "desk-short": ok(FLOW["desk-short"]),
          "desk-starter-docs": ok(FLOW["desk-starter-docs"])}
READS = {"cycle-7c1e5a90": ok({**FLOW["desk-standard-tester"], "source": "published",
                               "draft_digest": None, "latest_revision": 2, "next_revision": 3}),
         "old-cycle": ok({**FLOW["desk-standard"], "workflow_id": "old-cycle"})}


def reads(**over):
    return wizard_reads(**{"flow": WRITES, "flow_read": READS, **over})


def cards(bench):
    return bench.page.locator("[data-card-id]").evaluate_all(
        "nodes => nodes.map(node => node.dataset.cardId)")


def hm(bench, seconds):
    """How the page says a duration: the format is the page's, the number is the server's."""
    hours, minutes = divmod(round(seconds / 60), 60)
    if hours and minutes:
        return bench.say("wizard.time.hm", hours=str(hours), minutes=str(minutes))
    return bench.say("wizard.time.h", hours=str(hours)) if hours \
        else bench.say("wizard.time.m", minutes=str(minutes))


@pytest.mark.parametrize("lang", LANGS)
def test_a_pinned_cycle_wins_over_the_last_run_and_the_preselection_names_its_source(bench, lang):
    to_step(bench, lang, "cycle", reads=reads(cycle_read=ok(PINNED)))
    assert cards(bench) == ["cycle-7c1e5a90", "desk-standard", "desk-short", "old-cycle", "build"]
    chosen = bench.page.locator('[data-card-id][data-chosen="true"]')
    assert chosen.evaluate_all("nodes => nodes.map(node => node.dataset.cardId)") == [
        "cycle-7c1e5a90"]
    label = bench.page.locator("[data-cycle-source]")
    assert label.inner_text() == bench.say(
        "wizard.cycle.source_pinned", by="Вы: Василий", at="2026-09-28 13:50 UTC")
    assert label.get_attribute("data-cycle-source") == "pinned"
    pinned = bench.page.locator('[data-card-id="cycle-7c1e5a90"]')
    assert bench.say("wizard.cycle.pinned") in pinned.inner_text()
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_cycle_cards_carry_their_source_label_and_a_last_run_names_its_task_and_time(bench, lang):
    to_step(bench, lang, "cycle", reads=reads())
    assert cards(bench) == ["desk-standard", "desk-short", "cycle-7c1e5a90", "old-cycle", "build"]
    label = bench.page.locator("[data-cycle-source]")
    assert label.inner_text() == bench.say(
        "wizard.cycle.source_last_run", task="Fix the login form", at="2026-09-28 13:50 UTC")
    assert label.get_attribute("data-cycle-source") == "last_run"
    assert bench.page.locator('[data-card-id="desk-standard"]').get_attribute(
        "data-chosen") == "true"
    names = bench.page.locator("[data-card-id] h4").all_inner_texts()
    assert names[:2] == [bench.say("wizard.cycle.name_standard"),
                         bench.say("wizard.cycle.name_short")]
    assert names[2:4] == ["Standard with a tester", "Old cycle"]
    short = bench.page.locator('[data-card-id="desk-short"]').inner_text()
    assert bench.say("wizard.cycle.unpublished") in short
    assert bench.say("wizard.cycle.revision", number="1") in bench.page.locator(
        '[data-card-id="desk-standard"]').inner_text()


@pytest.mark.parametrize("lang", LANGS)
def test_an_unread_pinned_cycle_says_it_could_not_be_read_and_claims_nothing_more(bench, lang):
    refused = {"status": "refused", "code": "store_error", "payload": None}
    to_step(bench, lang, "cycle", reads=reads(cycle_read=refused))
    assert bench.page.locator("[data-cycle-unread]").inner_text() == bench.say(
        "wizard.cycle.pinned_unread")
    assert not any(bench.page.locator("[data-card-id]").evaluate_all(
        "nodes => nodes.map(node => node.dataset.pinned === 'true')"))
    assert bench.page.locator("[data-cycle-source]").get_attribute("data-cycle-source") == \
        "last_run"


@pytest.mark.parametrize("lang", LANGS)
def test_the_starter_cycle_is_shown_locked_with_no_alternative(bench, lang):
    to_step(bench, lang, "cycle", starter="desk-starter-docs", reads=reads())
    assert cards(bench) == ["desk-starter-docs"], "no other card and no build-your-own"
    card = bench.page.locator('[data-card-id="desk-starter-docs"]')
    assert card.get_attribute("data-locked") == "true"
    assert card.locator("button").count() == 0
    assert bench.say("wizard.cycle.locked") in bench.root().inner_text()
    assert bench.say("wizard.cycle.name_starter_docs") in card.inner_text()
    assert ["write:flow:1", "flow", "desk-starter-docs"] in bench.asks()
    expect(bench.page.locator("[data-budget]")).to_have_count(1)
    assert bench.control("wizard:next").is_enabled()


@pytest.mark.parametrize("lang", LANGS)
def test_choosing_a_card_asks_for_the_flow_and_shows_the_returned_budget_and_diagnostics(
        bench, lang):
    to_step(bench, lang, "cycle", reads=reads())
    standard = FLOW["desk-standard"]["budget"]
    expect(bench.page.locator("[data-budget]")).to_have_count(1)
    clean = bench.page.locator("[data-budget-clean]")
    assert clean.inner_text() == bench.say(
        "wizard.budget.clean", actions=str(standard["clean"]["actions"]),
        time=hm(bench, standard["clean"]["seconds"]))
    assert bench.page.locator("[data-budget-worst]").inner_text() == bench.say(
        "wizard.budget.worst", actions=str(standard["worst"]["actions"]),
        time=hm(bench, standard["worst"]["seconds"]))
    assert bench.page.locator("[data-budget-limit]").inner_text() == bench.say(
        "wizard.budget.limit", actions=str(standard["limits"]["max_actions"]))
    assert bench.page.locator("[data-diag]").count() == 0
    assert bench.page.locator("[data-diag-none]").inner_text() == bench.say("wizard.diag.none")
    bench.control("wizard:cycle:choose:desk-short").click()
    short = FLOW["desk-short"]["budget"]
    expect(bench.page.locator("[data-budget-clean]")).to_have_text(bench.say(
        "wizard.budget.clean", actions=str(short["clean"]["actions"]),
        time=hm(bench, short["clean"]["seconds"])))
    bench.control("wizard:cycle:choose:cycle-7c1e5a90").click()
    row = bench.page.locator('[data-diag="return_after_correction"]')
    expect(row).to_have_count(1)
    assert row.get_attribute("data-severity") == "warning"
    assert bench.say("wizard.diag.warning") in row.inner_text()
    assert bench.say("wizard.diag.return_after_correction") in row.inner_text()
    assert bench.say("wizard.diag.at_step", step="do") in row.inner_text()
    tester = FLOW["desk-standard-tester"]["budget"]
    assert bench.page.locator("[data-budget-worst]").inner_text() == bench.say(
        "wizard.budget.worst", actions=str(tester["worst"]["actions"]),
        time=hm(bench, tester["worst"]["seconds"]))
    writes = [ask for ask in bench.asks() if ask[1] == "flow"]
    assert [ask[2] for ask in writes] == ["desk-standard", "desk-short"]
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_a_diagnostic_with_no_text_here_says_so_and_names_its_code(bench, lang):
    odd = {**FLOW["desk-standard"], "diagnostics": [
        {"code": "made_up_by_the_server", "severity": "warning", "at": None, "params": {}},
        {"code": "dead_join", "severity": "warning", "at": {"link": ["a", "b", "success"]},
         "params": {}}]}
    to_step(bench, lang, "cycle", reads=reads(flow={"desk-standard": ok(odd)}))
    unknown = bench.page.locator('[data-diag="made_up_by_the_server"]')
    expect(unknown).to_have_count(1)
    assert bench.say("wizard.diag.unknown", code="made_up_by_the_server") in unknown.inner_text()
    link = bench.page.locator('[data-diag="dead_join"]').inner_text()
    assert bench.say("wizard.diag.at_link", **{"from": "a", "to": "b"}) in link
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_a_cycle_with_errors_cannot_be_left_and_says_which_check_failed(bench, lang):
    bad = {**FLOW["desk-standard"], "publishable": False, "diagnostics": [
        {"code": "final_gate_missing", "severity": "error", "at": None, "params": {}}]}
    to_step(bench, lang, "cycle", reads=reads(flow={"desk-standard": ok(bad)}))
    row = bench.page.locator('[data-diag="final_gate_missing"]')
    expect(row).to_have_count(1)
    assert row.get_attribute("data-severity") == "error"
    assert bench.control("wizard:next").is_disabled()
    assert bench.page.locator("[data-wizard-reason]").inner_text() == bench.say(
        "wizard.reason.flow_unpublishable")


@pytest.mark.parametrize("lang", LANGS)
def test_a_draft_conflict_tells_the_owner_and_choosing_the_card_again_writes_again(bench, lang):
    conflict = {"status": "refused", "code": "draft_conflict", "payload": None}
    drafted = ok({**FLOW["desk-standard"], "source": "draft", "draft_digest": DIGEST})
    to_step(bench, lang, "cycle", reads=reads(
        flow={"desk-standard": conflict}, flow_read={"desk-standard": drafted}))
    expect(bench.page.locator("[data-flow-status]")).to_have_attribute(
        "data-flow-status", "changed_elsewhere")
    assert bench.say("wizard.flow.changed") in bench.root().inner_text()
    assert bench.control("wizard:next").is_disabled()
    assert bench.wizard()["cycle"]["choice"]["workflowId"] == "desk-standard", "the card is kept"
    bench.call("dispatch", {"type": "cycle-choose", "id": "desk-standard"})
    writes = [ask for ask in bench.asks() if ask[1] == "flow"]
    assert len(writes) == 2 and writes[1][0] != writes[0][0]
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_a_published_card_offers_make_project_cycle_and_it_is_disabled_with_its_reason(bench, lang):
    to_step(bench, lang, "cycle", reads=reads())
    pin = bench.control("wizard:cycle:pin:desk-standard")
    assert pin.is_disabled()
    why = bench.page.locator('[data-blocked="wizard:cycle:pin:desk-standard"] small')
    assert why.inner_text() == bench.say("wizard.later.make_project_cycle")
    assert bench.control("wizard:cycle:pin:desk-short").count() == 0, "not published yet"
    assert bench.control("wizard:cycle:pin:old-cycle").is_disabled()
    build = bench.control("wizard:cycle:build")
    assert build.is_disabled()
    assert bench.page.locator('[data-blocked="wizard:cycle:build"] small').inner_text() == \
        bench.say("wizard.later.build_own")
    before = bench.wizard()
    pin.click(force=True)
    assert bench.wizard() == before
