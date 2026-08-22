"""Claude Code's own module: one provider id, declared in one place.

PENDING: the real Claude Code transport is NOT implemented here. This adapter
speaks only the deterministic fake JSON-line protocol review approved. It
discovers no executable, reads no home directory, and invents no vendor CLI
flag, stdin protocol, session recovery or evidence semantics for the real tool.

Everything this class DOES is the shared fake-protocol lifecycle in
``deep_adapters``, which knows no provider by name. What lives here is the
identity: the catalogued id, what a Cockpit displays for it, whose product it
is, which protocol token selects it, and which codec reads its frames.

**Why this is a module of its own, while it is still a fixture.** The AST
identity gate grants comparison rights over a provider id to exactly one
module -- the one its ``adapter_class`` is defined in. While ``claude-code``
and ``codex`` shared ``deep_adapters``, that one module held rights over BOTH,
so a branch on one written inside the other's transport would have walked
through a gate whose whole purpose is to refuse it. The gate could not have
noticed: such a comparison really does stand in an allowed module, just an
allowed one for the wrong provider. Splitting after a transport is real would
mean the loophole was open across the slice that needed it least to be.
``tests/test_provider_identity_gate.py`` holds the map injective from now on.
"""
from __future__ import annotations

from .deep_adapters import _DeepAdapter
from .deep_codecs import FakeClaudeCodec
from .deep_contracts import DeepProtocol

#: The graph node this provider binds to; ``conductor.harnesses`` registers it.
CLAUDE_PROVIDER_ID = "claude-code"

__all__ = ["CLAUDE_PROVIDER_ID", "ClaudeCodeAdapter"]


class ClaudeCodeAdapter(_DeepAdapter):
    """Configured adapter for the reviewed fake Claude JSON-line protocol."""

    ADAPTER_ID = CLAUDE_PROVIDER_ID
    DISPLAY_NAME = "Claude Code (fake protocol)"
    VENDOR = "Anthropic-compatible test fixture"
    PROTOCOL = DeepProtocol.FAKE_CLAUDE_V1
    CODEC = FakeClaudeCodec


#: This module's own statement of which concrete type is reviewed for this id,
#: and the whole of what ``_DeepAdapter._reviewed`` consults. It is read from a
#: class's OWN ``__dict__``, never inherited, so a subclass of the class below
#: does not quietly become a second reviewed type for ``claude-code``.
#:
#: It stands out here rather than in the shared base because a base that listed
#: its concrete classes would be a provider-neutral module naming two providers
#: -- and would have to import them, which is the cycle the split removes.
ClaudeCodeAdapter.REVIEWED_TYPE = ClaudeCodeAdapter
