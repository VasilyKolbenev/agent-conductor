"""The wizard's step 4 ("Роли и указания") and the starter journey, on the real renderer, RU and EN.

The roster, quotas and last run are the stand-in reads under `tests/fixtures/wizard/` (the provider
rows carry `capabilities`, `task_channel` and `offered`); the flows are lane L's fixtures. What
the model decides is in `tests/test_desk_wizard_roles.py`; what is drawn from it is here.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import expect

from browser_tests.desk_wizard_bench import bench, desk_url, ok, to_step, wizard_reads  # noqa: F401
from tests.desk_wizard_node import fixture

LANGS = ("ru", "en")
FLOW = {name: fixture("flow", f"{name}.flow-state.json") for name in (
    "desk-standard", "desk-starter-docs", "desk-standard-tester")}
TESTER = FLOW["desk-standard-tester"]
PINNED = fixture("wizard", "project_cycle.json")
SAVED = {**TESTER, "source": "published", "draft_digest": None, "latest_revision": 2,
         "next_revision": 3}
WITH_TESTER = {**TESTER, "workflow_id": "desk-standard"}


#: The last run's two reads. Left out by default: with them a role the last run did not have is
#: left to assign, which is the point of one test and a distraction in the others.
LAST_RUN = {"previous_run": ok(fixture("wizard", "previous_run.json")),
            "previous_revision": ok(fixture("wizard", "previous_revision.json"))}


def reads(**over):
    """Flows for the ready cycles and the saved one."""
    table = {"flow": {"desk-standard": ok(FLOW["desk-standard"]),
                      "desk-starter-docs": ok(FLOW["desk-starter-docs"]),
                      "cycle-7c1e5a90": ok(SAVED)},
             "flow_read": {"cycle-7c1e5a90": ok(SAVED)}}
    return wizard_reads(**{**table, **over})


def to_roles(bench, lang, **kwargs):
    to_step(bench, lang, "roles", **kwargs)
    expect(bench.root()).to_have_attribute("data-step", "roles")


def picks(bench, role):
    """The harness options of one role's picker, in order, as (id, label)."""
    return bench.page.locator(f'[data-focus="wizard:role:{role}"] option').evaluate_all(
        "nodes => nodes.map(node => [node.value, node.textContent])")


def reason(bench):
    return bench.page.locator("[data-wizard-reason]").inner_text()


@pytest.mark.parametrize("lang", LANGS)
def test_instruction_fields_follow_the_cycle_and_the_tester_field_is_required(bench, lang):
    to_roles(bench, lang, reads=reads(cycle_read=ok(PINNED)))
    fields = bench.page.locator("[data-instruction]")
    assert fields.evaluate_all("nodes => nodes.map(node => node.dataset.instruction)") == [
        "do", "tester"]
    doer = bench.page.locator('[data-instruction="do"]')
    assert bench.say("wizard.instr.from_task") in doer.inner_text()
    assert "Make it work." in doer.inner_text()
    tester = bench.control("wizard:instr:tester:text")
    assert tester.input_value() == ""
    assert bench.say("wizard.instr.required") in bench.page.locator(
        '[data-instruction="tester"]').inner_text()
    assert reason(bench) == bench.say("wizard.reason.instruction_empty")
    bench.type_into("wizard:instr:tester:text", "Test the login form.")
    expect(bench.page.locator("[data-wizard-reason]")).not_to_have_text(
        bench.say("wizard.reason.instruction_empty"))
    apart = bench.control("wizard:instr:do:apart")
    apart.click()
    expect(bench.control("wizard:instr:do:text")).to_have_value("Make it work.")
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_like_step_x_is_chosen_from_the_other_dispatch_steps_and_shows_its_cost(bench, lang):
    to_roles(bench, lang, reads=reads(cycle_read=ok(PINNED)))
    like = bench.control("wizard:instr:tester:like")
    options = like.locator("option").evaluate_all("nodes => nodes.map(node => node.value)")
    assert options == ["", "do"]
    like.select_option("do")
    tester = bench.page.locator('[data-instruction="tester"]')
    assert bench.say("wizard.instr.like_of", step="do") in tester.inner_text()
    assert bench.say("wizard.instr.like_cost") in tester.inner_text()
    assert bench.control("wizard:instr:tester:text").count() == 0, "a shared one has no own text"
    assert bench.control("wizard:instr:do:like").count() == 0, "a step others follow follows none"
    bench.control("wizard:instr:tester:like").select_option("")
    expect(bench.control("wizard:instr:tester:text")).to_have_count(1)
    assert bench.say("wizard.instr.like_cost") not in bench.root().inner_text()


@pytest.mark.parametrize("lang", LANGS)
def test_a_cycle_the_product_owns_is_never_offered_like_step_x(bench, lang):
    to_roles(bench, lang, reads=reads(flow={"desk-standard": ok(WITH_TESTER)}))
    assert bench.control("wizard:instr:tester:like").count() == 0
    assert bench.page.locator("[data-instruction]").count() == 2


@pytest.mark.parametrize("lang", LANGS)
def test_role_pickers_offer_only_reachable_harnesses_and_mark_unknown_limits_as_unknown(
        bench, lang):
    to_roles(bench, lang, reads=reads())
    assert [row[0] for row in picks(bench, "role-analyst")] == ["claude-code", "codex"]
    doer = picks(bench, "role-doer")
    assert [row[0] for row in doer] == ["claude-code", "codex", "grok-build", "deepseek-harness"]
    labels = dict(doer)
    assert bench.say("wizard.quota.remaining", value="12") in labels["claude-code"]
    assert bench.say("wizard.quota.remaining", value="64") in labels["codex"]
    unknown = bench.say("wizard.quota.unknown") + " · " + bench.say("wizard.quota.no_data")
    assert unknown in labels["grok-build"]
    assert bench.say("wizard.quota.balance") in labels["deepseek-harness"]
    text = bench.root().inner_text()
    assert "kimi-code" not in text and "qwen-code" not in text
    assert bench.page.locator('[data-role="role-doer"]').get_attribute("data-by") == "suggestion"
    bench.control("wizard:role:role-doer").select_option("claude-code")
    doer_row = bench.page.locator('[data-role="role-doer"]')
    expect(doer_row).to_have_attribute("data-by", "owner")
    assert bench.say("wizard.role.by_owner") in doer_row.inner_text()
    bench.control("wizard:role:role-doer:clear").click()
    expect(doer_row).to_have_attribute("data-by", "suggestion")
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_an_argv_harness_shows_its_character_count_and_an_input_over_it_blocks_the_step(
        bench, lang):
    to_roles(bench, lang, reads=reads())
    assert bench.page.locator("[data-argv]").count() == 0, "a stdin harness has no such limit"
    bench.control("wizard:role:role-doer").select_option("grok-build")
    counter = bench.page.locator('[data-instruction="do"] [data-argv]')
    expect(counter).to_have_count(1)
    assert counter.get_attribute("data-fits") == "true"
    assert "32767" in counter.inner_text()
    bench.dispatch(type="material-add", kind="note", title="Long", content="x" * 40000)
    expect(counter).to_have_attribute("data-fits", "false")
    assert reason(bench) == bench.say("wizard.reason.instruction_argv_over")


@pytest.mark.parametrize("lang", LANGS)
def test_the_step_waits_for_the_server_to_check_the_assignment_and_says_so(bench, lang):
    to_roles(bench, lang, reads=reads())
    bench.page.evaluate("() => { window.host.auto.flow = {}; }")
    line = bench.page.locator("[data-wizard-reason]")
    bench.control("wizard:role:role-doer").select_option("claude-code")
    expect(line).to_have_text(bench.say("wizard.reason.binding_pending"))
    bench.answer("flow", FLOW["desk-standard"], subject="desk-standard")
    expect(line).to_have_text("")
    rows = [{"code": "role_capability_unsupported", "severity": "warning",
             "at": {"step_id": "do"}, "params": {}}]
    bench.control("wizard:role:role-doer").select_option("codex")
    expect(line).to_have_text(bench.say("wizard.reason.binding_pending"))
    bench.answer("flow", {**FLOW["desk-standard"], "diagnostics": rows}, subject="desk-standard")
    expect(line).to_have_text(bench.say("wizard.reason.binding_rows"))
    assert bench.page.locator('[data-diag="role_capability_unsupported"]').count() == 1


@pytest.mark.parametrize("lang", LANGS)
def test_the_no_providers_state_shows_the_no_providers_message_and_blocks_the_step(bench, lang):
    empty = {**fixture("wizard", "workflows.json"), "providers": []}
    to_roles(bench, lang, reads=reads(workflows=ok(empty)))
    assert bench.page.locator("[data-providers-none]").inner_text() == bench.say(
        "wizard.providers.none")
    assert bench.page.locator("[data-role]").count() == 0
    assert reason(bench) == bench.say("wizard.reason.no_providers")
    assert bench.control("wizard:prepare").is_disabled()


@pytest.mark.parametrize("lang", LANGS)
def test_the_starter_journey_ends_step_four_with_three_review_roles_and_no_instruction_field(
        bench, lang):
    to_roles(bench, lang, starter="desk-starter-docs", reads=reads())
    assert bench.page.locator("[data-role]").evaluate_all(
        "nodes => nodes.map(node => node.dataset.role)") == [
        "role-analyst", "role-reviewer", "role-designer"]
    assert bench.page.locator("[data-instruction]").count() == 0
    assert bench.page.locator("[data-instructions-none]").inner_text() == bench.say(
        "wizard.instr.none")
    expect(bench.page.locator("[data-wizard-reason]")).to_have_text("")
    prepare = bench.control("wizard:prepare")
    assert prepare.is_disabled()
    assert bench.page.locator('[data-blocked="wizard:prepare"] small').inner_text() == \
        bench.say("wizard.later.prepare")
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_next_task_preselects_the_last_runs_cycle_and_role_assignment(bench, lang):
    to_roles(bench, lang, reads=reads(flow={"desk-standard": ok(WITH_TESTER)}, **LAST_RUN))
    rows = {row: bench.page.locator(f'[data-role="{row}"]') for row in (
        "role-analyst", "role-doer", "role-tester", "role-checker")}
    assert bench.page.locator("[data-wizard][data-step]").get_attribute("data-step") == "roles"
    for role, harness in (("role-analyst", "claude-code"), ("role-doer", "codex"),
                          ("role-checker", "claude-code")):
        assert rows[role].get_attribute("data-by") == "previous", role
        assert bench.control(f"wizard:role:{role}").input_value() == harness
    tester = rows["role-tester"]
    assert tester.get_attribute("data-by") == "none"
    assert bench.say("wizard.role.unassigned") in tester.inner_text()
    assert bench.say("wizard.note.new_role") in tester.inner_text()
    assert reason(bench) == bench.say("wizard.reason.roles_unassigned")
    bench.control("wizard:role:role-tester").select_option("codex")
    expect(bench.page.locator("[data-wizard-reason]")).not_to_have_text(
        bench.say("wizard.reason.roles_unassigned"))
    assert bench.problems == []
