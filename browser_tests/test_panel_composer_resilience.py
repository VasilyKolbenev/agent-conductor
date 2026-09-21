"""What the Cockpit does while its reads and writes are in flight.

Split from ``test_panel_task_scope`` at its own seam when that module reached the
line cap: those tests say WHERE work is filed, these say what the panel draws,
keeps and refuses while a read or a write is still on the wire -- a run selected
since, a proposal created since, a signal arriving mid-keystroke, a background
read that fails. Every helper and the served project come from that module, so
both drive one Cockpit.

Three of these were written after the 2026-09-19 review's own reproducer failed
4 runs in 5 against the shipped panel: a submit during a background refresh was refused
as "complete the fields", a signal arriving while the caret sat in an argument
field threw inside the render and left the panel refreshing for good, and a
re-render erased what had been typed into those fields.
"""
from __future__ import annotations

import threading
from collections.abc import Iterator

import pytest
from playwright.sync_api import Browser, Page, Route

from tests.test_command_adapters import FakeAdapter
from tests.test_command_schema_doubles import DeepPlanAdapter
from conductor.command.adapters.deep_adapters import DEEP_ARGUMENT_SCHEMA

from browser_tests.test_panel_task_scope import (
    ALPHA,
    BETA,
    SCOPES,
    TITLES,
    _compose,
    _context,
    _fill,
    _held,
    _load,
    _open,
    _ready,
    _selected,
    _until,
    cockpit_url,
    serve,
    shown,
)

__all__ = ["cockpit_url"]


class _EvidenceAdapter(DeepPlanAdapter):
    """The plan double, plus `evidence` -- whose arguments carry the composer's
    only MULTI-select, a control no other served capability can draw."""

    argument_schemas = {**DeepPlanAdapter.argument_schemas,
                        "evidence": DEEP_ARGUMENT_SCHEMA}

    def __init__(self, adapter_id: str = "claude-code") -> None:
        FakeAdapter.__init__(self, adapter_id=adapter_id, capabilities=(
            "observe", "dispatch", "review", "evidence"))


@pytest.fixture
def evidence_url(tmp_path) -> Iterator[str]:
    with serve(tmp_path, [_EvidenceAdapter()]) as url:
        yield url


def test_while_a_read_is_pending_on_a_live_line_no_other_run_can_be_selected(
        chromium: Browser, cockpit_url: str) -> None:
    """The ordinary road: while alpha's read is held and the line is up, the load
    control is disabled, and alpha's own context is drawn when the read lands."""
    page, _recorder = _open(chromium, cockpit_url)
    try:
        held, released = _held(page, "**/command/runs/run-alpha")
        _load(page, "run-alpha")
        _until(page, lambda: len(held) == 1)
        assert page.get_by_role("button", name="Load run").is_disabled()
        released.set()
        held[0].continue_()
        assert _context(page, "bound") == shown(ALPHA)
    finally:
        page.context.close()


def test_a_read_landing_after_a_disconnect_and_a_switch_is_never_drawn(
        chromium: Browser, cockpit_url: str) -> None:
    """The road where the load control DOES re-enable under a pending read: the
    line drops, the person selects beta, and alpha's read lands afterwards. It is
    dropped by the read's epoch, and beta stays selected with beta's task."""
    page, _recorder = _open(chromium, cockpit_url)
    try:
        held, released = _held(page, "**/command/runs/run-alpha")
        _load(page, "run-alpha")
        _until(page, lambda: len(held) == 1)
        page.evaluate("() => window.dispatchEvent(new Event('conduct:disconnected'))")
        assert page.get_by_role("button", name="Load run").is_enabled()
        _load(page, "run-beta")
        released.set()
        with page.expect_response("**/command/runs/run-alpha"):
            held[0].continue_()
        with page.expect_response("**/command/runs/run-beta"):
            page.evaluate("() => window.dispatchEvent(new Event('conduct:connected'))")
        _ready(page)
        assert (_selected(page), _context(page, "bound")) == ("run: run-beta", shown(BETA))
    finally:
        page.context.close()


def test_a_proposal_answer_landing_after_a_switch_is_never_drawn_into_the_new_run(
        chromium: Browser, cockpit_url: str) -> None:
    """Alpha's proposal is in flight when the person selects beta. When alpha's
    answer lands, beta's composer is untouched -- no snapshot, no "outcome
    unknown", beta's task still shown -- and the next proposal carries beta's
    scope. Alpha's proposal is durable on alpha, where it was sent.
    """
    page, recorder = _open(chromium, cockpit_url)
    try:
        _load(page, "run-alpha")
        _context(page, "bound")
        held, released = _held(page, "**/command/runs/run-alpha/proposals")
        _fill(page, "dispatch", "Sent on alpha.")
        with page.expect_request("**/command/runs/run-alpha/proposals"):
            page.locator('.command-proposal-form button[type="submit"]').click()
        _until(page, lambda: len(held) == 1)
        assert page.locator(".command-proposal-status").get_attribute(
            "data-proposal-state") == "submitting"

        _load(page, "run-beta")
        assert _context(page, "bound") == shown(BETA)
        released.set()
        with page.expect_response("**/command/runs/run-alpha/proposals") as landed:
            held[0].continue_()
        assert landed.value.status == 201

        assert page.locator(".command-proposal-status").get_attribute(
            "data-proposal-state") == "idle"
        assert page.locator(".command-review-fact").count() == 0
        assert _context(page, "bound") == shown(BETA)
        _compose(page, "dispatch", "Sent on beta.")
        assert [(run, body["arguments"]["work_scope"]) for run, body in recorder.rows] == [
            ("run-alpha", SCOPES[ALPHA]), ("run-beta", SCOPES[BETA])]
        _load(page, "run-alpha")
        _context(page, "bound")
        assert page.locator(".command-record strong", has_text="action_proposal").count() == 1
    finally:
        page.context.close()


@pytest.mark.parametrize("composed_again", [
    pytest.param(False, id="nothing-composed-since"),
    pytest.param(True, id="another-proposal-composed-since")])
def test_an_answer_sent_before_leaving_and_returning_is_never_drawn(
        chromium: Browser, cockpit_url: str, composed_again: bool) -> None:
    """alpha -> beta -> alpha while alpha's first proposal is in flight. Its answer
    belongs to the selection it was sent from, not to "run alpha": it neither
    revives the dropped proposal nor replaces the one composed since."""
    page, _recorder = _open(chromium, cockpit_url)
    try:
        _load(page, "run-alpha")
        _context(page, "bound")
        held, released = _held(page, "**/command/runs/run-alpha/proposals")
        _fill(page, "dispatch", "First, abandoned.")
        with page.expect_request("**/command/runs/run-alpha/proposals"):
            page.locator('.command-proposal-form button[type="submit"]').click()
        _until(page, lambda: len(held) == 1)
        _load(page, "run-beta")
        _context(page, "bound")
        _load(page, "run-alpha")
        _context(page, "bound")
        if composed_again:
            _compose(page, "dispatch", "Second, under review.")
        before = page.locator(".command-review").inner_text()
        released.set()
        with page.expect_response("**/command/runs/run-alpha/proposals"):
            held[0].continue_()
        _ready(page)
        state = page.locator(".command-proposal-status").get_attribute("data-proposal-state")
        after = page.locator(".command-review").inner_text()
        assert "First, abandoned." not in after
        assert (state, after) == (("created", before) if composed_again else ("idle", ""))
    finally:
        page.context.close()


def test_a_confirm_answer_landing_after_a_switch_is_never_drawn_into_the_new_run(
        chromium: Browser, cockpit_url: str) -> None:
    """The same race one step later: alpha's Confirm is in flight when the person
    selects beta. Its answer does not mark beta's confirmation as anything, and
    the request it recorded stands on alpha."""
    page, _recorder = _open(chromium, cockpit_url)
    try:
        _load(page, "run-alpha")
        _context(page, "bound")
        _compose(page, "dispatch", "Confirmed on alpha.")
        held, released = _held(page, "**/command/runs/run-alpha/actions")
        page.locator("#commandConfirmedBy").fill("release-owner")
        with page.expect_request("**/command/runs/run-alpha/actions"):
            page.get_by_role("button", name="Confirm unchanged proposal").click()
        _until(page, lambda: len(held) == 1)

        _load(page, "run-beta")
        assert _context(page, "bound") == shown(BETA)
        released.set()
        with page.expect_response("**/command/runs/run-alpha/actions") as landed:
            held[0].continue_()
        assert landed.value.status == 201

        status = page.locator(".command-confirm-status")
        assert (status.get_attribute("data-confirm-state"), status.text_content()) == (
            "idle", "")
        _load(page, "run-alpha")
        _context(page, "bound")
        assert page.locator(".command-record strong", has_text="action_request").count() == 1
    finally:
        page.context.close()


def test_a_signal_arriving_while_the_person_is_in_an_argument_field_never_freezes_the_panel(
        chromium: Browser, cockpit_url: str) -> None:
    """The person's caret is mid-word in an argument field -- named
    `argument:work_item_id` -- when a signal re-reads the run. The render gives
    back the field, what was typed into it, and the caret; it raises nothing, the
    phase returns to ready, and the NEXT signal still reads: the loop is alive.

    Mutations: focus is restored through a selector built from the name -> the
    render throws on `#argument:...`, the loop dies in "refreshing" and never
    reads again -> red; an argument field keeps its value only on submit -> the
    re-render erases what was typed -> red.
    """
    page, _recorder = _open(chromium, cockpit_url)
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        _load(page, "run-alpha")
        _context(page, "bound")
        _ready(page)
        field = page.locator('.command-proposal-form input[name="argument:work_item_id"]')
        field.fill("work-001")
        field.evaluate("node => { node.focus(); node.setSelectionRange(2, 2); }")
        for _signal in range(2):
            with page.expect_response("**/command/runs/run-alpha"):
                page.evaluate("() => window.dispatchEvent(new Event('conduct:state'))")
            _ready(page)
            assert errors == []
            assert page.evaluate("() => [document.activeElement.name, "
                                 "document.activeElement.value, "
                                 "document.activeElement.selectionStart]") == [
                "argument:work_item_id", "work-001", 2]
    finally:
        page.context.close()


def test_a_proposal_and_its_confirmation_go_through_during_a_background_refresh(
        chromium: Browser, cockpit_url: str) -> None:
    """A signal re-reads the run while the person works -- constantly, while a run
    executes. The form stays usable during that read, and so does its submit:
    held deterministically here by holding the background read open while the
    person proposes and then confirms. Both go through; nothing is refused as
    "complete the fields".

    Mutation: the submit handlers demand phase `ready` on their own -> both are
    refused while the read is held -> red.
    """
    page, recorder = _open(chromium, cockpit_url)
    try:
        _load(page, "run-alpha")
        _context(page, "bound")
        _ready(page)
        held, released = _held(page, "**/command/runs/run-alpha")
        page.evaluate("() => window.dispatchEvent(new Event('conduct:state'))")
        _until(page, lambda: len(held) == 1)
        page.wait_for_function("() => document.querySelector('#commandCockpit')"
                               ".dataset.phase === 'refreshing'")
        _compose(page, "dispatch", "Submitted during a refresh.")
        page.locator("#commandConfirmedBy").fill("release-owner")
        page.get_by_role("button", name="Confirm unchanged proposal").click()
        page.locator('[data-confirm-state="accepted"]').wait_for()
        assert page.locator("#commandCockpit").get_attribute("data-phase") == "refreshing"
        assert [(run, body["arguments"]["work_scope"]) for run, body in recorder.rows] == [
            ("run-alpha", SCOPES[ALPHA])]
        released.set()
        held[0].continue_()
        _ready(page)
    finally:
        page.context.close()


#: Flags when the page has READ the answer to its /actions POST, or seen the POST
#: fail -- the moment after which whatever the page does with that answer is done
#: within two frames. Installed into the page, never into the code under test.
_WATCH_ACTIONS = """() => {
  const original = window.fetch.bind(window);
  window.__actionsSettled = false;
  window.fetch = async (...args) => {
    const actions = String(args[0]).endsWith('/actions');
    let response;
    try {
      response = await original(...args);
    } catch (error) {
      if (actions) window.__actionsSettled = true;
      throw error;
    }
    if (actions) {
      const read = response.json.bind(response);
      response.json = async () => {
        try { return await read(); } finally { window.__actionsSettled = true; }
      };
    }
    return response;
  };
}"""
#: A refusal in the server's own wire shape, for the one answer the real server
#: cannot be made to give on cue.
_REFUSED = {"error": {"code": "authorization_refused", "detail": {},
                      "message": "confirmation did not authorize the request"}}


@pytest.mark.parametrize("late", ["accepted", "refused", "unknown"])
def test_a_late_confirm_answer_never_marks_the_proposal_created_since_on_the_same_run(
        chromium: Browser, cockpit_url: str, late: str) -> None:
    """P1's Confirm is in flight; on the SAME run the person creates P2. P1's answer
    then lands -- the real server's acceptance, a refusal, or a failed request --
    and P2's confirmation is untouched: still idle, no action facts, P2 still the
    snapshot under review. P2 is then confirmed normally, and the run's history
    holds exactly the requests the server really recorded.

    Mutation: the confirm answer is kept by the run selection alone -> P1's answer
    marks P2's block accepted, refused or unknown -> red.
    """
    page, _recorder = _open(chromium, cockpit_url)
    try:
        _load(page, "run-alpha")
        _context(page, "bound")
        _compose(page, "dispatch", "First, confirmed late.")
        _ready(page)
        page.evaluate(_WATCH_ACTIONS)
        held, released = _held(page, "**/command/runs/run-alpha/actions")
        page.locator("#commandConfirmedBy").fill("release-owner")
        with page.expect_request("**/command/runs/run-alpha/actions"):
            page.get_by_role("button", name="Confirm unchanged proposal").click()
        _until(page, lambda: len(held) == 1)
        status = page.locator(".command-confirm-status")
        assert status.get_attribute("data-confirm-state") == "submitting"

        _fill(page, "dispatch", "Second, created while the first was confirming.")
        page.locator('.command-proposal-form input[name="attempt_id"]').fill("attempt-002")
        page.locator('.command-proposal-form button[type="submit"]').click()
        page.locator('[data-proposal-state="created"]').wait_for()
        _ready(page)
        second = page.locator(".command-review").inner_text()
        assert "Second, created while the first was confirming." in second

        released.set()
        if late == "accepted":
            with page.expect_response("**/command/runs/run-alpha/actions") as landed:
                held[0].continue_()
            assert landed.value.status == 201
        elif late == "refused":
            held[0].fulfill(status=409, json=_REFUSED)
        else:
            held[0].abort()
        page.wait_for_function("() => window.__actionsSettled")
        page.evaluate("() => new Promise(done => requestAnimationFrame("
                      "() => requestAnimationFrame(done)))")
        assert page.locator(".command-review").inner_text() == second
        assert (status.get_attribute("data-confirm-state"), status.text_content()) == (
            "idle", "")
        assert page.locator(".command-action-fact").count() == 0

        page.locator("#commandConfirmedBy").fill("release-owner")
        page.get_by_role("button", name="Confirm unchanged proposal").click()
        page.locator('[data-confirm-state="accepted"]').wait_for()
        recorded = 2 if late == "accepted" else 1
        _until(page, lambda: page.locator(
            ".command-record strong", has_text="action_request").count() == recorded)
    finally:
        page.context.close()


# -- what the composer keeps ------------------------------------------------------


def _values(page: Page, names: list[str]) -> dict:
    return page.evaluate("""names => Object.fromEntries(names.map((name) => {
      const control = document.querySelector(`[name="argument:${name}"]`);
      return [name, control.multiple
        ? [...control.selectedOptions].map((row) => row.value) : control.value];
    }))""", names)


def test_everything_the_person_entered_survives_a_background_refresh(
        chromium: Browser, cockpit_url: str) -> None:
    """Three typed ids, two options chosen AWAY from their defaults, and a field
    the person cleared: a signal re-reads the run and every one of them comes back
    as it was left -- including the empty one -- and the proposal then carries
    exactly that.

    Mutations: `keep` replaces the capability's draft instead of merging (the
    siblings are erased); `keep` ignores an empty value (the cleared field comes
    back); the enum `change` listener is dropped (the choice falls to its
    default) -> red.
    """
    page, recorder = _open(chromium, cockpit_url)
    typed = {"work_item_id": "work-001", "instruction_ref": "instruction-001",
             "artifact_refs": "", "profile": "review", "output_limit_profile": "normal"}
    try:
        _load(page, "run-alpha")
        _context(page, "bound")
        _ready(page)
        _fill(page, "dispatch", "Everything entered survives.")
        form = page.locator(".command-proposal-form")
        form.locator('select[name="argument:profile"]').select_option("review")
        form.locator('select[name="argument:output_limit_profile"]').select_option("normal")
        form.locator('input[name="argument:artifact_refs"]').fill("")

        with page.expect_response("**/command/runs/run-alpha"):
            page.evaluate("() => window.dispatchEvent(new Event('conduct:state'))")
        _ready(page)
        assert _values(page, list(typed)) == typed

        page.locator('.command-proposal-form button[type="submit"]').click()
        page.locator('[data-proposal-state="created"]').wait_for()
        assert [body["arguments"] for _run, body in recorder.rows] == [{
            "work_item_id": "work-001", "instruction_ref": "instruction-001",
            "artifact_refs": [], "profile": "review", "output_limit_profile": "normal",
            "work_scope": SCOPES[ALPHA]}]
    finally:
        page.context.close()


def test_a_multi_select_argument_survives_a_background_refresh(
        chromium: Browser, evidence_url: str) -> None:
    """The composer's only multi-select -- `evidence`'s kinds -- keeps what was
    selected across a re-render, like every other control.

    Mutation: the enum-list `change` listener is dropped -> the selection falls
    back to none -> red.
    """
    page, _recorder = _open(chromium, evidence_url)
    try:
        _load(page, "run-alpha")
        _context(page, "bound")
        _ready(page)
        form = page.locator(".command-proposal-form")
        form.locator('select[name="capability"]').select_option("evidence")
        form.locator('input[name="argument:target_action_id"]').fill("action-001")
        form.locator('select[name="argument:kinds"]').select_option(["diff", "tests"])

        with page.expect_response("**/command/runs/run-alpha"):
            page.evaluate("() => window.dispatchEvent(new Event('conduct:state'))")
        _ready(page)
        assert _values(page, ["target_action_id", "kinds"]) == {
            "target_action_id": "action-001", "kinds": ["diff", "tests"]}
    finally:
        page.context.close()


def test_reloading_the_same_run_still_draws_the_answer_of_a_proposal_in_flight(
        chromium: Browser, cockpit_url: str) -> None:
    """Selecting the SAME run again is not moving on: the proposal in flight is
    still this selection's, and its answer is drawn when it lands.

    Mutation: the selection counter is bumped on every explicit load -> the
    answer is dropped and the composer stays in "submitting" -> red.
    """
    page, _recorder = _open(chromium, cockpit_url)
    try:
        _load(page, "run-alpha")
        _context(page, "bound")
        held, released = _held(page, "**/command/runs/run-alpha/proposals")
        _fill(page, "dispatch", "Sent, then the same run reloaded.")
        with page.expect_request("**/command/runs/run-alpha/proposals"):
            page.locator('.command-proposal-form button[type="submit"]').click()
        _until(page, lambda: len(held) == 1)

        _load(page, "run-alpha")
        _context(page, "bound")
        released.set()
        with page.expect_response("**/command/runs/run-alpha/proposals"):
            held[0].continue_()
        page.locator('[data-proposal-state="created"]').wait_for()
        assert page.locator(".command-review-fact").count() > 0
        assert page.locator(
            '.command-proposal-form button[type="submit"]').is_enabled()
    finally:
        page.context.close()


@pytest.mark.parametrize("operation", ["proposal", "confirm"])
@pytest.mark.parametrize("first", [pytest.param(503, id="the-first-read-failed"),
                                   pytest.param(200, id="the-first-read-succeeded")])
def test_a_read_queued_before_the_current_one_answered_keeps_that_answer(
        chromium: Browser, cockpit_url: str, first: int, operation: str) -> None:
    """The ORDER a person cannot control: a second signal queues the next read
    while the first is still on the wire, and only then does the first answer.

    What the first read answered is what stands. Failed: both forms stay shut
    while the queued read is still on the wire -- it has brought nothing either.
    Succeeded: the facts are current, so the ordinary refresh keeps both forms
    live and the work goes out.

    Mutation: the failure's effect is skipped when a later read has already
    bumped the epoch -> the queued read re-opens the write door -> red.
    """
    page, _recorder = _open(chromium, cockpit_url)
    held: list[Route] = []
    posts: list[str] = []
    page.on("request", lambda request: posts.append(request.url)
            if request.method == "POST" else None)
    try:
        _load(page, "run-alpha")
        _context(page, "bound")
        _compose(page, "dispatch", "Created before the reads were queued.")
        _ready(page)
        posts.clear()
        page.route("**/command/runs/run-alpha", lambda route: held.append(route))

        signal = "() => window.dispatchEvent(new Event('conduct:state'))"
        page.evaluate(signal)
        _until(page, lambda: len(held) == 1)
        page.evaluate(signal)          # queued BEFORE the first read answers
        assert len(held) == 1
        if first == 503:
            held[0].fulfill(status=503, json={"error": {
                "code": "store_error", "detail": {},
                "message": "the selected run could not be read"}})
        else:
            held[0].fulfill(response=held[0].fetch())
        _until(page, lambda: len(held) == 2)

        proposal = page.locator('.command-proposal-form button[type="submit"]')
        confirm = page.locator('.command-confirm-form button[type="submit"]')
        assert page.locator("#commandCockpit").get_attribute("data-phase") == "refreshing"
        if first == 503:
            assert (proposal.is_enabled(), confirm.is_enabled()) == (False, False)
            assert page.locator("#commandConfirmedBy").is_disabled()
            assert posts == []
            return
        assert (proposal.is_enabled(), confirm.is_enabled()) == (True, True)
        if operation == "proposal":
            _fill(page, "dispatch", "Sent while the queued read is still pending.")
            page.locator(
                '.command-proposal-form input[name="attempt_id"]').fill("attempt-queued")
            with page.expect_response("**/command/runs/run-alpha/proposals") as answered:
                proposal.click()
        else:
            page.locator("#commandConfirmedBy").fill("release-owner")
            with page.expect_response("**/command/runs/run-alpha/actions") as answered:
                confirm.click()
        assert answered.value.status == 201
        assert len(posts) == 1
    finally:
        page.unroute_all(behavior="ignoreErrors")
        page.context.close()


def test_a_background_read_that_fails_shuts_both_forms_until_one_succeeds(
        chromium: Browser, cockpit_url: str) -> None:
    """A failed background read leaves the facts under the forms unknown, though
    the stream never dropped: neither form may be worked or submitted. The RETRY
    does not reopen them -- its own start says `refreshing`, and an attempt to
    re-read is not a re-read -- and a second failure does not either. Only a read
    that came back does, and then both forms work again.

    Mutations: `workable` admits `stale`; `workable` asks the phase without
    asking whether the facts are current; a failed read leaves `current` true
    -> a proposal or a Confirm goes out during the window -> red.
    """
    page, _recorder = _open(chromium, cockpit_url)
    answer = {"mode": "pass"}
    held: list[Route] = []
    posts: list[str] = []
    page.on("request", lambda request: posts.append(request.url)
            if request.method == "POST" else None)

    def read(route: Route) -> None:
        if answer["mode"] == "fail":
            route.fulfill(status=503, json={"error": {
                "code": "store_error", "detail": {},
                "message": "run store could not complete the request"}})
        elif answer["mode"] == "hold":
            held.append(route)
        else:
            route.continue_()

    def signal() -> None:
        page.evaluate("() => window.dispatchEvent(new Event('conduct:state'))")

    def shut(where: str) -> None:
        assert page.evaluate("() => navigator.onLine") is True, where
        assert page.locator(
            ".command-proposal-form button[type=submit]").is_disabled(), where
        assert page.locator(
            ".command-confirm-form button[type=submit]").is_disabled(), where
        assert page.locator("#commandConfirmedBy").is_disabled(), where
        assert posts == [], where

    try:
        _load(page, "run-alpha")
        _context(page, "bound")
        _compose(page, "dispatch", "Composed while the facts were readable.")
        _ready(page)
        posts.clear()
        page.route("**/command/runs/run-alpha", read)

        answer["mode"] = "fail"
        signal()
        page.wait_for_function("() => document.querySelector('#commandCockpit')"
                               ".dataset.phase === 'stale'")
        shut("after the read failed")

        answer["mode"] = "hold"
        signal()
        _until(page, lambda: len(held) == 1)
        assert page.locator("#commandCockpit").get_attribute("data-phase") == "refreshing"
        shut("while the retry is still on the wire")

        answer["mode"] = "fail"
        held.pop().fulfill(status=503, json={"error": {
            "code": "store_error", "detail": {}, "message": "the retry failed too"}})
        page.wait_for_function("() => document.querySelector('#commandCockpit')"
                               ".dataset.phase === 'stale'")
        shut("after the retry failed as well")

        answer["mode"] = "pass"
        with page.expect_response("**/command/runs/run-alpha"):
            signal()
        _ready(page)
        assert page.locator(".command-proposal-form button[type=submit]").is_enabled()
        assert page.locator(".command-confirm-form button[type=submit]").is_enabled()
        page.locator("#commandConfirmedBy").fill("release-owner")
        page.get_by_role("button", name="Confirm unchanged proposal").click()
        page.locator('[data-confirm-state="accepted"]').wait_for()
    finally:
        page.context.close()


