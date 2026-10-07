"""Canonical whole-object result facts, independently spelled expected digests."""
from copy import deepcopy
import hashlib
import json

import pytest

from conductor.command.contract_values import ContractError, _thaw_json
from conductor.command.result_manifest import manifest_digest, rebuild_manifest


def manifest():
    return {"action_id": "action-do", "attempt_id": "attempt-1",
        "input_artifact_ids": ["artifact-instruction", "artifact-input", "artifact-instruction"],
        "files": [{"path": "task/empty.txt", "state": "present", "length": 0,
                   "sha256": "sha256:" + hashlib.sha256(b"").hexdigest()},
                  {"path": "task/removed.txt", "state": "deleted", "length": 0, "sha256": None},
                  {"path": "task/результат.txt", "state": "present", "length": 5,
                   "sha256": "sha256:" + hashlib.sha256("да!".encode("utf-8")).hexdigest()}]}


def test_whole_manifest_digest_preserves_ordered_inputs_duplicates_and_unicode():
    source = manifest()
    encoded = json.dumps(source, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    expected = "sha256:" + hashlib.sha256(encoded).hexdigest()
    rebuilt = rebuild_manifest(source)
    assert _thaw_json(rebuilt) == source
    assert rebuilt["input_artifact_ids"] == ("artifact-instruction", "artifact-input", "artifact-instruction")
    assert manifest_digest(rebuilt) == expected
    source["input_artifact_ids"] = ["artifact-input", "artifact-instruction", "artifact-instruction"]
    assert manifest_digest(source) != expected


def test_rebuild_detaches_and_freezes_every_nested_value():
    source = manifest()
    original = deepcopy(source)
    frozen = rebuild_manifest(source)
    source["files"][0]["length"] = 100
    source["input_artifact_ids"].clear()
    assert _thaw_json(frozen) == original
    with pytest.raises(TypeError):
        frozen["files"][0]["length"] = 100
    with pytest.raises(TypeError):
        frozen["action_id"] = "other"


def test_empty_present_file_and_deleted_file_are_distinct_result_facts():
    source = manifest()
    value = rebuild_manifest(source)
    assert value["files"][0]["length"] == value["files"][1]["length"] == 0
    assert value["files"][0]["sha256"] is not None
    assert value["files"][1]["sha256"] is None
    changed = deepcopy(source)
    changed["files"][0].update(state="deleted", sha256=None)
    assert manifest_digest(changed) != manifest_digest(source)


@pytest.mark.parametrize("path", ["", ".", "..", "/abs", "a//b", "a/./b", "a/../b", "a/",
    "C:/file", "a:b", "a\\b", "a\x00b", "a\x1fb", "a\x7fb", "a\x9fb", "a\ud800b"])
def test_manifest_never_normalizes_an_ambiguous_or_unencodable_path(path):
    source = manifest()
    source["files"] = [dict(source["files"][0], path=path)]
    with pytest.raises(ContractError):
        rebuild_manifest(source)


@pytest.mark.parametrize("length", [True, False, -1, 1.0, float("nan"), float("inf"), "1", None])
def test_present_length_is_an_exact_nonnegative_integer(length):
    source = manifest()
    source["files"][0]["length"] = length
    with pytest.raises(ContractError):
        rebuild_manifest(source)


@pytest.mark.parametrize("change", [
    {"state": "missing"}, {"state": "deleted", "length": 1, "sha256": None},
    {"state": "deleted"}, {"sha256": None}, {"sha256": "a" * 64},
    {"sha256": "sha256:" + "A" * 64}, {"decision": "accept"},
])
def test_file_state_digest_and_closed_shape_cannot_be_reinterpreted(change):
    source = manifest()
    source["files"][0].update(change)
    with pytest.raises(ContractError):
        rebuild_manifest(source)


@pytest.mark.parametrize("kind", ["unknown", "missing", "duplicate", "reversed", "id", "inputs", "files"])
def test_closed_outer_shape_identity_and_file_set(kind):
    source = manifest()
    if kind == "unknown":
        source["grant"] = "approved"
    elif kind == "missing":
        del source["attempt_id"]
    elif kind == "duplicate":
        source["files"].insert(0, source["files"][0])
    elif kind == "reversed":
        source["files"].reverse()
    elif kind == "id":
        source["action_id"] = "../other"
    elif kind == "inputs":
        source["input_artifact_ids"] = "artifact-input"
    else:
        source["files"] = {"task/file": "digest"}
    with pytest.raises(ContractError):
        rebuild_manifest(source)


@pytest.mark.parametrize("field,value", [("action_id", "action-other"), ("attempt_id", "attempt-other")])
def test_digest_binds_the_execution_subject_even_with_identical_result_files(field, value):
    source = manifest()
    changed = deepcopy(source)
    changed[field] = value
    assert manifest_digest(changed) != manifest_digest(source)
