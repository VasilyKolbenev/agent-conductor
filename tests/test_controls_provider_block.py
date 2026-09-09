"""The additive `providers` block on `/controls`, and its two unmixed dimensions.

`GET /command/runs/<run_id>/controls` gains one further array beside `instances`.
The six routes stay six; nothing already in the payload moves. Each provider row
carries exactly five names, and two of them are DIFFERENT questions that must
never be answered with each other's vocabulary:

- ``availability`` is a fact about the operator's machine: is this provider
  configured at all, is the pinned file there, does the pinned protocol match.
- ``implementation`` is a fact about this BUILD: is the transport behind the
  provider real, a fixture, or unproven.

A provider can be perfectly available and still `fixture_only`; a provider can be
`real_experimental` and still `unconfigured`. The guards below drive a resolution
that stands in every availability state at once and hold the two vocabularies
apart as sets, so a value from one can never be read as a value from the other.

The join key for the Fable UI lane is ``provider_id``, never the display name --
proved here by resolving two DIFFERENT providers that share one display name and
showing the rows stay distinct and correctly attributed.
"""
from __future__ import annotations

import json
from dataclasses import replace

from conductor.command.adapters import (
    AdapterManifest,
    AdapterObservation,
    AdapterVerification,
    PreparedAction,
)
from conductor.command.adapters.deep_adapters import DEEP_CAPABILITIES, DEEP_CONTROLS
from conductor.command.adapters.dsh_harness import DSH_PROFILE
from conductor.command.adapters.provider import (
    AVAILABILITY_STATES,
    IMPLEMENTATION_STATES,
    WEAKEST_IMPLEMENTATION,
    ProviderCatalogEntry,
    ProviderConfig,
    provider_projection,
)
from conductor.command.contracts import ActionResultReceipt
from conductor.command.http_api import COMMAND_ROUTES, CommandApi, PRODUCT_COMMAND_BUDGET
from conductor.command.http_transport import CommandSession
from conductor.command.providers import resolve_providers
from conductor.command.run_store import RunStore, snapshot_digest

from tests.test_cockpit_command_api_freeze import CANON, EXPECTED_ARGUMENT_SCHEMAS
from tests.test_command_http_api import PORT, RUN_ID, TOKEN, get_headers
from tests.test_command_run_store import CONFIG, a_run


#: The five names one frozen `providers` row may carry, and the two vocabularies
#: it keeps apart -- written here rather than read from production, so the spec
#: pin and the production door never come from one function.
SPEC_ROW_FIELDS = frozenset({
    "provider_id", "display_name", "availability", "implementation", "controls"})
SPEC_AVAILABILITY = frozenset({
    "available", "executable_absent", "version_mismatch", "unconfigured"})
SPEC_IMPLEMENTATION = frozenset({
    "real_experimental", "fixture_only", "unproven"})
NOW = "2026-08-18T12:00:00Z"
PROTOCOL = "fake-claude-jsonl-v1"
OTHER_PROTOCOL = "fake-codex-jsonl-v1"
#: One display name deliberately shared by two different providers.
SHARED_DISPLAY = "Shared display name"
SCHEMA_PAIRS = tuple(sorted(
    (capability, "deep-arguments-v1") for capability in DEEP_CAPABILITIES))
LIFECYCLE = ("observe", "prepare", "execute", "verify")
#: provider id -> (protocol, implementation, how the operator config pins it)
ROSTER = {
    "here-and-real": (PROTOCOL, "real_experimental", "present"),
    "here-and-fake": (PROTOCOL, "fixture_only", "absent"),
    "wrong-protocol": (PROTOCOL, "unproven", "mismatched"),
    "never-pinned": (PROTOCOL, "fixture_only", "unpinned"),
}
AVAILABLE_ID = "here-and-real"


class RosterAdapter:
    """One catalogued adapter class; only the available provider is ever built."""

    argument_schemas = {
        capability: "deep-arguments-v1" for capability in DEEP_CAPABILITIES}

    def __init__(self, config, runner, *, clock, ids) -> None:
        self.manifest = AdapterManifest(
            adapter_id=AVAILABLE_ID, display_name=SHARED_DISPLAY,
            vendor="variant-A fixture", version="fake-protocol-v1",
            capabilities=DEEP_CONTROLS, docs_url="")
        self._clock = clock
        self._ids = ids

    def observe(self, instance_id, run_id):
        return AdapterObservation(
            adapter_id=AVAILABLE_ID, instance_id=instance_id, run_id=run_id,
            observed_at=self._clock(), health="unknown", available_capabilities=(),
            detail="the roster fixture probes nothing")

    def prepare(self, request):
        return PreparedAction(
            adapter_id=AVAILABLE_ID, request=request,
            adapter_payload={"work_item_id": request.arguments["work_item_id"]})

    def execute(self, prepared):
        request = prepared.request
        return ActionResultReceipt(
            receipt_id=self._ids("receipt"), action_id=request.action_id,
            run_id=request.run_id, attempt_id=request.attempt_id,
            instance_id=request.instance_id, outcome="succeeded",
            observed_at=self._clock(), detail="the roster fixture completed",
            exit_code=0)

    def verify(self, request, result):
        return AdapterVerification(
            adapter_id=AVAILABLE_ID, action_id=request.action_id,
            state="unavailable", observed_at=self._clock(),
            detail="the roster fixture checks nothing", evidence_refs=())


#: One roster adapter whose profile really declares a vendor sandbox. Every
#: other adapter class in this build's own roster declares nothing, so a join
#: that had stopped carrying the declaration would answer `null` everywhere and
#: every other expectation here would still pass.
DECLARED_SANDBOX = (("dispatch", "--sandbox workspace-write"),)


class SandboxedRosterAdapter(RosterAdapter):
    """The same fixture, carrying a real profile that declares one road."""

    profile = replace(DSH_PROFILE, vendor_sandbox=DECLARED_SANDBOX)


def catalog(*, display_names=None, adapter_classes=None):
    """The reviewed roster; `display_names` overrides one or more display names.

    `adapter_classes` overrides the CLASS behind one or more providers, which is
    where a harness profile -- and therefore a declared vendor sandbox -- is read
    from. Per provider rather than for the roster, so one row can declare while
    the rows beside it declare nothing.
    """
    names = {} if display_names is None else display_names
    classes = {} if adapter_classes is None else adapter_classes
    return {
        provider_id: ProviderCatalogEntry(
            provider_id=provider_id,
            display_name=names.get(provider_id, SHARED_DISPLAY),
            vendor="variant-A fixture", protocol=protocol,
            capabilities=DEEP_CONTROLS, schema_pairs=SCHEMA_PAIRS,
            lifecycle=LIFECYCLE,
            adapter_class=classes.get(provider_id, RosterAdapter),
            implementation=implementation)
        for provider_id, (protocol, implementation, _pin) in ROSTER.items()
    }


def ids():
    counters: dict[str, int] = {}

    def mint(kind: str) -> str:
        counters[kind] = counters.get(kind, 0) + 1
        return f"{kind}-variant-a-{counters[kind]}"

    return mint


def resolve(tmp_path, *, display_names=None, adapter_classes=None):
    """Resolve the roster so all four availability states stand at once."""
    entries = catalog(display_names=display_names, adapter_classes=adapter_classes)
    configs = []
    for provider_id, (protocol, _implementation, pin) in sorted(ROSTER.items()):
        if pin == "unpinned":
            continue
        executable = tmp_path / f"{provider_id}.exe"
        if pin == "present":
            executable.write_text("", encoding="utf-8")
        configs.append(ProviderConfig(
            provider_id=provider_id, executable=str(executable),
            protocol=OTHER_PROTOCOL if pin == "mismatched" else protocol,
            env_allow=()))
    return resolve_providers(
        configs, root=tmp_path, clock=lambda: NOW, ids=ids(), catalog=entries)


def an_api(tmp_path, resolution, *, config=None):
    store = RunStore(tmp_path)
    config = CONFIG if config is None else config
    store.create_run(a_run(
        run_id=RUN_ID, mode="confirm", config_digest=snapshot_digest(config)), config)
    return CommandApi(
        store, resolution.registry, session=CommandSession(PORT, TOKEN),
        budget=PRODUCT_COMMAND_BUDGET, clock=lambda: NOW, ids=ids(),
        publish_run=lambda _run_id: None, providers=resolution.contracts)


def controls(tmp_path, **changes):
    resolution = resolve(tmp_path, **changes)
    api = an_api(tmp_path, resolution)
    response = api.handle("GET", f"/command/runs/{RUN_ID}/controls", get_headers())
    assert response.status == 200, response.payload
    return response.payload


# -- the additive block, and the routes it did not add to --


def test_the_provider_roster_rides_the_controls_route_and_adds_none_of_its_own(
        tmp_path):
    """Counting routes said this until a graph route made the count move.

    What the block actually promised is that the roster is an ADDITIVE array on
    a route that already existed -- so the claim is stated as the relation it
    always was, and it survives the next honest route as it did not survive
    this one.
    """
    payload = controls(tmp_path)
    assert ("GET", "/command/runs/<run_id>/controls") in COMMAND_ROUTES
    assert not [path for _method, path in COMMAND_ROUTES if "provider" in path]
    # Three blocks now, and the third is the same shape of claim: the isolation
    # WORDS ride this route once, joined to a binding's standings by name rather
    # than repeated under every instance.
    assert set(payload) == {"instances", "providers", "isolation_facts"}
    assert payload["instances"] and payload["providers"]
    assert payload["isolation_facts"]


def test_every_provider_row_carries_exactly_the_seven_agreed_names(tmp_path):
    """Seven now: what the VENDOR's own sandbox is, per road, joined the row.

    It is a fact about somebody else's product and it sits beside the other
    per-provider facts for that reason -- the request path may not know which
    provider has what, so the answer is carried here and never derived
    downstream.
    """
    rows = controls(tmp_path)["providers"]
    assert [set(row) for row in rows] == [{
        "provider_id", "display_name", "availability", "implementation",
        "auth", "controls", "vendor_sandbox"}] * len(rows)
    assert [row["provider_id"] for row in rows] == sorted(ROSTER)


def test_a_row_says_which_login_was_pinned_and_never_where_it_is_kept(tmp_path):
    """The mode is a fact about the CONFIG; the directory holding a credential
    is not a fact this answer carries at all."""
    payload = controls(tmp_path)
    rows = {row["provider_id"]: row for row in payload["providers"]}
    assert rows["never-pinned"]["auth"] == "unpinned"
    assert rows["here-and-real"]["auth"] == "api_key"
    assert "auth_home" not in json.dumps(payload)


def test_a_provider_the_operator_never_pinned_is_unconfigured(tmp_path):
    rows = {row["provider_id"]: row for row in controls(tmp_path)["providers"]}
    assert rows["never-pinned"]["availability"] == "unconfigured"
    assert {row["provider_id"]: row["availability"] for row in rows.values()} == {
        "here-and-real": "available",
        "here-and-fake": "executable_absent",
        "wrong-protocol": "version_mismatch",
        "never-pinned": "unconfigured",
    }


# -- the two dimensions are never mixed --


def test_availability_and_implementation_are_disjoint_closed_vocabularies():
    assert AVAILABILITY_STATES.isdisjoint(IMPLEMENTATION_STATES)
    assert AVAILABILITY_STATES == {
        "available", "executable_absent", "version_mismatch", "unconfigured"}
    assert IMPLEMENTATION_STATES == {
        "real_experimental", "fixture_only", "unproven"}


def test_no_row_answers_either_question_with_the_other_vocabulary(tmp_path):
    rows = controls(tmp_path)["providers"]
    for row in rows:
        assert row["availability"] in AVAILABILITY_STATES
        assert row["implementation"] in IMPLEMENTATION_STATES
    # The resolution really did stand in every availability state, so this is a
    # statement about all four and not about one lucky row.
    assert {row["availability"] for row in rows} == set(AVAILABILITY_STATES)


def test_the_two_dimensions_vary_independently_of_each_other(tmp_path):
    rows = {row["provider_id"]: row for row in controls(tmp_path)["providers"]}
    # An available provider whose transport is only a fixture, and an absent one
    # whose transport is real: neither dimension can be read off the other.
    assert (rows["here-and-real"]["availability"],
            rows["here-and-real"]["implementation"]) == (
        "available", "real_experimental")
    assert (rows["never-pinned"]["availability"],
            rows["never-pinned"]["implementation"]) == (
        "unconfigured", "fixture_only")
    assert (rows["wrong-protocol"]["availability"],
            rows["wrong-protocol"]["implementation"]) == (
        "version_mismatch", "unproven")


def test_an_entry_that_declares_no_implementation_claims_the_weakest_one():
    entry = ProviderCatalogEntry(
        provider_id="undeclared", display_name="Undeclared",
        vendor="variant-A fixture", protocol=PROTOCOL, capabilities=DEEP_CONTROLS,
        schema_pairs=SCHEMA_PAIRS, lifecycle=LIFECYCLE, adapter_class=RosterAdapter)
    assert entry.implementation == "unproven"


# -- the join key is the provider id, never the display name --


def test_two_providers_sharing_one_display_name_stay_distinct_and_correct(tmp_path):
    rows = controls(tmp_path)["providers"]
    assert len({row["display_name"] for row in rows}) == 1
    assert len({row["provider_id"] for row in rows}) == len(ROSTER)
    keyed = {row["provider_id"]: row["availability"] for row in rows}
    assert keyed["here-and-real"] != keyed["never-pinned"]


def without_display_name(rows):
    """Every row field except the one a rename is allowed to move."""
    return [
        {key: value for key, value in row.items() if key != "display_name"}
        for row in rows]


def test_renaming_a_provider_changes_its_display_name_and_nothing_else(tmp_path):
    first, second = tmp_path / "before", tmp_path / "after"
    first.mkdir()
    second.mkdir()
    before = controls(first)["providers"]
    after = controls(
        second,
        display_names={AVAILABLE_ID: "A completely different product name"},
    )["providers"]
    assert [row["display_name"] for row in after] != [
        row["display_name"] for row in before]
    assert without_display_name(after) == without_display_name(before)


def test_a_projection_row_is_built_from_contracts_alone(tmp_path):
    resolution = resolve(tmp_path)
    assert provider_projection(resolution.contracts) == controls(
        tmp_path)["providers"]


#: Two bindings on one run: one runs under the provider whose class declares a
#: vendor sandbox, the other under a provider whose class declares nothing.
BOUND_CONFIG = {
    "cycle": {"id": "sandbox-orbit", "phases": ["goal"]},
    "instances": [
        {"id": "declared", "adapter": AVAILABLE_ID},
        {"id": "silent", "adapter": "here-and-fake"},
    ],
}


def test_a_declared_vendor_sandbox_reaches_the_binding_that_runs_under_it(tmp_path):
    """The whole server-side road, on a value that is not `null`.

    The declaration lives on an adapter CLASS, the registry reads it into the
    contract, the projection puts it on the provider row, and `/controls` joins
    that row to the bindings this run froze -- by `adapter_id`, once, so the
    browser is never where two projections become a promise.

    Both answers ride the same response. The binding whose provider declares
    reads `active` and carries the vendor's own words; the binding beside it,
    whose provider declares nothing, reads `unknown` and carries none -- and a
    join that had lost the declaration, or had handed one binding's answer to
    the other, fails on one of those two halves.
    """
    resolution = resolve(
        tmp_path, adapter_classes={AVAILABLE_ID: SandboxedRosterAdapter})
    api = an_api(tmp_path, resolution, config=BOUND_CONFIG)

    payload = api.handle(
        "GET", f"/command/runs/{RUN_ID}/controls", get_headers()).payload

    rows = {row["provider_id"]: row["vendor_sandbox"] for row in payload["providers"]}
    assert rows[AVAILABLE_ID] == [["dispatch", "--sandbox workspace-write"]]
    assert rows["here-and-fake"] is None
    standings = {row["instance_id"]: {
        fact["name"]: fact for fact in row["isolation"]}
        for row in payload["instances"]}
    vendor = "vendor_sandbox_is_the_vendors"
    assert standings["declared"][vendor]["standing"] == "active"
    assert standings["declared"][vendor]["vendor_detail"] == [
        ["dispatch", "--sandbox workspace-write"]]
    assert standings["silent"][vendor]["standing"] == "unknown"
    assert standings["silent"][vendor].get("vendor_detail") is None


# -- the frozen spec example says the same thing the production payload does --


def test_the_frozen_controls_example_carries_exactly_the_two_agreed_arrays():
    assert set(CANON["controls_response"]) == {"instances", "providers"}


def test_every_frozen_provider_row_carries_five_names_and_sorted_proven_controls():
    rows = CANON["controls_response"]["providers"]
    assert rows == sorted(rows, key=lambda row: row["provider_id"])
    for row in rows:
        assert set(row) == SPEC_ROW_FIELDS
        assert row["controls"] == sorted(row["controls"])
        assert set(row["controls"]) <= set(EXPECTED_ARGUMENT_SCHEMAS)
        assert isinstance(row["display_name"], str) and row["display_name"]


def test_the_frozen_example_stands_in_every_state_of_both_vocabularies():
    """One lucky row would prove nothing, so the example exercises all of both."""
    rows = CANON["controls_response"]["providers"]
    assert {row["availability"] for row in rows} == AVAILABILITY_STATES
    assert {row["implementation"] for row in rows} == IMPLEMENTATION_STATES


def test_the_spec_vocabularies_are_the_ones_the_provider_contract_holds():
    """The frozen prose and the production door name the same two closed sets."""
    assert SPEC_AVAILABILITY == AVAILABILITY_STATES
    assert SPEC_IMPLEMENTATION == IMPLEMENTATION_STATES
    assert WEAKEST_IMPLEMENTATION in IMPLEMENTATION_STATES


def test_no_frozen_row_fact_can_be_recovered_from_the_label_beside_it():
    rows = CANON["controls_response"]["providers"]
    assert len({row["provider_id"] for row in rows}) == len(rows)
    for row in rows:
        label = row["display_name"].lower()
        assert row["availability"] not in label
        assert row["implementation"] not in label
