"""Harmless local example of one arachnid.utility.v1 exchange. No network or files."""
import json
import sys

request = json.loads(sys.stdin.buffer.readline())
if (sys.stdin.buffer.read() or set(request) != {"protocol", "utility_id", "exchange_id", "text"}
        or request["protocol"] != "arachnid.utility.v1"):
    raise SystemExit(2)
reply = {**request, "text": "Локальный пример получил: " + request["text"]}
sys.stdout.buffer.write(json.dumps(reply, ensure_ascii=True).encode("ascii") + b"\n")
