"""Native quota facts cannot become invented capacity or execution permission."""
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from functools import partial
import json

import pytest

from conductor.command.quota import (
    AccountIdentity, BalanceAmount, BalanceObservation, QuotaError, QuotaObservation,
    QuotaSource, QuotaWindow, failed_balance_observation, failed_observation,
    parse_observation,
)
from conductor.command.quota_service import QuotaService
from conductor.command.adapters.claude_code import QUOTA_POLICY as CLAUDE_QUOTA
from conductor.command.adapters.codex_cli import QUOTA_POLICY as CODEX_QUOTA
from conductor.command.adapters.dsh_harness import QUOTA_POLICY as DSH_QUOTA
from conductor.command.adapters.grok_build import QUOTA_POLICY as GROK_QUOTA
from conductor.command.adapters.kimi_code import QUOTA_POLICY as KIMI_QUOTA
from conductor.command.adapters.quota_contracts import NativeQuotaReading, NativeQuotaWindow, QuotaPolicy


parse_claude = partial(parse_observation, policy=CLAUDE_QUOTA)
parse_codex = partial(parse_observation, policy=CODEX_QUOTA)
parse_deepseek_balance = partial(parse_observation, policy=DSH_QUOTA)
parse_grok = partial(parse_observation, policy=GROK_QUOTA)
parse_kimi = partial(parse_observation, policy=KIMI_QUOTA)


AT = datetime(2026, 9, 21, 12, tzinfo=timezone.utc)
RESET = AT + timedelta(hours=2)
AGE = timedelta(minutes=5)
SOURCE = QuotaSource(CODEX_QUOTA, "tested-version")


def account(vendor="openai", native="account-A"):
    policy = {"openai": CODEX_QUOTA, "anthropic": CLAUDE_QUOTA, "moonshot": KIMI_QUOTA,
              "xai": GROK_QUOTA, "deepseek": DSH_QUOTA}[vendor]
    return AccountIdentity.from_verified_native_id(policy, native, verified_by=policy.identity_source)


def codex(value=25, reset=RESET):
    return {"rateLimits": {"limitId": "codex", "primary": {
        "usedPercent": value, "resetsAt": None if reset is None else int(reset.timestamp()),
        "windowDurationMins": 300}}}


def parsed(value=25, at=AT, identity=None):
    return parse_codex(codex(value), account=identity or account(), version=SOURCE.version, observed_at=at)


def test_codex_multiple_limits_are_not_added_and_map_is_authoritative():
    body = codex(99)
    body["rateLimitsByLimitId"] = {
        "codex": {"limitId": "codex", "primary": {"usedPercent": 12, "resetsAt": int(RESET.timestamp())}},
        "spark": {"limitId": "spark", "secondary": {"usedPercent": 84, "windowDurationMins": 10080}},
    }
    value = parse_codex(body, account=account(), version="version", observed_at=AT)
    assert [(w.limit_id, w.used_percent, w.remaining_percent) for w in value.windows] == [
        ("codex", 12, 88), ("spark", 84, 16)]
    assert value.windows[0].duration_minutes is None
    assert value.windows[1].resets_at is None
    body["rateLimitsByLimitId"] = {}
    assert parse_codex(body, account=account(), version="version", observed_at=AT).state == "unavailable"


@pytest.mark.parametrize("value", [None, {}, {"primary": None}, {"primary": {"usedPercent": None, "resetsAt": None}}])
def test_codex_absent_numbers_are_unavailable_not_zero(value):
    observation = parse_codex({"rateLimits": value}, account=account(), version="v", observed_at=AT)
    assert observation.state == "unavailable" and observation.windows == ()


def test_known_reset_and_unknown_percent_remain_partial():
    value = parse_codex(codex(None), account=account(), version="v", observed_at=AT)
    assert value.state == "observed"
    assert value.windows[0].resets_at == RESET
    assert value.windows[0].remaining_percent is None
    assert value.as_dict()["windows"][0]["used_percent"] is None


@pytest.mark.parametrize("bad", [True, False, "25", -1, 101, float("inf"), float("nan"), 10**1000, [], {}])
def test_codex_invalid_percent_is_refused_without_raw_payload(bad):
    with pytest.raises(QuotaError, match="percentage"):
        parse_codex(codex(bad), account=account(), version="v", observed_at=AT)


@pytest.mark.parametrize("field,bad", [("resetsAt", True), ("resetsAt", "2000000000"),
                                     ("resetsAt", float("inf")), ("resetsAt", -1),
                                     ("resetsAt", 10**100), ("windowDurationMins", False),
                                     ("windowDurationMins", 0), ("windowDurationMins", "300")])
def test_codex_malformed_time_or_duration_is_refused(field, bad):
    body = codex()
    body["rateLimits"]["primary"][field] = bad
    with pytest.raises(QuotaError):
        parse_codex(body, account=account(), version="v", observed_at=AT)


@pytest.mark.parametrize("identity", ["different", "", 0, False])
def test_codex_invalid_or_conflicting_limit_identity_is_refused(identity):
    body = {"rateLimitsByLimitId": {"codex": {"limitId": identity, "primary": {"usedPercent": 20}}}}
    with pytest.raises(QuotaError):
        parse_codex(body, account=account(), version="v", observed_at=AT)


def test_claude_subscription_windows_do_not_turn_gateway_spend_into_quota():
    body = {"rate_limits": {"five_hour": {"used_percentage": 0, "resets_at": int(RESET.timestamp())},
                            "seven_day": None, "spend_limit": {"used_percentage": 150}},
            "private": "DO-NOT-PUBLISH"}
    value = parse_claude(body, account=account("anthropic"), version="v", observed_at=AT)
    assert len(value.windows) == 1 and value.windows[0].remaining_percent == 100
    assert value.windows[0].duration_minutes == 300
    assert "DO-NOT-PUBLISH" not in json.dumps(value.as_dict())
    assert parse_claude({}, account=account("anthropic"), version="v", observed_at=AT).state == "unavailable"


def kimi(usages):
    return {"code": 0, "data": {"kind": "ok", "quota": {"usages": usages}}}


def test_kimi_actual_windows_and_rfc3339_reset():
    value = parse_kimi(kimi({"limit5h": {"usedRatio": 0.2, "resetAt": "2026-09-21T17:00:00+03:00"},
                             "monthTotal": {"usedRatio": 0.6}, "limit7d": None}),
                       account=account("moonshot"), version="v", observed_at=AT)
    assert [(w.window_id, w.used_percent) for w in value.windows] == [("limit5h", 20), ("monthTotal", 60)]
    assert value.windows[0].resets_at == RESET
    assert value.windows[1].duration_minutes is None and value.windows[1].resets_at is None


@pytest.mark.parametrize("body", [{"code": 0, "data": {"kind": "error", "message": "SECRET", "status": 401}},
                                 {"code": 40101, "msg": "SECRET"}])
def test_kimi_http_200_business_error_is_an_error_without_leaking_text(body):
    value = parse_kimi(body, account=account("moonshot"), version="v", observed_at=AT)
    assert value.state == "error" and value.windows == ()
    assert "SECRET" not in json.dumps(value.as_dict())


@pytest.mark.parametrize("body", [{"code": False, "data": {"kind": "ok"}},
                                 {"code": 0, "data": {"kind": "mystery"}},
                                 kimi({"limit5h": {"usedRatio": 1.1}}),
                                 kimi({"limit5h": {"usedRatio": True}}),
                                 kimi({"limit5h": {"usedRatio": float("nan")}}),
                                 kimi({"limit5h": {"resetAt": "2026-09-21T17:00:00"}})])
def test_kimi_malformed_payload_is_refused(body):
    with pytest.raises(QuotaError):
        parse_kimi(body, account=account("moonshot"), version="v", observed_at=AT)


def test_grok_shared_period_is_source_reported_and_money_is_not_quota():
    body = {"config": {"creditUsagePercent": 42.5, "currentPeriod": {
        "type": "USAGE_PERIOD_TYPE_WEEKLY", "start": "2026-09-14T14:00:00Z",
        "end": "2026-09-21T14:00:00Z"}, "productUsage": [{"usagePercent": 99}],
        "prepaidBalance": {"val": 1000}}}
    value = parse_grok(body, account=account("xai"), version="v", observed_at=AT)
    assert len(value.windows) == 1
    assert value.windows[0].used_percent == 42.5
    assert value.windows[0].resets_at == RESET and value.windows[0].duration_minutes == 10080
    legacy = {"config": {"monthlyLimit": {"val": 100}, "used": {"val": 50}, "prepaidBalance": {"val": 500}}}
    assert parse_grok(legacy, account=account("xai"), version="v", observed_at=AT).state == "unavailable"


@pytest.mark.parametrize("period", [{"type": "UNKNOWN"}, {"end": "tomorrow"},
                                   {"start": "2026-09-22T00:00:00Z", "end": "2026-09-21T00:00:00Z"}])
def test_grok_malformed_period_is_refused(period):
    with pytest.raises(QuotaError):
        parse_grok({"config": {"creditUsagePercent": 25, "currentPeriod": period}},
                   account=account("xai"), version="v", observed_at=AT)


def test_contract_requires_confirmed_identity_and_matching_source():
    with pytest.raises(QuotaError):
        AccountIdentity.from_verified_native_id(CODEX_QUOTA, "alias", verified_by="operator-alias")
    with pytest.raises(QuotaError):
        parse_codex(codex(), account=account("anthropic"), version="v", observed_at=AT)
    with pytest.raises(QuotaError):
        parsed(at=AT.replace(tzinfo=None))
    assert account(native="A") != account(native="a")
    assert "account-A" not in json.dumps(parsed().as_dict())


def test_contract_rejects_duplicate_windows_and_noncanonical_values():
    window = QuotaWindow("codex", "primary", 30, RESET)
    with pytest.raises(QuotaError, match="duplicate"):
        QuotaObservation(account(), SOURCE, AT, "observed", (window, window))
    with pytest.raises(QuotaError):
        QuotaObservation(account(), SOURCE, AT, "error", reason="SECRET upstream body")
    with pytest.raises(QuotaError):
        QuotaObservation(account(), SOURCE, AT, "observed", [window])
    with pytest.raises(FrozenInstanceError):
        window.used_percent = 10


def test_shared_account_bindings_deduplicate_and_different_accounts_do_not():
    service = QuotaService()
    first = service.bind("planet-one", account(), SOURCE)
    service.bind("different-alias", account(), SOURCE)
    service.bind("planet-three", account(native="account-B"), SOURCE)
    assert service.publish(first, parsed(), now=AT)
    snapshots = service.snapshots(("planet-one", "different-alias", "planet-three", "not-bound"), now=AT, max_age=AGE)
    assert len(snapshots) == 3
    assert snapshots[0].binding_ids == ("planet-one", "different-alias")
    assert snapshots[0].observation.windows[0].used_percent == 25
    assert snapshots[1].freshness == snapshots[2].freshness == "missing"


def test_out_of_order_and_equal_time_conflicts_cannot_overwrite_latest():
    service = QuotaService()
    ticket = service.bind("agent", account(), SOURCE)
    assert service.publish(ticket, parsed(40), now=AT)
    assert not service.publish(ticket, parsed(10, AT - timedelta(seconds=1)), now=AT)
    assert not service.publish(ticket, parsed(10), now=AT)
    assert service.publish(ticket, parsed(40), now=AT)  # exact replay
    assert service.snapshot("agent", now=AT, max_age=AGE).observation.windows[0].used_percent == 40


def test_account_switch_and_a_b_a_reject_old_in_flight_tickets():
    service = QuotaService()
    old = service.bind("agent", account(), SOURCE)
    new = service.bind("agent", account(native="account-B"), SOURCE)
    assert not service.publish(old, parsed(), now=AT)
    assert service.snapshot("agent", now=AT, max_age=AGE).freshness == "missing"
    with pytest.raises(QuotaError):
        service.publish(new, parsed(), now=AT)
    current = service.bind("agent", account(), SOURCE)
    assert not service.publish(old, parsed(), now=AT)
    assert service.publish(current, parsed(60), now=AT)
    service.unbind("agent")
    assert not service.publish(current, parsed(70, AT + timedelta(seconds=1)), now=AT + timedelta(seconds=1))
    assert service.snapshot("agent", now=AT, max_age=AGE).account is None


def test_failure_replaces_older_success_and_reading_does_not_fabricate_recovery():
    service = QuotaService()
    ticket = service.bind("agent", account(), SOURCE)
    service.publish(ticket, parsed(), now=AT)
    failed_at = AT + timedelta(seconds=1)
    failure = failed_observation(account(), SOURCE, failed_at, "not_authenticated")
    assert service.publish(ticket, failure, now=failed_at)
    assert not service.publish(ticket, parsed(), now=failed_at)
    snapshot = service.snapshot("agent", now=failed_at, max_age=AGE)
    assert snapshot.observation.state == "error" and snapshot.observation.windows == ()
    assert service.snapshot("agent", now=failed_at + AGE, max_age=AGE).freshness == "stale"


def test_ttl_reset_and_clock_rollback_are_stale_without_resetting_usage():
    service = QuotaService()
    ticket = service.bind("agent", account(), SOURCE)
    service.publish(ticket, parsed(), now=AT)
    assert service.snapshot("agent", now=AT + AGE - timedelta(microseconds=1), max_age=AGE).freshness == "current"
    for now, age, word in ((AT + AGE, AGE, "stale"), (RESET, timedelta(days=1), "reset_passed"),
                           (AT - timedelta(seconds=1), AGE, "stale")):
        body = service.snapshot("agent", now=now, max_age=age).as_dict()
        assert body["freshness"] == "stale" and body["windows"][0]["freshness"] == word
        assert body["windows"][0]["used_percent"] == 25
    with pytest.raises(QuotaError):
        service.publish(ticket, parsed(at=AT + timedelta(seconds=1)), now=AT)


def test_cache_reconstructs_input_and_snapshot_values_and_returns_detached_json():
    service = QuotaService()
    ticket = service.bind("agent", account(), SOURCE)
    observation = parsed()
    service.publish(ticket, observation, now=AT)
    object.__setattr__(observation.windows[0], "used_percent", 99)
    snapshot = service.snapshot("agent", now=AT, max_age=AGE)
    assert snapshot.observation.windows[0].used_percent == 25
    object.__setattr__(snapshot.observation.windows[0], "used_percent", 80)
    body = service.snapshot("agent", now=AT, max_age=AGE).as_dict()
    body["windows"][0]["used_percent"] = 70
    assert service.snapshot("agent", now=AT, max_age=AGE).observation.windows[0].used_percent == 25
    object.__setattr__(observation.windows[0], "used_percent", float("nan"))
    with pytest.raises(QuotaError):
        service.publish(ticket, observation, now=AT)


@pytest.mark.parametrize("age", [timedelta(0), timedelta(seconds=-1), 300, None])
def test_invalid_freshness_interval_is_refused(age):
    with pytest.raises(QuotaError):
        QuotaService().snapshot("agent", now=AT, max_age=age)


def deepseek(total="110.00", available=True):
    return {"is_available": available, "balance_infos": [{"currency": "CNY", "total_balance": total,
             "granted_balance": "10.00", "topped_up_balance": "100.00"}]}


def test_deepseek_balance_preserves_decimal_precision_and_has_no_quota_or_reset():
    exact = "123456789012345678901234567890.12345678901234567890"
    observation = parse_deepseek_balance(deepseek(exact, False), account=account("deepseek"),
                                         version="api-v1", observed_at=AT)
    body = observation.as_dict()
    assert body["balances"][0]["total_balance"] == exact
    assert body["is_available"] is False  # do not derive availability from money
    assert body["reset_applicability"] == "not_applicable" and body["resets_at"] is None
    assert body["windows"] == [] and "percent" not in json.dumps(body)


@pytest.mark.parametrize("bad", [None, 10, 1.1, True, "NaN", "Infinity", "-1.00", "+1", "1e3", "1,50", " 1.00", "١٢", "1."])
def test_deepseek_rejects_malformed_decimal_without_float_coercion(bad):
    with pytest.raises(QuotaError):
        parse_deepseek_balance(deepseek(bad), account=account("deepseek"), version="v1", observed_at=AT)


@pytest.mark.parametrize("body", [deepseek(available=None), deepseek(available=1), {"is_available": True},
                                 {"is_available": True, "balance_infos": []},
                                 {"is_available": True, "balance_infos": deepseek()["balance_infos"] * 2}])
def test_deepseek_missing_availability_or_duplicate_currency_is_refused(body):
    with pytest.raises(QuotaError):
        parse_deepseek_balance(body, account=account("deepseek"), version="v1", observed_at=AT)


def test_balance_service_deduplicates_and_marks_stale_without_changing_money():
    source = QuotaSource(DSH_QUOTA, "api-v1")
    identity = account("deepseek")
    service = QuotaService()
    first = service.bind("dsh-one", identity, source)
    service.bind("dsh-two", identity, source)
    missing = service.snapshot("dsh-one", now=AT, max_age=AGE).as_dict()
    assert missing["is_available"] is None and missing["reset_applicability"] == "not_applicable"
    observation = parse_deepseek_balance(deepseek(), account=identity, version="api-v1", observed_at=AT)
    assert service.publish(first, observation, now=AT)
    object.__setattr__(observation.balances[0], "total_balance", "999.00")
    values = service.snapshots(("dsh-one", "dsh-two"), now=AT + AGE, max_age=AGE)
    assert len(values) == 1 and values[0].freshness == "stale"
    assert values[0].as_dict()["balances"][0]["total_balance"] == "110.00"
    failure_time = AT + timedelta(seconds=1)
    assert service.publish(first, failed_balance_observation(identity, source, failure_time), now=failure_time)
    failure = service.snapshot("dsh-one", now=failure_time, max_age=AGE).as_dict()
    assert failure["state"] == "error" and failure["balances"] == [] and failure["is_available"] is None


def test_balance_currency_and_observation_kind_are_not_inferred():
    with pytest.raises(QuotaError):
        BalanceObservation(account("deepseek"), QuotaSource(DSH_QUOTA, "v1"), AT,
                           "observed", (BalanceAmount("EUR", "1", "0", "1"),), True)
    with pytest.raises(QuotaError):
        QuotaObservation(account("deepseek"), QuotaSource(DSH_QUOTA, "v1"), AT, "unavailable", reason="no_data")


def test_provider_unknown_to_the_core_supplies_its_own_policy_without_a_registry_edit():
    def native(payload):
        return NativeQuotaReading((NativeQuotaWindow("shared", "daily", payload["usage"],
                                                      payload["reset"], 1440),), policy=policy)
    policy = QuotaPolicy("new-vendor", "native-account-read", "new-native-source", "quota", "unix", native)
    identity = AccountIdentity.from_verified_native_id(policy, "native-A", verified_by="native-account-read")
    source = QuotaSource(policy, "v1")
    service = QuotaService()
    ticket = service.bind("new-participant", identity, source)
    value = parse_observation({"usage": 19, "reset": int(RESET.timestamp())}, policy=policy,
                              account=identity, version="v1", observed_at=AT)
    assert service.publish(ticket, value, now=AT)
    snapshot = service.snapshot("new-participant", now=AT, max_age=AGE).as_dict()
    assert snapshot["source"] == {"kind": "new-native-source", "version": "v1"}
    assert snapshot["windows"][0]["remaining_percent"] == 81
    assert snapshot["windows"][0]["resets_at"] == "2026-09-21T14:00:00Z"


@pytest.mark.parametrize("field,value", [("used_percent", float("nan")), ("resets_at", True),
                                        ("duration_minutes", 0), ("limit_id", ""), ("window_id", [])])
def test_native_frozen_results_are_revalidated_after_the_provider_parser(field, value):
    row = NativeQuotaWindow("shared", "primary", 20, int(RESET.timestamp()), 300)
    object.__setattr__(row, field, value)
    policy = QuotaPolicy("new-vendor", "native-account-read", "new-native-source", "quota", "unix",
                         lambda payload: NativeQuotaReading((row,), policy=policy))
    identity = AccountIdentity.from_verified_native_id(policy, "native-A", verified_by="native-account-read")
    with pytest.raises(QuotaError):
        parse_observation({}, policy=policy, account=identity, version="v1", observed_at=AT)


def test_policy_copies_cannot_change_a_previously_bound_source_or_account():
    policy = QuotaPolicy("new-vendor", "native-account-read", "new-native-source", "quota", "unix",
                         lambda payload: NativeQuotaReading(policy=policy))
    identity = AccountIdentity.from_verified_native_id(policy, "native-A", verified_by="native-account-read")
    source = QuotaSource(policy, "v1")
    service = QuotaService()
    service.bind("participant", identity, source)
    object.__setattr__(policy, "vendor", "changed-vendor")
    object.__setattr__(source.policy, "source_kind", "changed-source")
    object.__setattr__(identity.policy, "identity_source", "changed-proof")
    snapshot = service.snapshot("participant", now=AT, max_age=AGE)
    assert snapshot.account.vendor == "new-vendor"
    assert snapshot.account.verified_by == "native-account-read"
    assert snapshot.source.kind == "new-native-source"


def test_renaming_a_source_policy_cannot_relabel_a_different_native_parser():
    renamed = replace(CODEX_QUOTA, vendor=KIMI_QUOTA.vendor,
                      identity_source=KIMI_QUOTA.identity_source,
                      source_kind=KIMI_QUOTA.source_kind,
                      timestamp_format=KIMI_QUOTA.timestamp_format)
    with pytest.raises(QuotaError, match="native parser and declared source policy differ"):
        parse_observation(codex(), policy=renamed, account=account("moonshot"),
                          version="v1", observed_at=AT)
