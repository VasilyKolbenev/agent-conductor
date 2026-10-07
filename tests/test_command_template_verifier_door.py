"""The from-template door judges a step's named checker before one durable byte.

A plan is immutable. One that names a checker which cannot check -- no
independent seams, or an unreachable provider -- was admitted with 201 and then
refused at every Confirm of its step, with no road left to repair the run.
`open_run` already refused the same binding; this door now agrees with it.
"""
from __future__ import annotations

import copy

import pytest

from conductor.command.adapters import AdapterRegistry
from conductor.command.http_api import CommandApi, PRODUCT_COMMAND_BUDGET
from conductor.command.http_transport import CommandSession
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.template_store import TemplateStore
from tests.test_command_http_api import NOW, PORT, RUN_ID, TOKEN, ids
from tests.test_command_run_store import CONFIG, a_run
from tests.test_command_runtime_execute import ScriptedAdapter
from tests.test_command_schema_doubles import DeepPlanAdapter
from tests.test_command_template_routes import contracts
from tests.test_standard_cycle_checker import _StandardAdapter, _materialize


class _NoIndependentSeams(ScriptedAdapter):
    """The four protocol methods only: no publish, release or verify_for."""

    argument_schemas = DeepPlanAdapter.argument_schemas


def _door(path, checker, providers):
    config = copy.deepcopy(CONFIG)
    store = RunStore(path)
    store.create_run(a_run(mode="confirm", config_digest=snapshot_digest(config)), config)
    registry = AdapterRegistry([_StandardAdapter(store, adapter_id="claude-code"), checker(store)])
    api = CommandApi(
        store, registry, session=CommandSession(PORT, TOKEN), budget=PRODUCT_COMMAND_BUDGET,
        clock=lambda: NOW, ids=ids(), publish_run=lambda _run: None, providers=providers,
        templates=TemplateStore(path))
    return api, store.run_path(RUN_ID) / "records.jsonl", registry


def _capable(store):
    return _StandardAdapter(store, adapter_id="codex")


def _seamless(_store):
    return _NoIndependentSeams(
        adapter_id="codex", capabilities=("observe", "review", "dispatch"))


@pytest.mark.parametrize("checker,providers,code", [
    (_seamless, contracts(), "capability_unsupported"),
    (_capable, contracts(reachable=("claude-code",)), "service_refused"),
], ids=["checker-without-independent-seams", "checker-on-an-unreachable-provider"])
def test_a_checker_that_cannot_check_is_refused_before_the_plan_is_written(
        tmp_path, checker, providers, code):
    api, journal, _ = _door(tmp_path, checker, providers)
    before = journal.read_bytes()
    answer = _materialize(api)
    assert answer.status == 409, answer.payload
    assert answer.payload["error"]["code"] == code
    assert journal.read_bytes() == before, "a refused plan wrote durable bytes"


def test_a_capable_reachable_checker_still_materializes_the_standard_plan(tmp_path):
    api, journal, registry = _door(tmp_path, _capable, contracts())
    assert registry.verifies_independently("codex", "dispatch") is True
    before = journal.read_bytes()
    assert _materialize(api).status == 201
    assert journal.read_bytes() != before
