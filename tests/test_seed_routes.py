"""`POST /command/tasks/<task_id>/seed`: the door of a task's seed, and the seed in its preparation.

What the desk asks (spec 9.1.1) and what the server answers (9.1.3 to 9.1.6): a fresh seed
stages the base of the project outside `work/`, moves it and answers 201 `seeded` with the
record; the same
request again answers 200 with the record that stands; other conditions are `seed_exists`; a base
that cannot be seeded, or a git that cannot be asked, is `seed_refused` or `tool_unavailable`; and
a server started to view the project asks git nothing and leaves a request, read back as
`requested`. The move under `work/` and the driver are tested in `test_seed_move.py`; the parts of
the seed that need no door are tested where they are (`test_seed_plan.py`, `test_seed_stage.py`,
`test_seed_writer.py`).
"""
from __future__ import annotations

import os
import shutil
import threading
from http.client import RemoteDisconnected
from pathlib import Path
from types import SimpleNamespace

import pytest

from conductor import server_git
from conductor.command import seed_stage
from conductor.command.adapters import AdapterRegistry
from conductor.command.http_api import PRODUCT_COMMAND_BUDGET, CommandApi
from conductor.command.http_transport import CommandSession
from conductor.command.product_names import SEED_STAGING_DIR
from conductor.command.project_git import has_git_entry
from conductor.command.project_claim import ProjectIdentity
from conductor.command.run_store import RunStore
from conductor.command.seed_plan import shown
from conductor.command.task_contracts import TaskRecord
from conductor.command.task_store import TaskStore
from conductor.command.seed_record import (
    SeedRequest, read_request, read_seed, write_request)
from conductor.ownership import data_root
from tests.git_repo_helpers import Script, commit, git, needs_git, real_reader, repository, said
from tests.test_command_adapters import FakeAdapter
from tests.test_command_http_api import NOW, PORT, TOKEN, ids
from tests.test_command_materials_routes import FILES, PROJECT_ID, TASK, NoGit, Project
from tests.test_command_project_doors import code_of, request
from tests.test_seed_stage import plumb, tree_of
from tests.test_view_mode import _send, _served

ITEM = "work-001"
PATH = f"/command/tasks/{TASK}/seed"
OTHER = "task-materials-2"


def body(**changes):
    return {"work_item_id": ITEM, "source": "git", "expect_commit": None,
            "include_agent_instructions": False, **changes}


def seed(project, path=PATH, **changes):
    return request(project, "POST", path, body(**changes))


def reason_of(answer):
    return answer.payload["error"]["detail"]["reason"]


def task_folder(project, task=TASK):
    """Where a seeded task's files are: its own folder under `work/` (spec 9.1.4)."""
    return Path(project.root) / "work" / "_tasks" / task / ITEM


def add_task(project, task_id=OTHER):
    project.tasks.create_task(TaskRecord(task_id=task_id, title="Another", work_scope=task_id,
                                         created_at=NOW))


class Folder:
    """A project folder that is not a repository (or not yet one), served in a mode."""

    def __init__(self, tmp_path, *, mode="active", reader=None, name="plain"):
        self.root = tmp_path / name
        self.root.mkdir()
        self.store, self.tasks = RunStore(self.root), TaskStore(self.root)
        self.tasks.create_task(TaskRecord(task_id=TASK, title="Plain", work_scope=TASK,
                                          created_at=NOW))
        self.reader = reader if reader is not None else real_reader(tmp_path)
        self.api = CommandApi(
            self.store, AdapterRegistry([FakeAdapter()]), session=CommandSession(PORT, TOKEN),
            budget=PRODUCT_COMMAND_BUDGET, clock=lambda: NOW, ids=ids(),
            publish_run=lambda run_id: None, project_git=self.reader,
            identity=ProjectIdentity(PROJECT_ID, None, False, mode, None, None))


# --- the request ---------------------------------------------------------------------------------


BAD_BODIES = [
    {}, {"work_item_id": ITEM}, {**body(), "extra": 1}, body(work_item_id="work-002"),
    body(work_item_id=1), body(source="archive"), body(source=None),
    body(expect_commit="HEAD"), body(expect_commit="AB" * 20), body(expect_commit=7),
    body(expect_commit="ab" * 10), body(include_agent_instructions="no"),
    body(include_agent_instructions=None), body(source="empty", expect_commit="ab" * 20),
    [], "seed", 7]


@needs_git
@pytest.mark.parametrize("sent", BAD_BODIES)
def test_a_body_that_is_not_the_four_keys_of_the_spec_is_contract_invalid_and_writes_nothing(
        tmp_path, sent):
    project = Project(tmp_path, reader=NoGit())
    answer = request(project, "POST", PATH, sent)
    assert code_of(answer) in ((422, "contract_invalid"), (400, "malformed_request"))
    assert project.reader.asked == 0
    assert not (data_root(project.root) / "seeds").exists()
    assert not (project.root / SEED_STAGING_DIR).exists()


@needs_git
def test_a_task_this_build_does_not_hold_is_refused_by_its_id_and_writes_nothing(tmp_path):
    project = Project(tmp_path, reader=NoGit())
    answer = seed(project, "/command/tasks/task-none/seed")
    assert code_of(answer) == (409, "service_refused")
    assert answer.payload["error"]["detail"] == {"task_id": "task-none"}
    assert project.reader.asked == 0 and not (project.root / SEED_STAGING_DIR).exists()


@needs_git
def test_the_seed_path_answers_only_post(tmp_path):
    project = Project(tmp_path, reader=NoGit())
    answer = request(project, "GET", PATH)
    assert code_of(answer) == (405, "method_not_allowed")


def test_a_folder_under_a_git_entry_is_git_and_one_without_is_not_and_no_process_runs(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    assert has_git_entry(plain) is False
    (plain / ".git").mkdir()
    (plain / "sub").mkdir()
    assert has_git_entry(plain) is True and has_git_entry(plain / "sub") is True


# --- a seed made in an active project -----------------------------------------------------------


@needs_git
def test_seed_writes_head_blobs_byte_exact_without_filters_or_export_ignore(tmp_path):
    project = Project(tmp_path, files={
        "secret.txt": b"kept although export-ignore\n", "ver.txt": b"$Format:%H$\n",
        "mixed.txt": b"one\r\ntwo\nthree\r\n", "deep/er/x.bin": bytes(range(256))})
    commit(project.root, {".gitattributes": b"* text=auto eol=crlf\nsecret.txt export-ignore\n"
                                           b"ver.txt export-subst\n"})
    git("config", "core.autocrlf", "true", cwd=project.root)
    answer = seed(project)
    assert answer.status == 201 and answer.payload["state"] == "seeded"
    record = read_seed(project.root, TASK)
    assert record.base_commit == git("rev-parse", "HEAD", cwd=project.root).stdout.decode().strip()
    assert tree_of(task_folder(project)) == {
        "secret.txt": b"kept although export-ignore\n", "ver.txt": b"$Format:%H$\n",
        "mixed.txt": b"one\r\ntwo\nthree\r\n", "deep/er/x.bin": bytes(range(256)),
        ".gitattributes": b"* text=auto eol=crlf\nsecret.txt export-ignore\nver.txt export-subst\n"}


@needs_git
def test_a_fresh_seed_answers_201_with_the_record_and_its_state_and_a_repeat_answers_200(tmp_path):
    project = Project(tmp_path)
    first = seed(project)
    record = read_seed(project.root, TASK)
    assert first.status == 201
    assert first.payload == {**record.as_dict(), "state": "seeded"}
    again = seed(project)
    assert (again.status, again.payload) == (200, first.payload)
    assert [p.name for p in (data_root(project.root) / "seeds" / TASK).iterdir()] == [
        "work-001.json"]


@needs_git
def test_a_repeat_while_head_has_moved_still_answers_the_standing_record_for_the_same_base(
        tmp_path):
    project = Project(tmp_path)
    base = git("rev-parse", "HEAD", cwd=project.root).stdout.decode().strip()
    first = seed(project, expect_commit=base)
    commit(project.root, {"later.txt": "after\n"})
    again = seed(project, expect_commit=base)
    assert (first.status, again.status) == (201, 200) and again.payload == first.payload


@needs_git
@pytest.mark.parametrize("changes", [{"include_agent_instructions": True},
                                     {"source": "empty"},
                                     {"expect_commit": "ab" * 20}])
def test_other_conditions_than_the_standing_seeds_are_seed_exists_naming_its_base(
        tmp_path, changes):
    project = Project(tmp_path)
    seed(project)
    before = (data_root(project.root) / "seeds" / TASK / "work-001.json").read_bytes()
    answer = seed(project, **changes)
    record = read_seed(project.root, TASK)
    assert code_of(answer) == (409, "seed_refused") and reason_of(answer) == "seed_exists"
    assert answer.payload["error"]["detail"] == {"reason": "seed_exists",
                                                 "commit": record.base_commit}
    assert (data_root(project.root) / "seeds" / TASK / "work-001.json").read_bytes() == before


@needs_git
def test_seed_records_symlink_submodule_unportable_and_long_path_skips(tmp_path):
    project = Project(tmp_path, files={"keep.txt": "kept\n"})
    scope = Path(project.root) / "work" / "_tasks" / TASK / ITEM
    long_name = "/".join(["d" * 80] * 3 + ["f.txt"])
    room = 259 - len(str(scope)) - 1
    plumb(project.root, ("120000", "link", b"keep.txt"), ("160000", "vendor/sub", None),
          ("100644", "del\x7fname.txt", b"x\n"), ("100644", long_name, b"long\n"))
    answer = seed(project)
    assert answer.status == 201
    record = read_seed(project.root, TASK)
    skipped = {row.path: row.reason for row in record.skipped}
    assert skipped["link"] == "symlink" and skipped["vendor/sub"] == "submodule"
    assert skipped[shown("del\x7fname.txt")] == "unportable_name"
    too_long = os.name == "nt" and len(long_name) > room
    assert skipped.get(long_name) == ("path_budget" if too_long else None)
    assert ("keep.txt" in tree_of(task_folder(project))) and (
        (long_name in tree_of(task_folder(project))) != too_long)


@needs_git
def test_seed_skips_agent_instruction_files_unless_the_project_includes_them(tmp_path):
    project = Project(tmp_path)
    add_task(project)
    seed(project)
    record = read_seed(project.root, TASK)
    assert record.agent_instructions_skipped == ("CLAUDE.md",)
    assert "CLAUDE.md" not in tree_of(task_folder(project))
    seed(project, path=f"/command/tasks/{OTHER}/seed", include_agent_instructions=True)
    other = read_seed(project.root, OTHER)
    assert other.agent_instructions_skipped == () and other.include_agent_instructions is True
    assert tree_of(task_folder(project, OTHER))["CLAUDE.md"] == FILES["CLAUDE.md"].encode()


@needs_git
def test_seed_refuses_case_collision_and_a_tracked_product_directory(tmp_path, monkeypatch):
    project = Project(tmp_path, files={"ok.txt": "fine\n"})
    plumb(project.root, ("100644", "a/B", b"one\n"), ("100644", "A/b", b"two\n"))
    monkeypatch.setattr(seed_stage, "sys", SimpleNamespace(platform="win32"))
    answer = seed(project)
    assert code_of(answer) == (409, "seed_refused") and reason_of(answer) == "case_collision"
    monkeypatch.undo()
    project = Project(tmp_path, name="tracked", files={"ok.txt": "fine\n", "work/x.txt": "x\n"})
    answer = seed(project)
    assert code_of(answer) == (409, "seed_refused") and reason_of(answer) == "tracks_product_dir"
    for one in (tmp_path / "project", project.root):
        assert not (one / SEED_STAGING_DIR).exists()
        assert not (data_root(one) / "seeds").exists()


@needs_git
def test_seed_refuses_when_head_moved_from_the_expected_commit(tmp_path):
    project = Project(tmp_path)
    old = git("rev-parse", "HEAD", cwd=project.root).stdout.decode().strip()
    new = commit(project.root, {"moved.txt": "moved\n"})
    answer = seed(project, expect_commit=old)
    assert code_of(answer) == (409, "seed_refused") and reason_of(answer) == "base_moved"
    assert answer.payload["error"]["detail"] == {"reason": "base_moved", "commit": new}
    assert not (project.root / SEED_STAGING_DIR).exists()
    assert read_seed(project.root, TASK) is None
    assert seed(project, expect_commit=new).status == 201


@needs_git
def test_abandoned_staging_without_a_record_is_removed_by_the_next_seed(tmp_path):
    project = Project(tmp_path)
    left = project.root / SEED_STAGING_DIR / seed_stage.staging_name(TASK, ITEM)
    (left / "half").mkdir(parents=True)
    (left / "half" / "old.bin").write_bytes(b"abandoned")
    assert seed(project).status == 201
    assert not left.exists() and not (project.root / SEED_STAGING_DIR).exists()
    assert (task_folder(project) / "README.md").read_bytes() == b"# Project\n"
    assert not (task_folder(project) / "half").exists()


# --- a folder that cannot be seeded -------------------------------------------------------------


@needs_git
def test_a_folder_that_is_not_a_repository_is_refused_not_a_git_repository(tmp_path):
    folder = Folder(tmp_path)
    answer = request(folder, "POST", PATH, body())
    assert code_of(answer) == (409, "seed_refused") and reason_of(answer) == "not_a_git_repository"
    assert not (folder.root / SEED_STAGING_DIR).exists()


@needs_git
def test_a_repository_with_no_commit_is_refused_unborn_head(tmp_path):
    folder = Folder(tmp_path)
    git("init", "-q", cwd=folder.root)
    answer = request(folder, "POST", PATH, body())
    assert code_of(answer) == (409, "seed_refused") and reason_of(answer) == "unborn_head"


@needs_git
def test_a_subfolder_of_a_repository_is_refused_project_not_repo_root(tmp_path):
    repository(tmp_path, "outer")
    commit(tmp_path / "outer", {"a.txt": "a\n"})
    folder = Folder(tmp_path / "outer", name="inner")
    answer = request(folder, "POST", PATH, body())
    assert code_of(answer) == (409, "seed_refused")
    assert reason_of(answer) == "project_not_repo_root"


@needs_git
def test_an_empty_seed_is_allowed_only_for_a_folder_that_is_not_git(tmp_path):
    folder = Folder(tmp_path)
    made = request(folder, "POST", PATH, body(source="empty"))
    record = read_seed(folder.root, TASK)
    assert made.status == 201 and made.payload == {**record.as_dict(), "state": "seeded"}
    assert (record.source, record.base_commit, record.file_count) == ("empty", None, 0)
    task = Path(folder.root) / "work" / "_tasks" / TASK / ITEM
    assert task.is_dir() and tree_of(task) == {}
    project = Project(tmp_path, name="repo")
    refused = seed(project, source="empty")
    assert code_of(refused) == (409, "seed_refused") and reason_of(refused) == "empty_not_allowed"


@needs_git
def test_a_server_that_holds_no_reader_of_git_cannot_seed_from_it(tmp_path):
    project = Project(tmp_path, reader=None)
    answer = seed(project)
    assert code_of(answer) == (409, "seed_refused") and reason_of(answer) == "git_failed"


@needs_git
@pytest.mark.parametrize("answers, reason", [
    ([said(b"", code=128)], "git_failed"),
    ([said(b"", code=None, timed_out=True)], "git_timed_out")])
def test_a_git_that_fails_or_runs_late_is_seed_refused_with_its_word(tmp_path, answers, reason):
    project = Project(tmp_path, reader=Script(*answers))
    answer = seed(project)
    assert code_of(answer) == (409, "seed_refused") and reason_of(answer) == reason
    assert not (project.root / SEED_STAGING_DIR).exists()


@needs_git
@pytest.mark.parametrize("reason", server_git.REASONS)
def test_a_pinned_git_that_cannot_be_used_is_a_503_naming_git_and_why(tmp_path, reason):
    def gone(args, separate_stderr=False, **keywords):
        raise server_git.ToolUnavailable(reason)
    project = Project(tmp_path, reader=gone)
    answer = seed(project)
    assert code_of(answer) == (503, "tool_unavailable")
    assert answer.payload["error"]["detail"] == {"tool": "git", "reason": reason}


# --- a server started to view the project -------------------------------------------------------


@needs_git
def test_seed_request_in_view_mode_writes_a_request_without_git_and_reads_requested(tmp_path):
    project = Project(tmp_path, mode="view", reader=NoGit())
    made = seed(project, include_agent_instructions=True)
    stored = read_request(project.root, TASK)
    assert made.status == 201
    assert made.payload == {**stored.as_dict(), "state": "requested"}
    assert stored.include_agent_instructions is True and stored.requested_at == NOW
    assert read_seed(project.root, TASK) is None and project.reader.asked == 0
    again = seed(project, include_agent_instructions=True)
    assert (again.status, again.payload) == (200, made.payload)
    assert not (project.root / SEED_STAGING_DIR).exists()


@needs_git
def test_another_request_than_the_standing_one_is_seed_exists_in_view(tmp_path):
    project = Project(tmp_path, mode="view", reader=NoGit())
    seed(project)
    answer = seed(project, include_agent_instructions=True)
    assert code_of(answer) == (409, "seed_refused") and reason_of(answer) == "seed_exists"
    assert "commit" not in answer.payload["error"]["detail"]


@needs_git
def test_a_view_server_takes_no_expected_commit_for_a_git_seed(tmp_path):
    project = Project(tmp_path, mode="view", reader=NoGit())
    answer = seed(project, expect_commit="ab" * 20)
    assert code_of(answer) == (422, "contract_invalid") and project.reader.asked == 0
    assert read_request(project.root, TASK) is None


def serving(project, mode, reader):
    """The same project served again in another mode, over a reader of its own."""
    return SimpleNamespace(reader=reader, api=CommandApi(
        project.store, AdapterRegistry([FakeAdapter()]), session=CommandSession(PORT, TOKEN),
        budget=PRODUCT_COMMAND_BUDGET, clock=lambda: NOW, ids=ids(),
        publish_run=lambda run_id: None, project_git=reader,
        identity=ProjectIdentity(PROJECT_ID, None, False, mode, None, None)))


@needs_git
def test_a_seed_that_stands_is_read_in_view_with_its_state_and_without_git(tmp_path):
    active = Project(tmp_path)
    seed(active)
    viewing = serving(active, "view", NoGit())
    answer = seed(viewing)
    assert answer.status == 200 and answer.payload["state"] == "seeded"
    assert viewing.reader.asked == 0


@needs_git
def test_an_empty_seed_in_view_works_as_in_active_and_asks_no_git(tmp_path):
    folder = Folder(tmp_path, mode="view", reader=NoGit())
    answer = request(folder, "POST", PATH, body(source="empty"))
    assert answer.status == 201 and answer.payload["source"] == "empty"
    assert folder.reader.asked == 0


# --- the seed in the preparation of the task ----------------------------------------------------


def preparation(project, task=TASK):
    answer = request(project, "GET", f"/command/tasks/{task}/preparation")
    assert answer.status == 200, answer.payload
    return answer.payload["seed"]


@needs_git
def test_the_preparation_of_a_task_carries_its_seed_and_reads_the_state_off_the_disk(tmp_path):
    project = Project(tmp_path)
    assert preparation(project) is None
    made = seed(project)
    record = read_seed(project.root, TASK)
    assert preparation(project) == made.payload == {**record.as_dict(), "state": "seeded"}
    shutil.rmtree(task_folder(project))
    assert preparation(project) == {**record.as_dict(), "state": "seed_lost"}


@needs_git
def test_the_preparation_of_a_task_with_only_a_request_carries_the_request(tmp_path):
    project = Project(tmp_path, mode="view", reader=NoGit())
    made = seed(project)
    assert preparation(project) == made.payload and made.payload["state"] == "requested"


@needs_git
def test_a_request_on_file_is_performed_by_the_active_server_and_the_record_then_wins(tmp_path):
    project = Project(tmp_path)
    write_request(project.root, SeedRequest(TASK, ITEM, False, NOW))
    assert preparation(project)["state"] == "requested"
    other = seed(project, include_agent_instructions=True)
    assert code_of(other) == (409, "seed_refused") and reason_of(other) == "seed_exists"
    made = seed(project)
    assert made.status == 201 and preparation(project) == made.payload
    assert read_request(project.root, TASK) is not None, "the request stays as history"


@needs_git
def test_a_corrupt_record_does_not_hide_the_task_and_is_a_store_error_where_it_is_asked(tmp_path):
    project = Project(tmp_path)
    seed(project)
    path = data_root(project.root) / "seeds" / TASK / "work-001.json"
    path.write_text("{not json", encoding="utf-8")
    assert preparation(project) is None
    assert code_of(seed(project)) == (500, "store_error")


# --- two requests for one task ------------------------------------------------------------------


@needs_git
def test_requests_racing_for_one_task_make_one_seed_and_answer_the_same_record(tmp_path):
    project = Project(tmp_path)
    answers, gate = [], threading.Barrier(5)

    def ask():
        gate.wait()
        answers.append(seed(project))

    threads = [threading.Thread(target=ask) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(60)
    assert sorted(answer.status for answer in answers) == [200, 200, 200, 200, 201]
    assert len({str(answer.payload) for answer in answers}) == 1
    assert [p.name for p in (data_root(project.root) / "seeds" / TASK).iterdir()] == [
        "work-001.json"]


# --- the reader of git the server itself builds (lane H) ------------------------------------


@pytest.fixture
def conduct_home(tmp_path_factory, monkeypatch):
    """The hub's folder of the test: an empty one of its own, where git is pinned."""
    home = tmp_path_factory.mktemp("hub-home")
    monkeypatch.setenv("CONDUCT_HOME", str(home))
    return home


@needs_git
@pytest.mark.xfail(
    strict=True, raises=RemoteDisconnected,
    reason="the server's reader (lane H's _LazyReader) takes no keywords yet: handoff "
           "L8-to-H-git-reader-stdin; the marker goes the day the patch lands")
def test_the_seed_route_asks_the_pinned_git_through_the_servers_own_reader(
        tmp_path, conduct_home):
    with _served(tmp_path, "active", repository=True) as subject:
        _send(subject, "POST", "/command/tasks", {"task_id": "task-1", "title": "Seed me"}, 201)
        answer = _send(subject, "POST", "/command/tasks/task-1/seed", body(), 201)
    assert answer["state"] == "seeded" and answer["source"] == "git"
    assert answer["file_count"] == 2
