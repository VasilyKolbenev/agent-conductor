"""Operator-started client for a compatible local text utility."""

import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import secrets
import sys
from tempfile import TemporaryDirectory
import time
from urllib.parse import urlsplit

from .command.adapters.process import CommandSpec, ProcessRunner, STDIN_DELIVERED

PROTOCOL = "arachnid.utility.v1"
ENDPOINT = "/command/project/utilities"
_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,47}")
_WIRE_LIMIT = 65536


class BridgeError(ValueError):
    """A local connection, peer, or response did not satisfy the utility contract."""


def parse_address(value):
    try:
        url = urlsplit(value)
        port = url.port
        if port and value.rstrip("/") == f"http://127.0.0.1:{port}" and url.path in ("", "/"):
            return port
    except ValueError:
        pass
    raise BridgeError("expected http://127.0.0.1:PORT")


def _unique(pairs):
    row = dict(pairs)
    if len(row) != len(pairs):
        raise BridgeError("duplicate JSON field")
    return row


def _text(value):
    if (not isinstance(value, str) or not value.strip()
            or any(ord(c) < 32 and c not in "\t\r\n" for c in value)
            or len(value.encode("utf-8")) > 8192):
        raise BridgeError("invalid utility text")
    return value


def parse_reply(raw, request):
    if len(raw) > _WIRE_LIMIT or b"\n" in raw.strip():
        raise BridgeError("expected one bounded JSON line")
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique)
    except (ValueError, UnicodeError, RecursionError):
        raise BridgeError("invalid peer JSON") from None
    if (type(data) is not dict or set(data) != {"protocol", "utility_id", "exchange_id", "text"}
            or any(data[k] != request[k] for k in ("protocol", "utility_id", "exchange_id"))):
        raise BridgeError("unexpected peer response")
    return _text(data["text"])


class LocalStudio:
    def __init__(self, address):
        self.port = parse_address(address)
        self.origin = f"http://127.0.0.1:{self.port}"
        self.headers = {}
        session = self.get("/command/session")
        if session.get("origin") != self.origin or not isinstance(session.get("csrf_token"), str):
            raise BridgeError("unconfirmed Studio session")
        identity = self.get("/command/project")
        pid = identity.get("project_id")
        if (identity.get("mode") != "active" or not isinstance(pid, str)
                or not re.fullmatch(r"[a-f0-9]{32}", pid)):
            raise BridgeError("open this utility in an active, identified Studio project")
        self.headers = {"X-Conduct-Project": pid, "X-Conduct-CSRF": session["csrf_token"],
                        "Origin": self.origin, "Content-Type": "application/json"}

    def request(self, method, path, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request(method, path, body=body, headers=self.headers)
            response = conn.getresponse()
            raw = response.read(2 * 1024 * 1024 + 1)
            if len(raw) > 2 * 1024 * 1024:
                raise BridgeError("Studio response exceeded the limit")
            if response.status not in (200, 201, 409):
                raise BridgeError(f"Studio returned HTTP {response.status}")
            data = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique)
            if type(data) is not dict:
                raise BridgeError("unexpected Studio response")
            return response.status, data
        finally:
            conn.close()

    def get(self, path):
        status, data = self.request("GET", path)
        if status != 200:
            raise BridgeError(f"Studio returned HTTP {status}")
        return data

    def post(self, **body):
        return self.request("POST", ENDPOINT, json.dumps(body).encode("ascii"))


def exchange(client, utility_id, peer):
    state = client.get(ENDPOINT)
    if not any(u.get("utility_id") == utility_id and u.get("mode") == "stdio-v1"
               for u in state["utilities"]):
        raise BridgeError("no matching stdio-v1 utility in this project")
    pending = next((v for v in state["exchanges"] if v.get("state") == "pending"
                    and v.get("utility_id") == utility_id), None)
    if pending is None:
        return False
    eid = pending.get("exchange_id")
    if not isinstance(eid, str) or not _ID.fullmatch(eid):
        raise BridgeError("invalid exchange id")
    claim = dict(utility_id=utility_id, exchange_id=eid, claim_token=secrets.token_hex(32))
    request = dict(protocol=PROTOCOL, utility_id=utility_id, exchange_id=eid,
                   text=_text(pending["text"]))
    status, data = client.post(op="claim", **claim)
    if status in (200, 409):
        return False
    row = data.get("exchange")
    if (status != 201 or not isinstance(row, dict) or row.get("state") != "claimed"
            or any(row.get(k) != request[k] for k in ("utility_id", "exchange_id", "text"))):
        raise BridgeError("Studio did not confirm this claim")
    try:
        response = _text(peer(request))
    except (Exception, KeyboardInterrupt):
        client.post(op="finish", **claim, outcome="unknown")
        raise
    status, _ = client.post(op="finish", **claim, outcome="answered", text=response)
    if status not in (200, 201):
        raise BridgeError(f"Studio could not record the reply (HTTP {status})")
    return True


def _sha(executable):
    with executable.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def local_peer(path, args):
    executable = Path(path)
    if (not executable.is_absolute() or not executable.is_file()
            or (os.name == "nt" and executable.suffix.lower() != ".exe")):
        raise BridgeError("choose the absolute path of an installed executable")
    if type(args) is not list or len(args) > 32 or not all(type(a) is str for a in args):
        raise BridgeError("arguments must be a JSON array of strings")
    digest = _sha(executable)
    print(f"Selected utility SHA-256 {digest}", flush=True)

    def run(request):
        if _sha(executable) != digest:
            raise BridgeError("selected executable has changed")
        frame = json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode() + b"\n"
        with TemporaryDirectory(prefix="arachnid-utility-") as tmp:
            (Path(tmp) / "work").mkdir()
            spec = CommandSpec(argv=(str(executable), *args), cwd="work", stdin_bytes=frame,
                               separate_stderr=True, output_limit=_WIRE_LIMIT, timeout_seconds=120,
                               env_allow=("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA",
                                          "SYSTEMROOT", "PATH", "TMP", "TEMP"))
            result = ProcessRunner(tmp).run(spec)
        if (result.status != "completed" or result.exit_code != 0 or result.output_truncated
                or result.stdin_state != STDIN_DELIVERED):
            raise BridgeError("utility did not complete the exchange")
        return parse_reply(result.output, request)

    return run


def command(args):
    try:
        if not _ID.fullmatch(args.utility):
            raise BridgeError("invalid utility id")
        client = LocalStudio(args.server)
        path = input("Absolute path to your compatible executable: ").strip()
        argv = json.loads(input("Arguments as a JSON array (Return for []): ").strip() or "[]")
        peer = local_peer(path, argv)
        while True:
            worked = exchange(client, args.utility, peer)
            if worked:
                print("Reply recorded.", flush=True)
            if args.once:
                return 0
            time.sleep(1)
    except KeyboardInterrupt:
        return 0
    except (ValueError, OSError, RuntimeError, EOFError, http.client.HTTPException) as exc:
        print(f"Utility bridge stopped: {exc}", file=sys.stderr)
        return 1
