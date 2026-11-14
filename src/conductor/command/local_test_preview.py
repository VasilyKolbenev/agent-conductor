"""Disclose owner-bound local tests without running a tool or reading its installation."""
from .contract_values import ContractError


def test_steps(nodes, documents, bindings, limits):
    from .adapters.deep_commands import PATCH_PROFILE
    from .adapters.local_test_plan import plan_for
    by_id = {document.artifact_id: document for document in documents}
    by_node = {binding.node_id: by_id[binding.artifact_id] for binding in bindings}
    budgets = {row["node_id"] for row in limits}
    result = []
    try:
        for node in nodes:
            if node.capability != "dispatch":
                continue
            plan = plan_for(by_node[node.node_id])
            if plan is None:
                continue
            if (node.arguments.get("profile") != PATCH_PROFILE
                    or node.node_id not in budgets):
                raise ValueError("test policy is outside this patch step")
            result.append({"node_id": node.node_id, "policy": plan.as_dict(),
                           "policy_digest": plan.digest, "toolpin_digest": plan.toolchain_digest})
    except (ValueError, TypeError, KeyError):
        raise ContractError("test policy is invalid for the reviewed step") from None
    return result
