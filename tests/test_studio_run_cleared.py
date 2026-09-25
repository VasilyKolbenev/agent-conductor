"""Clearing the run on a task switch keeps the draft generations moving forward.

A write minted from a draft owns that draft's generation. If `run-cleared` sent
the counter back to zero, the same form retyped after the switch would land on
the same number, and the late answer of the OLD write would erase words nobody
sent (R07B of the review of `8dec0e4`, reopened by the task picker).
"""
from __future__ import annotations

from tests.test_studio_tasks import _js

TYPE = """
const type = (s, why) => {
  s = reduce(s, {type:'run-chosen', runId:'run-a'});
  s = reduce(s, {type:'step-chosen', nodeId:'identify'});
  s = reduce(s, {type:'step-edit', patch:{proposedBy:'alice'}});
  s = reduce(s, {type:'step-edit', patch:{rationale: why}});
  return reduce(s, {type:'document-edit', patch:{content: why}}); };
"""


def test_a_late_step_answer_never_spends_words_typed_after_the_run_was_cleared():
    body = TYPE + """
    let s = type(EMPTY, 'first, sent');
    const minted = s.runs.step.generation;
    s = type(reduce(s, {type:'run-cleared'}), 'SECOND, never sent');
    const retyped = s.runs.step.generation;
    s = reduce(s, {type:'step-spent', runId:'run-a', nodeId:'identify', generation: minted});
    console.log(JSON.stringify([retyped > minted, s.runs.step.rationale]));"""
    assert _js(body) == [True, "SECOND, never sent"]


def test_a_late_document_answer_never_spends_words_typed_after_the_run_was_cleared():
    body = TYPE + """
    let s = type(EMPTY, 'first, sent');
    const minted = s.runs.document.generation;
    s = type(reduce(s, {type:'run-cleared'}), 'SECOND, never sent');
    const retyped = s.runs.document.generation;
    s = reduce(s, {type:'document-spent', runId:'run-a', generation: minted});
    console.log(JSON.stringify([retyped > minted, s.runs.document.content]));"""
    assert _js(body) == [True, "SECOND, never sent"]


def test_run_cleared_still_empties_the_selection_the_detail_and_both_drafts():
    body = TYPE + """
    let s = reduce(type(EMPTY, 'words'), {type:'run-cleared'});
    console.log(JSON.stringify([s.runs.selectedId, s.runs.detail, s.runs.step.nodeId,
      s.runs.step.rationale, s.runs.document.runId, s.runs.document.content]));"""
    assert _js(body) == [None, None, None, "", None, ""]
