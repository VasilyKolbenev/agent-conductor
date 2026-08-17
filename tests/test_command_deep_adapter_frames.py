"""Adapter-seam frame refusals, evidence states, durability, and the RT-2 pair.

The codec circuit next door proves the two fake protocols in isolation.  This
module proves the seam that consumes them: every malformed, cross-wired,
duplicated, truncated, or oversized frame must die inside the adapter as one
fixed refusal, and neither the raw bytes nor a parser exception graph may
survive it.

It then drives the two fake adapters through the real ControlRuntime to prove
the two durable properties an adapter-local test cannot reach: no raw stdout,
vendor prose, exception text, or runner secret ever becomes a durable byte, and
the RT-2 bracket holds -- the effect fires only after a durable lease, and a
restart resolves a lease-only attempt without repeating it.

PENDING, and not proven here because it does not exist: the real Claude Code and
real Codex CLI transport.  Every frame below is a reviewed fake-protocol frame
produced by the test's own codec, never a recording of a real vendor tool.
"""
from __future__ import annotations

import pytest

from conductor.command.adapters import (
    AdapterContractError,
    ClaudeCodeAdapter,
    CodexAdapter,
)
from conductor.command.adapters.deep_codecs import (
    MAX_FRAME_BYTES,
    FakeClaudeCodec,
    FakeCodexCodec,
)
from conductor.command.adapters.deep_contracts import AdapterFailure
from conductor.command.adapters.deep_evidence import (
    EVIDENCE_VERIFICATIONS,
    AdapterEvidence,
)
from conductor.command.runtime import AttemptState

from tests.test_command_deep_adapters import (
    ARGUMENTS,
    DIGEST,
    NOW,
    FakeExecutable,
    configured,
    process_outcome,
    request,
    result,
)
from tests.test_command_runtime_authorize import a_store
from tests.test_command_runtime_execute import a_runtime, authorized


SECRET = "APIKEY_SECRET"
OWN_CODEC = {ClaudeCodeAdapter: FakeClaudeCodec, CodexAdapter: FakeCodexCodec}
INSTANCE = {ClaudeCodeAdapter: "claude-dev", CodexAdapter: "codex-review"}
ADAPTER_ID = {ClaudeCodeAdapter: "claude-code", CodexAdapter: "codex"}

#: One envelope field per adapter that a foreign or malformed frame can carry.
ENVELOPE_SWAPS = {
    ClaudeCodeAdapter: (
        ("wrong vendor", b'"vendor":"fake-claude"', b'"vendor":"APIKEY_SECRET"'),
        ("wrong version", b'"version":1', b'"version":2'),
        ("non-integer version", b'"version":1', b'"version":"1"'),
        ("wrong frame kind", b'"frame":"result"', b'"frame":"APIKEY_SECRET"'),
    ),
    CodexAdapter: (
        ("wrong vendor", b'"source":"fake-codex"', b'"source":"APIKEY_SECRET"'),
        ("wrong version", b'"version":1', b'"version":2'),
        ("non-integer version", b'"version":1', b'"version":"1"'),
        ("wrong event kind", b'"kind":"completed"', b'"kind":"APIKEY_SECRET"'),
    ),
}
#: The first canonical key of each envelope, re-emitted to duplicate it.
DUPLICATE_HEADS = {
    ClaudeCodeAdapter: b'"frame":"result"',
    CodexAdapter: b'"event":{"kind":"APIKEY_SECRET"}',
}


def own_frame(adapter_type):
    """One valid frame of this adapter's own reviewed fake protocol."""
    adapter_id, instance = ADAPTER_ID[adapter_type], INSTANCE[adapter_type]
    return OWN_CODEC[adapter_type].encode_result(result(adapter_id, instance))


def swapped(frame: bytes, old: bytes, new: bytes) -> bytes:
    assert frame.count(old) == 1, f"the fixture assumed exactly one {old!r}"
    return frame.replace(old, new)


def frame_cases(adapter_type):
    """Every shape of wrong frame the seam must refuse identically."""
    frame = own_frame(adapter_type)
    foreign = {ClaudeCodeAdapter: CodexAdapter, CodexAdapter: ClaudeCodeAdapter}
    cases = [(name, swapped(frame, old, new))
             for name, old, new in ENVELOPE_SWAPS[adapter_type]]
    cases += [
        ("foreign vendor frame", own_frame(foreign[adapter_type])),
        ("duplicate key", b"{" + DUPLICATE_HEADS[adapter_type] + b"," + frame[1:]),
        ("duplicate frame", frame + frame),
        ("truncated frame", frame[: len(frame) // 2] + b"\n"),
        ("unterminated frame", frame[:-1]),
        ("empty frame", b""),
        ("oversized frame", frame[:-2] + b',"pad":"' + SECRET.encode() * 1400 + b'"}\n'),
        ("non-canonical frame", frame.replace(b'":', b'" :')),
        ("carriage return", frame[:-1] + b"\r\n"),
        ("raw vendor prose", b"APIKEY_SECRET the vendor says the run went fine\n"),
    ]
    return cases


def refusal_graph(stopped) -> str:
    value = stopped.value
    return repr((value, value.args, value.__cause__, value.__context__))


# -- Every wrong frame is one fixed refusal at the adapter seam --

@pytest.mark.parametrize("adapter_type", [ClaudeCodeAdapter, CodexAdapter])
def test_every_malformed_or_cross_wired_frame_is_the_same_seam_refusal(
        tmp_path, adapter_type):
    """Vendor, version, kind, duplicate, truncated, oversized -- one message, no graph."""
    cases = frame_cases(adapter_type)
    assert len(cases) == 14
    oversized = dict(cases)["oversized frame"]
    assert len(oversized) > MAX_FRAME_BYTES
    for name, frame in cases:
        runner = FakeExecutable(process_outcome(frame))
        adapter = configured(adapter_type, runner, tmp_path)
        with pytest.raises(AdapterContractError) as stopped:
            adapter.execute(adapter.prepare(request(ADAPTER_ID[adapter_type])))
        assert str(stopped.value) == "deep protocol result was refused", name
        assert stopped.value.__cause__ is None and stopped.value.__context__ is None
        assert SECRET not in refusal_graph(stopped), name


@pytest.mark.parametrize("adapter_type", [ClaudeCodeAdapter, CodexAdapter])
def test_the_matching_frame_of_the_same_fixture_still_succeeds(tmp_path, adapter_type):
    """The refusal matrix above is discriminating, not a blanket refusal."""
    runner = FakeExecutable(process_outcome(own_frame(adapter_type)))
    adapter = configured(adapter_type, runner, tmp_path)
    receipt = adapter.execute(adapter.prepare(request(ADAPTER_ID[adapter_type])))
    assert receipt.outcome == "succeeded"


# -- Independent evidence decides verification; nothing else does --

def an_evidence(**changes):
    values = {
        "evidence_id": "evidence-001", "run_id": "run-001",
        "action_id": "action-fixed", "attempt_id": "attempt-001",
        "instance_id": "claude-dev", "adapter_id": "claude-code",
        "kind": "result", "artifact_ref": "artifact-001", "digest": DIGEST,
        "observed_at": NOW, "verification": "verified", "verified_at": NOW,
    }
    values.update(changes)
    return AdapterEvidence(**values)


def verified_adapter(tmp_path, source):
    frame = FakeClaudeCodec.encode_result(result())
    return configured(
        ClaudeCodeAdapter, FakeExecutable(process_outcome(frame)), tmp_path,
        evidence_source=source)


@pytest.mark.parametrize("verification", sorted(EVIDENCE_VERIFICATIONS))
def test_each_independent_verification_state_is_reported_and_never_upgraded(
        tmp_path, verification):
    """Only an evidence value that says 'verified' produces a verified adapter state."""
    verified_at = NOW if verification == "verified" else None
    adapter = verified_adapter(tmp_path, lambda _action: an_evidence(
        verification=verification, verified_at=verified_at))
    approved = request()
    receipt = adapter.execute(adapter.prepare(approved))
    assert receipt.outcome == "succeeded" and receipt.exit_code == 0
    outcome = adapter.verify(approved, receipt)
    assert outcome.state == verification
    assert outcome.evidence_refs == (("evidence-001",) if verification == "verified" else ())


@pytest.mark.parametrize("field,foreign", [
    ("run_id", "run-foreign"), ("action_id", "action-foreign"),
    ("attempt_id", "attempt-foreign"), ("instance_id", "instance-foreign"),
    ("adapter_id", "codex"),
])
def test_evidence_naming_any_foreign_bound_id_verifies_nothing(tmp_path, field, foreign):
    adapter = verified_adapter(
        tmp_path, lambda _action: an_evidence(**{field: foreign}))
    approved = request()
    receipt = adapter.execute(adapter.prepare(approved))
    assert adapter.verify(approved, receipt).state == "mismatch"


class HostileEvidence(AdapterEvidence):
    """A supplied value that lies about itself only after construction."""

    def as_dict(self):
        values = dict(super().as_dict())
        values["action_id"] = "action-foreign"
        return values


def test_a_lying_or_post_mutated_evidence_value_is_re_derived_not_trusted(tmp_path):
    """The seam reads its own clone, so a supplied object's later story buys nothing."""
    lying = HostileEvidence(**{
        name: getattr(an_evidence(), name) for name in sorted(AdapterEvidence._FIELDS)})
    mutated = an_evidence(verification="error", verified_at=None)
    object.__setattr__(mutated, "verification", "verified")
    assert (mutated.verification, mutated.verified_at) == ("verified", None)
    approved = request()
    # The liar's clone names a foreign action; the post-mutated value cannot be
    # re-derived at all, because "verified" without a verified_at is not a value.
    for source, expected in ((lambda _a: lying, "mismatch"),
                             (lambda _a: mutated, "unavailable")):
        adapter = verified_adapter(tmp_path, source)
        receipt = adapter.execute(adapter.prepare(approved))
        assert adapter.verify(approved, receipt).state == expected


class VendorProseError(Exception):
    """A source failure whose type and message are both untrusted vendor prose."""


def test_a_missing_raising_or_foreign_typed_source_verifies_nothing_and_leaks_nothing(
        tmp_path):
    approved = request()
    sources = (
        None,
        lambda _a: None,
        lambda _a: (_ for _ in ()).throw(VendorProseError(f"{SECRET}_EXCEPTION")),
        lambda _a: "an independent fact, honest",
    )
    for source in sources:
        adapter = verified_adapter(tmp_path, source)
        receipt = adapter.execute(adapter.prepare(approved))
        outcome = adapter.verify(approved, receipt)
        assert outcome.state == "unavailable"
        assert outcome.detail == "" and outcome.evidence_refs == ()
        assert SECRET not in repr(outcome) and "VendorProseError" not in repr(outcome)


def test_a_reported_exit_code_never_reaches_the_evidence_source_at_all(tmp_path):
    """A non-success is unavailable without a lookup: exit codes do not prove effects."""
    asked: list[str] = []
    frame = FakeClaudeCodec.encode_result(result(
        outcome="failed", exit_code=7,
        failure=AdapterFailure("protocol_error", "execute", False)))
    adapter = configured(
        ClaudeCodeAdapter, FakeExecutable(process_outcome(frame)), tmp_path,
        evidence_source=lambda action: asked.append(action) or an_evidence())
    approved = request()
    receipt = adapter.execute(adapter.prepare(approved))
    assert (receipt.outcome, receipt.exit_code) == ("failed", 7)
    assert adapter.verify(approved, receipt).state == "unavailable"
    assert asked == []


# -- Nothing untrusted becomes a durable byte --

def durable_bytes(root) -> bytes:
    return b"".join(
        path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file())


class RaisingExecutable:
    """A runner whose failure is vendor prose in both its type and its message."""

    def __init__(self):
        self.specs: list[object] = []

    def run(self, spec):
        self.specs.append(spec)
        raise VendorProseError(f"{SECRET}_EXCEPTION at /home/vendor/session.json")


def a_deep_run(root, runner, *, evidence_source=None):
    root.mkdir(parents=True, exist_ok=True)
    store = a_store(root)
    adapter = configured(
        ClaudeCodeAdapter, runner, root, evidence_source=evidence_source)
    runtime, authorization = authorized(
        store, adapter, proposal_changes={
            "arguments": ARGUMENTS["dispatch"],
            "rationale": "Run one closed fake deep dispatch."})
    return store, runtime, authorization


@pytest.mark.parametrize("name,runner,expected", [
    ("success carries a secret runner token",
     lambda: FakeExecutable(process_outcome(
         FakeClaudeCodec.encode_result(result()), token=f"{SECRET}_TOKEN")),
     AttemptState.SUCCEEDED),
    ("a non-zero exit carries raw vendor stdout",
     lambda: FakeExecutable(process_outcome(
         f"{SECRET}_STDOUT vendor prose\n".encode(), exit_code=9)),
     AttemptState.FAILED),
    ("undecodable stdout is refused inside the adapter",
     lambda: FakeExecutable(process_outcome(f"{SECRET}_STDOUT\n".encode())),
     AttemptState.UNKNOWN),
    ("the runner itself raises vendor prose",
     RaisingExecutable, AttemptState.UNKNOWN),
])
def test_no_raw_output_prose_exception_or_secret_ever_becomes_durable(
        tmp_path, name, runner, expected):
    """The adapter's whole durable surface is a closed value set, so nothing leaks.

    The probe is not vacuous: the same scan finds the ids that are supposed to be
    durable.  The adapter-owned half of this claim -- that its own receipt carries
    no output either -- is guarded next door on the receipt itself.
    """
    made = runner()
    store, runtime, authorization = a_deep_run(tmp_path / "durable", made)

    attempt = runtime.execute(authorization)

    assert attempt.state is expected, name
    assert made.specs, "the fixture must actually have reached the runner"
    written = durable_bytes(store.run_path("run-001"))
    for present in (b'"action_result"', b"action-fixed", b"claude-code"):
        assert present in written, f"{name}: the probe never read the journal"
    for leak in (SECRET, "VendorProseError", "vendor prose", "session.json"):
        assert leak.encode() not in written, f"{name}: {leak} became durable"
        assert leak not in repr(attempt), f"{name}: {leak} survived in the attempt"
    assert attempt.receipt.evidence_refs == ()


def test_a_refused_frame_leaves_a_durable_unknown_and_no_decoded_vendor_value(tmp_path):
    """The one place raw bytes are read still records only a closed unknown."""
    frame = FakeCodexCodec.encode_result(result("claude-code", "claude-dev"))
    runner = FakeExecutable(process_outcome(frame, token=f"{SECRET}_TOKEN"))
    store, runtime, authorization = a_deep_run(tmp_path / "refused", runner)

    attempt = runtime.execute(authorization)

    assert attempt.state is AttemptState.UNKNOWN
    assert attempt.receipt.exit_code is None
    written = durable_bytes(store.run_path("run-001"))
    for leak in (SECRET, "fake-codex", "fake-codex-jsonl", "deep protocol result"):
        assert leak.encode() not in written, leak


# -- RT-2: one durable lease before the effect, and no repeat after a restart --

class JournalWatchingExecutable(FakeExecutable):
    """Snapshot the durable journal bytes at the exact moment of the effect."""

    def __init__(self, outcome, journal):
        super().__init__(outcome)
        self._journal = journal
        self.at_effect = b""

    def run(self, spec):
        self.at_effect = self._journal.read_bytes()
        return super().run(spec)


def test_the_effect_fires_only_after_its_lease_is_already_durable(tmp_path):
    root = tmp_path / "lease"
    root.mkdir()
    store = a_store(root)
    journal = store.run_path("run-001") / "records.jsonl"
    runner = JournalWatchingExecutable(
        process_outcome(FakeClaudeCodec.encode_result(result())), journal)
    adapter = configured(ClaudeCodeAdapter, runner, root)
    runtime, authorization = authorized(
        store, adapter, proposal_changes={
            "arguments": ARGUMENTS["dispatch"],
            "rationale": "Run one closed fake deep dispatch."})

    attempt = runtime.execute(authorization)

    assert attempt.state is AttemptState.SUCCEEDED and len(runner.specs) == 1
    assert b'"effect_lease"' in runner.at_effect, "the effect ran before its lease"
    assert b'"execution_observed"' not in runner.at_effect
    assert b'"action_result"' not in runner.at_effect
    final = journal.read_bytes()
    assert final.count(b'"effect_lease"') == 1
    assert final.count(b'"execution_observed"') == 1


class PowerCut(BaseException):
    """A crash between the durable lease and the durable observation."""


class CrashingExecutable(FakeExecutable):
    def run(self, spec):
        super().run(spec)
        raise PowerCut("the host died mid-effect")


def test_a_restart_resolves_a_lease_only_attempt_without_repeating_the_effect(tmp_path):
    root = tmp_path / "restart"
    root.mkdir()
    store = a_store(root)
    journal = store.run_path("run-001") / "records.jsonl"
    crashed = CrashingExecutable(
        process_outcome(FakeClaudeCodec.encode_result(result())))
    adapter = configured(ClaudeCodeAdapter, crashed, root)
    runtime, authorization = authorized(
        store, adapter, proposal_changes={
            "arguments": ARGUMENTS["dispatch"],
            "rationale": "Run one closed fake deep dispatch."})

    with pytest.raises(PowerCut):
        runtime.execute(authorization)

    crashed_journal = journal.read_bytes()
    assert crashed_journal.count(b'"effect_lease"') == 1
    assert b'"execution_observed"' not in crashed_journal
    assert b'"action_result"' not in crashed_journal
    assert len(crashed.specs) == 1

    for restart in range(2):
        fresh = FakeExecutable(
            process_outcome(FakeClaudeCodec.encode_result(result())))
        recovered = a_runtime(store, configured(ClaudeCodeAdapter, fresh, root))
        attempt = recovered.execute(authorization)
        assert attempt.state is AttemptState.UNKNOWN, restart
        assert attempt.receipt.exit_code is None and attempt.receipt.evidence_refs == ()
        assert fresh.specs == [], "a restart repeated the effect"
        assert len(crashed.specs) == 1
    replayed = journal.read_bytes()
    assert replayed.count(b'"effect_lease"') == 1
    assert replayed.count(b'"action_result"') == 1
