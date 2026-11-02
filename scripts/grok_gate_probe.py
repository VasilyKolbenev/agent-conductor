"""Single operator-authorized Grok 1.0.5 authenticate exchange in a review AppContainer."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time

from conductor import ownership
from conductor.command.adapters import login_relay, relay_home
from conductor.command.adapters.grok_build import GROK_AUTH_RPC, GROK_FORCED_ENV, GROK_QUOTA_RPC
from conductor.command.adapters.grok_relay import GROK_RELAY
from conductor.command.adapters.harness_attempt import confined_spec
from conductor.command.adapters.jsonl_completion import decode_line
from conductor.command.adapters.process import CommandSpec, ProcessRunner
from conductor.command.adapters.process_boundary import AttemptFolders
from conductor.command.adapters.quota_connection import NativeQuotaReadError
from conductor.command.operator_config import load_provider_configs, provider_config_path


PIN = "4b924daa801663ea20e96382408b1f2b5ba39efad62c14d20d88618a9eb0be64"
BUILD = "a9044e1e4b9c"
AUTH = (b'{"jsonrpc":"2.0","id":3,"method":"authenticate","params":'
        b'{"methodId":"cached_token","_meta":{"headless":true}}}\n')
NOTICES = (*GROK_AUTH_RPC.notifications, "_x.ai/settings/update", "_x.ai/announcements/update")
INFO = replace(GROK_AUTH_RPC, notifications=NOTICES)
SERVICE = replace(GROK_QUOTA_RPC, payload=INFO.payload + AUTH, notifications=NOTICES)
SESSION_INPUT = (
    b'{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":1,'
    b'"clientCapabilities":{"fs":{},"terminal":false},"_meta":{"clientType":"grok-shell",'
    b'"startupHints":{"nonInteractive":true,"skipGitStatus":true,"skipProjectLayout":true}}}}\n'
    + SERVICE.payload.split(b"\n", 1)[1])


def pin_oidc(home):
    """The vendor explicitly refuses interactive fallback with preferred_method pinned."""
    with (home / "config.toml").open("x", encoding="ascii", newline="\n") as config:
        config.write('[auth]\npreferred_method = "oidc"\n')


def wire_facts(output):
    """Report response presence only; unknown methods, vendor errors and values stay private."""
    try:
        rows = [decode_line(raw) for raw in output.splitlines()]
        return {"reply_kinds": [
            next(("error" if "error" in row else "result" if "result" in row else "other"
                  for row in rows if type(row.get("id")) is int and row["id"] == n), "missing")
            for n in (1, 2, 3)],
            "extra_notification": any("method" in row and row["method"] not in NOTICES
                                      for row in rows)}
    except (ValueError, UnicodeError, RecursionError):
        return {"malformed_frame": True}


def signal(output):
    """Discard private vendor data. Only the fixed classification crosses the seam."""
    try:
        frames = [(raw, decode_line(raw)) for raw in output.splitlines()]
        if any(row.get("jsonrpc") != "2.0" for _, row in frames):
            return "unconfirmed_exchange"
        prefix = b"\n".join(raw for raw, row in frames if row.get("id") != 3)
        if INFO.decode(prefix).get("methodId") != "cached_token":
            return "unconfirmed_exchange"
        meta = SERVICE.decode(output).get("_meta")
    except (NativeQuotaReadError, ValueError, UnicodeError, RecursionError):
        return "unconfirmed_exchange"
    if meta is None:
        return "no_gate_reported"
    if type(meta) is not dict:
        return "invalid_gate"
    gate = meta.get("gate")
    if gate is None:
        return "no_gate_reported"
    if type(gate) is not dict or not isinstance(gate.get("message"), str) or not gate["message"]:
        return "invalid_gate"
    return "restriction_seen"


class SessionExchange:
    """One additional frame is permitted, and only after observing complete auth replies."""

    def __init__(self, cwd):
        self.cwd = cwd
        self.sent = False
        self.auth = "awaiting_auth"

    def advance(self, captured, pipe):
        if self.sent or self.auth != "awaiting_auth":
            return True
        complete = captured.rpartition(b"\n")[0]
        if not complete:
            return False
        try:
            rows = [decode_line(raw) for raw in complete.splitlines()]
        except (ValueError, UnicodeError, RecursionError):
            self.auth = "malformed_frame"
            return True
        if any(row.get("id") == 4 for row in rows):
            self.auth = "unsolicited_session_reply"
            return True
        if not any(row.get("id") == 3 for row in rows):
            return False
        self.auth = signal(complete)
        if self.auth == "no_gate_reported":
            frame = {"jsonrpc": "2.0", "id": 4, "method": "session/new",
                     "params": {"cwd": str(self.cwd), "mcpServers": []}}
            remaining = memoryview((json.dumps(frame) + "\n").encode())
            while remaining:
                size = pipe.write(remaining)
                if not size:
                    raise OSError("incomplete session frame")
                remaining = remaining[size:]
            pipe.flush()
            self.sent = True
        return True

    def verdict(self, captured):
        if not self.sent:
            return "session_not_sent"
        try:
            replies = [decode_line(raw) for raw in captured.splitlines()]
        except (ValueError, UnicodeError, RecursionError):
            return "invalid_session_reply"
        session = [row for row in replies if type(row.get("id")) is int and row["id"] == 4]
        if not session:
            return "no_session_reply"
        if len(session) != 1 or session[0].get("jsonrpc") != "2.0" or "method" in session[0]:
            return "invalid_session_reply"
        row = session[0]
        if "error" in row:
            return "session_rpc_error" if "result" not in row and type(row["error"]) is dict else (
                "invalid_session_reply")
        sid = row["result"].get("sessionId") if type(row.get("result")) is dict else None
        return "session_created" if type(sid) is str and sid.strip() else "invalid_session_reply"


class SessionRunner(ProcessRunner):
    """Keep the native runner's process ownership, concurrent pipe pump and group retirement."""

    def _spawn(self, spec):
        if (spec.boundary is None or spec.boundary.internet_client
                or spec.stdin_bytes != SESSION_INPUT or spec.stdin_completion_id != 4):
            raise ValueError("offline authenticated session probe required")
        owned = super()._spawn(spec)
        try:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                with owned._lock:
                    data, truncated = bytes(owned._buf), owned._truncated
                if truncated or any(secret and secret in data for secret in spec.sensitive_extra):
                    break
                if self.exchange.advance(data, owned.proc.stdin) or owned.proc.poll() is not None:
                    break
                time.sleep(0.02)
        except (OSError, ValueError):
            self.exchange.auth = "pipe_error"
        finally:
            if not self.exchange.sent:
                # Release the original feeder even if response 4 will never exist.
                owned._input_done.set()
        return owned


def check_session_directory(directory):
    # Exclude ancestor project configuration, even though the new cwd itself is empty.
    for parent in (directory, *directory.parents):
        for name in (".grok", ".mcp.json", ".envrc"):
            if os.path.lexists(parent / name):
                raise ValueError("external session configuration")


def pin_session(home):
    pin_oidc(home)
    # The vendor checks the relay's claude_compat marker before looking up
    # enabledPlugins in the real Windows profile's Claude settings.
    with (home / "config.toml").open("a", encoding="ascii", newline="\n") as config:
        config.write("\n[claude_compat]\nimported = true\n"
                     "[features]\ntwo_pass_compaction = false\nlsp_tools = false\n"
                     "codebase_indexing = false\nremote_fetch = false\n"
                     "[session]\nload_envrc = false\n")


def inspect_once(root, dc, facts, *, session=False):
    exe = dc / "harnesses/grok-build/1.0.5/grok.exe"
    login = dc / "logins/grok-build"
    with exe.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != PIN:
            raise ValueError("pin")
    system = os.environ["SystemRoot"]
    runner_type = SessionRunner if session else ProcessRunner
    runner = runner_type(root, environ={"SystemRoot": system, "windir": system,
                           "PATH": str(Path(system) / "System32") + ";" + system})
    with ownership.acquire_owner(root):
        providers = load_provider_configs(provider_config_path(ownership.data_root(root)))
        matches = [row for row in providers if row.provider_id == "grok-build"]
        if (len(matches) != 1 or matches[0].auth != "subscription"
                or Path(matches[0].auth_home) != login or Path(matches[0].executable) != exe):
            raise ValueError("subscription pin")
        with ProcessRunner.login_write_guard(root, str(login)):
            if not relay_home.lease_names(root, login):
                raise ValueError("lease")
            now = datetime.now(timezone.utc)
            ready = login_relay.ready(login, GROK_RELAY, now, timedelta(minutes=5))
            if isinstance(ready, login_relay.Refused):
                facts["stop"] = ready.code
                return
            work = "work/grok-acp-session-once" if session else "work/grok-acp-gate-once"
            directory = root / work
            directory.mkdir()
            home = None
            try:
                runner.ensure_relay_root(login)
                home = relay_home.mint_home(login, root, GROK_RELAY.kind)
                if home is None or runner.relay_acl_refusal(login, home) is not None:
                    facts["stop"] = "relay_refused"
                    return
                ticket = login_relay.copy_in(login, home, GROK_RELAY, ready.digest)
                if isinstance(ticket, login_relay.Refused):
                    facts["stop"] = ticket.code
                    return
                if session:
                    check_session_directory(directory)
                    pin_session(home)
                    runner.exchange = SessionExchange(directory)
                else:
                    pin_oidc(home)
                folders = AttemptFolders(work=work, home=str(home), install=str(exe.parent))
                with runner.container_profile(internet_client=not session, mode="review",
                                              folders=folders) as (boundary, paths):
                    prefix = (str(exe),)
                    child_env = {**dict(GROK_FORCED_ENV), "GROK_HOME": str(home)}
                    if session:
                        child_env.update(dict.fromkeys(("GROK_MEMORY", "GROK_SUBAGENTS",
                                                        "GROK_GOAL",
                                                        "GROK_SCHEDULER_BACKGROUND_LOOPS",
                                                        "GROK_MANAGED_MCPS_ENABLED",
                                                        "GROK_MANAGED_MCP_GATEWAY_TOOLS_ENABLED",
                                                        "GROK_WORKFLOWS"), "0"))
                        child_env.update(dict.fromkeys(("HOME", "USERPROFILE", "APPDATA"),
                                                       str(paths["runtime"])))
                        child_env["GROK_STORAGE_MODE"] = "local"
                    spec = CommandSpec((*prefix, *SERVICE.argv), work,
                        env=child_env,
                        env_allow=("SystemRoot", "windir", "PATH"), separate_stderr=True,
                        stdin_bytes=SESSION_INPUT if session else SERVICE.payload,
                        stdin_completion_id=4 if session else 3,
                        sensitive_extra=(*ready.secrets, *ticket.secrets), timeout_seconds=30)
                    out = runner.run(confined_spec(spec, boundary, paths, plain=prefix, prefix=prefix))
                facts.update(process=out.status, exit=out.exit_code, stdin=out.stdin_state)
                if session:
                    facts.update(auth=runner.exchange.auth, session_requests=int(runner.exchange.sent),
                                 session="capture_unconfirmed")
                    if not out.output_truncated and not out.output_contains_env_value:
                        facts["session"] = runner.exchange.verdict(out.output)
                    return
                if not out.output_truncated and not out.output_contains_env_value:
                    facts.update(wire_facts(out.output))
                if (out.status == "completed" and out.exit_code == 0 and out.stdin_state == "delivered"
                        and not out.output_truncated and not out.output_contains_env_value):
                    facts["signal"] = signal(out.output)
                else:
                    facts["signal"] = "process_or_capture_unconfirmed"
            finally:
                facts["relay_removed"] = home is None or (
                    login_relay.discard(home, GROK_RELAY.files) and not home.exists())
                after = login_relay.ready(login, GROK_RELAY, datetime.now(timezone.utc), timedelta())
                facts["original_unchanged"] = (
                    isinstance(after, login_relay.Ready) and after.digest == ready.digest)
                directory.rmdir()
                facts["empty_workspace_removed"] = True
                if not facts["relay_removed"] or not facts["original_unchanged"]:
                    raise RuntimeError("cleanup or login integrity")


def main():
    dc = Path.home() / "DecemberCommand"
    session = sys.argv[1:] == ["--session-once"]
    filename = "grok_session_probe.py" if session else "grok_gate_probe.py"
    if ((not session and sys.argv[1:] != ["--once"]) or not sys.flags.isolated
            or Path(__file__).resolve() != dc / "h5-a/tools" / filename
            or Path(sys.prefix).resolve() != dc / "product" / BUILD / "venv"):
        raise ValueError("protected host")
    stamp = dc / "grok-live" / ("g6-acp-session-once.json" if session else "g6-acp-gate-once.json")
    facts = {"build": BUILD, "methods": ["initialize", "_x.ai/auth/info", "authenticate"],
             "session_requests": 0, "prompt_requests": 0}
    if session:
        facts["internet_client"] = False
        facts["permitted_final_method"] = "session/new"
    with stamp.open("x", encoding="utf-8") as handle:
        json.dump({"reserved_utc": datetime.now(timezone.utc).isoformat()}, handle)
    try:
        inspect_once(Path.home() / "DecemberGrokG6", dc, facts, session=session)
    except Exception as error:
        facts["failure_type"] = type(error).__name__
    with stamp.with_suffix(".result.json").open("x", encoding="utf-8") as handle:
        json.dump(facts, handle)
    print(json.dumps(facts))
    return int("failure_type" in facts or "stop" in facts)


if __name__ == "__main__":
    sys.exit(main())
