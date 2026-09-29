"""Seatbelt as the boundary of the one runner, run natively on macOS only.

Written without a macOS host to run it on: the macOS CI ``tests`` job is what executes it,
and a red result there is a finding about the mechanism, not a regression. Every denial
has two controls: the same operation run WITHOUT the sandbox changes the tree (that half
is ``test_os_boundary_layout``, which runs on every POSIX host), and a write to the
attempt's own tmp works in a launch built the same way. The judge is a digest snapshot the
parent takes, never what the child prints. The profile text is unit-tested separately.

Two cases are the ones most likely to fail and are named so a red run is read correctly:
the hard link from a protected file (Seatbelt matches paths, so a second name for the same
file may be writable) and the profile that denies ``file-link``.
"""
from __future__ import annotations

import os
import stat
import subprocess
import sys

import pytest

from tests import os_boundary_darwin as sb
from tests.os_boundary_layout import Operation, Step, operations_for
from tests.os_boundary_seatbelt_box import (  # noqa: F401
    absent_box, implement_box, linked_box, protected_box, review_box, unprotected_box)

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin", reason="needs macOS: Seatbelt (sandbox-exec) is a macOS mechanism")

SOURCE_OPS = operations_for("source")
WORK_OPS = operations_for("work")
INTACT = (True, [], True, 0, 1)


def _ids(operation: Operation) -> str:
    return operation.name


def test_sandbox_exec_applies_a_profile_and_the_sandboxed_shell_reports_it(implement_box):
    outcome = implement_box.run_body("echo inside")
    assert outcome.applied and outcome.exit_code == 0 and "inside" in outcome.output


@pytest.mark.parametrize("operation", SOURCE_OPS, ids=_ids)
def test_a_sandboxed_child_cannot_change_the_source_tree_or_its_git_metadata(
        implement_box, operation):
    box = implement_box
    before = box.snapshot("source")
    results = box.run(operation, root="source")
    assert all(result.applied for result in results), results
    assert box.snapshot("source") == before
    assert box.control_write(), "the launch built the same way could not write to its own tmp"


_INNER = (
    'printf x > "@TMPD@/inner_ran"; printf x > "@SRC@/file.txt"; rm -f "@SRC@/.git/HEAD"; '
    'rm -rf "@SRC@/.git"; mv "@SRC@" "@SRC@-moved"'
)


def test_the_process_a_sandboxed_child_starts_is_sandboxed_like_its_parent(implement_box):
    box = implement_box
    before = box.snapshot("source")
    box.write_inner_script(_INNER)
    box.run_body('/bin/sh "@TMPD@/inner.sh"')
    assert (box.layout.tmp / "inner_ran").exists(), "the descendant never ran"
    assert box.snapshot("source") == before


@pytest.mark.parametrize("operation", WORK_OPS, ids=_ids)
def test_a_review_profile_child_cannot_change_the_work_copy(review_box, operation):
    box = review_box
    before = box.snapshot("work")
    results = box.run(operation, root="work")
    assert all(result.applied for result in results), results
    assert box.snapshot("work") == before
    assert box.control_write()


def test_a_review_profile_child_can_read_the_work_copy(review_box):
    outcome = review_box.run_body('cat "@WORK@/file.txt"')
    assert outcome.applied and "original source" in outcome.output


def test_an_implement_profile_child_changes_the_work_copy_and_still_not_the_source(
        implement_box):
    box = implement_box
    overwrite = next(op for op in operations_for("work") if op.name == "overwrite_file")
    before_source, before_work = box.snapshot("source"), box.snapshot("work")
    box.run(overwrite, root="work")
    box.run(overwrite, root="source")
    assert box.snapshot("work") != before_work, "the allow for the work copy did nothing"
    assert box.snapshot("source") == before_source


def test_allowed_tmp_and_home_take_file_and_directory_writes_under_the_sandbox(implement_box):
    box = implement_box
    body = "; ".join(
        f'printf 1 > "{d}/a"; printf 2 >> "{d}/a"; mv "{d}/a" "{d}/b"; mkdir "{d}/s"; '
        f'printf 3 > "{d}/s/c"; rm "{d}/s/c"; rmdir "{d}/s"; printf k > "{d}/keep"'
        for d in ("@TMPD@", "@HOMED@"))
    outcome = box.run_body(body)
    assert outcome.applied and outcome.exit_code == 0, outcome.output
    for directory in (box.layout.tmp, box.layout.home):
        assert (directory / "b").read_bytes() == b"12" and (directory / "keep").read_bytes() == b"k"
        assert not (directory / "s").exists() and not (directory / "a").exists()


def test_a_dedicated_vendor_home_takes_a_credential_update_in_place_and_by_rename(
        implement_box):
    box = implement_box
    vendor = box.layout.vendor_home
    before = os.stat(vendor / "auth.json")
    box.run_body('printf "token=updated" > "@VENDOR@/auth.json"')
    assert (vendor / "auth.json").read_bytes() == b"token=updated"
    assert os.stat(vendor / "auth.json").st_ino == before.st_ino, "a different file now stands"
    box.run_body('printf NEW > "@VENDOR@/new.tmp" && mv "@VENDOR@/new.tmp" "@VENDOR@/auth.json"')
    assert (vendor / "auth.json").read_bytes() == b"NEW"


def _sh(body: str) -> Step:
    return Step("sh", body)


PROTECTED_OPS = (
    Operation("overwrite_the_protected_file", ("vendor",),
              (), (_sh('printf x > "@VENDOR@/hooks-paths"'),)),
    Operation("delete_the_protected_file", ("vendor",),
              (), (_sh('rm -f "@VENDOR@/hooks-paths"'),)),
    Operation("rename_the_protected_file", ("vendor",),
              (), (_sh('mv "@VENDOR@/hooks-paths" "@VENDOR@/hp2"'),)),
    Operation("replace_the_protected_file_by_copy", ("vendor",), (),
              (_sh('printf evil > "@TMPD@/e" && cp "@TMPD@/e" "@VENDOR@/hooks-paths"'),)),
    Operation("hard_link_the_protected_file_and_write", ("vendor",), (),
              (_sh('ln "@VENDOR@/hooks-paths" "@TMPD@/hl"'),
               _sh('printf pwn >> "@TMPD@/hl"'))),
    Operation("create_a_file_in_the_protected_directory", ("vendor",),
              (), (_sh('printf x > "@VENDOR@/hooks/x"'),)),
    Operation("delete_the_protected_directory", ("vendor",),
              (), (_sh('rmdir "@VENDOR@/hooks"'),)),
    Operation("rename_the_protected_directory", ("vendor",),
              (), (_sh('mv "@VENDOR@/hooks" "@VENDOR@/hooks2"'),)),
    Operation("replace_the_protected_directory_via_the_parent", ("vendor",), (),
              (_sh('rmdir "@VENDOR@/hooks"; mkdir "@VENDOR@/hooks" 2>/dev/null; '
                   'printf x > "@VENDOR@/hooks/evil"'),)),
    Operation("rename_the_directory_that_holds_the_protected_entries", ("vendor",),
              (), (_sh('mv "@VENDOR@" "@VENDOR@-moved"'),)),
)


def protected_state(vendor) -> tuple:
    """(hooks is a real empty directory, its listing, paths is a plain file, size, links)."""
    try:
        hooks, paths = os.lstat(vendor / "hooks"), os.lstat(vendor / "hooks-paths")
    except FileNotFoundError:
        return ("missing",)
    return (stat.S_ISDIR(hooks.st_mode), sorted(os.listdir(vendor / "hooks")),
            stat.S_ISREG(paths.st_mode), paths.st_size, paths.st_nlink)


@pytest.mark.parametrize("operation", PROTECTED_OPS, ids=_ids)
def test_a_protected_entry_inside_a_writable_directory_survives_the_attempted_change(
        protected_box, operation):
    box = protected_box
    results = box.run(operation, root="vendor")
    assert all(result.applied for result in results), results
    assert protected_state(box.layout.vendor_home) == INTACT
    box.run_body('printf ok > "@VENDOR@/control.txt"')
    assert (box.layout.vendor_home / "control.txt").read_bytes() == b"ok", "launch was not sound"


@pytest.mark.parametrize("operation", PROTECTED_OPS, ids=_ids)
def test_the_same_operation_changes_the_entries_when_the_profile_does_not_protect_them(
        unprotected_box, operation):
    box = unprotected_box
    box.run(operation, root="vendor")
    assert protected_state(box.layout.vendor_home) != INTACT, f"{operation.name} is not a probe"


def test_a_name_that_is_absent_stays_uncreatable_where_the_profile_denies_it(
        absent_box, unprotected_box):
    guarded, open_box = absent_box, unprotected_box
    guarded_vendor = guarded.layout.vendor_home
    assert guarded_vendor != open_box.layout.vendor_home, "the two boxes share one vendor home"
    for name in ("hooks", "hooks-paths"):
        assert not (guarded_vendor / name).exists(), f"{name} stands before the attempt"
    control = open_box.run_body('rmdir "@VENDOR@/hooks"; mkdir "@VENDOR@/hooks"; '
                                'printf x > "@VENDOR@/hooks/e"')
    assert control.applied, control
    assert (open_box.layout.vendor_home / "hooks" / "e").exists(), "the control cannot create it"
    attempt = guarded.run_body('mkdir "@VENDOR@/hooks"; printf x > "@VENDOR@/hooks-paths"; '
                               'printf ok > "@VENDOR@/control.txt"')
    assert attempt.applied, attempt
    assert not (guarded_vendor / "hooks").exists()
    assert not (guarded_vendor / "hooks-paths").exists()
    assert (guarded_vendor / "control.txt").read_bytes() == b"ok", "launch was not sound"


def test_the_vendor_home_is_updated_while_the_source_tree_is_unreadable(implement_box):
    blind = implement_box.variant(unreadable=[implement_box.layout.source])
    reading = blind.run_body(
        'cat "@SRC@/file.txt" >/dev/null 2>&1 && echo readable || echo unreadable')
    assert "unreadable" in reading.output, reading
    blind.run_body('printf "token=updated" > "@VENDOR@/auth.json"')
    assert (blind.layout.vendor_home / "auth.json").read_bytes() == b"token=updated"


def test_a_profile_that_denies_hard_links_from_the_source_refuses_the_link_and_still_runs(
        linked_box):
    """Most likely to be red: a macOS that rejects a `file-link` rule is itself the finding."""
    box = linked_box
    hard_link = next(op for op in SOURCE_OPS if op.name == "hard_link_then_write_through")
    before = box.snapshot("source")
    results = box.run(hard_link, root="source")
    assert all(result.applied for result in results), results
    assert box.snapshot("source") == before
    assert box.control_write()


def test_a_profile_that_does_not_compile_is_refused_and_the_target_never_runs(tmp_path):
    marker = tmp_path / "ran"
    script = f'echo {sb.APPLIED}; touch "{marker}"'
    bad = "(version 1)\n(allow default)\n(this-is-not-a-rule)\n"
    done = subprocess.run(sb.sandbox_argv(bad, ["/bin/sh", "-c", script]),
                          capture_output=True, timeout=60, check=False)
    output = (done.stdout + done.stderr).decode("utf-8", errors="replace")
    assert done.returncode != 0
    with pytest.raises(sb.PolicyNotApplied):
        sb.require_applied(output)
    assert not marker.exists(), "the target ran although the profile was never applied"
