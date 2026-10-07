"""Reconcile: the one operator road that closes a request-only action.

`execute` refuses an action whose journal holds a durable `ActionRequest` and
nothing else. A restarted process holds no fresh effect authority, and the
refusal is right to be fail-closed. The state it left was the problem: the
action was neither resumable nor terminal, the refusal named "reconciliation",
and the product had no such operation anywhere -- no method, no CLI verb, no
route. The only escape was to delete the run directory, which is documented
nowhere and destroys the very facts the store exists to keep.

`ControlRuntime.reconcile` is that operation, and it is deliberately narrow. It
prepares nothing, executes nothing, verifies nothing, consults no adapter, and
appends exactly one terminal `unknown` receipt -- the only honest terminal for
an effect nobody observed. It can be safe at all only because the absence is
total: `_execute_granted` appends the `effect_lease` before it calls the execute
seam, so an action with no lease provably never reached a spawn. Every road that
carries its own recovery -- a lease, an observation, a terminal result already
written -- belongs to `execute`, and reconcile refuses those rather than become
a general terminal-stamping tool.

The refusal message is pinned here by CALLING the operation it names, never by
matching its words: a message may only promise what is really there.
"""
from __future__ import annotations

import re

import pytest

from conductor.command.contracts import ActionResultReceipt
from conductor.command.run_store import StoreError
from conductor.command.runtime import AttemptState, ControlRuntime, ExecutionError

from tests.test_command_runtime_authorize import a_store
from tests.test_command_runtime_execute import (
    ScriptedAdapter,
    VerifiedAdapter,
    a_runtime,
    authorized,
)
from tests.test_command_runtime_restart import an_event


def journal(store):
    return store.run_path("run-001") / "records.jsonl"


def kinds(store):
    return [row.kind for row in store.read("run-001").records]


def request_only(tmp_path):
    """A run whose journal holds the proposal and the request and nothing else.

    The execution grant lives in the runtime that authorized it, never in the
    journal, so a runtime built fresh over the same store IS the restarted
    process -- no crash simulation is needed to reach the stuck state.
    """
    store = a_store(tmp_path)
    _, authorization = authorized(store, ScriptedAdapter())
    assert kinds(store) == ["action_proposal", "action_request"]
    return store, authorization


def test_the_request_only_refusal_names_an_operation_that_can_close_the_action(tmp_path):
    """The message is held by calling what it names, not by matching its words.

    It used to promise "reconciliation" and the product had no reconciliation:
    the word occurred exactly once in the whole source tree, inside this very
    refusal. Reading the operation out of the message, resolving it on the class
    and closing the action with it fails three separate ways -- a message that
    names nothing, a name the class does not carry, and a name that carries
    something which cannot close the action.
    """
    store, authorization = request_only(tmp_path)
    adapter = ScriptedAdapter()
    with pytest.raises(ExecutionError) as refused:
        a_runtime(store, adapter).execute(authorization)
    named = re.findall(r"ControlRuntime\.(\w+)\(", str(refused.value))
    assert named, str(refused.value)
    operation = getattr(ControlRuntime, named[0])

    request = authorization.request
    attempt = operation(a_runtime(store, adapter), request.run_id, request.action_id)
    assert attempt.state is AttemptState.UNKNOWN
    assert adapter.prepare_calls == adapter.execute_calls == adapter.verify_calls == 0


def test_reconcile_closes_a_request_only_action_with_exactly_one_unknown_terminal(tmp_path):
    store, authorization = request_only(tmp_path)
    request = authorization.request
    # The one adapter in this suite that can reach `succeeded` is bound to the
    # instance and is never asked a thing; reconcile resolves nothing from it.
    adapter = VerifiedAdapter(store)
    attempt = a_runtime(store, adapter).reconcile(request.run_id, request.action_id)

    assert attempt.state is AttemptState.UNKNOWN
    assert attempt.history == (AttemptState.ACCEPTED, AttemptState.UNKNOWN)
    assert attempt.verification_evidence == ()
    receipt = attempt.receipt
    assert receipt.action_id == request.action_id and receipt.run_id == request.run_id
    assert receipt.attempt_id == request.attempt_id
    assert receipt.outcome == "unknown"
    assert receipt.exit_code is None
    assert receipt.evidence_refs == ()
    assert kinds(store) == ["action_proposal", "action_request", "action_result"]
    assert adapter.prepare_calls == adapter.execute_calls == adapter.verify_calls == 0


def test_a_second_reconcile_is_refused_and_leaves_the_journal_byte_identical(tmp_path):
    """Refused, not idempotent: the second call answers a question already answered.

    The store holds the same rule underneath, so this is two independent gates
    on one invariant -- the runtime refuses before it composes a receipt, and an
    append that reached the journal anyway would be refused there too.
    """
    store, authorization = request_only(tmp_path)
    request = authorization.request
    runtime = a_runtime(store, ScriptedAdapter())
    first = runtime.reconcile(request.run_id, request.action_id)
    before = journal(store).read_bytes()

    with pytest.raises(ExecutionError, match="already has a terminal result"):
        runtime.reconcile(request.run_id, request.action_id)
    assert journal(store).read_bytes() == before

    second = ActionResultReceipt.from_dict(
        {**first.receipt.as_dict(), "receipt_id": "result-hand-written"})
    with pytest.raises(StoreError, match="already has a terminal result"):
        store.append(second)
    assert journal(store).read_bytes() == before


@pytest.mark.parametrize("phases", [
    ("effect_lease",),
    ("effect_lease", "execution_observed"),
])
def test_reconcile_refuses_an_action_that_reached_a_durable_effect_boundary(tmp_path, phases):
    """The over-correction control: reconcile is not a terminal-stamping tool.

    A lease means an effect WAS authorized to start and may well have run, and
    an observation means one demonstrably did. Both roads already end in a
    terminal receipt through `execute` -- unknown for the first, the observed
    outcome put to verify for the second -- and neither may be short-circuited
    by an operator writing `unknown` over them.
    """
    store, authorization = request_only(tmp_path)
    request = authorization.request
    for phase in phases:
        store.append(an_event(request, phase))
    before = journal(store).read_bytes()

    adapter = VerifiedAdapter(store)
    with pytest.raises(ExecutionError, match="attempt event"):
        a_runtime(store, adapter).reconcile(request.run_id, request.action_id)
    assert journal(store).read_bytes() == before
    assert adapter.prepare_calls == adapter.execute_calls == adapter.verify_calls == 0


def test_reconcile_refuses_an_action_the_run_never_durably_requested(tmp_path):
    store, authorization = request_only(tmp_path)
    before = journal(store).read_bytes()
    with pytest.raises(ExecutionError, match="no durable request"):
        a_runtime(store, ScriptedAdapter()).reconcile("run-001", "action-nowhere")
    assert journal(store).read_bytes() == before


def test_reconcile_refuses_ids_that_are_not_contract_ids(tmp_path):
    """The one entry taking bare strings, so the ids are judged before any path.

    `execute` receives an `Authorization` whose request already passed the
    contract; an operator hands this two strings, and a run id that walks out of
    the store's route must not get as far as a route check to be caught.
    """
    store, authorization = request_only(tmp_path)
    runtime = a_runtime(store, ScriptedAdapter())
    before = journal(store).read_bytes()
    with pytest.raises(ExecutionError, match="run_id"):
        runtime.reconcile("../outside", authorization.request.action_id)
    with pytest.raises(ExecutionError, match="action_id"):
        runtime.reconcile("run-001", "../outside")
    assert journal(store).read_bytes() == before
    assert not (tmp_path.parent / "outside").exists()


def test_reconcile_refuses_a_run_whose_replay_left_unjudged_durable_bytes(tmp_path):
    """Repair belongs to the writer that owns the run, never to this operation.

    A crash tail is a repairable fact and reconcile is not the writer that may
    repair it; judging a request-only state from a prefix that is missing its
    own last line would be reading half a journal.
    """
    store, authorization = request_only(tmp_path)
    request = authorization.request
    with journal(store).open("ab") as stream:
        stream.write(b'{"record_type":"attempt_event"')
    before = journal(store).read_bytes()

    with pytest.raises(ExecutionError, match="unjudged durable bytes"):
        a_runtime(store, ScriptedAdapter()).reconcile(request.run_id, request.action_id)
    assert journal(store).read_bytes() == before


def test_reconcile_cannot_start_from_inside_a_store_transaction(tmp_path):
    store, authorization = request_only(tmp_path)
    request = authorization.request
    runtime = a_runtime(store, ScriptedAdapter())
    before = journal(store).read_bytes()
    with store.transaction():
        with pytest.raises(ExecutionError, match="inside a store transaction"):
            runtime.reconcile(request.run_id, request.action_id)
    assert journal(store).read_bytes() == before


def seed_request_only(store, request):
    return None


def seed_lease(store, request):
    store.append(an_event(request))


def seed_observed(store, request):
    store.append(an_event(request))
    store.append(an_event(request, "execution_observed"))


def seed_terminal(store, request):
    a_runtime(store, ScriptedAdapter()).reconcile(request.run_id, request.action_id)


@pytest.mark.parametrize("seed", [
    seed_request_only, seed_lease, seed_observed, seed_terminal,
], ids=lambda call: call.__name__.removeprefix("seed_"))
def test_reconcile_never_records_succeeded_whatever_the_journal_already_holds(tmp_path, seed):
    """Safety law 9 for this road: `unknown` is never promoted, on any input.

    The four seeds are every durable shape an action can stand in when someone
    reaches for this operation. Whatever it does -- close the action or refuse
    it -- no receipt in the run ever reads `succeeded`, and the adapter that
    could produce one is never consulted.
    """
    store, authorization = request_only(tmp_path)
    request = authorization.request
    seed(store, request)
    adapter = VerifiedAdapter(store)
    runtime = a_runtime(store, adapter)
    try:
        attempt = runtime.reconcile(request.run_id, request.action_id)
    except ExecutionError:
        pass
    else:
        assert attempt.state is AttemptState.UNKNOWN
        assert attempt.receipt.outcome == "unknown"
    outcomes = [
        row.value.outcome for row in store.read("run-001").records
        if row.kind == "action_result"]
    assert "succeeded" not in outcomes
    assert adapter.prepare_calls == adapter.execute_calls == adapter.verify_calls == 0


def test_execute_after_reconcile_replays_that_terminal_without_an_adapter_call(tmp_path):
    """The proof that the state is no longer stuck, said in execute's own words.

    Before reconcile existed, this authorization could only ever raise. Now the
    same call it used to refuse returns the durable terminal, byte for byte,
    through the ordinary replay road -- no grant, no adapter seam, no new byte.
    """
    store, authorization = request_only(tmp_path)
    request = authorization.request
    closed = a_runtime(store, ScriptedAdapter()).reconcile(
        request.run_id, request.action_id)
    before = journal(store).read_bytes()

    adapter = VerifiedAdapter(store)
    replayed = a_runtime(store, adapter).execute(authorization)
    assert replayed.receipt == closed.receipt
    assert replayed.receipt.as_dict() == closed.receipt.as_dict()
    assert replayed.state is AttemptState.UNKNOWN
    assert replayed.history == closed.history
    assert replayed.verification_evidence == ()
    assert adapter.prepare_calls == adapter.execute_calls == adapter.verify_calls == 0
    assert journal(store).read_bytes() == before
