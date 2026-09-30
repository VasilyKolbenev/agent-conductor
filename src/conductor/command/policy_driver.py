"""One coalesced wake, one selected run, and existing execution admission."""
import hashlib
from dataclasses import dataclass
from threading import Condition, Lock, Thread

from .contracts import ActionProposal, ActionRequest, ActionResultReceipt, PROPOSAL_INPUT_BINDING, ABSENT, _thaw_json
from .contract_values import ContractError
from .graph_schedule import schedule
from .policy_history import current_authorization, hold_selected_inputs
from .policy_runtime import hold_live
from .service import CommandService
from .work_layout import work_route


#: How long the driver's thread waits for a wake before it looks again.
TICK_SECONDS = 1


class NewWorkHeld(ContractError):
    """The driver is draining: what is in flight settles, nothing new is activated or started."""


class SlotBusy(ContractError):
    """Another run holds the project's slot: the terms may be fine, and the holder is named."""

    def __init__(self, holder: str) -> None:
        super().__init__("another bounded run is active in this project")
        self.holder = holder


@dataclass(frozen=True)
class SlotSnapshot:
    """What the driver holds at one instant: a copy, never a live view."""
    active_run_id: str | None
    inflight_run_id: str | None
    holding_new_work: bool


class PolicyDriver:
    def __init__(self, policy, runtime, execution, *, clock, ids):
        self.policy, self.runtime, self.execution = policy, runtime, execution
        self.service = CommandService(policy.store, policy.registry, clock=clock, ids=ids)
        self._condition = Condition()
        self._admission = Lock()  # held by a tick from its flag check to the end of its admission
        self._active = None
        self._pending = False
        self._stopping = False
        self._holding_new_work = False
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

    def hold_new_work(self) -> None:
        """Start nothing new from now on; an action already in flight still settles.

        In memory and one-way for the life of the process. It writes nothing to any run journal:
        a pause or any other control record written here would forge a human decision. It returns
        only after a tick that had already passed the flag check has finished admitting its
        action, so the open attempts a drain counts next include that action.
        """
        with self._condition:
            self._holding_new_work = True
        with self._admission:
            pass

    def slot(self) -> SlotSnapshot:
        """A frozen copy of the active run, the run with an action in flight, and the hold flag.

        It reads no journal and settles nothing, so the run it names as in flight is the one the
        driver last recorded. That run can still be named after its result is written, because
        `_inflight` clears only when a tick or an activation settles it, and it is recorded only
        once the request is written. The state of the holder comes from `automation_view`
        (spec 4.4.6).
        """
        with self._condition:
            return SlotSnapshot(
                active_run_id=self._active[0] if self._active is not None else None,
                inflight_run_id=self._inflight[0] if self._inflight is not None else None,
                holding_new_work=self._holding_new_work)

    def hold_activation(self, run_id):
        self._settle_inflight()
        with self._condition:
            if self._holding_new_work:
                raise NewWorkHeld("policy driver is holding new work")
            if self._stopping or self._thread is None or not self._thread.is_alive():
                raise ContractError("policy driver is not running")
            for held in (self._active, self._inflight):
                if held is not None and held[0] != run_id:
                    raise SlotBusy(held[0])

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

    def wake_queue(self):
        """Ask for a pass of the queue now instead of at the next tick (spec 4.4.4).

        It writes nothing and starts nothing: the thread looks, and the pass itself refuses
        when the slot is taken or new work is held back.
        """
        with self._condition:
            self._pending = True
            self._condition.notify()

    def reason(self, run_id):
        with self._condition:
            return self._reason if self._active and self._active[0] == run_id else "restart_required"

    def _work(self):
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._pending or self._stopping,
                                         timeout=TICK_SECONDS)
                if self._stopping:
                    return
                active = self._active
                self._pending = False
            if active is None:
                self._pump_queue()
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

    def _pump_queue(self):
        """One pass of the project queue, when nothing is active, in flight or held back.

        The pass runs inside `_admission`, exactly as a tick's admission does, so that
        `hold_new_work` returns only after a pass that had begun has finished: nothing is
        activated once a drain has been told to start nothing new. A fault of the pump is the
        pump's: the thread survives it and the next pass reconciles what it left.
        """
        queue = getattr(self.policy, "queue", None)
        if queue is None:
            return
        try:
            self._settle_inflight()
            with self._admission:
                with self._condition:
                    if self._holding_new_work or self._inflight is not None or self._stopping:
                        return
                queue.start_next()
        except Exception:
            return  # never put exception text into UI history; the next pass starts by reconciling

    def _tick(self, run_id, grant_id):
        self._settle_inflight()
        with self._admission:
            with self._condition:
                if self._holding_new_work:
                    return
            self._admit_next(run_id, grant_id)

    def _admit_next(self, run_id, grant_id):
        proposal, ended = self._select_next(run_id, grant_id)
        if ended:
            self._publish_frame(run_id)
        if proposal is None:
            return
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

    def _select_next(self, run_id, grant_id):
        """The proposal to admit next, and whether the plan just ended (and the slot was freed)."""
        with self.policy.store.transaction():
            if not self.is_active(run_id, grant_id):
                return None, False
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
                return None, reason == "complete"
            proposal = self._proposal(recovered, grant, selected)
            hold_live(self.runtime, recovered, grant, proposal)
            return proposal, False

    def _publish_frame(self, run_id):
        """Tell the desk the run left the slot: a read of the queue on the result frame must not
        still see it busy (spec 4.4.4). Publishing is best effort and never changes the driver."""
        try:
            self.policy.notify(run_id)
        except Exception:
            return

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
