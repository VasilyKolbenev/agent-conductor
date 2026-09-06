"""How a transport WRITES what it observed, for any vendor's one-shot CLI.

Split out of ``headless_cli`` when that module stood at the 800-line cap with
one seam still owed (the instruction a dispatch reads may now be a durable
document, bound at the proposal). The seam is the one the two earlier splits
found rather than a place to put spare lines: ``headless_routing`` holds how a
routed model becomes tokens; ``headless_values`` holds the values a spawn is
described with; this holds the four methods that turn an OBSERVATION into the
durable words a receipt or a verification may carry, and nothing that decides
what to observe.

Exit zero is an observation of the process and never a success -- every
sentence below says so, and the vendor's own exit-code contract decides only
how weakly. The receipt is ONE funnel, so an undiscarded home cannot escape
unsaid: ``_retained`` is read here and nowhere a provider could forget it.

What a mixin needs from the class it is mixed into is stated rather than
assumed: ``profile``, ``manifest``, ``_clock``, ``_ids`` and ``_retained``, all
of them ``HeadlessCliTransport``'s. Nothing here names a vendor, a model or a
path; ``headless_cli`` mixes it in and stays the one place a provider reaches
the shared machinery through.
"""
from __future__ import annotations

from ..contracts import ActionRequest, ActionResultReceipt
from .base import AdapterVerification
from .harness_profile import retained_detail
from .process import STDIN_INCOMPLETE, ProcessOutcome


class ReceiptWriting:
    """The words a receipt and a verification may carry, and the one funnel."""

    def _observed(
            self, request: ActionRequest,
            outcome: ProcessOutcome) -> ActionResultReceipt:
        """Report what was OBSERVED. Exit zero is an observation, not a success."""
        noun = self.profile.task_noun
        if outcome.status == "timed_out":
            return self._receipt(
                request, "failed", None,
                f"the {noun} exceeded its timeout and was terminated")
        if outcome.status == "stopped":
            return self._receipt(
                request, "cancelled", None,
                f"the {noun} was stopped by the runner")
        if outcome.stdin_state == STDIN_INCOMPLETE:
            # The mirror image of the capture bound below, and the earlier of the
            # two failures: there the answer was not read whole, here the QUESTION
            # was not delivered whole. A provider that takes its task on stdin and
            # exits zero without having received it has reported honestly about
            # something else, and no exit code can repair that. Checked before the
            # capture bound because a task never posed makes the answer moot.
            return self._receipt(
                request, "failed", None,
                f"the {noun} was never handed its whole instruction, so nothing "
                "it did can be read as an attempt at the one that was asked")
        if outcome.output_truncated:
            # The headless transport answers on stdout. A stream that overran the
            # capture bound was not read to its end, so whatever the exit code
            # says, this build did not see the answer -- and a bounded reader that
            # called that success would be lying about what it observed.
            return self._receipt(
                request, "failed", None,
                f"the {noun} wrote past the capture bound, so its result was "
                "never read whole and no success can be claimed for it")
        if outcome.exit_code == 0:
            return self._receipt(request, "succeeded", 0, self._zero_detail())
        return self._receipt(
            request, "failed", outcome.exit_code,
            f"the {noun} was observed to exit non-zero")

    def _zero_detail(self) -> str:
        """What an exit of zero is allowed to mean, given what the vendor published.

        Both readings end in the same place -- an observation of the process and
        never a verification of the work -- but they do not start in the same
        place, and a receipt that flattened them would overstate the weaker one.
        A vendor that documents no exit-code contract for its one-shot mode has
        not told this build what a zero means at all.
        """
        noun = self.profile.task_noun
        if self.profile.exit_codes_published:
            return (
                f"the {noun} was observed to exit zero; that is an observation "
                "of the process only, it is not a verification of the work, and "
                "this build cannot turn it into one")
        return (
            f"the {noun} was observed to exit zero; the vendor publishes no "
            "exit-code contract for this mode, so the code is read as the "
            "process having ended and as nothing else. It is not a verification "
            "of the work, and this build cannot turn it into one")

    def _receipt(
            self, request: ActionRequest, observed: str, exit_code: int | None,
            detail: str) -> ActionResultReceipt:
        """The one receipt funnel, so an undiscarded home cannot escape unsaid."""
        return ActionResultReceipt(
            receipt_id=self._ids("receipt"), action_id=request.action_id,
            run_id=request.run_id, attempt_id=request.attempt_id,
            instance_id=request.instance_id, outcome=observed,
            observed_at=self._clock(),
            detail=(detail + retained_detail(self.profile.tool_noun)
                    if self._retained else detail),
            exit_code=exit_code)

    def _verification(
            self, request: ActionRequest, state: str, refs: tuple[str, ...],
            detail: str) -> AdapterVerification:
        return AdapterVerification(
            adapter_id=self.manifest.adapter_id, action_id=request.action_id,
            state=state, observed_at=self._clock(), detail=detail,
            evidence_refs=refs)
