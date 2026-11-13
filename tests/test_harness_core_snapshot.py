"""Claude Code and Codex, held byte for byte while a third task channel is added (I0).

H5-GROK-DIAGNOSE puts a `file` task channel into code Claude Code and Codex share. This is the
witness taken on the tree BEFORE that change, and it is held equal after every iteration: for each
of the two vendors, on the API-key road and on the subscription road (a relay home), for a
dispatch, a review and an independent checker, every child the runner was asked to start -- its
argv, its environment, the stdin it was handed (length and SHA-256), whether its stderr was
separated, and the SHA-256 of each secret value its output is scanned for -- and the facts a
grant binds (`ProviderAuthority.facts`), for an API-key and a subscription pin.

The expected values are `tests/fixtures/h5_core_snapshot.json`, written from the unchanged tree and
never from the code under test. Paths of this run (its temporary folder, a relay home's random
name) are replaced by words before the comparison, and nothing else is: a changed flag, a new
environment name or one byte of a frame is a failed test here, not a note.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
from pathlib import Path

import pytest

from conductor.command.adapters import AdapterRegistry
from conductor.command.adapters.claude_code import CLAUDE_PROTOCOL, CLAUDE_PROVIDER_ID
from conductor.command.adapters.codex_cli import CODEX_PROTOCOL, CODEX_PROVIDER_ID
from conductor.command.adapters.process import ProcessRunner
from conductor.command.adapters.provider import ProviderConfig
from conductor.command.artifacts import ArtifactDocument
from conductor.command.contracts import RunEnvelope
from conductor.command.policy_providers import ProviderAuthority
from conductor.command.providers import resolve_providers
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.runtime import AttemptState, Budget, ControlRuntime

from tests import _fakeclaude, _fakecodex
from tests import test_command_claude_review as claude_review
from tests import test_command_claude_transport as claude_t
from tests import test_command_codex_review as codex_review
from tests import test_command_codex_transport as codex_t
from tests._boundary_assumed import boundary_assumed  # noqa: F401
from tests.relay_roads import CLAUDE, CODEX, Site
from tests.test_independent_checker_transport import setup as checker_setup
from tests.test_relay_road_success import _checked_run

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "h5_core_snapshot.json"
NOW = "2026-08-22T12:00:00Z"
ACCEPT = "enabled-verdict-accept"
RESULT = "result.txt:done"


def _golden() -> dict:
    """The snapshot written on the unchanged tree; empty if the file is not there yet."""
    if not FIXTURE.is_file():
        return {"specs": {}, "facts": {}}
    # The registered fixture is a Windows launcher or a POSIX script with the same stem.
    expected = FIXTURE.read_text(encoding="utf-8")
    return json.loads(expected.replace("<EXE_SUFFIX>", ".exe" if os.name == "nt" else ""))


def _scrubber(base: Path):
    """Words for the paths of THIS run: its folder in every spelling, a relay home's name and
    the key folder of its project (16 hex of the project's identity, which differs per run)."""
    spellings = {str(base), str(base.resolve()), base.as_posix(), base.resolve().as_posix()}
    longest_first = sorted(spellings, key=len, reverse=True)
    folder = re.compile("|".join(re.escape(row) for row in longest_first), re.IGNORECASE)
    keys = re.compile(r"(?<=/relay/)[0-9a-f]{16}(?=/)")
    homes = re.compile(r"(?<![0-9a-f])([cx])-[0-9a-f]{16}(?![0-9a-f])")

    def scrub(text: str) -> str:
        text = folder.sub("<TMP>", text).replace("\\", "/")
        return homes.sub(r"\1-<HEX16>", keys.sub("<KEY16>", text))
    return scrub


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _shape(spec, scrub) -> dict:
    """The five fields of a CommandSpec the task channel could move, as plain data."""
    stdin = spec.stdin_bytes
    return {
        "argv": [scrub(token) for token in spec.argv],
        "env": {name: scrub(value) for name, value in sorted(spec.env.items())},
        "stdin": None if stdin is None else [len(stdin), _digest(stdin)],
        "separate_stderr": spec.separate_stderr,
        "sensitive_extra": [_digest(value) for value in spec.sensitive_extra],
    }


@contextlib.contextmanager
def _recording():
    """Every spec any runner is asked to run, in order, and the real child still runs.

    On the relay road the boundary double calls `ProcessRunner.run` with the same spec less its
    boundary, so one wrapper at the base class sees each child once, whichever runner it is.
    """
    seen: list = []
    original = ProcessRunner.run

    def run(self, spec):
        seen.append(spec)
        return original(self, spec)

    ProcessRunner.run = run
    try:
        yield seen
    finally:
        ProcessRunner.run = original


def _hold(name: str, base: Path, drive) -> None:
    with _recording() as specs:
        drive()
    assert specs, f"{name}: no child was started, so nothing was witnessed"
    scrub = _scrubber(base)
    seen = [_shape(spec, scrub) for spec in specs]
    wanted = _golden()["specs"].get(name)
    if seen != wanted:
        pytest.fail(f"SNAPSHOT {name} {json.dumps(seen, sort_keys=True)}")


# -- the API-key road ----------------------------------------------------------------------------


def test_claude_dispatch_on_the_api_key_road(tmp_path):
    def drive():
        adapter, _root, _log = claude_t.a_harness(tmp_path)
        receipt = claude_t.run_once(adapter, claude_t.a_request())
        assert receipt.outcome == "succeeded", receipt.detail
    _hold("claude/api/dispatch", tmp_path, drive)


def test_codex_dispatch_on_the_api_key_road(tmp_path):
    def drive():
        adapter, _root, _log = codex_t.a_harness(tmp_path)
        receipt = codex_t.run_once(adapter, codex_t.a_request())
        assert receipt.outcome == "succeeded", receipt.detail
    _hold("codex/api/dispatch", tmp_path, drive)


def test_claude_review_on_the_api_key_road(tmp_path):
    def drive():
        attempt = claude_review._run(tmp_path)[0]
        assert attempt.state is AttemptState.SUCCEEDED, attempt.receipt.detail
    _hold("claude/api/review", tmp_path, drive)


def test_codex_review_on_the_api_key_road(tmp_path):
    def drive():
        attempt = codex_review._run(tmp_path)[0]
        assert attempt.state is AttemptState.SUCCEEDED, attempt.receipt.detail
    _hold("codex/api/review", tmp_path, drive)


@pytest.mark.parametrize("vendor,cross", [("claude", False), ("codex", True)])
def test_the_checker_on_the_api_key_road(vendor, cross, tmp_path, boundary_assumed):
    def drive():
        runtime, authorization, *_rest = checker_setup(tmp_path, cross=cross)
        attempt = runtime.execute(authorization)
        assert attempt.state is AttemptState.SUCCEEDED, attempt.receipt.detail
    _hold(f"{vendor}/api/checker", tmp_path, drive)


# -- the subscription road: a relay home --------------------------------------------------------


def _relay_review(site: Site, review):
    """One review through Confirm over a relay site, whichever vendor's fixtures `review` is."""
    with site.owned():
        store = RunStore(site.root)
        store.create_run(RunEnvelope(
            run_id=review.RUN_ID, cycle_id="review-cycle", created_at=NOW,
            config_digest=snapshot_digest(review.CONFIG), mode="confirm"), review.CONFIG)
        store.append(ArtifactDocument(
            artifact_id="artifact-source-1", artifact_ref=review.INPUT_REF, run_id=review.RUN_ID,
            created_at=NOW, media_type="text/markdown", content="# Candidate\n\nReview this."))
        proposal = review._proposal()
        store.append(proposal)
        runtime = ControlRuntime(
            store, AdapterRegistry([site.adapter]), clock=lambda: NOW, ids=review._Ids())
        budget = Budget(max_actions=8, max_action_seconds=3600, max_confirmation_age_seconds=3600)
        return runtime.execute(runtime.authorize(review._confirmation(proposal), budget=budget))


def test_claude_dispatch_on_the_relay_road(tmp_path):
    def drive():
        receipt = Site(tmp_path, CLAUDE, **{_fakeclaude.WRITE_FILE: RESULT}).run()
        assert receipt.outcome == "succeeded", receipt.detail
    _hold("claude/relay/dispatch", tmp_path, drive)


def test_codex_dispatch_on_the_relay_road(tmp_path):
    def drive():
        receipt = Site(tmp_path, CODEX).run()
        assert receipt.outcome == "succeeded", receipt.detail
    _hold("codex/relay/dispatch", tmp_path, drive)


def test_claude_review_on_the_relay_road(tmp_path):
    def drive():
        site = Site(tmp_path, CLAUDE, **{_fakeclaude.EMIT_REVIEW: "enabled-review-output"})
        attempt = _relay_review(site, claude_review)
        assert attempt.state is AttemptState.SUCCEEDED, attempt.receipt.detail
    _hold("claude/relay/review", tmp_path, drive)


def test_codex_review_on_the_relay_road(tmp_path):
    def drive():
        site = Site(tmp_path, CODEX, **{_fakecodex.EMIT_REVIEW: "enabled-review-output"})
        attempt = _relay_review(site, codex_review)
        assert attempt.state is AttemptState.SUCCEEDED, attempt.receipt.detail
    _hold("codex/relay/review", tmp_path, drive)


def test_claude_is_checked_by_claude_on_the_relay_road(tmp_path):
    def drive():
        site = Site(tmp_path, CLAUDE, **{_fakeclaude.WRITE_FILE: RESULT,
                                         _fakeclaude.EMIT_VERDICT: ACCEPT})
        attempt, _evidence = _checked_run(site, site.adapter, site.adapter, False)
        assert attempt.state is AttemptState.SUCCEEDED, attempt.receipt.detail
    _hold("claude/relay/checker", tmp_path, drive)


def test_codex_checks_a_claude_result_on_the_relay_road(tmp_path, boundary_assumed):
    def drive():
        site = Site(tmp_path, CODEX, **{_fakecodex.EMIT_VERDICT: ACCEPT})
        doer, _root, _log = claude_t.a_harness(
            tmp_path / "doer", root=site.root, **{_fakeclaude.WRITE_FILE: RESULT})
        attempt, _evidence = _checked_run(site, doer, site.adapter, True)
        assert attempt.state is AttemptState.SUCCEEDED, attempt.receipt.detail
    _hold("codex/relay/checker", tmp_path, drive)


# -- the facts a grant binds ---------------------------------------------------------------------

PINS = {"claude": (CLAUDE_PROVIDER_ID, CLAUDE_PROTOCOL, claude_t._executable),
        "codex": (CODEX_PROVIDER_ID, CODEX_PROTOCOL, codex_t._executable)}


def _scrubbed(value, scrub):
    if isinstance(value, str):
        return scrub(value)
    if isinstance(value, (list, tuple)):
        return [_scrubbed(row, scrub) for row in value]
    if isinstance(value, dict):
        return {scrub(key): _scrubbed(row, scrub) for key, row in value.items()}
    return value


@pytest.mark.parametrize("auth", ["api_key", "subscription"])
@pytest.mark.parametrize("vendor", sorted(PINS))
def test_the_facts_a_grant_binds_for_a_pin(vendor, auth, tmp_path):
    provider_id, protocol, build = PINS[vendor]
    root = tmp_path / "root"
    root.mkdir()
    login = tmp_path / "DecemberCommand" / "logins" / "x"
    login.mkdir(parents=True)
    config = ProviderConfig(
        provider_id=provider_id, executable=str(build(tmp_path)), protocol=protocol, auth=auth,
        auth_home=str(login) if auth == "subscription" else "")
    resolution = resolve_providers(
        [config], root=root, clock=lambda: NOW, ids=claude_t._Ids(), environ={},
        confine_platform=None)
    authority = ProviderAuthority([config], resolution.contracts, resolution.registry)
    facts = authority.facts({"instances": [{"id": "doer", "adapter": provider_id}]})
    seen = _scrubbed(json.loads(json.dumps(facts, sort_keys=True)), _scrubber(tmp_path))
    wanted = _golden()["facts"].get(f"{vendor}/{auth}")
    if seen != wanted:
        pytest.fail(f"SNAPSHOT-FACTS {vendor}/{auth} {json.dumps(seen, sort_keys=True)}")
