"""The wizard's Git read: eight states, no view spawn, no secrets or repository writes.

The boundary is CommandApi.handle, not the new handler called directly. Scripted admission
answers cover states that do not need real Git; repositories cover the facts shown to the
owner and snapshot every Git byte before and after the read (spec 6.2.1 and 9.1.6).
"""
from __future__ import annotations

import json
import os

import pytest

from conductor import ownership_transition
from conductor.command.adapters import AdapterRegistry
from conductor.command.command_routes import match_route
from conductor.command.http_api import CommandApi, PRODUCT_COMMAND_BUDGET
from conductor.command.http_transport import CommandSession
from conductor.command.product_names import BLOCK_BEGIN, BLOCK_END, EXCLUDE_LINES, PRODUCT_TOP_NAMES
from conductor.command.project_git import GitReadFailed
from conductor.command.run_store import RunStore
from conductor.command.seed_record import SeedRecord, SeedRequest, write_request, write_seed
from conductor.command.task_contracts import TaskRecord
from tests.git_repo_helpers import Script, git, needs_git, said, snapshot
from tests.test_command_adapters import FakeAdapter
from tests.test_command_http_api import NOW, PORT, TOKEN, get_headers, ids
from tests.test_command_materials_routes import NoGit, Project
from tests.test_command_project_doors import code_of, request
from tests.test_seed_record import an_empty_seed
from tests.test_seed_routes import Folder

PATH = "/command/project/git"
KEYS = {"state", "unsupported", "head", "object_format", "dirty_paths", "exclude",
        "agent_instructions", "remotes", "tools", "signing", "first_commit_pending"}


def read(project):
    answer = request(project, "GET", PATH)
    assert answer.status == 200, answer.payload
    assert set(answer.payload) == {"git"}
    facts = answer.payload["git"]
    assert set(facts) == KEYS
    return facts


def unknown(state, *, include=False):
    return {**dict.fromkeys(KEYS), "state": state,
            "agent_instructions": {"found": None, "default_include": include}}


def test_the_git_read_is_an_exact_get_behind_the_existing_host_gate(tmp_path):
    project = Folder(tmp_path, reader=NoGit())
    assert match_route("GET", PATH).name == "project_git"
    assert code_of(request(project, "POST", PATH, {})) == (405, "method_not_allowed")
    assert code_of(request(project, "GET", PATH + "?refresh=true")) == (404, "route_not_found")
    assert code_of(request(project, "GET", PATH + "/extra")) == (404, "route_not_found")
    answer = project.api.handle("GET", PATH, get_headers(host="attacker.invalid"))
    assert code_of(answer) == (403, "same_origin_denied")
    assert project.reader.asked == 0


@pytest.mark.parametrize("entry", ["absent", "directory", "file", "dangling", "ancestor"])
def test_view_uses_only_lexists_of_its_own_git_entry_and_starts_nothing(tmp_path, entry):
    project = Folder(tmp_path, mode="view", reader=NoGit())
    local = project.root / ".git"
    if entry == "directory":
        local.mkdir()
    elif entry == "file":
        local.write_text("gitdir: nowhere\n", encoding="utf-8")
    elif entry == "dangling":
        try:
            local.symlink_to(tmp_path / "missing-git", target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            pytest.skip(str(error))
    elif entry == "ancestor":
        (tmp_path / ".git").mkdir()
    before = snapshot(project.root)
    state = "not_git" if entry in {"absent", "ancestor"} else "not_active"
    assert read(project) == unknown(state)
    assert project.reader.asked == 0 and snapshot(project.root) == before


def test_active_not_git_needs_no_reader_and_has_no_head(tmp_path):
    project = Folder(tmp_path, reader=NoGit())
    assert read(project) == unknown("not_git")
    assert project.reader.asked == 0


@needs_git
@pytest.mark.parametrize("object_format", ["sha1", "sha256"])
@pytest.mark.parametrize("exclude", ["absent", "present"])
def test_repo_facts_read_head_instructions_signing_and_exclude_without_writing_git(
        tmp_path, monkeypatch, object_format, exclude):
    monkeypatch.setenv("GIT_DEFAULT_HASH", object_format)
    project = Project(tmp_path, files={
        "README.md": "Project\n", "AGENTS.md": "rules\n", "docs/ClAuDe.Md": "rules\n",
        ".claude/settings.json": "{}", "src/.KiMi/config": "rules\n",
        "src/.codex/settings": "rules\n", "src/.grok/settings": "rules\n",
        "docs/.claudeish/note": "not an instruction\n"})
    git("config", "commit.gpgsign", "true", cwd=project.root)
    exclude_path = project.root / ".git" / "info" / "exclude"
    if exclude == "present":
        exclude_path.write_text("owner-rule\n" + "\n".join(
            [BLOCK_BEGIN, *EXCLUDE_LINES, BLOCK_END]) + "\n", encoding="utf-8")
    ref = git("symbolic-ref", "HEAD", cwd=project.root).stdout.decode().strip()
    # A refreshed index could otherwise go unnoticed: invalidate its cached stat without
    # changing the tracked bytes, then retain every .git byte before the endpoint reads it.
    tracked = project.root / "README.md"
    previous = tracked.stat()
    os.utime(tracked, ns=(previous.st_atime_ns, previous.st_mtime_ns + 2_000_000_000))
    before = snapshot(project.root / ".git")
    facts = read(project)
    assert facts["state"] == "repo" and facts["unsupported"] is None
    assert facts["head"] == {"ref": ref, "commit": project.head}
    assert facts["object_format"] == object_format
    assert facts["dirty_paths"] == 0 and facts["exclude"] == exclude
    assert facts["agent_instructions"] == {"found": 6, "default_include": False}
    assert facts["signing"] is True and facts["remotes"] == []
    assert facts["tools"]["git"]["version"] and facts["tools"]["gh"] is None
    assert snapshot(project.root / ".git") == before
    assert project.events == []


@needs_git
def test_an_unborn_repository_is_not_a_non_git_folder(tmp_path):
    project = Folder(tmp_path)
    git("init", "-q", cwd=project.root)
    before = snapshot(project.root / ".git")
    facts = read(project)
    assert facts["state"] == "unborn" and facts["head"] is None
    assert facts["object_format"] in {"sha1", "sha256"}
    assert facts["agent_instructions"] == {"found": 0, "default_include": False}
    assert snapshot(project.root / ".git") == before


@pytest.mark.parametrize("state", ["not_repo_root", "unsupported", "unsafe_directory"])
def test_admission_states_are_closed_facts_without_diagnostics_or_absolute_paths(tmp_path, state):
    project = Folder(tmp_path, reader=NoGit())
    (project.root / ".git").mkdir()
    if state == "not_repo_root":
        reader = Script(said(str(tmp_path).encode() + b"\n"))
    elif state == "unsupported":
        reader = Script(said(str(project.root).encode() + b"\n"),
                        said(b"work/result.txt\0instructions/step.md\0"))
    else:
        reader = Script(said(b"fatal: detected dubious ownership; SECRET_DIAGNOSTIC " +
                             str(project.root).encode(), code=128))
    project.api._project_git = reader
    expected = unknown(state)
    if state == "unsupported":
        expected["unsupported"] = {"reason": "tracks_product_dir", "names": ["instructions", "work"]}
    facts = read(project)
    assert facts == expected and not reader.answers
    encoded = json.dumps(facts)
    assert "SECRET_DIAGNOSTIC" not in encoded and str(project.root) not in encoded


@pytest.mark.parametrize("reason", [None, "not_pinned", "missing", "version_changed"])
def test_unavailable_is_a_wizard_state_when_no_pinned_reader_can_run(tmp_path, reason):
    project = Folder(tmp_path, reader=NoGit())
    (project.root / ".git").mkdir()
    calls = []

    def unavailable(*args, **kwargs):
        calls.append(args)
        raise GitReadFailed("tool_unavailable", reason=reason)

    project.api._project_git = None if reason is None else unavailable
    assert read(project) == unknown("unavailable")
    assert len(calls) == (0 if reason is None else 1)


@needs_git
def test_dirty_paths_counts_a_rename_once_and_excludes_every_product_top_name(tmp_path):
    project = Project(tmp_path, files={"old.txt": "old\n", "edit.txt": "before\n"})
    ownership_transition.activate(project.root, legacy_writers_stopped=True)
    # All product names include the ownership namespace; use an activated project and a
    # fresh facade over its moved stores, rather than planting an invalid ownership tree.
    project.api = CommandApi(
        RunStore(project.root), AdapterRegistry([FakeAdapter()]),
        session=CommandSession(PORT, TOKEN), budget=PRODUCT_COMMAND_BUDGET,
        clock=lambda: NOW, ids=ids(), publish_run=project.events.append,
        project_git=project.reader, identity=project.api._identity)
    git("mv", "old.txt", "renamed.txt", cwd=project.root)
    (project.root / "edit.txt").write_text("after\n", encoding="utf-8")
    (project.root / "untracked.txt").write_text("new\n", encoding="utf-8")
    for name in (*PRODUCT_TOP_NAMES, "workspace"):
        folder = project.root / name.replace("*", "witness")
        if folder.is_file():
            continue
        folder.mkdir(exist_ok=True)
        (folder / "untracked.txt").write_text("product or control\n", encoding="utf-8")
    before = snapshot(project.root / ".git")
    assert read(project)["dirty_paths"] == 4
    assert snapshot(project.root / ".git") == before


@needs_git
@pytest.mark.parametrize("failure", ["answer", "exception"])
def test_a_status_timeout_keeps_repo_and_reports_an_unknown_dirty_count(tmp_path, failure):
    project = Project(tmp_path)
    real, calls = project.reader, []

    def reader(args, separate_stderr=False, **kwargs):
        if "status" in args:
            calls.append(tuple(args))
            if failure == "exception":
                raise GitReadFailed("git_timed_out")
            return said(b" M partial.txt\0", code=None, timed_out=True)
        return real(args, separate_stderr, **kwargs)

    project.api._project_git = reader
    facts = read(project)
    assert facts["state"] == "repo" and facts["head"]["commit"] == project.head
    assert facts["dirty_paths"] is None and len(calls) == 1
    assert "--no-optional-locks" in calls[0]


@needs_git
def test_remotes_reveal_only_safe_names_github_coordinates_and_a_credential_flag(tmp_path):
    project = Project(tmp_path)
    rows = [
        ("origin", "https://github.com/owner/repo.git", "owner/repo", False),
        ("scp", "git@github.com:owner/scp.git", "owner/scp", False),
        ("ssh", "ssh://git@github.com/owner/ssh.git", "owner/ssh", False),
        ("private", "https://private-user:SECRET_PASSWORD@github.com/owner/private.git",
         "owner/private", True),
        ("query", "https://github.com/owner/query.git?token=SECRET_QUERY", "owner/query", True),
        ("other", "https://private-user:SECRET_OTHER@gitlab.com/group/repo.git", None, True),
        ("lookalike", "https://github.com.attacker.invalid/owner/repo.git", None, False),
    ]
    for name, url, _, _ in rows:
        git("config", f"remote.{name}.url", url, cwd=project.root)
    before = snapshot(project.root / ".git")
    facts = read(project)
    assert facts["remotes"] == sorted([
        {"name": name, "github": github, "url_has_credentials": credentials}
        for name, _, github, credentials in rows], key=lambda row: row["name"])
    encoded = json.dumps(facts)
    for _, url, _, _ in rows:
        assert url not in encoded
    assert "SECRET_" not in encoded and "private-user" not in encoded
    assert snapshot(project.root / ".git") == before


@pytest.mark.parametrize("mode", ["active", "view"])
@pytest.mark.parametrize("latest_include", [False, True])
def test_default_include_uses_the_latest_seed_not_task_order_or_a_later_request(
        tmp_path, mode, latest_include):
    project = Folder(tmp_path, mode=mode, reader=NoGit())
    if mode == "view":
        (project.root / ".git").mkdir()
    assert read(project)["agent_instructions"]["default_include"] is False
    for task, include, date in (("task-z", not latest_include, "2026-09-29T12:00:00Z"),
                                ("task-a", latest_include, "2026-09-30T12:00:00Z")):
        project.tasks.create_task(TaskRecord(task_id=task, title=task, work_scope=task,
                                             created_at=NOW))
        write_seed(project.root, SeedRecord.from_dict(an_empty_seed(
            task_id=task, work_scope=task, include_agent_instructions=include, staged_at=date)))
    project.tasks.create_task(TaskRecord(task_id="task-request", title="Request",
                                         work_scope="task-request", created_at=NOW))
    write_request(project.root, SeedRequest("task-request", "work-001", not latest_include,
                                            "2026-10-01T12:00:00Z"))
    before = snapshot(project.root)
    assert read(project)["agent_instructions"]["default_include"] is latest_include
    assert snapshot(project.root) == before and project.reader.asked == 0
