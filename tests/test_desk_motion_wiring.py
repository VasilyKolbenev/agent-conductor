"""The wire from the production desk to its transitions (spec 5.5), held as text.

`desk-motion.js` draws the desk's transitions and the model beside it decides what they are, and
both stood proven and unconnected: the desk drew its regions and never handed a view to the
module. What makes the transitions the desk's is a chain of three links, and a one-line edit cuts
any of them without any other check of the panel noticing:

- `desk.js` builds the view of the desk's state in `render()` and mounts the scene with it, once
  per render;
- `desk-scene.js` imports `watchMotion` and hands it that view as the first thing `mountScene`
  does, before the foreign plate and before the deck, so that every view reaches it;
- `desk-motion.js` is imported by the scene alone and the model by that module alone, so the
  page has one detector and one watcher, and a second source of views cannot share the first's
  baseline.

The module graph (`tests/test_studio_module_graph.py`) says who MAY import whom; it cannot say that
the edge is there. And a browser test that served the page an edited scene would stay green the day
the edit left the product, so the files of the browser side are held here to route nothing of the
panel. What the text cannot say, a browser says (`browser_tests/test_desk_motion.py`): that the
page was served the packaged bytes, and what the wire does with a real render.

Every check is a function over text, and the table at the end feeds each one the defect it claims
to refuse, planted in the real text, so a check that stopped biting reds here and not in a review.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.test_desk_motion_source import blank, functions
from tests.test_graph_source import _code

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "src" / "conductor" / "panel"
BROWSER = ROOT / "browser_tests"
SCENE, BOOT, MOTION, MODEL = "desk-scene.js", "desk.js", "desk-motion.js", "desk-motion-model.js"
#: The browser side of the motion tests: the bench that boots the desk and the test module.
BROWSER_FILES = ("desk_motion_bench.py", "test_desk_motion.py")
IMPORT = 'import {watchMotion} from "./desk-motion.js";'
FIRST = "watchMotion(view);"
MOUNT = "export function mountScene(mount, view, handlers) {"
BOOT_IMPORT = 'import {mountScene} from "./desk-scene.js";'
MOUNT_CALL = 'mountScene(byId("deskScene"), view, handlers);'
#: What the motion module reads of the view `render` builds. A view without one of them is a view
#: the detector reads as no change at all, quietly.
VIEW_FIELDS = ("connection", "foreign", "tasks", "runs", "automation", "queue", "taskId", "run")
#: Who may import each module of the transitions, and who may call what: one of each.
IMPORTERS = {MOTION: {SCENE}, MODEL: {MOTION}}
#: A call, and not the declaration of the function or a method of something else.
CALL = r"(?<!function )(?<![\w$.])"


def panel_code() -> dict[str, str]:
    """The text of every script of the panel, comments out, by file name."""
    return {path.name: _code(path) for path in sorted(PANEL.glob("*.js"))}


def browser_text() -> dict[str, str]:
    return {name: (BROWSER / name).read_text(encoding="utf-8") for name in BROWSER_FILES}


def scene_faults(code: str) -> list[str]:
    """The scene's side of the wire: one import, one call, and the call is the first statement."""
    faults = []
    imports = code.count(IMPORT)
    if imports != 1:
        faults.append(f"{SCENE} has {imports} imports of watchMotion, expected one")
    named = len(re.findall(r"\bwatchMotion\b", code))
    if named != 2:
        faults.append(f"watchMotion is named {named} times in {SCENE}, expected two: the import "
                      "and the one call")
    if code.count(MOUNT) != 1:
        return faults + [f"{SCENE} does not declare {MOUNT} once"]
    body = code[code.index(MOUNT) + len(MOUNT):].lstrip()
    if not body.startswith(FIRST):
        faults.append(f"the first statement of mountScene is not {FIRST}: {body[:40]!r}")
    return faults


def keys_of(text: str, opener: int) -> list[str]:
    """The keys of the object literal whose `{` stands at `opener` in `text` (strings blanked):
    the name before a colon, or the whole of a shorthand. A spread has no key."""
    parts, depth, start = [], 0, opener + 1
    for index in range(opener, len(text)):
        char = text[index]
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
            if depth == 0:
                parts.append(text[start:index])
                break
        elif char == "," and depth == 1:
            parts.append(text[start:index])
            start = index + 1
    found = (re.match(r"\s*([A-Za-z_$][\w$]*)", part) for part in parts if part.strip())
    return [one.group(1) for one in found if one is not None]


def boot_faults(code: str) -> list[str]:
    """The boot module's side: `render` mounts the scene once, with the view it has built."""
    faults = []
    if code.count(BOOT_IMPORT) != 1:
        faults.append(f"{BOOT} does not import mountScene from the scene exactly once")
    text = blank(code)
    renders = [one for one in functions(text) if one[0] == "render"]
    if len(renders) != 1:
        return faults + [f"{BOOT} declares {len(renders)} functions called render, expected one"]
    _name, brace, end = renders[0]
    body, shown = code[brace:end + 1], text[brace:end + 1]
    if len(re.findall(r"\bmountScene\s*\(", body)) != 1 or MOUNT_CALL not in body:
        faults.append(f"render does not call {MOUNT_CALL} exactly once")
    if len(re.findall(r"\bmountScene\s*\(", code)) != 1:
        faults.append(f"{BOOT} calls mountScene outside render, or not at all")
    built = re.search(r"\bconst\s+view\s*=\s*\{", shown)
    if built is None:
        return faults + ["render builds no `const view = {`"]
    missing = [name for name in VIEW_FIELDS if name not in keys_of(shown, built.end() - 1)]
    if missing:
        faults.append(f"the view render builds lacks {missing}, which the transitions read")
    return faults


def edge_faults(panel: dict[str, str]) -> list[str]:
    """Who imports the transitions and who starts them: one place each, so one detector."""
    faults = []
    for target, allowed in IMPORTERS.items():
        spelling = re.compile(r"""(?:\bfrom|\bimport)\s*\(?\s*["']\./""" + re.escape(target)
                              + r"""["']""")
        found = {name for name, code in panel.items() if spelling.search(code)}
        if found != allowed:
            faults.append(f"{target} is imported by {sorted(found)}, expected {sorted(allowed)}")
    for word, home in (("createDetector", MOTION), ("watchMotion", SCENE)):
        where = sorted(name for name, code in panel.items()
                       if re.search(CALL + word + r"\s*\(", code))
        if where != [home]:
            faults.append(f"{word} is called in {where}, expected {home} alone")
    return faults


def route_faults(files: dict[str, str]) -> list[str]:
    """A browser file that answers a file of the panel itself: the page would run what the test
    wrote and not what the product carries."""
    return [f"{name} routes a file of /panel/" for name, text in files.items()
            if re.search(r"\.route\([^)]*panel", text)]


def wiring_faults(panel: dict[str, str], browser: dict[str, str]) -> list[str]:
    return (scene_faults(panel[SCENE]) + boot_faults(panel[BOOT]) + edge_faults(panel)
            + route_faults(browser))


REAL = panel_code()
BROWSER_REAL = browser_text()


def test_the_scene_hands_every_view_to_the_transitions_before_it_draws_anything():
    assert scene_faults(REAL[SCENE]) == []
    assert REAL[SCENE].count(IMPORT) == 1 and REAL[SCENE].count(FIRST) == 1


def test_the_boot_module_mounts_the_scene_once_per_render_with_the_view_it_has_built():
    assert boot_faults(REAL[BOOT]) == []


def test_the_page_has_one_detector_one_watcher_and_one_importer_of_each_module():
    assert len(REAL) > 100, "the scan found too few scripts to be reading the panel"
    assert edge_faults(REAL) == []


def test_the_files_of_the_browser_side_route_nothing_of_the_panel():
    assert set(BROWSER_REAL) == set(BROWSER_FILES)
    assert route_faults(BROWSER_REAL) == []


def test_the_whole_chain_is_held_at_once_and_a_clean_answer_is_not_an_empty_one():
    assert wiring_faults(REAL, BROWSER_REAL) == []
    assert "function render()" in REAL[BOOT] and MOUNT in REAL[SCENE]
    assert "export function watchMotion(view)" in REAL[MOTION]


# -- the table: each defect the checks claim to refuse, and a word its fault must carry ---------


def _without_call(code: str) -> str:
    return code.replace(f"  {FIRST}\n", "")


#: Each defect as (where it is planted, the file, the change made to the file's text, the word its
#: fault must carry). It is planted when its test runs and not when the module is read, so a real
#: tree that already has the fault fails the checks above by name and not the whole module at once.
DEFECTS = {
    "the import taken out of the scene": (
        "panel", SCENE, lambda code: code.replace(IMPORT + "\n", ""), "imports of watchMotion"),
    "the call taken out of the scene": ("panel", SCENE, _without_call, "named 1 times"),
    "the call moved after the foreign plate": (
        "panel", SCENE, lambda code: _without_call(code).replace(
            "  const {phase, detail} = view.run;\n",
            f"  {FIRST}\n  const {{phase, detail}} = view.run;\n"), "first statement"),
    "the call made under a condition": (
        "panel", SCENE, lambda code: code.replace(f"  {FIRST}\n", f"  if (view.taskId) {FIRST}\n"),
        "first statement"),
    "the call made twice in the scene": (
        "panel", SCENE, lambda code: code.replace(f"  {FIRST}\n", f"  {FIRST}\n  {FIRST}\n"),
        "named 3 times"),
    "a second detector in the scene": (
        "panel", SCENE, lambda code: code + "\nconst second = createDetector();\n",
        "createDetector is called in"),
    "the model imported by the scene": (
        "panel", SCENE, lambda code: code + '\nimport {planOf} from "./desk-motion-model.js";\n',
        "desk-motion-model.js is imported by"),
    "the boot module importing the transitions too": (
        "panel", BOOT, lambda code: code + f"\n{IMPORT}\n", "desk-motion.js is imported by"),
    "the boot module calling the watcher itself": (
        "panel", BOOT, lambda code: code.replace(MOUNT_CALL, f"{MOUNT_CALL}\n  {FIRST}"),
        "watchMotion is called in"),
    "render no longer mounting the scene": (
        "panel", BOOT, lambda code: code.replace(MOUNT_CALL, ""), "does not call"),
    "render mounting the scene twice": (
        "panel", BOOT, lambda code: code.replace(MOUNT_CALL, f"{MOUNT_CALL}\n  {MOUNT_CALL}"),
        "does not call"),
    "the boot module not importing the scene": (
        "panel", BOOT, lambda code: code.replace(BOOT_IMPORT + "\n", ""),
        "does not import mountScene"),
    "the view without its connection": (
        "panel", BOOT, lambda code: code.replace("    connection, task:", "    task:"),
        "lacks ['connection']"),
    "the view without its foreign word": (
        "panel", BOOT, lambda code: code.replace("foreign: state.foreign, ", ""),
        "lacks ['foreign']"),
    "the view without its queue": (
        "panel", BOOT, lambda code: code.replace("queue: state.queue, ", ""), "lacks ['queue']"),
    "the view without the run it draws": (
        "panel", BOOT, lambda code: code.replace("run: state.run,", ""), "lacks ['run']"),
    "the bench serving its own scene": (
        "browser", "desk_motion_bench.py", lambda text: text + (
            '\npage.route("**/panel/desk-scene.js", lambda route: route.fulfill(body=""))\n'),
        "desk_motion_bench.py routes a file"),
    "the motion test serving its own module": (
        "browser", "test_desk_motion.py", lambda text: text + (
            '\ncontext.route(f"**/panel/{name}", answering(body))\n'),
        "test_desk_motion.py routes a file"),
    "a route over several lines": (
        "browser", "desk_motion_bench.py", lambda text: text + (
            '\npage.route(\n    re.compile(r"/panel/desk-scene\\.js"), handler)\n'),
        "desk_motion_bench.py routes a file"),
}


@pytest.mark.parametrize("where,name,change,word", list(DEFECTS.values()), ids=list(DEFECTS))
def test_the_guard_refuses_each_defect_and_names_it(where, name, change, word):
    texts = REAL if where == "panel" else BROWSER_REAL
    planted = change(texts[name])
    assert planted != texts[name], f"the defect did not land in {name}: its text moved"
    panel, browser = ({**REAL, name: planted}, BROWSER_REAL) if where == "panel" else (
        REAL, {**BROWSER_REAL, name: planted})
    faults = wiring_faults(panel, browser)
    assert faults, "a tree with its chain cut was accepted"
    assert any(word in fault for fault in faults), faults

def test_a_comment_that_names_the_wire_is_not_the_wire(tmp_path):
    """The scene read through `_code`: an import and a call that stand only in prose are not the
    import and the call, so a comment cannot stand in for the code."""
    scene = (PANEL / SCENE).read_text(encoding="utf-8")
    assert IMPORT in scene and FIRST in scene
    prose = scene.replace(IMPORT, "// " + IMPORT).replace(f"  {FIRST}\n", f"  // {FIRST}\n")
    path = tmp_path / SCENE
    path.write_text(prose, encoding="utf-8")
    faults = scene_faults(_code(path))
    assert any("imports of watchMotion" in fault for fault in faults), faults
    assert any("first statement" in fault for fault in faults), faults


def test_the_keys_of_a_view_are_read_by_name_and_not_by_a_word_that_appears_in_it():
    """`foreign` is named twice in the real view (`foreign: state.foreign`); the key is the one
    before the colon, so a view that lost the key and kept the value would not pass for whole."""
    literal = blank("const view = {a: 1, b, c: f(x, y), ...rest, d: [1, 2], e: `${g}`};")
    assert keys_of(literal, literal.index("{")) == ["a", "b", "c", "d", "e"]
    kept_value = blank("const view = {a: state.foreign};")
    assert "foreign" not in keys_of(kept_value, kept_value.index("{"))
