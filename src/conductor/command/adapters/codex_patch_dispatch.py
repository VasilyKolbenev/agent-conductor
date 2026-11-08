"""The two phases of one opt-in Codex Do, under its existing durable action claim."""
from __future__ import annotations

import hashlib
from time import monotonic

from ..contracts import ActionRequest
from .deep_commands import OUTPUT_LIMIT_BYTES, PATCH_PROFILE
from .process import STDIN_DELIVERED
from .result_manifest import marked_policy

INSTRUCTION = (
    "\n\nPrepare the changes only. Your entire final answer must be one Codex patch starting "
    "with *** Begin Patch and ending with *** End Patch, without Markdown or commentary. "
    "Use Add, Update or Delete File with relative paths under the current task and existing "
    "parent directories. Do not edit files or run a patch tool. The application will validate "
    "and apply your patch; a separate participant will check the resulting files."
)


class PatchDispatch:
    def prepare(self, request):
        if (isinstance(request, ActionRequest) and request.capability == "dispatch"
                and request.arguments.get("profile") == PATCH_PROFILE
                and (not marked_policy(request) or not request.arguments.get("work_scope")
                     or self.patch_dispatch_version != PATCH_PROFILE or not self._confine)):
            raise self.error("a task-scoped bounded Codex subscription grant is required")
        return super().prepare(request)

    def _dispatch_process(self, request, args, work, before, task_text, model):
        if args.profile != PATCH_PROFILE:
            return super()._dispatch_process(request, args, work, before, task_text, model)
        # Imported here because result path validation derives reserved names from the catalogue.
        from . import codex_patch as patch
        from .patch_publish import PublishUnknown, publish

        if (not marked_policy(request) or not args.task_scope or not self._confine
                or self.patch_dispatch_version != PATCH_PROFILE
                or not self.boundary_provided("review")):
            return self._receipt(request, "failed", None, "patch dispatch requires a scoped grant")
        deadline = monotonic() + request.timeout_seconds
        cwd = work.relative_to(self._workspace.root).as_posix()
        payload = self._task_stdin(task_text + INSTRUCTION)
        if not self._task_fits_its_channel(self._review_argv, payload):
            return self._receipt(request, "failed", None, "patch instruction exceeds its bound")
        try:
            outcome = self._attempt(
                self._review_argv, cwd, mode="review", claim=self._claim_of(request), model=model,
                stdin_bytes=payload, timeout=patch.remaining(deadline), separate_stderr=True,
                output_limit=OUTPUT_LIMIT_BYTES[args.output_limit_profile])
            if (outcome.status != "completed" or outcome.exit_code != 0
                    or outcome.output_truncated):
                return outcome, self._evidence()
            if outcome.stdin_state != STDIN_DELIVERED:
                raise patch.PatchRefused("patch instruction was not delivered")
            if self._retained or self._login_residue or self._review_attempt_carries(outcome):
                raise patch.PatchRefused("patch proposal or its cleanup could not be admitted")
            ops = patch.parse_patch(outcome.output)
            if self._evidence() != before:
                raise patch.PatchRefused("task tree changed while preparing the patch")
            originals = {}
            prefix = self._workspace.subtree(work)
            for op in ops:
                _, image = patch.file_image(self._workspace, args, op.name)
                digest = hashlib.sha256(image[1]).hexdigest() if image is not None else None
                if before.get(prefix + op.name) != digest:
                    raise patch.PatchRefused("patch target changed after the proposal started")
                originals[op.name] = image
            proposed = patch.render_patch(self, args, cwd, ops, originals, deadline)
            if self._evidence() != before:
                raise patch.PatchRefused("task tree changed before patch publication")
            sensitive = self._sensitive_values()
            if any(value and value in image[1] for image in proposed.values()
                   if image is not None for value in sensitive):
                raise patch.PatchRefused("proposed file contains a protected value")
            publish(self._workspace, args, originals, proposed, deadline)
            expected = dict(before)
            for name, image in proposed.items():
                if image is None:
                    expected.pop(prefix + name)
                else:
                    expected[prefix + name] = hashlib.sha256(image[1]).hexdigest()
            if self._evidence() != expected:
                raise PublishUnknown()
            return outcome, expected
        except patch.PatchRefused as error:
            return self._receipt(request, "failed", None, str(error))
        except PublishUnknown:
            return self._receipt(request, "unknown", None, "patch outcome uncertain; do not replay")
