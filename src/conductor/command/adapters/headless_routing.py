"""How a routed model becomes tokens, for any vendor's one-shot CLI.

Split out of ``headless_cli`` when that module crossed the 800-line cap again,
and the seam is the same kind the two earlier splits found rather than a place
to put spare lines. ``harness_profile`` holds what a provider DECLARES;
``headless_values`` holds the values a spawn is described with; this holds the
one circuit that turns a DEPLOYMENT's choice into a command line. It grows with
the roster -- GLM is the next product to declare a flag -- while the transport
next door does not.

Nothing here knows a model id, a vendor, or a default. A profile declares the
FLAG its vendor names a model with and the NAMES that vendor publishes as
moving; the run's frozen configuration pins the VALUE; this joins them, and the
concrete provider decides only WHERE the pair stands in its own argv, because
that is a fact about a vendor's command line.

Both of this module's refusals are the PROFILE's policy read out loud, never
this module's own: a vendor with no reviewed flag, and a name that vendor says
is an alias for whatever it ships this week.

What a mixin needs from the class it is mixed into is stated rather than
assumed: ``profile``, ``_receipt`` and ``_retained``, all of them
``HeadlessCliTransport``'s. It is a mixin rather than two free functions
because the refusal has to build a receipt, and a receipt is the transport's own
funnel -- the one place an undiscarded home cannot escape unsaid.
"""
from __future__ import annotations

from ..contracts import ActionRequest, ActionResultReceipt
from .harness_profile import moving_model_detail, unroutable_model_detail


class ModelRouting:
    """The routed model's two seams: the refusal, and the tokens."""

    def _unroutable(
            self, request: ActionRequest,
            model: str | None) -> ActionResultReceipt | None:
        """Refuse before anything runs when a routed model cannot be delivered.

        The one gate, and it stands in front of BOTH roads rather than inside
        the argv builder that would have needed it. An action whose
        configuration pins a model for a provider this build knows no flag for
        cannot be run honestly: the child would take its model from the vendor's
        own configuration, and the receipt would describe work an operator's
        file did not ask for.

        A refusal rather than a silent drop, and the difference is the whole
        reason this method exists: a run that used a different model than an
        operator configured is worse than a run that did not happen, because
        nothing afterwards can tell which model it was.

        The second reason is the vendor's own naming. A model an operator pins
        must name ONE build; a name the vendor publishes as an alias for
        "the latest model" names a different one every release, so a journal
        recording it means something different each time it is read and no
        receipt built from that run can be checked against the model that did
        the work. Which names move is the PROFILE's declaration, never this
        method's: nothing here knows a model id, and a build that carried its
        own list would be maintaining a catalogue of somebody else's products.

        Nothing is minted, claimed or spawned for either refusal, which is why
        both are checked here and not after the workspace turn is taken.
        """
        if model is None:
            return None
        if not self.profile.model_flag:
            self._retained = 0
            return self._receipt(
                request, "failed", None,
                unroutable_model_detail(self.profile.tool_noun))
        if model in self.profile.unstable_models:
            self._retained = 0
            return self._receipt(
                request, "failed", None,
                moving_model_detail(self.profile.tool_noun))
        return None

    def _model_argv(self, model: str | None) -> tuple[str, ...]:
        """The vendor's own way of naming a routed model, or nothing at all.

        Provider-neutral, and that is the point of it being here: this method
        knows no model id, no vendor and no default. It joins the flag the
        profile declares to the value the run's frozen configuration pinned, and
        a provider decides only WHERE the pair stands in its own command line.
        The next products to route -- GLM among them -- add a profile field and
        a position, and no code in this module changes.

        There is no branch on an empty ``model_flag`` here, because there is no
        road to one: ``_unroutable`` refuses an action whose configuration
        routes a model to a provider that declares no flag, and it refuses
        before anything is minted, claimed or spawned. A guard here would be a
        claim nothing could hold.

        ``None`` is not a default model. It is a configuration that pinned none,
        and the honest rendering of that is an empty tuple -- what runs then is
        whatever the provider's own configuration decides, which is a different
        fact from this build having chosen it.
        """
        return () if model is None else (self.profile.model_flag, model)
