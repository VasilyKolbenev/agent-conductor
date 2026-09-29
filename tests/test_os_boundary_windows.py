"""Windows AppContainer as the boundary of the one runner: source tree, Git store, work copy.

Everything runs on throwaway directories with a controlled child (PowerShell .NET
calls, ``cmd mklink``, ``icacls``): no vendor binary and no model call. The parent
judges by a digest snapshot of the tree, never by what the child prints. Every
denial has two controls. The same operation run UNCONFINED must change the tree (the
instrument can say no), and a write to the attempt's own tmp must succeed in a
launch built the same way (only the protected write was refused, the launch worked).

What this proves is the OS policy on Windows 11; it does not prove that any vendor
binary starts, or runs correctly, inside the container.
"""
from __future__ import annotations

import os

import pytest

from tests.os_boundary_layout import Operation, operations_for

pytestmark = pytest.mark.skipif(
    os.name != "nt", reason="needs Windows: AppContainer is a Windows mechanism")

if os.name == "nt":
    from tests import os_boundary_windows as ac
    from tests.os_boundary_box import container, implement_box, review_box  # noqa: F401

SOURCE_OPS = operations_for("source")
WORK_OPS = operations_for("work")


def _ids(operation: Operation) -> str:
    return operation.name


def test_a_launch_with_the_container_attribute_gives_the_child_an_appcontainer_token(
        implement_box):
    box = implement_box
    confined = box.spawn_suspended([str(ac.CMD), "/d", "/c", "exit 0"], confined=True)
    plain = box.spawn_suspended([str(ac.CMD), "/d", "/c", "exit 0"], confined=False)
    try:
        assert ac.confinement_of(confined.handle) == box.container.sid
        assert ac.confinement_of(plain.handle) is None
    finally:
        confined.discard()
        plain.discard()


def test_a_process_started_by_popen_with_a_security_capabilities_entry_is_not_confined(
        implement_box):
    """Popen keeps only a handle list: the entry is ignored and the child runs unconfined."""
    proc = ac.popen_with_ignored_security_capabilities(implement_box.container.sid)
    try:
        assert ac.confinement_of(int(proc._handle)) is None
    finally:
        proc.kill()
        proc.wait()


@pytest.mark.parametrize("operation", SOURCE_OPS, ids=_ids)
def test_a_confined_child_cannot_change_the_source_tree_or_its_git_metadata(
        implement_box, operation):
    box = implement_box
    before = box.snapshot("source")
    results = box.run(operation, root="source")
    assert all(result.started for result in results), results
    assert box.snapshot("source") == before
    assert box.control_write(), "the launch built the same way could not write to its own tmp"


@pytest.mark.parametrize("operation", SOURCE_OPS, ids=_ids)
def test_the_same_operation_run_unconfined_changes_the_source_tree(implement_box, operation):
    box = implement_box
    before = box.snapshot("source")
    box.run(operation, root="source", confined=False)
    assert box.snapshot("source") != before, f"{operation.name} is not a probe"


_INNER = (
    "[IO.File]::WriteAllText('@TMPD@\\inner_ran.txt','ran'); "
    "try { [IO.File]::WriteAllText('@SRC@\\file.txt','x') } catch {}; "
    "try { [IO.File]::Delete('@SRC@\\.git\\HEAD') } catch {}; "
    "try { [IO.Directory]::Delete('@SRC@\\.git',$true) } catch {}; "
    "try { [IO.Directory]::Move('@SRC@','@SRC@-moved') } catch {}"
)


@pytest.mark.parametrize("confined", [True, False], ids=["confined", "unconfined-control"])
def test_the_process_a_confined_child_starts_is_confined_like_its_parent(
        implement_box, confined):
    box = implement_box
    before = box.snapshot("source")
    box.write_inner_script(_INNER)
    box.run_nested(confined=confined)
    if confined:
        assert (box.layout.tmp / "inner_ran.txt").exists(), "the descendant never ran"
        assert box.snapshot("source") == before
    else:
        assert box.snapshot("source") != before, "the nested script is not a probe"


@pytest.mark.parametrize("operation", WORK_OPS, ids=_ids)
def test_a_review_confined_child_cannot_change_the_work_copy(review_box, operation):
    box = review_box
    before = box.snapshot("work")
    results = box.run(operation, root="work")
    assert all(result.started for result in results), results
    assert box.snapshot("work") == before
    assert box.control_write()


@pytest.mark.parametrize("operation", WORK_OPS, ids=_ids)
def test_the_same_operation_run_unconfined_changes_the_work_copy(review_box, operation):
    box = review_box
    before = box.snapshot("work")
    box.run(operation, root="work", confined=False)
    assert box.snapshot("work") != before, f"{operation.name} is not a probe"


def test_a_review_confined_child_reads_the_work_copy_and_not_the_source_tree(review_box):
    box = review_box
    read_work = box.run_script("[Console]::Out.Write([IO.File]::ReadAllText('@WORK@\\file.txt'))")
    read_source = box.run_script("[Console]::Out.Write([IO.File]::ReadAllText('@SRC@\\file.txt'))")
    assert read_work.output == "original source\n"
    assert read_source.exit_code != 0 and "original source" not in read_source.output


def test_a_work_copy_granted_for_writing_changes_while_the_source_stays_untouched(
        implement_box):
    box = implement_box
    overwrite = next(op for op in operations_for("work") if op.name == "overwrite_file")
    before_source, before_work = box.snapshot("source"), box.snapshot("work")
    box.run(overwrite, root="work")
    box.run(overwrite, root="source")
    assert box.snapshot("work") != before_work, "the grant on the work copy did nothing"
    assert box.snapshot("source") == before_source


def test_allowed_tmp_and_home_take_file_and_directory_writes_under_confinement(implement_box):
    box = implement_box
    script = (
        "$t='@TMPD@'; $h='@HOMED@'; "
        "foreach ($d in @($t,$h)) { "
        "[IO.File]::WriteAllText($d+'\\a.txt','1'); [IO.File]::AppendAllText($d+'\\a.txt','2'); "
        "[IO.File]::Move($d+'\\a.txt',$d+'\\b.txt'); "
        "[void][IO.Directory]::CreateDirectory($d+'\\sub'); "
        "[IO.File]::WriteAllText($d+'\\sub\\c.txt','3'); [IO.File]::Delete($d+'\\sub\\c.txt'); "
        "[IO.Directory]::Delete($d+'\\sub'); [IO.File]::WriteAllText($d+'\\keep.txt','k') }"
    )
    outcome = box.run_script(script)
    assert outcome.started and outcome.exit_code == 0, outcome.output
    for directory in (box.layout.tmp, box.layout.home):
        assert (directory / "b.txt").read_bytes() == b"12"
        assert (directory / "keep.txt").read_bytes() == b"k"
        assert not (directory / "sub").exists() and not (directory / "a.txt").exists()


def test_a_native_rename_over_an_existing_file_works_in_the_granted_home(implement_box):
    box = implement_box
    (box.layout.home / "auth.json").write_bytes(b"old")
    (box.layout.home / "new.tmp").write_bytes(b"NEW")
    outcome = box.run_native_move_replace("@HOMED@\\new.tmp", "@HOMED@\\auth.json")
    assert outcome.started and outcome.output.strip() == "ok=True", outcome.output
    assert (box.layout.home / "auth.json").read_bytes() == b"NEW"


def test_the_verifier_rejects_a_process_that_is_not_an_appcontainer_process(implement_box):
    box = implement_box
    plain = box.spawn_suspended([str(ac.CMD), "/d", "/c", "exit 0"], confined=False)
    try:
        with pytest.raises(ac.PolicyNotApplied):
            ac.require_confinement(plain.handle, box.container.sid)
    finally:
        plain.discard()
