"""Read all journal facts needed for acceptance, without Git or a work-tree walk.

Listing projections deliberately survive corrupt neighbours; an acceptance proof cannot
silently drop an unknown run which might own the same work scope. This reader fails closed.
Healthy unbound legacy runs and runs proven bound to another scope do not block acceptance.
"""
from __future__ import annotations

from dataclasses import dataclass

from .acceptance_basis import AcceptanceBasis, AcceptanceRun, acceptance_basis
from .containment import first_directory_violation
from .contracts import ActionRequest, ActionResultReceipt, ContractError, frozen_config_workflow
from .contract_values import _id
from .graph_template import TemplateError
from .run_store import CorruptRun, StoreError
from .seed_record import read_seed
from .studio_routes import standing_graph
from .task_contracts import frozen_config_task


@dataclass(frozen=True)
class AcceptanceContext:
    recovered: object
    definition: object
    task: object
    workflow: tuple[str, int] | None
    template: object
    seed: object
    basis: AcceptanceBasis
    inventory: tuple[AcceptanceRun, ...]


def read_context(api, run_id):
    """Take one durable inventory snapshot. Execution does not happen under this transaction."""
    try:
        with api._store.transaction():
            api._hold_route(run_id)
            recovered = api._store.read(run_id)
            if recovered.warnings:
                raise CorruptRun("acceptance refuses ambiguous journal bytes")
            binding = frozen_config_task(recovered.config)
            inventory = _inventory(api, run_id, binding)
            definition = standing_graph(recovered)
            workflow = frozen_config_workflow(recovered.config)
            template = None if workflow is None else api._templates.load(*workflow)
            task = None if binding is None else api._tasks.read(binding.task_id)
            if task is not None and task.work_scope != binding.work_scope:
                raise CorruptRun("task and frozen work scope disagree")
            seed = None if binding is None else read_seed(api._store.project_root, binding.task_id)
            basis = (AcceptanceBasis("documents", refused=("run_has_no_task" if binding is None
                                                         else "run_not_complete")) if definition is None else
                     acceptance_basis(definition, (row.value for row in recovered.records), inventory, seed))
            return AcceptanceContext(recovered, definition, task, workflow, template, seed, basis, inventory)
    except (ContractError, TemplateError) as error:
        raise CorruptRun("acceptance inventory contradicts its stored bindings") from error


def _inventory(api, current_id, current_task):
    store = api._store
    roots = (store.project_root, store.runs_root.parent, store.runs_root)
    if first_directory_violation(roots):
        raise CorruptRun("acceptance run inventory has an unsafe route")
    try:
        entries = tuple(store.runs_root.iterdir())
    except OSError as error:
        raise StoreError("acceptance run inventory cannot be read") from error
    ids = []
    for entry in entries:
        try:
            ids.append(_id("run_id", entry.name))
        except ContractError:
            continue  # including the exclusively staged, dot-prefixed unpublished directories
    if current_id not in ids:
        raise CorruptRun("acceptance inventory omits the current run")
    # Queue's read projection removes only entries proven processed; ambiguous entries remain.
    queued = {entry["run_id"] for entry in api._queue.read()["entries"]}
    driver = api._policy.driver
    slot = None if driver is None else driver.slot()
    active = set() if slot is None else {slot.active_run_id, slot.inflight_run_id} - {None}
    if not (queued | active) <= set(ids):
        raise CorruptRun("queue or driver names a run absent from the acceptance inventory")
    result = []
    for other_id in sorted(ids):
        api._hold_route(other_id)
        other = store.read(other_id)
        if other.warnings:
            raise CorruptRun("acceptance inventory includes an ambiguous journal")
        task = frozen_config_task(other.config)
        if (task is not None and current_task is not None
                and task.task_id == current_task.task_id and task.work_scope != current_task.work_scope):
            raise CorruptRun("one task identity names different work scopes")
        if (task is not None and current_task is not None
                and task.work_scope == current_task.work_scope and task.task_id != current_task.task_id):
            raise CorruptRun("different task identities share the acceptance work scope")
        requests = {row.value.action_id for row in other.records if isinstance(row.value, ActionRequest)}
        answers = {row.value.action_id for row in other.records if isinstance(row.value, ActionResultReceipt)}
        result.append(AcceptanceRun(other_id, task, other.envelope.created_at, bool(requests),
                                    other_id in active or bool(requests - answers), other_id in queued))
    return tuple(result)


def basis_payload(basis):
    if basis.refused is not None:
        return {"refused": basis.refused}
    result = {"final_gate": basis.final_gate, "decided_at": basis.decided_at,
              "verified_action": basis.verified_action}
    if basis.kind == "files":
        result.update(accept_manifest_digest=basis.accept_manifest_digest,
                      pending_checks=list(basis.pending_checks))
    return result


def read_accept(api, run_id):
    from .accept_records import read_records
    context = read_context(api, run_id)
    records = read_records(api._store.project_root, run_id,
                           task_id=None if context.task is None else context.task.task_id,
                           kind=context.basis.kind)
    return 200, {"kind": context.basis.kind, "basis": basis_payload(context.basis), **records}
