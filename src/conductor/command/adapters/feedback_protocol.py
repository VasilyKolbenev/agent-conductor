"""Standalone value-only parser; runtime supplies attribution and authority."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol


FEEDBACK_PROTOCOL = "conduct.feedback.v1"
MAX_FINDINGS = 16
MAX_PAYLOAD_BYTES = 8192
#: A cited line is a location, not a number channel: seven digits name any real
#: source file and leave no room for an integer to carry other material.
MAX_LINE = 9_999_999
FINDING_KINDS = frozenset({"defect", "missing_requirement", "verification_gap"})
REASONS = frozenset({
    "not_opted_in", "invalid_sensitive_values", "invalid_outcome", "not_rejected",
    "malformed_payload", "duplicate_field", "nonfinite_value", "invalid_payload",
    "protocol_mismatch", "finding_count", "invalid_finding", "sensitive_material",
    "payload_over_limit"})

_PAYLOAD_FIELDS = frozenset({"protocol", "findings"})
_FINDING_FIELDS = frozenset({"kind", "summary", "path", "line"})
_REJECT_LINE = "VERDICT: reject"


class FeedbackProtocolError(ValueError):
    """A fixed refusal reason, never any child text or sensitive value."""

    def __init__(self, reason: str):
        if reason not in REASONS:
            raise ValueError("feedback refusal reason is not in the closed vocabulary")
        self.reason = reason
        super().__init__(reason)


class _Outcome(Protocol):
    status: str
    exit_code: int | None
    output: bytes
    output_truncated: bool
    output_contains_env_value: bool
    stdin_state: str


@dataclass(frozen=True)
class Finding:
    kind: str
    summary: str = field(repr=False)
    path: str | None = field(repr=False)
    line: int | None

    def as_dict(self) -> dict:
        return {"kind": self.kind, "summary": self.summary,
                "path": self.path, "line": self.line}


@dataclass(frozen=True)
class ParsedFeedback:
    """Immutable material returned by parse_feedback; not an authority envelope."""

    findings: tuple[Finding, ...] = field(repr=False)
    _canonical: bytes = field(repr=False)

    @property
    def protocol(self) -> str:
        return FEEDBACK_PROTOCOL

    def as_dict(self) -> dict:
        return {"protocol": self.protocol,
                "findings": [finding.as_dict() for finding in self.findings]}

    def canonical_bytes(self) -> bytes:
        return self._canonical


def _completed_output(outcome: _Outcome) -> bytes:
    try:
        valid = (
            outcome.status == "completed"
            and type(outcome.exit_code) is int and outcome.exit_code == 0
            and outcome.stdin_state == "delivered"
            and outcome.output_truncated is False
            and outcome.output_contains_env_value is False
            and type(outcome.output) is bytes)
    except AttributeError:
        valid = False  # refused below, outside the handler: no context holds the outcome
    if not valid:
        raise FeedbackProtocolError("invalid_outcome")
    return outcome.output


def _payload_text(output: bytes) -> str:
    # Refusals are raised OUTSIDE the handler: `from None` hides a context from
    # a traceback, but the context object would still hold the child's bytes.
    try:
        lines = output.decode("utf-8").splitlines(keepends=True)
    except UnicodeDecodeError:
        lines = None
    if lines is None:
        raise FeedbackProtocolError("malformed_payload")
    for index, line in enumerate(lines):
        if line.strip():
            # Keep the existing first-line convention, without calling or
            # changing its parser. Rejoining the tail preserves Unicode and CRLF.
            if line.splitlines()[0].lstrip() != _REJECT_LINE:
                raise FeedbackProtocolError("not_rejected")
            return "".join(lines[index + 1:])
    raise FeedbackProtocolError("not_rejected")


def _object(pairs) -> dict:
    result = {}
    for name, value in pairs:
        if name in result:
            raise FeedbackProtocolError("duplicate_field")
        result[name] = value
    return result


def _nonfinite(_value: str):
    raise FeedbackProtocolError("nonfinite_value")


def _decode(payload: str):
    try:
        return json.loads(payload, object_pairs_hook=_object, parse_constant=_nonfinite)
    except FeedbackProtocolError:
        raise
    except (ValueError, RecursionError):
        pass  # raised below, so the decoder's error does not travel as context
    raise FeedbackProtocolError("malformed_payload")


def _text(value) -> bool:
    return (type(value) is str and bool(value.strip()) and not any(
        ord(c) < 32 or 127 <= ord(c) <= 159 or 0xD800 <= ord(c) <= 0xDFFF for c in value))


def _location(path, line) -> bool:
    if line is not None and (type(line) is not int or not 1 <= line <= MAX_LINE):
        return False
    if path is None:
        return line is None
    return (_text(path) and "\\" not in path and ":" not in path
            and all(part not in {"", ".", ".."} for part in path.split("/")))


def _findings(document) -> tuple[Finding, ...]:
    if type(document) is not dict or set(document) != _PAYLOAD_FIELDS:
        raise FeedbackProtocolError("invalid_payload")
    if document["protocol"] != FEEDBACK_PROTOCOL:
        raise FeedbackProtocolError("protocol_mismatch")
    rows = document["findings"]
    if type(rows) is not list or not 1 <= len(rows) <= MAX_FINDINGS:
        raise FeedbackProtocolError("finding_count")
    found = []
    for row in rows:
        if (type(row) is not dict or set(row) != _FINDING_FIELDS
                or type(row["kind"]) is not str or row["kind"] not in FINDING_KINDS
                or not _text(row["summary"]) or not _location(row["path"], row["line"])):
            raise FeedbackProtocolError("invalid_finding")
        found.append(Finding(**row))
    return tuple(found)


def _scan(value, sensitive: tuple[bytes, ...]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            _scan(key, sensitive)
            _scan(item, sensitive)
    elif isinstance(value, list):
        for item in value:
            _scan(item, sensitive)
    elif type(value) in (str, int):
        # An integer is a decoded field too: digits can spell a sampled value.
        encoded = str(value).encode("utf-8")
        if any(secret and secret in encoded for secret in sensitive):
            raise FeedbackProtocolError("sensitive_material")


def _canonical(document: dict) -> bytes:
    return json.dumps(document, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def parse_feedback(outcome: _Outcome, *, opted_in_protocol: str | None,
                   sensitive: tuple[bytes, ...]) -> ParsedFeedback:
    """Validate explicitly opted-in findings; every failure refuses the whole payload.

    The caller supplies its already sampled secrets. Nothing here reads process
    state, files, a registry, a journal or the old ACCEPT/REJECT parser.
    """
    if type(opted_in_protocol) is not str or opted_in_protocol != FEEDBACK_PROTOCOL:
        raise FeedbackProtocolError("not_opted_in")
    if type(sensitive) is not tuple or any(type(value) is not bytes for value in sensitive):
        raise FeedbackProtocolError("invalid_sensitive_values")
    document = _decode(_payload_text(_completed_output(outcome)))
    findings = _findings(document)
    _scan(document, sensitive)
    canonical = _canonical(document)
    if len(canonical) > MAX_PAYLOAD_BYTES:
        raise FeedbackProtocolError("payload_over_limit")
    return ParsedFeedback(findings, canonical)
