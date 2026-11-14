"""A fixture for the tests of OTHER behaviour that authorize a step bound to a real transport.

Every dispatch and review step demands the execution boundary (R5), and the registry answers for a
real transport that is not confined that it has none, so a door refuses the step. The suites that
drive a harness fake as a plain child (``confine_platform=None``) and then authorize a plan over it
are about something else: a policy grant, a correction frame, a retention promise. They ask the
doors for the answer a transport on a platform with the boundary gives, and nothing else about the
transport changes: it is still not confined, so it still launches as a plain child and never
enters the boundary.

A transport that IS confined answers for itself, so the suites that confine one (a checker on a
platform without a boundary) keep their refusal. What the boundary does is witnessed in
``test_adapter_boundary_launch``, ``test_adapter_boundary_roads``,
``test_execution_boundary_refusal`` and ``test_production_door_boundary``, over a recording double
of the entry.

The other half is a test DOUBLE that starts no vendor agent (a scripted or a recording adapter): the
registry fails closed for an adapter that never answers the question, so such a double says so with
``StartsNoAgent``. Nothing is assumed for it; it declares what it is.

Import the fixture into the module and select it, which is what makes it opt-in::

    from tests._boundary_assumed import boundary_assumed  # noqa: F401
    pytestmark = pytest.mark.usefixtures("boundary_assumed")
"""
from __future__ import annotations

from functools import partial

import pytest

from conductor import server
from conductor.command.adapters.harness_attempt import AttemptLaunch
from conductor.command.providers import resolve_providers


class StartsNoAgent:
    """Mixin for a test double that starts no vendor agent: it answers the boundary question yes."""

    def boundary_provided(self, mode):
        return True


@pytest.fixture
def boundary_assumed(monkeypatch):
    """The doors are told a transport never confined provides the boundary; none is confined.

    The production server builds its harnesses through the provider door, which confines each one
    for the host; a suite that serves a harness fake through ``server.build`` gets the plain launch
    here instead, because the suite is not about the boundary.
    """
    real = AttemptLaunch.boundary_provided

    def assumed(self, mode):
        return real(self, mode) if self._confine else True

    monkeypatch.setattr(AttemptLaunch, "boundary_provided", assumed)
    plain = partial(resolve_providers, confine_platform=None)
    monkeypatch.setattr(server, "resolve_providers", plain)
