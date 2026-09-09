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


def _standing(name, category, standing, vendor=None):
    row = {"name": name, "category": category, "standing": standing}
    if vendor is not None:
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


def _detail(rows):
    return {"controls": {"isolation_facts": WORDS, "instances": [
        {"instance_id": name, "adapter_id": f"{name}-adapter", "model": None,
         "controls": ["dispatch"], "argument_schemas": {}, "isolation": rows}
        for name, rows in rows.items()]}}


def _render(page, detail, instance):
    return page.evaluate(
        """async ({detail, instance}) => {
          const {isolationFacts} = await import('/panel/studio-isolation.js');
          const nodes = isolationFacts(detail, {instance_id: instance});
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
        }""", {"detail": detail, "instance": instance})


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
    wire = {"instances": [
        {"instance_id": "alpha", "adapter_id": "alpha-adapter", "model": None,
         "controls": ["dispatch"], "argument_schemas": {}, "isolation": ALPHA}],
        "providers": [], "isolation_facts": WORDS}

    shown = page.evaluate(
        """async (wire) => {
          const {projectControls, wireControls} =
            await import('/panel/studio-controls.js');
          const {isolationFacts} = await import('/panel/studio-isolation.js');
          const settled = projectControls(wire);
          if (settled === null) return {refused: true};
          const nodes = isolationFacts(
            {controls: wireControls(settled)}, {instance_id: 'alpha'});
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
