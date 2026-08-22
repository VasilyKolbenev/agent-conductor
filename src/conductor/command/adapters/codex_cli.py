"""Codex CLI's own module: one provider id, declared in one place.

PENDING: the real Codex CLI transport is NOT implemented here. This adapter
speaks only the deterministic fake JSON-line protocol review approved. It
discovers no executable, reads no home directory, and invents no vendor CLI
flag, stdin protocol, session recovery or evidence semantics for the real tool.

Everything this class DOES is the shared fake-protocol lifecycle in
``deep_adapters``, which knows no provider by name. What lives here is the
identity: the catalogued id, what a Cockpit displays for it, whose product it
is, which protocol token selects it, and which codec reads its frames.

Why this is a module of its own while it is still a fixture is written out in
``claude_code.py`` and holds identically here: the AST identity gate grants
comparison rights per MODULE, so two providers in one module is one module
holding rights over two ids.
"""
from __future__ import annotations

from .deep_adapters import _DeepAdapter
from .deep_codecs import FakeCodexCodec
from .deep_contracts import DeepProtocol

#: The graph node this provider binds to; ``conductor.harnesses`` registers it.
CODEX_PROVIDER_ID = "codex"

__all__ = ["CODEX_PROVIDER_ID", "CodexAdapter"]


class CodexAdapter(_DeepAdapter):
    """Configured adapter for the reviewed fake Codex JSON-line protocol."""

    ADAPTER_ID = CODEX_PROVIDER_ID
    DISPLAY_NAME = "Codex (fake protocol)"
    VENDOR = "OpenAI-compatible test fixture"
    PROTOCOL = DeepProtocol.FAKE_CODEX_V1
    CODEC = FakeCodexCodec


#: This module's own statement of which concrete type is reviewed for this id.
#: See ``claude_code.py`` for why it is read from a class's own ``__dict__``.
CodexAdapter.REVIEWED_TYPE = CodexAdapter
