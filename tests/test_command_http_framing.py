"""The frozen command framing door bounds every body before server parsing."""
from __future__ import annotations

import pytest

from conductor.command.http_transport import (
    MAX_COMMAND_BODY_BYTES,
    CommandSession,
    HttpRefusal,
    command_content_length,
)


TOKEN = "current-process-token"


def headers(*extra):
    return (("Host", "127.0.0.1:7802"), *extra)


@pytest.mark.parametrize("value,expected", [
    ("0", 0),
    ("000", 0),
    ("1", 1),
    (str(MAX_COMMAND_BODY_BYTES), MAX_COMMAND_BODY_BYTES),
    ("00065536", MAX_COMMAND_BODY_BYTES),
])
def test_one_nonnegative_decimal_length_through_the_exact_cap_is_accepted(
        value, expected):
    assert command_content_length(headers(("Content-Length", value))) == expected


@pytest.mark.parametrize("pairs", [
    (),
    (("Content-Length", "1"), ("content-length", "1")),
    (("Content-Length", "-1"),),
    (("Content-Length", "+1"),),
    (("Content-Length", "1.0"),),
    (("Content-Length", "１"),),
    (("Content-Length", str(MAX_COMMAND_BODY_BYTES + 1)),),
    (("Content-Length", "9" * 1000),),
])
def test_missing_duplicate_nondecimal_negative_and_overflow_lengths_refuse(pairs):
    with pytest.raises(HttpRefusal) as caught:
        command_content_length(headers(*pairs))
    assert (caught.value.code, caught.value.status, caught.value.phase) == (
        "malformed_request", 400, "body")


@pytest.mark.parametrize("pairs", [
    (("Transfer-Encoding", "chunked"),),
    (("Transfer-Encoding", "identity"),),
    (("Content-Length", "2"), ("Transfer-Encoding", "chunked")),
])
def test_any_transfer_encoding_is_refused_including_with_content_length(pairs):
    with pytest.raises(HttpRefusal, match="one JSON object"):
        command_content_length(headers(*pairs))


def test_header_pairs_are_not_collapsed_to_last_wins():
    planted = headers(
        ("Content-Length", str(MAX_COMMAND_BODY_BYTES + 1)),
        ("content-length", "2"))
    collapsed = {name.casefold(): (name, value) for name, value in planted}
    assert command_content_length(tuple(collapsed.values())) == 2
    with pytest.raises(HttpRefusal):
        command_content_length(planted)


def test_the_literal_cap_and_comparison_boundary_are_pinned():
    assert MAX_COMMAND_BODY_BYTES == 64 * 1024 == 65536
    assert command_content_length(headers(("Content-Length", "65536"))) == 65536
    with pytest.raises(HttpRefusal):
        command_content_length(headers(("Content-Length", "65537")))


def test_exact_cap_reaches_the_json_parser_instead_of_the_size_refusal():
    prefix = b'{"accepted":true}'
    body = prefix + b" " * (MAX_COMMAND_BODY_BYTES - len(prefix))
    raw = headers(
        ("Origin", "http://127.0.0.1:7802"),
        ("X-Conduct-CSRF", TOKEN),
        ("Content-Type", "application/json"),
        ("Content-Length", str(len(body))))
    assert command_content_length(raw) == len(body)
    assert CommandSession(7802, TOKEN).validate_mutation(raw, body) == {
        "accepted": True}


def test_header_preflight_and_full_validation_share_one_length_authority():
    body = b'{"accepted":true}'
    raw = headers(
        ("Origin", "http://127.0.0.1:7802"),
        ("X-Conduct-CSRF", TOKEN),
        ("Content-Type", "application/json"),
        ("Content-Length", str(len(body))))
    session = CommandSession(7802, TOKEN)
    assert session.body_length(raw) == len(body)
    assert session.validate_mutation(raw, body) == {"accepted": True}
    with pytest.raises(HttpRefusal):
        session.validate_mutation(raw, body[:-1])
