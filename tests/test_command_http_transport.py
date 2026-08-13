"""Raw browser transport pins for the C/API-1 command boundary."""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from conductor.command.http_transport import (
    CommandSession,
    HttpRefusal,
    validate_command_host,
    validate_command_mutation,
)


_FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "cockpit_command_csrf_fixtures.json")
DATA = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
PORT = 17802
TOKEN = DATA["current_process_token"]
HOSTS = frozenset({f"127.0.0.1:{PORT}", f"localhost:{PORT}"})


def _replace_port(value):
    if isinstance(value, str):
        return value.replace("{port}", str(PORT))
    if isinstance(value, list):
        return [_replace_port(item) for item in value]
    if isinstance(value, dict):
        return {key: _replace_port(item) for key, item in value.items()}
    return value


def _legacy_case(row):
    request = _replace_port(row["request"])
    headers = tuple(request["headers"].items())
    body = json.dumps(
        request.get("json_body"), ensure_ascii=False,
        sort_keys=True, separators=(",", ":")).encode("utf-8")
    return headers, body


def _run(headers, body):
    try:
        decoded = validate_command_mutation(
            headers, body, allowed_hosts=HOSTS, current_token=TOKEN)
    except HttpRefusal as refusal:
        return "refuse", refusal.code, refusal.status, refusal.phase, None
    return "accept", None, 201, "contract", decoded


@pytest.mark.parametrize("row", DATA["fixtures"], ids=lambda row: row["name"])
def test_structured_csrf_fixtures_drive_the_real_transport(row):
    disposition, code, status, _phase, decoded = _run(*_legacy_case(row))
    assert (disposition, code, status) == (
        row["expected"]["disposition"], row["expected"]["error_code"],
        row["expected"]["status"])
    if disposition == "accept":
        assert decoded == row["request"]["json_body"]


@pytest.mark.parametrize(
    "row", DATA["raw_transport_cases"], ids=lambda row: row["name"])
def test_ordered_raw_header_and_body_fixtures_drive_frozen_precedence(row):
    headers = tuple(tuple(pair) for pair in _replace_port(row["raw_header_pairs"]))
    body = bytes.fromhex(row["body_utf8_hex"])
    disposition, code, _status, phase, decoded = _run(headers, body)
    expected_disposition = (
        "accept" if row["expected"]["disposition"] == "transport_pass" else "refuse")
    assert (disposition, code, phase) == (
        expected_disposition, row["expected"]["error_code"],
        row["expected"]["phase"])
    if disposition == "accept":
        assert decoded == {"x": 1}


def test_duplicate_headers_cannot_be_hidden_by_mapping_or_last_wins():
    duplicates = [
        row for row in DATA["raw_transport_cases"]
        if row["name"].startswith(("raw_duplicate_", "raw_conflicting_"))
        and row["name"] != "raw_duplicate_json_key"
    ]
    assert len(duplicates) == 10
    for row in duplicates:
        pairs = tuple(tuple(pair) for pair in _replace_port(row["raw_header_pairs"]))
        body = bytes.fromhex(row["body_utf8_hex"])
        original = _run(pairs, body)
        collapsed = {key.casefold(): (key, value) for key, value in pairs}
        assert _run(tuple(collapsed.values()), body) != original


def test_duplicate_json_key_cannot_be_hidden_by_normal_json_last_wins():
    row = next(item for item in DATA["raw_transport_cases"]
               if item["name"] == "raw_duplicate_json_key")
    pairs = tuple(tuple(pair) for pair in _replace_port(row["raw_header_pairs"]))
    body = bytes.fromhex(row["body_utf8_hex"])
    assert json.loads(body) == {"x": 2}
    assert _run(pairs, body)[:4] == (
        "refuse", "malformed_request", 400, "body")


def test_raw_fixture_header_pairs_are_accepted_without_pre_normalization():
    row = next(item for item in DATA["raw_transport_cases"]
               if item["name"] == "raw_valid_transport")
    pairs = _replace_port(row["raw_header_pairs"])
    assert isinstance(pairs[0], list)
    assert _run(pairs, bytes.fromhex(row["body_utf8_hex"]))[-1] == {"x": 1}


def test_each_precedence_door_wins_over_a_later_failure():
    expected = {
        "raw_origin_precedes_csrf": ("same_origin_denied", "origin"),
        "raw_csrf_precedes_content_type": ("csrf_denied", "csrf"),
        "raw_content_type_precedes_invalid_utf8": (
            "malformed_request", "content_type"),
        "raw_host_failure_precedes_invalid_utf8": ("same_origin_denied", "host"),
    }
    rows = {row["name"]: row for row in DATA["raw_transport_cases"]}
    for name, relation in expected.items():
        row = rows[name]
        pairs = tuple(tuple(pair) for pair in _replace_port(row["raw_header_pairs"]))
        assert _run(pairs, bytes.fromhex(row["body_utf8_hex"]))[1:4:2] == relation


def test_process_session_mints_32_bytes_once_and_never_reveals_token_in_repr():
    calls = []

    def mint(size):
        calls.append(size)
        return "process-token"

    session = CommandSession.mint(PORT, mint)
    assert calls == [32]
    assert session.session_response(f"127.0.0.1:{PORT}") == {
        "csrf_token": "process-token", "origin": f"http://127.0.0.1:{PORT}"}
    assert "process-token" not in repr(session)


def test_session_host_is_exact_and_token_comparison_has_independent_sides():
    session = CommandSession(PORT, TOKEN)
    with pytest.raises(HttpRefusal) as caught:
        session.session_response(f"attacker.example:{PORT}")
    assert (caught.value.code, caught.value.phase) == ("same_origin_denied", "host")
    valid = next(row for row in DATA["fixtures"]
                 if row["name"] == "valid_same_origin_with_token")
    headers, body = _legacy_case(valid)
    assert session.validate_mutation(headers, body) == valid["request"]["json_body"]
    prior = CommandSession(PORT, DATA["prior_process_token"])
    with pytest.raises(HttpRefusal, match="current"):
        prior.validate_mutation(headers, body)


def test_host_get_gate_refuses_duplicate_equal_host_before_any_read():
    host = f"127.0.0.1:{PORT}"
    assert validate_command_host((("Host", host),), HOSTS) == host
    with pytest.raises(HttpRefusal) as caught:
        validate_command_host((("Host", host), ("host", host)), HOSTS)
    assert (caught.value.code, caught.value.phase) == ("same_origin_denied", "host")


def test_transport_refusals_are_fixed_and_carry_no_submitted_secret_or_os_text():
    secret = "APIKEY_SECRET_PRESENTED"
    headers = (
        ("Host", f"127.0.0.1:{PORT}"),
        ("Origin", f"http://127.0.0.1:{PORT}"),
        ("X-Conduct-CSRF", secret),
        ("Content-Type", "application/json"),
    )
    with pytest.raises(HttpRefusal) as caught:
        validate_command_mutation(
            headers, b"{}", allowed_hosts=HOSTS, current_token=TOKEN)
    assert secret not in str(caught.value) and secret not in caught.value.message


@pytest.mark.parametrize("literal", [
    "NaN", "Infinity", "-Infinity", "1e999", "-1e999", "+1e999",
])
def test_every_non_finite_json_spelling_is_refused_at_the_body_phase(literal):
    row = next(item for item in DATA["raw_transport_cases"]
               if item["name"] == "raw_valid_transport")
    headers = _replace_port(row["raw_header_pairs"])
    disposition = _run(headers, f'{{"outer":[{{"value":{literal}}}]}}'.encode())
    assert disposition[:4] == ("refuse", "malformed_request", 400, "body")


def test_nested_finite_json_numbers_remain_the_independent_accept_side():
    row = next(item for item in DATA["raw_transport_cases"]
               if item["name"] == "raw_valid_transport")
    headers = _replace_port(row["raw_header_pairs"])
    result = _run(headers, b'{"outer":[1.25,{"value":-1e308}]}')
    assert result[:4] == ("accept", None, 201, "contract")
    assert math.isfinite(result[-1]["outer"][1]["value"])


def _object_graph_text(root):
    seen, pending, fragments = set(), [root], []
    while pending:
        value = pending.pop()
        if id(value) in seen:
            continue
        seen.add(id(value))
        fragments.extend((repr(value), str(value), repr(getattr(value, "__dict__", {}))))
        for name in ("__cause__", "__context__"):
            nested = getattr(value, name, None)
            if nested is not None:
                pending.append(nested)
    return " ".join(fragments)


def test_body_refusal_object_graph_retains_no_invalid_utf8_or_json_sentinel():
    row = next(item for item in DATA["raw_transport_cases"]
               if item["name"] == "raw_valid_transport")
    headers = _replace_port(row["raw_header_pairs"])
    for body in (b'APIKEY_SECRET_JSON', b'\xffAPIKEY_SECRET_UTF8'):
        with pytest.raises(HttpRefusal) as caught:
            validate_command_mutation(
                headers, body, allowed_hosts=HOSTS, current_token=TOKEN)
        graph = _object_graph_text(caught.value)
        assert "APIKEY_SECRET" not in graph
        assert caught.value.__cause__ is None and caught.value.__context__ is None


def test_header_iterator_refusal_object_graph_retains_no_iterator_exception():
    def hostile_headers():
        raise RuntimeError("APIKEY_SECRET_HEADER_ITERATOR")
        yield ("Host", "unreachable")

    with pytest.raises(HttpRefusal) as caught:
        validate_command_mutation(
            hostile_headers(), b"{}", allowed_hosts=HOSTS, current_token=TOKEN)
    assert (caught.value.code, caught.value.phase) == ("same_origin_denied", "host")
    assert "APIKEY_SECRET" not in _object_graph_text(caught.value)
    assert caught.value.__cause__ is None and caught.value.__context__ is None


def test_http_refusal_phase_is_the_only_constructor_authority():
    expected = {
        "host": ("same_origin_denied", 403, "request Host is not allowed"),
        "origin": ("same_origin_denied", 403, "request origin is not allowed"),
        "csrf": ("csrf_denied", 403, "request CSRF token is not current"),
        "content_type": (
            "malformed_request", 400, "request Content-Type is not supported"),
        "body": ("malformed_request", 400, "request body is not one JSON object"),
    }
    for phase, relation in expected.items():
        refusal = HttpRefusal(phase)
        assert (refusal.code, refusal.status, refusal.message) == relation
        assert refusal.__dict__ == {"phase": phase}
    with pytest.raises(ValueError, match="phase"):
        HttpRefusal("not-a-phase")
    with pytest.raises(TypeError):
        HttpRefusal("host", 403)


@pytest.mark.parametrize("referer", ["http://[", "http://]", "http://[::1"])
def test_malformed_referer_is_one_detached_fixed_origin_refusal(referer):
    headers = [
        ("Host", f"127.0.0.1:{PORT}"), ("Referer", referer),
        ("X-Conduct-CSRF", TOKEN), ("Content-Type", "application/json"),
    ]
    with pytest.raises(HttpRefusal) as caught:
        validate_command_mutation(
            headers, b"{}", allowed_hosts=HOSTS, current_token=TOKEN)
    refusal = caught.value
    assert (refusal.phase, refusal.code, refusal.message) == (
        "origin", "same_origin_denied", "request origin is not allowed")
    assert refusal.__cause__ is refusal.__context__ is None
    assert referer not in _object_graph_text(refusal)


def test_malformed_origin_is_the_same_detached_fixed_origin_refusal():
    hostile = "http://["
    headers = [
        ("Host", f"127.0.0.1:{PORT}"), ("Origin", hostile),
        ("X-Conduct-CSRF", TOKEN), ("Content-Type", "application/json"),
    ]
    with pytest.raises(HttpRefusal) as caught:
        validate_command_mutation(
            headers, b"{}", allowed_hosts=HOSTS, current_token=TOKEN)
    refusal = caught.value
    assert (refusal.phase, refusal.code, refusal.message) == (
        "origin", "same_origin_denied", "request origin is not allowed")
    assert refusal.__cause__ is refusal.__context__ is None
    assert hostile not in _object_graph_text(refusal)


def test_non_ascii_csrf_is_one_detached_fixed_csrf_refusal():
    headers = [
        ("Host", f"127.0.0.1:{PORT}"),
        ("Origin", f"http://127.0.0.1:{PORT}"),
        ("X-Conduct-CSRF", "APIKEY_SECRET_\u03bb"),
        ("Content-Type", "application/json"),
    ]
    with pytest.raises(HttpRefusal) as caught:
        validate_command_mutation(
            headers, b"{}", allowed_hosts=HOSTS, current_token=TOKEN)
    refusal = caught.value
    assert (refusal.phase, refusal.code, refusal.message) == (
        "csrf", "csrf_denied", "request CSRF token is not current")
    assert refusal.__cause__ is refusal.__context__ is None
    assert "APIKEY_SECRET" not in _object_graph_text(refusal)


@pytest.mark.parametrize("presented", ["\u03bb-secret", "ascii-presented"])
def test_non_ascii_current_token_never_becomes_header_authority(presented):
    current = "\u03bb-secret"
    headers = [
        ("Host", f"127.0.0.1:{PORT}"),
        ("Origin", f"http://127.0.0.1:{PORT}"),
        ("X-Conduct-CSRF", presented),
        ("Content-Type", "application/json"),
    ]
    with pytest.raises(HttpRefusal) as caught:
        validate_command_mutation(
            headers, b"{}", allowed_hosts=HOSTS, current_token=current)
    refusal = caught.value
    assert (refusal.phase, refusal.code, refusal.message) == (
        "csrf", "csrf_denied", "request CSRF token is not current")
    assert refusal.__cause__ is refusal.__context__ is None
    assert "secret" not in _object_graph_text(refusal)


def test_excessive_json_depth_is_one_detached_fixed_body_refusal():
    body = b'{"nested":' + b"[" * 1100 + b"0" + b"]" * 1100 + b"}"
    row = next(item for item in DATA["raw_transport_cases"]
               if item["name"] == "raw_valid_transport")
    with pytest.raises(HttpRefusal) as caught:
        validate_command_mutation(
            _replace_port(row["raw_header_pairs"]), body,
            allowed_hosts=HOSTS, current_token=TOKEN)
    refusal = caught.value
    assert (refusal.phase, refusal.code, refusal.message) == (
        "body", "malformed_request", "request body is not one JSON object")
    assert refusal.__cause__ is refusal.__context__ is None


def test_escape_paths_do_not_change_frozen_origin_first_precedence():
    headers = [
        ("Host", f"127.0.0.1:{PORT}"), ("Referer", "http://["),
        ("X-Conduct-CSRF", "\u03bb"), ("Content-Type", "text/plain"),
    ]
    with pytest.raises(HttpRefusal) as caught:
        validate_command_mutation(
            headers, b"[", allowed_hosts=HOSTS, current_token=TOKEN)
    assert caught.value.phase == "origin"
