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

__all__ = [
    "Adapter",
    "AdapterContractError",
    "AdapterManifest",
    "AdapterObservation",
    "AdapterRegistry",
    "AdapterVerification",
    "PreparedAction",
    "UnsupportedCapability",
]
