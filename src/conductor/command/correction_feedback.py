"""Runtime-attributed rejection data; a record alone grants no correction."""
from dataclasses import dataclass, field

from .authorization_terms import closed_fields, exact_schema, positive_integer
from .contract_values import ContractError, _id, _digest, _timestamp, _freeze_json, _thaw_json
from .feedback_payload import settled_payload, FeedbackPayloadError


@dataclass(frozen=True)
class CorrectionFeedback:
    feedback_id: str
    run_id: str
    authorization_id: str
    authorization_digest: str
    source_action_id: str
    source_attempt_id: str
    source_node_id: str
    source_lap: int
    checker_instance_id: str
    checker_adapter_id: str
    result_manifest: object = field(repr=False)
    result_manifest_digest: str
    payload: object = field(repr=False)
    recorded_at: str
    schema_version: int = 2

    _FIELDS = frozenset({"schema_version", "feedback_id", "run_id", "authorization_id",
        "authorization_digest", "source_action_id", "source_attempt_id", "source_node_id",
        "source_lap", "checker_instance_id", "checker_adapter_id", "result_manifest",
        "result_manifest_digest", "payload", "recorded_at"})

    def __post_init__(self):
        from .result_manifest import rebuild_manifest, manifest_digest
        exact_schema(self.schema_version)
        for name in ("feedback_id", "run_id", "authorization_id", "source_action_id",
                     "source_attempt_id", "source_node_id", "checker_instance_id", "checker_adapter_id"):
            _id(name, getattr(self, name))
        _digest("authorization_digest", self.authorization_digest)
        _digest("result_manifest_digest", self.result_manifest_digest)
        _timestamp("recorded_at", self.recorded_at)
        positive_integer("source_lap", self.source_lap)
        manifest = rebuild_manifest(self.result_manifest)
        if manifest_digest(manifest) != self.result_manifest_digest:
            raise ContractError("feedback result manifest digest differs")
        object.__setattr__(self, "result_manifest", manifest)
        try:
            payload = settled_payload(_thaw_json(self.payload))
        except FeedbackPayloadError:
            raise ContractError("feedback payload does not satisfy its bounded protocol") from None
        object.__setattr__(self, "payload", _freeze_json(payload))

    def as_dict(self):
        return {name: _thaw_json(getattr(self, name)) for name in self._FIELDS}

    @classmethod
    def from_dict(cls, value):
        return cls(**closed_fields(value, cls._FIELDS, "correction feedback"))
