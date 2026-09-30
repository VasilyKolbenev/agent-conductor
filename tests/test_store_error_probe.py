"""The test-only probe that says WHY the command API answered 500 `store_error`.

The public answer is fixed and safe on purpose: `store_error`, one line, no cause. A test that
meets it on a host it cannot be reproduced on (a Windows CI job) used to learn nothing else.
`tests/_store_error_probe.py` records, at the one place the API turns an exception into that
answer, the stage and the chain of exception types with `errno` and `winerror`, and nothing a
message or a file could hold. These tests hold its three promises: it records what it says, it
records no text, and it leaves the answer and the module as they were.
"""
from __future__ import annotations

import json

from conductor.command import http_api
from conductor.command.adapters.base import AdapterContractError
from conductor.command.store_errors import StoreError
from tests import _store_error_probe as probe

SECRET = "payload-that-must-not-be-kept-7f3a"
FOLDER = "C:\\Users\\someone\\runs\\.run-1.k3j2"


def _publish_failed() -> StoreError:
    """The error `RunStore.create_run` raises when the rename of its stage is refused."""
    denied = PermissionError(13, "Access is denied", f"{FOLDER}\\run.json")
    denied.winerror = 5
    try:
        raise denied
    except PermissionError as cause:
        try:
            raise StoreError(f"cannot publish run 'r': {SECRET}") from cause
        except StoreError as error:
            return error


def test_the_probe_records_the_stage_and_each_type_with_its_errno_and_winerror():
    with probe.watching() as seen:
        http_api.refusal_from_exception(_publish_failed())
    (record,) = seen
    assert [link["type"] for link in record["chain"]] == [
        "conductor.command.store_errors.StoreError", "builtins.PermissionError"]
    assert record["chain"][-1] == {
        "type": "builtins.PermissionError", "errno": 13, "winerror": 5, "file": "run.json"}
    assert record["stage"][-1].startswith("test_store_error_probe.py:_publish_failed:")


def test_the_probe_keeps_no_message_and_no_folder_of_a_path():
    with probe.watching() as seen:
        http_api.refusal_from_exception(_publish_failed())
    text = json.dumps(seen) + probe.describe(seen)
    assert SECRET not in text and "someone" not in text and ".run-1.k3j2" not in text


def test_the_public_answer_is_the_same_with_the_probe_watching():
    error = _publish_failed()
    plain = http_api.refusal_from_exception(error)
    with probe.watching():
        watched = http_api.refusal_from_exception(error)
    assert (watched.status, watched.as_dict()) == (plain.status, plain.as_dict())
    assert watched.code == "store_error" and SECRET not in json.dumps(watched.as_dict())


def test_the_probe_records_only_what_was_answered_store_error():
    with probe.watching() as seen:
        http_api.refusal_from_exception(AdapterContractError("not a store fault"))
    assert seen == []


def test_the_module_is_restored_when_the_watch_ends():
    before = http_api.refusal_from_exception
    with probe.watching():
        assert http_api.refusal_from_exception is not before
    assert http_api.refusal_from_exception is before
