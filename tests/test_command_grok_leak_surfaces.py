"""A secret the child prints reaches no receipt, no journal record, and no API.

The transport suite already holds that the receipt and the verification carry no
child output. That is the smallest of the three surfaces, and it is the one a
caller sees LAST. Between them sit two that outlive the process: the durable
journal the run store appends, and the HTTP views projected from it. A secret
that reached either would be retained and served, and no receipt assertion would
have said so.

So one Grok dispatch is driven through the real ``ControlRuntime`` with the same
secret planted on stdout, on stderr, and where a version belongs -- three
different roads into the transport -- and every string value of every durable
record and every API response is searched for it.

The same run is where the exact argv and environment are read back from the
child, because those are facts about a REAL dispatch rather than about an
adapter driven directly: the four privacy switches, the per-attempt home, and
``--no-auto-update`` all have to survive the whole runtime path, not just the
adapter's own.
"""
from __future__ import annotations

import json
from pathlib import Path

from conductor.command.adapters import AdapterRegistry
from conductor.command.adapters.grok_build import (
    GROK_FORCED_ENV,
    REVIEWED_GROK_VERSION,
    GROK_HOME_ENV,
    HOME_DIR,
)
from conductor.command.contracts import ActionProposal, RunEnvelope
from conductor.command.http_api import CommandApi, CommandSession
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.runtime import Budget, Confirmation, ControlRuntime

from tests import _fakegrok
from tests.test_command_grok_transport import NOW, a_harness, a_request

SECRET = "sk-live-planted-grok-secret-value"
RUN_ID = "run-grok-leak"
INSTANCE = "grok-dev"
PORT, TOKEN = 8899, "token-grok-leak"
CONFIG = {
    "cycle": {"id": "grok-orbit", "phases": ["dispatch"]},
    "instances": [{"id": INSTANCE, "adapter": "grok-build"}],
}
ARGUMENTS = {
    "work_item_id": "work-001", "instruction_ref": "instr-001",
    "profile": "implement", "artifact_refs": [],
    "output_limit_profile": "normal"}


def _ids():
    counters: dict[str, int] = {}

    def mint(purpose):
        counters[purpose] = counters.get(purpose, 0) + 1
        return f"{purpose}-{counters[purpose]}"

    return mint


def _strings(document) -> set[str]:
    """Every string VALUE in a document, keys excluded.

    A key and a value fail differently: ``detail`` is a key a receipt must carry,
    and the secret is a value nothing may.
    """
    if isinstance(document, dict):
        return {word for item in document.values() for word in _strings(item)}
    if isinstance(document, (list, tuple)):
        return {word for item in document for word in _strings(item)}
    return {document} if isinstance(document, str) else set()


def _driven(tmp_path: Path, **knobs: str):
    """One Grok dispatch through the real runtime, plus the API over the same store."""
    adapter, root, log = a_harness(tmp_path / "harness", **knobs)
    store = RunStore(root)
    store.create_run(
        RunEnvelope(
            run_id=RUN_ID, cycle_id="grok-orbit", created_at=NOW,
            config_digest=snapshot_digest(CONFIG), mode="confirm"),
        CONFIG)
    proposal = ActionProposal(
        proposal_id="proposal-grok", run_id=RUN_ID, attempt_id="attempt-grok",
        instance_id=INSTANCE, capability="dispatch", arguments=ARGUMENTS,
        scope=("work",), proposed_by="lane", proposed_at=NOW,
        timeout_seconds=60,
        rationale="drive Grok Build through the real Confirm runtime",
        config_digest=snapshot_digest(CONFIG))
    store.append(proposal)
    registry = AdapterRegistry([adapter])
    runtime = ControlRuntime(store, registry, clock=lambda: NOW, ids=_ids())
    confirmation = Confirmation(
        confirmation_id="confirmation-grok", run_id=RUN_ID,
        proposal_id=proposal.proposal_id,
        preview_digest=proposal.preview_digest, capability="dispatch",
        scope=("work",), config_digest=proposal.config_digest,
        confirmed_by="release-owner", confirmed_at=NOW)
    authorization = runtime.authorize(
        confirmation,
        budget=Budget(max_actions=8, max_action_seconds=3600,
                      max_confirmation_age_seconds=3600))
    attempt = runtime.execute(authorization)
    api = CommandApi(
        store, registry, session=CommandSession(PORT, TOKEN),
        budget=Budget(max_actions=8, max_action_seconds=3600,
                      max_confirmation_age_seconds=3600),
        clock=lambda: NOW, ids=_ids(), publish_run=lambda _run: None)
    return attempt, store, api, root, log


def _journal_records(store) -> list[tuple[str, dict]]:
    """Every durable record as (kind, fields).

    A `StoredRecord` carries `kind` and `value`, and the VALUE is the typed
    record -- so reading `record.as_dict()` finds nothing and falls back to a
    repr, which searches the same bytes far more weakly. Reading the value is
    what makes the search structured.
    """
    rows: list[tuple[str, dict]] = []
    for record in store.read(RUN_ID).records:
        value = record.value
        fields = value.as_dict() if hasattr(value, "as_dict") else {}
        rows.append((record.kind, dict(fields)))
    return rows


def _journal_strings(store) -> set[str]:
    """Every string value in every durable record of the run."""
    found: set[str] = set()
    for kind, fields in _journal_records(store):
        found.add(kind)
        found |= _strings(fields)
        found.add(json.dumps(fields, sort_keys=True, default=str))
    return found


#: The GET routes that really exist and really carry this run outward. Named
#: rather than guessed: a route that 404s contributes an error body and nothing
#: else, so searching one would be searching for a secret in a refusal.
READ_ROUTES = ("", "/controls")


def _api_strings(api) -> tuple[set[str], dict[str, int]]:
    """Every string an authorized reader gets back, and the status of each route."""
    found: set[str] = set()
    statuses: dict[str, int] = {}
    headers = (
        ("authorization", f"Bearer {TOKEN}"), ("host", f"127.0.0.1:{PORT}"))
    for suffix in READ_ROUTES:
        route = f"/command/runs/{RUN_ID}{suffix}"
        response = api.handle("GET", route, headers, b"")
        statuses[route] = response.status
        payload = dict(response.payload)
        found |= _strings(payload)
        found.add(json.dumps(payload, sort_keys=True, default=str))
    return found, statuses


def _served(api) -> set[str]:
    """The API strings, with a positive control that the surface is REAL.

    Without this a route rename would quietly reduce every assertion below to a
    search through 404 bodies, and the tests would stay green while covering
    nothing.
    """
    found, statuses = _api_strings(api)
    assert set(statuses.values()) == {200}, f"THE_API_SURFACE_IS_NOT_REAL={statuses}"
    assert RUN_ID in found, "the API did not name the run it was asked about"
    assert any("action_result" in value for value in found), (
        "the API served no result record, so the journal was not projected")
    return found


def test_a_secret_the_child_prints_reaches_no_receipt_journal_record_or_api(
        tmp_path):
    """Three roads in, three surfaces checked, one string that may appear on none."""
    attempt, store, api, _root, _log = _driven(
        tmp_path, FAKEGROK_STDOUT=SECRET, FAKEGROK_STDERR=SECRET)

    receipt_strings = _strings(
        attempt.receipt.as_dict() if hasattr(attempt.receipt, "as_dict")
        else repr(attempt.receipt))
    receipt_strings.add(repr(attempt.receipt))
    journal = _journal_strings(store)
    served = _served(api)

    assert journal, "no durable record was read, so this proved nothing"
    for surface, strings in (
            ("receipt", receipt_strings), ("journal", journal), ("api", served)):
        leaked = sorted(value for value in strings if SECRET in value)
        assert leaked == [], f"SECRET_REACHED_{surface.upper()}={leaked}"


def test_a_secret_planted_where_a_version_belongs_reaches_none_of_them(tmp_path):
    """The refusal road: the token is compared, never carried, not even in a refusal."""
    attempt, store, api, _root, log = _driven(
        tmp_path, FAKEGROK_VERSION=SECRET)

    assert _fakegrok.prompt_spawns(log) == [], "a prompt ran on an unreviewed build"
    for surface, strings in (
            ("journal", _journal_strings(store)), ("api", _served(api))):
        leaked = sorted(value for value in strings if SECRET in value)
        assert leaked == [], f"SECRET_REACHED_{surface.upper()}={leaked}"
    assert SECRET not in repr(attempt.receipt)


def test_the_journal_carries_the_runtimes_own_words_and_not_the_adapters(tmp_path):
    """WHY the two surfaces above are safe, stated instead of assumed.

    A mutation that echoed the observed version token into the transport's
    refusal left those assertions green, and the reason was not that the
    transport held. The durable `action_result` record IS a receipt and it DOES
    carry a `detail`, so the channel exists -- but the RUNTIME substitutes its
    own sentence for the adapter's on this road, so adapter prose never travels
    it. Protection by substitution, not by absence.

    That is a real second line of defence and it is not the transport's. The
    transport's own claim is falsifiable where the transport owns the object:
    `test_a_secret_planted_where_a_version_belongs_never_reaches_a_receipt` in
    the transport suite reads the receipt the adapter itself returned, and reds
    under exactly that mutation. This test holds the substitution, so a runtime
    that ever began forwarding adapter detail would be caught HERE and the
    reader would know which of the two protections had changed.
    """
    adapter, _root, _log = a_harness(tmp_path / "direct", FAKEGROK_VERSION=SECRET)
    direct = adapter.execute(adapter.prepare(a_request()))
    _attempt, store, _api, _r, _l = _driven(tmp_path / "run", FAKEGROK_VERSION=SECRET)

    results = [fields for kind, fields in _journal_records(store)
               if kind == "action_result"]
    assert len(results) == 1, f"EXPECTED_ONE_RESULT_RECORD={len(results)}"
    journalled = results[0].get("detail")
    assert journalled, "the durable result record carries no detail at all"
    assert REVIEWED_GROK_VERSION in direct.detail, (
        "the adapter's own refusal stopped naming the reviewed version, so this "
        "test no longer compares two different sentences")
    assert journalled != direct.detail, (
        "THE_RUNTIME_NOW_FORWARDS_ADAPTER_DETAIL -- the journal and API "
        "assertions above rest on substitution, so re-derive them")
    assert REVIEWED_GROK_VERSION not in journalled, (
        f"adapter prose reached the journal: {journalled!r}")


def test_the_real_runtime_path_still_sends_the_exact_argv_and_environment(tmp_path):
    """The argv and env facts, read off a dispatch the RUNTIME drove.

    The transport suite reads these from an adapter it drove itself. Driving the
    whole runtime is what proves nothing between authorization and the spawn
    rewrites them -- and it is the only place the four privacy switches, the
    per-attempt home and ``--no-auto-update`` are all observed together on a
    dispatch a caller could really have asked for.
    """
    _attempt, _store, _api, root, log = _driven(tmp_path)

    spawns = _fakegrok.spawns(log)
    assert len(spawns) == 2, f"EXPECTED_PREFLIGHT_AND_PROMPT={len(spawns)}"
    preflight, prompt = spawns
    assert preflight["argv"] == ["--version"]
    assert prompt["argv"][:4] == [
        "--no-auto-update", "--output-format", "plain", "--single"]
    assert len(prompt["argv"]) == 5

    expected_switches = {name: "0" for name, _value in GROK_FORCED_ENV}
    homes = []
    for row in spawns:
        assert row["switches"] == expected_switches, (
            f"SWITCH_NOT_OFF={row['switches']}")
        assert row["env_names"].count(GROK_HOME_ENV) == 1
        homes.append(row["grok_home"])
    assert len(set(homes)) == 2, "TWO_SPAWNS_SHARED_ONE_HOME=True"
    for home in homes:
        assert Path(home).parent == (root / HOME_DIR).resolve()
    standing = sorted(path.name for path in (root / HOME_DIR).iterdir())
    assert standing == [], f"HOME_SURVIVED_THE_RUNTIME_PATH={standing}"
