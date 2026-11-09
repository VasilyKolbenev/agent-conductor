"""Project utilities exchange only explicit operator text via the real command door."""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Thread

import pytest

from conductor import ownership, ownership_transition, server
from conductor.command.project_claim import Launch, ProjectIdentity
from tests.test_command_http_api import TOKEN, api, encode, get_headers, post_headers
from tests.test_server_command_http import _request
from tests.test_store import write_project

PATH = "/command/project/utilities"
REGISTRATIONS = PATH + "/registrations"
PROJECT = "a" * 32
UTILITY = {"utility_id": "tool-a", "label": "Внешняя CLI", "mode": "manual"}
REQUEST = {"utility_id": "tool-a", "exchange_id": "request-1", "text": "Прочитать текст"}


def installation(root):
    subject, store, events = api(root)
    subject._identity = ProjectIdentity(PROJECT, None, False, "active", None, None)
    return subject, store, events


def call(subject, op, *, project=PROJECT, csrf=TOKEN, **body):
    packet = {"op": op, **body}
    headers = list(post_headers(packet, token=csrf))
    if project is not None:
        headers.append(("X-Conduct-Project", project))
    return subject.handle("POST", PATH, headers, encode(packet))


def listed(subject):
    result = subject.handle("GET", PATH, get_headers(), b"")
    assert result.status == 200, result.payload
    return result.payload


def test_registrations_do_not_read_or_list_any_exchange(tmp_path, monkeypatch):
    subject, _store, _events = installation(tmp_path)
    assert call(subject, "attach", **UTILITY).status == 201
    assert call(subject, "send", **REQUEST).status == 201
    folder = ownership.data_root(tmp_path) / "utilities" / "tool-a"
    request = folder / "request-1" / "request"
    request.write_bytes(b"PRIVATE BROKEN EXCHANGE")
    assert subject.handle("GET", PATH, get_headers()).status == 500
    enumerate_children = Path.iterdir
    open_file = Path.open

    def enumerate_only_registry(path):
        assert path != folder, "registrations enumerated the exchanges"
        return enumerate_children(path)

    def open_metadata_only(path, *args, **kwargs):
        assert request.parent not in path.parents, "registrations opened an exchange"
        return open_file(path, *args, **kwargs)

    monkeypatch.setattr(Path, "iterdir", enumerate_only_registry)
    monkeypatch.setattr(Path, "open", open_metadata_only)
    result = subject.handle("GET", REGISTRATIONS, get_headers())
    assert result.status == 200 and result.payload == {"utilities": [UTILITY]}
    assert subject.handle("POST", REGISTRATIONS, get_headers()).status == 405
    wrong = (*get_headers(), ("X-Conduct-Project", "b" * 32))
    assert subject.handle("GET", REGISTRATIONS, wrong).status == 409
    assert subject.handle("GET", REGISTRATIONS, get_headers("foreign.test")).status == 403


def test_registration_list_rejects_linked_metadata_and_omits_unpublished_rows(tmp_path):
    subject, _store, _events = installation(tmp_path)
    registry = ownership.data_root(tmp_path) / "utilities"
    (registry / "pending").mkdir(parents=True)
    assert subject.handle("GET", REGISTRATIONS, get_headers()).payload == {"utilities": []}
    assert call(subject, "attach", **UTILITY).status == 201
    metadata = registry / "tool-a" / "utility.json"
    peer = tmp_path / "private"
    peer.write_bytes(b"PRIVATE METADATA")
    metadata.unlink()
    metadata.hardlink_to(peer)
    result = subject.handle("GET", REGISTRATIONS, get_headers())
    assert result.status == 500 and result.payload["error"]["code"] == "store_error"
    assert "PRIVATE METADATA" not in str(result.payload)
    assert peer.read_bytes() == b"PRIVATE METADATA"


def test_manual_exchange_persists_exact_text_separately_from_run_and_adapters(tmp_path):
    subject, store, events = installation(tmp_path)
    before = store.read("run-001").records
    attached = call(subject, "attach", **UTILITY)
    assert attached.status == 201, attached.payload
    assert attached.payload == {"utility": UTILITY}
    assert call(subject, "attach", **UTILITY).status == 200
    assert call(subject, "send", **REQUEST).payload == {
        "exchange": {**REQUEST, "state": "pending", "reply": None}}
    reply = {"utility_id": "tool-a", "exchange_id": "request-1", "text": "ответ\n✓"}
    assert call(subject, "manual_reply", **reply).status == 201
    assert call(subject, "manual_reply", **reply).status == 200
    assert call(subject, "manual_reply", **{**reply, "text": "изменён"}).status == 409
    done = {**REQUEST, "state": "answered", "reply": reply["text"]}
    assert call(subject, "send", **REQUEST).payload == {"exchange": done}
    reader, _, _ = installation(tmp_path / "empty")
    reader._store = store
    reader._identity = ProjectIdentity(PROJECT, None, False, "view", None, None)
    assert listed(reader) == {"utilities": [UTILITY], "exchanges": [done]}
    assert call(reader, "attach", **UTILITY).status == 409
    assert store.read("run-001").records == before
    assert events == []


def protocol(subject, tool="tool-a", exchange="request-1"):
    utility = {**UTILITY, "utility_id": tool, "mode": "stdio-v1"}
    request = {**REQUEST, "utility_id": tool, "exchange_id": exchange}
    assert call(subject, "attach", **utility).status in (200, 201)
    assert call(subject, "send", **request).status == 201
    return {"utility_id": tool, "exchange_id": exchange}


def test_only_one_created_claim_even_concurrently_and_replay_starts_nothing(tmp_path):
    subject, _, _ = installation(tmp_path)
    ids = protocol(subject)
    secrets = ["c"*64, "e"*64]
    with ThreadPoolExecutor(2) as workers:
        responses = list(workers.map(lambda token: call(
            subject, "claim", **ids, claim_token=token), secrets))
    assert sorted(reply.status for reply in responses) == [201, 409]
    token = next(token for token, response in zip(secrets, responses) if response.status == 201)
    assert call(subject, "claim", **ids, claim_token=token).status == 200
    assert listed(subject)["exchanges"][0] == {**REQUEST, "state": "claimed", "reply": None}
    packets = [file.read_bytes() for file in (ownership.data_root(tmp_path) / "utilities"
                                               ).rglob("*") if file.is_file()]
    assert any(b'"digest":' in packet for packet in packets)
    assert all(token.encode() not in packet for packet in packets)
    assert "digest" not in json.dumps(listed(subject))
    result = {**ids, "claim_token": token, "outcome": "answered", "text": "mine"}
    assert call(subject, "finish", **{**result, "claim_token": "0"*64}).status == 409
    assert call(subject, "finish", **result).status == 201
    assert call(subject, "finish", **result).status == 200
    assert call(subject, "finish", **{**result, "text": "replace"}).status == 409
    assert call(subject, "mark_unknown", **ids).status == 409
    assert call(subject, "claim", **ids, claim_token=token).status == 200
    assert listed(subject)["exchanges"] == [{**REQUEST, "state": "answered", "reply": "mine"}]


def test_unknown_after_crash_never_reopens_other_tool_or_manual_exchange(tmp_path):
    subject, _, _ = installation(tmp_path)
    a = protocol(subject)
    b = protocol(subject, tool="tool-b")
    token = "5"*64
    assert call(subject, "mark_unknown", **a).status == 409
    assert call(subject, "manual_reply", **a, text="wrong road").status == 409
    assert call(subject, "claim", **a, claim_token=token).status == 201
    assert call(subject, "finish", **b, claim_token=token, outcome="unknown").status == 409
    assert call(subject, "mark_unknown", **a).status == 201
    assert call(subject, "mark_unknown", **a).status == 200
    assert call(subject, "finish", **a, claim_token=token, outcome="unknown").status == 200
    assert call(subject, "claim", **a, claim_token="6"*64).status == 409
    assert call(subject, "send", **REQUEST).payload["exchange"]["state"] == "unknown"
    assert call(subject, "send", **{**REQUEST, "text": "retry"}).status == 409
    assert [row["state"] for row in listed(subject)["exchanges"]] == ["unknown", "pending"]


@pytest.mark.parametrize("edits", [
    {"mode": "custom"}, {"argv": ["calc.exe"]}, {"url": "https://example.invalid"},
    {"utility_id": "../x"}, {"utility_id": "con"}, {"utility_id": "Mixed"},
    {"label": "one\ntwo"}, {"label": "x"*81}, {"mode": []}, {"utility_id": "x"*49},
])
def test_closed_registration_rejects_command_fields_and_unsafe_names(tmp_path, edits):
    subject, _, _ = installation(tmp_path)
    assert call(subject, "attach", **{**UTILITY, **edits}).status == 422
    assert listed(subject) == {"utilities": [], "exchanges": []}
    assert not (ownership.data_root(tmp_path) / "utilities").exists()


def test_project_and_csrf_gate_precede_every_disk_write(tmp_path):
    subject, _, _ = installation(tmp_path)
    assert call(subject, "attach", **UTILITY, project=None).status == 409
    assert call(subject, "attach", **UTILITY, project="b"*32).status == 409
    assert call(subject, "attach", **UTILITY, csrf="bad").status == 403
    assert not (ownership.data_root(tmp_path) / "utilities").exists()
    assert call(subject, "attach", **UTILITY).status == 201
    assert call(subject, "attach", **{**UTILITY, "mode": "stdio-v1"}).status == 409
    assert call(subject, "send", **{**REQUEST, "text": "  "}).status == 422
    assert call(subject, "send", **{**REQUEST, "text": "я"*4097}).status == 422
    assert call(subject, "send", **REQUEST).status == 201
    ids = {key: REQUEST[key] for key in ("utility_id", "exchange_id")}
    assert call(subject, "claim", **ids, claim_token="X"*64).status == 422
    assert call(subject, "claim", **ids, claim_token="d"*64).status == 409
    assert call(subject, "finish", **ids, claim_token="d"*64, outcome="unknown",
                text="hidden").status == 422
    assert call(subject, "mark_unknown", **ids).status == 409
    assert listed(subject)["exchanges"][0]["state"] == "pending"


def test_tampered_or_hardlinked_records_fail_closed_without_disclosing_files(tmp_path):
    subject, _, _ = installation(tmp_path)
    ids = protocol(subject)
    claim = {"claim_token": "0"*64, **ids}
    assert call(subject, "claim", **claim).status == 201
    path = ownership.data_root(tmp_path) / "utilities" / "tool-a" / "request-1" / "claim"
    target = tmp_path / "untouched"
    target.write_text("PRIVATE EXTERNAL", encoding="utf-8")
    path.unlink()
    path.hardlink_to(target)
    read = subject.handle("GET", PATH, get_headers(), b"")
    assert read.status == 500 and "PRIVATE EXTERNAL" not in str(read.payload)
    assert call(subject, "claim", **claim).status == 500
    assert target.read_bytes() == b"PRIVATE EXTERNAL"


def test_owned_loopback_server_persists_manual_reply_across_restart_into_view(tmp_path):
    root = write_project(tmp_path)
    ownership_transition.activate(root, legacy_writers_stopped=True)
    for mode in ("active", "view"):
        srv = server.build(root, 0, launch=Launch(mode=mode), token_factory=lambda _: TOKEN)
        thread = Thread(target=srv.serve_forever, daemon=True)
        thread.start()
        try:
            status, project, _ = _request(srv, "GET", "/command/project")
            assert status == 200 and project["mode"] == mode
            headers = {"X-Conduct-Project": project["project_id"]}

            def post(op, body):
                return _request(srv, "POST", PATH, {"op": op, **body}, headers=headers)[:2]

            if mode == "active":
                assert post("attach", UTILITY) == (201, {"utility": UTILITY})
                assert post("send", REQUEST)[0] == 201
                assert post("manual_reply", {**REQUEST, "text": "literal answer"})[0] == 201
            else:
                assert post("attach", UTILITY)[0] == 409
            status, saved, _ = _request(srv, "GET", PATH, headers=headers)
            assert status == 200 and saved == {"utilities": [UTILITY], "exchanges": [
                {**REQUEST, "state": "answered", "reply": "literal answer"}]}
            status, catalog, _ = _request(srv, "GET", REGISTRATIONS, headers=headers)
            assert status == 200 and catalog == {"utilities": [UTILITY]}
        finally:
            srv.shutdown()
            srv.server_close()
            thread.join(5)
        assert not thread.is_alive()
