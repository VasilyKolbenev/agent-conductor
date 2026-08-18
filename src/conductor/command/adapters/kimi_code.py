"""Kimi Code: catalogued so it can be seen, and given no control to spend.

The vendor contract below was read from Moonshot AI's own published sources on
2026-08-18 and is recorded here so a later reader can re-check it rather than
trust this prose:

- the product is Kimi Code CLI, binary name ``kimi``, distributed as a single
  native binary by an install script -- ``code.kimi.com/kimi-code/install.sh``,
  or ``install.ps1`` on Windows -- and its README says the binary needs "no
  Node.js setup", so it is its own executable and pins no interpreter entrypoint
  (README, github.com/MoonshotAI/kimi-code);
- the predecessor repository ``MoonshotAI/kimi-cli`` is the Python build and
  says of itself that it "will be gradually wound down"
  (github.com/MoonshotAI/kimi-cli), so the Python CLI is not what this build
  would pin;
- a non-interactive transport IS documented: ``-p``/``--prompt <prompt>`` runs
  "a single prompt non-interactively and stream[s] the Assistant output to
  stdout", ``--output-format`` accepts ``text`` and ``stream-json``, and
  ``-V``/``--version`` prints the version and exits
  (moonshotai.github.io/kimi-code/en/reference/kimi-command.html);
- configuration and session state live in ``~/.kimi-code`` and relocate with
  ``KIMI_CODE_HOME``; credentials, however, are read ONLY from ``config.toml``,
  where that same page states the CLI "does not fall back to shell environment
  variables automatically", and telemetry is on by default and is turned off
  ONLY by writing ``telemetry = false`` into that file -- no environment
  variable is offered for it
  (moonshotai.github.io/kimi-code/en/configuration/config-files.html);
- the latest published release is 0.36.1, dated 2026-08-14
  (moonshotai.github.io/kimi-code/en/release-notes/changelog.html);
- the npm package third-party write-ups name, ``@kimi-code/cli``, does not
  exist: ``registry.npmjs.org/@kimi-code/cli`` answers 404. Only the install
  script is a distribution this build could honestly pin.

So the one-shot transport is real -- and this build still dispatches nothing
through it, for three reasons that are facts about that contract rather than
preferences:

1. **A credential cannot come from the environment.** A provider config in this
   build stores environment NAMES only and never a secret value; the value is
   read from the live environment at spawn time and is never written down. Kimi
   Code reads its key from ``config.toml`` and documents that it does not fall
   back to the environment, so dispatching would mean this build writing an
   operator's key to disk -- the one thing the config door exists to prevent.
2. **Telemetry cannot be disabled without authoring an unverified file.** There
   is no environment switch, so a fresh isolated ``KIMI_CODE_HOME`` boots with
   telemetry ON unless this build writes a ``config.toml`` whose exact schema it
   has not read. Guessing that schema is a fabrication, and shipping a spawn
   that quietly phones home is worse than shipping no spawn.
3. **The non-interactive exit codes are undocumented.** The reference publishes
   exit-code meanings for ``kimi login`` alone. "The process was observed to
   exit zero" needs a published meaning before a receipt may carry it.

Therefore Kimi Code is catalogued so the Cockpit can SEE it, named Experimental
where a reader will see that too, resolved unavailable whatever the operator
pinned, and given NO control at all -- an honest unavailable beats a fabricated
integration, and the registration door already refuses an undeclared control.
The class below exists only to satisfy that door's lifecycle proof, and every
one of its seams refuses, its constructor first, so no instance of it can exist
to spawn anything. When an environment-carried credential path and published
exit-code semantics land, this module is where the real transport goes.
"""
from __future__ import annotations

from .base import AdapterContractError
from .deep_contracts import DeepProtocol

#: The graph node this provider binds to. ``conductor.harnesses`` registers the
#: id ``kimi-code``, so a role that names it draws a real badge rather than the
#: neutral fallback an unregistered string gets.
KIMI_PROVIDER_ID = "kimi-code"
#: The protocol token this build catalogues. It names an UNPROVEN transport on
#: purpose: no adapter here implements it, and the factory refuses to resolve a
#: provider available when it declares nothing to dispatch.
KIMI_PROTOCOL = DeepProtocol.KIMI_UNPROVEN_V0.value
#: Experimental is said in the one field the Cockpit projection actually carries.
KIMI_DISPLAY_NAME = "Kimi Code (experimental, no proven transport)"
#: Observation only. Not one control is declared, because not one is proven.
KIMI_CAPABILITIES = ("observe",)
#: No control, so no argument schema binds -- and the door proves that emptiness
#: against this module's own ``argument_schemas`` rather than trusting it.
KIMI_SCHEMA_PAIRS: tuple[tuple[str, str], ...] = ()
#: The four seams the registration door requires of every provider.
KIMI_LIFECYCLE = ("execute", "observe", "prepare", "verify")
#: The one sentence every refusal carries. It reports the state of THIS build's
#: proof, never a claim about the vendor's product.
KIMI_REFUSAL = (
    "this build has proven no non-interactive transport it may drive Kimi Code "
    "through, so it declares no control and dispatches nothing")

__all__ = [
    "KIMI_CAPABILITIES", "KIMI_DISPLAY_NAME", "KIMI_LIFECYCLE", "KIMI_PROTOCOL",
    "KIMI_PROVIDER_ID", "KIMI_REFUSAL", "KIMI_SCHEMA_PAIRS",
    "KimiCodeContractAdapter", "KimiTransportUnproven",
]


class KimiTransportUnproven(AdapterContractError):
    """Kimi Code is catalogued and described, but this build drives nothing."""


class KimiCodeContractAdapter:
    """A declared absence: no instance can be built, and every seam refuses.

    The registration door proves a provider's declared controls against this
    class's own ``argument_schemas`` and its declared lifecycle against callables
    it really carries. Both proofs are satisfied HONESTLY here: the schema
    mapping is empty because no control is declared, and the four seams exist and
    refuse. The constructor refuses first, so the refusal does not depend on any
    caller reaching a seam -- and it is a second, independent door beside the
    factory's, which never builds an adapter for an unavailable provider at all.
    """

    #: Empty, and the door compares it as a WHOLE against the declared relation:
    #: a control smuggled into the catalog entry would fail against this mapping.
    argument_schemas: dict[str, str] = {}

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise KimiTransportUnproven(KIMI_REFUSAL)

    def observe(self, instance_id: str, run_id: str) -> object:
        raise KimiTransportUnproven(KIMI_REFUSAL)

    def prepare(self, request: object) -> object:
        raise KimiTransportUnproven(KIMI_REFUSAL)

    def execute(self, prepared: object) -> object:
        raise KimiTransportUnproven(KIMI_REFUSAL)

    def verify(self, request: object, result: object) -> object:
        raise KimiTransportUnproven(KIMI_REFUSAL)
