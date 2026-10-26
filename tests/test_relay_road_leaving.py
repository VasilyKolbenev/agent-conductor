"""A refusal from inside the boundary is the refusal that is told, even when leaving it refuses too.

The boundary entry of the runner proves its owner again on the way out, so leaving can refuse after
the body returned. For a relay attempt the body returns a value when the command could not be built,
the claim could not be taken, or its marker stands (`NotStarted`: `spec`, `claim`,
`claim_standing`); a refusal to leave then used to replace it with `enter`, which says the boundary
refused the relay home. The attempt did not begin for the reason the body gave, and the receipt says
that one. Once the child may have run, a refusal to leave is still the unknown outcome.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from conductor.command.adapters import harness_attempt
from conductor.command.adapters.harness_workspace import HarnessWorkspace
from conductor.command.adapters.process import CommandSpecError
from conductor.command.adapters.process_profile import ProfileRefused
from conductor.command.failure_reasons import reason_words
from conductor.ownership_errors import OwnerRefused

from tests.relay_roads import CLAUDE, Site
from tests.test_relay_road_refusals import (
    WORDS, _raising, assert_refused_before_the_claim, sentence)


def _refuses_to_be_left(site: Site) -> None:
    """The boundary refuses to be left, the way the runner's own exit does (the loan's owner)."""
    site.runner.hooks["exit"] = _raising(ProfileRefused("profile_acl_unproven", "token alive"))


def test_a_claim_that_cannot_be_taken_is_told_so_even_when_the_boundary_then_refuses_to_be_left(
        tmp_path, monkeypatch):
    """The refusal of the claim happened first and is the one that is true: nothing was started."""
    site = Site(tmp_path, CLAUDE)
    monkeypatch.setattr(HarnessWorkspace, "claim", _raising(
        OwnerRefused("ownership_lost", "the project is no longer owned by this process")))
    _refuses_to_be_left(site)
    request = site.request()

    receipt = site.run(request)

    assert_refused_before_the_claim(site, request, receipt, "claim", entered=True)
    assert site.runner.events[-2:] == ["enter", "exit"]


def test_a_claim_whose_marker_stands_is_told_so_even_when_the_boundary_then_refuses_to_be_left(
        tmp_path, monkeypatch):
    site = Site(tmp_path, CLAUDE)
    real = Path.write_text

    def half_written(self, data, *arguments, **options):
        real(self, data, *arguments, **options)
        if self.suffix == ".marker":
            raise OSError(28, "no space left on the device")

    monkeypatch.setattr(Path, "write_text", half_written)
    _refuses_to_be_left(site)
    request = site.request()

    receipt = site.run(request)
    monkeypatch.undo()

    assert receipt.outcome == "failed" and receipt.detail == sentence(CLAUDE, "claim_standing")
    assert reason_words(receipt.detail) == WORDS["claim_standing"]
    assert site.tasks() == [] and site.leftovers() == [] and site.lease_is_free()
    assert site.claimed(request), "the receipt speaks of a marker that does stand"
    assert site.runner.events[-2:] == ["enter", "exit"]


def test_a_command_that_cannot_be_made_is_told_so_even_when_the_boundary_then_refuses_to_be_left(
        tmp_path, monkeypatch):
    site = Site(tmp_path, CLAUDE)
    monkeypatch.setattr(
        harness_attempt, "confined_spec", _raising(CommandSpecError("a runtime that is no path")))
    _refuses_to_be_left(site)
    request = site.request()

    receipt = site.run(request)

    assert_refused_before_the_claim(site, request, receipt, "spec", entered=True)
    assert site.runner.events[-2:] == ["enter", "exit"]


def test_a_boundary_that_refuses_to_be_left_after_a_run_is_still_an_unknown_outcome(tmp_path):
    """The control of the three above: once the child may have run, the error is unchanged."""
    site = Site(tmp_path, CLAUDE)
    _refuses_to_be_left(site)
    request = site.request()

    with pytest.raises(site.adapter.error, match="could not start the pinned build"):
        site.run(request)

    assert site.claimed(request) and len(site.tasks()) == 1 and site.lease_is_free()
