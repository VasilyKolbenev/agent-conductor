"""The hub's frame, as values: where a project's desk is mounted, what its address says, and which
messages from it the page believes (spec 4.5.5).

`hub-frame.js` has a pure half and a half that touches the page. The pure half is judged here under
Node: the address of a desk is the one the hub gave, held to the rule of 4.5.5 (loopback, a port up
to 65535 that is not the hub's, `/panel/desk.html`) and never taken from the page's own address; the
hash the frame is given is written by the shared grammar (`project`, `embed=hub`, the navigation,
`lang`, `theme`) and so can hold no value the desk would refuse; a mounted frame is the same frame
only while its project, its address and its instance are the ones the hub's row says; and a message
from a desk is taken only when it comes from the frame's own window, from the desk's own origin, as
a plain object with exactly the four keys and ids of the grammar, about the mounted project. Every
forged shape is a row of its own. What a browser does with the element (the sandbox, the
replacement of the location, the listener) is proved in `browser_tests/test_hub_page_frame.py`.
"""
from __future__ import annotations

from typing import Any

from tests.desk_wizard_node import run_js

MODULES = {"frame": "hub-frame.js"}
PROJECT = "a" * 32
PRELUDE = """
const show = (value) => console.log(JSON.stringify(value));
const row = (over = {}) => ({project_id: "a".repeat(32), state: "running", working: "active",
  desk_url: "http://127.0.0.1:7701/panel/desk.html", instance: "b".repeat(32), ...over});
"""


def js(body: str, **extra: Any) -> Any:
    return run_js(PRELUDE + body, {**extra}, modules=MODULES)


def test_the_address_of_a_running_desk_is_the_one_the_hub_gave_and_judged_by_the_rule_of_the_spec():
    out = js("""
      const at = (desk_url, over = {}, port = "7700") =>
        frame.frameAddress(row({desk_url, ...over}), port);
      const ok = "http://127.0.0.1:7701/panel/desk.html";
      show({ok: at(ok), hubPort: at("http://127.0.0.1:7700/panel/desk.html"),
        defaultPort: at("http://127.0.0.1:80/panel/desk.html"),
        defaultHubPort: at("http://127.0.0.1:80/panel/desk.html", {}, ""),
        big: at("http://127.0.0.1:65536/panel/desk.html"),
        zero: at("http://127.0.0.1:0/panel/desk.html"),
        lead: at("http://127.0.0.1:07701/panel/desk.html"),
        host: at("http://localhost:7701/panel/desk.html"),
        path: at("http://127.0.0.1:7701/panel/desk.html?x=1"),
        slash: at("http://127.0.0.1:7701/panel/desk.html/"),
        other: at("http://127.0.0.1:7701/panel/studio.html"), none: at(null),
        notRunning: at(ok, {state: "stopped"}), starting: at(ok, {state: "starting"}),
        scheme: at("https://127.0.0.1:7701/panel/desk.html"),
        maxPort: at("http://127.0.0.1:65535/panel/desk.html"),
        badId: at(ok, {project_id: "A".repeat(32)}), shortId: at(ok, {project_id: "a"}),
        noRow: frame.frameAddress(null, "7700")});
    """)
    assert out["ok"] == {"url": "http://127.0.0.1:7701/panel/desk.html",
                         "origin": "http://127.0.0.1:7701"}
    assert out["maxPort"]["origin"] == "http://127.0.0.1:65535"
    assert out["defaultPort"] == {"url": "http://127.0.0.1:80/panel/desk.html",
                                  "origin": "http://127.0.0.1"}
    refused = [name for name in out if name not in ("ok", "maxPort", "defaultPort")]
    assert all(out[name] is None for name in refused), [n for n in refused if out[n] is not None]


def test_the_hash_of_the_frame_is_written_by_the_shared_grammar_and_holds_no_refused_value():
    out = js("""
      const prefs = {locale: "ru", theme: "dark"};
      const hash = (nav, p = prefs, id = "a".repeat(32)) => frame.frameHash(id, nav, p);
      show({full: hash({task: "task-1", run: "run-1", gate: "gate-1", panel: "run", new: "task"}),
        bare: hash({}), light: hash({}, {locale: "en", theme: null}),
        dirty: hash({task: "../x", run: "a b", gate: "g", panel: "evil", new: "project"}),
        gateNoRun: hash({task: "task-1", gate: "gate-1"}),
        noProject: hash({task: "task-1"}, prefs, "x")});
    """)
    assert out["full"] == (f"#project={PROJECT}&embed=hub&task=task-1&run=run-1&gate=gate-1"
                           "&panel=run&new=task&lang=ru&theme=dark")
    assert out["bare"] == f"#project={PROJECT}&embed=hub&lang=ru&theme=dark"
    assert out["light"] == f"#project={PROJECT}&embed=hub&lang=en"
    assert out["dirty"] == f"#project={PROJECT}&embed=hub&lang=ru&theme=dark", (
        "a task, run, gate, panel or new that the grammar refuses is not written")
    assert out["gateNoRun"] == f"#project={PROJECT}&embed=hub&task=task-1&lang=ru&theme=dark", (
        "a gate hangs on its run and goes with it")
    assert out["noProject"].startswith("#embed=hub&task=task-1"), "no project, no project key"


def test_a_mounted_frame_is_the_same_frame_only_while_project_address_and_instance_hold():
    out = js("""
      const mounted = {project_id: "a".repeat(32), desk_url: row().desk_url,
        instance: "b".repeat(32), origin: "http://127.0.0.1:7701"};
      const same = (over) => frame.sameMount(mounted, row(over));
      show({same: same({}), instance: same({instance: "c".repeat(32)}),
        address: same({desk_url: "http://127.0.0.1:7702/panel/desk.html"}),
        project: same({project_id: "d".repeat(32)}), stopped: same({state: "stopped"}),
        stopping: same({state: "stopping"}), nothing: frame.sameMount(null, row()),
        noRow: frame.sameMount(mounted, null),
        noInstance: frame.sameMount({...mounted, instance: null}, row({instance: null}))});
    """)
    assert out["same"] is True and out["noInstance"] is True
    assert [out[name] for name in ("instance", "address", "project", "stopped", "stopping",
                                   "nothing", "noRow")] == [False] * 7


#: Every shape a message may have, made from the one good message by one change each.
FORGED = {
    "another source": {"source": "other"},
    "no source": {"source": None},
    "another origin": {"origin": "http://127.0.0.1:7702"},
    "a named host": {"origin": "http://localhost:7701"},
    "the hub's own origin": {"origin": "http://127.0.0.1:7700"},
    "an extra key": {"data": {"kind": "desk-location", "project_id": PROJECT, "task_id": None,
                              "run_id": None, "token": "x"}},
    "a missing key": {"data": {"kind": "desk-location", "project_id": PROJECT, "task_id": None}},
    "another kind": {"data": {"kind": "desk-write", "project_id": PROJECT, "task_id": None,
                              "run_id": None}},
    "another project": {"data": {"kind": "desk-location", "project_id": "b" * 32, "task_id": None,
                                 "run_id": None}},
    "no project": {"data": {"kind": "desk-location", "project_id": None, "task_id": None,
                            "run_id": None}},
    "a task that is a path": {"data": {"kind": "desk-location", "project_id": PROJECT,
                                       "task_id": "../etc", "run_id": None}},
    "a run that is a sentence": {"data": {"kind": "desk-location", "project_id": PROJECT,
                                          "task_id": "task-1", "run_id": "fix the thing"}},
    "a task that is a number": {"data": {"kind": "desk-location", "project_id": PROJECT,
                                         "task_id": 7, "run_id": None}},
    "a list": {"data": [PROJECT]},
    "a string": {"data": "desk-location"},
    "nothing": {"data": None},
}


def test_a_message_is_believed_only_from_the_frame_window_at_the_desks_origin_in_the_one_shape():
    out = js("""
      const window_ = {name: "the frame"};
      const mounted = {window: window_, origin: "http://127.0.0.1:7701",
        project_id: "a".repeat(32)};
      const good = {source: window_, origin: "http://127.0.0.1:7701", data: {kind: "desk-location",
        project_id: "a".repeat(32), task_id: "task-1", run_id: "run-1"}};
      const made = (change) => ({...good, ...(change.source === "other" ? {source: {}} : change)});
      class Shaped { constructor() { Object.assign(this, good.data); } }
      const results = Object.fromEntries(Object.entries(d.forged).map(
        ([name, change]) => [name, frame.locationOf(made(change), mounted)]));
      show({good: frame.locationOf(good, mounted),
        nulls: frame.locationOf({...good, data: {...good.data, task_id: null, run_id: null}},
          mounted),
        results, unmounted: frame.locationOf(good, null),
        shaped: frame.locationOf({...good, data: new Shaped()}, mounted),
        inherited: frame.locationOf({...good, data: Object.create(good.data)}, mounted),
        frozen: Object.isFrozen(frame.locationOf(good, mounted))});
    """, forged=FORGED)
    assert out["good"] == {"task_id": "task-1", "run_id": "run-1"}
    assert out["nulls"] == {"task_id": None, "run_id": None}
    assert {name: found for name, found in out["results"].items() if found is not None} == {}, (
        "a forged message was taken")
    assert len(out["results"]) == len(FORGED) == 16
    assert out["unmounted"] is None and out["shaped"] is None and out["inherited"] is None
    assert out["frozen"] is True, "what the page is told cannot be changed under it"


def test_the_sandbox_is_the_one_the_spec_gives_and_grants_no_navigation_of_the_top_page():
    out = js("""show({sandbox: frame.SANDBOX, names: Object.keys(frame).sort()});""")
    assert out["sandbox"] == ("allow-scripts allow-same-origin allow-forms allow-popups "
                              "allow-popups-to-escape-sandbox")
    assert "allow-top-navigation" not in out["sandbox"]
    assert out["names"] == ["SANDBOX", "createFrameHost", "frameAddress", "frameHash",
                            "locationOf", "sameMount"], "the module's whole surface"
