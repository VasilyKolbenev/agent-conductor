"""A confirmed snapshot creates one branch; retry and crash recovery cannot rewrite owner work."""
import os

import pytest

from conductor.command import accept_commit
from conductor.command.accept_cache import AcceptancePreviews
from conductor.command.accept_manifest import SnapshotRefused
from conductor.command.adapters.process import ProcessRunner
from conductor.command.api_refusals import ApiRefusal
from conductor.command.git_index import temporary_index
from conductor.command.project_git import process_git_read
from conductor.command.run_store import StoreError
from conductor.ownership import data_root
from tests.git_repo_helpers import GIT, ISOLATED, KEPT, git, needs_git, snapshot
from tests.test_accept_context import RUN, TASK
from tests.test_accept_preview import PATH as PREVIEW, project
from tests.test_command_http_api import post

PATH = f"/command/runs/{RUN}/accept/commit"


def prepared(tmp_path):
    api, root, work, saved = project(tmp_path)
    cwd = data_root(root) / "git" / "cwd"
    cwd.mkdir(parents=True)
    hooks = cwd.parent / "hooks-empty"
    hooks.mkdir()
    runner = ProcessRunner(root, environ={name: os.environ[name] for name in KEPT if name in os.environ})
    api._project_git = process_git_read(runner, GIT, str(cwd), env_allow=KEPT, index_root=root,
        env={**ISOLATED, "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.hooksPath",
             "GIT_CONFIG_VALUE_0": str(hooks)})
    return api, root, work, saved


def confirm(api, digest, actor="Owner"):
    return post(api, PATH, {"accept_digest": digest, "actor": actor})


@needs_git
def test_confirm_creates_exact_branch_and_keeps_head_owner_index_worktree_and_hooks(tmp_path):
    api, root, work, saved = prepared(tmp_path)
    (root / "owner.txt").write_bytes(b"staged owner bytes\n")
    git("add", "owner.txt", cwd=root)
    (root / "old.txt").write_bytes(b"unstaged owner bytes\n")
    hook = root / ".git" / "hooks" / "reference-transaction"
    hook.write_text("#!/bin/sh\necho escaped > hook-ran\nexit 1\n", encoding="utf-8")
    if os.name != "nt":
        hook.chmod(0o755)
    head = git("rev-parse", "HEAD", cwd=root).stdout
    index = (root / ".git" / "index").read_bytes()
    digest = post(api, PREVIEW, {"branch": "conduct/chosen", "title": "Chosen title"}).payload["accept"]["accept_digest"]
    answer = confirm(api, digest)
    assert answer.status == 201, answer.payload
    record = answer.payload["commit"]
    assert record["branch"] == "conduct/chosen"
    assert git("show", "conduct/chosen:old.txt", cwd=root).stdout == b"reviewed\n"
    assert git("show", "conduct/chosen:new.txt", cwd=root).stdout == b"new bytes\n"
    assert git("cat-file", "-e", "conduct/chosen:gone.txt", cwd=root, check=False).returncode != 0
    assert git("cat-file", "-e", "conduct/chosen:ignored.txt", cwd=root, check=False).returncode != 0
    assert git("rev-parse", "HEAD", cwd=root).stdout == head
    assert (root / ".git" / "index").read_bytes() == index
    assert (root / "old.txt").read_bytes() == b"unstaged owner bytes\n"
    assert not (root / "hook-ran").exists()
    assert not list((data_root(root) / "git").glob("index-*"))
    before = snapshot(root / ".git")
    assert confirm(api, digest).payload == answer.payload
    assert confirm(api, digest).status == 200
    assert snapshot(root / ".git") == before
    other = confirm(api, "sha256:" + "f" * 64)
    assert other.payload["error"]["detail"]["reason"] == "acceptance_exists"


@needs_git
def test_changed_work_and_lost_cache_refuse_before_any_git_write_or_intent(tmp_path):
    api, root, work, saved = prepared(tmp_path)
    digest = post(api, PREVIEW, {}).payload["accept"]["accept_digest"]
    before = snapshot(root / ".git")
    (work / "new.txt").write_bytes(b"unreviewed")
    assert confirm(api, digest).payload["error"]["detail"]["reason"] == "work_changed_since_verification"
    (work / "new.txt").write_bytes(b"new bytes\n")
    api._accept_previews = AcceptancePreviews()
    assert confirm(api, digest).payload["error"]["detail"]["reason"] == "accept_terms_changed"
    assert snapshot(root / ".git") == before
    assert not list((data_root(root) / "accept" / RUN).glob("intent-*"))


@needs_git
def test_crash_after_ref_recovers_same_actor_digest_without_creating_a_second_commit(tmp_path, monkeypatch):
    api, root, work, saved = prepared(tmp_path)
    digest = post(api, PREVIEW, {"branch": "conduct/recover"}).payload["accept"]["accept_digest"]
    original = accept_commit.write_commit
    def crash(*args):
        raise StoreError("simulated interruption after CAS")
    monkeypatch.setattr(accept_commit, "write_commit", crash)
    assert confirm(api, digest).status == 500
    object_id = git("rev-parse", "conduct/recover", cwd=root).stdout
    api._accept_previews = AcceptancePreviews()
    before = snapshot(root / ".git")
    assert confirm(api, digest, actor="Other").payload["error"]["detail"]["reason"] == "accept_terms_changed"
    monkeypatch.setattr(accept_commit, "write_commit", original)
    answer = confirm(api, digest)
    assert answer.status == 201, answer.payload
    assert answer.payload["commit"]["commit"].encode() + b"\n" == object_id
    assert snapshot(root / ".git") == before


@needs_git
def test_prior_intent_ref_blocks_a_second_acceptance_and_corrupt_intent_is_never_skipped(tmp_path, monkeypatch):
    api, root, work, saved = prepared(tmp_path)
    first = post(api, PREVIEW, {"branch": "conduct/first"}).payload["accept"]["accept_digest"]
    monkeypatch.setattr(accept_commit, "write_commit", lambda *args: (_ for _ in ()).throw(StoreError("crash")))
    assert confirm(api, first).status == 500
    second = post(api, PREVIEW, {"branch": "conduct/second"}).payload["accept"]["accept_digest"]
    before = snapshot(root / ".git")
    assert confirm(api, second).payload["error"]["detail"]["reason"] == "acceptance_exists"
    assert snapshot(root / ".git") == before
    intent = next((data_root(root) / "accept" / RUN).glob("intent-*"))
    intent.write_bytes(b"damaged\n")
    assert confirm(api, second).payload["error"]["code"] == "run_corrupt"
    assert snapshot(root / ".git") == before


@needs_git
@pytest.mark.parametrize("changed", ["tree", "parent", "author", "message"])
def test_existing_foreign_ref_is_never_adopted_from_a_matching_trailer_alone(tmp_path, monkeypatch, changed):
    api, root, work, saved = prepared(tmp_path)
    view = post(api, PREVIEW, {}).payload["accept"]
    digest = view["accept_digest"]
    monkeypatch.setattr(accept_commit, "write_commit", lambda *args: (_ for _ in ()).throw(StoreError("crash")))
    assert confirm(api, digest).status == 500
    branch = f"conduct/{RUN}"
    accepted = git("rev-parse", branch, cwd=root).stdout.decode().strip()
    message = view["message"] + ("unreviewed extra text\n" if changed == "message" else "")
    (root / "message.txt").write_bytes(message.encode("utf-8"))
    # Keep the acceptance trailer, changing exactly one of the other recovery facts.
    tree = "HEAD^{tree}" if changed == "tree" else accepted + "^{tree}"
    author = [] if changed == "author" else ["-c", "user.name=Preview Author", "-c", "user.email=author@example.invalid"]
    parent = [] if changed == "parent" else ["-p", view["base"]["commit"]]
    foreign = git(*author, "commit-tree", tree, *parent, "-F", "message.txt", cwd=root).stdout.decode().strip()
    git("update-ref", "refs/heads/" + branch, foreign, accepted, cwd=root)
    before = snapshot(root / ".git")
    answer = confirm(api, digest)
    assert answer.payload["error"]["detail"]["reason"] == "branch_exists"
    assert snapshot(root / ".git") == before


def test_cache_is_bounded_and_detached_from_the_caller():
    cache = AcceptancePreviews(limit=2)
    options = {"documents": ["artifact-one"]}
    cache.remember("run", "first", options)
    options["documents"].append("artifact-two")
    assert cache.read("run", "first") == {"documents": ["artifact-one"]}
    cache.remember("run", "second", {})
    cache.remember("run", "third", {})
    assert cache.read("run", "first") is None


@needs_git
def test_required_signing_returns_exact_safe_facts_without_commit_or_ref_and_allows_explicit_retry(tmp_path):
    api, root, work, saved = prepared(tmp_path)
    git("config", "commit.gpgSign", "true", cwd=root)
    view = post(api, PREVIEW, {}).payload["accept"]
    original, calls, written_trees = api._project_git, [], []
    def observed(args, *positional, **keywords):
        calls.append(tuple(args))
        answer = original(args, *positional, **keywords)
        if "write-tree" in args:
            written_trees.append(answer.output.decode().strip())
        return answer
    api._project_git = observed
    head = git("rev-parse", "HEAD", cwd=root).stdout
    refs = snapshot(root / ".git" / "refs")
    index = (root / ".git" / "index").read_bytes()
    answer = confirm(api, view["accept_digest"])
    assert answer.status == 409, answer.payload
    identity = view["message"].split("Conduct-Acceptance: ")[1].strip()
    message_path = f"{data_root(root).name}/git/msg-{identity}.txt"
    assert answer.payload["error"] == {
        "code": "accept_refused", "message": "the result cannot be accepted: signing_required",
        "detail": {"reason": "signing_required", "tree": written_trees[0],
                   "base_commit": view["base"]["commit"], "branch": view["branch"],
                   "message_path": message_path}}
    assert (root / message_path).read_bytes() == view["message"].encode("utf-8")
    assert not any("commit-tree" in args or "update-ref" in args for args in calls)
    assert snapshot(root / ".git" / "refs") == refs
    assert git("rev-parse", "HEAD", cwd=root).stdout == head
    assert (root / ".git" / "index").read_bytes() == index
    assert not (data_root(root) / "accept" / RUN / "commit.json").exists()
    assert not list((data_root(root) / "git").glob("index-*"))
    # Simulate the owner's terminal-created exact commit without needing a signing key.
    object_id = git("-c", "user.name=Preview Author", "-c", "user.email=author@example.invalid",
                    "commit-tree", "--no-gpg-sign", written_trees[0], "-p", view["base"]["commit"],
                    "-F", message_path, cwd=root).stdout.decode().strip()
    git("update-ref", "refs/heads/" + view["branch"], object_id, cwd=root)
    api._accept_previews = AcceptancePreviews()
    calls.clear()
    retry = confirm(api, view["accept_digest"])
    assert retry.status == 201, retry.payload
    assert retry.payload["commit"]["commit"] == object_id
    assert not any("commit-tree" in args or "update-ref" in args for args in calls)


@pytest.mark.parametrize("field,value", [
    ("tree", "not-an-object"), ("base_commit", "b" * 64),
    ("branch", "conduct/name\nsecret"), ("branch", "conduct/../other"),
    ("branch", "conduct/name.lock"), ("message_path", "../secret.txt"),
    ("message_path", "C:/secret.txt"), ("message_path", "conductor.v3/git/msg-secret.txt")])
def test_signing_detail_admits_only_the_closed_typed_facts(field, value):
    facts = dict(tree="a" * 40, base_commit="b" * 40, branch="conduct/reviewed",
                 message_path="conductor.v3/git/msg-acc-" + "c" * 32 + ".txt")
    facts[field] = value
    with pytest.raises(ValueError):
        ApiRefusal.signing_required(**facts)


@needs_git
def test_broken_prior_intent_ref_is_not_treated_as_absent(tmp_path):
    api, root, work, saved = prepared(tmp_path)
    git("config", "commit.gpgSign", "true", cwd=root)
    first = post(api, PREVIEW, {"branch": "conduct/first"}).payload["accept"]["accept_digest"]
    assert confirm(api, first).payload["error"]["detail"]["reason"] == "signing_required"
    second = post(api, PREVIEW, {"branch": "conduct/second"}).payload["accept"]["accept_digest"]
    ref = root / ".git" / "refs" / "heads" / "conduct" / "first"
    ref.parent.mkdir(parents=True, exist_ok=True)
    ref.write_bytes(b"broken ref\n")
    before = snapshot(root / ".git")
    answer = confirm(api, second)
    assert answer.status == 409, answer.payload
    assert answer.payload["error"]["detail"]["reason"] == "git_failed"
    assert snapshot(root / ".git") == before
    assert len(list((data_root(root) / "accept" / RUN).glob("intent-*"))) == 1


def test_temporary_index_refuses_alias_and_cleanup_preserves_a_replaced_leaf(tmp_path):
    root = tmp_path.resolve()
    with pytest.raises(SnapshotRefused):
        with temporary_index(root, "acc-" + "a" * 32, "sha1") as owned:
            own_path = owned.path
            displaced = own_path.with_name("displaced-index")
            own_path.rename(displaced)
            own_path.write_bytes(b"foreign replacement")
            owned.environment(root)
    assert own_path.read_bytes() == b"foreign replacement"
    assert displaced.read_bytes().startswith(b"DIRC")
    with temporary_index(root, "acc-" + "b" * 32, "sha1") as owned:
        alias = owned.path.with_name("alias-index")
        os.link(owned.path, alias)
        try:
            with pytest.raises(SnapshotRefused):
                owned.environment(root)
        finally:
            alias.unlink()
    assert not owned.path.exists()
