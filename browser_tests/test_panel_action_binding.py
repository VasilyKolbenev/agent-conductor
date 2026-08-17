"""An accepted action must be this Human's Confirm on the frozen snapshot.

The reviewer's probe: a response carrying ``{"action_id": "action-fixed",
"capability": "dispatch", "mode": "policy"}`` with ``requested_by`` set to
``foreign-actor`` projected as ACCEPTED, and the Cockpit announced "Action
request accepted...". That contradicts the frozen API. The route the Confirm
control posts to is Confirm-only; Policy is a separate authority seam, and no
Human click stands in for a Policy grant.

The reviewer's quoted body is reproduced here with the four facts the
projection already checked before this change — ``schema_version``, ``run_id``,
``preview_digest`` and ``scope`` — added back. Without them the probe never
reaches the arms under test, and the whole point of the probe is that
everything past those four went unchecked.

Two levels, both in the engine that ships the module:

* the projection called directly, with a matrix of hostile responses; and
* the whole Cockpit, with ``POST /actions`` intercepted and answered by the
  three bodies the reviewer named.
"""
from __future__ import annotations

import json
from collections.abc import Iterator

import pytest
from playwright.sync_api import Browser, Page, Route

# ``cockpit_url`` is imported to be used as a fixture: one confirm-mode run with
# a bound adapter, served by the real loopback server, is exactly what both
# levels below need, and it already exists next door. The browser itself comes
# from the one session-scoped fixture in ``conftest.py``.
from browser_tests.test_panel_confirm import (  # noqa: F401
    ACCEPTED,
    RUN_ID,
    _create_proposal,
    _load_run,
    _open,
    _snapshot,
    cockpit_url,
)


UNKNOWN = "Outcome unknown. Reload the authoritative run."
CONFIRMED_BY = "release-owner"
PROPOSAL_ID = "proposal-fixed"
PREVIEW = "sha256:" + "a" * 64
CONFIG_DIGEST = "sha256:" + "b" * 64
ARGUMENTS = {
    "artifact_refs": ["artifact-001"],
    "instruction_ref": "instruction-001",
    "output_limit_profile": "small",
    "profile": "implement",
    "work_item_id": "work-001",
}
#: The proposal body the composer submitted, and the durable proposal returned.
SUBMITTED = {
    "arguments": ARGUMENTS,
    "attempt_id": "attempt-001",
    "capability": "dispatch",
    "instance_id": "claude-1",
    "proposed_by": "operator",
    "rationale": "Implement the item.",
    "scope": ["src", "tests"],
    "timeout_seconds": 900,
}
PROPOSAL = dict(
    SUBMITTED, schema_version=2, run_id=RUN_ID, proposal_id=PROPOSAL_ID,
    proposed_at="2026-08-16T09:00:00Z", preview_digest=PREVIEW,
    config_digest=CONFIG_DIGEST)
#: The one response the frozen snapshot vouches for, minted the way
#: ``ControlRuntime._mint_request`` mints it.
ACTION = {
    "action_id": "action-001",
    "arguments": ARGUMENTS,
    "attempt_id": "attempt-001",
    "capability": "dispatch",
    "idempotency_key": f"dispatch-{PROPOSAL_ID}",
    "instance_id": "claude-1",
    "mode": "confirm",
    "preview_digest": PREVIEW,
    "requested_at": "2026-08-16T09:00:01.500000Z",
    "requested_by": CONFIRMED_BY,
    "run_id": RUN_ID,
    "schema_version": 2,
    "scope": ["src", "tests"],
    "timeout_seconds": 900,
}
_DROP = object()


def _mutated(**changes: object) -> dict[str, object]:
    """One valid response with named facts replaced or removed."""
    row = dict(ACTION)
    for name, value in changes.items():
        if value is _DROP:
            row.pop(name, None)
        else:
            row[name] = value
    return row


#: The reviewer's own body, with the four already-checked facts restored.
REVIEWER_PROBE = {
    "action_id": "action-fixed",
    "capability": "dispatch",
    "mode": "policy",
    "preview_digest": PREVIEW,
    "requested_by": "foreign-actor",
    "run_id": RUN_ID,
    "schema_version": 2,
    "scope": ["src", "tests"],
}
REFUSED = (
    ("reviewer-probe", REVIEWER_PROBE),
    ("mode-policy", _mutated(mode="policy")),
    ("mode-observe", _mutated(mode="observe")),
    ("mode-missing", _mutated(mode=_DROP)),
    ("requested-by-foreign", _mutated(requested_by="foreign-actor")),
    ("requested-by-missing", _mutated(requested_by=_DROP)),
    ("attempt-id-other", _mutated(attempt_id="attempt-002")),
    ("attempt-id-missing", _mutated(attempt_id=_DROP)),
    ("instance-id-other", _mutated(instance_id="claude-2")),
    ("instance-id-missing", _mutated(instance_id=_DROP)),
    ("arguments-altered", _mutated(arguments=dict(ARGUMENTS, profile="review"))),
    ("arguments-missing", _mutated(arguments=_DROP)),
    ("scope-widened", _mutated(scope=["docs", "src", "tests"])),
    ("timeout-raised", _mutated(timeout_seconds=3600)),
    ("timeout-not-an-integer", _mutated(timeout_seconds="900")),
    ("capability-other", _mutated(capability="review")),
    ("preview-digest-other", _mutated(preview_digest="sha256:" + "c" * 64)),
    ("idempotency-key-other", _mutated(idempotency_key="dispatch-proposal-other")),
    ("idempotency-key-missing", _mutated(idempotency_key=_DROP)),
    ("action-id-missing", _mutated(action_id=_DROP)),
    ("action-id-malformed", _mutated(action_id="-not-an-id")),
    ("run-id-other", _mutated(run_id="run-other")),
    ("requested-at-missing", _mutated(requested_at=_DROP)),
    ("requested-at-prose", _mutated(requested_at="yesterday")),
    ("requested-at-not-utc", _mutated(requested_at="2026-08-16T12:00:01+03:00")),
    ("schema-version-missing", _mutated(schema_version=_DROP)),
)
#: Called in the page so the shipped module graph — not a copy of it — decides.
_PROJECT = """
async ({proposal, submitted, confirmedBy, response, runId}) => {
  const module = await import("/panel/command-projection.js");
  const frozen = module.projectProposal(proposal, submitted, runId);
  if (!frozen) return {action: null, stage: "proposal"};
  const body = module.confirmationBody(frozen, confirmedBy);
  if (!body) return {action: null, stage: "confirmation"};
  return {
    action: module.projectAction(response, body, runId, frozen.binding),
    stage: "action",
  };
}
"""


@pytest.fixture
def projection_page(chromium: Browser, cockpit_url: str) -> Iterator[Page]:
    """One page on the serving origin, so the module imports as it ships."""
    page, _recorder = _open(chromium, cockpit_url)
    try:
        yield page
    finally:
        page.context.close()


def _project(page: Page, response: object) -> dict[str, object]:
    return page.evaluate(_PROJECT, {
        "confirmedBy": CONFIRMED_BY,
        "proposal": PROPOSAL,
        "response": response,
        "runId": RUN_ID,
        "submitted": SUBMITTED,
    })


def test_the_projection_accepts_the_one_response_the_snapshot_vouches_for(
        projection_page: Page) -> None:
    """The positive control: without it the matrix below could pass by refusing all."""
    assert _project(projection_page, ACTION) == {
        "action": {
            "action_id": "action-001", "capability": "dispatch", "mode": "confirm"},
        "stage": "action",
    }


@pytest.mark.parametrize("response", [row for _name, row in REFUSED],
                         ids=[name for name, _row in REFUSED])
def test_the_projection_refuses_every_action_response_that_is_not_this_confirm(
        projection_page: Page, response: object) -> None:
    """Mode, actor, snapshot echo, derived key, mandatory ids and one UTC instant.

    ``idempotency_key`` is not compared against a value the response supplied:
    the runtime derives it as ``dispatch-<proposal_id>``
    (``ControlRuntime._mint_request``), so the projection recomputes it from the
    frozen snapshot. The honest limit of that check: it mirrors a derivation
    read from the runtime source rather than one the server states on the wire,
    so a runtime that changed the shape would make this UI reject responses that
    are in fact valid — the safe direction, and the coupling is pinned by
    ``tests/test_panel_command_source.py`` so the two cannot drift silently.
    """
    assert _project(projection_page, response) == {"action": None, "stage": "action"}


#: requested_at values the production ActionRequest contract accepts: drive
#: ``command/contracts.py`` ``_timestamp`` over each and it returns the string.
#: The projection must accept exactly these among well-formed responses, so each
#: keeps the one snapshot-vouched response ACCEPTED.
REQUESTED_AT_ACCEPTED = (
    ("trailing-z", "2026-08-16T09:00:02Z"),
    ("utc-offset", "2026-08-16T09:00:02+00:00"),
    ("fractional-second", "2026-08-16T09:00:02.5Z"),
    ("leap-day", "2024-02-29T09:00:02Z"),
    # ISO end-of-day midnight: production (datetime.fromisoformat) accepts it, so
    # parity — not a stricter UI rule — governs and the Cockpit accepts it too.
    ("end-of-day-midnight", "2026-08-16T24:00:00Z"),
)
#: requested_at values production refuses: a shape that passes UTC_INSTANT but is
#: no real UTC instant. Born red at 0b401e7 — the projection took the regex for
#: the fact and accepted the impossible instant among these.
REQUESTED_AT_REFUSED = (
    ("impossible-instant", "2026-99-99T99:99:99Z"),
    ("month-00", "2026-00-15T12:00:00Z"),
    ("month-13", "2026-13-15T12:00:00Z"),
    ("day-00", "2026-08-00T12:00:00Z"),
    ("day-32", "2026-08-32T12:00:00Z"),
    ("april-31", "2026-04-31T12:00:00Z"),
    ("feb-29-non-leap", "2026-02-29T12:00:00Z"),
    ("hour-25", "2026-08-17T25:00:00Z"),
    ("hour-24-second-set", "2026-08-17T24:00:01Z"),
    ("minute-60", "2026-08-17T12:60:00Z"),
    ("second-60", "2026-08-17T12:00:60Z"),
    ("year-0000", "0000-08-17T12:00:00Z"),
)


@pytest.mark.parametrize("requested_at", [ts for _name, ts in REQUESTED_AT_ACCEPTED],
                         ids=[name for name, _ts in REQUESTED_AT_ACCEPTED])
def test_the_projection_accepts_exactly_the_utc_instants_the_contract_accepts(
        projection_page: Page, requested_at: str) -> None:
    """Positive controls and the ISO midnight production's ``_timestamp`` accepts."""
    assert _project(projection_page, _mutated(requested_at=requested_at)) == {
        "action": {
            "action_id": "action-001", "capability": "dispatch", "mode": "confirm"},
        "stage": "action",
    }


@pytest.mark.parametrize("requested_at", [ts for _name, ts in REQUESTED_AT_REFUSED],
                         ids=[name for name, _ts in REQUESTED_AT_REFUSED])
def test_the_projection_refuses_a_regex_shaped_requested_at_that_names_no_instant(
        projection_page: Page, requested_at: str) -> None:
    """Born red at 0b401e7: a regex-only check accepted ``2026-99-99T99:99:99Z``."""
    assert _project(projection_page, _mutated(requested_at=requested_at)) == {
        "action": None, "stage": "action"}


def _intercepted_body(facts: dict[str, str], **changes: object) -> dict[str, object]:
    """One response built from the snapshot the page actually froze."""
    row = {
        "action_id": "action-intercepted",
        "arguments": json.loads(facts["arguments"]),
        "attempt_id": "attempt-001",
        "capability": facts["capability"],
        "idempotency_key": f"dispatch-{facts['proposal_id']}",
        "instance_id": facts["instance"],
        "mode": "confirm",
        "preview_digest": facts["preview_digest"],
        "requested_at": "2026-08-16T09:00:01.500000Z",
        "requested_by": CONFIRMED_BY,
        "run_id": RUN_ID,
        "schema_version": 2,
        "scope": [part.strip() for part in facts["scope"].split(",")],
        "timeout_seconds": int(facts["timeout_seconds"]),
    }
    row.update(changes)
    return row


HOSTILE = {
    "policy": lambda facts: _intercepted_body(facts, mode="policy"),
    "foreign-actor": lambda facts: _intercepted_body(facts, requested_by="foreign-actor"),
    "reviewer-probe": lambda facts: dict(REVIEWER_PROBE,
                                         preview_digest=facts["preview_digest"]),
    # A durable ActionRequest cannot carry an impossible requested_at; the whole
    # Cockpit must land in outcome-unknown, never announce it accepted.
    "impossible-instant": lambda facts: _intercepted_body(
        facts, requested_at="2026-99-99T99:99:99Z"),
}


@pytest.mark.parametrize("shape", sorted(HOSTILE))
def test_an_intercepted_action_response_lands_the_cockpit_in_outcome_unknown(
        chromium: Browser, cockpit_url: str, shape: str) -> None:
    """The whole Cockpit, answered by the three bodies the reviewer named."""
    page, recorder = _open(chromium, cockpit_url)
    try:
        _load_run(page)
        _create_proposal(page)
        facts = _snapshot(page)
        body = HOSTILE[shape](facts)

        def _answer(route: Route) -> None:
            route.fulfill(status=201, content_type="application/json",
                          body=json.dumps(body))

        page.route("**/actions", _answer)
        page.locator("#commandConfirmedBy").fill(CONFIRMED_BY)
        page.get_by_role("button", name="Confirm unchanged proposal").click()
        page.locator('[data-confirm-state="outcome-unknown"]').wait_for()

        assert len(recorder.actions()) == 1
        assert page.locator(".command-confirm-status").text_content() == UNKNOWN
        assert page.locator('[data-confirm-state="accepted"]').count() == 0
        assert page.locator(".command-action-fact").count() == 0
        assert ACCEPTED not in page.locator("#commandCockpit").inner_text()
    finally:
        page.context.close()
