"""What a person actually SEES about isolation before they confirm a step.

The backend can be perfectly honest and the screen still show nothing, or show
a protection the server did not claim. These run the real modules in a real
Chromium, against payloads shaped like the ones the controls route sends.

Three questions, and they are the ones a person's decision turns on:
the words come from the SERVER and not from a copy this window keeps; only a
standing the server called `active` is drawn as a protection; and a different
binding draws a different answer, with nothing left over from the last one.
"""
from __future__ import annotations

from playwright.sync_api import Browser

from conductor.command.run_store import RunStore

from browser_tests.test_studio_step import (  # noqa: F401
    LONE, bench, _Bench, _open, _read,
)

#: One reference block and two bindings that disagree, in the wire's own shape.
#: `alpha` measured a vendor sandbox and pins a login directory; `beta` declares
#: neither, so the same two rows read `unknown` for it. Written here as literal
#: payloads rather than fetched, so what is being tested is the RENDERING.
WORDS = [
    {"name": "uncontained_route", "category": "refused_before_spawn",
     "sentence": "A work route that leaves the project root stops the dispatch."},
    {"name": "work_outside_the_item", "category": "detected_after_spawn",
     "sentence": "Files changed elsewhere inside the observed work tree are "
                 "found by comparing that tree after the child ran."},
    {"name": "login_directory_carries_configuration",
     "category": "refused_before_spawn",
     "sentence": "A pinned login directory that also carries configuration is "
                 "refused before any task."},
    {"name": "no_operating_system_boundary", "category": "not_isolated",
     "sentence": "This build starts an ordinary process with this user's rights."},
    {"name": "vendor_sandbox_is_the_vendors", "category": "not_isolated",
     "sentence": "Where a vendor ships a sandbox of its own, this build pins it."},
]


#: The vendor row carries its key ALWAYS, exactly as `facts_for` sends it, and
#: the value is the three-answer: `None` declares nothing, `[]` requests none,
#: pairs are the modes. A row that simply has no key is a different question and
#: gets no vendor line at all -- which is why the sentinel exists rather than a
#: `None` default that would spell those two the same way.
NO_VENDOR_QUESTION = object()


def _standing(name, category, standing, vendor=NO_VENDOR_QUESTION):
    row = {"name": name, "category": category, "standing": standing}
    if vendor is not NO_VENDOR_QUESTION:
        row["vendor_detail"] = vendor
    return row


ALPHA = [
    _standing("uncontained_route", "refused_before_spawn", "active"),
    _standing("work_outside_the_item", "detected_after_spawn", "active"),
    _standing("login_directory_carries_configuration",
              "refused_before_spawn", "active"),
    _standing("no_operating_system_boundary", "not_isolated", "stated_absence"),
    _standing("vendor_sandbox_is_the_vendors", "not_isolated", "active",
              [["dispatch", "--sandbox workspace-write"]]),
]
BETA = [
    _standing("uncontained_route", "refused_before_spawn", "active"),
    _standing("work_outside_the_item", "detected_after_spawn", "active"),
    _standing("login_directory_carries_configuration",
              "refused_before_spawn", "unknown"),
    _standing("no_operating_system_boundary", "not_isolated", "stated_absence"),
    _standing("vendor_sandbox_is_the_vendors", "not_isolated", "unknown", None),
]
#: The same binding as `ALPHA`, whose vendor row says the third answer: this
#: integration looked and requests no sandbox mode anywhere.
GAMMA = [*ALPHA[:-1],
         _standing("vendor_sandbox_is_the_vendors", "not_isolated",
                   "stated_absence", [])]


#: The road every fixture below is read on. The standings arrive keyed by
#: capability because a review and a dispatch on one binding do not run the same
#: checks; these payloads carry one road, and the road-selection rule itself is
#: driven by its own test at the bottom.
ROAD = "dispatch"


def _detail(rows):
    return {"controls": {"isolation_facts": WORDS, "instances": [
        {"instance_id": name, "adapter_id": f"{name}-adapter", "model": None,
         "controls": [ROAD], "argument_schemas": {},
         "isolation": {ROAD: standings}, "task_channel": None}
        for name, standings in rows.items()]}}


def _render(page, detail, instance):
    return page.evaluate(
        """async ({detail, instance, road}) => {
          const {isolationFacts} = await import('/panel/studio-isolation.js');
          const nodes = isolationFacts(
            detail, {instance_id: instance}, road);
          const host = document.createElement('div');
          for (const node of nodes) host.append(node);
          return {
            html: host.innerHTML,
            text: host.textContent,
            summary: host.querySelector('.studio-isolation-summary')?.textContent
              ?? '',
            active: [...host.querySelectorAll('[data-standing="active"]')]
              .map(node => node.dataset.fact),
            unknown: [...host.querySelectorAll('[data-standing="unknown"]')]
              .map(node => node.dataset.fact),
            instances: [...host.querySelectorAll('[data-instance]')]
              .map(node => node.dataset.instance),
          };
        }""", {"detail": detail, "instance": instance, "road": ROAD})


def test_the_words_a_person_reads_are_the_servers_own(chromium: Browser, bench):
    """No copy of the text lives in this window.

    Every sentence rendered is one the answer carried; a screen that kept its
    own wording would drift from the guards the table is written against, and
    the drift would be invisible until somebody compared them by hand.
    """
    page, _ = _open(chromium, bench)
    detail = _detail({"alpha": ALPHA})

    shown = _render(page, detail, "alpha")

    for row in WORDS:
        if row["name"] == "login_directory_carries_configuration":
            pass
        assert row["sentence"] in shown["text"], row["name"]
    page.context.close()


def test_only_what_the_server_called_active_is_drawn_as_a_protection(
        chromium: Browser, bench):
    """`unknown` reaches the screen as itself, never as a guarantee.

    The summary counts protections, and a row nobody measured is not one. This
    is the difference between telling a person what is standing and telling
    them what could be.
    """
    page, _ = _open(chromium, bench)

    alpha = _render(page, _detail({"alpha": ALPHA}), "alpha")
    beta = _render(page, _detail({"beta": BETA}), "beta")

    assert "login_directory_carries_configuration" in alpha["active"]
    # Said out loud as unsettled rather than dropped: silence about a check
    # reads as "nothing to say here", which is itself a reassurance.
    assert "login_directory_carries_configuration" in beta["unknown"]
    assert "login_directory_carries_configuration" not in beta["active"]
    assert "Not established for this configuration" in beta["text"]
    # Three protections for alpha, two for beta -- and the count is the summary's
    # own, so a screen that quietly counted unknowns would say four.
    assert "3 checks stand" in alpha["summary"]
    assert "2 checks stand" in beta["summary"]
    page.context.close()


def test_a_second_binding_draws_its_own_answer_and_leaves_nothing_behind(
        chromium: Browser, bench):
    """Switching the selected step may not leave the last one's guarantees up.

    The section is keyed to the binding it describes, and rendering another one
    produces that one's rows -- the vendor's own sandbox is named for alpha and
    is absent for beta, which is exactly the pair a stale screen would blur.
    """
    page, _ = _open(chromium, bench)
    detail = _detail({"alpha": ALPHA, "beta": BETA})

    alpha = _render(page, detail, "alpha")
    beta = _render(page, detail, "beta")

    assert alpha["instances"] == ["alpha"] and beta["instances"] == ["beta"]
    assert "workspace-write" in alpha["text"]
    assert "workspace-write" not in beta["text"]
    assert "Requested of the vendor" in alpha["text"]
    assert "Requested of the vendor" not in beta["text"]
    page.context.close()


def test_a_binding_the_server_did_not_describe_draws_nothing_reassuring(
        chromium: Browser, bench):
    """An absent answer is never rendered as a calm one.

    A step bound to an instance the controls answer says nothing about gets no
    section at all, rather than an empty one that reads as "nothing to worry
    about here".
    """
    page, _ = _open(chromium, bench)

    shown = _render(page, _detail({"alpha": ALPHA}), "somebody-else")

    assert shown["html"] == "" and shown["text"] == ""
    page.context.close()


def _wire(rows):
    return {"instances": [
        {"instance_id": "alpha", "adapter_id": "alpha-adapter", "model": None,
         "controls": [ROAD], "argument_schemas": {},
         "isolation": {ROAD: rows}, "task_channel": None}],
        "providers": [], "isolation_facts": WORDS}


def _through_the_projection(page, rows):
    """Render one binding the way the product does: wire → projection → screen."""
    return page.evaluate(
        """async (wire) => {
          const {projectControls, wireControls} =
            await import('/panel/studio-controls.js');
          const {isolationFacts} = await import('/panel/studio-isolation.js');
          const settled = projectControls(wire);
          if (settled === null) return {refused: true};
          const nodes = isolationFacts(
            {controls: wireControls(settled)}, {instance_id: 'alpha'},
            'dispatch');
          const host = document.createElement('div');
          for (const node of nodes) host.append(node);
          return {refused: false, text: host.textContent,
            vendor: host.querySelector(
              '[data-fact="vendor_sandbox_is_the_vendors"]')?.textContent ?? ''};
        }""", _wire(rows))


def test_the_roster_keeps_the_three_answers_and_drops_what_it_cannot_read(
        chromium: Browser, bench):
    """The same three answers one seam over, on the provider roster itself.

    The roster is DECORATION: a row it cannot read is dropped rather than taking
    the payload down. That rule and this field meet badly if the reader is
    careless, because there is no spare answer for "malformed" to fold into --
    `null` would report an unreadable declaration as "this integration declares
    nothing", and `[]` would hand the Agents screen "this vendor ships none" as
    a measured fact. So the row is dropped, and the three real answers survive.

    Driven through the real `projectProviders`, which is the function that
    dropped every row in this build when the server grew this seventh field.
    """
    page, _ = _open(chromium, bench)

    def row(provider_id, sandbox):
        return {"provider_id": provider_id, "display_name": "A provider",
                "availability": "available", "implementation": "real_experimental",
                "auth": "unpinned", "controls": ["dispatch"],
                "vendor_sandbox": sandbox}

    kept = page.evaluate(
        """async (rows) => {
          const {projectProviders} = await import('/panel/studio-model.js');
          return projectProviders(rows).map(
            (row) => [row.providerId, row.vendorSandbox]);
        }""", [row("declares-nothing", None), row("declares-none", []),
               row("declares-modes", [["dispatch", "--sandbox workspace-write"]]),
               row("malformed", [["dispatch"]]),
               row("also-malformed", "workspace-write")])

    assert kept == [
        ["declares-nothing", None],
        ["declares-none", []],
        ["declares-modes", [["dispatch", "--sandbox workspace-write"]]],
    ], kept
    page.context.close()


def test_the_three_vendor_answers_are_three_different_things_to_read(
        chromium: Browser, bench):
    """`unknown`, `stated_absence` and `active`, in words, not in an attribute.

    They were the same paragraph. The standing reached the DOM as
    `data-standing` and the visible text of "nobody has established this" was
    character-for-character the text of "this build openly does not do it" --
    a distinction for somebody with an inspector open, and invisible to the
    person actually deciding whether to authorize a run.

    Driven through the real projection, because that is where the shape that
    made the two indistinguishable lived: every row was handed a null
    `vendor_detail`, so "this is not a vendor question" and "nothing was
    declared" arrived at the render as one value.
    """
    page, _ = _open(chromium, bench)

    unknown = _through_the_projection(page, BETA)
    absent = _through_the_projection(page, GAMMA)
    active = _through_the_projection(page, ALPHA)

    for shown in (unknown, absent, active):
        assert shown["refused"] is False and shown["vendor"], shown
    assert unknown["vendor"] != absent["vendor"] != active["vendor"]
    assert unknown["vendor"] != active["vendor"]
    # And each says WHICH of the three it is, in its own words.
    assert "no reviewed declaration" in unknown["vendor"], unknown["vendor"]
    assert "requests NO vendor sandbox" in absent["vendor"], absent["vendor"]
    assert "Requested of the vendor" in active["vendor"], active["vendor"]
    # An absent flag is never written up as a finding about the vendor.
    assert "not a finding that the vendor ships none" in absent["vendor"]
    # The ordinary-process warning survives all three, and so does the line
    # between asking a vendor for a mode and proving the OS enforced one. The
    # words the SERVER writes about that are guarded where they are written
    # (tests/test_command_isolation_facts.py); what is asserted here is the
    # render's own sentence, which is the one the vendor's modes are printed in.
    for shown in (unknown, absent, active):
        assert "ordinary process" in shown["text"]
    assert "not a boundary this build imposes" in active["vendor"]
    page.context.close()


def test_an_unsettled_check_says_so_where_a_person_can_read_it(
        chromium: Browser, bench):
    """The same rule one row over: a standing is words, not a class name.

    `unknown` and `not_applicable` are different reasons a check is not
    standing, and both are different from a check that is. A screen that drew
    all three as one paragraph would let a person read "we did not look" as
    "there is nothing here to worry about".
    """
    page, _ = _open(chromium, bench)

    shown = _through_the_projection(page, BETA)

    assert "Not established for this configuration" in shown["text"]
    # And the row that carries it is the one the server left unsettled.
    unsettled = page.evaluate(
        """async (wire) => {
          const {projectControls, wireControls} =
            await import('/panel/studio-controls.js');
          const {isolationFacts} = await import('/panel/studio-isolation.js');
          const nodes = isolationFacts({controls: wireControls(
            projectControls(wire))}, {instance_id: 'alpha'}, 'dispatch');
          const host = document.createElement('div');
          for (const node of nodes) host.append(node);
          return [...host.querySelectorAll('.studio-isolation-standing')]
            .map(node => node.closest('li').dataset.fact);
        }""", _wire(BETA))

    assert unsettled == ["login_directory_carries_configuration"], unsettled
    page.context.close()


def test_the_screen_reads_what_this_windows_own_projection_hands_it(
        chromium: Browser, bench):
    """The seam between the projection and the render, run in one page.

    Every test above hands the render a payload directly, which is how a render
    is proved. This one takes the answer in the SHAPE THE SERVER SENDS, runs it
    through the strict projection and back out to the wire's spelling, and
    renders what comes out -- the only place the two spellings meet.

    It is here because that seam really broke: the projection kept the vendor's
    words under a camelCase name inside an otherwise snake_case row, the render
    read the key that was never there, and the section drew every sentence
    except the one about the vendor. Nothing was thrown and nothing was empty.
    A witness that renders a hand-written payload cannot see that at all.
    """
    page, _ = _open(chromium, bench)
    wire = _wire(ALPHA)

    shown = page.evaluate(
        """async (wire) => {
          const {projectControls, wireControls} =
            await import('/panel/studio-controls.js');
          const {isolationFacts} = await import('/panel/studio-isolation.js');
          const settled = projectControls(wire);
          if (settled === null) return {refused: true};
          const nodes = isolationFacts(
            {controls: wireControls(settled)}, {instance_id: 'alpha'},
            'dispatch');
          const host = document.createElement('div');
          for (const node of nodes) host.append(node);
          return {refused: false, text: host.textContent,
            active: [...host.querySelectorAll('[data-standing="active"]')]
              .map(node => node.dataset.fact)};
        }""", wire)

    assert shown["refused"] is False, "the strict projection refused a real answer"
    for row in WORDS:
        assert row["sentence"] in shown["text"], row["name"]
    # The vendor's own words survive the round trip, and they are the half a
    # spelling mismatch loses while everything beside them still renders.
    assert "Requested of the vendor" in shown["text"], shown["text"]
    assert "dispatch: --sandbox workspace-write" in shown["text"], shown["text"]
    assert "vendor_sandbox_is_the_vendors" in shown["active"]
    page.context.close()


def test_the_road_the_step_takes_is_the_road_that_is_drawn(
        chromium: Browser, bench):
    """One binding, two roads, two different answers -- and no borrowing.

    A review and a dispatch on one transport do not run the same checks: the
    instruction digest is a dispatch question and the read-only tree comparison
    is a review one. A screen keyed to the BINDING alone would have to show
    their union or their intersection, and each of those is false for one of the
    two steps a person confirms.

    Both directions are asserted, so a render that quietly fell back to the
    other road, or to the first road it found, fails here.
    """
    page, _ = _open(chromium, bench)
    detail = {"controls": {"isolation_facts": WORDS, "instances": [
        {"instance_id": "alpha", "adapter_id": "alpha-adapter", "model": None,
         "controls": ["dispatch", "review"], "argument_schemas": {},
         "isolation": {"dispatch": ALPHA, "review": BETA}, "task_channel": None}]}}

    def drawn(road):
        return page.evaluate(
            """async ({detail, road}) => {
              const {isolationFacts} = await import('/panel/studio-isolation.js');
              const host = document.createElement('div');
              for (const node of isolationFacts(
                detail, {instance_id: 'alpha'}, road)) host.append(node);
              return {text: host.textContent,
                summary: host.querySelector('.studio-isolation-summary')
                  ?.textContent ?? ''};
            }""", {"detail": detail, "road": road})

    dispatch, review = drawn("dispatch"), drawn("review")

    assert "3 checks stand" in dispatch["summary"], dispatch["summary"]
    assert "2 checks stand" in review["summary"], review["summary"]
    assert "on the dispatch road" in dispatch["summary"]
    assert "on the review road" in review["summary"]
    # The vendor's modes belong to the dispatch answer here and to no other.
    assert "workspace-write" in dispatch["text"]
    assert "workspace-write" not in review["text"]
    # And a road this binding does not declare draws nothing at all rather than
    # falling back to one it does.
    assert drawn("stop")["text"] == ""
    page.context.close()


#: A run of this module's own, so the section is met on a form nothing else
#: has already driven: opened under `confirm` authority, which is the only
#: authority that reaches a Confirm form at all.
ISOLATION_RUN = "run-isolation"


def test_the_section_stands_on_the_real_confirm_form_before_the_control(
        chromium: Browser, bench):
    """And it is on the form a person actually confirms from.

    Driven through the product: a real server answering `/controls` from the
    real registry, a real proposal posted by the real Propose control, and then
    the Confirm form the run offers. So this proves the section REACHES a
    person -- with the server's own words, joined by the server's own reference
    block -- rather than proving a module somebody could have called returns
    elements.
    """
    from browser_tests.test_studio_step_offers import _open_run_under, _propose

    _open_run_under(RunStore(bench.root), ISOLATION_RUN, "confirm")
    page, window = _open(chromium, bench)
    try:
        _read(page, ISOLATION_RUN)
        assert _propose(page, LONE) == 201
        page.wait_for_selector(f'[data-step="confirm:{LONE}"]')
        form = page.locator(f'[data-step="confirm:{LONE}"]')
        section = form.locator(".studio-isolation")

        assert section.count() == 1, "no isolation section on the Confirm form"
        placed = page.evaluate(
            """(step) => {
              const form = document.querySelector(`[data-step="${step}"]`);
              const section = form.querySelector('.studio-isolation');
              const control = form.querySelector('button');
              return {before: (section.compareDocumentPosition(control)
                  & Node.DOCUMENT_POSITION_FOLLOWING) !== 0,
                instance: section.dataset.instance,
                text: section.textContent};
            }""", f"confirm:{LONE}")

        assert placed["before"], "it was drawn after the authorizing control"
        # The step's own binding, and the third category, in front of a person
        # before they authorize anything.
        assert placed["instance"] == "claude-dev", placed["instance"]
        assert "ordinary process" in placed["text"], placed["text"]
        assert window.writes("/actions") == 0
    finally:
        assert window.problems == []
        page.context.close()
