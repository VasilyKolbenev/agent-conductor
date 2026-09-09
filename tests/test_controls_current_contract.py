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

The scenario is chosen to exercise what the addendum claims rather than to be
small: one binding whose transport declares two guards on its one road, and one
binding nothing is registered for at all. Between them the four standings all
appear, the three answers of the vendor's sandbox are all reachable, and the
per-road keying is visible.
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


def _ids():
    counters: dict[str, int] = {}

    def mint(kind: str) -> str:
        counters[kind] = counters.get(kind, 0) + 1
        return f"{kind}-addendum-{counters[kind]}"

    return mint


def current_answer(tmp_path) -> dict:
    """The real route's real answer for the addendum's scenario."""
    executable = tmp_path / "example.exe"
    executable.write_text("", encoding="utf-8")
    resolution = resolve_providers(
        [ProviderConfig(provider_id=PROVIDER, executable=str(executable),
                        protocol=PROTOCOL, env_allow=())],
        root=tmp_path, clock=lambda: NOW, ids=_ids(),
        catalog={PROVIDER: ProviderCatalogEntry(
            provider_id=PROVIDER, display_name="Example Transport",
            vendor="example", protocol=PROTOCOL,
            capabilities=("observe", "dispatch"),
            schema_pairs=[("dispatch", "deep-arguments-v1")],
            lifecycle=("observe", "prepare", "execute", "verify"),
            adapter_class=ExampleTransport,
            implementation="real_experimental")})
    store = RunStore(tmp_path)
    store.create_run(
        a_run(run_id=RUN_ID, mode="confirm", config_digest=snapshot_digest(CONFIG)),
        CONFIG)
    api = CommandApi(
        store, resolution.registry, session=CommandSession(PORT, TOKEN),
        budget=PRODUCT_COMMAND_BUDGET, clock=lambda: NOW, ids=_ids(),
        publish_run=lambda _run_id: None, providers=resolution.contracts)
    answer = api.handle("GET", f"/command/runs/{RUN_ID}/controls", get_headers())
    assert answer.status == 200, answer.payload
    return answer.payload


def documented() -> dict:
    marker = "<!-- CANONICAL:controls_current -->\n```json\n"
    text = _SPEC.read_text(encoding="utf-8")
    return json.loads(text.split(marker, 1)[1].split("\n```", 1)[0])


def test_the_addendum_carries_the_answer_this_build_really_sends(tmp_path):
    """One example, produced by the route, compared with the document.

    Canonicalized on both sides so key order in the document is not a second
    thing to maintain -- what is pinned is the ANSWER, not its typography.
    """
    assert canonical_json(documented()) == canonical_json(current_answer(tmp_path))


def test_the_documented_answer_shows_every_state_it_claims_to_describe(tmp_path):
    """An example that reached only one standing would document one third of it.

    The addendum says the standings are four words and the vendor's sandbox has
    three answers. An example is worth having only if a reader can see those
    distinctions in it, so this asserts the example really exercises them --
    and it reads the DOCUMENT, so an example edited down to something tidier
    fails here rather than quietly teaching a consumer less than the truth.
    """
    payload = documented()
    rows = {row["instance_id"]: row for row in payload["instances"]}

    standings = {fact["standing"]
                 for road in rows["worker"]["isolation"].values()
                 for fact in road}
    assert standings == {"active", "not_applicable", "stated_absence"}
    # The unregistered binding is the fourth word's home, and the reason the
    # example carries a second instance at all.
    assert rows["unregistered"]["isolation"] == {}
    assert rows["unregistered"]["controls"] == []
    vendor = [fact for fact in rows["worker"]["isolation"]["dispatch"]
              if fact["name"] == "vendor_sandbox_is_the_vendors"]
    assert vendor and vendor[0]["vendor_detail"] == [
        ["dispatch", "--sandbox workspace-write"]]
    assert [row["vendor_sandbox"] for row in payload["providers"]] == [
        [["dispatch", "--sandbox workspace-write"]]]


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
