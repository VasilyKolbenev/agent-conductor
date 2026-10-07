"""The refusal `preview_stale` and the doors that say it (spec 4.4.2, 4.4.7, 6.4.5, 11.1).

Authorizing terms whose preview is gone, evicted, expired, or no longer describes the run was
`contract_invalid`, the same word as a body that is simply wrong. A desk told "invalid" could
only send the same body again; told `preview_stale` it repeats the preview and shows the human
what moved. It carries no detail: which of the four it was is not something a caller may act
on differently. The second half is the rule of 11.1, one commit into every place.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from conductor.command.api_contracts import (
    ERROR_STATUS, _FIXED_MESSAGES, refusal_from_exception)
from conductor.command.api_refusals import _REVIEWED_FACTS
from conductor.command.artifacts import ArtifactDocument
from conductor.command.contract_values import ContractError, _content_digest
from conductor.command.http_api import CommandApi
from conductor.command.http_transport import CommandSession
from conductor.command.policy_preview import MAX_PREVIEWS, PreviewCache, PreviewStale
from tests.alpha1_live_extensions import REFUSALS
from tests.test_cockpit_command_api_freeze import EXPECTED_ERRORS
from tests.test_command_http_api import PORT, TOKEN, post
from tests.test_policy_runtime import ASK, NOW, setup

REPO = Path(__file__).resolve().parents[1]
PANEL = REPO / "src" / "conductor" / "panel"
CODE = "preview_stale"
PATH = "/command/runs/run/automation/authorize"


def door(f):
    api = CommandApi(f.store, f.registry, session=CommandSession(PORT, TOKEN),
                     budget=f.policy.budget, clock=f.policy.clock, ids=f.runtime._ids,
                     publish_run=lambda run_id: None)
    api._policy = f.policy
    return api


def body_for(preview, **more):
    return {"authorization_id": "grant", "preview_digest": preview["preview_digest"],
            "authorized_by": "owner", "terms": preview["terms"], "supersedes": None, **more}


def outcome(answer):
    return answer.status, answer.payload["error"]["code"], answer.payload["error"]["detail"]


def refused_and_wrote_nothing(f, body, expected=(409, CODE, {})):
    before = f.store.read("run").records
    answer = post(door(f), PATH, body)
    assert outcome(answer) == expected, answer.payload
    assert f.store.read("run").records == before and f.policy.driver.calls == 0


# --- the ways a preview goes stale, and what stays contract_invalid ---------------------------


def test_authorizing_terms_that_no_preview_holds_is_409_preview_stale(tmp_path):
    f = setup(tmp_path)
    preview = f.policy.preview("run", ASK)
    f.policy.previews.discard("session", "run")
    refused_and_wrote_nothing(f, body_for(preview))


def test_terms_that_differ_from_the_reviewed_ones_are_409_preview_stale(tmp_path):
    f = setup(tmp_path)
    preview = f.policy.preview("run", ASK)
    other = {**preview["terms"], "duration_seconds": 301}
    refused_and_wrote_nothing(f, body_for(
        preview, terms=other, preview_digest=_content_digest(other)))


def test_terms_and_a_digest_of_them_that_no_preview_this_session_holds_are_409_preview_stale(
        tmp_path):
    f = setup(tmp_path)
    f.policy.preview("run", ASK)
    unheld = {**ASK, "max_actions": 2}
    refused_and_wrote_nothing(f, body_for(
        {"terms": unheld, "preview_digest": _content_digest(unheld)}))


def test_an_expired_preview_is_409_preview_stale(tmp_path):
    f = setup(tmp_path)
    preview = f.policy.preview("run", ASK)
    f.ticks[0] = "2026-08-11T12:05:01Z"
    refused_and_wrote_nothing(f, body_for(preview))


def test_an_evicted_preview_is_refused_as_stale_by_the_cache():
    cache = PreviewCache()
    first = {"preview_digest": "sha256:" + "1" * 64, "terms": {"a": 1},
             "previewed_at": NOW, "valid_until": "2026-08-11T12:05:00Z"}
    cache.put("session", "run-0", first)
    for number in range(1, MAX_PREVIEWS + 1):
        cache.put("session", f"run-{number}", {**first, "terms": {"a": number}})
    with pytest.raises(PreviewStale):
        cache.require("session", "run-0", first["preview_digest"], first["terms"], NOW)


def test_reviewed_facts_that_moved_before_the_grant_are_409_preview_stale(tmp_path):
    f = setup(tmp_path)
    preview = f.policy.preview("run", ASK)
    f.store.append(ArtifactDocument(
        artifact_id="instruction-2", run_id="run", artifact_ref="instructions", created_at=NOW,
        media_type="text/plain", content="Changed after the review"))
    refused_and_wrote_nothing(f, body_for(preview))


def test_a_preview_that_still_stands_authorizes_with_a_201(tmp_path):
    f = setup(tmp_path)
    granted = post(door(f), PATH, body_for(f.policy.preview("run", ASK)))
    assert granted.status == 201


@pytest.mark.parametrize("wrong", [
    {"authorized_by": ""},                             # no one named
    {"extra": 1},                                      # a key the door does not know
    {"preview_digest": "sha256:" + "0" * 64},          # not the digest of the terms it carries
    {"terms": ["not", "an", "object"]},                # terms that are not an object
])
def test_a_body_that_is_wrong_in_itself_is_still_contract_invalid(tmp_path, wrong):
    f = setup(tmp_path)
    refused_and_wrote_nothing(f, body_for(f.policy.preview("run", ASK), **wrong),
                              expected=(422, "contract_invalid", {}))


def test_a_self_inconsistent_body_is_contract_invalid_even_when_no_preview_is_held(tmp_path):
    """The body's own digest is judged before the cache is asked, so the cache being empty
    cannot turn a body that is wrong in itself into a stale one."""
    f = setup(tmp_path)
    preview = f.policy.preview("run", ASK)
    f.policy.previews.discard("session", "run")
    refused_and_wrote_nothing(f, body_for(preview, preview_digest="sha256:" + "0" * 64),
                              expected=(422, "contract_invalid", {}))


def test_the_translation_is_by_type_and_a_plain_contract_error_is_not_stale():
    assert refusal_from_exception(PreviewStale("x")).code == CODE
    assert refusal_from_exception(ContractError("x")).code == "contract_invalid"
    assert issubclass(PreviewStale, ContractError)


# --- 11.1: the code stands in every place of the vocabulary ---------------------------------------


def test_preview_stale_stands_in_every_place_of_the_command_vocabulary_that_python_can_read():
    assert ERROR_STATUS[CODE] == 409                       # place 1
    assert _FIXED_MESSAGES[CODE].strip()                   # place 2
    assert not [row for row in _REVIEWED_FACTS if row[0] == CODE], "it carries no detail"  # 3
    assert EXPECTED_ERRORS[CODE] == (409, "authorization")  # place 5
    assert REFUSALS[CODE] == 409                           # place 6


def test_preview_stale_stands_in_the_canon_the_labels_and_both_languages_of_the_notice():
    canon = (REPO / "docs" / "specs" / "2026-08-13-cockpit-command-api.md").read_text(
        encoding="utf-8")
    assert re.search(rf'"code": "{CODE}",\s+"status": 409,\s+"source": "authorization"', canon)
    labels = (PANEL / "command-projection.js").read_text(encoding="utf-8")
    assert re.search(rf"^  {CODE}: ", labels, re.MULTILINE)                              # 7
    notice = (PANEL / "studio-notice-copy.js").read_text(encoding="utf-8")
    found = re.search(rf'"error\.{CODE}": \["([^"]+)", "([^"]+)"\]', notice)              # 8
    assert found and all(found.groups()) and found.group(1) != found.group(2)
