"""A press made while the desk is still booting is the person's choice, and the boot keeps it.

The boot reads the address once, at its start, and applies it when its reads have landed: the
claim first, then the lists, then the run its address names. A person on a slow machine can press
a panel's toggle in between. The reads of the boot are HELD here, which is the window a slow
machine makes, and the press is a real click made inside it.

What is judged, for each of the three toggles ("Cycle", "People", "Run"):

- the control is on from the first moment and shows the press (`aria-expanded`), and nothing
  opens (no region, no request) before the claim has answered: the choice is only recorded;
- when the boot has applied its address, the person's LAST choice is the panel that is open, and
  the address (the hash) says it beside the task and the run the address named: a bookmarked task
  is not lost, and the task and run are applied before the panel (spec 4.5.3);
- a press again changes the choice, and the same toggle pressed twice is a choice of no panel,
  which also replaces a panel the address named;
- a desk the claim ends (another project) opens nothing, and the router that listens to the
  address still moves the desk after the boot.

The new task button is NOT a toggle. It is off until the claim names a mode and until the boot has
applied its address, and stays off, visibly, until then: a wizard is a flow with reads of its own
and typed text, and the address may open one itself (`new=task`, `prepare=1`), so a press that was
only remembered would have to be opened after the address's own wizard and could duplicate it.
"""
from __future__ import annotations

import json
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import Browser, Page, expect

from browser_tests.desk_hold import Hold, close_context, until
from browser_tests.desk_settled import FOREIGN_SAID
from browser_tests.test_desk_hash import ON_RUN, QUIET
from browser_tests.test_desk_rail_scene import seeded_url  # noqa: F401  (a fixture)

#: What each toggle of the top bar opens: the word of the address and the region that shows it.
PANELS = {"deskFlowToggle": ("cycle", "#deskFlow"), "deskPeopleToggle": ("people", "#deskPeople"),
          "deskRunToggle": ("run", "#deskRun")}
#: The reads of the boot that a test may hold: the claim comes first, the lists after it, and the
#: run of the task an address names last.
CLAIM, TASKS, RUN = "**/command/project", "**/command/tasks", "**/command/runs/run-fix-new"
#: The address of a desk that names a task and, with it, a panel that is not the one pressed.
BOOKMARK = "#task=task-fix&panel=people&lang=en"
#: Another project than any the desk is bound to.
OTHER = "0123456789abcdef0123456789abcdef"


def _booting(chromium: Browser, seeded_url: str, fragment: str, read: str):  # noqa: F811
    """A window whose boot is waiting for `read`, which is held."""
    context = chromium.new_context(viewport={"width": 1100, "height": 1200})
    page = context.new_page()
    page.set_default_timeout(5000)
    held = Hold(page, read)
    held.hold()
    page.goto(f"{seeded_url}{fragment}", wait_until="load")
    until(page, f"the boot's read {read} is held", held.reached)
    return context, page, held


def _booted(page: Page) -> None:
    """The boot has applied its address: the stream opens after it, and not before."""
    expect(page.locator("#deskShell")).to_have_attribute("data-connection", "open")


def _address(page: Page) -> dict[str, list[str]]:
    return parse_qs(urlsplit(page.url).fragment)


def _says(page: Page, panel: str | None) -> None:
    """Each toggle says what is chosen: only the one of `panel` is pressed."""
    for control, (name, _region) in PANELS.items():
        expect(page.locator(f"#{control}")).to_have_attribute(
            "aria-expanded", str(name == panel).lower())


def _shows(page: Page, panel: str | None) -> None:
    """Only the region of `panel` is open (the scene is what is open when none is)."""
    for _control, (name, region) in PANELS.items():
        if name == panel:
            expect(page.locator(region)).to_be_visible()
        else:
            expect(page.locator(region)).to_be_hidden()
    if panel is None:
        expect(page.locator("#deskScene")).to_be_visible()
    else:
        expect(page.locator("#deskScene")).to_be_hidden()


@pytest.mark.parametrize("read", [CLAIM, TASKS], ids=["claim", "tasks"])
@pytest.mark.parametrize("control", list(PANELS))
def test_a_panel_pressed_while_the_boot_reads_is_open_when_the_read_lands(
        chromium: Browser, seeded_url: str, control: str, read: str):  # noqa: F811
    panel, _region = PANELS[control]
    context, page, held = _booting(chromium, seeded_url, "#lang=en", read)
    try:
        page.locator(f"#{control}").click()
        _says(page, panel)
        _shows(page, None)
        held.land()
        _booted(page)
        _says(page, panel)
        _shows(page, panel)
        assert _address(page)["panel"] == [panel]
    finally:
        close_context(context)


#: Each series of presses and the panel the person has chosen when it ends (`None`: none).
PRESSES = {
    "one": (["deskFlowToggle"], "cycle"),
    "a-second-replaces-the-first": (["deskFlowToggle", "deskRunToggle"], "run"),
    "the-last-of-three": (["deskRunToggle", "deskFlowToggle", "deskPeopleToggle"], "people"),
    "the-same-twice-is-none": (["deskFlowToggle", "deskFlowToggle"], None),
    "the-address-panel-twice-is-none": (["deskPeopleToggle", "deskPeopleToggle"], None),
    "none-then-a-panel": (["deskFlowToggle", "deskFlowToggle", "deskRunToggle"], "run"),
}


@pytest.mark.parametrize("read", [CLAIM, TASKS, RUN], ids=["claim", "tasks", "run"])
@pytest.mark.parametrize("series", list(PRESSES))
def test_the_last_press_made_while_the_boot_reads_is_the_panel_it_opens_whatever_the_address_says(
        chromium: Browser, seeded_url: str, series: str, read: str):  # noqa: F811
    """The address names the task and the people panel; the person's last choice replaces the
    panel, the task and the run it names are kept, and the panel opens only after the run does."""
    presses, chosen = PRESSES[series]
    context, page, held = _booting(chromium, seeded_url, BOOKMARK, read)
    try:
        shown = None
        for control in presses:
            page.locator(f"#{control}").click()
            panel = PANELS[control][0]
            shown = None if shown == panel else panel
            _says(page, shown)
        _shows(page, None)
        held.land()
        _booted(page)
        page.wait_for_function(ON_RUN, arg="run-fix-new")
        _says(page, chosen)
        _shows(page, chosen)
        assert _address(page) == {"task": ["task-fix"], "run": ["run-fix-new"], "lang": ["en"],
                                  **({"panel": [chosen]} if chosen else {})}
    finally:
        close_context(context)


def test_a_press_made_while_the_run_of_the_address_is_read_waits_for_that_run_to_open(
        chromium: Browser, seeded_url: str):  # noqa: F811
    """The selection comes first (spec 4.5.3): while its read is out the panel is not open."""
    context, page, held = _booting(chromium, seeded_url, BOOKMARK, RUN)
    try:
        page.locator("#deskFlowToggle").click()
        _says(page, "cycle")
        _shows(page, None)
        held.land()
        _booted(page)
        page.wait_for_function(ON_RUN, arg="run-fix-new")
        _shows(page, "cycle")
    finally:
        close_context(context)


def test_nothing_is_asked_and_nothing_opens_before_the_claim_has_answered(
        chromium: Browser, seeded_url: str):  # noqa: F811
    context = chromium.new_context(viewport={"width": 1100, "height": 1200})
    asked: list[str] = []
    try:
        page = context.new_page()
        page.set_default_timeout(5000)
        page.on("request", lambda request: asked.append(urlsplit(request.url).path)
                if "/command/" in request.url else None)
        held = Hold(page, CLAIM)
        held.hold()
        page.goto(f"{seeded_url}#lang=en", wait_until="load")
        until(page, "the claim is held", held.reached)
        for control in PANELS:
            page.locator(f"#{control}").click()
        page.evaluate(QUIET)
        assert asked == ["/command/project"], asked
        _shows(page, None)
        held.land()
        _booted(page)
        _shows(page, "run")
        assert asked[0] == "/command/project" and asked.index("/command/tasks") > 0
    finally:
        close_context(context)


def test_a_desk_the_claim_ends_opens_nothing_for_a_press_made_before_it_answered(
        chromium: Browser, seeded_url: str):  # noqa: F811
    context = chromium.new_context(viewport={"width": 1100, "height": 1200})
    kept, asked = [], []
    try:
        page = context.new_page()
        page.set_default_timeout(5000)
        page.on("request", lambda request: asked.append(urlsplit(request.url).path)
                if "/command/" in request.url else None)
        page.route(CLAIM, lambda route: kept.append(route))
        page.goto(f"{seeded_url}#project={OTHER}&lang=en", wait_until="load")
        until(page, "the claim is held", lambda: bool(kept))
        page.locator("#deskFlowToggle").click()
        kept[0].fulfill(status=200, content_type="application/json", body=json.dumps(
            {"project_id": "f" * 32, "hub_origin": None, "demo": False, "mode": "active"}))
        page.wait_for_function(FOREIGN_SAID)
        page.evaluate(QUIET)
        for control, (_name, region) in PANELS.items():
            expect(page.locator(f"#{control}")).to_be_hidden()
            expect(page.locator(region)).to_be_hidden()
        assert page.locator("#deskShell").get_attribute("data-state") == "refused"
        assert asked == ["/command/project"], asked
    finally:
        close_context(context)


def test_the_router_still_moves_a_desk_whose_boot_kept_a_press(
        chromium: Browser, seeded_url: str):  # noqa: F811
    context, page, held = _booting(chromium, seeded_url, "#lang=en", TASKS)
    try:
        page.locator("#deskFlowToggle").click()
        held.land()
        _booted(page)
        _shows(page, "cycle")
        page.evaluate("() => { location.hash = '#panel=run&lang=en'; }")
        _shows(page, "run")
        _says(page, "run")
        page.locator("#deskRunToggle").click()
        _shows(page, None)
        assert "panel" not in _address(page)
    finally:
        close_context(context)


@pytest.mark.parametrize("read", [CLAIM, TASKS], ids=["claim", "tasks"])
def test_every_toggle_is_on_while_the_boot_reads(
        chromium: Browser, seeded_url: str, read: str):  # noqa: F811
    context, page, held = _booting(chromium, seeded_url, "#lang=en", read)
    try:
        for control in PANELS:
            expect(page.locator(f"#{control}")).to_be_enabled()
        held.land()
        _booted(page)
        for control in PANELS:
            expect(page.locator(f"#{control}")).to_be_enabled()
    finally:
        close_context(context)


@pytest.mark.parametrize("read", [CLAIM, TASKS], ids=["claim", "tasks"])
def test_the_new_task_button_is_off_while_the_boot_reads_and_a_press_on_it_opens_no_wizard(
        chromium: Browser, seeded_url: str, read: str):  # noqa: F811
    context, page, held = _booting(chromium, seeded_url, "#lang=en", read)
    try:
        opener = page.locator("#deskNewTask")
        expect(opener).to_be_disabled()
        opener.click(force=True)
        page.evaluate(QUIET)
        expect(page.locator("#deskWizard")).to_be_hidden()
        held.land()
        _booted(page)
        expect(opener).to_be_enabled()
        expect(page.locator("#deskWizard")).to_be_hidden()
        assert "new" not in _address(page)
        opener.click()
        expect(page.locator("#deskWizard [data-wizard]")).to_be_visible()
        assert _address(page)["new"] == ["task"]
    finally:
        close_context(context)


# -- a hash that arrives while the boot reads, and the order of it and the presses ---------------

#: What the hub (or any page that opened the window) does to a mounted desk: it replaces the
#: address, changing only the fragment, and the desk hears a `hashchange`.
SEND = "(hash) => location.replace(location.href.split('#')[0] + hash)"
#: Which centre panel is shown, in the order it became so: a region that opens and closes again
#: is in the list, so a panel the boot opens and withdraws cannot pass for a panel never opened.
WATCH_REGIONS = """() => {
  const regions = {cycle: "deskFlow", people: "deskPeople", run: "deskRun"};
  const shown = new Set();
  window.__opened = [];
  const look = () => {
    for (const [name, id] of Object.entries(regions)) {
      const open = !document.getElementById(id).hidden;
      if (open && !shown.has(name)) window.__opened.push(name);
      if (open) shown.add(name); else shown.delete(name);
    }
  };
  const watch = new MutationObserver(look);
  for (const id of Object.values(regions)) {
    watch.observe(document.getElementById(id), {attributes: true});
  }
}"""
PANEL_HASH = "#panel=cycle&lang=en"
#: A column click of the hub on another task: the task and nothing else that names a panel.
COLUMN_CLICK = "#task=task-docs&lang=en"
FIX, DOCS = ("task-fix", "run-fix-new"), ("task-docs", "run-docs")
LANGUAGE_ONLY = "#lang=ru"
#: Each series is what happens while the boot reads, in order (`press <toggle>` or `hash <hash>`),
#: and where the desk must stand when the boot has applied it: the panel (`None`: none), the task
#: and run, and the language. The address the desk booted from names the task `task-fix` and the
#: panel `people`.
ORDER = {
    "a press then a hash that names another panel": (
        [("press", "deskRunToggle"), ("hash", PANEL_HASH)], "cycle", FIX, "en"),
    "a hash that names a panel then a press": (
        [("hash", PANEL_HASH), ("press", "deskPeopleToggle")], "people", FIX, "en"),
    "a press then a hash that names a panel then a press": (
        [("press", "deskRunToggle"), ("hash", PANEL_HASH), ("press", "deskPeopleToggle")],
        "people", FIX, "en"),
    "a press then a hash that only repeats what the address said": (
        [("press", "deskFlowToggle"), ("hash", "#task=task-fix&panel=people&lang=ru")],
        "cycle", FIX, "ru"),
    "a press then a hash of the language alone": (
        [("press", "deskFlowToggle"), ("hash", LANGUAGE_ONLY)], "cycle", FIX, "ru"),
    "a press then a hash of the language alone then the same press": (
        [("press", "deskFlowToggle"), ("hash", LANGUAGE_ONLY), ("press", "deskFlowToggle")],
        None, FIX, "ru"),
    "a press then a column click on another task": (
        [("press", "deskRunToggle"), ("hash", COLUMN_CLICK)], None, DOCS, "en"),
    "a column click on another task then a press": (
        [("hash", COLUMN_CLICK), ("press", "deskRunToggle")], "run", DOCS, "en"),
    "a column click on another task alone": ([("hash", COLUMN_CLICK)], None, DOCS, "en"),
    "a column click on another task then a hash of the language alone": (
        [("hash", COLUMN_CLICK), ("hash", LANGUAGE_ONLY)], None, DOCS, "ru"),
    "a column click on another task then a press then a hash of the language alone": (
        [("hash", COLUMN_CLICK), ("press", "deskRunToggle"), ("hash", LANGUAGE_ONLY)],
        "run", DOCS, "ru"),
    "a column click on another task then a hash that names a panel": (
        [("hash", COLUMN_CLICK), ("hash", PANEL_HASH)], "cycle", DOCS, "en"),
    "a hash of the language alone then a column click on another task": (
        [("hash", LANGUAGE_ONLY), ("hash", COLUMN_CLICK)], None, DOCS, "en"),
}


@pytest.mark.parametrize("read", [CLAIM, TASKS], ids=["claim", "tasks"])
@pytest.mark.parametrize("series", list(ORDER))
def test_the_presses_and_the_hashes_made_while_the_boot_reads_are_applied_in_the_order_they_came(
        chromium: Browser, seeded_url: str, series: str, read: str):  # noqa: F811
    """What a person pressed before a hash that names a panel is replaced by it, what they pressed
    after it replaces it, and a hash that names no panel (a language, a repeat) leaves both. The
    boot opens only the panel it ends on: nothing is opened that a later event withdrew. Two
    hashes are two choices, each applied against the address it carried and one after the other,
    so a column click is not lost to the language the hub sends after it."""
    events, panel, (task, run), language = ORDER[series]
    context, page, held = _booting(chromium, seeded_url, BOOKMARK, read)
    try:
        page.evaluate(WATCH_REGIONS)
        for kind, what in events:
            if kind == "press":
                page.locator(f"#{what}").click()
            else:
                page.evaluate(SEND, what)
        _shows(page, None)
        held.land()
        _booted(page)
        want = {"task": [task], "run": [run], "lang": [language],
                **({"panel": [panel]} if panel else {})}
        until(page, f"the desk to stand at {want}", lambda: _address(page) == want)
        page.wait_for_function(ON_RUN, arg=run)
        _says(page, panel)
        _shows(page, panel)
        assert page.evaluate("window.__opened") == ([panel] if panel else [])
    finally:
        close_context(context)


#: Two fragments set in ONE turn of the page: the window fires a `hashchange` for each, and by then
#: the address bar already says the second.
SEND_TWO = """(hashes) => {
  for (const hash of hashes) location.replace(location.href.split('#')[0] + hash);
}"""


@pytest.mark.parametrize("held", [True, False], ids=["while-the-boot-reads", "after-the-boot"])
def test_two_hashes_set_in_one_turn_are_each_applied_against_the_address_they_carried(
        chromium: Browser, seeded_url: str, held: bool):  # noqa: F811
    """A `hashchange` says the address it was fired for (`newURL`), not the one the bar says by
    the time it is heard: the column click is applied, and the language after it is applied too."""
    want = {"task": ["task-docs"], "run": ["run-docs"], "lang": ["ru"]}
    if held:
        context, page, hold = _booting(chromium, seeded_url, BOOKMARK, TASKS)
    else:
        context = chromium.new_context(viewport={"width": 1100, "height": 1200})
        page = context.new_page()
        page.set_default_timeout(5000)
        page.goto(f"{seeded_url}#task=task-fix&lang=en", wait_until="load")
        _booted(page)
        page.wait_for_function(ON_RUN, arg="run-fix-new")
    try:
        page.evaluate(SEND_TWO, [COLUMN_CLICK, LANGUAGE_ONLY])
        if held:
            hold.land()
            _booted(page)
        until(page, f"the desk to stand at {want}", lambda: _address(page) == want)
        page.wait_for_function(ON_RUN, arg="run-docs")
        _says(page, None)
        _shows(page, None)
    finally:
        close_context(context)


@pytest.mark.parametrize("control", list(PANELS))
def test_a_hash_of_the_language_alone_keeps_the_panel_the_person_has_open(
        chromium: Browser, seeded_url: str, control: str):  # noqa: F811
    """What a person chose inside the desk stays when the hub sends only the language."""
    panel, _region = PANELS[control]
    context = chromium.new_context(viewport={"width": 1100, "height": 1200})
    try:
        page = context.new_page()
        page.set_default_timeout(5000)
        page.goto(f"{seeded_url}#task=task-fix&lang=en", wait_until="load")
        _booted(page)
        page.wait_for_function(ON_RUN, arg="run-fix-new")
        page.locator(f"#{control}").click()
        _shows(page, panel)
        page.evaluate(SEND, LANGUAGE_ONLY)
        page.wait_for_function("() => document.documentElement.lang === 'ru'")
        until(page, "the desk to write its address", lambda: _address(page).get("lang") == ["ru"])
        _says(page, panel)
        _shows(page, panel)
        assert _address(page) == {"task": ["task-fix"], "run": ["run-fix-new"], "panel": [panel],
                                  "lang": ["ru"]}
    finally:
        close_context(context)


def test_a_hash_that_moves_the_task_closes_the_panel_and_one_that_moves_only_the_run_keeps_it(
        chromium: Browser, seeded_url: str):  # noqa: F811
    """A panel closes for a hash that names another panel and for another task, and for no other."""
    context = chromium.new_context(viewport={"width": 1100, "height": 1200})
    try:
        page = context.new_page()
        page.set_default_timeout(5000)
        page.goto(f"{seeded_url}#task=task-fix&lang=en", wait_until="load")
        _booted(page)
        page.wait_for_function(ON_RUN, arg="run-fix-new")
        page.locator("#deskPeopleToggle").click()
        page.evaluate(SEND, "#task=task-fix&run=run-fix-old&lang=en")
        page.wait_for_function(ON_RUN, arg="run-fix-old")
        _says(page, "people")
        _shows(page, "people")
        page.evaluate(SEND, "#task=task-docs&lang=en")
        page.wait_for_function(ON_RUN, arg="run-docs")
        _says(page, None)
        _shows(page, None)
        assert "panel" not in _address(page)
    finally:
        close_context(context)


def test_a_hash_that_repeats_the_task_the_address_named_leaves_the_run_the_address_named(
        chromium: Browser, seeded_url: str):  # noqa: F811
    """A hash heard while the boot reads is compared with what the boot drew, and not with an empty
    address: the task it repeats is no new task, so the older run the address named is kept."""
    context, page, held = _booting(
        chromium, seeded_url, "#task=task-fix&run=run-fix-old&lang=en", TASKS)
    try:
        page.evaluate(SEND, "#task=task-fix&lang=ru")
        held.land()
        _booted(page)
        want = {"task": ["task-fix"], "run": ["run-fix-old"], "lang": ["ru"]}
        until(page, f"the desk to stand at {want}", lambda: _address(page) == want)
        page.wait_for_function(ON_RUN, arg="run-fix-old")
    finally:
        close_context(context)


def test_a_hash_that_opens_the_wizard_leaves_the_panel_the_person_has_open(
        chromium: Browser, seeded_url: str):  # noqa: F811
    """`new=task` names no panel and moves no task: the wizard is drawn over the desk and the
    panel the person opened stays as it was (spec 4.5.3: a panel changes by its own key)."""
    context = chromium.new_context(viewport={"width": 1100, "height": 1200})
    try:
        page = context.new_page()
        page.set_default_timeout(5000)
        page.goto(f"{seeded_url}#task=task-fix&lang=en", wait_until="load")
        _booted(page)
        page.wait_for_function(ON_RUN, arg="run-fix-new")
        page.locator("#deskPeopleToggle").click()
        _shows(page, "people")
        page.evaluate(SEND, "#task=task-fix&run=run-fix-new&new=task&lang=en")
        expect(page.locator("#deskWizard [data-wizard]")).to_be_visible()
        _says(page, "people")
        _shows(page, "people")
    finally:
        close_context(context)
