"""Deterministic fake Claude/Codex protocol codecs are distinct and fail closed."""
from __future__ import annotations

import json

import pytest

from conductor.command.adapters.deep_codecs import (
    MAX_FRAME_BYTES,
    DeepCodecError,
    FakeClaudeCodec,
    FakeCodexCodec,
)
from conductor.command.adapters.deep_contracts import (
    AdapterFailure,
    NormalizedResult,
)
from conductor.command.contracts import canonical_json


NOW = "2026-08-13T20:00:00Z"


def result(**changes):
    values = {
        "run_id": "run-001", "action_id": "action-001",
        "attempt_id": "attempt-001", "instance_id": "claude-dev",
        "adapter_id": "deep-claude", "outcome": "succeeded",
        "observed_at": NOW, "exit_code": 0, "failure": None,
    }
    values.update(changes)
    return NormalizedResult(**values)


@pytest.mark.parametrize("codec", [FakeClaudeCodec, FakeCodexCodec])
def test_fake_codec_roundtrip_is_exact_and_contains_only_normalized_result(codec):
    normalized = result()
    frame = codec.encode_result(normalized)
    assert codec.decode_result(frame) == normalized
    for forbidden in (b"stdout", b"stderr", b"raw_output", b"APIKEY"):
        assert forbidden not in frame


def test_fake_protocols_are_explicitly_distinct_and_cross_wire_refuses():
    normalized = result()
    claude = FakeClaudeCodec.encode_result(normalized)
    codex = FakeCodexCodec.encode_result(normalized)
    assert claude != codex
    with pytest.raises(DeepCodecError):
        FakeClaudeCodec.decode_result(codex)
    with pytest.raises(DeepCodecError):
        FakeCodexCodec.decode_result(claude)


@pytest.mark.parametrize("codec,changes", [
    (FakeClaudeCodec, {"vendor": "real-claude"}),
    (FakeClaudeCodec, {"version": 2}),
    (FakeClaudeCodec, {"frame": "progress"}),
    (FakeCodexCodec, {"source": "real-codex"}),
])
def test_foreign_vendor_version_or_kind_refuses(codec, changes):
    frame = json.loads(codec.encode_result(result()))
    frame.update(changes)
    with pytest.raises(DeepCodecError):
        codec.decode_result(canonical_json(frame).encode() + b"\n")


def test_fake_codex_nested_protocol_version_and_event_kind_are_frozen():
    for field, value in (("version", 2), ("name", "fake-claude-jsonl")):
        frame = json.loads(FakeCodexCodec.encode_result(result()))
        frame["protocol"][field] = value
        with pytest.raises(DeepCodecError):
            FakeCodexCodec.decode_result(canonical_json(frame).encode() + b"\n")
    frame = json.loads(FakeCodexCodec.encode_result(result()))
    frame["event"]["kind"] = "progress"
    with pytest.raises(DeepCodecError):
        FakeCodexCodec.decode_result(canonical_json(frame).encode() + b"\n")


@pytest.mark.parametrize("codec", [FakeClaudeCodec, FakeCodexCodec])
def test_unknown_frame_field_refuses(codec):
    frame = json.loads(codec.encode_result(result()))
    frame["secret"] = "APIKEY-secret"
    with pytest.raises(DeepCodecError, match="rejected"):
        codec.decode_result(canonical_json(frame).encode() + b"\n")


@pytest.mark.parametrize("codec", [FakeClaudeCodec, FakeCodexCodec])
def test_duplicate_json_key_refuses(codec):
    with pytest.raises(DeepCodecError, match="rejected"):
        codec.decode_result(b'{"vendor":"fake-claude","vendor":"other"}\n')


@pytest.mark.parametrize("frame", [
    b'{"vendor":"fake-claude"}',
    b'{"vendor":"fake-claude"}\ntrailing\n',
    b'',
    b'[]\n',
])
def test_truncated_multi_empty_or_nonobject_frame_refuses(frame):
    with pytest.raises(DeepCodecError):
        FakeClaudeCodec.decode_result(frame)


def test_oversized_frame_refuses_before_parsing():
    with pytest.raises(DeepCodecError, match="rejected"):
        FakeClaudeCodec.decode_result(b"{" + b" " * MAX_FRAME_BYTES + b"}\n")


@pytest.mark.parametrize("literal", [b"NaN", b"Infinity", b"-Infinity", b"1e999"])
def test_nonfinite_numbers_refuse_recursively(literal):
    frame = b'{"vendor":"fake-claude","version":1,"frame":"result",' \
            b'"payload":{"number":' + literal + b'}}\n'
    with pytest.raises(DeepCodecError, match="rejected"):
        FakeClaudeCodec.decode_result(frame)


def test_failure_frame_is_normalized_closed_code_not_raw_exception_prose():
    normalized = result(
        outcome="unknown", exit_code=None,
        failure=AdapterFailure("protocol_error", "execute", False))
    frame = FakeCodexCodec.encode_result(normalized)
    assert FakeCodexCodec.decode_result(frame) == normalized
    assert b"protocol_error" in frame
    assert b"exception" not in frame and b"traceback" not in frame


def test_payload_identity_and_no_extra_are_revalidated_after_protocol_decode():
    frame = json.loads(FakeClaudeCodec.encode_result(result()))
    frame["payload"]["action_id"] = "action-foreign"
    decoded = FakeClaudeCodec.decode_result(canonical_json(frame).encode() + b"\n")
    assert decoded.action_id == "action-foreign"
    frame["payload"]["raw_output"] = "APIKEY-secret"
    with pytest.raises(DeepCodecError):
        FakeClaudeCodec.decode_result(canonical_json(frame).encode() + b"\n")


@pytest.mark.parametrize("frame", [
    b"\xff\n",
    b'{"broken":APIKEY_SECRET}\n',
    b'{"vendor":"fake-claude","APIKEY_SECRET":1,"APIKEY_SECRET":2}\n',
])
def test_untrusted_frame_text_never_survives_in_exception_graph(frame):
    with pytest.raises(DeepCodecError) as stopped:
        FakeClaudeCodec.decode_result(frame)
    chain, current = [], stopped.value
    while current is not None:
        chain.append(repr(current))
        current = current.__cause__ or current.__context__
    joined = " ".join(chain)
    assert "APIKEY_SECRET" not in joined
    assert "\\xff" not in joined
    assert stopped.value.__cause__ is None


def test_invalid_nested_identity_is_normalized_without_echoing_secret():
    frame = json.loads(FakeClaudeCodec.encode_result(result()))
    frame["payload"]["action_id"] = "APIKEY/SECRET"
    with pytest.raises(DeepCodecError) as stopped:
        FakeClaudeCodec.decode_result(canonical_json(frame).encode() + b"\n")
    assert "APIKEY" not in repr(stopped.value)
    assert stopped.value.__cause__ is None
