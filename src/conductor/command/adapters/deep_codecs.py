"""Deterministic, deliberately incompatible JSON-line codecs for fake adapters."""
from __future__ import annotations

import json
import math
from collections.abc import Iterable
from typing import Any, ClassVar

from ..contracts import ContractError, canonical_json
from .deep_contracts import DeepContractError, NormalizedResult, _exact


MAX_FRAME_BYTES = 16 * 1024


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
    except (UnicodeError, json.JSONDecodeError, DeepCodecError):
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
        if not isinstance(result, NormalizedResult):
            raise DeepCodecError("encode_result requires a NormalizedResult")
        return canonical_json(cls._wrap(result.as_dict())).encode("utf-8") + b"\n"

    @classmethod
    def decode_result(cls, frame: object) -> NormalizedResult:
        framed = cls._safe_frame(frame)
        parsed = None if framed is None else cls._normalized(framed)
        if parsed is None:
            raise DeepCodecError("deep codec rejected the frame")
        return parsed

    @staticmethod
    def _safe_frame(frame: object) -> dict[str, Any] | None:
        try:
            return _frame_object(frame)
        except (DeepCodecError, ContractError):
            return None

    @classmethod
    def _normalized(cls, frame: dict[str, Any]) -> NormalizedResult | None:
        """Contain contract exceptions so rejected submitted values are not retained."""
        try:
            return NormalizedResult.from_dict(cls._unwrap(frame))
        except (DeepCodecError, ContractError):
            return None

    @classmethod
    def _wrap(cls, result: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @classmethod
    def _unwrap(cls, frame: dict[str, Any]) -> object:
        raise NotImplementedError


class FakeClaudeCodec(_FakeCodec):
    """The fake Claude protocol: a flat vendor/version envelope."""

    VENDOR = "fake-claude"

    @classmethod
    def _wrap(cls, result: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": cls.VENDOR, "version": 1,
                "frame": "result", "payload": result}

    @classmethod
    def _unwrap(cls, frame: dict[str, Any]) -> object:
        data = _exact(
            frame, frozenset({"vendor", "version", "frame", "payload"}),
            "fake Claude frame")
        if data["vendor"] != cls.VENDOR or data["version"] != 1:
            raise DeepCodecError("fake Claude frame has a foreign vendor or version")
        if data["frame"] != "result":
            raise DeepCodecError("fake Claude frame kind is unsupported")
        return data["payload"]


class FakeCodexCodec(_FakeCodec):
    """The fake Codex protocol: nested protocol and completion event values."""

    VENDOR = "fake-codex"

    @classmethod
    def _wrap(cls, result: dict[str, Any]) -> dict[str, Any]:
        return {
            "source": cls.VENDOR,
            "protocol": {"name": "fake-codex-jsonl", "version": 1},
            "event": {"kind": "completed", "result": result},
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
        if (data["source"] != cls.VENDOR
                or protocol != {"name": "fake-codex-jsonl", "version": 1}):
            raise DeepCodecError("fake Codex frame has a foreign vendor or version")
        if event["kind"] != "completed":
            raise DeepCodecError("fake Codex event kind is unsupported")
        return event["result"]
