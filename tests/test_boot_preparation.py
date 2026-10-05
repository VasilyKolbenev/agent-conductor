"""When may a NEW preparation be written: one decision for the project and for the login.

A preparation records the measurement a later recovery must be newer than. After the boot
environment changes, a second Restart does not make the old environment the current one, so the
old measurement can never be exceeded; the owner needs an explicit exit. This file holds the pure
decision, from two witness texts alone, that both recoveries use.
"""
from __future__ import annotations

import pytest

from conductor import boot_witness
from conductor.boot_witness import BootRefused, preparation_needed
from tests._boot_world import GUID, OTHER_GUID, assert_plain_restart_advice, counter

LEGACY = f"windows:{GUID}"
LINUX = "linux:5b1d9c0e-3b7a-4a76-9d0f-0d1f6c2e8a11"
DARWIN = "darwin:5b1d9c0e-3b7a-4a76-9d0f-0d1f6c2e8a11"


def refusal(recorded, current, **kwargs):
    with pytest.raises(BootRefused) as caught:
        preparation_needed(recorded, current, **kwargs)
    return caught.value


@pytest.mark.parametrize("current", [counter(1), counter(42), counter(900, OTHER_GUID)])
def test_a_legacy_record_needs_a_preparation_whatever_counter_the_machine_reads(current):
    assert preparation_needed(LEGACY, current, prepared=False) is True


@pytest.mark.parametrize("prepared", [False, True])
@pytest.mark.parametrize("current", [counter(1, OTHER_GUID), counter(42, OTHER_GUID),
                                     counter(9000, OTHER_GUID)])
def test_a_counter_of_another_environment_needs_a_new_preparation_whatever_its_value(
        prepared, current):
    assert preparation_needed(counter(42), current, prepared=prepared) is True


@pytest.mark.parametrize("current", [counter(5), counter(42), counter(43), counter(4294967294)])
def test_a_preparation_that_stands_in_this_environment_is_the_answer_whatever_the_counter(current):
    assert preparation_needed(counter(42), current, prepared=True) is False


def test_without_a_preparation_the_same_boot_is_refused_and_advises_a_full_restart_only():
    error = refusal(counter(42), counter(42), prepared=False)
    assert error.code == "same_boot"
    assert_plain_restart_advice(error.detail)


def test_without_a_preparation_a_lower_counter_of_this_environment_is_a_decrease_not_a_way_out():
    error = refusal(counter(42), counter(41), prepared=False)
    assert error.code == "counter_decreased"
    advice = error.detail.lower()
    assert "restart the os" not in advice and "full restart" not in advice


def test_without_a_preparation_a_greater_counter_of_this_environment_needs_none():
    error = refusal(counter(42), counter(43), prepared=False)
    assert error.code == "preparation_unneeded" and "already proven" in error.detail


@pytest.mark.parametrize("current", [LINUX, counter(42), counter(42, OTHER_GUID), LEGACY])
def test_a_per_boot_id_record_needs_no_preparation_whatever_is_measured_now(current):
    assert refusal(LINUX, current, prepared=False).code == "preparation_unneeded"
    assert refusal(DARWIN, current, prepared=False).code == "preparation_unneeded"


@pytest.mark.parametrize("recorded", [LEGACY, counter(42)])
@pytest.mark.parametrize("current", [LEGACY, LINUX, DARWIN])
def test_a_measurement_that_is_not_a_counter_prepares_nothing(recorded, current):
    assert refusal(recorded, current, prepared=False).code == "other_scheme"


def test_a_counter_with_no_room_above_it_is_never_a_baseline_for_a_new_preparation():
    saturated = f"windows-bootid.v1:{OTHER_GUID}:4294967295"
    for prepared in (False, True):
        assert refusal(counter(42), saturated, prepared=prepared).code == "counter_overflow"


@pytest.mark.parametrize("bad", ["", "windows:zzz", None, 42])
def test_an_unreadable_side_decides_nothing(bad):
    assert refusal(bad, counter(42), prepared=False).code == "unknown_format"
    assert refusal(counter(42), bad, prepared=False).code == "unknown_format"


def test_every_refusal_carries_a_code_of_the_closed_list_and_a_sentence():
    cases = [(counter(42), counter(42), False), (counter(42), counter(41), False),
             (counter(42), counter(43), False), (LINUX, counter(1), False),
             (LEGACY, LINUX, False), (counter(42), "x", True)]
    for recorded, current, prepared in cases:
        error = refusal(recorded, current, prepared=prepared)
        assert error.code in boot_witness.CODES and len(error.detail.split()) >= 4
