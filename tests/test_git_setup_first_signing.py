"""A first commit in a repository that requires signing: the intent and the refusal (plan Task 9a).

The product never signs, never makes the commit and never moves a ref on this road. Before it
shows the owner two commands it stores what the commands and the later recognition are judged
against, then refuses with the facts the commands are built from. The repeat of the same body
answers the same refusal from the STORED intent and writes nothing. Every test runs with the
route's confirm door held open until it opens for real, and with a throwaway key made in the
test's own folder (never a real key).
"""
from __future__ import annotations

import pytest

from conductor.command import git_setup_first
from conductor.command import git_setup_first_records as records
from conductor.command.accept_manifest import sha256
from conductor.command.api_refusals import ApiRefusal
from conductor.command.git_setup_first_index import verify
from conductor.command.git_setup_first_records import AWAITING_SIGNATURE
from conductor.command.git_setup_records import SetupRefused
from conductor.ownership import data_root
from tests.git_first_bench import confirm, confirm_door, op_file, seal, terms_of  # noqa: F401
from tests.git_first_signing import (
    FORMATS, command_lines, owner_makes_the_commit, run_owner, signing_key,  # noqa: F401
    signing_project, waits)
from tests.git_repo_helpers import needs_git, snapshot
from tests.test_git_setup import reason
from tests.test_git_setup_first_commit import install_files, no_receipt, text
from tests.test_git_setup_first_leftovers import a_restarted_server, setup_dir
from tests.test_git_setup_first_recovery import FILES, git_path, writes
from tests.test_git_setup_first_records import SHELL_READS
from tests.test_project_git_state import read

pytestmark = [needs_git, pytest.mark.usefixtures("confirm_door")]
for_both_modes = pytest.mark.parametrize("mode", ["snapshot", "empty"])
for_both_formats = pytest.mark.parametrize("fmt", FORMATS)
FOUR = {"reason", "tree", "target_ref", "message_path"}
SIGNING_WORDS = ("commit-tree", "update-ref", "-S", "--gpg-sign", "gpg", "ssh-keygen",
                 "verify-commit", "verify-tag")
MESSAGES = {"snapshot": "Первый коммит: 3 файлов (Conduct)\n\nConduct-Setup: first-commit\n",
            "empty": "Начало проекта (Conduct)\n\nConduct-Setup: first-commit\n"}


def only_objects_were_added(before: dict, after: dict) -> bool:
    """`.git` after equals `.git` before, but for the loose objects the preparation wrote."""
    return (all(after.get(name) == data for name, data in before.items())
            and all(name.startswith("objects/") for name in after if name not in before))


def calls_since(p, count):
    return [args for args, _ in p.spy.calls[count:]]


# --- the intent is stored before the commands are shown ---------------------------------------


@for_both_formats
@for_both_modes
def test_signing_required_stores_its_intent_before_it_refuses_and_names_the_two_commands(
        tmp_path, signing_key, mode, fmt):
    p = signing_project(tmp_path, signing_key, FILES, fmt=fmt)
    digest = terms_of(p, mode)
    before = snapshot(p.root / ".git")
    detail = waits(p, mode, digest)
    assert set(detail) == FOUR and detail["reason"] == "signing_required"
    assert detail["target_ref"] == "refs/heads/trunk"
    assert text(p, "cat-file", "-t", detail["tree"]) == "tree"
    message = (p.root / detail["message_path"]).read_bytes()
    assert message.decode("utf-8") == MESSAGES[mode]
    op = records.read_op(p.root)
    assert (op.stage, op.requested_by, op.mode, op.paths_digest, op.digest_version) == (
        AWAITING_SIGNATURE, "Owner", mode, digest, 2)
    assert (op.target_ref, op.object_format, op.expected_tree, op.commit) == (
        "refs/heads/trunk", fmt, detail["tree"], None)
    assert op.author == {"name": "First Author", "email": "first@example.invalid"}
    assert op.signing is True and op.message_sha256 == sha256(message)
    assert op.file_count == (3 if mode == "snapshot" else 0)
    assert verify(records.read_install(p.root, op), fmt).marker[0] == op.nonce
    assert only_objects_were_added(before, snapshot(p.root / ".git"))
    assert text(p, "rev-list", "--all") == "" and no_receipt(p)


@for_both_modes
def test_the_refusal_made_no_commit_no_ref_no_index_no_lock_no_copy_and_ran_no_signing_program(
        tmp_path, signing_key, mode):
    p = signing_project(tmp_path, signing_key, FILES)
    digest = terms_of(p, mode)
    asked = len(p.spy.calls)
    waits(p, mode, digest)
    waits(p, mode, digest)                                  # the repeat as well
    for word in SIGNING_WORDS:
        assert not [args for args in calls_since(p, asked) if word in args], word
    folder = p.root / ".git"
    assert not [path for path in (folder / "refs" / "heads").rglob("*") if path.is_file()]
    assert not git_path(p, "index").exists() and not git_path(p, "index.lock").exists()
    assert not list(folder.glob("conduct-first-index-*"))


@for_both_modes
def test_a_new_server_over_the_folder_still_finds_the_stored_intent_after_the_refusal(
        tmp_path, signing_key, mode):
    p = signing_project(tmp_path, signing_key, FILES)
    detail = waits(p, mode)
    pending = read(a_restarted_server(p))["first_commit_pending"]
    assert pending["state"] == "awaiting_signature"
    assert pending["signing"] == {key: detail[key] for key in sorted(FOUR - {"reason"})}
    assert pending["terms"]["requested_by"] == "Owner"


@for_both_modes
def test_the_repeat_answers_the_same_refusal_from_the_stored_intent_and_writes_nothing(
        tmp_path, signing_key, mode):
    p = signing_project(tmp_path, signing_key, FILES)
    digest = terms_of(p, mode)
    detail = waits(p, mode, digest)

    def world():
        return (snapshot(setup_dir(p)), snapshot(p.root / ".git"),
                snapshot(data_root(p.root) / "git"))

    stored, asked = world(), len(p.spy.calls)
    assert waits(p, mode, digest) == detail
    assert world() == stored
    assert not [args for args in calls_since(p, asked) if writes(args)]


# --- the vocabulary: a typed detail that admits four closed facts ------------------------------

TREE, PATH = "a" * 40, "conductor.v3/git/msg-first-" + "c" * 32 + ".txt"


def test_setup_signing_detail_admits_the_closed_typed_facts():
    shown = ApiRefusal.signing_required_setup(TREE, "refs/heads/trunk", PATH).as_dict()["error"]
    assert shown["code"] == "git_setup_refused" and shown["detail"] == {
        "reason": "signing_required", "tree": TREE, "target_ref": "refs/heads/trunk",
        "message_path": PATH}
    assert shown["message"] == "the Git setup step was refused: signing_required"
    assert ApiRefusal.signing_required_setup("b" * 64, "refs/heads/a/b-c_d.e",
                                             PATH.replace(".v3", ""))


@pytest.mark.parametrize("field, value", [
    *[("tree", tree) for tree in ("a" * 39, "A" * 40, "g" * 40, "a" * 41, "", TREE + "\n")],
    *[("target_ref", ref) for ref in (
        "refs/tags/x", "trunk", "refs/heads/", "refs/heads/a..b", "refs/heads/.a",
        "refs/heads/a.lock", "refs/heads/a/", "refs/heads/a//b", "refs/heads/a b",
        "refs/heads/a.", "refs/heads/" + "b" * 240, *SHELL_READS)],
    *[("message_path", path) for path in (
        "conductor/git/msg-acc-" + "c" * 32 + ".txt", "../conductor/git/msg-first-x.txt",
        "conductor/git/msg-first-" + "c" * 31 + ".txt", "/" + PATH, PATH + "x",
        "other/git/msg-first-" + "c" * 32 + ".txt", "C:/secret.txt", "")]])
def test_setup_signing_detail_refuses_a_fact_outside_its_closed_spelling(field, value):
    facts = dict(tree=TREE, target_ref="refs/heads/trunk", message_path=PATH) | {field: value}
    with pytest.raises(ValueError):
        ApiRefusal.signing_required_setup(**facts)


def test_setup_signing_detail_has_no_fifth_key_no_missing_key_and_no_other_reason():
    from conductor.command.api_refusals import _setup_signing_detail
    base = dict(reason="signing_required", tree=TREE, target_ref="refs/heads/trunk",
                message_path=PATH)
    assert _setup_signing_detail(base)
    for changed in ({**base, "extra": "x"}, {k: v for k, v in base.items() if k != "tree"},
                    {**base, "reason": "head_exists"}, {**base, "tree": 7}):
        assert not _setup_signing_detail(changed)


# --- a branch a shell could read is refused before anything is written -----------------------

#: The names of `SHELL_READS` that every file system takes as a file name (Windows refuses the
#: others: a quote, `<`, `>` and `|` cannot name a file).
ON_ANY_DISK = [ref for ref in SHELL_READS if not set(ref) & set('"<>|')] + [
    "refs/heads/x;y&z", "refs/heads/q`r's"]


@pytest.mark.parametrize("branch", ON_ANY_DISK)
def test_signing_on_a_branch_a_shell_could_read_is_refused_before_anything_is_written(
        tmp_path, signing_key, branch):
    p = signing_project(tmp_path, signing_key, FILES)
    p.git("symbolic-ref", "HEAD", branch, cwd=p.root)
    digest = terms_of(p)
    before = (snapshot(p.root / ".git"), snapshot(data_root(p.root) / "git"))
    asked = len(p.spy.calls)
    answer = confirm(p, digest=digest)
    assert reason(answer) == "signing_ref_unsupported"
    assert answer.payload["error"]["detail"] == {"reason": "signing_ref_unsupported"}
    assert (snapshot(p.root / ".git"), snapshot(data_root(p.root) / "git")) == before
    assert not [args for args in calls_since(p, asked) if writes(args)]
    assert not op_file(p).exists() and no_receipt(p)


def test_the_same_branch_without_required_signing_still_reaches_the_first_commit(
        tmp_path, signing_key):
    p = signing_project(tmp_path, signing_key, FILES)
    p.git("symbolic-ref", "HEAD", "refs/heads/a$(calc)", cwd=p.root)
    p.git("config", "commit.gpgsign", "false", cwd=p.root)
    answer = confirm(p)
    assert answer.status == 201, answer.payload
    assert answer.payload["setup"]["target_ref"] == "refs/heads/a$(calc)"
    assert answer.payload["setup"]["signature"] == "not_required"


# --- what the shown update-ref does ---------------------------------------------------------------


def test_the_shown_update_ref_command_creates_a_branch_that_does_not_exist(tmp_path, signing_key):
    p = signing_project(tmp_path, signing_key, FILES)
    detail = waits(p)
    oid = owner_makes_the_commit(p, detail, unsigned=True, publish=False)
    shown = command_lines(detail, oid)[1]
    assert shown.split()[-1] == "0" * len(detail["tree"])
    assert run_owner(p, shown).returncode == 0
    assert text(p, "rev-parse", detail["target_ref"]) == oid


def test_the_shown_update_ref_command_leaves_a_branch_made_in_the_meantime_where_it_is(
        tmp_path, signing_key):
    p = signing_project(tmp_path, signing_key, FILES)
    detail = waits(p)
    oid = owner_makes_the_commit(p, detail, unsigned=True, publish=False)
    other = text(p, "commit-tree", "-m", "made meanwhile", detail["tree"])
    p.git("update-ref", detail["target_ref"], other, cwd=p.root)
    assert run_owner(p, command_lines(detail, oid)[1]).returncode != 0
    assert text(p, "rev-parse", detail["target_ref"]) == other


def test_calibration_the_command_without_the_zero_object_id_would_overwrite_that_branch(
        tmp_path, signing_key):
    p = signing_project(tmp_path, signing_key, FILES)
    detail = waits(p)
    oid = owner_makes_the_commit(p, detail, unsigned=True, publish=False)
    other = text(p, "commit-tree", "-m", "made meanwhile", detail["tree"])
    p.git("update-ref", detail["target_ref"], other, cwd=p.root)
    without_the_old_value = command_lines(detail, oid)[1].rsplit(" ", 1)[0]
    assert run_owner(p, without_the_old_value).returncode == 0
    assert text(p, "rev-parse", detail["target_ref"]) == oid != other          # the violation


# --- the wait is not the driver's, and a changed term replaces it only through its own road -----


def test_a_wait_for_a_signature_never_reaches_the_drivers_table_or_the_ordinary_supersede(
        tmp_path, signing_key, monkeypatch):
    p = signing_project(tmp_path, signing_key, FILES)
    digest = terms_of(p)
    detail = waits(p, "snapshot", digest)

    def never(*args, **keywords):
        raise AssertionError("a wait was routed into the ordinary road")

    for name in ("drive", "_resume", "_supersede"):
        monkeypatch.setattr(git_setup_first, name, never)
    assert waits(p, "snapshot", digest) == detail
    p.git("config", "user.name", "Second Author", cwd=p.root)       # a changed term, no ref yet
    assert reason(confirm(p, digest=digest)) == "signing_required"
    assert records.read_op(p.root).author["name"] == "Second Author"


def test_the_ordinary_supersede_refuses_a_wait_and_leaves_every_file_where_it_is(
        tmp_path, signing_key):
    p = signing_project(tmp_path, signing_key, FILES)
    detail = waits(p)
    op = records.read_op(p.root)

    def world():
        return (snapshot(setup_dir(p)), snapshot(p.root / ".git"),
                (p.root / detail["message_path"]).read_bytes())

    stored = world()
    with pytest.raises(SetupRefused) as refused:
        git_setup_first._supersede(p.api, op)
    assert refused.value.reason == "setup_damaged" and world() == stored


def test_a_changed_term_replaces_the_wait_with_a_new_intent_and_removes_the_old_files(
        tmp_path, signing_key):
    p = signing_project(tmp_path, signing_key, FILES)
    old_detail = waits(p, "snapshot", terms_of(p))
    old = records.read_op(p.root)
    (p.root / "new.txt").write_bytes(b"fresh\n")
    new_digest = seal(p)["paths_digest"]
    answer = confirm(p, digest=new_digest)
    assert reason(answer) == "signing_required"
    new = records.read_op(p.root)
    assert (new.stage, new.paths_digest) == (AWAITING_SIGNATURE, new_digest) and (
        new.nonce != old.nonce)
    assert answer.payload["error"]["detail"]["tree"] == new.expected_tree != old_detail["tree"]
    assert [path.name for path in install_files(p)] == [f"first_commit.index-{new.nonce}"]
    assert (p.root / answer.payload["error"]["detail"]["message_path"]).exists()


def test_a_changed_term_removes_the_message_file_of_the_old_wait_when_the_new_message_differs(
        tmp_path, signing_key):
    p = signing_project(tmp_path, signing_key, FILES)
    old_detail = waits(p, "snapshot", terms_of(p))
    (p.root / "new.txt").write_bytes(b"fresh\n")
    answer = confirm(p, digest=seal(p)["paths_digest"])         # four files now: another message
    new_detail = answer.payload["error"]["detail"]
    assert new_detail["message_path"] != old_detail["message_path"]
    assert not (p.root / old_detail["message_path"]).exists()
    assert (p.root / new_detail["message_path"]).exists()


def test_a_changed_term_never_removes_a_message_file_that_is_not_the_one_the_wait_wrote(
        tmp_path, signing_key):
    p = signing_project(tmp_path, signing_key, FILES)
    digest = terms_of(p)
    detail = waits(p, "snapshot", digest)
    (p.root / detail["message_path"]).write_bytes(b"another message\n")
    p.git("config", "user.name", "Second Author", cwd=p.root)      # a changed term, no ref yet
    assert reason(confirm(p, digest=digest)) == "setup_damaged"
    assert (p.root / detail["message_path"]).read_bytes() == b"another message\n"


def test_a_wait_whose_message_file_is_gone_is_setup_damaged_and_nothing_is_removed(
        tmp_path, signing_key):
    p = signing_project(tmp_path, signing_key, FILES)
    digest = terms_of(p)
    detail = waits(p, "snapshot", digest)
    (p.root / detail["message_path"]).unlink()
    stored = (snapshot(setup_dir(p)), snapshot(p.root / ".git"))
    assert reason(confirm(p, digest=digest)) == "setup_damaged"
    assert (snapshot(setup_dir(p)), snapshot(p.root / ".git")) == stored


def test_a_wait_whose_message_file_was_edited_is_setup_damaged_and_nothing_is_removed(
        tmp_path, signing_key):
    p = signing_project(tmp_path, signing_key, FILES)
    digest = terms_of(p)
    detail = waits(p, "snapshot", digest)
    (p.root / detail["message_path"]).write_bytes(b"another message\n")
    stored = (snapshot(setup_dir(p)), snapshot(p.root / ".git"))
    assert reason(confirm(p, digest=digest)) == "setup_damaged"
    assert (snapshot(setup_dir(p)), snapshot(p.root / ".git")) == stored


def test_a_wait_whose_tree_object_is_gone_is_setup_damaged_and_nothing_is_removed(
        tmp_path, signing_key):
    p = signing_project(tmp_path, signing_key, FILES)
    digest = terms_of(p)
    tree = waits(p, "snapshot", digest)["tree"]
    loose = p.root / ".git" / "objects" / tree[:2] / tree[2:]
    loose.chmod(0o666)                                       # Git writes its objects read-only
    loose.unlink()
    stored = snapshot(setup_dir(p))
    assert reason(confirm(p, digest=digest)) == "setup_damaged"
    assert snapshot(setup_dir(p)) == stored
