"""The exported deep-adapter seams under hostile subclasses and post-mutation.

The registry reconstructs every contract value before the Confirm runtime hands
one to an adapter, so nothing proven here is reachable along that path.  But
``prepare``, ``execute``, and ``verify`` are exported: anything that resolves an
adapter calls them directly, and a frozen dataclass is frozen only against
attribute assignment -- ``object.__setattr__`` rewrites one in place, and a
subclass answers ``as_dict`` with whatever it likes.

So each seam rebuilds the exact base contract value BEFORE it reads a single
field, and that rebuild has two honest halves.  A value whose *text* is honest
survives it and is answered normally: only the hostile ``__hash__``, ``__eq__``,
or ``__ne__`` is left behind, and a lie told through comparison buys nothing.  A
value that cannot be rebuilt at all is refused with the module's fixed error,
and neither the vendor's secret nor the raw exception type may survive anywhere
in that refusal's exception graph.
"""
from __future__ import annotations

import pytest

from conductor.command.adapters import (
    AdapterContractError,
    ClaudeCodeAdapter,
    CodexAdapter,
    PreparedAction,
)
from conductor.command.adapters.deep_codecs import FakeClaudeCodec, FakeCodexCodec
from conductor.command.adapters.deep_evidence import AdapterEvidence
from conductor.command.contracts import ActionRequest, ActionResultReceipt

from tests.test_command_deep_adapters import (
    DIGEST,
    NOW,
    FakeExecutable,
    configured,
    process_outcome,
    request,
    result,
)


CAP_SECRET = "APIKEY_SECRET_CAP"
PAYLOAD_SECRET = "APIKEY_SECRET_PAYLOAD"
REQUEST_SECRET = "APIKEY_SECRET_REQUEST"
VERIFY_SECRET = "APIKEY_SECRET_VERIFY"
#: The bound ids a receipt and its request are compared on.
IDENTITY_FIELDS = ("run_id", "action_id", "attempt_id", "instance_id")
CODEC = {ClaudeCodeAdapter: FakeClaudeCodec, CodexAdapter: FakeCodexCodec}
ADAPTER_ID = {ClaudeCodeAdapter: "claude-code", CodexAdapter: "codex"}
INSTANCE = {ClaudeCodeAdapter: "claude-dev", CodexAdapter: "codex-review"}


class HostileHash(str):
    """A capability whose hash is the vendor's own prose."""

    def __hash__(self):
        raise RuntimeError(CAP_SECRET)


class HostileEq(str):
    """An identity field whose equality is the vendor's own prose."""

    def __eq__(self, other):
        raise RuntimeError(VERIFY_SECRET)

    def __ne__(self, other):
        raise RuntimeError(VERIFY_SECRET)

    __hash__ = str.__hash__


class LyingEq(str):
    """An identity field that claims to equal whatever it is compared against."""

    def __eq__(self, other):
        return True

    def __ne__(self, other):
        return False

    __hash__ = str.__hash__


class Tagged(str):
    """A harmless subclass: it lies about nothing, but it is not the base value."""


class HostileRequest(ActionRequest):
    """A request that answers the seam with prose instead of its own values."""

    def as_dict(self):
        raise RuntimeError(REQUEST_SECRET)


class HostileReceipt(ActionResultReceipt):
    """A receipt that answers the seam with prose instead of its own values."""

    def as_dict(self):
        raise RuntimeError(VERIFY_SECRET)


class HostilePayload(dict):
    """A prepared payload whose iteration is the vendor's own prose."""

    def items(self):
        raise RuntimeError(PAYLOAD_SECRET)


def hostile_request() -> HostileRequest:
    """One hostile subclass carrying exactly one honest request's values."""
    honest = request()
    return HostileRequest(**{
        name: getattr(honest, name) for name in sorted(ActionRequest._FIELDS)})


def a_receipt(**changes) -> ActionResultReceipt:
    values = {
        "receipt_id": "deep-result-001", "action_id": "action-fixed",
        "run_id": "run-001", "attempt_id": "attempt-001",
        "instance_id": "claude-dev", "outcome": "succeeded",
        "observed_at": NOW, "evidence_refs": (), "detail": None, "exit_code": 0}
    values.update(changes)
    return ActionResultReceipt(**values)


def hostile_receipt() -> HostileReceipt:
    """One hostile subclass carrying exactly one honest receipt's values."""
    honest = a_receipt()
    return HostileReceipt(**{
        name: getattr(honest, name) for name in sorted(ActionResultReceipt._FIELDS)})


def an_evidence(action_id: str) -> AdapterEvidence:
    """One independent fact that would verify the request it is keyed by."""
    return AdapterEvidence(
        "evidence-001", "run-001", action_id, "attempt-001", "claude-dev",
        "claude-code", "result", "artifact-001", DIGEST, NOW, "verified", NOW)


def an_adapter(tmp_path, adapter_type=ClaudeCodeAdapter, *, evidence_source=None):
    """One configured adapter plus the runner that proves nothing was spawned."""
    runner = FakeExecutable(process_outcome(
        CODEC[adapter_type].encode_result(
            result(ADAPTER_ID[adapter_type], INSTANCE[adapter_type]))))
    adapter = configured(
        adapter_type, runner, tmp_path, evidence_source=evidence_source)
    return adapter, runner


def exception_graph(error: BaseException) -> str:
    """Render every exception reachable from one refusal by cause and context."""
    seen: list[BaseException] = []
    pending: list[BaseException | None] = [error]
    while pending:
        current = pending.pop()
        if current is None or any(current is row for row in seen):
            continue
        seen.append(current)
        pending += [current.__cause__, current.__context__]
    return repr([(type(row).__name__, row.args, str(row)) for row in seen])


def refused(call, secret: str) -> AdapterContractError:
    """The seam answers one fixed refusal carrying no secret and no vendor type."""
    with pytest.raises(AdapterContractError) as stopped:
        call()
    error = stopped.value
    assert error.__cause__ is None and error.__context__ is None
    graph = exception_graph(error)
    assert secret not in graph and "APIKEY" not in graph
    assert "RuntimeError" not in graph, "the raw exception type must not survive"
    return error


# -- prepare: the first field is read only after the rebuild --

@pytest.mark.parametrize("adapter_type", [ClaudeCodeAdapter, CodexAdapter])
def test_prepare_rebuilds_a_capability_rewritten_after_construction(
        tmp_path, adapter_type):
    """object.__setattr__ reaches a frozen field; its hash must never reach us."""
    adapter, runner = an_adapter(tmp_path, adapter_type)
    approved = request(ADAPTER_ID[adapter_type])
    object.__setattr__(approved, "capability", HostileHash("dispatch"))

    prepared = adapter.prepare(approved)

    assert prepared.adapter_payload["capability"] == "dispatch"
    assert type(prepared.request.capability) is str
    assert runner.specs == []


def test_prepare_refuses_a_hostile_request_subclass_without_asking_it_anything(tmp_path):
    adapter, runner = an_adapter(tmp_path)
    refused(lambda: adapter.prepare(hostile_request()), REQUEST_SECRET)
    assert runner.specs == []


def test_prepare_binds_exact_base_strings_not_the_callers_subclassed_ones(tmp_path):
    """A rebuild is a rebuild: a benign subclass is accepted and then left behind."""
    adapter, _ = an_adapter(tmp_path)
    approved = request()
    object.__setattr__(approved, "capability", Tagged("dispatch"))
    object.__setattr__(approved, "action_id", Tagged("action-fixed"))

    prepared = adapter.prepare(approved)

    assert prepared.request.capability == "dispatch"
    assert type(prepared.request.capability) is str
    assert type(prepared.request.action_id) is str


# -- execute: the prepared value is rebuilt whole, request and payload alike --

def test_execute_refuses_a_prepared_request_swapped_for_a_hostile_subclass(tmp_path):
    adapter, runner = an_adapter(tmp_path)
    prepared = adapter.prepare(request())
    object.__setattr__(prepared, "request", hostile_request())
    refused(lambda: adapter.execute(prepared), REQUEST_SECRET)
    assert runner.specs == []


def test_execute_refuses_an_adapter_payload_rewritten_after_construction(tmp_path):
    adapter, runner = an_adapter(tmp_path)
    prepared = adapter.prepare(request())
    object.__setattr__(
        prepared, "adapter_payload", HostilePayload(capability="dispatch"))
    refused(lambda: adapter.execute(prepared), PAYLOAD_SECRET)
    assert runner.specs == []


def test_execute_rebuilds_a_capability_rewritten_inside_its_prepared_request(tmp_path):
    """The honest text survives; only the hostile hash is left behind."""
    adapter, runner = an_adapter(tmp_path)
    prepared = adapter.prepare(request())
    object.__setattr__(prepared.request, "capability", HostileHash("dispatch"))

    receipt = adapter.execute(prepared)

    assert (receipt.outcome, receipt.exit_code) == ("succeeded", 0)
    assert len(runner.specs) == 1


def test_execute_refuses_a_prepared_action_that_only_claims_to_be_its_own(tmp_path):
    """A lying __ne__ on adapter_id must not spend another vendor's preparation."""
    adapter, runner = an_adapter(tmp_path)
    prepared = adapter.prepare(request())
    object.__setattr__(prepared, "adapter_id", LyingEq("codex"))
    with pytest.raises(AdapterContractError) as stopped:
        adapter.execute(prepared)
    assert stopped.value.__cause__ is None and stopped.value.__context__ is None
    assert runner.specs == []


def test_execute_refuses_a_prepared_action_that_is_not_the_base_value(tmp_path):
    adapter, runner = an_adapter(tmp_path)
    honest = adapter.prepare(request())
    hostile = type("Hostile", (PreparedAction,), {})(
        adapter_id=honest.adapter_id, request=honest.request,
        adapter_payload=dict(honest.adapter_payload))
    with pytest.raises(AdapterContractError) as stopped:
        adapter.execute(hostile)
    assert stopped.value.__cause__ is None and stopped.value.__context__ is None
    assert runner.specs == []


# -- verify: identity is compared only between two rebuilt values --

@pytest.mark.parametrize("field", IDENTITY_FIELDS)
def test_verify_rebuilds_a_receipt_identity_rewritten_after_construction(tmp_path, field):
    """A raising __eq__ on any bound id must not reach the identity comparison."""
    adapter, _ = an_adapter(tmp_path)
    receipt = a_receipt()
    object.__setattr__(receipt, field, HostileEq(getattr(receipt, field)))

    verification = adapter.verify(request(), receipt)

    assert verification.state == "unavailable"
    assert verification.evidence_refs == ()


@pytest.mark.parametrize("field", IDENTITY_FIELDS)
def test_verify_rebuilds_a_request_identity_rewritten_after_construction(tmp_path, field):
    adapter, _ = an_adapter(tmp_path)
    approved = request()
    object.__setattr__(approved, field, HostileEq(getattr(approved, field)))

    verification = adapter.verify(approved, a_receipt())

    assert verification.state == "unavailable"
    assert verification.evidence_refs == ()


def test_verify_refuses_a_hostile_receipt_subclass_without_asking_it_anything(tmp_path):
    adapter, _ = an_adapter(tmp_path)
    refused(lambda: adapter.verify(request(), hostile_receipt()), VERIFY_SECRET)


def test_verify_never_verifies_a_receipt_whose_identity_only_claims_to_match(tmp_path):
    """A lying __eq__ must not turn a foreign receipt into a verified action."""
    adapter, _ = an_adapter(tmp_path, evidence_source=an_evidence)
    receipt = a_receipt()
    object.__setattr__(receipt, "action_id", LyingEq("action-foreign"))

    verification = adapter.verify(request(), receipt)

    assert verification.state == "mismatch"
    assert verification.evidence_refs == ()


def test_verify_reports_exact_base_identity_rebuilt_from_what_it_was_handed(tmp_path):
    adapter, _ = an_adapter(tmp_path)
    approved = request()
    object.__setattr__(approved, "action_id", Tagged("action-fixed"))

    verification = adapter.verify(approved, a_receipt())

    assert verification.state == "unavailable"
    assert verification.action_id == "action-fixed"
    assert type(verification.action_id) is str


# -- the honest path is unchanged by the contour --

@pytest.mark.parametrize("adapter_type", [ClaudeCodeAdapter, CodexAdapter])
def test_honest_values_still_prepare_execute_and_verify_unchanged(tmp_path, adapter_type):
    adapter, runner = an_adapter(tmp_path, adapter_type)
    approved = request(ADAPTER_ID[adapter_type])

    prepared = adapter.prepare(approved)
    receipt = adapter.execute(prepared)

    assert prepared.adapter_id == ADAPTER_ID[adapter_type]
    assert prepared.request == approved
    assert (receipt.outcome, receipt.exit_code) == ("succeeded", 0)
    assert adapter.verify(approved, receipt).state == "unavailable"
    assert len(runner.specs) == 1
