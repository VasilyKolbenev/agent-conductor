"""Publishing a document from the Runs screen, and what the step forms say it binds.

R04 of the review of ``8dec0e4``, half (a): no screen could publish an
artifact, so a step waiting for a document could only be unblocked by a
PowerShell block in the acceptance script, and the shipped starter's first
step -- whose instruction is a document nothing had written -- could not be
run from the product. The form lives in ``studio-rundocs.js``, its draft's
arms in ``studio-rundraft.js``, and both are held here to the rules that make
a write safe to have at all:

1. **nothing is free text but the document.** The reference is chosen from
   what the plan reads, the id is minted from the reference, the kind of text
   is the boundary's closed pair -- so the four keys of the body are the
   API's own and only one of them is typed;
2. **the boundary's numbers are the boundary's.** The media types and the
   byte bound are copies of ``artifacts.py``'s, held equal here;
3. **what a person is typing survives.** The draft lives in the reducer, is
   kept across a read of the same run, cleared one generation on when another
   run is chosen, and spent only by the write minted from it; the live value
   of a focused control is carried across a render, by the same rule the step
   controls carry theirs;
4. **the step forms say which document a proposal binds.** The Propose form
   states what a proposal made now would bind, the Confirm form what the
   standing proposal bound, and both name the file road when no document
   stands -- read through one projection, ``studio-runread.boundDocument``,
   that cuts the journal where the transport cuts it.

Everything here is SOURCE; what a browser draws and posts is
``browser_tests/test_studio_documents.py``.
"""
from __future__ import annotations

import re
from pathlib import Path

from conductor.command.api_contracts import _ARTIFACT_FIELDS
from conductor.command.artifacts import ARTIFACT_CONTENT_LIMIT, ARTIFACT_MEDIA_TYPES

from tests.test_graph_source import _code
from tests.test_studio_runs import frozen_list

PANEL = Path(__file__).resolve().parents[1] / "src" / "conductor" / "panel"
DOCS = PANEL / "studio-rundocs.js"
DRAFT = PANEL / "studio-rundraft.js"
STEP = PANEL / "studio-runstep.js"
STORE = PANEL / "studio-store.js"
WORDS = PANEL / "studio-runwords.js"
WRITER = PANEL / "studio-runwrite.js"
READ = PANEL / "studio-runread.js"
RUNS = PANEL / "studio-runs.js"
BOOT = PANEL / "studio.js"
ARTIFACTS = PANEL / "studio-artifacts.js"


def _function(source: str, name: str) -> str:
    """One top-level function's body, by name."""
    found = re.search(rf"^(?:export )?function {name}\([^)]*\) \{{\n(.*?)\n\}}$",
                      source, re.DOTALL | re.MULTILINE)
    assert found is not None, f"no top-level function {name}"
    return found.group(1)


def _constant(source: str, name: str) -> str:
    found = re.search(rf"const {name} = (\d+);", source)
    assert found is not None, f"no numeric constant {name}"
    return found.group(1)


# -- 1. nothing is free text but the document ---------------------------------


def test_the_body_is_the_apis_four_fields_and_only_the_document_is_typed():
    """The four keys are `api_contracts._ARTIFACT_FIELDS`, derived not spelled."""
    docs = _code(DOCS)
    body = re.search(r"body: \{\n(.*?)\}\}\);", docs, re.DOTALL)
    assert body is not None, "the form submits no body"
    keys = set(re.findall(r"(\w+): ", body.group(1)))
    assert keys == set(_ARTIFACT_FIELDS), keys ^ set(_ARTIFACT_FIELDS)
    # The only free-text control is the document itself: no `input` at all.
    assert 'element("input"' not in docs
    assert docs.count('element("textarea"') == 1
    assert docs.count('element("select"') == 2


def test_the_reference_is_chosen_from_what_the_plan_reads():
    """Every input list the reviewed schema marks, plus every instruction ref."""
    refs = _function(_code(DOCS), "consumableRefs")
    assert "CAPABILITY_FIELDS[node.capability]" in refs
    assert "INPUT_KINDS.includes(kind)" in refs
    assert "name === INSTRUCTION_FIELD" in refs
    docs = _code(DOCS)
    assert 'const INPUT_KINDS = Object.freeze(["artifact-ids", "artifact-ids-required"]);' in docs
    assert 'const INSTRUCTION_FIELD = "instruction_ref";' in docs
    # A plan that reads no document is told so rather than offered a form.
    section = _function(docs, "documentSection")
    assert "refs.length" in section and "names no document reference" in section


def test_the_id_is_minted_from_the_reference_the_way_an_attempt_id_is():
    """Counted under both forms, bounded, bumped until free -- the R09 rule."""
    docs = _code(DOCS)
    mint = _function(docs, "documentId")
    assert "const named = `${ref}-`;" in mint
    assert "const digested = `${fnv64(ref)}.`;" in mint
    assert "countersUnder(named, ids), ...countersUnder(digested, ids)" in mint
    assert "plain.length <= ID_LIMIT ? plain : `${digested}${counter}`" in mint
    assert "Math.max(...taken) + 1" in mint
    assert "while (ids.includes(minted)) minted = spell(++counter);" in mint
    assert _constant(docs, "ID_LIMIT") == "128"
    # The digest is the step fragment's own function, held equal here rather
    # than imported: that fragment exports nothing but its builder.
    assert _function(docs, "fnv64") == _function(_code(STEP), "fnv64")


# -- 2. the boundary's numbers are the boundary's ---------------------------------


def test_the_media_types_and_the_byte_bound_are_copies_of_the_contracts():
    words = _code(WORDS)
    assert set(frozen_list(WORDS, "ARTIFACT_MEDIA_TYPES")) == set(
        ARTIFACT_MEDIA_TYPES)
    assert _constant(words, "ARTIFACT_CONTENT_LIMIT") == str(
        ARTIFACT_CONTENT_LIMIT)
    docs = _code(DOCS)
    stops = _function(docs, "whyNotPublishable")
    assert "bytes > ARTIFACT_CONTENT_LIMIT" in stops
    assert "!refs.includes(ref)" in stops
    assert "!content.trim()" in stops
    # Bytes, never characters: the bound is over UTF-8.
    assert "new TextEncoder().encode(value).length" in _function(docs, "byteLength")


# -- 3. what a person is typing survives ---------------------------------------


def test_the_draft_lives_in_the_reducer_and_is_spent_only_by_its_own_write():
    draft = _code(DRAFT)
    edited = _function(draft, "documentEdited")
    assert "const runId = state.runs.selectedId;" in edited
    assert 'const TYPED = Object.freeze(["artifactRef", "mediaType", "content"]);' in draft
    spent = _function(draft, "documentSpent")
    assert "held.runId !== event.runId || held.generation !== event.generation" in spent
    assert "document: documentCleared(held)" in spent
    assert "generation: document.generation + 1" in _function(draft, "documentCleared")
    store = _code(STORE)
    kept = re.search(r"function keptDrafts\(state, detail\) \{(.*?)\n\}", store,
                     re.DOTALL).group(1)
    assert ("document: same ? state.runs.document : "
            "documentCleared(state.runs.document)") in kept
    chosen = re.search(r"function runChosen\(state, runId\) \{(.*?)\n\}", store,
                       re.DOTALL).group(1)
    assert "document: documentCleared(state.runs.document)" in chosen
    assert '"document-edit": (state, event) => documentEdited(state, event.patch),' in store
    assert '"document-spent": documentSpent,' in store


def test_the_document_write_is_owned_like_a_step_write_and_reads_the_same_map():
    writer = _code(WRITER)
    door = re.search(r"^  function onDocumentWrite\(row\) \{\n(.*?)\n  \}$",
                     writer, re.DOTALL | re.MULTILINE)
    assert door is not None, "the writer holds no document road"
    body = door.group(1)
    assert "const spent = {runId: asked, nodeId: DOCUMENT_KEY," in body
    assert body.index('{type: "step-writing", ...spent, writing: true}') < body.index(
        'door.write("artifacts", asked, row.body,')
    assert 'door.dispatch({type: "document-spent", runId: asked,' in body
    assert body.rstrip().endswith(
        '}).finally(() => door.dispatch({type: "step-writing", ...spent,\n'
        "      writing: false}));")
    docs = _code(DOCS)
    assert 'export const DOCUMENT_KEY = "@document";' in docs
    assert "Object.hasOwn(writes, `${runId}/${DOCUMENT_KEY}`)" in _function(
        docs, "writingOf")
    # The live value of a focused control is carried across a render by the
    # step fragment's own rule, held equal here for the same reason as fnv64.
    assert _function(docs, "liveValue") == _function(_code(STEP), "liveValue")
    assert docs.count('liveValue(FORM, "') == 3
    assert 'const FORM = "document";' in docs


# -- 4. the step forms say which document a proposal binds -------------------


def test_the_step_forms_name_the_document_a_proposal_binds():
    step = _code(STEP)
    facts = _function(step, "instructionFacts")
    assert "no durable document" in facts
    assert "durable document ${show(bound.artifact_id)}" in facts
    assert "The one standing when this proposal was written." in facts
    assert "The one standing now: a proposal made now binds it" in facts
    assert "instructions/${ref}.md" in facts
    # The Propose form asks for the latest; the Confirm form for the bound.
    assert ": latestDocument(rows(detail.records), ref), false)" in _function(
        step, "planFacts")
    assert "boundDocument(\n      rows(detail.records), proposal.proposal_id, ref), true)" in _function(
        step, "proposalFacts")
    read = _code(READ)
    bound = _function(read, "boundDocument")
    # Cut at the proposal, as the transport cuts (`values_the_proposal_saw`).
    assert 'wrapper.record.proposal_id === proposalId' in bound
    assert bound.strip().endswith("return null;")
    # And the position row names what the latest proposal bound.
    runs = _code(RUNS)
    assert "item.append(...boundInstruction(detail, node));" in runs
    assert "documentSection(detail, state, handlers)," in runs


def test_the_document_fragment_exports_its_two_builders_and_mounts_nothing():
    """The fragment's shape, which is the step control's and not a mount's."""
    docs = _code(DOCS)
    assert set(re.findall(r"export function (\w+)\(", docs)) == {
        "documentSection", "boundInstruction"}
    assert "export default" not in docs
    assert "mount.replaceChildren(" not in docs
    assert "chip(" not in docs
    # The boot module names the road and hands the two callbacks through.
    boot = _code(BOOT)
    assert "artifacts: (id) => `/command/runs/${encodeURIComponent(id)}/artifacts`," in boot
    assert "editDocument: docs.editDocument," in boot
    assert "publishDocument: docs.publishDocument," in boot
    # And the inspector's sentence about an external input names the screen
    # that hands it over, no longer a route a person has to call.
    assert "under Publish a document" in _code(ARTIFACTS)
    assert "artifacts route" not in _code(ARTIFACTS)
