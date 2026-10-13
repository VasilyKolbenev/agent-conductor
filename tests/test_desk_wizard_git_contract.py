"""The git stand-ins held to what the real route answers, not only to the contract's key sets.

`tests/test_desk_wizard_git_fixtures.py` holds the stand-ins to key sets written by hand from lane
L's two handoffs. That left one hole, which lane L named: the files were never compared with the
ANSWER. Here a real temporary repository is driven through the real command boundary (lane L's own
bench, with the confirm door held open the way its tests hold it) and the nested key structure of
each answer is compared with the stand-in that stands for it. A route that gains or loses a key
turns this red while the hand-written sets are still green, which is the point.
"""
from __future__ import annotations

import os
from typing import Any

import pytest

from tests.desk_wizard_node import fixture
from tests.git_first_bench import (  # noqa: F401
    confirm, confirm_door, crashed, op_file, project, seal, terms_of)
from tests.git_first_signing import (  # noqa: F401
    owner_makes_the_commit, signing_key, signing_project, waits)
from tests.git_repo_helpers import needs_git
from tests.test_command_project_doors import request
from tests.test_git_setup import PATH as SETUP, step
from tests.test_git_setup_first_recovery import FILES
from tests.test_project_git_state import read
from tests.test_seed_routes import Folder


pytestmark = [needs_git, pytest.mark.usefixtures("confirm_door")]


def key_faults(real: Any, stand_in: Any, where: str = "") -> list[str]:
    """Where the nested key structures of two answers differ: an extra and a missing key by path.

    A list is judged by its first row (a stand-in may hold more rows than a small repository
    makes), and an empty list on either side says nothing about its rows. Values are not compared.
    """
    if isinstance(real, dict) and isinstance(stand_in, dict):
        faults = [f"{where}/{key}: the route has a key the stand-in lacks"
                  for key in sorted(set(real) - set(stand_in))]
        faults += [f"{where}/{key}: the stand-in has a key the route lacks"
                   for key in sorted(set(stand_in) - set(real))]
        for key in sorted(set(real) & set(stand_in)):
            faults += key_faults(real[key], stand_in[key], f"{where}/{key}")
        return faults
    if isinstance(real, list) and isinstance(stand_in, list) and real and stand_in:
        return key_faults(real[0], stand_in[0], where + "[]")
    return []


def test_the_key_comparison_names_an_extra_and_a_missing_key_at_any_depth():
    real = {"a": 1, "b": {"c": 1, "extra": 2}, "rows": [{"x": 1}]}
    stand_in = {"a": 1, "b": {"c": 1, "gone": 2}, "rows": [{"x": 1, "y": 2}]}
    assert key_faults(real, stand_in) == [
        "/b/extra: the route has a key the stand-in lacks",
        "/b/gone: the stand-in has a key the route lacks",
        "/rows[]/y: the stand-in has a key the route lacks"]
    assert key_faults({"rows": []}, {"rows": [{"x": 1}]}) == []
    assert key_faults({"a": None}, {"a": {"b": 1}}) == [], "a value is not a key set"


def stand_in(name: str) -> dict[str, Any]:
    return fixture("wizard", f"{name}.json")


def a_manual_row(p) -> None:
    """A file that has two names in the folder: the preview lists both as 'add these yourself'."""
    os.link(p.root / "a.txt", p.root / "alias.txt")


def test_the_unborn_read_has_the_keys_of_the_unborn_stand_in(tmp_path):
    p = project(tmp_path, FILES)
    assert key_faults(read(p), stand_in("git_unborn")["git"]) == []
    assert read(p)["first_commit_pending"] is None


def test_the_repo_read_has_the_keys_of_the_repo_stand_in_once_the_first_commit_stands(tmp_path):
    p = project(tmp_path, FILES)
    assert confirm(p).status == 201
    facts = read(p)
    assert facts["state"] == "repo" and facts["first_commit_pending"] is None
    assert key_faults(facts, stand_in("git_repo")["git"]) == []


def test_an_unfinished_first_commit_reads_with_the_keys_of_the_unfinished_stand_in(
        tmp_path, monkeypatch):
    p = project(tmp_path, FILES)
    crashed(monkeypatch, p, "_do_mark_ref_moved", "snapshot", terms_of(p))
    facts = read(p)
    assert facts["state"] == "repo" and facts["first_commit_pending"]["state"] == "unfinished"
    assert key_faults(facts, stand_in("git_pending_unfinished")["git"]) == []


def test_a_wait_for_a_signature_reads_with_the_keys_of_the_signature_stand_ins(
        tmp_path, signing_key):
    p = signing_project(tmp_path, signing_key, FILES)
    waits(p)
    facts = read(p)
    assert facts["first_commit_pending"]["state"] == "awaiting_signature"
    assert key_faults(facts, stand_in("git_pending_signature")["git"]) == []
    assert key_faults(facts, stand_in("git_pending_signature_sha256")["git"]) == []


def test_a_damaged_record_reads_as_the_damaged_stand_in_says(tmp_path, monkeypatch):
    p = project(tmp_path, FILES)
    crashed(monkeypatch, p, "_do_mark_ref_moved", "snapshot", terms_of(p))
    op_file(p).write_bytes(b"torn\n")
    facts = read(p)
    assert facts["first_commit_pending"] == {"state": "damaged"}
    assert key_faults(facts, stand_in("git_pending_damaged")["git"]) == []


def test_the_preview_stand_ins_have_the_keys_of_the_real_preview_rows_included(tmp_path):
    p = project(tmp_path, FILES)
    a_manual_row(p)
    real = seal(p)
    assert real["manual"] and real["files"], "the comparison reads a file row and a manual row"
    assert key_faults({"setup": real}, stand_in("setup_preview_snapshot")) == []
    assert key_faults({"setup": seal(p, "empty")}, stand_in("setup_preview_empty")) == []


def test_the_commit_receipt_stand_ins_have_the_keys_of_the_real_receipt(tmp_path):
    p = project(tmp_path, FILES)
    answer = confirm(p)
    assert answer.status == 201
    assert key_faults(answer.payload, stand_in("setup_receipt_commit")) == []
    assert answer.payload["setup"]["signature"] == "not_required"


def test_the_signed_receipt_stand_in_has_the_keys_of_the_real_signed_receipt(
        tmp_path, signing_key):
    p = signing_project(tmp_path, signing_key, FILES)
    digest = terms_of(p)
    owner_makes_the_commit(p, waits(p, "snapshot", digest))
    answer = confirm(p, "snapshot", digest=digest)
    assert answer.status == 201 and answer.payload["setup"]["signature"] == "present"
    assert key_faults(answer.payload, stand_in("setup_receipt_commit_signed")) == []


def test_the_init_receipt_stand_in_has_the_keys_of_the_real_step_receipt(tmp_path):
    folder = Folder(tmp_path)
    answer = step(folder)
    assert answer.status == 201
    assert key_faults(answer.payload, stand_in("setup_receipt_init")) == []
    exclude = step(folder, "exclude")
    assert exclude.status == 200 or exclude.status == 201
    assert key_faults(exclude.payload, stand_in("setup_receipt_init")) == []


def test_a_refusal_has_the_three_keys_and_a_signing_wait_carries_four_in_its_detail(
        tmp_path, signing_key):
    p = project(tmp_path, FILES)
    assert confirm(p).status == 201
    again = request(p, "POST", SETUP, dict(step="first_commit", mode="snapshot", preview=True))
    assert again.status == 409
    assert set(again.payload) == {"error"}
    assert set(again.payload["error"]) == {"code", "message", "detail"}
    assert again.payload["error"]["detail"] == {"reason": "head_exists"}
    signing = signing_project(tmp_path, signing_key, FILES, name="signing")
    assert set(waits(signing)) == {"reason", "tree", "target_ref", "message_path"}
