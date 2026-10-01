"""Explicit setup steps and first-commit previews through the real command boundary."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from conductor.command import git_setup
from conductor.command.accept_manifest import blob_oid, sha256
from conductor.command.adapters import AdapterRegistry
from conductor.command.api_refusals import ApiRefusal, GIT_SETUP_REASONS
from conductor.command.http_api import CommandApi, PRODUCT_COMMAND_BUDGET
from conductor.command.http_transport import CommandSession
from conductor.command.product_names import BLOCK_BEGIN, BLOCK_END
from conductor.command.project_claim import ProjectIdentity
from conductor.command.project_git import GitAnswer
from conductor.command.run_store import RunStore, StoreError
from conductor.command.seed_record import SeedRecord, write_seed
from conductor.ownership import data_root
from tests.git_repo_helpers import commit, git, needs_git, real_reader, repository, snapshot
from tests.test_command_adapters import FakeAdapter
from tests.test_command_http_api import NOW, PORT, TOKEN, ids
from tests.test_command_materials_routes import NoGit, PROJECT_ID, TASK
from tests.test_command_project_doors import request
from tests.test_seed_record import an_empty_seed
from tests.test_seed_routes import Folder

PATH = "/command/project/git/setup"


class Trace:
    def __init__(self, read, *config):
        self.read, self.config, self.calls = read, config, []

    def __call__(self, args, *positional, **keywords):
        self.calls.append((tuple(args), dict(keywords)))
        return self.read([*self.config, *args], *positional, **keywords)


def step(project, name="init", **changes):
    return request(project, "POST", PATH, dict(step=name, actor="Owner", **changes))


def preview(project, mode="snapshot"):
    return request(project, "POST", PATH, dict(step="first_commit", mode=mode, preview=True))


def reason(answer):
    assert answer.status == 409, answer.payload
    return answer.payload["error"]["detail"]["reason"]


def unborn(tmp_path):
    project = Folder(tmp_path)
    assert step(project).status == 201
    git("config", "user.name", "Setup Author", cwd=project.root)
    git("config", "user.email", "setup@example.invalid", cwd=project.root)
    git("config", "core.autocrlf", "false", cwd=project.root)
    return project


@pytest.mark.parametrize("body", [{"step": "init", "actor": "Owner"},
    {"step": "exclude", "actor": "Owner"}, {"step": "first_commit", "mode": "empty", "preview": True}])
def test_view_refuses_every_setup_shape_without_git_or_writes(tmp_path, body):
    project = Folder(tmp_path, mode="view", reader=NoGit())
    before = snapshot(project.root)
    answer = request(project, "POST", PATH, body)
    assert answer.status == 409 and answer.payload["error"]["code"] == "project_not_active"
    assert project.reader.asked == 0 and snapshot(project.root) == before


@needs_git
def test_init_preserves_default_branch_adds_exclude_and_exact_retry_never_spawns(tmp_path):
    reader = Trace(real_reader(tmp_path), "-c", "init.defaultBranch=owner-choice", "-c", "commit.gpgSign=true",
                   "-c", "user.useConfigOnly=true")
    project = Folder(tmp_path, reader=reader)
    first = step(project)
    assert first.status == 201, first.payload
    assert first.payload["setup"]["step"] == "init" and first.payload["setup"]["exclude"] == "written"
    assert git("symbolic-ref", "HEAD", cwd=project.root).stdout.strip() == b"refs/heads/owner-choice"
    exclude = (project.root / ".git/info/exclude").read_text(encoding="utf-8")
    assert BLOCK_BEGIN in exclude and BLOCK_END in exclude
    assert not any("var" in args or "-b" in args for args, _ in reader.calls)
    before, calls = snapshot(project.root / ".git"), len(reader.calls)
    assert step(project).status == 200 and step(project).payload == first.payload
    assert len(reader.calls) == calls and snapshot(project.root / ".git") == before
    answer = request(project, "POST", PATH, {"step": "init", "actor": "Other"})
    assert reason(answer) == "setup_terms_changed"


@needs_git
def test_empty_seed_forces_sha1_without_overriding_the_default_branch(tmp_path):
    reader = Trace(real_reader(tmp_path), "-c", "init.defaultObjectFormat=sha256", "-c", "init.defaultBranch=mine")
    project = Folder(tmp_path, reader=reader)
    write_seed(project.root, SeedRecord.from_dict(an_empty_seed(task_id=TASK, work_scope=TASK)))
    answer = step(project)
    assert answer.status == 201 and answer.payload["setup"]["object_format"] == "sha1", answer.payload
    assert any("--object-format=sha1" in args for args, _ in reader.calls)
    assert git("symbolic-ref", "HEAD", cwd=project.root).stdout.strip() == b"refs/heads/mine"


@needs_git
def test_init_inside_another_repository_leaves_its_head_and_index_alone(tmp_path):
    parent = repository(tmp_path)
    commit(parent, {"owned.txt": "owner\n"})
    before = snapshot(parent / ".git")
    project = Folder(parent, name="nested")
    answer = step(project)
    assert answer.status == 201 and answer.payload["setup"]["warnings"] == ["nested_repository"]
    assert snapshot(parent / ".git") == before
    assert Path(git("rev-parse", "--show-toplevel", cwd=project.root).stdout.decode().strip()).resolve() == project.root


@needs_git
def test_crash_after_init_cannot_adopt_a_git_entry_without_its_receipt(tmp_path, monkeypatch):
    project = Folder(tmp_path)
    monkeypatch.setattr(git_setup, "publish", lambda *_a: (_ for _ in ()).throw(StoreError("crash")))
    assert step(project).status == 500
    before = snapshot(project.root / ".git")
    project.api._project_git = NoGit()
    assert reason(step(project)) == "already_git"
    assert snapshot(project.root / ".git") == before
    assert not (data_root(project.root) / "git/setup/init.json").exists()


def test_foreign_git_entry_and_missing_live_owner_refuse_before_any_git(tmp_path):
    project = Folder(tmp_path, reader=NoGit())
    (project.root / ".git").mkdir()
    assert reason(step(project)) == "already_git"
    (project.root / ".conduct").mkdir()
    answer = step(project)
    assert answer.status == 409 and answer.payload["error"]["code"] == "project_not_active"
    assert project.reader.asked == 0
    assert not (project.root / ".git/HEAD").exists()


@needs_git
def test_deferred_exclude_writes_the_actual_linked_worktrees_common_dir(tmp_path):
    main = repository(tmp_path)
    commit(main, {"owner.txt": "keep\n"})
    linked = tmp_path / "linked"
    git("worktree", "add", "--detach", str(linked), "HEAD", cwd=main)
    owner_lines = (main / ".git/info/exclude").read_bytes()
    reader = Trace(real_reader(tmp_path))
    subject = CommandApi(RunStore(linked), AdapterRegistry([FakeAdapter()]),
        session=CommandSession(PORT, TOKEN), budget=PRODUCT_COMMAND_BUDGET, clock=lambda: NOW,
        ids=ids(), publish_run=lambda _run: None, project_git=reader,
        identity=ProjectIdentity(PROJECT_ID, None, False, "active", None, None))
    project = SimpleNamespace(root=linked, api=subject)
    marker = (linked / ".git").read_bytes()
    answer = step(project, "exclude")
    assert answer.status == 201, answer.payload
    assert (linked / ".git").read_bytes() == marker
    assert (main / ".git/info/exclude").read_bytes().startswith(owner_lines)
    assert BLOCK_BEGIN.encode() in (main / ".git/info/exclude").read_bytes()
    assert not (linked / "info").exists()
    calls = len(reader.calls)
    assert step(project, "exclude").status == 200 and len(reader.calls) == calls


@needs_git
def test_snapshot_seals_raw_bytes_and_clean_filter_oid_without_git_writes_or_path_argv(tmp_path):
    project = unborn(tmp_path)
    cleaner = tmp_path / "cleaner.py"
    cleaner.write_text("import sys\nsys.stdout.buffer.write(sys.stdin.buffer.read().replace(b'raw', b'clean'))\n", encoding="utf-8")
    command = f'"{Path(sys.executable).as_posix()}" "{cleaner.as_posix()}"'
    git("config", "filter.demo.clean", command, cwd=project.root)
    (project.root / ".gitattributes").write_bytes(b"*.dat filter=demo\n")
    name, data = "credentials-data.dat", b"raw payload\n"
    (project.root / name).write_bytes(data)
    reader = Trace(project.api._project_git)
    project.api._project_git = reader
    before = snapshot(project.root / ".git")
    answer = preview(project)
    assert answer.status == 200, answer.payload
    value = answer.payload["setup"]
    row = next(row for row in value["files"] if row["path"] == name)
    assert row == dict(path=name, length=len(data), sha256=sha256(data),
                       git_oid=blob_oid(b"clean payload\n", value["object_format"]))
    encoded = json.dumps(value["files"], sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("ascii")
    assert value["paths_digest"] == sha256(encoded) and "suspicious_name" in value["warnings"]
    assert {row["path"] for row in value["files"]} == {name, ".gitattributes"}
    assert snapshot(project.root / ".git") == before
    assert not (data_root(project.root) / "git/setup/first_commit.json").exists()
    hashes = [(args, keywords) for args, keywords in reader.calls if "hash-object" in args]
    assert hashes and all("-w" not in args and name not in " ".join(args) for args, _ in hashes)
    assert name.encode() in hashes[0][1]["stdin"]
    assert preview(project, "empty").payload["setup"]["files"] == []


@needs_git
def test_preview_names_symlink_as_manual_and_refuses_an_index_or_head(tmp_path):
    project = unborn(tmp_path)
    outside = tmp_path / "outside"
    outside.write_bytes(b"not read")
    try:
        (project.root / "linked.txt").symlink_to(outside)
    except OSError as error:
        pytest.skip(str(error))
    answer = preview(project)
    assert answer.status == 200, answer.payload
    assert answer.payload["setup"]["manual"] == [{"path": "linked.txt", "reason": "symlink"}]
    assert answer.payload["setup"]["files"] == []
    (project.root / "ordinary.txt").write_bytes(b"owner")
    git("add", "ordinary.txt", cwd=project.root)
    assert reason(preview(project)) == "index_exists"
    git("commit", "-m", "owner commit", cwd=project.root)
    assert reason(preview(project)) == "head_exists"


@needs_git
def test_preview_checks_identity_signing_count_and_change_without_creating_objects(tmp_path):
    project = unborn(tmp_path)
    original = project.api._project_git
    project.api._project_git = Trace(original, "-c", "user.name=", "-c", "user.email=")
    assert reason(preview(project)) == "git_identity_missing"
    project.api._project_git = Trace(original, "-c", "commit.gpgSign=true")
    before = snapshot(project.root / ".git")
    answer = preview(project, "empty")
    assert answer.status == 200 and answer.payload["setup"]["signing"] is True
    assert answer.payload["setup"]["warnings"] == ["signing_required"]
    assert snapshot(project.root / ".git") == before
    def many(args, *positional, **keywords):
        if "ls-files" in args and "--others" in args:
            return GitAnswer(0, b"\0".join(f"file-{n}".encode() for n in range(5001)) + b"\0")
        return original(args, *positional, **keywords)
    project.api._project_git = many
    assert reason(preview(project)) == "too_many_files"
    (project.root / "new.txt").write_bytes(b"before")
    def moved(args, *positional, **keywords):
        result = original(args, *positional, **keywords)
        if "hash-object" in args:
            (project.root / "new.txt").write_bytes(b"after")
        return result
    project.api._project_git = moved
    assert reason(preview(project)) == "paths_changed"
    assert snapshot(project.root / ".git") == before


def test_refusal_reasons_are_closed_and_translated():
    copy = (Path(__file__).parents[1] / "src/conductor/panel/studio-notice-copy.js").read_text(encoding="utf-8")
    for key in GIT_SETUP_REASONS:
        assert ApiRefusal.git_setup_refused(key).as_dict()["error"]["detail"] == {"reason": key}
        assert f'"git_setup.reason.{key}": [' in copy
    with pytest.raises(ValueError):
        ApiRefusal.git_setup_refused("raw Git stderr")
