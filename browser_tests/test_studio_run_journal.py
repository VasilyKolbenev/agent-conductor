"""A run's own journal in a real Chromium, and the answers a Human writes into it.

Split from ``test_studio_lifecycle`` at the 800-line cap, along a real seam
rather than at a convenient line. That module is about a workflow DOCUMENT --
drawn, saved, published -- and about the socket the window reads over. This one
is about a RUN: the records it already wrote, the order it wrote them in, and
the durable receipt a person adds to them.

They share one seeded project, so the fixture, the page helpers and the seed
live next door and are imported here: one run described in one place. The gate
runs every module in its own process, so nothing about that import is shared
state -- it is one description read twice.

TWO TESTS HERE WERE WRITTEN RED, both against production defects this module
found by rendering the surface. Both are fixed and both are green now, and each
is kept as the guard that holds its fix closed:

- ``test_the_run_list_row_never_shows_the_outcome_word_without_its_sentence``
  -- ``runSummary`` drew ``verification_failed`` on the list row with no
  explanation beside it, in a file whose own comment said that word "must never
  appear without" its sentence. ``runRow`` now puts the sentence in the row
  beside the button, which is where it can be a paragraph at all.
- ``test_a_run_this_product_wrote_on_another_road_is_readable_in_the_studio``
  -- the Studio's boundary refused the frozen configuration that
  ``conduct preview`` and the control loop write, so a run this product created
  itself was listed and could not be opened. ``studio-model.CYCLE_KEYS`` admits
  ``phases`` now, and still reads nothing out of the cycle but its id.
"""
from __future__ import annotations

from playwright.sync_api import Browser, Page

from browser_tests.test_studio_lifecycle import (  # noqa: F401
    CONFIRM_GATE,
    DECIDER,
    DIGEST,
    PREVIEW_RUN,
    RUN_ID,
    _open,
    _Project,
    project,
    reach_the_confirm_gate,
)


# -- 1. the journal, in the order it was written ------------------------------------------------


def _timeline(page: Page) -> list[dict[str, str | None]]:
    """Every timeline row: the record kind, the progression step, the prose."""
    return page.evaluate(
        """() => [...document.querySelectorAll('ol.studio-timeline > li')]
             .map(row => {
               const head = row.querySelector('.studio-row__head');
               const mono = [...head.querySelectorAll('.studio-mono')]
                 .map(span => span.textContent);
               return {kind: mono[0],
                       step: mono.length > 1 ? mono[1] : null,
                       prose: head.children[1].textContent};
             })""")


def _read_the_run(page: Page) -> None:
    page.locator("#navRuns").click()
    page.wait_for_selector("#screenRuns:not([hidden])")
    page.locator(f'[data-focus-key="run:{RUN_ID}"]').click()
    page.wait_for_selector("ol.studio-timeline")


def _choose_a_run_and_settle_either_way(page: Page, run_id: str) -> str:
    """Open the Runs screen, choose one run, and wait until the read is done.

    The predicate resolves whichever way that read goes -- a journal drawn, or
    the screen in its `failed` state -- so a caller's assertion fails on what
    the window did rather than on a timeout that would hide it. Answers with
    what the window then says, which is where a refusal is written.
    """
    page.locator("#navRuns").click()
    page.wait_for_selector("#screenRuns:not([hidden])")
    page.locator(f'[data-focus-key="run:{run_id}"]').click()
    page.wait_for_function(
        "() => document.querySelector('ol.studio-timeline') !== null"
        " || document.getElementById('screenRuns').dataset.state === 'failed'")
    return page.locator("#studioStatus").inner_text()


def _choose_the_gates_decision(page: Page) -> None:
    """Open the Decisions screen and choose the seeded run's one open gate."""
    page.locator('[data-focus-key="action:showDecisions"]').click()
    page.wait_for_selector("#screenDecisions:not([hidden])")
    page.locator(f'[data-focus-key="decision:{RUN_ID}/{CONFIRM_GATE}"]').click()


def _wait_for_the_write_and_the_read_after_it(page: Page) -> None:
    """The READ first, and only then the sentence the write left behind.

    Both signals are waited on, and the ORDER is the whole point. It used to be
    the other way round -- the sentence first, then the read -- and that made
    this a sampling test rather than a guard: a write announces itself and then
    triggers the authoritative re-read of what it changed, and every read arm of
    the store blanked the notice, so the receipt was drawn for ONE animation
    frame and erased. A `wait_for_function` polls once per frame, so it caught
    that frame about half the time; three of six runs of this test failed, in
    both directions, for a defect that was in the product the whole time.

    Waiting for the read FIRST is what makes the sentence a durable fact on
    screen instead of a frame that happened to be sampled. It is also what makes
    the receipt read afterwards a READ rather than an echo of the body this
    window posted.
    """
    page.wait_for_function(
        "key => !document.querySelector(`[data-focus-key='${key}']`)"
        ".innerText.includes('gate idle')",
        arg=f"decision:{RUN_ID}/{CONFIRM_GATE}")
    page.wait_for_function(
        "() => document.getElementById('studioStatus').innerText"
        ".includes('durable receipt')")


def test_the_timeline_is_the_journal_in_order_and_names_every_record_kind(
        chromium: Browser, project: _Project) -> None:
    """Row for row against the durable records, read out of the store.

    The expected list is derived from the run directory rather than written
    down beside the seed, so a record the store rejects or reorders moves this
    assertion with it instead of being invisible to it.
    """
    page, window = _open(chromium, project)
    try:
        _read_the_run(page)
        rows = _timeline(page)
        assert [row["kind"] for row in rows] == project.record_kinds()
        # Each row names its kind twice: once in the protocol word a machine
        # reads and once in the plain sentence a person reads.
        for row in rows:
            assert row["prose"] and row["prose"] != row["kind"], row
        # The five steps of the real progression, in the one order they can
        # happen. An `attempt_event` answers with its own phase; the others
        # answer with their own name.
        assert [row["step"] for row in rows if row["step"]] == [
            "step: action_proposal", "step: action_request",
            "step: effect_lease", "step: execution_observed",
            "step: action_result"]
        assert window.problems == []
    finally:
        page.context.close()


def test_the_run_detail_never_shows_the_outcome_word_without_its_sentence(
        chromium: Browser, project: _Project) -> None:
    """Exit 0 is a fact about a process, and the detail refuses to confuse them.

    This journal's attempt boundary carries ``succeeded`` and exit code 0 while
    its immutable result says ``verification_failed``. In the run DETAIL --
    where this run stands, the outcome section, the timeline row -- every place
    the word is shown carries the sentence saying what it does not mean.

    The run LIST is a different container and it once did not; the test below
    is what holds that fix closed.
    """
    page, window = _open(chromium, project)
    try:
        _read_the_run(page)
        detail = page.locator(".studio-runs__detail")
        body = detail.inner_text()
        assert "verification_failed" in body
        note = ("Process exit 0 proves the process finished, not that the work "
                "was verified.")
        assert note in body
        # Not written once and left to cover the screen: every container in the
        # detail that shows the word carries its own copy.
        bare = detail.locator("li, section").evaluate_all(
            """boxes => boxes.filter(box =>
                 box.innerText.includes("verification_failed")
                 && !box.innerText.includes("proves the process finished"))
               .map(box => box.className + " :: "
                 + box.innerText.slice(0, 80).replace(/\\n/g, " / "))""")
        assert bare == [], bare
        # And the evidence this run claimed is drawn as UNVERIFIED, which is a
        # different word from a missing one and from a failed one.
        assert "unverified" in body
        assert window.problems == []
    finally:
        page.context.close()


def test_the_run_list_row_never_shows_the_outcome_word_without_its_sentence(
        chromium: Browser, project: _Project) -> None:
    """The first place a reader meets the word -- and a fixed defect's guard.

    Written red, against a defect rendering the surface found.
    ``studio-runs.js`` names ``VERIFICATION_FAILED_NOTE`` "the one sentence
    ``verification_failed`` must never appear without. The protocol word
    travels beside it, never instead of it." Three of the four places that show
    the word obeyed it -- ``positionRow``, ``outcomeSection``, ``timelineRow``
    -- and ``studio-view.latestRunCard`` obeyed it on the Overview.

    ``runSummary`` did not::

        if (typeof row.last_outcome === "string") {
          carried.unshift(chip(OUTCOME_CHANNEL[row.last_outcome] || "none",
            row.last_outcome));
        }

    So the run list drew ``✕ verification_failed`` on the row for this run, with
    no sentence anywhere in that row, and that row is the FIRST place a person
    meets the word -- before they have chosen anything to read. A reader who
    went no further than the list had been shown the protocol word instead of
    the fact, which is the one thing this product says it will never do.
    Measured in Chromium, the containers of ``#bodyRuns`` that show the word::

        LI                      (the run list row)   no sentence
        SECTION where-it-stands                      sentence present
        LI    studio-position                        sentence present
        SECTION outcome-and-verification             sentence present
        SECTION timeline                             sentence present
        LI    studio-row (the timeline row)          sentence present

    ``runRow`` now appends the note to the ``li`` BESIDE the button -- a
    button's accessible name is the words it contains -- from the same exported
    constant the detail draws. This test asks the ROW, so a bare chip reds it.
    """
    page, window = _open(chromium, project)
    try:
        page.locator("#navRuns").click()
        page.wait_for_selector(f'[data-focus-key="run:{RUN_ID}"]')
        row = page.locator(".studio-runs__list li").filter(
            has_text="verification_failed")
        assert row.count() == 1, "the list row stopped showing the outcome word"
        assert "proves the process finished" in row.inner_text(), (
            "the run list shows verification_failed with no explanation: "
            + row.inner_text().replace("\n", " / "))
        assert window.problems == []
    finally:
        page.context.close()


def test_the_run_screen_never_derives_a_word_the_journal_does_not_carry(
        chromium: Browser, project: _Project) -> None:
    """`envelope_status` is creation-time, and the screen says so out loud."""
    page, window = _open(chromium, project)
    try:
        _read_the_run(page)
        body = page.locator("#bodyRuns").inner_text()
        assert "Opened as is what the run was CREATED as" in body
        assert window.problems == []
    finally:
        page.context.close()


def test_the_run_screen_names_the_workflow_revision_the_run_froze(
        chromium: Browser, project: _Project) -> None:
    """The positive witness that replaced a marker for the unknowable.

    This screen used to say "A materialized plan records no template identity",
    and that was true: `graph_id` is minted per run and names no workflow, so
    the honest answer was that no revision could be shown. The run now freezes
    the reference into the configuration `config_digest` is taken over, and this
    reads it back through a real browser off a real server.

    The seeded run is opened with no workflow, so what is asserted here is the
    ABSENT half spoken in words -- which is the half a guess would have filled
    in. `tests/test_command_run_identity.py` holds the present half against the
    frozen document, and the source gate holds that this screen reads the
    configuration rather than the plan.
    """
    page, window = _open(chromium, project)
    try:
        _read_the_run(page)
        body = page.locator("#bodyRuns").inner_text()
        assert "A materialized plan records no template identity" not in body
        assert "Workflow" in body
        assert "Revision" in body
        # Absent is said, never left blank and never guessed.
        assert "none — this run was opened without one" in body
        assert "none — a run that follows no workflow follows no revision" in body
        assert window.problems == []
    finally:
        page.context.close()


# -- 2. a decision is a durable receipt --------------------------------------


def test_recording_a_decision_writes_a_receipt_this_window_then_reads_back(
        chromium: Browser, project: _Project) -> None:
    """One answer, one durable file, and the screen shows what it wrote.

    The receipt on screen is not the body this window posted: the write is
    followed by a READ of the run, and what is drawn is what came back. The
    durable check beside it is the store's own.
    """
    reach_the_confirm_gate(project.root, config_digest=DIGEST)
    page, window = _open(chromium, project)
    try:
        assert project.receipts() == []
        _read_the_run(page)
        _choose_the_gates_decision(page)
        page.locator('[data-focus-key="field:actor"]').fill(DECIDER)
        page.locator('[data-focus-key="field:actor"]').press("Tab")
        submit = page.locator('[data-focus-key="action:submitDecision"]')
        page.wait_for_selector(
            '[data-focus-key="action:submitDecision"]:not([disabled])')
        submit.click()
        _wait_for_the_write_and_the_read_after_it(page)

        receipts = project.receipts()
        assert len(receipts) == 1
        assert receipts[0].gate_id == CONFIRM_GATE
        assert receipts[0].actor == DECIDER
        assert receipts[0].action == "approve"
        # The gate, how many answers stood before this one, and the person --
        # in that order. The count is always there and never last: as an
        # optional suffix it collided across people, because `bob-1` answering
        # first mints what `bob` answering second would.
        assert receipts[0].receipt_id == f"receipt-{CONFIRM_GATE}-0-{DECIDER}"

        # The answer landed, so the gate is no longer waiting for one.
        assert "gate satisfied" in page.locator(
            f'[data-focus-key="decision:{RUN_ID}/{CONFIRM_GATE}"]').inner_text()
        # The read cleared the draft with the rest of the run's facts, so the
        # receipt is read by choosing the gate again -- which is the product
        # behaving as designed and not a second write.
        page.locator(
            f'[data-focus-key="decision:{RUN_ID}/{CONFIRM_GATE}"]').click()
        detail = page.locator(".studio-decisions__detail").inner_text()
        assert receipts[0].receipt_id in detail
        assert "satisfied" in detail
        assert "A decision is immutable" in detail
        assert DECIDER in detail
        assert window.writes("/decisions") == 1
        assert window.problems == []
    finally:
        page.context.close()


def test_the_receipt_sentence_outlives_every_read_the_write_itself_caused(
        chromium: Browser, project: _Project) -> None:
    """WRITTEN RED, against a defect this module was sampling instead of holding.

    Answering a gate dispatches one sentence -- "The decision is a durable
    receipt in this run's journal" -- and, in the same breath, three reads: the
    run detail and its controls, because the window refreshes what it changed,
    and the run LIST, because the server publishes a run frame before it answers
    the POST. Every read arm of the store wrote `notice: ""` on its success
    path. So the last read to land deleted the sentence, about twelve
    milliseconds after it appeared, and no person has ever read it.

    The measurement: the sentence was born at t+943.7ms and gone at t+956.1ms,
    erased by the run-list answer that arrived at t+953.5ms. One animation
    frame. The test above polls once per frame and therefore caught it three
    times in six, which is what a coin flip looks like when it is mistaken for
    a regression.

    A read may replace its OWN sentence and may say nothing at all, but it may
    not delete a sentence about what the person just did. This waits for all
    three reads to land -- the run list is the one that used to win the race, so
    its answer is what is waited on -- and then asserts the sentence is still
    there. It fails on the old store within a frame of the decision landing.
    """
    reach_the_confirm_gate(project.root, config_digest=DIGEST)
    page, window = _open(chromium, project)
    try:
        _read_the_run(page)
        _choose_the_gates_decision(page)
        page.locator('[data-focus-key="field:actor"]').fill(DECIDER)
        page.locator('[data-focus-key="field:actor"]').press("Tab")
        page.wait_for_selector(
            '[data-focus-key="action:submitDecision"]:not([disabled])')
        with page.expect_response(
                lambda answer: answer.url.endswith("/command/runs")
                and answer.request.method == "GET") as listed:
            page.locator('[data-focus-key="action:submitDecision"]').click()
            _wait_for_the_write_and_the_read_after_it(page)
        assert listed.value.ok
        # The run list has answered and the detail has been re-read. Nothing
        # further is in flight, and the sentence is a fact on screen rather
        # than a frame that happened to be sampled.
        page.wait_for_timeout(250)
        said = page.locator("#studioStatus").inner_text()
        assert "durable receipt" in said, (
            "a read the write itself caused erased the receipt: " + repr(said))
        assert window.problems == []
    finally:
        page.context.close()


def test_a_decision_pressed_while_the_stream_is_down_refuses_and_writes_nothing(
        chromium: Browser, project: _Project) -> None:
    """With the stream down the decision control closes, and says why.

    This test first held the opposite: the control stayed pressable while the
    two workflow write controls disabled themselves, which was reported as a
    minor asymmetry rather than a defect because the door refused loudly and
    nothing durable moved. It was still a control that looked available while
    nothing could be written, which is the thing this screen exists not to do.
    It now matches its neighbours.

    Disabled is not enough on its own, and the assertions below say so: a greyed
    button with no sentence is a dead end, so the reason has to be on screen,
    the typed actor has to survive, and nothing may reach the durable store.

    It sits with the other decision witnesses rather than in
    ``test_studio_lifecycle``: they share this seed AND the seeding that lets
    the plan reach the gate, and that module was one line under its cap.
    """
    reach_the_confirm_gate(project.root, config_digest=DIGEST)
    page, window = _open(chromium, project, double=True)
    try:
        _read_the_run(page)
        _choose_the_gates_decision(page)
        page.locator('[data-focus-key="field:actor"]').fill(DECIDER)
        page.locator('[data-focus-key="field:actor"]').press("Tab")
        submit = page.locator('[data-focus-key="action:submitDecision"]')
        page.wait_for_selector(
            '[data-focus-key="action:submitDecision"]:not([disabled])')
        page.evaluate("() => window.__stream.fire('error')")
        page.wait_for_selector('#studioConnection[data-connection="closed"]')

        assert submit.is_disabled(), (
            "the decision control stayed pressable while nothing could be written")
        said = page.locator(".studio-decide").inner_text()
        assert "connection is down" in said, (
            "the control closed without saying why: " + said)
        assert page.locator(
            '[data-focus-key="field:actor"]').input_value() == DECIDER, (
            "the drop discarded what the reader had already typed")
        assert window.writes("/decisions") == 0
        assert project.receipts() == []
        assert window.problems == []
    finally:
        page.context.close()


#: Two starting states and two landed reads, driven through the module the page
#: really loaded. Both starting states are built by the reducer's OWN arms: the
#: person's by the `status` arm a control dispatches into, the read's by a
#: run-list answer this build cannot read. Answers with both sentences as well
#: as both outcomes, so the caller can check the setup was real.
_PROVENANCE = """() => Promise.all([import("/panel/studio-store.js"),
    import("/panel/studio-i18n.js")]).then(([module, i18n]) => {
  const landed = [
    ["runs-loaded", {payload: {runs: [], providers: []}}],
    ["workflows-loaded", {payload: {project: null, workflows: [],
                                    starters: [], providers: []}}],
  ];
  const human = module.reduce(module.EMPTY,
    {type: "status", notice: "The decision is a durable receipt."});
  const read = module.reduce(module.EMPTY,
    {type: "runs-loaded", payload: {runs: "not a list"}});
  return [human.notice, i18n.noticeText({locale: "en"}, read.notice),
    landed.map(([type, event]) => module.reduce(human, {type, ...event}).notice),
    landed.map(([type, event]) => module.reduce(read, {type, ...event}).notice)];
})"""


def test_a_read_replaces_its_own_sentence_and_never_the_persons(
        chromium: Browser, project: _Project) -> None:
    """The rule above, in the shipped reducer, in both directions.

    The rendered witness proves the decision receipt survives. This proves the
    RULE it survives by, on every arm that lands a read, and proves the other
    half with it: a sentence a READ wrote is still cleared by the next read that
    succeeds. Without that half, a stale "could not be read" would sit under a
    run that reads perfectly well, and the fix would have traded one lie for
    another.

    Constructing either starting state by hand would be this test deciding what
    the two provenances are, which is the one thing it exists to check the
    shipped module decides -- so `_PROVENANCE` builds both through the arms.
    """
    page, window = _open(chromium, project)
    try:
        said, refused, kept, cleared = page.evaluate(_PROVENANCE)
        # Both starting states are real: one sentence from the person, one from
        # a read that failed. Neither is asserted from the outside.
        assert said == "The decision is a durable receipt.", said
        assert "could not be read" in refused, refused
        assert kept == [said] * 2, kept
        assert cleared == ["", ""], cleared
        assert window.problems == []
    finally:
        page.context.close()


def test_a_decision_the_receipt_contract_refuses_never_reaches_the_wire(
        chromium: Browser, project: _Project) -> None:
    """The two answers that cannot be given without a reason are held here.

    The rule is `DecisionReceipt`'s own, asked at the control so a person is
    told what is missing instead of watching a request be rejected.
    """
    reach_the_confirm_gate(project.root, config_digest=DIGEST)
    page, window = _open(chromium, project)
    try:
        _read_the_run(page)
        page.locator('[data-focus-key="action:showDecisions"]').click()
        page.locator(
            f'[data-focus-key="decision:{RUN_ID}/{CONFIRM_GATE}"]').click()
        page.locator('[data-focus-key="field:actor"]').fill(DECIDER)
        page.locator('[data-focus-key="field:actor"]').press("Tab")
        page.locator('[data-focus-key="choice:waive"]').check()
        submit = page.locator('[data-focus-key="action:submitDecision"]')
        assert submit.is_disabled()
        assert "A reason is required when the answer is waive" in \
            page.locator(".studio-decide").inner_text()
        assert window.writes("/decisions") == 0
        assert project.receipts() == []
        assert window.problems == []
    finally:
        page.context.close()



def test_a_run_this_product_wrote_on_another_road_is_readable_in_the_studio(
        chromium: Browser, project: _Project) -> None:
    """One shape for a frozen configuration -- and a fixed defect's guard.

    Written red, against a defect rendering the surface found.
    ``studio-model.projectConfig`` required the run's frozen configuration to
    carry a cycle of EXACTLY one key::

        const CYCLE_KEYS = ["id"];
        if (!isPlainObject(value.cycle) || !exactKeys(value.cycle, CYCLE_KEYS))
          return null;

    and ``projectInstance`` allows exactly ``id``, ``adapter`` and ``model``.
    That matched ``studio_contracts.RunInput.snapshot`` -- the configuration
    the Studio's own open-run route writes -- and it did NOT match the two
    configurations this same product writes on its other roads:

        preview.FROZEN_CONFIG      cycle {"id": "preview-orbit",
                                          "phases": ["dispatch"]}
        control_loop.FROZEN_CONFIG cycle {"id": "control-loop-orbit",
                                          "phases": ["dispatch"]}

    Both go through ``RunStore.create_run`` and both land in the same
    ``conductor/runs`` directory the Studio lists. So a run written by
    ``conduct preview`` or by the control loop was LISTED on the Runs screen
    and could not be opened: ``projectRunRead`` answered null, ``runLoaded``
    took the failed arm, and the screen said "This run answered with a payload
    this build cannot read" -- for a run this product wrote itself, minutes
    earlier, with no corruption anywhere. Nor was the run merely unread: its
    decisions, its participants and its journal all move with that read, so all
    four screens went blank for it at once.

    The fix took the first of the two roads out: ``CYCLE_KEYS`` is
    ``["id", "phases"]`` now, the set stays CLOSED against a third key, and the
    window still reads nothing out of a cycle but its id. The seed is the
    production constant itself, so a change on either side moves this test
    rather than leaving it pinned to a copy of one.
    """
    page, window = _open(chromium, project)
    try:
        said = _choose_a_run_and_settle_either_way(page, PREVIEW_RUN)
        assert "this build cannot read" not in said, (
            "the Studio refuses a run its own product wrote: " + said)
        assert page.locator("#screenRuns").get_attribute("data-state") == "ready"
        assert page.locator("ol.studio-timeline").count() == 1
        assert window.problems == []
    finally:
        page.context.close()
