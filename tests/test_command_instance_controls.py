"""The browser receives the registered argument family, not an inferred one."""
from conductor.command.adapters import AdapterRegistry
from conductor.command.instance_controls import instance_controls
from tests.test_command_adapters import FakeAdapter
from tests.test_command_http_api import RUN_ID, api, get_headers
from tests.test_command_schema_doubles import DeepDispatchAdapter, ProcessDispatchAdapter


def test_controls_expose_the_registered_schema_for_the_actual_pair(tmp_path):
    subject, _, _ = api(tmp_path, adapters=[DeepDispatchAdapter()])
    response = subject.handle("GET", f"/command/runs/{RUN_ID}/controls", get_headers())
    assert response.status == 200
    rows = {row["instance_id"]: row for row in response.payload["instances"]}
    assert rows["claude-dev"]["argument_schemas"] == {"dispatch": "deep-arguments-v1"}
    assert rows["codex-review"]["argument_schemas"] == {}
    assert rows["codex-review"]["controls"] == []


def test_registry_schema_none_is_not_replaced_by_the_global_capability_schema():
    config = {"instances": [{"id": "plain", "adapter": "claude-code"}]}
    rows = instance_controls(config, AdapterRegistry([FakeAdapter()]))
    assert rows[0]["controls"]
    assert rows[0]["argument_schemas"] == {}


def test_schema_follows_the_registered_transport_not_the_adapter_name():
    config = {"instances": [{"id": "plain", "adapter": "claude-code"}]}
    rows = instance_controls(config, AdapterRegistry([ProcessDispatchAdapter()]))
    assert rows[0]["argument_schemas"] == {"dispatch": "structured-process-v1"}
    assert rows[0]["model"] is None


def test_empty_registry_reports_no_controls_and_no_schema_guess():
    config = {"instances": [{"id": "plain", "adapter": "unknown-provider"}]}
    rows = instance_controls(config, AdapterRegistry([]))
    # The closed guard stays closed on the keys it always held; the isolation
    # projection is a different question and is held literally next door rather
    # than folded into an equality this one would then stop checking.
    assert [{k: v for k, v in row.items() if k != "isolation"} for row in rows] == [{
        "instance_id": "plain", "adapter_id": "unknown-provider", "model": None,
        "controls": [], "argument_schemas": {}}]
    assert set(rows[0]) == {"instance_id", "adapter_id", "model", "controls",
                            "argument_schemas", "isolation"}


def test_an_unasked_provider_reads_unknown_and_never_a_protection():
    """No provider facts were supplied, so the rows that need them say so.

    A screen may render only `active` as a protection. An integration that was
    told nothing about a login mode or a vendor sandbox must not have that read
    as a finding either way -- which is the whole reason the projection carries
    four words rather than a boolean.
    """
    config = {"instances": [{"id": "plain", "adapter": "unknown-provider"}]}

    rows = instance_controls(config, AdapterRegistry([]))[0]["isolation"]
    standing = {row["name"]: row["standing"] for row in rows}

    assert standing["vendor_sandbox_is_the_vendors"] == "unknown"
    assert standing["login_directory_carries_configuration"] == "unknown"
    assert standing["uncontained_route"] == "active"
    assert standing["no_operating_system_boundary"] == "stated_absence"
