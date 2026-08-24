"""Durable artifact contracts and the one operator publication road."""
from __future__ import annotations

import hashlib

import pytest

from conductor.command.artifacts import (
    ARTIFACT_CONTENT_LIMIT,
    ArtifactDocument,
    latest_artifacts,
)
from conductor.command.contracts import ContractError, canonical_json
from conductor.command.run_store import RecordConflict, StoreError

from tests.test_command_http_api import RUN_ID, api, get_headers, post


NOW = "2026-08-24T09:00:00Z"


def artifact(**changes) -> ArtifactDocument:
    values = {
        "artifact_id": "artifact-document-001",
        "artifact_ref": "artifact-brief",
        "run_id": RUN_ID,
        "created_at": NOW,
        "media_type": "text/markdown",
        "content": "# Goal\nShip the bounded alpha.",
    }
    values.update(changes)
    return ArtifactDocument(**values)


def body(**changes) -> dict[str, object]:
    values: dict[str, object] = {
        "artifact_id": "artifact-document-001",
        "artifact_ref": "artifact-brief",
        "media_type": "text/markdown",
        "content": "# Goal\nShip the bounded alpha.",
    }
    values.update(changes)
    return values


def test_artifact_contract_is_closed_canonical_and_digest_is_computed():
    document = artifact()
    payload = document.as_dict()

    assert ArtifactDocument.from_dict(payload) == document
    assert "source_action_id" not in payload and "digest" not in payload
    assert document.digest() == "sha256:" + hashlib.sha256(
        canonical_json(payload).encode("utf-8")).hexdigest()

    with pytest.raises(ContractError, match="unsupported field"):
        ArtifactDocument.from_dict({**payload, "path": "secret.txt"})
    with pytest.raises(ContractError, match="null is not a spelling"):
        ArtifactDocument.from_dict({**payload, "source_action_id": None})
    with pytest.raises(ContractError, match="require a runtime source"):
        artifact(input_artifact_ids=("artifact-input",))


@pytest.mark.parametrize("media_type", ["application/json", "TEXT/PLAIN", None])
def test_artifact_media_type_is_a_closed_text_vocabulary(media_type):
    with pytest.raises(ContractError, match="media_type"):
        artifact(media_type=media_type)


@pytest.mark.parametrize("content", ["", "   ", "has\x00nul"])
def test_artifact_content_must_be_nonempty_text_without_nul(content):
    with pytest.raises(ContractError, match="content"):
        artifact(content=content)


def test_artifact_content_limit_counts_utf8_bytes_not_codepoints():
    assert len(artifact(content="x" * ARTIFACT_CONTENT_LIMIT).content) == (
        ARTIFACT_CONTENT_LIMIT)
    with pytest.raises(ContractError, match=str(ARTIFACT_CONTENT_LIMIT)):
        artifact(content="é" * (ARTIFACT_CONTENT_LIMIT // 2 + 1))


def test_latest_artifacts_uses_append_order_and_preserves_requested_order():
    first = artifact()
    other = artifact(
        artifact_id="artifact-document-002", artifact_ref="artifact-plan",
        content="Plan one.")
    revised = artifact(
        artifact_id="artifact-document-003", content="A later brief.")

    assert latest_artifacts((first, other, revised), (
        "artifact-plan", "artifact-brief")) == (other, revised)
    with pytest.raises(ContractError, match="unavailable"):
        latest_artifacts((first,), ("artifact-missing",))
    with pytest.raises(ContractError, match="duplicates"):
        latest_artifacts((first,), ("artifact-brief", "artifact-brief"))


def test_artifact_route_is_immutable_idempotent_and_visible_in_run_read(tmp_path):
    clock_calls = []

    def clock():
        clock_calls.append(NOW)
        return NOW

    subject, store, events = api(tmp_path, clock=clock)
    path = f"/command/runs/{RUN_ID}/artifacts"
    created = post(subject, path, body())
    retried = post(subject, path, body())
    conflicted = post(subject, path, body(content="Different durable bytes."))
    read = subject.handle("GET", f"/command/runs/{RUN_ID}", get_headers())

    assert (created.status, retried.status, conflicted.status) == (201, 200, 409)
    assert created.payload == retried.payload == artifact().as_dict()
    assert conflicted.payload["error"]["code"] == "record_conflict"
    assert clock_calls == [NOW]
    assert events == [RUN_ID]
    assert read.payload["records"] == [{
        "record_type": "artifact", "record": artifact().as_dict()}]
    assert store.read(RUN_ID).records[0].value == artifact()


@pytest.mark.parametrize(
    "extra", [
        "run_id", "created_at", "source_action_id", "input_artifact_ids",
        "digest", "path", "uri"])
def test_artifact_route_refuses_every_non_caller_field_without_an_effect(
        tmp_path, extra):
    subject, store, events = api(tmp_path)
    journal = store.run_path(RUN_ID) / "records.jsonl"
    before = journal.read_bytes()

    response = post(
        subject, f"/command/runs/{RUN_ID}/artifacts", body(**{extra: "owned"}))

    assert (response.status, response.payload["error"]["code"]) == (
        422, "contract_invalid")
    assert journal.read_bytes() == before and events == []


def test_artifact_route_has_no_read_or_collection_surface(tmp_path):
    subject, _, _ = api(tmp_path)
    response = subject.handle(
        "GET", f"/command/runs/{RUN_ID}/artifacts", get_headers())
    assert (response.status, response.payload["error"]["code"]) == (
        405, "method_not_allowed")


def test_artifact_with_unknown_source_action_writes_nothing(tmp_path):
    subject, store, _ = api(tmp_path)
    with pytest.raises(StoreError, match="unknown source action"):
        store.append(artifact(source_action_id="action-missing"))
    assert store.read(RUN_ID).records == ()


def test_store_conflicts_on_same_artifact_identity_with_different_facts(tmp_path):
    _, store, _ = api(tmp_path)
    assert store.append(artifact()) is True
    assert store.append(artifact()) is False
    with pytest.raises(RecordConflict, match="different facts"):
        store.append(artifact(content="Different."))
