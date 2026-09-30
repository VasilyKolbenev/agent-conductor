"""The pure plan of a seed: what a tree listing becomes before any byte is read (9.1.2, 9.1.3).

`ls-tree -r -l -z` names every path of the base with its mode, type, object id and size. From that
alone the plan decides what is copied, what is left out and why, which paths the product cannot
seed at all, and how the bytes are asked for in batches of a size the runner accepts. Nothing here
touches a disk or runs a process; the staging that uses it is tested with a real repository.
"""
from __future__ import annotations

import zlib
from pathlib import PureWindowsPath

import pytest

from conductor.command import seed_plan
from conductor.command.api_refusals import SEED_REASONS
from conductor.command.product_names import PRODUCT_TOP_NAMES
from conductor.command.seed_plan import (
    BATCH_OUTPUT_CEILING, MAX_SKIPS, OBJECT_OVERHEAD, SEED_MAX_BYTES, SEED_MAX_FILES, SeedRefusal,
    TreeRow, blob_batches, is_lfs_pointer, parse_batch, parse_listing, plan_seed)

SHA1 = "ab" * 20
OTHER = "cd" * 20


def oid(number, length=40):
    return f"{number:x}".rjust(length, "0")


def row(path, *, mode="100644", size=10, blob=None):
    kind = "commit" if mode == "160000" else "blob"
    return TreeRow(mode, kind, blob or oid(zlib.crc32(path.encode("utf-8", "surrogatepass"))),
                   None if mode == "160000" else size, path)


def listing(*rows):
    """`ls-tree -r -l -z` output for rows, the size column right-aligned to seven as git does."""
    parts = []
    for one in rows:
        size = "-" if one.size is None else str(one.size)
        parts.append(f"{one.mode} {one.kind} {one.oid} {size:>7}\t{one.path}".encode("utf-8"))
    return b"\0".join(parts) + (b"\0" if parts else b"")


def planned(*rows, **asked):
    asked.setdefault("include_agent_instructions", False)
    return plan_seed(rows, **asked)


def refusal_of(*rows, **asked):
    with pytest.raises(SeedRefusal) as refused:
        planned(*rows, **asked)
    return refused.value.reason


# --- the refusal carries one word of the closed list --------------------------------------------


def test_a_refusal_carries_a_reason_of_the_closed_list_and_no_other():
    assert SeedRefusal("base_moved").reason == "base_moved"
    with pytest.raises(ValueError):
        SeedRefusal("not_a_reason")


def test_a_refusal_carries_the_commit_that_explains_it_and_none_by_default():
    assert SeedRefusal("git_failed").commit is None
    assert SeedRefusal("base_moved", SHA1).commit == SHA1


# --- the listing ----------------------------------------------------------------------------------


def test_a_listing_row_is_mode_type_oid_size_and_path():
    rows = parse_listing(listing(row("docs/a.md", size=12, blob=SHA1)))
    assert rows == (TreeRow("100644", "blob", SHA1, 12, "docs/a.md"),)


def test_a_submodule_row_has_no_size_and_an_empty_listing_has_no_rows():
    sub = TreeRow("160000", "commit", OTHER, None, "vendor/x")
    assert parse_listing(listing(sub)) == (sub,)
    assert parse_listing(b"") == ()


def test_a_path_with_spaces_a_tab_and_a_line_break_is_read_whole_up_to_its_nul():
    path = "we ird\tname\nhere.txt"
    assert parse_listing(listing(row(path)))[0].path == path


def test_a_path_that_is_not_utf8_comes_back_escaped_so_nothing_can_be_lost_or_confused():
    data = b"100644 blob " + SHA1.encode() + b"      10\tcaf\xe9.txt\0"
    path = parse_listing(data)[0].path
    assert path == "caf\udce9.txt" and path.encode("utf-8", "surrogateescape") == b"caf\xe9.txt"


@pytest.mark.parametrize("data", [
    b"100644 blob " + SHA1.encode() + b"      10\tno-terminator.txt",
    b"100644 blob " + SHA1.encode() + b"      10 no-tab.txt\0",
    b"10064 blob " + SHA1.encode() + b"      10\ta.txt\0",
    b"100644 tree " + SHA1.encode() + b"      10\ta.txt\0",
    b"100644 blob " + b"zz" * 20 + b"      10\ta.txt\0",
    b"100644 blob " + b"ab" * 19 + b"      10\ta.txt\0",
    b"100644 blob " + SHA1.encode() + b"     ten\ta.txt\0",
    b"100644 blob " + SHA1.encode() + b"       -\ta.txt\0",
    b"160000 commit " + SHA1.encode() + b"      10\ta.txt\0",
    b"100644 blob " + SHA1.encode() + b"      10\t\0",
    b"\0"])
def test_a_row_that_is_not_the_shape_git_prints_is_a_git_failed_refusal(data):
    with pytest.raises(SeedRefusal) as refused:
        parse_listing(data)
    assert refused.value.reason == "git_failed"


def test_a_sha256_repository_is_listed_with_its_sixty_four_digit_ids():
    long = "ef" * 32
    assert parse_listing(listing(row("a", blob=long)))[0].oid == long


# --- what is copied, what is left out and why ---------------------------------------------------


def test_an_ordinary_file_is_copied_with_its_mode_and_its_size_is_counted():
    plan = planned(row("a.txt", size=7), row("bin/run", mode="100755", size=5))
    assert [(one.path, one.mode) for one in plan.copy] == [("a.txt", "100644"),
                                                           ("bin/run", "100755")]
    assert (plan.file_count, plan.total_bytes) == (2, 12)
    assert plan.skipped == () and plan.instructions_skipped == ()


@pytest.mark.parametrize("mode, reason", [("120000", "symlink"), ("160000", "submodule")])
def test_a_link_and_a_submodule_are_skipped_and_named(mode, reason):
    plan = planned(row("x", mode=mode), row("y.txt"))
    assert [(one.path, one.reason) for one in plan.skipped] == [("x", reason)]
    assert [one.path for one in plan.copy] == ["y.txt"]


@pytest.mark.parametrize("path", [
    "a:b.txt", "a*b", "a?b", 'a"b', "a<b", "a>b", "a|b", "a\\b", "a\x01b", "a\x7fb", "a\nb",
    "a\rb", "a\tb", "caf\udce9", "dir/a:b/c.txt", "ends.with.dot.", "ends with space ",
    "dir./file", "src/nul/x", "aux.txt", "COM1", "lpt9.log", "con", "a/./b", "a/../b",
    "a//b", "/abs", "trailing/"])
def test_a_path_a_windows_or_a_manifest_could_not_carry_is_skipped_as_unportable(path):
    plan = planned(row(path))
    assert [(one.path, one.reason) for one in plan.skipped] == [
        (seed_plan.shown(path), "unportable_name")] and plan.copy == ()


@pytest.mark.parametrize("path", ["a b.txt", "caf\u00e9.txt", "dir/ok.name", "console.txt",
                                  "aux2.txt", "a-b_c.d/e", ".hidden", "...x", "x.y.z"])
def test_a_path_with_nothing_wrong_is_copied(path):
    assert [one.path for one in planned(row(path)).copy] == [path]


def test_a_path_too_long_for_windows_is_skipped_and_the_same_path_is_fine_on_another_root():
    long = "d/" * 60 + "file.txt"
    short_root = PureWindowsPath("C:/p/work/_tasks/t/work-001")
    deep_root = PureWindowsPath("C:/" + "deep/" * 30 + "work/_tasks/t/work-001")
    assert planned(row(long), budget_roots=(short_root,)).skipped == ()
    skipped = planned(row(long), budget_roots=(deep_root,)).skipped
    assert [(one.path, one.reason) for one in skipped] == [(long, "path_budget")]
    assert planned(row(long)).skipped == (), "no budget root, no budget"


def test_the_budget_holds_against_every_root_it_is_given():
    path = "d/" * 50 + "f"
    near, far = PureWindowsPath("C:/a"), PureWindowsPath("C:/" + "x/" * 80)
    assert planned(row(path), budget_roots=(near,)).skipped == ()
    assert planned(row(path), budget_roots=(near, far)).skipped[0].reason == "path_budget"


@pytest.mark.parametrize("path", [
    "AGENTS.md", "CLAUDE.md", "docs/CLAUDE.md", "deep/er/AGENTS.md", "claude.md", "Agents.MD",
    ".claude/settings.json", ".codex/config", ".grok/x", ".kimi/y/z", "pkg/.claude/a",
    ".CLAUDE/a"])
def test_an_instruction_file_or_folder_is_left_out_and_named_apart_from_the_skips(path):
    plan = planned(row(path), row("keep.txt"))
    assert plan.instructions_skipped == (path,) and plan.skipped == ()
    assert [one.path for one in plan.copy] == ["keep.txt"]


@pytest.mark.parametrize("path", [".claude", "docs/.codex", "CLAUDE.md.bak", "my-AGENTS.md",
                                  ".claudes/x", "notes/claude.txt"])
def test_a_name_that_only_looks_like_an_instruction_name_is_copied(path):
    assert [one.path for one in planned(row(path)).copy] == [path]


def test_with_the_switch_on_the_instruction_files_are_copied_like_any_other():
    plan = planned(row("CLAUDE.md"), row(".claude/s.json"), include_agent_instructions=True)
    assert [one.path for one in plan.copy] == ["CLAUDE.md", ".claude/s.json"]
    assert plan.instructions_skipped == ()


@pytest.mark.parametrize("mode, path, reason", [
    ("120000", "CLAUDE.md", "symlink"), ("160000", ".claude/x", "submodule"),
    ("100644", ".claude/a:b", "unportable_name"), ("100644", "a:b/CLAUDE.md", "unportable_name")])
def test_the_first_rule_of_the_table_that_fits_names_the_row(mode, path, reason):
    plan = planned(row(path, mode=mode))
    assert [one.reason for one in plan.skipped] == [reason] and plan.instructions_skipped == ()


def test_skips_and_instruction_files_keep_the_order_of_the_listing_and_count_only_what_is_copied():
    plan = planned(row("b", mode="120000"), row("CLAUDE.md"), row("a:x"), row("ok", size=3),
                   row("c", mode="160000"), row(".codex/z", size=99))
    assert [one.path for one in plan.skipped] == ["b", "a:x", "c"]
    assert plan.instructions_skipped == ("CLAUDE.md", ".codex/z")
    assert (plan.file_count, plan.total_bytes) == (1, 3)


def test_a_path_is_shown_in_the_record_as_one_line_of_bounded_text():
    assert seed_plan.shown("a\nb\x00c\rd") == "a\\x0ab\\x00c\\x0dd"
    assert seed_plan.shown("caf\udce9") == "caf\\udce9"
    assert seed_plan.shown("plain/é.txt") == "plain/é.txt"
    assert len(seed_plan.shown("x" * 9000)) == 4096 and seed_plan.shown("x" * 9000).endswith("~")


# --- what the product will not seed at all ------------------------------------------------------

PRODUCT_NAMES = [name for name in PRODUCT_TOP_NAMES if "*" not in name]


@pytest.mark.parametrize("name", PRODUCT_NAMES)
def test_a_base_that_tracks_a_name_the_product_owns_is_refused(name):
    assert refusal_of(row("a.txt"), row(f"{name}/inside.txt")) == "tracks_product_dir"


def test_the_retired_folder_pattern_is_a_product_name_too():
    assert refusal_of(row(".conduct-retired-1a2b/x")) == "tracks_product_dir"


def test_a_tracked_product_name_is_refused_whatever_its_case_and_even_when_it_is_a_link():
    assert refusal_of(row("Work/x.txt")) == "tracks_product_dir"
    assert refusal_of(row("work", mode="120000")) == "tracks_product_dir"
    assert refusal_of(row("CONDUCTOR/a", mode="160000")) == "tracks_product_dir"


@pytest.mark.parametrize("path", ["workspace/x", "src/work/x", "my-work/x", "conductors/a",
                                  "instructions.md", "docs/instructions/a.md"])
def test_a_name_that_only_contains_a_product_name_or_sits_below_the_top_is_fine(path):
    assert [one.path for one in planned(row(path)).copy] == [path]


@pytest.mark.parametrize("paths", [("a/B", "A/b"), ("Foo", "foo/bar"), ("x/Y/z", "x/y/Z"),
                                   ("README", "readme")])
def test_paths_that_differ_only_in_case_are_refused_where_the_volume_folds_case(paths):
    rows = [row(path) for path in paths]
    assert refusal_of(*rows, case_insensitive=True) == "case_collision"
    assert [one.path for one in planned(*rows, case_insensitive=False).copy] == list(paths)


def test_a_path_left_out_cannot_collide_with_one_that_is_copied():
    plan = planned(row("Readme", mode="120000"), row("README"), case_insensitive=True)
    assert [one.path for one in plan.copy] == ["README"]
    plan = planned(row("CLAUDE.md"), row("claude.MD"), row("x"), case_insensitive=True)
    assert [one.path for one in plan.copy] == ["x"] and len(plan.instructions_skipped) == 2


def test_two_hundred_skips_are_recorded_and_the_two_hundred_and_first_refuses():
    links = [row(f"l{number}", mode="120000") for number in range(MAX_SKIPS)]
    assert len(planned(*links).skipped) == MAX_SKIPS
    assert refusal_of(*links, row("one-more", mode="120000")) == "too_many_skips"


def test_instruction_files_are_not_counted_against_the_two_hundred():
    files = [row(f".claude/f{number}") for number in range(MAX_SKIPS + 100)]
    assert len(planned(*files).instructions_skipped) == MAX_SKIPS + 100


def test_five_thousand_files_are_seeded_and_the_next_one_refuses():
    rows = [row(f"f{number}", size=1, blob=oid(number + 1)) for number in range(SEED_MAX_FILES)]
    assert planned(*rows).file_count == SEED_MAX_FILES
    assert refusal_of(*rows, row("extra", size=1)) == "seed_too_large"


def test_sixty_four_mebibytes_are_seeded_and_one_byte_more_refuses():
    each = SEED_MAX_BYTES // 8
    rows = [row(f"f{number}", size=each) for number in range(8)]
    assert planned(*rows).total_bytes == SEED_MAX_BYTES
    assert refusal_of(*rows, row("one", size=1)) == "seed_too_large"


def test_a_file_no_batch_could_carry_whole_refuses_and_one_that_fits_is_fine():
    biggest = BATCH_OUTPUT_CEILING - OBJECT_OVERHEAD
    assert planned(row("big", size=biggest)).file_count == 1
    assert refusal_of(row("big", size=biggest + 1)) == "seed_too_large"


def test_what_is_left_out_does_not_count_against_the_size():
    plan = planned(row("l", mode="120000", size=SEED_MAX_BYTES * 2), row("ok", size=1))
    assert plan.total_bytes == 1


def test_the_refusals_are_judged_in_one_fixed_order_and_every_reason_is_a_word_of_the_list():
    tracked, collision = row("work/x"), [row("a"), row("A")]
    links = [row(f"l{n}", mode="120000") for n in range(MAX_SKIPS + 1)]
    huge = row("huge", size=SEED_MAX_BYTES + 1)
    assert refusal_of(tracked, *collision, *links, huge, case_insensitive=True) == (
        "tracks_product_dir")
    assert refusal_of(*collision, *links, huge, case_insensitive=True) == "case_collision"
    assert refusal_of(*links, huge) == "too_many_skips"
    assert refusal_of(huge) == "seed_too_large"
    assert {"tracks_product_dir", "case_collision", "too_many_skips",
            "seed_too_large"} <= set(SEED_REASONS)


# --- the batches the bytes are asked for in -----------------------------------------------------


def test_an_empty_plan_asks_for_nothing_and_a_plan_with_files_asks_in_listing_order():
    assert blob_batches(planned()) == ()
    plan = planned(row("b", blob=oid(2), size=3), row("a", blob=oid(1), size=4))
    batch, = blob_batches(plan)
    assert [one.oid for one in batch.rows] == [oid(2), oid(1)]
    assert batch.stdin == (oid(2) + "\n" + oid(1) + "\n").encode("ascii")
    assert batch.output_limit == 3 + 4 + 2 * OBJECT_OVERHEAD


def test_an_object_two_paths_share_is_asked_for_once():
    plan = planned(row("a", blob=oid(1), size=3), row("b", blob=oid(1), size=3),
                   row("c", blob=oid(2), size=1))
    batch, = blob_batches(plan)
    assert [one.oid for one in batch.rows] == [oid(1), oid(2)]
    assert batch.output_limit == 4 + 2 * OBJECT_OVERHEAD


def test_no_batch_sends_more_than_the_runners_stdin_ceiling():
    rows = [row(f"f{number}", size=1, blob=oid(number + 1, 64)) for number in range(5000)]
    batches = blob_batches(planned(*rows))
    assert len(batches) == 2
    assert all(len(batch.stdin) <= 256 * 1024 and b"\0" not in batch.stdin for batch in batches)
    assert [one.oid for batch in batches for one in batch.rows] == [r.oid for r in rows]


def test_no_batch_expects_more_than_sixteen_mebibytes_and_keeps_the_order():
    six = 6 * 1024 * 1024
    rows = [row(f"f{number}", size=six, blob=oid(number + 1)) for number in range(3)]
    batches = blob_batches(planned(*rows))
    assert [len(batch.rows) for batch in batches] == [2, 1]
    assert all(batch.output_limit <= BATCH_OUTPUT_CEILING for batch in batches)


def test_a_batch_may_reach_the_ceiling_exactly_and_the_next_byte_starts_another():
    fits = BATCH_OUTPUT_CEILING - 2 * OBJECT_OVERHEAD
    exactly = [row("a", size=fits - 2, blob=oid(1)), row("b", size=2, blob=oid(2))]
    assert [len(batch.rows) for batch in blob_batches(planned(*exactly))] == [2]
    over = [row("a", size=fits - 1, blob=oid(1)), row("b", size=2, blob=oid(2))]
    assert [len(batch.rows) for batch in blob_batches(planned(*over))] == [1, 1]


# --- reading a batch back -----------------------------------------------------------------------


def answer(*items):
    return b"".join(f"{name} blob {len(data)}\n".encode() + data + b"\n" for name, data in items)


def batch_for(*items):
    rows = [row(f"f{n}", size=len(data), blob=name) for n, (name, data) in enumerate(items)]
    return blob_batches(planned(*rows))[0]


def test_a_batch_answer_is_read_into_the_bytes_of_each_object():
    items = [(oid(1), b"alpha\n"), (oid(2), b""), (oid(3), b"\x00\xff" + b"line\n" * 3)]
    assert parse_batch(answer(*items), batch_for(*items)) == dict(items)


def test_a_blob_that_looks_like_a_header_is_read_by_its_size_and_not_by_its_lines():
    trap = f"{oid(2)} blob 99\nx\n".encode()
    items = [(oid(1), trap), (oid(2), b"real")]
    assert parse_batch(answer(*items), batch_for(*items)) == dict(items)


@pytest.mark.parametrize("damage", [
    lambda whole: whole[:-3],
    lambda whole: whole[:10],
    lambda whole: b"",
    lambda whole: whole + b"extra",
    lambda whole: whole.replace(b" blob ", b" tree "),
    lambda whole: whole.replace(oid(1).encode(), oid(9).encode(), 1),
    lambda whole: whole.replace(b" blob 6", b" blob 7", 1),
    lambda whole: oid(1).encode() + b" missing\n",
    lambda whole: whole.replace(b"\n", b"\r\n", 1)])
def test_an_answer_that_is_cut_reordered_or_not_the_objects_asked_for_is_a_git_failed_refusal(
        damage):
    items = [(oid(1), b"alpha\n"), (oid(2), b"beta")]
    with pytest.raises(SeedRefusal) as refused:
        parse_batch(damage(answer(*items)), batch_for(*items))
    assert refused.value.reason == "git_failed"


# --- the pointer the seed warns about -----------------------------------------------------------

POINTER = (b"version https://git-lfs.github.com/spec/v1\n"
           b"oid sha256:" + b"a" * 64 + b"\nsize 12345\n")


def test_a_git_lfs_pointer_is_known_by_its_three_lines_and_its_small_size():
    assert is_lfs_pointer(POINTER)
    assert is_lfs_pointer(POINTER.replace(b"\n", b"\r\n")) is False


@pytest.mark.parametrize("blob", [
    b"", b"hello\n", POINTER[:-1] + b"x", POINTER.replace(b"sha256", b"md5"),
    POINTER.replace(b"size 12345", b"size twelve"), POINTER + b"x" * 2000,
    POINTER.replace(b"oid sha256:" + b"a" * 64 + b"\n", b""),
    b"oid sha256:" + b"a" * 64 + b"\nversion https://git-lfs.github.com/spec/v1\nsize 1\n"])
def test_a_file_that_is_not_exactly_a_pointer_is_not_called_one(blob):
    assert is_lfs_pointer(blob) is False
