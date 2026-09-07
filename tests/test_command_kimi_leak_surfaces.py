"""Neither an allowed credential nor a byte the child printed reaches a RAW surface.

The transport suite already holds that a planted secret misses the receipt and
the verification. That is a search through four in-memory strings, and it is the
smallest question this build has to answer: between the adapter and a reader sit
surfaces that OUTLIVE the process -- the journal appended to disk, the bytes a
real server writes to a real socket, and the frames pushed to every attached
listener. A secret that reached one of those would be retained and served, and
no receipt assertion would have said so.

So this file asks the question Claude, Codex and Grok are already asked, of the
same shape of provider Grok is -- dispatch-only, argv-channel, no review road --
and it asks it of BYTES rather than of parsed objects: a search through a decoded
structure only finds what the decoder chose to expose.

Six surfaces, each read in the form it really travels in:

- the journal, as the bytes actually appended to ``records.jsonl``;
- the HTTP response, as the bytes a REAL loopback server wrote to a REAL socket
  and a client read back off it. Calling the encoder and searching what it
  returned would test the encoder a test chose rather than the path the product
  serves -- a header, a second body, or a route answering from somewhere else
  would all be invisible to it;
- the SSE frames, as the bytes a client actually received on ``/events``,
  including one the server's OWN publisher pushed while that client listened;
- the response HEADERS, because a body is not the only thing a response carries
  and a search that decoded the payload first would never look at one;
- the fake's spawn log, because a test artefact that stored a hunted string
  would be a leak this suite created rather than found;
- the receipt, and the adapter's own words -- the receipt and the verification
  the adapter handed the runtime in THIS run, intercepted where it handed them
  over. The attempt receipt a reader sees is the RUNTIME's, so a search of it
  alone would never notice an adapter that started naming a credential in its
  own refusal; the runtime would simply have substituted its sentence for the
  leaking one.

Three strings are hunted, and they enter by three different roads. The
CREDENTIAL is one an operator legitimately allows through ``env_allow``: Kimi
Code reads no keychain in this build's isolated home, and Moonshot documents the
``KIMI_MODEL_*`` family as the one explicit channel that does read a credential
from the shell, so a real deployment must pass one and it is genuinely in the
child's environment during these runs. The PRINTED secret is what the child
writes to stdout and stderr. The third is the same string planted where a
VERSION belongs, which is the refusal road: the token is compared and never
carried, not even into the sentence that refuses.

Both spellings of the credential matter and they are asserted differently. The
VALUE may appear nowhere at all. The NAME may appear in exactly one place -- the
child's own environment, which is what the operator asked for -- and nowhere
that persists or is served.

Nothing here is expected to be red on a clean tree, and that is the point: this
is the parity Grok has and Kimi did not. What each test buys is what it would
say if a future change made one of these surfaces start carrying what the child
was handed.
"""
from __future__ import annotations

import json
import threading
import urllib.request
from contextlib import contextmanager
from pathlib import Path

from conductor import server
from conductor.command.adapters import AdapterRegistry
from conductor.command.adapters.kimi_code import (
    HOME_DIR,
    KIMI_HOME_ENV,
    KIMI_TELEMETRY_ENV,
    REVIEWED_KIMI_VERSION,
)
from conductor.command.contracts import ActionProposal, RunEnvelope
from conductor.command.run_store import snapshot_digest
from conductor.command.runtime import Budget, Confirmation, ControlRuntime

from tests import _fakekimi
from tests.test_command_kimi_transport import NOW, a_harness, a_request, run_once
from tests.test_store import good_lane, write_project

#: The one credential channel the vendor documents as reading the shell, so an
#: operator's `env_allow` naming it is a real deployment and not a contrivance.
CREDENTIAL_ENV = "KIMI_MODEL_API_KEY"
#: Shaped like a real key and valid nowhere. It is really placed in the child's
#: environment through a real `env_allow`, because a key that never reached the
#: child would make every absence below vacuous.
CREDENTIAL = "sk-kimi-SYNTHETIC-NEVER-REAL-0000000000000000"
#: What the child writes to stdout and to stderr, and what it prints where a
#: version belongs. One string for three roads, so a hit names the road.
PRINTED = "PRINTED-BY-THE-CHILD-kimi-a1b2c3d4e5f60718"
RUN_ID = "run-kimi-leak"
INSTANCE = "kimi-dev"
CONFIG = {
    "cycle": {"id": "kimi-orbit", "phases": ["dispatch"]},
    "instances": [{"id": INSTANCE, "adapter": "kimi-code"}],
}
ARGUMENTS = {
    "work_item_id": "work-001", "instruction_ref": "instr-001",
    "profile": "implement", "artifact_refs": [],
    "output_limit_profile": "normal"}
#: The change the child leaves behind, so this dispatch is a run that really did
#: something. The text carries none of the hunted strings.
WRITTEN = "guard.py:the guard the task asked for"


def _ids():
    counters: dict[str, int] = {}

    def mint(purpose):
        counters[purpose] = counters.get(purpose, 0) + 1
        return f"{purpose}-{counters[purpose]}"

    return mint


def _dispatched(store, srv):
    """Drive a current bound dispatch, not an old pending proposal's refusal."""
    proposal = ActionProposal(
        proposal_id="proposal-kimi", run_id=RUN_ID, attempt_id="attempt-kimi",
        instance_id=INSTANCE, capability="dispatch", arguments=ARGUMENTS,
        scope=("work",), proposed_by="lane", proposed_at=NOW,
        timeout_seconds=60,
        rationale="drive Kimi Code through the real Confirm runtime",
        config_digest=snapshot_digest(CONFIG), input_binding="proposal-v1")
    store.append(proposal)
    confirmation = Confirmation(
        confirmation_id="confirmation-kimi", run_id=RUN_ID,
        proposal_id=proposal.proposal_id,
        preview_digest=proposal.preview_digest, capability="dispatch",
        scope=("work",), config_digest=proposal.config_digest,
        confirmed_by="release-owner", confirmed_at=NOW)
    budget = Budget(max_actions=8, max_action_seconds=3600,
                    max_confirmation_age_seconds=3600)
    runtime = ControlRuntime(
        store, srv.command_registry, clock=lambda: NOW, ids=_ids())
    return runtime.execute(runtime.authorize(confirmation, budget=budget))


def _overheard(adapter) -> list[str]:
    """Capture what the ADAPTER itself said, where it says it to the runtime.

    The runtime substitutes its own sentence for the adapter's on this road, so
    the attempt receipt a reader sees carries runtime prose whatever the adapter
    answered. That protection is real and is held by its own test below -- but a
    suite that searched only the substituted words could never see an adapter
    that began naming a credential in a refusal. This is the same object the
    registry handed onward, read as it was handed over rather than rebuilt by a
    second run that might not have refused the same way.
    """
    said: list[str] = []
    real_execute, real_verify = adapter.execute, adapter.verify

    def watched_execute(*args, **kwargs):
        receipt = real_execute(*args, **kwargs)
        said.append(json.dumps(
            receipt.as_dict() if hasattr(receipt, "as_dict") else {},
            sort_keys=True, default=str))
        said.append(repr(receipt))
        return receipt

    def watched_verify(*args, **kwargs):
        verification = real_verify(*args, **kwargs)
        said.append(repr(verification))
        return verification

    adapter.execute = watched_execute
    adapter.verify = watched_verify
    return said


@contextmanager
def _served(tmp_path: Path, **knobs: str):
    """One Kimi dispatch, and a REAL loopback server over the same project.

    The provider resolves against the SERVED root, so the instruction the child
    reads and the journal the routes project are the same tree -- not two trees
    that happen to agree.
    """
    adapter, root, log = a_harness(
        tmp_path / "harness",
        **{_fakekimi.WRITE_FILE: WRITTEN, CREDENTIAL_ENV: CREDENTIAL, **knobs})
    said = _overheard(adapter)
    write_project(root, lanes={"claude": good_lane()})
    srv = server.build(
        root, port=0, registry=AdapterRegistry([adapter]), clock=lambda: NOW)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        store = srv.command_store
        store.create_run(
            RunEnvelope(
                run_id=RUN_ID, cycle_id="kimi-orbit", created_at=NOW,
                config_digest=snapshot_digest(CONFIG), mode="confirm"),
            CONFIG)
        yield _dispatched(store, srv), store, srv, base, log, root, said
    finally:
        srv.shutdown()
        srv.server_close()


#: The GET routes that really exist and really carry this run outward. Named
#: rather than guessed: a route that 404s contributes an error body and nothing
#: else, so searching one would be searching for a secret in a refusal.
READ_ROUTES = ("", "/controls")


def _journal_bytes(store) -> bytes:
    """The durable record file exactly as it sits on disk."""
    path = Path(store.run_path(RUN_ID)) / "records.jsonl"
    raw = path.read_bytes()
    assert raw, "the journal is empty, so searching it proves nothing"
    return raw


def _journal_records(store) -> list[tuple[str, dict]]:
    """Every durable record as (kind, fields), for the one test that needs both.

    A `StoredRecord` carries `kind` and `value`, and the VALUE is the typed
    record -- so reading `record.as_dict()` finds nothing and falls back to a
    repr, which searches the same bytes far more weakly.
    """
    rows: list[tuple[str, dict]] = []
    for record in store.read(RUN_ID).records:
        value = record.value
        fields = value.as_dict() if hasattr(value, "as_dict") else {}
        rows.append((record.kind, dict(fields)))
    return rows


def _off_the_socket(base: str) -> dict[str, bytes]:
    """Each route's response as a client really read it off the wire.

    Body AND headers, because a body is not the only thing a response carries
    and a search that decoded the payload first would never see a header at all.
    """
    bodies: dict[str, bytes] = {}
    for suffix in READ_ROUTES:
        route = f"/command/runs/{RUN_ID}{suffix}"
        call = urllib.request.Request(
            base + route, headers={"Host": base.removeprefix("http://")})
        with urllib.request.urlopen(call, timeout=10) as answer:
            assert answer.status == 200, f"THE_API_SURFACE_IS_NOT_REAL={route}"
            head = "\n".join(f"{k}: {v}" for k, v in answer.headers.items())
            bodies[f"api{route}"] = answer.read()
            bodies[f"headers{route}"] = head.encode("utf-8")
    return bodies


#: Stop on FRAMES, not on a line count: a stream with nothing more to say leaves
#: the next `readline` blocking until its socket timeout, and a fixed number of
#: lines is a guess about a framing this test does not own. The line bound is a
#: backstop so a stream that speaks only blank lines still cannot hang the suite.
_FRAMES_WANTED = 2
_LINE_BOUND = 12


def _frames_off_the_stream(srv, base: str) -> bytes:
    """What a listener really receives on /events, pushed by the real publisher.

    The dispatch above runs through the runtime rather than through an HTTP
    write route, so nothing has published a run signal yet. This asks the
    SERVER'S OWN publisher for one -- the same call the API makes -- so the frame
    that arrives is the product's, travelling the product's socket, rather than
    a byte string this test built to look like one.
    """
    stream = urllib.request.urlopen(base + "/events", timeout=10)
    try:
        seen = stream.readline()
        srv.clients.publish_run(RUN_ID)
        frames = 1
        for _ in range(_LINE_BOUND):
            if frames >= _FRAMES_WANTED:
                break
            line = stream.readline()
            if not line:
                break
            seen += line
            if line.startswith(b"data: "):
                frames += 1
        return seen
    finally:
        stream.close()


def _surfaces(tmp_path: Path, **knobs: str):
    """Every raw surface one real dispatch produced, keyed by name."""
    with _served(tmp_path, **knobs) as (
            attempt, store, srv, base, log, root, said):
        receipt = attempt.receipt
        surfaces = {
            "journal": _journal_bytes(store),
            "sse-frames": _frames_off_the_stream(srv, base),
            "spawn-log": Path(log).read_bytes(),
            "attempt-receipt": json.dumps(
                receipt.as_dict() if hasattr(receipt, "as_dict") else {},
                sort_keys=True, default=str).encode("utf-8")
            + repr(receipt).encode(),
            "adapter-words": "\n".join(said).encode("utf-8"),
        }
        surfaces.update(_off_the_socket(base))
        return surfaces, attempt, root


def _rows(raw: bytes) -> list[dict]:
    """The spawn log, parsed back out of the bytes this suite searched."""
    return [json.loads(line) for line in raw.decode("utf-8").splitlines()
            if line.strip()]


def test_the_dispatch_this_suite_searches_really_ran_and_really_was_served(
        tmp_path):
    """The positive control, first, so every absence below means something.

    A run that never spawned, never reached the journal, or was never projected
    outward would make each search clean for reasons that have nothing to do
    with containment. So the child's own two lines are counted, the file it
    wrote is found on disk, the credential is read back out of the environment
    it really ran in, and the run is confirmed to have travelled all the way to
    a socket and to a listener.
    """
    surfaces, _attempt, root = _surfaces(tmp_path)

    rows = _rows(surfaces["spawn-log"])
    assert len(rows) == 2, f"EXPECTED_PREFLIGHT_AND_PROMPT={len(rows)}"
    preflight, prompt = rows
    assert preflight["argv"] == ["--version"]
    assert prompt["argv"][:3] == ["--output-format", "text", "--prompt"]
    assert len(prompt["argv"]) == 4, f"UNEXPECTED_ARGV={prompt['argv']}"
    assert (root / "work" / "work-001" / "guard.py").is_file(), (
        "the child changed nothing, so this run did no work")
    for row in rows:
        assert CREDENTIAL_ENV in row["env_names"], (
            "the credential never reached the child, so its absence elsewhere "
            "is vacuous")
    # Two spawns, two homes, and nothing of either left standing afterwards.
    homes = [row["kimi_home"] for row in rows]
    assert len(set(homes)) == 2, "TWO_SPAWNS_SHARED_ONE_HOME=True"
    for home in homes:
        assert Path(home).parent == (root / HOME_DIR).resolve()
    assert sorted(path.name for path in (root / HOME_DIR).iterdir()) == []
    assert RUN_ID.encode() in surfaces["journal"], (
        "the journal did not record the run")
    assert b"action_result" in surfaces[f"api/command/runs/{RUN_ID}"], (
        "the API served no result record, so the journal was not projected")
    assert RUN_ID.encode() in surfaces["sse-frames"], (
        "no frame about this run reached a listener")
    assert surfaces["adapter-words"], "the adapter was never overheard at all"


def test_an_allowed_credential_reaches_no_raw_surface(tmp_path):
    """The key is really in the child's environment, and in nothing that persists.

    Forwarding a secret to a child is what an operator asked for. Writing it
    down is not, and every surface here either outlives the process that held it
    or is delivered to somebody who never asked.
    """
    surfaces, _attempt, _root = _surfaces(tmp_path)

    leaked = sorted(
        name for name, raw in surfaces.items() if CREDENTIAL.encode() in raw)

    assert leaked == [], f"THE_CREDENTIAL_REACHED={leaked}"


def test_the_credential_name_reaches_the_child_and_no_other_surface(tmp_path):
    """A name and a value fail differently, so they are asserted differently.

    The NAME is what the operator wrote in durable config and what this build
    must hand the child, so finding it in the child's own environment is the
    proof that the allowlist worked. Everywhere else it is a disclosure of what
    this deployment is configured to hold -- and a surface that had begun
    carrying names would be one spelling away from carrying values.
    """
    surfaces, _attempt, _root = _surfaces(tmp_path)

    rows = _rows(surfaces["spawn-log"])
    assert rows and all(CREDENTIAL_ENV in row["env_names"] for row in rows), (
        "the name never reached the child, so this test compares nothing")
    leaked = sorted(
        name for name, raw in surfaces.items()
        if name != "spawn-log" and CREDENTIAL_ENV.encode() in raw)

    assert leaked == [], f"THE_CREDENTIAL_NAME_REACHED={leaked}"


def test_a_secret_the_child_prints_reaches_no_raw_surface(tmp_path):
    """Bounded, drained and dropped: raw child output is never carried onward."""
    surfaces, _attempt, _root = _surfaces(
        tmp_path, FAKEKIMI_STDOUT=PRINTED, FAKEKIMI_STDERR=PRINTED)

    leaked = sorted(
        name for name, raw in surfaces.items() if PRINTED.encode() in raw)

    assert leaked == [], f"THE_PRINTED_SECRET_REACHED={leaked}"


def test_a_secret_planted_where_a_version_belongs_reaches_no_raw_surface(
        tmp_path):
    """The refusal road: the token is compared, never carried, not even in a refusal.

    This is the one road where the child's bytes are read by this build rather
    than merely drained, so it is the road where a careless sentence would most
    plausibly repeat them.
    """
    surfaces, _attempt, _root = _surfaces(tmp_path, FAKEKIMI_VERSION=PRINTED)

    rows = _rows(surfaces["spawn-log"])
    assert [row for row in rows if row["argv"][:1] != ["--version"]] == [], (
        "a prompt ran on an unreviewed build")
    leaked = sorted(
        name for name, raw in surfaces.items() if PRINTED.encode() in raw)

    assert leaked == [], f"THE_VERSION_TOKEN_REACHED={leaked}"


def test_the_surfaces_still_carry_the_identifiers_a_reader_needs(tmp_path):
    """The over-correction control: absence is only a virtue where it is chosen.

    Every test above is satisfied by a surface that carries nothing at all, so a
    scrubber applied one layer too wide -- a journal that stopped naming the
    run, a route that stopped projecting the result, a spawn log that stopped
    recording the argv -- would leave them all green while destroying the thing
    they protect. What each surface owes is asserted here, positively.
    """
    surfaces, _attempt, _root = _surfaces(tmp_path)

    journal = surfaces["journal"]
    for owed in (RUN_ID, INSTANCE, "dispatch", "action_result", "attempt_event"):
        assert owed.encode() in journal, f"THE_JOURNAL_LOST={owed}"
    served = surfaces[f"api/command/runs/{RUN_ID}"]
    for owed in (RUN_ID, INSTANCE):
        assert owed.encode() in served, f"THE_API_LOST={owed}"
    log = surfaces["spawn-log"]
    for owed in ("--prompt", "--output-format", KIMI_HOME_ENV,
                 KIMI_TELEMETRY_ENV):
        assert owed.encode() in log, f"THE_SPAWN_LOG_LOST={owed}"
    rows = _rows(log)
    assert all(row["telemetry_disabled"] == "1" for row in rows), (
        f"TELEMETRY_NOT_DISABLED={[row['telemetry_disabled'] for row in rows]}")


def test_the_journal_carries_the_runtimes_own_words_and_not_the_adapters(
        tmp_path):
    """WHY four of the six surfaces are safe, stated instead of assumed.

    The durable `action_result` record IS a receipt and it DOES carry a
    `detail`, so the channel exists -- but the RUNTIME substitutes its own
    sentence for the adapter's on this road, and adapter prose therefore never
    travels it. Protection by substitution, not by absence.

    That is a real second line of defence and it is not the adapter's. Held here
    so that a runtime which ever began forwarding adapter detail is caught by a
    test whose message says which of the two protections changed, rather than by
    a leak search that reds for a reason nobody can name.
    """
    adapter, _root, _log = a_harness(tmp_path / "direct", FAKEKIMI_VERSION=PRINTED)
    direct = run_once(adapter, a_request())
    with _served(tmp_path / "run", FAKEKIMI_VERSION=PRINTED) as (
            _attempt, store, _srv, _base, _log2, _root2, _said):
        results = [fields for kind, fields in _journal_records(store)
                   if kind == "action_result"]

    assert len(results) == 1, f"EXPECTED_ONE_RESULT_RECORD={len(results)}"
    journalled = results[0].get("detail")
    assert journalled, "the durable result record carries no detail at all"
    assert REVIEWED_KIMI_VERSION in direct.detail, (
        "the adapter's own refusal stopped naming the reviewed version, so this "
        "test no longer compares two different sentences")
    assert journalled != direct.detail, (
        "THE_RUNTIME_NOW_FORWARDS_ADAPTER_DETAIL -- the journal and API "
        "assertions above rest on substitution, so re-derive them")
    assert REVIEWED_KIMI_VERSION not in journalled, (
        f"adapter prose reached the journal: {journalled!r}")


def test_the_spawn_log_stores_names_and_booleans_and_never_a_value(tmp_path):
    """The witness may not become the thing it witnesses against.

    A log that stored the environment would store the credential the operator
    allowed, on a machine that has a real one and in a file nothing sweeps. What
    it may hold is the shape of the spawn -- an argv this build owns, the paths
    it minted, the NAMES it forwarded -- and two booleans about a probe whose
    value is a constant both sides already know.
    """
    surfaces, _attempt, _root = _surfaces(tmp_path)

    rows = _rows(surfaces["spawn-log"])
    for row in rows:
        assert set(row) == {
            "argv", "argv0", "executable", "cwd", "kimi_home",
            "telemetry_disabled", "env_names", "probe"}, sorted(row)
        assert set(row["probe"]) == {"in_names", "in_values"}
        assert all(isinstance(value, bool) for value in row["probe"].values())
        assert CREDENTIAL not in json.dumps(row), (
            "the spawn log stored an environment VALUE")
