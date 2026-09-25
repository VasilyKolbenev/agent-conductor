"""Small HTTPS JSON reader for provider-owned quota endpoints.

Call only from an owned collector, never from a panel request. This does not
follow redirects or use proxy settings from the environment. The socket timeout
bounds blocking socket operations; it is not a deadline for DNS/the whole call.
Only decoded data or a closed error reason leaves this boundary.
"""
from __future__ import annotations

import http.client
import json
import math
import re
from urllib.parse import urlsplit


MAX_RESPONSE_BYTES = 64 * 1024
SOCKET_TIMEOUT_SECONDS = 5
_REASONS = frozenset({'unavailable', 'invalid_payload', 'unauthorized',
                      'rate_limited', 'unsupported_endpoint'})


class QuotaFetchError(ValueError):
    def __init__(self, reason: str) -> None:
        self.reason = reason if reason in _REASONS else 'unavailable'
        super().__init__(self.reason)


def _endpoint(value: object) -> tuple[str, str]:
    if type(value) is not str or not value or len(value) > 2048:
        raise QuotaFetchError('unsupported_endpoint')
    if any(ord(c) < 33 or ord(c) > 126 for c in value) or '\\' in value:
        raise QuotaFetchError('unsupported_endpoint')
    try:
        url = urlsplit(value)
        if (url.scheme != 'https' or url.username is not None or url.password is not None
                or url.port not in (None, 443) or url.query or url.fragment
                or not url.hostname or re.fullmatch(r'[a-zA-Z0-9.-]+', url.hostname) is None
                or not url.path.startswith('/') or '?' in value or '#' in value):
            raise ValueError('invalid endpoint')
        return url.hostname, url.path
    except ValueError:
        raise QuotaFetchError('unsupported_endpoint') from None


def _pairs(items):
    result = {}
    for name, value in items:
        if name in result:
            raise ValueError('duplicate JSON property')
        result[name] = value
    return result


def _constant(_value):
    raise ValueError('nonfinite JSON number')


def _decode(raw: bytes) -> dict:
    try:
        payload = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs, parse_constant=_constant)
        if type(payload) is not dict:
            raise ValueError('object required')
        pending = [(payload, 0)]
        while pending:
            value, depth = pending.pop()
            if depth > 16 or type(value) is float and not math.isfinite(value):
                raise ValueError('invalid JSON value')
            if type(value) in (dict, list):
                values = value.values() if type(value) is dict else value
                pending.extend((child, depth + 1) for child in values)
        return payload
    except (ValueError, UnicodeError, RecursionError):
        raise QuotaFetchError('invalid_payload') from None


def _read_response(response) -> dict:
    if response.status in (401, 403):
        raise QuotaFetchError('unauthorized')
    if response.status == 429:
        raise QuotaFetchError('rate_limited')
    if response.status != 200:
        raise QuotaFetchError('unavailable')
    if response.getheader('Content-Encoding', 'identity').lower() != 'identity':
        raise QuotaFetchError('invalid_payload')
    if response.getheader('Content-Type', '').split(';', 1)[0].strip().lower() != 'application/json':
        raise QuotaFetchError('invalid_payload')
    length = response.getheader('Content-Length')
    if length is not None and (len(length) > 10 or not length.isascii() or not length.isdecimal()
                               or int(length) > MAX_RESPONSE_BYTES):
        raise QuotaFetchError('invalid_payload')
    transfer = response.getheader('Transfer-Encoding')
    if transfer is not None and (transfer.lower() != 'chunked' or length is not None):
        raise QuotaFetchError('invalid_payload')
    raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES or length is not None and len(raw) != int(length):
        raise QuotaFetchError('invalid_payload')
    return _decode(raw)


def read_quota_json(endpoint: str, bearer: str) -> dict:
    """Read one fixed, trusted provider endpoint; never persist/log credentials.

    The caller must bind this credential to actual dispatch configuration.
    This generic transport does not infer an account or validate that binding.
    """
    host, path = _endpoint(endpoint)
    if (type(bearer) is not str or not 1 <= len(bearer) <= 8192
            or any(ord(c) < 33 or ord(c) > 126 for c in bearer)):
        raise QuotaFetchError('unauthorized')
    connection = None
    try:
        # HTTPSConnection's default SSL context verifies certificate and hostname.
        connection = http.client.HTTPSConnection(host, port=443, timeout=SOCKET_TIMEOUT_SECONDS)
        connection.request('GET', path, headers={
            'Authorization': 'Bearer ' + bearer, 'Accept': 'application/json',
            'Accept-Encoding': 'identity', 'Connection': 'close'})
        return _read_response(connection.getresponse())
    except QuotaFetchError:
        raise
    except Exception:
        # Upstream URLs, bodies, headers and exception messages are private.
        raise QuotaFetchError('unavailable') from None
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                # Closing an already broken socket cannot add a public detail.
                pass
