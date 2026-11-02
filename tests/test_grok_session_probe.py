"""The fourth RPC waits for the authenticated process and never carries a prompt."""
import io
import json
from pathlib import Path
import sys
import tomllib
from dataclasses import replace

import pytest

from scripts import grok_gate_probe as probe
from conductor.command.adapters.process import CommandSpec, ProcessRunner
from conductor.command.adapters.process_boundary import WindowsContainer


def result(n, value):
    return (json.dumps(dict(jsonrpc="2.0", id=n, result=value)) + "\n").encode()


INIT = result(1, {"_meta": {"defaultAuthMethodId": "cached_token"}})
INFO = result(2, {"methodId": "cached_token"})
AUTH = result(3, {})


def test_session_config_prevents_ambient_integrations(tmp_path):
    probe.pin_session(tmp_path)
    config = tomllib.loads((tmp_path / "config.toml").read_text())
    assert config == {"auth": {"preferred_method": "oidc"}, "claude_compat": {"imported": True},
                      "features": {"two_pass_compaction": False, "lsp_tools": False,
                                   "codebase_indexing": False, "remote_fetch": False},
                      "session": {"load_envrc": False}}
    init, info, auth = [json.loads(row) for row in probe.SESSION_INPUT.splitlines()]
    assert [row["method"] for row in (init, info, auth)] == [
        "initialize", "_x.ai/auth/info", "authenticate"]
    assert init["params"]["clientCapabilities"] == {"fs": {}, "terminal": False}
    assert init["params"]["_meta"]["startupHints"]["nonInteractive"] is True


def test_session_is_the_only_write_and_only_after_auth(tmp_path):
    stream = io.BytesIO()
    exchange = probe.SessionExchange(tmp_path)
    for wire in (b"", INIT, INIT + INFO, INIT + INFO + AUTH[:-1]):
        assert not exchange.advance(wire, stream) and not stream.getvalue()
    assert exchange.advance(INIT + INFO + AUTH, stream)
    assert exchange.advance(INIT + INFO + AUTH, stream)
    request, = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert request == {"jsonrpc": "2.0", "id": 4, "method": "session/new",
                       "params": {"cwd": str(tmp_path), "mcpServers": []}}
    assert exchange.verdict(INIT + INFO + AUTH + result(4, {"sessionId": "private"})) == (
        "session_created")
    for invalid in ("", None, 42, "  "):
        assert exchange.verdict(INIT + INFO + AUTH + result(4, {"sessionId": invalid})) == (
            "invalid_session_reply")
    assert exchange.verdict(INIT + INFO + AUTH) == "no_session_reply"
    error = b'{"jsonrpc":"2.0","id":4,"error":{"code":-1,"message":"private"}}\n'
    assert exchange.verdict(INIT + INFO + AUTH + error) == "session_rpc_error"


@pytest.mark.parametrize("wire", [
    INIT + INFO + result(3, {"_meta": {"gate": {"message": "private"}}}),
    INIT + result(2, {"methodId": "api_key"}) + AUTH,
    INIT + INFO + AUTH + result(4, {"sessionId": "unsolicited"}),
    b"broken\n",
])
def test_failed_auth_and_premature_session_never_trigger_another_request(wire):
    stream = io.BytesIO()
    exchange = probe.SessionExchange(Path.cwd())
    assert exchange.advance(wire, stream)
    assert not exchange.sent and not stream.getvalue()
    assert exchange.verdict(wire) != "session_created"


def test_ancestor_configuration_refuses_the_session(tmp_path):
    directory = tmp_path / "cwd"
    directory.mkdir()
    probe.check_session_directory(directory)
    (tmp_path / ".grok").mkdir()
    with pytest.raises(ValueError, match="external session"):
        probe.check_session_directory(directory)


def test_real_pipes_feed_session_only_after_auth_and_then_close(tmp_path, monkeypatch):
    work = tmp_path / "work"
    work.mkdir()
    peer = """
import json, sys
def send(n, result):
    print(json.dumps({"jsonrpc":"2.0","id":n,"result":result}), flush=True)
for n, method, result in [
    (1, "initialize", {"_meta":{"defaultAuthMethodId":"cached_token"}}),
    (2, "_x.ai/auth/info", {"methodId":"cached_token"}), (3, "authenticate", {})]:
    req = json.loads(sys.stdin.readline())
    assert req["method"] == method and req["id"] == n
    send(n, result)
req = json.loads(sys.stdin.readline())
assert req["method"] == "session/new" and req["params"]["mcpServers"] == []
send(4, {"sessionId":"synthetic private value"})
assert not sys.stdin.readline()
"""
    # Exercise the pinned host's real pipe pump with a local synthetic peer on any OS.
    spawn = ProcessRunner._spawn
    monkeypatch.setattr(ProcessRunner, "_spawn", lambda self, spec:
                        spawn(self, replace(spec, boundary=None)))
    runner = probe.SessionRunner(tmp_path)
    runner.exchange = probe.SessionExchange(work)
    policy = WindowsContainer("S-1-15-2-1-2-3-4-5-6-7")
    spec = CommandSpec((sys.executable, "-I", "-c", peer), "work", separate_stderr=True,
                       stdin_bytes=probe.SESSION_INPUT, stdin_completion_id=4,
                       boundary=policy, timeout_seconds=5)
    with pytest.raises(ValueError, match="offline"):
        runner.run(replace(spec, boundary=replace(policy, internet_client=True)))
    out = runner.run(spec)
    assert (out.exit_code, out.stdin_state) == (0, "delivered")
    assert runner.exchange.verdict(out.output) == "session_created"
