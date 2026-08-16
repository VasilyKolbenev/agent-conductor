"""Thin, explicitly configured adapters for the two reviewed fake protocols.

PENDING: the real Claude Code and the real Codex CLI transport is NOT
implemented here and these adapters do not support either tool.  They speak
only the two deterministic fake JSON-line protocols review approved.  They
discover no executable, read no home directory, and invent no vendor CLI flag,
stdin protocol, session recovery, or evidence semantics for the real tools.

The capability body a request carries is validated and bound to the prepared
action, but it is deliberately NOT delivered to the child process: the
code-owned process spec is derived from configuration alone, so two different
capability bodies produce byte-identical specs.  Carrying a capability body to
a real CLI is exactly the transport work that stays pending; nothing here
smuggles one through argv, cwd, or the environment.

Class-owned identity is re-derived at every seam, stdout is decoded into a
closed value, and no raw output, vendor prose, or exception text is copied into
a durable receipt.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, ClassVar

from ..contracts import ActionRequest, ActionResultReceipt, canonical_json
from .base import (
    AdapterContractError,
    AdapterManifest,
    AdapterObservation,
    AdapterVerification,
    PreparedAction,
    UnsupportedCapability,
)
from .deep_codecs import FakeClaudeCodec, FakeCodexCodec
from .deep_commands import DEEP_ARGUMENT_TYPES, DeepCommandSpec
from .deep_contracts import DeepAdapterConfig, DeepProtocol, NormalizedResult
from .deep_evidence import AdapterEvidence
from .process import ProcessOutcome


DEEP_CAPABILITIES = tuple(DEEP_ARGUMENT_TYPES)
DEEP_CONTROLS = ("observe", *DEEP_CAPABILITIES)
DEEP_ARGUMENT_SCHEMA = "deep-arguments-v1"
EvidenceSource = Callable[[str], AdapterEvidence | None]


class _DeepAdapter:
    """Shared fake-protocol lifecycle; subclasses supply only fixed identity."""

    ADAPTER_ID: ClassVar[str]
    DISPLAY_NAME: ClassVar[str]
    VENDOR: ClassVar[str]
    PROTOCOL: ClassVar[DeepProtocol]
    CODEC: ClassVar[type[FakeClaudeCodec] | type[FakeCodexCodec]]
    argument_schemas = {
        capability: DEEP_ARGUMENT_SCHEMA for capability in DEEP_CAPABILITIES}

    def __init__(
            self, config: DeepAdapterConfig, runner: Any, *,
            clock: Callable[[], str], ids: Callable[[str], str],
            evidence_source: EvidenceSource | None = None) -> None:
        reviewed = self._reviewed
        canonical = _canonical_config(config)
        if canonical.protocol is not reviewed.PROTOCOL:
            raise AdapterContractError("deep adapter protocol does not match its identity")
        if not callable(getattr(runner, "run", None)):
            raise AdapterContractError("deep adapter requires an owned process runner")
        if not callable(clock) or not callable(ids):
            raise AdapterContractError("deep adapter requires clock and id callables")
        if evidence_source is not None and not callable(evidence_source):
            raise AdapterContractError("evidence_source must be callable or absent")
        self.manifest = AdapterManifest(
            adapter_id=reviewed.ADAPTER_ID, display_name=reviewed.DISPLAY_NAME,
            vendor=reviewed.VENDOR, version="fake-protocol-v1",
            capabilities=DEEP_CONTROLS, docs_url="")
        self._config = canonical
        self._runner = runner
        self._clock = clock
        self._ids = ids
        self._evidence_source = evidence_source

    @property
    def _reviewed(self) -> type[_DeepAdapter]:
        """Re-derive the class that owns this identity at every seam.

        A property is a data descriptor, so neither a plain assignment nor
        ``object.__setattr__`` can shadow it with an instance attribute, and a
        rewritten ``__class__`` fails the membership test rather than silently
        borrowing another vendor's id, protocol, or decoder.
        """
        kind = type(self)
        if kind not in (ClaudeCodeAdapter, CodexAdapter):
            raise AdapterContractError("deep adapter requires one reviewed concrete type")
        return kind

    @property
    def _reviewed_config(self) -> DeepAdapterConfig:
        """Re-canonicalize the configured value and re-bind it to this identity."""
        canonical = _canonical_config(self._config)
        if canonical.protocol is not self._reviewed.PROTOCOL:
            raise AdapterContractError("deep adapter protocol does not match its identity")
        return canonical

    def observe(self, instance_id: str, run_id: str) -> AdapterObservation:
        """Report no liveness claim: construction and observation probe nothing."""
        return AdapterObservation(
            adapter_id=self._reviewed.ADAPTER_ID, instance_id=instance_id, run_id=run_id,
            observed_at=self._safe_clock(), health="unknown",
            available_capabilities=(), detail="")

    def prepare(self, request: ActionRequest) -> PreparedAction:
        """Purely bind one unchanged request to its closed capability body."""
        if type(request) is not ActionRequest:
            raise AdapterContractError("deep prepare requires an ActionRequest")
        arguments = _request_arguments(request)
        return PreparedAction(
            adapter_id=self._reviewed.ADAPTER_ID,
            request=ActionRequest.from_dict(request.as_dict()),
            adapter_payload={
                "capability": request.capability,
                "arguments_json": canonical_json(arguments)})

    def execute(self, prepared: PreparedAction) -> ActionResultReceipt:
        """Run the re-derived command and retain only a normalized closed result."""
        request = self._prepared_request(prepared)
        config = self._reviewed_config
        spec = DeepCommandSpec.from_config(
            config, timeout_seconds=request.timeout_seconds)
        runner_spec = spec.to_runner_spec(config)
        outcome = self._run(runner_spec)
        if outcome.status == "timed_out":
            return self._receipt(request, "failed", None)
        if outcome.status == "stopped":
            return self._receipt(request, "cancelled", None)
        if outcome.status != "completed":
            raise AdapterContractError("deep runner returned an unsupported status")
        if outcome.exit_code != 0:
            return self._receipt(request, "failed", outcome.exit_code)
        if outcome.output_truncated:
            return self._receipt(request, "unknown", None)
        normalized = self._decode(outcome.output)
        if not _identity_matches(normalized, request, self._reviewed.ADAPTER_ID):
            raise AdapterContractError("deep result identity does not match its request")
        return self._receipt(request, normalized.outcome, normalized.exit_code,
                             observed_at=normalized.observed_at)

    def verify(
            self, request: ActionRequest, result: ActionResultReceipt,
    ) -> AdapterVerification:
        """Verify only an independently supplied fact keyed by action identity."""
        if not _receipt_matches(result, request):
            return self._verification(request, "mismatch")
        if result.outcome != "succeeded" or self._evidence_source is None:
            return self._verification(request, "unavailable")
        evidence = self._read_evidence(request.action_id)
        if evidence is None:
            return self._verification(request, "unavailable")
        if not _evidence_matches(evidence, request, self._reviewed.ADAPTER_ID):
            return self._verification(request, "mismatch")
        if evidence.verification != "verified":
            return self._verification(request, evidence.verification)
        return AdapterVerification(
            adapter_id=self._reviewed.ADAPTER_ID, action_id=request.action_id,
            state="verified", observed_at=evidence.verified_at or evidence.observed_at,
            detail="", evidence_refs=(evidence.evidence_id,))

    def _prepared_request(self, prepared: PreparedAction) -> ActionRequest:
        own = self._reviewed.ADAPTER_ID
        if type(prepared) is not PreparedAction or prepared.adapter_id != own:
            raise AdapterContractError("deep execute requires its own PreparedAction")
        request = ActionRequest.from_dict(prepared.request.as_dict())
        payload = _plain_json(prepared.adapter_payload)
        expected = {
            "capability": request.capability,
            "arguments_json": canonical_json(_request_arguments(request)),
        }
        if payload != expected:
            raise AdapterContractError("prepared deep payload differs from its request")
        return request

    def _run(self, spec: object) -> ProcessOutcome:
        failed = False
        try:
            outcome = self._runner.run(spec)
            if type(outcome) is not ProcessOutcome:
                failed = True
        except Exception:  # noqa: BLE001 -- executable/OS prose must not escape
            failed = True
            outcome = None
        if failed:
            raise AdapterContractError("deep process execution failed") from None
        assert outcome is not None
        if (type(outcome.status) is not str
                or outcome.exit_code is not None and type(outcome.exit_code) is not int
                or type(outcome.output) is not bytes
                or type(outcome.output_truncated) is not bool):
            raise AdapterContractError("deep runner returned a malformed outcome")
        return outcome

    def _decode(self, output: bytes) -> NormalizedResult:
        codec = self._reviewed.CODEC
        failed = False
        try:
            normalized = codec.decode_result(output)
        except Exception:  # noqa: BLE001 -- raw output must leave no exception graph
            failed = True
            normalized = None
        if failed:
            raise AdapterContractError("deep protocol result was refused") from None
        assert normalized is not None
        return normalized

    def _receipt(
            self, request: ActionRequest, outcome: str, exit_code: int | None, *,
            observed_at: str | None = None) -> ActionResultReceipt:
        failed = False
        try:
            receipt = ActionResultReceipt(
                receipt_id=self._ids("deep-result"), action_id=request.action_id,
                run_id=request.run_id, attempt_id=request.attempt_id,
                instance_id=request.instance_id, outcome=outcome,
                observed_at=observed_at or self._clock(), evidence_refs=(),
                detail=None, exit_code=exit_code)
        except Exception:  # noqa: BLE001 -- injected clock/id prose is untrusted
            failed = True
            receipt = None
        if failed:
            raise AdapterContractError("deep result could not be constructed") from None
        assert receipt is not None
        return receipt

    def _safe_clock(self) -> str:
        failed = False
        try:
            value = self._clock()
            AdapterObservation(
                self._reviewed.ADAPTER_ID, "instance", "run", value, "unknown", (), "")
        except Exception:  # noqa: BLE001 -- clock exception details are not public
            failed = True
            value = ""
        if failed:
            raise AdapterContractError("deep adapter clock failed") from None
        return value

    def _read_evidence(self, action_id: str) -> AdapterEvidence | None:
        failed = False
        try:
            supplied = self._evidence_source(action_id)  # type: ignore[misc]
            evidence = (None if supplied is None else
                        AdapterEvidence.from_dict(supplied.as_dict()))
        except Exception:  # noqa: BLE001 -- independent source prose is untrusted
            failed = True
            evidence = None
        if failed:
            return None
        return evidence

    def _verification(self, request: ActionRequest, state: str) -> AdapterVerification:
        return AdapterVerification(
            adapter_id=self._reviewed.ADAPTER_ID, action_id=request.action_id,
            state=state, observed_at=self._safe_clock(), detail="", evidence_refs=())


class ClaudeCodeAdapter(_DeepAdapter):
    """Configured adapter for the reviewed fake Claude JSON-line protocol."""

    ADAPTER_ID = "claude-code"
    DISPLAY_NAME = "Claude Code (fake protocol)"
    VENDOR = "Anthropic-compatible test fixture"
    PROTOCOL = DeepProtocol.FAKE_CLAUDE_V1
    CODEC = FakeClaudeCodec


class CodexAdapter(_DeepAdapter):
    """Configured adapter for the reviewed fake Codex JSON-line protocol."""

    ADAPTER_ID = "codex"
    DISPLAY_NAME = "Codex (fake protocol)"
    VENDOR = "OpenAI-compatible test fixture"
    PROTOCOL = DeepProtocol.FAKE_CODEX_V1
    CODEC = FakeCodexCodec


def _canonical_config(config: DeepAdapterConfig) -> DeepAdapterConfig:
    failed = False
    try:
        if type(config) is not DeepAdapterConfig:
            failed = True
            canonical = None
        else:
            canonical = DeepAdapterConfig.from_dict(config.as_dict())
    except Exception:  # noqa: BLE001 -- configured values retain no hostile graph
        failed = True
        canonical = None
    if failed:
        raise AdapterContractError("deep adapter config is not canonical") from None
    assert canonical is not None
    return canonical


def _request_arguments(request: ActionRequest) -> dict[str, Any]:
    argument_type = DEEP_ARGUMENT_TYPES.get(request.capability)
    if argument_type is None:
        raise UnsupportedCapability(
            f"deep adapter does not support capability {request.capability!r}")
    failed = False
    try:
        arguments = argument_type.from_dict(request.as_dict()["arguments"]).as_dict()
    except Exception:  # noqa: BLE001 -- submitted values retain no hostile graph
        failed = True
        arguments = None
    if failed:
        raise AdapterContractError("request arguments do not match the deep schema") from None
    assert arguments is not None
    return arguments


def _plain_json(value: object) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain_json(item) for item in value]
    return value


def _identity_matches(
        result: NormalizedResult, request: ActionRequest, adapter_id: str) -> bool:
    return (
        result.run_id, result.action_id, result.attempt_id, result.instance_id,
        result.adapter_id,
    ) == (
        request.run_id, request.action_id, request.attempt_id, request.instance_id,
        adapter_id,
    )


def _receipt_matches(result: object, request: ActionRequest) -> bool:
    return type(result) is ActionResultReceipt and (
        result.run_id, result.action_id, result.attempt_id, result.instance_id,
    ) == (
        request.run_id, request.action_id, request.attempt_id, request.instance_id,
    )


def _evidence_matches(
        evidence: AdapterEvidence, request: ActionRequest, adapter_id: str) -> bool:
    return (
        evidence.run_id, evidence.action_id, evidence.attempt_id,
        evidence.instance_id, evidence.adapter_id,
    ) == (
        request.run_id, request.action_id, request.attempt_id,
        request.instance_id, adapter_id,
    )
