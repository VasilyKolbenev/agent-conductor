"use strict";
// Workflow writes share the boot module's one transport and session boundary.
import {draftFrom, saveProblems} from "./studio-store.js";
import {canonicalJson} from "./command-projection.js";
import {isId} from "./studio-model.js";

//: What a save or a publish says, stored as catalogue keys (`studio-notice-copy.js`).
const DRAFT_REFUSED = Object.freeze({key: "notice.draft_refused"});
const SAVED = Object.freeze({key: "notice.saved"});
const PUBLISHED = Object.freeze({key: "notice.published"});
const REOPENED = Object.freeze(["draft_changed", "draft_conflict"]);

class WorkflowWriters {
  constructor(door) { this.door = door; }
  onSaveDraft() {
    const {dispatch, write, refreshWorkflow} = this.door;
    const state = this.door.state();
    const held = state.workflows;
    const drawing = held.draft;
    if (drawing === null || !isId(this.door.chosenWorkflow())) {
      dispatch({type: "save", phase: "refused",
        notice: {key: "notice.save_choose_workflow"}});
      return;
    }
    if (saveProblems(drawing).length) {
      dispatch({type: "save", phase: "refused", notice: DRAFT_REFUSED});
      return;
    }
    // The document is read into a value ONCE and that value is what is judged,
    // what is sent, and what the confirming read is compared against.
    const written = JSON.parse(JSON.stringify(drawing));
    // Beside it, WHICH stored draft this window is replacing: the digest the
    // last read carried, or the claim that the last read carried none. It is
    // the same echo the publish body sends, one road earlier, and it is what
    // stops this save silently overwriting a draft another window stored after
    // this one last looked. `reviewedDigest` is exactly that answer and is
    // taken away by the read that would make it wrong.
    const body = held.reviewedDigest === null
      ? {document: written, expected_absent: true}
      : {document: written, expected_digest: held.reviewedDigest};
    const asked = this.door.chosenWorkflow();
    write("draft", asked, body, () => {
      // The answer belongs to the workflow it was asked about. If the Human
      // has moved on, it is not announced here and no read is provoked for a
      // workflow this write never touched.
      if (asked !== this.door.chosenWorkflow()) return;
      refreshWorkflow(asked, {kind: "draft", workflowId: asked,
        text: canonicalJson(written), phase: "saved", notice: SAVED});
    });
  }

  onPublish() {
    const {dispatch, write, refreshWorkflow} = this.door;
    const state = this.door.state();
    dispatch({type: "publish-review", open: true});
  }

  onPublishCancel() {
    const {dispatch, write, refreshWorkflow} = this.door;
    const state = this.door.state();
    dispatch({type: "publish-review", open: false});
  }

  onPublishConfirm() {
    const {dispatch, write, refreshWorkflow} = this.door;
    const state = this.door.state();
    const held = state.workflows;
    const number = held.nextRevision;
    if (!isId(this.door.chosenWorkflow()) || !held.publishable
        || !Number.isInteger(number)) {
      dispatch({type: "save", phase: "refused",
        notice: {key: "notice.publish_needs_saved"}});
      return;
    }
    const asked = this.door.chosenWorkflow();
    // The body names the revision expected, no document, and WHICH draft this
    // window reviewed. The draft the server holds is the one durable source,
    // read once by the route -- and the echo is what lets the route refuse when
    // that source moved between the review and this click.
    write("revisions", asked,
          {revision: number, reviewed_digest: held.reviewedDigest}, () => {
      if (asked !== this.door.chosenWorkflow()) return;
      refreshWorkflow(asked, {kind: "publish", workflowId: asked,
        revision: number, phase: "saved", notice: PUBLISHED});
    }, (result) => {
      // The two refusals a window can act on rather than only report, and the
      // recovery is one shape because the situation is: the review on screen is
      // of a document the server no longer holds. Leaving the panel open would
      // show a person that document above a Confirm now guaranteed to fail. So
      // the review is closed and the workflow is re-read, and what comes back
      // is what actually stands -- the newer DRAFT, which the person reviews
      // instead, or, when the draft was consumed rather than replaced, the
      // published REVISION, from which Edit as new draft is the road on.
      if (!REOPENED.includes(result.code) || asked !== this.door.chosenWorkflow()) return;
      dispatch({type: "publish-review", open: false});
      refreshWorkflow(asked);
    });
  }

  onStartWorkflow(request) {
    const {dispatch, write, refreshWorkflow} = this.door;
    const state = this.door.state();
    if (!isId(request.workflowId)) {
      dispatch({type: "status",
        notice: {key: "notice.workflow_id_grammar"}});
      return;
    }
    const starter = state.workflows.starters.find(
      (row) => row.starter_id === request.starterId) || null;
    const source = starter === null
      ? {schema_version: 1, title: request.workflowId, nodes: [], edges: []}
      : starter.document;
    if (!["", "bounded-run-v1", undefined].includes(request.executionContract)) return;
    const seed = {...source};
    if (request.executionContract === "bounded-run-v1") seed.execution_contract = "bounded-run-v1";
    else if (request.executionContract === "") delete seed.execution_contract;
    // The read goes first and the drawing lands on top of it: opening a name
    // that already exists must show what the server holds, not bury it.
    refreshWorkflow(request.workflowId);
    dispatch({type: "seed", document: draftFrom(seed)});
  }

  onEditPublished() {
    const {dispatch, write, refreshWorkflow} = this.door;
    const state = this.door.state();
    const held = state.workflows;
    const copy = held.detail === null ? null : draftFrom(held.detail.published);
    if (held.draft !== null || copy === null) {
      dispatch({type: "status", notice: held.draft !== null
        ? {key: "notice.copy_refused_drawing"} : {key: "notice.copy_refused_none"}});
      return;
    }
    dispatch({type: "seed", document: copy});
  }

  onValidate() {
    const {dispatch, write, refreshWorkflow} = this.door;
    const state = this.door.state();
    if (!isId(this.door.chosenWorkflow())) return;
    refreshWorkflow(this.door.chosenWorkflow(), null, true);
    dispatch({type: "status", notice: {key: "notice.validate_read_again"}});
  }
}

export function workflowWriters(door) {
  const writers = new WorkflowWriters(door);
  return Object.fromEntries(["onSaveDraft", "onPublish", "onPublishCancel", "onPublishConfirm", "onStartWorkflow", "onEditPublished", "onValidate"]
    .map((name) => [name, writers[name].bind(writers)]));
}
