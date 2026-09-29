"""Only a failed bind raises the typed bind error (spec 4.1.5: `bind_failed` versus `start_failed`).

`conduct up` maps `bind_failed` and `start_failed` onto two different sentences for the
person reading them (rerun on another port, or look at the disk), so the mapping may not
rest on "some OSError came out of `build`". The server raises `ServerBindError` from
`server_bind` and from nowhere else; the witnesses below run the REAL `server.build`,
against a real busy port and against a real failure after the bind.
"""
from __future__ import annotations

import socket

import pytest

from conductor import server
from tests.test_store import good_lane, write_project


def _blocker() -> socket.socket:
    """A listening socket that a second bind to its port cannot share, on every OS."""
    held = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
        held.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    held.bind(("127.0.0.1", 0))
    held.listen(1)
    return held


def test_a_busy_port_raises_the_typed_bind_error_with_the_original_cause(tmp_path):
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    held = _blocker()
    try:
        with pytest.raises(server.ServerBindError) as caught:
            server.build(root, held.getsockname()[1])
    finally:
        held.close()
    error = caught.value
    assert isinstance(error, OSError), "callers that catch OSError around build still catch it"
    cause = error.__cause__
    assert isinstance(cause, OSError) and not isinstance(cause, server.ServerBindError)
    assert error.errno == cause.errno and str(error) == str(cause)


def test_an_oserror_after_the_bind_is_not_a_bind_error_and_the_port_is_free_again(
        tmp_path, monkeypatch):
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()

    def fail_after_the_bind(subject, folder):
        raise OSError("the owner record could not be read")

    monkeypatch.setattr("conductor.server_policy.acquire_server_owner", fail_after_the_bind)
    with pytest.raises(OSError, match="owner record") as caught:
        server.build(root, port)
    assert not isinstance(caught.value, server.ServerBindError)
    again = socket.socket()
    try:
        again.bind(("127.0.0.1", port))          # the failed start closed its socket
    finally:
        again.close()
