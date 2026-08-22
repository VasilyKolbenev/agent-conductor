"""Neither the operator's instruction nor a credential reaches any RAW surface.

The transport suite already holds that a receipt carries no child output. This
file asks a harder question of a wider set, and it asks it of BYTES rather than
of parsed objects: a search through a decoded structure only finds what the
decoder chose to expose, and every surface below is ultimately a byte string
that leaves this process.

Five surfaces, and each is read in the form it really travels in:

- the journal, as the bytes actually appended to ``records.jsonl``;
- the HTTP response, as the bytes a REAL loopback server wrote to a REAL socket
  and a client read back off it. An earlier version of this file called the
  encoder itself and searched what it returned, which tests the encoder the test
  chose rather than the path the product serves -- a header, a second body, or a
  route that answered from somewhere else would all have been invisible to it;
- the SSE frames, as the bytes a client actually received on ``/events``,
  including one the server's OWN publisher pushed while that client listened;
- the response HEADERS, because a body is not the only thing a response carries
  and a search that decoded the payload first would never look at one;
- the fake's spawn log, because a test artefact that stored either string would
  be a leak this suite created rather than found;
- the receipt and its refusal text.

Two strings are hunted, and they enter by different roads. The PROBE TOKEN is
the operator's own prose: it arrives only inside the piped task, so a hit
anywhere else is the instruction escaping the channel chosen to contain it. The
API KEY is a credential an operator legitimately allows through ``env_allow`` --
Claude Code in bare mode reads no keychain, so a real deployment must pass one --
and it is therefore really in the child's environment during these runs. A
surface holding it would be retaining a secret this build was merely asked to
forward.

The SSE frames get one extra assertion of their own: every frame's vocabulary is
closed and every value is an identifier. A frame is a push, so anything it names
is delivered to every attached listener without anyone asking for it, and no
route-level test would notice a field growing there because no route serves it.
"""
from __future__ import annotations

import json
import threading
import urllib.request
from contextlib import contextmanager
from pathlib import Path

from conductor import server
from conductor.command.adapters import AdapterRegistry
from conductor.command.contracts import ActionProposal, RunEnvelope
from conductor.command.run_store import snapshot_digest
from conductor.command.runtime import Budget, Confirmation, ControlRuntime

from tests import _fakeclaude
from tests.test_command_claude_transport import NOW, a_harness
from tests.test_store import good_lane, write_project

#: The operator's prose, in the closed probe form the child can recognise.
PROBE = _fakeclaude.PROBE_PREFIX + "beef1234" * 8
#: A credential shaped like a real one and valid nowhere. It is really placed in
#: the child's environment through a real `env_allow`, because a key that never
#: reached the child would make every assertion below vacuous.
API_KEY = "sk-ant-api03-SYNTHETIC-NEVER-REAL-0000000000"
RUN_ID = "run-claude-leak"
INSTANCE = "claude-dev"
CONFIG = {
    "cycle": {"id": "claude-orbit", "phases": ["dispatch"]},
    "instances": [{"id": INSTANCE, "adapter": "claude-code"}],
}
ARGUMENTS = {
    "work_item_id": "work-001", "instruction_ref": "instr-001",
    "profile": "implement", "artifact_refs": ["art-001"],
    "output_limit_profile": "normal"}


def _ids():
    counters: dict[str, int] = {}

    def mint(purpose):
        counters[purpose] = counters.get(purpose, 0) + 1
        return f"{purpose}-{counters[purpose]}"

    return mint


def _dispatched(store, srv):
    """Propose, confirm and execute one dispatch through the real runtime."""
    proposal = ActionProposal(
        proposal_id="proposal-claude", run_id=RUN_ID,
        attempt_id="attempt-claude", instance_id=INSTANCE,
        capability="dispatch", arguments=ARGUMENTS, scope=("work",),
        proposed_by="lane", proposed_at=NOW, timeout_seconds=60,
        rationale="drive Claude Code through the real Confirm runtime",
        config_digest=snapshot_digest(CONFIG))
    store.append(proposal)
    confirmation = Confirmation(
        confirmation_id="confirmation-claude", run_id=RUN_ID,
        proposal_id=proposal.proposal_id,
        preview_digest=proposal.preview_digest, capability="dispatch",
        scope=("work",), config_digest=proposal.config_digest,
        confirmed_by="release-owner", confirmed_at=NOW)
    budget = Budget(max_actions=8, max_action_seconds=3600,
                    max_confirmation_age_seconds=3600)
    runtime = ControlRuntime(
        store, srv.command_registry, clock=lambda: NOW, ids=_ids())
    return runtime.execute(runtime.authorize(confirmation, budget=budget))


@contextmanager
def _served(tmp_path: Path):
    """One Claude dispatch, and a REAL loopback server over the same project.

    The provider resolves against the SERVED root, so the instruction the child
    reads and the journal the routes project are the same tree -- not two trees
    that happen to agree.
    """
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    adapter, _root, log = a_harness(
        tmp_path / "harness", root=root,
        instruction=f"Add the missing guard and prove it. {PROBE}",
        **{_fakeclaude.LEAK_CHECK: "1", "ANTHROPIC_API_KEY": API_KEY,
           # A real coding run leaves a change behind, and this suite needs one:
           # a dispatch that touched nothing is `verification_failed` under this
           # build's law. The written text carries neither hunted string.
           _fakeclaude.WRITE_FILE: "guard.py:the guard the task asked for"})
    srv = server.build(
        root, port=0, registry=AdapterRegistry([adapter]), clock=lambda: NOW)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        store = srv.command_store
        store.create_run(
            RunEnvelope(
                run_id=RUN_ID, cycle_id="claude-orbit", created_at=NOW,
                config_digest=snapshot_digest(CONFIG), mode="confirm"),
            CONFIG)
        yield _dispatched(store, srv), store, srv, base, log, root
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


def _off_the_socket(base: str) -> dict[str, bytes]:
    """Each route's response as a client really read it off the wire.

    Status AND body, because a body is not the only thing a response carries and
    a search that decoded the payload first would never see a header at all.
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
        # The greeting arrives on connect; the run signal has to be asked for,
        # because this dispatch went through the runtime rather than an HTTP
        # write route. Both are then read off the same socket.
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


def _surfaces(tmp_path: Path):
    """Every raw surface one real dispatch produced, keyed by name."""
    with _served(tmp_path) as (attempt, store, srv, base, log, root):
        receipt = attempt.receipt
        surfaces = {
            "journal": _journal_bytes(store),
            "sse-frames": _frames_off_the_stream(srv, base),
            "spawn-log": Path(log).read_bytes(),
            "receipt": json.dumps(
                receipt.as_dict() if hasattr(receipt, "as_dict") else {},
                sort_keys=True, default=str).encode("utf-8")
            + repr(receipt).encode(),
        }
        surfaces.update(_off_the_socket(base))
        return surfaces, attempt, root


def test_the_dispatch_this_suite_searches_really_ran_and_really_delivered(tmp_path):
    """The positive control, first, so every absence below means something.

    A run that never spawned, never piped, or never reached the journal would
    make each search below trivially clean. So the child's own witness is read:
    it saw the probe token in its stdin and nowhere else, which is both proof
    that the dispatch happened and proof that the leak scan was performed.
    """
    surfaces, attempt, root = _surfaces(tmp_path)

    # `verification_failed` is the CEILING for every real provider in this
    # build, not a failure of this dispatch: the transport's verifier reads a
    # real change under the authorized subtree and then refuses to call it a
    # verified success, because no durable evidence record is written for it
    # yet. Asserting `succeeded` here would be asserting a state no headless
    # provider can reach, and the day one can, this line is where that shows.
    assert attempt.receipt.outcome == "verification_failed", attempt.receipt.detail
    # The adapter's own verification sentence never reaches the journal -- the
    # runtime substitutes its own -- so the work is confirmed where it really
    # happened: the file the child wrote under the authorized subtree.
    written = root / "work" / "work-001" / "guard.py"
    assert written.is_file(), "the child changed nothing, so this run did no work"
    log_rows = json.loads(
        b"[" + b",".join(
            line for line in surfaces["spawn-log"].splitlines() if line.strip())
        + b"]")
    prompt = [row for row in log_rows if row["argv"][:1] != ["--version"]]
    assert len(prompt) == 1
    assert prompt[0]["marker"] == {
        "in_stdin": True, "in_argv": False, "in_cwd": False, "in_env": False}
    assert RUN_ID.encode() in surfaces["journal"], "the journal did not record the run"


def test_the_operators_instruction_reaches_no_raw_surface(tmp_path):
    """The probe token entered by exactly one road and may leave by none."""
    surfaces, _attempt, _root = _surfaces(tmp_path)

    leaked = sorted(
        name for name, raw in surfaces.items() if PROBE.encode() in raw)

    assert leaked == [], f"THE_INSTRUCTION_REACHED={leaked}"


def test_an_allowed_credential_reaches_no_raw_surface(tmp_path):
    """The key is really in the child's environment, and in nothing that persists.

    Forwarding a secret to a child is what an operator asked for. Writing it
    down is not, and every surface here outlives the process that held it.
    """
    surfaces, _attempt, _root = _surfaces(tmp_path)

    leaked = sorted(
        name for name, raw in surfaces.items() if API_KEY.encode() in raw)

    assert leaked == [], f"THE_CREDENTIAL_REACHED={leaked}"


def test_the_credential_really_reached_the_child_so_its_absence_means_something(
        tmp_path):
    """Without this, the test above passes on a key that was never forwarded."""
    adapter, _root, log = a_harness(
        tmp_path, **{"ANTHROPIC_API_KEY": API_KEY})
    from tests.test_command_claude_transport import a_request, run_once

    run_once(adapter, a_request())

    rows = _fakeclaude.spawns(log)
    assert rows, "no spawn was recorded"
    for row in rows:
        assert "ANTHROPIC_API_KEY" in row["env_names"], (
            "the key never reached the child, so its absence elsewhere is vacuous")


def test_the_pushed_frame_carries_identifiers_and_nothing_else(tmp_path):
    """A frame is a PUSH: whatever it names is delivered to every listener.

    So it is asserted whole rather than searched. An additive field would be
    served to attached clients that never asked for it, and no route-level test
    would have noticed, because no route serves this.
    """
    surfaces, _attempt, _root = _surfaces(tmp_path)

    payloads = [
        json.loads(line[len(b"data: "):].decode("utf-8"))
        for line in surfaces["sse-frames"].splitlines()
        if line.startswith(b"data: ")]

    assert payloads, "the stream delivered no frame at all"
    assert {"kind": "run", "run_id": RUN_ID} in payloads, (
        f"the run signal never reached a listener: {payloads}")
    # EVERY frame, not only the run one, and the vocabulary is closed: each
    # value is an identifier -- no detail, no path, no prose. A frame that grew
    # a field would be delivered to every attached client without anyone asking
    # for it, and no route-level test would notice, because no route serves it.
    for payload in payloads:
        assert set(payload) <= {"kind", "run_id"}, payload
        assert all(
            isinstance(value, str) and value
            and "\n" not in value and len(value) < 64
            for value in payload.values()), payload


def test_the_spawn_log_stores_measurements_and_booleans_and_no_contents(tmp_path):
    """The witness may not become the thing it witnesses against.

    A log that stored the environment would store the credential; one that
    stored the task text would store the instruction. What it may hold is what
    cannot be turned back into either: a length, a digest, and four booleans.
    """
    surfaces, _attempt, _root = _surfaces(tmp_path)

    rows = [json.loads(line) for line in
            surfaces["spawn-log"].decode("utf-8").splitlines() if line.strip()]
    prompt = [row for row in rows if row["argv"][:1] != ["--version"]][0]

    assert set(prompt["stdin"]) == {"read", "bytes", "sha256"}
    assert set(prompt["marker"]) == {"in_stdin", "in_argv", "in_cwd", "in_env"}
    assert all(isinstance(value, bool) for value in prompt["marker"].values())
    assert "env_values" not in prompt, "the log stored environment VALUES"
    assert "text" not in prompt["stdin"], "the log stored the task's text"
