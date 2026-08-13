"""Raw HTTP validation for the loopback command surface.

This module consumes ordered header pairs and body bytes. It deliberately has
no server, store, service, runtime, filesystem, cookie, redirect, or CORS door.
"""
from __future__ import annotations

import hmac
import json
import math
import secrets
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any
from urllib.parse import urlsplit


_JSON_MEDIA_TYPES = frozenset({
    "application/json", "application/json; charset=utf-8",
})
_REFUSALS = MappingProxyType({
    "host": (
        "same_origin_denied", 403, "request Host is not allowed"),
    "origin": (
        "same_origin_denied", 403, "request origin is not allowed"),
    "csrf": (
        "csrf_denied", 403, "request CSRF token is not current"),
    "content_type": (
        "malformed_request", 400, "request Content-Type is not supported"),
    "body": (
        "malformed_request", 400, "request body is not one JSON object"),
})


@dataclass(frozen=True)
class HttpRefusal(Exception):
    """A fixed transport refusal carrying no submitted header or body value."""

    phase: str

    def __post_init__(self) -> None:
        if self.phase not in _REFUSALS:
            raise ValueError("invalid HTTP refusal phase")

    @property
    def code(self) -> str:
        return _REFUSALS[self.phase][0]

    @property
    def status(self) -> int:
        return _REFUSALS[self.phase][1]

    @property
    def message(self) -> str:
        return _REFUSALS[self.phase][2]

    def __str__(self) -> str:
        return self.message


class CommandSession:
    """One process-memory CSRF token and the loopback hosts it belongs to."""

    __slots__ = ("_allowed_hosts", "_token")

    def __init__(self, port: int, token: str) -> None:
        if isinstance(port, bool) or not isinstance(port, int) or not 0 < port <= 65535:
            raise ValueError("port must be an integer from 1 through 65535")
        if not isinstance(token, str) or not token:
            raise ValueError("CSRF token must be non-empty text")
        self._allowed_hosts = frozenset({f"127.0.0.1:{port}", f"localhost:{port}"})
        self._token = token

    @classmethod
    def mint(
            cls, port: int,
            token_factory: Callable[[int], str] = secrets.token_urlsafe) -> "CommandSession":
        """Mint one token with at least 32 bytes of source entropy."""
        return cls(port, token_factory(32))

    @property
    def allowed_hosts(self) -> frozenset[str]:
        """Return the two exact Host values accepted by this process."""
        return self._allowed_hosts

    def session_response(self, host: str) -> dict[str, str]:
        """Build the no-store GET body after the caller validates Host."""
        validate_command_host((("Host", host),), self._allowed_hosts)
        return {"csrf_token": self._token, "origin": f"http://{host}"}

    def validate_mutation(
            self, raw_header_pairs: Iterable[tuple[str, str]],
            raw_body: bytes) -> dict[str, Any]:
        """Validate one browser mutation against this process's independent token."""
        return validate_command_mutation(
            raw_header_pairs, raw_body,
            allowed_hosts=self._allowed_hosts, current_token=self._token)

    def __repr__(self) -> str:
        return "CommandSession(<process-memory token>)"


def _header_pairs(raw: Iterable[tuple[str, str]]) -> tuple[tuple[str, str], ...]:
    failed = False
    try:
        pairs = tuple(raw)
    except Exception:  # noqa: BLE001 -- raw iterator prose is never retained
        failed = True
        pairs = ()
    if failed:
        raise HttpRefusal("host") from None
    if any(not isinstance(row, (tuple, list)) or len(row) != 2
           or not all(isinstance(part, str) for part in row) for row in pairs):
        raise HttpRefusal("host") from None
    return tuple((row[0], row[1]) for row in pairs)


def _values(pairs: tuple[tuple[str, str], ...], name: str) -> tuple[str, ...]:
    wanted = name.casefold()
    return tuple(value for key, value in pairs if key.casefold() == wanted)


def _host(
        pairs: tuple[tuple[str, str], ...], allowed_hosts: frozenset[str]) -> str:
    values = _values(pairs, "Host")
    if len(values) != 1 or values[0] not in allowed_hosts:
        raise HttpRefusal("host") from None
    return values[0]


def validate_command_host(
        raw_header_pairs: Iterable[tuple[str, str]],
        allowed_hosts: frozenset[str]) -> str:
    """Validate exact Host cardinality and allowlist for a command GET."""
    return _host(_header_pairs(raw_header_pairs), allowed_hosts)


def _same_origin(pairs: tuple[tuple[str, str], ...], host: str) -> None:
    origins = _values(pairs, "Origin")
    referers = _values(pairs, "Referer")
    if len(origins) > 1 or len(referers) > 1:
        raise HttpRefusal("origin") from None
    expected = f"http://{host}"
    if origins:
        valid = origins[0] == expected
    elif len(referers) == 1:
        parsed = urlsplit(referers[0])
        valid = f"{parsed.scheme}://{parsed.netloc}" == expected
    else:
        valid = False
    if not valid:
        raise HttpRefusal("origin") from None


def _csrf(
        pairs: tuple[tuple[str, str], ...], current_token: str) -> None:
    presented = _values(pairs, "X-Conduct-CSRF")
    if len(presented) != 1 or not hmac.compare_digest(presented[0], current_token):
        raise HttpRefusal("csrf") from None


def _content_type(pairs: tuple[tuple[str, str], ...]) -> None:
    values = _values(pairs, "Content-Type")
    if len(values) != 1 or values[0].casefold() not in _JSON_MEDIA_TYPES:
        raise HttpRefusal("content_type") from None


def _finite_json(value: object) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_finite_json(item) for item in value)
    if isinstance(value, dict):
        return all(_finite_json(item) for item in value.values())
    return True


def _json_object(raw_body: bytes) -> dict[str, Any]:
    if not isinstance(raw_body, bytes):
        raise HttpRefusal("body") from None

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def reject_constant(_value: str) -> None:
        raise ValueError

    invalid = False
    try:
        decoded = raw_body.decode("utf-8", errors="strict")
        value = json.loads(
            decoded, object_pairs_hook=unique_object,
            parse_constant=reject_constant)
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
        invalid = True
        value = None
    if invalid or not isinstance(value, dict) or not _finite_json(value):
        raise HttpRefusal("body") from None
    return value


def validate_command_mutation(
        raw_header_pairs: Iterable[tuple[str, str]], raw_body: bytes, *,
        allowed_hosts: frozenset[str], current_token: str) -> dict[str, Any]:
    """Validate in frozen precedence, returning only the decoded JSON object."""
    pairs = _header_pairs(raw_header_pairs)
    host = _host(pairs, allowed_hosts)
    _same_origin(pairs, host)
    _csrf(pairs, current_token)
    _content_type(pairs)
    return _json_object(raw_body)
