"""The index bytes the first commit installs: one verified format, one marker per operation.

Pure bytes: no Git, no file, no process. The bytes a test judges are built by hand
(`tests.git_index_bytes`) so that each case breaks exactly one fact; the same format is probed
against a real Git in `test_git_index_marker_compat`.
"""
import ast
import hashlib
import json
import re
from dataclasses import replace
from pathlib import Path

import pytest

from conductor.command import git_setup_first_index as index
from conductor.command import git_setup_snapshot
from conductor.command.accept_manifest import sha256
from conductor.command.git_setup_first_index import (
    INDEX_PIN, MAX_ENTRIES, REASONS, SIGNATURE, Binding, IndexFormatRefused, IndexShape,
    binding_of, mark, terms_hash, verify, verify_binding)
from conductor.command.git_setup_first_records import INDEX_LIMIT
from tests.git_index_bytes import (
    DEFAULT_TREE, SIZE, build, digest, entry, extension, marker, plain, rechecksum, tree_extension)
from tests.test_git_setup_first_records import an_op

FORMATS = ["sha1", "sha256"]
NONCE, OTHER_NONCE = "0123456789abcdef", "fedcba9876543210"
TERMS, OTHER_TERMS = "1" * 64, "2" * 64
OTHER_TREE = {"sha1": "b" * 40, "sha256": "b" * 64}


def two(fmt, **breaks):
    """Two good entries and the `TREE` extension, with `build` told to break one part."""
    return build([entry("a", fmt), entry("b", fmt)], [tree_extension(None, 2, fmt)], fmt, **breaks)


def with_entries(entries, extensions=None):
    def made(fmt):
        wanted = [tree_extension(None, 1, fmt)] if extensions is None else extensions(fmt)
        return build(entries(fmt), wanted, fmt)
    return made


def with_extensions(*parts):
    """One entry, then these extensions (a part is bytes, or a function of the format)."""
    def made(fmt):
        return build([entry("a", fmt)], [part(fmt) if callable(part) else part for part in parts],
                     fmt)
    return made


def tree_of(payload):
    return with_extensions(extension(b"TREE", payload))


def marker_of(payload):
    return with_extensions(extension(b"CNDT", payload))


def foreign_format(fmt):
    """The same index made for the other hash format, judged here under `fmt`."""
    other = "sha1" if fmt == "sha256" else "sha256"
    return build([entry("a", other)], [tree_extension(None, 1, other)], other)


def unterminated(fmt):
    """One entry with a 4100 byte name that the data ends in, with no NUL after it."""
    full = entry(b"x" * 4100, fmt, flags=0xFFF)
    return build([full[:40 + SIZE[fmt] + 2 + 4100]], [], fmt)


GOOD_MARKER = f"v1;nonce={NONCE};terms={TERMS}".encode()
REFUSED = [
    pytest.param(lambda fmt: b"", "too_short", id="no_bytes_at_all"),
    pytest.param(lambda fmt: b"DIRC\0\0\0\2", "too_short", id="shorter_than_a_header"),
    pytest.param(lambda fmt: b"DIRC\0\0\0\2" + digest(fmt, b"DIRC\0\0\0\2"), "too_short",
                 id="a_body_shorter_than_a_header_behind_a_good_checksum"),
    pytest.param(lambda fmt: bytes(INDEX_LIMIT + 1), "too_large", id="larger_than_the_limit"),
    pytest.param(lambda fmt: two(fmt, signature=b"DIRX"), "signature", id="a_wrong_signature"),
    pytest.param(lambda fmt: two(fmt, version=1), "version", id="version_1"),
    pytest.param(lambda fmt: two(fmt, version=3), "version", id="version_3"),
    pytest.param(lambda fmt: two(fmt, version=4), "version", id="version_4"),
    pytest.param(lambda fmt: build([], [], fmt, count=MAX_ENTRIES + 1), "entry_count",
                 id="a_count_over_the_maximum"),
    pytest.param(lambda fmt: build([entry("a", fmt)], [], fmt, count=2), "entry_bounds",
                 id="a_count_the_bytes_cannot_hold"),
    pytest.param(with_entries(lambda fmt: [entry("a", fmt, flags=200)]), "entry_bounds",
                 id="an_entry_that_runs_past_the_data"),
    pytest.param(unterminated, "entry_bounds", id="a_long_name_without_its_terminating_nul"),
    pytest.param(with_entries(lambda fmt: [entry(b"", fmt)]), "name_length",
                 id="a_name_length_of_zero"),
    pytest.param(with_entries(lambda fmt: [entry("a", fmt, flags=0xFFF)]), "name_length",
                 id="a_short_name_behind_the_long_name_flag"),
    pytest.param(with_entries(lambda fmt: [entry(b"a\0b", fmt)]), "name_nul",
                 id="a_nul_inside_a_name"),
    pytest.param(with_entries(lambda fmt: [entry("b", fmt), entry("a", fmt)]), "name_order",
                 id="names_out_of_order"),
    pytest.param(with_entries(lambda fmt: [entry("a", fmt), entry("a", fmt)]), "name_order",
                 id="a_duplicate_name"),
    pytest.param(with_entries(lambda fmt: [entry("a", fmt, flags=1 | 0x1000)]), "stage",
                 id="a_stage_that_is_not_zero"),
    pytest.param(with_entries(lambda fmt: [entry("a", fmt, flags=1 | 0x4000)]), "extended_flag",
                 id="the_extended_flag"),
    pytest.param(with_entries(lambda fmt: [entry("a", fmt, dirty_pad=True)]), "padding",
                 id="padding_that_is_not_nul"),
    pytest.param(with_extensions(b"TREE\0"), "extension_header",
                 id="an_extension_header_cut_short"),
    pytest.param(with_extensions(extension(b"TREE", b"\0", size=99)), "extension_bounds",
                 id="an_extension_size_past_the_data"),
    pytest.param(with_extensions(lambda fmt: tree_extension(None, 1, fmt),
                                 lambda fmt: tree_extension(None, 1, fmt)),
                 "extension_duplicate", id="two_tree_extensions"),
    pytest.param(with_extensions(extension(b"EOIE", bytes(24))), "extension_not_allowed",
                 id="the_end_of_index_entries_extension"),
    pytest.param(with_extensions(extension(b"IEOT", bytes(12))), "extension_not_allowed",
                 id="the_index_entry_offset_table"),
    pytest.param(with_extensions(extension(b"UNTR", bytes(12))), "extension_not_allowed",
                 id="the_untracked_cache"),
    pytest.param(with_extensions(extension(b"ABCD", b"")), "extension_not_allowed",
                 id="an_unknown_capital_signature"),
    pytest.param(with_extensions(extension(b"abcd", b"")), "extension_not_allowed",
                 id="an_unknown_lower_case_signature"),
    pytest.param(with_extensions(extension(b"CNDT", GOOD_MARKER),
                                 lambda fmt: tree_extension(None, 1, fmt)),
                 "marker_position", id="the_marker_before_another_extension"),
    pytest.param(with_extensions(extension(b"CNDT", GOOD_MARKER),
                                 extension(b"CNDT", GOOD_MARKER)),
                 "extension_duplicate", id="two_markers"),
    pytest.param(marker_of(b"v2;nonce=" + NONCE.encode() + b";terms=" + TERMS.encode()),
                 "marker_payload", id="a_marker_of_another_version"),
    pytest.param(marker_of(f"v1;nonce=01234567;terms={TERMS}".encode()), "marker_payload",
                 id="a_marker_nonce_that_is_too_short"),
    pytest.param(marker_of(f"v1;nonce={NONCE.upper()};terms={TERMS}".encode()), "marker_payload",
                 id="a_marker_nonce_in_upper_case"),
    pytest.param(marker_of(GOOD_MARKER + b";extra=1"), "marker_payload",
                 id="a_marker_with_a_further_field"),
    pytest.param(marker_of(b""), "marker_payload", id="an_empty_marker"),
    pytest.param(tree_of(b""), "tree_extension", id="a_tree_payload_that_is_empty"),
    pytest.param(tree_of(b"x\0" + b"1 0\n" + bytes(20)), "tree_extension",
                 id="a_tree_root_that_has_a_name"),
    pytest.param(tree_of(b"\0one 0\n" + bytes(20)), "tree_extension",
                 id="a_tree_count_that_is_not_a_number"),
    pytest.param(tree_of(b"\0" + b"1 0\n" + bytes(7)), "tree_extension",
                 id="a_tree_root_with_a_short_object_name"),
    pytest.param(lambda fmt: two(fmt, trailer=b"\1" * SIZE[fmt]), "checksum",
                 id="a_wrong_checksum"),
    pytest.param(lambda fmt: two(fmt, trailer=bytes(SIZE[fmt])), "checksum_zero",
                 id="an_all_zero_checksum"),
    pytest.param(foreign_format, "checksum", id="the_other_hash_formats_trailer"),
]


@pytest.mark.parametrize("fmt", FORMATS)
@pytest.mark.parametrize("names", [[], ["a"], ["a.txt", "d/y.txt", "d.txt", "z"],
                                   [f"dir/f{number:04}" for number in range(300)]])
def test_verify_accepts_a_plain_index_of_zero_one_and_many_entries_in_sha1_and_sha256(fmt, names):
    shape = verify(plain(names, fmt), fmt, entries=len(names))
    assert shape == IndexShape(entries=len(names), extensions=("TREE",),
                               tree_root=DEFAULT_TREE[fmt], marker=None)


@pytest.mark.parametrize("fmt", FORMATS)
def test_verify_accepts_a_path_longer_than_the_name_field_can_count(fmt):
    name = b"d/" + b"x" * 5000
    shape = verify(plain([name, "a"], fmt), fmt, entries=2)
    assert shape.entries == 2


@pytest.mark.parametrize("fmt", FORMATS)
@pytest.mark.parametrize("make, reason", REFUSED)
def test_verify_refuses_each_malformed_index_with_its_own_reason(fmt, make, reason):
    with pytest.raises(IndexFormatRefused) as refused:
        verify(make(fmt), fmt)
    assert refused.value.reason == reason


@pytest.mark.parametrize("fmt", FORMATS)
def test_verify_refuses_a_count_other_than_the_one_expected(fmt):
    verify(plain(["a", "b"], fmt), fmt, entries=2)
    with pytest.raises(IndexFormatRefused) as refused:
        verify(plain(["a", "b"], fmt), fmt, entries=3)
    assert refused.value.reason == "entry_count"


def test_verify_refuses_an_object_format_it_does_not_know():
    with pytest.raises(IndexFormatRefused) as refused:
        verify(plain(["a"], "sha1"), "md5")
    assert refused.value.reason == "object_format"


def test_every_reason_is_a_closed_word_and_every_word_has_a_case():
    named = {param.values[1] for param in REFUSED} | {"entry_count", "object_format"}
    assert named == set(REASONS)
    assert all(re.fullmatch(r"[a-z_]+", word) for word in REASONS)
    assert str(IndexFormatRefused("signature")) == "signature"
    with pytest.raises(ValueError):
        IndexFormatRefused("a made up word")


@pytest.mark.parametrize("fmt", FORMATS)
def test_mark_adds_one_cndt_extension_before_the_trailer_and_keeps_every_other_byte(fmt):
    base = plain(["a", "b"], fmt)
    size = SIZE[fmt]
    marked = mark(base, fmt, nonce=NONCE, terms=TERMS)
    added = marker(NONCE, TERMS)
    assert marked[:-size] == base[:-size] + added
    assert marked[-size:] == digest(fmt, marked[:-size])
    assert verify(marked, fmt, entries=2).marker == (NONCE, TERMS)
    stripped = marked[:-size - len(added)]
    assert stripped + digest(fmt, stripped) == base
    with pytest.raises(IndexFormatRefused) as twice:
        mark(marked, fmt, nonce=OTHER_NONCE, terms=TERMS)
    assert twice.value.reason == "extension_duplicate"


@pytest.mark.parametrize("fmt", FORMATS)
@pytest.mark.parametrize("names", [[], ["a.txt"]], ids=["no_rows", "one_row"])
def test_marked_bytes_differ_for_two_operations_in_both_modes_and_formats(fmt, names):
    base = plain(names, fmt)
    four = {mark(base, fmt, nonce=nonce, terms=terms)
            for nonce in (NONCE, OTHER_NONCE) for terms in (TERMS, OTHER_TERMS)}
    assert len({hashlib.sha256(data).hexdigest() for data in four}) == 4
    assert base not in four


@pytest.mark.parametrize("fmt", FORMATS)
@pytest.mark.parametrize("nonce, terms", [
    pytest.param("short", TERMS, id="a_nonce_that_is_too_short"),
    pytest.param(NONCE.upper(), TERMS, id="a_nonce_in_upper_case"),
    pytest.param(NONCE, "1" * 63, id="terms_that_are_too_short"),
    pytest.param(NONCE, "g" * 64, id="terms_that_are_not_hex"),
])
def test_mark_refuses_a_nonce_or_terms_outside_the_marker_form_and_adds_nothing(fmt, nonce, terms):
    with pytest.raises(IndexFormatRefused) as refused:
        mark(plain(["a"], fmt), fmt, nonce=nonce, terms=terms)
    assert refused.value.reason == "marker_payload"


@pytest.mark.parametrize("fmt", FORMATS)
def test_mark_refuses_bytes_outside_the_format_so_nothing_foreign_is_ever_marked(fmt):
    eoie = plain(["a"], fmt, extensions=[tree_extension(None, 1, fmt),
                                         extension(b"EOIE", bytes(4 + SIZE[fmt]))])
    with pytest.raises(IndexFormatRefused) as refused:
        mark(eoie, fmt, nonce=NONCE, terms=TERMS)
    assert refused.value.reason == "extension_not_allowed"


def nearly_full(fmt, room):
    """A valid index that is `room` bytes short of the limit: the tree extension carries filler."""
    def with_filler(size):
        root = b"\0" + b"1 0\n" + bytes.fromhex(DEFAULT_TREE[fmt])
        return build([entry("a", fmt)], [extension(b"TREE", root + bytes(size))], fmt)
    return with_filler(INDEX_LIMIT - len(with_filler(0)) - room)


@pytest.mark.parametrize("fmt", FORMATS)
def test_mark_refuses_when_the_marked_bytes_would_pass_the_size_limit(fmt):
    base = nearly_full(fmt, room=50)
    assert len(base) == INDEX_LIMIT - 50
    assert verify(base, fmt, entries=1).entries == 1
    with pytest.raises(IndexFormatRefused) as refused:
        mark(base, fmt, nonce=NONCE, terms=TERMS)
    assert refused.value.reason == "too_large"
    assert len(mark(nearly_full(fmt, room=200), fmt, nonce=NONCE, terms=TERMS)) <= INDEX_LIMIT


def test_the_marker_signature_starts_with_a_capital_letter():
    """A lower-case first letter makes the extension REQUIRED: every Git that reads the index
    dies (measured, exit 128), so the signature is fixed here and the probe keeps the proof."""
    assert SIGNATURE == b"CNDT"
    assert "A" <= chr(SIGNATURE[0]) <= "Z"


def bound(marked, fmt, *, tree=None, count=1, **changes):
    fields = dict(nonce=NONCE, install_sha256=sha256(marked), terms=TERMS,
                  expected_tree=tree or DEFAULT_TREE[fmt], object_format=fmt, file_count=count)
    return Binding(**{**fields, **changes})


@pytest.mark.parametrize("fmt", FORMATS)
def test_binding_needs_every_part_and_the_marker_header_alone_proves_nothing(fmt):
    own = mark(plain(["a", "b"], fmt), fmt, nonce=NONCE, terms=TERMS)
    assert verify_binding(own, bound(own, fmt, count=2)) is True
    wrong = {
        "another terms hash": bound(own, fmt, count=2, terms=OTHER_TERMS),
        "another nonce": bound(own, fmt, count=2, nonce=OTHER_NONCE),
        "another install digest": bound(own, fmt, count=2, install_sha256=sha256(b"other")),
        "another expected tree": bound(own, fmt, count=2, tree=OTHER_TREE[fmt]),
        "another file count": bound(own, fmt, count=1),
        "another object format": bound(own, fmt, count=2,
                                       object_format="sha1" if fmt == "sha256" else "sha256"),
    }
    assert {name: verify_binding(own, value) for name, value in wrong.items()} == {
        name: False for name in wrong}


@pytest.mark.parametrize("fmt", FORMATS)
def test_the_exact_marker_on_other_bytes_is_foreign(fmt):
    own = mark(plain(["a", "b"], fmt), fmt, nonce=NONCE, terms=TERMS)
    bigger = mark(plain(["a", "b", "c"], fmt), fmt, nonce=NONCE, terms=TERMS)
    other_tree = mark(plain(["a", "b"], fmt, tree=OTHER_TREE[fmt]), fmt, nonce=NONCE, terms=TERMS)
    unmarked = plain(["a", "b"], fmt)
    claim = bound(own, fmt, count=2)
    assert verify_binding(bigger, claim) is False
    assert verify_binding(other_tree, claim) is False
    assert verify_binding(unmarked, claim) is False
    assert verify_binding(unmarked, bound(unmarked, fmt, count=2)) is False
    assert verify_binding(bigger, bound(bigger, fmt, count=3)) is True
    assert verify_binding(other_tree, bound(other_tree, fmt, count=2)) is False


@pytest.mark.parametrize("fmt", FORMATS)
def test_a_binding_never_raises_on_bytes_that_are_not_an_index(fmt):
    claim = bound(plain(["a"], fmt), fmt)
    for junk in (b"", b"DIRC", b"CNDT" * 40, bytes(100), b"\xff" * 4096):
        assert verify_binding(junk, claim) is False


@pytest.mark.parametrize("fmt", FORMATS)
def test_cache_tree_root_is_read_from_the_tree_extension(fmt):
    wanted = OTHER_TREE[fmt]
    assert verify(plain(["a"], fmt, tree=wanted), fmt).tree_root == wanted
    invalidated = build([entry("a", fmt)], [tree_extension(None, -1, fmt)], fmt)
    assert verify(invalidated, fmt).tree_root is None
    assert verify(build([entry("a", fmt)], [], fmt), fmt).tree_root is None
    subtrees = b"\0" + b"2 1\n" + bytes.fromhex(wanted) + b"d\0" + b"1 0\n" + bytes(SIZE[fmt])
    held = build([entry("a", fmt)], [extension(b"TREE", subtrees)], fmt)
    assert verify(held, fmt).tree_root == wanted


def a_changed_byte(data, position, fmt):
    return rechecksum(data[:position] + bytes([data[position] ^ 1]) + data[position + 1:], fmt)


@pytest.mark.parametrize("fmt", FORMATS)
def test_no_cut_or_flipped_byte_makes_verify_do_anything_but_accept_or_refuse(fmt):
    own = mark(plain(["a", "d/b"], fmt), fmt, nonce=NONCE, terms=TERMS)
    claim = bound(own, fmt, count=2)
    for length in range(len(own)):
        with pytest.raises(IndexFormatRefused):
            verify(own[:length], fmt)
        assert verify_binding(own[:length], claim) is False
    for position in range(len(own) - SIZE[fmt]):
        changed = a_changed_byte(own, position, fmt)
        try:
            verify(changed, fmt)
        except IndexFormatRefused:
            pass
        assert verify_binding(changed, claim) is False


def test_the_pin_is_the_seven_settings_that_keep_optional_parts_out_of_a_built_index():
    pairs = list(zip(INDEX_PIN[0::2], INDEX_PIN[1::2]))
    assert all(flag == "-c" for flag, _ in pairs) and len(INDEX_PIN) == 14
    assert dict(value.split("=") for _, value in pairs) == {
        "core.splitIndex": "false", "index.version": "2", "index.skipHash": "false",
        "index.recordEndOfIndexEntries": "false", "index.threads": "1",
        "core.untrackedCache": "false", "index.sparse": "false"}


def test_the_largest_index_is_the_largest_first_commit_the_preview_allows():
    assert MAX_ENTRIES == git_setup_snapshot.MAX_FILES


TERM_FIELDS = dict(nonce=NONCE, mode="snapshot", digest_version=2,
                   paths_digest="sha256:" + "c" * 64, target_ref="refs/heads/trunk",
                   object_format="sha1", expected_tree="a" * 40, file_count=2)


def test_the_terms_hash_is_a_sha256_over_the_canonical_terms_and_changes_with_each_of_them():
    row = json.dumps(TERM_FIELDS, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    shown = terms_hash(**TERM_FIELDS)
    assert shown == hashlib.sha256(row.encode("ascii")).hexdigest()
    other = dict(nonce=OTHER_NONCE, mode="empty", digest_version=3, paths_digest=None,
                 target_ref="refs/heads/main", object_format="sha256", expected_tree="b" * 64,
                 file_count=3)
    assert set(other) == set(TERM_FIELDS)
    assert {key for key, value in other.items()
            if terms_hash(**{**TERM_FIELDS, key: value}) == shown} == set()


@pytest.mark.parametrize("fmt", FORMATS)
def test_the_binding_of_an_op_marks_and_proves_the_op_s_own_bytes_and_no_other_op(fmt):
    base = plain(["a", "b"], fmt, tree=OTHER_TREE[fmt])
    fields = dict(nonce=NONCE, mode="snapshot", digest_version=2, paths_digest="sha256:" + "c" * 64,
                  target_ref="refs/heads/trunk", object_format=fmt, expected_tree=OTHER_TREE[fmt],
                  file_count=2)
    marked = mark(base, fmt, nonce=NONCE, terms=terms_hash(**fields))
    op = an_op(data=marked, nonce=NONCE, object_format=fmt, expected_tree=OTHER_TREE[fmt])
    claim = binding_of(op)
    assert claim == Binding(NONCE, sha256(marked), terms_hash(**fields), OTHER_TREE[fmt], fmt, 2)
    assert verify_binding(marked, claim) is True
    for changed in (replace(op, paths_digest="sha256:" + "e" * 64), replace(op, file_count=1),
                    replace(op, target_ref="refs/heads/main"), replace(op, digest_version=3)):
        assert verify_binding(marked, binding_of(changed)) is False


def test_no_module_of_the_first_commit_names_or_filters_the_notice_a_git_prints_for_the_marker():
    """The line is the accepted cost: the product does not hide it, so no module spells it."""
    modules = sorted(Path(index.__file__).parent.glob("git_setup_first*.py"))
    assert Path(index.__file__) in modules and len(modules) >= 3
    spelled = [module.name for module in modules
               if re.search(r"\bignoring\b|CNDT\s+extension", module.read_text(encoding="utf-8"),
                            re.IGNORECASE)]
    assert spelled == []


def test_the_format_module_runs_no_process_and_touches_no_file():
    """Nothing here may reach outside its argument: the imports and calls are the witness."""
    tree = ast.parse(Path(index.__file__).read_text(encoding="utf-8"))
    imported = {alias.name.split(".")[0] for node in ast.walk(tree)
                if isinstance(node, ast.Import) for alias in node.names}
    imported |= {node.module.split(".")[0] for node in ast.walk(tree)
                 if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module}
    called = {node.func.id for node in ast.walk(tree)
              if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert not imported & {"os", "subprocess", "pathlib", "shutil", "tempfile", "socket", "io"}
    assert not called & {"open", "exec", "eval", "compile", "__import__"}
