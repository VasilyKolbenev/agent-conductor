"""The CURRENT `/controls` answer, held to the addendum that describes it.

The frozen C/API-0 document describes the answer as it stood when it was
frozen: two arrays, five provider names. The route has grown since -- a login
mode, a vendor's own sandbox, and the isolation standings -- and the frozen body
is deliberately NOT rewritten to match: it is the record of what was agreed
then, and editing it would erase the history it exists to keep.

So the current shape is described in its own addendum, and this module is what
keeps that addendum true: the example in it is compared, byte for byte after a
canonical dump, with a response a real `CommandApi.handle` really produced. A
document nobody drives is prose, and prose about a wire format is the thing that
is wrong first.

There are TWO examples, and the second exists because the first cannot show what
the document claims. The first is a transport that declares two guards on its
one road, beside a binding nothing is registered for; it reaches `active`,
`not_applicable` and `stated_absence`, and shows an empty road map -- which is
the absence of a road and not a standing at all. The second is the commoner
case, transports declaring no guards: that is where `unknown` lives, and where
the vendor's other two answers are, one provider requesting no sandbox mode and
one carrying no reviewed declaration.

Between them, and only between them, all four standings and all three sandbox
answers appear. A claim about coverage is worth nothing unless something checks
it, so the coverage test below reads the DOCUMENT rather than the responses.
"""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from conductor.command.adapters import (
    AdapterManifest,
    AdapterObservation,
    AdapterVerification,
    PreparedAction,
)
from conductor.command.adapters.dsh_harness import DSH_PROFILE
from conductor.command.adapters.provider import ProviderCatalogEntry
from conductor.command.contracts import ActionResultReceipt, canonical_json
from conductor.command.http_api import CommandApi, PRODUCT_COMMAND_BUDGET
from conductor.command.http_transport import CommandSession
from conductor.command.providers import resolve_providers
from conductor.command.adapters.provider import ProviderConfig
from conductor.command.run_store import RunStore, snapshot_digest

from tests.test_command_http_api import PORT, RUN_ID, TOKEN, get_headers
from tests.test_command_run_store import a_run

_SPEC = (Path(__file__).resolve().parents[1] / "docs" / "specs"
         / "2026-09-09-controls-current-contract.md")

NOW = "2026-09-09T12:00:00Z"
PROVIDER = "example-transport"
PROTOCOL = "fake-claude-jsonl-v1"
#: What the example's transport declares: two guards, one road. Everything else
#: this build states is then a MEASURED absence for it rather than an unknown,
#: which is the difference the addendum has to be able to show.
DECLARED_GUARDS = {
    "uncontained_route": ("dispatch",),
    "work_outside_the_item": ("dispatch",),
}
DECLARED_SANDBOX = (("dispatch", "--sandbox workspace-write"),)
CONFIG = {
    "cycle": {"id": "addendum-orbit"},
    "instances": [
        {"id": "worker", "adapter": PROVIDER},
        {"id": "unregistered", "adapter": "nothing-registered"},
    ],
}
#: The second example's provider: a transport that declares NO guards and whose
#: profile declares no vendor sandbox mode. It is the other half of what the
#: addendum describes -- `unknown` is what an undeclared transport gets, and it
#: is the standing a reader meets most often, so an example without one would
#: document the rare case and omit the common one.
SILENT = "silent-transport"
#: And beside it, the provider that carries no harness profile at all -- the
#: third answer of the vendor's sandbox, `null`, which neither of the other two
#: examples can show: one declares modes and the other declares none.
UNMEASURED = "unmeasured-transport"
SILENT_CONFIG = {
    "cycle": {"id": "addendum-orbit"},
    "instances": [
        {"id": "worker", "adapter": SILENT},
        {"id": "unmeasured", "adapter": UNMEASURED},
    ],
}


class ExampleTransport:
    """A dispatch-only transport that declares what its own code applies."""

    argument_schemas = {"dispatch": "deep-arguments-v1"}
    isolation_guards = DECLARED_GUARDS
    profile = replace(DSH_PROFILE, vendor_sandbox=DECLARED_SANDBOX)

    def __init__(self, config, runner, *, clock, ids) -> None:
        self.manifest = AdapterManifest(
            adapter_id=PROVIDER, display_name="Example Transport",
            vendor="example", version=PROTOCOL,
            capabilities=("observe", "dispatch"), docs_url="")
        self._clock = clock
        self._ids = ids

    def observe(self, instance_id, run_id):
        return AdapterObservation(
            adapter_id=PROVIDER, instance_id=instance_id, run_id=run_id,
            observed_at=self._clock(), health="unknown",
            available_capabilities=(), detail="the example probes nothing")

    def prepare(self, request):
        return PreparedAction(
            adapter_id=PROVIDER, request=request,
            adapter_payload={"work_item_id": request.arguments["work_item_id"]})

    def execute(self, prepared):
        request = prepared.request
        return ActionResultReceipt(
            receipt_id=self._ids("receipt"), action_id=request.action_id,
            run_id=request.run_id, attempt_id=request.attempt_id,
            instance_id=request.instance_id, outcome="succeeded",
            observed_at=self._clock(), detail="the example completed",
            exit_code=0)

    def verify(self, request, result):
        return AdapterVerification(
            adapter_id=PROVIDER, action_id=request.action_id,
            state="unavailable", observed_at=self._clock(),
            detail="the example checks nothing", evidence_refs=())


class SilentTransport(ExampleTransport):
    """The same shape, declaring nothing about the guards its code applies.

    Its profile DOES declare a vendor sandbox -- an empty one, the measured
    absence -- so the two examples together carry all three of that field's
    answers rather than two of them.
    """

    isolation_guards = None
    profile = replace(DSH_PROFILE, vendor_sandbox=())

    def __init__(self, config, runner, *, clock, ids) -> None:
        super().__init__(config, runner, clock=clock, ids=ids)
        self.manifest = AdapterManifest(
            adapter_id=SILENT, display_name="Silent Transport",
            vendor="example", version=PROTOCOL,
            capabilities=("observe", "dispatch"), docs_url="")


class UnmeasuredTransport(SilentTransport):
    """No harness profile at all: nothing was looked at, and nothing is claimed."""

    profile = None

    def __init__(self, config, runner, *, clock, ids) -> None:
        super().__init__(config, runner, clock=clock, ids=ids)
        self.manifest = AdapterManifest(
            adapter_id=UNMEASURED, display_name="Unmeasured Transport",
            vendor="example", version=PROTOCOL,
            capabilities=("observe", "dispatch"), docs_url="")


def _ids():
    counters: dict[str, int] = {}

    def mint(kind: str) -> str:
        counters[kind] = counters.get(kind, 0) + 1
        return f"{kind}-addendum-{counters[kind]}"

    return mint


def _entry(provider_id, display, adapter_class) -> ProviderCatalogEntry:
    return ProviderCatalogEntry(
        provider_id=provider_id, display_name=display,
        vendor="example", protocol=PROTOCOL,
        capabilities=("observe", "dispatch"),
        schema_pairs=[("dispatch", "deep-arguments-v1")],
        lifecycle=("observe", "prepare", "execute", "verify"),
        adapter_class=adapter_class, implementation="real_experimental")


def _answer(tmp_path, roster, config) -> dict:
    """One real route answer, for whichever transports an example is about."""
    configs = []
    for provider_id, _display, _adapter_class in roster:
        executable = tmp_path / f"{provider_id}.exe"
        executable.write_text("", encoding="utf-8")
        configs.append(ProviderConfig(
            provider_id=provider_id, executable=str(executable),
            protocol=PROTOCOL, env_allow=()))
    resolution = resolve_providers(
        configs, root=tmp_path, clock=lambda: NOW, ids=_ids(),
        catalog={provider_id: _entry(provider_id, display, adapter_class)
                 for provider_id, display, adapter_class in roster})
    store = RunStore(tmp_path)
    store.create_run(
        a_run(run_id=RUN_ID, mode="confirm", config_digest=snapshot_digest(config)),
        config)
    api = CommandApi(
        store, resolution.registry, session=CommandSession(PORT, TOKEN),
        budget=PRODUCT_COMMAND_BUDGET, clock=lambda: NOW, ids=_ids(),
        publish_run=lambda _run_id: None, providers=resolution.contracts)
    answer = api.handle("GET", f"/command/runs/{RUN_ID}/controls", get_headers())
    assert answer.status == 200, answer.payload
    return answer.payload


def current_answer(tmp_path) -> dict:
    """A transport that declares two guards, beside a binding nothing serves."""
    return _answer(
        tmp_path, [(PROVIDER, "Example Transport", ExampleTransport)], CONFIG)


def silent_answer(tmp_path) -> dict:
    """Two transports that declare no guards: one measured none, one unmeasured."""
    return _answer(
        tmp_path,
        [(SILENT, "Silent Transport", SilentTransport),
         (UNMEASURED, "Unmeasured Transport", UnmeasuredTransport)],
        SILENT_CONFIG)


def documented(name: str = "controls_current") -> dict:
    marker = f"<!-- CANONICAL:{name} -->\n```json\n"
    text = _SPEC.read_text(encoding="utf-8")
    return json.loads(text.split(marker, 1)[1].split("\n```", 1)[0])


def test_the_addendum_carries_the_answer_this_build_really_sends(tmp_path):
    """The declaring example, produced by the route, compared with the document.

    Canonicalized on both sides so key order in the document is not a second
    thing to maintain -- what is pinned is the ANSWER, not its typography.
    """
    assert canonical_json(documented()) == canonical_json(current_answer(tmp_path))


def test_the_second_example_is_the_answer_for_a_transport_that_declares_nothing(
        tmp_path):
    """And it is driven the same way, because it is the commoner case.

    Every adapter written before the guard declaration existed lands here, and
    so does every plugin. An addendum whose only example was a declaring
    transport would document the rarer half of its own contract.
    """
    assert canonical_json(documented("controls_current_silent")) == canonical_json(
        silent_answer(tmp_path))


def test_the_documented_examples_show_every_state_they_claim_to_describe():
    """Claimed coverage, held to the two examples rather than asserted in prose.

    The addendum describes four standings and three answers for the vendor's
    sandbox, and a document may only claim what its examples let a reader see.
    An earlier version of this test said the pair covered all four standings
    when the first example reached three and an empty road map is not a row
    whose standing is `unknown`; the second example is what makes the claim
    true, and this reads the DOCUMENT so that trimming either one fails here.
    """
    declaring = {row["instance_id"]: row for row in documented()["instances"]}
    silent = {row["instance_id"]: row
              for row in documented("controls_current_silent")["instances"]}

    seen = {fact["standing"]
            for row in (*declaring.values(), *silent.values())
            for road in row["isolation"].values() for fact in road}
    assert seen == {"active", "not_applicable", "stated_absence", "unknown"}
    # An empty road map is a different thing from any standing, and the
    # addendum describes it separately -- so it is asserted separately.
    assert declaring["unregistered"]["isolation"] == {}
    assert declaring["unregistered"]["controls"] == []

    def vendor_of(row):
        return [fact for fact in row["isolation"]["dispatch"]
                if fact["name"] == "vendor_sandbox_is_the_vendors"][0]

    # All three answers of the field, each on the binding that really carries it.
    assert vendor_of(declaring["worker"])["vendor_detail"] == [
        ["dispatch", "--sandbox workspace-write"]]
    assert vendor_of(silent["worker"])["vendor_detail"] == []
    assert vendor_of(silent["worker"])["standing"] == "stated_absence"
    assert vendor_of(silent["unmeasured"])["vendor_detail"] is None
    assert vendor_of(silent["unmeasured"])["standing"] == "unknown"
    assert sorted(
        json.dumps(row["vendor_sandbox"]) for row in documented()["providers"]
    ) == ['[["dispatch", "--sandbox workspace-write"]]']
    assert sorted(
        json.dumps(row["vendor_sandbox"])
        for row in documented("controls_current_silent")["providers"]
    ) == ["[]", "null"]


def test_the_addendum_names_the_frozen_document_it_extends_and_rewrites_none_of_it():
    """The addendum is additive, and says so where a reader arrives.

    The rule it exists under: the frozen body stays the record of what was
    agreed, and the current shape is described beside it. A reader who lands on
    either one has to be able to find the other.
    """
    frozen = (_SPEC.parent / "2026-08-13-cockpit-command-api.md").read_text(
        encoding="utf-8")
    text = _SPEC.read_text(encoding="utf-8")

    assert "2026-08-13-cockpit-command-api.md" in text
    assert _SPEC.name in frozen, "§6.2 does not link the addendum"
    # And the frozen example is untouched: still two arrays, five names.
    assert '"vendor_sandbox"' not in frozen.split(
        "<!-- CANONICAL:controls_response -->", 1)[1].split("\n```", 1)[0]
