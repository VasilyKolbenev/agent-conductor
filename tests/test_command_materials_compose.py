"""`compose_materials`: the pure half of the materials document (spec 6.2.3, 6.2.5).

The function turns the body of `POST /command/runs/<run_id>/materials` into the text of
`artifact-materials`. It is pure and bounded, so what is held here is what only a pure function can
promise: the same bytes for the same input whatever order the mappings were built in, a size
measured in UTF-8 bytes and decided before the work that would make it, a closed vocabulary of
refusals with the material each names, and no clock, randomness or I/O. Routes, the seed record
and the wire's own status codes are lane L's: the caller hands the composer `base`, the files the
seed really copied (a link is judged against it), and `documents`, the tracked documents of HEAD
by document id (a copy takes its path from it, and needs no seed), and turns a `MaterialsRefused`
into `materials_refused`.
"""
from __future__ import annotations

import ast
import copy
from pathlib import Path

import pytest

from conductor.command import materials
from conductor.command.artifacts import ARTIFACT_CONTENT_LIMIT
from conductor.command.contract_values import ContractError
from conductor.command.materials import (
    MAX_MATERIALS,
    REFUSALS,
    BaseFile,
    MaterialsRefused,
    compose_materials,
)
from tests.desk_wizard_node import run_js

OID = "a" * 40
OTHER_OID = "b" * 40
SPEC_ID = "d-" + "1" * 32
NOTES_ID = "d-" + "2" * 32
AGENTS_ID = "d-" + "3" * 32
BASE = {SPEC_ID: BaseFile("docs/spec.md", OID), NOTES_ID: BaseFile("docs/notes.md", OTHER_OID)}
#: HEAD's documents, which the seed need not have copied: `AGENTS.md` is one the seed leaves out.
DOCUMENTS = {SPEC_ID: "docs/spec.md", NOTES_ID: "docs/notes.md", AGENTS_ID: "AGENTS.md"}


def note(title="Notes", content="Body", kind="note"):
    return {"kind": kind, "title": title, "content": content}


def link(doc_id=SPEC_ID, oid=OID):
    return {"kind": "project_doc", "doc_id": doc_id, "git_oid": oid, "mode": "link"}


def copy_of(doc_id=SPEC_ID, oid=OID, content="Spec text"):
    return {"kind": "project_doc", "doc_id": doc_id, "git_oid": oid, "mode": "copy",
            "content": content}


def size(text):
    return len(text.encode("utf-8"))


def refusal(items, lang="en", base=BASE, documents=DOCUMENTS):
    with pytest.raises(MaterialsRefused) as raised:
        compose_materials(items, lang, base, documents)
    return raised.value


# --- the §6.2.5 claim --------------------------------------------------------------------------


def test_materials_document_is_composed_deterministically_and_bounded():
    items = [note("План", "Шаг один.", "plan"), note("Схема", "flowchart TD\n  A --> B", "scheme"),
             link(), copy_of(NOTES_ID, OTHER_OID, "Копия")]
    first = compose_materials(items, "ru", BASE, DOCUMENTS)
    assert first.encode("utf-8") == compose_materials(items, "ru", BASE, DOCUMENTS).encode("utf-8")
    reversed_keys = [dict(reversed(list(item.items()))) for item in items]
    assert compose_materials(reversed_keys, "ru", dict(reversed(list(BASE.items()))),
                             dict(reversed(list(DOCUMENTS.items())))) == first
    assert size(first) <= ARTIFACT_CONTENT_LIMIT
    twelve = [note(f"N{at}", "text") for at in range(MAX_MATERIALS)]
    assert compose_materials(twelve, "en", None, DOCUMENTS).count("\n## ") == 12
    assert refusal(twelve + [note()]).reason == "too_many_materials"


def test_the_count_is_judged_before_any_item_is_looked_at():
    garbage = [{} for _ in range(MAX_MATERIALS + 1)]
    assert refusal(garbage).reason == "too_many_materials"


def test_the_size_limit_counts_utf_8_bytes_of_the_composed_document_not_characters():
    def document(content):
        return compose_materials([note("T", content)], "en", None, DOCUMENTS)

    overhead = size(document("ж")) - 2
    room = ARTIFACT_CONTENT_LIMIT - overhead
    exact = "ж" * (room // 2) + "a" * (room % 2)
    assert size(document(exact)) == ARTIFACT_CONTENT_LIMIT
    assert refusal([note("T", exact + "a")]).reason == "materials_too_large"
    fewer_characters_than_bytes_allowed = "ж" * (ARTIFACT_CONTENT_LIMIT // 2 + 10)
    assert len(fewer_characters_than_bytes_allowed) < ARTIFACT_CONTENT_LIMIT
    assert refusal([note("T", fewer_characters_than_bytes_allowed)]).reason == (
        "materials_too_large")


# --- what the document says --------------------------------------------------------------------


def test_sections_are_numbered_in_order_and_each_names_its_kind():
    items = [note("Plan", "First step.", "plan"), note("Ideas", "One idea.", "ideas"),
             note("Notes", "A note.", "note")]
    assert compose_materials(items, "en", None, DOCUMENTS) == (
        "# Materials\n\n## 1. Plan · plan\nFirst step.\n\n## 2. Ideas · ideas\nOne idea.\n\n"
        "## 3. Notes · note\nA note.\n")
    assert compose_materials(items[:1], "ru", None, DOCUMENTS) == (
        "# Материалы\n\n## 1. Plan · plan\nFirst step.\n")


def test_a_scheme_is_fenced_as_mermaid_with_a_fence_longer_than_any_backtick_run_inside():
    def scheme(content):
        return compose_materials([note("S", content, "scheme")], "en", None, DOCUMENTS)

    assert scheme("flowchart TD\n  A --> B").endswith(
        "## 1. S · scheme\n```mermaid\nflowchart TD\n  A --> B\n```\n")
    assert "````mermaid\na ``` b\n````\n" in scheme("a ``` b")
    assert "``````mermaid\n`````\n``````\n" in scheme("`````")


def test_a_link_says_the_path_and_the_blob_and_that_no_text_was_copied_in_each_language():
    ru = compose_materials([link()], "ru", BASE, DOCUMENTS)
    assert ru == ("# Материалы\n\n## 1. docs/spec.md · project_doc\n"
                  f"Файл проекта в рабочей папке: `docs/spec.md` (git blob `{OID}`), "
                  "текст не скопирован\n")
    en = compose_materials([link()], "en", BASE, DOCUMENTS)
    assert en == ("# Materials\n\n## 1. docs/spec.md · project_doc\n"
                  f"Project file in the work folder: `docs/spec.md` (git blob `{OID}`), "
                  "text not copied\n")


def test_a_copy_names_its_source_as_path_at_oid_and_carries_the_owners_text():
    document = compose_materials([copy_of(SPEC_ID, OTHER_OID, "Edited by the owner.")], "en",
                                 BASE, DOCUMENTS)
    assert document == (f"# Materials\n\n## 1. docs/spec.md@{OTHER_OID} · project_doc\n"
                        "Edited by the owner.\n")


def test_a_copy_is_not_compared_with_the_base_blob_because_it_is_the_owners_text():
    document = compose_materials([copy_of(SPEC_ID, OTHER_OID)], "en", BASE, DOCUMENTS)
    assert f"docs/spec.md@{OTHER_OID}" in document and OID not in document


def test_a_copy_needs_no_seed_because_its_path_comes_from_the_head_documents():
    document = compose_materials([copy_of(SPEC_ID, OID, "Owner text")], "en", None, DOCUMENTS)
    assert document == f"# Materials\n\n## 1. docs/spec.md@{OID} · project_doc\nOwner text\n"


def test_a_copy_of_a_document_the_seed_did_not_copy_is_composed():
    """An agent-instructions file the seed leaves out is still a document the owner may copy."""
    assert AGENTS_ID not in BASE
    document = compose_materials([copy_of(AGENTS_ID, OID, "Rules, edited")], "en", BASE,
                                 DOCUMENTS)
    assert f"## 1. AGENTS.md@{OID} · project_doc\nRules, edited\n" in document


def test_a_copy_takes_its_path_from_the_documents_and_never_from_the_base():
    elsewhere = {SPEC_ID: BaseFile("elsewhere/spec.md", OID)}
    document = compose_materials([copy_of()], "en", elsewhere, DOCUMENTS)
    assert f"## 1. docs/spec.md@{OID}" in document and "elsewhere" not in document


def test_no_materials_compose_the_none_document_in_each_language():
    assert compose_materials([], "ru", None, DOCUMENTS) == "# Материалы\n\nМатериалов нет\n"
    assert compose_materials([], "en", None, DOCUMENTS) == "# Materials\n\nNo materials\n"


def test_the_language_changes_only_the_words_the_composer_writes_and_never_the_owners_text():
    items = [note("Owner title", "Owner body", "plan"), link(), copy_of()]
    for lang in ("ru", "en"):
        document = compose_materials(items, lang, BASE, DOCUMENTS)
        for kept in ("Owner title", "Owner body", "Spec text", "docs/spec.md", OID):
            assert kept in document, (lang, kept)


# --- what is refused ---------------------------------------------------------------------------


def test_a_copy_that_is_not_text_is_refused_as_not_text_and_names_its_material():
    for content in ("binary\x00bytes", "lone \ud800 surrogate"):
        raised = refusal([note(), copy_of(content=content)])
        assert (raised.reason, raised.index) == ("document_not_text", 1)


def test_a_link_the_seed_base_lacks_is_refused_as_unknown_even_when_the_head_documents_list_it():
    stranger = "d-" + "9" * 32
    assert refusal([link(stranger)]).reason == "doc_unknown"
    assert refusal([note(), link(stranger)]).index == 1
    assert AGENTS_ID in DOCUMENTS and AGENTS_ID not in BASE
    assert refusal([link(AGENTS_ID)]).reason == "doc_unknown"


def test_a_copy_the_head_documents_lack_is_refused_as_unknown_and_names_its_material():
    raised = refusal([note(), copy_of("d-" + "9" * 32)])
    assert (raised.reason, raised.index) == ("doc_unknown", 1)
    assert refusal([copy_of()], documents={}).reason == "doc_unknown"


def test_a_link_whose_oid_is_not_the_base_blob_is_refused_as_moved():
    raised = refusal([link(SPEC_ID, OTHER_OID)])
    assert (raised.reason, raised.index) == ("materials_base_moved", 0)


def test_a_link_without_a_seed_is_refused_as_seed_missing_and_text_needs_no_seed():
    raised = refusal([note(), link()], base=None)
    assert (raised.reason, raised.index) == ("seed_missing", 1)
    assert compose_materials([note()], "en", None, DOCUMENTS), "text materials need no seed"


def test_every_reason_the_composer_can_raise_is_in_the_closed_list():
    assert set(REFUSALS) == {"too_many_materials", "materials_too_large", "document_not_text",
                             "doc_unknown", "materials_base_moved", "seed_missing"}
    with pytest.raises(ValueError):
        MaterialsRefused("something_else")


SHAPE_FAULTS = {
    "a key of a path": [{**link(), "path": "docs/spec.md"}],
    "a key of a root": [{**note(), "root": "."}],
    "a key of a directory": [{**note(), "dir": "docs"}],
    "an unknown kind": [note(kind="diagram")],
    "no kind": [{"title": "T", "content": "c"}],
    "an unknown mode": [{**link(), "mode": "both"}],
    "a link that carries text": [{**link(), "content": "text"}],
    "a copy without text": [{key: value for key, value in copy_of().items() if key != "content"}],
    "a document id of another grammar": [link("d-short")],
    "an oid of another grammar": [link(oid="abc")],
    "no title": [{"kind": "note", "content": "c"}],
    "a blank title": [note("   ")],
    "a title on two lines": [note("one\ntwo")],
    "a title with a carriage return": [note("one\rtwo")],
    "blank text": [note(content="  \n")],
    "text with NUL": [note(content="a\x00b")],
    "text that is not a string": [note(content=7)],
    "an item that is not an object": ["note"],
    "items that are not a list": {"kind": "note"},
}


@pytest.mark.parametrize("items", SHAPE_FAULTS.values(), ids=list(SHAPE_FAULTS))
def test_a_body_the_closed_shape_does_not_name_is_a_contract_error_and_not_a_refusal(items):
    with pytest.raises(ContractError) as raised:
        compose_materials(items, "en", BASE, DOCUMENTS)
    assert not isinstance(raised.value, MaterialsRefused)


def test_a_language_the_desk_does_not_speak_is_a_contract_error():
    with pytest.raises(ContractError):
        compose_materials([note()], "de", None, DOCUMENTS)


def test_a_base_row_that_is_not_a_base_file_is_a_contract_error():
    with pytest.raises(ContractError):
        compose_materials([link()], "en", {SPEC_ID: ("docs/spec.md", OID)}, DOCUMENTS)


@pytest.mark.parametrize("path", ["docs/a\nb.md", "docs/`x`.md", "docs/a\x00b.md", ""])
def test_a_path_the_document_could_not_quote_is_a_contract_error(path):
    with pytest.raises(ContractError):
        compose_materials([link()], "en", {SPEC_ID: BaseFile(path, OID)}, DOCUMENTS)


@pytest.mark.parametrize("path", ["docs/a\nb.md", "docs/`x`.md", "docs/a\x00b.md", "", 7, None])
def test_a_documents_row_the_heading_could_not_carry_is_a_contract_error(path):
    with pytest.raises(ContractError) as raised:
        compose_materials([copy_of()], "en", None, {SPEC_ID: path})
    assert not isinstance(raised.value, MaterialsRefused)


@pytest.mark.parametrize("documents", [None, [SPEC_ID], "docs/spec.md"])
def test_documents_that_are_not_a_mapping_are_a_contract_error(documents):
    with pytest.raises(ContractError):
        compose_materials([copy_of()], "en", None, documents)


# --- purity ------------------------------------------------------------------------------------


def test_the_composer_never_changes_its_inputs():
    items = [note("T", "c", "scheme"), link(), copy_of()]
    held_items, held_base, held_documents = copy.deepcopy(items), dict(BASE), dict(DOCUMENTS)
    compose_materials(items, "en", BASE, DOCUMENTS)
    assert items == held_items and BASE == held_base and DOCUMENTS == held_documents


ALLOWED_IMPORTS = {"__future__", "re", "collections.abc", "typing", "conductor.command.artifacts",
                   "conductor.command.contract_values"}


def test_the_materials_module_reaches_no_clock_no_randomness_and_no_input_output():
    tree = ast.parse(Path(materials.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name for alias in node.names}
        if isinstance(node, ast.ImportFrom):
            level = "conductor.command" if node.level == 1 else ""
            imported.add(".".join(part for part in (level, node.module or "") if part))
    assert imported <= ALLOWED_IMPORTS, imported - ALLOWED_IMPORTS
    called = {node.func.id for node in ast.walk(tree)
              if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert not called & {"open", "print", "exec", "eval", "input", "__import__"}


# --- the desk and the composer agree -----------------------------------------------------------

DESK_CARDS = """
const cards = [
  m.textCard("m1", {kind: "plan", title: "План работ", content: "Шаг первый.\\nШаг второй."}),
  m.textCard("m2", {kind: "scheme", title: "Схема", content: "flowchart TD\\n  A --> B"}),
  m.textCard("m3", {kind: "note", title: "Из стартовых", content: "Текст",
    source: "starter_docs"}),
  {...m.documentCard("m4", {doc_id: d.spec, git_oid: d.oid, path: "docs/spec.md", length: 10}),
   mode: "link"},
  {...m.documentCard("m5", {doc_id: d.notes, git_oid: d.other, path: "docs/notes.md",
    length: 10}), mode: "copy", content: "Копия для правки", fetched: true}];
"""
DESK_SENDS = """
console.log(JSON.stringify({ru: m.bodyOf(cards, "ru"), en: m.bodyOf(cards, "en"),
  estimate: m.composeText(cards, "ru")}));
"""
NO_CARDS = "const cards = [];"
#: Two schemes whose text holds runs of backticks: the composer lengthens the fence around the
#: longest run, so a fence of three would leave the estimate below the document.
TICK_CARDS = """
const cards = [
  m.textCard("m1", {kind: "scheme", title: "S1", content: "a ````` b"}),
  m.textCard("m2", {kind: "scheme", title: "S2", content: "```\\n``` and ``"})];
"""
DOCS = {"spec": SPEC_ID, "notes": NOTES_ID, "oid": OID, "other": OTHER_OID}


@pytest.mark.parametrize("cards", [DESK_CARDS, NO_CARDS, TICK_CARDS],
                         ids=["five cards", "no cards", "schemes with backticks"])
def test_the_composer_accepts_the_body_the_desk_sends_and_the_desks_estimate_is_not_below_it(
        cards):
    sent = run_js(cards + DESK_SENDS, DOCS, modules={"m": "desk-wizard-materials.js"})
    for lang in ("ru", "en"):
        body = sent[lang]
        assert body["lang"] == lang
        document = compose_materials(body["items"], lang, BASE, DOCUMENTS)
        assert size(sent["estimate"]) >= size(document), (lang, sent["estimate"], document)
