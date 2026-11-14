"""Only the access-only Codex child gets the code-owned refresh route.

The successful road records the actual command environments, not a whitelist result. Its
preflights and quota reader stand on the real login, so that route must be absent there.
Every credential and CLI used here is synthetic.
"""
from dataclasses import replace

import pytest

from conductor.command.quota_plans import quota_plan_for
from tests import _fakecodex
from tests._fakeboundary import confined
from tests.relay_roads import CODEX, Site, digests
from tests.test_command_codex_transport import a_harness, a_request, run_once
from tests.test_relay_road_refusals import assert_refused_before_the_claim
from tests.test_subscription_quota import PAYLOAD, adapter as quota_adapter

NAME = "CODEX_REFRESH_TOKEN_URL_OVERRIDE"
VALUE = "http://127.0.0.1:9/oauth/token"
OPERATOR = "https://route.invalid/operator-refresh-0123456789"
CREDENTIAL_NAMES = (
    "OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN", "OPENAI_FEDERATION_RULE_ID",
    "OPENAI_IDENTITY_TOKEN_FILE", "OPENAI_WORKLOAD_IDENTITY_CONTEXT",
    "CODEX_GUARDIAN_DECISIONS_API_KEY")
FAKE_CREDENTIAL = "fake-credential-only-for-this-test-0123456789"


def with_code_owned_route(adapter):
    """Pin the reviewed profile pair even on the old implementation during the red phase."""
    adapter.profile = replace(adapter.profile, forced_env=((NAME, VALUE),))


def record_environments(runner):
    seen = []
    run = runner.run

    def observe(spec):
        seen.append((tuple(spec.argv), runner._child_env(spec)))
        return run(spec)

    runner.run = observe
    return seen


def test_only_the_access_only_task_gets_the_exact_code_owned_refresh_route(tmp_path):
    site = Site(tmp_path, CODEX)
    with_code_owned_route(site.adapter)
    seen = record_environments(site.runner)
    before, request = digests(site.login), site.request()

    receipt = site.run(request)

    assert receipt.outcome == "succeeded", receipt.detail
    assert len(site.tasks()) == 1 and site.claimed(request)
    assert len(seen) == 3, "version, login status and one task must all run"
    for argv, env in seen[:2]:
        assert "exec" not in argv
        assert env["CODEX_HOME"] == str(site.login)
        assert NAME not in env, "a question to the real login must not reroute refresh"
    argv, env = seen[-1]
    assert "exec" in argv and env["CODEX_HOME"] != str(site.login)
    assert env[NAME] == VALUE
    assert digests(site.login) == before
    assert site.leftovers() == [] and site.lease_is_free()


@pytest.mark.parametrize("name", [NAME, NAME.lower()])
@pytest.mark.parametrize("value", [VALUE, "https://route.invalid/token"])
def test_an_operator_refresh_override_is_refused_even_when_its_value_matches_code(
        tmp_path, name, value):
    site = Site(tmp_path, CODEX)
    with_code_owned_route(site.adapter)
    site.adapter._pin = replace(site.adapter._pin,
                                env_allow=(*site.adapter._pin.env_allow, name))
    site.runner._environ[name] = value
    request = site.request()

    receipt = site.run(request)

    assert_refused_before_the_claim(site, request, receipt, "env")
    assert site.rows() == [], "even a question to the real home is forbidden"
    assert "route.invalid" not in receipt.detail


@pytest.mark.parametrize("name,value", [
    (NAME, "http://127.0.0.1:10/oauth/token"),
    ("CODEX_AUTHAPI_BASE_URL", VALUE),
    ("HTTPS_PROXY", VALUE),
])
def test_the_code_owned_exception_does_not_admit_any_other_forced_route(tmp_path, name, value):
    site = Site(tmp_path, CODEX)
    site.adapter.profile = replace(site.adapter.profile, forced_env=((name, value),))
    request = site.request()

    receipt = site.run(request)

    assert_refused_before_the_claim(site, request, receipt, "env")
    assert site.rows() == []


def test_quota_and_its_version_question_keep_the_real_login_refresh_route(tmp_path):
    adapter, runner, home = quota_adapter(tmp_path)
    with_code_owned_route(adapter)

    result = quota_plan_for("codex", adapter).request.read()

    assert result == PAYLOAD
    assert len(runner.specs) == 2
    for spec in runner.specs:
        env = runner._child_env(spec)
        assert env["CODEX_HOME"] == str(home)
        assert NAME not in env


@pytest.mark.parametrize("boundary", [False, True])
def test_an_api_task_does_not_get_the_access_only_refresh_route(tmp_path, boundary):
    adapter, _root, log = a_harness(tmp_path)
    with_code_owned_route(adapter)
    if boundary:
        confined(adapter, tmp_path / "scratch", platform="win32")
    seen = record_environments(adapter._runner)

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "succeeded", receipt.detail
    assert len(_fakecodex.task_spawns(log)) == 1
    assert len(seen) == 2
    assert all(NAME not in env for _, env in seen)


@pytest.mark.parametrize("boundary", [False, True])
def test_the_publication_scan_holds_the_value_the_api_task_child_really_received(
        tmp_path, boundary):
    adapter, _root, _log = a_harness(tmp_path, **{NAME: OPERATOR})
    with_code_owned_route(adapter)
    if boundary:
        confined(adapter, tmp_path / "scratch", platform="win32")
    seen = record_environments(adapter._runner)

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "succeeded", receipt.detail
    assert all(env.get(NAME) == OPERATOR for _, env in seen)
    held = adapter._sensitive_values()
    assert OPERATOR.encode() in held, "the value the child received is not scanned"
    assert VALUE.encode() not in held, "a value no API child received is scanned for"


def test_the_relayed_task_scan_keeps_the_code_owned_route_the_child_received(tmp_path):
    site = Site(tmp_path, CODEX)
    with_code_owned_route(site.adapter)
    pin = site.adapter._pin
    # A direct pin: beside a subscription the product refuses this name, and a forced pair
    # reaches the scan only for a name in `env_allow`.
    site.adapter._pin = replace(pin, env_allow=(*pin.env_allow, NAME))
    seen = record_environments(site.runner)

    receipt = site.run()

    assert receipt.outcome == "succeeded", receipt.detail
    assert seen[-1][1][NAME] == VALUE, "the access-only task child was not given the route"
    assert VALUE.encode() in site.adapter._sensitive_values()


def test_the_scan_of_an_unconfined_relay_road_holds_no_route_no_child_received(
        tmp_path, monkeypatch):
    """Only a confined transport is relayed: `_confine` is half of the scan's predicate."""
    adapter, _root, _log = a_harness(tmp_path, **{NAME: OPERATOR})
    with_code_owned_route(adapter)
    monkeypatch.setattr(adapter, "_relay_road", lambda: True)

    assert adapter._relay_road() and adapter._confine is False and NAME in adapter._env_allow()
    assert adapter._relayed("dispatch") is False, "an unconfined transport is not relayed"
    held = adapter._sensitive_values()
    assert OPERATOR.encode() in held, "the value the task child would receive is not scanned"
    assert VALUE.encode() not in held, "a route no child of this transport received is scanned"


@pytest.mark.parametrize("name", CREDENTIAL_NAMES)
@pytest.mark.parametrize("lower", [False, True])
def test_a_direct_subscription_pin_refuses_a_selected_credential_before_any_spawn(
        tmp_path, name, lower):
    name = name.lower() if lower else name
    site = Site(tmp_path, CODEX)
    site.adapter._pin = replace(site.adapter._pin,
                                env_allow=(*site.adapter._pin.env_allow, name))
    site.runner._environ[name] = FAKE_CREDENTIAL
    request = site.request()

    receipt = site.run(request)

    assert_refused_before_the_claim(site, request, receipt, "env")
    assert site.rows() == [], "a credential selected by a direct pin reached a real-home query"
    assert FAKE_CREDENTIAL not in receipt.detail


@pytest.mark.parametrize("name", CREDENTIAL_NAMES)
def test_an_ambient_credential_not_selected_by_the_subscription_pin_does_not_block_it(
        tmp_path, name):
    site = Site(tmp_path, CODEX)
    assert name not in site.adapter._pin.env_allow
    site.runner._environ[name] = FAKE_CREDENTIAL
    seen = record_environments(site.runner)

    receipt = site.run()

    assert receipt.outcome == "succeeded", receipt.detail
    assert len(site.tasks()) == 1 and len(seen) == 3
    assert all(name not in env for _, env in seen)


@pytest.mark.parametrize("name", CREDENTIAL_NAMES)
def test_the_api_road_can_still_select_its_credential(tmp_path, name):
    adapter, _root, log = a_harness(tmp_path, **{name: FAKE_CREDENTIAL})
    seen = record_environments(adapter._runner)

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "succeeded", receipt.detail
    assert len(_fakecodex.task_spawns(log)) == 1 and len(seen) == 2
    assert all(env[name] == FAKE_CREDENTIAL for _, env in seen)
