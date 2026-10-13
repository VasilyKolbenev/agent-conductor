"""The stand-ins of the git block, held to the key sets of lane L's contract.

The desk's git block reads one route (`GET /command/project/git`, eleven keys) and talks to one
other (`POST /command/project/git/setup`, four closed bodies). The files under
`tests/fixtures/wizard/` are what the wizard's tests answer those asks with. Every key set below
is written BY HAND from the two handoffs that are the contract (`L-to-D1-D2-first-commit-pending.md`
sections 2-4 and `L-to-D2-first-commit-contract.md` sections 2-3), never read off a fixture, so a
stand-in that drifts from the contract turns a test red instead of quietly moving the desk with it.
`tests/test_desk_wizard_git_contract.py` holds the same files to what the real route answers.
"""
from __future__ import annotations

import re
from typing import Any

import pytest

from tests.desk_wizard_node import FIXTURES, fixture

WIZARD = FIXTURES / "wizard"
#: pending section 2: the eleven keys of the read; the eleventh is `first_commit_pending`.
GET_KEYS = {"state", "unsupported", "head", "object_format", "dirty_paths", "exclude",
            "agent_instructions", "remotes", "tools", "signing", "first_commit_pending"}
#: pending section 3: three closed shapes and the null.
PENDING = {"unfinished": {"state", "terms"}, "awaiting_signature": {"state", "terms", "signing"},
           "damaged": {"state"}}
TERMS = {"mode", "paths_digest", "digest_version", "requested_by", "file_count", "target_ref",
         "author"}
AUTHOR = {"name", "email"}
SIGNING = {"tree", "target_ref", "message_path"}
#: contract section 2: the preview, one file row, one manual row.
PREVIEW = {"step", "mode", "head", "target_ref", "object_format", "author", "signing", "files",
           "manual", "warnings", "digest_version", "paths_digest"}
FILE_ROW = {"path", "length", "sha256", "git_oid", "git_mode"}
MANUAL_ROW = {"path", "reason"}
#: contract section 3: the receipt of the first commit; and the receipt of `init` / `exclude`
#: (the shape of `git_setup_records.receipt`).
RECEIPT = {"schema_version", "step", "mode", "paths_digest", "digest_version", "target_ref",
           "commit", "tree", "object_format", "file_count", "signature", "requested_by",
           "recorded_at"}
STEP_RECEIPT = {"schema_version", "step", "requested_by", "recorded_at", "object_format",
                "exclude", "warnings"}

READS = ("git_repo", "git_unborn", "git_not_git", "git_not_repo_root", "git_unsupported",
         "git_unsafe_directory", "git_unavailable", "git_not_active")
PENDING_READS = ("git_pending_unfinished", "git_pending_unfinished_unborn", "git_pending_empty",
                 "git_pending_signature", "git_pending_signature_sha256", "git_pending_damaged")
SETUP = ("setup_receipt_init", "setup_preview_snapshot", "setup_preview_empty",
         "setup_preview_signing", "setup_receipt_commit", "setup_receipt_commit_signed")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
BRANCH = re.compile(r"refs/heads/[A-Za-z0-9._/-]+\Z")
MESSAGE = re.compile(r"conductor(?:\.v3)?/git/msg-first-[0-9a-f]{32}\.txt\Z")
INSTANT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z")


def keys(value: Any, expected: set[str], where: str) -> None:
    """The closed key set of one object: an extra key and a missing key are both a fault."""
    assert isinstance(value, dict), f"{where} is not an object"
    assert set(value) == expected, (
        f"{where}: extra {sorted(set(value) - expected)}, missing {sorted(expected - set(value))}")


def terms_hold(terms: Any, where: str) -> None:
    keys(terms, TERMS, where)
    keys(terms["author"], AUTHOR, where + ".author")
    assert terms["digest_version"] == 2
    assert (terms["paths_digest"] is None) == (terms["mode"] == "empty"), where
    assert terms["paths_digest"] is None or DIGEST.match(terms["paths_digest"]), where
    assert BRANCH.match(terms["target_ref"]), where
    assert isinstance(terms["file_count"], int) and 0 <= terms["file_count"] <= 5000, where


def pending_holds(pending: Any, where: str) -> None:
    if pending is None:
        return
    assert pending.get("state") in PENDING, f"{where}: {pending.get('state')!r}"
    keys(pending, PENDING[pending["state"]], where)
    if "terms" in pending:
        terms_hold(pending["terms"], where + ".terms")
    if "signing" in pending:
        keys(pending["signing"], SIGNING, where + ".signing")
        signing = pending["signing"]
        assert OID.match(signing["tree"]) and MESSAGE.match(signing["message_path"]), where
        assert BRANCH.match(signing["target_ref"]), where
        assert signing["target_ref"] == pending["terms"]["target_ref"], where
        assert len(signing["tree"]) in (40, 64), where


@pytest.mark.parametrize("name", [*READS, *PENDING_READS])
def test_every_git_read_stand_in_has_the_eleven_keys_of_the_route(name):
    read = fixture("wizard", f"{name}.json")
    keys(read, {"git"}, name)
    keys(read["git"], GET_KEYS, name)
    pending_holds(read["git"]["first_commit_pending"], name)


@pytest.mark.parametrize("name", READS)
def test_the_eight_state_stand_ins_say_no_first_commit_is_pending(name):
    assert fixture("wizard", f"{name}.json")["git"]["first_commit_pending"] is None


def test_a_pending_stand_in_stands_only_in_the_two_states_that_can_carry_it():
    found = {}
    for name in PENDING_READS:
        git = fixture("wizard", f"{name}.json")["git"]
        found[name] = (git["state"], git["first_commit_pending"]["state"])
    assert found == {
        "git_pending_unfinished": ("repo", "unfinished"),
        "git_pending_unfinished_unborn": ("unborn", "unfinished"),
        "git_pending_empty": ("unborn", "unfinished"),
        "git_pending_signature": ("unborn", "awaiting_signature"),
        "git_pending_signature_sha256": ("unborn", "awaiting_signature"),
        "git_pending_damaged": ("repo", "damaged")}


def test_the_empty_pending_stand_in_carries_a_null_digest_and_the_snapshot_ones_a_digest():
    empty = fixture("wizard", "git_pending_empty.json")["git"]["first_commit_pending"]["terms"]
    assert empty["mode"] == "empty" and empty["paths_digest"] is None
    snapshot = fixture("wizard", "git_pending_unfinished.json")
    terms = snapshot["git"]["first_commit_pending"]["terms"]
    assert terms["mode"] == "snapshot" and DIGEST.match(terms["paths_digest"])


def test_the_two_signature_stand_ins_differ_in_the_length_of_the_tree_and_say_the_format():
    sha1 = fixture("wizard", "git_pending_signature.json")["git"]
    sha256 = fixture("wizard", "git_pending_signature_sha256.json")["git"]
    assert (len(sha1["first_commit_pending"]["signing"]["tree"]),
            len(sha256["first_commit_pending"]["signing"]["tree"])) == (40, 64)
    assert (sha1["object_format"], sha256["object_format"]) == ("sha1", "sha256")
    assert sha1["signing"] is True and sha256["signing"] is True


def preview_holds(preview: Any, where: str) -> None:
    keys(preview, PREVIEW, where)
    assert preview["step"] == "first_commit" and preview["head"] is None, where
    assert preview["mode"] in ("snapshot", "empty") and preview["digest_version"] == 2, where
    assert DIGEST.match(preview["paths_digest"]), where
    assert preview["target_ref"].startswith("refs/heads/") and len(preview["target_ref"]) > 11
    keys(preview["author"], AUTHOR, where + ".author")
    assert isinstance(preview["signing"], bool), where
    for row in preview["files"]:
        keys(row, FILE_ROW, where + ".files")
        assert DIGEST.match(row["sha256"]) and OID.match(row["git_oid"]), where
        assert row["git_mode"] in ("100644", "100755") and row["length"] >= 0, where
    for row in preview["manual"]:
        keys(row, MANUAL_ROW, where + ".manual")
    assert preview["warnings"] == sorted(set(preview["warnings"])), where
    assert set(preview["warnings"]) <= {"signing_required", "suspicious_name",
                                        "nested_repository"}, where
    if preview["mode"] == "empty":
        assert preview["files"] == [] and preview["manual"] == [], where


@pytest.mark.parametrize("name", ("setup_preview_snapshot", "setup_preview_empty",
                                  "setup_preview_signing"))
def test_every_preview_stand_in_has_the_twelve_keys_and_the_rows_of_the_contract(name):
    body = fixture("wizard", f"{name}.json")
    keys(body, {"setup"}, name)
    preview_holds(body["setup"], name)


def test_the_preview_stand_ins_cover_a_manual_row_a_suspicious_name_and_a_signing_warning():
    snapshot = fixture("wizard", "setup_preview_snapshot.json")["setup"]
    assert snapshot["mode"] == "snapshot" and len(snapshot["files"]) >= 3
    assert snapshot["manual"] and "suspicious_name" in snapshot["warnings"]
    empty = fixture("wizard", "setup_preview_empty.json")["setup"]
    assert empty["mode"] == "empty" and empty["files"] == [] and empty["warnings"] == []
    signing = fixture("wizard", "setup_preview_signing.json")["setup"]
    assert signing["signing"] is True and "signing_required" in signing["warnings"]


@pytest.mark.parametrize("name", ("setup_receipt_commit", "setup_receipt_commit_signed"))
def test_every_commit_receipt_stand_in_has_the_thirteen_keys(name):
    body = fixture("wizard", f"{name}.json")
    keys(body, {"setup"}, name)
    receipt = body["setup"]
    keys(receipt, RECEIPT, name)
    assert receipt["schema_version"] == 1 and receipt["step"] == "first_commit"
    assert receipt["digest_version"] == 2 and INSTANT.match(receipt["recorded_at"])
    assert OID.match(receipt["commit"]) and OID.match(receipt["tree"])
    assert (receipt["paths_digest"] is None) == (receipt["mode"] == "empty")
    assert receipt["signature"] in ("not_required", "present")


def test_the_two_receipt_stand_ins_say_not_required_and_present():
    plain = fixture("wizard", "setup_receipt_commit.json")["setup"]
    signed = fixture("wizard", "setup_receipt_commit_signed.json")["setup"]
    assert (plain["signature"], signed["signature"]) == ("not_required", "present")


def test_the_init_receipt_stand_in_has_the_seven_keys_of_a_step_receipt():
    body = fixture("wizard", "setup_receipt_init.json")
    keys(body, {"setup"}, "setup_receipt_init")
    receipt = body["setup"]
    keys(receipt, STEP_RECEIPT, "setup_receipt_init")
    assert receipt["step"] == "init" and receipt["exclude"] in ("written", "present")
    assert receipt["warnings"] in ([], ["nested_repository"])
    assert INSTANT.match(receipt["recorded_at"])


def test_the_folder_holds_exactly_the_git_and_setup_stand_ins_the_desk_uses():
    git = sorted(path.stem for path in WIZARD.glob("git_*.json"))
    setup = sorted(path.stem for path in WIZARD.glob("setup_*.json"))
    assert git == sorted([*READS, *PENDING_READS])
    assert setup == sorted(SETUP)


def test_the_key_set_guard_names_an_extra_and_a_missing_key():
    planted = {name: None for name in GET_KEYS - {"signing"}} | {"stray": 1}
    with pytest.raises(AssertionError) as caught:
        keys(planted, GET_KEYS, "planted")
    message = str(caught.value)
    assert "extra ['stray']" in message and "missing ['signing']" in message


def test_the_pending_guard_refuses_a_shape_the_contract_does_not_have():
    for planted in ({"state": "waiting"}, {"state": "damaged", "reason": "torn"},
                    {"state": "unfinished"}):
        with pytest.raises(AssertionError):
            pending_holds(planted, "planted")
