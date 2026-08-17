"""Deterministic gated providers, admitted through the session-1 provider door.

Every ALPHA-1 execution gate and every frozen UI-lane artifact is driven by these
fixtures, so the adapter the runtime drives is the one a real operator config
would produce: each class is catalogued, carries the exact per-capability
argument schemas, and implements the four lifecycle seams the door proves.

Nothing here spawns a process. The effect is a counter, and every ordering claim
a caller makes is held by a gate or a barrier this module owns -- never by a
sleep. ``execute`` and ``verify`` each announce their arrival and then wait on an
Event the caller opens, so "while the effect is still unfinished" is a fact, not
a timing hope.
"""
from __future__ import annotations

import threading

from conductor.command.adapters import (
    AdapterManifest,
    AdapterObservation,
    AdapterVerification,
    PreparedAction,
    ProviderCatalogEntry,
    ProviderConfig,
)
from conductor.command.adapters.deep_adapters import DEEP_CAPABILITIES, DEEP_CONTROLS
from conductor.command.contracts import ActionResultReceipt, EvidenceRef
from conductor.command.providers import resolve_providers
from conductor.command.run_store import RunStore, snapshot_digest

from tests.test_command_http_api import RUN_ID, proposal_body
from tests.test_command_run_store import CONFIG, a_run


#: One frozen instant for every fixture clock, so a derived artifact is stable.
NOW = "2026-08-17T12:00:00Z"
VENDOR = "ALPHA-1 fixture"
CLAUDE_PROTOCOL = "fake-claude-jsonl-v1"
CODEX_PROTOCOL = "fake-codex-jsonl-v1"
SCHEMA_PAIRS = tuple(sorted(
    (capability, "deep-arguments-v1") for capability in DEEP_CAPABILITIES))
LIFECYCLE = ("observe", "prepare", "execute", "verify")
#: A gate or barrier that is never opened must fail the test, not hang it.
WAIT_SECONDS = 10.0


class GatedProvider:
    """A fake provider whose effect is a counter, a gate, and an optional barrier.

    ``execute`` and ``verify`` announce arrival before waiting, so a caller can
    prove a thread is INSIDE a seam. Setting ``barrier`` makes ``execute`` wait
    on it, so two providers sharing one barrier are provably inside execute at
    the same instant or the barrier breaks and the attempt fails.
    """

    argument_schemas = {
        capability: "deep-arguments-v1" for capability in DEEP_CAPABILITIES}
    provider_id = "gated"
    display_name = "Gated fixture provider"

    def __init__(self, config, runner, *, clock, ids) -> None:
        self.manifest = AdapterManifest(
            adapter_id=type(self).provider_id,
            display_name=type(self).display_name, vendor=VENDOR,
            version="fake-protocol-v1", capabilities=DEEP_CONTROLS, docs_url="")
        self._config = config
        self._runner = runner
        self._clock = clock
        self._ids = ids
        #: Both gates start open; clear one to park every thread entering it.
        self.gates = {"execute": threading.Event(), "verify": threading.Event()}
        for gate in self.gates.values():
            gate.set()
        self.barrier: threading.Barrier | None = None
        #: The outcome execute reports; the runtime, not the fixture, resolves it.
        self.outcome = "succeeded"
        #: Test-only stand-in for the independent evidence writer: the adapter
        #: API returns refs only and receives neither a store nor append power.
        self.evidence_sink = None
        self.verifies_with_evidence = False
        self.executions = 0
        self.arrivals: list[tuple[str, str]] = []
        self.execute_threads: list[tuple[str, int]] = []
        self.held_transactions: list[tuple[str, bool]] = []
        self.claims: list[dict[str, object]] = []
        self._lock = threading.Lock()
        self._arrived = threading.Condition(self._lock)

    def _enter(self, seam: str, action_id: str) -> None:
        with self._arrived:
            self.arrivals.append((seam, action_id))
            self.held_transactions.append(
                (seam, RunStore.current_thread_holds_transaction()))
            self._arrived.notify_all()

    def wait_for(self, seam: str, action_id: str) -> bool:
        """Block until a thread is provably inside `seam` for `action_id`."""
        with self._arrived:
            return self._arrived.wait_for(
                lambda: (seam, action_id) in self.arrivals, WAIT_SECONDS)

    def observe(self, instance_id, run_id):
        self._enter("observe", run_id)
        return AdapterObservation(
            adapter_id=self.manifest.adapter_id, instance_id=instance_id,
            run_id=run_id, observed_at=self._clock(), health="unknown",
            available_capabilities=(), detail="the gated fixture probes nothing")

    def prepare(self, request):
        self._enter("prepare", request.action_id)
        return PreparedAction(
            adapter_id=self.manifest.adapter_id, request=request,
            adapter_payload={"work_item_id": request.arguments["work_item_id"]})

    def execute(self, prepared):
        """Perform the fixture's whole effect: count, announce, wait, report."""
        request = prepared.request
        with self._lock:
            self.executions += 1
            self.execute_threads.append(
                (request.action_id, threading.get_ident()))
        self._enter("execute", request.action_id)
        if self.barrier is not None:
            self.barrier.wait(WAIT_SECONDS)
        self.gates["execute"].wait(WAIT_SECONDS)
        receipt = ActionResultReceipt(
            receipt_id=self._ids("receipt"), action_id=request.action_id,
            run_id=request.run_id, attempt_id=request.attempt_id,
            instance_id=request.instance_id, outcome=self.outcome,
            observed_at=self._clock(), detail="the fixture completed its effect",
            exit_code=0 if self.outcome == "succeeded" else None)
        with self._lock:
            self.claims.append({
                "action_id": receipt.action_id, "instance_id": receipt.instance_id,
                "outcome": receipt.outcome, "exit_code": receipt.exit_code})
        return receipt

    def verify(self, request, result):
        """Either declare no verifier, or record one post-effect verified fact."""
        self._enter("verify", request.action_id)
        self.gates["verify"].wait(WAIT_SECONDS)
        if not self.verifies_with_evidence or self.evidence_sink is None:
            return AdapterVerification(
                adapter_id=self.manifest.adapter_id, action_id=request.action_id,
                state="unavailable", observed_at=self._clock(),
                detail="the fixture holds no independent check of its own effect",
                evidence_refs=())
        evidence = EvidenceRef(
            evidence_id=self._ids("evidence"), run_id=request.run_id,
            kind="verification", uri=f"verification/{request.action_id}",
            label="the fixture's own post-effect check",
            created_by=self.manifest.adapter_id, observed_at=self._clock(),
            verification="verified", verified_by=self.manifest.adapter_id,
            verified_at=self._clock())
        self.evidence_sink(evidence)
        return AdapterVerification(
            adapter_id=self.manifest.adapter_id, action_id=request.action_id,
            state="verified", observed_at=self._clock(),
            detail="the fixture checked its own effect after observing it",
            evidence_refs=(evidence.evidence_id,))


class ClaudeGatedProvider(GatedProvider):
    """The gated fixture catalogued under the frozen config's `claude-code` binding."""

    provider_id = "claude-code"
    display_name = "Claude Code (ALPHA-1 gated fixture)"


class CodexGatedProvider(GatedProvider):
    """The gated fixture catalogued under the frozen config's `codex` binding."""

    provider_id = "codex"
    display_name = "Codex (ALPHA-1 gated fixture)"


class PreviewGatedProvider(GatedProvider):
    """A third catalogued provider, configured to resolve version_mismatch."""

    provider_id = "codex-preview"
    display_name = "Codex preview (ALPHA-1 gated fixture)"


_ENTRY_PROTOCOLS = {
    ClaudeGatedProvider: CLAUDE_PROTOCOL,
    CodexGatedProvider: CODEX_PROTOCOL,
    PreviewGatedProvider: CODEX_PROTOCOL,
}


def catalog() -> dict[str, ProviderCatalogEntry]:
    """The reviewed fixture catalog the factory resolves operator config against."""
    return {
        adapter_class.provider_id: ProviderCatalogEntry(
            provider_id=adapter_class.provider_id,
            display_name=adapter_class.display_name, vendor=VENDOR,
            protocol=protocol, capabilities=DEEP_CONTROLS,
            schema_pairs=SCHEMA_PAIRS, lifecycle=LIFECYCLE,
            adapter_class=adapter_class)
        for adapter_class, protocol in _ENTRY_PROTOCOLS.items()
    }


def ids():
    """Thread-safe deterministic ids: request threads and workers share them."""
    counters: dict[str, int] = {}
    lock = threading.Lock()

    def mint(kind: str) -> str:
        with lock:
            counters[kind] = counters.get(kind, 0) + 1
            return f"{kind}-{counters[kind]}"

    return mint


def resolve(root, mint, *, available=("claude-code",), mismatched=("codex-preview",)):
    """Resolve the fixture providers through the real factory door.

    A provider in `available` gets its operator-pinned executable created; one in
    `mismatched` is pinned to another catalogued provider's protocol; the rest
    resolve `executable_absent`. No adapter is built for anything but available.
    """
    entries = catalog()
    configs = []
    for provider_id in sorted(entries):
        executable = root / f"{provider_id}.exe"
        if provider_id in available:
            executable.write_text("", encoding="utf-8")
        protocol = (CLAUDE_PROTOCOL if provider_id in mismatched
                    else entries[provider_id].protocol)
        configs.append(ProviderConfig(
            provider_id=provider_id, executable=str(executable),
            protocol=protocol, env_allow=()))
    return resolve_providers(
        configs, root=root, clock=lambda: NOW, ids=mint, catalog=entries)


def a_store(root) -> RunStore:
    """One confirm-mode run over the frozen two-instance configuration."""
    store = RunStore(root)
    store.create_run(a_run(
        run_id=RUN_ID, mode="confirm", config_digest=snapshot_digest(CONFIG)), CONFIG)
    return store


def a_proposal(*, instance_id, attempt_id, work_item_id):
    """One proposal body bound to a named instance of the frozen configuration."""
    body = {**proposal_body(), "instance_id": instance_id, "attempt_id": attempt_id}
    body["arguments"] = {**body["arguments"], "work_item_id": work_item_id}
    return body
