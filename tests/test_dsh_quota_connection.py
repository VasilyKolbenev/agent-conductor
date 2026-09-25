"""Pending witnesses: private balance capture agrees with native dispatch env.

No native process or network is necessary for this value/factory slice. Native
precedence itself is witnessed separately by the instrumented 13-case probe.
"""
from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path

import pytest

from conductor.command.adapters.dsh_harness import (
    API_ORIGIN_ENV, BALANCE_ENDPOINT, BALANCE_SOURCE_VERSION, DEFAULT_API_KEY_ENV,
    DSH_HOME_ENV, DSH_PROTOCOL, DshHarnessAdapter, DshPin, QUOTA_POLICY,
)
from conductor.command.adapters.environment_values import EnvironmentSelectionError, EnvironmentValues
from conductor.command.adapters.codex_cli import QUOTA_POLICY as SUBSCRIPTION_POLICY
from conductor.command.adapters.process import CommandSpec, CommandSpecError, ProcessRunner
from conductor.command.adapters.provider import ProviderConfig
from conductor.command.adapters.quota_connection import NativeQuotaConnection, native_quota_connection
from conductor.command.adapters.quota_contracts import QuotaError
from conductor.command.providers import ProviderResolution, resolve_providers
from conductor.command.quota import CredentialContext, QuotaSource
from conductor.command.quota_plans import ProviderQuotaPlan, quota_plan_for

SECRET = "synthetic-capture-secret"
OTHER = "synthetic-other-secret"
NOW = "2026-09-21T13:00:00Z"


class NoSpawn(ProcessRunner):
    def run(self, *args, **kwargs):
        pytest.fail("a quota supplier must not spawn")


def adapter(tmp_path, environ=None, names=None):
    env = {DEFAULT_API_KEY_ENV: SECRET} if environ is None else environ
    pin = DshPin(str(tmp_path / "node.exe"), str(tmp_path / "bin.js"),
                 tuple(env) if names is None else names)
    runner = NoSpawn(tmp_path, environ=env)
    return DshHarnessAdapter(pin, runner, root=tmp_path, clock=lambda: NOW,
                             ids=lambda kind: kind + "-fixture")


def request(**changes):
    return replace(NativeQuotaConnection(QUOTA_POLICY, BALANCE_SOURCE_VERSION,
                                         BALANCE_ENDPOINT, SECRET), **changes)


def test_capture_uses_constructor_snapshot_and_same_explicit_overrides_as_child(tmp_path):
    original = {"CREDENTIAL": SECRET, "HIDDEN": OTHER}
    runner = NoSpawn(tmp_path, environ=original)
    original["CREDENTIAL"] = OTHER
    overrides = {"LITERAL": "owned", "CREDENTIAL": "literal-wins"}
    spec = CommandSpec((str(tmp_path / "node.exe"),), str(tmp_path),
                       env_allow=("CREDENTIAL",), env=overrides)
    captured = runner.capture_environment(spec.env_allow, overrides=spec.env)
    overrides["CREDENTIAL"] = OTHER
    assert dict(captured.values) == runner._child_env(spec) == {
        "CREDENTIAL": "literal-wins", "LITERAL": "owned"}
    assert runner._environment(("CREDENTIAL",), {}) == {"CREDENTIAL": SECRET}
    assert runner.capture_environment(("CREDENTIAL",)).native_value("CREDENTIAL") == SECRET
    assert OTHER not in repr(captured) and "literal-wins" not in repr(captured)
    with pytest.raises(TypeError):
        captured.values["CREDENTIAL"] = OTHER
    with pytest.raises(FrozenInstanceError):
        captured.windows = not captured.windows


def test_capture_reuses_command_environment_validation(tmp_path):
    runner = NoSpawn(tmp_path, environ={})
    for names in (("NODE_OPTIONS",), ("A", "A"), "CREDENTIAL"):
        with pytest.raises(CommandSpecError):
            runner.capture_environment(names)
    with pytest.raises(CommandSpecError):
        runner.capture_environment((), overrides={"A": "bad\x00value"})


def test_windows_interpretation_follows_exact_selection_and_does_not_guess(tmp_path):
    runner = NoSpawn(tmp_path, environ={"credential": SECRET})
    selected = runner.capture_environment(("credential",))
    assert EnvironmentValues(selected.values, windows=True).native_value("CREDENTIAL") == SECRET
    not_selected = runner.capture_environment(("CREDENTIAL",))
    assert EnvironmentValues(not_selected.values, windows=True).native_value("CREDENTIAL") is None
    aliases = EnvironmentValues({"credential": SECRET, "CREDENTIAL": OTHER}, windows=True)
    with pytest.raises(EnvironmentSelectionError, match="ambiguous native"):
        aliases.native_value("CREDENTIAL")
    distinct = EnvironmentValues(aliases.values, windows=False)
    assert distinct.native_value("CREDENTIAL") == OTHER
    assert distinct.native_value("credential") == SECRET


def test_environment_values_copy_and_never_repr_bad_values():
    original = {"CREDENTIAL": SECRET}
    captured = EnvironmentValues(original)
    original["CREDENTIAL"] = OTHER
    assert captured.native_value("CREDENTIAL") == SECRET
    assert SECRET not in repr(captured)
    with pytest.raises(EnvironmentSelectionError) as caught:
        EnvironmentValues({SECRET + "!": OTHER})
    assert SECRET not in str(caught.value) and OTHER not in str(caught.value)


@pytest.mark.parametrize("origin", [None, "https://api.deepseek.com"])
def test_supplier_uses_exact_default_key_and_fixed_public_balance_endpoint(tmp_path, origin):
    env = {DEFAULT_API_KEY_ENV: SECRET}
    if origin is not None:
        env[API_ORIGIN_ENV] = origin
    native = adapter(tmp_path, env).quota_connection()
    assert native == request()
    assert native.bearer == SECRET and SECRET not in repr(native)


@pytest.mark.parametrize("origin", ["", "https://gateway.example", "https://api.deepseek.com/",
                                    "http://api.deepseek.com", "https://api.deepseek.com/v1"])
def test_supplier_never_substitutes_public_balance_for_another_origin(tmp_path, origin):
    native = adapter(tmp_path, {DEFAULT_API_KEY_ENV: SECRET, API_ORIGIN_ENV: origin}).quota_connection()
    assert native.reason == "not_supported" and native.bearer is None


@pytest.mark.parametrize("key", [None, ""])
def test_missing_default_key_is_unavailable_without_file_discovery(tmp_path, monkeypatch, key):
    env = {} if key is None else {DEFAULT_API_KEY_ENV: key}
    subject = adapter(tmp_path, env)
    (tmp_path / ".env").write_text(DEFAULT_API_KEY_ENV + "=" + SECRET, encoding="utf-8")
    monkeypatch.setattr(Path, "read_text", lambda *a, **kw: pytest.fail("no quota file discovery"))
    native = subject.quota_connection()
    assert native.reason == "no_data" and native.bearer is None


def test_supplier_snapshot_rebind_requires_new_runner(tmp_path):
    env = {DEFAULT_API_KEY_ENV: SECRET}
    old = adapter(tmp_path, env)
    env[DEFAULT_API_KEY_ENV] = OTHER
    assert old.quota_connection().bearer == SECRET
    assert adapter(tmp_path, env).quota_connection().bearer == OTHER


@pytest.mark.parametrize("extra", [
    {DEFAULT_API_KEY_ENV.lower(): OTHER},
    {API_ORIGIN_ENV: "https://api.deepseek.com", API_ORIGIN_ENV.lower(): "https://gateway.example"},
    {DSH_HOME_ENV.lower(): "synthetic-home"},
])
def test_supplier_refuses_ambiguous_windows_credentials_origin_or_home(tmp_path, monkeypatch, extra):
    subject = adapter(tmp_path)
    selected = EnvironmentValues({DEFAULT_API_KEY_ENV: SECRET, **extra}, windows=True)
    monkeypatch.setattr(subject._runner, "capture_environment", lambda *a, **kw: selected)
    native = subject.quota_connection()
    assert native.reason == "not_supported" and native.bearer is None


def test_supplier_does_not_read_normal_inherited_home(tmp_path, monkeypatch):
    subject = adapter(tmp_path, {DEFAULT_API_KEY_ENV: SECRET, DSH_HOME_ENV: "synthetic-home"})
    monkeypatch.setattr(Path, "read_text", lambda *a, **kw: pytest.fail("no inherited home scan"))
    assert subject.quota_connection() == request()


def test_supplier_and_core_sanitize_exceptions_without_changing_dispatch(tmp_path, monkeypatch):
    subject = adapter(tmp_path)
    def broken(*args, **kwargs):
        raise RuntimeError(SECRET)
    monkeypatch.setattr(subject._runner, "capture_environment", broken)
    failed = subject.quota_connection()
    assert failed.reason == "source_error" and failed.bearer is None
    assert SECRET not in repr(failed)
    monkeypatch.setattr(subject, "quota_connection", broken)
    plan = quota_plan_for("provider-alias", subject)
    assert plan.reason == "source_error" and plan.request is None and plan.source is None
    assert plan.connection is None and SECRET not in repr(plan)


@pytest.mark.parametrize("changes", [
    {"bearer": ""}, {"bearer": " secret"}, {"bearer": "x\r\ny"},
    {"bearer": "x\x00y"}, {"bearer": "x\u2603"}, {"bearer": "x" * 8193},
    {"reason": "no_data"}, {"reason": "invented", "bearer": None},
    {"endpoint": "http://example.com/user/balance"},
    {"endpoint": "https://user:password@example.com/user/balance"},
    {"endpoint": "https://example.com:444/user/balance"},
    {"endpoint": "https://example.com/user/balance?key=" + SECRET},
])
def test_private_connection_invalid_shapes_refuse_without_secret_text(changes):
    with pytest.raises(QuotaError) as caught:
        request(**changes)
    assert SECRET not in str(caught.value)


def test_private_values_are_reconstructed_after_frozen_object_tampering():
    native = request()
    object.__setattr__(native, "bearer", "bad\r\n" + SECRET)
    with pytest.raises(QuotaError):
        native_quota_connection(native)
    class Supplier:
        def quota_connection(self):
            return native
    result = quota_plan_for("provider-alias", Supplier())
    assert result.reason == "source_error" and result.request is None
    assert SECRET not in repr(result)


def test_private_connection_cannot_claim_a_subscription_source():
    with pytest.raises(QuotaError, match="monetary"):
        request(policy=SUBSCRIPTION_POLICY)


def test_generic_plan_preserves_source_but_never_groups_credentials_or_aliases():
    class Supplier:
        def quota_connection(self):
            return request()
    first = quota_plan_for("same-alias", Supplier())
    again = quota_plan_for("same-alias", Supplier())
    assert first.connection.context_id != again.connection.context_id
    assert first.source == QuotaSource(QUOTA_POLICY, BALANCE_SOURCE_VERSION)
    assert first.connection.policy == first.request.policy == first.source.policy
    assert first.connection.as_dict()["account_status"] == "unknown"
    assert SECRET not in repr(first)
    with pytest.raises(QuotaError):
        replace(first, source=QuotaSource(QUOTA_POLICY, "another-schema"))
    foreign_policy = replace(QUOTA_POLICY, vendor="unlisted-vendor")
    with pytest.raises(QuotaError):
        replace(first, connection=CredentialContext.create(foreign_policy))


def test_generic_plan_optional_supplier_and_unavailable_contract(tmp_path):
    assert quota_plan_for("alias", None) is None
    assert quota_plan_for("alias", object()) is None
    plan = quota_plan_for("alias", adapter(tmp_path, {}))
    assert plan.reason == "no_data" and plan.connection is None and plan.source is not None
    with pytest.raises(QuotaError):
        replace(plan, connection=CredentialContext.create(QUOTA_POLICY))
    with pytest.raises(QuotaError):
        ProviderQuotaPlan("alias", reason="no_data")


def test_provider_resolution_keeps_quota_credentials_out_of_public_contracts(tmp_path, monkeypatch):
    node, entry = tmp_path / "node.exe", tmp_path / "bin.js"
    node.write_bytes(b"")
    entry.write_bytes(b"")
    config = ProviderConfig("deepseek-harness", str(node), DSH_PROTOCOL,
                            env_allow=(DEFAULT_API_KEY_ENV,), entrypoint=str(entry))
    monkeypatch.setattr(ProcessRunner, "run", lambda *a, **kw: pytest.fail("factory must not spawn"))
    kwargs = dict(root=tmp_path, clock=lambda: NOW, ids=lambda kind: kind,
                  environ={DEFAULT_API_KEY_ENV: SECRET})
    first = resolve_providers((config,), **kwargs)
    second = resolve_providers((config,), **kwargs)
    assert first.spawn_capable(config.provider_id)
    assert len(first.quota_plans) == 1
    plan = first.quota_plans[0]
    assert plan.provider_id == config.provider_id and plan.request.bearer == SECRET
    assert plan.connection.context_id != second.quota_plans[0].connection.context_id
    public = json.dumps([row.as_dict() for row in first.contracts])
    assert SECRET not in public and BALANCE_ENDPOINT not in public
    assert "quota_plans" not in public and "bearer" not in public
    assert SECRET not in repr(first) and SECRET not in json.dumps(config.as_dict())
    assert ProviderResolution(first.registry, first.contracts).quota_plans == ()
    unavailable = resolve_providers((config,), **{**kwargs, "environ": {}})
    assert unavailable.spawn_capable(config.provider_id)
    assert unavailable.quota_plans[0].reason == "no_data"
    assert unavailable.quota_plans[0].connection is None
