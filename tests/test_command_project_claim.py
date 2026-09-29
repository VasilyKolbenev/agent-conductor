"""The identity a project's server holds and the claim a request may make on it (spec 4.5.1).

`project_id` is the activation nonce: 32 lowercase hex, made once by `activate`, the same
across ownership generations, and the key of the hub's registry. A child learns it from its
OWNER (`ProjectOwner.project_id`, the head the owner holds), never from a value read earlier.
`ProjectIdentity` freezes what `GET /command/project` answers and what a request that carries
`X-Conduct-Project` is held to. The route row, the constructor parameter of `CommandApi` and
the one call of `check` are lane L's lines (`H-to-L-project-route.patch`), so this module
tests the handler and the check directly, not through the router.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from conductor import ownership, ownership_records, up_flags
from conductor.command import project_claim
from conductor.command.api_contracts import ApiRefusal
from conductor.command.api_refusals import ERROR_STATUS, _FIXED_MESSAGES
from conductor.command.project_claim import ProjectIdentity
from tests._drain_harness import DrainProject
from tests.alpha1_live_extensions import REFUSALS
from tests.test_cockpit_command_api_freeze import EXPECTED_ERRORS

HEX32 = re.compile(r"[0-9a-f]{32}")
CODE = "project_mismatch"
REPO = Path(__file__).resolve().parents[1]
PANEL = REPO / "src" / "conductor" / "panel"
NONCE = "3f9c0a1b2c3d4e5f60718293a4b5c6d7"
OTHER = "0" * 32
HUB = "http://127.0.0.1:7700"


def _activated(tmp_path):
    project = DrainProject.build(tmp_path)
    return project.root, project.project_id


# -- ProjectOwner.project_id --------------------------------------------------------


def test_the_owner_of_an_activated_project_reports_the_nonce_of_its_head(tmp_path):
    root, nonce = _activated(tmp_path)
    with ownership.acquire_owner(root) as owner:
        assert owner.project_id == nonce == ownership_records.state(root)[1]["nonce"]
        assert HEX32.fullmatch(owner.project_id)


def test_the_nonce_is_the_same_after_the_owner_closes_and_a_new_one_opens(tmp_path):
    root, nonce = _activated(tmp_path)
    first = ownership.acquire_owner(root)
    seen = [first.project_id]
    first.release()
    second = ownership.acquire_owner(root)
    seen.append(second.project_id)
    second.release()
    assert seen == [nonce, nonce]


# -- the identity and what `GET /command/project` answers ---------------------------


def _identity(**changes) -> ProjectIdentity:
    fields = {"project_id": NONCE, "hub_origin": HUB, "demo": False, "mode": "active",
              "transition_id": None, "auto_continue": None}
    return ProjectIdentity(**{**fields, **changes})


def test_the_payload_of_a_hub_child_is_exactly_four_keys_and_never_shows_the_handover():
    identity = _identity(mode="view", transition_id="8f6c2a3e-1b4d-4c5e-9a7b-0d1e2f3a4b5c",
                         auto_continue="0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d@3")
    assert identity.payload() == {"project_id": NONCE, "hub_origin": HUB, "demo": False,
                                  "mode": "view"}


def test_the_payload_of_a_standalone_activated_project_has_no_hub_and_is_active():
    assert _identity(hub_origin=None).payload() == {
        "project_id": NONCE, "hub_origin": None, "demo": False, "mode": "active"}


def test_the_payload_of_the_demo_has_no_project_id_and_says_it_is_the_demo():
    assert _identity(project_id=None, hub_origin=None, demo=True).payload() == {
        "project_id": None, "hub_origin": None, "demo": True, "mode": "active"}


@pytest.mark.parametrize("changes", [
    {"project_id": NONCE.upper()}, {"project_id": NONCE[:-1]}, {"project_id": ""},
    {"mode": "paused"}, {"mode": None}])
def test_an_identity_that_breaks_the_grammar_of_the_spec_cannot_be_built(changes):
    with pytest.raises(ValueError):
        _identity(**changes)


def test_the_handler_answers_200_with_the_payload_and_adds_nothing():
    identity = _identity()
    assert project_claim.read_project(identity) == (200, identity.payload())


def test_the_modes_of_the_identity_are_the_modes_of_the_flag():
    assert project_claim.MODES == up_flags.MODES


# -- the claim: the table of 4.5.1, row by row --------------------------------------


def _refusal_of(identity: ProjectIdentity, pairs) -> ApiRefusal:
    with pytest.raises(ApiRefusal) as caught:
        identity.check(pairs)
    return caught.value


HOST = ("Host", "127.0.0.1:7777")


def test_a_request_without_the_claim_header_passes_whatever_the_project_id():
    for identity in (_identity(), _identity(project_id=None)):
        assert identity.check([HOST, ("Accept", "*/*")]) is None
        assert identity.check([]) is None


def test_one_header_equal_to_the_project_id_passes_and_its_name_is_matched_without_case():
    for name in ("X-Conduct-Project", "x-conduct-project", "X-CONDUCT-PROJECT"):
        assert _identity().check([HOST, (name, NONCE)]) is None


@pytest.mark.parametrize("claim", [
    OTHER, NONCE.upper(), NONCE[:-1], NONCE + "0", "", " " + NONCE, NONCE + " ", NONCE + "\t",
    "null", "0x" + NONCE[2:]])
def test_one_header_that_differs_or_is_not_by_the_grammar_is_project_mismatch(claim):
    assert _refusal_of(_identity(), [HOST, ("X-Conduct-Project", claim)]).code == CODE


def test_a_header_on_a_server_that_has_no_project_id_is_project_mismatch():
    for claim in (NONCE, OTHER, ""):
        identity = _identity(project_id=None, hub_origin=None)
        assert _refusal_of(identity, [("X-Conduct-Project", claim)]).code == CODE


@pytest.mark.parametrize("pairs", [
    [("X-Conduct-Project", NONCE), ("X-Conduct-Project", NONCE)],
    [("X-Conduct-Project", NONCE), ("x-conduct-project", OTHER)],
    [("x-conduct-project", NONCE), HOST, ("X-CONDUCT-PROJECT", NONCE)]])
def test_two_headers_are_project_mismatch_even_when_both_are_right(pairs):
    assert _refusal_of(_identity(), pairs).code == CODE
    assert _refusal_of(_identity(project_id=None), pairs).code == CODE


def test_the_refusal_is_409_with_the_fixed_words_and_no_detail_and_never_echoes_the_header():
    sent = "d3adb33f" * 4
    refusal = _refusal_of(_identity(), [("X-Conduct-Project", sent)])
    assert refusal.status == 409
    assert refusal.message == "this server serves another project"
    assert dict(refusal.detail) == {}
    assert sent not in repr(refusal.as_dict()) and NONCE not in repr(refusal.as_dict())


# -- 11.1: the code stands in every place of the vocabulary --------------------------


def test_project_mismatch_stands_in_every_place_of_the_command_vocabulary_python_can_read():
    assert ERROR_STATUS[CODE] == 409                                     # place 1
    assert _FIXED_MESSAGES[CODE] == "this server serves another project"  # place 2
    assert EXPECTED_ERRORS[CODE] == (409, "identity")                    # place 5
    assert REFUSALS[CODE] == 409                                         # place 6


def test_project_mismatch_stands_in_the_canon_the_labels_and_both_languages_of_the_notice():
    canon = (REPO / "docs" / "specs" / "2026-08-13-cockpit-command-api.md").read_text(
        encoding="utf-8")
    assert re.search(rf'"code": "{CODE}",\s+"status": 409,\s+"source": "identity"', canon)   # 4
    labels = (PANEL / "command-projection.js").read_text(encoding="utf-8")
    assert re.search(rf"^  {CODE}: ", labels, re.MULTILINE)                               # 7
    notice = (PANEL / "studio-notice-copy.js").read_text(encoding="utf-8")
    found = re.search(rf'"error\.{CODE}": \["([^"]+)", "([^"]+)"\]', notice)               # 8
    assert found and all(found.groups()) and found.group(1) != found.group(2)


# -- the identity a real server builds at start, from its owner ----------------------

TRANSITION = "b71e4d09-c2a8-4f35-a6d8-1c0e9f3b5274"
FLAG = "6d0f2c1a-3b4e-4f5a-8b9c-0d1e2f3a4b5c@3"


def _identity_of_a_server(root, **options) -> ProjectIdentity:
    from conductor import server
    from conductor.command.adapters import AdapterRegistry
    subject = server.build(root, 0, registry=AdapterRegistry(), **options)
    try:
        return subject.project_identity
    finally:
        subject.server_close()


def test_a_hub_child_of_an_activated_root_holds_the_nonce_the_hub_origin_and_the_launch(
        tmp_path):
    root, nonce = _activated(tmp_path)
    launch = project_claim.Launch(mode="active", transition_id=TRANSITION, auto_continue=FLAG)
    assert _identity_of_a_server(root, hub_origin=HUB, launch=launch) == ProjectIdentity(
        nonce, HUB, False, "active", TRANSITION, FLAG)


def test_a_standalone_activated_root_holds_its_nonce_and_no_hub(tmp_path):
    root, nonce = _activated(tmp_path)
    assert _identity_of_a_server(root) == ProjectIdentity(
        nonce, None, False, "active", None, None)


def test_a_root_that_was_never_activated_holds_no_project_id(tmp_path):
    from tests.test_store import good_lane, write_project
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    assert _identity_of_a_server(root).payload() == {
        "project_id": None, "hub_origin": None, "demo": False, "mode": "active"}


def test_the_demo_launch_says_demo_and_holds_no_project_id(tmp_path):
    from tests.test_store import good_lane, write_project
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    identity = _identity_of_a_server(root, launch=project_claim.Launch(demo=True))
    assert identity.payload() == {
        "project_id": None, "hub_origin": None, "demo": True, "mode": "active"}


def test_the_nonce_comes_from_the_owner_and_not_from_a_value_read_before_it(
        tmp_path, monkeypatch):
    root, nonce = _activated(tmp_path)
    monkeypatch.setattr(ownership.ProjectOwner, "project_id", property(lambda self: OTHER))
    assert _identity_of_a_server(root).project_id == OTHER != nonce


def test_a_launch_that_says_nothing_is_active_with_no_demo_and_no_handover():
    assert project_claim.Launch() == project_claim.Launch("active", False, None, None)


def test_the_demo_plan_differs_from_the_standalone_plan_only_by_demo():
    import dataclasses
    assert up_flags.DEMO == dataclasses.replace(up_flags.STANDALONE, demo=True)
    assert up_flags.STANDALONE.demo is False and up_flags.DEMO.hub is False
