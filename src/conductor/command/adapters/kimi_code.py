"""Kimi Code: catalogued so it can be seen, and given no control to spend.

Re-audited 2026-08-18 against Moonshot AI's own published pages, and the audit
OVERTURNED two of the three grounds this module used to carry. They are named
here rather than quietly deleted, because a reader who met the old reasoning is
owed the correction:

- **A credential CAN come from the shell.** The environment reference says
  credential variables such as ``KIMI_API_KEY``, ``ANTHROPIC_API_KEY`` and
  ``OPENAI_API_KEY`` are "not read automatically from shell environment
  variables" -- and then names the exception: the ``KIMI_MODEL_*`` family "is an
  explicit channel that does read credentials from the shell", with
  ``KIMI_MODEL_API_KEY`` required once ``KIMI_MODEL_NAME`` is set. This module
  had generalised the first sentence over the second and concluded that
  dispatching would force this build to write an operator's key to disk. It
  would not: that channel is the exact shape this build's provider door already
  uses -- environment NAMES pinned in config, values read at spawn and never
  written down (moonshotai.github.io/kimi-code/en/configuration/env-vars.html).
- **Telemetry HAS an environment switch.** ``KIMI_DISABLE_TELEMETRY`` set to
  ``1`` turns off anonymous telemetry reporting (same page). This module had
  claimed the only route was authoring a ``config.toml`` whose schema it had not
  read, and called a fresh isolated home telemetry-ON for that reason.

What the audit left standing:

- the one-shot transport is documented: ``-p``/``--prompt <prompt>`` runs a
  single prompt non-interactively and streams to stdout, ``--output-format``
  takes ``text`` or ``stream-json`` and only alongside ``--prompt``, and
  ``-V``/``--version`` prints the version and exits;
- exit-code meanings are published for ``kimi login`` and ``kimi doctor`` only
  (``0`` on success, ``1`` on failure); the reference states none for a
  ``--prompt`` run (moonshotai.github.io/kimi-code/en/reference/kimi-command.html);
- configuration and session state live in ``~/.kimi-code`` and relocate with
  ``KIMI_CODE_HOME``;
- the binary installs by script and needs no Node.js, so it pins no interpreter
  entrypoint, and the npm name third-party write-ups repeat, ``@kimi-code/cli``,
  answers 404 on the registry.

So the honest state was never "the vendor makes this impossible". It is that
THIS BUILD has neither implemented nor proven that transport -- which is what
the catalogue entry's ``unproven`` implementation says, and what every refusal
below reports. Everything named in this module is a fact about this build's
proof; nothing is a claim about the product.

Driving it is a slice of its own, behind the doors DeepSeek already passes: an
operator-pinned absolute executable with no PATH discovery, an isolated
per-attempt ``KIMI_CODE_HOME``, ``KIMI_DISABLE_TELEMETRY=1``, an exact version
preflight, code-owned headless argv, bounded and drained output that reaches no
journal, API, SSE or evidence, and a deterministic fake executable with any real
smoke kept opt-in. The undocumented ``--prompt`` exit codes no longer block that
work -- they bound what it may CLAIM: under this build's law an exit code buys
``execution_observed`` and never success, so a Kimi dispatch could reach exactly
as far as DeepSeek reaches today, and no further.

Until that lands Kimi Code is catalogued so the Cockpit can SEE it, named
experimental where a reader will see that too, resolved unavailable whatever the
operator pinned, and given NO control at all -- the registration door already
refuses an undeclared control. The class below exists only to satisfy that
door's lifecycle proof, and every one of its seams refuses, its constructor
first, so no instance of it can exist to spawn anything.
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
#: Experimental is said in the one field the Cockpit projection actually carries,
#: and it says whose proof is missing: this build drives it, or nothing does.
KIMI_DISPLAY_NAME = "Kimi Code (experimental, not driven by this build)"
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
