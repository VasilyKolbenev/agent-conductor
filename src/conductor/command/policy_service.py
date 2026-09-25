"""Human preview/authorization/control, with exact retries before live checks."""
from .authorization_terms import closed_fields
from .authorization_history import validate_authorization_history
from .contract_values import ContractError, _content_digest, _id
from .contracts import ActionRequest, ActionResultReceipt
from .policy_history import current_authorization
from .policy_preview import (PREVIEW_FIELDS, PreviewCache, authorization_terms,
                             build_preview, from_terms)
from .run_authorization import RunAuthorization, RunAuthorizationControl
from .store_errors import RecordConflict


AUTHORIZE_FIELDS = frozenset({"authorization_id", "preview_digest", "authorized_by",
                              "terms", "supersedes"})
CONTROL_FIELDS = RunAuthorizationControl._FIELDS - {"schema_version", "run_id", "recorded_at"}


class PolicyService:
    def __init__(self, store, registry, *, budget, clock, provider_digest, owner_check,
                 session, notify, provider_facts=None):
        self.store, self.registry = store, registry
        self.budget, self.clock = budget, clock
        self.provider_digest, self.owner_check = provider_digest, owner_check
        self.session, self.notify = session, notify
        self.provider_facts = provider_facts
        self.previews = PreviewCache()
        self.driver = None

    def preview(self, run_id, body):
        with self.store.transaction():
            result = build_preview(self.store.read(run_id), body, budget=self.budget,
                provider_digest=self.provider_digest, registry=self.registry, clock=self.clock, provider_facts=self.provider_facts)
            self.previews.put(self.session, run_id, result)
            return result

    def authorize(self, run_id, body):
        body = closed_fields(body, AUTHORIZE_FIELDS, "automation authorize")
        with self.store.transaction():
            recovered = self.store.read(run_id)
            previous = next((r.value for r in recovered.records if r.kind == "run_authorization"
                             and r.value.authorization_id == body["authorization_id"]), None)
            if previous is not None:
                candidate = self._candidate(body, previous.authorized_at)
                if candidate != previous or candidate.run_id != run_id:
                    raise RecordConflict("authorization identity is already used by different terms")
                return previous, False
            self.owner_check()
            if self.driver is None:
                raise ContractError("automation driver is not available")
            self.driver.hold_activation(run_id)
            now = self.clock()
            self.previews.require(self.session, run_id, body["preview_digest"], body["terms"], now)
            asked = {key: body["terms"][key] for key in PREVIEW_FIELDS}
            fresh = build_preview(recovered, asked, budget=self.budget, registry=self.registry,
                provider_digest=self.provider_digest, clock=lambda: now, provider_facts=self.provider_facts)
            if fresh["terms"] != body["terms"] or fresh["preview_digest"] != body["preview_digest"]:
                raise ContractError("reviewed starting facts changed; preview again")
            candidate = self._candidate(body, now)
            if candidate.run_id != run_id:
                raise ContractError("preview belongs to another run")
            validate_authorization_history(recovered, candidate)
            created = self.store.append(candidate)
            self.previews.discard(self.session, run_id)
            if created:
                self.driver.activate(run_id, candidate.authorization_id)
        self.notify(run_id)
        return candidate, created

    @staticmethod
    def _candidate(body, at):
        if body["preview_digest"] != _content_digest(body["terms"]):
            raise ContractError("preview digest differs from its terms")
        return from_terms(body["terms"], authorization_id=body["authorization_id"],
            authorized_by=body["authorized_by"], authorized_at=at, supersedes=body["supersedes"])

    def control(self, run_id, body):
        body = closed_fields(body, CONTROL_FIELDS, "automation control")
        with self.store.transaction():
            recovered = self.store.read(run_id)
            previous = next((r.value for r in recovered.records if r.kind == "run_authorization_control"
                             and r.value.control_id == body["control_id"]), None)
            candidate = RunAuthorizationControl(**body, run_id=run_id,
                recorded_at=previous.recorded_at if previous else self.clock())
            if previous is not None:
                if candidate != previous:
                    raise RecordConflict("control identity is already used by different terms")
                return previous, False
            self.owner_check()
            if candidate.action == "resume":
                self._hold_resume(recovered)
                if self.driver is None:
                    raise ContractError("automation driver is not available")
                self.driver.hold_activation(run_id)
            validate_authorization_history(recovered, candidate)
            created = self.store.append(candidate)
            if created and self.driver is not None:
                if candidate.action == "resume":
                    self.driver.activate(run_id, candidate.authorization_id)
                else:
                    self.driver.deactivate(run_id)
        self.notify(run_id)
        return candidate, created

    @staticmethod
    def _hold_resume(recovered):
        values = tuple(row.value for row in recovered.records)
        results = {v.action_id: v for v in values if type(v) is ActionResultReceipt}
        grant = current_authorization(values)
        if any(type(v) is ActionRequest and (v.action_id not in results
                or grant is not None and v.run_authorization_id == grant.authorization_id
                and results[v.action_id].outcome == "unknown") for v in values):
            raise ContractError("resume requires settled, unambiguous actions")
