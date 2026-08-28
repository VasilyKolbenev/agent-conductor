"""The review road separates stderr, and it owes that to EVERY reviewer.

``ArtifactAwareTransport._run_review`` is the one spawn in this build that asks
its runner for a separated stderr, and the reason is what happens to the other
stream: ``outcome.output`` becomes the bytes of a durable review artifact. A
vendor CLI's diagnostics riding the same descriptor would be published as part
of the review, and stderr is the likeliest place for a tool to echo a key.

That is an invariant of the SHARED base, so it is held at the shared base's
level rather than inside one provider's suite. It used to be held in exactly one
-- Claude Code's -- while the second review-capable provider on the same base
covered it nowhere, which made a guard over shared code a property of which
subclass someone happened to write a test for.

WHICH providers it covers is derived from ``PROVIDER_CATALOG``: every catalogued
provider whose entry declares the review control. A sixth product that learns to
review inherits this guard on the day its row lands, and reds here until someone
hands it a child to drive. The only per-provider thing below is that child --
a real fake binary and the harness that pins it. The claim itself names no
product.

WHY THE RED DOES NOT LOOK LIKE A LEAK. A merged stream is scanned by a SECOND
gate, ``output_contains_env_value``, which refuses to publish a review whose
output repeated an allowed environment value. So the first cost of losing the
separation is not a published secret but a destroyed review: an honest child
that wrote one diagnostic line can no longer produce a durable artifact at all.
That is precisely why the separation may not be left standing on that gate. The
gate covers the values this build was already handed; a vendor's stderr is where
the values it was never handed would appear.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest

from conductor.command.adapters import AdapterRegistry
from conductor.command.artifacts import ArtifactDocument
from conductor.command.contracts import ActionProposal, RunEnvelope
from conductor.command.providers import PROVIDER_CATALOG
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.runtime import (
    AttemptState,
    Budget,
    Confirmation,
    ControlRuntime,
)

from tests import _fakeclaude, _fakecodex
from tests.test_command_claude_transport import NOW as CLAUDE_NOW
from tests.test_command_claude_transport import a_harness as claude_harness
from tests.test_command_codex_transport import NOW as CODEX_NOW
from tests.test_command_codex_transport import a_harness as codex_harness


#: The control word, spelled here rather than imported from the transport this
#: module judges: a selector read out of the code under test would follow that
#: code wherever it went.
REVIEW = "review"
#: What the child writes to its stderr, and what nothing else in this build
#: writes anywhere. Long enough that its absence from a document is a fact about
#: the stream it came from and not a coincidence about short strings, and no
#: credential shape at all -- a secret would be caught by the redaction gate,
#: and what is under test here is the road before that gate.
STDERR_ONLY = "vendor-diagnostic-line-that-must-never-be-published-4a7f2c9e10b6"

RUN_ID = "run-review-stderr"
CYCLE_ID = "review-cycle"
INSTANCE_ID = "reviewer"
INPUT_REF = "artifact-input"
OUTPUT_REF = "artifact-reviewed"
ARGUMENTS = {
    "work_item_id": "work-001",
    "target_artifact_refs": [INPUT_REF],
    "result_artifact_ref": OUTPUT_REF,
    "review_profile": "quality",
}


@dataclass(frozen=True)
class _Driver:
    """One catalogued provider's real child, and nothing about the claim.

    ``harness`` pins a real single-file executable through the real provider
    door and returns the registered adapter; ``fake`` is that executable's own
    module, which owns both the knob that makes it answer and the knob that
    makes it complain. ``now`` is the instant its harness clocks the adapter
    with, so the records this module writes and the receipts that adapter mints
    read the same time.
    """

    harness: Callable[..., Any]
    fake: Any
    now: str


#: The children this module can drive. Membership is not the roster -- the
#: roster comes from the catalog below -- and the first test holds the two to
#: each other, so a review-capable provider with no child here is a failure and
#: never a silently missing case.
_DRIVERS = {
    "claude-code": _Driver(claude_harness, _fakeclaude, CLAUDE_NOW),
    "codex": _Driver(codex_harness, _fakecodex, CODEX_NOW),
}

#: Every catalogued provider that declares the review control, in a stable order.
REVIEW_CAPABLE = tuple(sorted(
    provider_id for provider_id, entry in PROVIDER_CATALOG.items()
    if REVIEW in entry.capabilities))


class _Ids:
    """A deterministic id mint that never repeats a value."""

    def __init__(self) -> None:
        self._counts: dict[str, int] = {}

    def __call__(self, kind: str) -> str:
        self._counts[kind] = self._counts.get(kind, 0) + 1
        return f"{kind}-{self._counts[kind]}"


def _review(provider_id: str, driver: _Driver, tmp_path):
    """Drive one confirmed review through the ordinary runtime, against a real child.

    The child is told to answer on stdout and to complain on stderr, which is
    the only shape in which the two streams can be told apart afterwards.
    """
    fake = driver.fake
    adapter, root, _log = driver.harness(tmp_path, **{
        fake.EMIT_REVIEW: "enabled-review-output",
        fake.EMIT_STDERR: STDERR_ONLY,
    })
    config = {
        "cycle": {"id": CYCLE_ID, "phases": ["review"]},
        "instances": [{"id": INSTANCE_ID, "adapter": provider_id}],
    }
    digest = snapshot_digest(config)
    store = RunStore(root)
    store.create_run(
        RunEnvelope(
            run_id=RUN_ID, cycle_id=CYCLE_ID, created_at=driver.now,
            config_digest=digest, mode="confirm"),
        config)
    store.append(ArtifactDocument(
        artifact_id="artifact-source-1", artifact_ref=INPUT_REF,
        run_id=RUN_ID, created_at=driver.now, media_type="text/markdown",
        content="# Candidate\n\nReview this exact proposal."))
    proposal = ActionProposal(
        proposal_id="proposal-review", run_id=RUN_ID,
        attempt_id="attempt-review", instance_id=INSTANCE_ID,
        capability=REVIEW, arguments=ARGUMENTS, scope=("work",),
        proposed_by="lane", proposed_at=driver.now, timeout_seconds=60,
        rationale="review the durable role handoff", config_digest=digest)
    store.append(proposal)
    confirmation = Confirmation(
        confirmation_id="confirmation-review", run_id=RUN_ID,
        proposal_id=proposal.proposal_id,
        preview_digest=proposal.preview_digest, capability=REVIEW,
        scope=("work",), config_digest=digest,
        confirmed_by="release-owner", confirmed_at=driver.now)
    runtime = ControlRuntime(
        store, AdapterRegistry([adapter]), clock=lambda: driver.now, ids=_Ids())
    budget = Budget(
        max_actions=8, max_action_seconds=3600,
        max_confirmation_age_seconds=3600)
    attempt = runtime.execute(runtime.authorize(confirmation, budget=budget))
    return attempt, store.read(RUN_ID).records


def test_the_catalogue_names_review_providers_and_all_of_them_are_driven_here():
    """A guard over a set must be shown to have a subject, and to have all of it.

    Parametrizing over an empty roster is a module that passes by running
    nothing; parametrizing over a roster with an undriven member is a provider
    whose review road nobody watched. Both would look green, so both are refused
    here before the behavioural claim below reads the same set.
    """
    assert REVIEW_CAPABLE, "NO_CATALOGUED_PROVIDER_DECLARES_THE_REVIEW_CONTROL"
    assert set(_DRIVERS) == set(REVIEW_CAPABLE), (
        f"UNDRIVEN={sorted(set(REVIEW_CAPABLE) - set(_DRIVERS))} "
        f"UNCATALOGUED={sorted(set(_DRIVERS) - set(REVIEW_CAPABLE))}")


@pytest.mark.parametrize("provider_id", REVIEW_CAPABLE)
def test_no_review_capable_provider_publishes_what_its_child_wrote_to_stderr(
        provider_id, tmp_path):
    """A durable review is the child's ANSWER, and never its complaints as well.

    Both streams are real here: one process wrote distinct bytes to each, and
    what is asserted is the difference between them. The published document is
    the stdout answer exactly -- not merely free of the stderr line, which a
    truncation would also satisfy -- and the stderr line reaches no record of
    the run at all.

    The first assertion is the one a lost separation trips, and it trips on the
    review being gone rather than on the review being poisoned: with the streams
    merged, the diagnostic joins the answer, the redaction gate refuses the
    contaminated output, and the operator's review cannot be published by any
    road. A build one gate away from publishing a vendor's stderr has already
    lost the property this test is named for.
    """
    driver = _DRIVERS[provider_id]
    attempt, records = _review(provider_id, driver, tmp_path)
    published = [row.value for row in records
                 if row.kind == "artifact" and row.value.source_action_id]

    assert len(published) == 1, (
        f"{provider_id}: expected one durable review artifact, got "
        f"{len(published)}; the attempt ended {attempt.state.value} "
        f"({attempt.receipt.detail})")
    assert attempt.state is AttemptState.SUCCEEDED, attempt.receipt.detail
    assert STDERR_ONLY not in published[0].content, (
        f"{provider_id}: the child's stderr became durable artifact content")
    assert published[0].content == driver.fake.REVIEW_OUTPUT + "\n"
    journal = json.dumps(
        [row.value.as_dict() for row in records], sort_keys=True)
    assert STDERR_ONLY not in journal, (
        f"{provider_id}: the child's stderr reached the run's records")
