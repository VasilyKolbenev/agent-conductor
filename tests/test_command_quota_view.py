"""The reader of `GET /command/quotas` is a keyword of `CommandApi` (spec 4.3.1, 4.5.1).

A process opened for viewing never polls a quota source: it shows the last snapshot of the active
project's limits, read from a file the hub keeps. The reader that does so is another lane's object
with the one method the default reader has, `payload(contracts, now)`; the API only has to hold
whichever it was given. Until this keyword existed that lane assigned a private attribute after
construction.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from conductor.command.adapters import AdapterRegistry
from conductor.command.http_api import PRODUCT_COMMAND_BUDGET, CommandApi
from conductor.command.http_transport import CommandSession
from conductor.command.run_store import RunStore
from tests.test_command_adapters import FakeAdapter
from tests.test_command_http_api import NOW, PORT, TOKEN, get_headers, ids

ANSWER = {"as_of": NOW, "max_age_seconds": 300.0, "providers": [], "snapshots": [],
          "hub_snapshot": {"project_id": "a" * 32, "taken_at": NOW}}


class Reader:
    """What a view process holds: one method, and a record of how it was asked."""

    def __init__(self):
        self.asked = []

    def payload(self, contracts, now):
        self.asked.append((tuple(contracts), now))
        return dict(ANSWER)


def make(tmp_path, **extra):
    return CommandApi(RunStore(tmp_path), AdapterRegistry([FakeAdapter()]),
                      session=CommandSession(PORT, TOKEN), budget=PRODUCT_COMMAND_BUDGET,
                      clock=lambda: NOW, ids=ids(), publish_run=lambda run_id: None, **extra)


def quotas(api):
    return api.handle("GET", "/command/quotas", get_headers())


def test_a_reader_handed_in_answers_the_quotas_route_and_is_asked_once(tmp_path):
    reader = Reader()
    answer = quotas(make(tmp_path, quota_view=reader))
    assert answer.status == 200 and dict(answer.payload) == ANSWER
    assert reader.asked == [((), NOW)]


def test_the_default_reader_is_unchanged_when_no_keyword_is_given(tmp_path):
    answer = quotas(make(tmp_path))
    assert answer.status == 200
    assert set(answer.payload) == {"as_of", "max_age_seconds", "providers", "snapshots"}
    assert answer.payload["max_age_seconds"] == 300.0 and answer.payload["snapshots"] == []


def test_the_service_and_the_max_age_only_build_the_default_reader(tmp_path):
    shortened = quotas(make(tmp_path, quota_max_age=timedelta(seconds=7)))
    assert shortened.payload["max_age_seconds"] == 7.0
    reader = Reader()
    handed = quotas(make(tmp_path, quota_view=reader, quota_max_age=timedelta(seconds=7)))
    assert dict(handed.payload) == ANSWER


@pytest.mark.parametrize("reader", [object(), "payload", 3, type("Bare", (), {"payload": 1})()])
def test_an_object_without_a_payload_method_is_refused_before_the_api_exists(tmp_path, reader):
    with pytest.raises(TypeError, match="quota_view must have a payload method"):
        make(tmp_path, quota_view=reader)
