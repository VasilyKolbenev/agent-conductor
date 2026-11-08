"""A Kimi read-role configuration is code-owned, bounded and tied to reviewed profile bytes."""
import hashlib
import tomllib

import pytest


def test_only_managed_identity_and_selected_model_feed_the_read_role():
    from conductor.command.adapters.kimi_read_config import read_role_config
    from tests.test_kimi_quota import CONFIG

    source = (CONFIG + 'display_name = "unneeded display"\n').encode()
    plan = read_role_config(source)
    config = tomllib.loads(plan.content.decode())
    assert plan.profile_sha256 == hashlib.sha256(source).hexdigest()
    assert plan.config_sha256 == hashlib.sha256(plan.content).hexdigest()
    assert config["tools"] == {"enabled": ["Read"]}
    assert config["providers"]["managed:kimi-code"]["base_url"] == "https://api.kimi.com/coding/v1"
    assert config["models"][config["default_model"]]["model"] == "kimi-test"
    assert "unneeded display" not in plan.content.decode()
    assert read_role_config(CONFIG.encode()).config_sha256 == plan.config_sha256
    assert read_role_config(CONFIG.encode()).profile_sha256 != plan.profile_sha256


@pytest.mark.parametrize("policy", [(), ("Read", "Bash"), ("Write",), ["Read"]])
def test_bootstrap_cannot_request_any_other_tool_set(policy):
    from conductor.command.adapters.kimi_read_config import read_role_config
    from conductor.command.adapters.process_profile import ProfileRefused
    from tests.test_kimi_quota import CONFIG

    with pytest.raises(ProfileRefused, match="tool"):
        read_role_config(CONFIG.encode(), tools=policy)


@pytest.mark.parametrize("adjust", [
    lambda s: s + '\n[tools]\nenabled = ["Bash"]',
    lambda s: s.replace('api_key = ""', 'api_key = "unreviewed"'),
    lambda s: s.replace('model = "kimi-test"', 'model = "unreviewed/../model"'),
    lambda s: s.replace("api.kimi.com", "example.test"),
])
def test_foreign_profile_configuration_refuses_before_rendering(adjust):
    from conductor.command.adapters.kimi_read_config import read_role_config
    from conductor.command.adapters.process_profile import ProfileRefused
    from tests.test_kimi_quota import CONFIG

    with pytest.raises(ProfileRefused):
        read_role_config(adjust(CONFIG).encode())


def test_existing_temporary_config_is_never_overwritten(tmp_path):
    from conductor.command.adapters.kimi_read_config import bind_read_config, read_role_config
    from conductor.command.adapters.process_profile import ProfileRefused
    from tests.test_kimi_quota import CONFIG

    source = tmp_path / "source"
    state = tmp_path / "state"
    source.mkdir()
    state.mkdir()
    (source / "config.toml").write_bytes(CONFIG.encode())
    target = state / "config.toml"
    target.write_bytes(b"previous bytes")
    with pytest.raises(ProfileRefused, match="already exists"):
        with bind_read_config({"home": source, "kimi_state": state},
                              read_role_config(CONFIG.encode()), "unused", None):
            pytest.fail("used existing bytes")
    assert target.read_bytes() == b"previous bytes"


def test_missing_config_is_admissible_only_after_retirement_intent(tmp_path):
    from conductor.command.adapters.kimi_read_config import check_retiring_config
    from conductor.command.adapters.process_profile import ProfileRefused

    with pytest.raises(ProfileRefused, match="disappeared"):
        check_retiring_config(tmp_path, {}, retiring=False)
    check_retiring_config(tmp_path, {}, retiring=True)


def test_role_cannot_mutate_an_existing_restart_preparation(tmp_path, monkeypatch):
    from tests.test_kimi_state_journal import applied
    from conductor.command.adapters.process_profile import ProfileRefused

    _, acl, rec, _, _ = applied(tmp_path, monkeypatch)
    before = rec.read_bytes()
    preparation = rec.with_name(rec.stem + ".prepared-0.json")
    preparation.write_bytes(b"existing witness")
    binding = {"source_sha256": "a" * 64, "config_sha256": "b" * 64, "identity": [1, 2]}
    with pytest.raises(ProfileRefused, match="cannot bind"):
        acl.record_kimi_read_role(rec, binding)
    assert rec.read_bytes() == before and preparation.read_bytes() == b"existing witness"
    preparation.unlink()
    acl.retire(rec, proven=True)
    acl.close()
