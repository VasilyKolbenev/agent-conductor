"""Unknown billing accounts stay explicit and separate from verified identity."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from uuid import UUID

import pytest

from conductor.command.adapters.codex_cli import QUOTA_POLICY as SUBSCRIPTION
from conductor.command.adapters.dsh_harness import QUOTA_POLICY as BALANCE
from conductor.command.adapters.quota_contracts import NativeQuotaReading, QuotaPolicy
from conductor.command.quota import (
    AccountIdentity, BalanceObservation, CredentialContext, QuotaError,
    QuotaObservation, QuotaSource, failed_balance_observation, parse_observation,
)
from conductor.command.quota_service import QuotaService


AT = datetime(2026, 9, 21, 12, tzinfo=timezone.utc)
AGE = timedelta(minutes=5)
SOURCE = QuotaSource(BALANCE, "test-native-version")


def observed(context, *, total="110.00", at=AT, version=SOURCE.version):
    payload = {"is_available": False, "balance_infos": [{"currency": "CNY",
        "total_balance": total, "granted_balance": "10.00", "topped_up_balance": "100.00"}]}
    return parse_observation(payload, policy=BALANCE, account=None,
                             connection=context, version=version, observed_at=at)


def snapshot(service, name="agent", *, now=AT):
    return service.snapshot(name, now=now, max_age=AGE).as_dict()


def test_random_context_handles_make_no_account_identity_claim():
    first, second = CredentialContext.create(BALANCE), CredentialContext.create(BALANCE)
    assert first.context_id != second.context_id
    assert UUID(first.context_id).version == 4
    exact = "123456789012345678901234567890.12345678901234567890"
    body = observed(first, total=exact).as_dict()
    assert body["account"] is None
    assert body["connection"] == {"kind": "credential_context", "context_id": first.context_id,
                                   "vendor": BALANCE.vendor, "account_status": "unknown"}
    assert "account_digest" not in json.dumps(body) and "verified_by" not in json.dumps(body)
    assert body["balances"][0]["total_balance"] == exact
    assert body["is_available"] is False and body["windows"] == []
    assert body["resets_at"] is None and body["reset_applicability"] == "not_applicable"


@pytest.mark.parametrize("bad", [None, True, "alias-secret", "a" * 64, "",
    "12345678-1234-1234-8234-123456789abc", "12345678-1234-4234-0234-123456789abc",
    "12345678-ABCD-4234-8234-123456789ABC"])
def test_context_handle_refuses_alias_hash_and_noncanonical_uuid_without_echo(bad):
    with pytest.raises(QuotaError, match="^invalid credential context handle$"):
        CredentialContext(BALANCE, bad)


def test_subscription_policy_cannot_acquire_a_credential_context_subject():
    with pytest.raises(QuotaError, match="monetary"):
        CredentialContext.create(SUBSCRIPTION)
    context = CredentialContext.create(BALANCE)
    source = QuotaSource(SUBSCRIPTION, "v1")
    with pytest.raises(QuotaError, match="source policy differ"):
        QuotaService().bind("agent", None, source, connection=context)
    with pytest.raises(QuotaError, match="source policy differ"):
        parse_observation({}, policy=SUBSCRIPTION, connection=context, version="v1", observed_at=AT)
    with pytest.raises(QuotaError):
        QuotaObservation(context, source, AT, "unavailable", reason="no_data")
    object.__setattr__(context, "policy", SUBSCRIPTION)
    with pytest.raises(QuotaError, match="monetary"):
        QuotaService().bind("agent", None, source, connection=context)


@pytest.mark.parametrize("mode", ["neither", "both", "mapping"])
def test_every_subject_entry_requires_exactly_one_trusted_subject(mode):
    context = CredentialContext.create(BALANCE)
    identity = AccountIdentity.from_verified_native_id(BALANCE, "native-account",
                                                       verified_by=BALANCE.identity_source)
    account = identity if mode == "both" else None
    connection = None if mode == "neither" else context if mode == "both" else context.as_dict()
    with pytest.raises(QuotaError):
        QuotaService().bind("agent", account, SOURCE, connection=connection)
    with pytest.raises(QuotaError):
        BalanceObservation(account, SOURCE, AT, "error", reason="no_data", connection=connection)
    with pytest.raises(QuotaError):
        parse_observation({}, policy=BALANCE, account=account, connection=connection,
                          version=SOURCE.version, observed_at=AT)


def test_missing_connection_balance_keeps_subject_and_never_invents_zero():
    context = CredentialContext.create(BALANCE)
    service = QuotaService()
    service.bind("agent", None, SOURCE, connection=context)
    body = snapshot(service)
    assert body["account"] is None and body["connection"]["context_id"] == context.context_id
    assert body["state"] == body["freshness"] == "missing"
    assert body["balances"] == [] and body["is_available"] is None
    assert body["resets_at"] is None and body["reset_applicability"] == "not_applicable"


def test_different_contexts_and_even_shared_handles_never_merge_or_share_samples():
    first, second = CredentialContext.create(BALANCE), CredentialContext.create(BALANCE)
    service = QuotaService()
    ticket = service.bind("one", None, SOURCE, connection=first)
    service.bind("two", None, SOURCE, connection=second)
    service.bind("same-handle", None, SOURCE, connection=first)
    assert service.publish(ticket, observed(first), now=AT)
    values = service.snapshots(("one", "two", "same-handle"), now=AT, max_age=AGE)
    assert [value.binding_ids for value in values] == [("one",), ("two",), ("same-handle",)]
    assert [value.freshness for value in values] == ["current", "missing", "missing"]
    second_ticket = service.bind("two", None, SOURCE, connection=second)
    assert service.publish(second_ticket, observed(second, total="220.00"), now=AT)
    assert snapshot(service, "one")["balances"][0]["total_balance"] == "110.00"
    assert snapshot(service, "two")["balances"][0]["total_balance"] == "220.00"


def test_a_b_a_rebind_rejects_late_replies_and_does_not_reveal_old_cached_success():
    first, second = CredentialContext.create(BALANCE), CredentialContext.create(BALANCE)
    service = QuotaService()
    old = service.bind("agent", None, SOURCE, connection=first)
    assert service.publish(old, observed(first), now=AT)
    middle = service.bind("agent", None, SOURCE, connection=second)
    assert service.publish(middle, observed(second, total="220.00"), now=AT)
    current = service.bind("agent", None, SOURCE, connection=first)
    assert snapshot(service)["state"] == "missing"
    assert not service.publish(old, observed(first), now=AT)
    assert not service.publish(middle, observed(second), now=AT)
    assert service.publish(current, observed(first, total="90.00"), now=AT)
    same = service.bind("agent", None, SOURCE, connection=first)
    assert same.generation > current.generation
    assert snapshot(service)["state"] == "missing"
    assert not service.publish(current, observed(first), now=AT)
    service.unbind("agent")
    assert not service.publish(same, observed(first), now=AT)
    assert "connection" not in snapshot(service)
    service.bind("agent", None, SOURCE, connection=first)
    assert snapshot(service)["state"] == "missing"


def test_invalid_rebind_does_not_discard_the_current_sample_or_invalidate_its_ticket():
    context = CredentialContext.create(BALANCE)
    service = QuotaService()
    ticket = service.bind("agent", None, SOURCE, connection=context)
    assert service.publish(ticket, observed(context), now=AT)
    with pytest.raises(QuotaError):
        service.bind("agent", None, QuotaSource(SUBSCRIPTION, "v1"), connection=context)
    with pytest.raises(QuotaError):
        service.bind("agent", None, SOURCE)
    assert snapshot(service)["balances"][0]["total_balance"] == "110.00"
    assert service.publish(ticket, observed(context, total="100.00", at=AT + timedelta(seconds=1)),
                           now=AT + timedelta(seconds=1))


def test_verified_account_group_and_unknown_connection_remain_distinct():
    context = CredentialContext.create(BALANCE)
    identity = AccountIdentity.from_verified_native_id(BALANCE, "native-account",
                                                       verified_by=BALANCE.identity_source)
    service = QuotaService()
    verified = service.bind("verified", identity, SOURCE)
    service.bind("same-account", identity, SOURCE)
    service.bind("unknown-account", None, SOURCE, connection=context)
    assert service.publish(verified, failed_balance_observation(identity, SOURCE, AT), now=AT)
    values = service.snapshots(("verified", "same-account", "unknown-account"), now=AT, max_age=AGE)
    assert [value.binding_ids for value in values] == [("verified", "same-account"), ("unknown-account",)]
    assert values[0].as_dict()["account"] is not None and "connection" not in values[0].as_dict()
    assert values[1].as_dict()["account"] is None and values[1].freshness == "missing"


def test_wrong_context_source_version_and_verified_account_cannot_publish_for_ticket():
    context = CredentialContext.create(BALANCE)
    service = QuotaService()
    ticket = service.bind("agent", None, SOURCE, connection=context)
    identity = AccountIdentity.from_verified_native_id(BALANCE, "native-account",
                                                       verified_by=BALANCE.identity_source)
    wrong = [observed(CredentialContext.create(BALANCE)), observed(context, version="other-version"),
             failed_balance_observation(identity, SOURCE, AT)]
    for value in wrong:
        with pytest.raises(QuotaError, match="does not match"):
            service.publish(ticket, value, now=AT)
    assert snapshot(service)["state"] == "missing"
    assert service.publish(ticket, observed(context), now=AT)
    next_source = QuotaSource(BALANCE, "other-version")
    fresh = service.bind("agent", None, next_source, connection=context)
    assert snapshot(service)["state"] == "missing"
    assert not service.publish(ticket, observed(context), now=AT)
    assert service.publish(fresh, observed(context, version=next_source.version), now=AT)


def test_error_replaces_success_and_older_or_equal_conflicting_samples_cannot_restore_it():
    context = CredentialContext.create(BALANCE)
    service = QuotaService()
    ticket = service.bind("agent", None, SOURCE, connection=context)
    assert service.publish(ticket, observed(context), now=AT)
    later = AT + timedelta(seconds=1)
    failure = failed_balance_observation(None, SOURCE, later, "not_authenticated", connection=context)
    assert service.publish(ticket, failure, now=later)
    assert service.publish(ticket, failure, now=later)
    assert not service.publish(ticket, observed(context), now=later)
    assert not service.publish(ticket, observed(context, at=later), now=later)
    body = snapshot(service, now=later)
    assert body["state"] == "error" and body["balances"] == [] and body["is_available"] is None
    assert body["account"] is None and body["connection"]["context_id"] == context.context_id
    with pytest.raises(QuotaError, match="future"):
        service.publish(ticket, observed(context, at=later + AGE), now=later)
    assert snapshot(service, now=later + AGE)["freshness"] == "stale"


def test_connection_balance_ttl_and_clock_rollback_retain_exact_facts():
    context = CredentialContext.create(BALANCE)
    service = QuotaService()
    ticket = service.bind("agent", None, SOURCE, connection=context)
    service.publish(ticket, observed(context, total="0.00000000000000001"), now=AT)
    assert snapshot(service, now=AT + AGE - timedelta(microseconds=1))["freshness"] == "current"
    for at in (AT + AGE, AT - timedelta(microseconds=1)):
        body = snapshot(service, now=at)
        assert body["freshness"] == "stale"
        assert body["balances"][0]["total_balance"] == "0.00000000000000001"
        assert body["is_available"] is False


def test_bound_and_published_contexts_are_copied_and_mutations_revalidated():
    context = CredentialContext.create(BALANCE)
    handle = context.context_id
    service = QuotaService()
    ticket = service.bind("agent", None, SOURCE, connection=context)
    value = observed(context)
    service.publish(ticket, value, now=AT)
    object.__setattr__(context, "context_id", "SECRET-alias")
    object.__setattr__(value.connection, "context_id", "SECRET-alias")
    with pytest.raises(QuotaError, match="^invalid credential context handle$"):
        service.publish(ticket, value, now=AT)
    detached = service.snapshot("agent", now=AT, max_age=AGE)
    object.__setattr__(detached.connection, "context_id", "SECRET-alias")
    assert snapshot(service)["connection"]["context_id"] == handle
    object.__setattr__(ticket.connection, "context_id", "SECRET-alias")
    with pytest.raises(QuotaError, match="^invalid credential context handle$"):
        service.publish(ticket, observed(CredentialContext(BALANCE, handle)), now=AT)
    assert "SECRET-alias" not in json.dumps(snapshot(service))


def test_context_policy_cannot_be_relabelled_around_the_native_balance_parser():
    renamed = replace(BALANCE, vendor="different-vendor", source_kind="different-source")
    context = CredentialContext.create(renamed)
    with pytest.raises(QuotaError, match="source policy differ"):
        QuotaService().bind("agent", None, SOURCE, connection=context)
    with pytest.raises(QuotaError, match="native parser and declared source policy differ"):
        parse_observation({"is_available": True, "balance_infos": [{"currency": "CNY",
            "total_balance": "1", "granted_balance": "0", "topped_up_balance": "1"}]},
            policy=renamed, connection=context, version="v1", observed_at=AT)


def test_native_business_failure_retains_connection_and_checks_parser_policy_stamp():
    def native(payload):
        return NativeQuotaReading(error=True, policy=policy)
    policy = QuotaPolicy("new-vendor", "native-account", "native-balance", "balance", "none",
                         native, ("USD",))
    context = CredentialContext.create(policy)
    body = parse_observation({"error": "SECRET upstream"}, policy=policy, connection=context,
                              version="v1", observed_at=AT).as_dict()
    assert body["account"] is None and body["connection"]["context_id"] == context.context_id
    assert body["state"] == "error" and body["balances"] == [] and body["is_available"] is None
    assert "SECRET" not in json.dumps(body)
    renamed = replace(policy, source_kind="other-native-balance")
    with pytest.raises(QuotaError, match="native parser and declared source policy differ"):
        parse_observation({}, policy=renamed, connection=CredentialContext.create(renamed),
                          version="v1", observed_at=AT)
