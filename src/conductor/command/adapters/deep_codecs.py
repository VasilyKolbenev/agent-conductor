"""Deterministic, deliberately incompatible JSON-line codecs for fake adapters."""
from __future__ import annotations

import json
import math
from collections.abc import Iterable
from typing import Any, ClassVar

from ..contracts import canonical_json
from .deep_contracts import (
    AdapterFailure,
    DeepContractError,
    NormalizedResult,
    _exact,
)


MAX_FRAME_BYTES = 16 * 1024
CODEC_VERSION = 1
CLAUDE_VENDOR = "fake-claude"
CLAUDE_FRAME_KIND = "result"
CODEX_VENDOR = "fake-codex"
CODEX_PROTOCOL = "fake-codex-jsonl"
CODEX_EVENT_KIND = "completed"


class DeepCodecError(DeepContractError):
    """A fake protocol frame is ambiguous, cross-wired, or unsupported."""


def _pairs(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DeepCodecError("deep codec rejected the frame")
        result[key] = value
    return result


def _nonfinite(value: str) -> None:
    raise DeepCodecError("deep codec rejected the frame")


def _frame_object(frame: object) -> dict[str, Any]:
    if not isinstance(frame, bytes):
        raise DeepCodecError("frame must be bytes")
    if not frame or len(frame) > MAX_FRAME_BYTES:
        raise DeepCodecError("frame is empty or exceeds the bounded frame size")
    if not frame.endswith(b"\n") or frame.count(b"\n") != 1 or b"\r" in frame:
        raise DeepCodecError("frame must be exactly one newline-terminated JSON line")
    value = _parse_json(frame[:-1])
    if value is None:
        raise DeepCodecError("deep codec rejected the frame")
    if not isinstance(value, dict):
        raise DeepCodecError("frame JSON must be an object")
    if _has_nonfinite(value):
        raise DeepCodecError("frame contains a non-finite number")
    canonical = canonical_json(value).encode("utf-8") + b"\n"
    if canonical != frame:
        raise DeepCodecError("frame JSON must use the canonical byte representation")
    return value


def _parse_json(payload: bytes) -> object | None:
    """Contain parser exceptions so raw frame bytes leave no exception chain."""
    try:
        return json.loads(
            payload.decode("utf-8"), object_pairs_hook=_pairs,
            parse_constant=_nonfinite)
    except Exception:  # noqa: BLE001 -- no parser/canonicalization graph escapes
        return None


def _has_nonfinite(value: object) -> bool:
    if isinstance(value, float):
        return not math.isfinite(value)
    if isinstance(value, dict):
        return any(_has_nonfinite(row) for row in value.values())
    if isinstance(value, list):
        return any(_has_nonfinite(row) for row in value)
    return False


class _FakeCodec:
    VENDOR: ClassVar[str]

    @classmethod
    def encode_result(cls, result: NormalizedResult) -> bytes:
        cls._require_exact_codec()
        if type(result) is not NormalizedResult:
            raise DeepCodecError("encode_result requires a NormalizedResult")
        failed = False
        try:
            canonical = NormalizedResult.from_dict(_result_values(result))
            frame = canonical_json(
                cls._wrap(_result_values(canonical))).encode("utf-8") + b"\n"
            if len(frame) > MAX_FRAME_BYTES or cls.decode_result(frame) != canonical:
                failed = True
        except Exception:  # noqa: BLE001 -- a hostile value leaves no exception graph
            failed = True
            frame = b""
        if failed:
            raise DeepCodecError("deep codec rejected the encoded result") from None
        return frame

    @classmethod
    def decode_result(cls, frame: object) -> NormalizedResult:
        cls._require_exact_codec()
        framed = cls._safe_frame(frame)
        parsed = None if framed is None else cls._normalized(framed)
        if parsed is None:
            raise DeepCodecError("deep codec rejected the frame")
        return parsed

    @classmethod
    def _require_exact_codec(cls) -> None:
        if cls not in (FakeClaudeCodec, FakeCodexCodec):
            raise DeepCodecError("codec use requires one exact reviewed base type")

    @staticmethod
    def _safe_frame(frame: object) -> dict[str, Any] | None:
        try:
            return _frame_object(frame)
        except Exception:  # noqa: BLE001 -- parser/canonicalization failures are untrusted
            return None

    @classmethod
    def _normalized(cls, frame: dict[str, Any]) -> NormalizedResult | None:
        """Contain contract exceptions so rejected submitted values are not retained."""
        try:
            return NormalizedResult.from_dict(cls._unwrap(frame))
        except Exception:  # noqa: BLE001 -- submitted nested values are untrusted
            return None

    @classmethod
    def _wrap(cls, result: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @classmethod
    def _unwrap(cls, frame: dict[str, Any]) -> object:
        raise NotImplementedError


class FakeClaudeCodec(_FakeCodec):
    """The fake Claude protocol: a flat vendor/version envelope."""

    VENDOR = CLAUDE_VENDOR

    @classmethod
    def _wrap(cls, result: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": cls.VENDOR, "version": CODEC_VERSION,
                "frame": CLAUDE_FRAME_KIND, "payload": result}

    @classmethod
    def _unwrap(cls, frame: dict[str, Any]) -> object:
        data = _exact(
            frame, frozenset({"vendor", "version", "frame", "payload"}),
            "fake Claude frame")
        if (data["vendor"] != cls.VENDOR or type(data["version"]) is not int
                or data["version"] != CODEC_VERSION):
            raise DeepCodecError("fake Claude frame has a foreign vendor or version")
        if data["frame"] != CLAUDE_FRAME_KIND:
            raise DeepCodecError("fake Claude frame kind is unsupported")
        return data["payload"]


class FakeCodexCodec(_FakeCodec):
    """The fake Codex protocol: nested protocol and completion event values."""

    VENDOR = CODEX_VENDOR

    @classmethod
    def _wrap(cls, result: dict[str, Any]) -> dict[str, Any]:
        return {
            "source": cls.VENDOR,
            "protocol": {"name": CODEX_PROTOCOL, "version": CODEC_VERSION},
            "event": {"kind": CODEX_EVENT_KIND, "result": result},
        }

    @classmethod
    def _unwrap(cls, frame: dict[str, Any]) -> object:
        data = _exact(
            frame, frozenset({"source", "protocol", "event"}),
            "fake Codex frame")
        protocol = _exact(
            data["protocol"], frozenset({"name", "version"}),
            "fake Codex protocol")
        event = _exact(
            data["event"], frozenset({"kind", "result"}),
            "fake Codex event")
        if (data["source"] != cls.VENDOR or protocol["name"] != CODEX_PROTOCOL
                or type(protocol["version"]) is not int
                or protocol["version"] != CODEC_VERSION):
            raise DeepCodecError("fake Codex frame has a foreign vendor or version")
        if event["kind"] != CODEX_EVENT_KIND:
            raise DeepCodecError("fake Codex event kind is unsupported")
        return event["result"]


def _result_values(result: NormalizedResult) -> dict[str, Any]:
    """Snapshot exact base fields without calling adapter-polymorphic methods."""
    failure = result.failure
    if failure is not None and type(failure) is not AdapterFailure:
        raise DeepCodecError("normalized failure must have the exact base type")
    failure_values = None if failure is None else {
        "code": failure.code, "phase": failure.phase, "retryable": failure.retryable}
    return {
        "run_id": result.run_id, "action_id": result.action_id,
        "attempt_id": result.attempt_id, "instance_id": result.instance_id,
        "adapter_id": result.adapter_id, "outcome": result.outcome,
        "observed_at": result.observed_at, "exit_code": result.exit_code,
        "failure": failure_values,
    }
