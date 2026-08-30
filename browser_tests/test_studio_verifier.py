"""WHO confirms a step, drawn in a real Chromium and read back off the server.

``verifier_role_id`` is a durable field: ``TemplateNode`` stores it,
``GraphTemplate._roles_of`` counts it so a ``RunBinding`` must assign it,
``materialize`` freezes it into the plan as ``verifier_instance_id``, and
``graph_causality.permitted_verifier`` spends it. All of that was true before
this module existed and none of it was reachable: the inspector said the field
was not supported by this harness, and the run form could not ask who fills it.

The circuit this module drives, end to end and through the real wire: a person
NAMES a verifier role on a step, the draft route stores it, a revision freezes
it, and ``Open a run`` then asks who fills it -- including when the role belongs
to nobody else, which is the whole point of a separate reviewer.

Two rules are held from both sides rather than described:

* **A verifier is a role, not a picker over roles in use.** Typing a name no
  step carries out is first-class. A control that only offered existing roles
  would make a separate reviewer require a fictitious step to have carried the
  role first, so the datalist is a convenience and the text is the value.
* **A verifier needs a step that carries something out.**
  ``TemplateNode.__post_init__`` refuses one on a role-less step, so this window
  refuses it too -- beside the control, before the wire -- and clearing the
  role clears the verifier with it rather than leaving a draft that cannot be
  saved for a reason nobody typed.

A module of its own because ``test_studio_lifecycle`` is at the line cap. Its
boot, save and publish helpers are imported rather than re-spelled: one road to
a published revision, described in one place.
"""
from __future__ import annotations

import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Page

from conductor import server
from conductor.command.template_store import TemplateStore
from conductor.command.workflow_draft import WorkflowDraft

from browser_tests.test_studio_editing import _Recorder, _watch
from browser_tests.test_studio_lifecycle import _publish, _save_draft, _settle
from tests.test_store import good_lane, write_project

WORKFLOW_ID = "verifier-bench"
SAVED_AT = "2026-08-20T10:00:00Z"
#: The role the step carries out, and the role that confirms it. They are
#: deliberately different words, and the second is deliberately carried by NO
#: step as its own: that is the shape a separate reviewer takes, and the shape
#: a run form reading only `role_id` cannot ask about.
DOER_ROLE = "analyst"
VERIFIER_ROLE = "release-reviewer"
#: Two steps: one that carries something out and one that carries nothing. The
#: second is what makes the pairing refusal drivable through the real screen.
#: `observe` rather than `dispatch` on purpose -- an effecting step must stand
#: behind a gate, and this document is about a verifier and not about gating.
DRAFT = {
    "schema_version": 1,
    "title": "Verifier bench",
    "nodes": [
        {"node_id": "study", "kind": "task", "title": "Study the problem",
         "role_id": DOER_ROLE, "capability": "observe", "resources": []},
        {"node_id": "loose", "kind": "task", "title": "Carries nothing out",
         "resources": []},
    ],
    "edges": [],
}
VERIFIER_FIELD = '[data-edit-field="verifier_role_id"]'
ROLE_FIELD = '[data-edit-field="role_id"]'
#: Every role picker the run form writes, addressed as a group. `name^=` is what
#: makes this the FORM's own answer about how many roles it asks for, rather
#: than a list of names kept beside the test.
ROLE_PICKERS = "#workflowToolbar select[name^='role-']"


class _Project:
    """The served URL and the durable tree behind it, read after every write."""

    def __init__(self, url: str, root: Path) -> None:
        self.url = url
        self.root = root

    def templates(self) -> TemplateStore:
        return TemplateStore(self.root)

    def stored_node(self, node_id: str) -> dict:
        """One step of the draft the SERVER holds, never the drawing on screen."""
        draft = self.templates().load_draft(WORKFLOW_ID)
        assert draft is not None, "no draft is stored for this workflow"
        return next(row for row in draft.document["nodes"]
                    if row["node_id"] == node_id)


@pytest.fixture
def project(tmp_path) -> Iterator[_Project]:
    """A real server over a project holding the two-step draft above."""
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    TemplateStore(root).save_draft(WorkflowDraft(
        workflow_id=WORKFLOW_ID, saved_at=SAVED_AT, document=DRAFT))
    httpd = server.build(root, 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address[:2]
    try:
        yield _Project(f"http://{host}:{port}/", root)
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()
        assert not thread.is_alive(), "studio server did not stop"


def _open_the_workflow(page: Page) -> None:
    """Choose the seeded workflow and wait on the drawing and the write door."""
    page.locator("#navWorkflow").click()
    page.locator("#workflowToolbar select[name='workflow']").select_option(
        WORKFLOW_ID)
    page.wait_for_selector('.studio-canvas__banner[data-document="draft"]')
    page.wait_for_function(
        "() => document.querySelectorAll('[data-node-id]').length === 2")
    page.wait_for_selector(
        '#workflowToolbar [data-focus="action:onSaveDraft"]:not([disabled])')


class _Bench:
    """One opened Studio on the seeded draft, with its logs."""

    def __init__(self, page: Page, problems: list[str],
                 recorder: _Recorder) -> None:
        self.page = page
        self.problems = problems
        self.recorder = recorder

    def select(self, node_id: str) -> None:
        self.page.locator(f'[data-node-id="{node_id}"]').click()
        self.page.wait_for_selector(VERIFIER_FIELD)

    def verifier(self):
        return self.page.locator(VERIFIER_FIELD)

    def type_verifier(self, value: str) -> None:
        """Type a verifier role and commit it the way a person leaving a field does."""
        self.verifier().fill(value)
        self.verifier().press("Tab")

    def verification(self) -> str:
        return self.page.locator('[data-section="verification"]').inner_text()


@pytest.fixture
def bench(chromium: Browser, project: _Project) -> Iterator[_Bench]:
    context = chromium.new_context(viewport={"width": 1700, "height": 1400})
    page = context.new_page()
    problems = _watch(page)
    recorder = _Recorder(page)
    page.goto(project.url, wait_until="load")
    _settle(page)
    _open_the_workflow(page)
    try:
        yield _Bench(page, problems, recorder)
    finally:
        context.close()


# -- 1. a name nobody has used yet is a name this control accepts -------------


def test_a_verifier_role_no_step_uses_is_typed_saved_and_read_back(
        bench: _Bench, project: _Project) -> None:
    """The owner's rule, driven: a NEW name, through the wire, and back.

    The name is one no node carries as its own, so nothing could have offered
    it and nothing could have been picked. It is typed, and the assertion that
    matters is made against the draft the SERVER stored -- not against the
    drawing, which a window holding the change in a tab would satisfy just as
    well. The reload is the second half of that: what comes back is read off
    the store through a fresh page.
    """
    bench.select("study")
    assert bench.verifier().input_value() == "", "the seeded step names a verifier"
    bench.type_verifier(VERIFIER_ROLE)
    _save_draft(bench.page)

    stored = project.stored_node("study")
    assert stored["verifier_role_id"] == VERIFIER_ROLE, stored
    assert stored["role_id"] == DOER_ROLE, stored

    bench.page.reload(wait_until="load")
    _settle(bench.page)
    _open_the_workflow(bench.page)
    bench.select("study")
    assert bench.verifier().input_value() == VERIFIER_ROLE
    assert bench.problems == []


# -- 2. a verifier on a step that carries nothing out --------------------------


def test_a_verifier_on_a_step_with_no_role_is_refused_before_the_wire(
        bench: _Bench) -> None:
    """The contract's pairing rule, met beside the control instead of at the save.

    ``TemplateNode.__post_init__`` raises on this document, and the draft route
    runs every node through it -- so a window that posted it would meet a
    refusal about a step the person had already left. It is refused here, the
    step is named, and the count of writes is the proof that nothing was sent.
    """
    page = bench.page
    bench.select("loose")
    # The section says the rule in place, before anything is typed.
    assert "has nothing to verify" in bench.verification()
    bench.type_verifier(VERIFIER_ROLE)

    page.wait_for_function(
        "() => document.getElementById('workflowDiagnostics').innerText"
        ".includes('names a verifier role and binds no role of its own')")
    diagnostics = page.locator("#workflowDiagnostics")
    assert "local" in diagnostics.locator(".studio-diag__code").all_inner_texts()
    assert "Step loose names a verifier role" in diagnostics.inner_text()

    page.locator('#workflowToolbar [data-focus="action:onSaveDraft"]').click()
    page.wait_for_selector('#workflowToolbar [data-save="refused"]')
    assert bench.recorder.writes("/draft") == 0, (
        "a document this window had already refused was sent anyway")
    assert bench.problems == []


# -- 3. a name the contract could not store is refused, not posted -------------


def test_a_verifier_name_outside_the_id_grammar_is_refused_beside_the_control(
        bench: _Bench, project: _Project) -> None:
    """A control that validates, rather than one that posts and is rejected.

    The grammar is ``contract_values._ID_RE`` -- `studio-sections.ID_PATTERN` is
    held to it character for character by tests/test_studio_canvas.py -- so a
    spelling refused here is exactly one ``TemplateNode`` would refuse. The
    error sits beside the field and is announced through ``aria-describedby``,
    and the value never becomes an edit: the draft the server holds is the one
    it held before.

    The refused name breaks the grammar by ONE character, and that is
    deliberate: a name full of punctuation would still be refused by a control
    whose pattern had been widened, and this test would go on passing over a
    window that had stopped agreeing with the contract. A single space is the
    smallest thing the character class forbids.
    """
    page = bench.page
    bench.select("study")
    bench.type_verifier("release reviewer")

    error = page.locator("#studio-invalid-verifier_role_id")
    assert error.is_visible()
    assert "A verifier role must match" in error.inner_text()
    assert bench.verifier().get_attribute("aria-invalid") == "true"
    assert bench.verifier().get_attribute("aria-describedby") == \
        "studio-invalid-verifier_role_id"
    # Refused, so never committed and never sent: the stored draft is untouched.
    assert "verifier_role_id" not in project.stored_node("study")
    assert bench.recorder.writes("/draft") == 0
    assert bench.problems == []


# -- 4. clearing the role takes the verifier with it ---------------------------


def test_clearing_the_role_clears_the_verifier_and_the_draft_stays_savable(
        bench: _Bench, project: _Project) -> None:
    """A control a person did not touch may not make their draft unsavable.

    Clearing the role is the gesture; the verifier going with it is the rule.
    Without that, the document left behind is exactly the one the test above
    proves is refused, and the person would meet a refusal naming a field they
    had emptied nothing in. The save is what makes this a claim about a
    document the server accepted rather than about a field that looks blank.
    """
    page = bench.page
    bench.select("study")
    bench.type_verifier(VERIFIER_ROLE)
    page.wait_for_function(
        "() => document.querySelector('[data-edit-field=\\'verifier_role_id\\']')"
        ".value !== ''")

    role = page.locator(ROLE_FIELD)
    role.fill("")
    role.press("Tab")
    page.wait_for_function(
        "() => document.querySelector('[data-edit-field=\\'verifier_role_id\\']')"
        ".value === ''")

    _save_draft(page)
    stored = project.stored_node("study")
    assert "verifier_role_id" not in stored, stored
    assert "role_id" not in stored and "capability" not in stored, stored
    assert bench.problems == []


# -- 5. the run form asks for every role the revision names --------------------


def _publish_with_a_verifier(bench: _Bench) -> None:
    """Name the verifier, save, and publish -- the only road to a revision."""
    bench.select("study")
    bench.type_verifier(VERIFIER_ROLE)
    _save_draft(bench.page)
    _publish(bench.page)
    bench.page.wait_for_selector(
        '.studio-canvas__banner[data-document="published"]')


def test_open_a_run_asks_for_every_role_the_published_revision_names(
        bench: _Bench, project: _Project) -> None:
    """The roleNames witness, held against the contract rather than a name.

    ``GraphTemplate._roles_of`` counts a verifier role, so ``RunBinding.covers``
    demands an assignment for it and ``open_run`` refuses a binding that leaves
    one out. A form that read only ``role_id`` would therefore offer no picker
    for this revision's reviewer, assign nobody, and meet a refusal naming a
    role it had never shown -- with no control anywhere to answer it with.

    So the assertion is a RELATION: the pickers the form writes are exactly the
    roles the durable revision names. And the precondition is asserted rather
    than assumed -- the verifier role is carried by no step as its own, which is
    what makes this revision able to tell the two readings apart at all.
    """
    _publish_with_a_verifier(bench)
    page = bench.page
    page.wait_for_selector("#workflowToolbar select[name='run-mode']")

    revision = project.templates().load(WORKFLOW_ID, 1)
    assert VERIFIER_ROLE in revision.roles, revision.roles
    assert not any(node.role_id == VERIFIER_ROLE for node in revision.nodes), (
        "this witness needs a verifier role no step carries out as its own")

    offered = page.locator(ROLE_PICKERS).evaluate_all(
        "picks => picks.map(pick => pick.name.slice('role-'.length))")
    assert sorted(offered) == sorted(revision.roles), (offered, revision.roles)
    # And it is asked in the person's own words, beside a picker that starts
    # bound to nobody: an assignment is made deliberately, never defaulted.
    labels = page.locator("#workflowToolbar label").evaluate_all(
        "rows => rows.map(row => row.innerText)")
    assert any(f"Role {VERIFIER_ROLE}" in said for said in labels), labels
    assert page.locator(
        f"#workflowToolbar select[name='role-{VERIFIER_ROLE}']"
    ).input_value() == ""
    assert bench.problems == []


# -- 6. an immutable revision states it and refuses to be edited ---------------


def test_a_published_revision_states_the_verifier_and_disables_the_control(
        bench: _Bench) -> None:
    """A field that left the unsupported list must not leave the screen with it.

    The read-only half is the one that is easy to lose: a control disabled by
    being deleted would satisfy every "cannot be edited" assertion and tell a
    reader of a published revision nothing about who confirms its steps. Both
    are held -- the value is on screen and the control is shut -- which is how
    every other control on an immutable document behaves.
    """
    _publish_with_a_verifier(bench)
    page = bench.page
    page.locator('[data-node-id="study"]').click()
    page.wait_for_selector(VERIFIER_FIELD)

    assert bench.verifier().input_value() == VERIFIER_ROLE
    assert bench.verifier().is_disabled(), (
        "a published revision is immutable and its controls say so by being shut")
    assert page.locator(ROLE_FIELD).is_disabled()
    assert bench.problems == []
