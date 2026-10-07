"""A UTF-8 byte order mark at a document's start is a spelling, not a defect.

Windows PowerShell writes one: `Out-File -Encoding utf8` and every editor that
calls its output "UTF-8 with signature" prefix the file with `EF BB BF`. A
person who saves `conductor/map.toml` that way has changed nothing about what
the document says, so the three tolerant readers in `conductor.store` must read
it. Before this module they did not: the map failed as "Invalid statement (line
1, column 1)" on a file that looks perfectly fine, the lane was reported broken,
and `events.jsonl` silently DROPPED its first record with nothing on either
stream but a bumped `skipped_events`.

What is held here is the boundary, in both directions. A BOM is a document-start
artefact, so exactly one of them, at byte zero of the file, is admissible. A
second one is content; one in the middle of a document is content; one opening
the SECOND line of a JSONL stream is content, because line two of that stream is
not a document start. Each of those stays malformed, and each is what tells a
`utf-8-sig` decode apart from a blanket `lstrip("\\ufeff")` that would accept
every one of them.

The last test guards the other half of the contract this product has always
kept: it reads a BOM, and it never writes one.
"""
import json

from conductor import store
from conductor.__main__ import main
from tests.test_store import write_project, good_lane

#: The bytes PowerShell prepends. Spelled as bytes, never as `"﻿".encode()`,
#: so the fixture states the on-disk fact rather than restating the codec.
BOM = b"\xef\xbb\xbf"

MAP = ('schema_version = 1\nproject = "bommed"\n'
       '[[nodes]]\nid = "a"\nlabel = "a"\nkind = "artifact"\n')

EVENT_ONE = '{"ts":"2026-08-01T10:00:00+00:00","author":"a","kind":"ok","text":"first"}'
EVENT_TWO = '{"ts":"2026-08-01T11:00:00+00:00","author":"a","kind":"ok","text":"second"}'


def _rewrite(root, name, raw: bytes):
    """Replace one file under `conductor/` with exact bytes, encoding and all."""
    (root / "conductor" / name).write_bytes(raw)
    return root


# --- the three first-hour surfaces a BOM broke -------------------------------


def test_a_map_saved_with_a_byte_order_mark_is_read_rather_than_called_invalid(tmp_path):
    root = write_project(tmp_path, map_toml=MAP)
    _rewrite(root, "map.toml", BOM + MAP.encode("utf-8"))
    loaded = store.load(root)
    assert loaded.map_error is None, loaded.map_error
    assert loaded.map_data is not None
    assert loaded.map_data["project"] == "bommed"


def test_a_lane_saved_with_a_byte_order_mark_is_live_rather_than_broken(tmp_path):
    root = write_project(tmp_path)
    (root / "conductor" / "lanes" / "claude.json").write_bytes(
        BOM + good_lane().encode("utf-8"))
    loaded = store.load(root)
    assert loaded.lanes[0]["error"] is None, loaded.lanes[0]["error"]
    assert loaded.lanes[0]["data"] is not None
    assert loaded.lanes[0]["data"]["author"] == "claude"


def test_the_first_event_of_a_marked_log_is_read_rather_than_silently_dropped(tmp_path):
    # The worst of the three, because nothing said so: no error, no warning, a
    # green `conduct validate`, and the project's first event gone from the
    # merge and from the panel.
    root = write_project(tmp_path, events=f"{EVENT_ONE}\n{EVENT_TWO}\n")
    _rewrite(root, "events.jsonl",
             BOM + f"{EVENT_ONE}\n{EVENT_TWO}\n".encode("utf-8"))
    loaded = store.load(root)
    assert loaded.skipped_events == 0
    assert [e["text"] for e in loaded.events] == ["first", "second"]


# --- the boundary: only ONE mark, and only at byte zero of the document ------


def test_a_mark_in_the_middle_of_a_map_is_still_a_parse_error(tmp_path):
    root = write_project(tmp_path, map_toml=MAP)
    body = MAP.encode("utf-8").replace(b"[[nodes]]", BOM + b"[[nodes]]")
    _rewrite(root, "map.toml", body)
    loaded = store.load(root)
    assert loaded.map_data is None
    assert loaded.map_error and "unreadable" in loaded.map_error


def test_a_mark_in_the_middle_of_a_lane_is_still_a_broken_lane(tmp_path):
    root = write_project(tmp_path)
    body = good_lane().encode("utf-8").replace(b'"author"', BOM + b'"author"')
    (root / "conductor" / "lanes" / "claude.json").write_bytes(body)
    loaded = store.load(root)
    assert loaded.lanes[0]["data"] is None
    assert loaded.lanes[0]["error"].startswith("lane claude:")


def test_a_mark_opening_the_second_event_line_is_still_malformed(tmp_path):
    # Line two of a JSONL stream is not a document start, so the mark there is
    # content. This is the assertion a blanket lstrip of U+FEFF cannot pass.
    root = write_project(tmp_path, events="x\n")
    _rewrite(root, "events.jsonl",
             f"{EVENT_ONE}\n".encode("utf-8") + BOM + f"{EVENT_TWO}\n".encode("utf-8"))
    loaded = store.load(root)
    assert loaded.skipped_events == 1
    assert [e["text"] for e in loaded.events] == ["first"]


def test_a_second_mark_is_content_and_the_document_stays_malformed(tmp_path):
    # The over-correction control. One signature is a spelling of the same
    # document; two are not, and a reader that strips every leading U+FEFF it
    # meets has stopped reading UTF-8 and started editing the file.
    root = write_project(tmp_path, map_toml=MAP)
    _rewrite(root, "map.toml", BOM + BOM + MAP.encode("utf-8"))
    loaded = store.load(root)
    assert loaded.map_data is None
    assert loaded.map_error and "unreadable" in loaded.map_error


def test_a_marked_file_reaches_conduct_validate_as_a_clean_project(tmp_path, capsys):
    # The surface the person actually meets. A clean `validate` writes zero
    # bytes on both streams, so this measures the whole first-hour circuit and
    # not just the loader.
    root = write_project(tmp_path, map_toml=MAP)
    _rewrite(root, "map.toml", BOM + MAP.encode("utf-8"))
    (root / "conductor" / "lanes" / "claude.json").write_bytes(
        BOM + good_lane().encode("utf-8"))
    assert main(["validate", "--dir", str(root)]) == 0
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""


# --- and the product still never writes one ---------------------------------


def test_nothing_conduct_init_writes_ever_gains_a_byte_order_mark(tmp_path, capsys):
    # Tolerant reader, strict writer. Accepting a mark on the way in must not
    # become a licence to emit one: a BOM'd map.toml is a file every other tool
    # in a person's toolchain then has to be tolerant about too.
    assert main(["init", "--template", "minimal", "--dir", str(tmp_path)]) == 0
    capsys.readouterr()
    cdir = tmp_path / "conductor"
    for name in ("map.toml", "events.jsonl"):
        raw = (cdir / name).read_bytes()
        assert not raw.startswith(BOM), f"{name} was written with a BOM"
        assert b"\xef\xbb\xbf" not in raw, f"{name} carries a BOM somewhere inside"


def test_a_lane_the_product_reads_back_is_unchanged_by_the_mark(tmp_path):
    # The equality that says `utf-8-sig` decoded rather than edited: the same
    # document, saved with and without the signature, loads to the same object.
    plain = write_project(tmp_path / "plain", lanes={"claude": good_lane()})
    marked = write_project(tmp_path / "marked")
    (marked / "conductor" / "lanes" / "claude.json").write_bytes(
        BOM + good_lane().encode("utf-8"))
    assert (store.load(marked).lanes[0]["data"]
            == store.load(plain).lanes[0]["data"] == json.loads(good_lane()))
