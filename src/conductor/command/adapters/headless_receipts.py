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
how weakly. Every receipt an attempt produces goes through ONE funnel, so an
undiscarded home cannot escape unsaid: ``_retained`` is read there and nowhere
a provider could forget it. There is a SECOND form beside it, and the two are
told apart by whether the workspace turn was ever taken: a refusal built before
it has minted nothing, so the counts standing on the transport are a sibling's,
and that form deliberately reads neither -- it may not report another action's
directory as this one's, and clearing them first would erase that sibling's own
refusal. See ``_bare_receipt``.

What a mixin needs from the class it is mixed into is stated rather than
assumed: ``profile``, ``manifest``, ``_clock``, ``_ids`` and ``_retained``, all
of them ``HeadlessCliTransport``'s. Nothing here names a vendor, a model or a
path; ``headless_cli`` mixes it in and stays the one place a provider reaches
the shared machinery through.
"""
from __future__ import annotations

from ..contracts import ActionRequest, ActionResultReceipt
from .base import AdapterVerification
from .harness_profile import LOGIN_RESIDUE_DETAIL, login_residue_detail, retained_detail
#: What this mixin needs from the class it is mixed into, stated rather than
#: assumed: `profile`, `_ids`, `_clock`, `manifest`, and the two cleanup
#: counters -- `_retained` for an attempt home that would not go, and
#: `_login_residue` for a pinned login directory that gained state nobody
#: declared. Both are read HERE and nowhere a provider could forget them --
#: in the funnel an attempt's receipt goes through, never in the pre-turn form
#: beside it, which speaks only for what its own action can answer for.
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

    def _residue_receipt(
            self, request: ActionRequest, outcome: ProcessOutcome) -> ActionResultReceipt:
        """A task that ran and left undeclared state in the login directory: `failed`.

        ONE form for the dispatch road and the review road. The failure is this
        build's refusal, not the process's, so an exit of zero is not carried: the
        runtime admits `failed` only with no code or a non-zero one, and a
        `failed` receipt carrying 0 was recorded as `unknown` -- MEASURED on the
        first real subscription login (23.09.2026). A non-zero exit is still
        carried, because then the process failed too. This sentence stays on the
        adapter's receipt; the runtime settles from the durable event, which holds
        no adapter prose, so the run itself records `failed` and nothing more.
        """
        return self._receipt(request, "failed", outcome.exit_code or None,
                             LOGIN_RESIDUE_DETAIL)

    def _receipt(
            self, request: ActionRequest, observed: str, exit_code: int | None,
            detail: str) -> ActionResultReceipt:
        """The one receipt funnel, so an undiscarded home cannot escape unsaid."""
        return ActionResultReceipt(
            receipt_id=self._ids("receipt"), action_id=request.action_id,
            run_id=request.run_id, attempt_id=request.attempt_id,
            instance_id=request.instance_id, outcome=observed,
            observed_at=self._clock(),
            detail=self._with_residue(detail),
            exit_code=exit_code)

    def _bare_receipt(
            self, request: ActionRequest, observed: str, exit_code: int | None,
            detail: str) -> ActionResultReceipt:
        """A receipt for a refusal built BEFORE this road minted anything.

        The cleanup sentences describe what an attempt left behind, and an
        action refused before it took the workspace turn has left nothing: the
        counts standing on the transport belong to whatever ran last, or to a
        sibling action running now. Saying them here would report another
        action's directory as this one's.

        The alternative -- clearing those counts first -- is what a previous
        version did, and it is worse than a wrong sentence: an adapter serves
        every action of its provider, so clearing before the turn erases a
        sibling's real refusal and its sampled credential values.
        """
        return ActionResultReceipt(
            receipt_id=self._ids("receipt"), action_id=request.action_id,
            run_id=request.run_id, attempt_id=request.attempt_id,
            instance_id=request.instance_id, outcome=observed,
            observed_at=self._clock(), detail=detail, exit_code=exit_code)

    def _with_residue(self, detail: str) -> str:
        """Whatever the receipt says, plus every cleanup fact about this attempt.

        Two facts, two sentences, and neither replaces the outcome: a home that
        could not be discarded and a login directory that gained state nothing
        declares are different failures of the same promise, and an attempt can
        have both.
        """
        if self._retained:
            detail += retained_detail(self.profile.tool_noun)
        if self._login_residue:
            detail += login_residue_detail(self.profile.tool_noun)
        return detail

    def _verification(
            self, request: ActionRequest, state: str, refs: tuple[str, ...],
            detail: str) -> AdapterVerification:
        return AdapterVerification(
            adapter_id=self.manifest.adapter_id, action_id=request.action_id,
            state=state, observed_at=self._clock(), detail=detail,
            evidence_refs=refs)
