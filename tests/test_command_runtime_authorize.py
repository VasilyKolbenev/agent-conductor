"""Confirm authorization (A/CONF-1): refuse before preparation, else record it.

`ControlRuntime.authorize` takes a fresh Human `Confirmation` for one stored
proposal and holds every fact it restates against the run's own durable state --
the canonical preview digest, scope, capability, and frozen config -- plus the
confirmation's freshness and the run's action and time budgets. ANY changed or
stale fact refuses before the adapter is prepared and before one byte is written;
only a clean confirmation mints and records the authorized request.

The refusing paths are relations, not word-matches: each test builds the two
sides of the disagreement from separate sources -- a second proposal's own
contract-derived digest, a scope the test names itself -- and asserts they truly
differ before it asks authorize to refuse them. Every refusal also carries a
before/after record count, so a refusal that quietly wrote something would fail
on the state even if its message read right.

This module owns the shared builders the execute-state circuit imports; the two
files split a self-contained subject each and share no conftest.
"""
from __future__ import annotations

import pytest

from conductor.command.adapters import AdapterRegistry
from conductor.command.contracts import (
    ActionProposal,
    ActionRequest,
    ContractError,
    ControlMode,
)
from conductor.command.run_store import RecordConflict, RunStore, snapshot_digest
from conductor.command.runtime import (
    AttemptState,
    Authorization,
    AuthorizationError,
    Budget,
    Confirmation,
    ControlRuntime,
)

from tests.test_command_adapters import FakeAdapter
from tests.test_command_run_store import CONFIG, a_run

NOW = "2026-08-11T12:00:00Z"


# -- shared builders (also imported by the execute-state circuit) --

def fixed_clock(now=NOW):
    return lambda: now


def fixed_ids():
    return lambda purpose: f"{purpose}-fixed"


def counting_ids():
    """Distinct ids per call, so a second authorization mints a fresh action id."""
    counters: dict[str, int] = {}

    def ids(purpose):
        counters[purpose] = counters.get(purpose, 0) + 1
        return f"{purpose}-{counters[purpose]}"

    return ids


def a_store(tmp_path, *, mode="propose"):
    store = RunStore(tmp_path)
    store.create_run(a_run(mode=mode, config_digest=snapshot_digest(CONFIG)), CONFIG)
    return store


def a_proposal(store=None, **changes):
    values = {
        "proposal_id": "proposal-001",
        "run_id": "run-001",
        "attempt_id": "attempt-001",
        "instance_id": "claude-dev",
        "capability": "dispatch",
        "arguments": {"handoff": "packet-001"},
        "scope": ("src",),
        "proposed_by": "claude-dev",
        "proposed_at": NOW,
        "timeout_seconds": 900,
        "rationale": "The lane finished its handoff and asks to dispatch review.",
        "config_digest": snapshot_digest(CONFIG),
    }
    values.update(changes)
    proposal = ActionProposal(**values)
    if store is not None:
        store.append(proposal)
    return proposal


def a_confirmation(proposal, **changes):
    values = {
        "confirmation_id": "confirmation-001",
        "run_id": proposal.run_id,
        "proposal_id": proposal.proposal_id,
        "preview_digest": proposal.preview_digest,
        "capability": proposal.capability,
        "scope": tuple(proposal.scope),
        "config_digest": proposal.config_digest,
        "confirmed_by": "release-owner",
        "confirmed_at": NOW,
    }
    values.update(changes)
    return Confirmation(**values)


def a_budget(**changes):
    values = {
        "max_actions": 8,
        "max_action_seconds": 3600,
        "max_confirmation_age_seconds": 3600,
    }
    values.update(changes)
    return Budget(**values)


def a_runtime(store, *, clock=None, ids=None, adapters=None):
    registry = AdapterRegistry(adapters if adapters is not None else [FakeAdapter()])
    return ControlRuntime(store, registry, clock=clock or fixed_clock(), ids=ids or fixed_ids())


def action_requests(store, run_id="run-001"):
    return [row.value for row in store.read(run_id).records if row.kind == "action_request"]


# -- Confirmation and Budget validation at the boundary --

def test_a_confirmation_must_carry_the_confirm_mode(tmp_path):
    proposal = a_proposal()
    with pytest.raises(ContractError, match="confirm"):
        a_confirmation(proposal, mode="policy")


@pytest.mark.parametrize("field,value", [
    ("confirmation_id", "../x"),
    ("preview_digest", "sha256:not-hex"),
    ("config_digest", "deadbeef"),
    ("scope", ("../escape",)),
    ("confirmed_at", "2026-08-11 12:00:00"),
])
def test_a_confirmation_rejects_a_malformed_fact(field, value):
    proposal = a_proposal()
    with pytest.raises(ContractError):
        a_confirmation(proposal, **{field: value})


@pytest.mark.parametrize("field", [
    "max_actions", "max_action_seconds", "max_confirmation_age_seconds"])
def test_a_budget_below_one_is_refused(field):
    with pytest.raises(ContractError, match=field):
        a_budget(**{field: 0})


# -- positive path: a clean confirmation records the authorized request --

def test_a_clean_confirmation_records_the_request_separately_from_any_result(tmp_path):
    store = a_store(tmp_path)
    proposal = a_proposal(store)
    runtime = a_runtime(store)
    before = store.read("run-001").records
    assert [row.kind for row in before] == ["action_proposal"]  # no request yet

    authorization = runtime.authorize(a_confirmation(proposal), budget=a_budget())

    assert isinstance(authorization, Authorization)
    assert authorization.state is AttemptState.ACCEPTED
    request = authorization.request
    assert isinstance(request, ActionRequest)
    # The request IS the recorded confirmation: it carries the confirming human,
    # the freshness instant, and the exact confirmed digest.
    assert request.requested_by == "release-owner"
    assert request.requested_at == NOW
    assert request.preview_digest == proposal.preview_digest
    assert request.mode is ControlMode.CONFIRM
    after = store.read("run-001").records
    # It landed as its own record beside the proposal, and no result exists.
    assert [row.kind for row in after] == ["action_proposal", "action_request"]
    assert after[1].value == request


def test_an_identical_confirmation_replayed_adds_no_second_request(tmp_path):
    store = a_store(tmp_path)
    proposal = a_proposal(store)
    runtime = a_runtime(store)  # fixed ids: the same action id both times
    first = runtime.authorize(a_confirmation(proposal), budget=a_budget())
    second = runtime.authorize(a_confirmation(proposal), budget=a_budget())
    assert first.request == second.request
    assert len(action_requests(store)) == 1


def test_authorize_refuses_a_confirmation_for_a_proposal_the_run_never_held(tmp_path):
    store = a_store(tmp_path)
    proposal = a_proposal()  # built but NOT stored
    runtime = a_runtime(store)
    with pytest.raises(AuthorizationError, match="proposal-001"):
        runtime.authorize(a_confirmation(proposal), budget=a_budget())
    assert action_requests(store) == []


# -- refusing paths: every changed or stale fact refuses before preparation --

def test_a_changed_preview_digest_is_refused_and_nothing_is_authorized(tmp_path):
    # SABOTAGE (changed preview digest refused). The two digests are computed by
    # the contract from two different proposal bodies -- the witness the test holds
    # independently of authorize -- so the refusal is a real relation, not a word.
    store = a_store(tmp_path)
    proposal = a_proposal(store)
    tampered = a_proposal(arguments={"handoff": "a-different-packet"})
    assert tampered.preview_digest != proposal.preview_digest
    confirmation = a_confirmation(proposal, preview_digest=tampered.preview_digest)
    runtime = a_runtime(store)
    with pytest.raises(AuthorizationError, match="preview digest"):
        runtime.authorize(confirmation, budget=a_budget())
    assert action_requests(store) == []


def test_direct_authorize_refuses_a_hard_linked_journal_before_append(tmp_path):
    store = a_store(tmp_path)
    proposal = a_proposal(store)
    journal = store.run_path("run-001") / "records.jsonl"
    alias = tmp_path / "outside-authorize-journal.jsonl"
    try:
        import os
        os.link(journal, alias)
    except OSError as e:
        pytest.skip(f"hard links unavailable: {e}")
    before = alias.read_bytes()
    runtime = a_runtime(store)
    with pytest.raises(AuthorizationError, match="hard links"):
        runtime.authorize(a_confirmation(proposal), budget=a_budget())
    assert alias.read_bytes() == before and journal.read_bytes() == before
    assert action_requests(store) == []


def test_a_confirmation_older_than_the_freshness_budget_is_refused(tmp_path):
    # SABOTAGE (stale confirmation refused). now and confirmed_at are set by the
    # test, an hour apart; a ten-minute budget refuses it, a two-hour one would not.
    store = a_store(tmp_path)
    proposal = a_proposal(store)
    confirmation = a_confirmation(proposal, confirmed_at="2026-08-11T11:00:00Z")
    runtime = a_runtime(store, clock=fixed_clock("2026-08-11T12:00:00Z"))
    with pytest.raises(AuthorizationError, match="stale"):
        runtime.authorize(confirmation, budget=a_budget(max_confirmation_age_seconds=600))
    assert action_requests(store) == []
    # The same confirmation inside a wider window authorizes: the guard tracks the
    # age relation, not a fixed timestamp.
    ok = runtime.authorize(confirmation, budget=a_budget(max_confirmation_age_seconds=7200))
    assert ok.request.requested_at == "2026-08-11T11:00:00Z"


def test_a_confirmation_dated_in_the_future_of_the_clock_is_refused(tmp_path):
    store = a_store(tmp_path)
    proposal = a_proposal(store)
    confirmation = a_confirmation(proposal, confirmed_at="2026-08-11T13:00:00Z")
    runtime = a_runtime(store, clock=fixed_clock("2026-08-11T12:00:00Z"))
    with pytest.raises(AuthorizationError, match="future"):
        runtime.authorize(confirmation, budget=a_budget())
    assert action_requests(store) == []


def test_a_changed_scope_is_refused(tmp_path):
    store = a_store(tmp_path)
    proposal = a_proposal(store)  # scope ('src',)
    confirmation = a_confirmation(proposal, scope=("docs",))
    assert tuple(confirmation.scope) != tuple(proposal.scope)
    runtime = a_runtime(store)
    with pytest.raises(AuthorizationError, match="scope"):
        runtime.authorize(confirmation, budget=a_budget())
    assert action_requests(store) == []


def test_a_changed_capability_is_refused(tmp_path):
    store = a_store(tmp_path)
    proposal = a_proposal(store)  # capability 'dispatch'
    confirmation = a_confirmation(proposal, capability="review")
    assert confirmation.capability != proposal.capability
    runtime = a_runtime(store)
    with pytest.raises(AuthorizationError, match="capability"):
        runtime.authorize(confirmation, budget=a_budget())
    assert action_requests(store) == []


def test_a_confirmed_config_digest_that_is_not_the_runs_is_refused(tmp_path):
    store = a_store(tmp_path)
    proposal = a_proposal(store)
    foreign = snapshot_digest({"cycle": {"id": "other"}, "instances": []})
    assert foreign != store.read("run-001").envelope.config_digest
    confirmation = a_confirmation(proposal, config_digest=foreign)
    runtime = a_runtime(store)
    with pytest.raises(AuthorizationError, match="frozen config"):
        runtime.authorize(confirmation, budget=a_budget())
    assert action_requests(store) == []


def test_the_action_budget_refuses_one_more_than_it_allows(tmp_path):
    store = a_store(tmp_path)
    proposal = a_proposal(store)
    runtime = a_runtime(store, ids=counting_ids())
    # A one-action budget authorizes the first and refuses the second, which mints
    # a fresh action id (counting ids) rather than an idempotent retry.
    runtime.authorize(a_confirmation(proposal), budget=a_budget(max_actions=1))
    assert len(action_requests(store)) == 1
    other = a_proposal(
        store, proposal_id="proposal-002", attempt_id="attempt-002",
        arguments={"handoff": "packet-002"})
    with pytest.raises(AuthorizationError, match="action budget"):
        runtime.authorize(a_confirmation(other), budget=a_budget(max_actions=1))
    assert len(action_requests(store)) == 1


def test_an_identical_retry_is_not_a_new_action_at_the_budget_limit(tmp_path):
    store = a_store(tmp_path)
    proposal = a_proposal(store)
    runtime = a_runtime(store)
    first = runtime.authorize(a_confirmation(proposal), budget=a_budget(max_actions=1))
    second = runtime.authorize(a_confirmation(proposal), budget=a_budget(max_actions=1))
    assert second.request == first.request
    assert len(action_requests(store)) == 1


def test_the_time_budget_refuses_a_proposal_that_asks_for_longer(tmp_path):
    store = a_store(tmp_path)
    proposal = a_proposal(store, timeout_seconds=900)
    runtime = a_runtime(store)
    with pytest.raises(AuthorizationError, match="time budget"):
        runtime.authorize(a_confirmation(proposal), budget=a_budget(max_action_seconds=600))
    assert action_requests(store) == []
    # A budget wide enough for the proposal authorizes it.
    ok = runtime.authorize(a_confirmation(proposal), budget=a_budget(max_action_seconds=900))
    assert ok.request.timeout_seconds == 900


# -- SABOTAGE (duplicate idempotency refused): no second durable effect --

def test_a_replayed_confirmation_reuses_the_durable_idempotent_request(tmp_path):
    store = a_store(tmp_path)
    proposal = a_proposal(store)
    runtime = a_runtime(store, ids=counting_ids())
    first = runtime.authorize(a_confirmation(proposal), budget=a_budget())
    assert len(action_requests(store)) == 1
    # The durable idempotency key is consulted before minting a new action id.
    second = runtime.authorize(
        a_confirmation(proposal, confirmation_id="confirmation-002"),
        budget=a_budget())
    remaining = action_requests(store)
    assert len(remaining) == 1 and remaining[0] == first.request
    assert second.request == first.request
