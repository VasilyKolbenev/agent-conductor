"""The single independent-check road, shared by every artifact-aware harness."""
from __future__ import annotations

from dataclasses import replace
from ..contracts import ABSENT, ControlMode
from .deep_commands import DeepReviewArgs, OUTPUT_LIMIT_BYTES
from .harness_profile import REVIEW_CAPABILITY
from .harness_workspace import work_route
from .independent_check import CheckFrameError, build_frame, scan_frame, verdict
from .feedback_protocol import parse_feedback, FEEDBACK_PROTOCOL, FeedbackProtocolError
from .result_manifest import MaterialManifestError, check_result_manifest, marked_policy


class IndependentCheckTransport:
    def _checker_answer(self, request, reason) -> AdapterVerification:
        mismatch = ("tree_changed", "rejected", "rejected_findings_refused")
        state = "mismatch" if reason in mismatch else "error"
        return self._verification(request, state, (), reason)

    def _check_owned(self, request, verifier, material) -> AdapterVerification:
        # No inherited count is read here any more. A doer that could not take
        # its own home back is refused at PUBLICATION now, from a fact recorded
        # inside that attempt's own turn -- which is the only reading that works
        # when the checker is a different instance, and the only one a sibling
        # action cannot corrupt. What is left here is this checker's own view of
        # the home root, which is its own to judge.
        self._begin_road()
        if self._workspace.sweep_homes():
            return self._checker_answer(request, "homes_refused")
        if self._workspace.is_verification_claimed(request.run_id, request.action_id):
            return self._checker_answer(request, "marker_standing")
        before = self._workspace.digest_work_tree()
        if material.after is None or dict(material.after) != before:
            return self._checker_answer(request, "tree_changed")
        args = (self._review_args(request.arguments) if request.capability == REVIEW_CAPABILITY
                else self._dispatch_args(request.arguments))
        frame = self._check_frame(request, args, material)
        scan_frame(frame, (*material.sensitive, *self._sensitive_values()))
        if self._preflight(request) is not None or self._retained:
            return self._checker_answer(request, "preflight_refused")
        if self._login_residue:
            # A preflight that already left undeclared state in the login
            # directory is not a preflight this verification may build on: the
            # task must not run after a promise this build has already broken.
            return self._checker_answer(request, "login_residue")
        # The preflight has no authority to alter the tree it is about to judge.
        if self._evidence() != before:
            return self._checker_answer(request, "tree_changed")
        self._workspace.claim_verification(request.run_id, request.action_id)
        outcome = self._attempt(
            self._verdict_argv, work_route(args.work_item_id, args.task_scope),
            timeout=request.timeout_seconds, stdin_bytes=frame.payload,
            separate_stderr=True, model=verifier.model,
            output_limit=(None if request.capability == REVIEW_CAPABILITY
                          else OUTPUT_LIMIT_BYTES[args.output_limit_profile]))
        if self._evidence() != before:
            return self._checker_answer(request, "tree_changed")
        if self._retained:
            return self._checker_answer(request, "homes_refused")
        if self._login_residue:
            # Its own word rather than the home one: two directories, two
            # promises, and a reader of the journal must be able to tell which
            # of them this verification could not keep.
            return self._checker_answer(request, "login_residue")
        reason = verdict(outcome)
        if reason != "verified":
            return self._feedback_answer(request, reason, outcome, material)
        answer = self._record_check(request, args, verifier, frame.digest)
        return replace(answer, result_manifest=material.result_manifest)

    def _check_frame(self, request, args, material):
        inputs = tuple(self._artifact_document(row) for row in material.input_documents)
        self._hold_check_inputs(request, args, material, inputs)
        manifest = None
        if request.capability == REVIEW_CAPABILITY:
            document = self._artifact_document(material.result_document)
            if (document.source_action_id != request.action_id or document.run_id != request.run_id
                    or document.artifact_ref != args.result_artifact_ref
                    or document.input_artifact_ids != material.input_artifact_ids):
                raise CheckFrameError("material_unavailable")
            digest, tree, contents = document.digest(), {}, {}
        elif marked_policy(request):
            digest = None
            tree, contents, manifest = self._check_manifest(request, args, material)
        else:
            digest, (tree, contents) = None, self._workspace.read_work_tree(
                args.work_item_id, material.changed, work_scope=args.task_scope)
        return build_frame(request, material, tree, contents, result_digest=digest, result_manifest=manifest,
                           sensitive=(*material.sensitive, *self._sensitive_values()))

    def _check_manifest(self, request, args, material):
        tree, contents, absent, subtree = self._workspace.read_result_tree(
            args.work_item_id, material.changed, work_scope=args.task_scope)
        try:
            manifest = check_result_manifest(material.result_manifest, request,
                material.input_artifact_ids, material.changed, tree, contents,
                absent=absent, subtree=subtree,
                sensitive=(*material.sensitive, *self._sensitive_values()))
        except MaterialManifestError as error:
            raise CheckFrameError(error.reason) from error
        return tree, contents, manifest

    def _hold_check_inputs(self, request, args, material, inputs) -> None:
        refs = (args.target_artifact_refs if request.capability == REVIEW_CAPABILITY
                else args.artifact_refs)
        ids = tuple(row.artifact_id for row in inputs)
        invalid = (any(row.run_id != request.run_id for row in inputs)
                   or tuple(row.artifact_ref for row in inputs) != refs)
        bound = material.instruction_document
        if bound is not None:
            document = self._artifact_document(bound)
            invalid |= (request.capability != "dispatch" or document.run_id != request.run_id
                        or document.artifact_ref != args.instruction_ref
                        or document.content != material.instruction)
            ids = (document.artifact_id, *ids)
        if invalid or ids != material.input_artifact_ids:
            raise CheckFrameError("material_unavailable")

    def _record_check(self, request, args, verifier, digest) -> AdapterVerification:
        if request.capability == REVIEW_CAPABILITY:
            evidence = self._handoff.record_review(
                request, args.result_artifact_ref, input_artifact_ids=None,
                content=None, adapter_id=self.manifest.adapter_id,
                verifier_instance_id=verifier.instance_id, expected_digest=digest)
        else:
            evidence = self._handoff.record_dispatch(
                request, adapter_id=self.manifest.adapter_id, digest=digest,
                verifier_instance_id=verifier.instance_id)
        if evidence is None or evidence.digest != digest:
            return self._checker_answer(request, "material_unavailable")
        return self._verification(request, "verified", (evidence.evidence_id,), "verified")

    def _feedback_answer(self, request, reason, outcome, material):
        answer = self._checker_answer(request, reason)
        if (reason != "rejected" or request.capability != "dispatch"
                or request.mode is not ControlMode.POLICY or request.run_authorization_id is ABSENT):
            return answer
        if material.result_manifest is None:
            return self._checker_answer(request, "material_unavailable")
        try:
            feedback = parse_feedback(outcome, opted_in_protocol=FEEDBACK_PROTOCOL,
                sensitive=tuple(dict.fromkeys((*material.sensitive, *self._sensitive_values(),
                                               *self._login_seen))))
        except FeedbackProtocolError:
            # The verdict line said REJECT; the typed protocol refused its findings (malformed, over
            # their bound, or quoting a sensitive value), so no correction can carry them -- a
            # rejection, not an absent verdict (live-nc-1).
            return self._checker_answer(request, "rejected_findings_refused")
        return replace(answer, feedback=feedback.canonical_bytes(), result_manifest=material.result_manifest)
