"""Exact independently readable bytes are required before a Policy checker."""
import hashlib
from types import SimpleNamespace

import pytest

from conductor.command.contracts import ABSENT, ControlMode, _thaw_json
from conductor.command.adapters.result_manifest import (
    MaterialManifestError, build_result_manifest, check_result_manifest, marked_policy)
from conductor.command.adapters.harness_workspace import (
    FILE_BUDGET, HarnessWorkspace, WorkspaceNotContained)


def facts():
    request = SimpleNamespace(action_id="act-a", attempt_id="try-a")
    changed = ("_tasks/task/item/removed", "_tasks/task/item/result")
    contents = {changed[1]: b"actual full bytes\x00\xff"}
    tree = {path: hashlib.sha256(value).hexdigest() for path, value in contents.items()}
    return request, ("input-a", "input-a"), changed, tree, contents


def build(values=None, **overrides):
    values = facts() if values is None else values
    read = {"subtree": "_tasks/task/item/", "absent": (values[2][0],)}
    read.update(overrides)
    return build_result_manifest(*values, **read)


def test_full_binary_bytes_and_actual_absence_have_distinct_exact_rows():
    values = facts()
    result = _thaw_json(build(values))
    content = values[4][values[2][1]]
    assert result == {"action_id": "act-a", "attempt_id": "try-a",
        "input_artifact_ids": ["input-a", "input-a"], "files": [
            {"path": values[2][0], "state": "deleted", "length": 0, "sha256": None},
            {"path": values[2][1], "state": "present", "length": len(content),
             "sha256": "sha256:" + hashlib.sha256(content).hexdigest()}]}
    assert check_result_manifest(result, *values, subtree="_tasks/task/item/",
                                 absent=(values[2][0],)) == build(values)


@pytest.mark.parametrize("mutation", ["missing", "mismatch", "unsupported", "extra"])
def test_partial_oversize_or_foreign_content_cannot_be_hash_only_evidence(mutation):
    values = list(facts())
    name = values[2][1]
    if mutation == "missing":
        values[4].clear()
    elif mutation == "mismatch":
        values[4][name] = b"different bytes after the digest read"
    elif mutation == "unsupported":
        values[3][name] = "hard_link"
    else:
        values[4]["_tasks/task/item/not-changed"] = b"unrelated"
    with pytest.raises(MaterialManifestError):
        build(values)


@pytest.mark.parametrize("absence", [(), ("outside/victim",),
                                    ("_tasks/task/item/removed",) * 2])
def test_deleted_path_requires_one_actual_leaf_absence(absence):
    with pytest.raises(MaterialManifestError):
        build(absent=absence)


def test_a_file_cannot_be_both_present_and_deleted():
    values = facts()
    with pytest.raises(MaterialManifestError):
        build(values, absent=values[2])


def test_full_task_prefix_rejects_other_task_and_lookalike_prefix():
    for subtree in ("_tasks/other/item/", "_tasks/task/it/", "item/"):
        with pytest.raises(MaterialManifestError):
            build(subtree=subtree)


@pytest.mark.parametrize("field,value", [("action_id", "other-action"),
    ("attempt_id", "other-attempt"), ("input_artifact_ids", ["input-a"])])
def test_checker_rebuild_binds_subject_attempt_and_exact_ordered_inputs(field, value):
    manifest = _thaw_json(build())
    manifest[field] = value
    values = facts()
    with pytest.raises(MaterialManifestError):
        check_result_manifest(manifest, *values, subtree="_tasks/task/item/",
                              absent=(values[2][0],))


def test_secret_bytes_are_rejected_before_hex_or_json_encoding():
    values = facts()
    with pytest.raises(MaterialManifestError, match="frame_env_echo"):
        build(values, sensitive=(b"\x00\xff",))


@pytest.mark.parametrize("mode,grant,expected", [
    (ControlMode.CONFIRM, ABSENT, False), (ControlMode.POLICY, ABSENT, False),
    (ControlMode.POLICY, "grant-a", True)])
def test_manifest_road_is_only_the_marked_policy_revision(mode, grant, expected):
    assert marked_policy(SimpleNamespace(mode=mode, run_authorization_id=grant)) is expected


def test_actual_file_road_proves_deletion_and_all_present_bytes(tmp_path):
    workspace = HarnessWorkspace(tmp_path, "homes", "markers")
    work = workspace.work_dir("item", "task")
    (work / "present").write_bytes(b"\x00actual\xff")
    changed = ("_tasks/task/item/deleted", "_tasks/task/item/present")
    tree, contents, absent, subtree = workspace.read_result_tree("item", changed, work_scope="task")
    result = build_result_manifest(SimpleNamespace(action_id="a", attempt_id="b"), (),
                                  changed, tree, contents, absent=absent, subtree=subtree)
    assert result["files"][0]["state"] == "deleted"
    assert contents[changed[1]] == b"\x00actual\xff"
    assert result["files"][1]["length"] == 8


def test_actual_empty_directory_is_not_a_deleted_file(tmp_path):
    workspace = HarnessWorkspace(tmp_path, "homes", "markers")
    work = workspace.work_dir("item", "task")
    (work / "was-file").mkdir()
    changed = ("_tasks/task/item/was-file",)
    assert workspace.read_work_tree("item", changed, work_scope="task") == ({}, {})
    with pytest.raises(WorkspaceNotContained):
        workspace.read_result_tree("item", changed, work_scope="task")


def test_actual_over_limit_file_keeps_digest_but_cannot_build_a_manifest(tmp_path):
    workspace = HarnessWorkspace(tmp_path, "homes", "markers")
    work = workspace.work_dir("item", "task")
    (work / "large").write_bytes(b"a" * (FILE_BUDGET + 1))
    changed = ("_tasks/task/item/large",)
    tree, contents, absent, subtree = workspace.read_result_tree("item", changed, work_scope="task")
    assert tree == {changed[0]: hashlib.sha256(b"a" * (FILE_BUDGET + 1)).hexdigest()}
    assert contents == {} and absent == ()
    with pytest.raises(MaterialManifestError):
        build_result_manifest(SimpleNamespace(action_id="a", attempt_id="b"), (),
                              changed, tree, contents, absent=absent, subtree=subtree)


def test_only_a_regular_files_digest_reads_as_past_the_budget_not_a_link(tmp_path):
    """The over-budget word is for a hashed regular leaf; a hard link keeps its own code."""
    import os
    from conductor.command.adapters.artifact_transport import _is_hex_digest
    workspace = HarnessWorkspace(tmp_path, "homes", "markers")
    work = workspace.work_dir("item", "task")
    (work / "large").write_bytes(b"a" * (FILE_BUDGET + 1))
    (work / "small").write_bytes(b"b")
    os.link(work / "small", work / "linked")
    names = ("_tasks/task/item/large", "_tasks/task/item/linked", "_tasks/task/item/small")
    tree, contents = workspace.read_work_tree("item", names, work_scope="task")
    assert contents == {}
    assert [_is_hex_digest(tree[name]) for name in names] == [True, False, False]
