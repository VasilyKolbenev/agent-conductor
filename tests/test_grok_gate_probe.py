"""The one-shot operator probe observes only authenticate, before any session or task."""
import json
import tomllib

import pytest

from scripts import grok_gate_probe as probe


def reply(identity, result):
    return {"jsonrpc": "2.0", "id": identity, "result": result}


def stream(*rows):
    return b"\n".join(json.dumps(row).encode() for row in rows)


INIT = reply(1, {"_meta": {"defaultAuthMethodId": "cached_token"}})
CACHED = reply(2, {"methodId": "cached_token", "email": "private@example.invalid"})


def test_only_noninteractive_metadata_ends_the_wire():
    rows = [json.loads(row) for row in probe.SERVICE.payload.splitlines()]
    assert probe.SERVICE.argv == ("--no-auto-update", "agent", "stdio")
    assert [row["method"] for row in rows] == ["initialize", "_x.ai/auth/info", "authenticate"]
    assert rows[-1] == {"jsonrpc": "2.0", "id": 3, "method": "authenticate",
                        "params": {"methodId": "cached_token", "_meta": {"headless": True}}}
    assert probe.SERVICE.completion_id == 3


def test_only_oidc_pinned_configuration_is_generated_in_a_new_relay(tmp_path):
    probe.pin_oidc(tmp_path)
    assert tomllib.loads((tmp_path / "config.toml").read_text()) == {
        "auth": {"preferred_method": "oidc"}}
    with pytest.raises(FileExistsError):
        probe.pin_oidc(tmp_path)


def test_private_post_auth_notification_is_discarded():
    notice = {"jsonrpc": "2.0", "method": "_x.ai/settings/update",
              "params": {"gate": {"message": "not the authenticate reply"}}}
    assert probe.signal(stream(INIT, CACHED, notice, reply(3, {}))) == "no_gate_reported"


def test_unknown_method_and_vendor_error_do_not_leak_through_diagnostic_facts():
    opaque = {"jsonrpc": "2.0", "method": "_private_notification", "params": {"private": 1}}
    denied = {"jsonrpc": "2.0", "id": 3, "error": {"message": "private marker"}}
    assert probe.wire_facts(stream(INIT, CACHED, opaque, denied)) == {
        "reply_kinds": ["result", "result", "error"], "extra_notification": True}
    assert probe.wire_facts(b"unparseable") == {"malformed_frame": True}


@pytest.mark.parametrize(("result", "expected"), [
    ({"_meta": {"gate": {"message": "private reason", "url": "private url"}}}, "restriction_seen"),
    ({"_meta": {"subscriptionTier": "private tier"}}, "no_gate_reported"),
    ({}, "no_gate_reported"), ({"_meta": {"gate": None}}, "no_gate_reported"),
    ({"_meta": []}, "invalid_gate"), ({"_meta": {"gate": ""}}, "invalid_gate"),
    ({"_meta": {"gate": {"message": ""}}}, "invalid_gate"),
])
def test_only_a_fixed_label_leaves_the_response(result, expected):
    assert probe.signal(stream(INIT, CACHED, reply(3, result))) == expected


@pytest.mark.parametrize("rows", [
    [INIT, CACHED], [INIT, CACHED, reply(3, {}), reply(3, {})],
    [INIT, reply(2, {"methodId": "api_key"}), reply(3, {})],
    [reply(1, {}), CACHED, reply(3, {})],
    [{"jsonrpc": "1.0", "id": 1, "result": INIT["result"]}, CACHED, reply(3, {})],
    [INIT, CACHED, {"jsonrpc": "2.0", "id": 3, "error": {"message": "private reason"}}],
])
def test_wrong_account_or_incomplete_rpc_cannot_confirm_access(rows):
    assert probe.signal(stream(*rows)) == "unconfirmed_exchange"
