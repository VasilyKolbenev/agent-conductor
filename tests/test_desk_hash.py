"""The hash grammar of the desk (spec 4.5.2), read from the real module under Node.

`desk-hash.js` is values in, values out, and the hub's page loads it too, so it is tested the
way the desk's other pure modules are: the packaged file is imported and handed strings. The
table of keys is spelled out here from the spec and not read back from the module, so a check
that quietly stopped biting reds in this file. What the desk DOES with a hash is
`browser_tests/test_desk_hash.py`'s; what the module may reach is `test_desk_address_source.py`'s.
"""
from __future__ import annotations

from conductor.command import command_routes
from tests.desk_node import run_js

MODULES = {"address": "desk-hash.js", "prefs": "studio-preferences.js",
           "tasks": "studio-tasks-model.js"}
PROJECT = "0123456789abcdef0123456789abcdef"
KEYS = ("project", "embed", "task", "run", "gate", "workflow", "panel", "new", "prepare",
        "starter")
#: Every key absent: what `readDeskHash` answers for an empty address.
BLANK = {**{key: None for key in KEYS}, "projectRepeated": False}
#: One valid value per key, and what each key hangs on (the three dependencies of 4.5.2).
VALID = {"project": PROJECT, "embed": "hub", "task": "task-fix", "run": "run-1.a_b",
         "gate": "gate-1", "workflow": "wf.1", "panel": "people", "new": "task",
         "prepare": "1", "starter": "desk-starter-docs"}
NEEDS = {"gate": "run=r1", "prepare": "task=t1", "starter": "new=task"}
#: Values the grammar refuses, per key.
INVALID = {
    "project": [PROJECT.upper(), PROJECT[:-1], PROJECT + "0", PROJECT[:-1] + "g", ""],
    "embed": ["", "HUB", "hub2", "parent"],
    "task": ["", ".x", "-x", "a b", "a" * 65],
    "run": ["", "-x", "_x", "a/b", "a" * 129],
    "gate": ["", ".g", "a" * 129],
    "workflow": ["", "-w", "a" * 129],
    "panel": ["", "screen", "Run", "cycles"],
    "new": ["", "1", "Task"],
    "prepare": ["", "0", "true", "11"],
    "starter": ["", ".s", "a" * 129],
}


def _read(*hashes: str) -> list[dict]:
    return run_js("console.log(JSON.stringify(d.map((hash) => address.readDeskHash(hash))));",
                  MODULES, list(hashes))


def _alone(key: str, value: str) -> str:
    """A hash carrying `key` and only what it hangs on."""
    return "&".join(part for part in (NEEDS.get(key), f"{key}={value}") if part)


def test_every_key_of_the_grammar_reads_its_valid_value_and_refuses_the_invalid_ones():
    keys = list(VALID)
    read = _read(*(_alone(key, VALID[key]) for key in keys))
    for key, answer in zip(keys, read):
        assert answer[key] == VALID[key], key
    refused = [(key, bad) for key in keys for bad in INVALID[key]]
    read = _read(*(_alone(key, bad) for key, bad in refused))
    assert [answer[key] for (key, _bad), answer in zip(refused, read)] == [None] * len(refused)


def test_a_hash_reads_with_or_without_its_leading_sharp_and_an_empty_one_reads_blank():
    with_sharp, bare, empty, lone = _read("#task=t1", "task=t1", "", "#")
    assert with_sharp == bare == {**BLANK, "task": "t1"}
    assert empty == lone == BLANK


def test_a_repeated_key_reads_as_absent_and_a_repeated_project_says_so():
    twice, alike, other = _read("task=a&task=b", f"project={PROJECT}&project={PROJECT}",
                                f"project={PROJECT}&project={PROJECT[::-1]}&lang=ru")
    assert twice == BLANK
    assert alike == {**BLANK, "projectRepeated": True}
    assert other == {**BLANK, "projectRepeated": True}
    single, = _read(f"project={PROJECT}")
    assert single == {**BLANK, "project": PROJECT}


def test_unknown_keys_and_the_old_screen_key_are_ignored():
    plain = _read("task=t1&run=r1")[0]
    noisy = _read("screen=runs&task=t1&x=1&run=r1&lang=ru&theme=dark&token=abc")[0]
    assert plain == noisy == {**BLANK, "task": "t1", "run": "r1"}


def test_the_three_dependent_keys_are_ignored_without_the_key_they_hang_on():
    alone = _read("gate=g1", "prepare=1", "starter=desk-starter-docs", "gate=g1&task=t1",
                  "starter=desk-starter-docs&new=task&prepare=1")
    assert alone[0]["gate"] is None
    assert alone[1]["prepare"] is None and alone[2]["starter"] is None
    assert alone[3] == {**BLANK, "task": "t1"}
    assert alone[4] == {**BLANK, "new": "task", "starter": "desk-starter-docs"}
    both, = _read("run=r1&gate=g1&task=t1&prepare=1")
    assert (both["gate"], both["prepare"]) == ("g1", "1")


def test_deskhash_writes_the_keys_in_the_spec_order_and_never_writes_what_it_would_not_read():
    def write(*states: dict) -> list[str]:
        return run_js("console.log(JSON.stringify(d.map((state) => address.deskHash(state))));",
                      MODULES, list(states))

    everything, dirty, numbers, nothing, gate_alone, repeated_project = write(
        dict(VALID),
        {"task": "bad id", "run": "r1", "gate": "g1", "prepare": "1", "screen": "runs"},
        {"task": 5, "run": None, "gate": ["g"], "embed": True},
        {},
        {"gate": "g1"},
        {"project": PROJECT, "projectRepeated": True})
    assert everything == ("#project=" + PROJECT + "&embed=hub&task=task-fix&run=run-1.a_b"
                          "&gate=gate-1&workflow=wf.1&panel=people&new=task&prepare=1"
                          "&starter=desk-starter-docs")
    assert dirty == "#run=r1&gate=g1"
    assert numbers == "#" and nothing == "#" and gate_alone == "#"
    assert repeated_project == f"#project={PROJECT}"


def test_the_hash_a_desk_writes_is_read_back_as_the_state_it_wrote():
    states = [dict(VALID), {"task": "t1", "run": "r1"}, {"project": PROJECT, "embed": "hub"},
              {"panel": "continue", "new": "task"}, {}]
    hashes = run_js("console.log(JSON.stringify(d.map((state) => address.deskHash(state))));",
                    MODULES, states)
    for state, answer in zip(states, _read(*hashes)):
        assert answer == {**BLANK, **state}


def test_the_id_grammars_accept_exactly_what_their_sources_accept():
    """Task ids are `isTaskId`'s and the routes', run, gate, workflow and starter ids the run
    route's and the workflow route's: one corpus, judged four ways."""
    corpus = ["a", "A0", "0", "task-fix", "a.b_c-d", ".a", "-a", "_a", "a b", "a/b", "",
              "a" * 63, "a" * 64, "a" * 65, "a" * 127, "a" * 128, "a" * 129, "é1", "a%20b",
              "a\n", "a\u0000", "1"]
    judged = run_js("""
      console.log(JSON.stringify(d.map((id) => ({
        task: address.readDeskHash("task=" + encodeURIComponent(id)).task !== null,
        source: tasks.isTaskId(id),
        run: address.readDeskHash("run=" + encodeURIComponent(id)).run !== null,
        gate: address.readDeskHash("run=r1&gate=" + encodeURIComponent(id)).gate !== null,
        workflow: address.readDeskHash("workflow=" + encodeURIComponent(id)).workflow !== null,
        starter: address.readDeskHash("new=task&starter=" + encodeURIComponent(id))
          .starter !== null,
      }))));
    """, MODULES, corpus)
    for id_, row in zip(corpus, judged):
        assert row["task"] == row["source"], repr(id_)
        assert row["task"] == bool(command_routes._TASK_ROUTE.fullmatch(f"/command/tasks/{id_}")), \
            repr(id_)
        in_runs = bool(command_routes._RUN_ROUTE.fullmatch(f"/command/runs/{id_}"))
        assert (row["run"], row["gate"], row["starter"]) == (in_runs,) * 3, repr(id_)
        in_workflows = bool(command_routes._WORKFLOW_ROUTE.fullmatch(f"/command/workflows/{id_}"))
        assert row["workflow"] == in_workflows, repr(id_)
    assert any(row["task"] for row in judged) and not all(row["task"] for row in judged)


def _changes(*pairs: tuple[str, str]) -> list[dict]:
    return run_js("""
      console.log(JSON.stringify(d.map(([last, next]) => address.navigationChange(
        address.readDeskHash(last), address.readDeskHash(next)))));
    """, MODULES, [list(pair) for pair in pairs])


def _step(key: str, value: str) -> dict:
    return {"key": key, "value": value}


ALL_RESETS = ["run", "gate", "panel", "workflow", "prepare"]


def test_a_hash_with_no_navigation_key_moves_nothing_and_a_key_equal_to_the_last_is_no_step():
    rows = _changes(("", ""), ("task=a&run=r", "lang=ru&theme=dark"),
                    ("task=a&run=r", f"project={PROJECT}&embed=hub"),
                    ("task=a&run=r", "task=a&run=r"), ("task=a&run=r", "run=r"),
                    ("task=a&run=r", "task=a"))
    assert rows == [{"steps": [], "reset": []}] * 6


def test_navigation_change_names_the_present_keys_that_differ_and_orders_them_top_to_bottom():
    rows = _changes(("", "task=T&run=R&gate=G&workflow=W&panel=run&new=task&prepare=1"
                         "&starter=desk-starter-docs"),
                    ("task=A&run=R1", "task=A&run=R2"),
                    ("task=A&run=R1", "gate=g&run=R2"))
    assert [step["key"] for step in rows[0]["steps"]] == [
        "task", "run", "gate", "workflow", "panel", "new", "starter", "prepare"]
    assert rows[1] == {"steps": [_step("run", "R2")], "reset": []}
    assert [step["key"] for step in rows[2]["steps"]] == ["run", "gate"]


def test_a_changed_task_resets_the_keys_the_same_hash_does_not_carry():
    rows = _changes(("", "task=A"), ("", "task=A&run=R"), ("task=A&run=R1", "task=B"),
                    ("task=A", "task=A&run=R"))
    assert rows[0] == {"steps": [_step("task", "A")], "reset": ALL_RESETS}
    assert rows[1] == {"steps": [_step("task", "A"), _step("run", "R")],
                       "reset": ["gate", "panel", "workflow", "prepare"]}
    assert rows[2] == {"steps": [_step("task", "B")], "reset": ALL_RESETS}
    assert rows[3] == {"steps": [_step("run", "R")], "reset": []}


def test_a_foreign_project_is_a_repeat_or_a_claim_that_differs_from_the_bound_one():
    cases = [(PROJECT, f"project={PROJECT}", False), (PROJECT, "", False),
             (PROJECT, f"project={PROJECT[::-1]}", True), (None, f"project={PROJECT}", True),
             (None, "", False), (PROJECT, f"project={PROJECT}&project={PROJECT}", True),
             (PROJECT, "project=notanid", False), (None, "project=a&project=b", True)]
    judged = run_js("""
      console.log(JSON.stringify(d.map(([bound, hash]) => address.foreignProject(
        bound, address.readDeskHash(hash)))));
    """, MODULES, [[bound, hash_] for bound, hash_, _ in cases])
    assert judged == [expected for _b, _h, expected in cases]


def test_the_preference_functions_answer_as_they_did_before_the_move():
    reads = [("#lang=ru&theme=dark", "en"), ("", "ru-RU"), ("", "en-US"), ("", ""),
             ("#lang=ru&lang=en", "en"), ("#theme=dark&theme=light", "en"),
             ("#lang=de&theme=blue", "ru")]
    got = run_js("console.log(JSON.stringify(d.map(([h, l]) => address.readPreferences(h, l))));",
                 MODULES, [list(row) for row in reads])
    assert got == [{"locale": "ru", "theme": "dark"}, {"locale": "ru", "theme": None},
                   {"locale": "en", "theme": None}, {"locale": "en", "theme": None},
                   {"locale": "en", "theme": None}, {"locale": "en", "theme": None},
                   {"locale": "ru", "theme": None}]
    writes = run_js("""
      console.log(JSON.stringify(d.map(([h, v]) => address.preferenceHash(h, v))));
    """, MODULES, [["#task=a&lang=en", {"locale": "ru", "theme": "dark"}],
                   ["#theme=dark", {"locale": "en", "theme": None}], ["", {"locale": "ru",
                                                                            "theme": "light"}]])
    assert writes == ["#task=a&lang=ru&theme=dark", "#lang=en", "#lang=ru&theme=light"]


def test_the_studio_re_exports_the_very_functions_the_desk_hash_module_holds():
    same = run_js("""
      console.log(JSON.stringify([prefs.readPreferences === address.readPreferences,
        prefs.preferenceHash === address.preferenceHash]));
    """, MODULES)
    assert same == [True, True]
