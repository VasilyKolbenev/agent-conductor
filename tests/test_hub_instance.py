"""The one live hub: `hub.lock` held for the life of the process, `hub.json` saying where it is.

Spec 4.1.7: the lock is held all the time the hub lives, so a second `conduct hub` finds it
held, prints the URL of the live hub (read from `hub.json`) and exits 0. The lock is the OS's:
it is freed when its holder dies, so a file left behind by a dead hub never blocks the next one.
`hub.json` is `{pid, process_started, port, url, started_at}` and is written by the hub that
holds the lock; it is removed by the hub that wrote it when it leaves.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from conductor import process_identity
from conductor.hub import instance
from conductor.ownership_native import NativeHold

NOW = "2026-09-30T10:00:00Z"


def test_a_hub_takes_the_lock_and_a_second_one_is_refused_with_the_first_ones_url(tmp_path):
    first = instance.HubInstance.acquire(tmp_path)
    try:
        first.publish(7700, now=NOW)
        with pytest.raises(instance.HubAlreadyRunning) as caught:
            instance.HubInstance.acquire(tmp_path)
        assert caught.value.url == "http://127.0.0.1:7700/"
        assert first.held
    finally:
        first.close()


def test_a_second_hub_that_finds_no_usable_hub_json_is_refused_with_no_url(tmp_path):
    first = instance.HubInstance.acquire(tmp_path)
    try:
        with pytest.raises(instance.HubAlreadyRunning) as caught:
            instance.HubInstance.acquire(tmp_path)
        assert caught.value.url is None
        (tmp_path / "hub.json").write_text("{not json", encoding="utf-8")
        with pytest.raises(instance.HubAlreadyRunning) as again:
            instance.HubInstance.acquire(tmp_path)
        assert again.value.url is None
    finally:
        first.close()


def test_the_lock_is_free_again_after_the_hub_closes_and_a_new_hub_replaces_hub_json(tmp_path):
    first = instance.HubInstance.acquire(tmp_path)
    first.publish(7700, now=NOW)
    first.close()
    assert not first.held and not (tmp_path / "hub.json").exists()
    second = instance.HubInstance.acquire(tmp_path)
    try:
        second.publish(7701, now=NOW)
        assert instance.read_hub_json(tmp_path).port == 7701
    finally:
        second.close()


def test_a_hub_json_left_by_a_hub_that_died_does_not_stop_the_next_hub(tmp_path):
    stale = {"pid": 1, "process_started": None, "port": 7700, "url": "http://127.0.0.1:7700/",
             "started_at": NOW}
    (tmp_path / "hub.json").write_text(json.dumps(stale), encoding="utf-8")
    hub = instance.HubInstance.acquire(tmp_path)
    try:
        hub.publish(7702, now=NOW)
        assert instance.read_hub_json(tmp_path).port == 7702
    finally:
        hub.close()


def test_hub_json_says_who_and_where_with_exactly_the_keys_of_the_spec(tmp_path):
    hub = instance.HubInstance.acquire(tmp_path)
    try:
        hub.publish(7700, now=NOW)
        record = json.loads((tmp_path / "hub.json").read_text(encoding="utf-8"))
    finally:
        hub.close()
    assert set(record) == {"pid", "process_started", "port", "url", "started_at"}
    assert record["pid"] == os.getpid() and record["port"] == 7700
    assert record["process_started"] == process_identity.started_of(os.getpid())
    assert record["url"] == "http://127.0.0.1:7700/" and record["started_at"] == NOW


def test_closing_removes_only_the_hub_json_this_hub_wrote(tmp_path):
    hub = instance.HubInstance.acquire(tmp_path)
    hub.publish(7700, now=NOW)
    foreign = {"pid": os.getpid() + 1, "process_started": None, "port": 7799,
               "url": "http://127.0.0.1:7799/", "started_at": NOW}
    (tmp_path / "hub.json").write_text(json.dumps(foreign), encoding="utf-8")
    hub.close()
    assert instance.read_hub_json(tmp_path).port == 7799


@pytest.mark.skipif(os.name == "nt", reason="Windows does not let a held file be renamed")
def test_a_lock_file_that_is_replaced_under_a_live_hub_is_found_out_by_check(tmp_path):
    hub = instance.HubInstance.acquire(tmp_path)
    try:
        hub.check()
        os.replace(tmp_path / "hub.lock", tmp_path / "hub.lock.moved")
        with pytest.raises(instance.HubLockLost):
            hub.check()
    finally:
        hub.close()


def test_check_after_close_says_the_lock_is_no_longer_held(tmp_path):
    hub = instance.HubInstance.acquire(tmp_path)
    hub.close()
    with pytest.raises(instance.HubLockLost):
        hub.check()
    hub.close()                # closing twice is not an error


@pytest.mark.parametrize("record", [
    {"pid": 1, "process_started": None, "port": 7700, "url": "http://127.0.0.1:7700/"},
    {"pid": 0, "process_started": None, "port": 7700, "url": "http://127.0.0.1:7700/",
     "started_at": NOW},
    {"pid": 1, "process_started": None, "port": 0, "url": "http://127.0.0.1:7700/",
     "started_at": NOW},
    {"pid": 1, "process_started": None, "port": 7700, "url": "http://localhost:7700/",
     "started_at": NOW},
    {"pid": 1, "process_started": None, "port": 7700, "url": "http://127.0.0.1:7700/",
     "started_at": "yesterday"},
    {"pid": 1, "process_started": None, "port": 7700, "url": "http://127.0.0.1:7700/",
     "started_at": NOW, "extra": 1}], ids=["missing key", "pid 0", "port 0", "another host",
                                           "not a time", "an unknown key"])
def test_a_hub_json_that_is_not_the_record_reads_as_none(tmp_path, record):
    (tmp_path / "hub.json").write_text(json.dumps(record), encoding="utf-8")
    assert instance.read_hub_json(tmp_path) is None


def test_the_lock_is_the_os_lock_another_holder_of_the_file_is_what_refuses(tmp_path):
    (tmp_path / "hub.lock").write_bytes(b"")
    outside = NativeHold(Path(tmp_path) / "hub.lock", exclusive=True)
    try:
        with pytest.raises(instance.HubAlreadyRunning):
            instance.HubInstance.acquire(tmp_path)
    finally:
        outside.close()
    instance.HubInstance.acquire(tmp_path).close()
