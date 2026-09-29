"""Windows AppContainer: an entry that must survive inside a directory the child may write.

The case behind it is a vendor home the agent writes to that also holds a directory and
a file it must never be able to change or replace. The measured rule (see the lane
plan, F6 and F7): protection is the ABSENCE of an entry for the container on the
protected object (inheritance cut), and the parent is granted Modify, never full
control. Two tests are witnesses of OS behaviour rather than guarantees of ours; if a
newer Windows changes them, they say so, and the design is re-measured, not patched.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from tests.os_boundary_layout import Operation, Step

pytestmark = pytest.mark.skipif(
    os.name != "nt", reason="needs Windows: AppContainer is a Windows mechanism")

if os.name == "nt":
    from tests import os_boundary_windows as ac
    from tests.os_boundary_box import container, implement_box  # noqa: F401

INTACT = (True, [], True, 0, 1)


def _op(name: str, *steps: Step) -> Operation:
    return Operation(name, ("vendor",), tuple(steps), ())


def _ps(body: str) -> Step:
    return Step("ps", body)


PROTECTED_OPS = (
    _op("overwrite_the_protected_file",
        _ps("[IO.File]::WriteAllText('@VENDOR@\\hooks-paths','x')")),
    _op("delete_the_protected_file", _ps("[IO.File]::Delete('@VENDOR@\\hooks-paths')")),
    _op("rename_the_protected_file",
        _ps("[IO.File]::Move('@VENDOR@\\hooks-paths','@VENDOR@\\hp2')")),
    _op("replace_the_protected_file_by_copy",
        _ps("[IO.File]::WriteAllText('@TMPD@\\e.txt','evil'); "
            "[IO.File]::Copy('@TMPD@\\e.txt','@VENDOR@\\hooks-paths',$true)")),
    _op("hard_link_the_protected_file_and_write",
        Step("cmd", 'mklink /H "@TMPD@\\hl" "@VENDOR@\\hooks-paths"'),
        _ps("[IO.File]::AppendAllText('@TMPD@\\hl','pwn')")),
    _op("create_a_file_in_the_protected_directory",
        _ps("[IO.File]::WriteAllText('@VENDOR@\\hooks\\x','x')")),
    _op("delete_the_protected_directory", _ps("[IO.Directory]::Delete('@VENDOR@\\hooks')")),
    _op("rename_the_protected_directory",
        _ps("[IO.Directory]::Move('@VENDOR@\\hooks','@VENDOR@\\hooks2')")),
    _op("replace_the_protected_directory_via_the_parent",
        _ps("try { [IO.Directory]::Delete('@VENDOR@\\hooks') } catch {}; "
            "try { [void][IO.Directory]::CreateDirectory('@VENDOR@\\hooks') } catch {}; "
            "[IO.File]::WriteAllText('@VENDOR@\\hooks\\evil','x')")),
)
_CONTROL = "[IO.File]::WriteAllText('@VENDOR@\\control.txt','ok')"


def protected_state(vendor: Path) -> tuple:
    """(hooks is a real empty directory, its listing, paths is a plain file, its size, links)."""
    try:
        hooks, paths = os.lstat(vendor / "hooks"), os.lstat(vendor / "hooks-paths")
    except FileNotFoundError:
        return ("missing",)
    real_dir = stat.S_ISDIR(hooks.st_mode) and not getattr(hooks, "st_reparse_tag", 0)
    return (real_dir, sorted(os.listdir(vendor / "hooks")), stat.S_ISREG(paths.st_mode),
            paths.st_size, paths.st_nlink)


def _with_entries(box):
    """The vendor home gets an empty directory and an empty file, before any protection."""
    (box.layout.vendor_home / "hooks").mkdir()
    (box.layout.vendor_home / "hooks-paths").write_bytes(b"")
    return box


@pytest.fixture
def unprotected_box(implement_box):
    return _with_entries(implement_box)


@pytest.fixture
def protected_box(implement_box):
    """The two entries lose inheritance and every entry but the owner's: none for the container."""
    box = _with_entries(implement_box)
    for name in ("hooks", "hooks-paths"):
        ac.protect_entry(box.layout.vendor_home / name)
    return box


@pytest.mark.parametrize("operation", PROTECTED_OPS, ids=lambda op: op.name)
def test_a_protected_entry_inside_a_writable_directory_survives_every_change(
        protected_box, operation):
    box = protected_box
    results = box.run(operation, root="vendor")
    assert all(result.started for result in results), results
    assert protected_state(box.layout.vendor_home) == INTACT
    box.run_script(_CONTROL)
    assert (box.layout.vendor_home / "control.txt").read_bytes() == b"ok", "launch was not sound"


@pytest.mark.parametrize("operation", PROTECTED_OPS, ids=lambda op: op.name)
def test_the_same_operation_changes_the_entries_when_they_are_not_protected(
        unprotected_box, operation):
    box = unprotected_box
    box.run(operation, root="vendor")
    assert protected_state(box.layout.vendor_home) != INTACT, f"{operation.name} is not a probe"


def test_full_control_on_the_parent_directory_removes_the_protection_of_a_file_under_it(
        protected_box):
    box = protected_box
    vendor = box.layout.vendor_home
    ac.grant(vendor, box.container.sid, ac.FULL)
    box.run(PROTECTED_OPS[1], root="vendor")
    assert not (vendor / "hooks-paths").exists(), "FILE_DELETE_CHILD no longer overrides"


def test_a_deny_entry_for_the_container_is_ignored_while_an_allow_entry_also_applies(
        implement_box):
    box = implement_box
    target = box.layout.vendor_home / "denied.txt"
    target.write_bytes(b"before")
    ac.deny(target, box.container.sid, "F")
    box.run_script("[IO.File]::WriteAllText('@VENDOR@\\denied.txt','after')")
    assert target.read_bytes() == b"after", "a deny entry for the container is honoured now"


def test_a_name_that_is_absent_can_be_created_by_the_child_in_a_writable_directory(
        implement_box):
    box = implement_box
    vendor = box.layout.vendor_home
    assert not (vendor / "hooks").exists()
    box.run_script("[void][IO.Directory]::CreateDirectory('@VENDOR@\\hooks'); "
                   "[IO.File]::WriteAllText('@VENDOR@\\hooks\\evil','x')")
    assert (vendor / "hooks" / "evil").exists()
