"""The "Continue after" block of the console, in a real Chromium (spec 5.8, 4.3.4).

The block is the flag of the project's turn in the queue: a switch, the runs whose grant can
still be continued, the start of the task queue, one save that writes the flag in the name of the
person at the page, and one line that says what the flag is. It is drawn only in a desk a hub
frames (`embed=hub`), from the read of `/command/project/auto-continue`; the routes of that flag
were not in lane D1's branch when this was written, so they are answered in the page by
`desk_flag_fake.py`, in the record shape lane H's hand-off fixes, and the runs to continue are
given by answering the automation read of the newest run of each task. What this module holds,
each as a measurement of the page:

- only the runs whose grant can be continued have a mark (a pause, or a wait for an explicit
  resume), oldest first; a run whose grant expired has none and says why; nothing is sent until a
  person presses Save, and Save waits for the person's name;
- a save is ONE write whose body is exactly `{enabled, actor, resume_runs, start_task_queue}`, the
  runs in the order of the list and the actor the one of the console, through the transport's
  door with the project claim and the session token; the line then says the flag stands;
- taking the flag off is the same write with nothing listed and no queue start;
- a flag that stands opens with its runs marked, a consumed one reads "executed" with its switch
  off, and a refused save says so in place and keeps the marks; a `project_mismatch` on the
  write ends the desk;
- a desk nobody framed has no block and never reads the flag;
- a hash the hub sends closes the block when it moves the desk away from it (spec 4.5.3, step 2.1):
  a changed task with no panel in the same hash -- even while the read of the flag is still out --
  or a panel other than `continue`: the desk then opens that panel (`run`, `cycle` or `people`,
  which it mounts), the address it keeps says that panel in place of `continue`, and the other two
  toggles stand closed; a task sent together with `panel=continue` leaves the block open;
- no raw token in the words of the console, and nothing in any storage.

A fact and its sentence are read in ONE evaluation, as `test_desk_shell.py` does.
"""
from __future__ import annotations

import json

import pytest
from playwright.sync_api import Route

from browser_tests import desk_flag_fake as fake
from browser_tests.test_desk_embed import (  # noqa: F401  (fixtures and helpers)
    PROJECT, Embedded, Rig, _answering, _claim, _listen, embed, rig)
from browser_tests.test_desk_hash import ON_RUN, QUIET
from browser_tests.desk_settled import FOREIGN_SAID, SETTLED
from browser_tests.test_desk_status import RAW

#: The newest run of each task that has one, as the desk reads them, and what each says.
AUTOMATIONS = {
    "run-fix-new": fake.automation("run-fix-new", "paused", "paused"),
    "run-docs": fake.automation("run-docs", "restart_required", "explicit_resume_required"),
    "run-check": fake.automation("run-check", "expired", "expired"),
}
#: Oldest first: `run-check` and `run-docs` were made together (by id), `run-fix-new` later.
LISTED = ["run-check", "run-docs", "run-fix-new"]
TITLES = {"run-check": "Check the export", "run-docs": "Write the docs",
          "run-fix-new": "Fix lost text"}
WORDS = {
    "en": {"head": "Continue after", "runs": "Continue runs",
           "expired": "permission expired — a new confirmation of terms is needed",
           "need_name": "Give your name above to record the flag in it.",
           "standing": "Flag set since 09/30 14:05 · vasya",
           "consumed": "Flag executed on activation 09/30 16:40 · vasya",
           "save": "Save", "clear": "Remove the flag"},
    "ru": {"head": "Продолжить после", "runs": "Продолжить запуски",
           "expired": "разрешение истекло — нужно новое подтверждение условий",
           "need_name": "Укажите имя выше, чтобы записать флаг от вашего имени.",
           "standing": "Флаг стоит с 30.09 14:05 · vasya",
           "consumed": "Флаг исполнен при активации 30.09 16:40 · vasya",
           "save": "Сохранить", "clear": "Снять флаг"},
}
#: Everything a test asks of the block, in one evaluation; `textContent`, because the style
#: draws the headings in capitals.
BLOCK = """() => {
  const block = document.querySelector("#deskPult .desk-flag");
  if (!block) return null;
  const control = (key) => block.querySelector(`[data-focus-key="${key}"]`);
  const text = (node) => (node ? node.textContent.trim() : null);
  const hint = block.querySelector("[data-flag-hint]");
  return {
    open: block.open, head: text(block.querySelector("summary")),
    runs: text(block.querySelector("legend")),
    enabled: control("flag:enabled") ? control("flag:enabled").checked : null,
    queue: control("flag:queue") ? control("flag:queue").checked : null,
    rows: [...block.querySelectorAll("[data-run-id]")].map((row) => {
      const mark = row.querySelector("input[type=checkbox]");
      return {run: row.dataset.runId, title: text(row.querySelector("[data-flag-title]")),
        note: text(row.querySelector("[data-flag-note]")),
        mark: mark ? mark.checked : null};
    }),
    line: text(block.querySelector("[data-flag-line]")),
    verdicts: [...block.querySelectorAll("[data-verdict-run]")].map((row) => ({
      run: row.dataset.verdictRun, verdict: row.dataset.flagVerdict,
      title: text(row.querySelector("[data-flag-title]")),
      note: text(row.querySelector("[data-flag-note]"))})),
    save: control("flag:save") ? [text(control("flag:save")), control("flag:save").disabled] : null,
    clear: control("flag:clear") ? [text(control("flag:clear")), control("flag:clear").disabled]
      : null,
    hint: hint ? [text(hint), hint.hidden] : null,
    sizes: [...block.querySelectorAll("button, input, summary")].map((node) => {
      const box = node.getBoundingClientRect();
      return [node.tagName, Math.round(box.height)];
    })};
}"""
CONSOLE_TEXT = "() => document.getElementById('deskPult').innerText"
STORAGE = "() => [localStorage.length, sessionStorage.length]"
FRAMED = "#project={project}&embed=hub&lang={language}"


def _open(embed, rig, language, *, server=None, automations=AUTOMATIONS, before=None):
    """A framed desk on the seeded project with the flag door and the automation reads given."""
    server = server if server is not None else fake.FlagServer()
    window = embed(FRAMED.format(project=PROJECT, language=language),
                   _answering(_claim(hub_origin=rig.host_origin)),
                   flag=server, automations=automations, before=before)
    window.frame.wait_for_selector("#deskPult .desk-flag", timeout=6000)
    return window, server


def _name(window, who: str) -> None:
    """Give the console the name of the person at the page, as a person does."""
    window.frame.locator('[data-focus-key="pult:actor-change"]').click()
    window.frame.locator('[name="actor"]').fill(who)
    window.frame.locator('[data-focus-key="pult:actor-save"]').click()


def _open_block(window) -> None:
    window.frame.locator("#deskPult .desk-flag > summary").click()


@pytest.mark.parametrize("language", ["en", "ru"])
def test_continue_block_offers_only_resumable_runs_and_writes_the_flag_with_the_actor(
        embed, rig, language):
    words = WORDS[language]
    window, server = _open(embed, rig, language)
    window.frame.wait_for_function(SETTLED)
    opening = window.frame.evaluate(BLOCK)
    assert (opening["open"], opening["head"], opening["runs"]) == (
        False, words["head"], words["runs"])
    assert [row["run"] for row in opening["rows"]] == LISTED
    assert [(row["run"], row["title"], row["note"], row["mark"]) for row in opening["rows"]] == [
        ("run-check", TITLES["run-check"], words["expired"], None),
        ("run-docs", TITLES["run-docs"], None, False),
        ("run-fix-new", TITLES["run-fix-new"], None, False)]
    assert (opening["enabled"], opening["queue"], opening["line"]) == (False, False, None)
    assert opening["save"] == [words["save"], True] and opening["clear"][1] is True
    assert opening["hint"] == [words["need_name"], False]
    _name(window, "vasya")
    _open_block(window)
    window.frame.locator('[data-focus-key="flag:enabled"]').check()
    for run in ("run-fix-new", "run-docs"):  # marked newest first: the body is the list's order
        window.frame.locator(f'[data-focus-key="flag:run:{run}"]').check()
    window.frame.locator('[data-focus-key="flag:queue"]').check()
    ready = window.frame.evaluate(BLOCK)
    assert ready["open"] is True and ready["save"][1] is False and ready["hint"][1] is True
    assert server.posts == [] and server.reads == 1, "nothing is written before the press"
    window.frame.locator('[data-focus-key="flag:save"]').click()
    window.frame.wait_for_function(
        "(line) => document.querySelector('#deskPult [data-flag-line]')?.textContent === line",
        arg=words["standing"])
    assert server.posts == [{"enabled": True, "actor": "vasya",
                             "resume_runs": ["run-docs", "run-fix-new"],
                             "start_task_queue": True}]
    assert list(server.posts[0]) == ["enabled", "actor", "resume_runs", "start_task_queue"]
    sent = server.headers[0]
    assert sent["x-conduct-project"] == PROJECT and sent["x-conduct-csrf"]
    after = window.frame.evaluate(BLOCK)
    assert (after["enabled"], after["queue"], after["line"]) == (True, True, words["standing"])
    assert [(row["run"], row["mark"]) for row in after["rows"]] == [
        ("run-check", None), ("run-docs", True), ("run-fix-new", True)]
    assert not RAW.search(window.frame.evaluate(CONSOLE_TEXT))
    assert window.frame.evaluate(STORAGE) == [0, 0] and window.problems == []


@pytest.mark.parametrize("language", ["en", "ru"])
def test_taking_the_flag_off_writes_nothing_listed_and_no_queue_start(embed, rig, language):
    words = WORDS[language]
    server = fake.FlagServer(record=fake.standing("vasya", ("run-docs", "run-fix-new"), True))
    window, server = _open(embed, rig, language, server=server)
    _name(window, "petya")
    _open_block(window)
    window.frame.locator('[data-focus-key="flag:clear"]').click()
    window.frame.wait_for_function(
        "() => document.querySelector('#deskPult [data-focus-key=\"flag:enabled\"]')"
        "?.checked === false")
    assert server.posts == [{"enabled": False, "actor": "petya", "resume_runs": [],
                             "start_task_queue": False}]
    after = window.frame.evaluate(BLOCK)
    assert (after["enabled"], after["queue"], after["line"]) == (False, False, None)
    assert [row["mark"] for row in after["rows"]] == [None, False, False]
    assert after["clear"][0] == words["clear"] and window.problems == []


@pytest.mark.parametrize("language", ["en", "ru"])
def test_a_flag_that_stands_opens_with_its_runs_marked_and_says_who_set_it_and_when(
        embed, rig, language):
    words = WORDS[language]
    server = fake.FlagServer(record=fake.standing("vasya", ("run-docs", "run-check"), True))
    window, _server = _open(embed, rig, language, server=server)
    facts = window.frame.evaluate(BLOCK)
    assert (facts["enabled"], facts["queue"], facts["line"]) == (True, True, words["standing"])
    assert [(row["run"], row["mark"]) for row in facts["rows"]] == [
        ("run-check", None), ("run-docs", True), ("run-fix-new", False)]


@pytest.mark.parametrize("language", ["en", "ru"])
def test_a_consumed_flag_reads_executed_and_its_switch_is_off(embed, rig, language):
    words = WORDS[language]
    server = fake.FlagServer(record=fake.consumed("vasya", ("run-docs",)))
    window, _server = _open(embed, rig, language, server=server)
    facts = window.frame.evaluate(BLOCK)
    assert (facts["enabled"], facts["line"]) == (False, words["consumed"])
    assert [row["mark"] for row in facts["rows"]] == [None, False, False]


#: What a consumed flag says of a listed run that changed after it (spec 5.8, 4.3.4).
CHANGED = {"en": "Flag not applied: the run changed after it",
           "ru": "Флаг не применён: после него запуск изменился"}
#: The three listed runs of a consumed flag: one the flag's own resume continued, one that a
#: person paused after the flag, one that waits where the flag left it.
VERDICT_READS = {
    "run-check": fake.automation("run-check", "restart_required", "explicit_resume_required",
                                 bound=True, current=fake.control(fake.FLAG_RESUME)),
    "run-docs": fake.automation("run-docs", "paused", "paused", bound=True,
                                current=fake.control("control-9", "pause")),
    "run-fix-new": fake.automation("run-fix-new", "restart_required",
                                   "explicit_resume_required", bound=True),
}


@pytest.mark.parametrize("language", ["en", "ru"])
def test_a_consumed_flag_says_which_listed_run_changed_after_it_and_says_nothing_of_the_rest(
        embed, rig, language):
    server = fake.FlagServer(record=fake.consumed("vasya", LISTED))
    window, _server = _open(embed, rig, language, server=server, automations=VERDICT_READS)
    facts = window.frame.evaluate(BLOCK)
    assert facts["verdicts"] == [{"run": "run-docs", "verdict": "changed",
                                  "title": TITLES["run-docs"], "note": CHANGED[language]}]
    assert not RAW.search(window.frame.evaluate(CONSOLE_TEXT)) and window.problems == []


@pytest.mark.parametrize("record", [
    fake.standing("vasya", LISTED), fake.record()], ids=["a flag that stands", "no flag"])
def test_a_flag_that_was_not_consumed_says_nothing_of_the_runs(embed, rig, record):
    window, _server = _open(embed, rig, "en", server=fake.FlagServer(record=record),
                            automations=VERDICT_READS)
    assert window.frame.evaluate(BLOCK)["verdicts"] == []


def test_a_listed_run_whose_automation_was_not_read_is_not_said_to_have_changed(embed, rig):
    """The read of `run-docs` fails (the page answers 500), so the desk holds nothing of it."""
    server = fake.FlagServer(record=fake.consumed("vasya", LISTED))
    reads = {key: value for key, value in VERDICT_READS.items() if key != "run-docs"}
    window, _server = _open(embed, rig, "en", server=server, automations=reads,
                            before=lambda page: page.route(
                                "**/command/runs/run-docs/automation",
                                lambda route: route.fulfill(status=500, body="{}")))
    assert window.frame.evaluate(BLOCK)["verdicts"] == []


def test_a_refused_save_says_so_in_place_and_keeps_the_marks(embed, rig):
    server = fake.FlagServer(refuse=(422, {"error": {
        "code": "contract_invalid", "message": "the body is not a contract",
        "detail": {"run_id": "run-docs"}}}))
    window, server = _open(embed, rig, "en", server=server)
    _name(window, "vasya")
    _open_block(window)
    window.frame.locator('[data-focus-key="flag:enabled"]').check()
    window.frame.locator('[data-focus-key="flag:run:run-docs"]').check()
    window.frame.locator('[data-focus-key="flag:save"]').click()
    window.frame.wait_for_selector("#deskPult [data-flag-hint]:not([hidden])")
    facts = window.frame.evaluate(BLOCK)
    said = window.frame.evaluate("""async () => (await import("/panel/studio-i18n.js"))
      .message("en", "error.contract_invalid")""")
    assert facts["hint"] == [said, False]
    assert (facts["enabled"], facts["line"]) == (True, None)
    assert [row["mark"] for row in facts["rows"]] == [None, True, False]
    assert len(server.posts) == 1


def test_a_project_mismatch_on_the_save_ends_the_desk(embed, rig):
    server = fake.FlagServer(refuse=(409, {"error": {"code": "project_mismatch",
                                                     "message": "x", "detail": {}}}))
    window, server = _open(embed, rig, "en", server=server)
    _name(window, "vasya")
    _open_block(window)
    window.frame.locator('[data-focus-key="flag:enabled"]').check()
    window.frame.locator('[data-focus-key="flag:save"]').click()
    window.frame.wait_for_function(FOREIGN_SAID)
    assert window.frame.evaluate(BLOCK) is None
    sent = len(server.posts)
    window.frame.evaluate(QUIET)
    assert len(server.posts) == sent == 1


def test_a_desk_nobody_framed_has_no_block_and_never_reads_the_flag(chromium, rig):
    context = chromium.new_context(viewport={"width": 1280, "height": 900})
    server = fake.FlagServer()
    try:
        page = context.new_page()
        problems, asked = _listen(page, rig)
        page.route("**/command/project/auto-continue", server.handle)
        page.goto(f"{rig.desk_url}#project={PROJECT}&embed=hub&lang=en", wait_until="load")
        page.wait_for_function(SETTLED)
        window = Embedded(page, page.main_frame, problems, asked)
        assert page.evaluate(BLOCK) is None and server.reads == 0
        assert window.problems == []
    finally:
        context.close()
    assert json.dumps(server.posts) == "[]"


# -- the view plate, and the address that opens the block ------------------------------------

PLATE_WORDS = {
    "en": "Preview · another project is running. Agents do not start here: tasks, materials, "
          "the cycle and the queue are recorded, the start belongs to the active project",
    "ru": "Просмотр · в работе другой проект. Агенты здесь не запускаются: задачи, материалы, "
          "цикл и очередь записываются, старт — у активного проекта"}
#: The plate and where it stands, in one evaluation: its words as a person reads them, whether it
#: is hidden, and whether it is entirely above the scene, inside the centre.
PLATE = """() => {
  const plate = document.getElementById("deskPlate");
  const scene = document.getElementById("deskScene").getBoundingClientRect();
  const box = plate.getBoundingClientRect();
  return {shown: !plate.hidden, text: plate.hidden ? null : plate.innerText.trim(),
    above: !plate.hidden && box.bottom <= scene.top && box.height > 0,
    inCentre: document.getElementById("deskCenter").contains(plate),
    pult: document.getElementById("deskPult").innerText};
}"""


def _claim_of(mode: str, rig: Rig) -> dict:
    return {**_claim(hub_origin=rig.host_origin), "mode": mode}


@pytest.mark.parametrize("language", ["en", "ru"])
def test_a_desk_whose_claim_says_view_shows_the_plate_above_the_centre(embed, rig, language):
    window = embed(FRAMED.format(project=PROJECT, language=language),
                   _answering(_claim_of("view", rig)))
    facts = window.frame.evaluate(PLATE)
    assert facts["shown"] and facts["text"] == PLATE_WORDS[language]
    assert facts["above"] and facts["inCentre"]
    assert not RAW.search(facts["pult"]) and window.problems == []


@pytest.mark.parametrize("mode", ["active", "paused"])
def test_a_desk_whose_claim_says_active_or_nothing_it_knows_shows_no_plate(embed, rig, mode):
    window = embed(FRAMED.format(project=PROJECT, language="en"),
                   _answering(_claim_of(mode, rig)))
    facts = window.frame.evaluate(PLATE)
    assert (facts["shown"], facts["text"]) == (False, None)


def test_a_desk_nobody_framed_shows_the_plate_when_its_claim_says_view(chromium, rig):
    context = chromium.new_context(viewport={"width": 1280, "height": 900})
    try:
        page = context.new_page()
        page.route("**/command/project", _answering(_claim_of("view", rig)))
        page.route("**/command/project/auto-continue", fake.FlagServer().handle)
        page.goto(f"{rig.desk_url}#project={PROJECT}&lang=ru", wait_until="load")
        page.wait_for_function(SETTLED)
        facts = page.evaluate(PLATE)
    finally:
        context.close()
    assert facts["text"] == PLATE_WORDS["ru"] and facts["above"]


def test_a_desk_that_went_foreign_shows_no_plate(embed, rig):
    window = embed(FRAMED.format(project=PROJECT, language="en"),
                   _answering(_claim(project_id="b" * 32, hub_origin=rig.host_origin)))
    assert window.frame.evaluate(PLATE)["shown"] is False


#: Where the keyboard is, and what the address says, in one evaluation.
WHERE = """() => ({hash: location.hash,
  focus: document.activeElement?.getAttribute("data-focus-key") ?? null,
  open: document.querySelector("#deskPult .desk-flag")?.open ?? null,
  changes: window.__hashchanges ?? 0,
  expanded: Object.fromEntries(["deskFlowToggle", "deskPeopleToggle", "deskRunToggle"].map(
    (id) => [id, document.getElementById(id).getAttribute("aria-expanded")]))})"""
#: The toggle of the top bar that stands for each panel a hub may name besides `continue`.
PANEL_TOGGLES = {"run": "deskRunToggle", "cycle": "deskFlowToggle", "people": "deskPeopleToggle"}


@pytest.mark.parametrize("language", ["en", "ru"])
def test_panel_continue_opens_the_block_and_the_router_writes_nothing(embed, rig, language):
    server = fake.FlagServer()
    window = embed(f"#project={PROJECT}&embed=hub&panel=continue&lang={language}",
                   _answering(_claim(hub_origin=rig.host_origin)), flag=server)
    window.frame.wait_for_selector("#deskPult .desk-flag[open]", timeout=6000)
    window.frame.wait_for_function(SETTLED)
    facts = window.frame.evaluate(WHERE)
    assert (facts["open"], facts["focus"]) == (True, "flag:summary")
    assert facts["hash"] == f"#project={PROJECT}&embed=hub&panel=continue&lang={language}"
    assert server.posts == [] and server.reads == 1 and window.problems == []


def test_a_hash_the_hub_sends_later_opens_the_block_without_a_reload_and_writes_nothing(
        embed, rig):
    server = fake.FlagServer()
    window, server = _open(embed, rig, "en", server=server)
    window.frame.wait_for_function(SETTLED)
    assert window.frame.evaluate(WHERE)["open"] is False
    marker = window.frame.evaluate("window.__marker")
    window.frame.evaluate("(hash) => location.replace(location.href.split('#')[0] + hash)",
                          f"#project={PROJECT}&embed=hub&panel=continue&lang=en")
    window.frame.wait_for_selector("#deskPult .desk-flag[open]", timeout=6000)
    facts = window.frame.evaluate(WHERE)
    assert (facts["open"], facts["focus"], facts["changes"]) == (True, "flag:summary", 1)
    assert window.frame.evaluate("window.__marker") == marker
    assert facts["hash"] == f"#project={PROJECT}&embed=hub&panel=continue&lang=en"
    assert server.posts == [] and window.problems == []


#: What the hub does to a desk it frames: it sets the hash of the frame and does not reload it.
HUB_SENDS = "(hash) => location.replace(location.href.split('#')[0] + hash)"
OPEN_BY_ADDRESS = f"#project={PROJECT}&embed=hub&panel=continue&lang=en"


def _hub_sends(window, hash_: str) -> None:
    """The hub sets the hash of its frame, and the desk's router has read it."""
    before = window.frame.evaluate("window.__hashchanges")
    window.frame.evaluate(HUB_SENDS, hash_)
    window.frame.wait_for_function("(count) => window.__hashchanges > count", arg=before)
    window.frame.evaluate(QUIET)


def _open_by_address(embed, rig, server=None):
    """A framed desk whose address asked for the block, and the block is open."""
    window = embed(OPEN_BY_ADDRESS, _answering(_claim(hub_origin=rig.host_origin)),
                   flag=server or fake.FlagServer())
    window.frame.wait_for_selector("#deskPult .desk-flag[open]", timeout=6000)
    window.frame.wait_for_function(SETTLED)
    return window


def test_a_task_the_hub_sends_alone_closes_the_block_and_the_address_loses_its_panel(embed, rig):
    window = _open_by_address(embed, rig)
    assert window.frame.evaluate(WHERE)["open"] is True
    _hub_sends(window, f"#project={PROJECT}&embed=hub&task=task-docs&lang=en")
    window.frame.wait_for_function(ON_RUN, arg="run-docs")
    window.frame.evaluate(QUIET)
    facts = window.frame.evaluate(WHERE)
    assert facts["open"] is False
    assert facts["hash"] == f"#project={PROJECT}&embed=hub&task=task-docs&run=run-docs&lang=en"
    assert window.problems == []


@pytest.mark.parametrize("panel", list(PANEL_TOGGLES))
def test_a_panel_the_hub_sends_other_than_continue_closes_the_block_and_the_desk_opens_it_instead(
        embed, rig, panel):
    server = fake.FlagServer()
    window = _open_by_address(embed, rig, server)
    _hub_sends(window, f"#project={PROJECT}&embed=hub&panel={panel}&lang=en")
    facts = window.frame.evaluate(WHERE)
    assert facts["open"] is False
    assert facts["hash"] == f"#project={PROJECT}&embed=hub&panel={panel}&lang=en"
    assert facts["expanded"] == {toggle: "true" if name == panel else "false"
                                 for name, toggle in PANEL_TOGGLES.items()}
    assert server.posts == [] and window.problems == []


def test_a_task_the_hub_sends_with_panel_continue_leaves_the_block_open(embed, rig):
    window = _open_by_address(embed, rig)
    hub = f"#project={PROJECT}&embed=hub&task=task-docs&panel=continue&lang=en"
    _hub_sends(window, hub)
    window.frame.wait_for_function(ON_RUN, arg="run-docs")
    window.frame.evaluate(QUIET)
    facts = window.frame.evaluate(WHERE)
    assert facts["open"] is True
    assert facts["hash"] == (f"#project={PROJECT}&embed=hub&task=task-docs&run=run-docs"
                             "&panel=continue&lang=en")


class _HeldRead(fake.FlagServer):
    """A flag door whose first read waits, for the test to let it answer."""

    waiting = None

    def handle(self, route) -> None:
        if route.request.method == "GET" and self.waiting is None and self.reads == 0:
            self.reads += 1
            self.waiting = route
            return
        super().handle(route)

    def release(self) -> None:
        self._say(self.waiting, 200, self.record)


def test_a_task_the_hub_sends_before_the_flag_is_read_keeps_the_block_closed_when_it_lands(
        embed, rig):
    held = _HeldRead()
    window = embed(OPEN_BY_ADDRESS, _answering(_claim(hub_origin=rig.host_origin)), flag=held)
    window.frame.wait_for_function(SETTLED)
    assert held.waiting is not None and window.frame.evaluate(BLOCK) is None
    _hub_sends(window, f"#project={PROJECT}&embed=hub&task=task-docs&lang=en")
    window.frame.wait_for_function(ON_RUN, arg="run-docs")
    held.release()
    window.frame.wait_for_selector("#deskPult .desk-flag", timeout=6000)
    window.frame.evaluate(QUIET)
    facts = window.frame.evaluate(WHERE)
    assert facts["open"] is False
    assert facts["hash"] == f"#project={PROJECT}&embed=hub&task=task-docs&run=run-docs&lang=en"
    assert held.posts == [] and window.problems == []


def test_the_address_follows_a_person_who_opens_and_closes_the_block(embed, rig):
    window, server = _open(embed, rig, "en")
    window.frame.wait_for_function(SETTLED)
    closed = f"#project={PROJECT}&embed=hub&lang=en"
    assert window.frame.evaluate(WHERE)["hash"] == closed
    _open_block(window)
    window.frame.wait_for_function("(hash) => location.hash === hash",
                                   arg=f"#project={PROJECT}&embed=hub&panel=continue&lang=en")
    assert window.frame.evaluate(WHERE)["changes"] == 0, "the desk's own write fires no event"
    _open_block(window)
    window.frame.wait_for_function("(hash) => location.hash === hash", arg=closed)
    assert server.posts == [] and window.problems == []


#: What the block says of itself each time the console is drawn again, kept page-side so that no
#: draw between two reads of the test is lost: the block's `open` and the address at that moment.
WATCH_BLOCK = """() => {
  window.__block = [];
  new MutationObserver(() => window.__block.push([
    document.querySelector("#deskPult .desk-flag")?.open ?? null, location.hash])
  ).observe(document.getElementById("deskPult"),
    {childList: true, subtree: true, attributes: true, attributeFilter: ["open"]});
}"""


def test_a_block_opened_while_the_boot_reads_is_not_closed_by_the_boot_that_draws_a_task(
        embed, rig):
    """The address names a task and no panel. Its first navigation resets the keys the address
    does not carry, but a desk that has written no address has nothing to reset: the block is the
    person's, and it is not closed for an instant (the address losing its panel with it) to be
    opened again by the echo of the element it replaced."""
    held: list[Route] = []
    window = embed(
        f"#project={PROJECT}&embed=hub&task=task-fix&lang=en",
        _answering(_claim(hub_origin=rig.host_origin)), automations=AUTOMATIONS, wait=False,
        before=lambda page: page.route("**/command/tasks", lambda route: held.append(route)))
    window.frame.wait_for_selector("#deskPult .desk-flag", timeout=6000)
    assert len(held) == 1, "the block is drawn while the boot's list read is still held"
    _open_block(window)
    window.frame.evaluate(WATCH_BLOCK)
    held[0].continue_()
    window.frame.wait_for_function(ON_RUN, arg="run-fix-new")
    window.frame.evaluate(QUIET)
    drawn = window.frame.evaluate("window.__block")
    assert drawn and all(opened is True for opened, _hash in drawn), drawn
    assert all("panel=continue" in hash_ for _opened, hash_ in drawn), drawn
    assert window.frame.evaluate(WHERE)["hash"] == (
        f"#project={PROJECT}&embed=hub&task=task-fix&run=run-fix-new&panel=continue&lang=en")
    assert window.problems == []


def test_a_desk_nobody_framed_drops_panel_continue_from_its_address(chromium, rig):
    context = chromium.new_context(viewport={"width": 1280, "height": 900})
    try:
        page = context.new_page()
        page.route("**/command/project/auto-continue", fake.FlagServer().handle)
        page.goto(f"{rig.desk_url}#project={PROJECT}&panel=continue&lang=en", wait_until="load")
        page.wait_for_function(SETTLED)
        page.wait_for_function("(hash) => location.hash === hash",
                               arg=f"#project={PROJECT}&lang=en")
        assert page.evaluate(BLOCK) is None
    finally:
        context.close()
