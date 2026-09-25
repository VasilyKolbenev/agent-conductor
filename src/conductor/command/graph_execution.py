"""Explicit topology opt-in, separate from the live authority to run a graph."""
from .contracts import ABSENT, ContractError
from .authorization_terms import AUTOMATION_CONTRACT


def settled_execution_contract(value):
    if value is ABSENT:
        return value
    if type(value) is not str or value != AUTOMATION_CONTRACT:
        raise ContractError("execution_contract must be the explicit bounded-run-v1 contract")
    return value


def hold_template_execution(template, config):
    contract = template.as_dict().get("execution_contract", ABSENT)
    if contract is not ABSENT and config.get("automation_contract") != AUTOMATION_CONTRACT:
        raise ContractError("this workflow requires a new explicitly opted-in Policy run")


def hold_graph_execution(recovered, definition):
    from .authorization_history import _hold_opt_in
    if definition.execution_contract is not ABSENT:
        _hold_opt_in(recovered)
