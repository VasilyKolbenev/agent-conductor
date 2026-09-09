"""The browser receives the registered argument family, not an inferred one."""
from conductor.command.adapters import AdapterRegistry
from conductor.command.adapters.process import ProcessAdapter, ProcessRunner
from conductor.command.instance_controls import instance_controls
from tests.test_command_adapters import FakeAdapter
from tests.test_command_http_api import RUN_ID, api, get_headers
from tests.test_command_schema_doubles import DeepDispatchAdapter, ProcessDispatchAdapter

NOW = "2026-09-09T00:00:00Z"


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


def test_a_registration_that_is_absent_claims_no_protection_at_all():
    """An unregistered binding is answered for by nothing, and says so.

    This used to assert `uncontained_route == "active"` here, and that was the
    defect in one line: nothing was registered, so no code existed that could
    apply that refusal to this binding, and the screen said it was standing.
    A binding with no controls now carries no road, and a road is where a
    standing lives.
    """
    config = {"instances": [{"id": "plain", "adapter": "unknown-provider"}]}

    row = instance_controls(config, AdapterRegistry([]))[0]

    assert row["controls"] == []
    assert row["isolation"] == {}


def _standings(registry, adapter_id, capability):
    config = {"instances": [{"id": "plain", "adapter": adapter_id}]}
    rows = instance_controls(config, registry)[0]["isolation"][capability]
    return {row["name"]: row["standing"] for row in rows}


def test_a_transport_that_declares_no_guards_is_never_read_as_running_them():
    """The negative control the whole standing rule exists for.

    A plugin adapter carries no guard declaration. That is a fact about what
    this build has been TOLD, never a finding that the transport is unprotected
    -- so every row that depends on one reads `unknown`, and not one of them is
    drawn as a protection. The two absences this build states about ITSELF are
    unaffected: they are true of every transport because they are the lack of a
    mechanism rather than the presence of one.
    """
    standing = _standings(
        AdapterRegistry([FakeAdapter()]), "claude-code", "dispatch")

    claimed = [name for name, word in standing.items() if word == "active"]
    assert claimed == [], claimed
    assert standing["uncontained_route"] == "unknown"
    assert standing["instruction_bytes_moved"] == "unknown"
    assert standing["no_operating_system_boundary"] == "stated_absence"
    assert standing["scope_is_declarative"] == "stated_absence"


def test_the_owned_process_transport_claims_none_of_the_headless_checks():
    """The reviewer's own case, in the production class.

    `ProcessAdapter` runs one structured command and maps the outcome. It mints
    no home, compares no work tree, and resolves no instruction -- so the three
    checks that were shown as ACTIVE for it are exactly the three it cannot
    make. "This build can do it on another road" is not "this step is protected
    by it".
    """
    runner = ProcessRunner.__new__(ProcessRunner)
    adapter = ProcessAdapter("owned-process", runner, clock=lambda: NOW,
                             ids=lambda kind: f"{kind}-1")

    standing = _standings(
        AdapterRegistry([adapter]), "owned-process", "dispatch")

    for name in ("instruction_bytes_moved", "profile_home_retained",
                 "work_outside_the_item", "uncontained_route",
                 "inherited_home_residue", "unroutable_model"):
        assert standing[name] == "unknown", (name, standing[name])
    assert "active" not in standing.values()


def test_a_real_headless_transport_claims_what_its_own_code_applies(tmp_path):
    """The positive control, and the reason this is not just "say unknown".

    A rule that answered `unknown` everywhere would satisfy every negative
    control above and tell a person nothing. The real Codex transport carries
    the code for these checks, so its dispatch road says they stand -- read off
    the class the registry holds, with no instance constructed for the answer,
    no version probe and no login asked.
    """
    from tests.test_command_codex_transport import a_harness

    adapter, *_ = a_harness(tmp_path)

    standing = _standings(
        AdapterRegistry([adapter]), adapter.manifest.adapter_id, "dispatch")

    for name in ("uncontained_route", "inherited_home_residue",
                 "unroutable_model", "instruction_bytes_moved",
                 "work_outside_the_item", "profile_home_retained"):
        assert standing[name] == "active", (name, standing[name])


def test_the_two_roads_of_one_binding_are_not_told_the_same_story(tmp_path):
    """A review and a dispatch do not run the same checks, and say so.

    This is the half a single list per binding cannot express. The instruction
    digest is a dispatch question -- review resolves no instruction, so there is
    nothing to promise and nothing to check; the read-only tree comparison and
    the output scan are review questions, and a dispatch is neither read-only
    nor scanned. Both directions are asserted, so a rule that quietly answered
    with the union of the two roads fails here.
    """
    from tests.test_command_codex_transport import a_harness

    adapter, *_ = a_harness(tmp_path)
    registry = AdapterRegistry([adapter])
    adapter_id = adapter.manifest.adapter_id

    dispatch = _standings(registry, adapter_id, "dispatch")
    review = _standings(registry, adapter_id, "review")

    assert dispatch["instruction_bytes_moved"] == "active"
    assert review["instruction_bytes_moved"] == "not_applicable"
    assert dispatch["review_changed_the_tree"] == "not_applicable"
    assert review["review_changed_the_tree"] == "active"
    assert dispatch["environment_value_echoed"] == "not_applicable"
    assert review["environment_value_echoed"] == "active"
    # And a road neither runs is `not_applicable` on both, not `unknown`: the
    # transport DID declare its guards, so this is a measured absence.
    assert dispatch["uncontained_route"] == "active"
    assert review["uncontained_route"] == "not_applicable"
