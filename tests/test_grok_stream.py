"""Offline wire witnesses for the opt-in Grok review. No CLI or account is used."""
from __future__ import annotations

import json

import pytest

from conductor.command.adapters.grok_stream import decode_stream

SID = "synthetic-session"
INVALID = (b"", "the Grok diagnostic stream did not establish a result")
OPEN = (b"", "the Grok diagnostic reported an opened session before the error")
NO_ID = (b"", "the Grok diagnostic reported no session ID before the error")
TEXT = {"type": "text", "text": "tail"}
THOUGHT = {"type": "thinking", "thinking": "private synthetic thought", "signature": "s"}
TOOL = {"type": "tool_use", "id": "t1", "name": "read_file", "input": {"text": "tool input"}}
SERVER = {"type": "server_tool_use", "id": "t2", "name": "web_search", "input": {"query": "q"}}
HITS = {"type": "web_search_tool_result", "tool_use_id": "t2", "content": [
    {"type": "web_search_result", "url": "https://example.invalid/", "title": "tool title"}]}
TOOL_RESULT = {"type": "tool_result", "tool_use_id": "t1", "content": "tool output",
               "is_error": False}
INIT = {"type": "system", "subtype": "init", "session_id": SID}
COMPACT = {"type": "system", "subtype": "compact_boundary", "session_id": SID,
           "compact_metadata": {"trigger": "auto", "pre_tokens": 20}}
SUCCESS = {"type": "result", "subtype": "success", "is_error": False, "session_id": SID,
           "stop_reason": "end_turn", "result": "tail"}
ERROR = {"type": "result", "subtype": "error_during_execution", "is_error": True,
         "errors": ["synthetic private vendor detail"], "session_id": SID, "stop_reason": None}


def assistant(*blocks):
    return {"type": "assistant", "session_id": SID, "parent_tool_use_id": None,
            "message": {"type": "message", "role": "assistant", "content": list(blocks)}}


def user(*blocks):
    return {"type": "user", "session_id": SID, "parent_tool_use_id": None,
            "message": {"role": "user", "content": list(blocks)}}


def wire(*rows):
    return b"".join(json.dumps(row, ensure_ascii=True).encode("ascii") + b"\n" for row in rows)


def test_collects_only_direct_assistant_text_preserving_bytes_and_repetitions():
    first = {"type": "text", "text": " начало\r\n"}
    last = {"type": "text", "text": "🚀\n "}
    output = wire(INIT, assistant(first, THOUGHT, first, TOOL), user(TOOL_RESULT), COMPACT,
                  assistant(TEXT, SERVER, HITS, last), {**SUCCESS, "result": "tail🚀\n "})
    assert decode_stream(output, 0) == (" начало\r\n начало\r\ntail🚀\n ".encode(), None)


def test_terminal_can_corroborate_a_final_frame_without_text():
    output = wire(INIT, assistant(TEXT), assistant(TOOL), user(TOOL_RESULT),
                  {**SUCCESS, "result": ""})
    assert decode_stream(output, 0) == (b"tail", None)


@pytest.mark.parametrize(("session", "expected"), [(SID, OPEN), ("", NO_ID)])
def test_reports_only_the_session_evidence_on_a_complete_error(session, expected):
    output = wire({**INIT, "session_id": session}, {**ERROR, "session_id": session})
    assert decode_stream(output, 1) == expected


@pytest.mark.parametrize(("errors", "cause"), [
    (["HTTP 403 Forbidden: private"], "the harness reported an access refusal"),
    (["Internal error: HTTP 403 Forbidden: private"], "the harness reported an access refusal"),
    (["Internal error: unrecognized private detail"], "the harness reported an internal error"),
    (["HTTP 429: private"], "the harness reported a subscription usage limit"),
    (["Connection closed unexpectedly"],
     "the harness reported that its local prompt channel closed"),
    (["Grok Build is not yet available for this account."],
     "the harness reported an access refusal"),
    (["HTTP 503: private"], "the harness reported a server-side error"),
    (["Invalid params: unsupported content block in prompt: Audio(private)"],
     "the harness rejected a prompt content block"),
    (["quoted output: HTTP 403 Forbidden"], None),
    (["HTTP 4030 unknown"], None),
    (["HTTP 403", "HTTP 429"], None),
])
def test_recognized_post_open_cause_is_fixed_and_never_copies_error_text(errors, cause):
    expected = OPEN[1] + " | " + cause if cause else OPEN[1]
    assert decode_stream(wire(INIT, {**ERROR, "errors": errors}), 1) == (b"", expected)


@pytest.mark.parametrize(("subtype", "stop_reason", "cause"), [
    ("error_during_execution", None, None),
    ("error_during_execution", "max_tokens", "the harness reported an output token limit"),
    ("error_during_execution", "refusal", "the harness reported a turn refusal"),
    ("error_during_execution", "cancelled", "the harness reported that the turn was cancelled"),
    ("error_max_turns", "cancelled", "the harness reported that the turn limit was reached"),
])
def test_an_error_after_assistant_output_discards_the_partial_artifact(subtype, stop_reason, cause):
    end = {**ERROR, "subtype": subtype, "stop_reason": stop_reason}
    expected = OPEN[1] + " | " + cause if cause else OPEN[1]
    assert decode_stream(wire(INIT, assistant(TEXT), end), 1) == (b"", expected)


@pytest.mark.parametrize(("rows", "code"), [
    ([INIT, SUCCESS], 0),
    ([INIT, assistant(TEXT), {**SUCCESS, "result": "tail!"}], 0),
    ([INIT, assistant(TEXT), {**SUCCESS, "errors": []}], 0),
    ([INIT, assistant(TEXT), {**SUCCESS, "error": "private refusal"}], 0),
    ([INIT, assistant(TEXT), {**SUCCESS, "structuredOutputError": "private refusal"}], 0),
    ([INIT, assistant(TEXT), {**SUCCESS, "message": "ordinary-json error"}], 0),
    ([INIT, assistant(TEXT), {**SUCCESS, "is_error": 0}], 0),
    ([INIT, assistant(TEXT), {**SUCCESS, "stop_reason": "max_tokens"}], 0),
    ([INIT, assistant(TEXT), SUCCESS], 1),
    ([INIT, assistant(TEXT), SUCCESS], None),
    ([INIT, assistant({"type": "text", "text": " "}), {**SUCCESS, "result": " "}], 0),
    ([INIT, assistant(TEXT), {**SUCCESS, "session_id": "other"}], 0),
    ([{**INIT, "session_id": ""}, {**assistant(TEXT), "session_id": ""},
      {**SUCCESS, "session_id": ""}], 0),
    ([INIT, ERROR], 0),
    ([INIT, {**ERROR, "result": ""}], 1),
    ([INIT, {**ERROR, "errors": "private"}], 1),
    ([INIT, {**ERROR, "errors": []}], 1),
    ([INIT, {**ERROR, "is_error": 1}], 1),
    ([INIT, {**ERROR, "subtype": "future-error"}], 1),
    ([INIT, {**ERROR, "stop_reason": "end_turn"}], 1),
    ([INIT, {**ERROR, "stop_reason": "future"}], 1),
    ([INIT, {**ERROR, "session_id": None}], 1),
    ([INIT, {**ERROR, "session_id": ""}], 1),
    ([{**INIT, "session_id": ""}, ERROR], 1),
    ([{**INIT, "session_id": " "}, {**ERROR, "session_id": " "}], 1),
    ([INIT, INIT, ERROR], 1),
    ([ERROR], 1),
    ([ERROR, INIT], 1),
    ([INIT, ERROR, ERROR], 1),
    ([INIT, ERROR, COMPACT], 1),
    ([INIT, assistant(TEXT)], 0),
    ([INIT, {**assistant(TEXT), "session_id": "other"}, ERROR], 1),
    ([INIT, {"type": "stream_event", "session_id": SID}, ERROR], 1),
    ([INIT, {**COMPACT, "subtype": "unknown"}, ERROR], 1),
    ([INIT, {**assistant(TEXT), "parent_tool_use_id": "child"}, ERROR], 1),
    ([INIT, assistant({"type": "future", "text": "wrong"}, TEXT), SUCCESS], 0),
    ([INIT, assistant({"type": "text", "text": None}, TEXT), SUCCESS], 0),
    ([INIT, {**assistant(TEXT), "message": {"role": "user", "content": [TEXT]}}, ERROR], 1),
    ([INIT, user(TEXT), ERROR], 1),
    ([INIT, {"type": [], "session_id": SID}, ERROR], 1),
    ([INIT, assistant({"type": "text", "text": "\ud800"}),
      {**SUCCESS, "result": "\ud800"}], 0),
])
def test_rejects_unsupported_or_conflicting_evidence(rows, code):
    assert decode_stream(wire(*rows), code) == INVALID


@pytest.mark.parametrize("output", [
    wire(INIT, ERROR).rstrip(b"\n"),
    wire(INIT) + b"\n" + wire(ERROR),
    wire(INIT) + b'{"type":"result","type":"result","session_id":"synthetic-session",'
    b'"is_error":true,"subtype":"error_during_execution","errors":["e"],"stop_reason":null}\n',
    wire(INIT, {**ERROR, "unused": float("nan")}),
    wire(INIT) + b"[]\n" + wire(ERROR),
    wire(INIT) + b"\xff\n" + wire(ERROR),
    wire(INIT) + b"[" * 2000 + b"]" * 2000 + b"\n" + wire(ERROR),
])
def test_malformed_or_unterminated_ndjson_establishes_no_phase(output):
    assert decode_stream(output, 1) == INVALID


def test_accepts_exactly_the_bounded_wire_and_refuses_one_more_byte():
    body = wire(INIT, assistant(TEXT), SUCCESS)
    padding = b" " * (48 * 1024 - len(body))
    assert decode_stream(padding + body, 0) == (b"tail", None)
    assert decode_stream(b" " + padding + body, 0) == INVALID
