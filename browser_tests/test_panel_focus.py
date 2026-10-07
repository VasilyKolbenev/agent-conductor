"""Where a person is working, and what an authoritative render may take.

Split out of ``test_panel_confirm`` when that module crossed the line cap, and
along a real seam: that one is about the CONFIRM -- what it says, what reaches
the wire, what a refusal looks like -- and this is about the keyboard, on both
of the Cockpit's forms. It shares the seeded project, so the fixture and the
page helpers live next door and are imported: one description read twice.

Three properties, each measured before it was written and each with a mutation
that reds it:

- **a background read may not take the keyboard away.** The render replaces the
  focused node, and the restoration was skipped while the form was disabled --
  so a signal took the field from whoever was typing for the length of a read.
- **it may not take their PLACE either.** The field came back with the caret at
  the end, which moves somebody correcting a letter to the end of their word.
- **and it may not hand the keyboard back on a dead line.** A read still queued
  when the stream dropped lands afterwards, puts the phase back to
  `refreshing`, and -- if the line is not consulted -- re-opens both write
  doors. That one is the subtlest: the phase alone cannot tell it, because the
  disconnect's own render leaves a phase that is off the allowlist anyway.

Every witness here forces its collision inside a single task rather than
waiting for a timing window to repeat, and asserts that the collision really
happened, so none of them can pass by never colliding.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Browser, Page

from browser_tests.test_panel_confirm import (  # noqa: F401
    RUN_ID,
    _create_proposal,
    _load_run,
    _open,
    cockpit_url,
)


#: Focus a control, let the background refresh land INSIDE the same task, and
#: read where the keyboard is -- all without yielding to the event loop.
#:
#: `dispatchEvent` is synchronous, and so is everything the listener does up to
#: its first `await`: the phase moves, the form is re-rendered, and the focused
#: node is replaced, all before this function returns. So the read below is
#: taken at the exact instant the old test was sampling by luck. Nothing here
#: waits for a timing window to repeat.
_REFRESH_UNDER_FOCUS = """(asked) => {
  const control = document.querySelector(asked.selector);
  control.focus();
  const before = document.activeElement === control;
  window.dispatchEvent(new CustomEvent("conduct:run", {
    detail: Object.freeze({run_id: asked.runId})}));
  const active = document.activeElement;
  // BOTH names. These controls carry an id and a form name, and a probe that
  // picked one would report a real focus under a spelling the caller does not
  // use -- which reads exactly like the focus having been lost.
  return {before,
          id: active ? (active.id || "<body>") : "none",
          name: active ? (active.getAttribute("name") || "<none>") : "none",
          phase: document.getElementById("commandCockpit").dataset.phase};
}"""


def _settled(page: Page) -> None:
    """Wait until no read is in flight, so a dispatch really renders.

    `refreshSelectedRun` returns immediately when one is already running -- it
    only marks the work dirty -- so a signal sent into that window re-renders
    nothing. A witness that dispatched anyway would be asserting about a
    collision that did not happen, which is what its own `replaced` guard
    catches. Waiting for `ready` is what makes the collision real.
    """
    page.locator('#commandCockpit[data-phase="ready"]').wait_for()
    page.wait_for_function(
        "() => document.getElementById('commandCockpit')"
        ".dataset.phase === 'ready'")


def _refresh_under_focus(page: Page, selector: str) -> dict:
    _settled(page)
    return page.evaluate(_REFRESH_UNDER_FOCUS,
                         {"selector": selector, "runId": RUN_ID})


def test_a_background_refresh_never_takes_the_keyboard_out_of_the_confirm(
        chromium: Browser, cockpit_url: str) -> None:
    """WRITTEN RED, against a measured defect this suite was sampling.

    A run signal re-reads the authoritative facts, and that render replaces the
    node the person is typing in. The panel HAS a restoration for exactly this
    -- `renderConfirm` re-focuses the rebuilt control -- but it declined to
    when the form was disabled, and a background refresh disabled it. So the
    keyboard was taken away for the length of the read: measured at 8ms idle,
    and long enough under gate load that the test above failed twice on two
    different trees while passing eight times in a row on an idle host.

    The read here happens INSIDE the dispatch, so it cannot pass by luck: at
    the instant the refresh has re-rendered the form, the keyboard is still in
    the field, and the phase is asserted so this cannot pass by the refresh
    never having happened.
    """
    page, _recorder = _open(chromium, cockpit_url)
    try:
        _load_run(page)
        _create_proposal(page)

        seen = _refresh_under_focus(page, "#commandConfirmedBy")

        assert seen["before"] is True, "the control never took focus at all"
        assert seen["phase"] == "refreshing", (
            "the refresh did not land inside the dispatch, so this proves "
            "nothing about what a refresh does")
        assert seen["id"] == "commandConfirmedBy", seen
        # And it is still there once the read has landed.
        page.locator('#commandCockpit[data-phase="ready"]').wait_for()
        assert page.evaluate(
            "() => document.activeElement.id") == "commandConfirmedBy"
    finally:
        page.context.close()


def test_a_background_refresh_never_takes_the_keyboard_out_of_the_composer(
        chromium: Browser, cockpit_url: str) -> None:
    """The same claim on the form a person types in most, where it was worse.

    The composer had no restoration at all, so a refresh did not merely open a
    window -- the keyboard never came back. Measured: focus `rationale`, signal,
    and the document is left on `<body>` for good.

    The field is named, because a restoration that put a person in the FIRST of
    six controls would satisfy "focus is somewhere in the form" while moving
    them somewhere they did not choose.
    """
    page, _recorder = _open(chromium, cockpit_url)
    try:
        _load_run(page)

        seen = _refresh_under_focus(
            page, '.command-proposal-form [name="rationale"]')

        assert seen["before"] is True
        assert seen["phase"] == "refreshing", seen
        assert seen["name"] == "rationale", seen
        page.locator('#commandCockpit[data-phase="ready"]').wait_for()
        assert page.evaluate(
            '() => document.activeElement.getAttribute("name")') == "rationale"
    finally:
        page.context.close()


def test_a_refresh_takes_no_focus_into_a_form_nobody_was_working_in(
        chromium: Browser, cockpit_url: str) -> None:
    """The other direction, and the one a restoration gets wrong.

    Giving the keyboard back is only correct for somebody who had it. A render
    that focused its form whenever it ran would move a person reading the
    journal, or working the run-id field at the top, into a form they never
    opened -- which is the same theft this slice is removing, wearing the
    opposite sign.
    """
    page, _recorder = _open(chromium, cockpit_url)
    try:
        _load_run(page)
        _create_proposal(page)
        page.locator("#commandRunId").focus()

        seen = _refresh_under_focus(page, "#commandRunId")

        assert seen["phase"] == "refreshing", seen
        assert seen["id"] == "commandRunId", seen
        page.locator('#commandCockpit[data-phase="ready"]').wait_for()
        assert page.evaluate(
            "() => document.activeElement.id") == "commandRunId"
    finally:
        page.context.close()


#: Drop the line and read what THAT render left, inside a single task.
#:
#: `dispatchEvent` is synchronous, and so is the listener up to its first
#: `await`, so the three values below are the disconnect's own render and
#: nothing else's. Read them across separate round trips instead -- which is
#: what this witness used to do -- and the proposal's own run signal, arriving
#: on the REAL stream in between, starts a read that legitimately sets
#: `refreshing` (`command.js:290-292`, listener at `:366-370`). That is how the
#: normal gate went red on `2a1d8cc`, and no amount of quiescence beforehand
#: closes the window: the frame may arrive after the dispatch. What a read
#: landing behind a disconnect must NOT do is the last test in this module.
_DROP_THE_LINE = """() => {
  window.dispatchEvent(new Event("conduct:disconnected"));
  const actor = document.getElementById("commandConfirmedBy");
  const rationale = document.querySelector(
    '.command-proposal-form [name="rationale"]');
  return {phase: document.getElementById("commandCockpit").dataset.phase,
          confirm: actor ? actor.disabled : "gone",
          composer: rationale ? rationale.disabled : "gone"};
}"""


def test_a_lost_connection_still_shuts_both_forms_and_says_so(
        chromium: Browser, cockpit_url: str) -> None:
    """What a background read may take away, and what a DEAD LINE still must.

    The fix says a refresh is not a reason to shut a form. That is only honest
    if the reasons that remain still shut it, so the other side is asserted
    here on the phase that has always meant "nothing may be written": the
    connection is down, and neither form is workable until it is back.

    The phase and both doors are read in the disconnect's OWN task. `_settled`
    still runs first, for the reason it documents -- a dispatch into an
    in-flight read only marks the work dirty and re-renders nothing -- not
    because waiting could make a later frame impossible.
    """
    page, _recorder = _open(chromium, cockpit_url)
    try:
        _load_run(page)
        _create_proposal(page)
        assert not page.locator("#commandConfirmedBy").is_disabled()
        _settled(page)

        seen = page.evaluate(_DROP_THE_LINE)

        assert seen == {"phase": "stale", "confirm": True, "composer": True}
    finally:
        page.context.close()


#: The same forced collision as `_REFRESH_UNDER_FOCUS`, with the caret put
#: somewhere a person really puts one -- inside the word, not at either end --
#: and read back at the instant the refresh has re-rendered the form.
_REFRESH_MID_WORD = """(asked) => {
  const control = document.querySelector(asked.selector);
  control.focus();
  control.setSelectionRange(asked.at, asked.at);
  const before = {value: control.value,
                  start: control.selectionStart, end: control.selectionEnd};
  window.dispatchEvent(new CustomEvent("conduct:run", {
    detail: Object.freeze({run_id: asked.runId})}));
  const now = document.querySelector(asked.selector);
  const active = document.activeElement;
  return {before,
          replaced: now !== control,
          id: active ? (active.id || "<body>") : "none",
          name: active ? (active.getAttribute("name") || "<none>") : "none",
          value: now ? now.value : "<gone>",
          start: now ? now.selectionStart : -1,
          end: now ? now.selectionEnd : -1,
          phase: document.getElementById("commandCockpit").dataset.phase};
}"""


def test_a_refresh_gives_the_caret_back_where_the_person_left_it(
        chromium: Browser, cockpit_url: str) -> None:
    """WRITTEN RED. The field was given back; the place inside it was not.

    Focus alone is half the fact. A person correcting a letter in the middle of
    an actor name had their caret moved to the END by the re-render, so the
    rest of what they typed landed after the whole value instead of where they
    were. The owner's acceptance walk types an actor name and a reason, which
    is exactly where this is felt.

    The node really is replaced -- asserted, so this cannot pass on a build
    that stopped re-rendering -- and the caret comes back to the same offset in
    the same value.
    """
    page, _recorder = _open(chromium, cockpit_url)
    try:
        _load_run(page)
        _create_proposal(page)
        page.locator("#commandConfirmedBy").fill("release-owner")

        _settled(page)
        seen = page.evaluate(_REFRESH_MID_WORD, {
            "selector": "#commandConfirmedBy", "runId": RUN_ID, "at": 7})

        assert seen["phase"] == "refreshing", seen
        assert seen["replaced"] is True, (
            "the form was not re-rendered, so this proves nothing")
        assert seen["before"] == {"value": "release-owner", "start": 7, "end": 7}
        assert seen["id"] == "commandConfirmedBy", seen
        assert seen["value"] == "release-owner", seen
        assert (seen["start"], seen["end"]) == (7, 7), seen
    finally:
        page.context.close()


def test_the_composer_gives_the_caret_back_in_the_field_it_came_from(
        chromium: Browser, cockpit_url: str) -> None:
    """The same on the form with six controls, where the field is a choice too.

    A restoration that carried the caret but not the field, or the field but
    not the caret, would satisfy half of this. Both are asserted, on a value
    long enough that "the end" and "where they were" are far apart.
    """
    page, _recorder = _open(chromium, cockpit_url)
    try:
        _load_run(page)
        rationale = '.command-proposal-form [name="rationale"]'
        page.locator(rationale).fill("Implement the item.")

        _settled(page)
        seen = page.evaluate(_REFRESH_MID_WORD, {
            "selector": rationale, "runId": RUN_ID, "at": 9})

        assert seen["phase"] == "refreshing", seen
        assert seen["replaced"] is True
        assert seen["name"] == "rationale", seen
        assert seen["value"] == "Implement the item.", seen
        assert (seen["start"], seen["end"]) == (9, 9), seen
    finally:
        page.context.close()


#: The same forced collision, with `setSelectionRange` wrapped for its length.
#: A restoration that ran is recorded whatever offset it chose, so this sees
#: the ACT rather than a residue of it -- which is what the offsets it used to
#: read were, and why they moved with the timing.
_REFRESH_WATCHING_CARETS = """(runId) => {
  const proto = HTMLInputElement.prototype;
  const real = proto.setSelectionRange;
  const calls = [];
  proto.setSelectionRange = function (...args) {
    calls.push([this.id || this.getAttribute("name"), ...args]);
    return real.apply(this, args);
  };
  try {
    window.dispatchEvent(new CustomEvent("conduct:run", {
      detail: Object.freeze({run_id: runId})}));
  } finally {
    proto.setSelectionRange = real;
  }
  const el = document.getElementById("commandConfirmedBy");
  return {id: document.activeElement.id, calls,
          value: el ? el.value : "<gone>",
          phase: document.getElementById("commandCockpit").dataset.phase};
}"""


def test_a_person_who_was_not_typing_is_given_no_caret_anywhere(
        chromium: Browser, cockpit_url: str) -> None:
    """The control, and it is the one a restoration gets wrong.

    Handing back a place is only correct for somebody who had one. A render
    that placed a caret whenever it ran would put one in a form nobody opened.

    WHAT THIS DOES NOT MEASURE, and why: an earlier version of this witness
    asserted `selectionStart === 0` on the untouched control. That is not a
    fact about carets -- `fill()` leaves the offset at the END of the value
    whether or not the control has focus, and a REBUILT input reports 0 because
    its value came from an attribute -- so the assertion was really reading
    "was the node replaced", and it passed or failed with the timing. The call
    itself is watched instead: `setSelectionRange` is wrapped before the
    signal, and a restoration that ran would be recorded whatever offset it
    chose.
    """
    page, _recorder = _open(chromium, cockpit_url)
    try:
        _load_run(page)
        _create_proposal(page)
        page.locator("#commandConfirmedBy").fill("release-owner")
        page.locator("#commandRunId").focus()
        _settled(page)

        seen = page.evaluate(_REFRESH_WATCHING_CARETS, RUN_ID)

        assert seen["phase"] == "refreshing", seen
        # The keyboard stayed where the person really was.
        assert seen["id"] == "commandRunId", seen
        # No caret was placed anywhere, by anybody, during that render.
        assert seen["calls"] == [], seen
        # And the value they had typed survived, which is the older promise
        # this one sits beside rather than replaces.
        assert seen["value"] == "release-owner", seen
    finally:
        page.context.close()
@pytest.mark.parametrize("selector,named", [
    ('.command-proposal-form [name="timeout_seconds"]', "timeout_seconds"),
    ('.command-proposal-form [name="instance_id"]', "instance_id"),
])
def test_a_control_that_carries_no_caret_is_still_given_its_place_back(
        selector: str, named: str,
        chromium: Browser, cockpit_url: str) -> None:
    """WRITTEN RED. Not every control a person stands in has a caret.

    MEASURED in the browser this ships against, because the guard depends on
    which half of the pair misbehaves. READING `selectionStart` answers null on
    a `number` input and undefined on a `<select>` -- neither raises. WRITING
    raises: `setSelectionRange` gives `InvalidStateError` on the number input
    and `TypeError` on the select. So a build that treated the read's answer as
    a caret would raise while giving the place back.

    AND THAT RAISE IS INVISIBLE IN THE DOM, which is why this witness watches
    for it directly. The restoration is the last statement of the render, so
    the form is already complete when it throws -- and an exception inside an
    event listener does not propagate to whoever dispatched the event. Every
    assertion about the rendered page passes on the broken build; the first
    version of this witness did exactly that and survived its own mutation.
    """
    page, _recorder = _open(chromium, cockpit_url)
    raised: list[str] = []
    page.on("pageerror", lambda error: raised.append(str(error)))
    try:
        _load_run(page)
        _settled(page)

        seen = _refresh_under_focus(page, selector)

        assert seen["before"] is True, "the control never took focus"
        assert seen["phase"] == "refreshing", seen
        assert seen["name"] == named, seen
        # The render really finished: the form nobody focused is present too.
        assert page.locator(
            '.command-proposal-form [name="rationale"]').count() == 1
        # And it finished without raising. This is the assertion that sees the
        # defect; the ones above see only what survives it.
        page.wait_for_timeout(120)
        assert raised == [], raised
    finally:
        page.context.close()
#: Watch every render, not the end state. The regression this witnesses is a
#: MOMENT: a read that was already queued when the stream dropped lands
#: afterwards, sets the phase back to `refreshing`, and -- if the line is not
#: consulted -- re-opens the write door on a dead connection. Reading only the
#: settled page can miss it; this records what every render left behind.
_WATCH_RENDERS = """() => {
  const cockpit = document.getElementById("commandCockpit");
  window.__seen = [];
  const snap = () => {
    const actor = document.getElementById("commandConfirmedBy");
    const rationale = document.querySelector(
      '.command-proposal-form [name="rationale"]');
    const active = document.activeElement;
    window.__seen.push({
      phase: cockpit.dataset.phase,
      confirm: actor ? actor.disabled : "gone",
      composer: rationale ? rationale.disabled : "gone",
      active: active ? (active.id || active.getAttribute("name") || "<body>")
                     : "none"});
  };
  new MutationObserver(snap).observe(
    cockpit, {attributes: true, attributeFilter: ["data-phase"]});
  snap();
}"""

#: Queue a read, drop the line, and let the queued read land behind it.
#:
#: All three in one task, which is what makes the collision a fact rather than
#: a hope: the first signal starts a read and the second only marks the work
#: dirty, because `refreshSelectedRun` returns while one is in flight. The
#: disconnect then bumps the epoch, so the in-flight answer is discarded
#: WITHOUT rendering -- and the loop, still holding the dirty mark, starts a
#: second read whose first act is to set the phase to `refreshing`.
_QUEUE_THEN_DROP = """(runId) => {
  const signal = () => window.dispatchEvent(new CustomEvent("conduct:run", {
    detail: Object.freeze({run_id: runId})}));
  signal();
  signal();
  window.dispatchEvent(new Event("conduct:disconnected"));
}"""


def test_a_read_landing_behind_a_disconnect_never_reopens_the_write_door(
        chromium: Browser, cockpit_url: str) -> None:
    """WRITTEN RED, against a regression the focus fix introduced.

    A phase says what the last READ did, and any later read overwrites it. So a
    read still queued when the stream dropped lands afterwards and puts the
    phase back to `refreshing` -- and once a background refresh stopped
    disabling the forms, that re-opened both write doors on a dead connection.

    The disconnect test next door cannot see this: there the phase is `stale`,
    which is off the allowlist anyway, so the line is never what disables
    anything and dropping the line check leaves that witness green. This one
    drives the phase back onto the allowlist while the line is down, which is
    the only shape where the two differ.

    Every render is inspected rather than the settled page, and the run is
    asserted to have really gone through `refreshing` after the drop -- so this
    cannot pass by the collision never happening.
    """
    page, _recorder = _open(chromium, cockpit_url)
    try:
        _load_run(page)
        _create_proposal(page)
        _settled(page)
        page.locator("#commandConfirmedBy").focus()
        page.evaluate(_WATCH_RENDERS)

        page.evaluate(_QUEUE_THEN_DROP, RUN_ID)
        page.wait_for_function(
            "() => window.__seen.some(row => row.phase === 'stale')")
        page.wait_for_timeout(600)
        seen = page.evaluate("() => window.__seen")

        dropped = next(at for at, row in enumerate(seen)
                       if row["phase"] == "stale")
        after = seen[dropped:]
        assert any(row["phase"] == "refreshing" for row in after), (
            "no read landed behind the disconnect, so this proves nothing", seen)
        for row in after:
            assert row["confirm"] is True, (row, seen)
            assert row["composer"] is True, (row, seen)
            assert row["active"] != "commandConfirmedBy", (row, seen)
    finally:
        page.context.close()
