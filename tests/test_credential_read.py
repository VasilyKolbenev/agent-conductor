"""A JSON surrogate cannot abort or empty the declared credential leak scan."""
import json

import pytest

from conductor.command.adapters.login_home import credential_values
from conductor.command.adapters.quota_connection import NativeQuotaReadError
from tests.test_codex_quota_echo import account_reply, limits_reply, make, mcp_login


NEIGHBOR = "SYNTHETIC-neighbor-token-0123"
BAD = "\ud800" * 12
BAD_BYTES = b"\xed\xa0\x80" * 12


def test_escaped_surrogate_preserves_every_credential_byte_and_neighbor(tmp_path):
    home = tmp_path / "login"
    home.mkdir()
    leaf = home / "auth.json"
    document = {"bad": BAD, "neighbor": NEIGHBOR,
                "duplicates": [BAD, NEIGHBOR], "short": "\ud800" * 11,
                "nested": {"valid": "abcdefghijkl\u00e9", "small": "short"}}
    original = json.dumps(document, ensure_ascii=True).encode("ascii")
    leaf.write_bytes(original)
    (home / "unselected.json").write_text('{"secret":"UNSELECTED-secret-0123"}')
    assert b"\\ud800" * 12 in original and len(original) < 65536
    assert json.loads(original)["bad"] == BAD

    actual = credential_values(str(home), ("auth.json",))

    assert actual == (BAD_BYTES, b"SYNTHETIC-neighbor-token-0123", b"abcdefghijkl\xc3\xa9")
    assert leaf.read_bytes() == original


def test_a_valid_neighbor_still_blocks_quota_echo_beside_a_surrogate(tmp_path):
    adapter, runner = make(tmp_path, credentials=mcp_login(note=BAD, private=NEIGHBOR))
    home = tmp_path / "pinned"
    original = {name: (home / name).read_bytes()
                for name in ("auth.json", ".credentials.json")}
    # Omit the account id from both own fields, so it cannot cause this refusal.
    runner.account = account_reply(workspaceRouting=None)
    runner.limits = limits_reply(accountId=None, note=NEIGHBOR)

    with pytest.raises(NativeQuotaReadError):
        adapter.quota_connection().read()

    assert len(runner.specs) == 2, "both fake version and quota spawns must have run"
    assert b"SYNTHETIC-neighbor-token-0123" in runner.specs[-1].sensitive_extra
    assert BAD_BYTES in runner.specs[-1].sensitive_extra
    assert adapter._login_echo is True
    assert adapter._service is None and adapter._service_values == ()
    assert adapter._login_seen == () and adapter._retained == 0
    assert all((home / name).read_bytes() == value for name, value in original.items())
