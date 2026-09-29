"""The wizard's step 5 ("Подготовка") on the real renderer, in Russian and in English.

The chain of spec 6.4.1 runs against the fake server of `desk_wizard_server.py`, which keeps a
memory: a repeated write finds what stands, a lost answer lands without being heard, a refusal
comes on demand. What is asserted is what the page does and says (the links in order, the hash
before each write, no second task and no second run after a lost answer, a reload resumed from the
read alone) and what the server holds afterwards. The model's own rules are in
`tests/test_desk_wizard_prepare.py` and `tests/test_desk_wizard_resume.py`.
"""
from __future__ import annotations

from urllib.parse import parse_qs

import pytest
from playwright.sync_api import expect

from browser_tests import desk_wizard_server as server
from browser_tests.desk_wizard_bench import (  # noqa: F401
    NO_DRAFTS, advance, bench, desk_url, fill_task, ok, to_step, wizard_reads)
from tests.desk_wizard_node import fixture

LANGS = ("ru", "en")
FLOWS = {name: fixture("flow", f"{name}.flow-state.json") for name in (
    "desk-standard", "desk-short", "desk-starter-docs")}
LINKS = ["task", "seed", "flow", "run", "documents", "preview"]
ORDER = ["prep_task", "prep_read", "prep_seed", "prep_flow", "prep_run", "prep_doc", "prep_doc",
         "prep_materials", "preview"]


def drafts():
    """The reads a wizard draws its first four steps from, and the flows the drafts answer."""
    return wizard_reads(flow={name: ok(state) for name, state in FLOWS.items()},
                        flow_read=NO_DRAFTS)


def to_prepare(bench, lang, *, starter=None, **kwargs):
    """The wizard on step 5, the fake server behind it (nothing is asked until the button)."""
    to_step(bench, lang, "prepare", starter=starter, reads=drafts())
    server.install(bench, flows=FLOWS, **kwargs)
    expect(bench.root()).to_have_attribute("data-wizard-current", "prepare")


def statuses(bench):
    return bench.page.locator("[data-link]").evaluate_all(
        "nodes => nodes.map(node => [node.dataset.link, node.dataset.status])")


#: The keys of the desk's hash that the wizard writes. The others (`lang`, `theme`) are the
#: desk's own: its boot module keeps the language in the address, so a hash read while the
#: wizard runs carries them, and what these tests judge is only what the wizard added.
WIZARD_KEYS = ("task", "prepare", "workflow", "run", "starter")


def keys_of(hash_text):
    fields = parse_qs(hash_text.lstrip("#"))
    return {key: values[0] for key, values in fields.items() if key in WIZARD_KEYS}


def press(bench):
    bench.control("wizard:prepare:go").click()


def prepared(bench):
    expect(bench.page.locator('[data-prepare="review"]')).to_be_visible()


def stored(bench):
    return bench.page.evaluate(
        "() => [window.localStorage.length, window.sessionStorage.length]")


@pytest.mark.parametrize("lang", LANGS)
def test_step_five_lists_the_six_links_and_prepares_them_in_order_with_the_hash_before_each(
        bench, lang):
    to_prepare(bench, lang)
    assert [row[0] for row in statuses(bench)] == LINKS
    assert {row[1] for row in statuses(bench)} == {"todo"}
    names = bench.page.locator("[data-link]").evaluate_all(
        "nodes => nodes.map(node => node.querySelector(':scope > :first-child').innerText)")
    assert names == [f"{at + 1}. {bench.say(f'wizard.chain.link.{link}')}"
                     for at, link in enumerate(LINKS)]
    assert bench.control("wizard:prepare:go").inner_text() == bench.say("wizard.prepare")
    press(bench)
    prepared(bench)
    held = server.world(bench)
    assert [call["name"] for call in held["calls"]] == ORDER
    hashes = {call["name"]: keys_of(call["hash"]) for call in held["calls"]}
    ids = {"task": "task-bench", "prepare": "1"}
    assert hashes["prep_task"] == hashes["prep_read"] == hashes["prep_seed"] == ids
    assert hashes["prep_flow"] == {**ids, "workflow": "desk-standard"}
    for name in ("prep_run", "prep_doc", "prep_materials", "preview"):
        assert hashes[name] == {**ids, "workflow": "desk-standard", "run": "task-bench-r1"}
    assert keys_of(bench.page.evaluate("location.hash")) == hashes["preview"]
    assert {row[1] for row in statuses(bench)} == {"done"}
    assert (held["tasks_written"], held["seeds_written"], held["runs_written"]) == (1, 1, 1)
    assert held["doc_records"] == 3 and held["previews"] == 1
    assert bench.page.locator("[data-prepared]").inner_text() == bench.say("wizard.chain.ready")
    assert stored(bench) == [0, 0], "no browser storage"
    assert {method for method, _ in bench.requests} == {"GET"}
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("lost", ["prep_task", "prep_seed", "prep_flow", "prep_run", "prep_doc",
                                  "prep_materials"])
def test_a_lost_answer_is_read_back_and_never_writes_a_second_task_run_or_document(
        bench, lang, lost):
    to_prepare(bench, lang, lose={lost: 1})
    press(bench)
    prepared(bench)
    held = server.world(bench)
    calls = [call["name"] for call in held["calls"]]
    at = calls.index(lost)
    assert calls[at + 1] == "prep_read", "the read comes before anything is sent again"
    assert (held["tasks_written"], held["seeds_written"], held["runs_written"]) == (1, 1, 1)
    assert held["doc_records"] == 3, "brief, instruction and materials, once each"
    assert {row[1] for row in statuses(bench)} == {"done"}
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_a_lost_answer_is_said_while_the_read_is_out_and_the_link_is_marked_unknown(bench, lang):
    # The first read (after the task) is answered; the read after the lost run answer is not.
    to_prepare(bench, lang, lose={"prep_run": 1}, refuse={"prep_read": {
        "code": "store_error", "count": 99, "after": 1}})
    press(bench)
    expect(bench.page.locator('[data-prepare="unknown"]')).to_be_visible()
    assert dict(statuses(bench))["run"] == "unknown"
    assert bench.page.locator("[data-chain-note]").inner_text() == bench.say(
        "wizard.chain.read_failed", code="store_error")
    assert bench.control("wizard:prepare:retry").is_visible()
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_a_draft_conflict_after_a_lost_publish_reads_the_flow_and_closes_the_link(bench, lang):
    bench.open(lang, auto=wizard_reads())
    bench.door({name: state for name, state in FLOWS.items()}, {})
    fill_task(bench)
    advance(bench, "prepare")
    server.install(bench, flows=FLOWS, lose={"prep_flow": 1})
    press(bench)
    prepared(bench)
    held = server.world(bench)
    calls = [call["name"] for call in held["calls"]]
    assert calls[calls.index("prep_flow") + 1:][:3] == ["prep_read", "prep_flow", "prep_flow_read"]
    assert held["runs"]["task-bench-r1"]["revision"] == 2
    assert held["runs_written"] == 1
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_a_refusal_stops_at_its_link_says_the_code_and_a_retry_writes_the_same_thing(bench, lang):
    to_prepare(bench, lang, refuse={"prep_seed": {"code": "seed_refused", "count": 1,
                                                  "detail": {"reason": "base_moved"}}})
    press(bench)
    expect(bench.page.locator('[data-prepare="refused"]')).to_be_visible()
    assert [row for row in statuses(bench)] == [
        ["task", "done"], ["seed", "refused"], ["flow", "todo"], ["run", "todo"],
        ["documents", "todo"], ["preview", "todo"]]
    refusal = bench.page.locator('[data-refusal-link="seed"]')
    assert refusal.inner_text() == bench.say("wizard.chain.refused", code="seed_refused · base_moved")
    assert [call["name"] for call in server.world(bench)["calls"]] == [
        "prep_task", "prep_read", "prep_seed"]
    assert bench.control("wizard:prepare:go").count() == 0
    bench.control("wizard:prepare:retry").click()
    prepared(bench)
    assert server.world(bench)["seeds_written"] == 1
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_the_title_is_locked_once_the_task_is_written(bench, lang):
    to_prepare(bench, lang, refuse={"prep_seed": {"code": "store_error", "count": 9}})
    press(bench)
    expect(bench.page.locator('[data-prepare="refused"]')).to_be_visible()
    bench.control("wizard:step:task").click()
    expect(bench.control("wizard:title")).to_be_disabled()
    assert bench.say("wizard.task.title_locked") in bench.page.locator(
        '[data-field="title"]').inner_text()


@pytest.mark.parametrize("lang", LANGS)
def test_a_record_conflict_offers_the_recorded_arrangement_or_the_next_run(bench, lang):
    clash = {"prep_run": {"code": "record_conflict", "count": 1, "create_run": True}}
    to_prepare(bench, lang, refuse=clash)
    press(bench)
    expect(bench.page.locator('[data-prepare="refused"]')).to_be_visible()
    assert bench.page.locator('[data-refusal-link="run"]').inner_text() == bench.say(
        "wizard.chain.conflict_run")
    assert bench.control("wizard:prepare:adopt").inner_text() == bench.say("wizard.chain.adopt")
    assert bench.control("wizard:prepare:bump").inner_text() == bench.say(
        "wizard.chain.bump", number="2")
    bench.control("wizard:prepare:adopt").click()
    prepared(bench)
    held = server.world(bench)
    assert list(held["runs"]) == ["task-bench-r1"] and set(held["docs"]) == {"task-bench-r1"}
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_the_next_run_number_is_opened_when_the_owner_asks_for_it(bench, lang):
    clash = {"prep_run": {"code": "record_conflict", "count": 1, "create_run": True}}
    to_prepare(bench, lang, refuse=clash)
    press(bench)
    expect(bench.page.locator('[data-prepare="refused"]')).to_be_visible()
    bench.control("wizard:prepare:bump").click()
    prepared(bench)
    held = server.world(bench)
    assert sorted(held["runs"]) == ["task-bench-r1", "task-bench-r2"]
    assert set(held["docs"]) == {"task-bench-r2"}
    assert keys_of(bench.page.evaluate("location.hash"))["run"] == "task-bench-r2"


@pytest.mark.parametrize("lang", LANGS)
def test_a_starter_run_skips_the_seed_and_keeps_its_key_until_the_run_is_written(bench, lang):
    to_prepare(bench, lang, starter="desk-starter-docs")
    press(bench)
    prepared(bench)
    held = server.world(bench)
    assert [call["name"] for call in held["calls"]] == [
        "prep_task", "prep_read", "prep_flow", "prep_run", "prep_doc", "prep_materials", "preview"]
    assert dict(statuses(bench))["seed"] == "skipped"
    hashes = {call["name"]: keys_of(call["hash"]) for call in held["calls"]}
    assert hashes["prep_run"]["starter"] == "desk-starter-docs"
    assert "starter" not in hashes["prep_doc"]
    assert bench.problems == []


# -- after a reload ------------------------------------------------------------------------


def reload(bench, lang, resume, **opening):
    """A new wizard on the same page and the same server, opened as a reloaded page opens."""
    bench.open(lang, auto=drafts(), resume=resume, **opening)


RESUME = {"runId": "task-bench-r1", "workflowId": "desk-standard"}


@pytest.mark.parametrize("lang", LANGS)
def test_a_reload_in_the_middle_of_the_chain_resumes_from_the_read_and_writes_only_the_rest(
        bench, lang):
    to_prepare(bench, lang, refuse={"prep_doc": {"code": "store_error", "count": 99}})
    press(bench)
    expect(bench.page.locator('[data-prepare="refused"]')).to_be_visible()
    bench.page.evaluate("() => { window.host.world.refuse = {}; window.host.world.calls = []; }")
    reload(bench, lang, RESUME)
    expect(bench.root()).to_have_attribute("data-wizard-current", "prepare")
    documents = bench.page.locator('[data-resume="documents"]')
    expect(documents).to_be_visible()
    assert bench.say("wizard.resume.retype") in documents.inner_text()
    fields = bench.page.locator('[data-resume="documents"] [data-field]').evaluate_all(
        "nodes => nodes.map(node => node.dataset.field)")
    assert fields == ["brief", "hint", "materials", "instruction:do"]
    assert bench.control("wizard:prepare:go").inner_text() == bench.say("wizard.prepare.continue")
    assert bench.control("wizard:prepare:go").is_disabled()
    bench.type_into("wizard:brief", "Fix the login form.")
    bench.type_into("wizard:resume:instruction:do", "Do the login form.")
    press(bench)
    prepared(bench)
    held = server.world(bench)
    calls = [call["name"] for call in held["calls"]]
    assert calls == ["prep_read", "prep_doc", "prep_doc", "prep_materials", "preview"]
    assert (held["tasks_written"], held["runs_written"], held["seeds_written"]) == (1, 1, 1)
    assert set(held["docs"]["task-bench-r1"]) == {
        "artifact-brief", "artifact-materials", "instruction-do"}
    assert stored(bench) == [0, 0]
    assert {method for method, _ in bench.requests} == {"GET"}
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_a_reloaded_page_whose_task_the_server_does_not_know_starts_over_at_step_one(bench, lang):
    to_prepare(bench, lang)
    bench.page.evaluate("() => { window.host.world.task = null; }")
    reload(bench, lang, {"runId": None, "workflowId": None})
    expect(bench.root()).to_have_attribute("data-wizard-current", "task")
    assert "prepare" not in keys_of(bench.page.evaluate("location.hash"))
    assert bench.control("wizard:title").input_value() == ""
    assert bench.problems == []


@pytest.mark.parametrize("lang", LANGS)
def test_a_task_with_no_run_says_what_the_reload_lost_and_fills_in_again_with_its_title(
        bench, lang):
    to_prepare(bench, lang)
    server.install(bench, flows=FLOWS, task=True)
    reload(bench, lang, {"runId": None, "workflowId": None})
    lost = bench.page.locator('[data-resume="no_run"]')
    expect(lost).to_be_visible()
    assert lost.locator("p").first.inner_text() == bench.say("wizard.resume.no_run",
                                                             title="Fix login")
    bench.control("wizard:resume:restart").click()
    expect(bench.root()).to_have_attribute("data-wizard-current", "task")
    expect(bench.control("wizard:title")).to_be_disabled()
    assert bench.control("wizard:title").input_value() == "Fix login"
    assert "prepare" not in keys_of(bench.page.evaluate("location.hash"))


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("stage", ["queued", "authorized", "ended"])
def test_a_run_past_the_preparation_is_offered_to_the_desk_and_names_its_stage(
        bench, lang, stage):
    to_prepare(bench, lang)
    server.install(bench, flows=FLOWS, task=True, stage=stage, runs=[{
        "run_id": "task-bench-r1", "workflow_id": "desk-standard", "revision": 1}])
    reload(bench, lang, RESUME)
    notice = bench.page.locator('[data-resume="exit"]')
    expect(notice).to_be_visible()
    assert notice.locator("p").first.inner_text() == bench.say(f"wizard.resume.exit_{stage}")
    assert bench.page.evaluate("() => window.host.exit") == {"runId": "task-bench-r1",
                                                            "stage": stage}
    bench.control("wizard:resume:open").click()
    assert bench.page.evaluate("() => [window.host.closed, window.host.outcome]") == [
        1, {"runId": "task-bench-r1", "stage": stage}]


@pytest.mark.parametrize("lang", LANGS)
def test_a_read_that_fails_after_a_reload_is_said_and_asked_again_only_by_the_owner(bench, lang):
    to_prepare(bench, lang)
    server.install(bench, flows=FLOWS, task=True, refuse={"prep_read": {
        "code": "store_error", "count": 1}})
    reload(bench, lang, {"runId": None, "workflowId": None})
    failed = bench.page.locator('[data-resume="failed"]')
    expect(failed).to_be_visible()
    assert failed.locator("p").first.inner_text() == bench.say("wizard.resume.failed",
                                                               code="store_error")
    assert [call["name"] for call in server.world(bench)["calls"]] == ["prep_read"]
    bench.control("wizard:prepare:retry").click()
    expect(bench.page.locator('[data-resume="no_run"]')).to_be_visible()
    assert [call["name"] for call in server.world(bench)["calls"]] == ["prep_read", "prep_read"]
