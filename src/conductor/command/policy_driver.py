"""One coalesced wake, one selected run, and existing execution admission."""
import hashlib
from threading import Condition, Thread

from .contracts import ActionProposal, ActionRequest, ActionResultReceipt, PROPOSAL_INPUT_BINDING, ABSENT, _thaw_json
from .contract_values import ContractError
from .graph_schedule import schedule
from .policy_history import current_authorization, hold_selected_inputs
from .policy_runtime import hold_live
from .service import CommandService
from .work_layout import work_route


class PolicyDriver:
    def __init__(self, policy, runtime, execution, *, clock, ids):
        self.policy, self.runtime, self.execution = policy, runtime, execution
        self.service = CommandService(policy.store, policy.registry, clock=clock, ids=ids)
        self._condition = Condition()
        self._active = None
        self._pending = False
        self._stopping = False
        self._thread = None
        self._inflight = None
        self._reason = "restart_required"

    def start(self):
        with self._condition:
            if self._thread is not None:
                raise RuntimeError("one policy driver may be started only once")
            self._thread = Thread(target=self._work, name="conduct-policy", daemon=True)
            self._thread.start()

    def stop(self):
        with self._condition:
            self._stopping = True
            self._active = None
            self._condition.notify_all()
        if self._thread is not None:
            self._thread.join(5)
            if self._thread.is_alive():
                raise RuntimeError("policy driver did not retire")

    def hold_activation(self, run_id):
        self._settle_inflight()
        with self._condition:
            if self._stopping or self._thread is None or not self._thread.is_alive():
                raise ContractError("policy driver is not running")
            if (self._active is not None and self._active[0] != run_id
                    or self._inflight is not None and self._inflight[0] != run_id):
                raise ContractError("another bounded run is active in this project")

    def activate(self, run_id, grant_id):
        with self._condition:
            self._active = (run_id, grant_id)
            self._reason = "ready"
            self._pending = True
            self._condition.notify()

    def deactivate(self, run_id):
        with self._condition:
            if self._active is not None and self._active[0] == run_id:
                self._active = None
            self._pending = True
            self._condition.notify()

    def is_active(self, run_id, grant_id):
        with self._condition:
            return not self._stopping and self._active == (run_id, grant_id)

    def wake(self, run_id):
        with self._condition:
            if self._active is not None and self._active[0] == run_id:
                self._pending = True
                self._condition.notify()

    def reason(self, run_id):
        with self._condition:
            return self._reason if self._active and self._active[0] == run_id else "restart_required"

    def _work(self):
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._pending or self._stopping, timeout=1)
                if self._stopping:
                    return
                active = self._active
                self._pending = False
            if active is None:
                continue
            try:
                self._tick(*active)
            except Exception:
                # Do not put subprocess/provider exception text into UI history.
                with self._condition:
                    self._reason = "admission_refused"

    def _settle_inflight(self):
        with self._condition:
            inflight = self._inflight
        if inflight is None:
            return
        recovered = self.policy.store.read(inflight[0])
        if any(row.kind == "action_result" and row.value.action_id == inflight[1]
               for row in recovered.records):
            with self._condition:
                if self._inflight == inflight:
                    self._inflight = None

    def _tick(self, run_id, grant_id):
        self._settle_inflight()
        with self.policy.store.transaction():
            if not self.is_active(run_id, grant_id):
                return
            recovered = self.policy.store.read(run_id)
            values = tuple(row.value for row in recovered.records)
            grant = current_authorization(values)
            if grant is None or grant.authorization_id != grant_id:
                raise ContractError("driver authorization changed")
            selected, reason = _next_node(recovered, grant)
            with self._condition:
                self._reason = reason
            if selected is None:
                if reason == "complete":
                    self.deactivate(run_id)
                return
            proposal = self._proposal(recovered, grant, selected)
            hold_live(self.runtime, recovered, grant, proposal)
        claimed = []
        try:
            authorization = self.runtime.authorize_policy(run_id, proposal.proposal_id,
                grant_id, admit=lambda: claimed.append(self.execution.claim()))
            if authorization.record_created:
                with self._condition:
                    self._inflight = (run_id, authorization.request.action_id)
                    self._reason = "running"
                for slot in claimed:
                    slot.place(authorization)
        finally:
            for slot in claimed:
                slot.release()

    def _proposal(self, recovered, grant, node):
        values = tuple(row.value for row in recovered.records)
        ordinal = 1 + sum(type(v) is ActionRequest for v in values)
        identity = hashlib.sha256(f"{grant.authorization_id}/{node.node_id}/{ordinal}".encode()).hexdigest()
        proposal_id, attempt_id = f"policy-{identity}", f"attempt-{identity}"
        previous = next((v for v in values if type(v) is ActionProposal and v.proposal_id == proposal_id), None)
        if previous is not None:
            return previous
        limit = next(row for row in grant.node_limits if row.node_id == node.node_id)
        from .policy_frontier import required_feedback
        definition = next(row.value for row in recovered.records if row.kind == "graph_definition")
        feedback = required_feedback(definition, values, grant, node.node_id)
        fields = dict(feedback_ids=tuple(v.feedback_id for v in feedback) or ABSENT, run_id=grant.run_id, attempt_id=attempt_id, instance_id=node.instance_id,
            capability=node.capability, arguments=_thaw_json(node.arguments),
            scope=(work_route(node.arguments["work_item_id"], node.arguments.get("work_scope")),),
            proposed_by="run-driver", rationale=f"Bounded authorization {grant.authorization_id}",
            timeout_seconds=limit.timeout_seconds, node_id=node.node_id,
            proposal_id=proposal_id, proposed_at=self.policy.clock())
        # Hold permission and immutable inputs before writing even a proposal.
        probe = ActionProposal(**fields, config_digest=recovered.envelope.config_digest,
                               input_binding=PROPOSAL_INPUT_BINDING)
        hold_live(self.runtime, recovered, grant, probe)
        return self.service.propose(**fields)


def _next_node(recovered, grant):
    values = tuple(row.value for row in recovered.records)
    definition = next(row.value for row in recovered.records if row.kind == "graph_definition")
    requests = {v.action_id: v for v in values if type(v) is ActionRequest}
    results = {v.action_id: v for v in values if type(v) is ActionResultReceipt}
    if requests.keys() - results.keys():
        return None, "running"
    from .policy_frontier import failure_sources, required_feedback
    failure_sources(values, grant)  # Unknown always refuses, even if other steps look runnable.
    computed = schedule(definition, values)
    if computed.run_state != "open":
        return None, computed.run_state
    candidates = [n for n in definition.nodes if n.capability is not None
                  and n.node_id in computed.runnable]
    for node in candidates:
        try:
            required_feedback(definition, values, grant, node.node_id)
        except ContractError:
            continue
        return node, "ready"
    return None, "feedback_required" if candidates else "waiting"
