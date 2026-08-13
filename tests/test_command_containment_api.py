"""Public typed containment authority for API-1 and legacy command callers."""
from __future__ import annotations

import inspect
import os
import stat
import types
from pathlib import Path
from typing import get_args, get_origin, get_type_hints

import pytest

from conductor.command import containment
from conductor.command import preview
from conductor.command.containment import (
    RouteViolation,
    RouteViolationCode,
    assess_cwd_route,
    contained_directory,
    portal_violation,
    render_cwd_violation,
    render_route_violation,
    render_route_violations,
    run_route_violations,
)
from conductor.command.run_store import RunStore, snapshot_digest

from tests.test_command_run_store import CONFIG, a_run


def a_store(tmp_path: Path) -> RunStore:
    store = RunStore(tmp_path)
    store.create_run(a_run(config_digest=snapshot_digest(CONFIG)), CONFIG)
    return store


def test_api_relation_has_the_exact_public_typed_shape():
    returned = get_type_hints(run_route_violations)["return"]
    assert get_origin(returned) is tuple
    assert get_args(returned) == (RouteViolation, Ellipsis)
    assert set(RouteViolationCode) == {
        RouteViolationCode.SYMLINK,
        RouteViolationCode.JUNCTION,
        RouteViolationCode.REPARSE_POINT,
        RouteViolationCode.HARD_LINK,
        RouteViolationCode.IRREGULAR_FILE,
        RouteViolationCode.MISSING,
        RouteViolationCode.UNREADABLE,
        RouteViolationCode.NOT_DIRECTORY,
        RouteViolationCode.OUTSIDE_ROOT,
        RouteViolationCode.ROOT_NOT_DESCENDANT,
        RouteViolationCode.PARENT_TRAVERSAL,
    }
    assert "str(" not in inspect.getsource(run_route_violations)


@pytest.mark.parametrize("changes", [
    {"code": "not-a-route-code"},
    {"code": RouteViolationCode.REPARSE_POINT},
    {"code": RouteViolationCode.REPARSE_POINT, "reparse_tag": True},
    {"code": RouteViolationCode.HARD_LINK, "link_count": True},
    {"code": RouteViolationCode.HARD_LINK, "link_count": 1},
    {"code": RouteViolationCode.SYMLINK, "link_count": 2},
    {"code": RouteViolationCode.SYMLINK, "reparse_tag": 7},
    {"code": RouteViolationCode.OUTSIDE_ROOT},
    {"code": RouteViolationCode.SYMLINK, "project_root": Path("root")},
])
def test_typed_fact_rejects_untyped_or_code_incompatible_fields(changes):
    values = {"code": RouteViolationCode.SYMLINK, "path": Path("entry")}
    values.update(changes)
    with pytest.raises(ValueError):
        RouteViolation(**values)


@pytest.mark.parametrize("mode,tag,code,rendered", [
    (stat.S_IFLNK | 0o777, 0, RouteViolationCode.SYMLINK, "a symbolic link"),
    (stat.S_IFDIR | 0o755, containment.JUNCTION_TAG,
     RouteViolationCode.JUNCTION, "a directory junction"),
    (stat.S_IFREG | 0o644, 0x80000017,
     RouteViolationCode.REPARSE_POINT, "a reparse point (tag 0x80000017)"),
])
def test_one_portal_authority_drives_typed_relation_and_legacy_rendering(
        mode, tag, code, rendered):
    path = Path("component")
    found = types.SimpleNamespace(st_mode=mode, st_reparse_tag=tag)
    violation = portal_violation(path, found)
    assert violation is not None and violation.code is code
    assert rendered in render_route_violation(violation)
    assert containment.detected_portal(found) == rendered


def test_ordinary_stat_is_the_independent_no_violation_side():
    found = types.SimpleNamespace(st_mode=stat.S_IFREG | 0o644, st_reparse_tag=0)
    assert portal_violation(Path("ordinary"), found) is None
    assert containment.detected_portal(found) is None


def test_disabling_the_typed_detector_arm_disables_typed_and_legacy_refusal(
        tmp_path, monkeypatch):
    store = RunStore(tmp_path)
    run_path = store.run_path("preview-run")
    directories = {
        store.project_root / "conductor", store.runs_root,
        run_path, run_path / "decisions",
    }
    ordinary_dir = types.SimpleNamespace(
        st_mode=stat.S_IFDIR | 0o755, st_reparse_tag=0, st_nlink=1)
    tagged_file = types.SimpleNamespace(
        st_mode=stat.S_IFREG | 0o644, st_reparse_tag=0x80000017, st_nlink=1)

    def fake_lstat(path):
        if Path(path) in directories:
            return ordinary_dir
        if Path(path).name == "config.json":
            return tagged_file
        raise FileNotFoundError(path)

    monkeypatch.setattr(containment.os, "lstat", fake_lstat)
    with pytest.raises(preview.PreviewError, match="reparse point"):
        preview._check_route(store)
    monkeypatch.setattr(containment, "_portal_code", lambda observed: None)
    assert run_route_violations(store, "preview-run") == ()
    preview._check_route(store)


def test_run_relation_is_typed_and_legacy_renderer_preserves_exact_hardlink_fact(
        tmp_path):
    store = a_store(tmp_path)
    journal = store.run_path("run-001") / "records.jsonl"
    alias = tmp_path / "journal-alias"
    try:
        os.link(journal, alias)
    except OSError as error:
        pytest.skip(f"hard links unavailable: {error}")
    violations = run_route_violations(store, "run-001")
    assert violations == (RouteViolation(
        RouteViolationCode.HARD_LINK, journal, link_count=2),)
    assert render_route_violations(violations) == ((
        f"route: {str(journal)!r} carries 2 hard links: "
        "its bytes stand at another name as well"),)


def test_run_relation_types_irregular_owned_file_without_parsing_its_text(tmp_path):
    store = a_store(tmp_path)
    journal = store.run_path("run-001") / "records.jsonl"
    journal.unlink()
    journal.mkdir()
    violations = run_route_violations(store, "run-001")
    assert [(row.code, row.path) for row in violations] == [
        (RouteViolationCode.IRREGULAR_FILE, journal)]
    assert "not a regular file" in render_route_violation(violations[0])


@pytest.mark.parametrize("target", ["conductor", "runs", "decisions"])
def test_existing_non_directory_route_component_is_typed(tmp_path, target):
    store = RunStore(tmp_path)
    paths = {
        "conductor": store.project_root / "conductor",
        "runs": store.runs_root,
        "run": store.run_path("run-001"),
        "decisions": store.run_path("run-001") / "decisions",
    }
    path = paths[target]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not a directory")
    violations = run_route_violations(store, "run-001")
    assert violations == (RouteViolation(RouteViolationCode.NOT_DIRECTORY, path),)


def test_plain_file_at_final_run_name_defers_to_the_existing_store_refusal(tmp_path):
    store = RunStore(tmp_path)
    run_path = store.run_path("run-001")
    run_path.parent.mkdir(parents=True)
    run_path.write_bytes(b"claimed by an ordinary file")
    assert run_route_violations(store, "run-001") == ()
    assert "empty result is not run authorization" in run_route_violations.__doc__


@pytest.mark.parametrize("target", ["conductor", "runs", "run", "decisions", "owned"])
def test_unreadable_run_route_is_typed_and_never_treated_as_safe(
        tmp_path, monkeypatch, target):
    store = a_store(tmp_path)
    paths = {
        "conductor": store.project_root / "conductor",
        "runs": store.runs_root,
        "run": store.run_path("run-001"),
        "decisions": store.run_path("run-001") / "decisions",
        "owned": store.run_path("run-001") / "records.jsonl",
    }
    denied = paths[target]
    real_lstat = containment.os.lstat

    def refuse(path):
        if Path(path) == denied:
            raise PermissionError("untrusted OS prose")
        return real_lstat(path)

    monkeypatch.setattr(containment.os, "lstat", refuse)
    violations = run_route_violations(store, "run-001")
    assert violations == (RouteViolation(RouteViolationCode.UNREADABLE, denied),)
    assert "untrusted OS prose" not in repr(violations)


@pytest.mark.parametrize("raw,code,phrase", [
    ("work/missing", RouteViolationCode.MISSING, "does not exist or cannot be read"),
    (".", RouteViolationCode.ROOT_NOT_DESCENDANT, "not the root itself"),
    ("work/../../escape", RouteViolationCode.PARENT_TRAVERSAL, "through '..'"),
])
def test_cwd_assessment_is_typed_while_legacy_words_stay_stable(
        tmp_path, raw, code, phrase):
    root = tmp_path.resolve()
    (root / "work").mkdir()
    _, violation = assess_cwd_route(root, raw)
    assert violation is not None and violation.code is code
    assert phrase in render_cwd_violation(violation)


def test_cwd_unreadable_is_distinct_from_missing_but_intentionally_renders_the_same(
        tmp_path, monkeypatch):
    root = tmp_path.resolve()
    denied = root / "denied"
    real_lstat = containment.os.lstat

    def refuse(path):
        if Path(path) == denied:
            raise PermissionError("OS prose must not enter the typed fact")
        return real_lstat(path)

    monkeypatch.setattr(containment.os, "lstat", refuse)
    _, violation = assess_cwd_route(root, "denied")
    assert violation == RouteViolation(RouteViolationCode.UNREADABLE, denied)
    assert render_cwd_violation(violation) == (
        f"cwd route component {str(denied)!r} does not exist or cannot be read")


@pytest.mark.parametrize("leaf,make,expected", [
    ("missing", lambda path: None, "does not exist or cannot be read"),
    ("plain", lambda path: path.write_bytes(b"file"), "is not a directory"),
])
def test_contained_directory_wrapper_preserves_legacy_route_fact_bytes(
        tmp_path, leaf, make, expected):
    root = tmp_path.resolve()
    (root / "work").mkdir()
    target = root / "work" / leaf
    make(target)
    walked, fact = contained_directory(root, Path("work") / leaf)
    assert walked == target
    assert fact == f"route: {str(target)!r} {expected}"


def test_missing_run_remains_safe_for_create_and_is_not_a_typed_violation(tmp_path):
    store = RunStore(tmp_path)
    assert run_route_violations(store, "run-001") == ()
