"""The desk's guards over the flow door and the edit vocabulary (spec 7.11 item 7).

Four claims, each held from the side that would break it. The desk writes a cycle through one door
(`…/flow`) and never through `/draft` or `/revisions`, and never reuses the client's own counter;
the words of an edit are one vocabulary in three places and the flow schema's own in a fourth; the
road words are the core's conditions plus `always`; every code the server can put in a row has its
text in both languages. The scanners are functions of source text, and a calibration table feeds
each of them the ways it claims to refuse, so a guard that silently stopped biting reds here and
not in a review.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from conductor.command import flow_rules, graph_conditions, graph_values, plan_budget
from conductor.command import workflow_draft, workflow_flow
from tests.desk_wizard_node import PANEL, run_js
from tests.test_graph_source import _code
from tests.test_studio_wiring import _frozen_list

MODULES = {"shape": "desk-flow-shape.js", "fields": "desk-flow-fields.js",
           "i18n": "studio-i18n.js", "edits": "desk-flow-edits.js"}
DESK = sorted(path.name for path in PANEL.glob("desk*.js"))
TRANSPORT = "desk-transport.js"
#: The desk transport's rows for `/draft` and `/revisions`, inherited from the Studio it was moved
#: out of. They are debt: the desk writes cycles only by `flow`, and the lane that owns the
#: transport swaps the target set. Until it does, these rows are the ONE exception to the first
#: guard, and the guard holds the exception to be real: the day they are gone this test demands
#: that the exception go too.
INHERITED = frozenset({"draft", "revisions"})


def js(body: str) -> Any:
    return run_js("const show = (value) => console.log(JSON.stringify(value));\n" + body,
                  None, modules=MODULES)


# -- 1. the one door ------------------------------------------------------------------------

#: Every way a module can aim a write at the draft or the revisions door, or borrow the client's
#: own counter: a target named for the mutation door, the transport's path builders, the URL
#: itself, and the Studio module that holds `automationDraft`.
REACHES = {
    "a write target": r'target:\s*"(?:draft|revisions)"',
    "the path builders": r"\bpath\.(?:draft|revisions)\b",
    "a submit": r'submit\(\s*"(?:draft|revisions)"',
    "the url": r"/command/workflows/[^\"'`\n]*/(?:draft|revisions)\b",
    "the client's counter": r"\bautomationDraft\b",
    "its module": r'from "\./studio-automation[a-z-]*\.js"',
}


def reaches(source: str) -> list[str]:
    """Which of the ways to the draft door, the revisions door or the old counter a source uses."""
    return [name for name, pattern in REACHES.items() if re.search(pattern, source)]


@pytest.mark.parametrize("planted, expected", [
    ('ask({target: "draft", body})', "a write target"),
    ('ask({target: "revisions"})', "a write target"),
    ("const at = path.draft(id);", "the path builders"),
    ('await submit("revisions", id, body);', "a submit"),
    ("fetch(`/command/workflows/${id}/draft`)", "the url"),
    ('fetch("/command/workflows/x/revisions")', "the url"),
    ("const n = automationDraft(detail);", "the client's counter"),
    ('import {automationDraft} from "./studio-automation-model.js";', "its module"),
])
def test_the_draft_door_scanner_sees_each_way_a_module_could_reach_it(planted, expected):
    assert expected in reaches(planted), planted


def test_desk_sources_never_target_draft_or_revisions_nor_import_automation_draft():
    found = {name: reaches(_code(PANEL / name)) for name in DESK if name != TRANSPORT}
    assert {name: rows for name, rows in found.items() if rows} == {}, (
        "the desk writes a cycle through `flow` and counts with the server's budget")


def test_the_transports_inherited_draft_and_revisions_rows_are_the_one_live_exception():
    door = _code(PANEL / TRANSPORT)
    named = set(_frozen_list(door, "WRITE_TARGETS"))
    assert INHERITED <= named, "the rows are gone: delete the exception and this test with it"
    assert re.search(r"^\s+draft: \(", door, re.MULTILINE)
    assert re.search(r"^\s+revisions: \(", door, re.MULTILINE)
    assert [name for name in DESK if name != TRANSPORT and reaches(_code(PANEL / name))] == []


# -- 2. the edit vocabulary -----------------------------------------------------------------


def test_desk_flow_edit_fields_equal_the_flow_schema_and_extension_fields():
    edits, inspector = _code(PANEL / "desk-flow-edits.js"), _code(PANEL / "desk-flow-inspector.js")
    fields = _frozen_list(edits, "EDIT_FIELDS")
    assert fields == _frozen_list(inspector, "EDIT_FIELDS"), "two copies, one vocabulary"
    assert fields == sorted(fields) and len(fields) == len(set(fields))
    typed = {name for names in workflow_flow.STEP_FIELDS.values() for name in names}
    typed -= {"step_id", "type", "position", "ext"}
    schema = typed | workflow_flow.EXT_FIELDS | {"passes", "rework"} | {"flow_title"} \
        | workflow_flow.FLOW_EXT_FIELDS
    assert set(fields) == schema, sorted(set(fields) ^ schema)
    written = js("show(fields.WRITTEN_FIELDS);")
    assert written == fields, "the rows the inspector draws write exactly the vocabulary"
    for source, where in ((edits, "the edits"), (inspector, "the inspector")):
        assert source.count("const EDIT_FIELDS") == 1, f"{where} declares the list once"


def test_desk_flow_edit_words_are_the_canvas_nine_in_three_places():
    edits = _frozen_list(_code(PANEL / "desk-flow-edits.js"), "EDIT_TYPES")
    assert edits == _frozen_list(_code(PANEL / "desk-flow-inspector.js"), "EDIT_TYPES")
    assert edits == _frozen_list(_code(PANEL / "studio-canvas.js"), "EDIT_TYPES")
    assert len(edits) == 9 and edits == sorted(edits)


def test_the_shape_s_copies_of_the_schema_are_the_schemas_word_for_word():
    out = js("""
      show({types: shape.STEP_TYPES, whens: shape.LINK_WHENS, ext: shape.EXT_FIELDS,
        bound: shape.BOUND_EXT_FIELDS, flowExt: shape.FLOW_EXT_FIELDS, keys: shape.STEP_KEYS,
        profiles: shape.REVIEW_PROFILES, version: shape.FLOW_VERSION, limits: shape.LIMITS,
        reserved: shape.RESERVED_IDS, kinds: Object.fromEntries(Object.entries(shape.ROLE_KINDS)
          .map(([name, row]) => [name, row.capability])), timeout: shape.DEFAULT_TIMEOUT});
    """)
    assert out["types"] == list(workflow_flow.STEP_TYPES)
    assert set(out["whens"]) == set(workflow_flow.LINK_WHEN)
    assert set(out["ext"]) == workflow_flow.EXT_FIELDS
    assert set(out["bound"]) == workflow_flow.BOUND_EXT_FIELDS
    assert set(out["flowExt"]) == workflow_flow.FLOW_EXT_FIELDS
    assert {name: tuple(keys) for name, keys in out["keys"].items()} == dict(
        workflow_flow.STEP_FIELDS)
    assert out["profiles"] == list(workflow_flow.REVIEW_PROFILES)
    assert out["version"] == workflow_flow.FLOW_VERSION
    assert out["limits"]["steps"] == workflow_draft.MAX_DRAFT_NODES
    assert out["limits"]["links"] == workflow_draft.MAX_DRAFT_EDGES
    assert out["limits"]["reads"] == workflow_flow.MAX_READS
    assert out["limits"]["position"] == graph_values.POSITION_LIMIT
    assert out["limits"]["bound"] == {"min": graph_values.MIN_LOOP_BOUND,
                                      "max": graph_values.MAX_LOOP_BOUND}
    assert out["limits"]["timeout"] == {"min": 1, "max": 86400}
    assert set(out["reserved"]) == {ref.removeprefix("artifact-")
                                    for ref in workflow_flow.ENTRY_INPUTS}
    assert set(out["kinds"]) == set(workflow_flow.KIND_TITLES)
    assert out["kinds"] == dict(flow_rules.CAPABILITY_OF_KIND)
    assert out["timeout"] == plan_budget.DEFAULT_TIMEOUT_SECONDS


# -- 3. the words of a road -----------------------------------------------------------------


def test_link_when_vocabulary_equals_graph_conditions_plus_always():
    conditions = {word.removeprefix("on_") for word in graph_conditions.EDGE_CONDITIONS}
    conditions = {"success" if word == "succeeded" else word for word in conditions}
    words = js("show(shape.LINK_WHENS);")
    assert set(words) == conditions | {"always"}, sorted(set(words) ^ (conditions | {"always"}))
    assert len(words) == len(set(words))
    mapped = {word: condition for word, condition in workflow_flow.LINK_WHEN.items()
              if condition is not None}
    assert set(mapped.values()) == graph_conditions.EDGE_CONDITIONS
    assert workflow_flow.LINK_WHEN["always"] is None, "`always` is the road with no condition"
    desk = js("show(shape.DESK_WORDS);")
    assert set(desk) <= set(words) and set(desk) == {"success", "approved", "rejected"}


# -- 4. the words of every row the server can give ------------------------------------------

#: The keys of the wizard's diagnostic catalogue that are not a code.
NOT_CODES = {"heading", "error", "warning", "at_step", "at_link", "none", "unknown"}


def test_every_flow_code_has_ru_and_en_text():
    codes = set(flow_rules.FLOW_CODES)
    out = js("""
      const rows = Object.entries(i18n.MESSAGES).filter(([key]) => key.startsWith("wizard.diag."))
        .map(([key, text]) => [key.slice("wizard.diag.".length), text.en, text.ru]);
      show(rows);
    """)
    held = {code: (en, ru) for code, en, ru in out if code not in NOT_CODES}
    assert set(held) == codes, sorted(set(held) ^ codes)
    for code, (english, russian) in held.items():
        assert english.strip() and russian.strip(), code
        assert re.search("[А-Яа-яЁё]", russian), f"{code} has no Russian text"
        assert not re.search("[А-Яа-яЁё]", english), f"{code} has Russian in its English text"
    assert {row[0] for row in out if row[0] in NOT_CODES} == NOT_CODES


def test_the_severity_a_code_carries_is_one_of_the_two_the_panel_draws():
    assert set(flow_rules.FLOW_CODES.values()) == {"error", "warning"}
    assert sum(1 for kind in flow_rules.FLOW_CODES.values() if kind == "error") == 24
    assert sum(1 for kind in flow_rules.FLOW_CODES.values() if kind == "warning") == 13


# -- every word of the catalogue is said by something ----------------------------------------

FLOW_SOURCES = ("desk-flow.js", "desk-flow-draw.js", "desk-flow-diag.js", "desk-flow-inspector.js",
                "desk-flow-model.js", "desk-flowwrite.js", "desk-flow-shape.js",
                "desk-flow-edits.js", "desk-flow-loops.js", "desk-flow-branches.js",
                "desk-flow-fields.js", "desk-flow-graph.js", "desk-quickcycle.js")
LITERAL = re.compile(r'["`](schema\.[a-z0-9_.]+)["`]')
FAMILY = re.compile(r"`(schema\.[a-z0-9_.]+\.)\$\{")


def test_every_schema_message_is_named_by_a_module_or_belongs_to_a_family_one_names():
    source = "\n".join(_code(PANEL / name) for name in FLOW_SOURCES)
    literals = set(LITERAL.findall(source))
    families = set(FAMILY.findall(source))
    keys = set(js("""
      show(Object.keys(i18n.MESSAGES).filter((key) => key.startsWith("schema.")));
    """))
    orphans = sorted(key for key in keys if key not in literals
                     and not any(key.startswith(prefix) for prefix in families))
    assert orphans == [], "a message nothing says is a word the catalogue keeps for nobody"
    missing = sorted(key for key in literals if key not in keys)
    assert missing == [], "a module names a message the catalogue does not have"
    assert {"schema.notice.", "schema.write.", "schema.model.", "schema.field."} <= families
