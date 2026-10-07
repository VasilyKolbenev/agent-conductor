"""The CSRF fixture corpus: its structure, and its own accept/refuse relation.

Split out of ``test_cockpit_command_api_freeze`` when that module crossed the
line cap, along the seam the house rule names: this is a self-contained circuit.
It reads one JSON corpus and holds it to the frozen error vocabulary imported
from next door, so the two sides of every check still come from two places.

What it does NOT claim is the same thing the parent module disclaimed: these are
request-shaped fixtures, and nothing here drives a server. The behaviour they
describe is proved against the real transport in
``tests/test_command_http_transport.py`` and over a real socket in
``tests/test_server_command_http.py``.
"""
from __future__ import annotations

import hmac
import json
from urllib.parse import urlsplit

import pytest

from conductor.command.api_contracts import ApiRefusal

from tests.test_cockpit_command_api_freeze import (
    CANON,
    EXPECTED_ERROR_CODES,
    _load_fixtures,
)


# --- Fixtures for the PENDING Day-2 C/API-1 gate (structure only) -----------

def _status_for_code() -> dict[str, int]:
    return {row["code"]: row["status"] for row in CANON["error_codes"]}


def _fixtures():
    return _load_fixtures()["fixtures"]


def _same_request_origin(headers: dict[str, str], allowed_hosts: set[str]) -> bool:
    host = headers.get("Host")
    if host not in allowed_hosts:
        return False
    expected = f"http://{host}"
    if "Origin" in headers:
        return headers["Origin"] == expected
    referer = urlsplit(headers.get("Referer", ""))
    return f"{referer.scheme}://{referer.netloc}" == expected


def _json_content_type(headers: dict[str, str]) -> bool:
    return headers.get("Content-Type", "").casefold() in {
        "application/json", "application/json; charset=utf-8",
    }


def test_csrf_fixtures_are_marked_as_a_pending_gate_not_a_behaviour_claim():
    data = _load_fixtures()
    assert "PENDING" in data["_readme"] and "NOT" in data["_readme"]
    assert data["_pending_gate"] == "C/API-1 (Day 2)"
    assert data["csrf_header"] == "X-Conduct-CSRF"
    assert set(data["loopback_origins"]) == {
        f"http://{host}" for host in data["loopback_hosts"]}
    assert len({
        data["current_process_token"], data["prior_process_token"],
        data["attacker_token"],
    }) == 3


@pytest.mark.parametrize("fixture", _fixtures(), ids=lambda f: f["name"])
def test_each_csrf_fixture_is_wellformed(fixture):
    assert set(fixture) >= {"name", "note", "request", "expected"}
    request = fixture["request"]
    assert set(request) >= {"method", "path", "headers", "csrf_token_source"}
    assert request["csrf_token_source"] in {"current_process", "prior_process",
                                            "attacker", "none"}
    expected = fixture["expected"]
    assert expected["disposition"] in {"accept", "refuse"}
    if expected["disposition"] == "refuse":
        assert expected["error_code"] in EXPECTED_ERROR_CODES
        assert expected["status"] == _status_for_code()[expected["error_code"]]
    else:
        assert expected["error_code"] is None
        assert expected["status"] == 201


@pytest.mark.parametrize("fixture", _fixtures(), ids=lambda f: f["name"])
def test_token_provenance_label_and_literal_header_agree_independently(fixture):
    data = _load_fixtures()
    token_by_source = {
        "current_process": data["current_process_token"],
        "prior_process": data["prior_process_token"],
        "attacker": data["attacker_token"],
        "none": None,
    }
    presented = fixture["request"]["headers"].get(data["csrf_header"])
    assert presented == token_by_source[fixture["request"]["csrf_token_source"]]


@pytest.mark.parametrize("fixture", _fixtures(), ids=lambda f: f["name"])
def test_each_csrf_fixture_encodes_the_documented_accept_refuse_relation(fixture):
    data = _load_fixtures()
    request, headers = fixture["request"], fixture["request"]["headers"]
    origin_ok = _same_request_origin(headers, set(data["loopback_hosts"]))
    presented = headers.get(data["csrf_header"])
    expected_token = data["current_process_token"]
    token_ok = presented is not None and hmac.compare_digest(presented, expected_token)
    content_ok = _json_content_type(headers) and isinstance(request.get("json_body"), dict)
    disposition = fixture["expected"]["disposition"]
    # Accept iff origin, current-process token, and JSON-object body all hold.
    assert (disposition == "accept") == (origin_ok and token_ok and content_ok)
    if disposition == "refuse":
        if not origin_ok:
            expected_code = "same_origin_denied"
        elif not token_ok:
            expected_code = "csrf_denied"
        else:
            expected_code = "malformed_request"
        assert fixture["expected"]["error_code"] == expected_code


def test_presented_token_and_process_memory_token_are_two_real_sides():
    data = _load_fixtures()
    accepted = next(row for row in _fixtures()
                    if row["name"] == "valid_same_origin_with_token")
    presented = accepted["request"]["headers"][data["csrf_header"]]
    expected = data["current_process_token"]
    assert presented == expected
    assert not hmac.compare_digest(data["prior_process_token"], expected)
    assert not hmac.compare_digest(data["attacker_token"], expected)


def _raw_header_values(pairs: list[list[str]], name: str) -> list[str]:
    wanted = name.casefold()
    return [value for key, value in pairs if key.casefold() == wanted]


def _raw_body_is_one_json_object(body_hex: str) -> bool:
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    try:
        body = bytes.fromhex(body_hex).decode("utf-8", errors="strict")
        decoded = json.loads(body, object_pairs_hook=unique_object)
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
        return False
    return isinstance(decoded, dict)


def _raw_transport_result(case: dict) -> tuple[str, str | None, str]:
    data, pairs = _load_fixtures(), case["raw_header_pairs"]
    hosts = _raw_header_values(pairs, "Host")
    if len(hosts) != 1 or hosts[0] not in data["loopback_hosts"]:
        return "refuse", "same_origin_denied", "host"
    expected_origin = f"http://{hosts[0]}"
    origins = _raw_header_values(pairs, "Origin")
    referers = _raw_header_values(pairs, "Referer")
    if len(origins) > 1 or len(referers) > 1:
        return "refuse", "same_origin_denied", "origin"
    origin_ok = (origins[0] == expected_origin if origins else
                 len(referers) == 1 and
                 f"{urlsplit(referers[0]).scheme}://{urlsplit(referers[0]).netloc}"
                 == expected_origin)
    if not origin_ok:
        return "refuse", "same_origin_denied", "origin"
    tokens = _raw_header_values(pairs, data["csrf_header"])
    if len(tokens) != 1 or not hmac.compare_digest(tokens[0], data["current_process_token"]):
        return "refuse", "csrf_denied", "csrf"
    content = _raw_header_values(pairs, "Content-Type")
    if len(content) != 1 or content[0].casefold() not in {
            "application/json", "application/json; charset=utf-8"}:
        return "refuse", "malformed_request", "content_type"
    if not _raw_body_is_one_json_object(case["body_utf8_hex"]):
        return "refuse", "malformed_request", "body"
    return "transport_pass", None, "contract"


def _raw_transport_cases():
    return _load_fixtures()["raw_transport_cases"]


@pytest.mark.parametrize("case", _raw_transport_cases(), ids=lambda row: row["name"])
def test_raw_transport_fixtures_hold_order_bytes_precedence_and_code(case):
    assert isinstance(case["raw_header_pairs"], list)
    assert all(isinstance(pair, list) and len(pair) == 2
               for pair in case["raw_header_pairs"])
    bytes.fromhex(case["body_utf8_hex"])
    disposition, code, phase = _raw_transport_result(case)
    assert (disposition, code, phase) == (
        case["expected"]["disposition"], case["expected"]["error_code"],
        case["expected"]["phase"])


def test_duplicate_headers_cannot_be_hidden_by_dict_get_or_last_wins():
    duplicate_names = {
        "raw_duplicate_content_type", "raw_conflicting_content_type",
        "raw_duplicate_host", "raw_conflicting_host", "raw_duplicate_origin",
        "raw_conflicting_origin", "raw_duplicate_referer", "raw_conflicting_referer",
        "raw_duplicate_csrf", "raw_conflicting_csrf",
    }
    cases = {row["name"]: row for row in _raw_transport_cases()}
    assert duplicate_names <= set(cases)
    for name in duplicate_names:
        case = cases[name]
        collapsed = {key.casefold(): [key, value] for key, value in case["raw_header_pairs"]}
        last_wins = {**case, "raw_header_pairs": list(collapsed.values())}
        assert _raw_transport_result(last_wins) != _raw_transport_result(case)


def test_duplicate_json_key_is_visible_before_normal_json_last_wins():
    case = next(row for row in _raw_transport_cases()
                if row["name"] == "raw_duplicate_json_key")
    body = bytes.fromhex(case["body_utf8_hex"]).decode("utf-8")
    assert json.loads(body) == {"x": 2}
    assert not _raw_body_is_one_json_object(case["body_utf8_hex"])


def test_raw_transport_precedence_is_pairwise_and_phase_visible():
    assert _load_fixtures()["transport_precedence"] == [
        "host_cardinality_and_allowlist",
        "origin_or_referer_cardinality_and_relation",
        "csrf_cardinality_and_equality",
        "content_type_cardinality_and_value",
        "utf8_json_object_without_duplicate_keys",
    ]
    cases = {row["name"]: _raw_transport_result(row)
             for row in _raw_transport_cases()}
    assert cases["raw_origin_precedes_csrf"] == (
        "refuse", "same_origin_denied", "origin")
    assert cases["raw_csrf_precedes_content_type"] == (
        "refuse", "csrf_denied", "csrf")
    assert cases["raw_content_type_precedes_invalid_utf8"] == (
        "refuse", "malformed_request", "content_type")
    assert cases["raw_host_failure_precedes_invalid_utf8"] == (
        "refuse", "same_origin_denied", "host")
