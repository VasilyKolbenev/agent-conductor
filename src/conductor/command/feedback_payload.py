"""Pure, bounded feedback data shared by the parser and durable record."""
import json

FEEDBACK_PROTOCOL = "conduct.feedback.v1"
MAX_FINDINGS = 16
MAX_PAYLOAD_BYTES = 8192
MAX_LINE = 9_999_999  # the parser's ceiling (adapters/feedback_protocol.py); a record keeps it
FINDING_KINDS = frozenset({"defect", "missing_requirement", "verification_gap"})


class FeedbackPayloadError(ValueError):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def _text(value):
    return (type(value) is str and bool(value.strip()) and not any(
        ord(c) < 32 or 127 <= ord(c) <= 159 or 0xD800 <= ord(c) <= 0xDFFF for c in value))


def _location(path, line):
    if line is not None and (type(line) is not int or not 1 <= line <= MAX_LINE):
        return False
    if path is None:
        return line is None
    return (_text(path) and "\\" not in path and ":" not in path
            and all(part not in {"", ".", ".."} for part in path.split("/")))


def settled_payload(value, *, check_size=True):
    """Return an independent plain copy; malformed/oversized data is never clipped."""
    if type(value) is not dict or set(value) != {"protocol", "findings"}:
        raise FeedbackPayloadError("invalid_payload")
    if value["protocol"] != FEEDBACK_PROTOCOL:
        raise FeedbackPayloadError("protocol_mismatch")
    rows = value["findings"]
    if type(rows) is not list or not 1 <= len(rows) <= MAX_FINDINGS:
        raise FeedbackPayloadError("finding_count")
    found = []
    for row in rows:
        if (type(row) is not dict or set(row) != {"kind", "summary", "path", "line"}
                or type(row["kind"]) is not str or row["kind"] not in FINDING_KINDS
                or not _text(row["summary"]) or not _location(row["path"], row["line"])):
            raise FeedbackPayloadError("invalid_finding")
        found.append(dict(row))
    payload = {"protocol": FEEDBACK_PROTOCOL, "findings": found}
    if check_size and len(payload_bytes(payload)) > MAX_PAYLOAD_BYTES:
        raise FeedbackPayloadError("payload_over_limit")
    return payload


def payload_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def settled_feedback_bytes(value):
    if value is None:
        return None
    if type(value) is not bytes or len(value) > MAX_PAYLOAD_BYTES:
        raise FeedbackPayloadError("invalid_payload")
    try:
        rebuilt = settled_payload(json.loads(value.decode("utf-8")))
        if payload_bytes(rebuilt) != value:
            raise ValueError("not canonical")
    except (ValueError, UnicodeError, RecursionError):
        raise FeedbackPayloadError("invalid_payload") from None
    return value
