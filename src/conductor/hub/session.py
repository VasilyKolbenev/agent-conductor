"""`HubSession`: the hub's own CSRF token and its ONE allowed host (spec 4.6.2, ADR-2a).

The commands' session (`CommandSession`) accepts two spellings of loopback. The hub cannot: its
origin is written into the frame policy of every child (4.6.6), so `127.0.0.1:<hub>` is the only
Host it answers, and `localhost:<hub>` is `same_origin_denied`. The checks themselves are the
commands' own functions over the hub's one host, so there is one implementation of Origin, token,
content type and body framing and two sessions that differ only in the hosts they allow.
"""
from __future__ import annotations

import secrets
from collections.abc import Callable, Iterable
from typing import Any

from conductor.command.http_transport import (
    validate_command_host, validate_command_mutation, validate_command_mutation_headers)


class HubSession:
    """One process-memory CSRF token and the single host it belongs to."""

    __slots__ = ("_allowed_hosts", "_host", "_token")

    def __init__(self, port: int, token: str) -> None:
        if isinstance(port, bool) or not isinstance(port, int) or not 0 < port <= 65535:
            raise ValueError("port must be an integer from 1 through 65535")
        if not isinstance(token, str) or not token:
            raise ValueError("CSRF token must be non-empty text")
        self._host = f"127.0.0.1:{port}"
        self._allowed_hosts = frozenset({self._host})
        self._token = token

    @classmethod
    def mint(cls, port: int,
             token_factory: Callable[[int], str] = secrets.token_urlsafe) -> HubSession:
        """Mint one token with at least 32 bytes of source entropy."""
        return cls(port, token_factory(32))

    @property
    def allowed_hosts(self) -> frozenset[str]:
        """The one Host value this hub answers."""
        return self._allowed_hosts

    @property
    def canonical_host(self) -> str:
        """`127.0.0.1:<hub>`: the address a refusal of another spelling names."""
        return self._host

    @property
    def origin(self) -> str:
        """`http://127.0.0.1:<hub>`: the only Origin a write may carry."""
        return f"http://{self._host}"

    def check_host(self, raw_header_pairs: Iterable[tuple[str, str]]) -> str:
        """Validate the exact Host cardinality and value, for every method.

        Raises:
            HttpRefusal: `same_origin_denied`.
        """
        return validate_command_host(raw_header_pairs, self._allowed_hosts)

    def session_response(self, host: str) -> dict[str, str]:
        """The body of `GET /hub/session` after the caller validated Host."""
        validate_command_host((("Host", host),), self._allowed_hosts)
        return {"csrf_token": self._token, "origin": f"http://{host}"}

    def body_length(self, raw_header_pairs: Iterable[tuple[str, str]]) -> int:
        """Validate a write's headers in their frozen precedence; return the bounded length."""
        return validate_command_mutation_headers(
            raw_header_pairs, allowed_hosts=self._allowed_hosts, current_token=self._token)

    def validate_mutation(self, raw_header_pairs: Iterable[tuple[str, str]],
                          raw_body: bytes) -> dict[str, Any]:
        """Validate one write against this hub's token; return the decoded JSON object."""
        return validate_command_mutation(
            raw_header_pairs, raw_body, allowed_hosts=self._allowed_hosts,
            current_token=self._token)

    def __repr__(self) -> str:
        return "HubSession(<process-memory token>)"
