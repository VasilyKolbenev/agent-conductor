"""Publishing a document from the Runs screen, in a real Chromium.

R04 of the review of ``8dec0e4``: no screen could publish an artifact, so a
step waiting for a document was unblocked by a PowerShell block in the
acceptance script, and the shipped starter's first step -- whose instruction
is a document nothing had written -- could not be run from the product.

Two benches. The artifacts bench seeds a run whose lone waiter awaits a
document nobody publishes; the step bench serves a real executing fake, so a
dispatch proposed against a document really runs on it. Every claim is
measured on something durable -- the request log, the journal -- and the
screen is asked last.
"""
from __future__ import annotations

from playwright.sync_api import Browser, Page

from conductor.command.artifacts import ArtifactDocument
from conductor.command.graph_definition import GraphDefinition
from conductor.command.run_store import RunStore

from browser_tests.test_studio_artifacts import (  # noqa: F401
    EXTERNAL_REF,
    LONE_AWAITED_REF,
    LONE_WAITING_NODE,
    RUN_ID,
    _Project,
    project,
)
from browser_tests.test_studio_lifecycle import _open
from browser_tests.test_studio_step import (  # noqa: F401
    ACTOR,
    CONFIRM_GATE,
    DIGEST,
    NOW,
    WHY,
    _Bench,
    _fact,
    _open_run,
    _read,
    _type,
    bench,
)
from browser_tests.test_studio_step import _open as _open_bench
from browser_tests.test_studio_step_offers import _type_into
from tests.schedule_journal import routed_dalio
from tests.test_command_graph_projection import a_decision, settle_to_the_confirm_gate

BRIEF = "# Brief\n\nWhat this cycle is for."
LIMIT = 49152
#: The routed shipped plan, carried to its confirm gate and approved, so its
#: effecting step `do` is runnable -- the step whose instruction is the
#: starter's own reference, the one `conduct init` writes no file for. An
#: effect-capable step stands behind a gate by contract, so a plan of one
#: bare dispatch is refused; this is the plan a person really meets.
BOUND_RUN = "run-bound"
DO = "do"
INSTRUCTION_REF = "instruction-plan"


def _publish_form(page: Page) -> None:
    page.wait_for_selector('[data-step="document"]')


def _choose_ref(page: Page, ref: str) -> None:
    page.locator('[data-focus-key="field:artifact_ref"]').select_option(ref)


def _type_document(page: Page, words: str) -> None:
    """Type the document the way a person does, and commit it."""
    control = page.locator('[data-focus-key="field:content"]')
    control.click()
    page.keyboard.type(words)
    page.keyboard.press("Tab")


def _publish(page: Page) -> int:
    with page.expect_response(
            lambda answer: answer.url.endswith("/artifacts")) as waited:
        page.locator('[data-focus-key="document:publish"]').click()
    return waited.value.status


def _row(page: Page, node_id: str) -> str:
    """One position row, by its step's id AND kind: `do · task` is not the
    tail of `gate-confirm-do · gate`."""
    rows = page.locator("li.studio-position").evaluate_all(
        "items => items.map(item => item.innerText)")
    found = [row for row in rows if f"{node_id} · task" in row]
    assert len(found) == 1, (node_id, rows)
    return found[0]


def _documents(root, run_id: str) -> list:
    return [row.value for row in RunStore(root).read(run_id).records
            if row.kind == "artifact"]


# -- the form ------------------------------------------------------------------


def test_a_document_published_from_the_runs_screen_unblocks_the_step_waiting_for_it(
        chromium: Browser, project: _Project) -> None:
    """The acceptance script's step 12, without its PowerShell block.

    The lone waiter says which reference it waits for; the form offers that
    reference and no free text; the id is minted from it; the typed bytes are
    posted as the API's four fields and land in the journal; and, without a
    reload, the waiting sentence leaves the row and the document is listed.
    """
    page, window = _open(chromium, project)
    try:
        _read(page, RUN_ID)
        assert f"Waiting for artifact" in _row(page, LONE_WAITING_NODE)
        assert LONE_AWAITED_REF in _row(page, LONE_WAITING_NODE)
        _publish_form(page)
        offered = page.locator('[data-focus-key="field:artifact_ref"] option'
                               ).evaluate_all("items => items.map(i => i.value)")
        assert LONE_AWAITED_REF in offered and EXTERNAL_REF in offered, offered
        assert page.locator('[data-focus-key="document:publish"]').is_disabled()

        _choose_ref(page, LONE_AWAITED_REF)
        assert _fact(page, "document", "Document id") == f"{LONE_AWAITED_REF}-0"
        words = "# Plan\n\nThe plan this cycle follows."
        _type_document(page, words)
        assert _fact(page, "document", "Size") == (
            f"{len(words.encode('utf-8'))} of {LIMIT} bytes")
        assert _publish(page) == 201

        page.wait_for_function(
            "id => [...document.querySelectorAll('li.studio-position')].some("
            "item => item.innerText.includes(id + ' \\u00b7 ') "
            "&& !item.innerText.includes('Waiting for artifact'))",
            arg=LONE_WAITING_NODE)
        posted = window.posted("/artifacts")
        assert len(posted) == 1
        assert posted[0] == {"artifact_id": f"{LONE_AWAITED_REF}-0",
                             "artifact_ref": LONE_AWAITED_REF,
                             "media_type": "text/markdown", "content": words}
        durable = [row for row in _documents(project.root, RUN_ID)
                   if row.artifact_ref == LONE_AWAITED_REF]
        assert [row.artifact_id for row in durable] == [f"{LONE_AWAITED_REF}-0"]
        assert durable[0].content == posted[0]["content"]
        assert f"{LONE_AWAITED_REF}-0" in page.locator(
            "ul.studio-artifacts").inner_text()
        # The draft was spent: the editor is empty again for the next one.
        assert page.locator('[data-focus-key="field:content"]').input_value() == ""
    finally:
        assert window.problems == []
        page.context.close()


def test_the_document_id_counts_past_what_the_run_already_holds(
        chromium: Browser, project: _Project) -> None:
    """The greatest counter plus one, never the size of the set.

    `artifact-brief-1` stands, so the next under that reference is `-2`; and a
    lone `artifact-plan-7` -- a gap of seven -- makes the next `-8`, which is
    what tells "greatest plus one" from "count, then bump until free": the
    latter would mint `-1`, a free id an earlier document never held.
    """
    RunStore(project.root).append(ArtifactDocument(
        artifact_id=f"{LONE_AWAITED_REF}-7", artifact_ref=LONE_AWAITED_REF,
        run_id=RUN_ID, created_at=NOW, media_type="text/plain",
        content="a seventh plan, with none before it"))
    page, window = _open(chromium, project)
    try:
        _read(page, RUN_ID)
        _publish_form(page)
        _choose_ref(page, EXTERNAL_REF)
        assert _fact(page, "document", "Document id") == f"{EXTERNAL_REF}-2"
        _choose_ref(page, LONE_AWAITED_REF)
        assert _fact(page, "document", "Document id") == f"{LONE_AWAITED_REF}-8"
    finally:
        assert window.problems == []
        page.context.close()


def test_a_body_over_the_bound_is_refused_beside_the_control_and_never_sent(
        chromium: Browser, project: _Project) -> None:
    """The boundary's bound, met at the control rather than on the wire."""
    page, window = _open(chromium, project)
    try:
        _read(page, RUN_ID)
        _publish_form(page)
        _choose_ref(page, LONE_AWAITED_REF)
        control = page.locator('[data-focus-key="field:content"]')
        control.fill("x" * (LIMIT + 1))
        control.press("Tab")
        assert _fact(page, "document", "Size") == f"{LIMIT + 1} of {LIMIT} bytes"
        assert page.locator('[data-focus-key="document:publish"]').is_disabled()
        said = page.locator('[data-step="document"]').inner_text()
        assert f"1 bytes over the {LIMIT}-byte bound" in said, said
        page.locator('[data-focus-key="document:publish"]').click(
            force=True, no_wait_after=True, timeout=3000)
        assert window.writes("/artifacts") == 0
    finally:
        assert window.problems == []
        page.context.close()


def test_starting_from_an_existing_document_copies_its_bytes_into_the_editor(
        chromium: Browser, project: _Project) -> None:
    page, window = _open(chromium, project)
    try:
        _read(page, RUN_ID)
        _publish_form(page)
        page.locator('[data-focus-key="field:start_from"]').select_option(
            f"{EXTERNAL_REF}-1")
        page.locator('[data-focus-key="document:copy"]').click()
        assert page.locator('[data-focus-key="field:content"]').input_value() == BRIEF
        assert page.locator('[data-focus-key="field:media_type"]').input_value() == (
            "text/markdown")
        assert _fact(page, "document", "Size") == f"{len(BRIEF)} of {LIMIT} bytes"
    finally:
        assert window.problems == []
        page.context.close()


def test_what_is_typed_into_the_document_survives_a_read_of_the_run(
        chromium: Browser, project: _Project) -> None:
    """The draft is the reducer's, kept across a read of the same run."""
    page, window = _open(chromium, project)
    try:
        _read(page, RUN_ID)
        _publish_form(page)
        _choose_ref(page, LONE_AWAITED_REF)
        _type_document(page, "Half a document, kept")
        before = page.locator("ol.studio-timeline > li").count()
        # A real read, PROVEN to have landed: a record is appended first and
        # the timeline is waited on to grow past what the person was seeing.
        RunStore(project.root).append(ArtifactDocument(
            artifact_id="artifact-note-1", artifact_ref="artifact-note",
            run_id=RUN_ID, created_at=NOW, media_type="text/plain",
            content="a note on another reference"))
        page.locator(f'[data-focus-key="run:{RUN_ID}"]').click()
        page.wait_for_function(
            "n => document.querySelectorAll('ol.studio-timeline > li').length"
            " > n", arg=before)
        assert page.locator('[data-focus-key="field:content"]').input_value() == (
            "Half a document, kept")
        assert page.locator('[data-focus-key="field:artifact_ref"]').input_value() == (
            LONE_AWAITED_REF)
    finally:
        assert window.problems == []
        page.context.close()


# -- what the step forms say a proposal binds ------------------------------------


def _seed_the_run_at_its_effecting_step(store: RunStore) -> None:
    """The routed plan, its gate approved: `do` is the one runnable step."""
    _open_run(store, BOUND_RUN)
    drawn = routed_dalio()
    store.append(GraphDefinition(
        graph_id=drawn.graph_id, run_id=BOUND_RUN, created_at=drawn.created_at,
        nodes=drawn.nodes, edges=drawn.edges))
    settle_to_the_confirm_gate(store, run_id=BOUND_RUN, config_digest=DIGEST)
    store.append(a_decision(index=1, gate_id=CONFIRM_GATE, run_id=BOUND_RUN,
                            action="approve", config_digest=DIGEST))


def _publish_under(page: Page, ref: str, words: str, expected_id: str) -> None:
    """Publish one document under a reference and wait until the run lists it."""
    _publish_form(page)
    _choose_ref(page, ref)
    assert _fact(page, "document", "Document id") == expected_id
    _type_document(page, words)
    assert _publish(page) == 201
    # The list exists only once a document does, so the first wait is for the
    # list itself as much as for the id.
    page.wait_for_function(
        "id => (document.querySelector('ul.studio-artifacts')?.innerText || '')"
        ".includes(id)", arg=expected_id)


def _propose_do(page: Page) -> None:
    _type_into(page, DO, "proposed_by", ACTOR)
    _type_into(page, DO, "rationale", WHY)
    with page.expect_response(
            lambda answer: answer.url.endswith("/proposals")) as waited:
        page.locator(f'[data-focus-key="propose:{DO}"]').click()
    assert waited.value.status == 201, waited.value.json()
    page.wait_for_selector(f'[data-step="confirm:{DO}"]')


def _instruction_fact(page: Page, step: str) -> str:
    return _fact(page, step, f"Instruction {INSTRUCTION_REF}")


def _confirm_do(page: Page) -> None:
    """Confirm the standing proposal and wait for ONE MORE result.

    The settled steps before the gate already carry results, so the wait is
    for the count to grow past what the timeline shows now.
    """
    _type(page, "field:confirmed_by", ACTOR)
    results_before = page.evaluate(
        "() => [...document.querySelectorAll('ol.studio-timeline > li')]"
        ".filter(item => item.innerText.includes('action_result')).length")
    page.locator(f'[data-focus-key="confirm:{DO}"]').click()
    page.wait_for_function(
        "n => [...document.querySelectorAll('ol.studio-timeline > li')]"
        ".filter(item => item.innerText.includes('action_result')).length > n",
        arg=results_before, timeout=20000)


def test_the_step_forms_name_the_document_a_proposal_binds_and_keep_naming_it(
        chromium: Browser, bench: _Bench) -> None:
    """The Propose form: what a proposal made now would bind. The Confirm
    form: what the standing proposal bound -- and a document published after
    it does not move that. The plan the step reads and the instruction it
    runs are both published from this screen, and the road then completes;
    that the child READ the bound bytes is the transport's own witness
    (`tests/test_command_input_binding.py`), measured on its stdin.
    """
    _seed_the_run_at_its_effecting_step(RunStore(bench.root))
    page, window = _open_bench(chromium, bench)
    try:
        _read(page, BOUND_RUN)
        assert _instruction_fact(page, f"propose:{DO}") == "no durable document"
        said = page.locator(f'[data-step="propose:{DO}"]').inner_text()
        assert f"instructions/{INSTRUCTION_REF}.md" in said, said

        _publish_under(page, "artifact-plan", "# Plan\n\nThe plan to carry out.",
                       "artifact-plan-0")
        _publish_under(page, INSTRUCTION_REF, "Implement the reviewed plan.",
                       f"{INSTRUCTION_REF}-0")
        assert _instruction_fact(page, f"propose:{DO}").startswith(
            f"durable document {INSTRUCTION_REF}-0 · 28 bytes")
        _propose_do(page)
        assert _instruction_fact(page, f"confirm:{DO}").startswith(
            f"durable document {INSTRUCTION_REF}-0")
        assert "standing when this proposal was written" in page.locator(
            f'[data-step="confirm:{DO}"]').inner_text()

        # A newer document under the same reference: durable, listed, and
        # not what this proposal bound.
        _publish_under(page, INSTRUCTION_REF, "A later revision that must not run.",
                       f"{INSTRUCTION_REF}-1")
        assert _instruction_fact(page, f"confirm:{DO}").startswith(
            f"durable document {INSTRUCTION_REF}-0")
        assert "bound by" in _row(page, DO) and f"{INSTRUCTION_REF}-0" in _row(page, DO)

        _confirm_do(page)
        results = [row for row in bench.records(BOUND_RUN, "action_result")
                   if row.attempt_id.startswith(f"attempt-{DO}-")]
        assert len(results) == 1, [row.attempt_id for row in results]
        assert bench.kinds(BOUND_RUN).count("artifact") == 3
        assert f"{INSTRUCTION_REF}-0" in _row(page, DO)
    finally:
        assert window.problems == []
        page.context.close()
