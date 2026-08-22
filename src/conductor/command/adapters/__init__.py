"""Capability-driven adapters for December Command.

Importing this package registers and probes nothing.  Adapter instances enter
an `AdapterRegistry` only through explicit project/runtime configuration.
"""

from .base import (
    Adapter,
    AdapterContractError,
    AdapterManifest,
    AdapterObservation,
    AdapterRegistry,
    AdapterVerification,
    PreparedAction,
    UnsupportedCapability,
)
from .claude_code import ClaudeCodeAdapter
from .codex_cli import CodexAdapter
from .provider import (
    ProviderCatalogEntry,
    ProviderConfig,
    ProviderConfigError,
    ProviderContract,
    ProviderRegistry,
    provider_projection,
)

__all__ = [
    "Adapter",
    "AdapterContractError",
    "AdapterManifest",
    "AdapterObservation",
    "AdapterRegistry",
    "AdapterVerification",
    "PreparedAction",
    "UnsupportedCapability",
    "ClaudeCodeAdapter",
    "CodexAdapter",
    "ProviderCatalogEntry",
    "ProviderConfig",
    "ProviderConfigError",
    "ProviderContract",
    "ProviderRegistry",
    "provider_projection",
]
