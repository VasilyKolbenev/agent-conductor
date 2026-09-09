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

from dataclasses import replace

import pytest
from playwright.sync_api import Browser, Page

from conductor.command.artifacts import ArtifactDocument
from conductor.command.contracts import ABSENT
from conductor.command.graph_definition import GraphDefinition
from conductor.command.run_store import RunStore, snapshot_digest

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
    _a_proposal,
    _fact,
    _open_run,
    _read,
    _review,
    _two_steps,
    _type,
    bench,
)
from browser_tests.test_studio_step import _open as _open_bench
from browser_tests.test_studio_step_offers import _type_into
from browser_tests.test_studio_step_offers import _open_run_under, _propose, _row_says
from tests.schedule_journal import routed_dalio
from tests.test_command_graph_projection import a_decision, settle_to_the_confirm_gate
from tests.test_command_run_store import a_run

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


def test_words_typed_while_the_document_write_is_in_flight_are_not_spent_by_it(
        chromium: Browser, project: _Project) -> None:
    """The publish is held on the wire; the person keeps composing.

    The accepted write spent what it posted and nothing typed since: the
    editor holds the later words once the run has been read again, and the
    posted bytes are the earlier ones.
    """
    page, window = _open(chromium, project)
    try:
        _read(page, RUN_ID)
        _publish_form(page)
        _choose_ref(page, LONE_AWAITED_REF)
        _type_document(page, "first document")
        held: list = []
        page.route(f"**/command/runs/{RUN_ID}/artifacts",
                   lambda route: held.append(route))
        with page.expect_request(lambda request: request.method == "POST"
                                 and request.url.endswith("/artifacts")):
            page.locator('[data-focus-key="document:publish"]').click()
        for _ in range(40):
            if held:
                break
            page.wait_for_timeout(25)
        assert len(held) == 1, held
        control = page.locator('[data-focus-key="field:content"]')
        control.click()
        page.keyboard.press("End")
        # No Tab: the words are uncommitted when the answer lands. The render
        # the answer provokes removes the focused textarea, whose `change`
        # moves the generation BEFORE the spend compares it (the fold
        # review's R6) -- the order inside the carry is what holds this.
        page.keyboard.type(" and the next thing")
        held[0].continue_()
        page.unroute(f"**/command/runs/{RUN_ID}/artifacts")
        page.wait_for_function(
            "id => (document.querySelector('ul.studio-artifacts')?.innerText || '')"
            ".includes(id)", arg=f"{LONE_AWAITED_REF}-0")
        page.wait_for_function(
            "() => { const b = document.querySelector("
            "'[data-focus-key=\"document:publish\"]'); return b && !b.disabled; }")
        assert window.posted("/artifacts")[0]["content"] == "first document"
        assert control.input_value() == "first document and the next thing"
        assert _fact(page, "document", "Document id") == f"{LONE_AWAITED_REF}-1"
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


def _a_newer_document_moves_nothing(page: Page) -> None:
    """A newer document under either reference: durable, listed, and not what
    the standing proposal bound -- the instruction and the input alike, on
    the Confirm form and on the position row."""
    _publish_under(page, INSTRUCTION_REF, "A later revision that must not run.",
                   f"{INSTRUCTION_REF}-1")
    _publish_under(page, "artifact-plan", "# Plan, revised after the proposal.",
                   "artifact-plan-1")
    assert _instruction_fact(page, f"confirm:{DO}").startswith(
        f"durable document {INSTRUCTION_REF}-0")
    assert _fact(page, f"confirm:{DO}", "Input artifact-plan").startswith(
        "durable document artifact-plan-0")
    assert "bound by" in _row(page, DO) and f"{INSTRUCTION_REF}-0" in _row(page, DO)
    assert "Input artifact-plan bound by" in _row(page, DO)
    assert "artifact-plan-0" in _row(page, DO) and "artifact-plan-1" not in _row(page, DO)


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

        # The step's one INPUT is said beside its instruction, from nothing to
        # the newest document standing.
        assert _fact(page, f"propose:{DO}", "Input artifact-plan").startswith(
            "no durable document")
        _publish_under(page, "artifact-plan", "# Plan\n\nThe plan to carry out.",
                       "artifact-plan-0")
        assert _fact(page, f"propose:{DO}", "Input artifact-plan").startswith(
            "durable document artifact-plan-0")
        _publish_under(page, INSTRUCTION_REF, "Implement the reviewed plan.",
                       f"{INSTRUCTION_REF}-0")
        assert _instruction_fact(page, f"propose:{DO}").startswith(
            f"durable document {INSTRUCTION_REF}-0 · 28 bytes")
        _propose_do(page)
        assert _instruction_fact(page, f"confirm:{DO}").startswith(
            f"durable document {INSTRUCTION_REF}-0")
        assert _fact(page, f"confirm:{DO}", "Input artifact-plan").startswith(
            "durable document artifact-plan-0")
        assert "standing when this proposal was written" in page.locator(
            f'[data-step="confirm:{DO}"]').inner_text()

        _a_newer_document_moves_nothing(page)
        _confirm_do(page)
        results = [row for row in bench.records(BOUND_RUN, "action_result")
                   if row.attempt_id.startswith(f"attempt-{DO}-")]
        assert len(results) == 1, [row.attempt_id for row in results]
        assert bench.kinds(BOUND_RUN).count("artifact") == 4
        assert f"{INSTRUCTION_REF}-0" in _row(page, DO)
    finally:
        assert window.problems == []
        page.context.close()


@pytest.mark.parametrize("run_id,word", [
    ("run-closed", "complete"), ("run-halted", "stalled")])
def test_a_run_that_is_over_is_offered_no_document_form(
        chromium: Browser, bench: _Bench, run_id: str, word: str) -> None:
    """Both a complete plan and a stopped run offer no useless publication.

    The section says the run is over and draws no control; a document
    published now would be a durable record no step ever reads, and the
    form used to offer exactly that (the slice-3 review's #18).
    """
    page, window = _open_bench(chromium, bench)
    try:
        _read(page, run_id)
        section = page.locator('[data-section="documents"]')
        said = section.inner_text()
        assert f"This run is over: the plan is {word}" in said, said
        assert "none is offered" in said, said
        assert page.locator('[data-step="document"]').count() == 0
        assert page.locator('[data-focus-key="document:publish"]').count() == 0
        assert window.writes("/artifacts") == 0
    finally:
        assert window.problems == []
        page.context.close()


def test_a_review_row_names_every_input_bound_by_its_latest_proposal(
        chromium: Browser, bench: _Bench) -> None:
    """Review has no instruction ref, but its complete input list is visible.

    Two proposals surround two document generations; a third generation is
    newer than either proposal. The row must name generation two, for BOTH
    references, not the first proposal or whatever document is latest now.
    """
    run_id, node_id = "run-review-bindings", "review-inputs"
    refs = ("artifact-first", "artifact-second")
    node = _review(node_id)
    arguments = dict(node.arguments)
    arguments["target_artifact_refs"] = list(refs)
    store = RunStore(bench.root)
    _open_run(store, run_id)
    store.append(_two_steps(run_id, (replace(node, arguments=arguments),)))
    for generation in (1, 2, 3):
        for ref in refs:
            store.append(ArtifactDocument(
                artifact_id=f"{ref}-{generation}", artifact_ref=ref,
                run_id=run_id, created_at=NOW, media_type="text/plain",
                content=f"{ref} generation {generation}"))
        if generation < 3:
            proposal = _a_proposal(run_id, node_id, index=generation,
                                   attempt_id=f"attempt-review-{generation}")
            store.append(replace(proposal, arguments=arguments,
                                 input_binding="proposal-v1", preview_digest=""))
    page, window = _open_bench(chromium, bench)
    try:
        _read(page, run_id)
        row = _row(page, node_id)
        for ref in refs:
            assert f"Input {ref} bound by proposal-2" in row, row
            assert f"durable document {ref}-2" in row, row
            assert f"durable document {ref}-1" not in row, row
            assert f"durable document {ref}-3" not in row, row
        assert "Instruction " not in row
    finally:
        assert window.problems == []
        page.context.close()


@pytest.mark.parametrize("mode", ["observe", "propose", "policy", "confirm"])
def test_a_legacy_material_proposal_has_a_truthful_replacement_road(
        chromium: Browser, bench: _Bench, mode: str) -> None:
    """An old proposal stays readable; an authorized new preview binds inputs.

    The server's registered schema, not argument spellings, selects this road.
    No old digest is confirmed; the replacement is made by the real API, and
    lesser modes never inherit authority to confirm from this repair.
    """
    run_id, node_id = f"run-legacy-{mode}", "alpha"
    store = RunStore(bench.root)
    _open_run_under(store, run_id, mode)
    legacy = replace(_a_proposal(run_id, node_id, index=1,
                                 attempt_id="attempt-legacy-0"),
                     input_binding=ABSENT, preview_digest="")
    store.append(legacy)
    page, window = _open_bench(chromium, bench)
    try:
        _read(page, run_id)
        said = _row(page, node_id)
        assert "no material-binding revision" in said, said
        assert "bound by proposal-1" not in said, said
        assert page.locator(f'[data-step="confirm:{node_id}"]').count() == 0
        if mode == "observe":
            assert page.locator(f'[data-step="propose:{node_id}"]').count() == 0
            assert "nothing may be proposed" in said
            assert window.writes("/proposals") == 0
            return
        assert "Create a new proposal below" in said
        assert _propose(page, node_id) == 201
        proposals = bench.records(run_id, "action_proposal")
        assert len(proposals) == 2 and proposals[0] == legacy
        assert proposals[1].input_binding == "proposal-v1"
        assert proposals[1].preview_digest != legacy.preview_digest
        if mode == "confirm":
            page.wait_for_selector(f'[data-step="confirm:{node_id}"]')
            form = page.locator(f'[data-step="confirm:{node_id}"]').inner_text()
            assert proposals[1].proposal_id in form
            assert "no material-binding revision" not in form
        else:
            _row_says(page, node_id, "nothing can confirm it here")
            assert page.locator(f'[data-step="confirm:{node_id}"]').count() == 0
        assert window.writes("/actions") == 0
    finally:
        assert window.problems == []
        page.context.close()


def test_material_reproposal_uses_registered_schema_not_argument_names(
        chromium: Browser, bench: _Bench) -> None:
    """Native/other capabilities are not blocked by a deep-provider rule."""
    page, window = _open_bench(chromium, bench)
    try:
        actual = page.evaluate("""async () => {
          const {needsMaterialReproposal: held} = await import('/panel/studio-rundocs.js');
          const p = {instance_id:'same-instance', capability:'dispatch',
            node_id:'native',arguments:{instruction_ref:'looks-deep'}};
          const detail = schema => ({controls:{instances:[{instance_id:p.instance_id,
            controls:['dispatch','evidence'],
            argument_schemas:{dispatch:schema, evidence:'deep-arguments-v1'}}]}});
          const rule = [held(p,detail('deep-arguments-v1')),
            held(p,detail('structured-process-v1')), held(p,{controls:{instances:[]}}),
            held({...p,capability:'evidence'},detail('deep-arguments-v1')),
            held({...p,input_binding:'proposal-v1'},detail('deep-arguments-v1'))];
          const {stepControls} = await import('/panel/studio-runstep.js');
          const native = {...detail('structured-process-v1'),run:{run_id:'native',mode:'confirm'},
            records:[{record_type:'action_proposal',record:p}]};
          const shown = stepControls(p,{phase:'proposed'},{state:'runnable'},native,
            {connection:'open',runs:{step:{nodeId:'native',confirmedBy:'owner',generation:1}}},
            {chooseStep(){},editStep(){},confirmStep(){}});
          const form = shown.find(node => node.tagName === 'FORM');
          const {projectControls} = await import('/panel/studio-controls.js');
          const schema = value => projectControls({providers:[],isolation_facts:[],
            instances:[{
            instance_id:'native',adapter_id:'native',model:null,controls:['dispatch'],
            argument_schemas:value,isolation:[]}]});
          return {rule,form:shown.map(node => node.textContent).join(' '),
            disabled:form?.querySelector('button')?.disabled ?? true,
            schemas:[schema({}) !== null,schema({dispatch:'deep-arguments-v1'}) !== null,
              schema(null) === null,schema({dispatch:false}) === null,
              schema({review:'deep-arguments-v1'}) === null]};
        }""")
        assert actual["rule"] == [True, False, False, False, False]
        assert "Confirm this proposal" in actual["form"] and not actual["disabled"]
        assert "no material-binding revision" in actual["form"]
        assert actual["schemas"] == [True] * 5
    finally:
        assert window.problems == []
        page.context.close()


CHECKER_HISTORY_PROJECTION = """async () => {
  const {mountRuns} = await import('/panel/studio-runs.js');
  const mount = document.createElement('section'); document.body.append(mount);
  const record = (record_type, record) => ({record_type, record});
  const detail = {run:{run_id:'render-only'}, config:{}, graph:null, records:[
    record('artifact', {artifact_id:'rejected-product', artifact_ref:'result',
      source_action_id:'action-rejected', content:'kept only as history'}),
    record('action_result', {action_id:'action-rejected',outcome:'verification_failed'}),
    record('action_result', {action_id:'unrelated',outcome:'succeeded'}),
    record('evidence', {evidence_id:'evidence-signed',kind:'verification',
      verification:'verified',verified_by:'claude-code',verifier_instance_id:'checker'})]};
  mountRuns(mount, {runs:{selectedId:'render-only',list:[],detail}}, {});
  const result = {artifact:mount.querySelector('.studio-artifact').innerText,
    evidence:mount.querySelector('.studio-evidence').innerText,
    timeline:mount.querySelector('ol.studio-timeline').innerText};
  mount.remove(); return result;
}"""


def test_independent_verification_is_visible_before_authority_and_in_history(
        chromium: Browser, bench: _Bench) -> None:
    """Frozen facts come from a real run read; history rendering is a labeled
    projection fixture, not a claim that a paid checker has been executed.
    """
    run_id = "run-checker-preview"
    config = {"cycle": {"id": "default-orbit"}, "instances": [
        {"id": "claude-dev", "adapter": "claude-code", "model": "doer-model"},
        {"id": "checker", "adapter": "claude-code", "model": "checker-model"}]}
    store = RunStore(bench.root)
    store.create_run(a_run(run_id=run_id, mode="confirm",
                           config_digest=snapshot_digest(config)), config)
    store.append(_two_steps(run_id, (_review("checked", timeout_seconds=120,
        verifier_instance_id="checker"),)))
    page, window = _open_bench(chromium, bench)
    try:
        _read(page, run_id)
        form = page.locator('[data-step="propose:checked"]').inner_text()
        assert "checker · claude-code · checker-model" in form
        assert "result document this attempt produced" in form
        assert "64 KiB" in form and "JSON expansion counts" in form
        assert "2 × 120s = 240s" in form and "budget must cover both" in form
        assert "preflights and setup add wall-clock time" in form
        assert "none of the checker's prose becomes durable" in form
        assert "no independent checker" not in form
        assert _propose(page, "checked") == 201
        page.wait_for_selector('[data-step="confirm:checked"]')
        confirm = page.locator('[data-step="confirm:checked"]').inner_text()
        assert "checker · claude-code · checker-model" in confirm
        assert "2 × 120s = 240s" in confirm
        _read(page, "run-001")
        plain = page.locator('[data-step="propose:goal"]').inner_text()
        assert "same participant's adapter" in plain
        assert "no independent checker is named" in plain
        assert "Task time ceilings" not in plain
        shown = page.evaluate(CHECKER_HISTORY_PROJECTION)
        assert "checker" in shown["evidence"] and "claude-code" in shown["evidence"]
        assert "verifier_instance_idchecker" in shown["timeline"]
        assert "verification_failed" in shown["artifact"]
        assert "not used as input by later steps" in shown["artifact"]
        assert "not that the work was verified" in shown["artifact"]
        assert window.writes("/proposals") == 1 and window.writes("/actions") == 0
    finally:
        assert window.problems == []
        page.context.close()
