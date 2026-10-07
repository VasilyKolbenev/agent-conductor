"""Read only the quota API of a caller-owned native loopback server.

The adapter owns the native child, its explicit port and auth-home token. This boundary
accepts no remote host, proxy, redirect or caller-defined endpoint.
"""
import http.client
import math
import socket
from threading import Event, Timer
from time import monotonic

from .quota_transport import QuotaFetchError, _read_response


PATHS = frozenset({"/api/v1/auth", "/api/v1/oauth/usage"})


def choose_loopback_port():
    """Choose a currently free port. Bind races remain the child's closed refusal."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reservation:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            reservation.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        reservation.bind(("127.0.0.1", 0))
        return reservation.getsockname()[1]


def _deadline_seconds(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= 10:
        raise QuotaFetchError("unavailable")
    return float(value)


def wait_quota_loopback(ready, *, timeout=5):
    """Poll readiness for the explicit child port; never discover another server."""
    deadline = monotonic() + _deadline_seconds(timeout)
    pause = Event()
    while monotonic() < deadline:
        value = ready()
        if value is not None:
            port, bearer = value
            _validate(port, "/api/v1/auth", bearer)
            return port, bearer
        pause.wait(min(.05, max(0, deadline - monotonic())))
    raise QuotaFetchError("unavailable")


def _validate(port, path, bearer):
    if type(port) is not int or not 1 <= port <= 65535 or path not in PATHS:
        raise QuotaFetchError("unsupported_endpoint")
    if (type(bearer) is not str or not 1 <= len(bearer) <= 8192
            or any(ord(c) < 33 or ord(c) > 126 for c in bearer)):
        raise QuotaFetchError("unauthorized")


def _close(sock):
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    sock.close()


def fetch_loopback_json(*, port, path, bearer, timeout=5):
    """Literal IPv4 loopback, 64 KiB JSON ceiling and a whole-call deadline.

    The deadline shuts down the same socket even if headers/body arrive slowly.
    Socket exception text and the ephemeral bearer never leave this module.
    """
    _validate(port, path, bearer)
    timeout = _deadline_seconds(timeout)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    timer = Timer(timeout, _close, args=(sock,))
    timer.daemon = True
    response = None
    try:
        sock.settimeout(timeout)
        timer.start()
        sock.connect(("127.0.0.1", port))
        request = (f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
                   f"Authorization: Bearer {bearer}\r\nAccept: application/json\r\n"
                   "Accept-Encoding: identity\r\nConnection: close\r\n\r\n")
        sock.sendall(request.encode("ascii"))
        response = http.client.HTTPResponse(sock)
        response.begin()
        return _read_response(response)
    except QuotaFetchError:
        raise
    except Exception:
        raise QuotaFetchError("unavailable") from None
    finally:
        timer.cancel()
        if timer.ident is not None:
            timer.join()
        if response is not None:
            response.close()
        _close(sock)
