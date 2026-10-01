"""No function of the five tabs is lost silently (spec 5.6, 5.6.8 guards 1 and 2, node half).

`tests/desk_function_map.py` types the six tables of spec 5.6 (70 functions) and says, for each,
one of four things (on the desk, a module with no mount, not built, retired) with proofs in the
source. This module holds the map to the source in both directions, like the guards of the desk's
registries do: a row that says "not built" stops being true the day it is built, and a row that
says "on the desk" stops being true the day its code goes, and either reds until the row is moved.
It also holds the spec's own guard 1: every handler the Studio's boot module had (with the
handlers its two spread sources name) is kept under its name, retired to a new name, or owed with an
owner, and the desk has no path of the Studio's draft and revisions doors, no `automationDraft` and
no path of the hub's. What still stands of those is an exact, owned list, never a silence: when
somebody removes one, the list reds until the entry goes.

The browser half is `browser_tests/test_desk_map.py`: a booted desk draws what the map says it draws
and nothing the map says is not built.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pytest

from tests.desk_function_map import OWNERS, PROOF_KINDS, ROWS, STATES, Row
from tests.test_panel_cascade import strip_comments

PANEL = Path(__file__).resolve().parents[1] / "src" / "conductor" / "panel"
IMPORTS = re.compile(r'from "\./([a-z0-9-]+\.js)"')
#: How many functions each table of the spec lists.
SPEC_COUNTS = {"5.6.1": 14, "5.6.2": 5, "5.6.3": 18, "5.6.4": 24, "5.6.5": 4, "5.6.6": 5}


def read_file(name: str) -> str | None:
    """A panel file as code (comments stripped for scripts), or None when it does not exist."""
    path = PANEL / name
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    return strip_comments(text) if name.endswith(".js") else text


def desk_closure(reader=read_file, start: str = "desk.js") -> frozenset[str]:
    """Every module the boot module of the desk reaches by its imports."""
    seen: set[str] = set()
    pending = [start]
    while pending:
        name = pending.pop()
        text = reader(name)
        if name in seen or text is None:
            continue
        seen.add(name)
        pending += IMPORTS.findall(text)
    return frozenset(seen)


def _proof_fault(proof: tuple[str, str, str], closure: frozenset[str], reader) -> str | None:
    kind, file, token = proof
    text = reader(file)
    mounted = file in closure or file == "desk.html"
    if kind not in PROOF_KINDS:
        return f"{file}: an unknown kind of proof {kind!r}"
    if kind == "in":
        if not mounted:
            return f"{file} is said to be on the desk and the desk does not reach it"
        return None if text is not None and token in text else f"{file} no longer has {token!r}"
    if kind == "module":
        if text is None:
            return f"{file} is said to exist and does not"
        return f"{file} is mounted by the desk now" if mounted else None
    if kind == "token":
        if text is None or token not in text:
            return f"{file} no longer has {token!r}"
        return f"{file} is mounted by the desk now" if mounted else None
    if kind == "absent":
        return f"{file} has {token!r} now: what was not built is" if (
            text is not None and token in text) else None
    if kind == "present":
        return None if text is not None and token in text else (
            f"{file} no longer has the placeholder {token!r}: what was not built is")
    return None if text is not None and token in text else f"{file} no longer keeps {token!r}"


def row_faults(row: Row, closure: frozenset[str], reader=read_file) -> list[str]:
    """Every way `row` says what the source does not bear out."""
    faults = [f"{row.name}: {fault}" for proof in row.proofs
              if (fault := _proof_fault(proof, closure, reader)) is not None]
    kinds = {kind for kind, _file, _token in row.proofs}
    if row.state not in STATES:
        return faults + [f"{row.name}: state {row.state!r} is not one of the four"]
    if row.state != "on_desk" and row.owner not in OWNERS:
        faults.append(f"{row.name}: a function that is not on the desk names no owner")
    if any(owner not in OWNERS for owner, _what in row.owed):
        faults.append(f"{row.name}: a part owed names no owner")
    needs = {"on_desk": {"in"}, "module_only": {"module"}, "not_built": {"absent", "present"},
             "retired": {"kept"}}[row.state]
    if not kinds & needs:
        faults.append(f"{row.name}: {row.state} with no proof of that kind ({sorted(needs)})")
    if row.state == "on_desk" and kinds - {"in"}:
        faults.append(f"{row.name}: an on-desk row proved by more than what the desk reaches")
    return faults


def test_the_map_has_each_function_of_spec_5_6_once_and_no_other():
    by_section = Counter(row.section for row in ROWS)
    assert dict(by_section) == SPEC_COUNTS and len(ROWS) == 70
    names = [row.name for row in ROWS]
    assert len(set(names)) == len(names), [n for n, c in Counter(names).items() if c > 1]
    assert all(row.state in STATES for row in ROWS)


def test_every_row_of_the_map_is_true_of_the_source_today():
    closure = desk_closure()
    assert {"desk.js", "desk-rail.js", "desk-scene.js", "desk-pult.js"} <= closure
    assert {"desk-wizard.js", "desk-flow-host.js", "desk-flow.js", "desk-stream.js"} <= closure
    faults = [fault for row in ROWS for fault in row_faults(row, closure)]
    assert faults == [], "\n".join(faults)


def test_the_map_counts_what_is_on_the_desk_and_what_is_not_yet_and_who_owes_it():
    states = Counter(row.state for row in ROWS)
    owners = Counter(row.owner for row in ROWS if row.state != "on_desk")
    assert sum(states.values()) == 70 and states["on_desk"] >= 30
    assert states["module_only"] == 0, "the wizard and cycle editor are mounted"
    assert set(owners) <= {"D1", "D2"}, owners
    assert {row.owner for row in ROWS if row.state == "retired"} == {"D2"}, (
        "the deletion of the five tabs is the slice of lane D2")


def _row(state: str, proofs, owner="D1", owed=()) -> Row:
    return Row("5.6.1", "a function", "somewhere", state, tuple(proofs), owner, tuple(owed))


DESK = frozenset({"desk.js", "desk-rail.js"})
TEXTS = {"desk.js": "const a = b;", "desk-rail.js": "taskStatus", "desk-wizard.js": "mountWizard",
         "desk.html": "data-state"}
LIES = {
    "on desk, but the desk does not reach the file": (
        _row("on_desk", [("in", "desk-wizard.js", "mountWizard")], None), "does not reach it"),
    "on desk, but its token went": (
        _row("on_desk", [("in", "desk-rail.js", "gone")], None), "no longer has 'gone'"),
    "on desk with a proof of another kind": (
        _row("on_desk", [("in", "desk-rail.js", "taskStatus"),
                         ("absent", "desk.js", "zzz")], None), "more than what the desk reaches"),
    "a module with no mount that the desk mounts now": (
        _row("module_only", [("module", "desk-rail.js", "")]), "is mounted by the desk now"),
    "a module with no mount that is gone": (
        _row("module_only", [("module", "desk-nothing.js", "")]), "exist and does not"),
    "not built, but its token is there now": (
        _row("not_built", [("absent", "desk-rail.js", "taskStatus")]), "what was not built is"),
    "not built by a placeholder that went": (
        _row("not_built", [("present", "desk.js", "NO_STREAM")]), "no longer has the placeholder"),
    "retired, but the old code went": (
        _row("retired", [("kept", "desk.js", "latestRunCard")], "D2"), "no longer keeps"),
    "a state that is none of the four": (
        _row("half_built", [("absent", "desk.js", "zzz")]), "is not one of the four"),
    "not on the desk and no owner": (
        _row("not_built", [("absent", "desk.js", "zzz")], None), "names no owner"),
    "a part owed to nobody": (
        _row("not_built", [("absent", "desk.js", "zzz")], "D1", [("ZZ", "x")]),
        "a part owed names no owner"),
    "not built with nothing to show it": (
        _row("not_built", [("in", "desk-rail.js", "taskStatus")]), "no proof of that kind"),
    "a kind of proof nobody knows": (
        _row("not_built", [("wished", "desk.js", "zzz")]), "an unknown kind of proof"),
}


def _fake(name: str) -> str | None:
    return TEXTS.get(name)


@pytest.mark.parametrize("row,needle", list(LIES.values()), ids=list(LIES))
def test_the_map_check_refuses_each_planted_lie_and_names_it(row, needle):
    faults = row_faults(row, DESK, _fake)
    assert any(needle in fault for fault in faults), faults


def test_the_map_check_passes_a_row_that_is_true():
    truths = [_row("on_desk", [("in", "desk-rail.js", "taskStatus")], None),
              _row("module_only", [("module", "desk-wizard.js", "")]),
              _row("not_built", [("absent", "desk.js", "zzz")]),
              _row("retired", [("kept", "desk.js", "const a")], "D2")]
    assert [row_faults(row, DESK, _fake) for row in truths] == [[]] * 4


def test_the_closure_of_the_desk_follows_imports_and_ignores_a_file_that_is_not_there():
    texts = {"desk.js": 'import {a} from "./desk-rail.js"; import {b} from "./desk-gone.js";',
             "desk-rail.js": 'import {c} from "./desk.js";'}
    assert desk_closure(texts.get) == frozenset({"desk.js", "desk-rail.js"})


# -- the handlers of the old boot module ---------------------------------------------------------


def entries(literal: str) -> list[str]:
    """The keys of an object literal's top-level entries: `key: v`, `key` and `...spread`."""
    depth, current, found = 0, "", []
    for char in literal + ",":
        depth += char in "([{"
        depth -= char in ")]}"
        if char == "," and depth == 0:
            found.append(current.strip())
            current = ""
        else:
            current += char
    return [re.match(r"(\.\.\.)?(\w+)", piece).group(0) for piece in found if piece]


def handlers_of(source: str) -> list[str]:
    """The names of `const handlers = Object.freeze({...})`, spreads left as `...name`."""
    start = source.index("const handlers = Object.freeze({") + len("const handlers = Object.freeze({")
    depth, end = 1, start
    while depth:
        depth += source[end] == "{"
        depth -= source[end] == "}"
        end += 1
    return entries(source[start:end - 1])


def listed_names(source: str, anchor: str) -> list[str]:
    """The quoted names of the list that `Object.fromEntries(` takes in the function `anchor`."""
    body = source[source.index(anchor):]
    found = re.search(r"Object\.fromEntries\(\s*\[(.*?)\]\s*\.map", body, re.DOTALL)
    return re.findall(r'"(\w+)"', found.group(1))


def old_handlers() -> list[str]:
    """Every handler the Studio's boot module had, its spread sources expanded, and the actions of
    automation (spec 5.6.8, guard 1)."""
    studio = (PANEL / "studio.js").read_text(encoding="utf-8")
    names = [name for name in handlers_of(strip_comments(studio)) if not name.startswith("...")]
    spread = listed_names((PANEL / "studio-workflowwrite.js").read_text(encoding="utf-8"),
                          "export function workflowWriters")
    actions = listed_names((PANEL / "studio-automation-flow.js").read_text(encoding="utf-8"),
                           "export function automationFlow")
    return [*names, *spread, *actions]


def desk_handlers() -> list[str]:
    return handlers_of(strip_comments((PANEL / "desk.js").read_text(encoding="utf-8")))


#: What became of each handler of the old boot module: `kept` (the desk has it under its name),
#: `host` (mounted through a panel host),
#: `retired` (the spec's dictionary gives it a new name and the desk has that handler),
#: `pending` (the spec's new name, which the desk does not have yet, and who adds it) or `owed` (no new
#: name yet: who owes it, and where it will live).
HANDLERS = {
    "chooseTask": ("kept",),
    "onScreen": ("pending", "onPanel", "D1"), "showDecisions": ("pending", "onPanel", "D1"),
    "onSaveDraft": ("pending", "onFlowSave", "D1"), "onPublish": ("pending", "onFlowPublish", "D1"),
    "onPublishConfirm": ("pending", "onFlowPublishConfirm", "D1"),
    "onPublishCancel": ("pending", "onFlowPublishCancel", "D1"),
    "onStartWorkflow": ("pending", "onFlowStart", "D1"), "editStarter": ("pending", "editFlowStart", "D1"),
    "onEditPublished": ("pending", "onFlowCopy", "D1"), "onValidate": ("pending", "onFlowCheck", "D1"),
    "onEdit": ("pending", "onFlowEdit", "D1"),
    "onChooseWorkflow": ("owed", "D1", "the picker of «Схема»"),
    "onOpenRun": ("owed", "D1", "«Запуск подробно»"),
    "createTask": ("owed", "D1", "the wizard's «Задача» step"),
    "refreshTasks": ("owed", "D1", "the «↻» of the rail"),
    "refreshQuotas": ("owed", "D1", "limits in the pult"),
    "editTask": ("owed", "D1", "the wizard's «Задача» step"),
    "onFold": ("owed", "D1", "the folds of «Схема» and of the run panel"),
    "editOpening": ("owed", "D1", "the wizard's roles step"),
    "onRefreshRuns": ("owed", "D1", "the list of runs"), "onRefreshRun": ("owed", "D1", "the run panel"),
    "onRefreshAgents": ("owed", "D1", "«Участники»"),
    "onSelectTaskRun": ("owed", "D1", "«Ждут вас»"), "onSelectRun": ("owed", "D1", "the list of runs"),
    "onSelect": ("owed", "D1", "the canvas of «Схема»"), "onView": ("owed", "D1", "the canvas of «Схема»"),
    "onStatus": ("owed", "D1", "the status line"), "selectRun": ("owed", "D1", "the list of runs"),
    "refreshRuns": ("owed", "D1", "the list of runs"),
    "chooseStep": ("host", "desk-run-write-host.js", "stepWriters"),
    "editStep": ("host", "desk-run-write-host.js", "stepWriters"),
    "proposeStep": ("host", "desk-run-write-host.js", "stepWriters"),
    "confirmStep": ("host", "desk-run-write-host.js", "stepWriters"),
    "editDocument": ("host", "desk-run-write-host.js", "documentWriters"),
    "publishDocument": ("host", "desk-run-write-host.js", "documentWriters"),
    "selectDecision": ("host", "desk-run-write-host.js", "selectDecision"),
    "editDecision": ("host", "desk-run-write-host.js", "editDecision"),
    "submitDecision": ("host", "desk-run-write-host.js", "decisionWriters"),
    "refreshAgents": ("owed", "D1", "«Участники»"),
    "sync": ("owed", "D1", "the pult: the slot and the grants"),
    "clear": ("owed", "D1", "the pult: the slot and the grants"),
    "disconnect": ("owed", "D1", "the pult: the stream's end"),
    "refresh": ("owed", "D1", "the pult: the grants"),
    "edit": ("owed", "D2", "the terms card of the wizard"),
    "preview": ("owed", "D2", "the terms card of the wizard"),
    "authorize": ("owed", "D2", "the terms card of the wizard"),
    "control": ("owed", "D1", "the pult: «Освободить слот»"),
    "retry": ("owed", "D1", "the pult: the grants"),
}


def handler_faults(old: list[str], desk: list[str], table=HANDLERS) -> list[str]:
    """Every handler the old boot module had that the table does not account for, and every
    account the desk's handlers do not bear out."""
    faults = [f"{name}: a handler of the old boot module the table does not account for"
              for name in sorted(set(old) - set(table))]
    faults += [f"{name}: in the table and not a handler of the old boot module"
               for name in sorted(set(table) - set(old))]
    for name, fate in table.items():
        if fate[0] == "kept" and name not in desk:
            faults.append(f"{name}: said to be kept and the desk has no such handler")
        elif fate[0] == "pending" and (fate[1] in desk or fate[2] not in OWNERS):
            faults.append(f"{name}: its new name {fate[1]} is a handler now (or no owner): the row "
                          "is `kept`")
        elif fate[0] == "owed" and (name in desk or fate[1] not in OWNERS):
            faults.append(f"{name}: owed, but the desk has it now (or no owner)")
        elif fate[0] == "host" and (name in desk or fate[1] not in desk_closure()
                                   or fate[2] not in (read_file(fate[1]) or "")):
            faults.append(f"{name}: its mounted host no longer supplies {fate[2]}")
    return faults


def test_the_handlers_the_old_boot_module_had_are_each_kept_retired_or_owed_with_an_owner():
    old, desk = old_handlers(), desk_handlers()
    assert len(old) == len(set(old)) == 49, (
        "the boot module's 33 handlers, the 7 of its workflow writers and the 9 actions of automation")
    assert "chooseTask" in desk and "onFlowEdit" not in desk
    assert handler_faults(old, desk) == []


def test_the_dictionary_of_retired_handlers_is_the_specs_and_is_closed():
    retired = {name: fate[1] for name, fate in HANDLERS.items() if fate[0] == "pending"}
    assert retired == {
        "onScreen": "onPanel", "showDecisions": "onPanel", "onSaveDraft": "onFlowSave",
        "onPublish": "onFlowPublish", "onPublishConfirm": "onFlowPublishConfirm",
        "onPublishCancel": "onFlowPublishCancel", "onStartWorkflow": "onFlowStart",
        "editStarter": "editFlowStart", "onEditPublished": "onFlowCopy", "onValidate": "onFlowCheck",
        "onEdit": "onFlowEdit"}


def test_the_handler_check_refuses_a_lost_handler_a_stale_row_and_a_row_about_nothing():
    old = ["a", "b", "c", "d"]
    table = {"a": ("kept",), "b": ("pending", "onB", "D1"), "c": ("owed", "D1", "x"),
             "d": ("owed", "D2", "y")}
    assert handler_faults(old, ["a"], table) == []
    assert any("a: said to be kept" in f for f in handler_faults(old, [], table))
    assert any("b: its new name onB is a handler now" in f
               for f in handler_faults(old, ["a", "onB"], table))
    assert any("c: owed, but the desk has it now" in f
               for f in handler_faults(old, ["a", "c"], table))
    assert any("e: a handler of the old boot module the table does not account for" in f
               for f in handler_faults([*old, "e"], ["a"], table))
    assert any("z: in the table and not a handler" in f
               for f in handler_faults(old, ["a"], {**table, "z": ("kept",)}))


def test_the_parsers_read_the_object_literal_with_spreads_and_nested_bodies():
    source = "const handlers = Object.freeze({a, b: (x) => { f({y, z}); }, ...rest, c: d.e,});"
    assert handlers_of(source) == ["a", "b", "...rest", "c"]
    names = 'export function f(d) {\n  return Object.fromEntries(["x", "y"]\n    .map((n) => n));\n}'
    assert listed_names(names, "export function f") == ["x", "y"]


# -- the spec's end-state guards, with what still stands named -----------------------------------


def _code_of(pattern: str, names) -> dict[str, int]:
    found = {}
    for name in names:
        count = len(re.findall(pattern, strip_comments((PANEL / name).read_text(encoding="utf-8"))))
        if count:
            found[name] = count
    return found


def _desk_files() -> list[str]:
    return sorted(path.name for path in PANEL.glob("desk*") if path.suffix in (".js", ".html"))


def test_no_desk_file_names_the_draft_or_revisions_path_but_the_transport_that_still_holds_the_studios():
    """Spec 5.6.8: the desk writes `flow` and not `/draft` or `/revisions` (L19). The transport keeps
    those two targets of the Studio until the Studio is removed (owner D1, at that slice)."""
    assert _code_of(r"/(?:draft|revisions)\b", _desk_files()) == {"desk-transport.js": 3}


def test_the_name_automation_draft_stands_only_in_the_two_files_the_studio_removal_takes():
    """Spec 5.6.8: no `automationDraft` in the package (L18: the server's `terms_draft` replaces it).
    It stands in the two Studio files of the card of terms until their slice (owner D2)."""
    names = sorted(path.name for path in PANEL.iterdir() if path.suffix in (".js", ".html", ".css"))
    assert sorted(_code_of(r"automationDraft", names)) == [
        "studio-automation-flow.js", "studio-automation-model.js"]


def test_no_desk_file_asks_the_hub_for_anything_because_the_desk_and_the_hub_share_no_origin():
    assert _code_of(r"/hub/", _desk_files()) == {}
