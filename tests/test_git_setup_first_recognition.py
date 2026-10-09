"""The way back of a required signature: the owner's signed root commit is recognised (Task 9b).

After the owner runs the two shown commands, the same confirm body recognises their commit by the
terms STORED with the intent, never by a new preview, and installs the index through the driver of
the unsigned road: the product moves no ref in this road. What is checked of the signature is that
a signature header is PRESENT (the first line of its value is an armour line). Its validity and the
trust of its key are not checked, and no program that could check them is run. The samples are
real: a throwaway key made in the test's own folder signs the commit, and the same commands without
`-S` are the negative control. The pure judgement is tested on commits written by hand.
"""
from __future__ import annotations

import subprocess

import pytest

from conductor.command import git_setup_first, git_setup_first_signing as signing
from conductor.command import git_setup_first_records as records
from conductor.command.git_setup_first_index import verify
from conductor.command.git_setup_first_records import AWAITING_SIGNATURE
from conductor.ownership import data_root
from tests.git_first_bench import (  # noqa: F401
    confirm, confirm_door, crash_after, terms_of)
from tests.git_first_readers import READERS
from tests.git_first_signing import (  # noqa: F401
    command_lines, owner_environment, owner_makes_the_commit, run_owner, signing_key,
    signing_project, waits)
from tests.git_repo_helpers import GIT, needs_git, snapshot
from tests.test_git_setup import reason
from tests.test_git_setup_first_commit import no_receipt, own_leftovers, text
from tests.test_git_setup_first_recovery import (
    FILES, GRID, expected_status, git_path, own_copies)
from tests.test_git_setup_first_records import TREE, an_op

MESSAGE = b"First commit (Conduct)\n\nConduct-Setup: first-commit\n"
WHEN = "1791531279 +0300"
SSH = "-----BEGIN SSH SIGNATURE-----\nU1NIU0lH\n-----END SSH SIGNATURE-----"
PGP = "-----BEGIN PGP SIGNATURE-----\n\niQEzBAABCAAdFiEE\n-----END PGP SIGNATURE-----"
X509 = "-----BEGIN SIGNED MESSAGE-----\nMIAGCSqGSIb3\n-----END SIGNED MESSAGE-----"
VERIFYING = ("verify-commit", "verify-tag", "--show-signature", "gpg", "ssh-keygen", "log", "show")


# --- the pure judgement, on commits written by hand ------------------------------------------


def raw_commit(tree=TREE, *, parents=(), authors=None, committer="Someone <else@x.invalid>",
               signature=SSH, key="gpgsig", message=MESSAGE) -> bytes:
    """A commit object as `git cat-file commit` prints it: signature lines continued by a space."""
    authors = [f"First Author <first@example.invalid> {WHEN}"] if authors is None else authors
    lines = [f"tree {tree}", *[f"parent {oid}" for oid in parents],
             *[f"author {row}" for row in authors], f"committer {committer} {WHEN}"]
    if signature is not None:
        head, *rest = signature.split("\n")
        lines += [f"{key} {head}", *[" " + row for row in rest]]
    return ("\n".join(lines) + "\n\n").encode("utf-8") + message


def a_wait(fmt="sha1"):
    return an_op(stage=AWAITING_SIGNATURE, commit=None, signing=True, object_format=fmt,
                 expected_tree="a" * (40 if fmt == "sha1" else 64))


@pytest.mark.parametrize("signature", [SSH, PGP, X509], ids=["ssh", "pgp", "x509"])
@pytest.mark.parametrize("fmt, key", [("sha1", "gpgsig"), ("sha256", "gpgsig-sha256")])
def test_recognition_accepts_the_intended_commit_signed_in_any_armour_in_either_format(
        fmt, key, signature):
    op = a_wait(fmt)
    assert signing.recognises(
        raw_commit(op.expected_tree, signature=signature, key=key), op, MESSAGE)


def test_recognition_does_not_compare_the_committer():
    op = a_wait()
    assert signing.recognises(raw_commit(op.expected_tree, committer="Another <a@b.invalid>"),
                              op, MESSAGE)


ONE_TERM = {
    "tree": dict(tree="b" * 40), "parent": dict(parents=("c" * 40,)),
    "no_author": dict(authors=[]),
    "two_authors": dict(authors=[f"First Author <first@example.invalid> {WHEN}"] * 2),
    "author_name": dict(authors=[f"Second Author <first@example.invalid> {WHEN}"]),
    "author_email": dict(authors=[f"First Author <second@example.invalid> {WHEN}"]),
    "author_shape": dict(authors=["First Author first@example.invalid 1791531279 +0300"]),
    "message_cut": dict(message=MESSAGE[:-1]), "message_added": dict(message=MESSAGE + b"x"),
    "message_byte": dict(message=MESSAGE.replace(b"first", b"First")),
    "no_message": dict(message=b""), "unsigned": dict(signature=None),
    "not_an_armour": dict(signature="not an armour\nU1NIU0lH"),
    "other_armour": dict(signature="-----BEGIN PGP MESSAGE-----\nabc"),
    "empty_header": dict(signature=""),
    "wrong_header_for_sha1": dict(key="gpgsig-sha256"), "other_header": dict(key="signature")}


@pytest.mark.parametrize("change", ONE_TERM.values(), ids=ONE_TERM.keys())
def test_recognition_refuses_a_sha1_commit_that_differs_in_one_term(change):
    op = a_wait()
    fields = {"tree": op.expected_tree} | change
    assert not signing.recognises(raw_commit(**fields), op, MESSAGE)


def test_recognition_refuses_the_signature_header_of_the_other_format():
    sha256, sha1 = a_wait("sha256"), a_wait()
    assert not signing.recognises(raw_commit(sha256.expected_tree, key="gpgsig"), sha256, MESSAGE)
    assert not signing.recognises(raw_commit(sha1.expected_tree, key="gpgsig-sha256"), sha1,
                                  MESSAGE)


def test_recognition_refuses_two_signature_headers_and_objects_that_are_no_commit():
    op = a_wait()
    second = b"gpgsig -----BEGIN SSH SIGNATURE-----\n U1NIU0lH\n -----END SSH SIGNATURE-----\n"
    twice = raw_commit(op.expected_tree).replace(b"\n\n", b"\n" + second + b"\n", 1)
    assert twice.count(b"\ngpgsig ") == 2 and not signing.recognises(twice, op, MESSAGE)
    for garbage in (b"", b"tree " + b"a" * 40, b"tree \xff\xfe\n\n" + MESSAGE, b"\n\n" + MESSAGE):
        assert not signing.recognises(garbage, op, MESSAGE)


# --- real samples: a key made for this test signs, the same commands without -S do not ---------


def project_waiting(tmp_path, key, mode="snapshot", fmt="sha1", which="current"):
    """A signing project, its confirmation digest and the facts of the first refusal."""
    p = signing_project(tmp_path, key, FILES, fmt=fmt, which=which)
    digest = terms_of(p, mode)
    return p, digest, waits(p, mode, digest)


def product_moves(p):
    """The calls of the PRODUCT's Git that made a commit or moved a ref."""
    return [args for args, _ in p.spy.calls if "update-ref" in args or "commit-tree" in args]


def world(p):
    return (snapshot(data_root(p.root) / "git" / "setup"), snapshot(p.root / ".git" / "refs"))


@pytest.mark.parametrize("which", READERS)
@pytest.mark.parametrize("mode, fmt", GRID)
@needs_git
@pytest.mark.usefixtures("confirm_door")
def test_a_really_signed_first_commit_is_recognised_and_its_index_installed(
        tmp_path, signing_key, mode, fmt, which):
    p, digest, detail = project_waiting(tmp_path, signing_key, mode, fmt, which)
    nonce = records.read_op(p.root).nonce
    oid = owner_makes_the_commit(p, detail)
    answer = confirm(p, mode, digest=digest)
    assert answer.status == 201, answer.payload
    receipt = answer.payload["setup"]
    assert (receipt["commit"], receipt["signature"], receipt["target_ref"]) == (
        oid, "present", "refs/heads/trunk")
    assert (receipt["mode"], receipt["object_format"], receipt["tree"]) == (
        mode, fmt, detail["tree"])
    header = "gpgsig-sha256" if fmt == "sha256" else "gpgsig"
    raw = p.git("cat-file", "commit", oid, cwd=p.root).stdout.decode("utf-8")
    assert f"{header} -----BEGIN SSH SIGNATURE-----" in raw
    index = git_path(p, "index")
    assert verify(index.read_bytes(), fmt).marker[0] == nonce        # before any owner command
    assert text(p, "--no-optional-locks", "status", "--porcelain") == expected_status(mode)
    assert verify(index.read_bytes(), fmt).marker[0] == nonce        # the read left it alone
    assert text(p, "rev-list", "--count", "HEAD") == "1" and own_leftovers(p) == []
    assert product_moves(p) == [] and not no_receipt(p)


@needs_git
@pytest.mark.usefixtures("confirm_door")
def test_an_unsigned_commit_that_matches_in_everything_else_is_head_exists_not_a_signed_commit(
        tmp_path, signing_key):
    p, digest, detail = project_waiting(tmp_path, signing_key)
    owner_makes_the_commit(p, detail, unsigned=True)
    stored = world(p)
    assert reason(confirm(p, digest=digest)) == "head_exists"
    assert not git_path(p, "index").exists() and not git_path(p, "index.lock").exists()
    assert no_receipt(p) and world(p) == stored and not own_copies(p)
    assert records.read_op(p.root).stage == AWAITING_SIGNATURE
    assert reason(confirm(p, digest=digest)) == "head_exists"          # and the same again


def an_empty_tree(p) -> str:
    """The tree of an empty index, written to the repository: not the tree that was shown."""
    scratch = str(p.root.parent / "no-such-index")
    made = subprocess.run([GIT, "write-tree"], cwd=p.root, capture_output=True, check=True,
                          env={**owner_environment(), "GIT_INDEX_FILE": scratch})
    return made.stdout.decode().strip()


def commit_by_hand(p, detail, *, tree=None, parents=(), message=None, author=None) -> str:
    """The owner's commit, signed for real, with ONE thing changed from the shown commands."""
    source = detail["message_path"]
    if message is not None:
        source = str(p.root.parent / "other-message.txt")
        (p.root.parent / "other-message.txt").write_bytes(message)
    args = ["commit-tree", tree or detail["tree"], "-S",
            *[word for parent in parents for word in ("-p", parent)], "-F", source]
    made = subprocess.run([GIT, *args], cwd=p.root, capture_output=True, check=False,
                          env={**owner_environment(), **(author or {})})
    assert made.returncode == 0, made.stderr.decode(errors="replace")
    oid = made.stdout.decode().strip()
    moved = run_owner(p, command_lines(detail, oid)[1])
    assert moved.returncode == 0, moved.stderr.decode(errors="replace")
    return oid


@needs_git
@pytest.mark.usefixtures("confirm_door")
@pytest.mark.parametrize("difference", ["tree", "parent", "message_byte", "author_name",
                                        "author_email"])
def test_a_signed_commit_that_differs_in_tree_parent_message_or_author_is_head_exists(
        tmp_path, signing_key, difference):
    p, digest, detail = project_waiting(tmp_path, signing_key)
    stored = (p.root / detail["message_path"]).read_bytes()
    if difference == "tree":
        one = commit_by_hand(p, detail, tree=an_empty_tree(p))
    elif difference == "parent":
        one = commit_by_hand(p, detail, parents=(
            text(p, "commit-tree", "-m", "a parent", an_empty_tree(p)),))
    elif difference == "message_byte":
        one = commit_by_hand(p, detail, message=stored.replace(b"first", b"First"))
    else:
        field = {"author_name": "GIT_AUTHOR_NAME", "author_email": "GIT_AUTHOR_EMAIL"}[difference]
        one = commit_by_hand(p, detail, author={field: "someone-else@example.invalid"})
    assert text(p, "rev-parse", detail["target_ref"]) == one
    assert reason(confirm(p, digest=digest)) == "head_exists"
    assert not git_path(p, "index").exists() and not git_path(p, "index.lock").exists()
    assert records.read_op(p.root).stage == AWAITING_SIGNATURE and no_receipt(p)


@needs_git
@pytest.mark.usefixtures("confirm_door")
def test_a_header_that_is_no_armour_does_not_pass_as_a_signature_even_with_everything_else_right(
        tmp_path, signing_key):
    p, digest, detail = project_waiting(tmp_path, signing_key)
    real = owner_makes_the_commit(p, detail, publish=False)
    raw = p.git("cat-file", "commit", real, cwd=p.root).stdout
    forged = raw.replace(b"-----BEGIN SSH SIGNATURE-----", b"-----BEGIN NOTHING-----", 1)
    assert forged != raw
    made = subprocess.run([GIT, "hash-object", "-t", "commit", "-w", "--stdin"], input=forged,
                          cwd=p.root, capture_output=True, check=True, env=owner_environment())
    assert run_owner(p, command_lines(detail, made.stdout.decode().strip())[1]).returncode == 0
    assert reason(confirm(p, digest=digest)) == "head_exists" and no_receipt(p)


@needs_git
@pytest.mark.usefixtures("confirm_door")
@pytest.mark.parametrize("crash, status", [("_do_take_lock", 201), ("_do_install_index", 201),
                                           ("_do_finish", 200)])
def test_the_recognised_commit_enters_the_same_install_driver_and_resumes_from_its_faults(
        tmp_path, monkeypatch, signing_key, crash, status):
    p, digest, detail = project_waiting(tmp_path, signing_key)
    nonce = records.read_op(p.root).nonce
    oid = owner_makes_the_commit(p, detail)
    restart = crash_after(monkeypatch, crash, owner=git_setup_first)
    assert confirm(p, digest=digest).status == 500
    restart()
    again = confirm(p, digest=digest)
    assert again.status == status, again.payload
    assert again.payload["setup"]["commit"] == oid
    assert verify(git_path(p, "index").read_bytes(), "sha1").marker[0] == nonce
    assert text(p, "rev-list", "--count", "HEAD") == "1" and own_leftovers(p) == []
    assert product_moves(p) == [] and text(p, "status", "--porcelain") == ""


@needs_git
@pytest.mark.usefixtures("confirm_door")
def test_the_verification_level_is_stated_and_the_product_runs_no_verifying_program(
        tmp_path, signing_key):
    p, digest, detail = project_waiting(tmp_path, signing_key)
    owner_makes_the_commit(p, detail)
    asked = len(p.spy.calls)
    answer = confirm(p, digest=digest)
    assert answer.payload["setup"]["signature"] == "present"          # present, not verified
    seen = [args for args, _ in p.spy.calls[asked:]]
    assert seen and not [args for args in seen for word in VERIFYING if word in args]
    assert not [args for args in seen if "-S" in args or "--gpg-sign" in args]
