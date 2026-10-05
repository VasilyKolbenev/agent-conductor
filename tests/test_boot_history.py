"""The ownership history validator judges the boot transition itself, not only the command."""
from __future__ import annotations

import re

import pytest

from conductor.ownership_records import (HOME, RECORDS, OwnerRefused, canonical, chain, digest,
                                         exclusive, fence_bytes, publish)
from tests._boot_world import GUID, OTHER_GUID, counter

LEGACY_A = f"windows:{GUID}"
LEGACY_B = f"windows:{OTHER_GUID}"
LINUX_A = "linux:5b1d9c0e-3b7a-4a76-9d0f-0d1f6c2e8a11"
LINUX_B = "linux:6c2e0d1f-4c8b-4b87-8e1a-1e207d3f9b22"
SESSION = "a" * 32
OTHER_SESSION = "b" * 32
NONCE = "c" * 32

# What a reader of the schema-1 world knows: frozen here so that "an old reader refuses" is a fact
# of this file, not of whatever the validator becomes.
OLD_FIELDS = frozenset({"schema", "generation", "previous_digest", "phase", "nonce",
    "root_identity", "data_identity", "fence_identity", "fence_digest", "data_digest",
    "session_id", "boot_id", "recovered_session"})
OLD_OPENED_SUCCESSORS = {"closed", "recovered"}
OLD_BOOT = re.compile(r"(?:windows|linux|darwin):[0-9a-f-]{36}")


def start(tmp_path, boot):
    """A chain up to an opened owner session whose recorded boot is `boot`."""
    (tmp_path / HOME / RECORDS).mkdir(parents=True)
    head = publish(tmp_path, None, phase="prepared", nonce=NONCE, root_identity=[1, 2],
        data_identity=[3, 4], fence_identity=None, fence_digest=digest(fence_bytes(NONCE)),
        data_digest=digest(b""), session_id=None, boot_id=None, recovered_session=None)
    head = publish(tmp_path, head, phase="moved")
    head = publish(tmp_path, head, phase="active", fence_identity=[5, 6])
    return opened(tmp_path, head, boot, SESSION)


def opened(root, head, boot, session):
    return publish(root, head, phase="opened", session_id=session, boot_id=boot,
                   recovered_session=None)


def forge(root, previous, **changes):
    """Write a generation the way a hostile or buggy writer would: with no judgment."""
    value = dict(previous)
    value.update(changes)
    value.update(generation=previous["generation"] + 1, previous_digest=digest(canonical(previous)))
    exclusive(root / HOME / RECORDS / f"gen-{value['generation']:08d}.json", canonical(value))
    return value


def refused(root):
    with pytest.raises(OwnerRefused) as caught:
        chain(root)
    assert caught.value.code == "transition_conflict"
    return str(caught.value)


def prepare(root, head, measured):
    return publish(root, head, phase="recovery_prepared", prepared_boot=measured)


def recover(root, head, boot):
    return publish(root, head, phase="recovered", boot_id=boot,
                   recovered_session=head["session_id"])


def test_a_schema_one_history_with_a_legacy_recovered_still_reads_as_history(tmp_path):
    head = start(tmp_path, LEGACY_A)
    head = recover(tmp_path, head, LEGACY_B)
    assert head["schema"] == 1 and chain(tmp_path) == head


def test_a_schema_two_recovered_straight_after_a_legacy_opened_is_refused_by_the_history(
        tmp_path):
    head = start(tmp_path, LEGACY_A)
    with pytest.raises(OwnerRefused, match="legacy"):
        recover(tmp_path, head, counter(43))
    forge(tmp_path, head, schema=2, phase="recovered", boot_id=counter(43), prepared_boot=None,
          recovered_session=SESSION)
    assert "legacy" in refused(tmp_path)


def test_after_a_preparation_a_strictly_later_counter_completes_the_recovery(tmp_path):
    head = start(tmp_path, LEGACY_A)
    prepared = prepare(tmp_path, head, counter(42))
    assert prepared["schema"] == 2 and prepared["prepared_boot"] == counter(42)
    assert prepared["boot_id"] == LEGACY_A and prepared["session_id"] == SESSION
    assert prepared["previous_digest"] == digest(canonical(head))
    done = recover(tmp_path, prepared, counter(43))
    assert done["prepared_boot"] == counter(42) and chain(tmp_path) == done
    again = opened(tmp_path, done, counter(43), OTHER_SESSION)
    assert again["prepared_boot"] is None and chain(tmp_path) == again


@pytest.mark.parametrize("measured, why", [
    (counter(42), "same"), (counter(41), "lower"), (counter(900, OTHER_GUID), "scope"),
    (LINUX_B, "scheme"), (LEGACY_B, "legacy")])
def test_after_a_preparation_only_a_comparable_later_measurement_completes_it(
        tmp_path, measured, why):
    prepared = prepare(tmp_path, start(tmp_path, LEGACY_A), counter(42))
    with pytest.raises(OwnerRefused):
        recover(tmp_path, prepared, measured)
    forge(tmp_path, prepared, schema=2, phase="recovered", boot_id=measured,
          prepared_boot=counter(42), recovered_session=SESSION)
    assert "recovery" in refused(tmp_path), why


def test_a_recovered_after_a_preparation_must_carry_the_preparation_unchanged(tmp_path):
    prepared = prepare(tmp_path, start(tmp_path, LEGACY_A), counter(42))
    forge(tmp_path, prepared, schema=2, phase="recovered", boot_id=counter(43),
          prepared_boot=counter(40), recovered_session=SESSION)
    assert "preparation" in refused(tmp_path)


def test_a_preparation_follows_only_a_legacy_opened(tmp_path):
    for boot in (counter(42), LINUX_A):
        root = tmp_path / boot[:5]
        root.mkdir()
        head = start(root, boot)
        with pytest.raises(OwnerRefused, match="legacy"):
            prepare(root, head, counter(50))
        forge(root, head, schema=2, phase="recovery_prepared", prepared_boot=counter(50))
        assert "legacy" in refused(root)


@pytest.mark.parametrize("changes, word", [
    ({"session_id": OTHER_SESSION}, "session"), ({"boot_id": LEGACY_B}, "boot"),
    ({"prepared_boot": LEGACY_B}, "counter"), ({"prepared_boot": LINUX_B}, "counter"),
    ({"prepared_boot": None}, "counter"), ({"recovered_session": SESSION}, "session"),
    ({"schema": 1}, "schema")])
def test_a_preparation_that_changes_the_old_facts_or_holds_no_counter_is_refused(
        tmp_path, changes, word):
    head = start(tmp_path, LEGACY_A)
    shaped = {"schema": 2, "phase": "recovery_prepared", "prepared_boot": counter(42), **changes}
    if shaped["schema"] == 1:
        shaped.pop("prepared_boot")
        value = dict(head, **shaped)
        value.update(generation=head["generation"] + 1, previous_digest=digest(canonical(head)))
        exclusive(tmp_path / HOME / RECORDS / f"gen-{value['generation']:08d}.json",
                  canonical(value))
    else:
        forge(tmp_path, head, **shaped)
    assert word in refused(tmp_path)


def test_the_preparation_value_exists_only_in_the_preparation_and_the_recovery_it_completes(
        tmp_path):
    head = start(tmp_path, counter(42))
    assert head["schema"] == 2 and head["prepared_boot"] is None
    forge(tmp_path, head, schema=2, phase="closed", prepared_boot=counter(5))
    assert "preparation" in refused(tmp_path)


def test_a_direct_recovery_between_two_comparable_counters_needs_no_preparation(tmp_path):
    head = start(tmp_path, counter(42))
    done = recover(tmp_path, head, counter(43))
    assert done["prepared_boot"] is None and chain(tmp_path) == done


@pytest.mark.parametrize("measured", [counter(42), counter(7), counter(90, OTHER_GUID), LINUX_A])
def test_a_direct_recovery_between_counters_is_refused_unless_the_counter_is_greater(
        tmp_path, measured):
    head = start(tmp_path, counter(42))
    with pytest.raises(OwnerRefused):
        recover(tmp_path, head, measured)


def test_a_chain_never_goes_back_from_schema_two_to_schema_one(tmp_path):
    head = start(tmp_path, counter(42))
    value = {key: head[key] for key in OLD_FIELDS}
    value.update(schema=1, phase="closed", generation=head["generation"] + 1,
                 previous_digest=digest(canonical(head)))
    exclusive(tmp_path / HOME / RECORDS / f"gen-{value['generation']:08d}.json", canonical(value))
    assert "schema" in refused(tmp_path)


def test_an_unknown_schema_number_is_refused(tmp_path):
    head = start(tmp_path, LINUX_A)
    forge(tmp_path, head, schema=3, phase="closed")
    assert "shape" in refused(tmp_path)


def test_per_boot_id_records_stay_schema_one_and_keep_the_old_field_set(tmp_path):
    head = start(tmp_path, LINUX_A)
    assert head["schema"] == 1 and set(head) == OLD_FIELDS
    done = recover(tmp_path, head, LINUX_B)
    assert done["schema"] == 1 and set(done) == OLD_FIELDS
    with pytest.raises(OwnerRefused):
        recover(tmp_path, opened(tmp_path, done, LINUX_B, OTHER_SESSION), LINUX_B)


def test_every_record_this_version_writes_for_the_new_scheme_is_unreadable_to_the_old_reader(
        tmp_path):
    """The frozen old vocabulary: shape, phase and boot text each refuse it, independently."""
    prepared = prepare(tmp_path, start(tmp_path, LEGACY_A), counter(42))
    done = recover(tmp_path, prepared, counter(43))
    fresh_root = tmp_path / "fresh"
    fresh_root.mkdir()
    fresh = start(fresh_root, counter(7))
    for value in (prepared, done, fresh):
        assert value["schema"] != 1 and set(value) != OLD_FIELDS
    assert prepared["phase"] not in OLD_OPENED_SUCCESSORS
    for value in (done, fresh):
        assert OLD_BOOT.fullmatch(value["boot_id"]) is None
