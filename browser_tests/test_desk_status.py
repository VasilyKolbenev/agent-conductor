"""The status words, the waiting time and the "waiting for you" items in a real Chromium.

The desk's shared modules (`desk-status.js`, `desk-status-copy.js`, `desk-time.js`) are served by
the production server and imported here from the page, so what runs is the packaged bytes under a
real `Intl`, in a zone the test names. A small host in the page draws each answer as text the way
a region does -- the word through the catalogue, the time through `instantText`, the exact instant
in a `title` -- and the test reads the page's own `innerText`, so what is measured is what a
person would read. Each fact and its sentence are read in ONE evaluation.

What this module holds:

- one row per rule of spec 5.2.1 says its word in English and in Russian; a snapshot adds one
  caption and no other word changes;
- the hub's summary fixture (lane H's `hub_projects.json`) and the desk give the same word to the
  same task: the hub side is `taskStatus` over the fixture's rows, the desk side is a real desk
  booted on a page whose three reads (tasks, runs, the automation of the newest run) are answered
  with those same rows, and what is compared is the word its rail drew;
- the journal fixture (`tests/fixtures/desk/journal_index.json`, the spec's 4.5.6 shape) gives the
  same projection and the same waiting instants in the page as under Node, for all five reasons;
- an item of "waiting for you" says its reason and either "waiting since <time>", with the exact
  instant in the hint, or "noticed at <time>", or the phrase that the time is not given -- in the
  zone of the browser, in both languages;
- the reason a queue record gives is a sentence, and no innerText carries a machine word.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Browser, Page, Route

from browser_tests.desk_settled import SETTLED
from browser_tests.test_desk_rail_scene import seeded_url  # noqa: F401  (a fixture)
from tests.test_desk_attention import (
    FIVE, OBSERVED, RUN_OBSERVED, attention, automation, project, row)
from tests.test_desk_status import (
    ATTENTION_WORDS, CASES, ENTRY_REASONS, JOURNAL, RECEIPT_CONFLICT, SPEC_KEYS, SPEC_RUSSIAN,
    TASK, a_run)

MOSCOW, NEW_YORK = "Europe/Moscow", "America/New_York"
HUB = json.loads((Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "hub"
                  / "hub_projects.json").read_text(encoding="utf-8"))["response"]
#: The English words of the closed key list, spelled out here and not read back from the page.
ENGLISH = {
    "task_unreadable": "Record cannot be read", "not_started": "Not started",
    "run_unreadable": "Record cannot be read", "waiting_you": "Waiting for your decision",
    "queue_confirmation": "Waiting for your confirmation",
    "queue_blocked": "Queued · cannot start", "queued": "Queued · #{position}",
    "queued_inactive": "Queued · starts once the project is active",
    "state_unknown": "State unknown", "running": "Running",
    "checkpoint_inactive": "At a checkpoint · the run belongs to the active project",
    "checkpoint": "At a checkpoint · needs to be continued", "owner_missing": "No project owner",
    "stalled": "Run stalled", "expired": "Permission expired", "paused": "Paused",
    "revoked": "Permission revoked", "outcome_succeeded": "Succeeded",
    "outcome_verification_failed": "Verification failed", "outcome_failed": "Failed",
    "outcome_unknown": "Outcome unknown", "outcome_rejected": "Rejected",
    "outcome_cancelled": "Cancelled", "ended": "Ended without a result",
    "no_outcome": "No result yet"}
WORDS = {"en": ENGLISH, "ru": SPEC_RUSSIAN}
ENGLISH_ATTENTION = {
    "gate_decision": "Gate decision", "confirmation": "Confirm the step",
    "input_document": "A document is needed",
    "reconcile": "State needs reconciling outside the window",
    "attempt_bound": "The step ran out of attempts",
    "restart_required": "Continue after the restart",
    "stalled": "Run stalled", "expired": "Permission expired",
    "queue_confirmation": "Waiting for your confirmation",
    "slot_stuck": "Slot busy · free the slot in the desk",
    "recovery_required": "The OS needs a restart",
    "login_recovery_required": "Login needs recovery"}
#: The short time of an instant in each language, in Moscow (UTC+3, no daylight time).
CLOCK = {"en": {"2026-09-29T09:20:00Z": "09/29 12:20", "2026-09-29T09:05:00Z": "09/29 12:05",
                "2026-09-29T09:00:00Z": "09/29 12:00", "2026-09-29T09:15:00Z": "09/29 12:15",
                "2026-09-29T09:59:00Z": "09/29 12:59", "2026-09-29T10:00:00Z": "09/29 13:00",
                "2026-09-29T09:40:00Z": "09/29 12:40", "2026-09-29T08:40:00Z": "09/29 11:40"},
         "ru": {"2026-09-29T09:20:00Z": "29.09 12:20", "2026-09-29T09:05:00Z": "29.09 12:05",
                "2026-09-29T09:00:00Z": "29.09 12:00", "2026-09-29T09:15:00Z": "29.09 12:15",
                "2026-09-29T09:59:00Z": "29.09 12:59", "2026-09-29T10:00:00Z": "29.09 13:00",
                "2026-09-29T09:40:00Z": "29.09 12:40", "2026-09-29T08:40:00Z": "29.09 11:40"}}
PHRASES = {
    "en": {"waiting": "waiting since {time}", "noticed": "noticed at {time}",
           "noticed_unknown": "noticed · time not given", "snapshot": "snapshot from {time}",
           "snapshot_unknown": "snapshot · time not given"},
    "ru": {"waiting": "ждёт с {time}", "noticed": "замечено в {time}",
           "noticed_unknown": "замечено · время не указано", "snapshot": "снимок от {time}",
           "snapshot_unknown": "снимок · время не указано"}}
#: Machine words no innerText may carry (spec 5.2): the five it names, every key, reason and code
#: this module can say that is spelled with an underscore, and the raw states the routes carry.
MACHINE = sorted({
    "verification_failed", "policy", "created", "ready", "empty",
    *(word for word in [*SPEC_KEYS, *ATTENTION_WORDS, *ENTRY_REASONS,
                        *(f"attention_{reason}" for reason in ATTENTION_WORDS)]
      if "_" in word),
    "explicit_resume_required", "project_not_active", "plan_stalled", "seed_blocked",
    "confirmation_required", "preauthorized", "action_in_flight", "authorization_required",
    "owner_required", "human_state", "restart_required", "last_outcome"}, key=len, reverse=True)
RAW = re.compile(r"\b(?:" + "|".join(map(re.escape, MACHINE)) + r")\b", re.I)

#: The host in the page: it draws answers as text through the real modules, and reads them back.
DRAW = """async ({locale, statuses, projects, cases, entries}) => {
  const [status, i18n, clock] = await Promise.all([
    import("/panel/desk-status.js"), import("/panel/studio-i18n.js"),
    import("/panel/desk-time.js")]);
  const named = (text) => [...text.matchAll(/\\{([a-z_]+)\\}/g)].map((found) => found[1]);
  const said = (key, given = {}) => {
    const id = `desk_status.${key}`;
    const wanted = named(i18n.MESSAGES[id][locale]);
    return i18n.message(locale, id, Object.fromEntries(
      wanted.map((name) => [name, String(given[name])])));
  };
  const board = document.createElement("section");
  board.id = "statusBoard";
  document.body.append(board);
  const line = (text, exact = null) => {
    const node = document.createElement("p");
    node.textContent = text;
    if (exact !== null) node.title = exact;
    board.append(node);
    return node;
  };
  const timed = (key, at) => said(key, {time: clock.instantText(locale, at).short});
  const since = (one) => {
    if (one.kind === "waiting") return timed("since_waiting", one.at);
    return clock.instantText(locale, one.at).known ? timed("since_observed", one.at)
      : said("since_observed_unknown");
  };
  const caption = (at) => (clock.instantText(locale, at).known ? timed("snapshot", at)
    : said("snapshot_unknown"));
  const words = statuses.map((input) => {
    const word = status.taskStatus(input);
    const snap = Object.hasOwn(word.params, "snapshot_at") ? caption(word.params.snapshot_at)
      : null;
    const text = said(word.key, word.params);
    line(snap === null ? text : `${text} · ${snap}`);
    return {key: word.key, params: word.params, text, snap};
  });
  const lists = projects.map((one) => status.attentionItems(one).map((item) => {
    const parts = [said(item.key), since(item.since)];
    if (item.snapshot_at !== null) parts.push(caption(item.snapshot_at));
    const when = clock.instantText(locale, item.since.at);
    const node = line(parts.join(" · "), when.known ? when.exact : null);
    return {text: node.textContent, title: node.title, reason: item.reason};
  }));
  const found = cases.map((one) => ({
    index: status.journalIndex(one.records),
    waiting: one.waiting.map((wait) => status.waitingSince({reason: wait.reason,
      sources: wait.sources, journal: status.journalIndex(one.records), runtime: one.runtime}))}));
  const reasons = entries.map((code) => line(said(`entry_${code}`)).textContent);
  return {words, lists, found, reasons, text: board.innerText,
    zone: Intl.DateTimeFormat().resolvedOptions().timeZone};
}"""


@pytest.fixture
def drawn(chromium: Browser, seeded_url: str) -> Iterator[Callable[..., dict]]:  # noqa: F811
    """A factory: open the desk's page in a language and a zone, draw a spec, return the facts."""
    contexts = []

    def make(language: str, zone: str = MOSCOW, **spec: object) -> dict:
        context = chromium.new_context(viewport={"width": 1280, "height": 900},
                                       timezone_id=zone, locale=language)
        contexts.append(context)
        page: Page = context.new_page()
        problems: list[str] = []
        page.on("console", lambda message: problems.append(message.text)
                if message.type == "error" else None)
        page.on("pageerror", lambda error: problems.append(str(error)))
        page.goto(f"{seeded_url}#lang={language}", wait_until="load")
        page.wait_for_function(SETTLED)
        facts = page.evaluate(DRAW, {"locale": language, "statuses": [], "projects": [],
                                     "cases": [], "entries": [], **spec})
        assert problems == []
        return facts

    yield make
    for context in contexts:
        context.close()


def _word(language: str, key: str, **params: str) -> str:
    return WORDS[language][key].format(**params)


@pytest.mark.parametrize("language", ["en", "ru"])
def test_every_rule_of_the_table_says_its_word_in_the_page_and_no_machine_word_reaches_the_text(
        drawn, language):
    inputs = [case for case, _expected in CASES.values()]
    facts = drawn(language, statuses=inputs)
    for (name, (_case, expected)), got in zip(CASES.items(), facts["words"]):
        params = {key: value for key, value in expected["params"].items() if key == "position"}
        assert (got["key"], got["text"]) == (expected["key"],
                                             _word(language, expected["key"], **params)), name
        assert got["snap"] is None
    assert not RAW.search(facts["text"]), RAW.search(facts["text"]).group(0)


def test_the_machine_word_check_bites_on_a_planted_word_and_on_each_kind_of_token():
    for planted in ("terms_changed", "waiting_you", "verification_failed", "POLICY", "ready",
                    "restart_required", "attention_slot_stuck"):
        assert RAW.search(f"a row that says {planted} out loud"), planted
    assert not RAW.search("Ended without a result · Waiting for your decision")


@pytest.mark.parametrize("language", ["en", "ru"])
def test_a_snapshot_adds_one_caption_to_a_word_and_a_snapshot_with_no_moment_says_so(
        drawn, language):
    stamp = "2026-09-29T08:40:00Z"
    waiting = {"task": TASK, "run": a_run(human_state="required")}
    facts = drawn(language, statuses=[
        {**waiting, "data": "snapshot", "snapshot_at": stamp},
        {**waiting, "data": "snapshot"}, {**waiting, "data": "live", "snapshot_at": stamp}])
    first, blank, live = facts["words"]
    phrase = PHRASES[language]
    assert first["text"] == blank["text"] == live["text"] == _word(language, "waiting_you")
    assert first["snap"] == phrase["snapshot"].format(time=CLOCK[language][stamp])
    assert blank["snap"] == phrase["snapshot_unknown"] and live["snap"] is None
    assert not RAW.search(facts["text"])


#: What the rail of the desk says, in ONE evaluation: the id and the word of each row.
RAIL = """() => [...document.querySelectorAll("#deskRail .desk-task")].map((node) => ({
  id: node.dataset.taskId, word: node.querySelector(".desk-task__state").textContent}))"""


def _desk_reads(project: dict) -> dict[str, dict]:
    """What the three routes a desk reads at boot answer for one project of the hub fixture: the
    hub embeds the routes' rows as they are, so each body is those rows in the route's shape."""
    rows = project["tasks"]
    bodies = {"/command/tasks": {"tasks": [one["task"] for one in rows]},
              "/command/runs": {"runs": [one["run"] for one in rows], "providers": []}}
    for one in rows:
        run_id = one["run"]["run_id"]
        bodies[f"/command/runs/{run_id}/automation"] = {"run_id": run_id, **one["automation"]}
    return bodies


@pytest.fixture
def desk_of(chromium: Browser, seeded_url: str) -> Iterator[Callable[..., dict]]:  # noqa: F811
    """A factory: boot the desk's page in a language with its reads answered from `bodies`, and
    say what its rail drew, which routes it asked and what went wrong in the console.

    The stream is ended (HTTP 204, as the other rigs do), so the page holds the boot's own reads:
    a stream that opens makes full refreshes after the boot, and each one reads the lists and the
    automation again, so what the page had asked would depend on how far the stream had got."""
    contexts = []

    def make(language: str, bodies: dict[str, dict]) -> dict:
        context = chromium.new_context(viewport={"width": 1280, "height": 900}, locale=language)
        contexts.append(context)
        page: Page = context.new_page()
        problems: list[str] = []
        asked: list[str] = []

        def answer(route: Route) -> None:
            path = urlsplit(route.request.url).path
            asked.append(path)
            body = bodies.get(path, {"error": {"code": "route_not_found"}})
            route.fulfill(status=200 if path in bodies else 404,
                          content_type="application/json", body=json.dumps(body))

        page.route("**/events", lambda route: route.fulfill(status=204))
        for pattern in ("**/command/tasks", "**/command/runs", "**/command/runs/*/automation"):
            page.route(pattern, answer)
        page.on("pageerror", lambda error: problems.append(str(error)))
        page.goto(f"{seeded_url}#lang={language}", wait_until="load")
        page.wait_for_function(SETTLED)
        return {"rail": page.evaluate(RAIL), "asked": sorted(asked), "problems": problems}

    yield make
    for context in contexts:
        context.close()


@pytest.mark.parametrize("language", ["en", "ru"])
def test_the_rail_of_a_desk_fed_the_fixture_rows_says_the_word_the_hub_gives_each_task(
        drawn, desk_of, language):
    """Spec 5.2.1: the desk and the hub get one key per task from one fixture. The hub side is
    `taskStatus` over a project's rows with the project's own mode, data and snapshot; the desk
    side is a desk that reads the same rows through its own three routes, and the word compared
    is the one its rail drew. Only a snapshot, which only the hub has, adds a caption."""
    projects = [one for one in HUB["projects"] if one["tasks"]]
    hub_words = []
    for project in projects:
        hub = [{"task": one["task"], "run": one["run"], "automation": one["automation"],
                "entry": None, "mode": project["mode"], "data": project["data"],
                "snapshot_at": project["snapshot_at"]} for one in project["tasks"]]
        said = drawn(language, statuses=hub)["words"]
        bodies = _desk_reads(project)
        desk = desk_of(language, bodies)
        assert desk["asked"] == sorted(bodies) and desk["problems"] == []
        assert [row["id"] for row in desk["rail"]] == [
            one["task"]["task_id"] for one in project["tasks"]]
        assert [row["word"] for row in desk["rail"]] == [word["text"] for word in said]
        assert [row["word"] for row in desk["rail"]] == [
            _word(language, word["key"]) for word in said]
        hub_words.extend(said)
    assert [word["key"] for word in hub_words] == ["running", "waiting_you", "checkpoint"]
    assert [word["snap"] is not None for word in hub_words] == [False, False, True]


@pytest.mark.parametrize("language", ["en", "ru"])
def test_the_journal_fixture_projects_and_dates_the_same_in_the_page_as_under_node(
        drawn, language):
    cases = JOURNAL["cases"]
    facts = drawn(language, cases=cases)
    for case, found in zip(cases, facts["found"]):
        assert found["index"] == case["journal"], case["name"]
        assert found["waiting"] == [wait["at"] for wait in case["waiting"]], case["name"]


@pytest.mark.parametrize("language", ["en", "ru"])
def test_an_item_says_its_reason_and_when_the_wait_began_with_the_exact_instant_in_its_hint(
        drawn, language):
    facts = drawn(language, projects=[project(row(seen=FIVE))])
    [items] = facts["lists"]
    phrase, clock = PHRASES[language], CLOCK[language]
    says = ENGLISH_ATTENTION if language == "en" else ATTENTION_WORDS
    expected = [
        ("gate_decision", phrase["waiting"].format(time=clock["2026-09-29T09:20:00Z"]),
         "2026-09-29T09:20:00Z"),
        ("confirmation", phrase["waiting"].format(time=clock["2026-09-29T09:05:00Z"]),
         "2026-09-29T09:05:00Z"),
        ("input_document", phrase["waiting"].format(time=clock["2026-09-29T09:00:00Z"]),
         "2026-09-29T09:00:00Z"),
        ("reconcile", phrase["noticed"].format(time=clock[RUN_OBSERVED]), RUN_OBSERVED),
        ("attempt_bound", phrase["waiting"].format(time=clock["2026-09-29T09:15:00Z"]),
         "2026-09-29T09:15:00Z")]
    assert [(item["reason"], item["text"], item["title"]) for item in items] == [
        (reason, f"{says[reason]} · {since}", title) for reason, since, title in expected]
    assert not RAW.search(facts["text"])


@pytest.mark.parametrize("language", ["en", "ru"])
def test_a_wait_whose_moment_is_not_known_says_noticed_or_that_the_time_is_not_given(
        drawn, language):
    ghost = attention(("attempt_bound", ["ghost"]), observed=None)
    facts = drawn(language, projects=[
        project(row(seen=ghost), observed_at=OBSERVED),
        project(row(seen=ghost), observed_at=None)])
    noticed, unknown = facts["lists"]
    phrase, says = PHRASES[language], (ENGLISH_ATTENTION if language == "en" else ATTENTION_WORDS)
    assert [item["text"] for item in noticed] == [
        f"{says['attempt_bound']} · {phrase['noticed'].format(time=CLOCK[language][OBSERVED])}"]
    assert [item["title"] for item in noticed] == [OBSERVED]
    assert [item["text"] for item in unknown] == [
        f"{says['attempt_bound']} · {phrase['noticed_unknown']}"]
    assert [item["title"] for item in unknown] == [""]


@pytest.mark.parametrize("language", ["en", "ru"])
def test_the_items_of_a_snapshot_carry_its_caption_after_the_reason_and_the_time(drawn, language):
    stamp = "2026-09-29T08:40:00Z"
    stalled = row(human="not_required", grant=automation("stalled", "seed_blocked"))
    facts = drawn(language, projects=[project(stalled, data="snapshot", snapshot_at=stamp)])
    [items] = facts["lists"]
    phrase = PHRASES[language]
    says = ENGLISH_ATTENTION if language == "en" else ATTENTION_WORDS
    assert [item["text"] for item in items] == [
        f"{says['stalled']} · {phrase['noticed'].format(time=CLOCK[language][OBSERVED])}"
        f" · {phrase['snapshot'].format(time=CLOCK[language][stamp])}"]
    assert not RAW.search(facts["text"])


@pytest.mark.parametrize("language", ["en", "ru"])
def test_every_reason_a_queue_record_gives_is_a_sentence_and_the_spec_words_the_conflict(
        drawn, language):
    facts = drawn(language, entries=list(ENTRY_REASONS))
    assert len(facts["reasons"]) == len(ENTRY_REASONS)
    assert all(text and text == text.strip() and "_" not in text for text in facts["reasons"])
    assert not RAW.search(facts["text"])
    if language == "ru":
        assert facts["reasons"][ENTRY_REASONS.index("receipt_conflict")] == RECEIPT_CONFLICT


def test_the_short_time_follows_the_zone_of_the_browser_and_the_exact_text_does_not(drawn):
    spec = {"projects": [project(row(seen=FIVE))]}
    moscow, new_york = drawn("ru", MOSCOW, **spec), drawn("ru", NEW_YORK, **spec)
    assert (moscow["zone"], new_york["zone"]) == (MOSCOW, NEW_YORK)
    first = [facts["lists"][0][0] for facts in (moscow, new_york)]
    assert first[0]["text"].endswith("ждёт с 29.09 12:20")
    assert first[1]["text"].endswith("ждёт с 29.09 05:20")
    assert first[0]["title"] == first[1]["title"] == "2026-09-29T09:20:00Z"
