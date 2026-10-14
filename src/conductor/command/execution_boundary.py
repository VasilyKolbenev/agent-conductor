"""Whether this build provides the execution boundary (R5) for a platform and an attempt mode.

A pure fact over two words. It opens no file, starts no process and calls no OS API, so the plan
doors, the preview and an adapter's spawn can all ask it without a side effect. The platform is
passed in (``sys.platform``), never read here, so a test chooses the platform it asks about.

The table says what the runner can DO, not what a host has. A platform gains a row only in the
commit that adds its launch to the runner; a launch that depends on a host fact (a sandbox tool
installed) adds the host check in that same commit, or the table would say yes on a host that
cannot.

"Provided" is the operating-system half of R5 only. A harness is confined when its adapter also
launches through the boundary and has its own witness (spec 10.6); that half is not decided here.
The trusted launch value itself lives in ``adapters/process_boundary.py``; this module stays free
of the ``adapters`` package so ``containment`` can import it without a cycle.
"""
from __future__ import annotations

#: The sandbox resource name a step uses to demand the boundary, as ``project-root`` is the name
#: of the route walk. It is a legal ``GraphResource`` name and a legal ``sandbox`` refusal detail.
BOUNDARY_ROUTE = "execution-boundary"

#: A task attempt that may write its work folder, and one that may only read it (a review, an
#: independent check). The same two words the owned ACL journal grants for.
ATTEMPT_MODES = ("dispatch", "review")

#: ``sys.platform`` values whose launch exists in the runner: Windows AppContainer.
_PROVIDED_PLATFORMS = frozenset({"win32"})


class BoundaryUnavailable(RuntimeError):
    """No execution boundary on this build for the platform and mode: refuse before any spawn.

    Carries the facts the R5 answer is built from (``service_refused`` with a ``sandbox`` detail)
    and nothing else: no path, no vendor name, no free text. It is deliberately not a runner,
    spec, profile or OS error, so a catch written for those cannot swallow it.

    Attributes:
        route: Always ``BOUNDARY_ROUTE``, the sandbox word the refusal names.
        platform: The platform that was asked about.
        mode: The attempt mode that was asked about.
    """

    def __init__(self, platform: str, mode: str) -> None:
        self.route = BOUNDARY_ROUTE
        self.platform = platform
        self.mode = mode
        super().__init__(f"no execution boundary on platform {platform!r} for a {mode} attempt")


def boundary_provided(platform: str, mode: str) -> bool:
    """Say whether the execution boundary is provided for a platform and an attempt mode.

    Args:
        platform: A ``sys.platform`` value. Only ``"win32"`` is provided; Linux and macOS are
            not until their launch lands.
        mode: One of ``ATTEMPT_MODES``.

    Returns:
        True when this build can confine a child of that mode on that platform.

    Raises:
        ValueError: ``mode`` is not one of ``ATTEMPT_MODES``, whatever the platform, so a wrong
            word is found on the developer's host and not only on another one.
    """
    if mode not in ATTEMPT_MODES:
        raise ValueError(f"unknown attempt mode {mode!r}; expected one of {ATTEMPT_MODES}")
    return platform in _PROVIDED_PLATFORMS


def require_boundary(platform: str, mode: str) -> None:
    """Return when the boundary is provided; otherwise refuse, before anything is created.

    Args:
        platform: A ``sys.platform`` value.
        mode: One of ``ATTEMPT_MODES``.

    Raises:
        BoundaryUnavailable: The boundary is not provided for this platform and mode.
        ValueError: ``mode`` is not one of ``ATTEMPT_MODES``.
    """
    if not boundary_provided(platform, mode):
        raise BoundaryUnavailable(platform, mode)
