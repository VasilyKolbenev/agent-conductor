"""The inactive typed protocol refuses whole answers at its declared boundaries."""
from dataclasses import FrozenInstanceError, dataclass, replace
import json
from pathlib import Path
import subprocess
import sys

import pytest

from conductor.command.adapters import feedback_protocol as protocol
from conductor.command.adapters.feedback_protocol import (
    FEEDBACK_PROTOCOL, FeedbackProtocolError, MAX_FINDINGS, MAX_PAYLOAD_BYTES,
    parse_feedback,
)


@dataclass(frozen=True)
class Outcome:
    output: bytes
    status: str = "completed"
    exit_code: int | None = 0
    stdin_state: str = "delivered"
    output_truncated: bool = False
    output_contains_env_value: bool = False


def finding(**changes):
    row = dict(kind="defect", summary="The empty case is wrong.", path=None, line=None)
    row.update(changes)
    return row


def document(*rows):
    return dict(protocol=FEEDBACK_PROTOCOL, findings=list(rows or (finding(),)))


def output(value, *, ascii_only=False):
    return Outcome(b"VERDICT: reject\n" + json.dumps(
        value, ensure_ascii=ascii_only).encode("utf-8"))


def parse(outcome, **changes):
    args = dict(opted_in_protocol=FEEDBACK_PROTOCOL, sensitive=())
    args.update(changes)
    return parse_feedback(outcome, **args)


def test_closed_findings_preserve_order_and_export_unaliased_material():
    value = document(
        finding(path="src/count.py", line=12),
        finding(kind="missing_requirement", summary="The promised input is absent."),
        finding(kind="verification_gap", summary="No check covers this branch.",
                path="tests/test_count.py"))
    parsed = parse(output(value))
    assert parsed.as_dict() == value
    assert parsed.protocol == FEEDBACK_PROTOCOL
    assert [row.kind for row in parsed.findings] == [
        "defect", "missing_requirement", "verification_gap"]
    exported = parsed.as_dict()
    exported["findings"][0]["summary"] = "changed"
    exported["findings"].clear()
    assert parsed.as_dict() == value
    with pytest.raises(FrozenInstanceError):
        parsed.findings[0].summary = "changed"
    with pytest.raises(FrozenInstanceError):
        parsed.findings = ()
    for private in ("empty case", "src/count.py", "promised input"):
        assert private not in repr(parsed)
        assert private not in repr(parsed.findings)


def test_canonical_unicode_is_exact_without_normalization_or_newline():
    text = "  é e\u0301 😀 \u2028  "
    parsed = parse(output(document(finding(summary=text)), ascii_only=True))
    expected = (
        '{"findings":[{"kind":"defect","line":null,"path":null,"summary":'
        '"  é e\u0301 😀 \u2028  "}],"protocol":"conduct.feedback.v1"}').encode("utf-8")
    assert parsed.canonical_bytes() == expected
    assert parsed.findings[0].summary == text
    assert parse(output(document(finding(summary=text)))).canonical_bytes() == expected


def test_first_line_convention_and_crlf_leave_the_payload_meaning_intact():
    value = document(finding(summary="Line separator \u2028 stays in the string."))
    wire = b"\r\n  VERDICT: reject\r\n" + json.dumps(
        value, ensure_ascii=False, indent=2).replace("\n", "\r\n").encode("utf-8")
    assert parse(Outcome(wire)).as_dict() == value


def test_sixteen_findings_fit_and_seventeen_refuse_without_truncation():
    assert MAX_FINDINGS == 16
    rows = [finding(summary=f"Finding {index}.") for index in range(17)]
    assert len(parse(output(document(*rows[:16]))).findings) == 16
    with pytest.raises(FeedbackProtocolError, match="^finding_count$"):
        parse(output(document(*rows)))
    with pytest.raises(FeedbackProtocolError, match="^finding_count$"):
        parse(output(dict(protocol=FEEDBACK_PROTOCOL, findings=[])))


EMPTY_CANONICAL = (
    b'{"findings":[{"kind":"defect","line":null,"path":null,"summary":""}],'
    b'"protocol":"conduct.feedback.v1"}')


@pytest.mark.parametrize("suffix", ["", '"', "é", "😀"])
def test_8192_and_8193_are_whole_canonical_utf8_bytes(suffix):
    assert MAX_PAYLOAD_BYTES == 8192
    encoded_suffix = json.dumps(suffix, ensure_ascii=False)[1:-1].encode("utf-8")
    text = "x" * (8192 - len(EMPTY_CANONICAL) - len(encoded_suffix)) + suffix
    parsed = parse(output(document(finding(summary=text))))
    assert len(parsed.canonical_bytes()) == 8192
    assert parsed.findings[0].summary == text
    with pytest.raises(FeedbackProtocolError, match="^payload_over_limit$"):
        parse(output(document(finding(summary=text + "x"))))


def test_wire_escaping_is_not_mistaken_for_the_canonical_byte_budget():
    value = document(finding(summary="é" * 3000))
    escaped = output(value, ascii_only=True)
    assert len(escaped.output) > 8192
    parsed = parse(escaped)
    assert len(parsed.canonical_bytes()) < 8192
    assert parsed.as_dict() == value


@pytest.mark.parametrize("opt_in", [None, "", "conduct.feedback.v2", True])
def test_the_child_cannot_opt_in_by_writing_the_protocol_discriminator(opt_in):
    with pytest.raises(FeedbackProtocolError, match="^not_opted_in$"):
        parse(output(document()), opted_in_protocol=opt_in)


def test_opt_in_and_sampled_sensitive_values_are_explicit_required_arguments():
    with pytest.raises(TypeError):
        parse_feedback(output(document()), sensitive=())
    with pytest.raises(TypeError):
        parse_feedback(output(document()), opted_in_protocol=FEEDBACK_PROTOCOL)
    with pytest.raises(FeedbackProtocolError, match="^not_opted_in$"):
        parse_feedback(object(), opted_in_protocol=None, sensitive=())


@pytest.mark.parametrize("changes", [
    {"status": "timed_out"}, {"status": "stopped"}, {"exit_code": 1},
    {"exit_code": None}, {"exit_code": False}, {"stdin_state": "incomplete"},
    {"stdin_state": "not_provided"}, {"output_truncated": True},
    {"output_truncated": 0}, {"output_contains_env_value": True},
    {"output_contains_env_value": 0}, {"output": "VERDICT: reject"},
])
def test_only_a_complete_successful_delivered_outcome_reaches_payload_parsing(changes):
    with pytest.raises(FeedbackProtocolError, match="^invalid_outcome$"):
        parse(replace(output(document()), **changes))


@pytest.mark.parametrize("prefix", [
    b"VERDICT: accept\n", b"VERDICT: reject \n", b"rejected\n", b"Reasons first\n",
])
def test_only_the_existing_exact_reject_line_can_precede_findings(prefix):
    with pytest.raises(FeedbackProtocolError, match="^not_rejected$"):
        parse(Outcome(prefix + json.dumps(document()).encode()))


def test_legacy_free_prose_is_not_a_payload_and_the_existing_verdict_is_unchanged():
    from conductor.command.adapters.independent_check import verdict

    legacy = Outcome(b"VERDICT: reject\nPlease fix the empty-input case.")
    assert verdict(legacy) == "rejected"
    with pytest.raises(FeedbackProtocolError, match="^malformed_payload$"):
        parse(legacy)
    assert verdict(legacy) == "rejected"


@pytest.mark.parametrize("tail", [
    b"", b"not JSON", b"{} trailing prose", b"{}{}", b"```json\n{}\n```",
    b'{"protocol":', b"\xff", b"[" * 1200 + b"]" * 1199,
])
def test_malformed_incomplete_or_multiple_payloads_refuse(tail):
    with pytest.raises(FeedbackProtocolError, match="^malformed_payload$"):
        parse(Outcome(b"VERDICT: reject\n" + tail))


def test_a_deep_valid_array_refuses_as_shape_or_decoder_limit():
    # Decoder recursion limits differ across Python versions. A successfully
    # decoded array still cannot stand in for the closed payload object.
    tail = b"[" * 1200 + b"]" * 1200
    with pytest.raises(FeedbackProtocolError) as refused:
        parse(Outcome(b"VERDICT: reject\n" + tail))
    assert refused.value.reason in {"invalid_payload", "malformed_payload"}


@pytest.mark.parametrize("raw", [
    '{"protocol":"conduct.feedback.v1","protocol":"conduct.feedback.v1","findings":[]}',
    '{"protocol":"conduct.feedback.v1","findings":[{"kind":"defect",'
    '"summary":"first","summary":"second","path":null,"line":null}]}',
])
def test_duplicate_keys_refuse_even_when_their_values_match(raw):
    with pytest.raises(FeedbackProtocolError, match="^duplicate_field$"):
        parse(Outcome(b"VERDICT: reject\n" + raw.encode()))


@pytest.mark.parametrize("number", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_json_constants_are_refused(number):
    raw = json.dumps(document()).replace('"line": null', f'"line": {number}')
    with pytest.raises(FeedbackProtocolError, match="^nonfinite_value$"):
        parse(Outcome(b"VERDICT: reject\n" + raw.encode()))


@pytest.mark.parametrize("value", [
    [], None, {"protocol": FEEDBACK_PROTOCOL},
    dict(protocol=FEEDBACK_PROTOCOL, findings=[finding()], grant_id="claimed"),
])
def test_missing_unknown_or_authority_fields_do_not_enter_the_payload(value):
    with pytest.raises(FeedbackProtocolError, match="^invalid_payload$"):
        parse(output(value))


def test_a_different_payload_protocol_cannot_borrow_the_callers_opt_in():
    with pytest.raises(FeedbackProtocolError, match="^protocol_mismatch$"):
        parse(output(dict(protocol="conduct.feedback.v2", findings=[finding()])))


@pytest.mark.parametrize("changes", [
    {"kind": "instruction"}, {"kind": []}, {"summary": ""}, {"summary": "  "},
    {"summary": None}, {"checker_id": "claimed"}, {"line": 0}, {"line": -1},
    {"line": True}, {"line": 1.0}, {"line": float("inf")},
    {"line": 1}, {"path": 5}, {"path": ""}, {"path": "/src/a.py"},
    {"path": "../a.py"}, {"path": "src/../a.py"}, {"path": "src/./a.py"},
    {"path": "src//a.py"}, {"path": "src/"}, {"path": "src\\a.py"},
    {"path": "C:/a.py"}, {"path": "a.py:stream"},
])
def test_finding_fields_and_relative_locations_are_closed(changes):
    # A huge exponent is ordinary JSON syntax producing a non-finite float;
    # unlike the non-standard Infinity token, it must fail the typed line rule.
    wire = output(document(finding(**changes)))
    if changes.get("line") == float("inf"):
        wire = replace(wire, output=wire.output.replace(b"Infinity", b"1e9999"))
    with pytest.raises(FeedbackProtocolError, match="^invalid_finding$"):
        parse(wire)


def test_all_four_finding_fields_are_required_even_when_a_location_is_unknown():
    for name in ("kind", "summary", "path", "line"):
        row = finding()
        del row[name]
        with pytest.raises(FeedbackProtocolError, match="^invalid_finding$"):
            parse(output(document(row)))


@pytest.mark.parametrize("char", [
    "\x00", "\x1f", "\n", "\r", "\t", "\x7f", "\x85", "\x9f", "\ud800", "\udfff",
])
@pytest.mark.parametrize("field_name", ["summary", "path"])
def test_decoded_controls_and_surrogates_refuse_even_when_json_escaped(char, field_name):
    with pytest.raises(FeedbackProtocolError, match="^invalid_finding$"):
        parse(output(document(finding(**{field_name: "before" + char + "after"})),
                     ascii_only=True))


@pytest.mark.parametrize("codepoint", [0x20, 0x7E, 0xA0, 0xD7FF, 0xE000])
@pytest.mark.parametrize("field_name", ["summary", "path"])
def test_codepoints_beside_the_forbidden_ranges_remain_exact(codepoint, field_name):
    text = "before" + chr(codepoint) + "after"
    value = document(finding(**{field_name: text}))
    parsed = parse(output(value, ascii_only=True))
    assert parsed.as_dict() == value
    assert getattr(parsed.findings[0], field_name) == text


@pytest.mark.parametrize("field_name,secret", [
    ("summary", 'quote"slash\\secret'), ("summary", "секрет"),
    ("path", "private-token"),
])
def test_decoded_secrets_are_refused_before_canonical_encoding(monkeypatch, field_name, secret):
    wire = output(document(finding(**{field_name: "before" + secret + "after"})),
                  ascii_only=True)

    def canonical_must_not_run(_document):
        pytest.fail("secret reached canonical encoding")

    monkeypatch.setattr(protocol, "_canonical", canonical_must_not_run)
    with pytest.raises(FeedbackProtocolError, match="^sensitive_material$") as failure:
        parse(wire, sensitive=(secret.encode("utf-8"),))
    assert secret not in str(failure.value)
    assert secret not in repr(failure.value)


def test_nonmatching_and_empty_sensitive_samples_do_not_change_the_material():
    value = document(finding(summary="The empty branch lacks a check."))
    assert parse(output(value), sensitive=(b"", b"private-token")).as_dict() == value
    with pytest.raises(FeedbackProtocolError, match="^invalid_sensitive_values$"):
        parse(output(value), sensitive=("not bytes",))


def test_the_parser_imports_and_runs_without_any_conductor_runtime_or_store():
    script = r'''
import importlib.util
import json
import sys
from types import SimpleNamespace
spec = importlib.util.spec_from_file_location("detached_feedback", sys.argv[1])
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
payload = {"protocol": "conduct.feedback.v1", "findings": [
    {"kind": "defect", "summary": "The empty case is wrong.", "path": None, "line": None}]}
outcome = SimpleNamespace(status="completed", exit_code=0, stdin_state="delivered",
    output_truncated=False, output_contains_env_value=False,
    output=b"VERDICT: reject\n" + json.dumps(payload).encode())
parsed = module.parse_feedback(outcome, opted_in_protocol="conduct.feedback.v1", sensitive=())
assert parsed.as_dict() == payload
assert not any(name == "conductor" or name.startswith("conductor.") for name in sys.modules)
print("detached parser accepted one finding")
'''
    completed = subprocess.run(
        [sys.executable, "-I", "-B", "-c", script, str(Path(protocol.__file__).resolve())],
        capture_output=True, text=True, timeout=15, check=False)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "detached parser accepted one finding"
