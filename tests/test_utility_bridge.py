"""A terminal bridge must never invoke a peer twice on a replayed claim."""
import json
import sys

import pytest

from conductor.utility_bridge import BridgeError, PROTOCOL, exchange, parse_address, parse_reply
from conductor.utility_bridge import local_peer


class Client:
    def __init__(self, claim=201):
        self.claim = claim
        self.requests = []

    def get(self, path):
        return {"utilities": [{"utility_id": "research", "mode": "stdio-v1"}],
                "exchanges": [{"utility_id": "research", "exchange_id": "q1",
                               "text": "Check a counter", "state": "pending"}]}

    def post(self, **body):
        self.requests.append(body)
        if body["op"] == "claim":
            return self.claim, {"exchange": {**self.get("")["exchanges"][0], "state": "claimed"}}
        return 201, {"exchange": {}}


def test_bridge_claims_once_and_only_sends_the_task_text():
    client, seen = Client(), []

    def peer(request):
        seen.append(request)
        return "Counter checked"

    assert exchange(client, "research", peer)
    assert seen == [dict(protocol=PROTOCOL, utility_id="research", exchange_id="q1",
                         text="Check a counter")]
    claim, finish = client.requests
    assert len(claim["claim_token"]) == 64
    assert claim["claim_token"] == finish["claim_token"]
    assert finish["text"] == "Counter checked" and finish["outcome"] == "answered"
    assert not exchange(Client(200), "research", peer)
    assert len(seen) == 1


def test_peer_failure_closes_unknown_without_retry():
    client, calls = Client(), []

    def broken(_request):
        calls.append(1)
        raise BridgeError("invalid reply")

    with pytest.raises(BridgeError):
        exchange(client, "research", broken)
    assert calls == [1]
    assert client.requests[-1]["outcome"] == "unknown"
    assert "text" not in client.requests[-1]


def test_real_local_peer_receives_just_one_frame_and_returns_its_text(tmp_path):
    helper = tmp_path / "peer.py"
    helper.write_text(
        "import json, sys\n"
        "row = json.loads(sys.stdin.buffer.readline())\n"
        "assert sys.stdin.buffer.read() == b'' and len(row) == 4\n"
        "row['text'] = 'received: ' + row['text']\n"
        "sys.stdout.buffer.write(json.dumps(row, ensure_ascii=True).encode() + b'\\n')\n",
        encoding="utf-8")
    client = Client()
    assert exchange(client, "research", local_peer(sys.executable, ["-I", "-B", str(helper)]))
    assert client.requests[-1]["text"] == "received: Check a counter"


def test_valid_address_requires_a_positive_port():
    assert parse_address("http://127.0.0.1:7804/") == 7804
    with pytest.raises(BridgeError):
        parse_address("http://127.0.0.1:0")


@pytest.mark.parametrize("url", ["https://127.0.0.1:8000", "http://localhost:8000",
                                  "http://127.0.0.1:8000/f", "http://foo@127.0.0.1:8000",
                                  "http://127.0.0.1:8000/?secret=yes"])
def test_only_an_explicit_local_studio_address_is_accepted(url):
    with pytest.raises(BridgeError):
        parse_address(url)


def test_protocol_rejects_an_answer_for_some_other_exchange_and_duplicate_keys():
    row = dict(protocol=PROTOCOL, utility_id="research", exchange_id="q1", text="work")
    assert parse_reply(json.dumps({**row, "text": "done"}).encode(), row) == "done"
    for bad in (json.dumps({**row, "exchange_id": "q2"}),
                json.dumps(row)[:-1] + ', "text":"second"}', json.dumps(row) + "\n{}"):
        with pytest.raises(BridgeError):
            parse_reply(bad.encode(), row)
