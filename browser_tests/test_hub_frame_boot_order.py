"""A task chosen in the hub's column and a press on the desk's own toggle, both made while the desk
in the hub's frame is still booting, come out in the order the person made them.

The hub moves a mounted desk by replacing its fragment (`location.replace`), and the desk hears a
`hashchange` in the middle of its boot when the person is quicker than its reads. The reads of the
boot are HELD here, which is the window a slow machine makes: the desk is the real desk, served as
the project of the real hub, and the click is the person's click on the hub's column.

What is judged: a press made after the click is the panel the desk opens (it replaces whatever the
click meant), a click made after the press replaces the press (a column click is a new task, and a
new task starts with no panel), and the desk never opens a panel that a later event withdrew.
`test_desk_boot_presses.py` has the whole table, on a desk without a hub; this module is the same
two orders with the hub in front of it.
"""
from __future__ import annotations

from playwright.sync_api import Frame, expect

from browser_tests.desk_hold import Hold, until
from browser_tests.desk_settled import SETTLED
from browser_tests.hub_bench import lang  # noqa: F401  (a fixture)
from browser_tests.hub_live import A, LivePage, live, live_page, press  # noqa: F401
from browser_tests.test_hub_page_frame import running_a  # noqa: F401  (a fixture)

#: The first read of the desk's boot after the claim: the lists.
TASKS = "**/command/tasks"
#: Which centre panel is shown, in the order it became so, asked inside the frame.
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
FACTS = """() => ({
  chosen: [...document.querySelectorAll("#deskRail [data-task-id]")]
    .filter((row) => row.getAttribute("aria-pressed") === "true").map((row) => row.dataset.taskId),
  shown: ["deskFlow", "deskPeople", "deskRun"]
    .filter((id) => !document.getElementById(id).hidden),
  opened: window.__opened, hash: location.hash})"""


def _booting_desk(one: LivePage) -> tuple[Hold, Frame]:
    """Project `a` chosen in the column while the lists of its desk are held: the frame is
    mounted, its boot is waiting for the lists, and a watch on its panels is set."""
    held = Hold(one.page, TASKS)
    held.hold()
    press(one, f"project:{A}")
    until(one.page, "the desk's lists are held", held.reached)
    frame = one.page.wait_for_selector("#hubDesk iframe").content_frame()
    frame.evaluate(WATCH_REGIONS)
    return held, frame


def _lands(held: Hold, frame: Frame) -> dict:
    """The held lists land; the desk is judged once it has settled."""
    held.land()
    frame.wait_for_function(SETTLED)
    return frame.evaluate(FACTS)


def test_a_press_made_after_a_task_was_chosen_in_the_column_is_the_panel_the_desk_opens(running_a):
    one = running_a
    held, frame = _booting_desk(one)
    press(one, f"task:{A}:task-docs")
    frame.locator("#deskRunToggle").click()
    expect(frame.locator("#deskRunToggle")).to_have_attribute("aria-expanded", "true")
    facts = _lands(held, frame)
    assert facts["chosen"] == ["task-docs"]
    assert (facts["shown"], facts["opened"]) == (["deskRun"], ["run"])
    assert "task=task-docs" in facts["hash"] and "panel=run" in facts["hash"]


def test_a_task_chosen_in_the_column_after_a_press_replaces_it_and_no_panel_opens(running_a):
    one = running_a
    held, frame = _booting_desk(one)
    frame.locator("#deskRunToggle").click()
    expect(frame.locator("#deskRunToggle")).to_have_attribute("aria-expanded", "true")
    press(one, f"task:{A}:task-docs")
    facts = _lands(held, frame)
    assert facts["chosen"] == ["task-docs"]
    assert (facts["shown"], facts["opened"]) == ([], [])
    assert "task=task-docs" in facts["hash"] and "panel" not in facts["hash"]
