"""The closed fact `task_road` of a provider row: where a task of that harness would run (I3).

The Agents screen and the Desk wizard used to say one thing about every subscription login (that it
only reads quotas). Since I2b a subscription task of Claude Code and Codex runs inside the
execution boundary on a relay home, and Grok Build and Kimi Code still do not, so the screen has to
be told which, and by a fact and not by a vendor's name: the registry's own answer for a dispatch
(`AdapterRegistry.execution_boundary(provider_id, "dispatch")`), in two words, `boundary` or
`refused`. It is on every row of the provider projection, because the window judges a row by one
closed key set (`PROVIDER_KEYS`); it fails closed where no registry was asked, as the registry does.

What this file holds: the projection's own rule, the answer of the production door for the roads
that matter (a relay road in the folder the relay is derived from, in another, a harness with no
relay, an API key, a platform without the boundary, an unavailable provider), and that all three
routes that carry the array send the registry's answer.
"""
from __future__ import annotations

import pytest

from conductor.command import providers as provider_factory
from conductor.command.adapters import provider as provider_module
from conductor.command.adapters.provider import provider_projection
from conductor.command.providers import resolve_providers

from tests import test_command_grok_transport as grok_t
from tests import test_controls_provider_block as block
from tests._fakeboundary import recording_runners
from tests.test_command_http_api import get_headers
from tests.test_command_provider_contract import _contract
from tests.test_controls_provider_block import AVAILABLE_ID
from tests.test_production_door_boundary import _five_pins, _subscription_pins


def test_the_three_words_of_the_fact_are_closed():
    assert provider_module.TASK_ROADS == ("boundary", "refused", "review_only")


def test_every_row_carries_the_fact_and_it_fails_closed_where_no_registry_was_asked():
    rows = provider_projection([_contract()])

    assert [row.get("task_road") for row in rows] == ["refused"]


@pytest.mark.parametrize("answer,word", [
    (True, "boundary"), (False, "refused"), (None, "refused"), (1, "refused"), ("yes", "refused")])
def test_only_a_plain_yes_of_the_registry_is_a_boundary(answer, word):
    asked = []

    def boundary(provider_id, mode):
        asked.append((provider_id, mode))
        return answer

    (row,) = provider_projection([_contract()], boundary=boundary)

    assert row["task_road"] == word
    modes = ["dispatch", "review"] if answer is False else ["dispatch"]
    assert asked == [(row["provider_id"], mode) for mode in modes]


def test_a_registry_that_cannot_answer_for_a_provider_refuses_it():
    def boundary(provider_id, mode):
        raise LookupError("no adapter is registered under this id")

    (row,) = provider_projection([_contract()], boundary=boundary)

    assert row["task_road"] == "refused"


def _roads(tmp_path, monkeypatch, pins, platform="win32"):
    monkeypatch.setattr(provider_factory, "host_platform", lambda: platform)
    recording_runners(monkeypatch, tmp_path / "scratch")
    resolution = resolve_providers(
        pins, root=tmp_path, clock=lambda: grok_t.NOW, ids=grok_t._Ids())
    rows = provider_projection(
        resolution.contracts, boundary=resolution.registry.execution_boundary)
    return {row["provider_id"]: row["task_road"] for row in rows}


def test_the_production_door_says_boundary_for_the_roads_that_run_a_task_inside_it(
        tmp_path, monkeypatch):
    roads = _roads(tmp_path, monkeypatch, _subscription_pins(tmp_path))

    assert roads == {"claude-code": "boundary", "codex": "boundary", "deepseek-harness": "boundary",
                     "grok-build": "refused", "kimi-code": "refused"}


def test_an_api_key_road_is_a_boundary_for_all_five_on_windows(tmp_path, monkeypatch):
    roads = _roads(tmp_path, monkeypatch, _five_pins(tmp_path))

    assert set(roads.values()) == {"boundary"} and len(roads) == 5


@pytest.mark.parametrize("kept", [("logins",), ("DecemberCommand",)], ids=["no-product-folder",
                                                                          "no-logins-folder"])
def test_a_relay_road_whose_login_is_kept_elsewhere_is_refused_and_says_so_on_the_row(
        kept, tmp_path, monkeypatch):
    roads = _roads(tmp_path, monkeypatch, _subscription_pins(tmp_path, kept=kept))

    assert roads["claude-code"] == roads["codex"] == "refused"
    assert roads["deepseek-harness"] == "boundary", "an API key does not depend on the login folder"


@pytest.mark.parametrize("platform", ["linux", "darwin"])
def test_a_platform_without_the_boundary_refuses_every_road(platform, tmp_path, monkeypatch):
    roads = _roads(tmp_path, monkeypatch, _five_pins(tmp_path), platform=platform)

    assert set(roads.values()) == {"refused"}


def test_a_provider_no_row_configured_has_no_road(tmp_path, monkeypatch):
    pins = [pin for pin in _five_pins(tmp_path) if pin.provider_id != "codex"]

    roads = _roads(tmp_path, monkeypatch, pins)

    assert roads["codex"] == "refused" and roads["claude-code"] == "boundary"


class BoundedRoster(block.RosterAdapter):
    """The roster fixture's one available adapter, saying it launches inside the boundary."""

    def boundary_provided(self, mode):
        return True


def _rows(tmp_path, path, *, bounded):
    classes = {AVAILABLE_ID: BoundedRoster} if bounded else None
    resolution = block.resolve(tmp_path, adapter_classes=classes)
    api = block.an_api(tmp_path, resolution)
    response = api.handle("GET", path, get_headers())
    assert response.status == 200, response.payload
    return {row["provider_id"]: row.get("task_road") for row in response.payload["providers"]}


@pytest.mark.parametrize("path", ["/command/workflows", "/command/runs",
                                  f"/command/runs/{block.RUN_ID}/controls"])
def test_every_route_that_carries_the_array_sends_the_answer_of_the_registry(path, tmp_path):
    """The three are separate call sites; one of them passing is not the class."""
    bounded = _rows(tmp_path, path, bounded=True)

    assert bounded == {AVAILABLE_ID: "boundary", "here-and-fake": "refused",
                       "wrong-protocol": "refused", "never-pinned": "refused"}


@pytest.mark.parametrize("path", ["/command/workflows", "/command/runs",
                                  f"/command/runs/{block.RUN_ID}/controls"])
def test_an_adapter_that_does_not_say_it_is_confined_is_refused_on_every_route(path, tmp_path):
    assert set(_rows(tmp_path, path, bounded=False).values()) == {"refused"}


def test_the_fact_does_not_change_the_contract_a_grant_is_bound_by():
    """The contract of a provider (`as_dict`) is what an automation grant's digest covers; the
    road is a fact of the projection and rides nowhere else."""
    contract = _contract()

    assert "task_road" not in contract.as_dict()
