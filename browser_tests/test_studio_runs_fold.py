"""The Runs screen at 1280x900: the scene and the shared inspector are where a person looks first.

A real frozen run, read through the production server, measured on the real Runs screen -- not in a
harness that draws the deck on its own. The title row and the team row are one row each, so the scene
starts high enough that either lens ends inside the first screen and the inspector begins inside it.
Both languages are measured, because the Russian words are longer and must not push anything down.
"""
import pytest
from playwright.sync_api import Browser, expect

from browser_tests.test_studio_layout import _model_form, configured_project, project  # noqa: F401
from browser_tests.test_studio_lifecycle import _Project, _open
from browser_tests.test_studio_tasks import _open_run
from browser_tests.test_studio_participants import _detail
from browser_tests.test_studio_rendered import studio, studio_url  # noqa: F401

MEASURE = """lens => {
  const box = (node) => node ? node.getBoundingClientRect() : null;
  const deck = document.querySelector('#bodyRuns [data-deck-run]');
  const scene = lens === 'orbit' ? deck.querySelector('.studio-deck__fleet') : deck.querySelector('.studio-trace');
  const inspector = deck.querySelector('.studio-deck__inspector');
  const centre = (node) => { const b = box(node); return b ? b.top + b.height / 2 : null; };
  return {
    scene_top: box(scene).top, scene_bottom: box(scene).bottom,
    inspector_top: box(inspector).top, inspector_h4_bottom: box(inspector.querySelector('h4')).bottom,
    title: centre(document.querySelector('#bodyRuns .studio-runs__detail h2')),
    picker: centre(document.querySelector('#bodyRuns .studio-run-picker summary')),
    refresh: centre(document.querySelector('#bodyRuns [data-focus-key="action:refreshRuns"]')),
    team: centre(deck.querySelector('h3')),
    lenses: centre(deck.querySelector('.studio-lenses')),
    roster: centre(deck.querySelector('.studio-team-roster')),
    overflow: document.documentElement.scrollWidth - innerWidth,
    stages: [...deck.querySelectorAll('.studio-deck__inspector .studio-step-flow__stage')].map((node) => {
      const b = box(node); return [Math.round(b.top), Math.round(b.left)]; }),
    picker_row: centre(deck.querySelector('.studio-deck__inspector select')),
    heading_row: centre(deck.querySelector('.studio-deck__inspector h4')),
  };
}"""


@pytest.mark.parametrize("language", ["en", "ru"])
@pytest.mark.parametrize("lens", ["trassa", "orbit"])
def test_both_lenses_and_the_inspector_start_inside_the_first_screen_at_1280x900(
        chromium: Browser, configured_project: _Project, language: str, lens: str) -> None:
    page, window = _open(chromium, configured_project, double=True)
    try:
        _model_form(page, "fold-flow")
        _open_run(page, "fold-run")
        page.set_viewport_size({"width": 1280, "height": 900})
        if language != "en":
            page.locator('[data-focus="preference-language"]').select_option(language)
        page.locator("#navRuns").click()
        deck = page.locator('[data-deck-run="fold-run"]')
        expect(deck.locator(".studio-trace")).to_be_visible()
        deck.locator(f'[data-run-lens="{lens}"]').click()
        expect(deck.locator(f'[data-run-lens="{lens}"]')).to_have_attribute("aria-pressed", "true")
        seen = page.evaluate(MEASURE, lens)
        assert seen["overflow"] <= 0, seen
        # One row for what is being read and where to go next: the run's name and its controls.
        assert abs(seen["title"] - seen["picker"]) < 12 and abs(seen["title"] - seen["refresh"]) < 12, seen
        # One row for the team: its heading, the two lenses and the roster.
        assert abs(seen["team"] - seen["lenses"]) < 12 and abs(seen["team"] - seen["roster"]) < 12, seen
        # The scene ends inside the first screen, and the inspector begins inside it with its heading.
        assert seen["scene_bottom"] <= 900, seen
        assert seen["inspector_top"] <= 810 and seen["inspector_h4_bottom"] <= 900, seen
        # Under the scene, compact: who and which step on one row, then input, action and result side by side,
        # beginning inside the first screen.
        assert abs(seen["heading_row"] - seen["picker_row"]) < 12, seen
        tops, lefts = [top for top, _ in seen["stages"]], [left for _, left in seen["stages"]]
        assert len(tops) == 3 and max(tops) - min(tops) <= 2 and lefts == sorted(set(lefts)), seen
        assert max(tops) <= 860, seen
        assert window.page_errors == []
    finally:
        page.context.close()



def _long_plan() -> dict:
    """Fourteen steps in a chain: a plan wider than a narrow scene, so the Trace scrolls."""
    detail = _detail()
    nodes = [{"node_id": f"step-{i:02d}", "title": f"Step {i}", "kind": "task",
              "instance_id": "alpha" if i % 2 else "beta"} for i in range(1, 15)]
    graph = detail["graph"]
    graph["definition"]["nodes"] = nodes
    graph["definition"]["edges"] = [{"from_node": a["node_id"], "to_node": b["node_id"]}
                                    for a, b in zip(nodes, nodes[1:])]
    graph["runtime"]["nodes"] = [{"node_id": n["node_id"], "phase": "idle", "outcome": None,
                                  "attempt_ids": []} for n in nodes]
    graph["schedule"]["nodes"] = [{"node_id": n["node_id"], "state": "runnable" if at == 0 else "blocked",
                                   "blocked_by": [] if at == 0 else [nodes[at - 1]["node_id"]]}
                                  for at, n in enumerate(nodes)]
    return detail


MOUNT = """async detail => {
  const {mountRuns} = await import('/panel/studio-runs.js');
  let mount = document.getElementById('deckTest');
  if (!mount) {
    mount = document.createElement('div'); mount.id = 'deckTest'; mount.style.width = '720px';
    mount.className = 'studio-shell'; document.body.append(mount);
  }
  mountRuns(mount, {runs: {phase: 'ready', list: [], selectedId: detail.run.run_id, detail}}, {});
}"""


def test_a_new_read_of_the_same_run_keeps_the_trace_where_the_person_scrolled_it(studio) -> None:
    """Re-drawing the deck for the same run keeps the Trace's scroll; only a new run re-centres it."""
    page, problems = studio
    detail = _long_plan()
    page.evaluate(MOUNT, detail)
    page.locator('#deckTest [data-run-lens="trassa"]').evaluate("node => node.click()")
    trace = page.locator("#deckTest .studio-trace")
    expect(trace).to_be_visible()
    page.wait_for_function("() => document.querySelector('#deckTest .studio-trace').scrollWidth > 0")
    room = trace.evaluate("node => node.scrollWidth - node.clientWidth")
    assert room > 40, ("control: the plan is wider than the scene, so there is somewhere to scroll", room)
    trace.evaluate("node => { node.scrollLeft = node.scrollWidth; }")
    before = trace.evaluate("node => node.scrollLeft")
    assert before > 40, before
    page.evaluate(MOUNT, detail)
    page.wait_for_timeout(150)  # the Trace lays itself out on its own ResizeObserver turn
    after = page.locator("#deckTest .studio-trace").evaluate("node => node.scrollLeft")
    assert abs(after - before) <= 1, (before, after)
    assert problems == []


CARD = """async detail => {
  const {cycleCard} = await import('/panel/studio-runhead.js');
  const card = cycleCard({locale: 'en', workflows: {list: [{workflow_id: 'standard', title: 'Standard cycle'}]}},
    detail, false);
  document.body.append(card);
  return {process: card.querySelector('strong').textContent, crew: card.querySelector('p').textContent,
    loops: [...card.querySelectorAll('[data-cycle-loop]')].map((node) => [node.dataset.cycleLoop, node.textContent]),
    members: [...card.querySelectorAll('[data-cycle-member]')].map((node) => node.textContent)};
}"""


def test_the_cycle_card_states_each_loop_of_the_shipped_standard_with_its_own_bound(studio) -> None:
    """Revision 5 has two loops with different bounds; the card never folds them into one number."""
    from tests.test_command_graph_dalio import shipped

    page, problems = studio
    definition = shipped("dalio-v5").as_dict()
    titles = {node["node_id"]: node.get("title") for node in definition["nodes"]}
    detail = {"run": {"run_id": "run-card"}, "graph": {"definition": definition}, "config": {
        "workflow": {"id": "standard", "revision": 5},
        "instances": [{"id": "doer", "adapter": "claude-code"}, {"id": "checker", "adapter": "codex-cli"}]}}
    seen = page.evaluate(CARD, detail)
    assert seen["process"] == "Standard cycle · revision 5"
    assert seen["crew"] == "Participants: 2 · human gates: 2"
    assert seen["loops"] == [
        ["correct", f"{titles['correct']}: up to 2 passes, back to «{titles['do']}»"],
        ["retry-loop", f"{titles['retry-loop']}: up to 3 passes, back to «{titles['identify']}»"]]
    assert seen["members"] == ["doer · claude-code", "checker · codex-cli"]
    assert problems == []
