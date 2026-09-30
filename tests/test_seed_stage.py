"""The staging of a seed: a base commit written into a folder of its own, byte for byte (9.1.2).

The bytes of a seed are the bytes of the blobs, read by `cat-file --batch`, with no filter and no
line-ending change and none of the substitutions `git archive` applies: the work folder must agree
with the base, or the acceptance that diffs against it would see deletions that never happened.
These tests read real repositories, in the way the product does, and judge the folder the staging
leaves: its files, its modes, its record, what it leaves behind when it fails, and that it never
follows a link or touches a neighbour's staging.
"""
from __future__ import annotations

import io
import os
import subprocess
import tarfile
from contextlib import contextmanager
from pathlib import Path

import pytest

from conductor.command import seed_stage
from conductor.command.adapters.process import ProcessRunner
from conductor.command.api_refusals import SEED_REASONS
from conductor.command.product_names import SEED_STAGING_DIR
from conductor.command.project_git import GitAnswer
from conductor.command.seed_plan import SeedRefusal
from conductor.command.seed_record import SeedRecord, SeedWarning, Skip
from conductor.command.template_store import RouteNotOwned
from tests.git_repo_helpers import (
    GIT, IDENTITY, ISOLATED, Script, commit, git, needs_git, real_reader, repository, said,
    snapshot)

TASK, SCOPE, ITEM, AT = "task-seed-1", "scope-seed-1", "work-001", "2026-09-30T12:00:00Z"
POSIX = os.name == "posix"


def staged(folder, reader, base=None, **asked):
    base = base or seed_stage.read_base(folder, reader)
    asked.setdefault("include_agent_instructions", False)
    return seed_stage.stage_from_git(
        folder, reader, task_id=TASK, work_scope=SCOPE, work_item_id=ITEM, base=base,
        staged_at=AT, **asked)


def tree_of(folder):
    """Every file under `folder`, relative, with its bytes."""
    return {path.relative_to(folder).as_posix(): path.read_bytes()
            for path in sorted(Path(folder).rglob("*")) if path.is_file()}


def staging_of(folder, record):
    return Path(folder) / SEED_STAGING_DIR / record.staging


def blob_of(folder, data):
    """Write `data` as a blob of the repository and return its object id."""
    done = subprocess.run([GIT, *IDENTITY, "hash-object", "-w", "--stdin"], cwd=folder,
                          input=data, env={**os.environ, **ISOLATED}, capture_output=True)
    assert done.returncode == 0, done.stderr
    return done.stdout.decode().strip()


def plumb(folder, *entries):
    """Add index entries `(mode, name, bytes or None)` by plumbing, then commit them."""
    for mode, name, data in entries:
        oid = "ab" * 20 if data is None else blob_of(folder, data)
        git("update-index", "--add", "--cacheinfo", f"{mode},{oid},{name}", cwd=folder)
    git("commit", "-q", "-m", "plumbing", cwd=folder)


def case_sensitive(folder):
    probe = Path(folder) / "CaseProbe"
    probe.write_bytes(b"")
    try:
        return not (Path(folder) / "caseprobe").exists()
    finally:
        probe.unlink()


@pytest.fixture
def repo(tmp_path):
    folder = repository(tmp_path)
    return folder, real_reader(tmp_path)


# --- the names ----------------------------------------------------------------------------------


def test_a_staging_folder_is_named_by_the_task_and_work_item_and_by_nothing_else():
    one = seed_stage.staging_name("task-a", "work-001")
    assert one == seed_stage.staging_name("task-a", "work-001")
    assert one != seed_stage.staging_name("task-b", "work-001")
    assert one != seed_stage.staging_name("task-a", "work-002")
    assert len(one) == 10 and one.startswith("s-") and int(one[2:], 16) >= 0


def test_a_seed_record_of_the_reader_accepts_the_name():
    from conductor.command.seed_record import _STAGING
    assert _STAGING.match(seed_stage.staging_name(TASK, ITEM))


# --- the base -----------------------------------------------------------------------------------


@needs_git
def test_a_repository_with_no_commit_has_no_base(repo):
    folder, reader = repo
    assert seed_stage.read_base(folder, reader) is None


@needs_git
def test_the_base_is_the_commit_head_names_its_tree_its_object_format_and_its_ref(repo):
    folder, reader = repo
    head = commit(folder, {"a.txt": "alpha\n"})
    base = seed_stage.read_base(folder, reader)
    ref = git("symbolic-ref", "HEAD", cwd=folder).stdout.decode().strip()
    tree = git("rev-parse", "HEAD^{tree}", cwd=folder).stdout.decode().strip()
    assert (base.commit, base.tree, base.object_format, base.ref) == (head, tree, "sha1", ref)


@needs_git
def test_a_detached_head_names_itself_as_the_ref(repo):
    folder, reader = repo
    head = commit(folder, {"a.txt": "alpha\n"})
    git("checkout", "-q", "--detach", head, cwd=folder)
    assert seed_stage.read_base(folder, reader).ref == "HEAD"


# --- the bytes ----------------------------------------------------------------------------------


@needs_git
def test_the_folder_holds_the_bytes_of_the_blobs_and_no_more(repo):
    folder, reader = repo
    files = {"a.txt": b"alpha\n", "dir/deep/b.bin": bytes(range(256)), "empty": b"",
             "sp ace/café.md": "café\n".encode("utf-8"), "dir/c.txt": b"c\r\nd\n"}
    commit(folder, files)
    record = staged(folder, reader)
    assert tree_of(staging_of(folder, record)) == files
    assert (record.file_count, record.total_bytes) == (len(files), sum(map(len, files.values())))


@needs_git
def test_no_attribute_no_filter_and_no_line_ending_setting_changes_a_byte(repo):
    folder, reader = repo
    files = {"secret.txt": b"kept although export-ignore\n", "ver.txt": b"$Format:%H$\n",
             "x.flt": b"as stored\n", "mixed.txt": b"one\r\ntwo\nthree\r\n"}
    commit(folder, files)
    attributes = (b"* text=auto eol=crlf\nsecret.txt export-ignore\nver.txt export-subst\n"
                  b"*.flt filter=up\n")
    commit(folder, {".gitattributes": attributes})
    git("config", "core.autocrlf", "true", cwd=folder)
    git("config", "filter.up.smudge", "sh -c 'tr a-z A-Z'", cwd=folder)
    git("config", "filter.up.clean", "cat", cwd=folder)
    with tarfile.open(fileobj=io.BytesIO(git("archive", "HEAD", cwd=folder).stdout)) as archive:
        assert "secret.txt" not in archive.getnames(), "git archive would have dropped the file"
        assert archive.extractfile("ver.txt").read() != files["ver.txt"], "...and substituted"
    record = staged(folder, reader)
    assert tree_of(staging_of(folder, record)) == {**files, ".gitattributes": attributes}
    for name, data in files.items():
        assert git("cat-file", "blob", f"HEAD:{name}", cwd=folder).stdout == data


@needs_git
@pytest.mark.skipif(not POSIX, reason="a file mode bit is a POSIX fact")
def test_an_executable_file_of_the_base_is_executable_and_a_plain_one_is_not(repo):
    folder, reader = repo
    commit(folder, {"run.sh": "#!/bin/sh\n", "plain.txt": "x\n"})
    git("update-index", "--chmod=+x", "run.sh", cwd=folder)
    git("commit", "-q", "-m", "exec", cwd=folder)
    folder_of = staging_of(folder, staged(folder, reader))
    assert (folder_of / "run.sh").stat().st_mode & 0o777 == 0o755
    assert (folder_of / "plain.txt").stat().st_mode & 0o777 == 0o644


@needs_git
def test_a_link_and_a_submodule_are_left_out_and_recorded_with_their_reasons(repo):
    folder, reader = repo
    commit(folder, {"keep.txt": "kept\n"})
    plumb(folder, ("120000", "link", b"keep.txt"), ("160000", "vendor/sub", None))
    record = staged(folder, reader)
    assert tree_of(staging_of(folder, record)) == {"keep.txt": b"kept\n"}
    assert record.skipped == (Skip("link", "symlink"), Skip("vendor/sub", "submodule"))


@needs_git
def test_instruction_files_are_left_out_unless_the_owner_asks_for_them(repo):
    folder, reader = repo
    commit(folder, {"CLAUDE.md": "rules\n", ".claude/s.json": "{}\n", "src/a.py": "a\n"})
    left = staged(folder, reader)
    assert sorted(tree_of(staging_of(folder, left))) == ["src/a.py"]
    assert left.agent_instructions_skipped == (".claude/s.json", "CLAUDE.md")
    assert left.include_agent_instructions is False
    seed_stage.remove_staging(folder, left.staging)
    kept = staged(folder, reader, include_agent_instructions=True)
    assert sorted(tree_of(staging_of(folder, kept))) == [".claude/s.json", "CLAUDE.md", "src/a.py"]
    assert kept.agent_instructions_skipped == () and kept.include_agent_instructions is True


@needs_git
def test_a_git_lfs_pointer_is_seeded_as_it_is_and_named_in_a_warning(repo):
    folder, reader = repo
    pointer = (b"version https://git-lfs.github.com/spec/v1\noid sha256:" + b"b" * 64
               + b"\nsize 99\n")
    commit(folder, {"model.bin": pointer, "readme.txt": "hello\n"})
    record = staged(folder, reader)
    assert tree_of(staging_of(folder, record))["model.bin"] == pointer
    assert record.warnings == (SeedWarning("model.bin", "lfs_pointer"),)


@needs_git
def test_the_record_carries_the_base_the_counts_and_the_name_of_the_staging(repo):
    folder, reader = repo
    commit(folder, {"a.txt": "alpha\n"})
    base = seed_stage.read_base(folder, reader)
    record = staged(folder, reader, base)
    assert isinstance(record, SeedRecord)
    assert (record.task_id, record.work_scope, record.work_item_id) == (TASK, SCOPE, ITEM)
    assert (record.source, record.base_commit, record.base_tree) == (
        "git", base.commit, base.tree)
    assert (record.object_format, record.base_ref, record.staged_at) == (
        "sha1", base.ref, AT)
    assert record.staging == seed_stage.staging_name(TASK, ITEM)
    assert SeedRecord.from_dict(record.as_dict()) == record, "the reader admits what it made"


@needs_git
def test_a_sha256_repository_is_seeded_with_its_sixty_four_digit_ids(tmp_path):
    folder = tmp_path / "sha256"
    folder.mkdir()
    if git("init", "-q", "--object-format=sha256", cwd=folder, check=False).returncode:
        pytest.skip("this git cannot make a sha256 repository")
    commit(folder, {"a.txt": "alpha\n", "b/c.txt": "c\n"})
    reader = real_reader(tmp_path)
    record = staged(folder, reader)
    assert record.object_format == "sha256" and len(record.base_commit) == 64
    assert tree_of(staging_of(folder, record)) == {"a.txt": b"alpha\n", "b/c.txt": b"c\n"}


@needs_git
def test_reading_a_base_writes_nothing_into_the_owners_git_folder(repo):
    folder, reader = repo
    commit(folder, {"a.txt": "alpha\n", "b.txt": "beta\n"})
    before = snapshot(folder / ".git")
    staged(folder, reader)
    assert snapshot(folder / ".git") == before


# --- what a refused or failed seed leaves behind ------------------------------------------------


@needs_git
def test_a_refused_plan_writes_nothing_at_all(repo):
    folder, reader = repo
    commit(folder, {"ok.txt": "fine\n", "work/tracked.txt": "owned by the product\n"})
    with pytest.raises(SeedRefusal) as refused:
        staged(folder, reader)
    assert refused.value.reason == "tracks_product_dir"
    assert not (folder / SEED_STAGING_DIR).exists()


@needs_git
def test_a_case_collision_is_refused_where_the_volume_folds_case_and_writes_nothing(repo):
    folder, reader = repo
    plumb(folder, ("100644", "a/B", b"one\n"), ("100644", "A/b", b"two\n"))
    with pytest.raises(SeedRefusal) as refused:
        staged(folder, reader, case_insensitive=True)
    assert refused.value.reason == "case_collision" and not (folder / SEED_STAGING_DIR).exists()
    if case_sensitive(folder):
        record = staged(folder, reader, case_insensitive=False)
        assert sorted(tree_of(staging_of(folder, record))) == ["A/b", "a/B"]


class Cut:
    """A reader that lets the real one answer and then cuts the answer of its batch short."""

    def __init__(self, real, **change):
        self.real, self.change = real, change

    def __call__(self, args, separate_stderr=False, **keywords):
        answer = self.real(args, separate_stderr, **keywords)
        if "cat-file" in args and "--batch" in args:
            return GitAnswer(**{**answer.__dict__, **self.change})
        return answer


@needs_git
@pytest.mark.parametrize("change, reason", [
    ({"truncated": True}, "git_failed"), ({"exit_code": 128}, "git_failed"),
    ({"timed_out": True, "exit_code": None}, "git_timed_out"),
    ({"output": b"short"}, "git_failed")])
def test_a_batch_that_is_cut_failed_or_late_is_a_refusal_and_leaves_no_folder_behind(
        repo, change, reason):
    folder, reader = repo
    commit(folder, {"a.txt": "alpha\n", "b/c.txt": "beta\n"})
    with pytest.raises(SeedRefusal) as refused:
        staged(folder, Cut(reader, **change), seed_stage.read_base(folder, reader))
    assert refused.value.reason == reason and reason in SEED_REASONS
    assert not (folder / SEED_STAGING_DIR).exists()


@needs_git
def test_a_listing_git_cuts_short_is_a_base_too_large_to_know(repo):
    folder, reader = repo
    commit(folder, {"a.txt": "alpha\n"})

    def small(args, separate_stderr=False, **keywords):
        if "ls-tree" in args:
            keywords["output_limit"] = 10
        return reader(args, separate_stderr, **keywords)
    with pytest.raises(SeedRefusal) as refused:
        staged(folder, small, seed_stage.read_base(folder, reader))
    assert refused.value.reason == "seed_too_large" and not (folder / SEED_STAGING_DIR).exists()


@pytest.mark.parametrize("answers, reason", [
    ([said(b"", code=128)], "git_failed"),
    ([said(b"", code=None, timed_out=True)], "git_timed_out")])
def test_a_listing_that_fails_or_runs_late_is_a_refusal(tmp_path, answers, reason):
    base = seed_stage.BaseFacts("ab" * 20, "cd" * 20, "sha1", "refs/heads/main")
    with pytest.raises(SeedRefusal) as refused:
        staged(tmp_path, Script(*answers), base)
    assert refused.value.reason == reason and not (tmp_path / SEED_STAGING_DIR).exists()


# --- the folder it works in ---------------------------------------------------------------------


@needs_git
def test_a_leftover_preparation_of_the_same_task_is_removed_and_a_neighbours_is_not(repo):
    folder, reader = repo
    commit(folder, {"a.txt": "alpha\n"})
    mine = folder / SEED_STAGING_DIR / seed_stage.staging_name(TASK, ITEM)
    other = folder / SEED_STAGING_DIR / seed_stage.staging_name("task-other", ITEM)
    for place in (mine, other):
        (place / "junk").mkdir(parents=True)
        (place / "junk" / "old.txt").write_bytes(b"old")
    record = staged(folder, reader)
    assert tree_of(staging_of(folder, record)) == {"a.txt": b"alpha\n"}
    assert (other / "junk" / "old.txt").read_bytes() == b"old"


@needs_git
def test_removing_a_leftover_never_follows_a_link_out_of_it(repo, tmp_path):
    folder, reader = repo
    commit(folder, {"a.txt": "alpha\n"})
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "precious.txt").write_bytes(b"keep me")
    mine = folder / SEED_STAGING_DIR / seed_stage.staging_name(TASK, ITEM)
    mine.mkdir(parents=True)
    try:
        os.symlink(outside, mine / "door", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this account cannot make a link")
    staged(folder, reader)
    assert (outside / "precious.txt").read_bytes() == b"keep me"


@needs_git
def test_a_seed_folder_that_is_a_link_is_not_written_through(repo, tmp_path):
    folder, reader = repo
    commit(folder, {"a.txt": "alpha\n"})
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        os.symlink(outside, folder / SEED_STAGING_DIR, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this account cannot make a link")
    with pytest.raises(RouteNotOwned):
        staged(folder, reader)
    assert list(outside.iterdir()) == []


@needs_git
def test_the_staging_is_written_and_removed_under_the_projects_write_guard(repo, monkeypatch):
    folder, reader = repo
    commit(folder, {"a.txt": "alpha\n"})
    held = []

    @contextmanager
    def spy(root):
        held.append(Path(root))
        yield
    monkeypatch.setattr(ProcessRunner, "project_write_guard",
                        classmethod(lambda cls, root: spy(root)))
    record = staged(folder, reader)
    seed_stage.remove_staging(folder, record.staging)
    # The runner takes the guard of its own root for each git call; the seed takes the project's
    # once to stage and once to remove.
    assert [path.resolve() for path in held if path.resolve() == folder.resolve()] == [
        folder.resolve()] * 2


@needs_git
def test_removing_a_staging_takes_its_folder_and_the_seed_folder_only_when_it_is_empty(repo):
    folder, reader = repo
    commit(folder, {"a.txt": "alpha\n"})
    record = staged(folder, reader)
    neighbour = folder / SEED_STAGING_DIR / "s-00000000"
    neighbour.mkdir()
    seed_stage.remove_staging(folder, record.staging)
    assert not staging_of(folder, record).exists() and neighbour.is_dir()
    neighbour.rmdir()
    again = staged(folder, reader)
    seed_stage.remove_staging(folder, again.staging)
    assert not (folder / SEED_STAGING_DIR).exists()
    seed_stage.remove_staging(folder, again.staging)


@pytest.mark.parametrize("name", ["", "s-1", "s-ZZZZZZZZ", "../s-1a2b3c4d", "s-1a2b3c4d/x",
                                  "S-1A2B3C4D", ".conduct-seed"])
def test_only_a_staging_name_of_the_grammar_can_be_removed(tmp_path, name):
    with pytest.raises(ValueError):
        seed_stage.remove_staging(tmp_path, name)


def test_an_empty_seed_is_an_empty_folder_and_a_record_with_no_base(tmp_path):
    record = seed_stage.stage_empty(tmp_path, task_id=TASK, work_scope=SCOPE,
                                    work_item_id=ITEM, staged_at=AT)
    assert staging_of(tmp_path, record).is_dir() and tree_of(staging_of(tmp_path, record)) == {}
    assert (record.source, record.base_commit, record.base_tree, record.object_format,
            record.base_ref) == ("empty", None, None, None, None)
    assert (record.file_count, record.total_bytes) == (0, 0)
    assert (record.skipped, record.warnings) == ((), ())
    assert SeedRecord.from_dict(record.as_dict()) == record


def test_a_failed_write_removes_what_it_began(tmp_path, monkeypatch):
    folder = tmp_path / "project"
    folder.mkdir()
    base = seed_stage.BaseFacts("ab" * 20, "cd" * 20, "sha1", "refs/heads/main")
    row = f"100644 blob {'ef' * 20} {6:>7}\tfile.txt".encode() + b"\0"
    blob = f"{'ef' * 20} blob 6\nalpha\n\n".encode()

    def reader(args, separate_stderr=False, **keywords):
        return said(row if "ls-tree" in args else blob)

    def full(*_):
        raise OSError("the disk is full")
    monkeypatch.setattr(seed_stage, "_write_file", full)
    with pytest.raises(OSError):
        staged(folder, reader, base)
    assert not (folder / SEED_STAGING_DIR).exists()
