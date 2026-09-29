"""The wizard's sha256 and the document id of the chain (spec 6.4.1, link 5).

The id of a document the chain publishes is `doc-` and the first 32 hex of the sha256 of the run,
the reference, the media type and the content, NUL between them. The wizard's model is pure and
answers synchronously, so the digest is a fixed function in JavaScript rather than a platform
promise; here it is held against `hashlib` over the lengths where padding changes shape (55, 56,
63, 64, 65 bytes), multibyte and astral text, an embedded NUL and a long text.
"""
from __future__ import annotations

import hashlib

import pytest

from tests.desk_wizard_node import PANEL, run_js

MODULES = {"dig": "desk-wizard-digest.js"}
CORPUS = ["", "abc", "a" * 55, "a" * 56, "a" * 63, "a" * 64, "a" * 65, "a" * 119, "a" * 120,
          "a" * 128, "Привет, мир", "日本語のテキスト", "emoji 😀 and a NUL \x00 inside",
          "line one\r\nline two\n", "x" * 102400]


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_sha256_hex_equals_hashlib_over_the_lengths_where_padding_changes_shape():
    out = run_js("console.log(JSON.stringify(d.map((text) => dig.sha256Hex(text))));", CORPUS,
                 modules=MODULES)
    assert out == [sha256(text) for text in CORPUS]


def test_sha256_hex_of_abc_is_the_published_vector():
    out = run_js('console.log(JSON.stringify(dig.sha256Hex("abc")));', modules=MODULES)
    assert out == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


@pytest.mark.parametrize("run_id,ref,media,content", [
    ("task-a-r1", "artifact-brief", "text/markdown", "# Title\n\n## Todo\nText\n"),
    ("task-a-r1", "instruction-do", "text/markdown", "Сделай это"),
    ("task-b-r12", "artifact-materials", "text/plain", "")])
def test_the_document_id_is_doc_and_the_first_32_hex_of_the_nul_joined_fields(
        run_id, ref, media, content):
    out = run_js("""console.log(JSON.stringify(dig.documentId(...d)));""",
                 [run_id, ref, media, content], modules=MODULES)
    expected = sha256("\0".join([run_id, ref, media, content]))[:32]
    assert out == f"doc-{expected}"


def test_two_documents_that_differ_in_any_one_field_get_different_ids():
    out = run_js("""
      const base = ["run-1", "artifact-brief", "text/markdown", "text"];
      const ids = [base, ["run-2", ...base.slice(1)], [base[0], "artifact-x", ...base.slice(2)],
        [...base.slice(0, 2), "text/plain", base[3]], [...base.slice(0, 3), "text!"], base]
        .map((fields) => dig.documentId(...fields));
      console.log(JSON.stringify(ids));""", modules=MODULES)
    assert len(set(out[:5])) == 5 and out[5] == out[0]


def test_the_digest_module_imports_nothing_and_names_no_platform_digest():
    source = (PANEL / "desk-wizard-digest.js").read_text(encoding="utf-8")
    assert "import " not in source.replace("import * as", "")
    assert "crypto" not in source and "subtle" not in source
