"""The typed parser's integer field, first-line rule, opt-in, refusal vocabulary and the ceiling its readers share.

Each test here is the witness a surviving mutant of the first parser tests
lacked: the `line` rows had no path, no prefix carried a second verdict line,
and the opt-in was compared but never typed. The last two tests hold the durable
record and the Studio read door to the same line ceiling the parser admits.
"""
from __future__ import annotations

import json
from unittest import mock

import pytest

from conductor.command.adapters.feedback_protocol import (
    FEEDBACK_PROTOCOL, FINDING_KINDS, FeedbackProtocolError, MAX_FINDINGS, MAX_LINE,
    MAX_PAYLOAD_BYTES, REASONS,
)
from conductor.command.adapters.independent_check import verdict
from tests.test_feedback_protocol import Outcome, document, finding, output, parse


def test_digits_of_a_sampled_secret_in_the_line_field_are_refused():
    secret = b"8675309"
    wire = output(document(finding(path="src/a.py", line=int(secret))))
    assert int(secret) <= MAX_LINE, "control: only the scan can refuse this line"
    with pytest.raises(FeedbackProtocolError, match="^sensitive_material$"):
        parse(wire, sensitive=(secret,))
    assert parse(wire).findings[0].line == int(secret), "control: accepted without the sample"


@pytest.mark.parametrize("line", [MAX_LINE + 1, 2**53 + 1, int("9" * 400)])
def test_a_line_above_the_ceiling_refuses_the_payload(line):
    with pytest.raises(FeedbackProtocolError, match="^invalid_finding$"):
        parse(output(document(finding(path="src/a.py", line=line))))
    highest = parse(output(document(finding(path="src/a.py", line=MAX_LINE))))
    assert highest.findings[0].line == MAX_LINE, "control: the ceiling itself is a valid line"


@pytest.mark.parametrize("line", [0, -1, True, 1.0, "12"])
def test_a_line_of_the_wrong_type_or_range_refuses_even_beside_a_valid_path(line):
    with pytest.raises(FeedbackProtocolError, match="^invalid_finding$"):
        parse(output(document(finding(path="src/a.py", line=line))))


@pytest.mark.parametrize("prefix", [
    b"VERDICT: accept\nVERDICT: reject\n", b"Reasons first\nVERDICT: reject\n",
    b"VERDICT: reject x\nVERDICT: reject\n"])
def test_a_reject_line_below_the_first_non_empty_line_publishes_nothing(prefix):
    wire = Outcome(prefix + json.dumps(document()).encode("utf-8"))
    assert verdict(wire) != "rejected", "control: the existing parser does not reject this"
    with pytest.raises(FeedbackProtocolError, match="^not_rejected$"):
        parse(wire)


@pytest.mark.parametrize("claimed", [mock.ANY, b"conduct.feedback.v1", ["conduct.feedback.v1"]])
def test_only_the_exact_string_opts_a_caller_in(claimed):
    with pytest.raises(FeedbackProtocolError, match="^not_opted_in$"):
        parse(output(document()), opted_in_protocol=claimed)
    assert parse(output(document()), opted_in_protocol=FEEDBACK_PROTOCOL).findings


def test_the_refusal_vocabulary_is_closed_and_carries_no_decoder_context():
    with pytest.raises(ValueError, match="closed vocabulary"):
        FeedbackProtocolError("whatever the child printed")
    for wire in (Outcome(b"VERDICT: reject\nplease fix sk-LIVE-SECRET, not json"),
                 Outcome(b"VERDICT: reject\n\xff\xfe sk-LIVE-SECRET"),
                 object()):
        with pytest.raises(FeedbackProtocolError) as refused:
            parse(wire)
        assert refused.value.reason in REASONS
        assert refused.value.__context__ is None and refused.value.__cause__ is None


def test_the_durable_record_keeps_every_bound_of_the_parser():
    from conductor.command import feedback_payload as record

    assert (record.MAX_FINDINGS, record.MAX_PAYLOAD_BYTES, record.FINDING_KINDS, record.MAX_LINE) == (
        MAX_FINDINGS, MAX_PAYLOAD_BYTES, FINDING_KINDS, MAX_LINE)
    stored = record.settled_payload(document(finding(path="src/a.py", line=MAX_LINE)))
    assert stored["findings"][0]["line"] == MAX_LINE, "control: the ceiling itself is stored"
    with pytest.raises(record.FeedbackPayloadError, match="^invalid_finding$"):
        record.settled_payload(document(finding(path="src/a.py", line=MAX_LINE + 1)))


def test_the_studio_read_door_keeps_the_parsers_line_ceiling(tmp_path, monkeypatch):
    from tests.test_studio_feedback import js, reading

    value = reading(tmp_path, monkeypatch)
    result = js(value, """
      const at=(line)=>{const copy=structuredClone(p);
        const row=copy.records.find(x=>x.record_type==='correction_feedback').record;
        row.payload.findings[0].line=line;
        return [feedback.validFeedback(row), boundary.projectRunRead(copy)!==null];};
      console.log(JSON.stringify({ceiling:at(CEILING), above:at(CEILING+1)}));
    """.replace("CEILING", str(MAX_LINE)))
    assert result == {"ceiling": [True, True], "above": [False, False]}
