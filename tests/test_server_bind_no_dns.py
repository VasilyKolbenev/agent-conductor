"""The loopback server names itself by its bound literal, never by a reverse DNS lookup.

`http.server.HTTPServer.server_bind` follows the TCP bind with `socket.getfqdn(host)`.
For a server that only ever binds 127.0.0.1 that lookup answers nothing the product
reads, and on the macOS runners the installed `conduct up` printed its address only
after 35 s (Linux: 0.2 s). The witness builds the REAL server through `server.build`
with both resolver entry points replaced by recorders that refuse, so a lookup anywhere
on the bind, serve or close path is a failure here, not a slow pass.
"""
import http.client
import json
import os
import socket
import threading

import pytest

from conductor import ownership, ownership_transition, server
from tests.test_store import write_project


def _refusing_resolver(monkeypatch):
    """Replace getfqdn and gethostbyaddr with recorders that raise; return the record."""
    calls = []

    def refuse(name):
        def lookup(*args, **kwargs):
            calls.append((name, args))
            raise AssertionError(f"reverse DNS lookup attempted: socket.{name}{args!r}")
        return lookup

    monkeypatch.setattr(socket, "getfqdn", refuse("getfqdn"))
    monkeypatch.setattr(socket, "gethostbyaddr", refuse("gethostbyaddr"))
    return calls


def _get_state(host, port):
    """One real HTTP GET of /state.json, straight to the literal (no proxy lookup)."""
    connection = http.client.HTTPConnection(host, port, timeout=5)
    try:
        connection.request("GET", "/state.json")
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


def test_the_real_server_binds_serves_and_closes_without_a_reverse_dns_lookup(
        tmp_path, monkeypatch):
    root = write_project(tmp_path)
    ownership_transition.activate(root, legacy_writers_stopped=True)
    calls = _refusing_resolver(monkeypatch)
    srv = server.build(root, port=0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = srv.server_address[:2]
        assert host == "127.0.0.1" and port > 0          # the OS chose a real port
        assert (srv.server_name, srv.server_port) == (host, port)
        # The standard TCP bind still applies the class policy: off on Windows.
        reuse = srv.socket.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR)
        assert bool(reuse) == (os.name != "nt")
        assert ownership.require_owner(root) is srv.project_owner
        status, state = _get_state(host, port)
        assert status == 200 and isinstance(state, dict)
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(5)
    assert not thread.is_alive() and srv.socket.fileno() == -1
    assert srv.project_owner is None and not srv.retirement_uncertain
    with pytest.raises(ownership.OwnerRefused, match="owner_required"):
        ownership.require_owner(root)
    assert calls == []
